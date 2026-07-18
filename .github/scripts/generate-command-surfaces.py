#!/usr/bin/env python3
"""Generate the committed command surfaces from the registry command list.

Dev-side tooling (run via `make generate`); consumers never execute this
script. `installer/registry.py` `COMMAND_REGISTRY` is the command-list and
family source of truth. For each command row the generator reads the neutral
body `templates/.commands/<name>.md` and regenerates the committed bespoke
adapters in place:

- `templates/.claude/commands/sd/<short>.md`: the neutral body without its
  YAML frontmatter, with `CLAUDE_COMMAND_ALIAS_REWRITES` applied (Claude
  installs the Trellis wrapper workflows as `trellis:<command>` commands).
- `templates/.gemini/commands/sd/<short>.toml`: TOML with `description`
  from the neutral frontmatter and a `prompt` block holding the body minus
  the SD-preamble line; `GEMINI_SD_HEADING_STRIPPED` commands also drop the
  `SD ` prefix from the top heading (historical byte-stability list).
- `templates/.github/prompts/<name>.prompt.md`: commented YAML frontmatter
  (description + `mode: agent`) plus the full body; the commands in
  `GITHUB_UNTRUSTED_PR_NOTE_COMMANDS` gain the untrusted-PR safety note
  under their step-3 anchor line.

Files listed in `OVERRIDE_BODIES` are intentionally divergent hand-authored
adapters: the generator never rewrites them and reports them as
"override (hand-authored)". The parity tests import these dicts so the
transform data is single-sourced here.

manifest.json regeneration uses a partition-regenerate approach: the current
manifest is read, every entry matching a per-command derived shape (the
shared-skill row, the bespoke claude/gemini/github adapter rows, the neutral
command/workflow/prompt fan-out from `PLATFORM_REGISTRY` target patterns,
and the platform skill fan-out) is dropped, and the remaining static entries
(scripts, configs, docs, charters, managed blocks, ...) are kept in their
original relative order. The manifest is then rewritten as the static
entries followed by the derived entries in canonical order: `COMMAND_REGISTRY`
row order, then the fixed per-command entry order. Regeneration is therefore
idempotent and needs no second source file; header fields are preserved
verbatim.

The generator also renders the `sd-help` command catalog from registry family
metadata, canonical skill frontmatter, source-only policy, and manifest
version. Shared-skill reference declarations are fanned out through the same
derived manifest path as each skill, so installed skill directories stay
self-contained.

`--check` regenerates everything into a temp dir and byte-compares against
the committed files, exiting nonzero and listing drifted paths on any
mismatch. The default mode writes the generated surfaces in place.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Sequence, cast

PACK_ROOT = Path(__file__).resolve().parents[2]
if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from installer.registry import (  # noqa: E402
    COMMAND_FAMILIES,
    COMMAND_NAMES,
    COMMAND_REGISTRY,
    NEUTRAL_COMMAND_SOURCE_PLATFORMS,
    PLATFORM_REGISTRY,
    SHARED_SKILL_REFERENCES,
    SOURCE_ONLY_COMMAND_NAMES,
)

# The neutral-body preamble line that platform-agnostic adapters keep but the
# Gemini prompt block drops (Gemini shows the description separately).
SD_BODY_PREAMBLE = (
    "In this pack, SD means Software Delivery. A skill is a project-installed "
    "Markdown instruction bundle resolved by the agent's trusted "
    "installed-skill resolver."
)

# command short form -> (platform text, neutral text). The Claude adapters
# carry the platform text; the neutral bodies carry the neutral text. The
# parity tests import this dict and rewrite platform -> neutral before
# comparing bodies; this generator rewrites neutral -> platform.
CLAUDE_COMMAND_ALIAS_REWRITES = {
    "continue": (
        "1. Resolve the `trellis-continue` skill by name using the agent's trusted "
        "skill discovery mechanism for installed skills. On Claude Code this "
        "workflow is installed as the `trellis:continue` command; resolving "
        "`trellis:continue` counts as resolving this skill.",
        "1. Resolve the `trellis-continue` skill by name using the agent's trusted "
        "skill discovery mechanism for installed skills.",
    ),
    "finish-work": (
        "1. Resolve the `trellis-finish-work` skill by name using the agent's "
        "trusted skill discovery mechanism for installed skills. On Claude Code "
        "this workflow is installed as the `trellis:finish-work` command; "
        "resolving `trellis:finish-work` counts as resolving this skill.",
        "1. Resolve the `trellis-finish-work` skill by name using the agent's "
        "trusted skill discovery mechanism for installed skills.",
    ),
}

# (platform, command short form) -> reason. Intentionally divergent
# hand-authored bespoke bodies; never regenerated. The parity tests import
# this dict as their body-parity exemption list.
OVERRIDE_BODIES = {
    ("claude", "start"): (
        "Claude Code receives Trellis start context from the SessionStart hook "
        "and intentionally has no trellis-start skill."
    ),
}

# Commands whose committed Gemini adapters drop the `SD ` prefix from the top
# heading. This is a historical byte-stability list, not a convention: the
# parity tests normalize both heading forms, so both variants are valid, and
# this list only pins the committed bytes.
GEMINI_SD_HEADING_STRIPPED = frozenset(
    {
        "continue",
        "start",
        "finish-work",
        "review-pr",
        "review-local",
        "review-learnings",
        "housekeeping",
        "update-spec",
    }
)

GITHUB_UNTRUSTED_PR_NOTE = (
    "   - Before running commands from repo-owned skill instructions in an "
    "untrusted PR or fork context, require maintainer approval or use a sandbox "
    "with no secrets and only required network access."
)
# Commands whose GitHub prompt adapters carry the untrusted-PR note, inserted
# directly under the anchor line below.
GITHUB_UNTRUSTED_PR_NOTE_COMMANDS = frozenset(
    {"start", "continue", "finish-work", "full-check"}
)
GITHUB_UNTRUSTED_PR_NOTE_ANCHOR = (
    "3. Use that skill as the primary instructions for this workflow."
)

GITHUB_PROMPT_HEADER_COMMENT = (
    "# description is shown by GitHub prompt pickers; mode: agent means the "
    "prompt can use tools and run an interactive workflow."
)

# Adapter platforms whose per-command sources are bespoke generated files
# rather than the neutral body.
BESPOKE_ADAPTER_PLATFORMS = ("claude", "gemini", "github")

# Neutral-source platforms added after the original claude/cursor/gemini/
# github/opencode block; the manifest lists them after that block, in
# alphabetical order.
LATER_NEUTRAL_COMMAND_PLATFORMS = tuple(
    platform
    for platform in NEUTRAL_COMMAND_SOURCE_PLATFORMS
    if platform not in ("cursor", "opencode")
)

# Platforms that receive a per-command copy of the shared skill. Not derivable
# from PLATFORM_REGISTRY: these are the platforms whose agents resolve skills
# from their own directory instead of the shared `.agents/` tree.
SKILL_FANOUT_PLATFORMS = (
    "antigravity",
    "codebuddy",
    "devin",
    "droid",
    "kilo",
    "kiro",
    "pi",
    "qoder",
    "reasonix",
    "trae",
)

HELP_CATALOG_PATH = (
    "templates/.agents/skills/sd-help/references/command-catalog.md"
)
GENERATED_REFERENCE_PATHS = frozenset({HELP_CATALOG_PATH})

_COMMAND_SOURCE_PATTERNS = (
    re.compile(r"^templates/\.agents/skills/(sd-[a-z0-9-]+)/SKILL\.md$"),
    re.compile(
        r"^templates/\.agents/skills/(sd-[a-z0-9-]+)/references/[a-z0-9-]+\.md$"
    ),
    re.compile(r"^templates/\.commands/(sd-[a-z0-9-]+)\.md$"),
    re.compile(r"^templates/\.claude/commands/sd/([a-z0-9-]+)\.md$"),
    re.compile(r"^templates/\.gemini/commands/sd/([a-z0-9-]+)\.toml$"),
    re.compile(r"^templates/\.github/prompts/(sd-[a-z0-9-]+)\.prompt\.md$"),
)


class GenerationError(RuntimeError):
    """Raised when a surface cannot be generated safely."""


def manifest_object() -> dict[str, object]:
    manifest_path = PACK_ROOT / "manifest.json"
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationError(f"cannot read {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("files"), list):
        raise GenerationError("manifest.json must be an object with a files array")
    if not all(isinstance(entry, dict) for entry in raw["files"]):
        raise GenerationError("manifest.json files entries must be objects")
    return raw


def _frontmatter_scalar(value: str, source: Path, key: str) -> str:
    value = value.strip()
    if not value:
        raise GenerationError(f"{source}: empty frontmatter {key}")
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise GenerationError(
                f"{source}: invalid quoted frontmatter {key}: {exc}"
            ) from exc
        if not isinstance(decoded, str):
            raise GenerationError(f"{source}: frontmatter {key} must be text")
        return decoded
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise GenerationError(f"{source}: invalid quoted frontmatter {key}")
        return value[1:-1].replace("''", "'")
    return value


def skill_description(name: str) -> str:
    source = PACK_ROOT / f"templates/.agents/skills/{name}/SKILL.md"
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise GenerationError(f"cannot read canonical skill {source}: {exc}") from exc
    if not text.startswith("---\n"):
        raise GenerationError(f"{source}: missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise GenerationError(f"{source}: missing frontmatter terminator")
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key in {"name", "description"}:
            fields[key] = _frontmatter_scalar(value, source, key)
    if fields.get("name") != name:
        raise GenerationError(
            f"{source}: frontmatter name must be {name!r}, got {fields.get('name')!r}"
        )
    description = fields.get("description")
    if not description:
        raise GenerationError(f"{source}: missing frontmatter description")
    return " ".join(description.split())


def _markdown_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


def generate_command_catalog() -> str:
    manifest = manifest_object()
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise GenerationError("manifest.json version must be non-empty text")

    lines = [
        "<!-- Generated by .github/scripts/generate-command-surfaces.py; do not edit. -->",
        "# SD Command Catalog",
        "",
        f"Bundled pack version: `{version}`",
        "",
        "This catalog describes pack-owned commands. Runtime discovery remains",
        "authoritative for whether a command is available in the current session.",
        "",
    ]
    for family in COMMAND_FAMILIES:
        commands = [
            command for command in COMMAND_REGISTRY if command.family == family.id
        ]
        if not commands:
            raise GenerationError(f"command family has no members: {family.id}")
        lines.extend(
            [
                f"## {family.label}",
                "",
                family.summary,
                "",
                "| Command | Bundled availability | Description |",
                "|---|---|---|",
            ]
        )
        for command in commands:
            availability = (
                "source-checkout-only"
                if command.name in SOURCE_ONLY_COMMAND_NAMES
                else "included in installed pack"
            )
            lines.append(
                f"| `{command.name}` | {availability} | "
                f"{_markdown_cell(skill_description(command.name))} |"
            )
        lines.append("")
    return "\n".join(lines)


def neutral_description_and_body(name: str) -> tuple[str, str]:
    source = PACK_ROOT / f"templates/.commands/{name}.md"
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise GenerationError(f"cannot read neutral body {source}: {exc}") from exc
    if not text.startswith("---\n"):
        raise GenerationError(f"{source}: missing YAML frontmatter")
    end = text.find("\n---\n\n", 3)
    if end == -1:
        raise GenerationError(f"{source}: missing frontmatter terminator")
    description = None
    for line in text[4:end].splitlines():
        if line.startswith("description: "):
            description = line[len("description: ") :]
    if not description:
        raise GenerationError(f"{source}: missing frontmatter description")
    if '"' in description:
        raise GenerationError(
            f"{source}: description must not contain double quotes"
        )
    body = text[end + len("\n---\n\n") :]
    if not body.endswith("\n"):
        raise GenerationError(f"{source}: body must end with a newline")
    return description, body


def bespoke_adapter_path(platform: str, name: str, short: str) -> str:
    if platform == "claude":
        return f"templates/.claude/commands/sd/{short}.md"
    if platform == "gemini":
        return f"templates/.gemini/commands/sd/{short}.toml"
    if platform == "github":
        return f"templates/.github/prompts/{name}.prompt.md"
    raise GenerationError(f"unknown bespoke adapter platform: {platform}")


def claude_adapter(name: str, short: str, body: str) -> str:
    rewrite = CLAUDE_COMMAND_ALIAS_REWRITES.get(short)
    if rewrite is None:
        return body
    platform_text, neutral_text = rewrite
    if neutral_text not in body:
        raise GenerationError(
            f"{name}: neutral body lost the Claude alias-rewrite anchor line"
        )
    return body.replace(neutral_text, platform_text)


def gemini_adapter(name: str, short: str, description: str, body: str) -> str:
    lines = body.splitlines()
    if short in GEMINI_SD_HEADING_STRIPPED:
        if not lines or not lines[0].startswith("# SD "):
            raise GenerationError(
                f"{name}: expected a `# SD ` heading to strip for Gemini"
            )
        lines[0] = "# " + lines[0][len("# SD ") :]
    if SD_BODY_PREAMBLE in lines:
        index = lines.index(SD_BODY_PREAMBLE)
        del lines[index]
        if index < len(lines) and lines[index] == "":
            del lines[index]
    prompt = "\n".join(lines)
    if '"""' in prompt:
        raise GenerationError(f"{name}: body must not contain a TOML string fence")
    return f'description = "{description}"\n\nprompt = """\n{prompt}\n"""\n'


