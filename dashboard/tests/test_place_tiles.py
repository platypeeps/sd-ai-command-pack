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
import os
import signal
import socket
import subprocess
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
                         [("work", "simulator", ["Start", "Stop", "Update", "Refresh"]),
                          ("acme", "staging", ["Deploy", "Tear down", "Refresh"])])

    def test_a_line_it_cannot_read_is_named_with_its_number_and_the_rest_count(self):
        tiles, problems = place_tiles.parse("tile|acme|app|App|/x|-\nact|nope|Go|true\nact|app|Go|echo 'open\n"
                                            "act|app|Go|true\nact|app|go!|true\nbogus\n")
        self.assertEqual([a["label"] for a in tiles[0]["actions"]], ["Go"])
        self.assertEqual([p.split(":")[0] for p in problems], ["line 2", "line 3", "line 5", "line 6"])

    def test_an_act_line_may_end_with_its_help_and_a_four_field_line_reads_as_before(self):
        # Pack sd:7536: act|<tile>|<label>|<command>|<help>, the help optional; the button's hover shows it.
        tiles, problems = place_tiles.parse("tile|acme|app|App|/x|-\nact|app|Go|true\nact|app|Stop|./app.sh stop|Stops the app.\n")
        self.assertEqual(problems, [])
        self.assertEqual([(a["label"], a["command"], a["argv"], a["help"]) for a in tiles[0]["actions"]],
                         [("Go", "true", ["true"], ""), ("Stop", "./app.sh stop", ["./app.sh", "stop"], "Stops the app.")])

    def test_a_command_that_holds_a_pipe_is_still_refused(self):
        # The line splits on every |, as before the help field: a pipe in a command made too many fields, or a
        # quote the split leaves open, and runs nothing. An empty help field is refused like any empty field.
        tiles, problems = place_tiles.parse('tile|acme|app|App|/x|-\nact|app|Count|ls | wc -l|Counts the files.\n'
                                            'act|app|Count|sh -c "ls | wc -l"\nact|app|Go|true|\n')
        self.assertEqual(tiles[0]["actions"], [])
        self.assertEqual([p.split(":")[0] for p in problems], ["line 2", "line 3", "line 4"])

    def test_every_example_action_says_what_it_does(self):
        tiles, _ = place_tiles.parse(place_tiles.EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual([a["label"] for t in tiles for a in t["actions"] if not a["help"]], [])

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
        self.assertEqual(doc["rows"][0]["actions"][0], {"label": "Say hi", "command": "printf hi", "help": "", "last": {"state": "none"}})

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

    def test_a_name_that_resolves_slowly_is_unknown_within_the_bound(self):
        # sd:6396: the socket timeout bounds connect and read, not the name lookup before them; a slow resolver held
        # the whole Overview read past its bound.
        def slow(*args, **kwargs):
            time.sleep(5)
            raise socket.gaierror(8, "nodename nor servname provided")

        self.write("http://slow.example.test:8740/studio")
        with mock.patch.object(place_tiles, "PROBE_SECONDS", 0.2), mock.patch("socket.getaddrinfo", slow):
            began = time.monotonic()
            doc = self.doc()
            took = time.monotonic() - began
        # The lookup takes 5 s; cut at 0.2 s, the rest is slack for a loaded gate (sd:6468).
        self.assertLess(took, 3, "the read waited for the name lookup")
        probe = doc["rows"][0]["probe"]
        self.assertEqual((probe["answers"], probe["status"]), (None, "not known: no answer within 0.2 s"))

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


class TheUpdateAndRefresh(Case):
    """Pack sd:7665: every service gets Update (pull the latest code, restart nothing) and, when it has Start and Stop,
    Refresh (stop, update, start), with no act line for either. A line that names one wins."""

    def actions(self, text):
        tiles, problems = place_tiles.parse(text)
        self.assertEqual(problems, [])
        return {t["id"]: [(a["label"], a["argv"]) for a in t["actions"]] for t in tiles}

    def git(self, *args, cwd=None):
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.test", "-c", "commit.gpgsign=false",
                        *args], cwd=cwd, check=True, capture_output=True, timeout=60)

    def test_a_checkout_gets_update_and_one_with_start_and_stop_also_refresh(self):
        (self.app / ".git").mkdir()
        site = self.dir / "site"
        (site / ".git").mkdir(parents=True)
        got = self.actions(f"tile|acme|app|App|{self.app}|-\nact|app|Start|./app.sh start\nact|app|Stop|./app.sh stop\n"
                           f"act|app|Status|./app.sh status\ntile|acme|site|Site|{site}|-\nact|site|Deploy|./deploy.sh\n")
        self.assertEqual(got["app"], [("Start", ["./app.sh", "start"]), ("Stop", ["./app.sh", "stop"]),
                                      ("Status", ["./app.sh", "status"]), ("Update", ["git", "pull", "--ff-only"]),
                                      ("Refresh", [])])
        self.assertEqual(got["site"], [("Deploy", ["./deploy.sh"]), ("Update", ["git", "pull", "--ff-only"])])
        update = place_tiles.parse(f"tile|acme|app|App|{self.app}|-\n")[0][0]["actions"][0]
        self.assertEqual(update["command"], "git pull --ff-only")
        self.assertIn("restarts nothing", update["help"])
        refresh = place_tiles.parse(f"tile|acme|app|App|{self.app}|-\nact|app|Start|./app.sh start\n"
                                    "act|app|Stop|/bin/zsh -lc \"echo $HOME\"\n")[0][0]["actions"][-1]
        # The hover names each step's command as its line split it; Start runs through its own button (`refresh`).
        self.assertEqual((refresh["command"], refresh["refresh"]),
                         ("/bin/zsh -lc 'echo $HOME'; git pull --ff-only && Start: ./app.sh start", True))

    def test_a_folder_inside_another_checkout_or_not_here_gets_neither_and_a_hosted_one_both(self):
        # A tool folder inside a pinned checkout (no .git of its own): pulling there moves the whole checkout, which its
        # lane owns. A folder not here runs nothing anyway. A hosted tile's host has the folder and decides there.
        got = self.actions(f"tile|acme|app|App|{self.app}|-\nact|app|Start|s\nact|app|Stop|t\n"
                           f"tile|acme|gone|Gone|{self.dir / 'gone'}|-\nact|gone|Start|s\nact|gone|Stop|t\n"
                           f"tile|acme|far|Far|{self.dir / 'gone'}|-|far-host\nact|far|Start|s\nact|far|Stop|t\n")
        self.assertEqual([label for label, _ in got["app"]], ["Start", "Stop"])
        self.assertEqual([label for label, _ in got["gone"]], ["Start", "Stop"])
        self.assertEqual([label for label, _ in got["far"]], ["Start", "Stop", "Update", "Refresh"])

    def test_a_line_that_names_update_or_refresh_wins_and_refresh_runs_that_update(self):
        got = self.actions(f"tile|acme|app|App|{self.app}|-\nact|app|Start|s\nact|app|Stop|t\nact|app|update|./app.sh update\n"
                           f"tile|acme|own|Own|{self.app}|-|far-host\nact|own|Start|s\nact|own|Stop|t\nact|own|Refresh|./re.sh\n")
        self.assertEqual(got["app"][2:], [("update", ["./app.sh", "update"]), ("Refresh", [])])
        refresh = place_tiles.parse(f"tile|acme|app|App|{self.app}|-\nact|app|Start|s\nact|app|Stop|t\n"
                                    "act|app|update|./app.sh update\n")[0][0]["actions"][-1]
        self.assertEqual(refresh["command"], "t; ./app.sh update && Start: s")
        self.assertEqual(got["own"][2:], [("Refresh", ["./re.sh"]), ("Update", ["git", "pull", "--ff-only"])])

    def test_refresh_stops_updates_then_starts_and_starts_nothing_after_a_failed_update(self):
        for update, runs, code in (('sh -c "echo update >> runs"', "stop\nupdate\nstart\n", 0),
                                   ('sh -c "echo update >> runs; exit 4"', "stop\nupdate\n", 4)):
            (self.app / "runs").unlink(missing_ok=True)
            self.config.write_text(f"tile|acme|app|App|{self.app}|-\nact|app|Start|sh -c \"echo start >> runs\"\n"
                                   "act|app|Stop|sh -c \"echo stop >> runs\"\n"
                                   f"act|app|Update|{update}\n", encoding="utf-8")
            self.assertEqual(self.start("Refresh")[0], 202)
            last = self.wait_done("Refresh")
            if code == 0:
                # Start runs under its own lock, after Refresh pressed it: its line lands when it ends.
                self.assertEqual(self.wait_done("Start")["exit"], 0)
            self.assertEqual(((self.app / "runs").read_text(encoding="utf-8"), last["exit"]), (runs, code), update)
        self.assertIn("Update exited 4, so Start was not pressed", last["output"])

    # Review of sd:7665: a Refresh that ran Start inline held a foreground server under Refresh's lock, so Start could
    # launch a second server, Refresh read running for the server's life, and the next Refresh was a 409 until Stop.
    def serve(self):
        """A tile whose Start runs a foreground server; each server adds its pid to `pids`, and Stop ends them all."""
        self.config.write_text(f"tile|acme|app|App|{self.app}|-\n"
                               "act|app|Start|sh -c 'echo $$ >> pids; echo start >> runs; exec sleep 60'\n"
                               "act|app|Stop|sh -c 'kill $(cat pids) 2>/dev/null; : > pids; echo stop >> runs'\n"
                               "act|app|Update|sh -c 'echo update >> runs'\n", encoding="utf-8")
        self.addCleanup(self.stop_servers)
        status, body = self.start("Refresh")
        self.assertEqual(status, 202, body)

    def servers(self):
        """The pids of the servers running, once the first one wrote its pid (at most 10 s)."""
        for _ in range(200):
            pids = (self.app / "pids").read_text(encoding="utf-8").split() if (self.app / "pids").is_file() else []
            if pids:
                return pids
            time.sleep(0.05)
        self.fail("no server started")

    def stop_servers(self):
        """Ends every test server and waits for each lock, so the folder's cleanup races no exit-record write."""
        for pid in (self.app / "pids").read_text(encoding="utf-8").split() if (self.app / "pids").is_file() else []:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        for action in ("start", "refresh"):
            lock = place_tiles.state_dir() / "acme" / "app" / action / "lock"
            if lock.is_file():
                with open(lock, "a+", encoding="utf-8") as handle:
                    fcntl.flock(handle, fcntl.LOCK_EX)

    def test_refresh_ends_once_it_has_started_start(self):
        self.serve()
        last = self.wait_done("Refresh")
        self.assertEqual((last["state"], last["exit"]), ("done", 0))
        self.servers()
        self.assertEqual(self.last("Start")["state"], "running", "the server is not Start's")

    def test_start_after_a_refresh_is_a_409_not_a_second_server(self):
        self.serve()
        self.servers()
        self.assertEqual(self.start("Start")[0], 409, "Start launched a second server")
        self.assertEqual(len(self.servers()), 1)

    def test_a_second_refresh_restarts_the_server_and_is_no_409(self):
        self.serve()
        first = self.servers()
        self.wait_done("Refresh")
        status, body = self.start("Refresh")
        self.assertEqual(status, 202, f"the second Refresh was refused: {body}")
        self.assertEqual(self.wait_done("Refresh")["exit"], 0)
        second = self.servers()
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first, second, "the old server still runs")
        self.assertEqual((self.app / "runs").read_text(encoding="utf-8"), "stop\nupdate\nstart\n" * 2)

    def test_update_pulls_the_newest_commit_into_the_checkout(self):
        # No global or system git config: a signing or hook setting of the machine's is not this test's.
        self.enterContext(mock.patch.dict("os.environ", {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}))
        origin, clone = self.dir / "origin", self.dir / "clone"
        self.git("init", "-q", "-b", "main", str(origin))
        self.git("commit", "-q", "--allow-empty", "-m", "one", cwd=origin)
        self.git("clone", "-q", str(origin), str(clone))
        self.git("commit", "-q", "--allow-empty", "-m", "two", cwd=origin)
        self.config.write_text(f"tile|acme|app|App|{clone}|-\nact|app|Start|true\n", encoding="utf-8")
        self.assertEqual(self.start("Update")[0], 202)
        self.assertEqual(self.wait_done("Update")["exit"], 0)
        head = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=clone, capture_output=True, text=True, check=True)
        self.assertEqual(head.stdout.strip(), "two")


