"""`sd_db.review`: one review queue made of notes, and `sd-db review file|export|apply` (sd:3635).

Each case names the failure-table row of the design it covers (system
`docs/work/2026-10-12-review-queue/design.md`). Every case runs on a temporary
store; none reads or writes the live database.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from sd_db import connect, review, workflow, writes
from sd_db.migrate import initialise
from . import support

KEY_A = b"subject,tier\nexample.test/a@1a2b3c4:src/one.py,cheap\nexample.test/a@1a2b3c4:src/two.py,deep\n"
KEY_B = b"subject,tier\nexample.test/b@5d6e7f8:src/one.py,skip\n"


def batch(**changes) -> dict:
    """A small valid batch file, open mode, two questions."""
    found = {
        "schema": 1, "queue": "jev-entry-2", "batch": "C1", "title": "Label: C1 review tiers",
        "source": "system@6c4317b", "mode": "open",
        "questions": [
            {"subject": "example.test/a@1a2b3c4:src/one.py", "text": "Which review tier fits this change?",
             "evidence": ["diff: git show 1a2b3c4"], "options": ["skip", "cheap", "standard", "deep"]},
            {"subject": "example.test/a@1a2b3c4:src/two.py", "text": "Which review tier fits this change?",
             "options": ["skip", "cheap", "standard", "deep"]},
        ],
    }
    found.update(changes)
    return found


def sealed(key: bytes = KEY_A, **changes) -> dict:
    return batch(mode="sealed", seal={"sha256": hashlib.sha256(key).hexdigest(), "name": "key-C1.csv"}, **changes)


def nightly(name: str, subjects: list[str], **changes) -> dict:
    changes.setdefault("queue", "nightly")
    return batch(batch=name, title=f"Nightly review {name}", questions=[
        {"subject": subject, "text": f"Suggestion: {subject}. Expected gain: fewer stalls.",
         "evidence": ["log: example.test/logs/run.log"], "options": ["Approve", "Reject"]}
        for subject in subjects], **changes)


class ReviewCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "sd.db"
        initialise(self.path)
        self.db = connect(self.path)
        self.addCleanup(self.db.close)

    def counts(self) -> tuple[int, int]:
        return (self.db.execute("SELECT count(*) FROM item").fetchone()[0],
                self.db.execute("SELECT count(*) FROM note").fetchone()[0])

    def file(self, found: dict, **extra) -> int:
        result = review.file(self.db, found, who="tester", **extra)
        return result["item"]

    def rule(self, item: int, index: int, option: str) -> dict:
        batch_read = review.read(self.db, item)
        note = batch_read["questions"][index]["note"]
        revision = workflow.item_state(self.db, item)["revision"]
        return review.rule(self.db, item, note, option, expected_revision=revision, who="tester")

    def withdraw(self, item: int, ruling: int) -> dict:
        revision = workflow.item_state(self.db, item)["revision"]
        return review.withdraw(self.db, item, ruling, expected_revision=revision, who="tester")

    def status(self, item: int) -> str:
        return self.db.execute("SELECT status FROM item WHERE id = ?", (item,)).fetchone()[0]


class FileABatch(ReviewCase):
    def test_the_item_carries_the_ref_the_header_and_one_question_note_each(self):
        item = self.file(batch())
        row = self.db.execute("SELECT * FROM item WHERE id = ?", (item,)).fetchone()
        self.assertEqual((row["source"], row["external_id"], row["title"]),
                         ("task-ref", "review:jev-entry-2:C1", "Label: C1 review tiers"))
        found = review.read(self.db, item)
        self.assertEqual(found["header"]["queue"], "jev-entry-2")
        self.assertEqual(found["header"]["source"], "system@6c4317b")
        self.assertEqual([q["subject"] for q in found["questions"]],
                         ["example.test/a@1a2b3c4:src/one.py", "example.test/a@1a2b3c4:src/two.py"])
        first = found["questions"][0]
        self.assertEqual(first["options"], ["skip", "cheap", "standard", "deep"])
        self.assertEqual(first["evidence"], ["diff: git show 1a2b3c4"])
        body = self.db.execute("SELECT kind, body FROM note WHERE id = ?", (first["note"],)).fetchone()
        # The Decisions panel's format: the question, then one `Option:` line per choice.
        self.assertEqual(body["kind"], "question")
        self.assertIn("\nOption: skip\nOption: cheap\n", body["body"])
        self.assertEqual(first["sha256"], hashlib.sha256(body["body"].encode()).hexdigest())

    def test_an_error_after_the_second_question_leaves_no_item_and_no_note(self):
        before = self.counts()
        real = writes.add_note
        calls = []

        def failing(*args, **kwargs):
            calls.append(args)
            if len(calls) == 4:  # the header, two questions, then a third write
                raise RuntimeError("stopped after the second question")
            return real(*args, **kwargs)

        three = batch()
        three["questions"].append({"subject": "example.test/a@1a2b3c4:src/three.py",
                                   "text": "Which tier?", "options": ["a", "b"]})
        with mock.patch.object(review, "add_note", side_effect=failing):
            with self.assertRaises(RuntimeError):
                review.file(self.db, three, who="tester")
        self.assertEqual(self.counts(), before)
        # The rerun files the whole batch.
        self.assertEqual(len(review.read(self.db, self.file(three))["questions"]), 3)

    def test_filing_twice_returns_one_item(self):
        first = review.file(self.db, batch(), who="tester")
        before = self.counts()
        second = review.file(self.db, batch(), who="tester")
        self.assertEqual((first["created"], second["created"]), (True, False))
        self.assertEqual(first["item"], second["item"])
        self.assertEqual(self.counts(), before)

    def test_a_changed_option_is_refused_naming_it_and_the_batch_is_unchanged(self):
        item = self.file(batch())
        before = (self.counts(), workflow.item_state(self.db, item)["revision"])
        changed = batch()
        changed["questions"][1]["options"] = ["skip", "cheap", "standard", "deeper"]
        with self.assertRaisesRegex(review.ReviewError, r"src/two\.py.*options"):
            review.file(self.db, changed, who="tester")
        self.assertEqual((self.counts(), workflow.item_state(self.db, item)["revision"]), before)

    def test_a_sealed_batch_without_a_good_seal_files_nothing(self):
        before = self.counts()
        broken = [batch(mode="sealed"),
                  batch(mode="sealed", seal={"sha256": "abc", "name": "key.csv"}),
                  batch(mode="sealed", seal={"sha256": "A" * 64, "name": "key.csv"}),
                  batch(mode="sealed", seal={"sha256": "a" * 64}),
                  batch(seal={"sha256": "a" * 64, "name": "key.csv"})]
        for found in broken:
            with self.subTest(found=found.get("seal")), self.assertRaises(review.ReviewError):
                review.file(self.db, found, who="tester")
        self.assertEqual(self.counts(), before)

    def test_the_sealed_header_carries_the_seal(self):
        item = self.file(sealed())
        header = review.read(self.db, item)["header"]
        self.assertEqual((header["mode"], header["seal"]), ("sealed", hashlib.sha256(KEY_A).hexdigest()))

    def test_the_schema_limits_are_refused_before_any_write(self):
        def one(**question):
            return batch(questions=[{"subject": "s", "text": "t", "options": ["a", "b"], **question}])

        def many(count):
            return batch(questions=[{"subject": f"s{n}", "text": "t", "options": ["a", "b"]} for n in range(count)])

        refused = {
            "one option": one(options=["a"]),
            "ten options": one(options=[str(n) for n in range(10)]),
            "a repeated option": one(options=["a", "a"]),
            "a long option": one(options=["a", "b" * 81]),
            "a padded option": one(options=["a", " b"]),
            "long text": one(text="x" * 4097),
            "six evidence lines": one(evidence=["e"] * 6),
            "a long subject": one(subject="s" * 201),
            "an Option line in the text": one(text="Which?\nOption: smuggled"),
            "a Subject line in the text": one(text="Which?\n  Subject: other"),
            "a newline in an option": one(options=["a", "b\nc"]),
            "a repeated subject": batch(questions=[{"subject": "s", "text": "t", "options": ["a", "b"]}] * 2),
            "an unknown key": batch(owner="someone"),
            "a queue with a colon": batch(queue="a:b"),
            "an unknown mode": batch(mode="secret"),
            "schema 2": batch(schema=2),
            "501 questions": many(501),
            "a limit of 501": batch(limit=501),
            "no questions": batch(questions=[]),
        }
        before = self.counts()
        for name, found in refused.items():
            with self.subTest(name), self.assertRaises(review.ReviewError):
                review.file(self.db, found, who="tester")
        self.assertEqual(self.counts(), before)
        # 501 questions file when a limit says how many to keep.
        result = review.file(self.db, batch(batch="big", questions=many(501)["questions"], limit=500), who="tester")
        self.assertEqual(len(result["dropped"]), 1)
        self.assertEqual(len(review.read(self.db, result["item"])["questions"]), 500)


    def test_300_questions_file_in_one_transaction(self):
        many = batch(questions=[{"subject": f"example.test/a@1a2b3c4:src/{n}.py", "text": "Which tier?",
                                 "options": ["skip", "cheap", "standard", "deep"]} for n in range(300)])
        statements = []
        self.db.set_trace_callback(statements.append)
        item = self.file(many)
        self.db.set_trace_callback(None)
        self.assertEqual([s for s in statements if s in ("BEGIN IMMEDIATE", "COMMIT")], ["BEGIN IMMEDIATE", "COMMIT"])
        self.assertEqual(len(review.read(self.db, item)["questions"]), 300)


class NightlySuppression(ReviewCase):
    def test_a_subject_rejected_in_90_days_is_dropped_and_named(self):
        first = self.file(nightly("2026-10-11", ["cap-retries", "split-gate", "old-idea"]))
        self.rule(first, 0, "Reject")
        self.rule(first, 1, "Approve")
        result = review.file(self.db, nightly("2026-10-12", ["cap-retries", "split-gate", "new-idea"]), who="tester")
        self.assertEqual([q["subject"] for q in review.read(self.db, result["item"])["questions"]],
                         ["split-gate", "new-idea"])
        self.assertEqual([d["subject"] for d in result["dropped"]], ["cap-retries"])
        self.assertIn("rejected", result["dropped"][0]["reason"])

    def test_a_rejection_older_than_90_days_does_not_suppress(self):
        first = self.file(nightly("2026-06-01", ["cap-retries"]))
        self.rule(first, 0, "Reject")
        later = (datetime.now(UTC) + timedelta(days=91)).isoformat(timespec="seconds")
        result = review.file(self.db, nightly("2026-09-01", ["cap-retries"]), who="tester", now=later)
        self.assertEqual(result["dropped"], [])

    def test_a_withdrawn_rejection_does_not_suppress(self):
        first = self.file(nightly("2026-10-11", ["cap-retries"]))
        ruled = self.rule(first, 0, "Reject")
        self.withdraw(first, ruled["ruling"]["id"])
        result = review.file(self.db, nightly("2026-10-12", ["cap-retries"]), who="tester")
        self.assertEqual(result["dropped"], [])

    def test_the_limit_keeps_the_first_in_rank_and_names_the_rest(self):
        result = review.file(self.db, nightly("2026-10-12", [f"idea-{n}" for n in range(7)], limit=5), who="tester")
        self.assertEqual([q["subject"] for q in review.read(self.db, result["item"])["questions"]],
                         [f"idea-{n}" for n in range(5)])
        self.assertEqual([d["subject"] for d in result["dropped"]], ["idea-5", "idea-6"])

    def test_a_rerun_after_a_new_rejection_still_finds_its_batch(self):
        """The same file twice is one batch, even when a rejection of one of its subjects landed between."""
        yesterday = self.file(nightly("2026-10-11", ["cap-retries"]))
        today = review.file(self.db, nightly("2026-10-12", ["cap-retries", "split-gate"]), who="tester")
        self.rule(yesterday, 0, "Reject")
        before = self.counts()
        again = review.file(self.db, nightly("2026-10-12", ["cap-retries", "split-gate"]), who="tester")
        self.assertEqual((again["item"], again["created"], again["dropped"]), (today["item"], False, []))
        self.assertEqual([q["subject"] for q in review.read(self.db, today["item"])["questions"]],
                         ["cap-retries", "split-gate"])
        self.assertEqual(self.counts(), before)


class LabelAndWithdraw(ReviewCase):
    def test_a_ruling_writes_the_decision_note_and_resolves_the_question(self):
        item = self.file(batch())
        state = self.rule(item, 0, "cheap")
        self.assertEqual(state["ruling"]["body"], f"Ruling on note #{review.read(self.db, item)['questions'][0]['note']}: cheap")
        found = review.read(self.db, item)
        self.assertEqual((found["questions"][0]["label"], found["open"], found["labels"]), ("cheap", 1, 1))

    def test_the_decisions_panels_two_calls_land_a_label_too(self):
        """Older state: the dashboard before the Review page writes a ruling with the same two library calls."""
        item = self.file(batch())
        note = review.read(self.db, item)["questions"][0]["note"]
        ruled = workflow.add_item_note(self.db, item, kind="decision", who="dashboard",
                                       body=f"Ruling on note #{note}: standard")
        workflow.resolve_item_note(self.db, note, who="dashboard", expected_revision=ruled["revision"])
        found = review.read(self.db, item)["questions"][0]
        self.assertEqual((found["label"], found["ruled_by"]), ("standard", "dashboard"))

    def test_a_ruling_naming_an_option_not_offered_is_not_a_label(self):
        item = self.file(batch())
        note = review.read(self.db, item)["questions"][0]["note"]
        workflow.add_item_note(self.db, item, kind="decision", who="tester", body=f"Ruling on note #{note}: medium")
        workflow.resolve_item_note(self.db, note, who="tester")
        found = review.read(self.db, item)["questions"][0]
        self.assertEqual((found["label"], found["rulings"]), (None, []))

    def test_a_stale_revision_is_refused_and_writes_nothing(self):
        item = self.file(batch())
        note = review.read(self.db, item)["questions"][0]["note"]
        stale = workflow.item_state(self.db, item)["revision"]
        self.rule(item, 1, "skip")
        before = self.counts()
        with self.assertRaises(workflow.StaleItem):
            review.rule(self.db, item, note, "cheap", expected_revision=stale, who="tester")
        self.assertEqual(self.counts(), before)

    def test_an_option_not_offered_and_a_question_already_ruled_are_refused(self):
        item = self.file(batch())
        with self.assertRaisesRegex(review.ReviewError, "no option"):
            self.rule(item, 0, "medium")
        self.rule(item, 0, "cheap")
        with self.assertRaisesRegex(review.ReviewError, "ruled"):
            self.rule(item, 0, "deep")

    def test_a_note_outside_the_batch_is_refused(self):
        item = self.file(batch())
        extra = workflow.add_item_note(self.db, item, kind="question", who="tester",
                                       body="Hand filed?\nOption: yes\nOption: no")["note"]["id"]
        revision = workflow.item_state(self.db, item)["revision"]
        with self.assertRaisesRegex(review.ReviewError, "not a question of"):
            review.rule(self.db, item, extra, "yes", expected_revision=revision, who="tester")

    def test_an_item_that_is_not_a_batch_is_refused(self):
        plain = workflow.capture_task(self.db, title="a plain task", who="tester")["item"]["id"]
        with self.assertRaisesRegex(review.ReviewError, "not a review batch"):
            review.read(self.db, plain)

    def test_a_withdrawal_reopens_the_question_and_keeps_both_notes(self):
        item = self.file(batch())
        ruled = self.rule(item, 0, "cheap")
        note = review.read(self.db, item)["questions"][0]["note"]
        state = self.withdraw(item, ruled["ruling"]["id"])
        self.assertEqual(state["withdrawal"]["body"], f"Withdrawn: ruling #{ruled['ruling']['id']} on note #{note}")
        found = review.read(self.db, item)["questions"][0]
        self.assertEqual((found["label"], found["open"]), (None, True))
        resolved = self.db.execute("SELECT resolved_at FROM note WHERE id = ?", (note,)).fetchone()[0]
        self.assertIsNone(resolved)
        self.assertEqual([r["ruling"] for r in found["rulings"] if r["withdrawal"]], [ruled["ruling"]["id"]])
        # It can be ruled again.
        self.assertEqual(self.rule(item, 0, "deep")["ruling"]["body"], f"Ruling on note #{note}: deep")
        self.assertEqual(review.read(self.db, item)["questions"][0]["label"], "deep")

    def test_a_second_withdrawal_is_refused_and_nothing_moves(self):
        item = self.file(batch())
        ruled = self.rule(item, 0, "cheap")
        self.withdraw(item, ruled["ruling"]["id"])
        before = (self.counts(), workflow.item_state(self.db, item)["revision"])
        with self.assertRaisesRegex(review.ReviewError, "withdrawn"):
            self.withdraw(item, ruled["ruling"]["id"])
        self.assertEqual((self.counts(), workflow.item_state(self.db, item)["revision"]), before)

    def test_a_superseded_ruling_cannot_be_withdrawn(self):
        item = self.file(batch())
        first = self.rule(item, 0, "cheap")
        self.withdraw(item, first["ruling"]["id"])
        self.rule(item, 0, "deep")
        with self.assertRaises(review.ReviewError):
            self.withdraw(item, first["ruling"]["id"])

    def test_a_withdrawal_naming_another_question_moves_nothing(self):
        item = self.file(batch())
        ruled = self.rule(item, 0, "cheap")
        other = review.read(self.db, item)["questions"][1]["note"]
        workflow.add_item_note(self.db, item, kind="decision", who="tester",
                               body=f"Withdrawn: ruling #{ruled['ruling']['id']} on note #{other}")
        found = review.read(self.db, item)["questions"][0]
        self.assertEqual((found["label"], found["ruling"]), ("cheap", ruled["ruling"]["id"]))
        self.withdraw(item, ruled["ruling"]["id"])
        self.assertIsNone(review.read(self.db, item)["questions"][0]["label"])

    def test_a_reopened_batch_still_refuses_and_a_late_hand_ruling_moves_no_label(self):
        item = self.file(batch())
        self.rule(item, 0, "cheap")
        workflow.change_status(self.db, item, "done", who="tester", reason="closed for the test")
        workflow.change_status(self.db, item, "planning", who="tester")
        with self.assertRaisesRegex(review.ReviewError, "closed"):
            self.rule(item, 1, "skip")
        note = review.read(self.db, item)["questions"][1]["note"]
        ruled = workflow.add_item_note(self.db, item, kind="decision", who="tester",
                                       body=f"Ruling on note #{note}: deep")
        workflow.resolve_item_note(self.db, note, who="tester", expected_revision=ruled["revision"])
        found = review.read(self.db, item)["questions"][1]
        self.assertEqual((found["label"], [late["note"] for late in found["late"]]), (None, [ruled["note"]["id"]]))

    def test_a_done_batch_refuses_a_ruling_and_a_withdrawal(self):
        item = self.file(batch())
        ruled = self.rule(item, 0, "cheap")
        workflow.change_status(self.db, item, "done", who="tester", reason="closed for the test")
        before = self.counts()
        with self.assertRaisesRegex(review.ReviewError, "closed"):
            self.rule(item, 1, "skip")
        with self.assertRaisesRegex(review.ReviewError, "closed"):
            self.withdraw(item, ruled["ruling"]["id"])
        self.assertEqual(self.counts(), before)


class Export(ReviewCase):
    def test_the_manifest_and_each_line_carry_the_provenance(self):
        item = self.file(batch())
        ruled = self.rule(item, 0, "cheap")
        self.withdraw(item, ruled["ruling"]["id"])
        self.rule(item, 0, "deep")
        note = review.read(self.db, item)["questions"][0]["note"]
        workflow.add_item_note(self.db, item, who="tester", body=f"On note #{note}: borderline")
        lines = review.export(self.db, item, who="tester")
        manifest, first, second = lines
        self.assertEqual({k: manifest[k] for k in ("kind", "batch", "ref", "queue", "source", "mode", "seal",
                                                     "questions", "labels", "open")},
                         {"kind": "manifest", "batch": item, "ref": "review:jev-entry-2:C1", "queue": "jev-entry-2",
                          "source": "system@6c4317b", "mode": "open", "seal": None,
                          "questions": 2, "labels": 1, "open": 1})
        self.assertRegex(manifest["exported_by"], r"^sd-ai-command-pack@([0-9a-f]{40}|unknown)$")
        self.assertEqual((first["label"], first["position"], first["ruled_by"]), ("deep", 4, "tester"))
        # A producer's per-question provenance, such as a grader version, rides in the evidence lines.
        self.assertEqual(first["evidence"], ["diff: git show 1a2b3c4"])
        self.assertEqual([w["ruling"] for w in first["withdrawn"]], [ruled["ruling"]["id"]])
        self.assertEqual([c["text"] for c in first["comments"]], ["borderline"])
        body = self.db.execute("SELECT body FROM note WHERE id = ?", (note,)).fetchone()[0]
        self.assertEqual(first["question_sha256"], hashlib.sha256(body.encode()).hexdigest())
        self.assertEqual((second["label"], second["ruling"]), (None, None))
        self.assertNotIn("key", first)

    def test_the_file_lands_through_a_part_file_and_a_rename(self):
        item = self.file(batch())
        out = self.root / "out" / "labels.jsonl"
        out.parent.mkdir()
        review.write(review.export(self.db, item, who="tester"), out)
        self.assertEqual(sorted(p.name for p in out.parent.iterdir()), ["labels.jsonl"])
        self.assertEqual(json.loads(out.read_text().splitlines()[0])["kind"], "manifest")

    def test_a_key_on_a_batch_that_is_not_sealed_is_refused(self):
        item = self.file(batch())
        with self.assertRaisesRegex(review.ReviewError, "not sealed"):
            review.export(self.db, item, key=KEY_A, who="tester")


class SealedExport(ReviewCase):
    def ruled_sealed(self) -> int:
        item = self.file(sealed())
        self.rule(item, 0, "cheap")
        self.rule(item, 1, "standard")
        return item

    def test_the_key_joins_in_by_subject_and_the_batch_closes(self):
        item = self.ruled_sealed()
        manifest, first, second = review.export(self.db, item, key=KEY_A, who="tester")
        self.assertEqual(self.status(item), "done")
        self.assertEqual(manifest["key"], {"sha256": hashlib.sha256(KEY_A).hexdigest(), "rows": 2, "unmatched": 0})
        self.assertEqual((first["key"]["tier"], second["key"]["tier"]), ("cheap", "deep"))

    def test_a_stop_after_the_close_refuses_a_ruling_and_the_rerun_writes_the_file(self):
        item = self.ruled_sealed()
        # Reopen one question first, so a ruling could land if the close did not hold.
        ruling = review.read(self.db, item)["questions"][1]["ruling"]
        self.withdraw(item, ruling)
        self.rule(item, 1, "deep")
        out = self.root / "labels.jsonl"
        with mock.patch.object(review, "_lines", side_effect=RuntimeError("stopped after the close")):
            with self.assertRaises(RuntimeError):
                review.export(self.db, item, key=KEY_A, who="tester")
        self.assertEqual(self.status(item), "done")
        latest = review.read(self.db, item)["questions"][1]["ruling"]
        with self.assertRaisesRegex(review.ReviewError, "closed"):
            self.withdraw(item, latest)
        review.write(review.export(self.db, item, key=KEY_A, who="tester"), out)
        self.assertEqual(len(out.read_text().splitlines()), 3)

    def test_another_batchs_key_is_refused_and_changes_nothing(self):
        item = self.ruled_sealed()
        before = (self.counts(), workflow.item_state(self.db, item)["revision"])
        with self.assertRaisesRegex(review.ReviewError, "key"):
            review.export(self.db, item, key=KEY_B, who="tester")
        self.assertEqual((self.counts(), workflow.item_state(self.db, item)["revision"]), before)
        self.assertEqual(self.status(item), "planning")

    def test_one_open_question_refuses_the_export_naming_the_count(self):
        item = self.file(sealed())
        self.rule(item, 0, "cheap")
        before = self.counts()
        with self.assertRaisesRegex(review.ReviewError, "1 question"):
            review.export(self.db, item, key=KEY_A, who="tester")
        self.assertEqual((self.counts(), self.status(item)), (before, "planning"))

    def test_without_a_key_a_sealed_batch_exports_labels_and_stays_open(self):
        item = self.file(sealed())
        self.rule(item, 0, "cheap")
        lines = review.export(self.db, item, who="tester")
        self.assertEqual((lines[0]["open"], self.status(item)), (1, "planning"))
        self.assertNotIn("key", lines[1])

    def test_a_key_is_parsed_only_after_the_close_commits(self):
        item = self.ruled_sealed()
        with mock.patch.object(review, "_key_rows", side_effect=RuntimeError("stopped while reading the key")):
            with self.assertRaises(RuntimeError):
                review.export(self.db, item, key=KEY_A, who="tester")
        self.assertEqual(self.status(item), "done")

    def test_a_late_hand_ruling_after_the_export_moves_no_label(self):
        item = self.ruled_sealed()
        review.export(self.db, item, key=KEY_A, who="tester")
        note = review.read(self.db, item)["questions"][0]["note"]
        workflow.add_item_note(self.db, item, kind="decision", who="tester", body=f"Ruling on note #{note}: deep")
        line = review.export(self.db, item, key=KEY_A, who="tester")[1]
        self.assertEqual((line["label"], len(line["late"])), ("cheap", 1))

    def test_a_key_with_a_repeated_subject_or_column_is_refused(self):
        for key, reason in ((KEY_A + b"example.test/a@1a2b3c4:src/one.py,skip\n", "more than once"),
                            (b"subject,subject,tier\nexample.test/a@1a2b3c4:src/one.py,"
                             b"example.test/a@1a2b3c4:src/two.py,deep\n", "unique, named columns")):
            with self.subTest(reason=reason):
                item = self.file(sealed(key=key, batch=f"K{len(key)}"))
                self.rule(item, 0, "cheap")
                self.rule(item, 1, "deep")
                with self.assertRaisesRegex(review.ReviewError, reason):
                    review.export(self.db, item, key=key, who="tester")


class Apply(ReviewCase):
    def approved(self) -> int:
        item = self.file(nightly("2026-10-12", ["cap-retries", "split-gate", "drop-idea"]))
        self.rule(item, 0, "Approve")
        self.rule(item, 1, "Approve")
        self.rule(item, 2, "Reject")
        return item

    def task(self, note: int):
        return self.db.execute("SELECT * FROM item WHERE source = 'task-ref' AND external_id = ?",
                               (f"review-approved:{note}",)).fetchone()

    def test_each_approval_becomes_one_task_and_the_ruled_batch_closes(self):
        item = self.approved()
        result = review.apply(self.db, "nightly", who="tester")
        notes = [q["note"] for q in review.read(self.db, item)["questions"]]
        self.assertEqual([t["note"] for t in result["tasks"]], notes[:2])
        self.assertIsNone(self.task(notes[2]))
        self.assertIn("cap-retries", self.task(notes[0])["title"])
        self.assertEqual((result["closed"], self.status(item)), ([item], "done"))

    def test_a_stop_after_the_first_task_reruns_to_one_task_each_and_never_edits_the_first(self):
        item = self.approved()
        notes = [q["note"] for q in review.read(self.db, item)["questions"]]
        real = workflow.capture_task
        calls = []

        def stopping(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("stopped after task one")
            return real(*args, **kwargs)

        with mock.patch.object(review.workflow, "capture_task", side_effect=stopping):
            with self.assertRaises(RuntimeError):
                review.apply(self.db, "nightly", who="tester")
        first = dict(self.task(notes[0]))
        self.assertIsNone(self.task(notes[1]))
        self.assertEqual(self.status(item), "planning")
        result = review.apply(self.db, "nightly", who="tester")
        self.assertEqual(([t["note"] for t in result["tasks"]], result["existing"]), ([notes[1]], [notes[0]]))
        self.assertEqual(dict(self.task(notes[0])), first)
        self.assertEqual(self.status(item), "done")
        self.assertEqual(review.apply(self.db, "nightly", who="tester")["tasks"], [])

    def test_a_batch_older_than_7_days_expires_its_open_questions_and_closes(self):
        item = self.file(nightly("2026-10-01", ["cap-retries", "split-gate"]))
        self.rule(item, 0, "Reject")
        self.assertEqual(review.apply(self.db, "nightly", who="tester")["closed"], [])
        later = (datetime.now(UTC) + timedelta(days=8)).isoformat(timespec="seconds")
        result = review.apply(self.db, "nightly", who="tester", now=later)
        note = review.read(self.db, item)["questions"][1]["note"]
        self.assertEqual((result["expired"], result["closed"]), ([note], [item]))
        found = review.read(self.db, item)["questions"][1]
        self.assertEqual((found["label"], [c["text"] for c in found["comments"]]), (None, ["Expired, not ruled"]))
        self.assertEqual((found["open"], found["expired"]), (False, True))
        resolved = self.db.execute("SELECT resolved_at FROM note WHERE id = ?", (note,)).fetchone()[0]
        self.assertIsNotNone(resolved)

    def test_a_stop_after_one_expiry_reruns_to_a_closed_batch(self):
        item = self.file(nightly("2026-10-01", ["cap-retries", "split-gate"]))
        later = (datetime.now(UTC) + timedelta(days=8)).isoformat(timespec="seconds")
        real = writes.resolve_note
        calls = []

        def stopping(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("stopped after one expiry")
            return real(*args, **kwargs)

        with mock.patch.object(review, "resolve_note", side_effect=stopping):
            with self.assertRaises(RuntimeError):
                review.apply(self.db, "nightly", who="tester", now=later)
        found = review.read(self.db, item)
        self.assertEqual((found["open"], self.status(item)), (1, "planning"))
        result = review.apply(self.db, "nightly", who="tester", now=later)
        self.assertEqual((len(result["expired"]), result["closed"]), (1, [item]))
        comments = [c for q in review.read(self.db, item)["questions"] for c in q["comments"]]
        self.assertEqual(len(comments), 2)

    def test_a_queue_with_other_options_is_refused_before_any_write(self):
        self.approved()
        labels = self.file(batch(queue="nightly", batch="odd"))
        before = self.counts()
        with self.assertRaisesRegex(review.ReviewError, "Approve and Reject"):
            review.apply(self.db, "nightly", who="tester")
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.status(labels), "planning")

    def test_another_queue_is_untouched(self):
        other = self.file(nightly("2026-10-12", ["cap-retries"], queue="weekly"))
        self.rule(other, 0, "Approve")
        self.assertEqual(review.apply(self.db, "nightly", who="tester"),
                         {"tasks": [], "existing": [], "expired": [], "closed": []})
        self.assertEqual(self.status(other), "planning")


class FrozenAtClose(ReviewCase):
    """Class pass (lane review on 2ab91c11d): labels come from the note history up to the first
    close, never from a question's live `resolved_at`, so nothing after the close moves them."""

    def hand_ruling(self, item: int, index: int, option: str) -> int:
        """A ruling written as a decision note alone, as `sd task note` writes one: no resolution."""
        note = review.read(self.db, item)["questions"][index]["note"]
        return workflow.add_item_note(self.db, item, kind="decision", who="tester",
                                      body=f"Ruling on note #{note}: {option}")["note"]["id"]

    def close(self, item: int) -> None:
        workflow.change_status(self.db, item, "done", who="tester", reason="closed for the test")

    @staticmethod
    def frozen(lines: list[dict]) -> list[dict]:
        return [{k: v for k, v in line.items() if k != "exported_at"} for line in lines]

    def test_resolving_a_question_after_the_close_moves_no_label(self):
        item = self.file(batch())
        self.rule(item, 0, "cheap")
        self.hand_ruling(item, 1, "deep")
        self.close(item)
        before = self.frozen(review.export(self.db, item, who="tester"))
        note = review.read(self.db, item)["questions"][1]["note"]
        workflow.resolve_item_note(self.db, note, who="tester")
        self.assertEqual(self.frozen(review.export(self.db, item, who="tester")), before)
        workflow.change_status(self.db, item, "planning", who="tester")
        self.assertEqual(self.frozen(review.export(self.db, item, who="tester")), before)
        self.assertEqual([line["label"] for line in before[1:]], ["cheap", "deep"])

    def test_reopening_a_question_after_the_close_moves_no_label(self):
        item = self.file(batch())
        self.rule(item, 0, "cheap")
        self.rule(item, 1, "skip")
        self.close(item)
        before = self.frozen(review.export(self.db, item, who="tester"))
        writes.reopen_note(self.db, review.read(self.db, item)["questions"][0]["note"])
        self.assertEqual(self.frozen(review.export(self.db, item, who="tester")), before)
        self.assertEqual((before[0]["labels"], before[0]["open"]), (2, 0))

    def test_a_sealed_export_is_the_same_after_a_question_is_reopened(self):
        item = self.file(sealed())
        self.rule(item, 0, "cheap")
        self.rule(item, 1, "deep")
        before = self.frozen(review.export(self.db, item, key=KEY_A, who="tester"))
        writes.reopen_note(self.db, review.read(self.db, item)["questions"][1]["note"])
        self.assertEqual(self.frozen(review.export(self.db, item, key=KEY_A, who="tester")), before)

    def test_a_rejection_still_suppresses_after_its_question_is_reopened(self):
        first = self.file(nightly("2026-10-11", ["cap-retries"]))
        self.rule(first, 0, "Reject")
        self.close(first)
        writes.reopen_note(self.db, review.read(self.db, first)["questions"][0]["note"])
        result = review.file(self.db, nightly("2026-10-12", ["cap-retries", "split-gate"]), who="tester")
        self.assertEqual([d["subject"] for d in result["dropped"]], ["cap-retries"])

    def test_apply_does_not_expire_a_question_a_ruling_settled(self):
        item = self.file(nightly("2026-10-01", ["cap-retries", "split-gate"]))
        self.rule(item, 0, "Reject")
        self.hand_ruling(item, 1, "Approve")
        later = (datetime.now(UTC) + timedelta(days=8)).isoformat(timespec="seconds")
        result = review.apply(self.db, "nightly", who="tester", now=later)
        self.assertEqual((result["expired"], len(result["tasks"]), result["closed"]), ([], 1, [item]))
        self.assertEqual(review.read(self.db, item)["questions"][1]["label"], "Approve")

    def test_apply_leaves_a_batch_once_closed_and_reopened_alone(self):
        item = self.file(nightly("2026-10-01", ["cap-retries", "split-gate"]))
        self.rule(item, 0, "Approve")
        self.close(item)
        workflow.change_status(self.db, item, "planning", who="tester")
        before = self.counts()
        later = (datetime.now(UTC) + timedelta(days=8)).isoformat(timespec="seconds")
        self.assertEqual(review.apply(self.db, "nightly", who="tester", now=later),
                         {"tasks": [], "existing": [], "expired": [], "closed": []})
        self.assertEqual(self.counts(), before)

    def test_an_expiry_after_the_close_settles_nothing(self):
        item = self.file(batch())
        self.rule(item, 0, "cheap")
        self.close(item)
        note = review.read(self.db, item)["questions"][1]["note"]
        workflow.add_item_note(self.db, item, who="tester", body=f"On note #{note}: Expired, not ruled")
        found = review.read(self.db, item)
        self.assertEqual((found["open"], found["questions"][1]["expired"]), (1, False))