def github_prompt(name: str, short: str, description: str, body: str) -> str:
    if short in GITHUB_UNTRUSTED_PR_NOTE_COMMANDS:
        lines = body.splitlines()
        anchors = [
            index
            for index, line in enumerate(lines)
            if line.startswith(GITHUB_UNTRUSTED_PR_NOTE_ANCHOR)
        ]
        if len(anchors) != 1:
            raise GenerationError(
                f"{name}: expected exactly one untrusted-PR note anchor line, "
                f"found {len(anchors)}"
            )
        lines.insert(anchors[0] + 1, GITHUB_UNTRUSTED_PR_NOTE)
        body = "\n".join(lines) + "\n"
    return (
        "---\n"
        f"{GITHUB_PROMPT_HEADER_COMMENT}\n"
        f"description: {description}\n"
        "mode: agent\n"
        "---\n\n"
        f"{body}"
    )


def override_adapter_paths() -> tuple[str, ...]:
    shorts = {short: name for name, short in COMMAND_NAMES}
    paths = []
    for platform, short in sorted(OVERRIDE_BODIES):
        name = shorts.get(short)
        if name is None:
            raise GenerationError(
                f"override ({platform}, {short}) is not a COMMAND_NAMES command"
            )
        paths.append(bespoke_adapter_path(platform, name, short))
    return tuple(paths)


