"""Part of the sd-ai-command-pack installer package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from installer.registry import *  # noqa: F401,F403
from installer.manifest import *  # noqa: F401,F403
from installer.fileops import *  # noqa: F401,F403
from installer.provenance import *  # noqa: F401,F403
from installer.localonly import *  # noqa: F401,F403

def installed_target_candidates(
    files: list[PackFile],
    target: Path,
    *,
    platforms: list[str] | None,
    install_all: bool,
) -> set[str]:
    receipt_targets = read_existing_installed_targets_for_remove(target)
    provenance_targets = set(read_existing_provenance_files_for_remove(target).keys())
    if receipt_targets or provenance_targets:
        candidates = {*receipt_targets, *provenance_targets}
    else:
        selected, _ = selected_files(files, target, platforms, install_all)
        candidates = {file.target.as_posix() for file in selected}

    candidates.update(
        {
            INSTALLED_TARGETS_FILE.as_posix(),
            PROVENANCE_FILE.as_posix(),
            LOCAL_ONLY_MARKER_FILE.as_posix(),
            TRELLIS_GITIGNORE_TARGET.as_posix(),
            COPILOT_INSTRUCTIONS_TARGET.as_posix(),
        }
    )
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
    provenance_files = read_existing_provenance_files_for_remove(target)

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

    block_targets = {
        TRELLIS_GITIGNORE_TARGET.as_posix(),
        COPILOT_INSTRUCTIONS_TARGET.as_posix(),
    }
    for candidate in sorted(
        installed_target_candidates(
            files,
            target,
            platforms=platforms,
            install_all=install_all,
        )
        - block_targets
    ):
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
