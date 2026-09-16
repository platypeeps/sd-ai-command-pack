"""Criterion 31 of sd:10: the symbols requirement 13 cuts are gone, by grep.

One test per symbol, each a `git grep` over the governed tree -- what runs or
governs, criterion 4's list -- rather than a list of the files the cut was
known to touch. A hand-kept file list proves the cut reached those files; the
grep proves it reached every file, including the one nobody thought carried
the name.

This is 31(a): `sd_sweep`, the age sweep cut under criterion 21. The parts
that follow it, 31(b) the prose symbols and flags and 31(c) the bug
regressions, land in their own pull requests and add their symbols here.

Two things the tree carries by name and this file leaves alone. `docs/work/`
and `CHANGELOG.md` are history, excluded by the criterion's own definition of
the governed tree. `tests/fixtures/*-round.json` are captured review rounds --
`tests/test_sd_review_ack.py` says of the first one, "not an invented
fixture", twelve pull requests read from the GitHub API "as they stand" -- and
a Copilot body in one of them summarises a change to `bin/sd_sweep.py`.
Editing a capture to satisfy a grep would falsify the record the capture is
kept for, so the captures are excluded here by name, as history, and the
exclusion is stated rather than buried in a pattern.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402

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

#: Excluded from every grep below. This file quotes each symbol it searches
#: for, and the review captures are history, see the module docstring.
EXCLUDED = ("tests/test_cut_symbols.py", "tests/fixtures/*-round.json")


def governed_grep(pattern: str) -> list[str]:
    """`git grep` over the governed tree, returning `path:line:text` rows."""
    result = subprocess.run(
        ["git", "grep", "-nIE", pattern, "--", *GOVERNED,
         *(f":(exclude){path}" for path in EXCLUDED)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line]


class TheGrepMeasuresSomething(unittest.TestCase):
    """The control: a grep that could not find a name that is there proves
    nothing about a name that is not."""

    def test_a_symbol_the_tree_does_carry_is_found(self) -> None:
        rows = governed_grep(r"def work_items\(")
        self.assertTrue(rows, "the governed grep found nothing for work_items")


class SweepCut(unittest.TestCase):
    """31(a): `sd_sweep`, the 45-day age sweep, cut under criterion 21."""

    def test_no_governed_file_names_sd_sweep(self) -> None:
        rows = governed_grep(r"sd_sweep")
        self.assertEqual(rows, [], "sd_sweep is still named: " + "; ".join(rows))

    def test_the_module_and_its_suite_are_gone(self) -> None:
        for path in ("bin/sd_sweep.py", "tests/test_sd_sweep.py"):
            self.assertFalse((REPO_ROOT / path).exists(), f"{path} still exists")

    def test_sd_has_no_sweep_verb(self) -> None:
        """The verb, not only the module: a `sweep` group left registered
        against some other handler would still be a sweep code path."""
        sd = sd_lib.sibling("sd_under_cut_symbols", "sd")
        parser = sd.build_parser()
        groups = [action for action in parser._actions
                  if hasattr(action, "choices") and action.choices]
        self.assertEqual(len(groups), 1, "expected one group of top-level verbs")
        verbs = set(groups[0].choices)
        self.assertIn("store", verbs, "the verb enumeration missed a verb that exists")
        self.assertNotIn("sweep", verbs)

    def test_the_aging_basis_survived_the_cut_in_the_library(self) -> None:
        """What `sd-status` read off the sweep now lives in `sd_lib`: the
        threshold and the three functions behind `idle-planning`. The cut
        removed a verb, not the one definition of idle."""
        self.assertEqual(sd_lib.DEFAULT_DAYS, 45)
        for name in ("item_date", "last_active", "touched"):
            self.assertTrue(callable(getattr(sd_lib, name, None)), f"sd_lib.{name} is missing")


if __name__ == "__main__":
    unittest.main()
