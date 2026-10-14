"""Hub failover slice 2, the fence (sd:4044, design D5 in system's `docs/work/2026-10-10-hub-failover/`).

A machine holds the hub role only while its tailnet name matches the fleet
setting `sd.hub_name`. A returning old hub still has its database and no
`hub.json`, so without the fence it serves, runs lanes and pushes as the hub.
Each caller reads four answers: `holder` and `off` (no setting: a fleet that
never named its hub) go on; `elsewhere` (another node holds the name) and
`unknown` (the setting or Tailscale does not answer) refuse.

`tailscale` is the harness stub on PATH; no test reaches the real daemon.
"""

from __future__ import annotations

import ipaddress
import io
import os
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from sd_db import database, hub, initialise, remote, serve, ship, tailnet, upsert_repo, writes
from sd_db.testing import Stubs

from . import support

HUB_NAME = "hub.example.test"
REPOSITORY = "example/one"
REMOTE = "git@github.com:example/one.git"


class StubCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stubs = Stubs(self.root / "stubs", names=("tailscale",))
        self.enterContext(mock.patch.dict(os.environ, self.stubs.environment()))
        self.enterContext(mock.patch.object(hub, "_name_failed", None, create=True))
        self.path = self.root / "sd.db"
        initialise(self.path)

    def name_hub(self, value: str | None) -> None:
        connection = database.connect(self.path)
        try:
            writes.set_setting(connection, "sd.hub_name", value)
        finally:
            connection.close()

    def node(self, dnsname: str | None = HUB_NAME + ".", **state) -> None:
        if dnsname is not None:
            state["dnsname"] = dnsname
        self.stubs.state("tailscale", {"ips": ["100.64.0.10"], **state})

    def asked(self) -> list[list[str]]:
        return [call.argv for call in self.stubs.calls("tailscale")]


class TheRole(StubCase):
    def role(self) -> hub.Role:
        return hub.role_at(self.path)

    def test_the_named_node_holds_the_role(self):
        self.name_hub(HUB_NAME)
        self.node("Hub.Example.Test.")
        found = self.role()
        self.assertEqual((found.state, found.holder), ("holder", HUB_NAME))

    def test_a_bare_machine_name_matches_the_first_label(self):
        self.name_hub("hub")
        self.node()
        self.assertEqual(self.role().state, "holder")
        self.node("hub-2.example.test.")
        self.assertEqual(self.role().state, "elsewhere")

    def test_another_node_is_elsewhere_and_named(self):
        self.name_hub(HUB_NAME)
        self.node("old-hub.example.test.")
        found = self.role()
        self.assertEqual(found.state, "elsewhere")
        self.assertIn(f"sd.hub_name names {HUB_NAME}, and this node is old-hub.example.test", found.reason)

    def test_no_setting_is_off_and_asks_tailscale_nothing(self):
        self.node("old-hub.example.test.")
        found = self.role()
        self.assertEqual((found.state, found.refuses), ("off", False))
        self.assertIn("sd.hub_name is unset, so the fence is off", found.reason)
        self.name_hub(HUB_NAME)
        self.name_hub(None)
        self.assertEqual(self.role().state, "off", "a cleared row reads unset")
        self.assertEqual(self.asked(), [])

    def test_a_tailscale_that_does_not_answer_is_unknown(self):
        self.name_hub(HUB_NAME)
        for state in ({"backend": "Stopped"}, {"backend": "NeedsLogin"}, {"dnsname": ""}):
            with self.subTest(state=state):
                hub._name_failed = None
                self.node(**state)
                found = self.role()
                self.assertEqual(found.state, "unknown")
                self.assertIn("Tailscale does not name this node", found.reason)

    def test_an_unreadable_setting_row_is_unknown(self):
        connection = database.connect(self.path)
        connection.execute("INSERT INTO state (kind, key, body, timestamp) VALUES ('setting', ?, 'nope', '2026')",
                           (hub.HUB_NAME,))
        connection.close()
        self.node()
        found = self.role()
        self.assertEqual(found.state, "unknown")
        self.assertIn("does not read", found.reason)

    def test_a_database_that_does_not_open_is_unknown(self):
        self.assertEqual(hub.role_at(self.root / "missing.db").state, "unknown")

    def test_a_rename_refuses_the_next_check(self):
        """Codex pass: a held name admitted a renamed node for 30 s; a name is read at every check."""
        self.name_hub(HUB_NAME)
        self.node()
        self.assertEqual(self.role().state, "holder")
        self.node("old-hub.example.test.")
        self.assertEqual(self.role().state, "elsewhere")

    def test_a_failed_read_refuses_again_without_asking(self):
        self.name_hub(HUB_NAME)
        self.node(backend="Stopped")
        self.assertEqual(self.role().state, "unknown")
        self.node()
        for _ in range(5):
            self.assertEqual(self.role().state, "unknown")
        self.assertEqual(len(self.asked()), 1, "a stalled daemon costs a lane run one timeout")
        with mock.patch.object(hub.time, "monotonic", return_value=hub.time.monotonic() + hub.NAME_SECONDS + 1):
            self.assertEqual(self.role().state, "holder")


