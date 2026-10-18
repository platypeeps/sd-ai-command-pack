"""The one text layout of `sd today` and `sd-status` (sd:5098), pinned as exact text.

A fixture database with fixed timestamps, a fixed `now` and a fixed zone, so
the golden text cannot drift: a changed column, order, cap or cell fails here.
"""

from __future__ import annotations

import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import sd_db  # noqa: E402
import sd_views  # noqa: E402
from sd_db import today  # noqa: E402
from sd_db.writes import add_note, transition  # noqa: E402

from tests.clean_env import clean_environment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-06T18:00:00Z"
MOMENT = datetime.datetime(2026, 9, 6, 18, 0, tzinfo=datetime.timezone.utc)
APP = "~/repos/example.test/app"
LIB = "~/repos/example.test/lib"
SHA = "c0ffee" + "0" * 34


def fill(connection) -> dict[str, int]:
    """One row or more for every section, all stamped at fixed times."""
    sd_db.upsert_repo(connection, APP, remote="https://github.com/example-owner/app")
    sd_db.upsert_repo(connection, LIB, remote="https://github.com/example-owner/lib")
    made = {}

    def item(name, title, **fields):
        made[name] = sd_db.create_item(connection, kind=fields.pop("kind", "task"), title=title, **fields)
        return made[name]

    item("report", "nightly-sweep: needs attention", kind="report", repo=APP, fields={"attention": "two stale rows"})
    asked = item("asked", "Pick a store", repo=APP)
    add_note(connection, asked, "question", "Which store holds the rows?\nOption: Pack\nOption: Database")
    for number in range(1, 8):
        owed = item(f"owed{number}", f"Owed work number {number}", repo=LIB, priority=number % 3)
        add_note(connection, owed, "followup", f"Chase the vendor about {number}")
    shipped = item("shipped", "Ship the parser", repo=APP, status="in_progress")
    transition(connection, shipped, "done", who="sd-ship", reason=f"delivered at {SHA} on origin/main")
    add_note(connection, shipped, "comment", f"Code delivery https://github.com/example-owner/app/pull/42 at {SHA}")
    running = item("running", "Land the cache", repo=APP)
    waiting = item("waiting", "Land the index", repo=APP)
    for number, minutes in enumerate((20, 30, 40)):
        lane(connection, "example-owner/app", f"m{number}", item=900 + number, status="merged", position=number,
             started_at="2026-09-05T10:00:00Z", finished_at=f"2026-09-05T10:{minutes:02d}:00Z")
    lane(connection, "example-owner/app", "r", item=running, status="running", position=5, step="prepare",
         started_at="2026-09-06T17:50:00Z")
    lane(connection, "example-owner/app", "w", item=waiting, status="pending", position=6)
    stuck = item("stuck", "Wire the webhook", repo=LIB)
    transition(connection, stuck, "blocked", who="operator", reason="Waits on the vendor's API key")
    item("planned", "Renew the certificate", repo=LIB, due="2026-09-09")
    item("late", "Rotate the token", repo=APP, due="2026-09-01", status="in_progress")
    transition(connection, item("swept", "Close a stale row", repo=APP), "done", who="operator", reason="bulk close")
    connection.execute("UPDATE item SET created_at = '2026-09-01T09:00:00Z', updated_at = '2026-09-01T09:00:00Z'")
    connection.execute("UPDATE note SET timestamp = '2026-09-06T15:00:00+00:00'")
    connection.commit()
    return made


def lane(connection, repository, entry, **body):
    connection.execute("INSERT INTO state(kind, key, timestamp, body) VALUES ('checkpoint', ?, ?, ?)",
                       (f"{today.LANE_KEY_PREFIX}{repository}:{entry}", NOW, json.dumps({"id": entry, **body})))


