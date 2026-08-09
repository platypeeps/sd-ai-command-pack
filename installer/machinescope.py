"""Machine-scope install engine: plan, apply, receipt, remove, status.

Installs the `machine-other` partition slice plus the `sharedRuntime` scripts
into user-level destinations (`~/.agents`, `~/.gemini/commands`, the XDG
OpenCode config root) so non-Claude surfaces resolve the pack without a
vendored copy. The destination families, the payload digest, and the partition
gate live in `installer.machinepayload`, shared with the plugin generator that
bundles the same payload.

Three properties drive the shape of this module:

* **Nothing is written before every conflict is known.** Phase 1 classifies
  every target, phase 2 applies, phase 3 commits the receipt. A single
  unowned or drifted path refuses the whole run.
* **Ownership is proven, never inferred.** Byte identity alone does not make a
  file ours: a pre-existing user file identical to the payload must not be
  adopted, because `remove` would later delete it. An interrupted run is
  recovered through the intent journal it wrote before its first write, which
  is the only evidence that admits a receipt-absent path.
* **The receipt authorizes deletes, so it is validated like untrusted input.**
  Family allowlist, relative traversal-free paths, containment after
  resolution; one bad entry invalidates the whole receipt.

Errors are `MachineInstallError`, carrying the process exit code, so callers
(`install.py --machine`, the plugin bootstrap, the status collector) share one
error model instead of trapping `SystemExit` strings.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import ModuleType

from installer.fileops import atomic_write_bytes
from installer.machinepayload import (
    FAMILIES_BY_NAME,
    PARTITION_FILE,
    DestinationFamily,
    PartitionGate,
    PayloadEntry,
    content_digest,
    entry_is_executable,
    family_for_target,
    family_roots,
    payload_digest,
    payload_targets,
    read_partition,
)
from installer.status import StringStatus

RECEIPT_SCHEMA_VERSION = 1
INTENT_SCHEMA_VERSION = 1
STATUS_SCHEMA_VERSION = 1

# Every private state surface hangs off the shared ladder root under its own
# subdirectory; this one owns the receipt and the intent journal.
MACHINE_STATE_DIR = "machine"
RECEIPT_FILE = "machine-receipt.json"
INTENT_FILE = "machine-install.intent.json"

DEFAULT_PAYLOAD_DIRNAME = "machine-payload"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFLICT = 2

SHARED_LIB_MODULE = "sd_ai_command_pack_lib"
# The shipped helper is not an `installer` module: it lives beside the scripts
# that import it, which is `scripts/` in a pack checkout and `bin/` under a
# plugin root. Both are siblings of this package's parent.
SHARED_LIB_DIRECTORIES = ("scripts", "bin")

# OpenCode's own opt-outs for the external-skills lane. Neither changes what
# gets installed -- they are per-environment variables another shell may not
# set -- but silently installing a surface the operator's OpenCode ignores is
# worth one line.
OPENCODE_SKILL_OPT_OUTS = (
    "OPENCODE_DISABLE_EXTERNAL_SKILLS",
    "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS",
)

_DIGEST_PREFIX = "sha256:"
_DIGEST_LENGTH = len(_DIGEST_PREFIX) + 64


class MachineInstallError(RuntimeError):
    """A refusal or failure that ends the run, carrying its exit code."""

    def __init__(self, message: str, *, exit_code: int = EXIT_ERROR) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class PlanStatus(StringStatus):
    """How one payload target relates to the receipt and the destination."""

    OWNED_CURRENT = "owned-current"
    OWNED_STALE = "owned-stale"
    ABSENT = "absent"
    DRIFTED = "drifted"
    UNOWNED = "unowned"
    SYMLINK = "symlink"
    SYMLINK_PARENT = "symlink-parent"
    NOT_A_FILE = "not-a-file"


class FileState(StringStatus):
    """How one receipt entry compares against what is on disk now."""

    CURRENT = "current"
    MISSING = "missing"
    DRIFTED = "drifted"
    MODE_DRIFT = "mode-drift"
    SYMLINK = "symlink"
    UNREADABLE = "unreadable"


class MachineState(StringStatus):
    """Receipt-level state reported by `status`."""

    NONE = "none"
    INSTALLED = "installed"
    INVALID = "invalid"


# --force displaces these after taking a backup.
FORCEABLE_STATUSES = frozenset({PlanStatus.DRIFTED, PlanStatus.UNOWNED})
# --force never displaces these: a symlink or a non-file cannot be backed up
# and restored faithfully, so `remove`'s restoration promise would be a lie.
REFUSED_STATUSES = frozenset(
    {
        PlanStatus.SYMLINK,
        PlanStatus.SYMLINK_PARENT,
        PlanStatus.NOT_A_FILE,
    }
)
WRITE_STATUSES = frozenset(
    {
        PlanStatus.OWNED_STALE,
        PlanStatus.ABSENT,
        PlanStatus.DRIFTED,
        PlanStatus.UNOWNED,
    }
)


# --------------------------------------------------------------------------
# Shared helper library (state-root ladder)
# --------------------------------------------------------------------------

_shared_lib_cache: ModuleType | None = None


def _shared_lib() -> ModuleType:
    """The shipped helper library that owns the user-local state-root ladder.

    Loaded by path rather than re-implemented here: `resolve_state_root` has
    exactly one definition in the repository, and one variable
    (`SD_AI_COMMAND_PACK_STATE_HOME`) must keep moving every private state
    surface, this one included.
    """

    global _shared_lib_cache
    if _shared_lib_cache is None:
        _shared_lib_cache = _load_shared_lib()
    return _shared_lib_cache


def _load_shared_lib() -> ModuleType:
    existing = sys.modules.get(SHARED_LIB_MODULE)
    if existing is not None:
        return existing
    package_parent = Path(__file__).resolve().parent.parent
    for directory in SHARED_LIB_DIRECTORIES:
        candidate = package_parent / directory / f"{SHARED_LIB_MODULE}.py"
        if not candidate.is_file():
            continue
        spec = importlib.util.spec_from_file_location(SHARED_LIB_MODULE, candidate)
        if spec is None or spec.loader is None:  # pragma: no cover - loader always set
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[SHARED_LIB_MODULE] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(SHARED_LIB_MODULE, None)
            raise
        return module
    raise MachineInstallError(
        f"shared helper library {SHARED_LIB_MODULE}.py not found beside the "
        f"installer package (looked in: {', '.join(SHARED_LIB_DIRECTORIES)})"
    )


def resolve_home(home: Path | None = None) -> Path:
    """The destination home directory, or an error when it cannot resolve.

    Gemini falls back to a temporary directory when the home directory is
    unresolvable; the installer treats that as unsupported rather than writing
    a machine payload somewhere that vanishes on reboot.
    """

    if home is not None:
        candidate = home.expanduser()
    else:
        try:
            candidate = Path.home()
        except RuntimeError as error:
            raise MachineInstallError(f"cannot resolve home directory: {error}") from None
    if not candidate.is_absolute():
        raise MachineInstallError(f"home directory must be absolute: {candidate}")
    return candidate


def state_directory(
    *,
    environ: Mapping[str, str],
    home: Path,
    state_home: Path | None = None,
    create: bool,
) -> Path:
    """The private directory holding the receipt and the intent journal."""

    lib = _shared_lib()
    try:
        root = lib.resolve_state_root(environ=environ, home=home, state_home=state_home)
    except RuntimeError as error:
        raise MachineInstallError(f"cannot resolve state root: {error}") from None
    directory = Path(root) / MACHINE_STATE_DIR
    if not create:
        return directory
    try:
        lib.ensure_private_directory(directory, label="machine state directory")
    except RuntimeError as error:
        raise MachineInstallError(f"cannot prepare state directory: {error}") from None
    return directory


def receipt_path(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    state_home: Path | None = None,
) -> Path:
    """Where the machine receipt lives, without creating anything.

    Exposed for the status collector, which reads the receipt directly and
    must never need a plugin root to find it.
    """

    resolved_environ = os.environ if environ is None else environ
    return (
        state_directory(
            environ=resolved_environ,
            home=resolve_home(home),
            state_home=state_home,
            create=False,
        )
        / RECEIPT_FILE
    )


# --------------------------------------------------------------------------
# Payload
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Payload:
    """A validated machine payload: admitted entries and their identity."""

    root: Path
    entries: tuple[PayloadEntry, ...]
    digest: str
    pack_version: str


def default_payload_root() -> Path:
    """The payload bundled beside this package, used when no root is given."""

    return Path(__file__).resolve().parent.parent / DEFAULT_PAYLOAD_DIRNAME


def load_payload(root: Path) -> Payload:
    """Read and gate a payload root, or refuse with every reason listed."""

    if not root.is_dir():
        raise MachineInstallError(f"payload root not found or not a directory: {root}")
    gate = read_partition(root / PARTITION_FILE)
    if isinstance(gate, str):
        raise MachineInstallError(gate)
    targets = payload_targets(root)
    if isinstance(targets, str):
        raise MachineInstallError(targets)
    if not targets:
        raise MachineInstallError(f"payload root holds no installable files: {root}")

    entries: list[PayloadEntry] = []
    refusals: list[str] = []
    for target in targets:
        reason = gate.reject_reason(target)
        if reason is not None:
            refusals.append(f"{target}: {reason}")
            continue
        family = family_for_target(target)
        if family is None:
            refusals.append(f"{target}: no machine destination family")
            continue
        relative = target[len(family.prefix) :]
        try:
            content = (root / target).read_bytes()
        except OSError as error:
            refusals.append(f"{target}: cannot be read ({error.strerror or error})")
            continue
        entries.append(
            PayloadEntry(
                target=target,
                family=family,
                relative=relative,
                content=content,
                executable=entry_is_executable(family, relative),
            )
        )
    if refusals:
        raise MachineInstallError(
            "payload is not machine-installable:\n"
            + "\n".join(f"  {line}" for line in sorted(refusals))
        )
    return Payload(
        root=root,
        entries=tuple(sorted(entries, key=lambda entry: entry.target)),
        digest=payload_digest(entries),
        pack_version=gate.pack_version,
    )


# --------------------------------------------------------------------------
# Receipt
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BackupRecord:
    """The `.bak` sibling holding content a --force overwrite displaced."""

    path: str
    digest: str


@dataclass(frozen=True)
class ReceiptFile:
    family: str
    path: str
    digest: str
    executable: bool
    backup: BackupRecord | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.family, self.path)


@dataclass(frozen=True)
class Receipt:
    pack_version: str
    payload_digest: str
    installed_at: str
    source_root: str
    files: tuple[ReceiptFile, ...]

    def by_key(self) -> dict[tuple[str, str], ReceiptFile]:
        return {entry.key: entry for entry in self.files}


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _DIGEST_LENGTH
        and value.startswith(_DIGEST_PREFIX)
        and all(character in "0123456789abcdef" for character in value[len(_DIGEST_PREFIX) :])
    )


def _safe_relative(value: object) -> str | None:
    """A family-relative POSIX path that cannot escape its family root."""

    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        return None
    if value.startswith("/") or PurePosixPath(value).is_absolute():
        return None
    parts = PurePosixPath(value).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        return None
    if PurePosixPath(*parts).as_posix() != value:
        return None
    return value


def _resolved_within(root: Path, relative: str) -> Path | None:
    """The destination for `relative`, or None when it escapes `root`.

    Containment is decided on the resolved *parent* directory. Resolving the
    full path would follow a symlink at the final component and report a
    perfectly legitimate target as an escape; a link sitting there is a
    conflict for the planner to classify, not a containment breach. A
    symlinked intermediate directory pointing out of the tree still fails
    here, which is the traversal this guards against.
    """

    destination = root / relative
    try:
        resolved_root = root.resolve(strict=False)
        resolved_parent = destination.parent.resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    try:
        resolved_parent.relative_to(resolved_root)
    except ValueError:
        return None
    return destination


def _symlinked_parent(root: Path, destination: Path) -> Path | None:
    """The nearest symlinked directory from the family root down, if any.

    The family root is checked too. A symlinked root resolves consistently and
    so passes containment, but writing through it would put pack files
    somewhere `remove` cannot reason about, so it refuses instead.
    """

    current = destination.parent
    while True:
        if current.is_symlink():
            return current
        if current == root or current == current.parent:
            return None
        current = current.parent


def parse_receipt(raw: object, roots: Mapping[str, Path]) -> Receipt:
    """Validate untrusted receipt JSON, or raise naming the first violation.

    Every entry is checked before any is trusted: the receipt is what
    authorizes overwrites and deletes, so partial trust is not an option.
    """

    if not isinstance(raw, dict):
        raise MachineInstallError("receipt is not a JSON object")
    version = raw.get("schemaVersion")
    if version != RECEIPT_SCHEMA_VERSION:
        raise MachineInstallError(f"receipt schemaVersion {version!r} is not supported")
    strings: dict[str, str] = {}
    for key in ("packVersion", "payloadDigest", "installedAt", "sourceRoot"):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MachineInstallError(f"receipt {key} is missing or not a string")
        strings[key] = value
    if not _is_digest(strings["payloadDigest"]):
        raise MachineInstallError("receipt payloadDigest is not a sha256 digest")
    raw_files = raw.get("files")
    if not isinstance(raw_files, list):
        raise MachineInstallError("receipt files is not an array")

    files: list[ReceiptFile] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(raw_files):
        entry = _parse_receipt_file(row, roots, index)
        if entry.key in seen:
            raise MachineInstallError(
                f"receipt entry {index} repeats {entry.family}/{entry.path}"
            )
        seen.add(entry.key)
        files.append(entry)
    return Receipt(
        pack_version=strings["packVersion"],
        payload_digest=strings["payloadDigest"],
        installed_at=strings["installedAt"],
        source_root=strings["sourceRoot"],
        files=tuple(files),
    )


def _parse_receipt_file(
    row: object,
    roots: Mapping[str, Path],
    index: int,
) -> ReceiptFile:
    if not isinstance(row, dict):
        raise MachineInstallError(f"receipt entry {index} is not an object")
    family = row.get("family")
    if not isinstance(family, str) or family not in FAMILIES_BY_NAME:
        raise MachineInstallError(f"receipt entry {index} names unknown family {family!r}")
    root = roots.get(family)
    if root is None:  # pragma: no cover - roots always cover every family
        raise MachineInstallError(f"receipt entry {index} family {family} has no root")
    relative = _safe_relative(row.get("path"))
    if relative is None:
        raise MachineInstallError(f"receipt entry {index} path is not a safe relative path")
    if _resolved_within(root, relative) is None:
        raise MachineInstallError(
            f"receipt entry {index} path resolves outside {family}: {row.get('path')!r}"
        )
    digest = row.get("digest")
    if not _is_digest(digest):
        raise MachineInstallError(f"receipt entry {index} digest is not a sha256 digest")
    executable = row.get("executable")
    if not isinstance(executable, bool):
        raise MachineInstallError(f"receipt entry {index} executable is not a boolean")
    backup = _parse_backup(row.get("backup"), root, family, index)
    assert isinstance(digest, str)
    return ReceiptFile(
        family=family,
        path=relative,
        digest=digest,
        executable=executable,
        backup=backup,
    )


def _parse_backup(
    raw: object,
    root: Path,
    family: str,
    index: int,
) -> BackupRecord | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise MachineInstallError(f"receipt entry {index} backup is not an object")
    relative = _safe_relative(raw.get("path"))
    if relative is None:
        raise MachineInstallError(
            f"receipt entry {index} backup path is not a safe relative path"
        )
    if _resolved_within(root, relative) is None:
        raise MachineInstallError(
            f"receipt entry {index} backup path resolves outside {family}: "
            f"{raw.get('path')!r}"
        )
    digest = raw.get("digest")
    if not _is_digest(digest):
        raise MachineInstallError(f"receipt entry {index} backup digest is not a sha256 digest")
    assert isinstance(digest, str)
    return BackupRecord(path=relative, digest=digest)


def read_receipt(path: Path, roots: Mapping[str, Path]) -> Receipt | None:
    """The validated receipt at `path`, or None when there is none."""

    if path.is_symlink():
        raise MachineInstallError(f"receipt must not be a symlink: {path}")
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise MachineInstallError(f"receipt is unreadable: {path}: {error}") from None
    return parse_receipt(raw, roots)


def receipt_content(receipt: Receipt) -> str:
    files: list[dict[str, object]] = []
    for entry in sorted(receipt.files, key=lambda item: item.key):
        row: dict[str, object] = {
            "family": entry.family,
            "path": entry.path,
            "digest": entry.digest,
            "executable": entry.executable,
        }
        if entry.backup is not None:
            row["backup"] = {"path": entry.backup.path, "digest": entry.backup.digest}
        files.append(row)
    payload = {
        "schemaVersion": RECEIPT_SCHEMA_VERSION,
        "packVersion": receipt.pack_version,
        "payloadDigest": receipt.payload_digest,
        "installedAt": receipt.installed_at,
        "sourceRoot": receipt.source_root,
        "files": files,
    }
    return json.dumps(payload, indent=2) + "\n"


# --------------------------------------------------------------------------
# Intent journal
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Intent:
    payload_digest: str
    paths: frozenset[tuple[str, str]]


def parse_intent(raw: object) -> Intent | None:
    if not isinstance(raw, dict):
        return None
    if raw.get("schemaVersion") != INTENT_SCHEMA_VERSION:
        return None
    digest = raw.get("payloadDigest")
    if not _is_digest(digest):
        return None
    rows = raw.get("paths")
    if not isinstance(rows, list):
        return None
    paths: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            return None
        family = row.get("family")
        relative = _safe_relative(row.get("path"))
        if not isinstance(family, str) or family not in FAMILIES_BY_NAME or relative is None:
            return None
        paths.add((family, relative))
    assert isinstance(digest, str)
    return Intent(payload_digest=digest, paths=frozenset(paths))


def read_intent(path: Path) -> Intent | None:
    """The intent journal left by an interrupted run, or None.

    A malformed journal is None rather than an error: it is evidence, and
    unreadable evidence proves nothing, so the paths it would have vouched for
    stay unowned.
    """

    if path.is_symlink() or not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return parse_intent(raw)


def intent_content(payload: Payload) -> str:
    paths = [
        {"family": entry.family.name, "path": entry.relative}
        for entry in sorted(payload.entries, key=lambda item: item.target)
    ]
    return (
        json.dumps(
            {
                "schemaVersion": INTENT_SCHEMA_VERSION,
                "payloadDigest": payload.digest,
                "paths": paths,
            },
            indent=2,
        )
        + "\n"
    )


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedFile:
    entry: PayloadEntry
    destination: Path
    status: PlanStatus
    detail: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.entry.family.name, self.entry.relative)


@dataclass(frozen=True)
class PlannedRemoval:
    entry: ReceiptFile
    destination: Path
    removable: bool
    detail: str | None = None
    restores_backup: bool = False


@dataclass(frozen=True)
class Plan:
    payload: Payload
    roots: dict[str, Path]
    files: tuple[PlannedFile, ...]
    removals: tuple[PlannedRemoval, ...]
    receipt: Receipt | None
    intent: Intent | None
    notes: tuple[str, ...]

    @property
    def conflicts(self) -> tuple[PlannedFile, ...]:
        return tuple(
            planned
            for planned in self.files
            if planned.status in FORCEABLE_STATUSES or planned.status in REFUSED_STATUSES
        )

    @property
    def refusals(self) -> tuple[PlannedFile, ...]:
        return tuple(planned for planned in self.files if planned.status in REFUSED_STATUSES)

    def writes(self) -> tuple[PlannedFile, ...]:
        return tuple(planned for planned in self.files if planned.status in WRITE_STATUSES)


def _destination_state(destination: Path) -> PlanStatus | None:
    """A blocking node at the destination, or None when it is usable."""

    if destination.is_symlink():
        return PlanStatus.SYMLINK
    if destination.exists() and not destination.is_file():
        return PlanStatus.NOT_A_FILE
    return None


def _file_identity(destination: Path) -> tuple[str, bool] | None:
    try:
        content = destination.read_bytes()
        mode = destination.stat().st_mode
    except OSError:
        return None
    return content_digest(content), bool(mode & stat.S_IXUSR)


def _classify(
    entry: PayloadEntry,
    destination: Path,
    root: Path,
    owned: ReceiptFile | None,
    intent: Intent | None,
    payload: Payload,
) -> PlannedFile:
    symlinked = _symlinked_parent(root, destination)
    if symlinked is not None:
        return PlannedFile(
            entry,
            destination,
            PlanStatus.SYMLINK_PARENT,
            f"parent directory is a symlink: {symlinked}",
        )
    blocking = _destination_state(destination)
    if blocking is not None:
        return PlannedFile(entry, destination, blocking)
    if not destination.exists():
        return PlannedFile(entry, destination, PlanStatus.ABSENT)
    identity = _file_identity(destination)
    if identity is None:
        return PlannedFile(entry, destination, PlanStatus.DRIFTED, "cannot be read")
    digest, executable = identity
    matches_payload = digest == entry.digest and executable == entry.executable
    if owned is not None:
        if matches_payload:
            return PlannedFile(entry, destination, PlanStatus.OWNED_CURRENT)
        if digest == owned.digest and executable == owned.executable:
            return PlannedFile(entry, destination, PlanStatus.OWNED_STALE)
        return PlannedFile(entry, destination, PlanStatus.DRIFTED, "content changed locally")
    # Receipt-absent. Byte identity alone never proves authorship; only an
    # intent journal from an interrupted run of this exact payload does.
    if (
        matches_payload
        and intent is not None
        and intent.payload_digest == payload.digest
        and (entry.family.name, entry.relative) in intent.paths
    ):
        return PlannedFile(entry, destination, PlanStatus.OWNED_CURRENT)
    return PlannedFile(entry, destination, PlanStatus.UNOWNED, "not recorded in the receipt")


def build_plan(
    payload: Payload,
    *,
    roots: Mapping[str, Path],
    receipt: Receipt | None,
    intent: Intent | None,
) -> Plan:
    notes: list[str] = []
    if intent is not None and intent.payload_digest != payload.digest:
        notes.append(
            "discarding an intent journal written for a different payload "
            f"({intent.payload_digest})"
        )
        intent = None

    owned = receipt.by_key() if receipt is not None else {}
    planned_files: list[PlannedFile] = []
    for entry in payload.entries:
        root = roots[entry.family.name]
        destination = _resolved_within(root, entry.relative)
        if destination is None:
            raise MachineInstallError(
                f"payload target resolves outside {entry.family.name}: {entry.target}"
            )
        planned_files.append(
            _classify(
                entry,
                destination,
                root,
                owned.get((entry.family.name, entry.relative)),
                intent,
                payload,
            )
        )

    current_keys = {planned.key for planned in planned_files}
    removals: list[PlannedRemoval] = []
    if receipt is not None:
        for record in sorted(receipt.files, key=lambda item: item.key):
            if record.key in current_keys:
                continue
            removals.append(_plan_removal(record, roots[record.family]))
    return Plan(
        payload=payload,
        roots=dict(roots),
        files=tuple(planned_files),
        removals=tuple(removals),
        receipt=receipt,
        intent=intent,
        notes=tuple(notes),
    )


def _plan_removal(record: ReceiptFile, root: Path) -> PlannedRemoval:
    destination = _resolved_within(root, record.path)
    if destination is None:  # pragma: no cover - parse_receipt already refused these
        raise MachineInstallError(
            f"receipt entry resolves outside {record.family}: {record.path}"
        )
    symlinked = _symlinked_parent(root, destination)
    if symlinked is not None:
        return PlannedRemoval(
            record,
            destination,
            False,
            f"parent directory is a symlink: {symlinked}",
        )
    if destination.is_symlink():
        return PlannedRemoval(record, destination, False, "is a symlink")
    if not destination.exists():
        return PlannedRemoval(record, destination, False, "already gone")
    if not destination.is_file():
        return PlannedRemoval(record, destination, False, "is not a regular file")
    identity = _file_identity(destination)
    if identity is None:
        return PlannedRemoval(record, destination, False, "cannot be read")
    digest, executable = identity
    if digest != record.digest or executable != record.executable:
        return PlannedRemoval(record, destination, False, "modified since install")
    return PlannedRemoval(
        record,
        destination,
        True,
        restores_backup=record.backup is not None and _backup_problem(root, record) is None,
    )


# --------------------------------------------------------------------------
# Applying
# --------------------------------------------------------------------------


def _write_bytes(destination: Path, content: bytes, *, executable: bool) -> None:
    """Atomic write through the package primitive, in this module's error model."""

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise MachineInstallError(
            f"cannot create directory {destination.parent}: {error.strerror or error}"
        ) from None
    try:
        atomic_write_bytes(destination, content, executable=executable)
    except SystemExit as error:
        raise MachineInstallError(str(error).removeprefix("error: ")) from None


