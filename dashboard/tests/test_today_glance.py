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
