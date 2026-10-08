"""`sd-ship prepare` lints the pull request body with or without a work root.

With no work root the call runs with `--body-only`. No scope line is required:
`sd-docs-lint` rule 8 is retired (sd:2999).

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
        return [argv for argv in calls if any(word.endswith("sd-docs-lint") for word in argv)]

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

    def test_the_lint_takes_no_claim_support_reading(self) -> None:
        """sd:2762. The reading is advisory and takes minutes through the
        local Kev; inside prepare it buys nothing, so the call switches it off."""
        (self.root / "docs/work").mkdir(parents=True)
        lint = self.lint_calls()
        self.assertEqual(lint[0][:2], ["env", "JEV_SD_DOCS_LINT=0"], lint)

    def test_a_ci_diff_with_no_scope_line_still_reaches_ready_to_send(self) -> None:
        # sd:2999: no scope line is required.
        self.commit_a_ci_change()
        self.assertEqual(self.prepare()["phase"], "ready_to_send")

    def test_green_the_same_diff_with_the_line_reaches_ready_to_send(self) -> None:
        self.commit_a_ci_change()
        body = self.directory / "body.md"
        body.write_text("A workflow.\n\nCI/review scope: one workflow added.\n")
        self.assertEqual(self.prepare("--body-file", str(body))["phase"], "ready_to_send")


if __name__ == "__main__":
    unittest.main()