def _next_backup_path(root: Path, destination: Path) -> Path:
    index = 0
    while True:
        suffix = ".bak" if index == 0 else f".bak{index}"
        candidate = destination.with_name(f"{destination.name}{suffix}")
        if not (candidate.exists() or candidate.is_symlink()):
            relative = candidate.relative_to(root).as_posix()
            if _safe_relative(relative) is None or _resolved_within(root, relative) is None:
                raise MachineInstallError(f"unsafe backup path: {candidate}")
            return candidate
        index += 1


def _backup_displaced_file(root: Path, destination: Path) -> BackupRecord:
    """Copy the file --force is about to displace, preserving its mode."""

    backup = _next_backup_path(root, destination)
    try:
        # copy2 keeps the mode, so `remove` can rename the backup back into
        # place and restore the original exactly as the user had it.
        shutil.copy2(destination, backup)
        content = backup.read_bytes()
    except OSError as error:
        raise MachineInstallError(
            f"cannot back up {destination}: {error.strerror or error}"
        ) from None
    return BackupRecord(
        path=backup.relative_to(root).as_posix(),
        digest=content_digest(content),
    )


def _prune_empty_directories(root: Path, destination: Path) -> None:
    current = destination.parent
    while True:
        try:
            current.rmdir()
        except OSError:
            return
        if current == root:
            return
        current = current.parent


