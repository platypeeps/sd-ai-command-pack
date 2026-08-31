"""Drift guard for the retired status selector contract.

`sd-status` and `sd-housekeeping` expose only `F-*` follow-up and `T-*` task
selectors; the separate Roadmap collection and its `R-*` selector were removed
by `07-23-status-untracked-roadmap-items`. This scans the shipped surface —
authored templates, docs, and the generated adapters and mirrors — for the
retired wording.

The scope is an allowlist of shipped roots, never a repo-wide grep with
exclusions: work items under `docs/work/` -- the planning records that
described and performed the removal -- legitimately name the retired selector
and must stay out of scope, which is why `docs` carries the one carve-out
below. Roots that stop existing (for example when the committed mirrors are
retired) are skipped rather than failing the scan.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The shipped surface is now `skills/` plus this repo's own docs. The nine
# roots this tuple used to name were the eighteen-platform render payload and
# the generated command surfaces; step 3e deleted them, and the installer
# renders from `skills/` at install time rather than from committed copies. So
# there is exactly one authored tree to scan, which is the point.
SHIPPED_ROOTS = (
    "skills",
    "docs",
)

# The only carve-out inside a shipped root: work items are the history of the
# removal, so quoting the retired selector is what they are for.
EXCLUDED_PREFIXES = ("docs/work/",)

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

# Precise retired wording only. Prose mentions of roadmap files stay legal
# (roadmap-file discovery is a live collector feature); a standalone
# "Roadmap" line — the retired report-collection heading — is banned.
RETIRED_PATTERNS = (
    ("F/T/R selector wording", re.compile(r"F/T/R")),
    ("retired R-* selector", re.compile(r"R-\*")),
    ("retired R-<n> selector instance", re.compile(r"\bR-\d")),
    ("separate Roadmap report collection", re.compile(r"^Roadmap$", re.MULTILINE)),
)

# `R-<n>` alone is a shape, not a claim. `R-4` is a perfectly ordinary
# identifier, and the fold brought sixty-four skills into a root this scan was
# written for when it held twelve status-adjacent ones: `sd-coherence-audit`
# numbers its findings by class letter -- `C-1` contradiction, `M-2` missing
# precedence, `V-3` vagueness, `B-2` bandaid, `R-4` redundancy -- so its ledger
# reference trips the instance pattern while saying nothing about status at all.
#
# The exemption is written as the *presence of a competing scheme*, not as the
# absence of status vocabulary. That direction matters: an allowlist keyed on
# "this file mentions sd-status" would have disarmed the guard over
# `skills/sd-plan/templates/prd.md`, an empty work-item template that mentions
# no command and is exactly where a retired selector could reappear unread. A
# file only earns the exemption by declaring all four sibling class letters,
# which is a thing one document does deliberately and a status surface never
# does by accident. The two unambiguous spellings above are never exempt --
# `F/T/R` and `R-*` are the contract's own wording and mean nothing else.
CONTEXT_REQUIRED = {"retired R-<n> selector instance"}
OWN_ID_SCHEME = tuple(re.compile(rf"\b{letter}-\d") for letter in "CMVB")


def declares_its_own_id_scheme(text: str) -> bool:
    return all(pattern.search(text) for pattern in OWN_ID_SCHEME)


def visible_to_git() -> set[str] | None:
    """Repo-relative paths git does not ignore, or None if git cannot answer.

    The scan below walks the filesystem, and one of its roots is `.claude/`.
    Agent worktrees live at `.claude/worktrees/<id>/` -- a whole second checkout
    of this repo, ignored via `.git/info/exclude` -- so rglob descended into it
    and reported the retired selector against archived work items belonging to
    another branch. The suite failed for a reason that had nothing to do with
    the working tree, which is the worst kind of red.

    Filtering through git fixes the class rather than that one directory: any
    ignored scratch path under a shipped root is now invisible here, and the
    project's own doctrine encourages worktrees, so this will recur otherwise.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {entry for entry in out.split("\0") if entry}


def shipped_files() -> list[Path]:
    visible = visible_to_git()
    files: list[Path] = []
    for root in SHIPPED_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative.startswith(EXCLUDED_PREFIXES):
                continue
            # None means git could not be consulted; scan everything rather
            # than silently checking nothing.
            if visible is not None and relative not in visible:
                continue
            files.append(path)
    return files


class SelectorContractDriftTests(unittest.TestCase):
    def test_shipped_surface_has_no_retired_selector_wording(self) -> None:
        findings: list[str] = []
        for path in shipped_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            exempt = declares_its_own_id_scheme(text)
            for label, pattern in RETIRED_PATTERNS:
                if label in CONTEXT_REQUIRED and exempt:
                    continue
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
        self.assertIn("skills/sd-status/SKILL.md", scanned)
        self.assertIn("skills/sd-plan/templates/prd.md", scanned)

    def test_the_narrowing_does_not_disarm_the_status_surface(self) -> None:
        """The exemption must not reach the surfaces the guard exists for.

        `R-<n>` goes unchecked only in a file declaring its own class-letter id
        scheme. That is worth nothing unless the surfaces which could actually
        regrow the retired selector fail to qualify -- so assert they do not,
        rather than trusting that they never will.
        """

        for relative in ("skills/sd-status/SKILL.md", "skills/sd-plan/templates/prd.md"):
            path = REPO_ROOT / relative
            with self.subTest(surface=relative):
                self.assertFalse(
                    declares_its_own_id_scheme(path.read_text(encoding="utf-8")),
                    "a status surface exempted from the R-<n> check",
                )

    def test_exactly_one_shipped_file_claims_the_exemption(self) -> None:
        """An exemption nobody counts is an exemption that spreads."""

        exempt = sorted(
            path.relative_to(REPO_ROOT).as_posix()
            for path in shipped_files()
            if declares_its_own_id_scheme(
                path.read_text(encoding="utf-8", errors="replace")
            )
        )
        self.assertEqual(
            exempt, ["skills/sd-coherence-audit/references/ledger-format.md"]
        )


if __name__ == "__main__":
    unittest.main()