class ABenchmarkPlugIn(ReviewCase):
    """The contract a benchmark's labelling flow needs (the work satellite's survey, note #16318 on sd:3635).

    Cells keyed by their row id; one vocabulary; provenance on every label;
    labels that outlive a regrade; an export a kappa reads; LLM adjudication
    conflicts filed as questions. No code here is the benchmark's.
    """

    VERDICTS = ["keyword_correct", "rubric_correct", "both_wrong"]

    def conflicts(self, name: str, source: str, key: bytes) -> dict:
        return batch(queue="benchmark-conflicts", batch=name, title=f"Conflicts {name}", source=source,
                     mode="sealed", seal={"sha256": hashlib.sha256(key).hexdigest(), "name": f"key-{name}.csv"},
                     questions=[{"subject": row, "text": "Which grader read this cell right?",
                                 "evidence": ["grader: rubric v3, prompt v7", "adjudication: needs_human_review, low"],
                                 "options": self.VERDICTS} for row in ("row-0001", "row-0002", "row-0003")])

    def test_labels_keyed_by_row_id_export_with_provenance_and_feed_an_agreement_count(self):
        key = b"row_id,judge\nrow-0001,rubric_correct\nrow-0002,both_wrong\nrow-0003,rubric_correct\n"
        item = self.file(self.conflicts("matrix-0001", "bench@1a2b3c4", key))
        for index, verdict in enumerate(["rubric_correct", "keyword_correct", "rubric_correct"]):
            self.rule(item, index, verdict)
        manifest, *lines = review.export(self.db, item, key=key, who="tester")
        self.assertEqual(manifest["source"], "bench@1a2b3c4")
        self.assertEqual([line["subject"] for line in lines], ["row-0001", "row-0002", "row-0003"])
        for line in lines:
            self.assertEqual((line["ruled_by"], line["evidence"][0]), ("tester", "grader: rubric v3, prompt v7"))
            self.assertIsNotNone(line["ruled_at"])
        # Human against judge, joined by row id in one line each: what a kappa counts.
        pairs = [(line["label"], line["key"]["judge"]) for line in lines]
        self.assertEqual(sum(human == judge for human, judge in pairs), 2)

    def test_a_regrade_files_a_new_batch_and_the_old_labels_still_export(self):
        first_key = b"row_id,judge\nrow-0001,rubric_correct\nrow-0002,both_wrong\nrow-0003,rubric_correct\n"
        first = self.file(self.conflicts("matrix-0001", "bench@1a2b3c4", first_key))
        for index in range(3):
            self.rule(first, index, "rubric_correct")
        review.export(self.db, first, key=first_key, who="tester")
        second = self.file(self.conflicts("matrix-0002", "bench@5d6e7f8", b"row_id,judge\nrow-0001,keyword_correct\n"))
        self.assertNotEqual(first, second)
        # The regrade deletes nothing: the first batch's labels export unchanged.
        self.assertEqual([line["label"] for line in review.export(self.db, first, who="tester")[1:]],
                         ["rubric_correct"] * 3)
        self.assertEqual(review.read(self.db, second)["open"], 3)


