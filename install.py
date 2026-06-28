#!/usr/bin/env python3
"""Install the Trellis PR review loop extension pack into a Trellis repo."""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"
PLATFORMS = ("claude", "gemini", "github", "opencode", "shared")
ALWAYS_INSTALL = "always"
LEGACY_PACK_COMMANDS = frozenset(
    {"full-check", "housekeeping", "refresh-specs", "review-pr"}
)
FORCE_PRESERVED_TARGETS = frozenset({Path(".prism/rules.json")})


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
class LegacyCleanupResult:
    target: Path
    status: str
    reason: str | None = None


def load_manifest() -> tuple[dict, list[PackFile]]:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install Trellis review-cycle shared assets and command adapters."
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
            "Install only this platform adapter. Repeat to select several. "
            "Shared skills, scripts, Prism rules, and docs are always installed."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Install all adapters even if the platform directory is not present.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite existing files that differ from the pack templates, "
            "except .prism/rules.json."
        ),
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="With --force, save overwritten files next to the original with a .bak suffix.",
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
            "(.trellis/config.yaml not found)"
        )


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
        if file.install == ALWAYS_INSTALL:
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
    destination = target / file.target
    validate_resolved_target_path(target, destination, "target path")
    if path_is_occupied(destination) and not destination.is_file():
        raise SystemExit(f"error: target exists and is not a file: {file.target}")
    new_content = source.read_bytes()
    if destination.exists():
        current = destination.read_bytes()
        if current == new_content:
            return InstallResult(file, "unchanged")
        if file.target in FORCE_PRESERVED_TARGETS:
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
            shutil.copyfile(source, destination)
        return InstallResult(file, "overwritten", backup_path)

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return InstallResult(file, "created")


def legacy_adapter_target(file: PackFile) -> Path | None:
    command_name = file.target.stem.removeprefix("sd-").removesuffix(".prompt")
    if command_name not in LEGACY_PACK_COMMANDS:
        return None

    target = file.target.as_posix()
    if file.kind == "command" and "/commands/sd/" in target:
        return Path(target.replace("/commands/sd/", "/commands/trellis/"))
    if (
        file.platform == "github"
        and file.kind == "prompt"
        and file.target.name.startswith("sd-")
    ):
        return file.target.with_name(file.target.name.removeprefix("sd-"))
    return None


def legacy_adapter_contents(file: PackFile) -> set[bytes]:
    content = file.source.read_bytes()
    contents = {content}
    contents.add(content.replace(b'description = "SD: ', b'description = "Trellis: '))
    return contents


def cleanup_legacy_adapters(
    selected: list[PackFile],
    target: Path,
    *,
    dry_run: bool,
    force: bool,
) -> list[LegacyCleanupResult]:
    results: list[LegacyCleanupResult] = []
    seen: set[Path] = set()
    for file in selected:
        legacy_target = legacy_adapter_target(file)
        if legacy_target is None or legacy_target in seen:
            continue
        seen.add(legacy_target)

        destination = target / legacy_target
        validate_resolved_target_path(target, destination, "legacy adapter path")
        if not path_is_occupied(destination):
            continue
        if path_is_occupied(destination) and not (
            destination.is_file() or destination.is_symlink()
        ):
            results.append(
                LegacyCleanupResult(
                    legacy_target,
                    "legacy-conflict",
                    "target exists and is not a file",
                )
            )
            continue
        content_matches_template = (
            not destination.is_symlink()
            and destination.read_bytes() in legacy_adapter_contents(file)
        )
        if not force and not content_matches_template:
            reason = (
                "target is a symlink"
                if destination.is_symlink()
                else "content differs from pack template"
            )
            results.append(
                LegacyCleanupResult(
                    legacy_target,
                    "legacy-conflict",
                    reason,
                )
            )
            continue

        status = "would-remove" if dry_run else "removed"
        if not dry_run:
            destination.unlink()
            with contextlib.suppress(OSError):
                destination.parent.rmdir()
        results.append(LegacyCleanupResult(legacy_target, status))
    return results


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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.backup and not args.force:
        raise SystemExit("error: --backup requires --force")

    target = Path(args.target).resolve()
    manifest, files = load_manifest()

    validate_manifest(files)
    require_trellis_repo(target)
    selected, skipped = selected_files(files, target, args.platform, args.all)

    print(f"{manifest['name']} {manifest['version']}")
    print(f"target: {target}")
    if args.dry_run:
        print("mode: dry-run")

    results: list[InstallResult] = []
    for file in selected:
        result = install_file(
            file,
            target,
            force=args.force,
            dry_run=args.dry_run,
            backup=args.backup,
        )
        results.append(result)

    for result in results:
        print(f"{result.status:11} {result.file.target}")
        if result.backup:
            print(f"{'backup':11} {result.backup.relative_to(target)}")
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

    legacy_results = cleanup_legacy_adapters(
        selected,
        target,
        dry_run=args.dry_run,
        force=args.force,
    )
    for result in legacy_results:
        suffix = f" ({result.reason})" if result.reason else ""
        print(f"{result.status:11} {result.target}{suffix}")

    legacy_conflicts = [
        result for result in legacy_results if result.status == "legacy-conflict"
    ]
    if legacy_conflicts:
        print("")
        print("Legacy adapter conflicts:")
        for result in legacy_conflicts:
            suffix = f" ({result.reason})" if result.reason else ""
            print(f"- {result.target}{suffix}")
        print("Re-run with --force to remove these legacy adapter files.")
        return 2

    if not args.dry_run and not args.skip_diff_check:
        diff_paths = [
            result.file.target
            for result in results
            if result.status not in {"conflict", "preserved"}
        ]
        diff_paths.extend(
            result.target for result in legacy_results if result.status == "removed"
        )
        diff_status = run_diff_check(target, diff_paths)
        if diff_status != 0:
            return diff_status

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