def apply_plan(
    plan: Plan,
    *,
    state_dir: Path,
    force: bool,
) -> Receipt:
    """Write the payload, prune removed rows, and return the new receipt."""

    intent_file = state_dir / INTENT_FILE
    writes = plan.writes()
    removals = [removal for removal in plan.removals if removal.removable]
    if writes or removals:
        _write_bytes(intent_file, intent_content(plan.payload).encode("utf-8"), executable=False)

    owned = plan.receipt.by_key() if plan.receipt is not None else {}
    files: list[ReceiptFile] = []
    for planned in plan.files:
        entry = planned.entry
        previous = owned.get(planned.key)
        # An earlier run's backup already holds the pre-pack original, and the
        # receipt carries one backup per file. Taking a second one would record
        # our own displaced payload and strand the user's content under a name
        # nothing explains, so the first backup is the one that survives.
        backup = previous.backup if previous is not None else None
        if backup is None and force and planned.status in FORCEABLE_STATUSES:
            backup = _backup_displaced_file(plan.roots[entry.family.name], planned.destination)
        if planned.status in WRITE_STATUSES:
            _write_bytes(planned.destination, entry.content, executable=entry.executable)
        files.append(
            ReceiptFile(
                family=entry.family.name,
                path=entry.relative,
                digest=entry.digest,
                executable=entry.executable,
                backup=backup,
            )
        )

    for removal in removals:
        root = plan.roots[removal.entry.family]
        # This is the last moment the receipt still remembers the backup, so a
        # row that leaves the payload restores its displaced original now
        # rather than stranding a .bak nothing will ever explain.
        if not (removal.restores_backup and _restore_backup(root, removal.entry, dry_run=False)):
            _unlink(removal.destination)
        _prune_empty_directories(root, removal.destination)

    receipt = Receipt(
        pack_version=plan.payload.pack_version,
        payload_digest=plan.payload.digest,
        installed_at=_timestamp(),
        source_root=str(plan.payload.root),
        files=tuple(files),
    )
    _write_bytes(
        state_dir / RECEIPT_FILE,
        receipt_content(receipt).encode("utf-8"),
        executable=False,
    )
    _unlink_if_present(intent_file)
    return receipt


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError as error:
        raise MachineInstallError(f"cannot remove {path}: {error.strerror or error}") from None


