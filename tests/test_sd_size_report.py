"""`bin/sd-size-report` measures what the item it came from measured.

A report nobody can check is a report nobody has to believe, and this one is
arguing a case -- that `bin/` has grown by gaining functions rather than by
fattening them -- off four numbers. So the anchor cases below re-derive those
numbers from the repository's own history and compare them to the figures
recorded by hand on the item, at two revisions taken ten days apart:

    v1.0.0      2026-09-01   7,947 lines   273 definitions   11 commands  29.1
    53c31600    2026-09-11  20,803 lines   618 definitions   15 commands  33.6

Four values agreeing at once is what makes them evidence rather than a
coincidence. Had the tool counted methods as well as top-level definitions, or
taken the executable bit for a command, or counted lines with `read().count`,
each of those would land near enough to look right and none of them would hit
all four.

Both revisions are pinned by full SHA and read as objects, never found by
walking this checkout's history (sd:2593). A squash, a rebase or an orphan
branch with the same tree measures the same, which is what lets the check
declare tree-keyed gate reuse. The item these come from carries a correction
for citing a pre-squash hash that never landed; the guard against that is that
each pin must be a commit object present here, and that its measurement
matches four recorded figures at once, which no wrong commit does by chance.

Reading those objects makes this file depend on a full clone, as
`tests/test_archive_untouched.py` does for its own pinned commit. Every other
test here, the trend and the report included, reads a fixture repository with
synthetic, dated commits.

The rest of the file is the control. Anchors alone would pass against a tool
that had stopped discriminating between revisions -- a `size_at` that read one
tree and returned it forever would satisfy neither, but one that returned a
constant `Size` would satisfy either on its own -- so the fixtures exercise
each measurement against a case built to move it.
"""

from __future__ import annotations

import datetime as dt
import importlib.machinery
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from types import ModuleType

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "bin" / "sd-size-report"

#: v1.0.0, and the commit `bin/`'s line cap was retired at. Full SHAs: an
#: abbreviation is not a name, and the history these read is long enough now
#: that eight characters is a bet rather than an identifier.
FIRST_RELEASE = "daebee6c6cd456a81cbbbba91de6196c8b8b7de0"
CAP_RETIRED = "53c3160058110b1360b84bff584fd0a743e986db"


