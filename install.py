#!/usr/bin/env python3
"""Install the SD AI command pack into a Trellis repo."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from installer import (
    conversion,
    fileops,
    inspection,
    localonly,
    machinescope,
    machinestage,
    manifest,
    removal,
    thin,
)
from installer.fileops import (
    CONFLICT_STATUSES,
    InstallResult,
    InstallStatus,
    RemoveResult,
    RemoveStatus,
    atomic_write_bytes,
    display_path,
    generated_text_file_status,
    install_file,
    install_managed_block,
    install_trellis_gitignore,
    merge_managed_block,
    merge_trellis_gitignore_block,
    next_backup_path,
    normalize_managed_block_template,
    payload_source_bytes,
    remove_marked_block,
    remove_text_block_file,
    remove_unmanaged_trellis_blanket_entries,
    run_diff_check,
    selected_files,
)
from installer.localonly import (
    LocalOnlyResult,
    LocalOnlyStatus,
    ensure_local_only_exclude,
    ensure_trellis_for_local_only,
    git_info_exclude_path,
    git_output,
    local_only_exclude_block,
    merge_local_only_exclude_block,
    reject_tracked_local_only_paths,
    remove_local_only_exclude,
    require_git_repo_for_local_only,
    tracked_paths,
    trellis_init_platforms,
    write_local_only_marker,
)
from installer.manifest import (
    PackFile,
    load_manifest,
    manifest_cli_identity,
    read_text_if_exists,
    read_text_strict,
    require_target_directory,
    require_trellis_repo,
    system_exit_detail,
    validate_manifest,
    validate_pack_source,
    validate_resolved_target_path,
)
from installer.provenance import (
    install_installed_targets_file,
    install_pack_manifest_file,
    install_provenance_file,
    installed_targets_content,
    installed_targets_set,
    never_vouched_targets,
    preserved_receipt_targets,
    read_existing_installed_targets,
    read_existing_provenance_files,
    read_existing_provenance_pin,
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
    IF_ANCHOR_EXISTS,
    IF_NOT_EXISTS,
    INSTALLED_TARGETS_FILE,
    KNOWN_INSTALL_MODES,
    LOCAL_ENV_GITIGNORE_PATTERNS,
    LOCAL_ONLY_EXCLUDE_END,
    LOCAL_ONLY_EXCLUDE_START,
    LOCAL_ONLY_MARKER_FILE,
    LOCAL_ONLY_TRACKED_CHECK_PATHS,
    MANAGED_BLOCK_KIND,
    NEUTRAL_COMMAND_SOURCE_PLATFORMS,
    PACK_MANIFEST_FILE,
    PLATFORM_LOCAL_GITIGNORE_PATTERNS,
    PLATFORM_REGISTRY,
    PLATFORMS,
    PROVENANCE_FILE,
    REVIEW_ARTIFACT_GITIGNORE_PATTERNS,
    ROOT,
    SOURCE_ONLY_COMMAND_NAMES,
    SOURCE_ONLY_SKILL_REFERENCES,
    TRELLIS_GITIGNORE_END,
    TRELLIS_GITIGNORE_PATTERNS,
    TRELLIS_GITIGNORE_START,
    TRELLIS_GITIGNORE_TARGET,
    TRELLIS_INIT_PLATFORM_FLAGS,
    TRELLIS_INSTALL_DOCS_URL,
    _ordered_platform_groups_with_local_gitignore,
    _ordered_platform_groups_with_local_only,
    _validate_registry_group_order,
    _validate_registry_group_orders,
    validate_source_only_command_names,
)
from installer.removal import (
    MANAGED_BLOCK_REMOVAL_TARGETS,
    RETIRED_FULL_CHECK_TARGETS,
    RETIRED_REVIEW_LOCAL_ALL_TARGETS,
    RETIRED_REVIEW_LOCAL_TARGETS,
    RETIRED_TARGETS,
    RETIRED_WATCH_PR_TARGETS,
    RETIRED_WORK_DESIGNS_TARGETS,
    SOURCE_ONLY_COMMAND_TARGETS,
    installed_target_candidates,
    may_remove_pack_file,
    remove_installed_pack,
    remove_pack_file,
    retire_stale_targets,
)
from installer.status import WRITTEN_REMOVE_STATUSES

__all__ = [
    "ACTIVE_TRELLIS_PLATFORM_MARKERS",
    "ALWAYS_INSTALL",
    "CONFLICT_STATUSES",
    "COPILOT_GUIDANCE_END",
    "COPILOT_GUIDANCE_START",
    "COPILOT_INSTRUCTIONS_TARGET",
    "FORCE_PRESERVED_TARGETS",
    "IF_ANCHOR_EXISTS",
    "IF_NOT_EXISTS",
    "INSTALLED_TARGETS_FILE",
    "KNOWN_INSTALL_MODES",
    "InstallResult",
    "InstallStatus",
    "LOCAL_ENV_GITIGNORE_PATTERNS",
    "LOCAL_ONLY_EXCLUDE_END",
    "LOCAL_ONLY_EXCLUDE_START",
    "LOCAL_ONLY_MARKER_FILE",
    "LOCAL_ONLY_TRACKED_CHECK_PATHS",
    "LocalOnlyResult",
    "LocalOnlyStatus",
    "MANAGED_BLOCK_KIND",
    "ManifestVersionAction",
    "NEUTRAL_COMMAND_SOURCE_PLATFORMS",
    "PACK_MANIFEST_FILE",
    "PLATFORMS",
    "PLATFORM_LOCAL_GITIGNORE_PATTERNS",
    "PLATFORM_REGISTRY",
    "PROVENANCE_FILE",
    "PackFile",
    "RETIRED_TARGETS",
    "RETIRED_FULL_CHECK_TARGETS",
    "RETIRED_REVIEW_LOCAL_ALL_TARGETS",
    "RETIRED_REVIEW_LOCAL_TARGETS",
    "RETIRED_WATCH_PR_TARGETS",
    "RETIRED_WORK_DESIGNS_TARGETS",
    "REVIEW_ARTIFACT_GITIGNORE_PATTERNS",
    "ROOT",
    "SOURCE_ONLY_COMMAND_NAMES",
    "SOURCE_ONLY_COMMAND_TARGETS",
    "SOURCE_ONLY_SKILL_REFERENCES",
    "RemoveResult",
    "RemoveStatus",
    "TRELLIS_GITIGNORE_END",
    "TRELLIS_GITIGNORE_PATTERNS",
    "TRELLIS_GITIGNORE_START",
    "TRELLIS_GITIGNORE_TARGET",
    "TRELLIS_INIT_PLATFORM_FLAGS",
    "TRELLIS_INSTALL_DOCS_URL",
    "WRITTEN_REMOVE_STATUSES",
    "_LOCAL_GITIGNORE_GROUP_ORDER",
    "_LOCAL_ONLY_GROUP_ORDER",
    "_ordered_platform_groups_with_local_gitignore",
    "_ordered_platform_groups_with_local_only",
    "_validate_registry_group_order",
    "_validate_registry_group_orders",
    "atomic_write_bytes",
    "display_path",
    "configure_fleet_profile",
    "conversion",
    "ensure_local_only_exclude",
    "ensure_trellis_for_local_only",
    "fileops",
    "inspection",
    "thin",
    "git_info_exclude_path",
    "git_output",
    "install_file",
    "install_installed_targets_file",
    "install_managed_block",
    "install_pack_manifest_file",
    "install_provenance_file",
    "install_trellis_gitignore",
    "installed_target_candidates",
    "installed_targets_content",
    "installed_targets_set",
    "load_manifest",
    "local_only_exclude_block",
    "localonly",
    "machinescope",
    "machinestage",
    "main",
    "manifest",
    "manifest_cli_identity",
    "may_remove_pack_file",
    "merge_local_only_exclude_block",
    "merge_managed_block",
    "merge_trellis_gitignore_block",
    "never_vouched_targets",
    "next_backup_path",
    "normalize_managed_block_template",
    "payload_source_bytes",
    "os",
    "parse_args",
    "preserved_receipt_targets",
    "read_existing_installed_targets",
    "read_existing_provenance_files",
    "read_existing_provenance_pin",
    "read_text_if_exists",
    "read_text_strict",
    "reject_tracked_local_only_paths",
    "removal",
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
    "run_machine_install",
    "selected_files",
    "validate_source_only_command_names",
    "shutil",
    "system_exit_detail",
    "tracked_paths",
    "trellis_init_platforms",
    "validate_manifest",
    "validate_pack_source",
    "validate_resolved_target_path",
    "write_local_only_marker",
]


class ManifestVersionAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        print(manifest_cli_identity())
        parser.exit()


def configure_fleet_profile(
    pack_source: Path,
    *,
    dry_run: bool,
) -> Any:
    scripts_dir = str((pack_source / "scripts").resolve())
    inserted = scripts_dir not in sys.path
    if inserted:
        sys.path.insert(0, scripts_dir)
    try:
        fleet = importlib.import_module("sd_ai_command_pack_fleet_lib")
    except ImportError as error:
        raise ValueError(
            "fleet helper is missing from the pack source; refresh the checkout"
        ) from error
    finally:
        if inserted:
            sys.path.remove(scripts_dir)
    return fleet.configure_fleet_profile(pack_source, dry_run=dry_run)


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
        default=None,
        help="Target Trellis repository root. Defaults to the current directory.",
    )
    inspection_group = parser.add_mutually_exclusive_group()
    inspection_group.add_argument(
        "--status",
        action="store_true",
        help=(
            "Report whether the target is current with this pack checkout "
            "without changing files."
        ),
    )
    inspection_group.add_argument(
        "--check",
        action="store_true",
        help=(
            "Check status and structural integrity; exit 3 when a valid "
            "install needs a refresh."
        ),
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help=(
            "With --status, also run the structural install audit; --check "
            "always runs it."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --status or --check, emit the stable JSON report schema.",
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
        "--machine",
        action="store_true",
        help=(
            "Install the machine-scope surfaces for non-Claude platforms into "
            "the current user's home directory instead of into a repository. "
            "The payload is staged from this checkout; no repository target, "
            "platform selection, or Trellis install is involved."
        ),
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help=(
            "With --machine, the destination home directory. Defaults to the "
            "current user's; a scratch prefix keeps a trial install contained."
        ),
    )
    parser.add_argument(
        "--state-home",
        type=Path,
        default=None,
        help=(
            "With --machine, the private state root holding the machine "
            "receipt and the intent journal."
        ),
    )
    parser.add_argument(
        "--configure-fleet",
        action="store_true",
        help=(
            "Create or update the machine-local fleet profile so installed "
            "sd-status commands can find this pack checkout and its fleet "
            "manifest. Existing checkout path overrides are preserved."
        ),
    )
    parser.add_argument(
        "--thin",
        action="store_true",
        help=(
            "Convert the target repo to a thin install: delete the machine-scope "
            "payload, keep the repo-native surfaces, and record a thin pin. "
            "Requires --resweep-verdict."
        ),
    )
    parser.add_argument(
        "--revert-thin",
        action="store_true",
        help=(
            "Undo a thin conversion: restore the machine-scope payload from this "
            "checkout and rewrite the receipts as a fat install."
        ),
    )
    parser.add_argument(
        "--resweep-verdict",
        type=Path,
        help=(
            "Path to the `clear` verdict document from "
            "scripts/sd-ai-command-pack-thin-resweep.py. Mandatory with --thin: "
            "a conversion is only safe against a tree somebody has swept."
        ),
    )
    parser.add_argument(
        "--consumer",
        help=(
            "With --thin or --revert-thin, the fleet registry name for this "
            "target, overriding the receipt's recorded name."
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
    args = parser.parse_args(argv)
    inspecting = args.status or args.check
    if args.audit and not inspecting:
        parser.error("--audit requires --status or --check")
    if args.json and not inspecting and not args.machine:
        parser.error("--json requires --status, --check, or --machine")
    if not args.machine and (args.home is not None or args.state_home is not None):
        parser.error("--home and --state-home require --machine")
    if args.machine:
        # Machine scope writes user-level surfaces from this checkout's own
        # payload: it has no repository target, so every option that selects,
        # inspects, or edits one is a sign the caller meant something else.
        incompatible = [
            option
            for option, enabled in (
                ("a repository target", args.target is not None),
                ("--platform", bool(args.platform)),
                ("--all", args.all),
                ("--status", args.status),
                ("--check", args.check),
                ("--audit", args.audit),
                ("--remove", args.remove),
                ("--backup", args.backup),
                ("--local-only", args.local_only),
                ("--skip-trellis-init", args.skip_trellis_init),
                ("--skip-diff-check", args.skip_diff_check),
                ("--configure-fleet", args.configure_fleet),
            )
            if enabled
        ]
        if incompatible:
            parser.error(f"--machine cannot be combined with {', '.join(incompatible)}")
    if inspecting:
        incompatible = [
            option
            for option, enabled in (
                ("--platform", bool(args.platform)),
                ("--all", args.all),
                ("--configure-fleet", args.configure_fleet),
                ("--remove", args.remove),
                ("--force", args.force),
                ("--backup", args.backup),
                ("--local-only", args.local_only),
                ("--skip-trellis-init", args.skip_trellis_init),
                ("--dry-run", args.dry_run),
                ("--skip-diff-check", args.skip_diff_check),
            )
            if enabled
        ]
        if incompatible:
            parser.error(
                f"{('--check' if args.check else '--status')} cannot be combined "
                f"with {', '.join(incompatible)}"
            )
    if args.remove and args.configure_fleet:
        parser.error("--remove cannot be combined with --configure-fleet")
    _reject_incompatible_conversion_flags(parser, args, inspecting=inspecting)
    return args


def _reject_incompatible_conversion_flags(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    *,
    inspecting: bool,
) -> None:
    """Enforce design.md's conversion matrix, declared rather than ordered.

    `--thin` and `--revert-thin` are two more mutators entering a dispatch that
    already has three, and dispatch order silently picks a winner when two are
    passed. Every rejection here names both flags: a caller who passed two
    destructive selectors needs to know which one was ignored, and "did
    something reasonable" is the failure mode, not the fallback.
    """
    direction = "--thin" if args.thin else "--revert-thin" if args.revert_thin else None

    if args.thin and args.revert_thin:
        parser.error("--thin cannot be combined with --revert-thin: opposing mutators")

    if direction is not None:
        incompatible = [
            option
            for option, enabled in (
                ("--remove", args.remove),
                ("--machine", args.machine),
                ("--status", args.status),
                ("--check", args.check),
                ("--configure-fleet", args.configure_fleet),
                # Payload selectors do not apply in *either* direction: the
                # conversion's payload is derived from the receipt and the
                # partition, so a selector could only disagree with it.
                ("--platform", bool(args.platform)),
                ("--all", args.all),
                ("--local-only", args.local_only),
            )
            if enabled
        ]
        if incompatible:
            parser.error(
                f"{direction} cannot be combined with {', '.join(incompatible)}"
            )

    if args.thin and args.resweep_verdict is None:
        parser.error(
            "--thin requires --resweep-verdict: a conversion is only safe "
            "against a tree somebody has swept"
        )
    if args.resweep_verdict is not None and not args.thin:
        parser.error("--resweep-verdict requires --thin")

    if args.revert_thin and args.force:
        # Revert makes no drift decision, so there is nothing for --force to
        # override. Restore-path occupancy is refused outright (R19-C3), not
        # forced over: overwriting a consumer's file to reach a state they had
        # before is the wrong default and the wrong flag.
        parser.error("--force cannot be combined with --revert-thin")

    if args.consumer is not None and direction is None:
        parser.error("--consumer requires --thin or --revert-thin")


def _install_payload(
    selected: list[PackFile],
    target: Path,
    *,
    local_only: bool,
    force: bool,
    dry_run: bool,
    backup: bool,
    planned_results: dict[Path, InstallResult] | None = None,
    install_gitignore: bool = True,
    is_thin: bool = False,
) -> tuple[list[InstallResult], list[Path]]:
    results: list[InstallResult] = []
    generated_targets: list[Path] = []
    # Read once per run and thread it, the way removal.py already threads the
    # same file. Every pass that reaches here -- the preflight, the apply, and
    # the --check/--status dry run -- runs before the receipts are rewritten,
    # so one read describes the previous release for all of them, and the
    # preflight cannot classify a target differently from the apply.
    provenance_files = read_existing_provenance_files(target)
    # A thin checkout stripped the pack's .gitignore block on purpose: the
    # entries it carries ignore machine surfaces that no longer live in the
    # repository. Reinstalling it would make every thin inspection report a
    # pending change and would relist .gitignore as an installed target.
    if not local_only and install_gitignore:
        results.append(install_trellis_gitignore(target, dry_run=dry_run))
        generated_targets.append(TRELLIS_GITIGNORE_TARGET)

    for file in selected:
        if file.kind == MANAGED_BLOCK_KIND:
            result = install_managed_block(
                file, target, dry_run=dry_run, is_thin=is_thin
            )
        else:
            result = install_file(
                file,
                target,
                force=force,
                dry_run=dry_run,
                backup=backup,
                is_thin=is_thin,
                planned_result=(
                    planned_results.get(file.target) if planned_results else None
                ),
                provenance_files=provenance_files,
            )
        results.append(result)

    return results, generated_targets


def _conflict_results(results: list[InstallResult]) -> list[InstallResult]:
    return [result for result in results if result.status in CONFLICT_STATUSES]


def _print_conflicts(conflicts: list[InstallResult]) -> None:
    print("")
    print("Conflicts:")
    for result in conflicts:
        if result.status is InstallStatus.SYMLINK_CONFLICT:
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
    pin: dict | None = None,
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
            pin=pin,
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
    for local_result in local_only_results[local_only_results_printed:]:
        suffix = f" ({local_result.detail})" if local_result.detail else ""
        print(
            f"{local_result.status:29} "
            f"{display_path(target, local_result.target)}{suffix}"
        )
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


SURFACE_PARTITION_FILE = Path("docs/fleet/surface-partition.json")


def _residual_files_for_thin(
    files: list[PackFile],
    target: Path,
) -> tuple[list[PackFile], bool]:
    """Narrow the payload to the residual slice when this checkout is thin.

    Returns ``(files, False)`` for every fat checkout, which is every existing
    consumer: the sole discriminator is ``mode: "thin"`` in the provenance
    receipt. An unreadable partition also falls back to the full payload --
    that over-reports a refresh rather than under-reporting one, and the
    resweep is where a missing partition is a hard error.
    """
    receipt = conversion.read_thin_receipt(target)
    if receipt is None or not receipt.is_thin:
        return files, False
    try:
        partition = conversion.load_partition(ROOT / SURFACE_PARTITION_FILE)
    except (OSError, ValueError, KeyError, TypeError):
        return files, False
    # R18-C1: an unusable pin must not be allowed to choose the comparison it
    # is then measured against. Falling back to the full payload reports the
    # deleted machine surfaces as missing, which is `invalid` -- the same
    # answer a half-converted consumer gets, and the right one for a pin that
    # cannot be trusted.
    if conversion.unusable_thin_pin_reason(receipt, partition) is not None:
        return files, False
    return conversion.residual_source_files(files, target, partition, receipt), True


def _selection_for_target(
    files: list[PackFile],
    target: Path,
    *,
    platforms: list[str] | None,
    install_all: bool,
) -> tuple[list[PackFile], list[tuple[PackFile, str]], bool]:
    """The payload this consumer gets, decided in one place for every caller.

    Inspection and refresh have to answer this identically or a converted
    consumer reports `refresh-required` forever against a refresh that would
    change nothing. Two things differ for a thin consumer and both are decided
    here: the payload is narrowed to the residual, and the platform filter is
    the pin's rather than a fresh detection -- detection answers "what is
    active now", and a refresh must not widen a consumer because somebody
    activated another Trellis platform after the conversion.
    """
    payload, is_thin = _residual_files_for_thin(files, target)
    if not is_thin:
        return (*selected_files(payload, target, platforms, install_all), False)
    pinned = conversion.read_thin_receipt(target)
    assert pinned is not None  # _residual_files_for_thin returned True
    return (*selected_files(payload, target, sorted(pinned.platforms), False), True)


def _receipt_manifest(manifest_data: dict, *, is_thin: bool) -> dict:
    """The manifest as the installed receipt carries it.

    `thin_pin_state` reads the installed manifest *before* provenance, so the
    thin marker has to survive every write that touches it. Writing the plain
    manifest here is what made `--check` report a converted consumer as
    `refresh-required` forever: the dry-run receipt disagreed with the file on
    disk about one key.
    """
    return {**manifest_data, "mode": conversion.THIN_MODE} if is_thin else manifest_data


def _refuse(reasons: list[str] | tuple[str, ...], headline: str) -> int:
    """Every conversion refusal, in one shape: nothing was written."""
    for reason in reasons:
        print(f"blocked     {reason}", file=sys.stderr)
    print(f"error: {headline}; nothing was written.", file=sys.stderr)
    return 2


def _run_thin_conversion(
    args: argparse.Namespace,
    target: Path,
    manifest_data: dict,
    files: list[PackFile],
) -> int:
    """Plan the whole conversion, validate all of it, then write in fixed order.

    Every refusal below happens before the first byte lands. That is not a
    stylistic preference: a conversion deletes ~170 files across two roots and
    has no rollback, so a check that runs one step late is a consumer that has
    already lost them.
    """
    resweep = thin.load_resweep_module(ROOT)
    try:
        entry, checkout = resweep.resolve_consumer(args.consumer, target)
    except SystemExit as error:
        print(system_exit_detail(error), file=sys.stderr)
        return 2

    verdict_load = thin.load_verdict(args.resweep_verdict)
    if verdict_load.document is None:
        return _refuse(
            [verdict_load.detail or ""],
            f"the resweep verdict is {verdict_load.state}",
        )
    fresh = resweep.resweep_consumer(args.consumer, checkout)
    binding = thin.verdict_binding_reasons(verdict_load.document, fresh)
    if binding:
        return _refuse(binding, "this verdict does not authorize this conversion")

    origin = _origin_url(ROOT)
    locator_reason = thin.pack_repository_reason(origin)
    if locator_reason is not None:
        return _refuse([locator_reason], "the marketplace source cannot be validated")

    for root, label in ((target, "target"), (ROOT, "pack root")):
        reason = thin.writability_reason(root, label)
        if reason is not None:
            return _refuse([reason], "both roots must be writable before either is")

    receipt = conversion.read_installed_targets_receipt(target)
    if receipt.state != conversion.RECEIPT_PRESENT:
        return _refuse(
            [receipt.detail or ""], "the installed-targets receipt is unusable"
        )
    partition = conversion.load_partition(ROOT / SURFACE_PARTITION_FILE)
    platforms = frozenset(entry.get("platforms") or ())
    plan = conversion.build_conversion_plan(
        receipt,
        partition,
        platforms,
        occupied=conversion.occupied_receipt_targets(target, receipt),
    )
    if plan.blocked:
        return _refuse(
            [f"{blocked.target}: {blocked.reason}" for blocked in plan.blocked],
            "the conversion plan does not classify every installed target",
        )

    # Deliberately not `inspection.inspect_receipts(target).errors`, which was
    # the first attempt: that bundles per-file content drift into the same
    # answer, so refusing on it would make `--force` unreachable -- and
    # overriding removal drift is exactly what `--force` is for. The question
    # here is narrower and is the one the staleness test exposed: do the two
    # receipts describe the same install? A conversion rewrites all three from
    # the state of these ones, so contradictory inputs produce a thin receipt
    # certifying a tree nobody measured.
    disagreement = thin.receipt_disagreement_reason(target)
    if disagreement is not None:
        return _refuse([disagreement], "this consumer's receipts do not agree")
    installed_version = inspection.inspect_receipts(target).installed_version
    stale = thin.version_currency_reason(installed_version, manifest_data["version"])
    if stale is not None:
        return _refuse([stale], "this consumer is not current enough to convert")

    residual = frozenset(plan.keep) | frozenset(plan.receipts)
    expected = conversion.expected_residual_targets(
        frozenset(file.target.as_posix() for file in files),
        partition,
        platforms,
        present_managed_blocks=frozenset(
            managed
            for managed in MANAGED_BLOCK_REMOVAL_TARGETS
            if (target / managed).exists() and managed not in plan.block_strip
        ),
    )
    drifted_receipt = thin.stale_receipt_reason(expected, residual)
    if drifted_receipt is not None:
        return _refuse([drifted_receipt], "this consumer's receipt is stale")

    # Every check above reads outward from the receipt. This one reads back:
    # a tracked pack-like file the receipt never listed is in neither `keep`
    # nor `delete` -- the plan is built from the receipt -- so conversion walks
    # past it and it survives into the thin tree while the receipt comparisons
    # all still pass. Structural failures only, so `--force` stays reachable
    # for the content drift it exists to override.
    structural = thin.structural_audit_reasons(ROOT, target)
    if structural:
        return _refuse(
            list(structural), "this consumer's installed tree is not structurally sound"
        )

    marketplace_name, plugin_name = _plugin_identity(ROOT)
    settings, settings_reason = thin.plan_settings_merge(
        target / thin.CLAUDE_SETTINGS_FILE, marketplace_name, plugin_name
    )
    if settings is None:
        return _refuse(
            [settings_reason or ""], "the settings merge cannot proceed"
        )

    files_by_target = {file.target.as_posix(): file for file in files}
    provenance_files = read_existing_provenance_files(target)
    drift = thin.removal_preflight_reasons(
        target,
        plan,
        files_by_target=files_by_target,
        provenance_files=provenance_files,
        force=args.force,
    )
    if drift:
        return _refuse(drift, "removal drift; re-run with --force to override it")

    print(f"{manifest_data['name']} {manifest_data['version']}")
    print(f"target: {target}")
    print("mode: thin")
    print(
        f"plan: delete {len(plan.delete)}, retire {len(plan.retire)}, "
        f"block-strip {len(plan.block_strip)}, keep {len(plan.keep)}, "
        f"receipts {len(plan.receipts)}"
    )
    if args.dry_run:
        # All six categories, not just the deletions. A delete-only printout
        # passes a "the tree was unchanged" comparison while the settings
        # merge, the three receipt rewrites, and the registry flip go
        # unannounced -- which is most of what makes this command
        # irreversible.
        print("mode: dry-run")
        for entry_path in plan.delete:
            print(f"would-delete   {entry_path}")
        for entry_path in plan.retire:
            print(f"would-retire   {entry_path}")
        for entry_path in plan.block_strip:
            print(f"would-strip    {entry_path}")
        for receipt_path in (PACK_MANIFEST_FILE, INSTALLED_TARGETS_FILE, PROVENANCE_FILE):
            print(f"would-rewrite  {receipt_path.as_posix()}")
        if settings.created_file:
            print(f"would-create   {thin.CLAUDE_SETTINGS_FILE.as_posix()}")
        for container, entries in sorted(settings.additions.items()):
            for key in sorted(entries):
                print(f"would-set      {container}.{key}")
        if args.consumer is not None:
            print(f"would-registry {args.consumer} -> thin")
        return 0

    try:
        written = thin.apply_conversion(
            ROOT,
            target,
            plan=plan,
            settings=settings,
            manifest_data=manifest_data,
            residual=residual,
            existing_files=provenance_files,
            platforms=tuple(sorted(platforms)),
            consumer=args.consumer,
            forced=(),
            files_by_target=files_by_target,
            provenance_files=provenance_files,
            force=args.force,
            backup=args.backup,
        )
    except thin.PartialConversion as partial:
        return _report_partial(
            partial,
            f"{display_path(ROOT, target)} is converted and the registry still "
            f"reads fat",
            f"install.py TARGET --thin re-run, or set {args.consumer} to "
            "mode: thin in docs/fleet/consumers.json by hand",
        )
    for write in written:
        print(f"{write.step:26} {write.detail}")
    return 0


def _report_partial(
    partial: thin.PartialConversion, headline: str, recovery: str
) -> int:
    """Say which half landed, then exit nonzero. Never claim a clean run."""
    for write in partial.written:
        print(f"{write.step:26} {write.detail}")
    print(
        f"error: the fleet registry could not be written ({partial.detail}).\n"
        f"       {headline}; nothing is rolled back.\n"
        f"       Recover with: {recovery}",
        file=sys.stderr,
    )
    return 2


def _run_thin_revert(
    args: argparse.Namespace,
    target: Path,
    manifest_data: dict,
    files: list[PackFile],
) -> int:
    """Restore the fat payload, undo the settings merge, unflip the registry.

    The same plan-then-mutate shape as `--thin` and for the same reason, with
    one addition the forward direction does not need: revert writes *into*
    paths the consumer has had time to occupy, so every restore path is
    probed before the first one is written (R19-C3). `--force` is rejected
    rather than made to override that -- overwriting a consumer's file to
    reach a state they had before is the wrong default and the wrong flag, and
    the recovery is to move the colliding file, which only they can decide.
    """
    receipt = conversion.read_thin_receipt(target)
    if receipt is None or not receipt.is_thin:
        return _refuse(
            [f"{display_path(ROOT, target)} carries no thin pin"],
            "there is nothing to revert",
        )

    stale = thin.revert_version_reason(receipt.version, manifest_data["version"])
    if stale is not None:
        return _refuse([stale], "this checkout cannot restore this pin")

    consumer, identity_reason = thin.revert_consumer_identity(
        ROOT,
        target,
        receipt_consumer=receipt.consumer,
        flag_consumer=args.consumer,
    )
    if consumer is None:
        return _refuse([identity_reason or ""], "the consumer cannot be identified")

    for root, label in ((target, "target"), (ROOT, "pack root")):
        reason = thin.writability_reason(root, label)
        if reason is not None:
            return _refuse([reason], "both roots must be writable before either is")

    marketplace_name, plugin_name = _plugin_identity(ROOT)
    settings_plan, settings_reason = thin.plan_settings_revert(
        target / thin.CLAUDE_SETTINGS_FILE,
        receipt.settings_additions,
        plugin_key=f"{plugin_name}@{marketplace_name}",
    )
    if settings_plan is None:
        return _refuse([settings_reason or ""], "the settings revert cannot proceed")

    # The pin's platform set, never re-detected. Detection answers "what is
    # active in this tree now", and revert's question is "what was taken away"
    # -- the two agree until the consumer activates another Trellis platform
    # while converted, and then detection restores a payload the pre-conversion
    # tree never had, with receipts that vouch for it. Passing the set
    # explicitly also skips the anchor check, which is right for the same
    # reason: the anchor is evidence about now.
    platforms = sorted(receipt.platforms)
    if not platforms:
        return _refuse(
            ["this consumer's thin pin declares no usable platform set"],
            "the payload to restore cannot be determined",
        )
    selected, skipped = selected_files(files, target, platforms, False)

    preflight_results, _ = _install_payload(
        selected, target, local_only=False, force=False, dry_run=True, backup=False
    )
    collisions = _conflict_results(preflight_results)
    if collisions:
        return _refuse(
            [
                f"{collision.file.target} is occupied by a different file"
                for collision in collisions
            ],
            "restore paths are occupied; move or delete them and re-run "
            "(--force is not accepted here)",
        )
    receipt_conflicts = [
        (destination, status)
        for destination, status in (
            (path, generated_text_file_status(target / path))
            for path in (PACK_MANIFEST_FILE, PROVENANCE_FILE, INSTALLED_TARGETS_FILE)
        )
        if status is not None
    ]
    if receipt_conflicts:
        return _refuse(
            [f"{destination}: {status.value}" for destination, status in receipt_conflicts],
            "a pack receipt cannot be written in place",
        )

    print(f"{manifest_data['name']} {manifest_data['version']}")
    print(f"target: {target}")
    print("mode: revert-thin")
    print(f"consumer: {consumer}")
    print(f"plan: restore {len(selected)}, platforms {', '.join(platforms)}")
    if args.dry_run:
        print("mode: dry-run")
        for result in preflight_results:
            print(f"would-{result.status:11} {result.file.target}")
        for receipt_path in (PACK_MANIFEST_FILE, INSTALLED_TARGETS_FILE, PROVENANCE_FILE):
            print(f"would-rewrite  {receipt_path.as_posix()}")
        for entry in receipt.retired:
            print(f"would-not-restore {entry}")
        for note in settings_plan.notes:
            print(f"note        {note}")
        print(f"would-settings {settings_plan.action}")
        print(f"would-registry {consumer} -> fat")
        return 0

    # Write order, and it is the mirror of the conversion's rather than its
    # reverse. The payload comes back first, while the pin still says thin, so
    # an interruption anywhere in here leaves a consumer that reads thin and
    # re-runs cleanly -- restoring a file that is already byte-identical is a
    # no-op. The receipts commit; the settings undo happens only after the
    # files it was covering for are back; the registry is last.
    results, generated_targets = _install_payload(
        selected,
        target,
        local_only=False,
        force=False,
        dry_run=False,
        backup=False,
        planned_results={
            result.file.target: result
            for result in preflight_results
            if result.source_content is not None
        },
    )
    kept_receipt_targets = _install_receipt_files(
        manifest_data,
        files,
        target,
        selected=selected,
        skipped=skipped,
        results=results,
        generated_targets=generated_targets,
        dry_run=False,
    )
    # An interrupted conversion leaves this behind, and its whole meaning is
    # "removals are outstanding". After a restore they are not outstanding;
    # they are undone.
    inventory = target / thin.REMOVAL_INVENTORY_FILE
    if inventory.is_file():
        inventory.unlink()

    _print_install_summary(
        target,
        results=results,
        retired_results=[],
        local_only_results=[],
        local_only_results_printed=0,
        skipped=skipped,
        files=files,
        platforms_requested=platforms,
        kept_receipt_targets=kept_receipt_targets,
    )
    for entry in receipt.forced:
        print(f"restored-to-source {entry}")
    for entry in receipt.retired:
        print(f"not-restored {entry} (retired before the conversion; the pack "
              "no longer ships it)")
    settings_detail = thin.apply_settings_revert(settings_plan)
    if settings_detail is not None:
        print(f"settings    {settings_detail}")
    for note in settings_plan.notes:
        print(f"note        {note}")
    try:
        thin.flip_registry_mode(ROOT, consumer, "fat")
    except OSError as error:
        return _report_partial(
            thin.PartialConversion(
                (thin.ConversionWrite("payload", "restored"),), str(error)
            ),
            f"{display_path(ROOT, target)} is fat again and the registry still "
            "reads thin",
            # Not "re-run --revert-thin": the pin is already fat, so a re-run
            # refuses with "carries no thin pin" and the row stays wrong.
            f"set {consumer} to mode: fat in docs/fleet/consumers.json by hand",
        )
    print(f"registry    {consumer} -> fat")
    return 0


def _thin_refresh_rejection(
    args: argparse.Namespace, pinned: conversion.ThinReceipt | None
) -> str | None:
    """Why this refresh must not run against a thin consumer.

    A refresh updates a converted consumer's version and nothing else. Every
    rejection here is a way of asking it to also change *what* is installed --
    which is a conversion decision, made against a resweep verdict, in a
    reviewed PR, not a side effect of a fleet-wide `install.py` sweep.
    """
    if args.platform or args.all:
        return (
            "a thin consumer's platform set is owned by its pin; --platform "
            "and --all do not apply. Revert first if the platform set must "
            "change"
        )
    if args.local_only:
        return (
            "--local-only installs an untracked payload, which a thin "
            "consumer does not have; it has a pin and a residual"
        )
    if pinned is None or not pinned.platforms:
        return (
            "this consumer's thin pin cannot be read against the surface "
            "partition, so the residual to refresh is unknown; run "
            "install.py TARGET --check for the diagnosis"
        )
    return None


def _origin_url(root: Path) -> str | None:
    """The pack checkout's `origin`, or None when there isn't one.

    `git_output` rather than a second subprocess call: it is the installer's
    one git surface, it already carries the timeout and the missing-binary
    handling, and `tests/test_git_invocation_boundary.py` exists to keep the
    count at one.
    """
    return git_output(root, "remote", "get-url", "origin") or None


def _plugin_identity(root: Path) -> tuple[str, str]:
    """The marketplace and plugin names, read rather than hardcoded.

    Renaming either in one place cannot then leave consumers enabling a plugin
    that no longer exists -- and both manifests are classifier-digest inputs,
    so a rename also invalidates every outstanding verdict.
    """
    marketplace = json.loads(
        (root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
    )
    plugin = json.loads(
        (root / "plugins/sd/.claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    return str(marketplace["name"]), str(plugin["name"])


def _run_inspection(
    args: argparse.Namespace,
    target: Path,
    manifest_data: dict,
    files: list[PackFile],
) -> int:
    """Plan a refresh without writes and render status/check output."""
    receipts = inspection.inspect_receipts(target)
    receipt_errors = list(receipts.errors)
    try:
        require_target_directory(target)
        if manifest_data.get("requiresTrellis", True):
            require_trellis_repo(target)
    except SystemExit as error:
        receipt_errors.append(system_exit_detail(error))
    if tuple(receipt_errors) != receipts.errors:
        receipts = inspection.ReceiptState(
            receipts.present,
            receipts.installed_version,
            receipts.targets,
            receipts.platforms,
            tuple(dict.fromkeys(receipt_errors)),
        )

    results: list[InstallResult] = []
    retired_results: list[RemoveResult] = []
    if receipts.present and not receipts.errors:
        try:
            # A thin consumer is missing its machine surfaces on purpose.
            # Comparing it against the full payload would report
            # refresh-required forever, and fleet-review-classify requires
            # `current`. mode: "thin" in the provenance receipt is the only
            # discriminator; a fat consumer takes the unchanged path below.
            selected, skipped, is_thin = _selection_for_target(
                files, target, platforms=None, install_all=False
            )
            results, generated_targets = _install_payload(
                selected,
                target,
                local_only=False,
                force=False,
                dry_run=True,
                backup=False,
                install_gitignore=not is_thin,
                is_thin=is_thin,
            )
            retired_results = retire_stale_targets(
                target,
                force=False,
                dry_run=True,
                backup=False,
            )
            _install_receipt_files(
                _receipt_manifest(manifest_data, is_thin=is_thin),
                files,
                target,
                selected=selected,
                skipped=skipped,
                results=results,
                generated_targets=generated_targets,
                dry_run=True,
                pin=read_existing_provenance_pin(target),
            )
        except SystemExit as error:
            receipts = inspection.ReceiptState(
                receipts.present,
                receipts.installed_version,
                receipts.targets,
                receipts.platforms,
                (*receipts.errors, system_exit_detail(error)),
            )

    audit_requested = args.audit or args.check
    if not receipts.present:
        audit_result = inspection.not_requested_audit(
            applicable=False, requested=audit_requested
        )
    elif audit_requested:
        audit_result = inspection.run_install_audit(target)
    else:
        audit_result = inspection.not_requested_audit()
    report = inspection.build_report(
        manifest_data=manifest_data,
        target=target,
        receipts=receipts,
        install_results=results,
        retired_results=retired_results,
        audit=audit_result,
    )
    print(
        inspection.render_json(report) if args.json else inspection.render_human(report)
    )
    return inspection.report_exit_code(report, check=args.check)


def run_machine_install(args: argparse.Namespace) -> int:
    """Stage this checkout's machine payload and hand it to the engine.

    The engine owns the plan, the conflict refusals, the receipt, and the exit
    codes; staging only decides what the payload contains. Both halves are the
    same code the plugin ships, so a developer installing from a checkout and a
    machine installing from the plugin converge on the same tree.
    """

    engine_argv = ["install"]
    if args.force:
        engine_argv.append("--force")
    if args.dry_run:
        engine_argv.append("--dry-run")
    if args.json:
        engine_argv.append("--json")
    if args.home is not None:
        engine_argv.extend(["--home", str(args.home)])
    if args.state_home is not None:
        engine_argv.extend(["--state-home", str(args.state_home)])
    try:
        with machinestage.staged_payload(ROOT) as payload_root:
            return machinescope.main([*engine_argv, "--payload", str(payload_root)])
    except (
        machinestage.MachineStageError,
        machinestage.ReferenceRewriteError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.machine:
        return run_machine_install(args)
    if args.backup and not args.force and not args.remove:
        raise SystemExit("error: --backup requires --force unless --remove is set")
    if args.skip_trellis_init and not args.local_only:
        raise SystemExit("error: --skip-trellis-init requires --local-only")

    target = Path(args.target or ".").resolve()
    manifest_data, files = load_manifest()

    validate_manifest(files)
    fleet_profile_plan = None
    if args.configure_fleet:
        try:
            fleet_profile_plan = configure_fleet_profile(ROOT, dry_run=True)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    if args.status or args.check:
        return _run_inspection(args, target, manifest_data, files)
    if args.thin:
        # Before the thin-consumer guard below, deliberately: converting an
        # already-thin consumer is the documented recovery from an interrupted
        # run, and the guard exists to stop *fat-shaped* commands, not this
        # one.
        return _run_thin_conversion(args, target, manifest_data, files)
    if args.revert_thin:
        # Also before the guard: the guard's whole message is "run
        # --revert-thin first", so routing it through the refusal it names
        # would make the instruction unfollowable.
        return _run_thin_revert(args, target, manifest_data, files)
    thin_state = conversion.thin_pin_state(target)
    thin_refresh = False
    if thin_state == conversion.PIN_STATE_THIN and not args.remove:
        # Step 9b. R19-C1's refusal was fail-closed and never the end state:
        # `sd-fleet-refresh` runs exactly this command against every consumer,
        # so a converted consumer that could not be refreshed could not
        # receive a pack update at all. The refusal survives for `--remove`
        # and for a malformed pin below; ordinary install becomes thin-aware
        # instead, by narrowing the payload with the same predicate `--check`
        # uses rather than a second formula.
        pinned = conversion.read_thin_receipt(target)
        reason = _thin_refresh_rejection(args, pinned)
        if reason is not None:
            print(f"error: {reason}", file=sys.stderr)
            return 2
        thin_refresh = True
    elif thin_state != conversion.PIN_STATE_FAT:
        # R18-C2 and R19-C1. Two shipped commands mutate a consumer without
        # ever asking whether it is thin, and both corrupt one when it is.
        # `--remove` deletes provenance and leaves the plugin enabled and the
        # registry saying `thin`: a repository with no pack files, no receipt
        # that a pack was ever there, and a live plugin still serving it.
        # `--remove` still refuses and always will: it has no thin form. The
        # ordinary install that used to refuse alongside it is now the
        # thin-aware refresh above, because a fleet refresh runs exactly that
        # command and a consumer it cannot refresh is a consumer that cannot
        # receive a security fix.
        #
        # `malformed` refuses in both directions. It means a receipt that
        # carried the pin has since been edited, which is exactly the state
        # that must not be treated as "fat, go ahead" -- and equally must not
        # be treated as a pin worth carrying forward.
        detail = (
            "provenance records mode: thin"
            if thin_state == conversion.PIN_STATE_THIN
            else "provenance carries thin pin keys it cannot be read against"
        )
        action = "--remove" if args.remove else "install"
        print(
            f"error: {display_path(ROOT, target)} is a thin consumer "
            f"({detail}); {action} would leave it half-converted.\n"
            "       Run install.py TARGET --revert-thin first, then retry.",
            file=sys.stderr,
        )
        return 2
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
        # One selection helper for refresh and inspection both, so a converted
        # consumer cannot report `refresh-required` against a refresh that
        # would change nothing.
        selected, skipped, is_thin = _selection_for_target(
            files, target, platforms=args.platform, install_all=args.all
        )
        if thin_refresh and not is_thin:
            # The pin state said thin and the partition could not be read
            # against it. `_thin_refresh_rejection` catches the reachable
            # forms; this is the backstop that refuses rather than silently
            # installing the full payload over a converted consumer.
            print(
                "error: this consumer's thin pin cannot be read against the "
                "surface partition; run install.py TARGET --check",
                file=sys.stderr,
            )
            return 2
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
            install_gitignore=not thin_refresh,
            is_thin=thin_refresh,
        )
        preflight_conflicts = _conflict_results(preflight_results)
        if preflight_conflicts:
            for conflict in preflight_conflicts:
                print(f"{conflict.status:11} {conflict.file.target}")
            _print_conflicts(preflight_conflicts)
            return 2
        # R20-C1: the payload preflight above covers selected files only. The
        # three receipts are written afterwards, by a different path, so a
        # conflict on one of them was reported only after the payload had
        # already landed -- which is how a thin consumer with a symlinked
        # provenance got its machine surfaces rewritten while the command
        # exited 2. "Plan before apply" has to include the files the plan
        # itself writes.
        receipt_conflicts = [
            (destination, status)
            for destination, status in (
                # Deliberately unresolved: `is_symlink()` is the question, so
                # the path must not be resolved through the link first.
                (receipt, generated_text_file_status(target / receipt))
                for receipt in (
                    PACK_MANIFEST_FILE,
                    PROVENANCE_FILE,
                    INSTALLED_TARGETS_FILE,
                )
            )
            if status is not None
        ]
        if receipt_conflicts:
            for destination, status in receipt_conflicts:
                print(f"{status.value:11} {destination}")
            print(
                "error: a pack receipt cannot be written in place; nothing was "
                "installed.\n"
                "       Resolve the paths above, or re-run with --force.",
                file=sys.stderr,
            )
            return 2
        planned_results = {
            result.file.target: result
            for result in preflight_results
            if result.source_content is not None
        }
    else:
        planned_results = None

    results, generated_targets = _install_payload(
        selected,
        target,
        local_only=args.local_only,
        force=args.force,
        dry_run=args.dry_run,
        backup=args.backup,
        planned_results=planned_results,
        # A thin checkout stripped the pack's .gitignore block on purpose: its
        # entries ignore machine surfaces that no longer live in the
        # repository. Reinstalling it would make every thin inspection report
        # a pending change and would relist .gitignore as an installed target.
        install_gitignore=not thin_refresh,
        # The same discriminator decides the payload's text: a thin consumer's
        # repo-native files must name the machine locations, and deciding it
        # here keeps the preflight above and this apply pass byte-identical.
        is_thin=thin_refresh,
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
        # Both thin witnesses carried forward, not one: the pin into
        # provenance and `mode: "thin"` into the installed manifest.
        _receipt_manifest(manifest_data, is_thin=thin_refresh),
        files,
        target,
        selected=selected,
        skipped=skipped,
        results=results,
        generated_targets=generated_targets,
        dry_run=args.dry_run,
        pin=read_existing_provenance_pin(target) if thin_refresh else None,
    )
    if args.local_only:
        local_only_results.append(write_local_only_marker(target, dry_run=args.dry_run))

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
        unwritten_statuses = CONFLICT_STATUSES | {InstallStatus.PRESERVED}
        diff_paths = [
            result.file.target
            for result in results
            if result.status not in unwritten_statuses
        ]
        diff_status = run_diff_check(target, diff_paths)
        if diff_status != 0:
            return diff_status

    if args.configure_fleet:
        assert fleet_profile_plan is not None
        profile = (
            fleet_profile_plan
            if args.dry_run
            else configure_fleet_profile(ROOT, dry_run=False)
        )
        print(f"{profile.status:29} fleet profile {profile.path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
