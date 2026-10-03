"""`sd-ship prepare` gates on the docs-lint failures a branch introduces (sd:1646).

A tree failure already on the default branch made every prepare there fail,
whatever the branch changed (hoa #135, anomaly-metric-creator #454,
rwbp-coordinator #307, rwbp-website #344 on 2026-09-26). Now a failed lint is
run again against `origin/<base>`: a failure the base already has comes back
as a warning, and only the failures the branch introduces refuse.

The fixture is `tests/test_sd_ship.py`'s. A work directory named without its
date is the tree failure: rule 1 reports it with no database row needed.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sd_db.testing.remote import _git

from tests import test_sd_ship as ship_fixture

ship = ship_fixture.ship

BAD_NAME = "a work item directory is named <YYYY-MM-DD>-<slug>"


class LintBaseCase(unittest.TestCase):
    setUp = ship_fixture.ShipCase.setUp
    args = ship_fixture.ShipCase.args
    operation = ship_fixture.ShipCase.operation
    prepare = ship_fixture.ShipCase.prepare

    def commit_item(self, name: str) -> None:
        prd = self.root / "docs/work" / name / "prd.md"
        prd.parent.mkdir(parents=True, exist_ok=True)
        prd.write_text(f"---\ntitle: {name}\ncreated: 2026-09-26\n---\n\n# {name}\n", encoding="utf-8")
        _git(self.root, "add", str(prd.relative_to(self.root)))
        _git(self.root, "commit", "-m", f"add {name}\n\nAuthored-with: human")

    def break_the_base(self) -> None:
        """Land a misnamed work directory on origin/main, then bring the branch up to date."""
        branch = _git(self.root, "branch", "--show-current").strip()
        _git(self.root, "checkout", "-q", "-b", "base-change", "origin/main")
        self.commit_item("old-item")
        _git(self.root, "push", "-q", "origin", "HEAD:refs/heads/main")
        _git(self.root, "fetch", "-q", "origin")
        _git(self.root, "checkout", "-q", branch)
        _git(self.root, "merge", "-q", "--no-edit", "origin/main")

    def test_a_failure_already_on_the_base_warns_and_does_not_block(self) -> None:
        self.break_the_base()
        result = self.prepare()
        self.assertEqual(result["phase"], "ready_to_send")
        said = "\n".join(result["warnings"])
        self.assertIn("already on origin/main", said)
        self.assertIn(f"docs/work/old-item: {BAD_NAME}", said)
        self.assertEqual(_git(self.root, "worktree", "list", "--porcelain").count("worktree "), 1,
                         "the base tree is removed again")

    def test_a_failure_the_branch_introduces_refuses_and_names_only_it(self) -> None:
        self.break_the_base()
        self.commit_item("new-item")
        with self.assertRaises(ship.Refusal) as caught:
            self.prepare()
        said = str(caught.exception)
        self.assertIn(f"docs/work/new-item: {BAD_NAME}", said)
        self.assertNotIn("docs/work/old-item", said)
        self.assertIn("1 more failure(s) already on origin/main", said)
        self.assertEqual(caught.exception.workflow["blocker"]["code"], "docs_lint_failed")
        self.assertEqual(self.remote.pull_requests, {}, "nothing was pushed or opened")


TRACEBACK = ("Traceback (most recent call last):\n  File \"sd-docs-lint\", line 1, in <module>\n"
             "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte\n")


class UnparsedLintExit(unittest.TestCase):
    """A non-zero lint exit with no `FAIL` line is not a clean answer (sd:1646 review).

    `sd-docs-lint` also exits 1 on an uncaught exception, such as a
    `UnicodeDecodeError` reading tracked markdown, and prints only the
    traceback. Read as zero failures, that let prepare go on through review
    with the lint never finished. Only two runs that both parsed may excuse
    anything; otherwise the refusal stands, with the raw output.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def answering(self, *lint_answers: tuple[int, str]):
        """`completed_process` with git succeeding and each lint run answering in turn."""
        answers = list(lint_answers)

        def fake(cwd, argv, **kwargs):
            if argv[0] == "git":
                return subprocess.CompletedProcess(argv, 0, "", "")
            code, stderr = answers.pop(0)
            return subprocess.CompletedProcess(argv, code, "", stderr)
        return patch.object(ship.sd_ship_body, "completed_process", fake)

    def test_a_branch_run_that_printed_only_a_traceback_refuses_with_it(self) -> None:
        with self.answering((1, TRACEBACK)), self.assertRaises(ship.Refusal) as caught:
            ship.sd_ship_body.lint_against_base(self.root, ["sd-docs-lint"], "main")
        self.assertEqual(caught.exception.workflow["blocker"]["code"], "docs_lint_failed")
        self.assertIn("UnicodeDecodeError", str(caught.exception))

    def test_a_base_run_that_printed_only_a_traceback_excuses_nothing(self) -> None:
        failure = f"FAIL {self.root}/docs/work/old-item: {BAD_NAME}\n"
        with self.answering((1, failure), (1, TRACEBACK)), self.assertRaises(ship.Refusal) as caught:
            ship.sd_ship_body.lint_against_base(self.root, ["sd-docs-lint"], "main")
        self.assertIn(f"docs/work/old-item: {BAD_NAME}", str(caught.exception))
        self.assertEqual(caught.exception.workflow["blocker"]["code"], "docs_lint_failed")


if __name__ == "__main__":
    unittest.main()
