"""`sd_db.today`: the sections `sd today`, `sd-status` and the dashboard show (sd:5098)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sd_db import (
    connect,
    create_assignment,
    create_item,
    reads,
    review,
    today,
    upsert_repo,
    workflow,
)
from sd_db.migrate import initialise
from sd_db.writes import add_note, transition

#: A fixed instant, so windows and estimates do not depend on when the suite runs.
NOW = "2026-09-06T12:00:00Z"
WHEN = "2026-09-04T09:00:00+00:00"
APP = "~/repos/example.test/app"
LIB = "~/repos/example.test/lib"


class TodayCase(unittest.TestCase):
    SHA = "a" * 40
    OTHER = "b" * 40

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "sd.db"
        initialise(path)
        self.connection = connect(path)
        self.addCleanup(self.connection.close)
        upsert_repo(self.connection, APP, remote="https://github.com/example-owner/app")
        upsert_repo(self.connection, LIB, remote="git@github.com:example-owner/lib.git")

    def item(self, title, **fields):
        return create_item(self.connection, kind=fields.pop("kind", "task"), title=title, **fields)

    def lane(self, repository, entry, **body):
        self.connection.execute(
            "INSERT INTO state(kind, key, timestamp, body) VALUES ('checkpoint', ?, ?, ?)",
            (f"{today.LANE_KEY_PREFIX}{repository}:{entry}", WHEN, json.dumps({"id": entry, **body})))


class TheSections(TodayCase):
    def test_delivered_names_the_pr_and_merge_commit_of_the_last_day(self):
        shipped = self.item("Shipped", status="in_progress")
        transition(self.connection, shipped, "done", who="sd-ship", reason=f"delivered at {self.SHA} on origin/main")
        add_note(self.connection, shipped, "comment", f"Code delivery https://github.com/o/r/pull/7 at {self.SHA}")
        old = self.item("Old", status="in_progress")
        transition(self.connection, old, "done", who="sd-ship", reason=f"delivered at {self.OTHER} on origin/main")
        self.connection.execute("UPDATE note SET timestamp = '2020-01-01T00:00:00+00:00' WHERE item = ?", (old,))
        merged = self.item("Merged, still open")
        add_note(self.connection, merged, "comment", f"Code delivery https://github.com/o/r/pull/9 at {self.OTHER}")
        by_hand = self.item("Closed by hand", status="in_progress")
        transition(self.connection, by_hand, "done", who="operator", reason="test")
        self.assertEqual([(row["id"], row["pr"], row["commit"]) for row in today.delivered(self.connection)],
                         [(merged, 9, self.OTHER), (shipped, 7, self.SHA)])
        # A hand close is a count, not a row: a bulk close would fill the table.
        self.assertEqual([row["id"] for row in today.closed_by_hand(self.connection)], [by_hand])
        found = today.sections(self.connection)
        self.assertEqual((found["summary"]["delivered"], found["summary"]["closed_by_hand"]), (2, 1))

    def test_landing_is_each_items_newest_live_entry_with_its_place(self):
        first, second, third, finished, failed, delivered = (
            self.item(title) for title in ("First", "Second", "Third", "Finished", "Failed", "Delivered"))
        transition(self.connection, delivered, "done", who="operator", reason="test")
        self.lane("o/r", "e0", item=first, status="failed", position=1)
        self.lane("o/r", "e1", item=first, status="running", position=5, step="prepare")
        self.lane("o/r", "e2", item=third, status="pending", position=7)
        self.lane("o/r", "e3", item=second, status="pending", position=6)
        self.lane("o/r", "e4", item=finished, status="merged", position=2)
        self.lane("o/s", "e5", item=failed, status="failed", position=3, step="prepare")
        self.lane("o/s", "e6", item=delivered, status="failed", position=4)
        self.lane("o/s", "e7", item=second, status="cancelled", position=8)
        found = today.landing(self.connection)
        self.assertEqual([(row["id"], row["repository"], row["status"], row["place"]) for row in found["entries"]],
                         [(first, "o/r", "running", 1), (second, "o/r", "pending", 2), (third, "o/r", "pending", 3),
                          (failed, "o/s", "failed", None)])
        self.assertIsNone(found["gate"])

    def test_landing_gives_exact_times_and_no_estimate(self):
        """The lane records no ETA: `since` is when the entry started, else when the hub queued it."""
        running, waiting = self.item("Running", repo=APP), self.item("Waiting", repo=APP)
        self.lane("example-owner/app", "r", item=running, status="running", position=10,
                  started_at="2026-09-06T11:55:00Z")
        self.lane("example-owner/app", "w", item=waiting, status="pending", position=11)
        entries = today.landing(self.connection)["entries"]
        self.assertEqual([(row["place"], row["since"], row["repo"]) for row in entries],
                         [(1, "2026-09-06T11:55:00Z", APP), (2, WHEN, APP)])
        self.assertNotIn("eta", entries[0])

    def test_landing_carries_the_gate_or_why_it_is_unknown(self):
        snapshot = {"holders": [{"slot": 1, "pid": 7, "label": "tests", "since": WHEN, "cwd": "/tmp"}],
                    "waiters": [{"place": 1, "pid": 8, "label": "lane", "since": WHEN, "cwd": "/tmp"}]}
        self.assertEqual(today.landing(self.connection, gate=snapshot)["gate"],
                         {"holders": [{"slot": 1, "label": "tests", "since": WHEN}],
                          "waiters": [{"place": 1, "label": "lane", "since": WHEN}], "error": None})
        self.assertEqual(today.landing(self.connection, gate="permission denied")["gate"]["error"], "permission denied")

    def test_planned_is_open_items_due_after_today_soonest_first(self):
        later = self.item("Later", due="2026-09-30")
        sooner = self.item("Sooner", due="2026-09-07")
        self.item("Due today, so in Work", due="2026-09-06")
        self.item("Done", due="2026-09-08", status="done")
        self.item("Undated")
        self.assertEqual([row["id"] for row in today.planned(self.connection, now=NOW)], [sooner, later])

    def test_unscheduled_leaves_out_dated_laned_assigned_blocked_and_idea_items(self):
        low = self.item("Low", priority=3)
        high = self.item("High", priority=1)
        unranked = self.item("Unranked")
        self.item("Dated", due="2026-12-01")
        laned = self.item("Laned")
        self.lane("o/r", "e1", item=laned, status="pending", position=1)
        assigned = self.item("Assigned")
        create_assignment(self.connection, role="builder", status="running", item=assigned)
        finished = self.item("Assignment ended")
        create_assignment(self.connection, role="builder", status="done", item=finished)
        self.item("Blocked", status="blocked")
        self.item("An idea", kind="idea")
        self.item("Done", status="done")
        self.assertEqual([row["id"] for row in today.unscheduled(self.connection)], [high, low, unranked, finished])

    def test_blocked_says_why_from_the_status_change_or_a_waiting_note(self):
        vendor = self.item("Vendor")
        transition(self.connection, vendor, "blocked", who="operator", reason="Waits on the vendor\nmore detail")
        bare = self.item("Bare", status="blocked")
        waiting = self.item("Waiting")
        add_note(self.connection, waiting, "comment", "Waiting on Alex for the keys")
        chatty = self.item("Chatty")
        add_note(self.connection, chatty, "comment", "Waiting on Alex was yesterday")
        add_note(self.connection, chatty, "comment", "Alex answered")
        self.assertEqual([(row["id"], row["why"]) for row in today.blocked(self.connection)],
                         [(vendor, "Waits on the vendor"), (bare, ""), (waiting, "Waiting on Alex for the keys")])

    def test_decisions_and_followups_leave_out_plain_questions_and_reports_own(self):
        asked = self.item("Asked")
        decision = add_note(self.connection, asked, "question", "Which store?\nOption: Pack\nOption: Rows")
        add_note(self.connection, asked, "question", "A plain question")
        chase = add_note(self.connection, asked, "followup", "Chase the vendor")
        report = self.item("Report", kind="report", fields={"attention": "two stale rows"})
        add_note(self.connection, report, "followup", "The report's own")
        self.assertEqual([(row["id"], row["note"], row["title"]) for row in today.decisions(self.connection)],
                         [(asked, decision, "Which store?")])
        self.assertEqual([(row["id"], row["note"]) for row in today.followups(self.connection)], [(asked, chase)])
        self.assertEqual([(row["id"], row["why"]) for row in today.attention(self.connection)],
                         [(report, "two stale rows")])

    def test_closing_an_item_keeps_its_unanswered_question_in_decisions(self):
        """Pack sd:6329: a close answers no question; the followups it owed go."""
        asked = self.item("Asked")
        decision = add_note(self.connection, asked, "question", "Move all 45?\nOption: Approve all\nOption: Videos only")
        add_note(self.connection, asked, "followup", "Chase the vendor")
        workflow.change_status(self.connection, asked, "done", who="operator", reason="landed")
        self.assertEqual([(row["id"], row["note"], row["status"]) for row in today.decisions(self.connection)],
                         [(asked, decision, "done")])
        self.assertEqual(today.followups(self.connection), [])

    def batch(self, name, questions=1, repo=APP):
        """A review batch filed by the review store itself, so the marker is the one it writes."""
        return review.file(self.connection, {
            "schema": 1, "queue": "labels", "batch": name, "title": f"Label {name}", "repo": repo,
            "source": "example.test@1a2b3c4", "mode": "open",
            "questions": [{"subject": f"example.test/{name}/{number}", "text": "Which tier fits?",
                           "options": ["cheap", "deep"]} for number in range(questions)]}, who="tester")["item"]

    def test_decisions_leave_review_batch_questions_to_the_review_page_as_a_count(self):
        """sd:5130: `sd-next` walks the Decisions rows; a batch's questions wait on the Review page."""
        batch = self.batch("B1", questions=2)
        asked = self.item("Asked")
        decision = add_note(self.connection, asked, "question", "Which store?\nOption: Pack\nOption: Rows")
        # Older state: a ref task that is no batch, and an approval's task, keep their questions as rows.
        bare = self.item("Bare ref", source="task-ref")
        unbatched = add_note(self.connection, bare, "question", "Keep it?\nOption: Yes\nOption: No")
        approved = self.item("Approved", source="task-ref", external_id="review-approved:1")
        followed = add_note(self.connection, approved, "question", "Ship it?\nOption: Yes\nOption: No")
        self.assertEqual([row["note"] for row in today.decisions(self.connection)], [decision, unbatched, followed])
        self.assertEqual(today.review_questions(self.connection), 2)
        self.assertEqual(today.sections(self.connection, now=NOW)["summary"]["review_questions"], 2)
        self.assertEqual(today.review_questions(self.connection, repos=[LIB]), 0)
        # A label resolves the question, so the count falls; the batch never becomes a row.
        state = review.read(self.connection, batch)
        review.rule(self.connection, batch, state["questions"][0]["note"], "deep",
                    expected_revision=workflow.item_state(self.connection, batch)["revision"], who="tester")
        self.assertEqual(today.review_questions(self.connection), 1)
        self.assertNotIn(batch, [row["id"] for row in today.decisions(self.connection)])

    def test_a_batch_larger_than_the_note_limit_leaves_the_decisions_whole(self):
        """The batch is left out in the query: 250 older batch questions do not fill `open_notes`' 200."""
        self.batch("Big", questions=250)
        asked = self.item("Asked")
        decision = add_note(self.connection, asked, "question", "Which store?\nOption: Pack\nOption: Rows")
        self.assertEqual([row["note"] for row in today.decisions(self.connection)], [decision])
        self.assertEqual(today.review_questions(self.connection), 250)

    def test_the_batch_marker_is_the_one_the_review_store_files(self):
        self.assertIn(f"item.source IS '{review.REF_SOURCE}'", reads.REVIEW_BATCH)
        self.assertIn("substr(item.external_id, 1, 7) IS 'review:'", reads.REVIEW_BATCH)

    def grill(self, ref="grill:2026-09-07", repo=APP, questions=2):
        """A weekly grill as the KISS audit files it: `sd task add --ref grill:<date>`, then question notes."""
        item = self.item("Weekly grill", repo=repo, source="task-ref", external_id=ref)
        return item, [add_note(self.connection, item, "question", f"Keep mechanism {n}?\nOption: Keep\nOption: Drop")
                      for n in range(questions)]

    def test_a_grills_questions_are_one_ready_line_not_decisions(self):
        """pack sd:6022: the audit's seed questions wait for the operator to say 'grill', not in every walk."""
        grilled, (first, _) = self.grill()
        asked = self.item("Asked")
        decision = add_note(self.connection, asked, "question", "Which store?\nOption: Pack\nOption: Rows")
        # Older state: a ref task under another prefix keeps its questions as Decisions rows.
        other = self.item("Other ref", source="task-ref", external_id="grilled:1")
        kept = add_note(self.connection, other, "question", "Keep it?\nOption: Yes\nOption: No")
        self.assertEqual([row["note"] for row in today.decisions(self.connection)], [decision, kept])
        self.assertEqual([(row["id"], row["questions"]) for row in today.grill(self.connection)], [(grilled, 2)])
        found = today.sections(self.connection, now=NOW)
        self.assertEqual((found["summary"]["grill"], [row["id"] for row in found["grill"]]), (2, [grilled]))
        self.assertEqual(today.grill(self.connection, repos=[LIB]), [])
        # A ruling resolves a question, so the count falls; the last one ends the line.
        workflow.resolve_item_note(self.connection, first, who="tester")
        self.assertEqual([row["questions"] for row in today.grill(self.connection)], [1])
        transition(self.connection, grilled, "done", who="operator", reason="test")
        self.assertEqual(today.grill(self.connection), [])

    def test_a_grill_with_no_open_question_is_not_ready(self):
        self.grill(questions=0)
        self.assertEqual(today.grill(self.connection), [])
        self.assertEqual(today.sections(self.connection, now=NOW)["summary"]["grill"], 0)

    def test_sections_come_in_one_order_with_their_counts(self):
        self.item("Soon", due="2026-09-08")
        self.item("Later", due="2026-10-30")
        found = today.sections(self.connection, now=NOW)
        self.assertEqual(list(found), ["summary", *today.ORDER, "closed_by_hand", "grill"])
        self.assertEqual((found["summary"]["planned"], found["summary"]["planned_this_week"]), (2, 1))

    def test_the_active_assignment_states_match_the_workflow(self):
        self.assertEqual(today.ACTIVE_ASSIGNMENTS, workflow.ACTIVE_ASSIGNMENTS)


