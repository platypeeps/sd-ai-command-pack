"""Today at a glance: the spend line (sd:6031), the builder runs in In motion (sd:6003) and the day's digest (sd:6002).

Each is a part of `now_screen.document`, read on `/api/now` with the rest of Today, and drawn by `today.js`. A part whose
read failed is its reason, never a zero or an empty list.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest import mock

from sd_db import reads

from sd_dashboard import now_screen

from support import NOW, ScreenCase
from test_now_screen import JobsBackend, fleet_document
from test_v2_today_reader import ReaderCase

CLOCK = datetime.fromisoformat(NOW.replace("Z", "+00:00"))


def ago(**delta) -> str:
    return (CLOCK - timedelta(**delta)).isoformat(timespec="seconds")


class TodayCase(ScreenCase):
    def today(self, **seams):
        return now_screen.document(self.connection, now=NOW, jobs=JobsBackend(self.tmp.name), fleet=fleet_document, **seams)

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
