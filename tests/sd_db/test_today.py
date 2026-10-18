"""`sd_db.today`: the sections `sd today`, `sd-status` and the dashboard show (sd:5098)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sd_db import connect, create_assignment, create_item, today, upsert_repo, workflow
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

    def test_landing_estimates_each_place_from_the_median_run_time(self):
        """The lane records no ETA; one median run per place after the running entry's start."""
        for number, minutes in enumerate((10, 20, 30)):
            self.lane("example-owner/app", f"m{number}", item=900 + number, status="merged", position=number,
                      started_at="2026-09-06T08:00:00Z", finished_at=f"2026-09-06T08:{minutes:02d}:00Z")
        running, waiting = self.item("Running", repo=APP), self.item("Waiting", repo=APP)
        self.lane("example-owner/app", "r", item=running, status="running", position=10,
                  started_at="2026-09-06T11:55:00Z")
        self.lane("example-owner/app", "w", item=waiting, status="pending", position=11)
        entries = today.landing(self.connection, now=NOW)["entries"]
        self.assertEqual([(row["place"], row["eta"], row["repo"]) for row in entries],
                         [(1, "2026-09-06T12:15:00Z", APP), (2, "2026-09-06T12:35:00Z", APP)])

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

    def test_sections_come_in_one_order_with_their_counts(self):
        self.item("Soon", due="2026-09-08")
        self.item("Later", due="2026-10-30")
        found = today.sections(self.connection, now=NOW)
        self.assertEqual(list(found), ["summary", *today.ORDER])
        self.assertEqual((found["summary"]["planned"], found["summary"]["planned_this_week"]), (2, 1))

    def test_the_active_assignment_states_match_the_workflow(self):
        self.assertEqual(today.ACTIVE_ASSIGNMENTS, workflow.ACTIVE_ASSIGNMENTS)


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
