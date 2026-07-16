"""Payload file operations: selection, atomic writes, backups, managed text blocks."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from installer.manifest import (
    MANIFEST_PATH,
    PackFile,
    read_text_if_exists,
    read_text_strict,
    removal_target_destination,
    system_exit_detail,
    target_destination,
    validate_resolved_target_path,
)
from installer.registry import (
    ACTIVE_TRELLIS_PLATFORM_MARKERS,
    ALWAYS_INSTALL,
    COPILOT_GUIDANCE_END,
    COPILOT_GUIDANCE_START,
    COPILOT_INSTRUCTIONS_TARGET,
    FORCE_PRESERVED_TARGETS,
    IF_ANCHOR_EXISTS,
    IF_NOT_EXISTS,
    LOCAL_ENV_GITIGNORE_PATTERNS,
    PLATFORM_LOCAL_GITIGNORE_PATTERNS,
    REVIEW_ARTIFACT_GITIGNORE_PATTERNS,
    TRELLIS_BLANKET_GITIGNORE_ENTRIES,
    TRELLIS_GITIGNORE_END,
    TRELLIS_GITIGNORE_PATTERNS,
    TRELLIS_GITIGNORE_START,
    TRELLIS_GITIGNORE_TARGET,
)
from installer.status import (
    CONFLICT_STATUSES,
    VOUCHABLE_STATUSES,
    InstallStatus,
    RemoveStatus,
)

GIT_TIMEOUT_SECONDS = 60

_LEGACY_CLAUDE_GITIGNORE_SEQUENCE = (
    ".claude/**",
    "!.claude/commands/",
    "!.claude/commands/sd/",
    "!.claude/commands/sd/*.md",
)


@dataclass(frozen=True)
class InstallResult:
    file: PackFile
    status: InstallStatus
    backup: Path | None = None


def generated_pack_file(kind: str, target: Path) -> PackFile:
    """PackFile for an installer-generated file (receipt/manifest/provenance/gitignore)."""
    return PackFile(
        platform="shared",
        kind=kind,
        source=MANIFEST_PATH,
        target=target,
        anchor=None,
        install=ALWAYS_INSTALL,
    )


def default_file_mode(*, executable: bool = False) -> int:
    current_umask = os.umask(0)
    try:
        base_mode = 0o777 if executable else 0o666
        return base_mode & ~current_umask
    finally:
        os.umask(current_umask)


def source_is_executable(source: Path) -> bool:
    return bool(source.stat().st_mode & 0o111)


def atomic_write_bytes(
    destination: Path,
    content: bytes,
    *,
    executable: bool = False,
) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        # NamedTemporaryFile creates 0600 files; installed files should get
        # normal umask-derived modes, executable when the caller requests it
        # (install_file passes the pack source's executable state).
        os.chmod(temporary_path, default_file_mode(executable=executable))
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


def has_active_trellis_platform(target: Path, platform: str) -> bool:
    markers = ACTIVE_TRELLIS_PLATFORM_MARKERS.get(platform, ())
    return any((target / marker).is_file() for marker in markers)


def selected_files(
    files: list[PackFile],
    target: Path,
    platforms: list[str] | None,
    install_all: bool,
) -> tuple[list[PackFile], list[tuple[PackFile, str]]]:
    """Split manifest files into (selected, skipped-with-reason) for one run,
    honoring always/if-not-exists policies, the platform filter or --all
    override, and anchor plus active-Trellis-platform detection."""
    selected: list[PackFile] = []
    skipped: list[tuple[PackFile, str]] = []
    platform_filter = set(platforms or [])

    for file in files:
        if file.install in {ALWAYS_INSTALL, IF_NOT_EXISTS}:
            selected.append(file)
            continue
        if file.install != IF_ANCHOR_EXISTS:
            raise SystemExit(
                f"error: unknown install mode {file.install!r} for {file.target}"
            )
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


def _require_file_destination(destination: Path, relative_target: Path) -> None:
    """Fail cleanly when the target path is occupied by a non-file node."""
    if path_is_occupied(destination) and not destination.is_file():
        raise SystemExit(
            f"error: target exists and is not a file: {relative_target}"
        )


def generated_text_file_status(destination: Path) -> InstallStatus | None:
    """Return the non-writing status for a generated text destination, if any."""
    if destination.is_symlink():
        return InstallStatus.SYMLINK_CONFLICT
    if destination.exists() and not destination.is_file():
        return InstallStatus.CONFLICT
    return None


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
    _require_file_destination(destination, file.target)
    new_content = source.read_bytes()
    executable = source_is_executable(source)
    if destination.is_symlink():
        # Provenance and the install audit vouch plain regular files only
        # (lstat-based), so a symlinked target must never report
        # "unchanged"/vouchable even when the linked content is identical.
        if file.install == IF_NOT_EXISTS or file.target in FORCE_PRESERVED_TARGETS:
            return InstallResult(file, InstallStatus.PRESERVED)
        if not force:
            return InstallResult(file, InstallStatus.SYMLINK_CONFLICT)
        backup_path = None
        if not dry_run:
            backup_path = backup_existing_file(
                target,
                destination,
                backup=backup,
                dry_run=dry_run,
            )
            atomic_write_bytes(destination, new_content, executable=executable)
        return InstallResult(file, InstallStatus.OVERWRITTEN, backup_path)
    if destination.exists():
        current = destination.read_bytes()
        if current == new_content:
            return InstallResult(file, InstallStatus.UNCHANGED)
        if file.install == IF_NOT_EXISTS or file.target in FORCE_PRESERVED_TARGETS:
            return InstallResult(file, InstallStatus.PRESERVED)
        if not force:
            return InstallResult(file, InstallStatus.CONFLICT)
        backup_path = None
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            backup_path = backup_existing_file(
                target,
                destination,
                backup=backup,
                dry_run=dry_run,
            )
            atomic_write_bytes(destination, new_content, executable=executable)
        return InstallResult(file, InstallStatus.OVERWRITTEN, backup_path)

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(destination, new_content, executable=executable)
    return InstallResult(file, InstallStatus.CREATED)


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


def remove_legacy_claude_gitignore_sequence(current: str) -> tuple[str, bool]:
    """Remove the exact pre-managed-block Claude policy used by older installs."""
    lines = current.splitlines(keepends=True)
    kept: list[str] = []
    removed = False
    index = 0
    sequence_length = len(_LEGACY_CLAUDE_GITIGNORE_SEQUENCE)
    while index < len(lines):
        candidate = tuple(
            line.rstrip("\r\n") for line in lines[index : index + sequence_length]
        )
        if candidate == _LEGACY_CLAUDE_GITIGNORE_SEQUENCE:
            removed = True
            index += sequence_length
            continue
        kept.append(lines[index])
        index += 1
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
        prefix, _ = remove_legacy_claude_gitignore_sequence(current[:start_index])
        replace_end = end_index + len(TRELLIS_GITIGNORE_END)
        if replace_end < len(current) and current[replace_end] == "\n":
            replace_end += 1
        return prefix + block + current[replace_end:]

    prefix, _ = remove_unmanaged_trellis_blanket_entries(current)
    prefix, _ = remove_legacy_claude_gitignore_sequence(prefix)
    if not prefix.strip():
        return block
    if not prefix.endswith("\n"):
        prefix += "\n"
    if not prefix.endswith("\n\n"):
        prefix += "\n"
    return prefix + block


def install_trellis_gitignore(target: Path, *, dry_run: bool) -> InstallResult:
    file = generated_pack_file("generated-gitignore", TRELLIS_GITIGNORE_TARGET)
    destination = target_destination(target, file.target)
    status = generated_text_file_status(destination)
    if status is not None:
        return InstallResult(file, status)
    _require_file_destination(destination, file.target)

    existed = destination.exists()
    current = read_text_if_exists(destination, str(file.target))
    merged = merge_trellis_gitignore_block(current)
    if merged == current:
        return InstallResult(file, InstallStatus.UNCHANGED)
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(destination, merged)
    return InstallResult(
        file,
        InstallStatus.UPDATED if existed else InstallStatus.CREATED,
    )


def install_managed_block(
    file: PackFile,
    target: Path,
    *,
    dry_run: bool,
) -> InstallResult:
    if file.target != COPILOT_INSTRUCTIONS_TARGET:
        raise SystemExit(f"error: unsupported managed block target: {file.target}")

    destination = target_destination(target, file.target)
    status = generated_text_file_status(destination)
    if status is not None:
        return InstallResult(file, status)
    _require_file_destination(destination, file.target)

    block = normalize_managed_block_template(file)
    if destination.exists():
        current = destination.read_bytes().decode(
            "utf-8",
            errors="surrogateescape",
        )
        merged = merge_managed_block(current, block)
        if merged == current:
            return InstallResult(file, InstallStatus.UNCHANGED)
        if not dry_run:
            atomic_write_text_preserving_invalid_utf8(destination, merged)
        return InstallResult(file, InstallStatus.UPDATED)

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(destination, block)
    return InstallResult(file, InstallStatus.CREATED)


def remove_marked_block(
    current: str,
    *,
    start_marker: str,
    end_marker: str,
    label: str,
) -> str:
    start_index, end_index = marker_pair_indexes(
        current,
        start_marker,
        end_marker,
        label,
    )
    if start_index == -1:
        return current
    replace_end = end_index + len(end_marker)
    if replace_end < len(current) and current[replace_end] == "\n":
        replace_end += 1
    return current[:start_index] + current[replace_end:]


def backup_existing_file(
    target: Path,
    destination: Path,
    *,
    backup: bool,
    dry_run: bool,
) -> Path | None:
    if not backup or dry_run:
        return None
    backup_path = next_backup_path(target, destination)
    try:
        shutil.copyfile(destination, backup_path)
    except OSError as error:
        raise SystemExit(
            f"error: cannot create backup for {display_path(target, destination)}: "
            f"{display_path(target, backup_path)} ({error})"
        ) from None
    return backup_path


def unlink_target_file(target: Path, destination: Path) -> None:
    try:
        destination.unlink()
    except OSError as error:
        raise SystemExit(
            f"error: cannot remove {display_path(target, destination)}: {error}"
        ) from None


def prune_empty_parent_dirs(target: Path, destination: Path) -> None:
    current = destination.parent
    while current != target and current != current.parent:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def read_bytes_for_remove(path: Path, label: str) -> tuple[bytes | None, str | None]:
    try:
        return path.read_bytes(), None
    except OSError as error:
        return None, f"{label} cannot be read: {error}"


def sha256_file(path: Path) -> tuple[str | None, str | None]:
    content, detail = read_bytes_for_remove(path, "target")
    if detail is not None:
        return None, detail
    assert content is not None
    return "sha256:" + hashlib.sha256(content).hexdigest(), None


def remove_text_block_file(
    target: Path,
    relative_path: Path,
    *,
    start_marker: str,
    end_marker: str,
    label: str,
    dry_run: bool,
    backup: bool,
    preserve_invalid_utf8: bool = False,
) -> RemoveResult:
    try:
        destination = removal_target_destination(target, relative_path)
    except SystemExit as error:
        return RemoveResult(
            relative_path,
            RemoveStatus.PRESERVED,
            detail=system_exit_detail(error),
        )
    if not path_is_occupied(destination):
        return RemoveResult(relative_path, RemoveStatus.MISSING)
    if destination.is_symlink() or not destination.is_file():
        return RemoveResult(
            relative_path,
            RemoveStatus.PRESERVED,
            detail="target is not a regular file",
        )

    if preserve_invalid_utf8:
        content, detail = read_bytes_for_remove(destination, "target")
        if detail is not None:
            return RemoveResult(relative_path, RemoveStatus.PRESERVED, detail=detail)
        assert content is not None
        current = content.decode(
            "utf-8",
            errors="surrogateescape",
        )
    else:
        try:
            current = read_text_strict(destination, str(relative_path))
        except SystemExit as error:
            return RemoveResult(
                relative_path,
                RemoveStatus.PRESERVED,
                detail=system_exit_detail(error),
            )
    try:
        stripped = remove_marked_block(
            current,
            start_marker=start_marker,
            end_marker=end_marker,
            label=label,
        )
    except SystemExit as error:
        return RemoveResult(
            relative_path,
            RemoveStatus.PRESERVED,
            detail=system_exit_detail(error),
        )
    if stripped == current:
        return RemoveResult(
            relative_path,
            RemoveStatus.UNCHANGED,
            detail="managed block not present",
        )

    status = RemoveStatus.REMOVED if not stripped.strip() else RemoveStatus.UPDATED
    if dry_run:
        return RemoveResult(
            relative_path,
            (
                RemoveStatus.WOULD_REMOVE
                if status is RemoveStatus.REMOVED
                else RemoveStatus.WOULD_UPDATE
            ),
        )

    backup_path = backup_existing_file(
        target,
        destination,
        backup=backup,
        dry_run=dry_run,
    )
    if status is RemoveStatus.REMOVED:
        unlink_target_file(target, destination)
        prune_empty_parent_dirs(target, destination)
    elif preserve_invalid_utf8:
        atomic_write_text_preserving_invalid_utf8(destination, stripped)
    else:
        atomic_write_text(destination, stripped)
    return RemoveResult(relative_path, status, backup_path)




@dataclass(frozen=True)
class RemoveResult:
    target: Path
    status: RemoveStatus
    backup: Path | None = None
    detail: str | None = None


def run_diff_check(target: Path, paths: list[Path] | None = None) -> int:
    if paths == []:
        return 0

    try:
        work_tree_probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=target,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        print("warning: git not found; skipped git diff --check")
        return 0
    except subprocess.TimeoutExpired:
        print(
            "warning: git rev-parse timed out while checking target repo; "
            "skipped whitespace validation"
        )
        return 0
    if work_tree_probe.returncode != 0 or work_tree_probe.stdout.strip() != "true":
        # The Trellis target is not a git work tree (e.g. a tarball
        # export); skip the whitespace validation instead of surfacing
        # git's own exit code as the installer's. Real git failures inside
        # a work tree still propagate below.
        print(
            "warning: git diff --check could not run in this target "
            "(not a git work tree); skipped whitespace validation"
        )
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
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(f"error: git diff --check timed out after {GIT_TIMEOUT_SECONDS}s")
        return 1

    if result.stdout:
        print(result.stdout.rstrip())
    return result.returncode


def display_path(target: Path, path: Path) -> Path:
    try:
        return path.relative_to(target)
    except ValueError:
        return path


__all__ = [
    "CONFLICT_STATUSES",
    "InstallResult",
    "InstallStatus",
    "RemoveResult",
    "RemoveStatus",
    "VOUCHABLE_STATUSES",
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_write_text_preserving_invalid_utf8",
    "backup_existing_file",
    "default_file_mode",
    "display_path",
    "generated_text_file_status",
    "has_active_trellis_platform",
    "install_file",
    "install_managed_block",
    "install_trellis_gitignore",
    "marker_pair_indexes",
    "merge_managed_block",
    "merge_trellis_gitignore_block",
    "next_backup_path",
    "normalize_managed_block_template",
    "path_is_occupied",
    "prune_empty_parent_dirs",
    "read_bytes_for_remove",
    "remove_marked_block",
    "remove_text_block_file",
    "remove_unmanaged_trellis_blanket_entries",
    "run_diff_check",
    "selected_files",
    "sha256_file",
    "source_is_executable",
    "trellis_gitignore_block",
    "unlink_target_file",
]
