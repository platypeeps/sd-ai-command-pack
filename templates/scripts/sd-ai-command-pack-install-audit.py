#!/usr/bin/env python3
"""Audit an installed sd-ai-command-pack footprint in a target repository."""

from __future__ import annotations

import argparse
import fnmatch
import os
from pathlib import Path


INSTALLED_TARGETS_FILE = Path(".sd-ai-command-pack/installed-targets.txt")

# Files unique to the sd-ai-command-pack source checkout. A consumer repo never
# has all three (it receives shipped scripts, but not the installer, manifest, or
# template tree), so this is a safe signal that there is nothing installed to audit.
SOURCE_REPO_MARKERS = (
    Path("install.py"),
    Path("manifest.json"),
    Path("templates"),
)

PACK_FILE_PATTERNS = [
    ".agents/skills/sd-*/*",
    ".claude/commands/sd/*",
    ".cursor/commands/sd-*",
    ".gemini/commands/sd/*",
    ".github/prompts/sd-*.prompt.md",
    ".opencode/commands/sd-*.md",
    ".prism/rules.json",
    ".sd-ai-command-pack/*",
    "docs/SD_AI_COMMAND_PACK.md",
    "scripts/sd-ai-command-pack-*",
]

LOCAL_ALLOWED_PACK_FILES = {
    ".sd-ai-command-pack/pr-body-scope.json",
}

def is_disabled(value: str | None) -> bool:
    return (value or "").lower() in {"0", "false", "no", "skip", "none"}


def is_pack_source_checkout(root: Path) -> bool:
    return all((root / marker).exists() for marker in SOURCE_REPO_MARKERS)


def load_installed_targets(root: Path) -> tuple[set[str], list[str]]:
    targets_file = root / INSTALLED_TARGETS_FILE
    if not targets_file.exists():
        return set(), [f"{INSTALLED_TARGETS_FILE} is missing"]

    targets: set[str] = set()
    failures: list[str] = []
    for line_number, raw_line in enumerate(
        targets_file.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/") or ".." in Path(line).parts:
            failures.append(
                f"{INSTALLED_TARGETS_FILE}:{line_number} contains unsafe target {line!r}"
            )
            continue
        targets.add(line)

    if not targets:
        failures.append(f"{INSTALLED_TARGETS_FILE} has no installed targets")

    return targets, failures


def path_exists(root: Path, relative_path: Path) -> bool:
    path = root / relative_path
    return path.exists() or path.is_symlink()


def matches_pack_file(relative_path: str) -> bool:
    return any(fnmatch.fnmatchcase(relative_path, pattern) for pattern in PACK_FILE_PATTERNS)


def collect_pack_like_files(root: Path) -> list[str]:
    bases = [
        ".agents/skills",
        ".claude/commands",
        ".cursor/commands",
        ".gemini/commands",
        ".github/prompts",
        ".opencode/commands",
        ".prism",
        ".sd-ai-command-pack",
        "docs",
        "scripts",
    ]

    pack_like: list[str] = []
    for base in bases:
        base_path = root / base
        if not base_path.exists():
            continue
        for path in base_path.rglob("*"):
            if path.is_file() or path.is_symlink():
                relative_path = path.relative_to(root).as_posix()
                if matches_pack_file(relative_path):
                    pack_like.append(relative_path)

    return sorted(set(pack_like))


def audit_structural_state(root: Path, targets: set[str]) -> list[str]:
    failures: list[str] = []

    for target in sorted(targets):
        if not path_exists(root, Path(target)):
            failures.append(f"installed target is missing: {target}")

    allowed = set(targets) | LOCAL_ALLOWED_PACK_FILES
    for relative_path in collect_pack_like_files(root):
        if relative_path not in allowed:
            failures.append(
                "pack-like file is not listed in installed targets: "
                f"{relative_path}"
            )

    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit the installed sd-ai-command-pack footprint."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="target repository root to audit; defaults to the current directory",
    )
    return parser.parse_args()


def main() -> int:
    if is_disabled(os.environ.get("SD_AI_COMMAND_PACK_INSTALL_AUDIT")):
        print("warning: skipping install audit because SD_AI_COMMAND_PACK_INSTALL_AUDIT is disabled")
        return 0

    args = parse_args()
    root = Path(args.repo).resolve()

    if is_pack_source_checkout(root) and not (root / INSTALLED_TARGETS_FILE).exists():
        print(
            "skipping install audit: running inside the sd-ai-command-pack "
            "source checkout (no installed footprint to audit)"
        )
        return 0

    targets, failures = load_installed_targets(root)
    if targets:
        failures.extend(audit_structural_state(root, targets))

    if failures:
        for failure in failures:
            print(f"error: {failure}")
        return 1

    print(f"SD AI command pack install audit passed: {len(targets)} targets checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
