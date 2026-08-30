"""Green and red fixtures for each of the five rules in bin/sd-docs-lint."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import pathlib
import tempfile
import unittest
from types import ModuleType

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

    def run_lint(self, pr_body: str | None = None) -> lint.Report:
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
        self.assert_fails("prd.md, design.md and implement.md only")

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

    def test_red_in_progress_without_a_branch(self) -> None:
        self.write_item(
            "2026-08-30-adrift",
            GOOD_PRD.replace("status: ready", "status: in_progress").replace(
                "created: 2026-08-29", "created: 2026-08-30"
            ),
        )
        self.assert_fails("records the branch it lives on")


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
    def test_green_work_line_resolving_with_no_unchecked_boxes(self) -> None:
        report = self.run_lint("Work: docs/work/2026-08-29-a-workable-item\n")
        self.assertEqual(report.failures, [])

    def test_green_declared_absence_with_a_reason(self) -> None:
        report = self.run_lint("Work: none - typo fix in a comment\n")
        self.assertEqual(report.failures, [])

    def test_red_no_work_line(self) -> None:
        self.assert_fails("needs a Work: line", pr_body="Fixes a typo.\n")

    def test_red_two_work_lines(self) -> None:
        self.assert_fails(
            "exactly one is allowed",
            pr_body="Work: docs/work/2026-08-29-a-workable-item\nWork: none - other\n",
        )

    def test_red_none_without_a_reason(self) -> None:
        self.assert_fails("needs a reason", pr_body="Work: none\n")

    def test_red_item_does_not_exist(self) -> None:
        self.assert_fails(
            "does not resolve to a work item", pr_body="Work: docs/work/2026-01-01-ghost\n"
        )

    def test_red_path_outside_the_work_directory(self) -> None:
        self.assert_fails("is not a path under", pr_body="Work: docs/spec/backend\n")

    def test_red_unchecked_box_in_the_item(self) -> None:
        self.write_item(
            "2026-08-29-a-workable-item",
            GOOD_PRD.replace("- [x] the thing works", "- [ ] the thing works"),
        )
        self.assert_fails(
            "unchecked box", pr_body="Work: docs/work/2026-08-29-a-workable-item\n"
        )


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


if __name__ == "__main__":
    unittest.main()
