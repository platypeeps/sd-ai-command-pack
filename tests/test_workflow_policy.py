"""`WORKFLOW.md` is the policy, and the payload agrees with it.

Four things drift silently and each has a test here.

**The override keys.** The `CLAUDE.local.md` block the installer writes and the
Overrides section of `WORKFLOW.md` describe the same set of keys. Neither is
checked against a list written down beside it: the expectation is enumerated
from `sd_lib.MODES`, `sd_lib.CHECK_NAMES` and `sd_lib.CONSENT_KEY` in the
source, so adding a sixth key to the library and to only one of the two pages
fails here.

**The review table.** It appears in exactly two files and the two copies are
byte-identical. A cap edited in one place and not the other is the failure this
catches; a third copy is the failure the count catches.

**The planning review rule.** Exactly one file states it. Every other file that
needs it links to that one.

**The deleted second-model lane.** It is named nowhere in the governed tree.
`CHANGELOG.md` and `docs/work/` are history and are excluded by name, since the
archive is kept unchanged and holds every name the cuts removed.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_install  # noqa: E402
import sd_lib  # noqa: E402

WORKFLOW = REPO_ROOT / "WORKFLOW.md"
RULE = REPO_ROOT / ".claude/rules/sd-planning-adversarial-review.md"

#: What runs or governs. `docs/work/` and `CHANGELOG.md` are history.
GOVERNED = (
    "bin",
    "skills",
    "agents",
    "dashboard",
    "tests",
    ".claude",
    ".github",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "docs/spec",
)

TABLE_HEADER = "| Flow | Point | What it checks | Cap |"

SELF = "tests/test_workflow_policy.py"

#: An indented `key: value` line inside a fenced-free block.
KEY_LINE = re.compile(r"^ {4}([a-z][a-z_]*):")


def governed_grep(pattern: str) -> list[str]:
    """`git grep` over the governed tree, returning `path:line:text` rows."""
    result = subprocess.run(
        # This file is excluded: it quotes every pattern it searches for, and
        # a test that matches itself measures nothing.
        ["git", "grep", "-nIE", pattern, "--", *GOVERNED, f":(exclude){SELF}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line]


def expected_keys() -> set[str]:
    """The key set, enumerated from the library rather than from a list."""
    keys = {"mode"} if sd_lib.MODES else set()
    return keys | set(sd_lib.CHECK_NAMES) | {sd_lib.CONSENT_KEY}


def section(text: str, heading: str) -> str:
    """One `## ` section of a markdown page, heading excluded."""
    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = start
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    return "\n".join(lines[start:end])


def documented_keys(text: str) -> set[str]:
    """Every `    key:` line in an indented block."""
    return {m.group(1) for m in (KEY_LINE.match(line) for line in text.splitlines()) if m}


def overrides_keys(page: pathlib.Path) -> set[str]:
    return documented_keys(section(page.read_text(encoding="utf-8"), "## Overrides"))


def states_the_rule(path: pathlib.Path) -> bool:
    """A file states the rule when it carries both halves: the trigger and
    the table the caps come from. A file with one half is a pointer or a
    procedure, not a second statement."""
    text = path.read_text(encoding="utf-8")
    return TABLE_HEADER in text and "convergence" in text


def review_table(path: pathlib.Path) -> list[str]:
    """The contiguous pipe-block that starts at the review table's header."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(TABLE_HEADER)
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return lines[start:end]