def _unlink_if_present(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as error:
        raise MachineInstallError(f"cannot remove {path}: {error.strerror or error}") from None


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------


def opencode_skill_advisory(environ: Mapping[str, str]) -> str | None:
    """One line when this environment tells OpenCode to ignore ~/.agents/skills.

    Advisory only, never a gate: the opt-out is per-environment, so the payload
    still installs for every other shell and platform that reads the surface.
    """

    disabled = [
        name for name in OPENCODE_SKILL_OPT_OUTS if environ.get(name, "").strip() == "1"
    ]
    if not disabled:
        return None
    return (
        f"{' and '.join(disabled)} is set here, so OpenCode will not autoload the "
        "installed ~/.agents/skills surface in this environment"
    )


@dataclass(frozen=True)
class InstallOutcome:
    plan: Plan
    receipt: Receipt | None
    dry_run: bool
    forced: bool
    advisories: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.plan.writes()) or any(
            removal.removable for removal in self.plan.removals
        )


def install(
    payload_root: Path,
    *,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    state_home: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> InstallOutcome:
    resolved_environ = os.environ if environ is None else environ
    resolved_home = resolve_home(home)
    roots = family_roots(home=resolved_home, environ=resolved_environ)
    payload = load_payload(payload_root)
    state_dir = state_directory(
        environ=resolved_environ,
        home=resolved_home,
        state_home=state_home,
        create=not dry_run,
    )
    receipt = read_receipt(state_dir / RECEIPT_FILE, roots)
    intent = read_intent(state_dir / INTENT_FILE)
    plan = build_plan(payload, roots=roots, receipt=receipt, intent=intent)

    refusals = plan.refusals
    if refusals:
        raise MachineInstallError(
            _conflict_message(
                "refusing to install; these destinations cannot be replaced safely",
                refusals,
                advice="resolve them by hand and rerun",
            ),
            exit_code=EXIT_CONFLICT,
        )
    conflicts = plan.conflicts
    if conflicts and not force:
        raise MachineInstallError(
            _conflict_message(
                "refusing to install over files this receipt does not own",
                conflicts,
                advice="rerun with --force to overwrite them (originals are backed up)",
            ),
            exit_code=EXIT_CONFLICT,
        )
    advisory = opencode_skill_advisory(resolved_environ)
    advisories = () if advisory is None else (advisory,)
    if dry_run:
        return InstallOutcome(
            plan=plan, receipt=None, dry_run=True, forced=force, advisories=advisories
        )
    new_receipt = apply_plan(plan, state_dir=state_dir, force=force)
    return InstallOutcome(
        plan=plan,
        receipt=new_receipt,
        dry_run=False,
        forced=force,
        advisories=advisories,
    )


def _conflict_message(
    headline: str,
    conflicts: Sequence[PlannedFile],
    *,
    advice: str,
) -> str:
    lines = [f"{headline}:"]
    for planned in sorted(conflicts, key=lambda item: str(item.destination)):
        detail = f" ({planned.detail})" if planned.detail else ""
        lines.append(f"  {planned.status}: {planned.destination}{detail}")
    lines.append(advice)
    return "\n".join(lines)


@dataclass(frozen=True)
class RemovalOutcome:
    had_receipt: bool
    removed: tuple[Path, ...]
    restored: tuple[Path, ...]
    skipped: tuple[tuple[Path, str], ...]
    dry_run: bool


def remove(
    *,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    state_home: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> RemovalOutcome:
    """Delete receipt-owned files and restore --force-displaced originals.

    The "clean machine" claim is exactly this and no more: files this receipt
    recorded installing are removed, and files it recorded displacing are put
    back from their digest-verified backups. Anything else stays.
    """

    resolved_environ = os.environ if environ is None else environ
    resolved_home = resolve_home(home)
    roots = family_roots(home=resolved_home, environ=resolved_environ)
    state_dir = state_directory(
        environ=resolved_environ,
        home=resolved_home,
        state_home=state_home,
        create=False,
    )
    receipt = read_receipt(state_dir / RECEIPT_FILE, roots)
    if receipt is None:
        return RemovalOutcome(False, (), (), (), dry_run)

    planned = [_plan_removal(record, roots[record.family]) for record in receipt.files]
    # Everything that could refuse is decided here, before the first deletion,
    # so a mid-loop refusal can never leave the machine half-removed.
    problems: list[tuple[Path, str]] = []
    for removal in planned:
        if not removal.removable and removal.detail != "already gone":
            problems.append((removal.destination, removal.detail or "cannot be removed"))
        backup_problem = _backup_problem(roots[removal.entry.family], removal.entry)
        if backup_problem is not None:
            problems.append(backup_problem)
    if problems and not force:
        lines = ["refusing to remove; these paths no longer match the receipt:"]
        lines.extend(f"  {path}: {detail}" for path, detail in sorted(problems))
        lines.append("rerun with --force to remove what can be removed")
        raise MachineInstallError("\n".join(lines), exit_code=EXIT_CONFLICT)

    removed: list[Path] = []
    restored: list[Path] = []
    for removal in planned:
        root = roots[removal.entry.family]
        deletable = removal.removable or (
            force
            and removal.detail != "already gone"
            and not removal.destination.is_symlink()
            and removal.destination.is_file()
            and _symlinked_parent(root, removal.destination) is None
        )
        if deletable:
            if not dry_run:
                _unlink(removal.destination)
            removed.append(removal.destination)
        if _restore_backup(root, removal.entry, dry_run=dry_run):
            restored.append(removal.destination)
        if not dry_run:
            _prune_empty_directories(root, removal.destination)

    if not dry_run:
        _unlink_if_present(state_dir / RECEIPT_FILE)
        _unlink_if_present(state_dir / INTENT_FILE)
    # --force turns some of the refusals above into deletions; a path it did
    # delete is reported as removed and nothing else, or the same run would
    # claim to have both removed and skipped it.
    deleted = set(removed)
    return RemovalOutcome(
        had_receipt=True,
        removed=tuple(removed),
        restored=tuple(restored),
        skipped=tuple((path, detail) for path, detail in problems if path not in deleted),
        dry_run=dry_run,
    )


def _backup_path(root: Path, record: ReceiptFile) -> Path | None:
    if record.backup is None:
        return None
    return _resolved_within(root, record.backup.path)


def _backup_problem(root: Path, record: ReceiptFile) -> tuple[Path, str] | None:
    """Why a recorded backup cannot be restored, or None when it can."""

    backup = _backup_path(root, record)
    if backup is None or record.backup is None:
        return None
    if backup.is_symlink() or not backup.is_file():
        return (backup, "recorded backup is missing")
    identity = _file_identity(backup)
    if identity is None or identity[0] != record.backup.digest:
        return (backup, "backup no longer matches the digest recorded at backup time")
    return None


def _restore_backup(root: Path, record: ReceiptFile, *, dry_run: bool) -> bool:
    """Put a --force-displaced original back, leaving unverifiable ones alone."""

    if _backup_problem(root, record) is not None:
        return False
    backup = _backup_path(root, record)
    destination = _resolved_within(root, record.path)
    if backup is None or destination is None:
        return False
    if dry_run:
        return True
    try:
        # A rename inside one directory restores bytes and mode atomically and
        # retires the .bak in the same step.
        os.replace(backup, destination)
    except OSError as error:
        raise MachineInstallError(
            f"cannot restore {destination} from {backup}: {error.strerror or error}"
        ) from None
    return True


def status(
    *,
    payload_root: Path | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    state_home: Path | None = None,
) -> dict[str, object]:
    """Receipt state and per-file drift, optionally against a payload root."""

    resolved_environ = os.environ if environ is None else environ
    resolved_home = resolve_home(home)
    roots = family_roots(home=resolved_home, environ=resolved_environ)
    state_dir = state_directory(
        environ=resolved_environ,
        home=resolved_home,
        state_home=state_home,
        create=False,
    )
    path = state_dir / RECEIPT_FILE
    report: dict[str, object] = {
        "schemaVersion": STATUS_SCHEMA_VERSION,
        "receiptPath": str(path),
        "state": str(MachineState.NONE),
        "packVersion": None,
        "payloadDigest": None,
        "installedAt": None,
        "files": [],
    }
    try:
        receipt = read_receipt(path, roots)
    except MachineInstallError as error:
        report["state"] = str(MachineState.INVALID)
        report["detail"] = str(error)
        return report
    if receipt is None:
        return report

    report["state"] = str(MachineState.INSTALLED)
    report["packVersion"] = receipt.pack_version
    report["payloadDigest"] = receipt.payload_digest
    report["installedAt"] = receipt.installed_at
    report["files"] = [
        {
            "family": record.family,
            "path": record.path,
            "state": str(_receipt_file_state(roots[record.family], record)),
        }
        for record in sorted(receipt.files, key=lambda item: item.key)
    ]
    if payload_root is not None:
        payload = load_payload(payload_root)
        report["payloadRoot"] = str(payload.root)
        report["payloadVersion"] = payload.pack_version
        report["expectedPayloadDigest"] = payload.digest
        report["comparison"] = (
            "current" if payload.digest == receipt.payload_digest else "skew"
        )
    return report


def _receipt_file_state(root: Path, record: ReceiptFile) -> FileState:
    destination = _resolved_within(root, record.path)
    if destination is None:  # pragma: no cover - parse_receipt already refused these
        return FileState.UNREADABLE
    if destination.is_symlink():
        return FileState.SYMLINK
    if not destination.exists():
        return FileState.MISSING
    if not destination.is_file():
        return FileState.DRIFTED
    identity = _file_identity(destination)
    if identity is None:
        return FileState.UNREADABLE
    digest, executable = identity
    if digest != record.digest:
        return FileState.DRIFTED
    if executable != record.executable:
        return FileState.MODE_DRIFT
    return FileState.CURRENT


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="destination home directory (scratch-prefix installs and tests)",
    )
    parser.add_argument(
        "--state-home",
        type=Path,
        default=None,
        help="private state root holding the receipt and the intent journal",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sd-machine-install",
        description="Install the pack's machine-scope surfaces for non-Claude platforms.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="install or refresh the payload")
    install_parser.add_argument(
        "--payload",
        type=Path,
        default=None,
        help=f"payload root (default: {DEFAULT_PAYLOAD_DIRNAME}/ beside the installer package)",
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite unowned or locally changed files, backing each one up first",
    )
    install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the plan without writing anything",
    )
    _add_common_arguments(install_parser)

    remove_parser = subparsers.add_parser("remove", help="remove receipt-owned files")
    remove_parser.add_argument(
        "--force",
        action="store_true",
        help="remove files that changed since install",
    )
    remove_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be removed without writing anything",
    )
    _add_common_arguments(remove_parser)

    status_parser = subparsers.add_parser("status", help="report receipt state and drift")
    status_parser.add_argument(
        "--payload",
        type=Path,
        default=None,
        help="compare the receipt against this payload root",
    )
    _add_common_arguments(status_parser)
    return parser.parse_args(list(argv))


