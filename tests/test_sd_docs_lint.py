"""Green and red fixtures for each rule in bin/sd-docs-lint."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
from types import ModuleType
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def in_directory(path: pathlib.Path):
    """Run the body with `path` as the working directory, then put it back."""

    previous = pathlib.Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)

LINT_PATH = REPO_ROOT / "bin" / "sd-docs-lint"


def load_lint() -> ModuleType:
    """Import the executable, which has no .py suffix to import by name."""
    spec = importlib.util.spec_from_loader(
        "sd_docs_lint",
        importlib.machinery.SourceFileLoader("sd_docs_lint", str(LINT_PATH)),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lint = load_lint()

GOOD_PRD = """---
title: A workable item
status: ready
created: 2026-08-29
---

# PRD

## Acceptance criteria

- [x] the thing works
"""

GOOD_DECISION = """---
title: Use JSON for pack-owned config
status: accepted
date: 2026-08-29
---

## Decision

Every pack-owned config file is JSON.
"""


class LintFixture(unittest.TestCase):
    """A throwaway repository laid out the way the rules expect it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = pathlib.Path(self._tmp.name)
        # A git repository, because rule 7 enumerates tracked markdown rather
        # than walking the tree: an untracked scratch file is not a document
        # this repository publishes, and the rule declines to read one.
        self.git("init", "-q")
        self.work = self.repo / "docs" / "work"
        self.spec = self.repo / "docs" / "spec"
        self.write_item("2026-08-29-a-workable-item", GOOD_PRD)
        self.write_spec("backend", ["quality.md"])

    def write_item(self, name: str, prd: str, *, month: str | None = None) -> pathlib.Path:
        parent = self.work / "archive" / month if month else self.work
        item = parent / name
        item.mkdir(parents=True, exist_ok=True)
        (item / "prd.md").write_text(prd, encoding="utf-8")
        return item

    def write_spec(self, area: str, pages: list[str], *, index: str | None = None) -> None:
        directory = self.spec / area
        directory.mkdir(parents=True, exist_ok=True)
        for page in pages:
            (directory / page).write_text(f"# {page}\n", encoding="utf-8")
        body = index
        if body is None:
            links = "\n".join(f"- [{page}](./{page})" for page in pages)
            body = f"# {area}\n\n{links}\n"
        (directory / "index.md").write_text(body, encoding="utf-8")

    def git(self, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True, capture_output=True
        )

    def run_lint(
        self, pr_body: str | None = None, changed: list[str] | None = None, body_only: bool = False
    ) -> lint.Report:
        # Staged, not committed: `ls-files` reads the index, and every test
        # here writes its fixture immediately before asking for a verdict.
        self.git("add", "-A")
        mode = {"body_only": True} if body_only else {}
        return lint.run(self.repo, "docs/work", "docs/spec", "docs/decisions", pr_body, changed, **mode)

    def assert_clean(self) -> None:
        report = self.run_lint()
        self.assertEqual(report.failures, [])

    def notes(self) -> str:
        """Every note one run printed, joined. What a rule says it did."""
        return "\n".join(self.run_lint().notes)

    def cited_item(self) -> pathlib.Path:
        item = self.write_item("2026-08-29-a-cited-item", GOOD_PRD)
        (item / "design.md").write_text(
            "# design\n\nThe ladder is at `prd.md:3`.\n", encoding="utf-8"
        )
        return item

    def record(self) -> tuple[int, list[tuple[str, str, str, str]]]:
        return lint.write_citation_manifest(self.cited_item(), self.work)[:2]

    def assert_fails(
        self, needle: str, pr_body: str | None = None, changed: list[str] | None = None
    ) -> list[str]:
        report = self.run_lint(pr_body, changed)
        joined = "\n".join(report.failures)
        self.assertIn(needle, joined)
        return report.failures


class Rule1ShapeTests(LintFixture):
    def test_green(self) -> None:
        self.write_item(
            "2026-07-04-an-archived-item",
            GOOD_PRD.replace("created: 2026-08-29", "created: 2026-07-04"),
            month="2026-07",
        )
        self.assert_clean()

    def test_red_directory_name_is_not_dated(self) -> None:
        self.write_item("no-date-here", GOOD_PRD)
        self.assert_fails("named <YYYY-MM-DD>-<slug>")

    def test_red_missing_prd(self) -> None:
        (self.work / "2026-08-30-empty").mkdir(parents=True)
        self.assert_fails("every work item has a prd.md")

    def test_red_missing_frontmatter(self) -> None:
        self.write_item("2026-08-30-bare", "# PRD\n\n## Acceptance criteria\n")
        self.assert_fails("opens with a --- frontmatter block")

    def test_red_unknown_status(self) -> None:
        self.write_item(
            "2026-08-30-odd",
            GOOD_PRD.replace("status: ready", "status: pondering"),
        )
        self.assert_fails("'pondering' is not one of")

    def test_red_created_disagrees_with_the_directory(self) -> None:
        self.write_item("2026-08-30-drifted", GOOD_PRD)
        self.assert_fails("disagrees with the directory date")

    def test_red_stray_file_in_a_work_item(self) -> None:
        (self.work / "2026-08-29-a-workable-item" / "task.json").write_text("{}", encoding="utf-8")
        self.assert_fails("prd.md, design.md, implement.md and .citations.tsv only")

    def test_red_archive_bucket_is_not_a_month(self) -> None:
        (self.work / "archive" / "july").mkdir(parents=True)
        self.assert_fails("archive buckets are named YYYY-MM")

    def test_green_item_key_names_a_row(self) -> None:
        """sd:994. A folder written for a task or followup row names it as
        `item: sd:<id>`; the key is optional and its form is `sd:` then digits."""
        self.write_item(
            "2026-08-29-a-keyed-item",
            GOOD_PRD.replace("created: 2026-08-29\n", "created: 2026-08-29\nitem: sd:361\n"),
        )
        self.assert_clean()

    def test_red_item_key_is_not_sd_then_digits(self) -> None:
        for value in ("361", "sd:x", "sd:", "SD:361"):
            with self.subTest(value=value):
                self.write_item(
                    "2026-08-29-a-keyed-item",
                    GOOD_PRD.replace(
                        "created: 2026-08-29\n", f"created: 2026-08-29\nitem: {value}\n"),
                )
                failures = self.assert_fails("is not sd: followed by digits")
                self.assertTrue(
                    any(f"item {value!r}" in f and "a-keyed-item/prd.md" in f for f in failures),
                    failures,
                )


class Rule1StatusSourceTests(LintFixture):
    """The sign of rule 1's status check inverts on `docs/work/.status-source`.

    #767 inverted it and tested nothing: a `row` root with a `status:` line
    left in an active `prd.md` failed the lint, and no test said so, which is
    how sd:382 found the contract prose and the code disagreeing with nothing
    to arbitrate. Each case here is one cell of the sign table -- marker or
    none, active or archived, line or no line.
    """

    RETIRED_PRD = GOOD_PRD.replace("status: ready\n", "")

    def setUp(self) -> None:
        super().setUp()
        # A `row` marker opens the one database through `$HOME`. An empty home
        # holds none, so the read answers "no database" and asks git, which
        # has no remote here to fetch from -- the operator's rows are never
        # consulted and nothing leaves the machine.
        home = self.repo / "home"
        home.mkdir()
        patched = mock.patch.dict(os.environ, {"HOME": str(home)})
        patched.start()
        self.addCleanup(patched.stop)

    def mark(self, word: str) -> None:
        (self.work / lint.sd_lib.STATUS_MARKER).write_text(word + "\n", encoding="utf-8")

    def test_green_row_root_with_a_retired_active_prd(self) -> None:
        self.mark("row")
        self.write_item("2026-08-29-a-workable-item", self.RETIRED_PRD)
        self.assert_clean()

    def test_red_row_root_with_a_status_line_in_an_active_prd(self) -> None:
        self.mark("row")
        failures = self.assert_fails("the row is the status; prd.md carries no status: line")
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("2026-08-29-a-workable-item/prd.md", failures[0])

    def test_green_row_root_with_a_status_line_only_under_the_archive(self) -> None:
        self.mark("row")
        self.write_item("2026-08-29-a-workable-item", self.RETIRED_PRD)
        self.write_item(
            "2026-07-04-an-archived-item",
            GOOD_PRD.replace("created: 2026-08-29", "created: 2026-07-04"),
            month="2026-07",
        )
        self.assert_clean()

    def test_green_unmarked_root_with_a_status_line(self) -> None:
        self.assertFalse((self.work / lint.sd_lib.STATUS_MARKER).exists())
        self.assert_clean()

    def test_green_file_root_with_a_status_line(self) -> None:
        self.mark("file")
        self.assert_clean()


class Rule2ReadyTests(LintFixture):
    def test_green_in_progress_with_a_branch(self) -> None:
        self.write_item(
            "2026-08-30-running",
            GOOD_PRD.replace("status: ready", "status: in_progress\nbranch: task/08-30-running")
            .replace("created: 2026-08-29", "created: 2026-08-30"),
        )
        self.assert_clean()

    def test_green_planning_item_needs_no_acceptance_criteria(self) -> None:
        self.write_item(
            "2026-08-30-idea",
            "---\ntitle: An idea\nstatus: planning\ncreated: 2026-08-30\n---\n\n# PRD\n",
        )
        self.assert_clean()

    def test_red_missing_acceptance_criteria(self) -> None:
        self.write_item(
            "2026-08-30-vague",
            "---\ntitle: Vague\nstatus: ready\ncreated: 2026-08-30\n---\n\n# PRD\n",
        )
        self.assert_fails("states acceptance criteria")

    def test_red_open_blocking_line(self) -> None:
        self.write_item(
            "2026-08-30-blocked",
            GOOD_PRD.replace("created: 2026-08-29", "created: 2026-08-30")
            + "\nBLOCKING: the API is not designed yet.\n",
        )
        self.assert_fails("no open BLOCKING line")

    def test_red_open_blocking_line_as_a_list_item(self) -> None:
        self.write_item(
            "2026-08-30-blocked-bullet",
            GOOD_PRD.replace("created: 2026-08-29", "created: 2026-08-30")
            + "\n- BLOCKING: the API is not designed yet.\n",
        )
        self.assert_fails("no open BLOCKING line")

    def test_green_prose_that_quotes_the_marker(self) -> None:
        """The word inside a sentence is a record, not an open blocker.

        An item's own log discusses blocking findings; matching the token
        anywhere on a line meant such an item could never be `in_progress`.
        """
        self.write_item(
            "2026-08-30-discusses",
            GOOD_PRD.replace("created: 2026-08-29", "created: 2026-08-30")
            + "\nRule 2 checks that no open `BLOCKING:` line remains.\n",
        )
        self.assert_clean()

    def test_red_in_progress_without_a_branch(self) -> None:
        self.write_item(
            "2026-08-30-adrift",
            GOOD_PRD.replace("status: ready", "status: in_progress").replace(
                "created: 2026-08-29", "created: 2026-08-30"
            ),
        )
        self.assert_fails("records the branch it lives on")

    def test_red_the_note_says_how_many_items_rule_2_actually_checked(self) -> None:
        """Backbone item sd:5. The item total was never rule 2's coverage.

        Rule 2's three checks run on `ready` and `in_progress` items only, and
        the note it shares with rule 1 counts every item on disk. On this
        repository that reads `checked 497 item(s)` for a rule that ran on
        two. `status_source_note` describes the mechanism that narrows it,
        which is not the same as saying how far: one number cannot tell 497 of
        497 from 2 of 497, and both print `clean`.

        Here: one `ready` fixture item, one `planning` item beside it.
        """
        self.write_item(
            "2026-08-30-idea",
            "---\ntitle: An idea\nstatus: planning\ncreated: 2026-08-30\n---\n\n# PRD\n",
        )
        report = self.run_lint()
        self.assertEqual(report.failures, [])
        self.assertIn(
            "rules 1-2 work items: checked 2 item(s), 1 of them workable by rule 2",
            "\n".join(report.notes),
        )


class Rule2StatusSourceTests(LintFixture):
    """The run says where rule 2 read its statuses, because the two sources
    check different item sets and print the same `clean`."""

    def source_note(self) -> str:
        report = self.run_lint()
        return next(note for note in report.notes if note.startswith("rule 2 status source:"))

    def test_no_marker_reads_the_line(self) -> None:
        self.assertIn("the status: line in prd.md", self.source_note())

    def test_an_unreadable_marker_is_not_reported_as_the_line(self) -> None:
        (self.work / ".status-source").write_text("column\n", encoding="utf-8")
        note = self.source_note()
        self.assertIn("nowhere", note)
        self.assertIn("'column'", note)
        self.assertNotIn("status: line", note)

    def test_a_row_marker_with_no_database_says_git_and_names_the_gap(self) -> None:
        (self.work / ".status-source").write_text("row\n", encoding="utf-8")
        # An empty HOME is a machine with the library and no database: the
        # CI lint job, and any checkout that never ran `sd-db.sh init`.
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home}):
            note = self.source_note()
        self.assertIn("git, not the row", note)
        self.assertIn("rule 2 does not check it", note)


