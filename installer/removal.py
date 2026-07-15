"""Part of the sd-ai-command-pack installer package."""

from __future__ import annotations

from pathlib import Path

from installer.fileops import (
    RemoveResult,
    backup_existing_file,
    display_path,
    path_is_occupied,
    prune_empty_parent_dirs,
    read_bytes_for_remove,
    remove_text_block_file,
    run_diff_check,
    selected_files,
    sha256_file,
    unlink_target_file,
)
from installer.localonly import remove_local_only_exclude
from installer.manifest import (
    PackFile,
    removal_target_destination,
    require_target_directory,
    system_exit_detail,
)
from installer.provenance import (
    read_existing_installed_targets_for_remove,
    read_existing_provenance_files_for_remove,
)
from installer.registry import (
    COPILOT_GUIDANCE_END,
    COPILOT_GUIDANCE_START,
    COPILOT_INSTRUCTIONS_TARGET,
    INSTALLED_TARGETS_FILE,
    LOCAL_ONLY_MARKER_FILE,
    PACK_MANIFEST_FILE,
    PROVENANCE_FILE,
    TRELLIS_GITIGNORE_END,
    TRELLIS_GITIGNORE_START,
    TRELLIS_GITIGNORE_TARGET,
)

GENERATED_REMOVAL_TARGETS = frozenset(
    {
        INSTALLED_TARGETS_FILE.as_posix(),
        PACK_MANIFEST_FILE.as_posix(),
        PROVENANCE_FILE.as_posix(),
        LOCAL_ONLY_MARKER_FILE.as_posix(),
    }
)
MANAGED_BLOCK_REMOVAL_TARGETS = frozenset(
    {
        TRELLIS_GITIGNORE_TARGET.as_posix(),
        COPILOT_INSTRUCTIONS_TARGET.as_posix(),
    }
)


def normalize_removal_candidate(candidate: str) -> str:
    normalized = candidate.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_git_internal_candidate(candidate: str) -> bool:
    return candidate == ".git" or candidate.startswith(".git/")


def recognized_removal_targets(files: list[PackFile]) -> set[str]:
    return {
        *(file.target.as_posix() for file in files),
        *GENERATED_REMOVAL_TARGETS,
        *MANAGED_BLOCK_REMOVAL_TARGETS,
    }


def removal_candidate_rejection(
    candidate: str,
    recognized_targets: set[str],
) -> str | None:
    if is_git_internal_candidate(candidate):
        return "refusing to remove .git internals"
    if candidate not in recognized_targets:
        return "not a recognized sd-ai-command-pack target"
    return None


def installed_target_candidates(
    files: list[PackFile],
    target: Path,
    *,
    platforms: list[str] | None,
    install_all: bool,
    provenance_files: dict[str, str] | None = None,
) -> set[str]:
    receipt_targets = {
        normalize_removal_candidate(path)
        for path in read_existing_installed_targets_for_remove(target)
    }
    # remove_installed_pack parses provenance.json once and threads the
    # normalized dict in; standalone callers pass nothing and we read it here.
    if provenance_files is None:
        provenance_files = {
            normalize_removal_candidate(path): digest
            for path, digest in read_existing_provenance_files_for_remove(
                target
            ).items()
        }
    provenance_targets = set(provenance_files)
    if receipt_targets or provenance_targets:
        candidates = {*receipt_targets, *provenance_targets}
    else:
        selected, _ = selected_files(files, target, platforms, install_all)
        candidates = {file.target.as_posix() for file in selected}

    candidates.update(GENERATED_REMOVAL_TARGETS)
    candidates.update(MANAGED_BLOCK_REMOVAL_TARGETS)
    return candidates


def may_remove_pack_file(
    destination: Path,
    *,
    file: PackFile | None,
    recorded_hash: str | None,
    force: bool,
) -> tuple[bool, str | None]:
    if force:
        return True, None
    if recorded_hash:
        digest, detail = sha256_file(destination)
        if detail is not None:
            return False, detail
        if recorded_hash == digest:
            return True, None
    if file:
        destination_content, detail = read_bytes_for_remove(destination, "target")
        if detail is not None:
            return False, detail
        source_content, source_detail = read_bytes_for_remove(
            file.source,
            "pack template",
        )
        if source_detail is not None:
            raise SystemExit(f"error: {source_detail}") from None
        if destination_content == source_content:
            return True, None
    return False, "content differs from installed pack version"


