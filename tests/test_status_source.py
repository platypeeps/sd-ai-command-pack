"""Criterion 13's readers: the marker, the row, and the two words for the tree.

Three questions, and the suite is organised by them.

**Which question does this checkout ask?** `docs/work/.status-source` is one
tracked word. No marker is `file`, and `file` has to be the path readers took
before rows existed rather than a new path that agrees with it -- so the
absent-marker cases assert that `sd_lib.delivered` is not called at all and
that a `status:` line still decides.

**What does a row that cannot be read mean?** Five defects on this item shared
one shape: a guard that answered a question about form where the question was
about substance. Here the shape is a missing database, an unreadable marker or
a missing row read as "no row, so the item is open", which hands delivered
work back to `sd-review --scope planning` and `sd-plan` to be done again. The
three are given three different meanings on purpose, and each one is asserted:

    no database at all      the designed database-free case -- ask git alone
    a database with no row   the item is lost; `unknown`, and named
    a marker nothing reads   `unknown` for every item, and the marker named

**What does the tree still say?** A `status:` line that survived on a retained
worktree is *stale* when it disagrees with the row, and a row that says `done`
while no commit carries a closing trailer is *unmarked*. Both words are the
criterion's and both come out of `sd-status`.

Nothing here mocks git or sqlite: the repositories are real, and the rows are
written through `sd_db` with the same calls the migration uses.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_db  # noqa: E402 - installed into this virtualenv by `make setup`
import sd_lib  # noqa: E402


def _load(name: str, module_name: str) -> Any:
    """Import a `bin/` executable, which has no `.py` suffix to import by name."""
    path = REPO_ROOT / "bin" / name
    loader = importlib.machinery.SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_file_location(module_name, str(path), loader=loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


status_tool = _load("sd-status", "sd_status_for_status_source")
lint = _load("sd-docs-lint", "sd_docs_lint_for_status_source")

ITEM = "2026-09-05-a-thing"
OTHER = "2026-09-04-another-thing"


def prd(status: str | None, *, branch: str = "", criteria: bool = True) -> str:
    """An item's `prd.md`. `status=None` is the file the retire step leaves."""
    lines = ["---", "title: A thing"]
    if status is not None:
        lines.append(f"status: {status}")
    lines.append("created: 2026-09-05")
    if branch:
        lines.append(f"branch: {branch}")
    lines += ["---", "", "# PRD", ""]
    if criteria:
        lines += ["## Acceptance criteria", "", "- [x] it works", ""]
    return "\n".join(lines)


def merge_message(*trailers: str) -> str:
    """A merge message shaped as `sd-ship` writes one: subject, body, trailers."""
    return "feat: the slice (#1)\n\nWhat this merge settles.\n\n" + "\n".join(trailers)