class Rule3DecisionTests(LintFixture):
    def write_decision(self, name: str, body: str) -> None:
        directory = self.repo / "docs" / "decisions"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(body, encoding="utf-8")

    def test_green(self) -> None:
        self.write_decision("2026-08-29-json-config.md", GOOD_DECISION)
        self.assert_clean()

    def test_green_absent_directory_is_not_a_failure(self) -> None:
        report = self.run_lint()
        self.assertEqual(report.failures, [])
        self.assertTrue(any("rule 3" in note for note in report.notes))

    def test_red_undated_filename(self) -> None:
        self.write_decision("json-config.md", GOOD_DECISION)
        self.assert_fails("named <YYYY-MM-DD>-<slug>.md")

    def test_red_unknown_status(self) -> None:
        self.write_decision(
            "2026-08-29-json-config.md", GOOD_DECISION.replace("accepted", "maybe")
        )
        self.assert_fails("'maybe' is not one of")

    def test_red_date_disagrees_with_filename(self) -> None:
        self.write_decision(
            "2026-08-30-json-config.md", GOOD_DECISION
        )
        self.assert_fails("disagrees with the filename date")

    def test_red_no_decision_section(self) -> None:
        self.write_decision(
            "2026-08-29-json-config.md", GOOD_DECISION.replace("## Decision", "## Notes")
        )
        self.assert_fails("states its decision under a Decision heading")

    def test_red_the_count_is_records_checked_not_files_enumerated(self) -> None:
        """Backbone item sd:5, smallest of the set.

        An `index.md` is a table of contents, and skipping it is right.
        Counting it as a checked record is not: `len(records)` was the
        enumeration, and reporting an enumeration as coverage is how a rule
        claims to have checked what it passed over. One record, one index,
        and the note has to say one.
        """
        self.write_decision("2026-08-29-json-config.md", GOOD_DECISION)
        self.write_decision("index.md", "# decisions\n\n- one\n")
        report = self.run_lint()
        self.assertEqual(report.failures, [])
        self.assertIn(
            "rule 3 decision shape: checked 1 record(s), skipping 1 index.md",
            "\n".join(report.notes),
        )


class Rule4SpecIndexTests(LintFixture):
    def test_green(self) -> None:
        self.write_spec("frontend", ["adapters.md", "layout.md"])
        self.assert_clean()

    def test_red_missing_index(self) -> None:
        directory = self.spec / "tooling"
        directory.mkdir(parents=True)
        (directory / "lanes.md").write_text("# lanes\n", encoding="utf-8")
        self.assert_fails("every spec directory has an index.md")

    def test_red_index_does_not_link_a_sibling(self) -> None:
        self.write_spec("tooling", ["lanes.md", "gates.md"], index="# tooling\n\n- [lanes](./lanes.md)\n")
        self.assert_fails("index does not link gates.md")


class Rule5PullRequestLinkTests(LintFixture):
    def test_green_work_line_resolving_to_an_item(self) -> None:
        report = self.run_lint("Work: docs/work/2026-08-29-a-workable-item\n")
        self.assertEqual(report.failures, [])

    def test_database_associations_pass_without_claiming_verified_rows(self) -> None:
        for value in ("sd:1", "sd:36", "sd:999999999999999999999999999999"):
            with self.subTest(value=value):
                report = self.run_lint(f"Work: {value}\n")
                self.assertEqual(report.failures, [])
                note = next(note for note in report.notes if "rule 5 PR link:" in note)
                self.assertIn(f"database association {value}", note)
                self.assertIn("row existence, ownership and delivery require sd-ship verification", note)

    def test_malformed_database_associations_refuse(self) -> None:
        for value in ("sd:", "sd:0", "sd:01", "sd:-1", "sd:+1", "sd:1.0",
                      "sd: 1", "sd:1 extra", "sd:1/other", "sd:١", "SD:1"):
            with self.subTest(value=value):
                self.assert_fails("must use sd:<positive integer>", pr_body=f"Work: {value}\n")

    def test_database_association_does_not_hide_another_work_line(self) -> None:
        self.assert_fails("exactly one is allowed", pr_body=(
            "Work: sd:36\nWork: docs/work/2026-08-29-a-workable-item\n"))

    def test_database_association_does_not_bypass_work_directory_checks(self) -> None:
        (self.work / "2026-08-30-empty").mkdir()
        self.assert_fails("every work item has a prd.md", pr_body="Work: sd:36\n")

    def test_green_no_work_line_claims_no_item(self) -> None:
        """A change with no item carries no line, and is not asked for one.

        Criterion 10 removes the `none - <reason>` form rather than replacing
        it, so the absence of a `Work:` line is the whole of how a change says
        it advances no item. There is no placeholder to write and none to
        forget, and a body that says nothing cannot say it wrongly.
        """
        report = self.run_lint("Fixes a typo.\n")
        self.assertEqual(report.failures, [])

    def test_red_two_work_lines(self) -> None:
        self.assert_fails(
            "exactly one is allowed",
            pr_body=(
                "Work: docs/work/2026-08-29-a-workable-item\n"
                "Work: docs/work/2026-08-29-another-item\n"
            ),
        )

    def test_red_empty_work_line(self) -> None:
        self.assert_fails("Work: line is empty", pr_body="Work: \t\n")

    def test_red_the_none_form_is_no_longer_an_escape(self) -> None:
        """`none - <reason>` is now a path that does not resolve, and fails.

        The form used to pass rule 5 by naming no item. A body still carrying
        it is stale rather than exempt, so it has to fail rather than quietly
        keep working -- otherwise the form survives in every body written
        before this change and criterion 10 is met only in the lint's source.
        """
        self.assert_fails(
            "is not a path under",
            pr_body="Work: none - typo fix in a comment\n",
        )

    def test_red_a_bare_none_is_a_path_that_does_not_resolve(self) -> None:
        self.assert_fails("is not a path under", pr_body="Work: none\n")

    def test_red_a_bare_item_name_is_an_unresolved_path(self) -> None:
        """31(c): `Work: nonexistent-item` fails as a path, not as a reason.

        The two messages send the author to different places. "is not a path
        under" says the value names nothing; the missing-reason refusal says
        the value is fine but under-explained. An author given the second for
        a typo goes looking for a sentence to write instead of for an item
        that exists.

        The bug was a `startswith("none")` test, so every value beginning with
        those four letters took the missing-reason branch. That is why the
        spellings here start with them: `nonexistent-item` is the criterion's
        own example and `nonesuch` is the shortest one, and a fix that
        special-cases the first while leaving the prefix test in place fails
        on the second. The plain `notaname` is the control -- it shares no
        prefix with the bug and must give the same message, or the branch is
        still deciding by spelling.
        """
        for value in ("nonexistent-item", "nonesuch", "notaname"):
            with self.subTest(value=value):
                self.assert_fails("is not a path under", pr_body=f"Work: {value}\n")

    def test_red_item_does_not_exist(self) -> None:
        self.assert_fails(
            "does not resolve to a work item", pr_body="Work: docs/work/2026-01-01-ghost\n"
        )

    def test_red_path_outside_the_work_directory(self) -> None:
        self.assert_fails("is not a path under", pr_body="Work: docs/spec/backend\n")

    def test_red_path_traversing_outside_the_work_directory(self) -> None:
        self.assert_fails("is not a path under", pr_body="Work: docs/work/../spec/backend\n")

    def test_red_symlink_outside_the_work_directory(self) -> None:
        (self.work / "2026-08-30-escape").symlink_to(self.spec / "backend", target_is_directory=True)
        self.assert_fails("is not a path under", pr_body="Work: docs/work/2026-08-30-escape\n")

    def test_red_work_root_is_not_an_item(self) -> None:
        self.assert_fails("does not resolve to a work item", pr_body="Work: docs/work\n")

    def test_green_non_final_slice_with_later_acceptance_criteria_pending(self) -> None:
        item = self.write_item(
            "2026-08-29-a-workable-item",
            GOOD_PRD.replace(
                "- [x] the thing works",
                "- [x] database reads work\n- [ ] dashboard controls work",
            ),
        )
        (item / "implement.md").write_text(
            "# Implementation\n\n- [x] Add database reads\n- [ ] Add dashboard controls\n",
            encoding="utf-8",
        )
        report = self.run_lint(
            "Add database reads; dashboard controls follow in the next slice.\n\n"
            "Work: docs/work/2026-08-29-a-workable-item\n"
        )
        self.assertEqual(report.failures, [])


#: A policy file with the two classes this repository declares, in the shape
#: rule 8 reads: a row per class, the line in the first cell, the globs in the
#: second. The prose around the table is not what the rule reads.
SCOPE_POLICY = """# Repository Copilot Instructions

## Where to spend review budget

- A diff that touches a path in the table below carries the matching line.

| Scope line | Paths that demand it | Why |
|---|---|---|
| `CI/review scope:` | `.github/**`, `actions/**`, `Makefile` | What CI runs and a reviewer reads. |
| `Automation scope:` | `bin/sd_setup_github.py` | What writes automation elsewhere. |
"""

#: The four paths #968 changed, the pull request whose body ran clean without
#: a scope line and raised sd:931.
PR_968_PATHS = [
    ".github/scripts/check-zizmor-personas.py",
    ".github/workflows/tests.yml",
    "Makefile",
    "tests/test_zizmor_persona_decisions.py",
]


