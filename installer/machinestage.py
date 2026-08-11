"""Build the machine payload from a pack checkout.

The machine installer consumes a target-relative payload tree plus the
partition copy that gates it (`installer.machinescope.load_payload`). Two
producers build that tree from the same checkout:

* `install.py --machine` stages it into a temporary directory and installs it
  straight away — the developer path, no plugin required;
* the plugin generator commits it under the plugin root, so a machine with only
  the plugin installed has the payload without a pack checkout.

Both call `build_payload()`, so what a developer installs from a checkout and
what a plugin ships are the same bytes by construction rather than by review.
The reference rewrite and its two gates come from `installer.references`,
shared in turn with the Claude plugin build.

Selection is the partition's decision, not this module's: a row is staged when
`PartitionGate.reject_reason` admits it, which is the same fail-closed rule the
installer applies at load time — so a platform still marked `provisional`
contributes nothing, and a row that lost its machine category disappears from
the payload instead of being installed by a stale copy of this list.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from installer.machinepayload import (
    PARTITION_FILE,
    PartitionGate,
    entry_is_executable,
    family_for_target,
    parse_partition,
)
from installer.references import (
    BIN_LITERAL_ALLOWLIST,
    MACHINE_CLOSURE_ALLOWLIST,
    MACHINE_PROFILE,
    ReferenceRewriteError,
    check_closure,
    check_executable_residue,
    check_text_residue,
    rewrite_text,
)

MANIFEST_PATH = "manifest.json"
PARTITION_PATH = "docs/fleet/surface-partition.json"

BIN_FAMILY = "agents-bin"
DOCS_FAMILY = "agents-docs"

EXECUTABLE_MODE = 0o755
DATA_MODE = 0o644


class MachineStageError(Exception):
    """A fail-closed condition in the machine payload build."""


@dataclass(frozen=True)
class StagedFile:
    """One payload file: its bytes and the mode its family implies."""

    content: bytes
    executable: bool


def _load_json(path: Path, label: str) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MachineStageError(f"{label} not found: {path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise MachineStageError(f"{label} is unreadable: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MachineStageError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise MachineStageError(f"{label} is not a JSON object: {path}")
    return loaded


def manifest_sources(root: Path) -> dict[str, str]:
    """Target -> authored template source, from the checkout manifest."""

    manifest = _load_json(root / MANIFEST_PATH, "manifest")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise MachineStageError(f"{MANIFEST_PATH} has no `files` list")
    sources: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise MachineStageError(f"{MANIFEST_PATH} `files` holds a non-object entry")
        target = str(row.get("target", ""))
        source = str(row.get("source", ""))
        if target and source:
            sources[target] = source
    return sources


def read_partition_document(root: Path) -> tuple[dict[str, object], PartitionGate]:
    """The partition artifact verbatim, plus the gate parsed from it.

    The document travels into the payload unchanged so the installed copy and
    the committed artifact are the same file, and the gate is parsed from that
    same object so staging and installing can never disagree about a row.
    """

    raw = _load_json(root / PARTITION_PATH, "surface partition")
    gate = parse_partition(raw)
    if isinstance(gate, str):
        raise MachineStageError(f"{PARTITION_PATH} is unusable: {gate}")
    return raw, gate


def _admitted_targets(gate: PartitionGate) -> list[str]:
    return sorted(target for target in gate.rows if gate.reject_reason(target) is None)


def build_payload(root: Path) -> dict[str, StagedFile]:
    """Every machine payload file, fully gated, keyed by payload-relative path."""

    sources = manifest_sources(root)
    document, gate = read_partition_document(root)
    targets = _admitted_targets(gate)
    if not targets:
        raise MachineStageError(
            f"{PARTITION_PATH} admits no machine-installable rows; a platform "
            "may still be provisional, or `make generate` has not run"
        )

    staged: dict[str, StagedFile] = {}
    text_bodies: dict[str, str] = {}
    for target in targets:
        family = family_for_target(target)
        if family is None:
            raise MachineStageError(
                f"machine row has no destination family: {target}; give the "
                "prefix a family in installer/machinepayload.py"
            )
        source = sources.get(target)
        if source is None:
            raise MachineStageError(f"machine row has no manifest source row: {target}")
        try:
            raw = (root / source).read_bytes()
        except OSError as exc:
            raise MachineStageError(
                f"cannot read template source {source} for {target}: {exc}"
            ) from exc
        relative = target[len(family.prefix) :]
        executable = entry_is_executable(family, relative)
        if family.name == BIN_FAMILY:
            # Executables travel verbatim into both payloads; their remaining
            # repository-root literals are layout data, gated by allowlist.
            staged[target] = StagedFile(content=raw, executable=executable)
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MachineStageError(
                f"template source is not UTF-8: {source}: {exc}"
            ) from exc
        body = rewrite_text(text, profile=MACHINE_PROFILE, key=target)
        text_bodies[target] = body
        staged[target] = StagedFile(content=body.encode("utf-8"), executable=False)

    _check_payload(staged, text_bodies)
    staged[PARTITION_FILE] = StagedFile(
        content=(json.dumps(document, indent=2) + "\n").encode("utf-8"),
        executable=False,
    )
    return dict(sorted(staged.items()))


def _check_payload(
    staged: dict[str, StagedFile],
    text_bodies: dict[str, str],
) -> None:
    """Residue and dependency closure, in this payload's own terms."""

    shipped_commands = frozenset(
        PurePosixPath(target).name
        for target in staged
        if family_of(target) == BIN_FAMILY
    )
    shipped_docs = frozenset(
        PurePosixPath(target).name
        for target in staged
        if family_of(target) == DOCS_FAMILY
    )
    for target, entry in sorted(staged.items()):
        if family_of(target) != BIN_FAMILY:
            continue
        name = PurePosixPath(target).name
        check_executable_residue(
            target,
            entry.content.decode("utf-8", errors="replace"),
            allowlist=BIN_LITERAL_ALLOWLIST,
            name=name,
        )
    for target, body in sorted(text_bodies.items()):
        check_text_residue(target, body, profile=MACHINE_PROFILE)
        check_closure(
            target,
            body,
            profile=MACHINE_PROFILE,
            shipped_commands=shipped_commands,
            shipped_docs=shipped_docs,
            allowlist=MACHINE_CLOSURE_ALLOWLIST,
        )


def family_of(target: str) -> str | None:
    family = family_for_target(target)
    return None if family is None else family.name


def materialize(staged: dict[str, StagedFile], destination: Path) -> None:
    """Write a built payload under `destination`."""

    for target, entry in sorted(staged.items()):
        path = destination / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(entry.content)
        os.chmod(path, EXECUTABLE_MODE if entry.executable else DATA_MODE)


@contextmanager
def staged_payload(root: Path) -> Iterator[Path]:
    """A temporary payload root built from `root`, removed on the way out."""

    staged = build_payload(root)
    directory = Path(tempfile.mkdtemp(prefix="sd-machine-payload-"))
    try:
        materialize(staged, directory)
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


__all__ = [
    "BIN_FAMILY",
    "DOCS_FAMILY",
    "MANIFEST_PATH",
    "PARTITION_PATH",
    "MachineStageError",
    "ReferenceRewriteError",
    "StagedFile",
    "build_payload",
    "family_of",
    "manifest_sources",
    "materialize",
    "read_partition_document",
    "staged_payload",
]
