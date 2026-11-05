"""`/api/usage` as `sd usage --json`'s bytes (sd:234 slice 8d), under the merged caps (slice 12h).

The Usage area that drew this month moved to Metrics' Spend view (pack sd:7524): its four numbers, burn line and
month picker are test_v2_metrics's, and its cap forms are Metrics' Cap command (TheControls, TheControlsScript)."""

import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sd_db import connect, provider_controls
from sd_db.migrate import initialise
from support import NOW, ScreenCase, record_cost
from test_workflow_actions import BrowserSession

#: The pack whose `bin/sd-db` the verb runs (sd:3279). The verb defaults `SD_PACK_ROOT` under `$HOME`, which these
#: tests point at a temporary store, so name the checkout this suite sits in (sd:5987).
PACK = str(Path(__file__).resolve().parents[2])
SD_DB = Path(PACK) / "lib"


class Seeds:
    def bill(self, name, cap=None, basis="api"):
        self.connection.execute("INSERT OR IGNORE INTO bill VALUES (?, ?, ?)", (name, basis, cap))
        self.connection.commit()

    def cost(self, source, *, at, **columns):
        row = record_cost(self.connection, source=source, **columns)
        self.connection.execute("UPDATE cost SET timestamp = ? WHERE id = ?", (at, row))
        self.connection.commit()
        return row

    def month(self):
        self.provider("kimi")
        self.bill("capped", 100)
        self.bill("open")
        self.cost("run", at="2026-09-01T10:00:00Z", provider="kimi", bill="capped", role="author", usd=10)
        self.cost("bound", at="2026-09-05T10:00:00Z", provider="kimi", bill="capped", role="author",
                  call_id="lost", usd=30)
        self.cost("sending", at="2026-09-06T09:00:00Z", provider="kimi", bill="capped", role="author",
                  call_id="wire", usd=5, owner_pid=os.getpid())
        self.cost("run", at="2026-09-03T10:00:00Z", provider="kimi", bill="open", role="reviewer", usd=1)



def _home_store(self):
    """`ScreenCase.setUp` with the store where `sd-db` looks for it."""
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.home = Path(self.tmp.name)
    self.path = self.home / ".local/share/sd/sd.db"
    self.path.parent.mkdir(parents=True)
    initialise(self.path)
    self.connection = connect(self.path)
    self.addCleanup(self.connection.close)
    self.now = NOW


class UsageApi(Seeds, BrowserSession):
    def setUp(self):
        with patch.object(ScreenCase, "setUp", _home_store):
            super().setUp()

    def test_the_api_serves_the_read_and_the_verb_sweeps_first(self):
        """The dashboard's GET connection is read-only (`mode=ro`,
        `query_only`), so `/api/usage` and the panel show the read as it
        stands: a dead owner's `sending` row is still held until the next
        reservation or `sd usage` sweeps it. After the verb, the API's bytes
        are the verb's."""
        self.month()
        child = subprocess.Popen(["true"])
        child.wait()
        self.cost("sending", at="2026-09-07T09:00:00Z", provider="kimi", bill="capped", role="author",
                  call_id="orphan", usd=7, owner_pid=child.pid)
        before = self.request("/api/usage?month=2026-09", headers={"Cookie": self.cookie})[2]
        self.assertIn('"held": 12.0', before)
        self.assertEqual(self.connection.execute("SELECT source FROM cost WHERE call_id = 'orphan'").fetchone()[0],
                         "sending")
        environment = {**os.environ, "HOME": str(self.home), "PYTHONPATH": str(SD_DB), "SD_PACK_ROOT": PACK}
        environment.pop("XDG_STATE_HOME", None)
        printed = subprocess.run([str(Path(PACK) / "bin/sd-db"), "usage", "--month", "2026-09", "--json"],
                                 capture_output=True, text=True, input="", env=environment)
        self.assertEqual(printed.returncode, 0, printed.stderr)
        self.assertIn("bound 1 sending row(s)", printed.stderr)
        self.assertNotEqual(printed.stdout, before)
        self.assertEqual(self.request("/api/usage?month=2026-09", headers={"Cookie": self.cookie})[2], printed.stdout)
        self.assertIn('"held": 5.0', printed.stdout)

    def test_the_api_serves_the_verbs_json_byte_for_byte(self):
        self.month()
        environment = {**os.environ, "HOME": str(self.home), "PYTHONPATH": str(SD_DB), "SD_PACK_ROOT": PACK}
        environment.pop("XDG_STATE_HOME", None)
        verb = subprocess.run([str(Path(PACK) / "bin/sd-db"), "usage", "--month", "2026-09", "--json"],
                              capture_output=True, text=True, input="", env=environment)
        self.assertEqual(verb.returncode, 0, verb.stdout + verb.stderr)
        status, headers, body = self.request("/api/usage?month=2026-09", headers={"Cookie": self.cookie})
        self.assertEqual((status, headers["Content-Type"]), (200, "application/json; charset=utf-8"))
        self.assertEqual(body, verb.stdout)
        self.assertIn('"estimated": 30.0', body)
        self.assertEqual(self.request("/api/usage?month=2026-09")[0], 403)
        self.assertEqual(self.request("/api/usage?month=soon", headers={"Cookie": self.cookie})[0], 400)
        self.assertEqual(self.request("/api/usage?week=1", headers={"Cookie": self.cookie})[0], 400)


