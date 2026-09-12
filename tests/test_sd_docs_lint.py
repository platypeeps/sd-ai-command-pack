"""Green and red fixtures for each of the six rules in bin/sd-docs-lint."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import pathlib
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

    def run_lint(self, pr_body: str | None = None) -> lint.Report:
        # Staged, not committed: `ls-files` reads the index, and every test
        # here writes its fixture immediately before asking for a verdict.
        self.git("add", "-A")
        return lint.run(self.repo, "docs/work", "docs/spec", "docs/decisions", pr_body)

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

    def assert_fails(self, needle: str, pr_body: str | None = None) -> list[str]:
        report = self.run_lint(pr_body)
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


if __name__ == "__main__":
    unittest.main()
