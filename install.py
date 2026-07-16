#!/usr/bin/env python3
"""Install the SD AI command pack into a Trellis repo."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from installer import (
    fileops,
    localonly,
    manifest,
    provenance,
    registry,
    removal,
)
from installer.fileops import (
    CONFLICT_STATUSES,
    VOUCHABLE_STATUSES,
    InstallResult,
    RemoveResult,
    atomic_write_bytes,
    atomic_write_text,
    atomic_write_text_preserving_invalid_utf8,
    backup_existing_file,
    default_file_mode,
    display_path,
    has_active_trellis_platform,
    install_file,
    install_managed_block,
    install_trellis_gitignore,
    marker_pair_indexes,
    merge_managed_block,
    merge_trellis_gitignore_block,
    next_backup_path,
    normalize_managed_block_template,
    path_is_occupied,
    prune_empty_parent_dirs,
    read_bytes_for_remove,
    remove_marked_block,
    remove_text_block_file,
    remove_unmanaged_trellis_blanket_entries,
    run_diff_check,
    selected_files,
    sha256_file,
    source_is_executable,
    trellis_gitignore_block,
    unlink_target_file,
)
from installer.localonly import (
    LocalOnlyResult,
    ensure_local_only_exclude,
    ensure_trellis_for_local_only,
    git_info_exclude_path,
    git_output,
    local_only_exclude_block,
    local_only_exclude_patterns,
    local_only_pack_excludes,
    local_only_tracked_check_specs,
    merge_local_only_exclude_block,
    optional_git_info_exclude_path,
    reject_tracked_local_only_paths,
    remove_local_only_exclude,
    require_git_repo_for_local_only,
    tracked_paths,
    trellis_init_command,
    trellis_init_platforms,
    write_local_only_marker,
)
from installer.manifest import (
    KNOWN_MANIFEST_KINDS,
    MANIFEST_PATH,
    SUPPORTED_MANIFEST_SCHEMA_VERSION,
    PackFile,
    load_manifest,
    manifest_cli_identity,
    read_text_if_exists,
    read_text_strict,
    removal_target_destination,
    require_target_directory,
    require_trellis_repo,
    system_exit_detail,
    target_destination,
    validate_manifest,
    validate_pack_source,
    validate_relative_manifest_path,
    validate_resolved_target_path,
)
from installer.provenance import (
    PROVENANCE_EXCLUDED_KINDS,
    install_installed_targets_file,
    install_pack_manifest_file,
    install_provenance_file,
    installed_pack_manifest_content,
    installed_targets_content,
    installed_targets_set,
    is_gitignored_path,
    never_vouched_targets,
    preserved_receipt_targets,
    provenance_content,
    read_existing_installed_targets,
    read_existing_installed_targets_for_remove,
    read_existing_provenance_files,
    read_existing_provenance_files_for_remove,
)
from installer.registry import (
    _LOCAL_GITIGNORE_GROUP_ORDER,
    _LOCAL_ONLY_GROUP_ORDER,
    ACTIVE_TRELLIS_PLATFORM_MARKERS,
    ALWAYS_INSTALL,
    COPILOT_GUIDANCE_END,
    COPILOT_GUIDANCE_START,
    COPILOT_INSTRUCTIONS_TARGET,
    FORCE_PRESERVED_TARGETS,
    IF_NOT_EXISTS,
    INSTALLED_TARGETS_FILE,
    LOCAL_ENV_GITIGNORE_PATTERNS,
    LOCAL_ONLY_EXCLUDE_END,
    LOCAL_ONLY_EXCLUDE_START,
    LOCAL_ONLY_MARKER_FILE,
    LOCAL_ONLY_TRACKED_CHECK_PATHS,
    LOCAL_ONLY_TRELLIS_EXCLUDES,
    MANAGED_BLOCK_KIND,
    NEUTRAL_COMMAND_SOURCE_PLATFORMS,
    PACK_LOCAL_GITIGNORE_GROUP,
    PACK_MANIFEST_FILE,
    PLATFORM_LOCAL_GITIGNORE_PATTERNS,
    PLATFORM_REGISTRY,
    PLATFORMS,
    PROVENANCE_FILE,
    REVIEW_ARTIFACT_GITIGNORE_PATTERNS,
    ROOT,
    TRELLIS_BLANKET_GITIGNORE_ENTRIES,
    TRELLIS_GITIGNORE_END,
    TRELLIS_GITIGNORE_PATTERNS,
    TRELLIS_GITIGNORE_START,
    TRELLIS_GITIGNORE_TARGET,
    TRELLIS_INIT_PLATFORM_FLAGS,
    TRELLIS_INSTALL_DOCS_URL,
)
from installer.removal import (
    GENERATED_REMOVAL_TARGETS,
    MANAGED_BLOCK_REMOVAL_TARGETS,
    RETIRED_TARGETS,
    installed_target_candidates,
    is_git_internal_candidate,
    may_remove_pack_file,
    normalize_removal_candidate,
    recognized_removal_targets,
    removal_candidate_rejection,
    remove_installed_pack,
    remove_pack_file,
    retire_stale_targets,
)

__all__ = [
    "ACTIVE_TRELLIS_PLATFORM_MARKERS",
    "ALWAYS_INSTALL",
    "CONFLICT_STATUSES",
    "COPILOT_GUIDANCE_END",
    "COPILOT_GUIDANCE_START",
    "COPILOT_INSTRUCTIONS_TARGET",
    "FORCE_PRESERVED_TARGETS",
    "GENERATED_REMOVAL_TARGETS",
    "IF_NOT_EXISTS",
    "INSTALLED_TARGETS_FILE",
    "InstallResult",
    "KNOWN_MANIFEST_KINDS",
    "LOCAL_ENV_GITIGNORE_PATTERNS",
    "LOCAL_ONLY_EXCLUDE_END",
    "LOCAL_ONLY_EXCLUDE_START",
    "LOCAL_ONLY_MARKER_FILE",
    "LOCAL_ONLY_TRACKED_CHECK_PATHS",
    "LOCAL_ONLY_TRELLIS_EXCLUDES",
    "LocalOnlyResult",
    "MANAGED_BLOCK_KIND",
    "MANAGED_BLOCK_REMOVAL_TARGETS",
    "MANIFEST_PATH",
    "ManifestVersionAction",
    "NEUTRAL_COMMAND_SOURCE_PLATFORMS",
    "PACK_LOCAL_GITIGNORE_GROUP",
    "PACK_MANIFEST_FILE",
    "PLATFORM_LOCAL_GITIGNORE_PATTERNS",
    "PLATFORM_REGISTRY",
    "PLATFORMS",
    "PROVENANCE_EXCLUDED_KINDS",
    "PROVENANCE_FILE",
    "PackFile",
    "RETIRED_TARGETS",
    "REVIEW_ARTIFACT_GITIGNORE_PATTERNS",
    "ROOT",
    "RemoveResult",
    "SUPPORTED_MANIFEST_SCHEMA_VERSION",
    "TRELLIS_BLANKET_GITIGNORE_ENTRIES",
    "TRELLIS_GITIGNORE_END",
    "TRELLIS_GITIGNORE_PATTERNS",
    "TRELLIS_GITIGNORE_START",
    "TRELLIS_GITIGNORE_TARGET",
    "TRELLIS_INIT_PLATFORM_FLAGS",
    "TRELLIS_INSTALL_DOCS_URL",
    "VOUCHABLE_STATUSES",
    "_LOCAL_GITIGNORE_GROUP_ORDER",
    "_LOCAL_ONLY_GROUP_ORDER",
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_write_text_preserving_invalid_utf8",
    "backup_existing_file",
    "default_file_mode",
    "display_path",
    "ensure_local_only_exclude",
    "ensure_trellis_for_local_only",
    "fileops",
    "git_info_exclude_path",
    "git_output",
    "has_active_trellis_platform",
    "install_file",
    "install_installed_targets_file",
    "install_managed_block",
    "install_pack_manifest_file",
    "install_provenance_file",
    "install_trellis_gitignore",
    "installed_pack_manifest_content",
    "installed_target_candidates",
    "installed_targets_content",
    "installed_targets_set",
    "is_git_internal_candidate",
    "is_gitignored_path",
    "load_manifest",
    "local_only_exclude_block",
    "local_only_exclude_patterns",
    "local_only_pack_excludes",
    "local_only_tracked_check_specs",
    "localonly",
    "main",
    "manifest",
    "manifest_cli_identity",
    "marker_pair_indexes",
    "may_remove_pack_file",
    "merge_local_only_exclude_block",
    "merge_managed_block",
    "merge_trellis_gitignore_block",
    "never_vouched_targets",
    "next_backup_path",
    "normalize_managed_block_template",
    "normalize_removal_candidate",
    "optional_git_info_exclude_path",
    "os",
    "parse_args",
    "path_is_occupied",
    "preserved_receipt_targets",
    "provenance",
    "provenance_content",
    "prune_empty_parent_dirs",
    "read_bytes_for_remove",
    "read_existing_installed_targets",
    "read_existing_installed_targets_for_remove",
    "read_existing_provenance_files",
    "read_existing_provenance_files_for_remove",
    "read_text_if_exists",
    "read_text_strict",
    "recognized_removal_targets",
    "registry",
    "reject_tracked_local_only_paths",
    "removal",
    "removal_candidate_rejection",
    "removal_target_destination",
    "remove_installed_pack",
    "remove_local_only_exclude",
    "remove_marked_block",
    "remove_pack_file",
    "remove_text_block_file",
    "remove_unmanaged_trellis_blanket_entries",
    "require_git_repo_for_local_only",
    "require_target_directory",
    "require_trellis_repo",
    "retire_stale_targets",
    "run_diff_check",
    "selected_files",
    "sha256_file",
    "shutil",
    "source_is_executable",
    "system_exit_detail",
    "target_destination",
    "tracked_paths",
    "trellis_gitignore_block",
    "trellis_init_command",
    "trellis_init_platforms",
    "unlink_target_file",
    "validate_manifest",
    "validate_pack_source",
    "validate_relative_manifest_path",
    "validate_resolved_target_path",
    "write_local_only_marker",
]

class ManifestVersionAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        print(manifest_cli_identity())
        parser.exit()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install SD AI command pack shared assets and command adapters."
    )
    parser.add_argument(
        "--version",
        action=ManifestVersionAction,
        help="Print the sd-ai-command-pack version and exit.",
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
        "--remove",
        action="store_true",
        help=(
            "Remove this pack from the target repo. By default this deletes "
            "vouched or template-identical pack files and removes managed "
            "blocks while preserving drifted or user-owned files; add --force "
            "to delete drifted regular pack files too."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite existing files that differ from the pack templates "
            "(except .prism/rules.json, .gito/config.toml, and "
            ".github/PULL_REQUEST_TEMPLATE.md). Add --backup to save .bak "
            "copies before overwriting."
        ),
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help=(
            "With --force or --remove, save a .bak copy next to each "
            "overwritten or deleted file before changing it."
        ),
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help=(
            "Set up Trellis and this pack for only the current checkout. "
            "When Trellis is missing, run `trellis init --yes --skip-existing` "
            "with the requested platform flags (Codex by default), then add "
            "generated Trellis and pack paths to "
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


def _install_payload(
    selected: list[PackFile],
    target: Path,
    *,
    local_only: bool,
    force: bool,
    dry_run: bool,
    backup: bool,
) -> tuple[list[InstallResult], list[Path]]:
    results: list[InstallResult] = []
    generated_targets: list[Path] = []
    if not local_only:
        results.append(install_trellis_gitignore(target, dry_run=dry_run))
        generated_targets.append(TRELLIS_GITIGNORE_TARGET)

    for file in selected:
        if file.kind == MANAGED_BLOCK_KIND:
            result = install_managed_block(file, target, dry_run=dry_run)
        else:
            result = install_file(
                file,
                target,
                force=force,
                dry_run=dry_run,
                backup=backup,
            )
        results.append(result)

    return results, generated_targets


def _conflict_results(results: list[InstallResult]) -> list[InstallResult]:
    return [result for result in results if result.status in CONFLICT_STATUSES]


def _print_conflicts(conflicts: list[InstallResult]) -> None:
    print("")
    print("Conflicts:")
    for result in conflicts:
        if result.status == "symlink-conflict":
            print(
                f"- {result.file.target} "
                "(target is a symlink; the pack installs regular files only)"
            )
        else:
            print(f"- {result.file.target}")
    print("Re-run with --force to overwrite these files.")


def _install_receipt_files(
    manifest_data: dict,
    files: list[PackFile],
    target: Path,
    *,
    selected: list[PackFile],
    skipped: list[tuple[PackFile, str]],
    results: list[InstallResult],
    generated_targets: list[Path],
    dry_run: bool,
) -> list[tuple[Path, str]]:
    """Write the pack-manifest, provenance, and installed-targets receipts.

    Appends each receipt's result to ``results`` in order (provenance vouches
    for the results collected so far, so the ordering is load-bearing) and
    returns the receipt entries preserved for platforms skipped only in this
    checkout.
    """
    results.append(
        install_pack_manifest_file(
            manifest_data,
            target,
            dry_run=dry_run,
        )
    )
    generated_targets.append(PACK_MANIFEST_FILE)

    kept_receipt_targets = preserved_receipt_targets(
        target, read_existing_installed_targets(target), skipped
    )
    receipt_extra_targets = [
        *generated_targets,
        PROVENANCE_FILE,
        *(kept_target for kept_target, _ in kept_receipt_targets),
    ]
    receipt_target_set = installed_targets_set(selected, receipt_extra_targets)
    results.append(
        install_provenance_file(
            manifest_data,
            results,
            target,
            receipt_targets=receipt_target_set,
            never_vouched=never_vouched_targets(files),
            dry_run=dry_run,
        )
    )
    results.append(
        install_installed_targets_file(
            selected,
            target,
            dry_run=dry_run,
            extra_targets=receipt_extra_targets,
        )
    )
    return kept_receipt_targets


def _print_install_summary(
    target: Path,
    *,
    results: list[InstallResult],
    retired_results: list[RemoveResult],
    local_only_results: list[LocalOnlyResult],
    local_only_results_printed: int,
    skipped: list[tuple[PackFile, str]],
    files: list[PackFile],
    platforms_requested: list[str] | None,
    kept_receipt_targets: list[tuple[Path, str]],
) -> None:
    """Print install, retired, local-only results, skips, hints, and notes."""
    for result in results:
        print(f"{result.status:11} {result.file.target}")
        if result.backup:
            print(f"{'backup':11} {result.backup.relative_to(target)}")
    for retired in retired_results:
        suffix = f" ({retired.detail})" if retired.detail else ""
        print(f"{retired.status:17} {display_path(target, retired.target)}{suffix}")
        if retired.backup:
            print(f"{'backup':17} {display_path(target, retired.backup)}")
    for result in local_only_results[local_only_results_printed:]:
        suffix = f" ({result.detail})" if result.detail else ""
        print(f"{result.status:29} {display_path(target, result.target)}{suffix}")
    for file, reason in skipped:
        print(f"skipped     {file.target} ({reason})")
    marker_missed_platforms = sorted(
        {
            file.platform
            for file, reason in skipped
            if reason.endswith("install not detected")
        }
    )
    for platform in marker_missed_platforms:
        directory = PLATFORM_REGISTRY[platform].directory
        print(
            f"hint: {directory}/ exists but no active Trellis {platform} "
            f"install was detected; pass --platform {platform} or update "
            "Trellis if that platform should be active here"
        )
    for platform in sorted(set(platforms_requested or [])):
        if not any(file.platform == platform for file in files):
            print(
                f"note: platform {platform} has no dedicated manifest files; "
                "its commands are provided by the shared .agents skills"
            )
    for kept_target, kept_platform in kept_receipt_targets:
        print(
            f"kept-in-receipt {kept_target} "
            f"({kept_platform} adapter not selected in this checkout; "
            "file may be local-only)"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.backup and not args.force and not args.remove:
        raise SystemExit("error: --backup requires --force unless --remove is set")
    if args.skip_trellis_init and not args.local_only:
        raise SystemExit("error: --skip-trellis-init requires --local-only")

    target = Path(args.target).resolve()
    manifest_data, files = load_manifest()

    validate_manifest(files)
    if args.remove:
        return remove_installed_pack(
            manifest_data,
            files,
            target,
            platforms=args.platform,
            install_all=args.all,
            force=args.force,
            dry_run=args.dry_run,
            backup=args.backup,
            skip_diff_check=args.skip_diff_check,
        )

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
        if manifest_data.get("requiresTrellis", True):
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

    print(f"{manifest_data['name']} {manifest_data['version']}")
    print(f"target: {target}")
    if args.dry_run:
        print("mode: dry-run")
    if args.local_only:
        print("mode: local-only")
    local_only_results_printed = len(local_only_results)
    for result in local_only_results:
        suffix = f" ({result.detail})" if result.detail else ""
        print(f"{result.status:29} {display_path(target, result.target)}{suffix}")

    # A normal refresh is plan-before-apply: detect every selected-file
    # conflict before the first pack-owned write. Local-only Trellis bootstrap
    # remains outside this boundary because it invokes an external installer.
    if not args.local_only and not args.force and not args.dry_run:
        preflight_results, _ = _install_payload(
            selected,
            target,
            local_only=False,
            force=False,
            dry_run=True,
            backup=False,
        )
        preflight_conflicts = _conflict_results(preflight_results)
        if preflight_conflicts:
            for result in preflight_conflicts:
                print(f"{result.status:11} {result.file.target}")
            _print_conflicts(preflight_conflicts)
            return 2

    results, generated_targets = _install_payload(
        selected,
        target,
        local_only=args.local_only,
        force=args.force,
        dry_run=args.dry_run,
        backup=args.backup,
    )

    # Retired-target cleanup must run before the receipt files are rewritten:
    # it vouches stale files against the prior install's provenance, and the
    # provenance rewrite below drops retired entries (they left the manifest,
    # so receipts never list them again).
    retired_results = retire_stale_targets(
        target,
        force=args.force,
        dry_run=args.dry_run,
        backup=args.backup,
    )

    kept_receipt_targets = _install_receipt_files(
        manifest_data,
        files,
        target,
        selected=selected,
        skipped=skipped,
        results=results,
        generated_targets=generated_targets,
        dry_run=args.dry_run,
    )
    if args.local_only:
        local_only_results.append(
            write_local_only_marker(target, dry_run=args.dry_run)
        )

    _print_install_summary(
        target,
        results=results,
        retired_results=retired_results,
        local_only_results=local_only_results,
        local_only_results_printed=local_only_results_printed,
        skipped=skipped,
        files=files,
        platforms_requested=args.platform,
        kept_receipt_targets=kept_receipt_targets,
    )

    conflict_results = _conflict_results(results)
    if conflict_results:
        _print_conflicts(conflict_results)
        return 2

    if not args.dry_run and not args.skip_diff_check:
        # Skip diff-checking any target this run did not write: conflicts and
        # preserved files are left byte-for-byte untouched.
        unwritten_statuses = CONFLICT_STATUSES | {"preserved"}
        diff_paths = [
            result.file.target
            for result in results
            if result.status not in unwritten_statuses
        ]
        diff_status = run_diff_check(target, diff_paths)
        if diff_status != 0:
            return diff_status

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