GATE = {"holders": [{"slot": 1, "pid": 7, "label": "app tests", "since": "2026-09-06T17:55:00Z", "cwd": "/tmp"}],
        "waiters": [{"place": 1, "pid": 8, "label": "lib tests", "since": "2026-09-06T17:58:00Z", "cwd": "/tmp"}]}

TODAY = """\
1 attention · 1 decisions · 2 landing · 1 delivered · 1 planned this week · 1 blocked · 8 unscheduled · 7 followups · 1 work

Attention (1)
ID  Repo  State     Why             Title                           When
--  ----  --------  --------------  ------------------------------  -------
#1  app   planning  two stale rows  nightly-sweep: needs attention  5 d ago

Decisions (1)
ID  Repo  State     Note  Title                        When
--  ----  --------  ----  ---------------------------  -------
#2  app   planning  #3    Which store holds the rows?  3 h ago

Landing now (2)
ID   Repo  State    Position  ETA         Title             When
---  ----  -------  --------  ----------  ----------------  -------
#11  app   running  1         ~12:20 MDT  Land the cache    in 20 m
#12  app   pending  2         ~12:50 MDT  Land the index    in 50 m
Gate slots: 1 holding (app tests since 11:55 MDT) · 1 waiting (lib tests)

Delivered (1)
ID   Repo  State   PR   Commit     Title             When
---  ----  ------  ---  ---------  ----------------  ---------
#10  app   merged  #42  c0ffee000  Ship the parser   09:00 MDT
+1 closed by hand

Planned (1)
ID   Repo  State     Due             Title                  When
---  ----  --------  --------------  ---------------------  ------
#14  lib   planning  2026-09-09 MDT  Renew the certificate  in 3 d

Blocked (1)
ID   Repo  State    Waiting on                     Title             When
---  ----  -------  -----------------------------  ----------------  -------
#13  lib   blocked  Waits on the vendor's API key  Wire the webhook  3 h ago

Unscheduled (8)
ID  Repo  State     Priority  Title               When
--  ----  --------  --------  ------------------  -------
#5  lib   planning  P0        Owed work number 3  5 d ago
#8  lib   planning  P0        Owed work number 6  5 d ago
#3  lib   planning  P1        Owed work number 1  5 d ago
#6  lib   planning  P1        Owed work number 4  5 d ago
#9  lib   planning  P1        Owed work number 7  5 d ago
… 3 more

Followups (7)
ID  Repo  State     Note  Title                     When
--  ----  --------  ----  ------------------------  -------
#3  lib   planning  #5    Chase the vendor about 1  3 h ago
#4  lib   planning  #7    Chase the vendor about 2  3 h ago
#5  lib   planning  #9    Chase the vendor about 3  3 h ago
#6  lib   planning  #11   Chase the vendor about 4  3 h ago
#7  lib   planning  #13   Chase the vendor about 5  3 h ago
… 2 more

Work (1)
ID   Repo  State        Due              Priority  Title             When
---  ----  -----------  ---------------  --------  ----------------  -------
#15  app   in_progress  2026-09-01 late  -         Rotate the token  3 h ago
"""

STATUS = """\

work across the shared database
  repositories: app, lib
  2 landing · 1 delivered · 1 planned this week · 1 blocked · 8 unscheduled

  Landing now (2)
  ID   Repo  State    Position  ETA         Title             When
  ---  ----  -------  --------  ----------  ----------------  -------
  #11  app   running  1         ~12:20 MDT  Land the cache    in 20 m
  #12  app   pending  2         ~12:50 MDT  Land the index    in 50 m

  Delivered (1)
  ID   Repo  State   PR   Commit     Title             When
  ---  ----  ------  ---  ---------  ----------------  ---------
  #10  app   merged  #42  c0ffee000  Ship the parser   09:00 MDT
  +1 closed by hand

  Planned (1)
  ID   Repo  State     Due             Title                  When
  ---  ----  --------  --------------  ---------------------  ------
  #14  lib   planning  2026-09-09 MDT  Renew the certificate  in 3 d

  Blocked (1)
  ID   Repo  State    Waiting on                     Title             When
  ---  ----  -------  -----------------------------  ----------------  -------
  #13  lib   blocked  Waits on the vendor's API key  Wire the webhook  3 h ago

  Unscheduled (8)
  ID  Repo  State     Priority  Title               When
  --  ----  --------  --------  ------------------  -------
  #5  lib   planning  P0        Owed work number 3  5 d ago
  #8  lib   planning  P0        Owed work number 6  5 d ago
  #3  lib   planning  P1        Owed work number 1  5 d ago
  #6  lib   planning  P1        Owed work number 4  5 d ago
  #9  lib   planning  P1        Owed work number 7  5 d ago
  … 3 more
"""


