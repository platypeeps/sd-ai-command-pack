#!/usr/bin/env python3
"""Generate the committed Claude Code plugin from the machine-claude slice.

Dev-side tooling (run via `make generate`); consumers never execute this
script. It reads the committed partition artifact
`docs/fleet/surface-partition.json` (schema version 1), takes every row whose
category is `machine-claude`, joins it back to `manifest.json` by `target` to
find the authored template source, and writes the plugin tree under
`plugins/sd`:

- `.claude/skills/<name>/...`      -> `skills/<name>/...`
- `.claude/commands/sd/<short>.md` -> `commands/<short>.md`
- `scripts/<name>`                 -> `bin/<name>`

Flattening `commands/sd/<short>.md` to `commands/<short>.md` under a plugin
named `sd` preserves the `/sd:<short>` invocation surface, because Claude Code
namespaces plugin commands by plugin name.

`scripts/` rows carry `sharedRuntime: true` in the partition: they ship as
plugin executables *and* stay part of the machine-installer payload for
non-Claude surfaces. That duplication is the contract, not an accident, so the
generator treats those rows as shared rather than exclusive. Library modules
(`sd_ai_command_pack_*.py`) travel with them so own-location sibling resolution
and `sys.path` handling keep working; they are imported, never executed, and so
keep a non-executable mode while every other `bin/` entry gets one.

`.claude/rules/**` is `consumer-config` in the partition and therefore never
reaches the plugin: consumers keep those files wherever the payload lives.

Markdown bodies are rewritten on the way in (the authored templates are
untouched): a `scripts/`-prefixed pack script reference becomes the bare
command name, which resolves through `bin/` on the Bash tool PATH. `node
<name>.mjs` loses its runner prefix, because `node` does not PATH-search a
script operand while `bash` does. Plugin command copies also gain the YAML
frontmatter description authored in `.github/command-sources/<name>.md`; the
Claude adapter drops it because Claude reads the skill, but a plugin command
without a description fails `claude plugin validate --strict`.

Six conditions fail the build closed:

1. a slice row whose target has no `manifest.json` source row;
2. a missing or unreadable template source (including a command's authored
   source or its frontmatter description);
3. a slice row of an unmapped kind or an unexpected target prefix, so a future
   agent/hook row forces a deliberate mapping instead of silent omission;
4. rewrite residue in two scopes: generated Markdown may not contain a
   `scripts/sd[-_]ai[-_]command[-_]pack` path at all, and `bin/` contents may
   only contain the literals in `BIN_LITERAL_ALLOWLIST`, each of which is
   semantic data about some *other* filesystem rather than a path the script
   resolves to reach a sibling;
5. a missing or empty `manifest.json` version;
6. dependency-closure failure: a bare pack command in rewritten Markdown whose
   target is absent from `bin/`, unless the (file, command) pair carries a
   written justification in `CLOSURE_ALLOWLIST`.

The tree is built and validated in full before anything is written, then
materialized in a temporary directory and swapped into place, so files that
left the set are deleted with it. `--check` rebuilds and compares against the
committed tree — content, executable bit, and extraneous files — exiting
nonzero on drift, which is how the unittest keeps the committed output fresh.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

PACK_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_PATH = "manifest.json"
PARTITION_PATH = "docs/fleet/surface-partition.json"
PLUGIN_PATH = "plugins/sd"
COMMAND_SOURCE_DIR = ".github/command-sources"
PLUGIN_MANIFEST_PATH = ".claude-plugin/plugin.json"

MACHINE_CLAUDE = "machine-claude"

PLUGIN_NAME = "sd"
PLUGIN_DESCRIPTION = (
    "Software Delivery command pack: the /sd command surface, its skills, and "
    "the shared pack toolchain as executables."
)
PLUGIN_AUTHOR = {"name": "platypeeps", "url": "https://github.com/platypeeps"}

# Target prefix per manifest kind. A slice row is mapped only when its kind is
# known *and* its target sits under the prefix that kind is allowed to use.
SKILL_PREFIX = ".claude/skills/"
COMMAND_PREFIX = ".claude/commands/sd/"
SCRIPT_PREFIX = "scripts/"
KIND_PREFIXES: dict[str, str] = {
    "skill": SKILL_PREFIX,
    "command": COMMAND_PREFIX,
    "script": SCRIPT_PREFIX,
}

EXECUTABLE_MODE = 0o755
DATA_MODE = 0o644
# Library modules are imported by their siblings, never invoked as commands.
LIBRARY_PREFIX = "sd_ai_command_pack_"

_PACK_SCRIPT_NAME = (
    r"(?:sd-ai-command-pack-[A-Za-z0-9_-]+\.(?:py|sh|mjs)"
    r"|sd_ai_command_pack_[A-Za-z0-9_]+\.py)"
)
# `scripts/<pack script>` in an authored body -> the bare command name.
INVOCATION_RE = re.compile(rf"scripts/({_PACK_SCRIPT_NAME})")
# `node <name>.mjs` -> `<name>.mjs`: bash PATH-searches a slash-free operand,
# node does not, and every bin/ entry carries a shebang plus an executable bit.
NODE_PREFIX_RE = re.compile(r"\bnode (sd-ai-command-pack-[A-Za-z0-9_-]+\.mjs)")
# Anything still naming a repository-root pack path after the rewrite.
RESIDUE_RE = re.compile(r"scripts/sd[-_]ai[-_]command[-_]pack[A-Za-z0-9_.*-]*")
BARE_COMMAND_RE = re.compile(_PACK_SCRIPT_NAME)

# bin/ file name -> (justification, literals that may appear in it).
#
# Every literal is semantic data about some *other* filesystem: a consumer
# repository being audited, a changed-path set being classified, the pack
# source repository's own tree, or a comment consumed by a linter. None of them
# resolves a helper the script then runs — functional sibling resolution is
# forbidden outright by tests/test_script_sibling_resolution.py, whose
# justifications these mirror.
BIN_LITERAL_ALLOWLIST: dict[str, tuple[str, frozenset[str]]] = {
    "sd-ai-command-pack-check.py": (
        "repo-scoped payload discovery: sd-check reports whether the repository "
        "under --repo carries the vendored helpers, so the paths describe that "
        "repository's layout, not this script's siblings",
        frozenset(
            {
                "scripts/sd-ai-command-pack-install-audit.py",
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "scripts/sd-ai-command-pack-review-preflight.mjs",
                "scripts/sd-ai-command-pack-review-scope.sh",
                "scripts/sd-ai-command-pack-update-spec-kb.py",
            }
        ),
    ),
    "sd-ai-command-pack-full-check.sh": (
        "pack-source-only release gate: the fleet candidate checker has no "
        "manifest row and only ever runs inside the pack source repository, "
        "whose own tree is the correct anchor",
        frozenset({"scripts/sd-ai-command-pack-fleet-candidate-check.py"}),
    ),
    "sd-ai-command-pack-housekeeping.sh": (
        "shellcheck source= directive: a static-analysis annotation, not a "
        "runtime path (the runtime load uses $SCRIPT_DIR)",
        frozenset({"scripts/sd-ai-command-pack-shell-lib.sh"}),
    ),
    "sd-ai-command-pack-install-audit.py": (
        "consumer-layout data: the audit describes where a vendored install "
        "puts payload files in the repository it inspects",
        frozenset(
            {
                "scripts/sd-ai-command-pack-",
                "scripts/sd-ai-command-pack-*",
                "scripts/sd-ai-command-pack-fleet-candidate-check.py",
                "scripts/sd-ai-command-pack-fleet-controller.py",
                "scripts/sd-ai-command-pack-fleet-finding-classify.py",
                "scripts/sd-ai-command-pack-fleet-preflight.py",
                "scripts/sd-ai-command-pack-fleet-publish.py",
                "scripts/sd-ai-command-pack-fleet-review-classify.py",
                "scripts/sd-ai-command-pack-fleet-timing.py",
                "scripts/sd-ai-command-pack-fleet-wave-plan.py",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/sd_ai_command_pack_fleet_lib.py",
                "scripts/sd_ai_command_pack_lib.py",
            }
        ),
    ),
    "sd-ai-command-pack-pr-body-scope.py": (
        "consumer-layout data: region globs classify changed paths in the "
        "repository whose PR body is being scoped",
        frozenset(
            {
                "scripts/sd-ai-command-pack-*.mjs",
                "scripts/sd-ai-command-pack-*.py",
                "scripts/sd-ai-command-pack-*.sh",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/sd-ai-command-pack-install-audit.py",
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "scripts/sd-ai-command-pack-review-learnings.py",
                "scripts/sd-ai-command-pack-review-local.sh",
                "scripts/sd-ai-command-pack-review-scope.sh",
                "scripts/sd-ai-command-pack-shell-lib.sh",
                "scripts/sd_ai_command_pack_*.py",
                "scripts/sd_ai_command_pack_lib.py",
            }
        ),
    ),
    "sd-ai-command-pack-review-learnings.py": (
        "changed-path classification: payload prefixes used to recognize pack "
        "files in a diff",
        frozenset({"scripts/sd-ai-command-pack-", "scripts/sd_ai_command_pack_"}),
    ),
    "sd-ai-command-pack-review-preflight.mjs": (
        "changed-path classification: copiedTemplateKind recognizes vendored "
        "payload paths in a diff",
        frozenset(
            {
                "scripts/sd-ai-command-pack-",
                "scripts/sd-ai-command-pack-review-scope.sh",
            }
        ),
    ),
    "sd-ai-command-pack-surface-check.py": (
        "pack-source-only validator: every path names the pack source "
        "repository's own tree, which is always a full checkout",
        frozenset(
            {
                "scripts/sd-ai-command-pack-fleet-candidate-check.py",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-surface-check.py",
            }
        ),
    ),
    "sd-ai-command-pack-toolchain.sh": (
        "repository-state report: doctor tells the operator whether the "
        "repository it inspects carries a vendored full-check",
        frozenset({"scripts/sd-ai-command-pack-full-check.sh"}),
    ),
    "sd-ai-command-pack-update-spec-kb.py": (
        "generated-file provenance: the banner written into generated KB files "
        "names the generator by its canonical repository path",
        frozenset({"scripts/sd-ai-command-pack-update-spec-kb.py"}),
    ),
}

# (plugin-relative Markdown path, bare command) -> justification for a
# reference the plugin cannot satisfy from bin/.
CLOSURE_ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "skills/sd-review-pr/SKILL.md",
        "sd-ai-command-pack-fleet-review-classify.py",
    ): (
        "fleet-operator path: the fleet scripts have no manifest rows, so this "
        "reference is already absent from vendored consumer installs today; a "
        "follow-up task fixes the skill text and retires this entry"
    ),
}


class PluginError(Exception):
    """Fail-closed condition in the plugin build."""


@dataclass(frozen=True)
class PluginFile:
    """One generated plugin file: its bytes and whether it is executable."""

    content: bytes
    executable: bool


def _load_json(path: Path, label: str) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PluginError(f"{label} not found: {path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise PluginError(f"{label} is unreadable: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PluginError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise PluginError(f"{label} is not a JSON object: {path}")
    return loaded


def manifest_sources(root: Path) -> tuple[dict[str, tuple[str, str]], str]:
    """Target -> (template source, kind), plus the manifest version."""

    manifest = _load_json(root / MANIFEST_PATH, "manifest")
    version = str(manifest.get("version", "")).strip()
    if not version:
        raise PluginError(
            f"{MANIFEST_PATH} has no version; the plugin version is stamped from it"
        )
    raw_rows = manifest.get("files")
    if not isinstance(raw_rows, list):
        raise PluginError(f"{MANIFEST_PATH} has no `files` list")
    sources: dict[str, tuple[str, str]] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            raise PluginError(f"{MANIFEST_PATH} `files` holds a non-object entry")
        target = str(row.get("target", ""))
        source = str(row.get("source", ""))
        if target and source:
            sources[target] = (source, str(row.get("kind", "")))
    return sources, version


def machine_claude_slice(root: Path) -> list[dict[str, object]]:
    partition = _load_json(root / PARTITION_PATH, "surface partition")
    raw_rows = partition.get("files")
    if not isinstance(raw_rows, list):
        raise PluginError(f"{PARTITION_PATH} has no `files` list; run `make generate`")
    rows = [
        row
        for row in raw_rows
        if isinstance(row, dict) and row.get("category") == MACHINE_CLAUDE
    ]
    if not rows:
        raise PluginError(
            f"{PARTITION_PATH} holds no {MACHINE_CLAUDE} rows; run `make generate`"
        )
    rows.sort(key=lambda row: str(row.get("target", "")))
    return rows


def plugin_relative_path(target: str, kind: str) -> str:
    """Plugin-relative destination for a slice target, or a hard error."""

    prefix = KIND_PREFIXES.get(kind)
    if prefix is None or not target.startswith(prefix):
        raise PluginError(
            f"unmapped {MACHINE_CLAUDE} row: kind {kind!r} target {target}; "
            "give the kind a plugin destination in KIND_PREFIXES and "
            "plugin_relative_path() in .github/scripts/generate-plugin.py"
        )
    remainder = target[len(prefix) :]
    if kind == "skill":
        return f"skills/{remainder}"
    if kind == "command":
        return f"commands/{remainder}"
    return f"bin/{remainder}"


def read_source(root: Path, source: str, target: str) -> bytes:
    path = root / source
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PluginError(
            f"cannot read template source {source} for {target}: {exc}"
        ) from exc


def command_description(root: Path, short: str) -> str:
    """Authored description for a command, from its neutral command source."""

    source = root / COMMAND_SOURCE_DIR / f"sd-{short}.md"
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise PluginError(f"cannot read command source {source}: {exc}") from exc
    if not text.startswith("---\n"):
        raise PluginError(f"{source}: missing YAML frontmatter")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise PluginError(f"{source}: missing frontmatter terminator")
    description = ""
    for line in text[4:end].splitlines():
        if line.startswith("description: "):
            description = " ".join(line[len("description: ") :].split())
    if not description:
        raise PluginError(f"{source}: missing frontmatter description")
    return description


def rewrite_markdown(text: str) -> str:
    """Repository-root pack invocations become bare `bin/` commands."""

    rewritten = INVOCATION_RE.sub(r"\1", text)
    return NODE_PREFIX_RE.sub(r"\1", rewritten)


def build_files(root: Path) -> dict[str, PluginFile]:
    """Every plugin file, fully validated, keyed by plugin-relative path."""

    sources, version = manifest_sources(root)
    files: dict[str, PluginFile] = {}
    for row in machine_claude_slice(root):
        target = str(row.get("target", ""))
        entry = sources.get(target)
        if entry is None:
            raise PluginError(
                f"{MACHINE_CLAUDE} row has no manifest source row: {target}"
            )
        source, kind = entry
        destination = plugin_relative_path(target, kind)
        raw = read_source(root, source, target)
        if kind == "script":
            name = destination[len("bin/") :]
            files[destination] = PluginFile(
                content=raw,
                executable=not name.startswith(LIBRARY_PREFIX),
            )
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PluginError(f"template source is not UTF-8: {source}: {exc}") from exc
        body = rewrite_markdown(text)
        if kind == "command":
            short = destination[len("commands/") : -len(".md")]
            description = command_description(root, short)
            body = f"---\ndescription: {description}\n---\n\n{body}"
        files[destination] = PluginFile(content=body.encode("utf-8"), executable=False)

    files[PLUGIN_MANIFEST_PATH] = PluginFile(
        content=render_plugin_manifest(version), executable=False
    )
    check_residue(files)
    check_closure(files)
    return dict(sorted(files.items()))


def render_plugin_manifest(version: str) -> bytes:
    manifest = {
        "name": PLUGIN_NAME,
        "version": version,
        "description": PLUGIN_DESCRIPTION,
        "author": PLUGIN_AUTHOR,
    }
    return (json.dumps(manifest, indent=2) + "\n").encode("utf-8")


def check_residue(files: dict[str, PluginFile]) -> None:
    """Markdown may keep no repo-root pack path; bin/ only allowlisted data."""

    for path, entry in sorted(files.items()):
        if path.startswith("bin/"):
            name = path[len("bin/") :]
            justification, allowed = BIN_LITERAL_ALLOWLIST.get(name, ("", frozenset()))
            text = entry.content.decode("utf-8", errors="replace")
            found = {match.rstrip(".") for match in RESIDUE_RE.findall(text)}
            unexpected = sorted(found - allowed)
            if unexpected:
                raise PluginError(
                    f"repository-root pack paths in bin/{name}: "
                    + ", ".join(unexpected)
                    + "; convert functional sibling resolution to own-location "
                    "resolution, or add the literal to BIN_LITERAL_ALLOWLIST "
                    "with a written justification if it is layout data"
                )
            if allowed and not justification:
                raise PluginError(
                    f"BIN_LITERAL_ALLOWLIST entry for {name} has no justification"
                )
            continue
        if not path.endswith(".md"):
            continue
        text = entry.content.decode("utf-8")
        residue = sorted({match.rstrip(".") for match in RESIDUE_RE.findall(text)})
        if residue:
            raise PluginError(
                f"rewrite residue in {path}: "
                + ", ".join(residue)
                + "; the plugin ships no repository-root scripts/ directory, so "
                "extend the rewrite rules in .github/scripts/generate-plugin.py"
            )


def check_closure(files: dict[str, PluginFile]) -> None:
    """Every pack command named in Markdown must ship in bin/."""

    shipped = {path[len("bin/") :] for path in files if path.startswith("bin/")}
    for path, entry in sorted(files.items()):
        if not path.endswith(".md"):
            continue
        text = entry.content.decode("utf-8")
        for command in sorted(set(BARE_COMMAND_RE.findall(text))):
            if command in shipped:
                continue
            justification = CLOSURE_ALLOWLIST.get((path, command))
            if not justification:
                raise PluginError(
                    f"{path} references {command}, which the plugin does not "
                    "ship in bin/; add the script to the manifest, or record "
                    "the reference in CLOSURE_ALLOWLIST with a written "
                    "justification"
                )


def materialize(files: dict[str, PluginFile], destination: Path) -> None:
    for path, entry in sorted(files.items()):
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(entry.content)
        target.chmod(EXECUTABLE_MODE if entry.executable else DATA_MODE)


def committed_files(plugin_root: Path) -> dict[str, PluginFile]:
    found: dict[str, PluginFile] = {}
    if not plugin_root.is_dir():
        return found
    for path in sorted(plugin_root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(plugin_root).as_posix()
        found[relative] = PluginFile(
            content=path.read_bytes(),
            executable=bool(path.stat().st_mode & 0o111),
        )
    return found


def run_check(root: Path, files: dict[str, PluginFile]) -> int:
    plugin_root = root / PLUGIN_PATH
    committed = committed_files(plugin_root)
    if not committed:
        print(
            f"error: {PLUGIN_PATH} is missing; run `make generate`",
            file=sys.stderr,
        )
        return 1
    drift: list[str] = []
    for path in sorted(set(files) | set(committed)):
        expected = files.get(path)
        actual = committed.get(path)
        if expected is None:
            drift.append(f"extraneous: {PLUGIN_PATH}/{path}")
        elif actual is None:
            drift.append(f"missing: {PLUGIN_PATH}/{path}")
        elif expected.content != actual.content:
            drift.append(f"content: {PLUGIN_PATH}/{path}")
        elif expected.executable != actual.executable:
            drift.append(f"mode: {PLUGIN_PATH}/{path}")
    if drift:
        for line in drift:
            print(line, file=sys.stderr)
        print(
            f"error: {PLUGIN_PATH} drifts from the surface partition and "
            "templates; run `make generate`",
            file=sys.stderr,
        )
        return 1
    print(f"check: {PLUGIN_PATH} matches the committed tree ({len(files)} files)")
    return 0


def write_plugin(root: Path, files: dict[str, PluginFile]) -> int:
    plugin_root = root / PLUGIN_PATH
    if committed_files(plugin_root) == files:
        print(f"unchanged: {PLUGIN_PATH} ({len(files)} files)")
        return 0
    plugin_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=".generate-plugin-", dir=str(plugin_root.parent))
    )
    try:
        build = staging / "build"
        build.mkdir()
        materialize(files, build)
        # Wholesale replacement: whatever left the set leaves the tree with it.
        if plugin_root.exists():
            shutil.rmtree(plugin_root)
        os.replace(build, plugin_root)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"wrote: {PLUGIN_PATH} ({len(files)} files)")
    return 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the Claude Code plugin under plugins/sd from the "
            "machine-claude slice of docs/fleet/surface-partition.json."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Rebuild and compare against the committed plugin tree instead of "
            "writing it; exit 1 on drift"
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=PACK_ROOT,
        help="pack root to read and write; defaults to the repository root",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root).resolve()
    try:
        files = build_files(root)
    except PluginError as exc:
        print(f"generate-plugin error: {exc}", file=sys.stderr)
        return 1
    if args.check:
        return run_check(root, files)
    return write_plugin(root, files)


if __name__ == "__main__":
    raise SystemExit(main())
