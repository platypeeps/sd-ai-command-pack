"""What the 45-day sweep reports, and what it refuses to guess.

The fixtures are shaped after the fleet the first real run found: one
repository holding 34 due items among 48 active, five holding none, and the
exclusions -- `in_progress` and an item already parked -- that make this pass
comparable to the bulk-park it succeeds. A `branch:` field was a third, until
it was found to hide an item on the strength of a claim nobody resolved; it now
annotates and excludes nothing, and the tests below are that difference.

`today` is a literal in every test. The rule under test is an arithmetic one
and a test that read the clock would pass or fail depending on the day it ran,
which is the property the module was written to avoid.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

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


GIT_RECORDER = """#!/usr/bin/env python3
'''A `git` that logs its argv and answers `ls-remote` from a fixture.

Everything else is handed to the real git, so `for-each-ref` reads the real
local heads of the real fixture checkout and only the network half is canned.
'''
import json, os, subprocess, sys

argv = sys.argv[1:]
with open(os.environ["GIT_CALLS"], "a", encoding="utf-8") as log:
    log.write(json.dumps(argv) + "\\n")
if "ls-remote" in argv:
    if os.environ.get("GIT_LS_REMOTE_FAILS"):
        sys.stderr.write("fatal: could not read from remote\\n")
        sys.exit(128)
    for name in json.loads(os.environ.get("GIT_REMOTE_HEADS", "[]")):
        print("0" * 40 + "\\trefs/heads/" + name)
    sys.exit(0)