class TheRefreshSteps(Case):
    """Review round 2 of sd:7665, one test per row of the failure table in the PR body: Refresh's Stop, Update and Start
    each move state, and a step that fails, hangs or is cut short leaves Refresh ended, its lock free, and no Update
    over a server that may still run. `refresh` runs here in-process, so the bounds can be patched."""

    servers, stop_servers = TheUpdateAndRefresh.servers, TheUpdateAndRefresh.stop_servers
    SERVER = "act|app|Start|sh -c 'echo $$ >> pids; echo start >> runs; exec sleep 60'\n"

    def tiles(self, stop, update="sh -c 'echo update >> runs'", url="-"):
        self.config.write_text(f"tile|acme|app|App|{self.app}|{url}\n{self.SERVER}act|app|Stop|{stop}\n"
                               f"act|app|Update|{update}\n", encoding="utf-8")
        self.addCleanup(self.stop_servers)

    def refresh(self):
        return place_tiles.refresh("acme", "app", str(self.config))

    def runs(self):
        return (self.app / "runs").read_text(encoding="utf-8") if (self.app / "runs").is_file() else ""

    def running_server(self):
        self.assertEqual(self.start("Start")[0], 202)
        return self.servers()

    def test_a_file_that_lost_its_steps_runs_nothing(self):
        self.config.write_text(f"tile|acme|app|App|{self.app}|-\n{self.SERVER}", encoding="utf-8")
        self.assertEqual(self.refresh(), 2)
        self.assertEqual(self.runs(), "")
        self.config.write_bytes(b"\xff\xfe")
        self.assertEqual(self.refresh(), 2, "a file that does not read is no traceback")

    def test_a_stop_that_fails_runs_no_update(self):
        self.tiles("sh -c 'echo stop >> runs; exit 3'")
        self.running_server()
        with mock.patch.object(place_tiles, "START_WAIT", 0.2, create=True):
            self.assertEqual(self.refresh(), 3)
        self.assertEqual(self.runs(), "start\nstop\n", "Update ran over a server Stop did not stop")

    def test_a_failed_stop_of_a_stopped_service_whose_link_refuses_goes_on(self):
        # Already stopped: Start's lock is free and its link refuses, so Stop's exit is not a server still running.
        self.tiles("sh -c 'echo stop >> runs; exit 1'", url=f"http://127.0.0.1:{free_port()}/")
        self.assertEqual(self.refresh(), 0)
        self.servers()
        self.assertEqual(self.runs(), "stop\nupdate\nstart\n")

    def test_a_failed_stop_with_no_link_to_ask_runs_no_update(self):
        # No link to ask: whether it still runs is not known, and not known is not stopped.
        self.tiles("sh -c 'echo stop >> runs; exit 1'")
        self.assertEqual(self.refresh(), 1)
        self.assertEqual(self.runs(), "stop\n")

    def test_a_stop_that_leaves_the_server_running_runs_no_update(self):
        self.tiles("sh -c 'echo stop >> runs'")
        self.running_server()
        with mock.patch.object(place_tiles, "STOP_WAIT", 0.5, create=True), \
                mock.patch.object(place_tiles, "START_WAIT", 0.2, create=True):
            self.assertEqual(self.refresh(), 1)
        self.assertEqual(self.runs(), "start\nstop\n", "Update ran while Start's server still ran")

    def test_a_hung_stop_or_update_is_ended_with_its_children_and_refresh_ends(self):
        hang = "sh -c 'sleep 30 & echo $! > hung; wait'"
        for stop, update, runs in ((hang, "sh -c 'echo update >> runs'", ""), ("true", hang, "")):
            (self.app / "hung").unlink(missing_ok=True)
            self.tiles(stop, update)
            began = time.monotonic()
            with mock.patch.object(place_tiles, "STEP_SECONDS", 0.5, create=True):
                code = self.refresh()
            self.assertLess(time.monotonic() - began, 10, "Refresh waited on the hung step")
            self.assertEqual((code, self.runs()), (124, runs), "a step ran after the hung one")
            pid = int((self.app / "hung").read_text(encoding="utf-8"))
            for _ in range(100):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                self.fail("the hung step's child still runs")

    def test_a_start_refused_or_gone_after_the_update_is_named_and_ends(self):
        self.tiles("true")
        for answer, code in ((lambda payload, config: (lambda c: (409, {"error": "App Start is already running"})), 1),
                             (mock.Mock(side_effect=ValueError("Nothing ran: no action 'Start'")), 2)):
            with mock.patch.object(place_tiles, "run", answer), mock.patch.object(place_tiles, "START_WAIT", 0.2, create=True):
                self.assertEqual(self.refresh(), code)

    def test_a_refresh_cut_short_after_stop_leaves_its_lock_free_and_the_next_one_finishes(self):
        # Refresh's own process is killed between Stop and Start (a reboot, a kill): its exit record names that, its
        # lock is free, and the next Refresh stops nothing that runs, updates and starts.
        self.tiles("sh -c 'kill $(cat pids) 2>/dev/null; : > pids; echo stop >> runs'", update="sh -c 'kill -9 $PPID'")
        self.running_server()
        self.assertEqual(self.start("Refresh")[0], 202)
        self.assertNotEqual(self.wait_done("Refresh")["exit"], 0)
        self.tiles("sh -c 'kill $(cat pids) 2>/dev/null; : > pids; echo stop >> runs'")
        self.assertEqual(self.start("Refresh")[0], 202, "the cut Refresh still holds its lock")
        self.assertEqual(self.wait_done("Refresh")["exit"], 0)
        self.servers()
        self.assertEqual(self.runs(), "start\nstop\nstop\nupdate\nstart\n")

    def test_a_hosted_refresh_says_the_start_button_here_does_not_show_its_start(self):
        # The host's Refresh starts Start there under its own lock and writes no Start row, so the hub's Start reads
        # its last answered request: a limit the button's hover says.
        refresh = place_tiles.parse(f"tile|work|sim|Sim|{self.app}|-|far-host\nact|sim|Start|s\nact|sim|Stop|t\n")[0][0]["actions"][-1]
        self.assertEqual(refresh["label"], "Refresh")
        self.assertIn("the Start button here does not show", refresh["help"])


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
        # The detached child holds the action's lock until it exits; wait for it, or the temporary folder's
        # cleanup races its exit-file write (gate 2026-10-30 02:09 MDT: "Directory not empty").
        lock = next(self.dir.rglob("say-hi/lock"))
        with open(lock, "a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
        self.assertTrue((lock.parent / "exit").is_file(), "the child wrote its exit line before it let go")


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
