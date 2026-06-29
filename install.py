#!/usr/bin/env python3
"""Install the SD AI command pack into a Trellis repo."""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Union


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
PLATFORMS = ("claude", "cursor", "gemini", "github", "opencode", "shared")
ALWAYS_INSTALL = "always"
ACTIVE_TRELLIS_PLATFORM_MARKERS = {
    "claude": (
        Path(".claude/commands/trellis/continue.md"),
        Path(".claude/hooks/session-start.py"),
        Path(".claude/skills/trellis-before-dev/SKILL.md"),
    ),
    "cursor": (
        Path(".cursor/commands/trellis-continue.md"),
        Path(".cursor/hooks.json"),
        Path(".cursor/skills/trellis-before-dev/SKILL.md"),
    ),
    "gemini": (
        Path(".gemini/commands/trellis/continue.toml"),
        Path(".gemini/hooks/session-start.py"),
        Path(".gemini/agents/trellis-check.md"),
    ),
    "github": (
        Path(".github/hooks/trellis.json"),
        Path(".github/copilot/hooks.json"),
        Path(".github/skills/trellis-before-dev/SKILL.md"),
    ),
    "opencode": (
        Path(".opencode/commands/trellis/continue.md"),
        Path(".opencode/lib/trellis-context.js"),
        Path(".opencode/skills/trellis-before-dev/SKILL.md"),
    ),
}
LEGACY_PACK_COMMANDS = frozenset(
    {"full-check", "housekeeping", "review-pr"}
)
TRELLIS_INSTALL_DOCS_URL = "https://docs.trytrellis.app/start/install-and-first-task"
FORCE_PRESERVED_TARGETS = frozenset({Path(".prism/rules.json")})
INSTALLED_TARGETS_FILE = Path(".sd-ai-command-pack/installed-targets.txt")
OBSOLETE_SHARED_SKILL_TARGETS = {
    Path(".agents/skills/sd-review-pr/SKILL.md"): Path(
        ".agents/skills/trellis-review-pr/SKILL.md"
    ),
    Path(".agents/skills/sd-full-check/SKILL.md"): Path(
        ".agents/skills/trellis-full-check/SKILL.md"
    ),
    Path(".agents/skills/sd-housekeeping/SKILL.md"): Path(
        ".agents/skills/trellis-housekeeping/SKILL.md"
    ),
}
OBSOLETE_SHARED_SCRIPT_TARGETS = {
    Path("scripts/sd-ai-command-pack-full-check.sh"): (
        Path("scripts/trellis-full-check.sh"),
        Path("scripts/sd-command-pack-full-check.sh"),
    ),
    Path("scripts/sd-ai-command-pack-housekeeping.sh"): (
        Path("scripts/trellis-housekeeping.sh"),
        Path("scripts/sd-command-pack-housekeeping.sh"),
    ),
}
OBSOLETE_RENAMED_TARGETS = {
    Path("scripts/sd-ai-command-pack-review-learnings.py"): (
        Path("scripts/sd-review-learnings.py"),
    ),
    Path(".agents/skills/sd-update-spec/SKILL.md"): (
        Path(".agents/skills/sd-refresh-specs/SKILL.md"),
    ),
    Path("scripts/sd-ai-command-pack-review-scope.sh"): (
        Path("scripts/sd-command-pack-review-scope.sh"),
    ),
    Path("scripts/sd-ai-command-pack-pr-body-scope.py"): (
        Path("scripts/sd-command-pack-pr-body-scope.py"),
    ),
    Path("scripts/sd-ai-command-pack-update-spec-kb.py"): (
        Path("scripts/sd-ai-command-pack-refresh-specs-kb.py"),
        Path("scripts/sd-command-pack-update-spec-kb.py"),
        Path("scripts/sd-command-pack-refresh-specs-kb.py"),
    ),
    Path(".claude/commands/sd/update-spec.md"): (
        Path(".claude/commands/sd/refresh-specs.md"),
    ),
    Path(".cursor/commands/sd-update-spec.md"): (
        Path(".cursor/commands/sd-refresh-specs.md"),
    ),
    Path(".gemini/commands/sd/update-spec.toml"): (
        Path(".gemini/commands/sd/refresh-specs.toml"),
    ),
    Path(".github/prompts/sd-update-spec.prompt.md"): (
        Path(".github/prompts/sd-refresh-specs.prompt.md"),
    ),
    Path(".opencode/commands/sd-update-spec.md"): (
        Path(".opencode/commands/sd-refresh-specs.md"),
    ),
}
OBSOLETE_RENAMED_TARGET_VALUES = frozenset(
    target for targets in OBSOLETE_RENAMED_TARGETS.values() for target in targets
)
MANAGED_BLOCK_KIND = "managed-block"
COPILOT_INSTRUCTIONS_TARGET = Path(".github/copilot-instructions.md")
COPILOT_GUIDANCE_START = "<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START -->"
COPILOT_GUIDANCE_END = "<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:END -->"