class TheLaneHost(StubCase):
    """`hosts_lane` on this machine's own database: the fence decides."""

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(ship, "this_host", return_value="build-2"))
        self.enterContext(mock.patch.object(ship, "served_by", return_value=None))

    def hosts(self, lane_host: str | None = None) -> bool:
        connection = database.connect(self.path)
        try:
            upsert_repo(connection, "/srv/one", remote=REMOTE)
            connection.execute("UPDATE repo SET lane_host = ? WHERE path = '/srv/one'", (lane_host,))
            return ship.hosts_lane(connection, self.path, REPOSITORY)
        finally:
            connection.close()

    def test_the_holder_runs_its_lanes(self):
        self.name_hub(HUB_NAME)
        self.node()
        self.assertTrue(self.hosts())
        self.assertTrue(self.hosts("build-2"))

    def test_a_demoted_hub_runs_no_lane_and_names_the_holder(self):
        self.name_hub(HUB_NAME)
        self.node("old-hub.example.test.")
        for lane_host in (None, "build-2"):
            with self.subTest(lane_host=lane_host), self.assertRaises(ship.LaneElsewhere) as caught:
                self.hosts(lane_host)
            self.assertEqual(caught.exception.code, "lane_elsewhere")
            self.assertIn(f"runs on the hub, {HUB_NAME}, not on this machine", str(caught.exception))
            self.assertNotIn("lane-host", str(caught.exception), "moving the lane here is no remedy")

    def test_no_setting_runs_the_lanes_as_before(self):
        self.node("old-hub.example.test.")
        self.assertTrue(self.hosts())
        self.assertEqual(self.asked(), [])

    def test_unknown_runs_no_lane(self):
        self.name_hub(HUB_NAME)
        self.node(backend="Stopped")
        with self.assertRaisesRegex(ship.LaneUnknown, "Tailscale does not name this node"):
            self.hosts()

    def test_a_lane_elsewhere_never_asks_the_fence(self):
        self.assertFalse(self.hosts("build-3"))
        self.assertEqual(self.asked(), [])

    def test_the_ship_lock_refuses_on_a_demoted_hub_and_locks_nothing(self):
        self.name_hub(HUB_NAME)
        self.node("old-hub.example.test.")
        with self.assertRaises(ship.LaneElsewhere):
            self.hosts()
        with self.assertRaises(ship.LaneElsewhere):
            with ship.repository_lock(self.path, REPOSITORY):
                self.fail("the lock was taken")
        self.assertFalse((self.root / ship.LOCK_DIRECTORY).exists())


class TheServer(StubCase):
    """`sd-db serve` without `--loopback` at start; `--loopback` leaves the machine for nobody."""

    def run_serve(self, *arguments) -> subprocess.CompletedProcess:
        home = self.root / "home"
        environment = {**os.environ, "PYTHONPATH": str(support.LIB), "HOME": str(home),
                       "XDG_DATA_HOME": str(home / ".local" / "share")}
        return subprocess.run(support.sd_db_argv("serve", *arguments, "--database", str(self.path)),
                              capture_output=True, text=True, env=environment, cwd=support.LIB, timeout=60)

    def test_a_demoted_hub_does_not_listen_and_names_the_holder(self):
        self.name_hub(HUB_NAME)
        self.node("old-hub.example.test.", ips=["100.100.100.100"])
        done = self.run_serve("--port", "0")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn(f"this machine is not the hub: sd.hub_name names {HUB_NAME}", done.stderr)
        self.assertNotIn("cannot listen", done.stderr)
        self.assertEqual(sorted(p.name for p in self.root.glob("sd.db.serve.*")), [])

    def test_unknown_does_not_listen(self):
        self.name_hub(HUB_NAME)
        self.node(dnsname="", ips=["100.100.100.100"])
        done = self.run_serve("--port", "0")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("this machine is not the hub: Tailscale does not name this node", done.stderr)

    def test_no_setting_goes_on_to_bind(self):
        self.node(ips=["100.100.100.100"])
        done = self.run_serve("--port", "0")
        self.assertIn("cannot listen on 100.100.100.100:0", done.stderr)

    def test_the_holder_goes_on_to_bind(self):
        # 100.100.100.100 is Tailscale's resolver and never a node's, so the bind fails past the fence.
        self.name_hub(HUB_NAME)
        self.node(ips=["100.100.100.100"])
        done = self.run_serve("--port", "0")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("cannot listen on 100.100.100.100:0", done.stderr)
        self.assertEqual(self.asked(), [["status", "--json"]], "one status call names the node and its name")

    def test_loopback_is_not_fenced(self):
        self.node("old-hub.example.test.")
        refused: list[str] = []
        with mock.patch.object(serve, "Server", side_effect=OSError("stop here")):
            code = serve.serve(0, self.path, stream=mock.Mock(write=refused.append), loopback=True)
        self.assertEqual(code, 1)
        self.assertIn("cannot listen on 127.0.0.1:0", "".join(refused))
        self.assertEqual(self.asked(), [])


