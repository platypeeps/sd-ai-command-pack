"""A realm place's Overview tiles (sd:6162, sd:6164): `place_tiles` and its two routes.

What this slice promises: the tiles come from the config folder's `place-tiles.conf`, never a request. Each tile says
whether its folder is on this machine and whether its link answers, and each action its last run, read back from the
files its start left: running while the lock is held, done with the exit code, unknown when a run left no exit record.
A button runs only a command the file names, in the tile's folder; one that names no line, or a folder not here, runs
nothing (400), and a second start of a running action is a 409.

sd:6387: a tile line that names another machine's host runs nothing here. Its button writes a request row that the
host's follow job answers (system `local-repo-sync/satellite_tiles.py`), and each action reads pending until that
host's result row answers the request, then mirrors it.
"""

from __future__ import annotations

import fcntl
import json
import socket
import tempfile
import threading
import time
import tracemalloc
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from sd_dashboard import place_tiles

from support import NOW
from test_workflow_actions import BrowserSession


class Answering:
    """An HTTP server on 127.0.0.1 that answers every GET with `status`."""

    def __init__(self, status=200):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(status)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/studio"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.dict("os.environ", {"XDG_STATE_HOME": str(self.dir / "state")}))
        self.app = self.dir / "app"
        self.app.mkdir()
        self.config = self.dir / "place-tiles.conf"

    def write(self, url="-"):
        self.config.write_text(f"tile|acme|app|App|{self.app}|{url}\n"
                               "act|app|Say hi|printf hi\n"
                               "act|app|Fail|sh -c 'echo no; exit 3'\n"
                               f"tile|acme|far|Far app|{self.dir / 'elsewhere'}|-\n"
                               "act|far|Start|true\n"
                               "tile|other|x|Other realm|/|-\n", encoding="utf-8")

    def doc(self):
        return place_tiles.document("acme", now=NOW, config=self.config)

    def last(self, label):
        rows = {r["id"]: r for r in self.doc()["rows"]}
        return next(a["last"] for a in rows["app"]["actions"] if a["label"] == label)

    def start(self, action, tile="app"):
        return place_tiles.run({"realm": "acme", "tile": tile, "action": action}, config=self.config)(None)

    def wait_done(self, label):
        for _ in range(200):
            last = self.last(label)
            if last["state"] not in ("none", "running"):
                return last
            time.sleep(0.05)
        self.fail(f"{label} did not end")


