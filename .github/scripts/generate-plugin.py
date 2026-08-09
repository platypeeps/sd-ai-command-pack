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
script operand while `bash` does. The rewrite rules and both gates live in
`installer/references.py`, shared with the machine payload build, which
relocates the same references to `~/.agents/bin` instead — one judgement about
what is and is not a reference, applied to both payloads. Plugin command copies
also gain the YAML frontmatter description authored in
`.github/command-sources/<name>.md`; the Claude adapter drops it because Claude
reads the skill, but a plugin command without a description fails `claude
plugin validate --strict`.

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
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

PACK_ROOT = Path(__file__).resolve().parents[2]
if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from installer import references  # noqa: E402

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

# Re-exported so a test can patch the allowlist this build applies; the shared
# gates read whichever object is passed in.
BIN_LITERAL_ALLOWLIST = references.BIN_LITERAL_ALLOWLIST
CLOSURE_ALLOWLIST = references.PLUGIN_CLOSURE_ALLOWLIST


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

    return references.rewrite_text(text, profile=references.PLUGIN_PROFILE)


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
    try:
        check_residue(files)
        check_closure(files)
    except references.ReferenceRewriteError as exc:
        # The shared gates report in their own error model; this build has one.
        raise PluginError(str(exc)) from exc
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
            references.check_executable_residue(
                path,
                entry.content.decode("utf-8", errors="replace"),
                allowlist=BIN_LITERAL_ALLOWLIST,
                name=path[len("bin/") :],
            )
            continue
        if not path.endswith(".md"):
            continue
        references.check_text_residue(
            path,
            entry.content.decode("utf-8"),
            profile=references.PLUGIN_PROFILE,
        )


def check_closure(files: dict[str, PluginFile]) -> None:
    """Every pack command named in Markdown must ship in bin/."""

    shipped = frozenset(path[len("bin/") :] for path in files if path.startswith("bin/"))
    for path, entry in sorted(files.items()):
        if not path.endswith(".md"):
            continue
        references.check_closure(
            path,
            entry.content.decode("utf-8"),
            profile=references.PLUGIN_PROFILE,
            shipped_commands=shipped,
            shipped_docs=frozenset(),
            allowlist=CLOSURE_ALLOWLIST,
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
