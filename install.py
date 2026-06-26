#!/usr/bin/env python3
"""Install the Trellis PR review loop extension pack into a Trellis repo."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "manifest.json"


@dataclass(frozen=True)
class PackFile:
    platform: str
    kind: str
    source: Path
    target: Path
    anchor: Path | None
    install: str


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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install trellis-review-pr skill and command adapters."
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
        choices=["gemini", "github", "opencode", "shared"],
        help=(
            "Install only this platform adapter. Repeat to select several. "
            "The shared skill is always installed unless platform filters exclude it."
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
        help="Overwrite existing files that differ from the pack templates.",
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
        if platform_filter and file.platform not in platform_filter:
            skipped.append((file, "platform not selected"))
            continue
        if file.install == "always" or install_all or platform_filter:
            selected.append(file)
            continue
        if file.anchor and not (target / file.anchor).exists():
            skipped.append((file, f"anchor {file.anchor} not present"))
            continue
        selected.append(file)

    return selected, skipped


def install_file(file: PackFile, target: Path, *, force: bool, dry_run: bool) -> str:
    source = file.source
    destination = target / file.target
    if not source.is_file():
        raise SystemExit(f"error: missing pack template {source}")

    new_content = source.read_bytes()
    if destination.exists():
        current = destination.read_bytes()
        if current == new_content:
            return "unchanged"
        if not force:
            return "conflict"
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        return "overwritten"

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return "created"


def run_diff_check(target: Path) -> int:
    try:
        result = subprocess.run(
            ["git", "diff", "--check"],
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
    target = Path(args.target).resolve()
    manifest, files = load_manifest()

    require_trellis_repo(target)
    selected, skipped = selected_files(files, target, args.platform, args.all)

    print(f"{manifest['name']} {manifest['version']}")
    print(f"target: {target}")
    if args.dry_run:
        print("mode: dry-run")

    results: list[tuple[PackFile, str]] = []
    for file in selected:
        status = install_file(file, target, force=args.force, dry_run=args.dry_run)
        results.append((file, status))

    for file, status in results:
        print(f"{status:11} {file.target}")
    for file, reason in skipped:
        print(f"skipped     {file.target} ({reason})")

    conflicts = [file for file, status in results if status == "conflict"]
    if conflicts:
        print("")
        print("Conflicts:")
        for file in conflicts:
            print(f"- {file.target}")
        print("Re-run with --force to overwrite these files.")
        return 2

    if not args.dry_run and not args.skip_diff_check:
        diff_status = run_diff_check(target)
        if diff_status != 0:
            return diff_status

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