def load_status():
    path = ROOT / "bin" / "sd-status"
    loader = importlib.machinery.SourceFileLoader("sd_status_views", str(path))
    spec = importlib.util.spec_from_file_location("sd_status_views", str(path), loader=loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Zone(unittest.TestCase):
    def setUp(self):
        zone = unittest.mock.patch.dict(os.environ, {"TZ": "America/Denver"})
        zone.start()
        time.tzset()
        self.addCleanup(time.tzset)
        self.addCleanup(zone.stop)
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name)
        sd_db.initialise(home=self.home)
        self.connection = sd_db.connect(home=self.home)
        self.addCleanup(self.connection.close)


class SdToday(Zone):
    def test_the_layout_is_this_text_exactly(self):
        fill(self.connection)
        text = sd_views.render_sections(today.sections(self.connection, now=NOW, gate=GATE), now=MOMENT, width=100)
        self.maxDiff = None
        self.assertEqual(text, TODAY)

    def test_an_empty_store_prints_every_heading(self):
        text = sd_views.render_sections(today.sections(self.connection, now=NOW), now=MOMENT, width=100)
        self.assertEqual(text.splitlines()[2::2], [f"{heading} (0)" for heading in sd_views.HEADINGS.values()])

    def test_two_runs_of_the_command_print_the_same_bytes(self):
        """The real clock runs here, so the lane goes: an ETA is a minute that two runs can straddle."""
        fill(self.connection)
        self.connection.execute("DELETE FROM state WHERE key LIKE ?", (f"{today.LANE_KEY_PREFIX}%",))
        self.connection.commit()
        runs = [subprocess.run([sys.executable, str(ROOT / "bin" / "sd"), "today"], capture_output=True, text=True,
                               env=clean_environment(HOME=str(self.home), COLUMNS="100",
                                                     SD_GATE_SLOTS_DIR=str(self.home)),
                               check=True).stdout for _ in range(2)]
        self.assertEqual(runs[0], runs[1])
        self.assertEqual([line for line in runs[0].splitlines() if line.endswith(")") and "(" in line][:3],
                         ["Attention (1)", "Decisions (1)", "Landing now (0)"])


class SdStatus(Zone):
    """`sd-status` prints the same tables for its repositories, indented under its one heading."""

    def test_the_views_block_is_this_text_exactly(self):
        fill(self.connection)
        section = {"available": True, "reason": "", "repos": [APP, LIB],
                   "sections": today.sections(self.connection, repos=[APP, LIB], now=NOW)}
        stream = io.StringIO()
        load_status()._render_views(section, stream.write, now=MOMENT, width=100)
        self.maxDiff = None
        self.assertEqual(stream.getvalue(), STATUS)

    def test_two_renders_print_the_same_bytes(self):
        fill(self.connection)
        status = load_status()
        runs = []
        for _ in range(2):
            section = {"available": True, "reason": "", "repos": [APP],
                       "sections": today.sections(self.connection, repos=[APP], now=NOW)}
            stream = io.StringIO()
            status._render_views(section, stream.write, now=MOMENT, width=100)
            runs.append(stream.getvalue())
        self.assertEqual(runs[0], runs[1])


if __name__ == "__main__":
    unittest.main()
