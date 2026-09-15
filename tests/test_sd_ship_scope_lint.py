"""`sd-ship prepare` lints the pull request body with or without a work root.

Rule 8 of `sd-docs-lint`, the scope check, was reached only inside
`sd-ship`'s `if work.is_dir()` block: the linter fails on a missing work
root before any rule runs, so `sd-ship` withheld the whole call in a
repository with no planning directory, and a pull request there could change
`.github/**` and ship without the scope line the template asks for (#972
review, the suppressed finding on `skills/sd-ship/SKILL.md:68`). Now the call
is made in both cases, with `--body-only` when there is no work root.

The fixture is `tests/test_sd_ship.py`'s, whose clone has no `docs/work`
unless a test makes one, so its default shape is the no-work-root case.
"""
from __future__ import annotations

import pathlib
import unittest
from unittest.mock import patch

from sd_db.testing.remote import _git

from tests import test_sd_ship as ship_fixture

ship = ship_fixture.ship

SCOPE_POLICY = (
    "# Repository Copilot Instructions\n\n"
    "| Line | Paths | Grounds |\n|---|---|---|\n"
    "| `CI/review scope:` | `.github/**`, `Makefile` | The CI surface. |\n"
)


class ScopeLintCase(unittest.TestCase):
    setUp = ship_fixture.ShipCase.setUp
    args = ship_fixture.ShipCase.args
    operation = ship_fixture.ShipCase.operation
    prepare = ship_fixture.ShipCase.prepare

    def lint_calls(self, *extra: str) -> list[list[str]]:
        calls: list[list[str]] = []
        original = ship.run

        def recording(root, argv, **kwargs):
            calls.append([str(word) for word in argv])
            return original(root, argv, **kwargs)

        with patch.object(ship, "run", recording):
            self.assertEqual(self.prepare(*extra)["phase"], "ready_to_send")
        return [argv for argv in calls if argv[1].endswith("sd-docs-lint")]

    def commit_a_ci_change(self) -> None:
        # The policy file is on the branch, because the linter reads it from
        # the checkout, and the workflow is the path that demands the line.
        for name, text in ((".github/copilot-instructions.md", SCOPE_POLICY),
                           (".github/workflows/tests.yml", "on: push\n")):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            _git(self.root, "add", name)
        _git(self.root, "commit", "-m", "touch the CI surface\n\nAuthored-with: human")

    def test_with_no_work_root_the_body_is_linted_in_body_only_mode(self) -> None:
        self.assertFalse((self.root / "docs/work").exists(), "the fixture grew a work root")
        lint = self.lint_calls()
        self.assertEqual(len(lint), 1, lint)
        self.assertIn("--body-only", lint[0])
        self.assertEqual(lint[0][-2], "--pr-body")
        self.assertFalse(pathlib.Path(lint[0][-1]).exists(), "the body file is temporary")

    def test_with_a_work_root_every_rule_runs_and_the_flag_is_absent(self) -> None:
        (self.root / "docs/work").mkdir(parents=True)
        lint = self.lint_calls()
        self.assertEqual(len(lint), 1, lint)
        self.assertNotIn("--body-only", lint[0])

    def test_red_a_ci_diff_with_no_scope_line_and_no_work_root_is_refused_before_push(self) -> None:
        # The fail-first case. Before #972's second push the linter was not
        # run here at all, and this prepare reached `ready_to_send`.
        self.commit_a_ci_change()
        with self.assertRaisesRegex(ship.Refusal, r'carries no "CI/review scope:" line'):
            self.prepare()
        self.assertEqual(self.remote.pull_requests, {}, "nothing was pushed or opened")

    def test_green_the_same_diff_with_the_line_reaches_ready_to_send(self) -> None:
        self.commit_a_ci_change()
        body = self.directory / "body.md"
        body.write_text("A workflow.\n\nCI/review scope: one workflow added.\n")
        self.assertEqual(self.prepare("--body-file", str(body))["phase"], "ready_to_send")


if __name__ == "__main__":
    unittest.main()