class TheLiveServer(StubCase):
    """A server that started as the hub and is demoted while it runs (the 2026-10-14 review of sd:4044).

    An old hub that slept, or lost its network, keeps its process; the
    console renames it meanwhile. The check at start does not see that, so
    every session frame asks the fence again, within `serve.FENCE_SECONDS`
    and never across a wall-clock jump (a sleep).
    """

    OPERATOR = "operator@example.test"
    HUB_IP = "100.64.0.10"
    SATELLITE = "100.64.0.20"

    def setUp(self):
        super().setUp()
        local = database.connect(self.path)
        local.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        local.close()
        self.name_hub(HUB_NAME)
        self.rename(HUB_NAME + ".")
        self.stream = io.StringIO()
        node = tailnet.Node(frozenset({ipaddress.ip_address(self.HUB_IP)}), self.OPERATOR,
                            ipaddress.IPv4Address("127.0.0.1"), HUB_NAME)
        self.server = serve.Server(0, self.path, serve.Log(self.stream), "", self.root / "unused.token", node)
        self.addCleanup(self.server.server_close)

    def rename(self, dnsname: str) -> None:
        whois = {self.SATELLITE: {"Node": {"Addresses": [f"{self.SATELLITE}/32"], "Tags": []},
                                  "UserProfile": {"LoginName": self.OPERATOR}}}
        self.node(dnsname, ips=[self.HUB_IP], login=self.OPERATOR, whois=whois)

    def rows(self) -> int:
        watch = database.connect(self.path, write=False)
        try:
            return watch.execute("SELECT count(*) FROM probe").fetchone()[0]
        finally:
            watch.close()

    def session(self, *frames, between=None, after: int = 0) -> list:
        """Open, then each frame; `between` runs after answer `after` (0 is the open's). `None` once the hub hangs up."""
        ours, theirs = socket.socketpair()
        ours.settimeout(30)

        def handle():
            try:
                serve.Session(theirs, (self.SATELLITE, 45678), self.server)
            finally:
                theirs.close()

        handler = threading.Thread(target=handle, daemon=True)
        handler.start()
        answers: list = []
        opening = remote.request("open", path=None, write=True, create=False, busy_timeout=5000,
                                 token="", **remote.handshake())
        try:
            for index, frame in enumerate((opening, *frames)):
                try:
                    remote.send_frame(ours, frame)
                    answers.append(remote.read_frame(ours))
                except (EOFError, OSError):
                    answers.append(None)
                    break
                if index == after and between is not None:
                    between()
        finally:
            ours.close()
            handler.join(30)
        self.assertFalse(handler.is_alive(), "the session handler did not end")
        return answers

    def test_a_rename_after_start_refuses_the_next_open(self):
        self.enterContext(mock.patch.object(serve, "FENCE_SECONDS", 0.0))
        self.assertTrue(self.session(remote.request("close"))[0]["ok"])
        self.rename("old-hub.example.test.")
        answers = self.session(remote.request("execute", sql="INSERT INTO probe (name) VALUES ('stale')", params=None))
        self.assertFalse(answers[0]["ok"], answers)
        self.assertIn(f"this machine is not the hub: sd.hub_name names {HUB_NAME}", answers[0]["error"]["text"])
        self.assertEqual(answers[1:], [None], "a fenced server answered a second frame")
        self.assertEqual(self.rows(), 0)

    def test_a_rename_mid_session_refuses_the_write_and_rolls_back(self):
        self.enterContext(mock.patch.object(serve, "FENCE_SECONDS", 0.0))
        rid = remote.new_request_id()
        answers = self.session(
            remote.request("execute", sql="BEGIN IMMEDIATE", params=None, rid=rid),
            remote.request("execute", sql="INSERT INTO probe (name) VALUES ('before')", params=None),
            remote.request("execute", sql="INSERT INTO probe (name) VALUES ('after')", params=None),
            remote.request("execute", sql="COMMIT", params=None, rid=rid),
            between=None)
        self.assertTrue(all(a and a["ok"] for a in answers), answers)
        self.assertEqual(self.rows(), 2)

        def demote():
            self.rename("old-hub.example.test.")
        second = remote.new_request_id()
        answers = self.session(
            remote.request("execute", sql="BEGIN IMMEDIATE", params=None, rid=second),
            remote.request("execute", sql="INSERT INTO probe (name) VALUES ('stale')", params=None),
            remote.request("execute", sql="COMMIT", params=None, rid=second),
            remote.request("close"),
            between=demote, after=2)
        self.assertTrue(all(a["ok"] for a in answers[:3]), answers)
        self.assertFalse(answers[3]["ok"], answers)
        self.assertIn("this machine is not the hub", answers[3]["error"]["text"])
        self.assertEqual(answers[4:], [None], "a fenced server answered a second frame")
        self.assertEqual(self.rows(), 2, "a demoted hub wrote a row")
        self.assertIn("no longer the hub", self.stream.getvalue())

    def test_the_answer_stands_a_few_seconds_but_never_across_a_sleep(self):
        clock = {"monotonic": 1000.0, "time": 2_000_000_000.0}
        self.enterContext(mock.patch.object(serve.time, "monotonic", lambda: clock["monotonic"]))
        self.enterContext(mock.patch.object(serve.time, "time", lambda: clock["time"]))
        self.assertIsNone(self.server.fence())
        self.rename("old-hub.example.test.")
        clock["monotonic"] += 1
        clock["time"] += 1
        self.assertIsNone(self.server.fence(), "asked again inside the window")
        self.assertEqual(self.asked().count(["status", "--json"]), 1)
        # A sleep: the wall clock moves an hour, the monotonic clock does not.
        clock["time"] += 3600
        self.assertIn(f"sd.hub_name names {HUB_NAME}", self.server.fence() or "")
        clock["monotonic"] += serve.FENCE_SECONDS + 1
        clock["time"] += serve.FENCE_SECONDS + 1
        self.rename(HUB_NAME + ".")
        self.assertIsNone(self.server.fence(), "a refusal outlived its window")

    def test_no_setting_serves_as_before_and_asks_tailscale_nothing(self):
        self.name_hub(None)
        self.enterContext(mock.patch.object(serve, "FENCE_SECONDS", 0.0))
        answers = self.session(remote.request("execute", sql="INSERT INTO probe (name) VALUES ('x')", params=None,
                                              rid=remote.new_request_id()))
        self.assertTrue(all(a and a["ok"] for a in answers), answers)
        self.assertEqual(self.asked().count(["status", "--json"]), 0)