class Fixture(unittest.TestCase):
    """One real repository, one real item, and a `HOME` nothing else shares."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        # The database is found through `$HOME`, read at call time. Without
        # this the suite would read the operator's own rows.
        patched = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patched.start()
        self.addCleanup(patched.stop)

        self.root = self.tmp / "repo"
        self.work = self.root / "docs" / "work"
        self.work.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")
        self.git("config", "commit.gpgsign", "false")
        self.item = self.work / ITEM
        self.item.mkdir()
        self.write(prd("planning"))
        self.commit("chore: the item")

    # ---------------------------------------------------------------- helpers

    def git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=str(self.root), check=True, capture_output=True, text=True
        )
        return done.stdout.strip()

    def write(self, text: str) -> None:
        (self.item / "prd.md").write_text(text, encoding="utf-8")

    def commit(self, subject: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", subject)

    def marker(self, word: str) -> None:
        (self.work / sd_lib.STATUS_MARKER).write_text(word + "\n", encoding="utf-8")

    def identity(self, name: str = ITEM) -> str:
        """The row key, spelled out here rather than asked of the code."""
        return f"{self.root}::docs/work/{name}/prd.md"

    def database(self) -> Any:
        sd_db.initialise(home=self.home)
        connection = sd_db.connect(home=self.home)
        self.addCleanup(connection.close)
        sd_db.upsert_repo(connection, str(self.root))
        return connection

    def seed(self, status: str, name: str = ITEM) -> Any:
        connection = getattr(self, "_connection", None) or self.database()
        self._connection = connection
        sd_db.upsert_item(
            connection,
            source=sd_lib.ITEM_ROW_SOURCE,
            external_id=self.identity(name),
            kind="work",
            title="A thing",
            status=status,
            who="the test",
            created_at="2026-09-05T00:00:00+00:00",
            repo=str(self.root),
            path=f"docs/work/{name}/prd.md",
            branch="main",
        )
        return connection

    def only(self) -> sd_lib.WorkItem:
        found = [i for i in sd_lib.work_items(self.root) if i.slug == "a-thing"]
        self.assertEqual(len(found), 1, "the fixture holds exactly one item")
        return found[0]

    def picked(self) -> list[str]:
        """What `bin/sd-review:417` picks, spelled the way that line spells it."""
        return [
            i.path.name
            for i in sd_lib.work_items(self.root)
            if i.status in ("planning", "in_progress")
        ]

    def rendered(self) -> str:
        stream = io.StringIO()
        status_tool._render_work(status_tool.work_section(self.root), stream.write)
        return stream.getvalue()


class NoMarkerIsTheOldPathExactly(Fixture):
    """Requirement 1. Absent means `file`, and `file` means what it meant."""

    def test_no_marker_reads_file(self) -> None:
        self.assertEqual(sd_lib.status_marker(self.root), (sd_lib.FROM_FILE, ""))

    def test_no_marker_still_reads_the_line(self) -> None:
        for word in ("planning", "ready", "done"):
            with self.subTest(word=word):
                self.write(prd(word, branch="wip" if word == "ready" else ""))
                self.assertEqual(self.only().status, word)

    def test_no_marker_asks_git_nothing(self) -> None:
        """The whole of "bit-for-bit identical": no new question is put.

        A reader that answered the same word after asking `delivered` would
        pass every assertion above and still fetch from a remote on every
        `sd-status` in every repository that has not migrated.
        """
        with mock.patch.object(
            sd_lib, "delivered", side_effect=AssertionError("delivered was asked")
        ):
            self.assertEqual(self.only().status, "planning")

    def test_no_marker_opens_no_database(self) -> None:
        self.database()
        self.seed("done")
        with mock.patch.object(
            sd_lib, "Rows", side_effect=AssertionError("the database was opened")
        ):
            self.assertEqual(self.only().status, "planning")

    def test_an_unreadable_status_line_is_still_unknown(self) -> None:
        self.write(prd("halfway"))
        item = self.only()
        self.assertEqual(item.status, "unknown")
        self.assertTrue(any("halfway" in problem for problem in item.inconsistencies))


class AMarkerNothingReads(Fixture):
    """A marker that exists and says nothing readable is not read as `file`."""

    def test_a_word_that_is_neither_is_no_word_at_all(self) -> None:
        self.marker("rows")
        word, problem = sd_lib.status_marker(self.root)
        self.assertEqual(word, "")
        self.assertIn("'rows'", problem)
        self.assertIn(sd_lib.STATUS_MARKER, problem)

    def test_a_marker_that_cannot_be_read_is_no_word_at_all(self) -> None:
        (self.work / sd_lib.STATUS_MARKER).mkdir()
        word, problem = sd_lib.status_marker(self.root)
        self.assertEqual(word, "")
        self.assertIn(sd_lib.STATUS_MARKER, problem)

    def test_every_item_is_unknown_and_the_marker_is_named(self) -> None:
        """Not `file`, which after the retire reads a line that is not there,
        and not the row either, since nothing said to read one."""
        self.marker("row ")  # a trailing space is stripped; this one is `row`
        self.assertEqual(sd_lib.status_marker(self.root)[0], sd_lib.FROM_ROW)
        self.marker("ROW")
        item = self.only()
        self.assertEqual(item.status, "unknown")
        self.assertTrue(any("'ROW'" in problem for problem in item.inconsistencies))
        self.assertEqual(self.picked(), [])

    def test_a_written_file_keeps_reading_the_line(self) -> None:
        self.marker("file")
        self.write(prd("in_progress", branch="wip/a-thing"))
        self.assertEqual(self.only().status, "in_progress")


class TheRowDecides(Fixture):
    """Requirement 2, on a machine that has the database."""

    def test_the_row_answers_and_the_line_does_not(self) -> None:
        self.marker("row")
        self.seed("ready")
        self.write(prd("planning"))
        self.assertEqual(self.only().status, "ready")

    def test_a_word_the_file_vocabulary_never_had_passes_through(self) -> None:
        """`ready_to_send` and `blocked` are rows, not lines. Folding either
        into one of the four words is how `blocked` becomes workable."""
        self.marker("row")
        for word in ("ready_to_send", "blocked"):
            with self.subTest(word=word):
                self.seed(word)
                self.assertEqual(self.only().status, word)
                self.assertEqual(self.picked(), [])

    def test_the_row_key_is_the_registered_checkout_and_the_prd_path(self) -> None:
        rows = sd_lib.Rows(self.root)
        self.addCleanup(rows.close)
        self.assertEqual(rows.external_id(self.item), self.identity())

    def test_a_linked_worktree_reads_the_main_checkout_s_row(self) -> None:
        """The migration enumerates the `repo` table, and a worktree was never
        added to it -- so its rows are keyed by the checkout it was cut from."""
        self.git("branch", "side")
        kept = self.tmp / "kept"
        self.git("worktree", "add", "-q", str(kept), "side")
        rows = sd_lib.Rows(kept)
        self.addCleanup(rows.close)
        self.assertEqual(
            rows.external_id(kept / "docs" / "work" / ITEM), self.identity()
        )

    def test_a_database_with_no_row_for_the_item_is_unknown_and_not_open(self) -> None:
        """The fail-open this whole class is written against.

        A row that is not there is an item the database has lost, and reading
        it as "open" is how a delivered item is picked again. The registered
        repository exists; only the item's row does not.
        """
        self.marker("row")
        self.database()
        item = self.only()
        self.assertEqual(item.status, "unknown")
        self.assertTrue(
            any(self.identity() in problem for problem in item.inconsistencies)
        )
        self.assertEqual(self.picked(), [])

    def test_a_row_whose_status_is_not_a_word_is_unknown_and_not_open(self) -> None:
        """The schema's own CHECK stops the six-word list being widened by a
        write, so the guard is exercised where a widened schema would reach
        it: a row that comes back saying something this version has no word
        for. It must not be read as an item nobody has started."""
        self.marker("row")
        self.seed("planning")
        rows = sd_lib.Rows(self.root)
        self.addCleanup(rows.close)
        rows._read = lambda *_: {"status": "shipped"}
        word, problem = rows.status(self.item)
        self.assertEqual(word, "")
        self.assertIn("'shipped'", problem)

    def test_a_row_the_library_refuses_is_unknown_and_not_open(self) -> None:
        self.marker("row")
        self.seed("planning")
        rows = sd_lib.Rows(self.root)
        self.addCleanup(rows.close)

        def refuse(*_: Any) -> Any:
            raise RuntimeError("the database is locked")

        rows._read = refuse
        word, problem = rows.status(self.item)
        self.assertEqual(word, "")
        self.assertIn("the database is locked", problem)

    def test_the_database_is_opened_once_for_a_whole_enumeration(self) -> None:
        self.marker("row")
        self.seed("ready")
        self.seed("ready", name=OTHER)
        (self.work / OTHER).mkdir()
        (self.work / OTHER / "prd.md").write_text(prd(None), encoding="utf-8")
        opened = []
        real = sd_lib.Rows.__init__

        def counted(instance: Any, root: Any) -> None:
            opened.append(root)
            real(instance, root)

        with mock.patch.object(sd_lib.Rows, "__init__", counted):
            self.assertEqual(len(sd_lib.work_items(self.root)), 2)
        self.assertEqual(len(opened), 1, "one enumeration, one connection")


class GitAloneWhenThereIsNoDatabase(Fixture):
    """A's round forty-one: the line while the marker is absent, git once it is.

    This is also the criterion's recording double -- in a checkout with no
    database, every reader that picks an item asks `sd_lib.delivered` and
    nothing else.
    """

    def setUp(self) -> None:
        super().setUp()
        self.marker("row")
        self.write(prd(None))
        self.commit("chore: the retire")
        self.calls: list[tuple[Any, ...]] = []

    def recorder(self, answer: sd_lib.Answer):
        def record(root: Any, item: str) -> sd_lib.Answer:
            self.calls.append((pathlib.Path(root), item))
            return answer

        return mock.patch.object(sd_lib, "delivered", record)

    def test_a_delivered_item_is_done_and_the_line_is_not_consulted(self) -> None:
        """"and nothing else": the line says `planning` and the answer is
        `done`, so no second source contributed to it."""
        self.write(prd("planning"))
        with self.recorder(sd_lib.Answer(sd_lib.YES)):
            self.assertEqual(self.only().status, "done")
            self.assertEqual(self.picked(), [])
        self.assertEqual(self.calls[0], (self.root, ITEM))

    def test_an_undelivered_item_is_still_picked(self) -> None:
        with self.recorder(sd_lib.Answer(sd_lib.NO)):
            self.assertEqual(self.picked(), [ITEM])

    def test_what_the_retire_left_says_which_kind_of_open(self) -> None:
        self.write(prd(None, branch="wip/a-thing"))
        with self.recorder(sd_lib.Answer(sd_lib.NO)):
            self.assertEqual(self.only().status, "in_progress")
        self.write(prd(None))
        with self.recorder(sd_lib.Answer(sd_lib.NO)):
            self.assertEqual(self.only().status, "planning")

    def test_unknown_is_not_no(self) -> None:
        """A shallow clone and an unreachable remote cannot see the trailer.
        Reading either as "not delivered" reopens finished work, so neither is
        allowed to produce a status any reader picks."""
        with self.recorder(sd_lib.Answer(sd_lib.UNKNOWN, "git fetch --unshallow")):
            item = self.only()
            self.assertEqual(self.picked(), [])
        self.assertEqual(item.status, "unknown")
        self.assertTrue(
            any("git fetch --unshallow" in p for p in item.inconsistencies)
        )

    def test_the_question_is_asked_once_per_item_and_of_git_only(self) -> None:
        (self.work / OTHER).mkdir()
        (self.work / OTHER / "prd.md").write_text(prd(None), encoding="utf-8")
        with self.recorder(sd_lib.Answer(sd_lib.NO)):
            sd_lib.work_items(self.root)
        self.assertEqual(self.calls, [(self.root, OTHER), (self.root, ITEM)])

    def test_the_real_answer_comes_off_a_real_trailer(self) -> None:
        """No double at all: the trailer is written and `sd_lib.delivered`
        reads it, so the recorder above is standing in for something real."""
        self.assertEqual(self.picked(), [ITEM])
        self.git("commit", "-q", "--allow-empty", "-m",
                 merge_message(f"Item: {ITEM}", f"Delivers: {ITEM}"))
        self.assertEqual(self.only().status, "done")
        self.assertEqual(self.picked(), [])


class WhatStatusNames(Fixture):
    """Requirement 4. Both words are the criterion's."""

    def test_a_surviving_line_that_disagrees_is_named_stale(self) -> None:
        """A worktree kept across the retire, on a branch that still carries
        its line, after a status change made in the database."""
        self.git("branch", "-q", "before-the-retire")
        self.marker("row")
        self.write(prd(None))
        self.commit("chore: the retire")
        kept = self.tmp / "kept"
        self.git("worktree", "add", "-q", str(kept), "before-the-retire")
        (kept / "docs" / "work" / sd_lib.STATUS_MARKER).write_text("row\n", encoding="utf-8")
        self.seed("ready")

        found = [i for i in sd_lib.work_items(kept) if i.slug == "a-thing"][0]
        self.assertEqual(found.status, "ready")
        stale = [p for p in found.inconsistencies if "stale" in p]
        self.assertEqual(len(stale), 1, found.inconsistencies)
        self.assertIn("'planning'", stale[0])
        self.assertIn("'ready'", stale[0])

    def test_a_line_that_agrees_is_not_called_stale(self) -> None:
        """The check is what the line says, not that there is one. A line the
        retire has not reached yet is rule 1's finding, not a disagreement."""
        self.marker("row")
        self.seed("planning")
        self.assertEqual(
            [p for p in self.only().inconsistencies if "stale" in p], []
        )

    def test_a_done_row_no_commit_closed_is_named_unmarked(self) -> None:
        """The hand merge through the remote carried `Item:` and no closing
        trailer; `deliver` on the item screen then wrote the row `done`."""
        self.marker("row")
        self.write(prd(None))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", merge_message(f"Item: {ITEM}"))
        self.seed("done")
        item = self.only()
        self.assertEqual(item.status, "done")
        unmarked = [p for p in item.inconsistencies if "unmarked" in p]
        self.assertEqual(len(unmarked), 1, item.inconsistencies)
        self.assertIn(ITEM, unmarked[0])

    def test_a_done_row_a_commit_did_close_is_not_named_unmarked(self) -> None:
        self.marker("row")
        self.write(prd(None))
        self.git("add", "-A")
        self.git("commit", "-q", "-m",
                 merge_message(f"Item: {ITEM}", f"Closes: {ITEM}"))
        self.seed("done")
        self.assertEqual(
            [p for p in self.only().inconsistencies if "unmarked" in p], []
        )

    def test_sd_status_prints_both_words(self) -> None:
        self.marker("row")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", merge_message(f"Item: {ITEM}"))
        self.seed("done")
        printed = self.rendered()
        self.assertIn("stale", printed)
        self.assertIn("unmarked", printed)
        self.assertIn(ITEM, printed)

    def test_a_finding_is_never_elided_past_the_listed_items(self) -> None:
        """`done` items sort into the tail that stops at twenty, and a finding
        printed nowhere a human looks is what this section exists against."""
        self.marker("row")
        fillers = []
        for number in range(status_tool.LISTED_ITEMS + 5):
            name = f"2026-08-{number % 28 + 1:02d}-filler-{number}"
            (self.work / name).mkdir()
            (self.work / name / "prd.md").write_text(prd(None), encoding="utf-8")
            self.seed("done", name=name)
            fillers.append(name)
        # Every filler is delivered and clean, so only the one item with a
        # finding stands between the elision and the reader.
        self.git("add", "-A")
        self.git("commit", "-q", "-m", merge_message(
            f"Item: {ITEM}", *(f"Closes: {name}" for name in fillers)))
        self.seed("done")
        printed = self.rendered()
        self.assertIn("more not being worked", printed)
        self.assertIn("unmarked", printed)
        self.assertIn(ITEM, printed)


