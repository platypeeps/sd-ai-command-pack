"""The real CLI operates on a scratch database, without repository ceremony."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sd_db
from sd_db.workflow import NOTE_KINDS

ROOT = Path(__file__).resolve().parents[1]


class TaskCLI(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name)
        sd_db.initialise(home=self.home)
        self.environment = {**os.environ, "HOME": str(self.home)}

    def call(self, *arguments, code=0):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "sd"), *map(str, arguments)],
            cwd=self.home, env=self.environment, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_task_lifecycle_outside_checkout_and_stale_edit(self):
        state = json.loads(self.call("task", "add", "Check the workflow", "--json").stdout)
        item = state["item"]["id"]
        edited = json.loads(self.call(
            "task", "edit", item, "--priority", 1, "--due", "2026-09-08",
            "--if-revision", state["revision"], "--json").stdout)
        refused = self.call("task", "status", item, "done", "--if-revision",
                            state["revision"], code=1)
        self.assertIn("changed", refused.stderr)
        readback = json.loads(self.call("store", "item", item, "--json").stdout)
        self.assertEqual(readback, edited)
        noted = json.loads(self.call("task", "note", item, "--body", "Verify on iPad",
                                     "--json").stdout)
        resolved = json.loads(self.call("task", "resolve", noted["note"]["id"],
                                        "--json").stdout)
        self.assertTrue(resolved["note"]["resolved_at"])
        completed = json.loads(self.call("task", "status", item, "done", "--json").stdout)
        self.assertEqual(completed["item"]["status"], "done")
        self.assertEqual(json.loads(self.call("store", "items", "--open", "--json").stdout), [])
        self.assertFalse((self.home / "docs").exists())
        self.assertFalse((self.home / ".git").exists())

    def test_cli_and_today_query_agree(self):
        for title in ("One", "Two"):
            state = json.loads(self.call("task", "add", title, "--json").stdout)
            self.call("task", "status", state["item"]["id"], "in_progress")
        with sd_db.connect(sd_db.default_path(self.home), write=False) as connection:
            expected = [dict(row) for row in sd_db.reads.today_items(connection)]
        self.assertEqual(json.loads(self.call("today", "--json").stdout), expected)

    def test_note_defaults_to_comment_without_creating_a_followup(self):
        state = json.loads(self.call("task", "add", "Parent task", "--json").stdout)
        item = state["item"]["id"]
        result = json.loads(self.call("task", "note", item, "--body", "A useful observation",
                                      "--json").stdout)
        self.assertEqual(result["note"]["kind"], "comment")
        self.assertEqual((result["item"]["kind"], result["item"]["status"]), ("task", "planning"))
        readback = json.loads(self.call("store", "item", item, "--json").stdout)
        self.assertEqual(readback["notes"], result["notes"])
        with sd_db.connect(sd_db.default_path(self.home), write=False) as connection:
            self.assertEqual(sd_db.reads.open_followups(connection), [])

    def test_all_public_note_kinds_parse_and_persist_without_internal_kinds(self):
        self.assertEqual(set(NOTE_KINDS), {"comment", "followup", "question", "decision", "proposal"})
        state = json.loads(self.call("task", "add", "Parent task", "--json").stdout)
        item = state["item"]["id"]
        initial_notes = state["notes"]
        initial_ids = {note["id"] for note in initial_notes}
        for kind in NOTE_KINDS:
            with self.subTest(kind=kind):
                state = json.loads(self.call("task", "note", item, "--kind", kind,
                    "--body", f"Recorded {kind}", "--if-revision", state["revision"], "--json").stdout)
                self.assertEqual(state["note"]["kind"], kind)
                self.assertEqual(state["note"]["body"], f"Recorded {kind}")
        before = json.loads(self.call("store", "item", item, "--json").stdout)
        self.assertEqual([note["kind"] for note in before["notes"] if note["id"] not in initial_ids], list(NOTE_KINDS))
        self.assertEqual([note for note in before["notes"] if note["id"] in initial_ids], initial_notes)
        self.call("task", "note", item, "--body", "Forged history", "--kind", "status_change", code=2)
        self.assertEqual(json.loads(self.call("store", "item", item, "--json").stdout), before)
        help_text = self.call("task", "note", "--help").stdout
        self.assertIn("{" + ",".join(NOTE_KINDS) + "}", help_text)
        self.assertIn("default: comment", help_text)

    def test_task_add_remains_task_only(self):
        state = json.loads(self.call("task", "add", "Standalone work", "--json").stdout)
        self.assertEqual(state["item"]["kind"], "task")
        self.call("task", "add", "Not another task", "--kind", "proposal", code=2)
        rows = json.loads(self.call("store", "items", "--json").stdout)
        self.assertEqual([row["id"] for row in rows], [state["item"]["id"]])

    def test_refusals_and_usage_have_distinct_exit_codes(self):
        self.assertIn("no item", self.call("store", "item", 9999, code=1).stderr)
        self.call("task", "add", "Task", "--priority", 9, code=2)
        self.assertIn("Git checkout", self.call("task", "add", "Task", "--here", code=1).stderr)
        self.call("task", "add", "Task", "--due", "tomorrow", code=1)


if __name__ == "__main__":
    unittest.main()
