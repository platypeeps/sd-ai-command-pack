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


class Activity(unittest.TestCase):
    """The aging basis: what counts as something happening to an item.

    `item_date` answers when an item began. `last_active` answers when anything
    last happened to it, and it is what the threshold is measured from -- the
    two are different questions, and `idle-planning` read the first one while
    saying the second. This class is the one definition both `scan` here and
    `sd-status`'s producer read, so it is where the difference is pinned.
    """

    ITEM = datetime.date(2026, 1, 1)

    def last(self, name: str = "2026-01-01-x", activity: str = "",
             marks: dict | None = None) -> datetime.date:
        return sd_sweep.last_active(self.ITEM, name, activity, marks)

    def test_an_item_with_no_evidence_ages_from_its_own_date(self) -> None:
        """The floor, and the whole of the old behaviour."""
        self.assertEqual(self.last(), self.ITEM)

    def test_a_commit_on_its_directory_is_activity(self) -> None:
        commit = datetime.date(2026, 9, 5)
        self.assertEqual(self.last(marks={"2026-01-01-x": commit}), commit)

    def test_a_database_stamp_is_activity(self) -> None:
        """A note carries a full timestamp; only its day is read."""
        self.assertEqual(
            self.last(activity="2026-09-06T09:14:00+00:00"),
            datetime.date(2026, 9, 6),
        )

    def test_the_latest_of_the_three_wins_rather_than_the_first_found(self) -> None:
        """A union, not a precedence chain: each source is blind where the
        others see, so the newest evidence is the answer whichever gave it."""
        marks = {"2026-01-01-x": datetime.date(2026, 8, 1)}
        self.assertEqual(
            self.last(activity="2026-09-06T09:14:00+00:00", marks=marks),
            datetime.date(2026, 9, 6),
        )
        self.assertEqual(
            self.last(activity="2026-07-01T09:14:00+00:00", marks=marks),
            datetime.date(2026, 8, 1),
        )

    def test_an_unparseable_stamp_lowers_nothing(self) -> None:
        """Absent evidence degrades to the floor, never below it."""
        self.assertEqual(self.last(activity="not a date"), self.ITEM)
        self.assertEqual(self.last(activity=""), self.ITEM)

    def test_a_commit_on_another_item_is_not_this_item_s_activity(self) -> None:
        self.assertEqual(
            self.last(marks={"2026-01-01-other": datetime.date(2026, 9, 5)}),
            self.ITEM,
        )


class ItemDirectory(unittest.TestCase):
    """Which item a tracked path belongs to, for `touched`'s one `git log`."""

    def resolve(self, path: str) -> str:
        return sd_sweep._item_directory(path, "docs/work")

    def test_a_file_in_an_item_names_that_item(self) -> None:
        self.assertEqual(self.resolve("docs/work/2026-01-01-x/prd.md"), "2026-01-01-x")

    def test_an_archived_item_is_named_through_its_month(self) -> None:
        self.assertEqual(
            self.resolve("docs/work/archive/2026-08/2026-01-01-x/prd.md"),
            "2026-01-01-x",
        )

    def test_a_file_directly_in_the_work_directory_names_no_item(self) -> None:
        """`.status-source` lives there and is not an item."""
        self.assertEqual(self.resolve("docs/work/.status-source"), "")

    def test_a_path_outside_the_work_directory_names_no_item(self) -> None:
        self.assertEqual(self.resolve("bin/sd-status"), "")