def _resolve_payload_argument(value: Path | None) -> Path:
    if value is not None:
        return value
    default = default_payload_root()
    if not default.is_dir():
        raise MachineInstallError(
            "no payload root given and none bundled beside the installer package; "
            "pass --payload"
        )
    return default


def _print_install(outcome: InstallOutcome, *, as_json: bool) -> None:
    plan = outcome.plan
    counts: dict[str, int] = {}
    for planned in plan.files:
        counts[str(planned.status)] = counts.get(str(planned.status), 0) + 1
    removals = [removal for removal in plan.removals if removal.removable]
    dropped = [removal for removal in removals if not removal.restores_backup]
    restored = [removal for removal in removals if removal.restores_backup]
    # A row that left the payload but no longer matches its receipt entry stays
    # on disk, and the new receipt is about to forget it, so this line is the
    # only notice the operator ever gets that the file is now theirs to manage.
    kept = [
        removal
        for removal in plan.removals
        if not removal.removable and removal.detail != "already gone"
    ]
    if as_json:
        report = {
            "schemaVersion": STATUS_SCHEMA_VERSION,
            "dryRun": outcome.dry_run,
            "forced": outcome.forced,
            "changed": outcome.changed,
            "packVersion": plan.payload.pack_version,
            "payloadDigest": plan.payload.digest,
            "counts": dict(sorted(counts.items())),
            "removed": [str(removal.destination) for removal in dropped],
            "restored": [str(removal.destination) for removal in restored],
            "kept": [
                {"path": str(removal.destination), "detail": removal.detail}
                for removal in kept
            ],
            "notes": list(plan.notes),
            "advisories": list(outcome.advisories),
        }
        print(json.dumps(report, indent=2))
        return
    for note in (*plan.notes, *outcome.advisories):
        print(f"note: {note}")
    prefix = "would install" if outcome.dry_run else "installed"
    summary = ", ".join(f"{status} {count}" for status, count in sorted(counts.items()))
    print(f"{prefix} {len(plan.files)} files ({summary})")
    for removal in dropped:
        verb = "would remove" if outcome.dry_run else "removed"
        print(f"{verb} {removal.destination}")
    for removal in restored:
        verb = "would restore" if outcome.dry_run else "restored"
        print(f"{verb} {removal.destination} from its recorded backup")
    for removal in kept:
        print(f"kept {removal.destination}: {removal.detail}; no longer tracked")
    if not outcome.dry_run:
        print(f"receipt: pack {plan.payload.pack_version} payload {plan.payload.digest}")


