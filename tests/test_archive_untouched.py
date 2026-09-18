"""Criterion 21 history, the archive boundary, and pack deletion paths.

Two halves. The archive half: the retire changed nothing under `archive/`. The
code-path half, `NoDeletionPath` at the end: no sweep or park code path
remains, and the deletion verbs the tree does carry are a frozen set that
this file enumerates.

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

The 2026-09-17 removal changed only its reviewed first batch.
Git history preserves the removed records.
New archived `prd.md` files must still carry their historical `status:` line.
Active items must not carry one.
"""

from __future__ import annotations

import pathlib
import subprocess
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MARKER = "docs/work/.status-source"
ARCHIVE = "docs/work/archive/"
REMOVED_SNAPSHOT = "8ba8fa7a15fcd4783b42cbe580a04e89149be08d"


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
    """The tracked paths matching `pattern`, each named once.

    `--deduplicate` because the index holds an unmerged path once per merge
    stage, and plain `ls-files` prints it once per stage. Inert here -- the
    one caller that reads the rows feeds them to `set()`, and the other only
    asks whether the list is non-empty -- so this is the form, not a fix for a
    failure. It is written this way because the right form was already the
    rule everywhere the rows are read as a list -- `.github/scripts/`, the
    `Makefile`, `bin/` and the test modules -- and the two calls that did not
    carry it are how the wrong form survived (sd:823). No count is given here
    on purpose: a number in a comment is the thing that drifts. To read the
    inventory, enumerate it -- `git grep -nI -- ls-files -- tests bin scripts
    .github Makefile .githooks`.
    """
    return lines(git("ls-files", "--deduplicate", "--", f":(glob){pattern}"))


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


class TheArchiveBoundary(unittest.TestCase):
    """Current archived items remain records; active items use database status."""

    def test_every_archived_item_keeps_its_status_line(self) -> None:
        archived = tracked("docs/work/archive/*/*/prd.md") or self.fail("the archive enumeration matched nothing")
        missing = sorted(set(archived) - set(carrying_status(
            "docs/work/archive/*/*/prd.md")))
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} archived item(s) lost the line that records what "
            f"they were: " + ", ".join(missing[:5]),
        )

    def test_the_archive_index_names_the_removed_snapshot(self) -> None:
        index = REPO_ROOT / "docs/work/archive/README.md"
        self.assertTrue(index.is_file(), "the archive index is missing")
        self.assertIn(
            REMOVED_SNAPSHOT,
            index.read_text(encoding="utf-8"),
        )
        commit = subprocess.run(
            ["git", "cat-file", "-e", f"{REMOVED_SNAPSHOT}^{{commit}}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            commit.returncode,
            0,
            f"removed archive snapshot is unreachable: {commit.stderr.strip()}",
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


#: Every `git rm`, `rmtree` and `rmdir` under `bin/` and `skills/`, keyed by
#: file and by the text that carries it -- not by line number, which moves
#: under every unrelated edit. Eight sites when this was frozen on
#: 2026-09-16, and the criterion's own words explain why the set is not
#: empty and cannot be: five are the exact-removal *strings* in `sd-status`'s
#: `RESIDUE` tuple, telling an operator how to uninstall a Trellis or legacy
#: footprint; two are `sd_install.py` pruning its own empty parents, once in
#: the docstring and once in the call, which the criterion allows by name;
#: one is an error message reading "Untrack it (git rm --cached) and re-run".
#: None of the eight is a sweep or park code path, and the sweep module the
#: cut removed was never among them. Requirement 13 cuts the
#: `RESIDUE` tuple after one clean fleet run, which takes five: the assertion
#: is a subset, so that cut lowers the count without touching this file, and
#: a ninth site fails it.
FROZEN_DELETION_SITES = frozenset({
    ("bin/sd-status", "git rm -r --cached --ignore-unmatch .trellis && rm -rf .trellis"),
    ("bin/sd-status", "git config --unset core.hooksPath; git rm -r --ignore-unmatch .githooks"),
    ("bin/sd-status", "git rm -r --ignore-unmatch 'scripts/sd-ai-command-pack-*'"),
    ("bin/sd-status", "git rm --ignore-unmatch '.github/workflows/sd-ai-command-pack-*.y*ml'"),
    ("bin/sd-status", "git rm -r --ignore-unmatch '.github/candidate-validation*'"),
    ("bin/sd_install.py", "Bounded by `rmdir` refusing a non-empty directory: the loop cannot escape"),
    ("bin/sd_install.py", "current.rmdir()"),
    ("bin/sd_install.py", "tracked file. Untrack it (git rm --cached) and re-run."),
})

DELETION_VERBS = r"git rm|rmtree|rmdir"


def deletion_sites() -> set[tuple[str, str]]:
    """Every line under `bin/` and `skills/` carrying a deletion verb.

    `git grep` exits 1 on no match, which is the answer this criterion would
    most like to hear and not a failure, so it is spelled out. The text is
    stripped of its indentation and its trailing quote-and-comma, so that the
    frozen set above reads as the sentence a person sees and not as a line of
    Python punctuation.
    """
    done = subprocess.run(  # nosec B603 - fixed argv, no shell
        ["git", "-C", str(REPO_ROOT), "grep", "-nIE", DELETION_VERBS, "--",
         "bin", "skills"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode == 1:
        return set()
    if done.returncode != 0:
        raise AssertionError(f"git grep failed: {done.stderr.strip()}")
    found = set()
    for row in lines(done.stdout):
        path, _, text = row.split(":", 2)
        found.add((path, text.strip().strip('",')))
    return found


class NoDeletionPath(unittest.TestCase):
    """The code-path half: what deletes, enumerated, and no sweep among it."""

    def test_the_deletion_verbs_are_the_frozen_set_and_no_more(self) -> None:
        found = deletion_sites()
        grown = sorted(found - FROZEN_DELETION_SITES)
        self.assertEqual(
            grown,
            [],
            "a deletion verb appeared outside the frozen set; a new sweep or "
            "park code path is the thing this criterion forbids: "
            + "; ".join(f"{path}: {text}" for path, text in grown),
        )

    def test_the_grep_reaches_the_sites_it_freezes(self) -> None:
        """The control: an empty enumeration would pass the subset above
        while measuring nothing. The residue cut may lower this to three, and
        three is still not zero; zero means the grep did not run."""
        found = deletion_sites()
        self.assertTrue(found, "the deletion-verb grep matched nothing")
        self.assertTrue(
            found & FROZEN_DELETION_SITES,
            "the grep found sites but none of the frozen ones, so the frozen "
            "text has drifted from the tree and the set is not measuring it",
        )

    def test_no_frozen_site_is_a_sweep_or_park_code_path(self) -> None:
        """Every site is a string an operator reads, or the installer pruning
        its own empty parents. Not one is in a file that sweeps or parks a
        work item, and `tests/test_cut_symbols.py` asserts there is no such
        file to be in."""
        for path, _ in FROZEN_DELETION_SITES:
            self.assertNotIn("sweep", path)
            self.assertNotIn("park", path)


if __name__ == "__main__":
    unittest.main()