@dataclass(frozen=True)
class PackFile:
    platform: str
    kind: str
    source: Path
    target: Path
    anchor: Path | None
    install: str


@dataclass(frozen=True)
class InstallResult:
    file: PackFile
    status: str
    backup: Path | None = None


@dataclass(frozen=True)
class LegacyCleanupResult:
    target: Path
    status: str
    reason: str | None = None
    backup: Path | None = None


def load_manifest() -> tuple[dict, list[PackFile]]:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    files: list[PackFile] = []
    for item in raw.get("files", []):
        files.append(
            PackFile(
                platform=str(item["platform"]),
                kind=str(item["kind"]),
                source=ROOT / str(item["source"]),
                target=Path(str(item["target"])),
                anchor=Path(str(item["anchor"])) if item.get("anchor") else None,
                install=str(item.get("install", "if-anchor-exists")),
            )
        )
    return raw, files


def validate_manifest(files: list[PackFile]) -> None:
    seen_targets: set[Path] = set()
    for file in files:
        if file.platform not in PLATFORMS:
            raise SystemExit(f"error: unknown platform {file.platform!r} in manifest")
        validate_pack_source(file.source)
        validate_relative_manifest_path("target", file.target)
        if file.anchor is not None:
            validate_relative_manifest_path("anchor", file.anchor)
        if file.target in seen_targets:
            raise SystemExit(f"error: duplicate target in manifest: {file.target}")
        seen_targets.add(file.target)
        if not file.source.is_file():
            raise SystemExit(f"error: missing pack template {file.source}")


def validate_relative_manifest_path(field: str, path: Path) -> None:
    windows_path = PureWindowsPath(str(path))
    if (
        path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
        or ".." in path.parts
        or ".." in windows_path.parts
    ):
        raise SystemExit(f"error: unsafe {field} path in manifest: {path}")


def validate_pack_source(source: Path) -> None:
    try:
        relative_source = source.relative_to(ROOT)
    except ValueError:
        raise SystemExit(f"error: unsafe source path in manifest: {source}") from None
    validate_relative_manifest_path("source", relative_source)
    try:
        source.resolve(strict=False).relative_to(ROOT.resolve())
    except (OSError, RuntimeError) as error:
        raise SystemExit(
            f"error: cannot resolve source path in manifest: {source} ({error})"
        ) from None
    except ValueError:
        raise SystemExit(f"error: unsafe source path in manifest: {source}") from None


def validate_resolved_target_path(target: Path, path: Path, label: str) -> None:
    try:
        target_root = target.resolve()
        resolved_path = path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise SystemExit(f"error: cannot resolve {label}: {path} ({error})") from None

    try:
        resolved_path.relative_to(target_root)
    except ValueError:
        raise SystemExit(
            f"error: {label} resolves outside target repo: {path}"
        ) from None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install SD AI command pack shared assets and command adapters."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Target Trellis repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--platform",
        action="append",
        choices=PLATFORMS,
        help=(
            "Install only this platform adapter, even if no active Trellis "
            "marker is detected. Repeat to select several. "
            "Shared skills, scripts, Prism rules, and docs are always installed."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Install all adapters even if platform directories or active Trellis "
            "markers are not present."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite existing files that differ from the pack templates "
            "(except .prism/rules.json) and delete conflicting legacy/obsolete "
            "adapter files. Add --backup to save .bak copies before deleting."
        ),
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help=(
            "With --force, save a .bak copy next to each overwritten or "
            "deleted file before changing it."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files.",
    )
    parser.add_argument(
        "--skip-diff-check",
        action="store_true",
        help="Skip the final git diff --check validation.",
    )
    return parser.parse_args(argv)