class TheOperations(TodayCase):
    """pack sd:5432: the open report lines that name this machine, every repository's, and the gate."""

    def report(self, job, basis, *, repo=None, **fields):
        return self.item(f"{job}: needs attention", kind="report", repo=repo, source="cron-report",
                         external_id=f"{job}:20261020T101505Z-1",
                         fields={"attention": fields.pop("attention", True), "report": {"attention_basis": basis},
                                 **fields})

    def test_only_the_lines_naming_the_host_are_rows_and_the_gate_rides_along(self):
        health = self.report("health-check-nightly", "\n".join((
            "health check on alpha: launchd: com.example.test.job reports a failed run",
            "health check on beta: disk: under 10% free",
            "health check on alphabet: not this machine")), repo=APP)
        store = self.report("maintenance-nightly", "\n".join((
            "maintenance on alpha: App Store updates pending:",
            "maintenance on alpha: App Store updates pending: 1 Example (1.0 -> 1.1)")), repo=LIB)
        exited = self.report("secret-scan-weekly", "job exited 2 on alpha")
        folded = self.report("brew-doctor-nightly", "brew doctor on alpha: first set",
                             repeats={"basis": "brew doctor on alpha: current set"})
        self.report("quiet-nightly", "quiet on alpha: x", attention=False)
        transition(self.connection, self.report("done-nightly", "done on alpha: x"), "done", who="operator",
                   reason="acknowledged")
        unread = self.report("broken-nightly", "broken on beta: x")
        self.connection.execute("UPDATE item SET fields = 'not json' WHERE id = ?", (unread,))
        self.item("No basis", kind="report", fields={"attention": "look"})
        snapshot = {"slots": 2, "load": [1.5, 1.0, 0.5], "load_max": 40.0,
                    "holders": [{"slot": 1, "pid": 7, "label": "tests", "since": WHEN, "cwd": "/tmp"}], "waiters": []}
        found = today.operations(self.connection, host="alpha", gate=snapshot)
        self.assertEqual(sorted((row["id"], row["job"], row["finding"]) for row in found["findings"]), sorted([
            (health, "health-check-nightly", "launchd: com.example.test.job reports a failed run"),
            (store, "maintenance-nightly", "App Store updates pending: 1 Example (1.0 -> 1.1)"),
            (exited, "secret-scan-weekly", "job exited 2"),
            (folded, "brew-doctor-nightly", "current set"),
            (unread, "broken-nightly", today.FIELDS_UNREAD),
        ]))
        self.assertEqual(found["gate"], {"holders": [{"slot": 1, "label": "tests", "since": WHEN}], "waiters": [],
                                         "error": None, "slots": 2, "load": [1.5, 1.0, 0.5], "load_max": 40.0})
        self.assertEqual(today.operations(self.connection, host="beta", gate="slots unreadable")["gate"],
                         {"holders": [], "waiters": [], "error": "slots unreadable"})
        # A machine belongs to no repository: the repository filter leaves the section whole.
        with mock.patch.object(today, "this_host", return_value="alpha"):
            mine = today.sections(self.connection, repos=[LIB], now=NOW, gate=snapshot)
        self.assertEqual(mine["operations"], {**found, "host": "alpha"})
        self.assertEqual(mine["summary"]["operations"], 5)