class RuleTwoReadsTheRow(Fixture):
    """Requirement 5. `check_ready` returns early on a word it cannot find."""

    def lint(self) -> list[str]:
        """Rule 2's findings alone.

        Rule 1 fails on a `prd.md` with no `status:` line and will go on
        failing until the retire commit changes its sign, which is the next
        pull request's work and not this one's. Filtering it out here keeps
        this class asserting the thing it is about.
        """
        report = lint.run(self.root, "docs/work", "docs/spec", "docs/decisions", None)
        return [f for f in report.failures if "is not one of" not in f]

    def test_the_three_checks_survive_the_retire(self) -> None:
        """Without the row, `check_ready` finds no workable item once the
        lines are gone and its three checks stop running everywhere at once."""
        self.marker("row")
        self.write(prd(None, criteria=False))
        self.seed("in_progress")
        failures = self.lint()
        self.assertTrue(
            any("states acceptance criteria" in f for f in failures), failures
        )
        self.assertTrue(
            any("records the branch it lives on" in f for f in failures), failures
        )

    def test_a_blocked_row_is_not_workable(self) -> None:
        self.marker("row")
        self.write(prd(None, criteria=False))
        self.seed("blocked")
        self.assertEqual(self.lint(), [])

    def test_with_no_marker_the_line_still_decides(self) -> None:
        self.write(prd("ready", criteria=False))
        self.assertTrue(
            any("states acceptance criteria" in f for f in self.lint()), self.lint()
        )

    def test_with_no_marker_an_archived_line_is_still_checked(self) -> None:
        """`status_report` answers `done` for anything under `archive/` by
        virtue of where it lives, and this repository holds one archived item
        whose line still says `in_progress`. Reading that as `done` would stop
        checking it -- the same switch as the retire, in miniature."""
        archived = self.work / "archive" / "2026-08" / OTHER
        archived.mkdir(parents=True)
        (archived / "prd.md").write_text(
            prd("in_progress", criteria=False), encoding="utf-8"
        )
        self.assertTrue(
            any("states acceptance criteria" in f for f in self.lint()), self.lint()
        )
