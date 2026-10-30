"""Video and book/article rows move to their Documents view and leave Tasks, Today and the counts (pack sd:6262).

`records.plan_documents` is the match list: a learning row titled as a YouTube video goes to Videos, a learning row
the operator lists goes to Books. `move_documents` writes `fields.document-type` on each, only for the plan the dry
run showed; `return_documents` takes it off. The reads leave a moved row out through `reads._unparked_clause`.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from sd_db import connect, reads, records, retention, today
from sd_db.jobs import cli
from sd_db.migrate import initialise
from sd_db.records import (
    RecordRefused,
    move_documents,
    plan_documents,
    return_documents,
)
from sd_db.writes import add_note, create_item

NOW = "2026-10-26T12:00:00Z"


def learning(connection, title, status="ready", stage="in-progress", **fields):
    """One `sdw.learning` base row, as the vault import files it: an idea item of source vault."""
    return create_item(connection, kind="idea", title=title, status=status, source="vault", stage=stage,
                       external_id=f"learning:Learning/{title}.md", path=f"Learning/{title}.md",
                       fields={"kind": "learning", "dateCreated": "2026-01-06", **fields}, body={"markdown": ""})


class DocumentsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        path = self.home / ".local/share/sd/sd.db"
        path.parent.mkdir(parents=True)
        initialise(path)
        self.db = connect(path)
        self.addCleanup(self.db.close)
        self.video = learning(self.db, "2016-06-06 - YouTube - Example Channel - A Talk", **{"content-type": "youtube"})
        self.named = learning(self.db, "2024-02-03 - YouTube - Other Channel - Queues - A Primer", status="planning",
                              stage="queued")
        self.book = learning(self.db, "Agile Retrospectives", **{"content-type": "book"})
        self.bare = learning(self.db, "A Listed Note", status="planning", stage="queued")
        self.course = learning(self.db, "A Course", status="planning", stage="queued", **{"content-type": "course"})
        self.task = create_item(self.db, kind="task", title="2025-01-01 - YouTube - Some Channel - Not a learning row")
        add_note(self.db, self.video, "comment", "worth a second watch", session="operator")

    def listed(self):
        return {row["id"] for row in reads.backlog_items(self.db, now=NOW)}

    def field(self, item):
        return self.db.execute("""SELECT json_extract(fields, '$."document-type"') FROM item WHERE id=?""",
                               (item,)).fetchone()[0]


class ThePlan(DocumentsCase):
    def test_videos_match_by_title_and_books_only_by_the_list(self):
        plan = plan_documents(self.db, books=[self.book, self.bare])
        self.assertEqual([(move.id, move.view) for move in plan.moves],
                         [(self.video, "videos"), (self.named, "videos"), (self.book, "books"), (self.bare, "books")])
        # The task row matches the title but is no learning row: listed, never moved.
        self.assertEqual([row[0] for row in plan.skipped], [self.task])
        self.assertEqual(plan.moved, ())

    def test_an_unlisted_book_is_a_candidate_not_a_move(self):
        plan = plan_documents(self.db, books=[])
        self.assertNotIn(self.book, [move.id for move in plan.moves])
        self.assertEqual([row[0] for row in plan.candidates], [self.book])

    def test_a_book_that_is_not_a_learning_row_refuses(self):
        with self.assertRaisesRegex(RecordRefused, f"item {self.task} is not a learning row"):
            plan_documents(self.db, books=[self.task])
        with self.assertRaisesRegex(RecordRefused, "item 999999 is not a learning row"):
            plan_documents(self.db, books=[999999])

    def test_the_digest_names_the_list(self):
        first = plan_documents(self.db, books=[self.book]).digest
        self.assertEqual(plan_documents(self.db, books=[self.book]).digest, first)
        self.assertNotEqual(plan_documents(self.db, books=[]).digest, first)


class TheMove(DocumentsCase):
    def test_a_moved_row_leaves_tasks_today_and_the_counts_and_keeps_its_id_and_notes(self):
        self.assertTrue({self.video, self.book} <= self.listed())
        add_note(self.db, self.book, "question", "Which edition?\nOption: first (Recommended)\nOption: second", session="operator")
        # Due and blocked rows, so Today's sections would show them.
        self.db.execute("UPDATE item SET due='2026-10-20' WHERE id=?", (self.video,))
        self.db.execute("UPDATE item SET due='2026-11-20' WHERE id=?", (self.book,))
        self.db.execute("UPDATE item SET status='blocked' WHERE id=?", (self.named,))
        sections = today.sections(self.db, now=NOW)
        ids = {row["id"] for key in ("planned", "blocked", "work") for row in sections[key]}
        self.assertTrue({self.video, self.named, self.book} <= ids)
        before = len(self.db.execute("SELECT id FROM note WHERE item=?", (self.video,)).fetchall())
        plan = plan_documents(self.db, books=[self.book])
        moved = move_documents(self.db, books=[self.book], plan=plan.digest, who="operator")
        self.assertEqual([move.id for move in moved.moves], [self.video, self.named, self.book])
        self.assertEqual((self.field(self.video), self.field(self.book)), ("videos", "books"))
        listed = self.listed()
        for item in (self.video, self.named, self.book):
            self.assertNotIn(item, listed)
            self.assertNotIn(item, {row["id"] for row in reads.backlog_items(self.db, now=NOW, parked=True)})
        # The rest stays: the course, the unlisted note and the task.
        self.assertTrue({self.course, self.bare, self.task} <= listed)
        sections = today.sections(self.db, now=NOW)
        ids = {row["id"] for key in ("planned", "blocked", "work") for row in sections[key]}
        self.assertFalse({self.video, self.named, self.book} & ids)
        # An open question on a moved row still reaches Decide: it waits on the operator.
        self.assertIn(self.book, {row["item"] for row in reads.open_notes(self.db, "question")})
        # The id, the notes, the stage and the status stay; one comment note says what moved it.
        row = self.db.execute("SELECT status, stage FROM item WHERE id=?", (self.video,)).fetchone()
        self.assertEqual((row["status"], row["stage"]), ("ready", "in-progress"))
        notes = self.db.execute("SELECT kind, body FROM note WHERE item=? ORDER BY id", (self.video,)).fetchall()
        self.assertEqual(len(notes), before + 1)
        self.assertEqual(notes[-1]["kind"], "comment")
        self.assertIn("Moved to Documents > Videos by operator", notes[-1]["body"])

    def test_apply_refuses_a_plan_from_another_list(self):
        seen = plan_documents(self.db, books=[]).digest
        with self.assertRaisesRegex(RecordRefused, "the match list changed since the dry run"):
            move_documents(self.db, books=[self.book], plan=seen, who="operator")
        learning(self.db, "2026-10-01 - YouTube - New Channel - Filed After The Dry Run")
        with self.assertRaisesRegex(RecordRefused, "the match list changed since the dry run"):
            move_documents(self.db, books=[], plan=seen, who="operator")
        self.assertIsNone(self.field(self.video))

    def test_a_write_that_fails_partway_moves_no_row(self):
        plan = plan_documents(self.db, books=[self.book])
        real = records.add_note
        calls = []

        def failing(*args, **kwargs):
            calls.append(args[1])
            if len(calls) == 2:
                raise OSError("disk went away")
            return real(*args, **kwargs)

        with mock.patch("sd_db.records.add_note", failing), self.assertRaises(OSError):
            move_documents(self.db, books=[self.book], plan=plan.digest, who="operator")
        self.assertEqual([self.field(item) for item in (self.video, self.named, self.book)], [None, None, None])
        # The same plan applies on the next run.
        move_documents(self.db, books=[self.book], plan=plan.digest, who="operator")
        self.assertEqual([self.field(item) for item in (self.video, self.named, self.book)],
                         ["videos", "videos", "books"])

    def test_a_second_run_finds_nothing_to_move(self):
        plan = plan_documents(self.db, books=[self.book])
        move_documents(self.db, books=[self.book], plan=plan.digest, who="operator")
        again = plan_documents(self.db, books=[self.book])
        self.assertEqual(again.moves, ())
        self.assertEqual({row[0] for row in again.moved}, {self.video, self.named, self.book})

    def test_a_store_before_parked_at_still_leaves_documents_out(self):
        plan = plan_documents(self.db, books=[])
        move_documents(self.db, books=[], plan=plan.digest, who="operator")
        with mock.patch("sd_db.reads._has_parked_at", return_value=False):
            clause = reads._unparked_clause(self.db)
        found = {row[0] for row in self.db.execute(f"SELECT id FROM item WHERE {clause}")}
        self.assertNotIn(self.video, found)
        self.assertIn(self.book, found)

    def test_a_row_with_unreadable_fields_still_lists(self):
        self.db.execute("UPDATE item SET fields='not json' WHERE id=?", (self.task,))
        self.assertIn(self.task, self.listed())
        # An empty or non-text view names no view, in SQL as in `document_view`.
        for held in ('""', "0", "null"):
            self.db.execute(f"""UPDATE item SET fields='{{"document-type": {held}}}' WHERE id=?""", (self.task,))
            self.assertIn(self.task, self.listed(), held)
            self.assertIsNone(reads.document_view({"document-type": json.loads(held)}))

    def test_the_prune_never_parks_a_document(self):
        plan = plan_documents(self.db, books=[])
        move_documents(self.db, books=[], plan=plan.digest, who="operator")
        old = "2025-01-01T00:00:00+00:00"
        self.db.execute("UPDATE item SET updated_at=?, priority=4", (old,))
        self.db.execute("UPDATE note SET timestamp=?", (old,))
        now = datetime(2026, 10, 26, 2, 10, tzinfo=UTC)
        parked = retention.park_untouched(self.db, now=now + timedelta(days=1))
        self.assertNotIn(self.video, parked)
        self.assertNotIn(self.named, parked)
        self.assertIn(self.book, parked)


class TheUndo(DocumentsCase):
    def test_undo_puts_the_row_back_in_tasks_with_its_id_and_notes(self):
        plan = plan_documents(self.db, books=[self.book])
        move_documents(self.db, books=[self.book], plan=plan.digest, who="operator")
        self.assertEqual(return_documents(self.db, [self.video, self.book], who="operator"), [self.video, self.book])
        self.assertIsNone(self.field(self.video))
        self.assertTrue({self.video, self.book} <= self.listed())
        self.assertNotIn(self.named, self.listed())
        body = self.db.execute("SELECT body FROM note WHERE item=? ORDER BY id DESC LIMIT 1", (self.book,)).fetchone()[0]
        self.assertIn("Moved back from Documents > Books by operator", body)
        self.assertIn("worth a second watch", [row[0] for row in self.db.execute(
            "SELECT body FROM note WHERE item=?", (self.video,))])

    def test_undo_refuses_a_row_that_was_not_moved(self):
        plan = plan_documents(self.db, books=[])
        move_documents(self.db, books=[], plan=plan.digest, who="operator")
        with self.assertRaisesRegex(RecordRefused, f"item {self.book} is in no Documents view"):
            return_documents(self.db, [self.video, self.book], who="operator")
        self.assertEqual(self.field(self.video), "videos")


class TheVerb(DocumentsCase):
    def sd_db(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["records", "documents", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_the_dry_run_opens_the_database_read_only(self):
        with mock.patch("sd_db.jobs.cli._open_for_write", side_effect=AssertionError("a dry run writes nothing")):
            code, out, err = self.sd_db("--book", str(self.book))
        self.assertEqual(code, 0, err)
        self.assertIn(f"move  videos  sd:{self.video}  2016-06-06 - YouTube - Example Channel - A Talk", out)
        self.assertIn(f"move  books   sd:{self.book}  Agile Retrospectives", out)
        self.assertIn(f"skip  not a learning row  sd:{self.task}", out)
        digest = plan_documents(self.db, books=[self.book]).digest
        self.assertIn(f"3 to move (2 videos, 1 books); plan {digest}", out)
        self.assertIn("dry run, nothing moved", out)
        self.assertIsNone(self.field(self.video))

    def test_apply_moves_the_plan_and_undo_moves_it_back(self):
        digest = plan_documents(self.db, books=[self.book]).digest
        code, out, err = self.sd_db("--book", str(self.book), "--apply", digest)
        self.assertEqual(code, 0, err)
        self.assertIn("moved 3 row(s)", out)
        self.assertEqual(self.field(self.book), "books")
        code, out, err = self.sd_db("--apply", digest)
        self.assertEqual(code, 1)
        self.assertIn("the match list changed since the dry run", err)
        code, out, err = self.sd_db("--undo", str(self.book))
        self.assertEqual(code, 0, err)
        self.assertIsNone(self.field(self.book))

    def test_bad_arguments_exit_one(self):
        for argv in (["--book"], ["--book", "x"], ["--undo"], ["--apply"], ["--undo", "1", "--apply", "a"], ["--all"]):
            with self.subTest(argv=argv):
                code, _, err = self.sd_db(*argv)
                self.assertEqual(code, 1)
                self.assertIn("sd-db records: expected", err)


if __name__ == "__main__":
    unittest.main()