class TheRepositoryFilter(TodayCase):
    """sd:5098: `sd-status` reads the same sections for its own repository and its companions."""

    def test_every_section_keeps_only_the_named_repositories(self):
        mine, theirs, loose = self.item("Mine", repo=APP), self.item("Theirs", repo=LIB), self.item("Loose")
        for item in (mine, theirs, loose):
            add_note(self.connection, item, "followup", f"Chase {item}")
            add_note(self.connection, item, "question", f"Pick {item}\nOption: A\nOption: B")
        self.lane("example-owner/app", "a", item=mine, status="pending", position=1)
        self.lane("example-owner/lib", "b", item=theirs, status="pending", position=2)
        planned = [self.item(f"Due {repo}", repo=repo, due="2026-09-09") for repo in (APP, LIB)]
        stuck = [self.item(f"Stuck {repo}", repo=repo, status="blocked") for repo in (APP, LIB)]
        free = [self.item(f"Free {repo}", repo=repo) for repo in (APP, LIB)]
        found = today.sections(self.connection, repos=[APP], now=NOW)
        self.assertEqual([row["id"] for row in found["followups"]], [mine])
        self.assertEqual([row["id"] for row in found["decisions"]], [mine])
        self.assertEqual([(row["id"], row["repo"]) for row in found["landing"]["entries"]], [(mine, APP)])
        self.assertEqual([row["id"] for row in found["planned"]], [planned[0]])
        self.assertEqual([row["id"] for row in found["blocked"]], [stuck[0]])
        self.assertEqual([row["id"] for row in found["unscheduled"]], [free[0]])
        both = today.sections(self.connection, repos=[APP, LIB], now=NOW)
        self.assertEqual({row["repo"] for row in both["unscheduled"]}, {APP, LIB})
        self.assertEqual(len(today.sections(self.connection, now=NOW)["followups"]), 3)

    def test_delivered_and_attention_follow_the_filter(self):
        for repo in (APP, LIB):
            shipped = self.item(f"Shipped {repo}", repo=repo, status="in_progress")
            transition(self.connection, shipped, "done", who="sd-ship", reason=f"delivered at {self.SHA} on origin/main")
            self.item(f"Report {repo}", repo=repo, kind="report", fields={"attention": "look"})
        self.assertEqual([row["repo"] for row in today.delivered(self.connection, repos=[LIB])], [LIB])
        self.assertEqual([row["repo"] for row in today.attention(self.connection, repos=[LIB])], [LIB])


if __name__ == "__main__":
    unittest.main()
