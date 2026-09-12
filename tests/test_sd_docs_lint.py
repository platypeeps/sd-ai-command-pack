"""Green and red fixtures for each of the six rules in bin/sd-docs-lint."""

from __future__ import annotations

import contextlib
import importlib.util
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


class Rule2StatusSourceTests(LintFixture):
    """The run says where rule 2 read its statuses, because the two sources
    check different item sets and print the same `clean`."""

    def source_note(self) -> str:
        report = self.run_lint()
        return next(note for note in report.notes if note.startswith("rule 2 status source:"))

    def test_no_marker_reads_the_line(self) -> None:
        self.assertIn("the status: line in prd.md", self.source_note())

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

    def cited_item(self) -> pathlib.Path:
        item = self.write_item("2026-08-29-a-cited-item", GOOD_PRD)
        (item / "design.md").write_text(
            "# design\n\nThe ladder is at `prd.md:3`.\n", encoding="utf-8"
        )
        return item

    def record(self) -> int:
        return lint.write_citation_manifest(self.cited_item(), self.work)

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
        self.assertEqual(lint.write_citation_manifest(item, self.work), 1)
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

    def test_red_a_malformed_manifest_row(self) -> None:
        item = self.cited_item()
        (item / lint.CITATION_MANIFEST).write_text("two\tfields\n", encoding="utf-8")
        self.assert_fails("a manifest row is not five fields")

    def test_an_item_with_no_manifest_is_not_checked(self) -> None:
        self.cited_item()
        report = self.run_lint()
        self.assertEqual(report.failures, [])
        self.assertIn("across 0 recorded item(s)", "\n".join(report.notes))

    def test_the_manifest_is_not_a_stray_file_under_rule_1(self) -> None:
        self.record()
        self.assert_clean()

    def test_a_citation_that_leaves_the_work_root_does_not_resolve(self) -> None:
        item = self.cited_item()
        (item / "design.md").write_text(
            "See `../../../etc/passwd.md:1`.\n", encoding="utf-8"
        )
        self.assertEqual(lint.item_citations(item, self.work), [])

    def test_a_citation_into_code_is_left_to_the_adjacency_rule(self) -> None:
        item = self.cited_item()
        (item / "design.md").write_text("The reader is at `bin/sd:1378`.\n", encoding="utf-8")
        self.assertEqual(lint.item_citations(item, self.work), [])

    def test_a_citation_below_the_log_heading_is_a_quotation_not_a_claim(self) -> None:
        item = self.cited_item()
        (item / "design.md").write_text(
            "# design\n\nThe ladder is at `prd.md:3`.\n\n"
            "## Log\n\n- C-1: `prd.md:3` was wrong on the day.\n",
            encoding="utf-8",
        )
        citations = lint.item_citations(item, self.work)
        self.assertEqual([entry[0] for entry in citations], ["design.md:3"])

    def test_a_blank_target_line_anchors_to_the_text_under_it(self) -> None:
        item = self.cited_item()
        prd = item / "prd.md"
        lines = prd.read_text(encoding="utf-8").splitlines()
        lines[2] = ""
        prd.write_text("\n".join(lines) + "\n", encoding="utf-8")
        lint.write_citation_manifest(item, self.work)
        recorded = (item / lint.CITATION_MANIFEST).read_text(encoding="utf-8").split("\t")
        self.assertNotEqual(recorded[4].strip(), "")


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


if __name__ == "__main__":
    unittest.main()
