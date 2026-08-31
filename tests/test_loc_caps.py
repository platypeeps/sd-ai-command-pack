"""The three line-count ceilings, enforced instead of remembered.

The design fixes a ceiling for each part of the replacement world -- `bin/` at
8,000 lines, the temporary `migrate-*` tools at 1,500 outside it, `dashboard/`
at 2,500 -- and says in as many words that "caps are CI tests; a cap is never
raised in the PR that busts it". Until now they were prose. The retired stack
this repository is replacing reached 95,000 lines one defensible commit at a
time, and no single one of those commits looked like the problem, which is
exactly why the bound has to be mechanical: a number in a design document is
checked by whoever remembers to check it.

Landing the test while every cap passes is deliberate. A cap introduced in the
change that breaks it is a negotiation; a cap introduced with headroom is a
guard, and the next pull request that would cross the line meets a red check
instead of a reviewer's memory.

**Enumerated from `git ls-files`, never from a list here.** Two reasons, both
learned rather than assumed. A hand-written list of files cannot see the
thirteenth one somebody adds next month -- the same trap the Makefile's lint
paths still carry. And walking the directory instead would count whatever is
lying in it: `find bin -type f` once reported this repository at 8,862 lines,
over its own cap, because it swept up `__pycache__/*.pyc`. The index holds
tracked source and nothing else, so it answers the question actually being
asked.
"""

from __future__ import annotations

import pathlib
import subprocess
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Each cap names the design decision it enforces, so a failure points at the
# record rather than at a bare number.
BIN_CAP = 8_000            # LOC discipline, restated after the feasibility audit
MIGRATE_CAP = 1_500        # temporary tools, outside the bin/ cap, deleted at steps 7 and 11
DASHBOARD_CAP = 2_500      # r2 dashboard: stdlib server plus one JS file


def tracked(*pathspecs: str) -> list[pathlib.Path]:
    """Tracked files matching `pathspecs`, as the index reports them."""

    output = subprocess.run(
        ["git", "ls-files", "-z", "--", *pathspecs],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / name for name in output.split("\0") if name]


def line_count(paths: list[pathlib.Path]) -> int:
    total = 0
    for path in paths:
        # A tracked path can be absent from the working tree during a partial
        # checkout. Counting it as zero would understate the total and let a
        # cap pass for the wrong reason, so it is an error, not a skip.
        with path.open(encoding="utf-8") as handle:
            total += sum(1 for _ in handle)
    return total


class LineCountCaps(unittest.TestCase):
    def assert_cap(self, label: str, paths: list[pathlib.Path], cap: int) -> int:
        total = line_count(paths)
        self.assertLessEqual(
            total,
            cap,
            f"{label} is {total} lines against a cap of {cap}. The cap is a design "
            f"decision, not a lint setting: raise it in its own change with its own "
            f"record, never in the pull request that crossed it. Files counted: "
            f"{', '.join(sorted(str(p.relative_to(REPO_ROOT)) for p in paths))}",
        )
        return total

    def test_bin_stays_under_its_ceiling(self) -> None:
        """`bin/` minus the temporary migration tools, which have their own cap."""

        paths = [p for p in tracked("bin") if not p.name.startswith("migrate-")]
        # The enumeration is asserted non-empty before the cap. A pathspec that
        # stopped matching -- a rename, a move, a typo -- would count zero lines
        # and report a clean pass, which is the one way a cap test can fail at
        # its job while looking like it worked. Non-empty is the whole check: a
        # directory pathspec matches everything under it or nothing, so there is
        # no partial-match case for a file-count floor to catch, and a floor
        # would instead fail on a legitimate consolidation.
        self.assertTrue(paths, "bin/ enumeration matched no tracked files")
        self.assert_cap("bin/", paths, BIN_CAP)

    def test_the_migration_tools_stay_under_their_own_ceiling(self) -> None:
        """`migrate-*` is outside the `bin/` cap because it is deleted, not kept.

        An empty result is correct rather than suspicious here: steps 7 and 11
        delete these tools, and a cap on nothing is satisfied. It is asserted
        rather than skipped so the transition is visible in the test output.
        """

        paths = [p for p in tracked("bin") if p.name.startswith("migrate-")]
        if not paths:
            self.assertEqual(paths, [], "no migrate-* tools remain; the cap has no subject")
            return
        self.assert_cap("bin/migrate-*", paths, MIGRATE_CAP)

    def test_the_dashboard_stays_under_its_ceiling(self) -> None:
        """`dashboard/` only.

        `bin/sd-dashboard` is the CLI in front of it and counts against `bin/`,
        where the design's own itemisation puts the dashboard glue. Counting it
        in both places would make the two caps overlap and neither one mean
        what it says.
        """

        paths = tracked("dashboard")
        self.assertTrue(paths, "dashboard/ enumeration matched no tracked files")
        self.assert_cap("dashboard/", paths, DASHBOARD_CAP)


if __name__ == "__main__":
    unittest.main()
