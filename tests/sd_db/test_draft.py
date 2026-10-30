"""Draft runs: the queue, the claim, the parser, the one write and the reap (pack sd:6361).

The design's failure table names most of these tests: system
`docs/work/2026-10-25-lead-drafts-specs/design.md`. The supervisor's
tests, with a fake `claude`, are `Drafts` in `test_build_run.py`; the
capture route's are in the dashboard's `test_capture_actions.py`.
"""
import tempfile
import threading
import unittest
from pathlib import Path

from sd_db import build, draft, recovery
from sd_db.database import connect
from sd_db.migrate import initialise
from sd_db.writes import create_item, record_state, transition, upsert_repo

from .test_build import Kill, Probe, later

A = "/fixture/a"
ROOM = {"machine": build.MACHINE_CAP, "used": {}, "held": [], "why": ""}
REPLY = """## Spec

Problem: the capture box files one line.
Approach: draft a spec headless.
Acceptance criteria:
- `make test` passes with 0 failures.
Risks: a weak draft.

## Questions

Which store holds drafts?
Option: Notes on the item (Recommended)
Option: A new table

Who marks it ready?
Option: The operator (Recommended)
Option: The lead
"""


def parsed(text=REPLY):
    found = draft.parse(text)
    assert found is not None
    return found


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / "sd.db"
        initialise(self.database)
        self.db = connect(self.database)
        self.addCleanup(self.db.close)
        upsert_repo(self.db, A, remote="/fixture/remote-a", managed=1)

    def item(self, repo=A, status="planning", kind="task"):
        return create_item(self.db, kind=kind, title="Draft me", repo=repo, status=status)

    def queued(self, repo=A):
        item = self.item(repo=repo)
        assignment = draft.queue_if_eligible(self.db, item, who="dashboard")
        assert assignment is not None
        return item, assignment

    def claim(self, db=None, available=None):
        return draft.claim(db or self.db, owner="fixture", available=available or ROOM)

    def count(self, sql, *args):
        return self.db.execute(sql, args).fetchone()[0]

    def notes(self, item):
        return [dict(row) for row in self.db.execute("SELECT * FROM note WHERE item = ? ORDER BY id", (item,))]

    def status(self, item):
        return self.db.execute("SELECT status FROM item WHERE id = ?", (item,)).fetchone()["status"]


