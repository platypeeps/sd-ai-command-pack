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

Both revisions are pinned by full SHA and both are asserted to be in this
checkout's history rather than assumed to be: the item these come from carries
a correction for citing a pre-squash hash that never landed, and a test
anchored to an object that is not on the branch fails everywhere except the
machine it was written on.

Reading history at all makes this file depend on a full clone. That is a real
dependency and it is the one CI already carries deliberately -- the unittest
job checks out at `fetch-depth: 0` because `tests/test_archive_untouched.py`
needs the same thing, and the reason is written in the workflow.

The rest of the file is the control. Anchors alone would pass against a tool
that had stopped discriminating between revisions -- a `size_at` that read one
tree and returned it forever would satisfy neither, but one that returned a
constant `Size` would satisfy either on its own -- so the fixtures exercise
each measurement against a case built to move it.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
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


class RecordedFigures(unittest.TestCase):
    """The anchors: the tool agrees with two independent hand measurements."""

    def test_both_anchor_revisions_are_on_the_branch(self) -> None:
        """The premise, asserted before the conclusions that rest on it.

        A revision that is not in this repository's history is not evidence
        about it, and measuring one would prove nothing about the figures the
        item recorded. This is the check the item's own correction was written
        after somebody skipped: it cited a pre-squash hash whose object exists
        and whose commit never landed, and every claim resting on it was
        unfalsifiable on any machine but the one that made it.

        Against `HEAD` rather than `origin/main`, and the difference is CI. No
        other test here depends on this checkout's own `refs/remotes/origin/*`
        -- the ones that mention `origin/main` create it inside a fixture
        repository -- and a test that needs a remote-tracking ref a checkout
        action may not have written is a test that fails for reasons unrelated
        to the code under test. `HEAD` always resolves, and on a pull request
        it is the merge with the default branch, so an anchor that is not
        under it is not on the mainline either.
        """

        for anchor in (FIRST_RELEASE, CAP_RETIRED):
            with self.subTest(anchor=anchor):
                self.assertEqual(
                    subprocess.run(
                        ["git", "merge-base", "--is-ancestor", anchor, "HEAD"],
                        cwd=REPO_ROOT, capture_output=True, check=False).returncode,
                    0, f"{anchor} is not an ancestor of HEAD")

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

        samples = report.trend_revisions(REPO_ROOT)
        newest = samples[-1][0]
        self.assertEqual(
            newest,
            report.dt.datetime.now(report.dt.timezone.utc).date().isoformat())

    def test_the_trend_names_each_commit_once(self) -> None:
        """A quiet fortnight otherwise prints one commit three times, which
        reads as three weeks of flat growth rather than as no new data."""

        commits = [commit for _when, commit in report.trend_revisions(REPO_ROOT)]
        self.assertEqual(sorted(commits), sorted(set(commits)))

    def test_the_trend_is_ordered_oldest_first(self) -> None:
        dates = [when for when, _commit in report.trend_revisions(REPO_ROOT)]
        self.assertEqual(dates, sorted(dates))

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

    def test_the_report_names_every_measure_and_the_change(self) -> None:
        rendered = "\n".join(report.render_report(REPO_ROOT))
        for expected in ("lines", "definitions", "commands", "lines/definition",
                         "this change", "The last 30 days"):
            self.assertIn(expected, rendered, expected)

    def test_the_report_says_it_is_not_a_gate(self) -> None:
        """The one line that has to survive every edit to this tool. A report
        that reads as a threshold acquires the ratchet the cap had, which is
        the whole reason the item asked for a report instead of a cap."""

        self.assertIn("never a gate", "\n".join(report.render_report(REPO_ROOT)))

    def test_running_it_prints_the_report_and_exits_zero(self) -> None:
        done = subprocess.run([str(REPORT_PATH)], cwd=REPO_ROOT,
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("lines/definition", done.stdout)

    def test_it_refuses_outside_a_repository_instead_of_measuring_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            done = subprocess.run([str(REPORT_PATH)], cwd=home,
                                  capture_output=True, text=True, check=False)
            self.assertEqual(done.returncode, 1)
            self.assertIn("not inside a repository", done.stderr)


if __name__ == "__main__":
    unittest.main()
