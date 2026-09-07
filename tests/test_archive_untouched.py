"""Criterion 21's archive half: the retire changed nothing under `archive/`.

The `docs/work` retire removed every active item's `status:` line and wrote
`docs/work/.status-source`. Archived items keep their line, because they are
records of what was, and a migration that rewrote a record after the fact
would be the one failure this criterion exists to catch.

Two readings of "untouched", both here, because either alone fails open.

The *diff* reading is the criterion's own words: the commit that landed the
retire names no path under `docs/work/archive/`. It is the strongest form and
it needs the history to be present, so it fails rather than skips when the
commit is not reachable -- `.github/workflows/tests.yml` fetches the whole
history for that reason.

The *tree* reading is what survives a rewrite of that history: every archived
`prd.md` still carries its `status:` line, and no active one does. A future
change that quietly stripped the archive would leave the retire commit exactly
as it is, and the diff reading would go on passing over it.
"""

from __future__ import annotations

import pathlib
import subprocess
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MARKER = "docs/work/.status-source"
ARCHIVE = "docs/work/archive/"


def git(*args: str) -> str:
    """`git` in this checkout, its stdout, and a failure that is not a skip.

    A test that cannot ask git is a test that has not run. Reporting that as
    a pass -- which is what returning `""` here would do to every assertion
    below -- is the shape this whole work item keeps finding, so the failure
    is loud and names what git said.
    """

    done = subprocess.run(  # nosec B603 - fixed argv, no shell
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise AssertionError(
            f"`git {' '.join(args)}` failed with {done.returncode}: "
            f"{done.stderr.strip()}"
        )
    return done.stdout


def lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line]


def tracked(pattern: str) -> list[str]:
    return lines(git("ls-files", "--", f":(glob){pattern}"))


def carrying_status(pattern: str) -> list[str]:
    """The tracked files matching `pattern` that hold a top-level `status:`.

    `git grep -l` exits 1 when it matches nothing, which is an answer and not
    a failure, so the empty case is spelled out rather than raised.
    """

    done = subprocess.run(  # nosec B603 - fixed argv, no shell
        ["git", "-C", str(REPO_ROOT), "grep", "-l", "^status:", "--",
         f":(glob){pattern}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode == 1:
        return []
    if done.returncode != 0:
        raise AssertionError(f"git grep failed: {done.stderr.strip()}")
    return lines(done.stdout)


class TheRetireCommit(unittest.TestCase):
    """The diff reading. What the commit that landed the retire names."""

    def setUp(self) -> None:
        self.adds = lines(
            git("log", "--diff-filter=A", "--format=%H", "--", MARKER)
        )

    def test_the_history_holds_the_commit_that_added_the_marker(self) -> None:
        """The control, and the reason this is not a skip.

        A shallow clone is the case to name first. It does not reach the
        retire commit, and it does not answer "no commit added the marker"
        either -- its grafted root adds every tracked file, so the query
        below returns HEAD and the archive check downstream fails with a
        message about a rewritten record that never happened. Ask git
        directly, and say what is actually wrong. If this fails in CI, the
        checkout needs `fetch-depth: 0`, not a weaker test.
        """

        self.assertEqual(
            git("rev-parse", "--is-shallow-repository").strip(),
            "false",
            "this clone is shallow, so the retire commit is unreachable and "
            "nothing below is being asserted about it",
        )
        self.assertEqual(
            len(self.adds),
            1,
            f"{MARKER} was added by {len(self.adds)} reachable commit(s); "
            f"exactly one is expected, and none means the history is shallow",
        )

    def test_the_commit_touches_work_items_outside_the_archive(self) -> None:
        """The second control: the absence below is worth nothing if the
        commit names no work item at all."""

        touched = lines(git("show", "--format=", "--name-only", self.adds[0]))
        outside = [
            path
            for path in touched
            if path.startswith("docs/work/") and not path.startswith(ARCHIVE)
        ]
        self.assertTrue(
            outside,
            "the retire commit names no work item outside the archive, so "
            "the archive check below would pass over any commit at all",
        )

    def test_it_names_nothing_under_the_archive(self) -> None:
        touched = lines(git("show", "--format=", "--name-only", self.adds[0]))
        inside = [path for path in touched if path.startswith(ARCHIVE)]
        self.assertEqual(
            inside,
            [],
            "the retire rewrote records of work that was already done: "
            + ", ".join(inside),
        )


class TheArchiveStillSaysWhatItSaid(unittest.TestCase):
    """The tree reading. What the two sides of the boundary hold today."""

    def test_every_archived_item_keeps_its_status_line(self) -> None:
        archived = tracked("docs/work/archive/*/*/prd.md")
        self.assertTrue(archived, "the archive enumeration matched nothing")
        missing = sorted(set(archived) - set(carrying_status(
            "docs/work/archive/*/*/prd.md")))
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} archived item(s) lost the line that records what "
            f"they were: " + ", ".join(missing[:5]),
        )

    def test_no_active_item_carries_one(self) -> None:
        """The other sign, which is what makes the check above discriminate.

        Both must hold at once. A tree where every `prd.md` carried a
        `status:` line would pass the archive half and mean the retire never
        happened; `bin/sd-docs-lint` rule 1 enforces this side per item, and
        it is asserted here as a count so the two readings sit together.
        """

        active = tracked("docs/work/*/prd.md")
        self.assertTrue(active, "the active enumeration matched nothing")
        self.assertEqual(
            carrying_status("docs/work/*/prd.md"),
            [],
            "an active item still answers from its file",
        )


if __name__ == "__main__":
    unittest.main()
