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

OBSOLETE_PATHS = [
    Path(".agents/skills/trellis-review-pr/SKILL.md"),
    Path(".agents/skills/trellis-full-check/SKILL.md"),
    Path(".agents/skills/trellis-housekeeping/SKILL.md"),
    Path(".agents/skills/sd-refresh-specs/SKILL.md"),
    Path(".claude/commands/sd/refresh-specs.md"),
    Path(".cursor/commands/sd-refresh-specs.md"),
    Path(".gemini/commands/sd/refresh-specs.toml"),
    Path(".github/prompts/sd-refresh-specs.prompt.md"),
    Path(".opencode/commands/sd-refresh-specs.md"),
    Path(".opencode/commands/sd/review-pr.md"),
    Path(".opencode/commands/sd/full-check.md"),
    Path(".opencode/commands/sd/housekeeping.md"),
    Path("docs/TRELLIS_REVIEW_PR_PACK.md"),
    Path("scripts/trellis-full-check.sh"),
    Path("scripts/trellis-housekeeping.sh"),
    Path("scripts/sd-review-learnings.py"),
    Path("scripts/sd-command-pack-full-check.sh"),
    Path("scripts/sd-command-pack-housekeeping.sh"),
    Path("scripts/sd-command-pack-review-scope.sh"),
]

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

REPO_MAP_CANDIDATES = [
    Path("docs/repomix-map.md"),
    Path("docs/repo-map.md"),
    Path("docs/repospec.md"),
    Path("docs/REPOSPEC.md"),
    Path("REPOSPEC.md"),
]

OBSOLETE_REFERENCE_PATTERNS = [
    "trellis-review-pr-pack",
    ".agents/skills/trellis-review-pr/SKILL.md",
    ".agents/skills/trellis-full-check/SKILL.md",
    ".agents/skills/trellis-housekeeping/SKILL.md",
    ".agents/skills/sd-refresh-specs/SKILL.md",
    ".claude/commands/sd/refresh-specs.md",
    ".cursor/commands/sd-refresh-specs.md",
    ".gemini/commands/sd/refresh-specs.toml",
    ".github/prompts/sd-refresh-specs.prompt.md",
    ".opencode/commands/sd-refresh-specs.md",
    "scripts/trellis-full-check.sh",
    "scripts/trellis-housekeeping.sh",
    "scripts/sd-review-learnings.py",
    "sd-command-pack-",
]


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

    for obsolete_path in OBSOLETE_PATHS:
        if path_exists(root, obsolete_path):
            failures.append(f"obsolete pack artifact still exists: {obsolete_path.as_posix()}")

    allowed = set(targets) | LOCAL_ALLOWED_PACK_FILES
    for relative_path in collect_pack_like_files(root):
        if relative_path not in allowed:
            failures.append(
                "pack-like file is not listed in installed targets: "
                f"{relative_path}"
            )

    return failures


def audit_stale_references(root: Path, strict_references: bool) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []

    for candidate in REPO_MAP_CANDIDATES:
        path = root / candidate
        if not path.exists() or not path.is_file():
            continue

        content = path.read_text(encoding="utf-8", errors="replace")
        matched = [
            pattern for pattern in OBSOLETE_REFERENCE_PATTERNS if pattern in content
        ]
        if not matched:
            continue

        message = (
            f"{candidate.as_posix()} mentions obsolete pack names: "
            + ", ".join(sorted(set(matched)))
            + "; refresh the generated repository map or mark the history intentional"
        )
        if strict_references:
            failures.append(message)
        else:
            warnings.append(message)

    return failures, warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit the installed sd-ai-command-pack footprint."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="target repository root to audit; defaults to the current directory",
    )
    parser.add_argument(
        "--strict-references",
        action="store_true",
        help="fail when generated repository maps mention obsolete pack names",
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

    strict_references = args.strict_references or os.environ.get(
        "SD_AI_COMMAND_PACK_INSTALL_AUDIT_STRICT_REFS", ""
    ).lower() in {"1", "true", "yes", "required"}

    targets, failures = load_installed_targets(root)
    if targets:
        failures.extend(audit_structural_state(root, targets))

    reference_failures, warnings = audit_stale_references(root, strict_references)
    failures.extend(reference_failures)

    for warning in warnings:
        print(f"warning: {warning}")

    if failures:
        for failure in failures:
            print(f"error: {failure}")
        return 1

    print(f"SD AI command pack install audit passed: {len(targets)} targets checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