def load_report() -> ModuleType:
    """Import the executable, which has no .py suffix to import by name.

    Registered in `sys.modules` before it is executed, not after. A frozen
    dataclass resolves its own `__module__` out of `sys.modules` while the
    decorator runs, so a module still absent from there fails on the class
    body with an `AttributeError` about `NoneType` that says nothing about
    what is actually wrong.
    """

    spec = importlib.util.spec_from_loader(
        "sd_size_report",
        importlib.machinery.SourceFileLoader("sd_size_report", str(REPORT_PATH)),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


report = load_report()


def git(root: pathlib.Path, *argv: str) -> str:
    """A git runner bound to `root`, with identity and signing passed in.

    Per invocation rather than read from the machine, so the fixtures below
    neither fail on a host with no `user.email` nor block on one that signs
    every commit.
    """

    done = subprocess.run(
        ["git", "-c", "user.email=size@example.invalid", "-c", "user.name=size",
         "-c", "commit.gpgsign=false", *argv],
        cwd=root, capture_output=True, text=True, check=True)
    return done.stdout


def a_repository_with_two_commits(root: pathlib.Path) -> None:
    """A throwaway repository whose `bin/` grows between its two commits."""

    git(root, "init", "-q", "-b", "main", ".")
    (root / "bin").mkdir()
    (root / "bin" / "tool").write_text("def one():\n    return 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "first")
    (root / "bin" / "lib.py").write_text("def two():\n    return 2\n\n\ndef three():\n    pass\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "second")


def a_repository_with_dated_commits(root: pathlib.Path) -> list[str]:
    """A throwaway repository with commits 29, 15 and 0 days back, oldest first.

    The trend and the report read this, not this checkout's history (sd:2593).
    `rev-list --before` reads the committer date, so both dates are set. Noon
    for the older two, and today's midnight for the last, which no clock that
    runs the test is before.
    """

    git(root, "init", "-q", "-b", "main", ".")
    (root / "bin").mkdir()
    today = dt.datetime.now(dt.timezone.utc).date()
    commits = []
    for index, back in enumerate((29, 15, 0)):
        day = today - dt.timedelta(days=back)
        stamp = f"{day.isoformat()}T{'00:00:00' if back == 0 else '12:00:00'}Z"
        (root / "bin" / f"part{index}.py").write_text(f"def part{index}():\n    return {index}\n")
        git(root, "add", "-A")
        subprocess.run(
            ["git", "-c", "user.email=size@example.invalid", "-c", "user.name=size",
             "-c", "commit.gpgsign=false", "commit", "-qm", f"part {index}"],
            cwd=root, capture_output=True, text=True, check=True,
            env={**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
        commits.append(git(root, "rev-parse", "HEAD").strip())
    return commits


class RecordedFigures(unittest.TestCase):
    """The anchors: the tool agrees with two independent hand measurements."""

    def test_both_anchor_revisions_are_commits_here(self) -> None:
        """The premise, asserted before the conclusions that rest on it.

        A revision that is not a commit object here is not evidence about
        this repository, and `size_at` would answer `None` for it with no
        reason. Presence, not ancestry: `merge-base --is-ancestor <pin> HEAD`
        read this checkout's history, so an orphan commit carrying the same
        tree failed it while every figure below still held (sd:2593). The
        pre-squash hash the item corrected is caught by the figures: a
        commit that never landed does not measure four recorded values.
        """

        for anchor in (FIRST_RELEASE, CAP_RETIRED):
            with self.subTest(anchor=anchor):
                self.assertEqual(
                    subprocess.run(
                        ["git", "cat-file", "-e", f"{anchor}^{{commit}}"],
                        cwd=REPO_ROOT, capture_output=True, check=False).returncode,
                    0, f"{anchor} is not a commit in this repository")

    def test_the_first_release_measures_what_was_recorded(self) -> None:
        measured = report.size_at(REPO_ROOT, FIRST_RELEASE)
        self.assertIsNotNone(measured)
        self.assertEqual(
            (measured.lines, measured.definitions, measured.commands),
            (7947, 273, 11))
        self.assertEqual(round(measured.ratio, 1), 29.1)

    def test_the_cap_retirement_measures_what_was_recorded(self) -> None:
        """Three figures match exactly; the fourth is recorded truncated.

        20,803 over 618 is 33.6618, which this tool prints as 33.7 and the
        item records as 33.6. The item truncated where the tool rounds, and
        the difference showed up here rather than in a reader's head, which is
        what an anchor is for. Asserted to two places so the quotient is
        pinned without either convention being written into the test.
        """

        measured = report.size_at(REPO_ROOT, CAP_RETIRED)
        self.assertIsNotNone(measured)
        self.assertEqual(
            (measured.lines, measured.definitions, measured.commands),
            (20803, 618, 15))
        self.assertEqual(round(measured.ratio, 2), 33.66)

    def test_the_two_anchors_do_not_measure_the_same_thing(self) -> None:
        """The control for the pair above, and the one they cannot be.

        A `size_at` that ignored its revision would still have to produce two
        different answers to pass both, so this is belt and braces -- but a
        cached first answer returned forever is exactly the shape that would,
        and it is the shape this file's neighbouring item is about.
        """

        self.assertNotEqual(report.size_at(REPO_ROOT, FIRST_RELEASE),
                            report.size_at(REPO_ROOT, CAP_RETIRED))


class Measurement(unittest.TestCase):
    """What each measurement counts, against cases built to move it."""

    def test_definitions_are_top_level_and_include_async(self) -> None:
        self.assertEqual(report.definitions_in(
            "def one():\n    pass\n\n\nasync def two():\n    pass\n"), 2)

    def test_a_method_is_not_a_top_level_definition(self) -> None:
        self.assertEqual(report.definitions_in(
            "class C:\n    def method(self):\n        def inner():\n            pass\n"), 0)

    def test_source_that_will_not_parse_counts_no_definitions(self) -> None:
        self.assertEqual(report.definitions_in("def ("), 0)

    def test_a_command_is_a_file_with_no_py_suffix(self) -> None:
        measured = report.size_of({"bin/sd-thing": "def a():\n    pass\n",
                                   "bin/sd_thing.py": "def b():\n    pass\n"})
        self.assertEqual((measured.lines, measured.definitions, measured.commands),
                         (4, 2, 1))

    def test_the_ratio_is_lines_over_definitions(self) -> None:
        self.assertEqual(report.Size(lines=90, definitions=3, commands=1).ratio, 30.0)

    def test_a_tree_with_no_definitions_has_no_ratio_rather_than_an_error(self) -> None:
        """Division, not a crash. `bin/` will never be empty; a sampled
        revision from before it existed is another matter, and the trend walks
        thirty days back without asking what it will find there."""

        self.assertEqual(report.Size(lines=10, definitions=0, commands=0).ratio, 0.0)


class History(unittest.TestCase):
    """Reading past revisions, and choosing which ones to read."""

    def test_a_revision_with_no_bin_directory_measures_as_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            git(root, "init", "-q", "-b", "main", ".")
            (root / "README.md").write_text("no bin here\n")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "only a readme")
            self.assertIsNone(report.size_at(root, "HEAD"))

    def test_each_revision_is_measured_as_it_stood(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            a_repository_with_two_commits(root)
            first = report.size_at(root, "HEAD~1")
            second = report.size_at(root, "HEAD")
            self.assertEqual((first.lines, first.definitions, first.commands), (2, 1, 1))
            self.assertEqual((second.lines, second.definitions, second.commands), (8, 3, 1))

    def test_the_trend_reaches_todays_revision(self) -> None:
        """The newest sample is the change in hand, not a week-old commit.

        Stepping a 30-day window by 7 lands on 30, 23, 16, 9 and 2 days back
        and never on 0, so the newest row the first draft printed was dated
        two days before the run and the movement the report exists to show was
        the one movement missing from it.
        """

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            a_repository_with_dated_commits(root)
            samples = report.trend_revisions(root)
        newest = samples[-1][0]
        self.assertEqual(
            newest,
            report.dt.datetime.now(report.dt.timezone.utc).date().isoformat())

    def test_the_trend_names_each_commit_once(self) -> None:
        """A quiet fortnight otherwise prints one commit three times, which
        reads as three weeks of flat growth rather than as no new data."""

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            a_repository_with_dated_commits(root)
            commits = [commit for _when, commit in report.trend_revisions(root)]
        self.assertEqual(sorted(commits), sorted(set(commits)))

    def test_the_trend_is_ordered_oldest_first(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            a_repository_with_dated_commits(root)
            dates = [when for when, _commit in report.trend_revisions(root)]
        self.assertEqual(dates, sorted(dates))

    def test_each_sample_is_the_newest_commit_at_or_before_its_date(self) -> None:
        """The samples, named. The three tests above hold on any history.

        Commits 29, 15 and 0 days back, sampled at 30, 23, 16, 9, 2 and 0:
        30 is before the first commit and gives nothing, 23 and 16 give the
        first, 9 and 2 the second, and 0 the third. Each commit once, at its
        oldest sample point.
        """

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            commits = a_repository_with_dated_commits(root)
            samples = report.trend_revisions(root)
        today = report.dt.datetime.now(report.dt.timezone.utc).date()
        expected = [((today - report.dt.timedelta(days=back)).isoformat(), commit)
                    for back, commit in zip((23, 9, 0), commits, strict=True)]
        self.assertEqual(samples, expected)

    def test_a_repository_without_a_remote_falls_back_to_the_previous_commit(self) -> None:
        """No `origin/main` is the ordinary state of a fresh or shallow clone,
        and a report that refuses to run there is a report that stops running
        in CI on the day somebody changes the checkout depth."""

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            a_repository_with_two_commits(root)
            self.assertEqual(report.baseline_revision(root),
                             git(root, "rev-parse", "HEAD~1").strip())

    def test_a_repository_with_one_commit_has_no_base_rather_than_a_wrong_one(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            git(root, "init", "-q", "-b", "main", ".")
            (root / "f.py").write_text("VALUE = 1\n")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "only")
            self.assertIsNone(report.baseline_revision(root))


class TheReport(unittest.TestCase):
    """What the pull request actually sees."""

    def setUp(self) -> None:
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.root = pathlib.Path(home.name)
        a_repository_with_dated_commits(self.root)

    def test_the_report_names_every_measure_and_the_change(self) -> None:
        rendered = "\n".join(report.render_report(self.root))
        for expected in ("lines", "definitions", "commands", "lines/definition",
                         "this change", "The last 30 days"):
            self.assertIn(expected, rendered, expected)

    def test_the_report_says_it_is_not_a_gate(self) -> None:
        """The one line that has to survive every edit to this tool. A report
        that reads as a threshold acquires the ratchet the cap had, which is
        the whole reason the item asked for a report instead of a cap."""

        self.assertIn("never a gate", "\n".join(report.render_report(self.root)))

    def test_running_it_prints_the_report_and_exits_zero(self) -> None:
        done = subprocess.run([str(REPORT_PATH)], cwd=self.root,
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("lines/definition", done.stdout)
        # Every dated commit sampled, so the trend rows came from the fixture.
        self.assertEqual(done.stdout.count("\n| 20"), 3, done.stdout)

    def test_it_refuses_outside_a_repository_instead_of_measuring_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            done = subprocess.run([str(REPORT_PATH)], cwd=home,
                                  capture_output=True, text=True, check=False)
            self.assertEqual(done.returncode, 1)
            self.assertIn("not inside a repository", done.stderr)


if __name__ == "__main__":
    unittest.main()
