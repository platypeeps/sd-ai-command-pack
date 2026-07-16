"""Pack removal: vouch-gated deletion, managed-block and retired-target cleanup."""

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
from installer.status import WRITTEN_REMOVE_STATUSES, RemoveStatus

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

# sd-review-local-all was retired in 0.13.0: its full-codebase loop moved
# into `sd-review-local all`. These are the installed target paths the last
# manifest that shipped the command listed for it; a normal install/refresh
# deletes vouched leftovers (retire_stale_targets) so consumer repos do not
# fail the install audit on orphaned pack-like files.
RETIRED_TARGETS: tuple[str, ...] = (
    ".agents/skills/sd-review-local-all/SKILL.md",
    ".claude/commands/sd/review-local-all.md",
    ".cursor/commands/sd-review-local-all.md",
    ".gemini/commands/sd/review-local-all.toml",
    ".github/prompts/sd-review-local-all.prompt.md",
    ".opencode/commands/sd-review-local-all.md",
    ".agent/workflows/sd-review-local-all.md",
    ".codebuddy/commands/sd/review-local-all.md",
    ".devin/workflows/sd-review-local-all.md",
    ".factory/commands/sd/review-local-all.md",
    ".kilocode/workflows/sd-review-local-all.md",
    ".pi/prompts/sd-review-local-all.md",
    ".qoder/commands/sd-review-local-all.md",
    ".trae/commands/sd-review-local-all.md",
    ".zcode/commands/sd/review-local-all.md",
    ".agent/skills/sd-review-local-all/SKILL.md",
    ".codebuddy/skills/sd-review-local-all/SKILL.md",
    ".devin/skills/sd-review-local-all/SKILL.md",
    ".factory/skills/sd-review-local-all/SKILL.md",
    ".kilocode/skills/sd-review-local-all/SKILL.md",
    ".kiro/skills/sd-review-local-all/SKILL.md",
    ".pi/skills/sd-review-local-all/SKILL.md",
    ".qoder/skills/sd-review-local-all/SKILL.md",
    ".reasonix/skills/sd-review-local-all/SKILL.md",
    ".trae/skills/sd-review-local-all/SKILL.md",
)

# remove_pack_file statuses renamed so the install summary reads as
# retirement, not pack removal ("missing" is excluded on purpose: absent
# retired targets are skipped without a result).
_RETIRED_STATUSES = {
    RemoveStatus.REMOVED: RemoveStatus.RETIRED,
    RemoveStatus.PRESERVED: RemoveStatus.RETIRED_PRESERVED,
    RemoveStatus.WOULD_REMOVE: RemoveStatus.WOULD_RETIRE,
}


def normalize_removal_candidate(candidate: str) -> str:
    normalized = candidate.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_git_internal_candidate(candidate: str) -> bool:
    return candidate == ".git" or candidate.startswith(".git/")


def recognized_removal_targets(files: list[PackFile]) -> set[str]:
    # Retired targets stay recognized so a full --remove on a consumer whose
    # receipts still list them deletes the leftovers instead of reporting
    # them as unrecognized.
    return {
        *(file.target.as_posix() for file in files),
        *GENERATED_REMOVAL_TARGETS,
        *MANAGED_BLOCK_REMOVAL_TARGETS,
        *RETIRED_TARGETS,
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
            RemoveStatus.PRESERVED,
            detail=system_exit_detail(error),
        )
    if not path_is_occupied(destination):
        return RemoveResult(relative_path, RemoveStatus.MISSING)
    if destination.is_symlink():
        if not force:
            return RemoveResult(
                relative_path,
                RemoveStatus.PRESERVED,
                detail="target is a symlink",
            )
    elif not destination.is_file():
        return RemoveResult(
            relative_path,
            RemoveStatus.PRESERVED,
            detail="target is not a regular file",
        )

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
        return RemoveResult(relative_path, RemoveStatus.PRESERVED, detail=detail)
    if dry_run:
        return RemoveResult(relative_path, RemoveStatus.WOULD_REMOVE)

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
    return RemoveResult(relative_path, RemoveStatus.REMOVED, backup_path)


def retire_stale_targets(
    target: Path,
    *,
    force: bool,
    dry_run: bool,
    backup: bool,
) -> list[RemoveResult]:
    """Delete retired-command leftovers during a normal install/refresh.

    Must run before the receipt files are rewritten: vouching reads the
    prior install's provenance records, and the provenance rewrite drops
    retired entries (their targets left the manifest). Semantics mirror the
    removal flow's per-file handling: hash-vouched files are deleted with
    empty parent dirs pruned, drifted or unvouched files are preserved and
    reported unless ``force`` (which honors ``backup``), and absent targets
    produce no result.
    """
    provenance_files = {
        normalize_removal_candidate(path): digest
        for path, digest in read_existing_provenance_files_for_remove(target).items()
    }
    results: list[RemoveResult] = []
    for candidate in RETIRED_TARGETS:
        result = remove_pack_file(
            target,
            Path(candidate),
            file=None,
            recorded_hash=provenance_files.get(candidate),
            force=force,
            dry_run=dry_run,
            backup=backup,
        )
        if result.status is RemoveStatus.MISSING:
            continue
        results.append(
            RemoveResult(
                result.target,
                _RETIRED_STATUSES[result.status],
                backup=result.backup,
                detail=result.detail,
            )
        )
    return results


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
    """Run the remove entry point: strip managed blocks, delete vouched pack
    files (honoring force/dry-run/backup), drop the local-only exclude, then
    report per-file results and return the diff-check exit code."""
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
            results.append(
                RemoveResult(Path(candidate), RemoveStatus.IGNORED, detail=rejection)
            )
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
        if result.status in WRITTEN_REMOVE_STATUSES
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
    "RETIRED_TARGETS",
    "installed_target_candidates",
    "is_git_internal_candidate",
    "may_remove_pack_file",
    "normalize_removal_candidate",
    "recognized_removal_targets",
    "removal_candidate_rejection",
    "remove_installed_pack",
    "remove_pack_file",
    "RemoveStatus",
    "retire_stale_targets",
]