class TheConfig(Case):
    def test_the_example_reads_with_no_problem_and_names_no_private_value(self):
        tiles, problems = place_tiles.parse(place_tiles.EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(problems, [])
        self.assertEqual([(t["realm"], t["id"], [a["label"] for a in t["actions"]]) for t in tiles],
                         [("work", "simulator", ["Start", "Stop", "Update"]), ("acme", "staging", ["Deploy", "Tear down", "Refresh"])])

    def test_a_line_it_cannot_read_is_named_with_its_number_and_the_rest_count(self):
        tiles, problems = place_tiles.parse("tile|acme|app|App|/x|-\nact|nope|Go|true\nact|app|Go|echo 'open\n"
                                            "act|app|Go|true\nact|app|go!|true\nbogus\n")
        self.assertEqual([a["label"] for a in tiles[0]["actions"]], ["Go"])
        self.assertEqual([p.split(":")[0] for p in problems], ["line 2", "line 3", "line 5", "line 6"])

    def test_no_file_is_an_empty_read_naming_the_file_to_copy(self):
        doc = self.doc()
        self.assertEqual((doc["state"], doc["rows"]), ("read", []))
        self.assertIn("copy place-tiles.conf.example to <config>/project-dashboard/place-tiles.conf", doc["reason"])

    def test_a_file_it_cannot_read_is_unknown_not_empty(self):
        self.config.write_bytes(b"\xff\xfe")
        doc = self.doc()
        self.assertEqual((doc["state"], doc["rows"]), ("unknown", []))
        self.assertIn("UnicodeDecodeError", doc["reason"])


class TheTiles(Case):
    def test_the_realms_tiles_in_file_order_with_whether_each_is_here(self):
        self.write()
        doc = self.doc()
        self.assertEqual([(r["id"], r["here"]) for r in doc["rows"]], [("app", True), ("far", False)])
        self.assertIn("is not on this machine", doc["rows"][1]["why"])
        self.assertEqual(doc["rows"][0]["actions"][0], {"label": "Say hi", "command": "printf hi", "last": {"state": "none"}})

    def test_the_link_answers_does_not_or_is_not_known(self):
        up = Answering(503)
        self.addCleanup(up.close)
        for url, answers in ((up.url, (True, "HTTP 503")), (f"http://127.0.0.1:{free_port()}/", (False, "nothing listens there"))):
            self.write(url)
            probe = self.doc()["rows"][0]["probe"]
            self.assertEqual((probe["answers"], probe["status"]), answers, url)
        self.write("http://192.0.2.1:9/")
        for timeout in (urllib.error.URLError(TimeoutError("timed out")), TimeoutError("timed out")):
            with mock.patch.object(place_tiles._OPENER, "open", side_effect=timeout):
                probe = self.doc()["rows"][0]["probe"]
            self.assertIsNone(probe["answers"], f"a timeout is not a down app: {timeout!r}")

    def test_a_url_http_refuses_to_send_is_that_tiles_unknown_not_the_overviews_failure(self):
        for url in ("http://127.0.0.1:1/a b", "http://127.0.0.1:nope/"):
            self.write(url)
            doc = self.doc()
            self.assertEqual([r["id"] for r in doc["rows"]], ["app", "far"], url)
            probe = doc["rows"][0]["probe"]
            self.assertEqual((probe["answers"], probe["status"]), (None, "not known: InvalidURL"), url)


class TheRun(Case):
    def test_an_action_runs_in_the_folder_and_its_exit_and_output_read_back(self):
        self.write()
        status, body = self.start("Say hi")
        self.assertEqual((status, body["repo"], body["command"]), (202, str(self.app), "printf hi"))
        last = self.wait_done("Say hi")
        self.assertEqual((last["state"], last["exit"], last["output"]), ("done", 0, "hi"))
        self.assertEqual(self.start("Fail")[0], 202)
        last = self.wait_done("Fail")
        self.assertEqual((last["state"], last["exit"], last["output"]), ("done", 3, "no\n"))

    def test_a_running_action_reads_running_and_a_second_start_is_a_409(self):
        self.write()
        state = place_tiles.state_dir() / "acme" / "app" / "say-hi"
        state.mkdir(parents=True)
        with open(state / "lock", "a+", encoding="utf-8") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            held.write("2026-09-05T08:00:00+00:00")
            held.flush()
            (state / "start.log").write_text("2026-09-05T08:00:00+00:00 printf hi in /x\n", encoding="utf-8")
            self.assertEqual(self.last("Say hi")["state"], "running")
            status, body = self.start("Say hi")
        self.assertEqual(status, 409)
        self.assertIn("App Say hi is already running", body["error"])

    def test_a_run_stopped_before_its_exit_record_is_unknown_and_the_next_start_clears_an_old_record(self):
        self.write()
        state = place_tiles.state_dir() / "acme" / "app" / "say-hi"
        state.mkdir(parents=True)
        (state / "start.log").write_text("2026-09-05T08:00:00+00:00 printf hi in /x\npartial", encoding="utf-8")
        last = self.last("Say hi")
        self.assertEqual((last["state"], last["output"]), ("unknown", "partial"))
        self.assertIn("no exit record", last["reason"])
        (state / "exit").write_text("7 2026-09-05T08:01:00Z\n", encoding="utf-8")
        self.start("Say hi")
        self.assertEqual(self.wait_done("Say hi")["exit"], 0, "the old run's exit 7 was read as the new run's")

    def test_a_long_logs_last_run_reads_only_its_tail(self):
        self.write()
        state = place_tiles.state_dir() / "acme" / "app" / "say-hi"
        state.mkdir(parents=True)
        log = state / "start.log"
        log.write_bytes(b"2026-09-05T08:00:00+00:00 printf hi in /x\n")
        with open(log, "r+b") as grown:
            grown.truncate(64 << 20)
            grown.seek(0, 2)
            grown.write(b"the end")
        tracemalloc.start()
        self.addCleanup(tracemalloc.stop)
        last = self.last("Say hi")
        peak = tracemalloc.get_traced_memory()[1]
        self.assertEqual((last["started"], last["output"][-7:], len(last["output"]), last["cut"]),
                         ("2026-09-05T08:00:00+00:00", "the end", place_tiles.TAIL, True))
        self.assertLess(peak, 1 << 20, "the read held the whole 64 MiB log")

    def test_a_name_no_line_holds_or_a_folder_not_here_runs_nothing(self):
        self.write()
        for payload, why in (({"realm": "acme", "tile": "app", "action": "rm -rf /"}, "names no action 'rm -rf /'"),
                             ({"realm": "other", "tile": "app", "action": "Say hi"}, "names no action"),
                             ({"realm": "acme", "tile": "far", "action": "Start"}, "is not on this machine"),
                             ({"realm": "acme", "tile": "app", "action": "Say hi", "command": "id"}, "Expected {realm, tile, action}")):
            with self.assertRaises(ValueError, msg=payload) as refused:
                place_tiles.run(payload, config=self.config)
            self.assertIn(why, str(refused.exception))
        self.assertFalse((place_tiles.state_dir() / "acme").exists(), "a refused start wrote state")


class TheHostedTile(Case):
    """sd:6387: a tile on another machine's host asks it through a request row, and reads its answer back."""

    def setUp(self):
        super().setUp()
        from sd_db import connect
        from sd_db.migrate import initialise

        initialise(self.dir / "sd.db")
        self.connection = connect(self.dir / "sd.db")
        self.addCleanup(self.connection.close)
        self.config.write_text(f"tile|work|sim|World simulator|{self.app}|-|far-host\n"
                               "act|sim|Start|./example-simulator.sh studio\n"
                               f"tile|work|mine|Mine|{self.app}|-|{place_tiles.this_host()}\n"
                               "act|mine|Say hi|printf hi\n", encoding="utf-8")
        self.tile = {"host": "far-host", "realm": "work", "id": "sim"}

    def rows(self, connection="default"):
        doc = place_tiles.document("work", now=NOW, config=self.config,
                                   connection=self.connection if connection == "default" else connection)
        return {r["id"]: r for r in doc["rows"]}

    def last(self, **kwargs):
        return self.rows(**kwargs)["sim"]["actions"][0]["last"]

    def ask(self):
        return place_tiles.run({"realm": "work", "tile": "sim", "action": "Start"}, config=self.config)(self.connection)

    def answer(self, request, **fields):
        from sd_db import writes

        row = {"host": "far-host", "realm": "work", "tile": "sim", "action": "Start", "request": request, "attempt": 1,
               "written": NOW, **fields}
        writes.set_setting(self.connection, place_tiles.key(place_tiles.RESULT, self.tile, "Start"), json.dumps(row))

    def test_a_line_reads_its_host_and_a_host_that_is_no_id_is_a_problem(self):
        tiles, problems = place_tiles.parse("tile|work|a|A|/x|-|far-host\ntile|work|b|B|/x|-|Far_Host\ntile|work|c|C|/x|-\n")
        self.assertEqual([(t["id"], t["host"]) for t in tiles], [("a", "far-host"), ("c", "")])
        self.assertEqual([p.split(":")[0] for p in problems], ["line 2"])

    def test_a_hosted_start_writes_a_request_row_and_runs_nothing_here(self):
        from sd_db import writes

        with mock.patch("sd_dashboard.sweep.spawn") as spawn:
            status, body = self.ask()
        self.assertEqual((status, body["host"], body["command"]), (202, "far-host", "./example-simulator.sh studio"))
        spawn.assert_not_called()
        self.assertFalse(place_tiles.state_dir().exists(), "a hosted start wrote state here")
        key = place_tiles.key(place_tiles.REQUEST, self.tile, "Start")
        self.assertEqual(key, "place_tiles.request.far_host.work.sim.start")
        row = json.loads(writes.read_settings(self.connection, [key])[key])
        self.assertEqual(row, {"id": body["requested"], "at": body["at"], "host": "far-host", "realm": "work",
                               "tile": "sim", "action": "Start"}, "the row names a command, or misses a name")

    def test_the_tile_shows_its_host_and_reads_pending_until_its_host_answers_the_request(self):
        row = self.rows()["sim"]
        self.assertEqual((row["host"], row["here"], row["why"]), ("far-host", False, ""))
        self.assertEqual(self.last(), {"state": "none", "host": "far-host"})
        asked = self.ask()[1]
        first = asked["requested"]
        self.assertEqual((self.last()["state"], self.last()["requested"]), ("pending", asked["at"]))
        self.answer(first, state="running", started="2026-09-06T12:01:00+00:00", output="up\n", cut=False)
        self.assertEqual(self.last()["state"], "running")
        second = self.ask()[1]["requested"]
        self.assertEqual(self.last()["state"], "pending", "an answer to the older request read as this one's")
        self.answer(second, state="done", started=NOW, ended=NOW, exit=0, output="ok\n", cut=False)
        last = self.last()
        self.assertEqual((last["state"], last["exit"], last["output"], last["host"]), ("done", 0, "ok\n", "far-host"))
        self.answer(second, state="refused", reason="example-simulator.sh studio is already running")
        self.assertEqual(self.last()["state"], "refused")

    def test_a_row_for_another_action_or_no_database_is_unknown_not_none(self):
        from sd_db import writes

        writes.set_setting(self.connection, place_tiles.key(place_tiles.RESULT, self.tile, "Start"),
                           json.dumps({"host": "far-host", "realm": "work", "tile": "x-sim", "action": "Start", "state": "done"}))
        last = self.last()
        self.assertEqual(last["state"], "unknown")
        self.assertIn("another action's row", last["reason"])
        last = self.last(connection=None)
        self.assertEqual(last["state"], "unknown")
        self.assertIn("no database answered", last["reason"])

    def test_a_line_that_names_this_machine_runs_here(self):
        row = self.rows()["mine"]
        self.assertEqual((row["host"], row["here"]), ("", True))
        status, body = place_tiles.run({"realm": "work", "tile": "mine", "action": "Say hi"}, config=self.config)(None)
        self.assertEqual((status, body["repo"]), (202, str(self.app)))


class TheRoutes(BrowserSession):
    def test_the_overview_read_needs_a_session_and_the_run_refuses_a_name_no_line_holds(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(place_tiles, "CONFIG", Path(folder) / "place-tiles.conf"):
            self.assertEqual(self.request("/api/place/acme/overview")[0], 403)
            status, _, body = self.request("/api/place/acme/overview", headers={"Cookie": self.cookie})
            self.assertEqual((status, json.loads(body)["state"], json.loads(body)["rows"]), (200, "read", []))
            self.assertEqual(self.request("/api/place/hoa/overview", headers={"Cookie": self.cookie})[0], 404)
            status, _, out = self.post("/api/place/tiles", {"realm": "acme", "tile": "app", "action": "Start"})
        self.assertEqual(status, 400)
        self.assertIn("Nothing ran", out["error"])

    def test_a_hosted_tiles_button_writes_its_request_and_the_overview_reads_it_pending(self):
        # sd:6387: the route hands the write its connection, and the read its own.
        with tempfile.TemporaryDirectory() as folder, mock.patch("sd_dashboard.sweep.spawn") as spawn:
            config = Path(folder) / "place-tiles.conf"
            config.write_text(f"tile|acme|sim|Simulator|{folder}|-|far-host\nact|sim|Start|./run.sh\n", encoding="utf-8")
            with mock.patch.object(place_tiles, "CONFIG", config):
                status, _, out = self.post("/api/place/tiles", {"realm": "acme", "tile": "sim", "action": "Start"})
                self.assertEqual((status, out["host"]), (202, "far-host"), out)
                _, _, body = self.request("/api/place/acme/overview", headers={"Cookie": self.cookie})
        spawn.assert_not_called()
        last = json.loads(body)["rows"][0]["actions"][0]["last"]
        self.assertEqual((last["state"], last["host"]), ("pending", "far-host"))


if __name__ == "__main__":
    unittest.main()