def require_trellis_repo(target: Path) -> None:
    if not (target / ".trellis" / "config.yaml").is_file():
        raise SystemExit(
            f"error: {target} does not look like a Trellis repo "
            "(.trellis/config.yaml not found). Install Trellis and run "
            f"`trellis init` first: {TRELLIS_INSTALL_DOCS_URL}"
        )


def has_active_trellis_platform(target: Path, platform: str) -> bool:
    markers = ACTIVE_TRELLIS_PLATFORM_MARKERS.get(platform, ())
    return any((target / marker).is_file() for marker in markers)


def selected_files(
    files: list[PackFile],
    target: Path,
    platforms: list[str] | None,
    install_all: bool,
) -> tuple[list[PackFile], list[tuple[PackFile, str]]]:
    selected: list[PackFile] = []
    skipped: list[tuple[PackFile, str]] = []
    platform_filter = set(platforms or [])

    for file in files:
        if file.install == ALWAYS_INSTALL:
            selected.append(file)
            continue
        if platform_filter and file.platform not in platform_filter:
            skipped.append((file, "platform not selected"))
            continue
        if install_all or platform_filter:
            selected.append(file)
            continue
        if file.anchor and not (target / file.anchor).exists():
            skipped.append((file, f"anchor {file.anchor} not present"))
            continue
        if not has_active_trellis_platform(target, file.platform):
            skipped.append(
                (
                    file,
                    f"active Trellis {file.platform} install not detected",
                )
            )
            continue
        selected.append(file)

    return selected, skipped


