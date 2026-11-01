"""Today at a glance: the spend line (sd:6031), the builder runs in In motion (sd:6003) and the day's digest (sd:6002).

Each is a part of `now_screen.document`, read on `/api/now` with the rest of Today, and drawn by `today.js`. A part whose
read failed is its reason, never a zero or an empty list.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from unittest import mock

from sd_dashboard import now_screen
from sd_db import reads
from support import NOW, ScreenCase
from test_now_screen import JobsBackend, fleet_document
from test_today_needs import blocked, lane, queue
from test_v2_today_reader import ReaderCase

CLOCK = datetime.fromisoformat(NOW.replace("Z", "+00:00"))


def ago(**delta) -> str:
    return (CLOCK - timedelta(**delta)).isoformat(timespec="seconds")


class TodayCase(ScreenCase):
    def today(self, jobs=(), **seams):
        return now_screen.document(self.connection, now=NOW, jobs=JobsBackend(self.tmp.name, jobs=jobs),
                                   fleet=fleet_document, **seams)

    def cost(self, usd, at, source="run", **columns):
        self.connection.execute(
            "INSERT INTO cost (timestamp, usd, source, assignment, pass, window_minutes, used_percent)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)", (at, usd, source, columns.get("assignment"), columns.get("pass_"),
                                              columns.get("window_minutes"), columns.get("used_percent")))
        self.connection.commit()


class TheSpend(TodayCase):
    def test_spend_is_the_last_24_hours_and_seven_daily_windows_of_spent_cost(self):
        self.cost(1.5, ago(hours=1))
        self.cost(0.25, ago(hours=23).replace("+00:00", "Z"), source="bound")
        self.cost(2.0, ago(hours=36))
        self.cost(9.0, ago(hours=1), source="reserved")  # held, not spent
        self.cost(4.0, ago(days=8))  # before the week
        self.cost(None, ago(hours=2), source="meter", window_minutes=300, used_percent=40.0)
        spend = self.today()["spend"]
        self.assertEqual(spend, {"day": 1.75, "week": 3.75, "days": [0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 1.75], "error": ""})

    def test_a_cost_read_that_failed_is_its_reason_never_zero(self):
        with mock.patch.object(reads, "spent_since", side_effect=sqlite3.OperationalError("database is locked")):
            self.assertEqual(self.today()["spend"], {"error": "database is locked"})


class TheSpendLine(ReaderCase):
    def test_the_spend_line_shows_the_day_the_week_and_a_bar_per_day(self):
        self.doc["spend"] = {"day": 1.75, "week": 3.75, "days": [0, 0, 0, 0, 0, 2.0, 1.75], "error": ""}
        out = self.run_page("R.spend = ELS.spend.html;")
        spend = out["R"]["spend"]
        self.assertIn("24h <b>$1.75</b> · 7 days <b>$3.75</b>", spend)
        self.assertIn('aria-label="Spent per day, oldest first: $0.00, $0.00, $0.00, $0.00, $0.00, $2.00, $1.75"', spend)
        self.assertEqual(spend.count("<rect "), 7)
        self.assertIn('href="/metrics"', spend)

    def test_a_spend_read_that_failed_says_so(self):
        self.doc["spend"] = {"error": "database is locked"}
        out = self.run_page("R.spend = ELS.spend.html;")
        self.assertIn("Spend not read: database is locked", out["R"]["spend"])
        self.assertNotIn("$0.00", out["R"]["spend"])


class TheBuilders(TodayCase):
    """sd:6003: each open build run (`sd_db.build`) with its items, stage, start, ETA from past runs and cost so far."""

    def setUp(self):
        super().setUp()
        self.repo_path = self.repo("/repos/pack")

    def run_row(self, ident, *, titles=("Build me",), created, step="building", beat=None, outcome=None, released=None):
        lead = None
        for title in titles:
            item = self.item(title, kind="task", repo=self.repo_path)
            assignment = self.assignment(item, status="running", parent=lead)
            self.connection.execute("UPDATE assignment SET scope = 'build' WHERE id = ?", (assignment,))
            lead = lead or assignment
        self.connection.execute(
            "INSERT INTO runner_run (id, assignment, run, repo, branch, owner, work_path, retained_path, created_at,"
            " updated_at, step, heartbeat_at, model, outcome, released_at)"
            " VALUES (?, ?, 1, ?, 'build/sd-1', 'fixture', '/wt', '/wt', ?, ?, ?, ?, 'opus', ?, ?)",
            (ident, lead, self.repo_path, created, created, step, beat, outcome, released))
        self.connection.commit()

    def done(self, ident, minutes):
        self.run_row(ident, created=ago(days=1, minutes=minutes), step="cleaning", outcome="done", released=ago(days=1))

    def test_an_open_run_shows_its_items_stage_start_eta_and_cost(self):
        for n, minutes in enumerate((40, 50, 60)):
            self.done(f"past{n}", minutes)
        self.run_row("live", titles=("Port the page", "Fix the link"), created=ago(minutes=30), step="reviewing",
                     beat=ago(seconds=20))
        self.cost(0.42, ago(minutes=5), pass_="live")
        self.cost(3.0, ago(minutes=5), pass_="past0")
        found = self.today()["builders"]
        self.assertEqual(found["error"], "")
        [row] = found["rows"]
        self.assertEqual([it["title"] for it in row["items"]], ["Port the page", "Fix the link"])
        self.assertEqual((row["run"], row["repo"], row["stage"], row["step"], row["state"]),
                         ("live", "pack", "review", "reviewing", "running"))
        self.assertEqual((row["started"], row["elapsed"]), ("2026-09-06T11:30:00Z", "30m"))
        self.assertEqual((row["eta"], row["eta_why"]), ("2026-09-06T12:20:00Z", "median of the last 3 done runs"))
        self.assertEqual(row["usd"], 0.42)

    def test_each_item_names_its_assignment_for_show_assignment(self):
        # sd:6714: In motion's Details shows an item's builder; Show assignment names the member's assignment.
        self.run_row("live", titles=("Port the page", "Fix the link"), created=ago(minutes=5), beat=ago(seconds=5))
        [row] = self.today()["builders"]["rows"]
        members = self.connection.execute("SELECT id, item FROM assignment WHERE scope = 'build' ORDER BY id").fetchall()
        self.assertEqual([(it["item"], it["assignment"]) for it in row["items"]], [(m["item"], m["id"]) for m in members])

    def test_with_fewer_than_three_past_runs_the_eta_says_why_it_is_not_known(self):
        self.done("past0", 40)
        self.run_row("live", created=ago(minutes=5), beat=ago(seconds=5))
        [row] = self.today()["builders"]["rows"]
        self.assertEqual((row["stage"], row["eta"], row["eta_why"]), ("building", None, "1 done run so far; an ETA needs 3"))

    def test_state_comes_from_the_run_row_never_a_quiet_stream(self):
        self.run_row("quiet", created=ago(minutes=40), step="building", beat=ago(minutes=10))
        self.run_row("lane", created=ago(minutes=40), step="enqueued", beat=ago(minutes=10))
        self.run_row("held", created=ago(minutes=40), step="fixing", beat=ago(seconds=5), outcome="blocked")
        rows = {row["run"]: row for row in self.today()["builders"]["rows"]}
        self.assertEqual({run: (row["stage"], row["state"]) for run, row in rows.items()},
                         {"quiet": ("building", "stalled"), "lane": ("lane", "running"), "held": ("building", "blocked")})
        self.assertEqual(rows["quiet"]["quiet"], 600)

    def test_a_build_read_that_failed_is_its_reason_never_no_builders(self):
        from sd_db import build

        with mock.patch.object(build, "open_runs", side_effect=sqlite3.OperationalError("no such column: step")):
            self.assertEqual(self.today()["builders"], {"rows": [], "error": "no such column: step"})


BUILDER = {"run": "live", "repo": "pack", "items": [{"item": 7, "title": "Port the page"}], "step": "reviewing",
           "stage": "review", "model": "opus", "started": "2026-09-06T11:30:00Z", "elapsed": "30m",
           "eta": "2026-09-06T12:20:00Z", "eta_why": "median of the last 3 done runs", "state": "running", "quiet": 20,
           "usd": 0.42}


class TheBuilderRows(ReaderCase):
    def test_in_motion_lists_each_builder_run_with_stage_start_and_eta(self):
        self.doc["builders"] = {"rows": [BUILDER, {**BUILDER, "run": "old", "state": "stalled", "quiet": 600, "eta": None,
                                                   "eta_why": "1 done run so far; an ETA needs 3"}], "error": ""}
        out = self.run_page("R.builds = ELS.builds.html; R.hidden = ELS['builds-table'].hidden; R.tally = ELS['active-tally'].html;")
        builds = out["R"]["builds"]
        self.assertFalse(out["R"]["hidden"])
        self.assertIn("#7 Port the page</a>", builds)
        self.assertIn("<b>review</b>", builds)
        self.assertIn("pack · opus · $0.42 so far", builds)
        self.assertIn('<time datetime="2026-09-06T12:20:00Z">', builds)
        self.assertIn('title="stalled: no beat for 10m"', builds)
        self.assertIn("1 done run so far; an ETA needs 3", builds)
        self.assertIn("<span>2 builders</span>", out["R"]["tally"])

    def test_no_open_run_hides_the_table_and_a_failed_read_says_so(self):
        self.doc["builders"] = {"rows": [], "error": ""}
        none = self.run_page("R.hidden = ELS['builds-table'].hidden;")
        self.assertTrue(none["R"]["hidden"])
        self.doc["builders"] = {"rows": [], "error": "no such column: step"}
        out = self.run_page("R.builds = ELS.builds.html; R.hidden = ELS['builds-table'].hidden;")
        self.assertFalse(out["R"]["hidden"])
        self.assertIn("Builder runs could not be read: no such column: step", out["R"]["builds"])


class TheQueues(TodayCase):
    def test_the_queues_are_sd_todays_ready_build_and_lane_rows(self):
        """Pack sd:6946: one Queues panel, read as `sd today` reads it."""
        from sd_db import create_item

        ready = create_item(self.connection, kind="task", title="Build me next", status="ready", priority=1)
        rows = self.today()["queues"]["rows"]
        self.assertIn(("ready", ready, "P1"), [(row["queue"], row["id"], row["detail"]) for row in rows])

    def test_a_queues_read_that_failed_is_its_reason_never_empty(self):
        from sd_db import today

        with mock.patch.object(today, "queues", side_effect=sqlite3.OperationalError("database is locked")):
            self.assertEqual(self.today()["queues"], {"rows": [], "error": "database is locked"})


QUEUED = [{"queue": "ready", "id": 7, "repo": "~/repos/pack", "title": "Port the page", "status": "ready",
           "detail": "P1", "since": "2026-09-06T11:00:00Z"},
          {"queue": "build", "id": 8, "repo": "~/repos/system", "title": "Fix the job", "status": "blocked",
           "detail": "3 review rounds left blockers", "since": "2026-09-06T10:00:00Z"},
          {"queue": "lane", "id": 9, "repo": "~/repos/pack", "title": "Land it", "status": "pending",
           "detail": "-", "since": "2026-09-06T11:30:00Z", "place": 2}]


class TheQueueRows(ReaderCase):
    def test_the_queues_panel_lists_each_queue_with_a_chip_per_repo(self):
        self.doc["queues"] = {"rows": QUEUED, "error": ""}
        out = self.run_page("R.rows = ELS.queues.html; R.chips = ELS['queues-repos'].html; "
                            "R.tally = ELS['queues-tally'].html;")
        rows = out["R"]["rows"]
        self.assertIn("#7 Port the page</a>", rows)
        self.assertIn("<b>build</b> · blocked", rows)
        self.assertIn("3 review rounds left blockers", rows)
        self.assertIn("<b>lane</b> · pending · position 2", rows)
        self.assertIn('data-qrepo="~/repos/system"', out["R"]["chips"])
        self.assertIn("<span>1 ready</span>", out["R"]["tally"])

    def test_a_failed_queues_read_says_so(self):
        self.doc["queues"] = {"rows": [], "error": "database is locked"}
        out = self.run_page("R.rows = ELS.queues.html;")
        self.assertIn("The queues could not be read: database is locked", out["R"]["rows"])


class RowDetails(ReaderCase):
    """sd:6714: a plain click on an In motion row, a builder row or a day-track mark draws its Details, as a Needs you
    row's does; the item link still opens a new tab on a modifier click."""

    SESSION = {"item": 7, "title": "Port the page", "status": "in_progress", "kind": "lane", "session": "Lane queue",
               "started": "2026-09-06T11:30:00Z", "elapsed": "30m", "seconds": 1800, "via": "lane entry", "verified": True,
               "revision": "rev7", "item_kind": "task", "lane": "pack: next, position 2"}

    def setUp(self):
        super().setUp()
        self.doc["active"] = {"rows": [self.SESSION], "sources": {}, "error": ""}
        self.doc["builders"] = {"rows": [{**BUILDER, "items": [{"item": 7, "title": "Port the page", "assignment": 41}]}], "error": ""}
        self.doc["track"] = {"since": "2026-09-05T12:00:00Z", "until": NOW, "landed": [{"at": "2026-09-06T10:00:00Z", "id": "item:5", "item": 5, "what": "sd:5 Ship it"}],
                             "jobs": [{"at": "2026-09-06T09:00:00Z", "id": "job:gone:3", "what": "gone failed"}], "briefs": [],
                             "live": [{"at": "2026-09-06T11:30:00Z", "id": "session:7:0", "item": 7, "what": "sd:7 Lane queue"}],
                             "key": {"landed": 1, "landing": 0, "due_week": 0, "blocked": 0}}

    CLICK = ("ELS['%s'].listeners.click[0]({ prevented: false, preventDefault() { this.prevented = true; R.prevented = true; },"
             " target: { closest: s => s === '%s' ? { dataset: { id: '%s' } } : s === 'a' ? %s : null } });")

    def click(self, table, sel, ident, link="null"):
        return self.CLICK % (table, sel, ident, link)

    def test_an_in_motion_row_shows_the_item_its_sessions_lane_and_builder(self):
        out = self.run_page(self.click("active", "tr[data-id]", "live:7", "{ href: '/tasks?row=7' }")
                            + " R.details = ELS.details.html; R.row = location.search; R.active = ELS.active.html;"
                            " R.cmds = REG.filter(c => c.on === 'live item').map(c => [c.id, C.offWhy(c, C.get('live:7'))]);")
        details = out["R"]["details"]
        self.assertTrue(out["R"]["prevented"], "a plain click on the item link selects instead of leaving the page")
        self.assertEqual(out["R"]["row"], "?row=live%3A7")
        for text in ("Port the page", "Lane queue", "lane entry", "30m", "pack: next, position 2", "<b>review</b>", "#41"):
            self.assertIn(text, details)
        self.assertEqual(dict(out["R"]["cmds"]), {"today.live.open": "", "today.live.assignment": "", "live item.fix": ""})
        self.assertIn('data-id="live:7"', out["R"]["active"])

    def test_a_modifier_click_on_the_item_link_leaves_it_to_the_browser(self):
        click = self.click("active", "tr[data-id]", "live:7", "{ href: '/tasks?row=7' }").replace("prevented: false,", "metaKey: true,")
        out = self.run_page("R.before = ELS.details.html;" + click + " R.after = ELS.details.html;")
        self.assertNotIn("prevented", out["R"])
        self.assertEqual(out["R"]["before"], out["R"]["after"])

    def test_a_builder_row_and_each_day_track_mark_show_their_details(self):
        out = self.run_page(self.click("builds", "tr[data-id]", "run:live") + " R.builder = ELS.details.html;"
                            + self.click("track-rows", "tr[data-id]", "landed:5") + " R.landed = ELS.details.html;"
                            + self.click("track-plot", "[data-id]", "job:gone:3") + " R.gone = ELS.details.html;"
                            + self.click("track-plot", "[data-id]", "live:7") + " R.live = ELS.details.html;"
                            + self.click("track-rows", "tr[data-id]", "job:nightly-sync:7") + " R.job = ELS.details.html; R.sel = selected();")
        self.assertIn("Port the page", out["R"]["builder"])
        self.assertIn("median of the last 3 done runs", out["R"]["builder"])
        self.assertIn("sd:5 Ship it", out["R"]["landed"])
        self.assertIn("no longer on Needs you", out["R"]["gone"])
        self.assertIn("pack: next, position 2", out["R"]["live"])
        self.assertIn("nightly-sync failed with exit 7", out["R"]["job"])
        self.assertEqual(out["R"]["sel"], ["job:nightly-sync:7"])

    def test_the_address_keeps_an_in_motion_selection(self):
        out = self.run_page("R.details = ELS.details.html; R.row = location.search;", search="?row=live%3A7")
        self.assertIn("pack: next, position 2", out["R"]["details"])
        self.assertEqual(out["R"]["row"], "?row=live%3A7")