class TheVerb(unittest.TestCase):
    """`bin/sd-db review` through the entrypoint, on a store under a temporary home."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / ".local/share/sd").mkdir(parents=True)
        self.sd_db("init")

    def sd_db(self, *args, expect=0):
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("PYTHONPATH", "XDG_STATE_HOME")}
        done = subprocess.run(support.sd_db_argv(*args), capture_output=True, text=True, input="",
                              env={**environment, "HOME": str(self.home), "PYTHONPATH": str(support.LIB)})
        self.assertEqual(done.returncode, expect, done.stdout + done.stderr)
        return done

    def store(self):
        connection = sqlite3.connect(self.home / ".local/share/sd/sd.db")
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        return connection

    def write(self, name: str, found) -> Path:
        path = self.home / name
        path.write_text(found if isinstance(found, str) else json.dumps(found), encoding="utf-8")
        return path

    def test_file_then_export_then_apply(self):
        filed = self.sd_db("review", "file", str(self.write("batch.json", sealed())))
        self.assertIn("filed sd:", filed.stdout)
        again = self.sd_db("review", "file", str(self.write("batch.json", sealed())))
        self.assertIn("unchanged", again.stdout)
        item = self.store().execute("SELECT id FROM item WHERE external_id = 'review:jev-entry-2:C1'").fetchone()[0]
        out = self.home / "labels.jsonl"
        self.sd_db("review", "export", str(item), "--out", str(out))
        self.assertEqual(json.loads(out.read_text().splitlines()[0])["open"], 2)
        refused = self.sd_db("review", "export", str(item), "--key", str(self.write("key.csv", KEY_A.decode())),
                             "--out", str(out), expect=1)
        self.assertIn("2 questions", refused.stderr)
        self.assertIn("nothing to apply", self.sd_db("review", "apply", "nightly").stdout)

    def test_an_export_that_cannot_write_exits_1_and_the_rerun_writes(self):
        self.sd_db("review", "file", str(self.write("batch.json", sealed())))
        item = self.store().execute("SELECT id FROM item WHERE external_id = 'review:jev-entry-2:C1'").fetchone()[0]
        connection = connect(self.home / ".local/share/sd/sd.db")
        self.addCleanup(connection.close)
        for index, option in ((0, "cheap"), (1, "deep")):
            note = review.read(connection, item)["questions"][index]["note"]
            revision = workflow.item_state(connection, item)["revision"]
            review.rule(connection, item, note, option, expected_revision=revision, who="tester")
        key = str(self.write("key.csv", KEY_A.decode()))
        missing = self.home / "absent" / "labels.jsonl"
        refused = self.sd_db("review", "export", str(item), "--key", key, "--out", str(missing), expect=1)
        self.assertIn("is closed, and the same command writes it again", refused.stderr)
        out = self.home / "labels.jsonl"
        self.sd_db("review", "export", str(item), "--key", key, "--out", str(out))
        self.assertEqual(json.loads(out.read_text().splitlines()[1])["key"]["tier"], "cheap")

    def test_invalid_json_refuses_and_files_nothing(self):
        refused = self.sd_db("review", "file", str(self.write("batch.json", '{"schema": 1, "queue": ')), expect=1)
        self.assertIn("not JSON", refused.stderr)
        self.assertEqual(self.store().execute("SELECT count(*) FROM item").fetchone()[0], 0)

    def test_a_bad_call_prints_the_usage_and_exits_1(self):
        for argv in (["review"], ["review", "file"], ["review", "export", "x", "--out", "y"],
                     ["review", "export", "1"], ["review", "apply"], ["review", "undo", "1"]):
            with self.subTest(argv=argv):
                self.assertIn("sd-db review", self.sd_db(*argv, expect=1).stderr)


if __name__ == "__main__":
    unittest.main()