def generate_adapters() -> dict[str, str]:
    outputs: dict[str, str] = {}
    for name, short in COMMAND_NAMES:
        description, body = neutral_description_and_body(name)
        for platform in BESPOKE_ADAPTER_PLATFORMS:
            if (platform, short) in OVERRIDE_BODIES:
                continue
            if platform == "claude":
                content = claude_adapter(name, short, body)
            elif platform == "gemini":
                content = gemini_adapter(name, short, description, body)
            else:
                content = github_prompt(name, short, description, body)
            outputs[bespoke_adapter_path(platform, name, short)] = content
    return outputs


def _neutral_adapter_entry(platform: str, name: str, short: str) -> dict[str, str]:
    info = PLATFORM_REGISTRY[platform]
    if not info.command_kind or not info.command_target_pattern:
        raise GenerationError(f"platform {platform} has no command target pattern")
    return {
        "platform": platform,
        "kind": info.command_kind,
        "source": f"templates/.commands/{name}.md",
        "target": info.command_target_pattern.format(
            filename=f"{name}.md",
            name=short,
        ),
        "anchor": info.directory,
    }


def _platform_skill_entry(platform: str, name: str) -> dict[str, str]:
    directory = PLATFORM_REGISTRY[platform].directory
    return {
        "platform": platform,
        "kind": "skill",
        "source": f"templates/.agents/skills/{name}/SKILL.md",
        "target": f"{directory}/skills/{name}/SKILL.md",
        "anchor": directory,
    }


