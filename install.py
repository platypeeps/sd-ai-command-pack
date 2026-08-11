#!/usr/bin/env python3
"""Install the SD AI command pack into a Trellis repo."""

from __future__ import annotations

import argparse
import importlib
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
    return args


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
) -> tuple[list[InstallResult], list[Path]]:
    results: list[InstallResult] = []
    generated_targets: list[Path] = []
    # A thin checkout stripped the pack's .gitignore block on purpose: the
    # entries it carries ignore machine surfaces that no longer live in the
    # repository. Reinstalling it would make every thin inspection report a
    # pending change and would relist .gitignore as an installed target.
    if not local_only and install_gitignore:
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
                planned_result=(
                    planned_results.get(file.target) if planned_results else None
                ),
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
            inspected_files, is_thin = _residual_files_for_thin(files, target)
            selected, skipped = selected_files(inspected_files, target, None, False)
            results, generated_targets = _install_payload(
                selected,
                target,
                local_only=False,
                force=False,
                dry_run=True,
                backup=False,
                install_gitignore=not is_thin,
            )
            retired_results = retire_stale_targets(
                target,
                force=False,
                dry_run=True,
                backup=False,
            )
            _install_receipt_files(
                manifest_data,
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
    thin_state = conversion.thin_pin_state(target)
    if thin_state != conversion.PIN_STATE_FAT:
        # R18-C2 and R19-C1. Two shipped commands mutate a consumer without
        # ever asking whether it is thin, and both corrupt one when it is.
        # `--remove` deletes provenance and leaves the plugin enabled and the
        # registry saying `thin`: a repository with no pack files, no receipt
        # that a pack was ever there, and a live plugin still serving it.
        # Ordinary install is worse because it is routine -- a fleet refresh
        # rewrites the receipt without the pin, silently de-thinning every
        # converted consumer while the registry still reads `thin`.
        #
        # Both refuse rather than becoming thin-aware, and the reason is the
        # same one the argument matrix gives: undoing or refreshing a thin
        # consumer needs the pack root as well as the target, and neither
        # command takes one. A thin-aware refresh is a real surface and it is
        # planned as its own step; until it exists, the safe answer is to stop
        # loudly. No consumer is thin yet, so this refuses nothing that works
        # today.
        #
        # `malformed` refuses too. It means a receipt that carried the pin has
        # since been edited, which is exactly the state that must not be
        # treated as "fat, go ahead".
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