#: One `start` entry on `a`, one `url` entry on the capped `c`: the shape
#: `registry.merge` warns about once a row cap lands on `a`.
REGISTRY = """bills:
  a: {cost: subscription}
  c: {cost: api, cap_usd_month: 20}
providers:
  claude: {start: "claude -p", vendor: anthropic, bill: a, roles: [author, reviewer], reader: claude-json}
  minimax: {url: "https://example.invalid/v1", model: fixture, vendor: minimax, bill: c, roles: [author, reviewer]}
roles:
  author: [claude, minimax]
  reviewer: [minimax, claude]
"""


class MergedCaps(Seeds, BrowserSession):
    """#435's residue (sd:234 slice 12h): the API reads a bill's cap the way `snapshot` does, so a legacy row cap on
    a `start` bill is not the cap, while the `url` bill's cap is unchanged."""

    def setUp(self):
        with patch.object(ScreenCase, "setUp", _home_store):
            super().setUp()
        (self.path.parent / "providers.yaml").write_text(REGISTRY)
        provider_controls.snapshot(self.connection)  # seeds the rows the bare UPDATE below needs
        with self.connection:
            self.assertEqual(self.connection.execute("UPDATE bill SET cap_usd_month = 5.0 WHERE name = 'a'").rowcount, 1)
        # The served page reads the wall clock, and its cost tile sums the current month, so the costs fall at the start
        # of the current UTC month: a pinned month fails every run outside it (sd:2288).
        self.this_month = datetime.now(timezone.utc).strftime("%Y-%m")
        self.cost("run", at=f"{self.this_month}-01T00:00:00Z", provider="claude", bill="a", role="author", usd=2)
        self.cost("run", at=f"{self.this_month}-01T00:00:01Z", provider="minimax", bill="c", role="reviewer", usd=4)

    def test_the_api_and_the_verb_carry_the_merged_caps_in_the_same_bytes(self):
        body = self.request(f"/api/usage?month={self.this_month}", headers={"Cookie": self.cookie})[2]
        environment = {**os.environ, "HOME": str(self.home), "PYTHONPATH": str(SD_DB), "SD_PACK_ROOT": PACK}
        environment.pop("XDG_STATE_HOME", None)
        verb = subprocess.run([str(Path(PACK) / "bin/sd-db"), "usage", "--month", self.this_month, "--json"],
                              capture_output=True, text=True, input="", env=environment)
        self.assertEqual(verb.returncode, 0, verb.stdout + verb.stderr)
        self.assertEqual(body, verb.stdout)
        self.assertIn('"name": "a",\n      "room": null', body)
        self.assertIn('"cap": null,\n      "cost_basis": "subscription"', body)
        self.assertIn('"cap": 20.0,\n      "cost_basis": "api"', body)