def _print_removal(outcome: RemovalOutcome, *, as_json: bool) -> None:
    if as_json:
        report = {
            "schemaVersion": STATUS_SCHEMA_VERSION,
            "dryRun": outcome.dry_run,
            "hadReceipt": outcome.had_receipt,
            "removed": [str(path) for path in outcome.removed],
            "restored": [str(path) for path in outcome.restored],
            "skipped": [
                {"path": str(path), "detail": detail} for path, detail in outcome.skipped
            ],
        }
        print(json.dumps(report, indent=2))
        return
    if not outcome.had_receipt:
        print("no machine receipt found; nothing to remove")
        return
    verb = "would remove" if outcome.dry_run else "removed"
    print(f"{verb} {len(outcome.removed)} files, restored {len(outcome.restored)} backups")
    for path, detail in outcome.skipped:
        print(f"skipped {path}: {detail}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "install":
            outcome = install(
                _resolve_payload_argument(args.payload),
                home=args.home,
                state_home=args.state_home,
                force=args.force,
                dry_run=args.dry_run,
            )
            _print_install(outcome, as_json=args.json)
        elif args.command == "remove":
            removal = remove(
                home=args.home,
                state_home=args.state_home,
                force=args.force,
                dry_run=args.dry_run,
            )
            _print_removal(removal, as_json=args.json)
        else:
            report = status(
                payload_root=args.payload,
                home=args.home,
                state_home=args.state_home,
            )
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(f"machine install: {report['state']}")
                if report["state"] == str(MachineState.INSTALLED):
                    print(f"  pack version:   {report['packVersion']}")
                    print(f"  payload digest: {report['payloadDigest']}")
                    if "comparison" in report:
                        print(f"  payload:        {report['comparison']}")
                elif report["state"] == str(MachineState.INVALID):
                    print(f"  detail: {report.get('detail')}")
    except MachineInstallError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code
    return EXIT_OK


__all__ = [
    "EXIT_CONFLICT",
    "EXIT_ERROR",
    "EXIT_OK",
    "INTENT_FILE",
    "INTENT_SCHEMA_VERSION",
    "MACHINE_STATE_DIR",
    "RECEIPT_FILE",
    "RECEIPT_SCHEMA_VERSION",
    "BackupRecord",
    "DestinationFamily",
    "FileState",
    "Intent",
    "InstallOutcome",
    "MachineInstallError",
    "MachineState",
    "PartitionGate",
    "Payload",
    "Plan",
    "PlanStatus",
    "PlannedFile",
    "PlannedRemoval",
    "Receipt",
    "ReceiptFile",
    "RemovalOutcome",
    "apply_plan",
    "build_plan",
    "default_payload_root",
    "install",
    "intent_content",
    "load_payload",
    "main",
    "opencode_skill_advisory",
    "parse_intent",
    "parse_receipt",
    "read_intent",
    "read_receipt",
    "receipt_content",
    "receipt_path",
    "remove",
    "resolve_home",
    "state_directory",
    "status",
]
