#!/usr/bin/env python3
"""Install the SD AI command pack into a Trellis repo."""

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



from installer import (  # noqa: F401
    fileops,
    localonly,
    manifest,
    provenance,
    registry,
    removal,
)
from installer.registry import *  # noqa: F401,F403
from installer.registry import (  # noqa: F401
    _LOCAL_GITIGNORE_GROUP_ORDER,
    _LOCAL_ONLY_GROUP_ORDER,
)
from installer.manifest import *  # noqa: F401,F403
from installer.fileops import *  # noqa: F401,F403
from installer.provenance import *  # noqa: F401,F403
from installer.localonly import *  # noqa: F401,F403
from installer.removal import *  # noqa: F401,F403



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
            "(except .prism/rules.json and .gito/config.toml). Add --backup "
            "to save .bak copies before overwriting."
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.backup and not args.force and not args.remove:
        raise SystemExit("error: --backup requires --force unless --remove is set")
    if args.skip_trellis_init and not args.local_only:
        raise SystemExit("error: --skip-trellis-init requires --local-only")

    target = Path(args.target).resolve()
    manifest, files = load_manifest()

    validate_manifest(files)
    if args.remove:
        return remove_installed_pack(
            manifest,
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
        if manifest.get("requiresTrellis", True):
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
        install_pack_manifest_file(
            manifest,
            target,
            dry_run=args.dry_run,
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
    receipt_target_set = {
        *(file.target.as_posix() for file in selected),
        *(path.as_posix() for path in receipt_extra_targets),
        INSTALLED_TARGETS_FILE.as_posix(),
    }
    results.append(
        install_provenance_file(
            manifest,
            results,
            target,
            receipt_targets=receipt_target_set,
            never_vouched=never_vouched_targets(files),
            dry_run=args.dry_run,
        )
    )
    results.append(
        install_installed_targets_file(
            selected,
            target,
            dry_run=args.dry_run,
            extra_targets=receipt_extra_targets,
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
    for platform in sorted(set(args.platform or [])):
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

    conflict_results = [
        result
        for result in results
        if result.status in {"conflict", "symlink-conflict"}
    ]
    if conflict_results:
        print("")
        print("Conflicts:")
        for result in conflict_results:
            if result.status == "symlink-conflict":
                print(
                    f"- {result.file.target} "
                    "(target is a symlink; the pack installs regular files only)"
                )
            else:
                print(f"- {result.file.target}")
        print("Re-run with --force to overwrite these files.")
        return 2

    if not args.dry_run and not args.skip_diff_check:
        diff_paths = [
            result.file.target
            for result in results
            if result.status not in {"conflict", "symlink-conflict", "preserved"}
        ]
        diff_status = run_diff_check(target, diff_paths)
        if diff_status != 0:
            return diff_status

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