class Queue(Case):
    def test_a_capture_in_a_managed_hub_repo_queues_one_draft(self):
        item, assignment = self.queued()
        row = self.db.execute("SELECT * FROM assignment WHERE id = ?", (assignment,)).fetchone()
        self.assertEqual((row["item"], row["status"], row["scope"], row["role"], row["budget_minutes"]),
                         (item, "queued", "draft", "author", 15))
        self.assertIn(f"Draft assignment {assignment} queued by dashboard", self.notes(item)[-1]["body"])

    def test_an_ineligible_item_queues_nothing(self):
        """The repository rule is `build._repo_refusal` as it is: managed, a remote, a hub lane."""
        upsert_repo(self.db, "/fixture/off", remote="/fixture/r-off", managed=0)
        upsert_repo(self.db, "/fixture/none", managed=1)
        upsert_repo(self.db, "/fixture/sat", remote="/fixture/r-sat", managed=1)
        self.db.execute("UPDATE repo SET lane_host = 'work' WHERE path = '/fixture/sat'")
        cases = {"unmanaged": self.item(repo="/fixture/off"), "no remote": self.item(repo="/fixture/none"),
                 "satellite lane": self.item(repo="/fixture/sat"), "no repo": self.item(repo=None),
                 "followup": self.item(kind="followup"), "personal": self.item(kind="personal", repo=None),
                 "ready": self.item(status="ready")}
        for case, item in cases.items():
            with self.subTest(case=case):
                self.assertIsNone(draft.queue_if_eligible(self.db, item, who="dashboard"))
        self.assertEqual(self.count("SELECT COUNT(*) FROM assignment"), 0)

    def test_a_restore_reimport_queues_and_claims_nothing(self):
        queued, _ = self.queued()
        record_state(self.db, "restore", key="fixture", body={})
        self.assertIsNone(draft.queue_if_eligible(self.db, self.item(), who="dashboard"))
        self.assertIsNone(self.claim())
        self.assertEqual(self.count("SELECT COUNT(*) FROM assignment"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 0)
        self.assertEqual(self.status(queued), "planning")


class Claim(Case):
    def test_one_draft_runs_at_a_time(self):
        """Failure table, Claim: a second claim, on another connection or racing, finds the first run and takes none."""
        first, _ = self.queued()
        second, _ = self.queued()
        answers: list = []

        def race():
            # A connection serves only the thread that opened it.
            db = connect(self.database)
            try:
                answers.append(self.claim(db))
            finally:
                db.close()

        threads = [threading.Thread(target=race) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        taken = [answer for answer in answers if answer is not None]
        self.assertEqual(len(taken), 1)
        run = taken[0]
        self.assertEqual((run["step"], run["branch"], run["model"], run["work_path"]),
                         ("claimed", f"draft/sd-{first}", "opus", A))
        self.assertIsNone(self.claim())
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease"), 0, "a draft holds no lease")
        self.assertEqual([self.status(item) for item in (first, second)], ["planning", "planning"])

    def test_no_room_claims_nothing(self):
        self.queued()
        self.assertIsNone(self.claim(available={**ROOM, "machine": 0}))
        self.assertIsNone(self.claim(available={**ROOM, "machine": 0, "why": "the load was not read"}))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 0)

    def test_a_moved_item_ends_its_draft_cancelled(self):
        moved, assignment = self.queued()
        transition(self.db, moved, "ready", who="operator")
        later_item, _ = self.queued()
        run = self.claim()
        self.assertEqual(self.db.execute("SELECT item FROM assignment WHERE id = ?",
                                         (run["assignment"],)).fetchone()[0], later_item)
        row = self.db.execute("SELECT status, result FROM assignment WHERE id = ?", (assignment,)).fetchone()
        self.assertEqual(row["status"], "cancelled")
        self.assertIn("moved to ready", row["result"])

    def test_a_draft_counts_against_the_machine_cap_only(self):
        """A draft holds no branch: it takes one machine slot, no repository slot."""
        self.queued()
        run = self.claim()
        room = build.room(self.db, load=1.0, load_cap=40.0, interactive=[])
        self.assertEqual((room["machine"], room["used"]), (build.MACHINE_CAP - 1, {}))
        self.assertEqual(build.room_for(room, A), build.REPO_CAP)
        build.write(self.db, run["id"], session_id="draft-session")
        interactive = [{"repo": None, "session_id": "draft-session"}] + [{"repo": None, "session_id": f"s{n}"}
                                                                          for n in range(build.MACHINE_CAP - 1)]
        full = build.room(self.db, load=1.0, load_cap=40.0, interactive=interactive)
        self.assertEqual(full["machine"], 0, "the draft's own session is counted once")


class Parse(unittest.TestCase):
    def test_a_reply_parses_to_its_spec_and_questions(self):
        spec, questions = parsed()
        self.assertTrue(spec.startswith("Problem: the capture box"))
        self.assertNotIn("## Questions", spec)
        self.assertEqual(questions, ["Which store holds drafts?\nOption: Notes on the item (Recommended)\n"
                                     "Option: A new table",
                                     "Who marks it ready?\nOption: The operator (Recommended)\nOption: The lead"])
        self.assertEqual(draft.parse("## Spec\n\nJust the spec."), ("Just the spec.", []))
        self.assertEqual(draft.parse("## Spec\n\nJust the spec.\n\n## Questions\n\nNone.\n"), ("Just the spec.", []))

    def test_anything_else_is_no_draft(self):
        one_option = REPLY.replace("Option: A new table\n", "")
        four = REPLY + "".join(f"\nAsk {n}?\nOption: x\nOption: y\n" for n in range(2))
        cases = {"no spec": "Problem: x", "text first": "Sure, here it is.\n" + REPLY, "empty spec": "## Spec\n\n",
                 "questions first": "## Questions\n\nA?\nOption: x\nOption: y\n## Spec\n\ny",
                 "spec twice": REPLY + "\n## Spec\n\nagain", "one option": one_option, "four questions": four,
                 "an option alone": "## Spec\n\nx\n\n## Questions\n\nOption: x\nOption: y",
                 "a repeated option": "## Spec\n\nx\n\n## Questions\n\nA?\nOption: x\nOption: x",
                 "a blank option": "## Spec\n\nx\n\n## Questions\n\nA?\nOption: x\nOption:",
                 "no pick (pack sd:6708)": "## Spec\n\nx\n\n## Questions\n\nA?\nOption: x\nOption: y",
                 "no text": "", "not text": None}
        for case, reply in cases.items():
            with self.subTest(case=case):
                self.assertIsNone(draft.parse(reply))


class Write(Case):
    def running(self):
        item, assignment = self.queued()
        return item, assignment, self.claim()

    def test_a_parsed_draft_writes_its_notes_in_one_transaction(self):
        item, assignment, run = self.running()
        spec, questions = parsed()
        self.assertTrue(draft.write(self.db, run["id"], spec, questions))
        notes = [note for note in self.notes(item) if note["session"] == f"draft:{run['id']}"]
        self.assertEqual([note["kind"] for note in notes], ["comment", "question", "question"])
        self.assertTrue(notes[0]["body"].startswith("Draft spec:\n\nProblem: the capture box"))
        row = build.run(self.db, run["id"])
        self.assertEqual((row["outcome"], row["released_at"] is not None), ("done", True))
        self.assertEqual(self.db.execute("SELECT status FROM assignment WHERE id = ?", (assignment,)).fetchone()[0],
                         "done")
        self.assertEqual(self.status(item), "planning")

    def test_a_late_draft_writes_nothing(self):
        """Failure table, Write: a reap ended the run, so the old supervisor's write names a released run."""
        item, assignment, run = self.running()
        reaped = draft.reap(self.db, now=later(run["created_at"], 600), probe=Probe(group=False), kill=Kill(self.db))
        self.assertEqual([(row["run"], row["outcome"]) for row in reaped], [(run["id"], "interrupted")])
        before = self.notes(item)
        self.assertFalse(draft.write(self.db, run["id"], *parsed()))
        self.assertEqual(self.notes(item), before)
        self.assertEqual(self.db.execute("SELECT status FROM assignment WHERE id = ?", (assignment,)).fetchone()[0],
                         "running", "the retry holds the assignment")

    def test_an_assignment_that_stopped_running_takes_no_draft(self):
        item, assignment, run = self.running()
        self.db.execute("UPDATE assignment SET status = 'blocked' WHERE id = ?", (assignment,))
        before = self.notes(item)
        self.assertFalse(draft.write(self.db, run["id"], *parsed()))
        self.assertEqual(self.notes(item), before)
        self.assertIsNone(build.run(self.db, run["id"])["outcome"], "the write rolled back whole")


class Reap(Case):
    def test_a_lost_draft_retries_once_then_blocks_with_a_followup(self):
        item, assignment = self.queued()
        run = self.claim()
        first = draft.reap(self.db, now=later(run["created_at"], 600), probe=Probe(group=False), kill=Kill(self.db))
        retry = first[0]["retry"]
        self.assertEqual((build.run(self.db, retry)["step"], build.run(self.db, retry)["run"]), ("claimed", 2))
        second = draft.reap(self.db, now=later(run["created_at"], 1200), probe=Probe(group=False), kill=Kill(self.db))
        self.assertEqual(second[0]["retry"], None)
        self.assertEqual(self.db.execute("SELECT status FROM assignment WHERE id = ?", (assignment,)).fetchone()[0],
                         "blocked")
        followups = [note["body"] for note in self.notes(item) if note["kind"] == "followup"]
        self.assertEqual(len(followups), 1)
        self.assertTrue(followups[0].startswith("Draft blocked: draft run"))
        self.assertEqual(self.status(item), "planning", "a blocked draft leaves the item planning")
        self.assertEqual(draft.open_runs(self.db), [])

    def test_a_build_reap_leaves_draft_runs_alone(self):
        self.queued()
        run = self.claim()
        self.assertEqual(build.reap(self.db, now=later(run["created_at"], 600), probe=Probe(group=False),
                                    kill=Kill(self.db)), [])
        self.assertIsNone(build.run(self.db, run["id"])["outcome"])

    def test_a_restore_abandons_a_draft_run(self):
        """Older state: a restore ends an open draft run unretried, as it does a build run."""
        item, _ = self.queued()
        run = self.claim()
        recovery.prepare_restore(self.db)
        row = build.run(self.db, run["id"])
        self.assertEqual((row["outcome"], row["released_at"]), ("abandoned", None))
        draft.reap(self.db, probe=Probe(alive=False, group=False), kill=Kill(self.db))
        self.assertIsNotNone(build.run(self.db, run["id"])["released_at"])
        self.assertEqual(draft.open_runs(self.db), [])
        self.assertEqual(self.status(item), "planning")


if __name__ == "__main__":
    unittest.main()
