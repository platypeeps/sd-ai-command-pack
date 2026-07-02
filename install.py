#!/usr/bin/env python3
"""Install the SD AI command pack into a Trellis repo."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
PLATFORMS = ("claude", "cursor", "gemini", "github", "opencode", "shared")
ALWAYS_INSTALL = "always"
IF_NOT_EXISTS = "if-not-exists"
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
TRELLIS_INSTALL_DOCS_URL = "https://docs.trytrellis.app/start/install-and-first-task"
FORCE_PRESERVED_TARGETS = frozenset(
    {
        Path(".prism/rules.json"),
        Path(".gito/config.toml"),
        Path(".github/PULL_REQUEST_TEMPLATE.md"),
    }
)
INSTALLED_TARGETS_FILE = Path(".sd-ai-command-pack/installed-targets.txt")
LOCAL_ONLY_MARKER_FILE = Path(".sd-ai-command-pack/local-only.txt")
LOCAL_ONLY_EXCLUDE_START = "# sd-ai-command-pack local-only start"
LOCAL_ONLY_EXCLUDE_END = "# sd-ai-command-pack local-only end"
TRELLIS_GITIGNORE_TARGET = Path(".gitignore")
TRELLIS_GITIGNORE_START = "# sd-ai-command-pack trellis-gitignore start"
TRELLIS_GITIGNORE_END = "# sd-ai-command-pack trellis-gitignore end"
LOCAL_ENV_GITIGNORE_PATTERNS = (
    ".env",
    ".env.*",
    "!.env.example",
    "!.env.ci",
    "!.env.test",
)
TRELLIS_GITIGNORE_PATTERNS = (
    ".trellis/.developer",
    ".trellis/.backup-*",
    ".trellis/worktrees/",
    ".trellis/.template-hashes.json",
    ".trellis/.runtime/",
    ".trellis/.cache/",
)
REVIEW_ARTIFACT_GITIGNORE_PATTERNS = (
    ".build/",
    "code-review-report.json",
    "code-review-report.md",
    "sd-ai-command-pack-gito.*",
    "sd-ai-command-pack-review-paths.*",
    "sd-ai-command-pack-review-filters.*",
    "sd-ai-command-pack-prism-codebase.*",
    "sd-ai-command-pack-ci-paths.*",
    "sd-ai-command-pack-uv-cache/",
    "sd-ai-command-pack-uv-tools/",
)
PLATFORM_LOCAL_GITIGNORE_PATTERNS = (
    ".claude/settings.local.json",
    ".claude/**/*.local.*",
    ".claude/**/.cache/",
    ".claude/**/cache/",
    ".claude/**/logs/",
    ".claude/**/*.log",
    ".codex/**/*.local.*",
    ".codex/**/.cache/",
    ".codex/**/cache/",
    ".codex/**/logs/",
    ".codex/**/sessions/",
    ".codex/**/tmp/",
    ".codex/**/*.log",
    ".gemini/settings.local.json",
    ".gemini/**/*.local.*",
    ".gemini/**/.cache/",
    ".gemini/**/cache/",
    ".gemini/**/logs/",
    ".gemini/**/tmp/",
    ".gemini/**/*.log",
    ".gito/**/*.local.*",
    ".gito/**/.cache/",
    ".gito/**/cache/",
    ".gito/**/logs/",
    ".gito/**/tmp/",
    ".gito/**/*.log",
    ".opencode/**/*.local.*",
    ".opencode/**/.cache/",
    ".opencode/**/cache/",
    ".opencode/**/logs/",
    ".opencode/**/tmp/",
    ".opencode/**/state/",
    ".opencode/**/sessions/",
    ".opencode/node_modules/",
    ".opencode/**/*.log",
    "node_modules/",
)
TRELLIS_BLANKET_GITIGNORE_ENTRIES = frozenset(
    {
        ".trellis",
        ".trellis/",
        "/.trellis",
        "/.trellis/",
    }
)
LOCAL_ONLY_TRELLIS_EXCLUDES = (
    "AGENTS.md",
    ".trellis/",
    ".agents/skills/trellis-*/",
    ".claude/commands/trellis/",
    ".claude/hooks/",
    ".claude/skills/trellis-*/",
    ".codex/agents/trellis-*.toml",
    ".codex/config.toml",
    ".codex/hooks.json",
    ".codex/hooks/",
    ".cursor/agents/trellis-*.md",
    ".cursor/commands/trellis-*.md",
    ".cursor/hooks.json",
    ".cursor/hooks/",
    ".cursor/skills/trellis-*/",
    ".gemini/commands/trellis/",
    ".gemini/hooks/",
    ".gemini/agents/trellis-*.md",
    ".github/hooks/trellis.json",
    ".github/copilot/hooks.json",
    ".github/skills/trellis-*/",
    ".opencode/commands/trellis/",
    ".opencode/lib/trellis-context.js",
    ".opencode/skills/trellis-*/",
    ".obsidian-kb/",
)
LOCAL_ONLY_TRACKED_CHECK_PATHS = (
    "AGENTS.md",
    ".trellis",
    ".agents/skills/trellis-*",
    ".claude/commands/trellis",
    ".claude/hooks",
    ".claude/skills/trellis-*",
    ".codex/agents/trellis-*.toml",
    ".codex/config.toml",
    ".codex/hooks.json",
    ".codex/hooks",
    ".cursor/agents/trellis-*.md",
    ".cursor/commands/trellis-*.md",
    ".cursor/hooks.json",
    ".cursor/hooks",
    ".cursor/skills/trellis-*",
    ".gemini/commands/trellis",
    ".gemini/hooks",
    ".gemini/agents/trellis-*.md",
    ".github/hooks/trellis.json",
    ".github/copilot/hooks.json",
    ".github/skills/trellis-*",
    ".opencode/commands/trellis",
    ".opencode/lib/trellis-context.js",
    ".opencode/skills/trellis-*",
)
TRELLIS_INIT_PLATFORM_FLAGS = {
    "claude": "--claude",
    "cursor": "--cursor",
    "gemini": "--gemini",
    "github": "--copilot",
    "opencode": "--opencode",
}
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
class LocalOnlyResult:
    status: str
    target: Path
    detail: str | None = None


def load_manifest() -> tuple[dict, list[PackFile]]:
    raw = json.loads(read_text_strict(MANIFEST_PATH, "manifest"))
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


def read_text_strict(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"error: {label} not found: {path}") from None
    except UnicodeDecodeError as error:
        raise SystemExit(f"error: {label} is not valid UTF-8: {path} ({error})") from None
    except OSError as error:
        raise SystemExit(f"error: cannot read {label}: {path} ({error})") from None


def read_text_if_exists(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except UnicodeDecodeError as error:
        raise SystemExit(f"error: {label} is not valid UTF-8: {path} ({error})") from None
    except OSError as error:
        raise SystemExit(f"error: cannot read {label}: {path} ({error})") from None


def atomic_write_bytes(destination: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, destination)
        temporary_path = None
    except OSError as error:
        raise SystemExit(f"error: cannot write {destination}: {error}") from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def atomic_write_text(destination: Path, content: str) -> None:
    atomic_write_bytes(destination, content.encode("utf-8"))


def atomic_write_text_preserving_invalid_utf8(destination: Path, content: str) -> None:
    atomic_write_bytes(destination, content.encode("utf-8", errors="surrogateescape"))


def marker_pair_indexes(
    current: str,
    start_marker: str,
    end_marker: str,
    label: str,
) -> tuple[int, int]:
    start_index = current.find(start_marker)
    end_index = current.find(end_marker)
    has_start = start_index != -1
    has_end = end_index != -1
    if has_start != has_end or (has_start and end_index < start_index):
        raise SystemExit(f"error: {label} has incomplete sd-ai-command-pack markers")
    if has_start and current.find(start_marker, start_index + len(start_marker)) != -1:
        raise SystemExit(f"error: {label} has duplicate sd-ai-command-pack start markers")
    if has_end and current.find(end_marker, end_index + len(end_marker)) != -1:
        raise SystemExit(f"error: {label} has duplicate sd-ai-command-pack end markers")
    return start_index, end_index


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


def target_destination(target: Path, relative_path: Path, label: str = "target path") -> Path:
    validate_relative_manifest_path("target", relative_path)
    destination = target / relative_path
    validate_resolved_target_path(target, destination, label)
    return destination


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
            "Shared skills, scripts, Prism/Gito defaults, and docs are always installed."
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
            "(except .prism/rules.json and .gito/config.toml). Add --backup "
            "to save .bak copies before overwriting."
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
        "--local-only",
        action="store_true",
        help=(
            "Set up Trellis and this pack for only the current checkout. "
            "When Trellis is missing, run `trellis init --yes --skip-existing` "
            "first, then add generated Trellis and pack paths to "
            ".git/info/exclude instead of changing tracked ignore files."
        ),
    )
    parser.add_argument(
        "--skip-trellis-init",
        action="store_true",
        help=(
            "With --local-only, do not run `trellis init` automatically; "
            "require an existing .trellis/config.yaml."
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


def git_output(
    target: Path,
    *args: str,
    required: bool = False,
    context: str = "run git",
) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=target,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError:
        if required:
            raise SystemExit(f"error: git is required to {context}") from None
        return None
    if result.returncode != 0:
        if required:
            detail = result.stdout.strip()
            suffix = f": {detail}" if detail else f" (exit status {result.returncode})"
            raise SystemExit(f"error: failed to {context}{suffix}") from None
        return None
    return result.stdout.strip()


def require_git_repo_for_local_only(target: Path) -> None:
    repo_root = git_output(
        target,
        "rev-parse",
        "--show-toplevel",
        required=True,
        context="verify --local-only target Git repository",
    )
    if not repo_root:
        raise SystemExit("error: --local-only requires the target to be a Git repo")
    try:
        resolved_repo = Path(repo_root).resolve()
        resolved_target = target.resolve()
    except OSError as error:
        raise SystemExit(f"error: cannot resolve target repo: {error}") from None
    if resolved_repo != resolved_target:
        raise SystemExit(
            "error: --local-only target must be the Git repo root "
            f"(got {target}, repo root is {resolved_repo})"
        )


def git_info_exclude_path(target: Path) -> Path:
    exclude_path = git_output(
        target,
        "rev-parse",
        "--git-path",
        "info/exclude",
        required=True,
        context="find .git/info/exclude for --local-only",
    )
    if not exclude_path:
        raise SystemExit("error: cannot find .git/info/exclude for --local-only")
    path = Path(exclude_path)
    if not path.is_absolute():
        path = target / path
    return path


def trellis_init_platforms(
    platforms: list[str] | None,
    install_all: bool,
) -> list[str]:
    if install_all:
        return sorted(TRELLIS_INIT_PLATFORM_FLAGS)
    return sorted(
        platform
        for platform in set(platforms or [])
        if platform in TRELLIS_INIT_PLATFORM_FLAGS
    )


def trellis_init_command(
    platforms: list[str] | None,
    install_all: bool,
) -> list[str]:
    command = ["trellis", "init", "--yes", "--skip-existing", "--codex"]
    command.extend(
        TRELLIS_INIT_PLATFORM_FLAGS[platform]
        for platform in trellis_init_platforms(platforms, install_all)
    )
    return command


def ensure_trellis_for_local_only(
    target: Path,
    *,
    platforms: list[str] | None,
    install_all: bool,
    dry_run: bool,
    skip_trellis_init: bool,
) -> LocalOnlyResult:
    if (target / ".trellis" / "config.yaml").is_file():
        return LocalOnlyResult("trellis-present", Path(".trellis/config.yaml"))
    if skip_trellis_init:
        require_trellis_repo(target)

    command = trellis_init_command(platforms, install_all)
    if dry_run:
        return LocalOnlyResult(
            "would-init-trellis-local",
            Path(".trellis/config.yaml"),
            " ".join(command),
        )

    if shutil.which("trellis") is None:
        raise SystemExit(
            "error: --local-only needs `trellis` on PATH to initialize this "
            f"repo first: {TRELLIS_INSTALL_DOCS_URL}"
        )

    result = subprocess.run(
        command,
        cwd=target,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        output = result.stdout.rstrip()
        if output:
            print(output)
        raise SystemExit("error: trellis init failed for --local-only") from None
    if not (target / ".trellis" / "config.yaml").is_file():
        raise SystemExit(
            "error: trellis init completed but .trellis/config.yaml is missing"
        )
    return LocalOnlyResult(
        "initialized-trellis-local",
        Path(".trellis/config.yaml"),
        " ".join(command),
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
        if file.install in {ALWAYS_INSTALL, IF_NOT_EXISTS}:
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
    destination = target_destination(target, file.target)
    if path_is_occupied(destination) and not destination.is_file():
        raise SystemExit(f"error: target exists and is not a file: {file.target}")
    new_content = source.read_bytes()
    if destination.exists():
        current = destination.read_bytes()
        if current == new_content:
            return InstallResult(file, "unchanged")
        if file.install == IF_NOT_EXISTS or file.target in FORCE_PRESERVED_TARGETS:
            return InstallResult(file, "preserved")
        if not force:
            return InstallResult(file, "conflict")
        backup_path = (
            next_backup_path(target, destination) if backup and not dry_run else None
        )
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if backup_path:
                shutil.copyfile(destination, backup_path)
            atomic_write_bytes(destination, new_content)
        return InstallResult(file, "overwritten", backup_path)

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(destination, new_content)
    return InstallResult(file, "created")


def normalize_managed_block_template(file: PackFile) -> str:
    block = read_text_strict(
        file.source,
        f"managed block template {file.source}",
    ).strip("\n") + "\n"
    if COPILOT_GUIDANCE_START not in block or COPILOT_GUIDANCE_END not in block:
        raise SystemExit(
            f"error: managed block template missing markers: {file.source}"
        )
    return block


def merge_managed_block(current: str, block: str) -> str:
    start_index, end_index = marker_pair_indexes(
        current,
        COPILOT_GUIDANCE_START,
        COPILOT_GUIDANCE_END,
        ".github/copilot-instructions.md",
    )
    has_start = start_index != -1
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


def trellis_gitignore_block() -> str:
    lines = [
        TRELLIS_GITIGNORE_START,
        "# Generated by `python3 install.py`. DO NOT EDIT MANUALLY.",
        "# Ignore local/runtime files without hiding shared Trellis or AI-tool adapters.",
        "# Common local secrets and environment files.",
        *LOCAL_ENV_GITIGNORE_PATTERNS,
        "",
        "# Trellis local/runtime state.",
        *TRELLIS_GITIGNORE_PATTERNS,
        "",
        "# Review/build artifacts.",
        *REVIEW_ARTIFACT_GITIGNORE_PATTERNS,
        "",
        "# AI-tool local state; keep shared platform adapters tracked.",
        *PLATFORM_LOCAL_GITIGNORE_PATTERNS,
        "",
        "# Project-local personal ignores can be added below this managed block.",
        TRELLIS_GITIGNORE_END,
    ]
    return "\n".join(lines) + "\n"


def remove_unmanaged_trellis_blanket_entries(current: str) -> tuple[str, bool]:
    kept: list[str] = []
    removed = False
    for line in current.splitlines(keepends=True):
        if line.strip() in TRELLIS_BLANKET_GITIGNORE_ENTRIES:
            removed = True
            continue
        kept.append(line)
    return "".join(kept), removed


def merge_trellis_gitignore_block(current: str) -> str:
    block = trellis_gitignore_block()
    start_index, end_index = marker_pair_indexes(
        current,
        TRELLIS_GITIGNORE_START,
        TRELLIS_GITIGNORE_END,
        ".gitignore",
    )
    has_start = start_index != -1
    if has_start:
        replace_end = end_index + len(TRELLIS_GITIGNORE_END)
        if replace_end < len(current) and current[replace_end] == "\n":
            replace_end += 1
        return current[:start_index] + block + current[replace_end:]

    prefix, _ = remove_unmanaged_trellis_blanket_entries(current)
    if not prefix.strip():
        return block
    if not prefix.endswith("\n"):
        prefix += "\n"
    if not prefix.endswith("\n\n"):
        prefix += "\n"
    return prefix + block


def install_trellis_gitignore(target: Path, *, dry_run: bool) -> InstallResult:
    file = PackFile(
        platform="shared",
        kind="generated-gitignore",
        source=MANIFEST_PATH,
        target=TRELLIS_GITIGNORE_TARGET,
        anchor=None,
        install=ALWAYS_INSTALL,
    )
    destination = target_destination(target, file.target)
    if path_is_occupied(destination) and not destination.is_file():
        raise SystemExit(f"error: target exists and is not a file: {file.target}")

    current = read_text_if_exists(destination, str(file.target))
    merged = merge_trellis_gitignore_block(current)
    if merged == current:
        return InstallResult(file, "unchanged")
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(destination, merged)
    return InstallResult(file, "updated" if destination.exists() else "created")


def install_managed_block(
    file: PackFile,
    target: Path,
    *,
    dry_run: bool,
) -> InstallResult:
    if file.target != COPILOT_INSTRUCTIONS_TARGET:
        raise SystemExit(f"error: unsupported managed block target: {file.target}")

    destination = target_destination(target, file.target)
    if path_is_occupied(destination) and not destination.is_file():
        raise SystemExit(f"error: target exists and is not a file: {file.target}")

    block = normalize_managed_block_template(file)
    if destination.exists():
        current = destination.read_bytes().decode(
            "utf-8",
            errors="surrogateescape",
        )
        merged = merge_managed_block(current, block)
        if merged == current:
            return InstallResult(file, "unchanged")
        if not dry_run:
            atomic_write_text_preserving_invalid_utf8(destination, merged)
        return InstallResult(file, "updated")

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(destination, block)
    return InstallResult(file, "created")


def installed_targets_content(
    selected: list[PackFile],
    *,
    extra_targets: Iterable[Path] = (),
) -> str:
    targets = {file.target.as_posix() for file in selected}
    targets.update(target.as_posix() for target in extra_targets)
    targets.add(INSTALLED_TARGETS_FILE.as_posix())
    targets = sorted(targets)
    return "\n".join(targets) + "\n"


def local_only_pack_excludes(selected: list[PackFile]) -> tuple[str, ...]:
    paths = {file.target.as_posix() for file in selected}
    paths.add(INSTALLED_TARGETS_FILE.as_posix())
    paths.add(LOCAL_ONLY_MARKER_FILE.as_posix())
    paths.add(".sd-ai-command-pack/")
    return tuple(sorted(paths))


def local_only_exclude_patterns(selected: list[PackFile]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *LOCAL_ONLY_TRELLIS_EXCLUDES,
                *local_only_pack_excludes(selected),
            )
        )
    )


def local_only_tracked_check_specs(selected: list[PackFile]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *LOCAL_ONLY_TRACKED_CHECK_PATHS,
                *(file.target.as_posix() for file in selected),
                INSTALLED_TARGETS_FILE.as_posix(),
                LOCAL_ONLY_MARKER_FILE.as_posix(),
            )
        )
    )


def tracked_paths(target: Path, specs: Iterable[str]) -> list[str]:
    spec_list = list(specs)
    if not spec_list:
        return []
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", *spec_list],
            cwd=target,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError:
        raise SystemExit("error: git is required to check tracked --local-only paths") from None
    if result.returncode != 0:
        raise SystemExit(f"error: git ls-files failed: {result.stdout}") from None
    return [line for line in result.stdout.splitlines() if line]


def reject_tracked_local_only_paths(target: Path, selected: list[PackFile]) -> None:
    tracked = tracked_paths(target, local_only_tracked_check_specs(selected))
    if not tracked:
        return
    print("error: --local-only cannot manage paths that are already tracked:")
    for path in tracked[:20]:
        print(f"- {path}")
    if len(tracked) > 20:
        print(f"- ... {len(tracked) - 20} more")
    raise SystemExit(
        "Remove these paths from Git tracking or use the normal tracked install."
    )


def local_only_exclude_block(patterns: Iterable[str]) -> str:
    lines = [
        LOCAL_ONLY_EXCLUDE_START,
        "# Generated by `python3 install.py --local-only`.",
        "# Keeps personal Trellis and SD AI command pack files out of commits.",
        *patterns,
        LOCAL_ONLY_EXCLUDE_END,
    ]
    return "\n".join(lines) + "\n"


def merge_local_only_exclude_block(current: str, block: str) -> str:
    start_index, end_index = marker_pair_indexes(
        current,
        LOCAL_ONLY_EXCLUDE_START,
        LOCAL_ONLY_EXCLUDE_END,
        ".git/info/exclude",
    )
    has_start = start_index != -1
    if has_start:
        replace_end = end_index + len(LOCAL_ONLY_EXCLUDE_END)
        if replace_end < len(current) and current[replace_end] == "\n":
            replace_end += 1
        return current[:start_index] + block + current[replace_end:]
    if not current:
        return block
    prefix = current
    if not prefix.endswith("\n"):
        prefix += "\n"
    if not prefix.endswith("\n\n"):
        prefix += "\n"
    return prefix + block


def ensure_local_only_exclude(
    target: Path,
    selected: list[PackFile],
    *,
    dry_run: bool,
) -> LocalOnlyResult:
    exclude_path = git_info_exclude_path(target)
    validate_resolved_target_path(exclude_path.parent.parent, exclude_path, "git exclude path")
    current = read_text_if_exists(exclude_path, ".git/info/exclude")
    block = local_only_exclude_block(local_only_exclude_patterns(selected))
    merged = merge_local_only_exclude_block(current, block)
    if merged == current:
        return LocalOnlyResult("local-exclude-unchanged", exclude_path)
    if dry_run:
        return LocalOnlyResult("would-update-local-exclude", exclude_path)
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(exclude_path, merged)
    status = "local-exclude-updated" if current else "local-exclude-created"
    return LocalOnlyResult(status, exclude_path)


def write_local_only_marker(target: Path, *, dry_run: bool) -> LocalOnlyResult:
    marker = target / LOCAL_ONLY_MARKER_FILE
    content = (
        "This checkout was set up with `sd-ai-command-pack --local-only`.\n"
        "Generated Trellis and SD AI command pack files are ignored through "
        ".git/info/exclude for this local clone.\n"
    )
    if marker.exists() and read_text_strict(marker, str(LOCAL_ONLY_MARKER_FILE)) == content:
        return LocalOnlyResult("local-only-marker-unchanged", LOCAL_ONLY_MARKER_FILE)
    if dry_run:
        return LocalOnlyResult("would-write-local-only-marker", LOCAL_ONLY_MARKER_FILE)
    marker.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(marker, content)
    return LocalOnlyResult("local-only-marker-written", LOCAL_ONLY_MARKER_FILE)


def install_installed_targets_file(
    selected: list[PackFile],
    target: Path,
    *,
    dry_run: bool,
    extra_targets: Iterable[Path] = (),
) -> InstallResult:
    file = PackFile(
        platform="shared",
        kind="generated-manifest",
        source=MANIFEST_PATH,
        target=INSTALLED_TARGETS_FILE,
        anchor=None,
        install=ALWAYS_INSTALL,
    )
    destination = target_destination(target, file.target)

    content = installed_targets_content(selected, extra_targets=extra_targets)
    if destination.exists():
        current = read_text_strict(destination, str(file.target))
        if current == content:
            return InstallResult(file, "unchanged")
        if not dry_run:
            atomic_write_text(destination, content)
        return InstallResult(file, "updated")

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(destination, content)
    return InstallResult(file, "created")


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


def display_path(target: Path, path: Path) -> Path:
    try:
        return path.relative_to(target)
    except ValueError:
        return path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.backup and not args.force:
        raise SystemExit("error: --backup requires --force")
    if args.skip_trellis_init and not args.local_only:
        raise SystemExit("error: --skip-trellis-init requires --local-only")

    target = Path(args.target).resolve()
    manifest, files = load_manifest()

    validate_manifest(files)
    local_only_results: list[LocalOnlyResult] = []
    if args.local_only:
        require_git_repo_for_local_only(target)
        selected, skipped = selected_files(files, target, args.platform, args.all)
        reject_tracked_local_only_paths(target, selected)
        local_only_results.append(
            ensure_trellis_for_local_only(
                target,
                platforms=args.platform,
                install_all=args.all,
                dry_run=args.dry_run,
                skip_trellis_init=args.skip_trellis_init,
            )
        )
    else:
        require_trellis_repo(target)
        selected, skipped = selected_files(files, target, args.platform, args.all)
    if args.local_only:
        local_only_results.append(
            ensure_local_only_exclude(
                target,
                selected,
                dry_run=args.dry_run,
            )
        )

    print(f"{manifest['name']} {manifest['version']}")
    print(f"target: {target}")
    if args.dry_run:
        print("mode: dry-run")
    if args.local_only:
        print("mode: local-only")
    local_only_results_printed = len(local_only_results)
    for result in local_only_results:
        suffix = f" ({result.detail})" if result.detail else ""
        print(f"{result.status:29} {display_path(target, result.target)}{suffix}")

    results: list[InstallResult] = []
    generated_targets: list[Path] = []
    if not args.local_only:
        results.append(
            install_trellis_gitignore(
                target,
                dry_run=args.dry_run,
            )
        )
        generated_targets.append(TRELLIS_GITIGNORE_TARGET)

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
            extra_targets=generated_targets,
        )
    )
    if args.local_only:
        local_only_results.append(
            write_local_only_marker(target, dry_run=args.dry_run)
        )

    for result in results:
        print(f"{result.status:11} {result.file.target}")
        if result.backup:
            print(f"{'backup':11} {result.backup.relative_to(target)}")
    for result in local_only_results[local_only_results_printed:]:
        suffix = f" ({result.detail})" if result.detail else ""
        print(f"{result.status:29} {display_path(target, result.target)}{suffix}")
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

    if not args.dry_run and not args.skip_diff_check:
        diff_paths = [
            result.file.target
            for result in results
            if result.status not in {"conflict", "preserved"}
        ]
        diff_status = run_diff_check(target, diff_paths)
        if diff_status != 0:
            return diff_status

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