class Touched(unittest.TestCase):
    """One `git log` per root, and what it maps."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name) / "repo"
        (self.repo / "docs" / "work").mkdir(parents=True)
        self.at("init", "--quiet", "--initial-branch=main")
        self.at("config", "user.email", "t@example.com")
        self.at("config", "user.name", "t")
        self.at("config", "commit.gpgsign", "false")

    def at(self, *args: str, when: str | None = None) -> None:
        """One git call in the fixture repository.

        Not named `run`: that is `TestCase.run`, and overriding it stops the
        case from running at all -- which it did, loudly, on the first draft.
        """
        env = {**os.environ}
        if when:
            env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = when
        subprocess.run(["git", *args], cwd=self.repo, check=True,
                       capture_output=True, env=env)

    def commit(self, name: str, when: str, **fields: str) -> None:
        """One item, written as a real item and committed on a chosen day."""
        item = self.repo / "docs" / "work" / name
        if item.exists():
            (item / "touched").write_text(when, encoding="utf-8")
        else:
            make_item(self.repo, name, **fields)
        self.at("add", "-A")
        self.at("commit", "--quiet", "-m", f"touch {name}", when=when)

    def test_each_item_maps_to_the_day_it_was_last_committed_to(self) -> None:
        self.commit("2026-01-01-a", "2026-08-01T12:00:00 +0000")
        self.commit("2026-01-01-b", "2026-09-05T12:00:00 +0000")
        self.assertEqual(
            sd_sweep.touched(self.repo),
            {"2026-01-01-a": datetime.date(2026, 8, 1),
             "2026-01-01-b": datetime.date(2026, 9, 5)},
        )

    def test_the_latest_commit_wins_and_not_the_first_one(self) -> None:
        """`git log` is newest first, so the first sighting is the latest."""
        self.commit("2026-01-01-a", "2026-08-01T12:00:00 +0000")
        self.commit("2026-01-01-a", "2026-09-05T12:00:00 +0000")
        self.assertEqual(
            sd_sweep.touched(self.repo), {"2026-01-01-a": datetime.date(2026, 9, 5)}
        )

    def test_a_directory_that_is_not_a_checkout_is_empty_and_not_an_error(self) -> None:
        """Git refusing and git finding nothing leave the age on its other two
        sources, so there is no third state for a caller to handle."""
        loose = self.repo.parent / "not-a-checkout"
        loose.mkdir()
        self.assertEqual(sd_sweep.touched(loose), {})

    def test_the_sweep_does_not_call_a_recently_committed_item_due(self) -> None:
        """sd:455's sequencing note, checked rather than trusted.

        The sweep and `sd-status` read one aging basis. If only the report had
        moved, the sweep would go on counting from birth dates and would park
        exactly the items the report had just stopped calling idle.
        """
        self.commit("2026-01-01-a", "2026-08-30T12:00:00 +0000",
                    status="planning", created="2026-01-01")
        self.assertEqual(sd_sweep.scan(self.repo, TODAY, 45)["due"], [])

    def test_an_item_nothing_has_touched_is_still_due_and_says_from_when(
        self,
    ) -> None:
        """The other direction: the check still fires, on the later date.

        243 days since it was created, 92 since anything happened to it, and
        the row carries both -- `date` is the item's own, `active` is what the
        age was measured from.
        """
        self.commit("2026-01-01-a", "2026-06-01T12:00:00 +0000",
                    status="planning", created="2026-01-01")
        due = sd_sweep.scan(self.repo, TODAY, 45)["due"]
        self.assertEqual([(row["slug"], row["age"]) for row in due], [("a", 92)])
        self.assertEqual(due[0]["date"], "2026-01-01")
        self.assertEqual(due[0]["active"], "2026-06-01")


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



class FleetPins(unittest.TestCase):
    """What `sd sweep --fleet` says about the commits the fleet pins.

    A pack or system pin is a full SHA that no ecosystem watches: Dependabot is
    told to ignore it, and the `ref:`, `*_REVISION:` and tarball-manifest forms
    are invisible by construction. So the report rides the fleet walk that is
    already scheduled rather than a flag of its own, and the control below is
    the load-bearing case: a single-checkout sweep must *not* grow a `pins`
    key, because one checkout cannot answer what the rest of the fleet pins.

    The seeded tree is `$HOME/fleet` and not `$HOME/repos` on purpose. If the
    pin half ever stopped reading the checkouts the sweep enumerated and went
    back to walking the home tree itself, `search_root()` would land on a
    directory that does not exist, and every assertion below would read zero
    pins rather than quietly agreeing with a second walk.
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Resolved: on macOS the scratch directory is a symlink, and the pin
        # half compares a pin's target against the checkout it walked by path.
        self.home = pathlib.Path(tmp.name).resolve()
        self.root = self.home / "fleet"
        self.root.mkdir()
        self.environment = {**os.environ, "HOME": str(self.home),
                            "SD_REPO_ROOT": str(self.root)}
        self.upstream, first = self.checkout("system-probe", commits=3)
        self.consumer, _ = self.checkout("consumer-probe")
        flows = self.consumer / ".github" / "workflows"
        flows.mkdir(parents=True)
        (flows / "tests.yml").write_text(
            "jobs:\n  t:\n    steps:\n"
            f"      - uses: owner/system-probe@{first}\n", encoding="utf-8")

    def git(self, repo: pathlib.Path, *args: str) -> str:
        done = subprocess.run(["git", "-C", str(repo), *args], check=True,
                              capture_output=True, text=True)
        return done.stdout.strip()

    def checkout(self, name: str, commits: int = 1) -> tuple[pathlib.Path, str]:
        """One checkout under an org directory, with real commits behind it."""
        repo = self.root / "owner" / name
        (repo / "docs" / "work").mkdir(parents=True)
        self.git(repo, "init", "--quiet", "--initial-branch=main")
        self.git(repo, "config", "user.email", "t@example.com")
        self.git(repo, "config", "user.name", "t")
        self.git(repo, "config", "commit.gpgsign", "false")
        first = ""
        for number in range(commits):
            (repo / "f.txt").write_text(str(number), encoding="utf-8")
            self.git(repo, "add", "-A")
            self.git(repo, "commit", "--quiet", "-m", f"c{number}")
            first = first or self.git(repo, "rev-parse", "HEAD")
        return repo, first

    def sweep(self, *arguments: str, cwd: pathlib.Path | None = None):
        done = subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "sd"), "sweep", *arguments],
            cwd=str(cwd or self.root), env=self.environment,
            capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def test_the_fleet_sweep_names_the_pin_that_is_behind(self) -> None:
        report = json.loads(self.sweep("--fleet", "--json").stdout)
        self.assertEqual(
            [(row["repo"], row["target"], row["status"]) for row in report["pins"]],
            [("consumer-probe", "system-probe", "behind 2")])

    def test_a_single_checkout_sweep_reports_no_pins_at_all(self) -> None:
        """The control. Without it the case above passes on a key that is
        always there, which would be one checkout answering a fleet question."""
        report = json.loads(self.sweep("--json", cwd=self.consumer).stdout)
        self.assertNotIn("pins", report)

    def test_the_text_report_carries_the_pin_section_and_its_footer(self) -> None:
        printed = self.sweep("--fleet").stdout
        self.assertIn("behind 2", printed)
        self.assertIn("1 pin site(s) across 1 repo(s); 1 behind.", printed)
        self.assertIn("Report only", printed)

    def test_the_pin_site_is_named_by_file_and_line(self) -> None:
        report = json.loads(self.sweep("--fleet", "--json").stdout)
        self.assertEqual(report["pins"][0]["where"],
                         ".github/workflows/tests.yml:4")


if __name__ == "__main__":
    unittest.main()