def remove_pack_file(
    target: Path,
    relative_path: Path,
    *,
    file: PackFile | None,
    recorded_hash: str | None,
    force: bool,
    dry_run: bool,
    backup: bool,
) -> RemoveResult:
    try:
        destination = removal_target_destination(target, relative_path)
    except SystemExit as error:
        return RemoveResult(
            relative_path,
            "preserved",
            detail=system_exit_detail(error),
        )
    if not path_is_occupied(destination):
        return RemoveResult(relative_path, "missing")
    if destination.is_symlink():
        if not force:
            return RemoveResult(relative_path, "preserved", detail="target is a symlink")
    elif not destination.is_file():
        return RemoveResult(relative_path, "preserved", detail="target is not a regular file")

    generated_state = relative_path in {
        INSTALLED_TARGETS_FILE,
        PACK_MANIFEST_FILE,
        PROVENANCE_FILE,
        LOCAL_ONLY_MARKER_FILE,
    }
    if generated_state and not destination.is_symlink():
        removable = True
        detail = None
    else:
        removable, detail = may_remove_pack_file(
            destination,
            file=file,
            recorded_hash=recorded_hash,
            force=force,
        )
    if not removable:
        return RemoveResult(relative_path, "preserved", detail=detail)
    if dry_run:
        return RemoveResult(relative_path, "would-remove")

    backup_path = None
    if not destination.is_symlink():
        backup_path = backup_existing_file(
            target,
            destination,
            backup=backup,
            dry_run=dry_run,
        )
    unlink_target_file(target, destination)
    prune_empty_parent_dirs(target, destination)
    return RemoveResult(relative_path, "removed", backup_path)


def remove_installed_pack(
    manifest: dict,
    files: list[PackFile],
    target: Path,
    *,
    platforms: list[str] | None,
    install_all: bool,
    force: bool,
    dry_run: bool,
    backup: bool,
    skip_diff_check: bool,
) -> int:
    require_target_directory(target)
    files_by_target = {file.target.as_posix(): file for file in files}
    provenance_files = {
        normalize_removal_candidate(path): digest
        for path, digest in read_existing_provenance_files_for_remove(target).items()
    }
    recognized_targets = recognized_removal_targets(files)

    print(f"{manifest['name']} {manifest['version']}")
    print(f"target: {target}")
    print("mode: remove")
    if dry_run:
        print("mode: dry-run")

    results: list[RemoveResult] = []
    results.append(
        remove_text_block_file(
            target,
            TRELLIS_GITIGNORE_TARGET,
            start_marker=TRELLIS_GITIGNORE_START,
            end_marker=TRELLIS_GITIGNORE_END,
            label=".gitignore",
            dry_run=dry_run,
            backup=backup,
        )
    )
    results.append(
        remove_text_block_file(
            target,
            COPILOT_INSTRUCTIONS_TARGET,
            start_marker=COPILOT_GUIDANCE_START,
            end_marker=COPILOT_GUIDANCE_END,
            label=".github/copilot-instructions.md",
            dry_run=dry_run,
            backup=backup,
            preserve_invalid_utf8=True,
        )
    )

    block_targets = MANAGED_BLOCK_REMOVAL_TARGETS
    for candidate in sorted(
        installed_target_candidates(
            files,
            target,
            platforms=platforms,
            install_all=install_all,
            provenance_files=provenance_files,
        )
        - block_targets
    ):
        rejection = removal_candidate_rejection(candidate, recognized_targets)
        if rejection is not None:
            results.append(RemoveResult(Path(candidate), "ignored", detail=rejection))
            continue
        relative_path = Path(candidate)
        file = files_by_target.get(relative_path.as_posix())
        results.append(
            remove_pack_file(
                target,
                relative_path,
                file=file,
                recorded_hash=provenance_files.get(relative_path.as_posix()),
                force=force,
                dry_run=dry_run,
                backup=backup,
            )
        )

    local_exclude = remove_local_only_exclude(target, dry_run=dry_run)
    if local_exclude is not None:
        results.append(local_exclude)

    for result in results:
        suffix = f" ({result.detail})" if result.detail else ""
        print(f"{result.status:14} {display_path(target, result.target)}{suffix}")
        if result.backup:
            print(f"{'backup':14} {display_path(target, result.backup)}")

    changed_paths = [
        result.target
        for result in results
        if result.status in {"removed", "updated"}
        and not result.target.is_absolute()
    ]
    if not dry_run and not skip_diff_check:
        diff_status = run_diff_check(target, changed_paths)
        if diff_status != 0:
            return diff_status
    return 0


__all__ = [
    "GENERATED_REMOVAL_TARGETS",
    "MANAGED_BLOCK_REMOVAL_TARGETS",
    "installed_target_candidates",
    "is_git_internal_candidate",
    "may_remove_pack_file",
    "normalize_removal_candidate",
    "recognized_removal_targets",
    "removal_candidate_rejection",
    "remove_installed_pack",
    "remove_pack_file",
]