sys.exit(subprocess.run([os.environ["GIT_REAL"], *argv]).returncode)
"""


class BranchResolution(unittest.TestCase):
    """Criteria 1 through 5: the `branch:` field is resolved, not believed.

    The recorder shadows `git` on `PATH` rather than patching `sd_lib`, so the
    real subprocess policy -- the timeout, the fixed argv, failure-is-None --
    runs against a process that answers from a fixture. Only `ls-remote` is
    canned; local heads come from a real `git init` in the fixture directory.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.log = self.tmp / "git-calls.log"
        real = shutil.which("git")
        self.assertIsNotNone(real, "git must be installed to run this test")
        bindir = self.tmp / "bin"
        bindir.mkdir()
        (bindir / "git").write_text(GIT_RECORDER, encoding="utf-8")
        (bindir / "git").chmod(0o755)
        self.env = {
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "GIT_CALLS": str(self.log),
            "GIT_REAL": str(real),
        }

    def repo_with(self, *locals_: str) -> pathlib.Path:
        """A real checkout holding these local branches and a fake remote."""
        root = self.tmp / f"repo-{len(list(self.tmp.iterdir()))}"
        (root / "docs" / "work").mkdir(parents=True)
        run = lambda *a: subprocess.run(  # noqa: E731 - one shape, six uses
            ["git", *a], cwd=root, check=True, capture_output=True,
            env={**os.environ, **self.env})
        run("init", "--quiet", "--initial-branch=main")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "t")
        run("config", "commit.gpgsign", "false")
        run("remote", "add", "origin", "https://example.invalid/r.git")
        (root / "seed").write_text("seed\n", encoding="utf-8")
        run("add", "-A")
        run("commit", "--quiet", "-m", "seed")
        for name in locals_:
            run("branch", name)
        return root

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text("utf-8").splitlines()]

    def heads(self, root: pathlib.Path, *remote: str,
              fails: bool = False) -> frozenset[str] | None:
        environ = dict(os.environ)
        environ.update(self.env)
        environ["GIT_REMOTE_HEADS"] = json.dumps(list(remote))
        if fails:
            environ["GIT_LS_REMOTE_FAILS"] = "1"
        with unittest.mock.patch.dict(os.environ, environ, clear=True):
            return sd_sweep.branches(root)

    def due(self, root: pathlib.Path, heads: frozenset[str] | None) -> list[dict]:
        return sd_sweep.scan(root, TODAY, 45, heads)["due"]

    # --- criterion 1 -----------------------------------------------------

    def test_a_deleted_branch_is_annotated_gone_and_the_item_is_due(self) -> None:
        """The defect this item exists for: the claim outlived the branch."""
        root = self.repo_with()
        make_item(root, "2020-01-01-claimed", status="planning",
                  created="2020-01-01", branch="task/deleted")
        due = self.due(root, self.heads(root))
        self.assertEqual([row["slug"] for row in due], ["claimed"])
        self.assertEqual(due[0]["branch_state"], sd_sweep.GONE)

    # --- criterion 2 -----------------------------------------------------

    def test_a_live_branch_is_annotated_live_and_the_item_is_still_due(self) -> None:
        """Liveness is advisory. The annotation changes; the listing does not."""
        root = self.repo_with("task/live")
        make_item(root, "2020-01-01-claimed", status="planning",
                  created="2020-01-01", branch="task/live")
        due = self.due(root, self.heads(root))
        self.assertEqual([row["slug"] for row in due], ["claimed"])
        self.assertEqual(due[0]["branch_state"], sd_sweep.LIVE)

    def test_a_branch_only_on_the_remote_is_live(self) -> None:
        """Not every live branch has been fetched here."""
        root = self.repo_with()
        make_item(root, "2020-01-01-claimed", status="planning",
                  created="2020-01-01", branch="task/theirs")
        due = self.due(root, self.heads(root, "task/theirs"))
        self.assertEqual(due[0]["branch_state"], sd_sweep.LIVE)

    def test_an_item_with_no_branch_field_gets_no_annotation(self) -> None:
        """Absence of a claim is not a claim that could not be checked."""
        root = self.repo_with()
        make_item(root, "2020-01-01-plain", status="planning", created="2020-01-01")
        due = self.due(root, self.heads(root))
        self.assertNotIn("branch_state", due[0])

    # --- criterion 3 -----------------------------------------------------

    def test_the_same_branch_name_resolves_per_root(self) -> None:
        """One name, two repositories, two answers.

        A resolution that reached for the current working directory would give
        both items the same annotation and pass every test above.
        """
        has = self.repo_with("shared/name")
        lacks = self.repo_with()
        for root in (has, lacks):
            make_item(root, "2020-01-01-claimed", status="planning",
                      created="2020-01-01", branch="shared/name")
        self.assertEqual(self.due(has, self.heads(has))[0]["branch_state"], sd_sweep.LIVE)
        self.assertEqual(self.due(lacks, self.heads(lacks))[0]["branch_state"], sd_sweep.GONE)

    def test_sweep_resolves_each_root_against_itself(self) -> None:
        """Criterion 3 at the level that walks the roots.

        `scan` takes the answer as an argument, so a test that calls it
        directly proves the annotation and not the resolution. Only `sweep`
        chooses which root to ask, and a `sweep` that asked the first root
        about every item would pass every other test in this class.
        """
        has = self.repo_with("shared/name")
        lacks = self.repo_with()
        for root in (has, lacks):
            make_item(root, "2020-01-01-claimed", status="planning",
                      created="2020-01-01", branch="shared/name")
        environ = {**os.environ, **self.env, "GIT_REMOTE_HEADS": "[]"}
        with unittest.mock.patch.dict(os.environ, environ, clear=True):
            report = sd_sweep.sweep([("has", has), ("lacks", lacks)], TODAY, 45)
        states = {row["repo"]: row["due"][0]["branch_state"] for row in report["repos"]}
        self.assertEqual(states, {"has": sd_sweep.LIVE, "lacks": sd_sweep.GONE})

    # --- criterion 4 -----------------------------------------------------

    def test_a_root_that_is_not_a_checkout_answers_unknown(self) -> None:
        """"git cannot answer" is not "the branch is absent"."""
        root = self.tmp / "not-a-repo"
        (root / "docs" / "work").mkdir(parents=True)
        make_item(root, "2020-01-01-claimed", status="planning",
                  created="2020-01-01", branch="task/whatever")
        self.assertIsNone(self.heads(root))
        due = self.due(root, self.heads(root))
        self.assertEqual([row["slug"] for row in due], ["claimed"])
        self.assertEqual(due[0]["branch_state"], sd_sweep.UNKNOWN)

    def test_a_failing_remote_query_is_unknown_not_gone(self) -> None:
        """The local half succeeded; that is not enough to call a branch gone."""
        root = self.repo_with("task/local")
        self.assertIsNone(self.heads(root, fails=True))

    def test_the_unknown_root_says_so_once_beside_its_heading(self) -> None:
        report = {"days": 45, "today": "2026-09-01", "due": 2, "undated": 0, "active": 2,
                  "repos": [{"repo": "r", "active": 2, "undated": [], "branches": "unknown",
                             "due": [{"slug": "a", "age": 99, "branch": "x",
                                      "branch_state": sd_sweep.UNKNOWN},
                                     {"slug": "b", "age": 98, "branch": "y",
                                      "branch_state": sd_sweep.UNKNOWN}]}]}
        lines = sd_sweep.render(report)
        said = [line for line in lines if "could not list" in line]
        self.assertEqual(len(said), 1, lines)

    # --- criterion 5 -----------------------------------------------------

    def test_one_remote_query_per_root_classifies_two_remote_only_branches(self) -> None:
        """C-20's case: a query filtered by one branch could only answer for it."""
        root = self.repo_with()
        for name in ("first", "second"):
            make_item(root, f"2020-01-0{len(name) % 9}-{name}", status="planning",
                      created="2020-01-01", branch=f"task/{name}")
        heads = self.heads(root, "task/first", "task/second")
        states = {row["slug"]: row["branch_state"] for row in self.due(root, heads)}
        self.assertEqual(set(states.values()), {sd_sweep.LIVE}, states)
        self.assertEqual(len(states), 2)
        listings = [c for c in self.calls() if "ls-remote" in c]
        self.assertEqual(len(listings), 1, listings)
        self.assertNotIn("task/first", listings[0])

    def test_the_item_count_is_the_same_across_all_three_annotations(self) -> None:
        """One fixture, three answers from git, one listing.

        Three separate tests each asserting their own count would pass while
        disagreeing with each other.
        """
        counts = set()
        for heads in (self.heads(self.repo_with()),  # gone
                      frozenset({"task/x"}),          # live
                      None):                          # unknown
            root = self.repo_with()
            make_item(root, "2020-01-01-claimed", status="planning",
                      created="2020-01-01", branch="task/x")
            counts.add(len(self.due(root, heads)))
        self.assertEqual(counts, {1})


if __name__ == "__main__":
    unittest.main()
