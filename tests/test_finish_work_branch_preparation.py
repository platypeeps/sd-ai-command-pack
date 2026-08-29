"""Contract tests for the finish-work branch preparation ordering.

Owner task: 07-30-resolve-branch-field-finalization-deadlock.

The pre-archive gate refuses a completion-ready task whose ``branch`` is null,
and ``task.py start`` never writes that field. Recording it after the
finalization base is captured puts the write inside the archive commit, which
completion validation reads as a changed field. Step 4 therefore has to record
a missing branch *before* the base capture, and these assertions pin that
ordering in both shipped copies of the skill so a later edit cannot quietly
move the preparation back below the capture and reopen the deadlock.
"""

from __future__ import annotations

import re
import unittest

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

install = _support.install

SKILL_ROOTS = ("templates/.agents",)

PREPARATION = (
    "When an active task is selected for completion, record any missing "
    "branch before capturing the finalization base."
)
BASE_CAPTURE = "Capture the current commit as the finalization base."
DETACHED_HEAD_STOP = (
    "If that value is empty because the checkout is on a detached HEAD, or if "
    "it equals the record's `base_branch`, stop and report instead of guessing"
)
SKIPPED_PATHS = (
    "the planning finalization boundary and the no-active-task successor path "
    "below both skip it"
)


def _skill_text(root: str) -> str:
    path = install.ROOT / root / "skills/sd-finish-work/SKILL.md"
    return path.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class FinishWorkBranchPreparationTests(unittest.TestCase):
    def test_preparation_precedes_the_base_capture(self) -> None:
        for root in SKILL_ROOTS:
            with self.subTest(root=root):
                normalized = _normalize(_skill_text(root))
                preparation = normalized.find(_normalize(PREPARATION))
                capture = normalized.find(_normalize(BASE_CAPTURE))
                self.assertNotEqual(
                    preparation, -1, f"{root}: missing the branch preparation"
                )
                self.assertNotEqual(
                    capture, -1, f"{root}: missing the finalization base capture"
                )
                self.assertLess(
                    preparation,
                    capture,
                    f"{root}: the branch preparation must precede the "
                    "finalization base capture; recording it afterwards puts "
                    "the write inside the archive commit",
                )

    def test_preparation_names_its_stops(self) -> None:
        for root in SKILL_ROOTS:
            with self.subTest(root=root):
                normalized = _normalize(_skill_text(root))
                self.assertIn(_normalize(DETACHED_HEAD_STOP), normalized)

    def test_preparation_is_scoped_to_the_completion_path(self) -> None:
        for root in SKILL_ROOTS:
            with self.subTest(root=root):
                normalized = _normalize(_skill_text(root))
                self.assertIn(_normalize(SKIPPED_PATHS), normalized)

    def test_invalid_gate_result_is_still_a_stop(self) -> None:
        """The preparation must not read as license to repair a failed gate."""

        for root in SKILL_ROOTS:
            with self.subTest(root=root):
                normalized = _normalize(_skill_text(root))
                self.assertIn(
                    _normalize("do not attempt a repair by mutating the task"),
                    normalized,
                )


if __name__ == "__main__":
    unittest.main()