SHA = "a" * 40


class InMotionFacts(TodayCase):
    """sd:6714: each In motion session row carries what its Details and Fix need: the item's revision and kind, and its
    place in a lane."""

    def test_a_session_row_carries_its_items_revision_kind_and_lane_place(self):
        moving, idle = self.item("Port the page", kind="task"), self.item("Read the docs")
        rows = [{"item": moving, "title": "Port the page", "status": "in_progress", "kind": "lane", "session": "Lane queue",
                 "started": NOW, "elapsed": "5m", "seconds": 300, "via": "lane entry", "verified": True},
                {"item": idle, "title": "Read the docs", "status": "in_progress", "kind": "worktree", "session": "wt",
                 "started": NOW, "elapsed": "5m", "seconds": 300, "via": "-C /wt", "verified": True}]
        nxt = {"item": moving, "title": "Port the page", "state": "next", "position": 2, "held": False}
        with mock.patch("sd_dashboard.active_sessions.document", return_value={"rows": rows, "sources": {}, "error": ""}):
            found = self.today(lanes=queue(lane("pack", rows=[nxt])))["active"]["rows"]
        self.assertEqual([(r["item"], r["item_kind"], r["lane"]) for r in found],
                         [(moving, "task", "pack: next, position 2"), (idle, "work", "")])
        self.assertEqual([r["revision"] for r in found], [reads.revisions(self.connection, [moving])[moving],
                                                         reads.revisions(self.connection, [idle])[idle]])


