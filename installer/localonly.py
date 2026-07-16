"""Local-only install mode: git info/exclude wiring and Trellis bootstrap."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from installer.fileops import (
    RemoveResult,
    atomic_write_text,
    marker_pair_indexes,
    remove_marked_block,
)
from installer.manifest import (
    PackFile,
    read_text_if_exists,
    read_text_strict,
    require_trellis_repo,
    system_exit_detail,
    validate_resolved_target_path,
)
from installer.registry import (
    INSTALLED_TARGETS_FILE,
    LOCAL_ONLY_EXCLUDE_END,
    LOCAL_ONLY_EXCLUDE_START,
    LOCAL_ONLY_MARKER_FILE,
    LOCAL_ONLY_TRACKED_CHECK_PATHS,
    LOCAL_ONLY_TRELLIS_EXCLUDES,
    TRELLIS_INIT_PLATFORM_FLAGS,
    TRELLIS_INSTALL_DOCS_URL,
)
from installer.status import LocalOnlyStatus, RemoveStatus


@dataclass(frozen=True)
class LocalOnlyResult:
    status: LocalOnlyStatus
    target: Path
    detail: str | None = None


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
        return LocalOnlyResult(
            LocalOnlyStatus.TRELLIS_PRESENT,
            Path(".trellis/config.yaml"),
        )
    if skip_trellis_init:
        require_trellis_repo(target)

    command = trellis_init_command(platforms, install_all)
    if dry_run:
        return LocalOnlyResult(
            LocalOnlyStatus.WOULD_INIT_TRELLIS_LOCAL,
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
        LocalOnlyStatus.INITIALIZED_TRELLIS_LOCAL,
        Path(".trellis/config.yaml"),
        " ".join(command),
    )


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
        return LocalOnlyResult(LocalOnlyStatus.LOCAL_EXCLUDE_UNCHANGED, exclude_path)
    if dry_run:
        return LocalOnlyResult(
            LocalOnlyStatus.WOULD_UPDATE_LOCAL_EXCLUDE,
            exclude_path,
        )
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(exclude_path, merged)
    status = (
        LocalOnlyStatus.LOCAL_EXCLUDE_UPDATED
        if current
        else LocalOnlyStatus.LOCAL_EXCLUDE_CREATED
    )
    return LocalOnlyResult(status, exclude_path)


def write_local_only_marker(target: Path, *, dry_run: bool) -> LocalOnlyResult:
    marker = target / LOCAL_ONLY_MARKER_FILE
    content = (
        "This checkout was set up with `sd-ai-command-pack --local-only`.\n"
        "Generated Trellis and SD AI command pack files are ignored through "
        ".git/info/exclude for this local clone.\n"
    )
    if marker.exists() and read_text_strict(marker, str(LOCAL_ONLY_MARKER_FILE)) == content:
        return LocalOnlyResult(
            LocalOnlyStatus.LOCAL_ONLY_MARKER_UNCHANGED,
            LOCAL_ONLY_MARKER_FILE,
        )
    if dry_run:
        return LocalOnlyResult(
            LocalOnlyStatus.WOULD_WRITE_LOCAL_ONLY_MARKER,
            LOCAL_ONLY_MARKER_FILE,
        )
    marker.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(marker, content)
    return LocalOnlyResult(
        LocalOnlyStatus.LOCAL_ONLY_MARKER_WRITTEN,
        LOCAL_ONLY_MARKER_FILE,
    )


def optional_git_info_exclude_path(target: Path) -> Path | None:
    try:
        return git_info_exclude_path(target)
    except SystemExit:
        return None


def remove_local_only_exclude(target: Path, *, dry_run: bool) -> RemoveResult | None:
    exclude_path = optional_git_info_exclude_path(target)
    if exclude_path is None:
        return None
    try:
        validate_resolved_target_path(
            exclude_path.parent.parent,
            exclude_path,
            "git exclude path",
        )
        current = read_text_if_exists(exclude_path, ".git/info/exclude")
        stripped = remove_marked_block(
            current,
            start_marker=LOCAL_ONLY_EXCLUDE_START,
            end_marker=LOCAL_ONLY_EXCLUDE_END,
            label=".git/info/exclude",
        )
    except SystemExit as error:
        return RemoveResult(
            exclude_path,
            RemoveStatus.PRESERVED,
            detail=system_exit_detail(error),
        )
    if stripped == current:
        return None
    if dry_run:
        return RemoveResult(exclude_path, RemoveStatus.WOULD_UPDATE)
    atomic_write_text(exclude_path, stripped)
    return RemoveResult(exclude_path, RemoveStatus.UPDATED)


__all__ = [
    "LocalOnlyResult",
    "LocalOnlyStatus",
    "ensure_local_only_exclude",
    "ensure_trellis_for_local_only",
    "git_info_exclude_path",
    "git_output",
    "local_only_exclude_block",
    "local_only_exclude_patterns",
    "local_only_pack_excludes",
    "local_only_tracked_check_specs",
    "merge_local_only_exclude_block",
    "optional_git_info_exclude_path",
    "reject_tracked_local_only_paths",
    "remove_local_only_exclude",
    "require_git_repo_for_local_only",
    "tracked_paths",
    "trellis_init_command",
    "trellis_init_platforms",
    "write_local_only_marker",
]