class TheVerb(StubCase):
    """`sd-db fence`: what shell callers outside the library read (hub-pin, the NAS copy)."""

    def fence(self) -> subprocess.CompletedProcess:
        home = self.root / "home"
        data = database.local_path(home).parent
        data.mkdir(parents=True, exist_ok=True)
        if not database.local_path(home).exists():
            os.link(self.path, database.local_path(home))
        environment = {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(home / ".local" / "share")}
        return subprocess.run(support.sd_db_argv("fence"), capture_output=True, text=True, env=environment,
                              cwd=support.LIB, timeout=60)

    def test_exit_one_only_where_the_fence_refuses(self):
        self.node()
        done = self.fence()
        self.assertEqual((done.returncode, done.stdout.split(":")[1:3]), (0, [" fence", " off"]), done.stderr)
        self.name_hub(HUB_NAME)
        done = self.fence()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("sd-db: fence: holder:", done.stdout)
        self.node("old-hub.example.test.")
        done = self.fence()
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"sd-db: fence: elsewhere: sd.hub_name names {HUB_NAME}", done.stdout)
        self.node(backend="Stopped")
        done = self.fence()
        self.assertEqual(done.returncode, 1)
        self.assertIn("sd-db: fence: unknown: Tailscale does not name this node", done.stdout)

    def test_a_satellite_is_elsewhere_and_asks_nobody(self):
        config = self.root / "home" / ".config" / "sd" / "hub.json"
        config.parent.mkdir(parents=True)
        config.write_text('{"hub": "hub.example.test", "port": 8769}')
        done = self.fence()
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("sd-db: fence: elsewhere: this machine is a satellite of hub.example.test", done.stdout)
        self.assertEqual(self.asked(), [])


class TheName(StubCase):
    def test_this_name_is_the_magicdns_name_without_its_dot(self):
        self.node("Hub.Example.Test.")
        self.assertEqual(tailnet.this_name(), HUB_NAME)
        self.assertEqual(tailnet.this_node().name, HUB_NAME)


if __name__ == "__main__":
    unittest.main()