class TheDigest(TodayCase):
    """sd:6002: Since yesterday, the overnight card (grill Q32): merged per repo, failed with why and fix, questions."""

    def merged(self, title, repo, pr):
        item = self.item(title, kind="task", repo=self.repo(f"/repos/{repo}"))
        self.note(item, f"Code delivery https://example.test/{repo}/pull/{pr} at {SHA}", kind="comment")
        return item

    def test_the_digest_groups_merges_by_repo_and_lists_failures_and_questions(self):
        one = self.merged("Port the page", "pack", 12)
        two = self.merged("Fix the link", "pack", 13)
        three = self.merged("Pin the gate", "system", 7)
        asks = self.item("Pick a colour", repo=self.repo("/repos/pack"))
        self.note(asks, "Which colour?\nOption: red\nOption: blue", kind="question")
        digest = self.today(jobs=[("backup", "failed", 1, None)], lanes=queue(lane(rows=[blocked(5)])))["digest"]
        self.assertEqual(digest["error"], "")
        self.assertEqual(digest["merged"], [{"repo": "pack", "n": 2, "titles": ["Fix the link", "Port the page"]},
                                            {"repo": "system", "n": 1, "titles": ["Pin the gate"]}])
        self.assertEqual(digest["more"], 0)
        self.assertEqual([(pr["item"], pr["repo"], pr["pr"]) for pr in digest["prs"]],
                         [(three, "system", 7), (two, "pack", 13), (one, "pack", 12)])
        self.assertEqual([(row["what"], row["fix"]) for row in digest["failed"]],
                         [("backup failed with exit 1", "retry: launchctl kickstart fixture/backup"),
                          ("system sd:5 blocked at prepare", "Retry it in Needs you or on Queue")])
        self.assertTrue(all(row["why"] for row in digest["failed"]))
        self.assertEqual(digest["failed"][1]["why"], "lane: sd-check: a suite failed")
        self.assertEqual(digest["questions"], 1)

    def test_more_repos_than_the_card_holds_are_counted(self):
        for n in range(7):
            self.merged(f"Item {n}", f"repo{n}", n + 1)
        digest = self.today()["digest"]
        self.assertEqual((len(digest["merged"]), digest["more"], len(digest["prs"])), (5, 2, 7))

    def test_a_read_that_failed_is_its_reason_never_a_quiet_night(self):
        from sd_db import today

        with mock.patch.object(today, "decisions", side_effect=sqlite3.OperationalError("database is locked")):
            self.assertEqual(self.today()["digest"], {"error": "database is locked"})


    def test_a_job_or_lane_read_that_failed_makes_the_failures_unknown(self):
        """sd:6259: a failed job or lane read listed no failures, and the card said a quiet night."""
        self.assertEqual(self.today(lanes=queue())["digest"]["unknown"], "")

        def down(connection, now):
            raise OSError("lane store unreadable")

        with mock.patch.object(now_screen, "_jobs", side_effect=OSError("launchctl did not answer")):
            digest = self.today(lanes=down)["digest"]
        self.assertEqual(digest["error"], "")
        self.assertEqual(digest["unknown"], "jobs: launchctl did not answer; lane: lane store unreadable")

    def test_a_lane_one_repo_could_not_list_is_unknown_too(self):
        def partial(connection, now):
            return {**queue()(connection, now), "problems": [{"repo": "/repos/pack", "error": "lane.json unreadable"}]}

        self.assertEqual(self.today(lanes=partial)["digest"]["unknown"], "lane pack: lane.json unreadable")

