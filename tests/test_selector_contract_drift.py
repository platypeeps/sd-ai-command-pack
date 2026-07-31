"""Drift guard for the retired status selector contract.

`sd-status` and `sd-housekeeping` expose only `F-*` follow-up and `T-*` task
selectors; the separate Roadmap collection and its `R-*` selector were removed
by `07-23-status-untracked-roadmap-items`. This scans the shipped surface —
authored templates, docs, and the generated adapters and mirrors — for the
retired wording.

The scope is an allowlist of shipped roots, never a repo-wide grep with
exclusions: `.trellis/` task records, the archive, and the journal
legitimately describe the removal and must stay out of scope. Roots that stop
existing (for example when the committed mirrors are retired) are skipped
rather than failing the scan.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SHIPPED_ROOTS = (
    "templates",
    "docs",
    ".agents",
    ".claude",
    ".codex",
    ".gemini",
    ".opencode",
    ".github/prompts",
    ".github/command-sources",
)

TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

# Precise retired wording only: bare "Roadmap" stays legal because
# roadmap-file discovery is a live feature of the status collector.
RETIRED_PATTERNS = (
    ("F/T/R selector wording", re.compile(r"F/T/R")),
    ("retired R-* selector", re.compile(r"R-\*")),
    ("retired R-<n> selector instance", re.compile(r"\bR-\d")),
    ("separate Roadmap report collection", re.compile(r"^Roadmap$", re.MULTILINE)),
)


def shipped_files() -> list[Path]:
    files: list[Path] = []
    for root in SHIPPED_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        files.extend(
            path
            for path in sorted(base.rglob("*"))
            if path.is_file() and path.suffix in TEXT_SUFFIXES
        )
    return files


class SelectorContractDriftTests(unittest.TestCase):
    def test_shipped_surface_has_no_retired_selector_wording(self) -> None:
        findings: list[str] = []
        for path in shipped_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for label, pattern in RETIRED_PATTERNS:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    relative = path.relative_to(REPO_ROOT).as_posix()
                    findings.append(f"{relative}:{line}: {label}")
        self.assertEqual(
            findings,
            [],
            "retired selector contract wording found on the shipped surface:\n"
            + "\n".join(findings),
        )

    def test_scan_covers_the_authored_status_surface(self) -> None:
        scanned = {path.relative_to(REPO_ROOT).as_posix() for path in shipped_files()}
        self.assertIn("templates/.agents/skills/sd-status/SKILL.md", scanned)
        self.assertIn("templates/.agents/skills/sd-housekeeping/SKILL.md", scanned)


if __name__ == "__main__":
    unittest.main()