class Rule8PullRequestScopeTests(LintFixture):
    """A diff touching a scope class carries that class's line in the body.

    `bin/sd-docs-lint --pr-body` ran clean on #968, whose diff touched
    `.github/workflows/tests.yml` and whose body carried no scope line; the
    template asked for one and only the reviewer noticed (sd:931). The
    classes come from `.github/copilot-instructions.md`, so the fixture
    writes that file and the rule is asserted against what it wrote.
    """

    def policy(self, text: str = SCOPE_POLICY) -> None:
        path = self.repo / lint.SCOPE_POLICY
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def rule_8(self, report: lint.Report) -> str:
        return "\n".join(note for note in report.notes if note.startswith("rule 8"))

    def test_no_policy_file_is_no_scope_classes_and_is_said(self) -> None:
        # A consumer repository has no Copilot instructions of this shape;
        # sd-ship runs this linter there, and a rule with nothing to read
        # says so rather than failing every pull request in it.
        report = self.run_lint("Work: sd:1\n", changed=PR_968_PATHS)
        self.assertEqual(report.failures, [])
        self.assertIn("declares no scope classes; not run", self.rule_8(report))

    def test_a_policy_file_that_will_not_read_is_a_failure_not_an_absent_policy(self) -> None:
        # Absent and unreadable are two answers, not one. A directory in the
        # policy file's place read as "this repository declares no scope
        # classes" and passed a diff that file may well have classified, so
        # the rule failed open (#972 review).
        (self.repo / lint.SCOPE_POLICY).mkdir(parents=True, exist_ok=True)
        failures = self.assert_fails(
            "rule 8 cannot read the scope policy: IsADirectoryError",
            pr_body="Work: sd:876\n\nNo scope line anywhere.\n",
            changed=PR_968_PATHS,
        )
        self.assertEqual(len(failures), 1, failures)

    def test_a_policy_file_that_is_not_utf8_fails_by_name(self) -> None:
        # The other half of the same guard: bytes that do not decode are an
        # unreadable policy, reported by name rather than as a traceback.
        # Rule 8 alone, because rule 7 reads every tracked file and this
        # fixture is deliberately not text.
        path = self.repo / lint.SCOPE_POLICY
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"| `CI/review scope:` | `\xff.github/**` | why |\n")
        report = lint.Report()
        lint.check_pr_scope(self.repo, "Work: sd:876\n", PR_968_PATHS, report)
        self.assertIn(
            "rule 8 cannot read the scope policy: UnicodeDecodeError",
            "\n".join(report.failures),
        )

    def test_a_policy_symlink_to_nothing_is_unreadable_and_not_absent(self) -> None:
        # `exists()` is False for a broken symlink, which is exactly the shape
        # that would slip back into the absent-policy note.
        path = self.repo / lint.SCOPE_POLICY
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to("copilot-instructions-that-are-not-here.md")
        self.assert_fails(
            "rule 8 cannot read the scope policy: FileNotFoundError",
            pr_body="Work: sd:876\n\nNo scope line anywhere.\n",
            changed=PR_968_PATHS,
        )

    def test_no_body_is_not_run_whatever_changed(self) -> None:
        self.policy()
        report = self.run_lint(None, changed=PR_968_PATHS)
        self.assertEqual(report.failures, [])
        self.assertIn("no --pr-body supplied, not run", self.rule_8(report))

    def test_red_the_968_diff_with_no_scope_line_names_the_path_and_the_line(self) -> None:
        # The fail-first case. The path named is the first one the class
        # claims, and the line named is the one the body must carry.
        self.policy()
        failures = self.assert_fails(
            'touches .github/scripts/check-zizmor-personas.py, which '
            '.github/copilot-instructions.md puts under "CI/review scope:", '
            'and carries no "CI/review scope:" line',
            pr_body="Work: sd:876\n\nNo scope line anywhere.\n",
            changed=PR_968_PATHS,
        )
        self.assertEqual(len(failures), 1, failures)

    def test_green_the_line_on_its_own_satisfies_the_class(self) -> None:
        self.policy()
        report = self.run_lint(
            "Work: sd:876\n\nCI/review scope: one step added to the lint job.\n",
            changed=PR_968_PATHS,
        )
        self.assertEqual(report.failures, [])
        self.assertIn('demands "CI/review scope:", and the body carries it', self.rule_8(report))

    def test_green_a_markdown_heading_is_the_line_on_its_own(self) -> None:
        # How #968 wrote it once asked: `## CI/review scope:`.
        self.policy()
        report = self.run_lint("Work: sd:876\n\n## CI/review scope:\n\nThe CI surface.\n",
                               changed=PR_968_PATHS)
        self.assertEqual(report.failures, [])

    def test_green_a_bold_or_list_form_is_the_line_on_its_own(self) -> None:
        self.policy()
        for form in ("**CI/review scope:** the lint job\n", "- CI/review scope: the lint job\n",
                     "> ci/review scope: the lint job\n"):
            with self.subTest(form=form):
                report = self.run_lint(f"Work: sd:876\n\n{form}", changed=PR_968_PATHS)
                self.assertEqual(report.failures, [], form)

    def test_red_a_mention_in_prose_is_not_the_line(self) -> None:
        # The template asks for the line on its own; a sentence that names
        # the heading has not declared a scope.
        self.policy()
        self.assert_fails(
            'carries no "CI/review scope:" line',
            pr_body="Work: sd:876\n\nRemember to add the CI/review scope: line later.\n",
            changed=PR_968_PATHS,
        )

    def test_red_another_class_s_line_does_not_stand_in(self) -> None:
        self.policy()
        self.assert_fails(
            'carries no "CI/review scope:" line',
            pr_body="Work: sd:876\n\nAutomation scope: none.\n",
            changed=PR_968_PATHS,
        )

    def test_each_touched_class_is_demanded_and_failed_on_its_own(self) -> None:
        self.policy()
        failures = self.assert_fails(
            'carries no "Automation scope:" line',
            pr_body="Work: sd:876\n\nCI/review scope: the workflow.\n",
            changed=[".github/workflows/tests.yml", "bin/sd_setup_github.py"],
        )
        self.assertEqual(len(failures), 1, failures)
        self.assertNotIn("CI/review", "\n".join(failures))

    def test_green_a_path_in_no_class_demands_nothing(self) -> None:
        self.policy()
        report = self.run_lint("Work: sd:1\n", changed=["bin/sd_lib.py", "docs/work/x/prd.md"])
        self.assertEqual(report.failures, [])
        self.assertIn("2 changed path(s) from --changed, 0 class(es) demanded", self.rule_8(report))

    def test_the_glob_crosses_directories(self) -> None:
        # `.github/**` claims `.github/scripts/x.py`, two levels down; a
        # `*` that stopped at `/` would leave the scripts CI runs unclaimed.
        self.policy()
        self.assert_fails('touches .github/scripts/deep/er/x.py',
                          pr_body="Work: sd:1\n", changed=[".github/scripts/deep/er/x.py"])
        self.assertTrue(lint.matches_scope("Makefile", "Makefile"))
        self.assertFalse(lint.matches_scope("sub/Makefile", "Makefile"))

    def test_the_classes_are_read_from_the_table_and_not_from_the_linter(self) -> None:
        # A row added to the policy is a class the linter enforces, with no
        # edit here: the enumeration is the table's, which is the point of
        # sd:931's "not retyped in the linter".
        self.policy(SCOPE_POLICY + "| `Kitchen scope:` | `kitchen/**` | Everything and the sink. |\n")
        self.assert_fails(
            'touches kitchen/sink.py, which .github/copilot-instructions.md puts under '
            '"Kitchen scope:", and carries no "Kitchen scope:" line',
            pr_body="Work: sd:1\n", changed=["kitchen/sink.py"],
        )
        self.assertEqual(
            [line for line, _ in lint.scope_classes(self.repo)],
            ["CI/review scope:", "Automation scope:", "Kitchen scope:"],
        )

    def test_a_policy_file_with_no_table_declares_no_class_and_is_said(self) -> None:
        self.policy("# Repository Copilot Instructions\n\nNo table here.\n")
        report = self.run_lint("Work: sd:1\n", changed=PR_968_PATHS)
        self.assertEqual(report.failures, [])
        self.assertIn("tabulates no scope class; not run", self.rule_8(report))

    def commit_all(self, message: str) -> None:
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)

    def test_changed_paths_come_from_git_against_origin_head_when_not_listed(self) -> None:
        # sd-ship pins `origin/HEAD` to the remote default branch before it
        # runs this linter, and passes no list; the diff from the merge base
        # is what the pull request will carry.
        self.policy()
        self.commit_all("base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        (self.repo / ".github" / "workflows" / "tests.yml").write_text("on: push\n", encoding="utf-8")
        self.commit_all("touch a workflow")
        report = self.run_lint("Work: sd:1\n")
        self.assertEqual(len(report.failures), 1, report.failures)
        self.assertIn("touches .github/workflows/tests.yml", report.failures[0])
        self.assertIn("1 changed path(s) from origin/HEAD", self.rule_8(report))

    def test_a_non_ascii_path_still_reaches_its_scope_class(self) -> None:
        # `core.quotePath` is on by default, so a newline `--name-only`
        # printed `.github/workflows/tëst.yml` quoted, no scope glob matched
        # it, and the diff passed without its scope line (sd:1440).
        self.policy()
        self.commit_all("base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        (self.repo / ".github" / "workflows" / "tëst.yml").write_text("on: push\n", encoding="utf-8")
        self.commit_all("touch a workflow with a non-ASCII name")
        report = self.run_lint("Work: sd:1\n")
        self.assertIn("touches .github/workflows/tëst.yml", "\n".join(report.failures))

    def test_origin_main_is_read_when_origin_head_is_not_set(self) -> None:
        self.policy()
        self.commit_all("base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        (self.repo / "Makefile").write_text("check:\n", encoding="utf-8")
        self.commit_all("touch the gate")
        report = self.run_lint("Work: sd:1\n")
        self.assertIn("touches Makefile", "\n".join(report.failures))
        self.assertIn("from origin/main", self.rule_8(report))

    def test_no_base_ref_and_no_list_is_a_failure_and_not_a_pass(self) -> None:
        # The body is there, so the rule is supposed to run. A rule that
        # cannot see the diff and reports clean is the bug in sd:931 with a
        # different cause.
        self.policy()
        self.commit_all("base")
        self.assert_fails(
            "rule 8 cannot enumerate the changed paths: neither origin/HEAD nor origin/main "
            "resolves; pass --changed <file> listing them, one per line",
            pr_body="Work: sd:1\n",
        )

    def test_cli_reads_the_changed_list_and_fails_by_name(self) -> None:
        self.policy()
        self.git("add", "-A")
        body = self.repo / "body.md"
        body.write_text("Work: sd:876\n", encoding="utf-8")
        listed = self.repo / "changed.txt"
        listed.write_text("\n".join(PR_968_PATHS) + "\n  \n", encoding="utf-8")
        with in_directory(self.repo), contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(lint.main(["--pr-body", str(body), "--changed", str(listed)]), 1)
        self.assertIn('carries no "CI/review scope:" line', said.getvalue())

    def test_cli_changed_without_a_body_is_an_argument_error(self) -> None:
        listed = self.repo / "changed.txt"
        listed.write_text("Makefile\n", encoding="utf-8")
        with in_directory(self.repo), contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(lint.main(["--changed", str(listed)]), 2)
        self.assertIn("--changed needs --pr-body", said.getvalue())

    def test_cli_rejects_an_unreadable_changed_list(self) -> None:
        body = self.repo / "body.md"
        body.write_text("Work: sd:1\n", encoding="utf-8")
        with in_directory(self.repo), contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(
                lint.main(["--pr-body", str(body), "--changed", str(self.repo / "missing")]), 2)
        self.assertIn("cannot read --changed", said.getvalue())

    def test_a_rename_out_of_a_class_names_the_path_it_left(self) -> None:
        # Git detects renames by default and `--name-only` then prints the
        # new name alone, so a workflow moved out of `.github/` read as one
        # changed path in no class and the diff that retired it passed
        # clean (#972 review, measured at ac0f954b). Both paths of a move
        # are what the pull request touches, and the one it left demands
        # the line.
        self.policy()
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        (self.repo / ".github" / "workflows" / "tests.yml").write_text(
            "on: push\njobs:\n  a:\n    runs-on: ubuntu\n    steps:\n      - run: echo hi\n",
            encoding="utf-8",
        )
        self.commit_all("base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("mv", ".github/workflows/tests.yml", "docs/tests.yml.retired")
        self.commit_all("retire the workflow")
        self.assertEqual(
            lint.sd_lib.git_output(["diff", "--name-status", "origin/main...HEAD"], self.repo).split(),
            ["R100", ".github/workflows/tests.yml", "docs/tests.yml.retired"],
            "the fixture is a rename git detects, or it tests nothing",
        )
        report = self.run_lint("Work: sd:1\n")
        self.assertIn("touches .github/workflows/tests.yml", "\n".join(report.failures))
        self.assertIn("2 changed path(s) from origin/main, 1 class(es) demanded", self.rule_8(report))

    def test_cli_a_body_that_is_not_utf8_is_refused_by_name_and_not_by_traceback(self) -> None:
        # `UnicodeDecodeError` is a `ValueError`, not an `OSError`, so a body
        # file of bytes that do not decode escaped the argument guard as a
        # traceback with exit 1, where every other bad argument is a named
        # refusal with exit 2 (#972 review).
        body = self.repo / "body.md"
        body.write_bytes(b"Work: sd:1\n\xff\n")
        with in_directory(self.repo), contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(lint.main(["--pr-body", str(body)]), 2)
        self.assertIn("error: cannot read --pr-body: 'utf-8' codec can't decode", said.getvalue())

    def test_cli_a_changed_list_that_is_not_utf8_is_refused_by_name(self) -> None:
        body = self.repo / "body.md"
        body.write_text("Work: sd:1\n", encoding="utf-8")
        listed = self.repo / "changed.txt"
        listed.write_bytes(b"Makefile\n\xff\n")
        with in_directory(self.repo), contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(lint.main(["--pr-body", str(body), "--changed", str(listed)]), 2)
        self.assertIn("error: cannot read --changed: 'utf-8' codec can't decode", said.getvalue())


class BodyOnlyTests(LintFixture):
    """`--body-only`: rules 5 and 8 with no work root, and nothing else.

    Rule 8 was reached only inside `sd-ship`'s `if work.is_dir()` block,
    because the linter fails on a missing work root before any rule runs
    and `sd-ship` withheld the whole call rather than fail every repository
    without a planning directory. So a pull request in such a repository
    could change `.github/**` and ship without its scope line (#972 review,
    the suppressed finding on `skills/sd-ship/SKILL.md:68`). The body rules
    need no work root; this mode runs them alone.
    """

    def setUp(self) -> None:
        super().setUp()
        shutil.rmtree(self.work)
        path = self.repo / lint.SCOPE_POLICY
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SCOPE_POLICY, encoding="utf-8")

    def test_red_the_968_diff_with_no_work_root_and_no_scope_line_fails_by_name(self) -> None:
        # The fail-first case: before this mode, the only answer with no
        # work root was the missing-root failure, and `sd-ship` skipped the
        # call to avoid it.
        report = self.run_lint("Work: sd:876\n\nNo scope line.\n", PR_968_PATHS, body_only=True)
        self.assertEqual(
            report.failures,
            ['pull request body: touches .github/scripts/check-zizmor-personas.py, which '
             '.github/copilot-instructions.md puts under "CI/review scope:", '
             'and carries no "CI/review scope:" line'],
        )

    def test_green_the_line_passes_and_every_tree_rule_says_it_did_not_run(self) -> None:
        report = self.run_lint("Work: sd:876\n\n## CI/review scope:\n\nthe lint job\n",
                               PR_968_PATHS, body_only=True)
        self.assertEqual(report.failures, [])
        notes = "\n".join(report.notes)
        self.assertIn("rules 1-4, 6-7: --body-only, not run", notes)
        self.assertIn("rule 5 PR link: database association sd:876", notes)
        self.assertIn('demands "CI/review scope:", and the body carries it', notes)
        for tree_rule in ("rules 1-2 work items", "rule 3 decision", "rule 4 spec", "rule 6 citations", "rule 7 work"):
            self.assertNotIn(tree_rule, notes)

    def test_a_path_shaped_work_value_resolves_against_the_root_that_is_not_there(self) -> None:
        # Rule 5 still runs, and a path claim in a repository with no work
        # root is a claim onto nothing.
        report = self.run_lint("Work: docs/work/2026-08-29-a-workable-item\n", ["src.py"], body_only=True)
        self.assertEqual(
            report.failures,
            ["pull request body: Work: docs/work/2026-08-29-a-workable-item does not resolve to a work item"],
        )

    def test_without_the_flag_no_work_root_is_still_the_failure_it_was(self) -> None:
        # The mode is opt-in. A mistyped `--work-dir` on a full run stays a
        # failure by name rather than a body-only run nobody asked for.
        report = self.run_lint("Work: sd:876\n", PR_968_PATHS)
        self.assertEqual(report.failures, [f"{self.work.resolve()}: the work directory does not exist"])

    def test_the_flag_without_a_body_is_a_failure_in_the_library_and_an_argument_error_at_the_cli(self) -> None:
        report = self.run_lint(None, None, body_only=True)
        self.assertEqual(report.failures, ["--body-only: needs --pr-body; rules 5 and 8 read it"])
        with in_directory(self.repo), contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(lint.main(["--body-only"]), 2)
        self.assertIn("--body-only needs --pr-body", said.getvalue())

    def test_cli_body_only_fails_by_name_on_the_968_diff(self) -> None:
        self.git("add", "-A")
        body = self.repo / "body.md"
        body.write_text("Work: sd:876\n", encoding="utf-8")
        listed = self.repo / "changed.txt"
        listed.write_text("\n".join(PR_968_PATHS) + "\n", encoding="utf-8")
        with in_directory(self.repo), contextlib.redirect_stderr(io.StringIO()) as said, \
                contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(
                lint.main(["--body-only", "--pr-body", str(body), "--changed", str(listed)]), 1)
        self.assertIn('carries no "CI/review scope:" line', said.getvalue())
        self.assertIn("rules 1-4, 6-7: --body-only, not run", printed.getvalue())
        self.assertNotIn("the work directory does not exist", said.getvalue())


class ScopePolicyTests(unittest.TestCase):
    """This repository's own table, and the template that points at it.

    Rule 8 reads its classes from `.github/copilot-instructions.md`, so a
    table deleted from that file switches the rule off with a note and no
    failure. These pin the table's presence and its agreement with the
    template, which is the only other place the lines are named.
    """

    TEMPLATE = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"

    def classes(self) -> list[tuple[str, tuple[str, ...]]]:
        found = lint.scope_classes(REPO_ROOT)
        assert found is not None, f"{lint.SCOPE_POLICY} is not here"
        return found

    def test_the_table_is_here_and_names_the_two_live_classes(self) -> None:
        self.assertEqual([line for line, _ in self.classes()],
                         ["CI/review scope:", "Automation scope:"])
        for line, globs in self.classes():
            with self.subTest(line=line):
                self.assertTrue(globs, f"{line} has no path that demands it")

    def test_the_template_names_exactly_the_lines_the_table_has(self) -> None:
        # The template quotes the lines for an author; the table defines
        # them for the linter. One dropped from either is drift.
        quoted = re.findall(r'"([^"]*scope:)"', self.TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(sorted(set(quoted)), sorted(line for line, _ in self.classes()))

    def test_every_glob_in_the_table_names_a_tracked_path(self) -> None:
        # A row whose globs match nothing tracked is a class that demands
        # nothing and reads as if it did.
        tracked = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--deduplicate"],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        for line, globs in self.classes():
            for glob in globs:
                with self.subTest(line=line, glob=glob):
                    self.assertTrue(any(lint.matches_scope(path, glob) for path in tracked), glob)

    def test_the_968_diff_demands_the_ci_review_line_here(self) -> None:
        # The fixture that raised sd:931, run against this repository's own
        # table rather than the test's copy of it.
        report = lint.Report()
        lint.check_pr_scope(REPO_ROOT, "Work: sd:876\n", PR_968_PATHS, report)
        self.assertEqual(len(report.failures), 1, report.failures)
        self.assertIn('carries no "CI/review scope:" line', report.failures[0])
        report = lint.Report()
        lint.check_pr_scope(REPO_ROOT, "Work: sd:876\n\n## CI/review scope:\n\nOne step.\n",
                            PR_968_PATHS, report)
        self.assertEqual(report.failures, [])


class RepositoryTests(unittest.TestCase):
    def test_this_repository_is_clean(self) -> None:
        report = lint.run(REPO_ROOT, "docs/work", "docs/spec", "docs/decisions", None)
        self.assertEqual(report.failures, [])

    def test_missing_work_directory_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            report = lint.run(
                pathlib.Path(name), "docs/work", "docs/spec", "docs/decisions", None
            )
            self.assertEqual(len(report.failures), 1)
            self.assertIn("does not exist", report.failures[0])

    def test_frontmatter_reads_quoted_scalars(self) -> None:
        fields = lint.parse_frontmatter('---\ntitle: "PARKED: do a thing"\nstatus: planning\n---\n')
        assert fields is not None
        self.assertEqual(fields["title"], "PARKED: do a thing")
        self.assertEqual(fields["status"], "planning")

    def test_frontmatter_absent_returns_none(self) -> None:
        self.assertIsNone(lint.parse_frontmatter("# PRD\n"))

    def test_cli_reports_clean_on_this_repository(self) -> None:
        # There is no --repo any more (R10-D6): the linter reads cwd, so the
        # test has to stand in the repository it means to lint.
        with in_directory(REPO_ROOT):
            self.assertEqual(lint.main([]), 0)

    def test_cli_rejects_an_unreadable_pr_body(self) -> None:
        with in_directory(REPO_ROOT):
            self.assertEqual(lint.main(["--pr-body", str(REPO_ROOT / "no-such-file")]), 2)

    def test_cli_refuses_outside_a_git_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw, in_directory(pathlib.Path(raw)):
            self.assertEqual(lint.main([]), 2)


class Rule6CitationTests(LintFixture):
    """A `prd.md:N` citation still points at the line it was written against.

    Across four adversarial review rounds of one planning batch, six findings
    were citation drift, and twice the round that corrected the citations was
    the round that invalidated them: a fix inserted four lines into `prd.md`
    and re-anchored nothing below it. Rule 6 records what each citation points
    at and reports where the text went, so re-anchoring is a read rather than
    arithmetic.

    What it does not do is certify that a citation was right when it was
    recorded. The baseline is what the page says today; the rule watches it
    from there.
    """

    def test_green_a_recorded_citation_that_has_not_moved(self) -> None:
        self.record()
        self.assert_clean()

    def long_cited_item(self) -> tuple[pathlib.Path, str, int]:
        item = self.cited_item()
        prefix = "Cited source text stays meaningful across edits"
        lines = (item / "prd.md").read_text().splitlines()
        lines.append(prefix + " beyond the first phrase.")
        (item / "prd.md").write_text("\n".join(lines) + "\n")
        (item / "design.md").write_text(f"# design\n\nSee `prd.md:{len(lines)}`.\n")
        self.assertEqual(lint.write_citation_manifest(item, self.work)[:2], (1, []))
        return item, prefix, len(lines)

    def test_manifest_writer_emits_no_space_at_the_truncation_boundary(self) -> None:
        item, prefix, _ = self.long_cited_item()
        rows = (item / lint.CITATION_MANIFEST).read_text().splitlines()
        self.assertEqual(rows[0].split("\t")[-1], prefix)
        self.assertTrue(all(row == row.rstrip() for row in rows))
        self.assert_clean()

    def test_legacy_trailing_space_anchor_still_detects_moved_and_changed_text(self) -> None:
        item, _, start = self.long_cited_item()
        manifest = item / lint.CITATION_MANIFEST
        manifest.write_text(manifest.read_text().rstrip("\n") + " \n")
        self.assert_clean()
        source = item / "prd.md"
        lines = source.read_text().splitlines()
        lines.insert(start - 1, "New text before the cited sentence.")
        source.write_text("\n".join(lines) + "\n")
        self.assert_fails(f"that text is now at line {start + 1}")
        lines[start] = "The original cited sentence has changed."
        source.write_text("\n".join(lines) + "\n")
        self.assert_fails("that text is gone from the file")

    def test_red_an_insertion_above_the_target_moves_it(self) -> None:
        self.record()
        item = self.work / "2026-08-29-a-cited-item"
        lines = (item / "prd.md").read_text(encoding="utf-8").splitlines()
        lines.insert(1, "an inserted line")
        (item / "prd.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        failures = self.assert_fails("was written against")
        self.assertIn("that text is now at line 4", "\n".join(failures))

    def test_red_the_cited_text_deleted_altogether(self) -> None:
        self.record()
        item = self.work / "2026-08-29-a-cited-item"
        lines = (item / "prd.md").read_text(encoding="utf-8").splitlines()
        del lines[2]
        (item / "prd.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assert_fails("that text is gone from the file")

    def test_red_the_citing_page_no_longer_carries_the_citation(self) -> None:
        """Backbone item sd:572. The rule only ever read the target side.

        Every other check here asks whether the recorded text is still at the
        recorded line in the page being cited. None asked whether the citing
        page still cites it, so an edit that deleted a citation left its
        manifest row behind, and the row reported as checked forever. The
        count said `checked 25 citation(s)` while one of the twenty-five had
        not existed for some time.
        """

        self.record()
        item = self.work / "2026-08-29-a-cited-item"
        (item / "design.md").write_text("# design\n\nNo citation here.\n", encoding="utf-8")
        self.assert_fails("design.md no longer cites it")

    def test_green_a_citation_that_moved_down_its_own_page_is_not_a_failure(self) -> None:
        """The source side is searched, not read at the recorded line.

        An edit above a citation moves it without changing what it says. If
        this rule read `design.md:3` literally it would go red on ordinary
        editing while catching nothing the page-wide search does not.
        """

        self.record()
        item = self.work / "2026-08-29-a-cited-item"
        page = item / "design.md"
        lines = page.read_text(encoding="utf-8").splitlines()
        lines.insert(1, "An inserted paragraph above the citation.")
        page.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assert_clean()

    def test_red_a_deleted_citation_that_is_a_prefix_of_a_surviving_one(self) -> None:
        """`prd.md:3` is a substring of `prd.md:35`.

        Three pages in this repository carry a pair like that today, so a
        source-side check written as a substring scan would report the
        shorter citation as still present after it was deleted. The check
        compares against `item_citations`, the same walk the recorder uses,
        so the two halves of the comparison cannot disagree.
        """

        item = self.cited_item()
        lines = (item / "prd.md").read_text(encoding="utf-8").splitlines()
        while len(lines) < 35:
            lines.append(f"filler line {len(lines) + 1}")
        (item / "prd.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        page = item / "design.md"
        page.write_text(
            "# design\n\nThe ladder is at `prd.md:3`.\n\nThe filler is at `prd.md:35`.\n",
            encoding="utf-8",
        )
        self.assertEqual(lint.write_citation_manifest(item, self.work)[0], 2)
        page.write_text("# design\n\nThe filler is at `prd.md:35`.\n", encoding="utf-8")
        self.assert_fails("design.md no longer cites it")

    def test_red_the_citing_page_is_gone_altogether(self) -> None:
        """A deleted page and a deleted citation read differently to a reader.

        Both end with a row asserting a citation nobody carries, but one is
        fixed by restoring a page and the other by re-recording, so the rule
        says which happened rather than making the reader look.
        """

        self.record()
        item = self.work / "2026-08-29-a-cited-item"
        (item / "design.md").unlink()
        self.assert_fails("design.md, which does not exist")

    def test_the_recorder_names_the_row_it_drops(self) -> None:
        """Re-recording is where a row that outlived its citation leaves.

        The survey walks the pages, so a deleted citation yields no row and
        simply stops being written. That is correct, and it was silent.
        """

        self.record()
        item = self.cited_item()
        (item / "design.md").write_text("# design\n\nNo citation here.\n", encoding="utf-8")
        count, _, dropped = lint.write_citation_manifest(item, self.work)
        self.assertEqual(count, 0)
        self.assertEqual(dropped, ["design.md:3 `prd.md:3`"])

    def test_red_a_malformed_manifest_row(self) -> None:
        item = self.cited_item()
        (item / lint.CITATION_MANIFEST).write_text("two\tfields\n", encoding="utf-8")
        self.assert_fails("a manifest row is not five fields")

    def test_red_an_item_that_cites_and_was_never_recorded_is_named(self) -> None:
        """Backbone item sd:440. The skip used to be the whole story.

        `cited_item` writes a `design.md` naming `prd.md:3` and records
        nothing. Before this, rule 6 reached the item, found no
        `.citations.tsv`, moved on, and the run printed a clean verdict over a
        citation it had never looked at. The only difference from a citation
        that was checked and found sound was a count nobody compared against
        anything.
        """
        self.cited_item()
        failures = "\n".join(self.assert_fails(lint.CITATION_MANIFEST))
        self.assertIn("2026-08-29-a-cited-item", failures)
        self.assertIn("`prd.md:3`", failures)
        self.assertIn("--update-citations", failures)

    def test_the_note_says_how_many_items_are_active_beside_how_many_recorded(self) -> None:
        """The two numbers a reader needs to see a gap, on the same line.

        The fixture's own `2026-08-29-a-workable-item` cites nothing, so it is
        active without being recorded and the numbers legitimately differ. That
        is the case the old note could not express at all.
        """
        self.record()
        report = self.run_lint()
        self.assertEqual(report.failures, [])
        self.assertIn(
            "checked 1 citation(s) across 1 recorded item(s) of 2 active item(s)",
            "\n".join(report.notes),
        )

    def test_an_item_with_nothing_to_cite_needs_no_manifest(self) -> None:
        """A freshly planned item is not a finding.

        The demand is for a recording of the citations an item has, not for a
        file per directory: an item that cites nothing leaves nothing
        unguarded, and failing it would make every item red on the day it was
        created for a gap that cannot hide anything.
        """
        self.write_item("2026-08-29-an-uncitable-item", GOOD_PRD)
        self.assert_clean()

    def test_an_archived_item_that_cites_and_was_never_recorded_is_left_alone(self) -> None:
        """The archive is a record of what was, and rule 6 has always read past it.

        Demanding a baseline from it would ask for a recording of pages that
        are finished changing, which is the one place citation drift cannot
        happen.
        """
        archived = self.write_item(
            "2026-08-29-an-archived-citer", GOOD_PRD, month="2026-08"
        )
        (archived / "design.md").write_text(
            "# design\n\nThe ladder is at `prd.md:3`.\n", encoding="utf-8"
        )
        self.assert_clean()

    def test_the_manifest_is_not_a_stray_file_under_rule_1(self) -> None:
        self.record()
        self.assert_clean()

    def test_a_citation_that_leaves_the_work_root_does_not_resolve(self) -> None:
        """Still not checked, and no longer not mentioned.

        The escape stands -- this must never open `/etc/passwd` -- but a
        refusal that vanishes is indistinguishable from a citation that was
        read and found sound, which is the whole of this item.
        """
        item = self.cited_item()
        (item / "design.md").write_text(
            "See `../../../etc/passwd.md:1`.\n", encoding="utf-8"
        )
        found, skipped = lint.item_citations(item, self.work)
        self.assertEqual(found, [])
        self.assertEqual(
            skipped, [("design.md:1", "../../../etc/passwd.md:1", lint.ELSEWHERE, "")]
        )

    def test_a_citation_into_code_is_left_to_the_adjacency_rule(self) -> None:
        """And is not even seen: `CITATION_RE` requires a `.md` target.

        Recorded rather than fixed. A code citation is another gate's work by
        design, so rule 6 declining it is right; what this pins is that rule 6
        cannot count what its own regex never matched, so `bin/sd:1378` is
        absent from both halves rather than present in the census. The
        citations the census does count as elsewhere are markdown outside the
        work directory, which the regex does match.
        """
        item = self.cited_item()
        (item / "design.md").write_text("The reader is at `bin/sd:1378`.\n", encoding="utf-8")
        self.assertEqual(lint.item_citations(item, self.work), ([], []))

    def test_a_citation_below_the_log_heading_is_a_quotation_not_a_claim(self) -> None:
        item = self.cited_item()
        (item / "design.md").write_text(
            "# design\n\nThe ladder is at `prd.md:3`.\n\n"
            "## Log\n\n- C-1: `prd.md:3` was wrong on the day.\n",
            encoding="utf-8",
        )
        found, skipped = lint.item_citations(item, self.work)
        self.assertEqual([entry[0] for entry in found], ["design.md:3"])
        # The exemption keeps its reason and loses its silence: the quotation
        # is still not compared, and is now counted as a quotation.
        self.assertEqual(
            skipped, [("design.md:7", "prd.md:3", lint.QUOTATION, "")]
        )

    def test_a_blank_target_line_anchors_to_the_text_under_it(self) -> None:
        item = self.cited_item()
        prd = item / "prd.md"
        lines = prd.read_text(encoding="utf-8").splitlines()
        lines[2] = ""
        prd.write_text("\n".join(lines) + "\n", encoding="utf-8")
        lint.write_citation_manifest(item, self.work)
        recorded = (item / lint.CITATION_MANIFEST).read_text(encoding="utf-8").split("\t")
        self.assertNotEqual(recorded[4].strip(), "")


class Rule6SilencerTests(LintFixture):
    """Backbone item sd:5. Every decline rule 6 makes now says so.

    Rule 6 declined more citations than it checked and reported only what it
    checked. Measured on this repository at `06fb9de0`: 25 citations compared,
    126 declined -- 69 naming markdown outside the work directory, 54 below a
    Log heading, and 3 that the recorder silently refused to record. The run
    printed `checked 25 citation(s)` and `clean`, which is the same output a
    run that compared all 151 would have produced.

    The three refusals are the ones that matter, because they are rule 6's own
    corpus: a citation to a line the file does not have is a stale citation,
    exactly what this rule exists to catch, and `--update-citations` dropped it
    from the baseline so the rule never saw it again.

    They are reported, not failed. Two of the three live instances are a
    document *quoting* a citation while explaining this defect, and the gate
    cannot tell a quotation from a claim -- open question 3 on the item, still
    open. Failing them would make this repository red over prose that is
    correct. The precedent is the item's own answer to open question 1:
    compared and reported, nothing red, until there is a way to write an inert
    citation.
    """

    def out_of_range_item(self) -> pathlib.Path:
        """An item citing a line its own prd.md does not have."""
        item = self.write_item("2026-08-29-a-citing-item", GOOD_PRD)
        (item / "design.md").write_text(
            "# design\n\nThe ladder is at `prd.md:900`.\n", encoding="utf-8"
        )
        return item

    def test_red_a_citation_the_recorder_refused_is_named(self) -> None:
        """The silencer, at its narrowest and most damning.

        `prd.md:900` names a line of a twelve-line file. `write_citation_manifest`
        dropped it, the manifest came out empty, rule 6 read an empty manifest
        and reported a clean run, and no output anywhere in the program
        mentioned the citation. Against the unfixed code the assertion below
        finds nothing to match.
        """
        item = self.out_of_range_item()
        lint.write_citation_manifest(item, self.work)
        self.assertEqual((item / lint.CITATION_MANIFEST).read_text(encoding="utf-8"), "")
        length = len((item / "prd.md").read_text(encoding="utf-8").splitlines())
        notes = self.notes()
        self.assertIn("rule 6 not recorded:", notes)
        self.assertIn("`prd.md:900`", notes)
        self.assertIn(f"names line 900 of 2026-08-29-a-citing-item/prd.md, which has {length}", notes)

    def test_red_the_census_counts_each_kind_of_decline_apart(self) -> None:
        """One line, three buckets, and a total that conserves them.

        Kept apart on purpose: a citation into another tree is a handoff to
        the adjacency rule, a citation below a Log heading is a deliberate
        exemption, and a citation that could not be recorded is rule 6
        failing to watch its own corpus. Rolling them into one number would
        hide the third behind the first two, which outnumber it 41 to 1 in
        this repository.
        """
        item = self.out_of_range_item()
        (item / "implement.md").write_text(
            "# implement\n\nSee `../../../etc/passwd.md:1`.\n\n"
            "## Log\n\n- C-1: `prd.md:3` was right on the day.\n",
            encoding="utf-8",
        )
        notes = self.notes()
        self.assertIn("rule 6 not checked: 3 citation(s)", notes)
        self.assertIn(f"1 {lint.ELSEWHERE}", notes)
        self.assertIn(f"1 {lint.QUOTATION}", notes)
        self.assertIn(f"1 {lint.UNRECORDABLE}", notes)

    def test_red_update_citations_says_what_it_would_not_record(self) -> None:
        """The recorder's own count was a count of what it wrote.

        A person running `--update-citations` is looking straight at the
        citation at the one moment it could have been caught, and was told
        `recorded 0 citation(s)` with no hint that there had been one to
        record.
        """
        self.out_of_range_item()
        self.git("add", "-A")
        with in_directory(self.repo):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(lint.main(["--update-citations"]), 0)
        printed = out.getvalue()
        self.assertIn("2026-08-29-a-citing-item: recorded 0 of 1 citation(s)", printed)
        self.assertIn("not recorded: design.md:3 `prd.md:900`", printed)

    def test_a_recordable_citation_is_not_reported_as_declined(self) -> None:
        """The control for this class: a sound citation stays out of the census.

        Green before this change and after it. If the census ever starts
        naming citations that were checked, the two halves have stopped
        conserving and every count above is meaningless.
        """
        self.record()
        notes = self.notes()
        self.assertIn("checked 1 citation(s)", notes)
        self.assertNotIn("rule 6 not recorded:", notes)
        self.assertNotIn("rule 6 not checked:", notes)


class CitationRecorderIdempotenceTests(LintFixture):
    """sd:593. Re-recording a current manifest is a no-op, so it can be a check.

    It was not. On a clean checkout `--update-citations` rewrote four rows of
    one manifest and nothing else, every time: the snippet field of four rows
    ended in a space, because an older writer truncated at 48 characters
    without stripping and the boundary landed on one. Nothing was
    mis-reported -- rule 6 reads both shapes on purpose, and
    `test_legacy_trailing_space_anchor_still_detects_moved_and_changed_text`
    says so -- but a recorder that moves the tree on a tree that is already
    current cannot be asserted about. The assertion fails for a reason that is
    not a defect, so the check is never added, and the only evidence a
    manifest is current is that somebody says they ran the writer.

    Tolerating the old shape on READ stays, forever. Writing it stops.
    """

    def test_re_recording_this_repository_changes_no_manifest(self) -> None:
        """The property as a check, over the live corpus, without writing to it.

        `citation_survey` is the walk the writer records from and
        `manifest_body` is the bytes it writes, so comparing them against the
        file on disk is exactly `--update-citations` followed by a porcelain
        status, with nothing left behind when it fails.
        """
        work = REPO_ROOT / "docs" / "work"
        compared = 0
        for item in lint.item_directories(work):
            if "archive" in item.parts:
                continue
            manifest = item / lint.CITATION_MANIFEST
            if not manifest.is_file():
                continue
            rows, _ = lint.citation_survey(item, work)
            compared += 1
            self.assertEqual(
                manifest.read_text(encoding="utf-8"),
                lint.manifest_body(rows),
                f"re-recording {item.name} would rewrite its manifest; run "
                "bin/sd-docs-lint --update-citations and commit the result",
            )
        # The control for this test's own reach: an assertion that compared
        # nothing would pass on an empty repository just as loudly.
        self.assertGreater(compared, 0, "no recorded item was compared")

    def test_a_legacy_trailing_space_row_is_rewritten_once_and_then_never(self) -> None:
        """The fixture form: one re-record normalises, the next is byte-equal."""
        item = self.cited_item()
        lint.write_citation_manifest(item, self.work)
        manifest = item / lint.CITATION_MANIFEST
        current = manifest.read_text(encoding="utf-8")
        manifest.write_text(current.replace("\n", " \n"), encoding="utf-8")
        lint.write_citation_manifest(item, self.work)
        first = manifest.read_text(encoding="utf-8")
        self.assertEqual(first, current)
        lint.write_citation_manifest(item, self.work)
        self.assertEqual(manifest.read_text(encoding="utf-8"), first)

    def test_the_writer_strips_a_snippet_that_truncates_onto_a_space(self) -> None:
        """The guard itself, called directly, on the shape that produced the four.

        A line whose 48th character is a space is the whole cause, so the
        fixture builds one rather than hoping the corpus still contains one.
        """
        line = "a" * (lint.SNIPPET_CHARS - 1) + " trailing words follow"
        self.assertEqual(lint.snippet_of(line), "a" * (lint.SNIPPET_CHARS - 1))
        # CONTROL: a snippet that does not end on the boundary is untouched.
        self.assertEqual(lint.snippet_of("  a  short   line  "), "a short line")


class Rule6MisresolutionTests(LintFixture):
    """sd:533. A citation that resolves onto the wrong file is an error.

    The live instance: an implement.md wrote `README.md:34`, meaning the
    repository README, and `resolve_citation` landed it on the seven-line
    `docs/work/README.md` -- a real file, at a line it does not have. The
    citation was stale AND mis-resolved, and rule 6's verdict was clean.

    WHY AN ERROR AND NOT A SILENT NARROWING. The cheapest available fix was
    to fail only when the cited line exceeds the resolved file's length,
    which would have caught this instance. It does not catch the class: a
    bare name that lands on a file long enough to have the cited line is
    read, compared against unrelated text, and reported as sound. The second
    cheapest was to stop resolving a bare name anywhere but beside the citing
    page, which turns the wrong answer into no answer -- still silence, which
    is the thing sd:5 closed and this must not reopen.

    So the rule is stated positively: every citation rule 6 owns names a work
    item document. A citation that resolved onto anything else resolved
    through a fallback base rather than because its author meant it, and both
    readings are named in the failure so the author can write the path.
    """

    def misresolving_item(self) -> pathlib.Path:
        """An item whose page cites a sibling and a bare work-root filename.

        `docs/work/README.md` is four lines long on purpose. The cited line
        exists in it, so this fixture is the case a length check would miss:
        without the guard the citation is recorded, compared against text
        about something else, and reported as checked and clean.
        """
        (self.work / "README.md").write_text(
            "# Work items\n\nOne directory per item.\nNothing here is a claim about installs.\n",
            encoding="utf-8",
        )
        item = self.write_item("2026-08-29-a-misciting-item", GOOD_PRD)
        (item / "design.md").write_text(
            "# design\n\nThe ladder is at `prd.md:3`.\nThe claim is `README.md:3`.\n",
            encoding="utf-8",
        )
        return item

    def test_red_a_bare_name_resolving_onto_a_non_item_document_fails(self) -> None:
        """The guard, called directly, and then through the run.

        Called directly first because the same page carries a citation that
        must still resolve: a fixture that only asserted a failure would pass
        just as well against a resolver that refused everything.
        """
        item = self.misresolving_item()
        found, skipped = lint.item_citations(item, self.work)
        # CONTROL, in the same page and the same walk.
        self.assertEqual(
            [entry[:3] for entry in found],
            [("design.md:3", "prd.md:3", "2026-08-29-a-misciting-item/prd.md")],
        )
        self.assertEqual(
            [entry[:3] for entry in skipped],
            [("design.md:4", "README.md:3", lint.MISRESOLVED)],
        )
        joined = "\n".join(self.assert_fails("`README.md:3`"))
        self.assertIn("names no README.md beside design.md", joined)
        self.assertIn("resolved onto README.md", joined)

    def test_the_census_counts_a_misresolution_apart_from_a_decline(self) -> None:
        """It is counted, because the census is a partition or it is nothing."""
        self.misresolving_item()
        notes = self.notes()
        self.assertIn("rule 6 not checked: 1 citation(s)", notes)
        self.assertIn(f"1 {lint.MISRESOLVED}", notes)

    def test_green_a_bare_name_that_names_a_sibling_is_untouched(self) -> None:
        """The control for the whole class: the ordinary citation still works.

        `docs/work/README.md` exists here too, so this is not green merely
        because the ambiguous file is absent -- it is green because the
        citation names a document of the item it sits in.
        """
        (self.work / "README.md").write_text("# Work items\n", encoding="utf-8")
        self.record()
        self.assert_clean()
        self.assertIn("checked 1 citation(s)", self.notes())


class MetavariableTests(unittest.TestCase):
    """`METAVARIABLE_RE` reads a token, not a substring.

    Two readers share it: rule 7 here and the pull-request template walk in
    `tests/test_pull_request_template_links.py`. Both skip what it matches, so
    a match on a real name is a check that silently did not happen (sd:801).
    """

    def test_a_placeholder_is_a_whole_token(self) -> None:
        for token in ("<YYYY-MM-DD>-<slug>", "YYYY-MM-DD-slug", "archive/YYYY-MM/",
                      "YYYY_MM", "DD.md", "<id>", "MM"):
            with self.subTest(token=token):
                self.assertIsNotNone(lint.METAVARIABLE_RE.search(token))

    def test_a_name_that_merely_contains_the_letters_is_not_one(self) -> None:
        # The last two names separate the halves of the boundary, and until
        # they were added nothing did. Five of the names above them carry a
        # date token, and each of those sits between two alphanumerics -- `MM`
        # inside `COMMANDS` and `SUMMARY`, `DD` inside `ADDING`, `YYYY` inside
        # `HAPPYYYYEAR`, `MM` between the zeroes of `0MM0` -- so either
        # lookaround alone rejects all five, while the remaining two carry no
        # token and ask neither lookaround anything. Deleting either one left
        # all 133 tests green (sd:833). Only the lookbehind rejects
        # `docs/ADD/plan.md`, where a `/` follows the `DD`; only the lookahead
        # rejects `docs/MMap.md`, where a `/` precedes the `MM`.
        for token in ("docs/COMMANDS.md", "ADDING.md", "HAPPYYYYEAR", "2026-08-29-slug",
                      "SUMMARY.md", "0MM0", "docs/work/2026-09-04-an-item/prd.md",
                      "docs/ADD/plan.md", "docs/MMap.md"):
            with self.subTest(token=token):
                self.assertIsNone(lint.METAVARIABLE_RE.search(token))


class Rule7WorkReferenceTests(LintFixture):
    """A `docs/work/` path a document names has to resolve.

    No deletion is needed to break one. This repository's own case is a move:
    `2026-08-29-artifacts-as-product` went into the archive after fourteen
    tracked lines had already linked to it where it used to be, and until this
    rule nothing said the links had stopped resolving.
    """

    def name_it(self, reference: str, page: str = "NOTES.md") -> None:
        (self.repo / page).write_text(
            f"# notes\n\nThe shape is described in `{reference}`.\n", encoding="utf-8"
        )

    def test_red_a_page_naming_an_item_directory_that_is_not_there(self) -> None:
        self.name_it("docs/work/2026-08-29-an-item-that-was-never-created/prd.md")
        joined = "\n".join(self.assert_fails("names nothing in the checkout"))
        self.assertIn("NOTES.md", joined)
        self.assertIn("2026-08-29-an-item-that-was-never-created/prd.md", joined)

    def test_green_a_metavariable_is_a_pattern_and_not_a_path(self) -> None:
        self.name_it("docs/work/<YYYY-MM-DD>-<slug>/prd.md")
        self.assert_clean()

    def test_green_a_bare_date_placeholder_is_a_pattern_without_the_brackets(self) -> None:
        # `YYYY`, `MM` and `DD` as whole tokens carry the skip on their own;
        # the case above carries it on `<` as well, so it cannot say so.
        self.name_it("docs/work/YYYY-MM-DD-slug/prd.md")
        self.assert_clean()
        self.assertIn("and 1 template reference(s)", self.notes())

    def test_red_a_name_carrying_a_date_letter_pair_is_a_path_and_not_a_pattern(self) -> None:
        """`COMMANDS` carries `MM` and `ADDING` carries `DD`.

        Matched as substrings, `METAVARIABLE_RE` made either name a template,
        and a reference to an item that was never created was passed over
        instead of failed. No tracked name carried one when this was found,
        so nothing was hidden yet; the boundary is what keeps it that way
        (sd:801).
        """
        for slug in ("2026-08-29-COMMANDS-that-do-not-exist",
                     "2026-08-29-ADDING-what-is-not-there",
                     "2026-08-29-HAPPYYYYEAR"):
            with self.subTest(slug=slug):
                self.name_it(f"docs/work/{slug}/prd.md")
                joined = "\n".join(self.assert_fails("names nothing in the checkout"))
                self.assertIn(slug, joined)
                self.assertIn("and 0 template reference(s)", self.notes())

    def test_green_a_reference_that_resolves(self) -> None:
        self.name_it("docs/work/2026-08-29-a-workable-item/prd.md")
        self.assert_clean()

    def test_the_archive_is_read_past(self) -> None:
        """Its items are records, and its own links point inside itself."""
        self.write_item("2026-08-29-an-archived-item", GOOD_PRD, month="2026-08")
        archived = self.work / "archive" / "2026-08" / "2026-08-29-an-archived-item"
        (archived / "design.md").write_text(
            "# design\n\nSee `docs/work/2026-01-01-long-gone/prd.md`.\n", encoding="utf-8"
        )
        self.assert_clean()

    def test_the_changelog_is_read_past(self) -> None:
        """It names paths as they were, which is where a stale one is correct."""
        self.name_it("docs/work/2026-01-01-long-gone/prd.md", page="CHANGELOG.md")
        self.assert_clean()

    def test_red_the_note_counts_the_files_and_references_it_skipped(self) -> None:
        """Backbone item sd:5. Both exemptions keep their reason, lose their silence.

        `read 77 reference(s) across 143 file(s)` was rule 7's whole report on
        this repository while 954 tracked documents went unread under
        `archive/` or as `CHANGELOG.md`, and 11 references were passed over as
        templates. Neither skip is wrong and neither is being removed. What
        was wrong is that a reader given one number cannot tell a narrow
        corpus from a whole one, and a skip nobody can count is a skip nobody
        can audit.

        Here: one archived document and one `CHANGELOG.md` unread, one
        metavariable reference passed over, one real reference read.
        """
        self.write_item("2026-08-29-an-archived-item", GOOD_PRD, month="2026-08")
        self.name_it("docs/work/2026-01-01-long-gone/prd.md", page="CHANGELOG.md")
        self.name_it(
            "docs/work/<YYYY-MM-DD>-<slug>/prd.md and "
            "docs/work/2026-08-29-a-workable-item/prd.md"
        )
        report = self.run_lint()
        self.assertEqual(report.failures, [])
        self.assertIn(
            "rule 7 work references: read 1 reference(s) across 4 file(s); "
            "skipped 2 file(s) under docs/work/archive/ or named CHANGELOG.md, "
            "and 1 template reference(s)",
            "\n".join(report.notes),
        )

    def test_an_untracked_page_is_not_a_document_this_repository_publishes(self) -> None:
        self.assert_clean()
        self.name_it("docs/work/2026-01-01-long-gone/prd.md")
        # No `git add` here, so `ls-files` does not see the page and the rule
        # does not read it. Deliberate: a scratch file beside a checkout is not
        # something the repository says.
        report = lint.run(self.repo, "docs/work", "docs/spec", "docs/decisions", None)
        self.assertEqual(report.failures, [])

    def test_a_directory_git_cannot_enumerate_fails_rather_than_passes(self) -> None:
        """The pass-on-nothing failure this whole rule set exists to close.

        `ls-files` outside a repository answers nothing, and a rule that reads
        nothing has checked nothing. Reporting that as clean is the shape of
        every silent fail-open, so the rule says so instead.
        """
        with tempfile.TemporaryDirectory() as scratch:
            outside = pathlib.Path(scratch)
            (outside / "docs" / "work").mkdir(parents=True)
            report = lint.run(outside, "docs/work", "docs/spec", "docs/decisions", None)
        joined = "\n".join(report.failures)
        self.assertIn("rule 7 read nothing", joined)


BAD_REFERENCE = "docs/work/2026-01-01-long-gone/prd.md"
NOTES = f"# notes\n\nThe shape is described in `{BAD_REFERENCE}`.\n"


class Rule7UnmergedIndexTests(unittest.TestCase):
    """What rule 7 reports while a merge is still being resolved.

    `sd-docs-lint` is run *during* the merge workflow, which is the only
    reason this case is worth building by hand: an unmerged path sits in the
    index once per stage, so the enumeration hands the rule the same document
    three times, and it is read, linted and reported on three times.

    The fixture resolves the working tree and deliberately leaves it
    unstaged. That is the state a person is actually in -- the conflict is
    fixed in the editor, the file on disk is ordinary markdown again, nothing
    warns them, and the index still carries three stages.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = pathlib.Path(self._tmp.name)
        self._build()

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            # Identity and signing are set per invocation rather than read
            # from the machine, so the fixture does not fail on a host with no
            # `user.email` or one that signs every commit.
            ["git", "-C", str(self.repo),
             "-c", "user.email=lint@example.invalid",
             "-c", "user.name=docs lint",
             "-c", "commit.gpgsign=false", *args],
            capture_output=True, text=True, check=check,
        )

    def _build(self) -> None:
        """A real merge, not a hand-written index.

        The three stages have to come from git's own conflict machinery, or
        the fixture restates the belief under test instead of evidencing it.
        """
        notes = self.repo / "NOTES.md"
        item = self.repo / "docs" / "work" / "2026-08-29-a-workable-item"
        item.mkdir(parents=True)
        (item / "prd.md").write_text(GOOD_PRD, encoding="utf-8")

        self.git("init", "-q", "-b", "main")
        notes.write_text("# notes\n\nbase\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.git("checkout", "-q", "-b", "other")
        notes.write_text("# notes\n\ntheir side\n", encoding="utf-8")
        self.git("commit", "-qam", "other")
        self.git("checkout", "-q", "main")
        notes.write_text("# notes\n\nmy side\n", encoding="utf-8")
        self.git("commit", "-qam", "mine")
        self.git("merge", "other", check=False)
        # Resolved on disk, never staged.
        notes.write_text(NOTES, encoding="utf-8")

    def assert_the_index_is_unmerged(self) -> None:
        stages = self.git("ls-files", "-u", "--", "NOTES.md").stdout
        self.assertEqual(
            [line.split("\t")[0].split()[-1] for line in stages.splitlines()],
            ["1", "2", "3"],
            "the fixture did not leave an unmerged index, so the cases below "
            "prove nothing -- they would pass against any clean checkout",
        )
        # ls-files-form: plain -- the repetition is what this case asserts
        listed = self.git("ls-files", "-z", "--", "NOTES.md").stdout
        self.assertEqual(
            [name for name in listed.split("\0") if name],
            ["NOTES.md"] * 3,
            "this git no longer repeats an unmerged path; if that is now the "
            "default, say so here rather than deleting the case",
        )

    def test_a_conflicted_document_is_reported_once(self) -> None:
        """One bad reference in one file is one finding, not three.

        This is what the person resolving the merge reads, so it is asserted
        on the report rather than on the path list: a rule that deduplicated
        its enumeration but still counted per stage would look fixed and
        print the same three lines.
        """
        self.assert_the_index_is_unmerged()
        report = lint.run(self.repo, "docs/work", "docs/spec", "docs/decisions", None)
        self.assertEqual(
            [f for f in report.failures if "names nothing in the checkout" in f],
            [f"NOTES.md: {BAD_REFERENCE} names nothing in the checkout"],
            "a conflicted document was linted once per merge stage",
        )

    def test_the_totals_count_the_conflicted_document_once(self) -> None:
        """The counters, which a deduplicated path list alone would not fix.

        Two files are readable here -- `NOTES.md` and the item's `prd.md` --
        and between them they name one `docs/work/` path. Both numbers are
        read rather than computed, so the case cannot agree with the defect.

        Matched as a prefix of the note rather than as the whole of it, so
        that the skip counts the note gained for sd:5 -- and anything else it
        gains later -- cannot make this case pass or fail for a reason that
        has nothing to do with merge stages. The two numbers it is about are
        still pinned exactly.
        """
        self.assert_the_index_is_unmerged()
        report = lint.run(self.repo, "docs/work", "docs/spec", "docs/decisions", None)
        self.assertIn(
            "rule 7 work references: read 1 reference(s) across 2 file(s)",
            "\n".join(report.notes),
            f"inflated totals: {report.notes}",
        )


class WorkDirSpellingTests(LintFixture):
    """A spelling that opens a root is read as that root, or is refused.

    `--work-dir` is a path to rules 1, 2, 5 and 6 and a *literal prefix* to
    rule 7, which matches it against the text of tracked markdown where a
    `docs/work/` reference is written repo-relative and nothing else. Before
    sd:374 every spelling but the plain relative one made those two meanings
    disagree without saying so: `./docs/work`, `docs/work/`,
    `docs/../docs/work` and the tree's own absolute path each left rule 7
    matching nothing, reporting `read 0 reference(s)`, and passing over the
    dangling reference the relative spelling catches. A rule that reads
    nothing has checked nothing, which is the failure the rule's own
    `git could not list tracked markdown` branch already refuses to commit.

    This class first claimed the general form -- one root however it is
    spelled -- and the review of #833 showed that claim false on this
    platform, which is the reason for the hedged sentence above. `resolve()`
    canonicalises `..`, symlinks and separators but not *case*, so on APFS
    `--work-dir DOCS/WORK` opened the real tree for rules 1, 2, 5 and 6 and
    survived as `DOCS/WORK` into rule 7: 77 references across 143 files
    became 0 across 1096, and the command still exited 0. The canonical
    spelling now comes from the directory entry, so the claim holds where the
    filesystem folds case; where it does not fold case, a mis-cased root
    opens nothing and is reported missing. Both are answers. Neither is the
    silent pass.
    """

    def case_folds(self) -> bool:
        """Whether this filesystem opens `DOCS` and `docs` as one directory."""
        return (self.repo / "DOCS" / "WORK").is_dir()

    def setUp(self) -> None:
        super().setUp()
        (self.repo / "NOTES.md").write_text(
            "See `docs/work/2026-01-01-never-created/prd.md`.\n", encoding="utf-8"
        )

    def report_for(self, work_dir: str) -> lint.Report:
        self.git("add", "-A")
        return lint.run(self.repo, work_dir, "docs/spec", "docs/decisions", None)

    def rule_7_note(self, report: lint.Report) -> str:
        notes = [note for note in report.notes if note.startswith("rule 7")]
        self.assertEqual(len(notes), 1, report.notes)
        return notes[0]

    def test_the_relative_spelling_is_the_baseline_and_catches_the_reference(self) -> None:
        report = self.report_for("docs/work")
        self.assertIn("read 1 reference(s)", self.rule_7_note(report))
        self.assertIn("names nothing in the checkout", "\n".join(report.failures))

    def test_an_absolute_root_inside_the_repository_reads_the_same_tree(self) -> None:
        """The same directory, spelled the long way, is the same directory."""
        baseline = self.report_for("docs/work")
        absolute = self.report_for(str(self.work))
        self.assertEqual(self.rule_7_note(absolute), self.rule_7_note(baseline))
        self.assertEqual(absolute.failures, baseline.failures)

    def test_every_accepted_spelling_reads_the_same_references(self) -> None:
        baseline = self.rule_7_note(self.report_for("docs/work"))
        for spelling in ("./docs/work", "docs/work/", "docs/../docs/work", "docs//work"):
            with self.subTest(spelling=spelling):
                self.assertEqual(self.rule_7_note(self.report_for(spelling)), baseline)

    def test_a_root_outside_the_repository_refuses_rather_than_half_applies(self) -> None:
        """The recorded case: rules 1-2-6 read there, rule 7 read here.

        Rule 7's enumeration, rule 2's row database and rule 5's `Work:`
        resolution are all rooted at the checkout the caller stands in, so a
        foreign work root is not a root this run can honour. It says so.
        """
        with tempfile.TemporaryDirectory() as elsewhere:
            outside = pathlib.Path(elsewhere) / "docs" / "work"
            outside.mkdir(parents=True)
            report = self.report_for(str(outside))
        self.assertEqual(len(report.failures), 1, report.failures)
        self.assertIn("is outside", report.failures[0])
        self.assertEqual([note for note in report.notes if note.startswith("rule 7")], [])

    def test_the_repository_root_is_not_a_work_directory(self) -> None:
        report = self.report_for(".")
        self.assertEqual(len(report.failures), 1, report.failures)
        self.assertIn("itself, not a directory inside it", report.failures[0])

    def test_cli_refuses_a_work_dir_outside_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as elsewhere, in_directory(self.repo):
            outside = pathlib.Path(elsewhere) / "docs" / "work"
            outside.mkdir(parents=True)
            self.assertEqual(lint.main(["--work-dir", str(outside)]), 2)

    def test_cli_refuses_a_spec_dir_outside_the_repository(self) -> None:
        """No second meaning, but a verdict over a mixture is still wrong."""
        with tempfile.TemporaryDirectory() as elsewhere, in_directory(self.repo):
            outside = pathlib.Path(elsewhere) / "docs" / "spec"
            outside.mkdir(parents=True)
            self.assertEqual(lint.main(["--spec-dir", str(outside)]), 2)

    def test_a_case_only_misspelling_is_not_a_second_work_root(self) -> None:
        """The #833 finding: `resolve()` does not canonicalise case.

        On a case-folding filesystem `DOCS/WORK` is the same directory, so it
        has to read the same; on one that does not fold, it is no directory at
        all, so it has to be reported missing. The outcome this refuses is the
        third one, which is what the tool did: open the right tree, keep the
        typed string, read nothing with it, and exit 0.
        """
        baseline = self.report_for("docs/work")
        shouted = self.report_for("DOCS/WORK")
        if self.case_folds():
            self.assertEqual(self.rule_7_note(shouted), self.rule_7_note(baseline))
            self.assertEqual(shouted.failures, baseline.failures)
        else:
            self.assertEqual(len(shouted.failures), 1, shouted.failures)
            self.assertIn("does not exist", shouted.failures[0])

    def test_the_canonical_spelling_comes_from_the_directory_entry(self) -> None:
        self.assertEqual(lint.spelled_on_disk(self.repo, "docs"), "docs")
        # Left as typed, so the caller reports the directory that is not there
        # rather than this inventing one that is.
        self.assertEqual(lint.spelled_on_disk(self.repo, "not-a-directory"), "not-a-directory")
        if self.case_folds():
            self.assertEqual(lint.spelled_on_disk(self.repo, "DOCS"), "docs")

    def test_run_guards_every_root_and_not_only_the_work_dir(self) -> None:
        """An absolute right-hand operand wins in pathlib, for all three.

        The foreign tree here is deliberately *valid*, so that a `run` which
        only guards `work_dir` reports no failures at all -- which is what it
        did: rules 3 and 4 lint one repository while the rest lint another,
        and the verdict over that mixture is a clean one.
        """
        for flag, relative in (("--spec-dir", "docs/spec"), ("--decisions-dir", "docs/decisions")):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as elsewhere:
                outside = pathlib.Path(elsewhere) / relative
                outside.mkdir(parents=True)
                (outside / "page.md").write_text("# page\n", encoding="utf-8")
                (outside / "index.md").write_text(
                    "# index\n\n- [page](./page.md)\n", encoding="utf-8"
                )
                self.git("add", "-A")
                report = lint.run(
                    self.repo,
                    "docs/work",
                    str(outside) if flag == "--spec-dir" else "docs/spec",
                    str(outside) if flag == "--decisions-dir" else "docs/decisions",
                    None,
                )
                self.assertEqual(len(report.failures), 1, report.failures)
                self.assertIn(flag, report.failures[0])
                self.assertIn("is outside", report.failures[0])

    def test_cli_accepts_an_absolute_work_dir_inside_the_repository(self) -> None:
        self.git("add", "-A")
        (self.repo / "NOTES.md").unlink()
        self.git("add", "-A")
        with in_directory(self.repo):
            self.assertEqual(lint.main(["--work-dir", str(self.work)]), 0)


JEV_STUB = """#!/usr/bin/env python3
import json
import os
import shutil
import sys

verb = sys.argv[1] if len(sys.argv) > 1 else ""
if verb == "enabled":
    probed = os.environ.get("JEV_STUB_PROBED")
    if probed:
        open(probed, "w").close()
    raise SystemExit(int(os.environ.get("JEV_STUB_ENABLED", "0")))
state = sys.argv[sys.argv.index("--state") + 1]
capture = os.environ.get("JEV_STUB_CAPTURE")
if capture:
    shutil.copyfile(state, capture)
questions = json.loads(sys.stdin.read())
if os.environ.get("JEV_STUB_FAIL") == "1":
    sys.stdout.write("not json at all\\n")
    raise SystemExit(1)
noul = float(os.environ.get("JEV_STUB_NOUL", "0.9"))
answers = {key: {"noul": noul} for key in questions}
sys.stdout.write(json.dumps({"model": "stub", "answers": answers}))
"""


class Rule6ClaimSupportTests(LintFixture):
    """The optional second reading of rule 6, which asks a model a question.

    Every test here runs against a stub on PATH and never against the real
    command: a suite that reaches a paid endpoint is a suite that fails when
    somebody else's invoice does, and none of what is being tested here is
    the model's judgment. What is being tested is that the linter behaves the
    same whatever the model says, and says what it was told.
    """

    def setUp(self) -> None:
        super().setUp()
        self.bin = self.repo / "stub-bin"
        self.bin.mkdir()
        stub = self.bin / "jev"
        stub.write_text(JEV_STUB, encoding="utf-8")
        stub.chmod(0o755)
        self.capture = self.repo / "sent.json"
        self.probed = self.repo / "probed"
        # Opted in by default, so every case below that is not about the
        # opt-in exercises the path a reading takes. The cases about the
        # opt-in remove or rewrite the file themselves.
        self.opt_in(True)

    def opt_in(self, value: object) -> None:
        """Write the repository's opt-in file; a `str` is written verbatim."""
        path = self.repo / lint.JEV_OPT_IN_RELATIVE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        text = value if isinstance(value, str) else json.dumps({lint.JEV_OPT_IN_KEY: value})
        path.write_text(text, encoding="utf-8")

    def opt_out(self) -> None:
        (self.repo / lint.JEV_OPT_IN_RELATIVE_PATH).unlink()

    @contextlib.contextmanager
    def jev(self, **extra: str):
        """The stub on PATH and nothing left behind.

        The switch is unset unless a case sets it: unset leaves the
        repository's opt-in to decide, so a fixture that set it would no
        longer be testing the path every run takes. It is *removed* rather than merely not added, because
        `patch.dict` layers over the real environment and `CONTRIBUTING.md`
        now tells operators to export `JEV_SD_DOCS_LINT=0` -- a reader who
        follows that advice would otherwise watch seven of these fail, and
        conclude the suite is flaky rather than that the fixture is.
        `patch.dict` restores the whole mapping on exit, so popping inside it
        leaves nothing behind either.
        """
        environment = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "JEV_STUB_CAPTURE": str(self.capture),
            "JEV_STUB_PROBED": str(self.probed),
            **extra,
        }
        with mock.patch.dict(os.environ, environment):
            if lint.JEV_STAGE not in extra:
                os.environ.pop(lint.JEV_STAGE, None)
            yield

    def recorded_item(self) -> pathlib.Path:
        item = self.cited_item()
        lint.write_citation_manifest(item, self.work)
        return item

    def test_an_opted_in_repository_with_the_switch_unset_takes_the_reading(self) -> None:
        """The opt-in on, the switch unset: the one way a reading is taken."""

        self.recorded_item()
        with self.jev():
            self.assertIn("claim support", self.notes())
        self.assertTrue(self.capture.exists(), "an opted-in repository took no reading")

    def test_a_repository_that_has_not_opted_in_sends_nothing(self) -> None:
        """The default (sd:1304). No file, the switch unset, `jev` on PATH and
        keyed: no request, no note, and `jev` is not even asked whether it can
        answer. Before sd:1304 this run took the reading, and every checkout
        whose `docs/work` must not leave the machine had to export `0`."""

        self.opt_out()
        self.recorded_item()
        with self.jev():
            self.assertNotIn("claim support", self.notes())
        self.assertFalse(self.capture.exists(), "a repository that never opted in sent a request")
        self.assertFalse(self.probed.exists(), "a repository that never opted in probed jev")

    def test_no_environment_variable_can_opt_a_repository_in(self) -> None:
        """The variable only ever subtracts. The operator's shell exports
        `JEV_SD_DOCS_LINT=1` for other reasons; that must not turn the
        reading on in a repository that did not ask for it."""

        self.opt_out()
        self.recorded_item()
        for value in ("1", "on", "true", "True", "TRUE", "yes", "enabled", ""):
            with self.subTest(value=value), self.jev(JEV_SD_DOCS_LINT=value):
                self.assertNotIn("claim support", self.notes())
            self.assertFalse(self.capture.exists(), f"{value!r} opted a repository in")
            self.assertFalse(self.probed.exists(), f"{value!r} made a repository probe jev")

    def test_a_file_that_says_false_is_the_default(self) -> None:
        self.opt_in(False)
        self.recorded_item()
        with self.jev():
            self.assertNotIn("claim support", self.notes())
        self.assertFalse(self.capture.exists(), "an opt-in of false sent a request")

    def test_the_switch_off_wins_over_the_opt_in(self) -> None:
        """Silence, not a note: the operator asked for silence, and the
        repository's `true` does not overrule them.

        `patch.dict` adds to the environment it patches and removes nothing,
        so the switch is stated by the fixture rather than inherited.
        """
        self.recorded_item()
        self.assertEqual(lint.jev_opt_in(self.repo), (True, ""))
        with self.jev(JEV_SD_DOCS_LINT="0"):
            self.assertNotIn("claim support", self.notes())
        self.assertFalse(self.capture.exists(), "a switched-off run sent a request")

    def test_an_opt_in_that_cannot_mean_anything_is_a_note_and_sends_nothing(self) -> None:
        """Fails closed, and says so. Only a JSON `true` opts in: a value that
        opens an egress path is spelled one way. The note names the file and
        the fault and never what the file held."""

        self.recorded_item()
        cases = {
            "{not json": "not valid JSON",
            "[true]": "the top level must be a JSON object",
            json.dumps({lint.JEV_OPT_IN_KEY: True, "secret_tenant": True}): "1 unknown key(s)",
            json.dumps({lint.JEV_OPT_IN_KEY: "true"}): f"{lint.JEV_OPT_IN_KEY} must be true or false",
            json.dumps({lint.JEV_OPT_IN_KEY: 1}): f"{lint.JEV_OPT_IN_KEY} must be true or false",
        }
        for text, fault in cases.items():
            with self.subTest(text=text):
                self.opt_in(text)
                with self.jev():
                    report = self.run_lint()
                joined = "\n".join(report.notes)
                self.assertIn(
                    f"rule 6 claim support: not run (.github/sd-docs-lint.json: {fault}", joined)
                self.assertNotIn("secret_tenant", joined)
                self.assertEqual(report.failures, [])
                self.assertFalse(self.capture.exists(), f"{text!r} sent a request")
                self.assertFalse(self.probed.exists(), f"{text!r} made the run probe jev")

    def test_the_schema_names_the_keys_the_reader_accepts(self) -> None:
        """Two statements of one vocabulary, pinned so they cannot drift."""

        schema = json.loads(
            (REPO_ROOT / ".github" / "sd-docs-lint.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(sorted(schema["properties"]), sorted(lint.JEV_OPT_IN_KNOWN_KEYS))
        self.assertEqual(schema["properties"][lint.JEV_OPT_IN_KEY]["type"], "boolean")

    def test_every_off_word_switches_it_off(self) -> None:
        self.recorded_item()
        for word in lint.sd_lib.JEV_FLAG_OFF:
            for value in (word, word.upper(), f" {word} "):
                with self.subTest(value=value):
                    self.assertTrue(lint.sd_lib.jev_stage_off(value))
        for value in (None, "", "1", "true", "yes", "offf"):
            with self.subTest(value=value):
                self.assertFalse(lint.sd_lib.jev_stage_off(value),
                                 "a typo must not be an outage")

    def test_no_jev_on_path_says_nothing_either(self) -> None:
        """A PATH with git on it and no jev, which is every checkout but one.

        Silent, and that is the half of this flip worth reviewing. `jev` is
        absent from nearly every checkout, so a note here would be a line of
        noise in every pull request in both repositories, forever -- which is
        the exact cost `NOT_ASKED` was created to avoid. The flip must not
        reintroduce it by turning "nobody opted in" into "nobody has jev".

        git is symlinked in rather than the real PATH being kept, because the
        operator running this suite has `jev` on theirs: a test that removed
        nothing would pass by finding the real command, and a test that
        removed everything would fail on `git` before reaching the question.
        """
        self.recorded_item()
        gitless = self.repo / "git-only-bin"
        gitless.mkdir()
        (gitless / "git").symlink_to(shutil.which("git"))
        with mock.patch.dict(os.environ, {"PATH": str(gitless)}):
            self.assertNotIn("claim support", self.notes())

    def test_a_jev_that_cannot_answer_is_silent_too(self) -> None:
        """The third silent reason, and the one review caught.

        Exit 3 is the only non-zero `jev enabled` returns, so a gate that
        says "any non-zero is loud" is saying "every unkeyed machine is
        loud". `jev off` is the documented fleet kill switch; using it would
        then print a line in every pull request in both repositories, which
        is what `NOT_ASKED` exists to prevent. `bin/sd_jev.py` already
        treated 3 as silent, and two gates that disagree are a policy nobody
        can state.
        """

        self.recorded_item()
        with self.jev(JEV_STUB_ENABLED="3"):
            notes = self.notes()
        self.assertNotIn("claim support", notes)
        self.assertFalse(self.capture.exists(), "a switched-off jev was sent a request")

    def test_a_probe_that_fails_some_other_way_is_still_loud(self) -> None:
        """The half that must not go silent with it.

        0 and 3 are the codes `jev enabled` has today. Anything else is a
        `jev` this gate does not understand -- a broken install, a shim, a
        future version -- and that is a run that could have had a reading and
        did not, which is the whole of what the note is for.
        """

        self.recorded_item()
        with self.jev(JEV_STUB_ENABLED="4"):
            notes = self.notes()
        self.assertIn("not run (jev enabled exited 4)", notes)
        self.assertFalse(self.capture.exists(), "a failing probe was sent a request")

    def test_a_weak_answer_is_a_note_and_never_a_failure(self) -> None:
        self.recorded_item()
        with self.jev(JEV_STUB_NOUL="0.10"):
            report = self.run_lint()
        joined = "\n".join(report.notes)
        self.assertIn("`prd.md:3`", joined)
        self.assertIn("0.10", joined)
        self.assertIn("1 of 1 recorded citation(s) answered, 1 under 0.5", joined)
        self.assertEqual(report.failures, [])

    def test_a_confident_answer_is_counted_and_not_named(self) -> None:
        self.recorded_item()
        with self.jev(JEV_STUB_NOUL="0.95"):
            report = self.run_lint()
        joined = "\n".join(report.notes)
        self.assertIn("1 of 1 recorded citation(s) answered, 0 under 0.5", joined)
        self.assertNotIn("may no longer support", joined)
        self.assertEqual(report.failures, [])

    def test_a_broken_jev_changes_neither_the_notes_nor_the_verdict(self) -> None:
        self.recorded_item()
        with self.jev(JEV_STUB_FAIL="1"):
            report = self.run_lint()
        # `0 of 1 ... answered`, not `1 ... 0 under the floor`. A pass that
        # answered nothing and a pass that answered confidently printed the
        # same line until this test was written, which is the whole of how a
        # dead check goes on reading clean.
        self.assertIn("0 of 1 recorded citation(s) answered", "\n".join(report.notes))
        self.assertEqual(report.failures, [])

    def test_only_the_two_passages_leave_the_machine(self) -> None:
        """The payload cap, asserted against what the stub was handed.

        A cap documented in a docstring is a cap nobody re-checks. This reads
        the bytes the command received and refuses every name the linter knows
        -- the item directory, the two file names, the absolute root -- so a
        later edit that widens the state fails here rather than in somebody's
        outbound traffic.
        """
        item = self.recorded_item()
        with self.jev():
            self.run_lint()
        sent = self.capture.read_text(encoding="utf-8")
        for forbidden in (item.name, "prd.md:3", "design.md", str(self.repo), "docs/work"):
            self.assertNotIn(forbidden, sent, f"{forbidden!r} left the machine")
        payload = json.loads(sent)
        self.assertEqual(list(payload), ["citations"])
        self.assertEqual(list(payload["citations"]), ["c1"])
        self.assertEqual(sorted(payload["citations"]["c1"]), ["claim", "evidence"])

    def test_a_long_passage_is_capped_before_it_is_sent(self) -> None:
        item = self.cited_item()
        (item / "prd.md").write_text(
            "---\ntitle: A cited item\ndate: 2026-08-29\nstatus: planning\n---\n"
            + "ladder " * 400 + "\n",
            encoding="utf-8",
        )
        lint.write_citation_manifest(item, self.work)
        with self.jev():
            self.run_lint()
        payload = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertLessEqual(len(payload["citations"]["c1"]["evidence"]), lint.EVIDENCE_CHARS)
        self.assertLessEqual(len(payload["citations"]["c1"]["claim"]), lint.CLAIM_CHARS)


WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"


def docs_lint_step_code(text: str) -> str:
    """The `Docs lint` step with its comment lines removed.

    Comments are dropped because the step's own comment names the spellings
    it rejects, and a test that greps the whole block would read the
    explanation as the code.
    """
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines)
                 if line.strip().startswith("- name: Docs lint"))
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].lstrip()
        if (stripped.startswith("- name:")
                and len(lines[index]) - len(stripped) == indent):
            end = index
            break
    return "".join(line for line in lines[start:end]
                   if not line.lstrip().startswith("#"))


class ChangedPathsComeFromTheMergeRefTests(unittest.TestCase):
    """Rule 8 reads `--changed`, and CI computes it from the merge ref.

    `github.event.pull_request.base.sha` is frozen in the stored payload at
    the base tip the pull request was opened against. It does not move when
    the base does, so on a busy base every merge adds that merge's paths to
    an older pull request's apparent scope, and rule 8 demands a scope class
    for a file the branch never touched. That is sd:1401, and #1151 could not
    be made to pass: two files of its own, nineteen in the computed set.

    The merge ref does not drift. Its first parent is the base as it stands,
    its second the pull request's head, so the diff between the first parent
    and the merge is exactly what the pull request adds. The first test here
    is the reproduction -- it builds both diffs over one history and shows
    them disagreeing -- and the second pins the workflow to the right one.
    """

    def git(self, *args: str) -> str:
        return subprocess.run(("git", *args), cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout

    def commit(self, path: str, message: str) -> str:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(message + "\n", encoding="utf-8")
        self.git("add", path)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def changed(self, *revisions: str) -> list[str]:
        out = self.git("diff", "--name-only", "--no-renames", *revisions)
        return sorted(line for line in out.splitlines() if line)

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "lint@example.invalid")
        self.git("config", "user.name", "Lint")
        self.git("config", "commit.gpgsign", "false")
        # The base as it stood when the pull request was opened. This is the
        # sha the event payload freezes.
        self.opened_against = self.commit("README.md", "base")
        self.git("checkout", "-q", "-b", "feature")
        self.commit("bin/mine.py", "the branch's own change")
        self.git("checkout", "-q", "main")
        # Somebody else's pull request lands while this one waits.
        self.commit("other/theirs.py", "a later merge into the base")
        # What GitHub serves as refs/pull/N/merge: base first, head second.
        self.git("checkout", "-q", "-b", "merge-ref")
        self.git("merge", "-q", "--no-ff", "-m", "merge ref", "feature")

    def test_the_frozen_base_sha_widens_the_set_with_somebody_elses_file(self) -> None:
        self.assertEqual(
            self.changed(f"{self.opened_against}...HEAD"),
            ["bin/mine.py", "other/theirs.py"],
        )

    def test_the_merge_refs_first_parent_reads_the_branchs_own_change_alone(self) -> None:
        self.assertEqual(self.changed("HEAD^1", "HEAD"), ["bin/mine.py"])

    def test_the_workflow_diffs_the_first_parent_and_refuses_a_plain_checkout(self) -> None:
        code = docs_lint_step_code(WORKFLOW.read_text(encoding="utf-8"))
        self.assertIn("git diff --name-only --no-renames HEAD^1 HEAD", code)
        self.assertIn("HEAD^2", code)
        self.assertNotIn("pull_request.base.sha", code)



class ArchiveIsBelowTheWorkRootTests(unittest.TestCase):
    """sd:1540. Only `archive/` below the work root is history.

    The #1177 review found a checkout under a directory named `archive`
    compared `0 of 0` items; the other checks read the same absolute path.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work_root = pathlib.Path(tmp.name).resolve() / "archive" / "repo" / "docs" / "work"
        self.item = self.work_root / "2026-09-01-thing"
        self.item.mkdir(parents=True)
        (self.item / "prd.md").write_text(GOOD_PRD, encoding="utf-8")

    def test_an_item_is_archived_only_below_the_work_root(self) -> None:
        self.assertFalse(lint.is_archived(self.item, self.work_root))
        self.assertTrue(lint.is_archived(self.work_root / "archive" / "2026-08" / "old", self.work_root))

    def test_recording_reads_an_item_in_a_checkout_under_archive(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(lint.record_citations(self.work_root), 0)
        self.assertIn("2026-09-01-thing: recorded", out.getvalue())

    def test_no_check_reads_archive_from_the_absolute_path(self) -> None:
        source = LINT_PATH.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r".*in item\.parts.*", source), [])


if __name__ == "__main__":
    unittest.main()