DIGEST = {"merged": [{"repo": "pack", "n": 2, "titles": ["Fix the link", "Port the page"]}], "more": 1,
          "prs": [{"item": 7, "title": "Fix the link", "repo": "pack", "pr": 13}],
          "failed": [{"what": "backup failed with exit 1", "why": "the disk was full",
                      "fix": "retry: launchctl kickstart fixture/backup"}], "questions": 2, "error": ""}


class TheDigestCard(ReaderCase):
    def test_the_card_shows_merged_lines_failures_and_questions_with_the_prs_folded(self):
        self.doc["digest"] = DIGEST
        card = self.run_page("R.digest = ELS.digest.html;")["R"]["digest"]
        self.assertIn("<b>pack</b>: 2 merged · Fix the link, Port the page", card)
        self.assertIn("and 1 more repo", card)
        self.assertIn("<details><summary>1 merged item</summary>", card)
        self.assertIn("#7 Fix the link</a> · pack · PR #13", card)
        self.assertIn("backup failed with exit 1</b> · the disk was full · retry: launchctl kickstart fixture/backup", card)
        self.assertIn('<a href="/decide">2 questions wait</a>', card)

    def test_a_quiet_night_says_so_and_a_failed_read_says_why(self):
        self.doc["digest"] = {"merged": [], "more": 0, "prs": [], "failed": [], "questions": 0, "error": ""}
        quiet = self.run_page("R.digest = ELS.digest.html;")["R"]["digest"]
        self.assertIn("Nothing merged, failed or waiting since yesterday.", quiet)
        self.doc["digest"] = {"error": "database is locked"}
        failed = self.run_page("R.digest = ELS.digest.html;")["R"]["digest"]
        self.assertIn("The digest was not read: database is locked. Read again tries again.", failed)

    def test_unknown_failures_are_said_never_a_quiet_night(self):
        """sd:6259: a job or lane read that failed leaves the failures unknown."""
        self.doc["digest"] = {"merged": [], "more": 0, "prs": [], "failed": [], "questions": 0, "error": "",
                              "unknown": "jobs: launchctl did not answer"}
        card = self.run_page("R.digest = ELS.digest.html;")["R"]["digest"]
        self.assertNotIn("Nothing merged", card)
        self.assertIn("Failed jobs and blocked lane entries unknown: jobs: launchctl did not answer", card)