def path_is_occupied(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def next_backup_path(target: Path, destination: Path) -> Path:
    candidate = destination.with_name(f"{destination.name}.bak")
    if not path_is_occupied(candidate):
        validate_resolved_target_path(target, candidate, "backup path")
        return candidate

    index = 1
    while True:
        candidate = destination.with_name(f"{destination.name}.bak{index}")
        if not path_is_occupied(candidate):
            validate_resolved_target_path(target, candidate, "backup path")
            return candidate
        index += 1


def install_file(
    file: PackFile,
    target: Path,
    *,
    force: bool,
    dry_run: bool,
    backup: bool,
) -> InstallResult:
    source = file.source
    destination = target / file.target
    validate_resolved_target_path(target, destination, "target path")
    if path_is_occupied(destination) and not destination.is_file():
        raise SystemExit(f"error: target exists and is not a file: {file.target}")
    new_content = source.read_bytes()
    if destination.exists():
        current = destination.read_bytes()
        if current == new_content:
            return InstallResult(file, "unchanged")
        if file.target in FORCE_PRESERVED_TARGETS:
            return InstallResult(file, "preserved")
        if current in legacy_adapter_contents(file):
            if not dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            return InstallResult(file, "updated")
        if not force:
            return InstallResult(file, "conflict")
        backup_path = (
            next_backup_path(target, destination) if backup and not dry_run else None
        )
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if backup_path:
                shutil.copyfile(destination, backup_path)
            shutil.copyfile(source, destination)
        return InstallResult(file, "overwritten", backup_path)

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return InstallResult(file, "created")


def normalize_managed_block_template(file: PackFile) -> str:
    block = file.source.read_text(encoding="utf-8").strip("\n") + "\n"
    if COPILOT_GUIDANCE_START not in block or COPILOT_GUIDANCE_END not in block:
        raise SystemExit(
            f"error: managed block template missing markers: {file.source}"
        )
    return block


def merge_managed_block(current: str, block: str) -> str:
    start_index = current.find(COPILOT_GUIDANCE_START)
    end_index = current.find(COPILOT_GUIDANCE_END)
    has_start = start_index != -1
    has_end = end_index != -1
    if has_start != has_end or (has_start and end_index < start_index):
        raise SystemExit(
            "error: .github/copilot-instructions.md has incomplete "
            "sd-ai-command-pack managed block markers"
        )
    if has_start:
        replace_end = end_index + len(COPILOT_GUIDANCE_END)
        if replace_end < len(current) and current[replace_end] == "\n":
            replace_end += 1
        return current[:start_index] + block + current[replace_end:]

    if not current.strip():
        return block
    if not current.endswith("\n"):
        return current + "\n\n" + block
    if not current.endswith("\n\n"):
        return current + "\n" + block
    return current + block


def install_managed_block(
    file: PackFile,
    target: Path,
    *,
    dry_run: bool,
) -> InstallResult:
    if file.target != COPILOT_INSTRUCTIONS_TARGET:
        raise SystemExit(f"error: unsupported managed block target: {file.target}")

    destination = target / file.target
    validate_resolved_target_path(target, destination, "target path")
    if path_is_occupied(destination) and not destination.is_file():
        raise SystemExit(f"error: target exists and is not a file: {file.target}")

    block = normalize_managed_block_template(file)
    if destination.exists():
        current = destination.read_text(encoding="utf-8")
        merged = merge_managed_block(current, block)
        if merged == current:
            return InstallResult(file, "unchanged")
        if not dry_run:
            destination.write_text(merged, encoding="utf-8")
        return InstallResult(file, "updated")

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(block, encoding="utf-8")
    return InstallResult(file, "created")


def installed_targets_content(selected: list[PackFile]) -> str:
    targets = {file.target.as_posix() for file in selected}
    targets.add(INSTALLED_TARGETS_FILE.as_posix())
    targets = sorted(targets)
    return "\n".join(targets) + "\n"


def install_installed_targets_file(
    selected: list[PackFile],
    target: Path,
    *,
    dry_run: bool,
) -> InstallResult:
    file = PackFile(
        platform="shared",
        kind="generated-manifest",
        source=MANIFEST_PATH,
        target=INSTALLED_TARGETS_FILE,
        anchor=None,
        install=ALWAYS_INSTALL,
    )
    destination = target / file.target
    validate_resolved_target_path(target, destination, "target path")

    content = installed_targets_content(selected)
    if destination.exists():
        current = destination.read_text(encoding="utf-8")
        if current == content:
            return InstallResult(file, "unchanged")
        if not dry_run:
            destination.write_text(content, encoding="utf-8")
        return InstallResult(file, "updated")

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return InstallResult(file, "created")


def legacy_adapter_target(file: PackFile) -> Path | None:
    command_name = file.target.stem.removeprefix("sd-").removesuffix(".prompt")
    if command_name not in LEGACY_PACK_COMMANDS:
        return None

    target = file.target.as_posix()
    if file.kind == "command" and "/commands/sd/" in target:
        return Path(target.replace("/commands/sd/", "/commands/trellis/"))
    if (
        file.platform in {"cursor", "opencode"}
        and file.kind == "command"
        and file.target.parent == Path(f".{file.platform}/commands")
        and file.target.name.startswith("sd-")
    ):
        if file.platform == "cursor":
            return Path(".cursor/commands") / f"trellis-{command_name}.md"
        return Path(".opencode/commands/trellis") / f"{command_name}.md"
    if (
        file.platform == "github"
        and file.kind == "prompt"
        and file.target.name.startswith("sd-")
    ):
        return file.target.with_name(file.target.name.removeprefix("sd-"))
    return None


CleanupTargets = Union[Path, Iterable[Path], None]


def obsolete_adapter_target(file: PackFile) -> CleanupTargets:
    targets: list[Path] = []
    if file.target in OBSOLETE_RENAMED_TARGETS:
        targets.extend(OBSOLETE_RENAMED_TARGETS[file.target])
    if file.platform == "shared" and file.kind == "skill":
        if file.target in OBSOLETE_SHARED_SKILL_TARGETS:
            targets.append(OBSOLETE_SHARED_SKILL_TARGETS[file.target])
    if file.platform == "shared" and file.kind == "script":
        if file.target in OBSOLETE_SHARED_SCRIPT_TARGETS:
            targets.extend(OBSOLETE_SHARED_SCRIPT_TARGETS[file.target])
    if file.platform == "shared" and file.kind == "doc":
        if file.target == Path("docs/SD_AI_COMMAND_PACK.md"):
            targets.append(Path("docs/TRELLIS_REVIEW_PR_PACK.md"))
    if (
        file.platform == "opencode"
        and file.kind == "command"
        and file.target.parent == Path(".opencode/commands")
        and file.target.name.startswith("sd-")
        and file.target.suffix == ".md"
    ):
        command_name = file.target.stem.removeprefix("sd-")
        targets.append(Path(".opencode/commands/sd") / f"{command_name}.md")
    return tuple(targets) if targets else None


def strip_yaml_frontmatter(content: bytes) -> bytes:
    if not content.startswith(b"---\n"):
        return content
    end = content.find(b"\n---\n", len(b"---\n"))
    if end == -1:
        return content
    stripped = content[end + len(b"\n---\n") :]
    if stripped.startswith(b"\n"):
        return stripped[1:]
    return stripped


def toml_description_variant(
    content: bytes,
    command_name: str,
    namespace: str,
) -> bytes:
    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(b"description = "):
            lines[index] = f'description = "{namespace}: {command_name}"\n'.encode(
                "utf-8"
            )
            return b"".join(lines)
    return content


def old_pack_identity_variant(content: bytes) -> bytes:
    replacements = (
        (b"sd-ai-command-pack", b"trellis-review-pr-pack"),
        (b"SD AI Command Pack", b"Trellis Review PR Pack"),
        (b"SD AI command pack", b"Trellis review PR pack"),
        (b"SD AI command setup", b"Trellis review-cycle setup"),
        (b"SD_AI_COMMAND_PACK", b"TRELLIS_REVIEW_PR_PACK"),
    )
    for new, old in replacements:
        content = content.replace(new, old)
    return content


def old_pack_owned_entity_variant(content: bytes) -> bytes:
    replacements = (
        (b"scripts/sd-ai-command-pack-", b"scripts/sd-command-pack-"),
        (b"sd-ai-command-pack-ci-paths", b"sd-command-pack-ci-paths"),
        (b"SD_AI_COMMAND_PACK_", b"SD_COMMAND_PACK_"),
        (b"SD AI command pack", b"SD command-pack"),
        (b"SD AI command pack", b"SD command pack"),
        (b"sd_ai_command_pack", b"sd_command_pack"),
    )
    for new, old in replacements:
        content = content.replace(new, old)
    return content


def old_trellis_pack_owned_entity_variant(content: bytes) -> bytes:
    replacements = (
        (b"sd-command-pack-full-check.sh", b"trellis-full-check.sh"),
        (b"sd-command-pack-housekeeping.sh", b"trellis-housekeeping.sh"),
        (b"SD_COMMAND_PACK_FULL_CHECK_", b"TRELLIS_FULL_CHECK_"),
        (b"SD_COMMAND_PACK_HOUSEKEEPING_", b"TRELLIS_HOUSEKEEPING_"),
        (b"SD command-pack full check", b"Trellis full check"),
        (b"SD command-pack housekeeping", b"Trellis housekeeping"),
    )
    for new, old in replacements:
        content = content.replace(new, old)
    return content


def old_review_skill_name_variant(content: bytes) -> bytes:
    replacements = (
        (b"name: sd-review-pr", b"name: trellis-review-pr"),
        (b"# SD PR Review Loop", b"# Trellis PR Review Loop"),
        (
            b"Use this project-local skill for `sd-review-pr` and "
            b"`/sd:review-pr` style work.",
            b"Use this project-local skill for `/trellis:review-pr` style work.",
        ),
        (b"SD PR review loop", b"Trellis PR review loop"),
    )
    for new, old in replacements:
        content = content.replace(new, old)
    content = content.replace(
        b"Use this project-local skill for `/trellis:review-pr` style work.\n"
        b"It turns a draft or in-progress PR into a reviewed PR by running the local\n"
        b"full-check and Prism review first, inspecting existing comments and CI, and\n"
        b"requesting GitHub Copilot review only when the user explicitly asks for a\n"
        b"remote/final pass or when local review is clean and a remote review is\n"
        b"intentionally warranted.",
        b"Use this project-local skill for `/trellis:review-pr` style work. It turns a\n"
        b"draft or in-progress PR into a reviewed PR by running the local full-check and\n"
        b"Prism review first, inspecting existing comments and CI, and requesting GitHub\n"
        b"Copilot review only when the user explicitly asks for a remote/final pass or\n"
        b"when local review is clean and a remote review is intentionally warranted.",
    )
    return content


def old_full_check_skill_name_variant(content: bytes) -> bytes:
    replacements = (
        (b"name: sd-full-check", b"name: trellis-full-check"),
        (b"# SD Full Check", b"# Trellis Full Check"),
        (
            b"Run this project-local skill for `sd-full-check` and "
            b"`/sd:full-check` style\nwork. It is an optional but strongly "
            b"recommended PR-readiness gate, not an\nevery-edit requirement.",
            b"Run this project-local skill for `/trellis:full-check` style work. "
            b"It is an\noptional but strongly recommended PR-readiness gate, "
            b"not an every-edit\nrequirement.",
        ),
    )
    for new, old in replacements:
        content = content.replace(new, old)
    return content


def old_housekeeping_skill_name_variant(content: bytes) -> bytes:
    replacements = (
        (b"name: sd-housekeeping", b"name: trellis-housekeeping"),
        (b"# SD Housekeeping", b"# Trellis Housekeeping"),
        (
            b"Run this project-local skill for `sd-housekeeping` and "
            b"`/sd:housekeeping` style\nwork when the user wants a ready PR "
            b"wrapped up and merged, or after a PR has\nmerged and the repo "
            b"should return to a clean default-branch state.",
            b"Run this project-local skill for `/trellis:housekeeping` style "
            b"work when the\nuser wants a ready PR wrapped up and merged, or "
            b"after a PR has merged and the\nrepo should return to a clean "
            b"default-branch state.",
        ),
    )
    for new, old in replacements:
        content = content.replace(new, old)
    return content


def old_shared_skill_name_variant(file: PackFile, content: bytes) -> bytes:
    if file.target == Path(".agents/skills/sd-review-pr/SKILL.md"):
        return old_review_skill_name_variant(content)
    if file.target == Path(".agents/skills/sd-full-check/SKILL.md"):
        return old_full_check_skill_name_variant(content)
    if file.target == Path(".agents/skills/sd-housekeeping/SKILL.md"):
        return old_housekeeping_skill_name_variant(content)
    return content


def old_refresh_specs_generated_content_matches(content: bytes) -> bool:
    has_old_identity = any(
        phrase in content
        for phrase in (
            b"sd-refresh-specs",
            b"refresh-specs",
            b"Refresh Specs",
            b"Refresh Trellis specs",
        )
    )
    has_trellis_foundation = b"trellis-update-spec/SKILL.md" in content
    has_pack_extensions = (
        b"repospec artifact" in content
        and (
            b"architectural overview" in content
            or b"ARCHITECTURE.md" in content
        )
        and (
            b"sd-ai-command-pack-refresh-specs-kb.py" in content
            or b"sd-command-pack-refresh-specs-kb.py" in content
            or b".obsidian-kb" in content
        )
    )
    return has_old_identity and has_trellis_foundation and has_pack_extensions


def legacy_adapter_contents(file: PackFile) -> set[bytes]:
    content = file.source.read_bytes()
    contents = {content}
    contents.add(strip_yaml_frontmatter(content))
    contents.add(old_pack_identity_variant(content))
    contents.add(old_pack_identity_variant(strip_yaml_frontmatter(content)))
    if file.target in OBSOLETE_SHARED_SKILL_TARGETS:
        contents.add(old_shared_skill_name_variant(file, content))
    if file.platform == "gemini" and file.kind == "command":
        command_name = file.target.stem.removeprefix("sd-").removesuffix(".prompt")
        contents.add(toml_description_variant(content, command_name, "SD"))
        contents.add(toml_description_variant(content, command_name, "Trellis"))
    contents.update(
        item.replace(b'description = "SD: ', b'description = "Trellis: ')
        for item in list(contents)
    )
    contents.update(old_pack_owned_entity_variant(item) for item in list(contents))
    contents.update(
        old_trellis_pack_owned_entity_variant(item) for item in list(contents)
    )
    return contents


def cleanup_content_matches_template(
    file: PackFile,
    cleanup_target: Path,
    content: bytes,
) -> bool:
    if content in legacy_adapter_contents(file):
        return True
    if (
        cleanup_target in OBSOLETE_RENAMED_TARGET_VALUES
        and old_refresh_specs_generated_content_matches(content)
    ):
        return True
    return False


def normalize_cleanup_targets(cleanup_targets: CleanupTargets) -> tuple[Path, ...]:
    if cleanup_targets is None:
        return ()
    if isinstance(cleanup_targets, Path):
        return (cleanup_targets,)
    return tuple(cleanup_targets)


def cleanup_adapter_targets(
    selected: list[PackFile],
    target: Path,
    *,
    dry_run: bool,
    force: bool,
    backup: bool,
    target_for_file: Callable[[PackFile], CleanupTargets],
    conflict_status: str,
) -> list[LegacyCleanupResult]:
    results: list[LegacyCleanupResult] = []
    seen: set[Path] = set()
    for file in selected:
        for cleanup_target in normalize_cleanup_targets(target_for_file(file)):
            if cleanup_target in seen:
                continue
            seen.add(cleanup_target)

            destination = target / cleanup_target
            validate_resolved_target_path(
                target,
                destination.parent,
                "adapter cleanup parent path",
            )
            if not path_is_occupied(destination):
                continue
            if path_is_occupied(destination) and not (
                destination.is_file() or destination.is_symlink()
            ):
                results.append(
                    LegacyCleanupResult(
                        cleanup_target,
                        conflict_status,
                        "target exists and is not a file",
                    )
                )
                continue
            content_matches_template = (
                not destination.is_symlink()
                and cleanup_content_matches_template(
                    file,
                    cleanup_target,
                    destination.read_bytes(),
                )
            )
            if not force and not content_matches_template:
                reason = (
                    "target is a symlink"
                    if destination.is_symlink()
                    else "content differs from pack template"
                )
                results.append(
                    LegacyCleanupResult(
                        cleanup_target,
                        conflict_status,
                        reason,
                    )
                )
                continue

            status = "would-remove" if dry_run else "removed"
            backup_path: Path | None = None
            if not dry_run:
                if backup:
                    backup_path = next_backup_path(target, destination)
                    if destination.is_symlink():
                        backup_path.symlink_to(destination.readlink())
                    else:
                        shutil.copyfile(destination, backup_path)
                destination.unlink()
                with contextlib.suppress(OSError):
                    destination.parent.rmdir()
            results.append(
                LegacyCleanupResult(cleanup_target, status, backup=backup_path)
            )
    return results


def cleanup_legacy_adapters(
    selected: list[PackFile],
    target: Path,
    *,
    dry_run: bool,
    force: bool,
    backup: bool,
) -> list[LegacyCleanupResult]:
    return cleanup_adapter_targets(
        selected,
        target,
        dry_run=dry_run,
        force=force,
        backup=backup,
        target_for_file=legacy_adapter_target,
        conflict_status="legacy-conflict",
    )


def cleanup_obsolete_adapters(
    selected: list[PackFile],
    target: Path,
    *,
    dry_run: bool,
    force: bool,
    backup: bool,
) -> list[LegacyCleanupResult]:
    return cleanup_adapter_targets(
        selected,
        target,
        dry_run=dry_run,
        force=force,
        backup=backup,
        target_for_file=obsolete_adapter_target,
        conflict_status="obsolete-conflict",
    )


def run_diff_check(target: Path, paths: list[Path] | None = None) -> int:
    if paths == []:
        return 0

    command = ["git", "diff", "--check"]
    if paths:
        command.extend(["--", *(str(path) for path in paths)])

    try:
        result = subprocess.run(
            command,
            cwd=target,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError:
        print("warning: git not found; skipped git diff --check")
        return 0

    if result.stdout:
        print(result.stdout.rstrip())
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.backup and not args.force:
        raise SystemExit("error: --backup requires --force")

    target = Path(args.target).resolve()
    manifest, files = load_manifest()

    validate_manifest(files)
    require_trellis_repo(target)
    selected, skipped = selected_files(files, target, args.platform, args.all)

    print(f"{manifest['name']} {manifest['version']}")
    print(f"target: {target}")
    if args.dry_run:
        print("mode: dry-run")

    results: list[InstallResult] = []
    for file in selected:
        if file.kind == MANAGED_BLOCK_KIND:
            result = install_managed_block(
                file,
                target,
                dry_run=args.dry_run,
            )
        else:
            result = install_file(
                file,
                target,
                force=args.force,
                dry_run=args.dry_run,
                backup=args.backup,
            )
        results.append(result)

    results.append(
        install_installed_targets_file(
            selected,
            target,
            dry_run=args.dry_run,
        )
    )

    for result in results:
        print(f"{result.status:11} {result.file.target}")
        if result.backup:
            print(f"{'backup':11} {result.backup.relative_to(target)}")
    for file, reason in skipped:
        print(f"skipped     {file.target} ({reason})")

    conflicts = [result.file for result in results if result.status == "conflict"]
    if conflicts:
        print("")
        print("Conflicts:")
        for file in conflicts:
            print(f"- {file.target}")
        print("Re-run with --force to overwrite these files.")
        return 2

    legacy_results = cleanup_legacy_adapters(
        selected,
        target,
        dry_run=args.dry_run,
        force=args.force,
        backup=args.backup,
    )
    for result in legacy_results:
        suffix = f" ({result.reason})" if result.reason else ""
        print(f"{result.status:11} {result.target}{suffix}")
        if result.backup:
            print(f"{'backup':11} {result.backup.relative_to(target)}")

    legacy_conflicts = [
        result for result in legacy_results if result.status == "legacy-conflict"
    ]
    if legacy_conflicts:
        print("")
        print("Legacy adapter conflicts:")
        for result in legacy_conflicts:
            suffix = f" ({result.reason})" if result.reason else ""
            print(f"- {result.target}{suffix}")
        print(
            "Re-run with --force to delete these legacy adapter files. "
            "Add --backup to save a .bak copy of each removed file first."
        )
        return 2

    obsolete_results = cleanup_obsolete_adapters(
        selected,
        target,
        dry_run=args.dry_run,
        force=args.force,
        backup=args.backup,
    )
    for result in obsolete_results:
        suffix = f" ({result.reason})" if result.reason else ""
        print(f"{result.status:11} {result.target}{suffix}")
        if result.backup:
            print(f"{'backup':11} {result.backup.relative_to(target)}")

    obsolete_conflicts = [
        result for result in obsolete_results if result.status == "obsolete-conflict"
    ]
    if obsolete_conflicts:
        print("")
        print("Obsolete adapter conflicts:")
        for result in obsolete_conflicts:
            suffix = f" ({result.reason})" if result.reason else ""
            print(f"- {result.target}{suffix}")
        print(
            "Re-run with --force to delete these obsolete adapter files. "
            "Add --backup to save a .bak copy of each removed file first."
        )
        return 2

    if not args.dry_run and not args.skip_diff_check:
        diff_paths = [
            result.file.target
            for result in results
            if result.status not in {"conflict", "preserved"}
        ]
        diff_paths.extend(
            result.target for result in legacy_results if result.status == "removed"
        )
        diff_paths.extend(
            result.target for result in obsolete_results if result.status == "removed"
        )
        diff_status = run_diff_check(target, diff_paths)
        if diff_status != 0:
            return diff_status

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
