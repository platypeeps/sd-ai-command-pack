"""What the 45-day sweep reports, and what it refuses to guess.

The fixtures are shaped after the fleet the first real run found: one
repository holding 34 due items among 48 active, five holding none, and the
exclusions -- `in_progress`, a `branch:` field, an item already parked -- that
make this pass comparable to the bulk-park it succeeds.

`today` is a literal in every test. The rule under test is an arithmetic one
and a test that read the clock would pass or fail depending on the day it ran,
which is the property the module was written to avoid.
"""

from __future__ import annotations

import datetime
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_sweep  # noqa: E402

TODAY = datetime.date(2026, 9, 1)


def make_item(repo: pathlib.Path, name: str, **fields) -> None:
    """One work item, with only the frontmatter lines the caller names."""
    item = repo / "docs" / "work" / name
    item.mkdir(parents=True)
    lines = ["---", f"title: {name}"]
    lines += [f"{key}: {value}" for key, value in fields.items() if value is not None]
    lines += ["---", "", "# body"]
    (item / "prd.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


class Scan(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name) / "repo"
        (self.repo / "docs" / "work").mkdir(parents=True)

    def scan(self, days: int = 45) -> dict:
        return sd_sweep.scan(self.repo, TODAY, days)

    def test_an_item_past_the_threshold_is_due(self) -> None:
        make_item(self.repo, "2026-07-01-old", status="planning", created="2026-07-01")
        got = self.scan()
        self.assertEqual([row["slug"] for row in got["due"]], ["old"])
        self.assertEqual(got["due"][0]["age"], 62)

    def test_the_boundary_is_exclusive_as_the_design_writes_it(self) -> None:
        """`design.md:106` says ">45 days", so exactly 45 is not yet due.

        Both fixtures are needed: one asserting only that 46 is swept would
        pass against `>=`, and one asserting only that 45 is not would pass
        against a sweep that never fires at all.
        """
        make_item(self.repo, "2026-07-17-past-it", status="planning", created="2026-07-17")
        make_item(self.repo, "2026-07-18-exactly-45", status="planning",
                  created="2026-07-18")
        self.assertEqual((TODAY - datetime.date(2026, 7, 18)).days, 45)
        self.assertEqual((TODAY - datetime.date(2026, 7, 17)).days, 46)
        self.assertEqual([row["slug"] for row in self.scan()["due"]], ["past-it"])

    def test_in_progress_is_never_swept_however_old(self) -> None:
        """Somebody's open work. The bulk-park honoured this and so does this."""
        make_item(self.repo, "2020-01-01-ancient", status="in_progress",
                  created="2020-01-01")
        got = self.scan()
        self.assertEqual(got["due"], [])
        self.assertEqual(got["active"], 1)

    def test_a_branch_field_protects_an_old_planning_item(self) -> None:
        """A `branch:` line claims a branch exists for the item.

        This is the second half of the park rule -- `status: planning` AND no
        `branch:` -- and an implementation that checked only the status would
        pass every other test in this file.
        """
        make_item(self.repo, "2020-01-01-claimed", status="planning",
                  created="2020-01-01", branch="task/thing")
        self.assertEqual(self.scan()["due"], [])

    def test_an_already_parked_item_is_neither_due_nor_active(self) -> None:
        """Otherwise every run reports the same items the last run parked."""
        make_item(self.repo, "2020-01-01-done-with", status="planning",
                  created="2020-01-01", parked="2026-09-01 bulk-park (D2)")
        got = self.scan()
        self.assertEqual(got["due"], [])
        self.assertEqual(got["active"], 0)

    def test_an_archived_item_is_out_of_scope(self) -> None:
        month = self.repo / "docs" / "work" / "archive" / "2026-07"
        month.mkdir(parents=True)
        (month / "2020-01-01-shipped").mkdir()
        got = self.scan()
        self.assertEqual(got["due"], [])
        self.assertEqual(got["active"], 0)

    def test_an_undated_item_is_reported_and_not_swept(self) -> None:
        """Zero days old hides it forever; infinitely old sweeps it blindly.

        Neither is an answer, so it goes in its own list where a person has to
        look at it.
        """
        make_item(self.repo, "untitled-thing", status="planning")
        got = self.scan()
        self.assertEqual(got["due"], [])
        self.assertEqual([row["slug"] for row in got["undated"]], ["untitled-thing"])
        self.assertEqual(got["active"], 1)

    def test_the_directory_prefix_dates_an_item_whose_frontmatter_does_not(self) -> None:
        """Every templated item carries one, and the bulk-park sorted on it."""
        make_item(self.repo, "2026-01-01-no-created-line", status="planning")
        got = self.scan()
        self.assertEqual([row["slug"] for row in got["due"]], ["no-created-line"])
        self.assertEqual(got["due"][0]["dir"], "2026-01-01-no-created-line")
        self.assertEqual(got["undated"], [])

    def test_created_outranks_the_directory_prefix(self) -> None:
        """The item's own statement about itself wins.

        A directory renamed or copied from another item carries a date that is
        not this item's, so the frontmatter is the more trustworthy of the two
        whenever both exist.
        """
        make_item(self.repo, "2020-01-01-stale-prefix", status="planning",
                  created="2026-08-30")
        self.assertEqual(self.scan()["due"], [])

    def test_an_unparseable_created_falls_back_rather_than_crashing(self) -> None:
        """`created: soon` is a real thing a person types."""
        make_item(self.repo, "2026-01-01-vague", status="planning", created="soon")
        got = self.scan()
        self.assertEqual([row["slug"] for row in got["due"]], ["vague"])

    def test_a_garbage_date_everywhere_is_undated_not_an_error(self) -> None:
        make_item(self.repo, "2026-13-45-impossible", status="planning", created="nope")
        got = self.scan()
        self.assertEqual([row["slug"] for row in got["undated"]], ["impossible"])

    def test_days_changes_what_is_due(self) -> None:
        """`--days` asks what another threshold would catch, and must move."""
        make_item(self.repo, "2026-08-15-recent", status="planning", created="2026-08-15")
        self.assertEqual(self.scan(45)["due"], [])
        self.assertEqual(len(self.scan(10)["due"]), 1)


class Sweep(unittest.TestCase):
    """The fleet shape, over the same scan."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)

    def repo(self, name: str) -> pathlib.Path:
        path = self.root / name
        (path / "docs" / "work").mkdir(parents=True)
        return path

    def test_repositories_are_ordered_by_how_much_they_owe(self) -> None:
        """34 of the fleet's due items sat in one repository.

        Alphabetical order would have put that repository fifth and the report
        would read as an even spread, which is the opposite of what it found.
        """
        quiet = self.repo("aaa-quiet")
        loud = self.repo("zzz-loud")
        make_item(quiet, "2026-07-01-one", status="planning", created="2026-07-01")
        for n in range(3):
            make_item(loud, f"2026-07-0{n}-x", status="planning", created="2026-07-01")
        got = sd_sweep.sweep([("aaa-quiet", quiet), ("zzz-loud", loud)], TODAY)
        self.assertEqual([row["repo"] for row in got["repos"]], ["zzz-loud", "aaa-quiet"])
        self.assertEqual(got["due"], 4)

    def test_a_repository_with_nothing_live_is_left_out(self) -> None:
        """Six checkouts had items; thirteen exist. The rest are silence."""
        empty = self.repo("empty")
        has = self.repo("has")
        make_item(has, "2026-07-01-x", status="planning", created="2026-07-01")
        got = sd_sweep.sweep([("empty", empty), ("has", has)], TODAY)
        self.assertEqual([row["repo"] for row in got["repos"]], ["has"])

    def test_a_repository_with_live_items_and_nothing_due_still_reports(self) -> None:
        """`active` is the denominator; dropping the repo would misstate it."""
        repo = self.repo("busy")
        make_item(repo, "2026-08-30-fresh", status="planning", created="2026-08-30")
        got = sd_sweep.sweep([("busy", repo)], TODAY)
        self.assertEqual(got["active"], 1)
        self.assertEqual(got["due"], 0)

    def test_the_totals_add_up_across_repositories(self) -> None:
        first = self.repo("one")
        second = self.repo("two")
        make_item(first, "2026-07-01-a", status="planning", created="2026-07-01")
        make_item(first, "2026-08-30-b", status="in_progress", created="2026-08-30")
        make_item(second, "no-date", status="planning")
        got = sd_sweep.sweep([("one", first), ("two", second)], TODAY)
        self.assertEqual((got["due"], got["undated"], got["active"]), (1, 1, 3))


class Render(unittest.TestCase):
    def test_an_empty_report_says_so_rather_than_printing_nothing(self) -> None:
        """Silence reads as a broken command, especially from a scheduled run."""
        lines = sd_sweep.render(
            {"days": 45, "today": "2026-09-01", "repos": [], "due": 0,
             "undated": 0, "active": 0})
        self.assertEqual(lines, ["nothing over 45 days: 0 active"])

    def test_oldest_first_within_a_repository(self) -> None:
        report = {
            "days": 45, "today": "2026-09-01", "due": 2, "undated": 0, "active": 2,
            "repos": [{
                "repo": "one", "active": 2, "undated": [],
                "due": [{"slug": "younger", "age": 50}, {"slug": "older", "age": 90}],
            }],
        }
        lines = sd_sweep.render(report)
        self.assertLess(
            next(i for i, line in enumerate(lines) if "older" in line),
            next(i for i, line in enumerate(lines) if "younger" in line),
        )


if __name__ == "__main__":
    unittest.main()