def _skill_reference_entries(name: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for reference in SHARED_SKILL_REFERENCES.get(name, ()):
        source = f"templates/.agents/skills/{name}/{reference}"
        if source not in GENERATED_REFERENCE_PATHS and not (PACK_ROOT / source).is_file():
            raise GenerationError(f"missing shared skill reference: {source}")
        entries.append(
            {
                "platform": "shared",
                "kind": "skill",
                "source": source,
                "target": f".agents/skills/{name}/{reference}",
                "install": "always",
            }
        )
        entries.extend(
            {
                "platform": platform,
                "kind": "skill",
                "source": source,
                "target": (
                    f"{PLATFORM_REGISTRY[platform].directory}/skills/"
                    f"{name}/{reference}"
                ),
                "anchor": PLATFORM_REGISTRY[platform].directory,
            }
            for platform in SKILL_FANOUT_PLATFORMS
        )
    return entries


def derived_manifest_entries(name: str, short: str) -> list[dict[str, str]]:
    entries = [
        {
            "platform": "shared",
            "kind": "skill",
            "source": f"templates/.agents/skills/{name}/SKILL.md",
            "target": f".agents/skills/{name}/SKILL.md",
            "install": "always",
        },
        {
            "platform": "claude",
            "kind": "command",
            "source": bespoke_adapter_path("claude", name, short),
            "target": f".claude/commands/sd/{short}.md",
            "anchor": PLATFORM_REGISTRY["claude"].directory,
        },
        _neutral_adapter_entry("cursor", name, short),
        {
            "platform": "gemini",
            "kind": "command",
            "source": bespoke_adapter_path("gemini", name, short),
            "target": f".gemini/commands/sd/{short}.toml",
            "anchor": PLATFORM_REGISTRY["gemini"].directory,
        },
        {
            "platform": "github",
            "kind": "prompt",
            "source": bespoke_adapter_path("github", name, short),
            "target": f".github/prompts/{name}.prompt.md",
            "anchor": PLATFORM_REGISTRY["github"].directory,
        },
        _neutral_adapter_entry("opencode", name, short),
    ]
    entries.extend(
        _neutral_adapter_entry(platform, name, short)
        for platform in LATER_NEUTRAL_COMMAND_PLATFORMS
    )
    entries.extend(
        _platform_skill_entry(platform, name) for platform in SKILL_FANOUT_PLATFORMS
    )
    entries.extend(_skill_reference_entries(name))
    return entries


def _candidate_command_pairs(entry: dict[str, object]) -> set[tuple[str, str]]:
    source = entry.get("source")
    if not isinstance(source, str):
        return set()
    shorts = {short: name for name, short in COMMAND_NAMES}
    candidates: set[tuple[str, str]] = set()
    for pattern in _COMMAND_SOURCE_PATTERNS:
        match = pattern.match(source)
        if not match:
            continue
        token = match.group(1)
        if token.startswith("sd-"):
            candidates.add((token, token[len("sd-") :]))
        else:
            candidates.add((f"sd-{token}", token))
            if token in shorts:
                candidates.add((shorts[token], token))
    return candidates


def _is_command_shaped(entry: dict[str, object]) -> bool:
    for name, short in _candidate_command_pairs(entry):
        if entry in derived_manifest_entries(name, short):
            return True
    return False


def generate_manifest_text() -> str:
    raw = manifest_object()
    raw_files = cast(list[dict[str, object]], raw["files"])
    static = [entry for entry in raw_files if not _is_command_shaped(entry)]
    derived = [
        entry
        for name, short in COMMAND_NAMES
        if name not in SOURCE_ONLY_COMMAND_NAMES
        for entry in derived_manifest_entries(name, short)
    ]
    files = static + derived
    seen: dict[str, str] = {}
    for entry in files:
        target = str(entry.get("target", ""))
        folded = target.casefold()
        if folded in seen:
            raise GenerationError(
                f"duplicate manifest target: {target} collides with {seen[folded]}"
            )
        seen[folded] = target
    output = {key: value for key, value in raw.items() if key != "files"}
    output["files"] = files
    return json.dumps(output, indent=2) + "\n"


def generate_surfaces() -> dict[str, str]:
    outputs = generate_adapters()
    outputs[HELP_CATALOG_PATH] = generate_command_catalog()
    outputs["manifest.json"] = generate_manifest_text()
    return outputs


def print_overrides() -> None:
    for path in override_adapter_paths():
        print(f"override (hand-authored): {path}")


def run_check(outputs: dict[str, str]) -> int:
    drifted = []
    with tempfile.TemporaryDirectory(prefix="sd-command-surfaces-") as temp_name:
        temp_root = Path(temp_name)
        for relative, content in outputs.items():
            generated = temp_root / relative
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_text(content, encoding="utf-8")
            committed = PACK_ROOT / relative
            if not committed.is_file() or (
                committed.read_bytes() != generated.read_bytes()
            ):
                drifted.append(relative)
    if drifted:
        for relative in sorted(drifted):
            print(f"drift: {relative}")
        print(
            f"error: {len(drifted)} of {len(outputs)} generated surfaces drift "
            "from the committed tree; run `make generate`",
            file=sys.stderr,
        )
        return 1
    print(f"check: {len(outputs)} generated surfaces match the committed tree")
    return 0


def write_surfaces(outputs: dict[str, str]) -> int:
    written = 0
    for relative, content in sorted(outputs.items()):
        destination = PACK_ROOT / relative
        if destination.is_file() and destination.read_text(
            encoding="utf-8"
        ) == content:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        print(f"wrote: {relative}")
        written += 1
    print(
        f"surfaces: {len(outputs)} generated, {written} written, "
        f"{len(outputs) - written} unchanged"
    )
    return 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate command adapters, the help catalog, and manifest.json "
            "from installer/registry.py COMMAND_REGISTRY."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Regenerate to a temp dir and byte-compare against the committed "
            "files instead of writing in place; exit 1 on drift"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        outputs = generate_surfaces()
        print_overrides()
        if args.check:
            return run_check(outputs)
        return write_surfaces(outputs)
    except GenerationError as exc:
        print(f"generate-command-surfaces error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