class WorkflowPage(unittest.TestCase):
    def test_page_exists_at_the_repository_root(self):
        self.assertTrue(WORKFLOW.is_file(), "WORKFLOW.md is missing from the root")

    def test_page_states_the_named_sections(self):
        headings = {
            line.strip()
            for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        }
        for wanted in (
            "## Two flows, one spine",
            "## Defaults",
            "## Opt-in",
            "## Reviews",
            "## Advisory",
            "## Never in a shared repository",
            "## The path for a change",
            "## Modes",
            "## Overrides",
        ):
            self.assertIn(wanted, headings)

    def test_every_mode_is_documented(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for mode in sd_lib.MODES:
            self.assertIn(f"`{mode}`", text, f"WORKFLOW.md never names the {mode!r} mode")

    def test_the_installer_block_names_the_page(self):
        self.assertIn("WORKFLOW.md", sd_install.DEFAULT_BLOCK_BODY)

    def test_sd_help_names_the_page(self):
        skill = (REPO_ROOT / "skills/sd-help/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("WORKFLOW.md", skill)


class OverrideKeys(unittest.TestCase):
    """The two pages and the library agree, and none of the three is a list."""

    def test_the_page_documents_the_keys_the_library_reads(self):
        self.assertEqual(overrides_keys(WORKFLOW), expected_keys())

    def test_the_installer_block_writes_the_keys_the_library_reads(self):
        self.assertEqual(documented_keys(sd_install.DEFAULT_BLOCK_BODY), expected_keys())

    def test_a_sixth_key_on_one_side_alone_fails(self):
        """The guard against the guard: a key added to the library and to
        neither page must not pass, or the two tests above prove nothing."""
        with_a_sixth = expected_keys() | {"sixth"}
        self.assertNotEqual(overrides_keys(WORKFLOW), with_a_sixth)
        self.assertNotEqual(documented_keys(sd_install.DEFAULT_BLOCK_BODY), with_a_sixth)


class ReviewTable(unittest.TestCase):
    def test_the_table_appears_in_exactly_two_files(self):
        rows = governed_grep(re.escape(TABLE_HEADER))
        files = {row.split(":", 1)[0] for row in rows}
        self.assertEqual(files, {".claude/rules/sd-planning-adversarial-review.md"})
        self.assertTrue(TABLE_HEADER in WORKFLOW.read_text(encoding="utf-8"))

    def test_the_two_copies_are_identical(self):
        self.assertEqual(review_table(WORKFLOW), review_table(RULE))

    def test_the_table_has_a_cap_on_every_row(self):
        body = review_table(RULE)[2:]
        self.assertEqual(len(body), 4)
        for row in body:
            self.assertTrue(row.rsplit("|", 2)[1].strip(), f"no cap on row: {row}")


class OneStatementOfTheRule(unittest.TestCase):
    def test_exactly_one_file_states_the_planning_review_rule(self):
        rows = governed_grep(r"convergence boundary")
        mentions = sorted({row.split(":", 1)[0] for row in rows})
        statements = [f for f in mentions if states_the_rule(REPO_ROOT / f)]
        self.assertEqual(statements, [".claude/rules/sd-planning-adversarial-review.md"])

    def test_every_other_mention_links_to_that_one_file(self):
        rows = governed_grep(r"convergence boundary")
        mentions = sorted({row.split(":", 1)[0] for row in rows})
        for name in mentions:
            if name == ".claude/rules/sd-planning-adversarial-review.md":
                continue
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
            self.assertTrue(
                "sd-planning-adversarial-review.md" in text
                or name == ".claude/sd-ai-command-pack/planning-adversarial-review.md",
                f"{name} mentions the boundary and does not point at the rule",
            )

    def test_the_contract_is_reached_by_link_and_not_restated(self):
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(".claude/rules/sd-planning-adversarial-review.md", agents)
        self.assertNotIn("concern ledger", agents)


class ConditionalObligations(unittest.TestCase):
    """Criterion 8: the ledger and the sweep are gated on a `sensitive` path."""

    SITES = (
        ".claude/sd-ai-command-pack/planning-adversarial-review.md",
        "skills/sd-receive-review/SKILL.md",
    )

    def test_every_site_naming_the_ledger_names_the_gate(self):
        rows = governed_grep(r"concern ledger|cross-artifact")
        files = {row.split(":", 1)[0] for row in rows}
        self.assertEqual(files, set(self.SITES))
        for site in self.SITES:
            text = (REPO_ROOT / site).read_text(encoding="utf-8")
            self.assertIn("`sensitive`", text, f"{site} states the obligation unconditionally")


class DeletedLane(unittest.TestCase):
    def test_the_lane_page_is_gone(self):
        self.assertFalse((REPO_ROOT / "docs/planning-adversarial-review-codex.md").exists())

    def test_no_governed_file_names_the_lane(self):
        rows = governed_grep(r"second-model lane|codex (review )?lane")
        self.assertEqual(rows, [])

    def test_no_governed_file_references_the_deleted_page(self):
        rows = governed_grep(r"planning-adversarial-review-codex")
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
