"""`dashboard.sh shots`: each touched page dark and light, desktop and phone width (sd:6007).

A fake Chrome speaks the DevTools pipe protocol on fds 3 and 4, so these tests
need no browser and check what the capture asked for, not what Chrome drew.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from sd_dashboard import shots
from sd_db import connect, create_item
from sd_db.migrate import initialise

PNG = b"\x89PNG\r\n\x1a\nfake"

FAKE = textwrap.dedent('''\
    import base64, json, os, select, sys, time
    log = open(os.environ["FAKE_LOG"], "a")
    mode = os.environ.get("FAKE_MODE", "ok")
    outbox = os.fdopen(4, "wb")
    buffer, loads = b"", 0

    def send(message):
        outbox.write(json.dumps(message).encode() + b"\\0")
        outbox.flush()

    while True:
        while b"\\0" not in buffer:
            chunk = os.read(3, 65536)
            if not chunk:
                sys.exit(0)
            buffer += chunk
        raw, buffer = buffer.split(b"\\0", 1)
        message = json.loads(raw)
        method, reply = message["method"], {}
        log.write(json.dumps(message) + "\\n")
        log.flush()
        if method == "Target.createTarget":
            time.sleep(float(os.environ.get("FAKE_TARGET_DELAY", "0")))
            reply = {"targetId": "T"}
        elif method == "Target.attachToTarget":
            reply = {"sessionId": "S"}
        elif method == "Page.navigate":
            loads += 1
            reply = {"frameId": "F", "loaderId": "L%d" % loads}
        elif method == "Page.getLayoutMetrics":
            reply = {"cssContentSize": {"x": 0, "y": 0, "width": 375, "height": 9000}}
        elif method == "Page.captureScreenshot":
            reply = {"data": base64.b64encode(b"\\x89PNG\\r\\n\\x1a\\nfake").decode()}
        send({"id": message["id"], "result": reply})
        if method == "Page.navigate" and mode != "never":
            if mode == "stale":
                # The client must keep waiting: a command within 0.3 s means it took the old load's idle.
                event = {"frameId": "F", "loaderId": "OLD", "name": "networkIdle"}
                send({"method": "Page.lifecycleEvent", "params": event, "sessionId": "S"})
                if select.select([3], [], [], 0.3)[0]:
                    log.write(json.dumps({"early": True}) + "\\n")
            event = {"frameId": "F", "loaderId": "L%d" % loads, "name": "networkIdle"}
            send({"method": "Page.lifecycleEvent", "params": event, "sessionId": "S"})
        if method == "Browser.close":
            sys.exit(0)
''')


class FakeChrome(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.chrome = self.root / "chrome"
        self.chrome.write_text(f"#!{sys.executable}\n{FAKE}")
        self.chrome.chmod(0o755)
        self.log = self.root / "log.jsonl"
        self.out = self.root / "out"
        patch = mock.patch.dict(os.environ, {"FAKE_LOG": str(self.log)})
        patch.start()
        self.addCleanup(patch.stop)

    def sent(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]


class Capture(FakeChrome):
    def test_each_page_is_drawn_dark_and_light_at_desktop_and_phone_width(self) -> None:
        files = shots.capture(str(self.chrome), "http://127.0.0.1:9", ["/tasks", "/"], self.out)
        self.assertEqual([f.name for f in files], [
            "tasks-dark-1440.png", "tasks-dark-375.png", "tasks-light-1440.png", "tasks-light-375.png",
            "root-dark-1440.png", "root-dark-375.png", "root-light-1440.png", "root-light-375.png"])
        for file in files:
            self.assertEqual(file.read_bytes(), PNG)
        sent = self.sent()
        themes = [m["params"]["source"] for m in sent if m["method"] == "Page.addScriptToEvaluateOnNewDocument"]
        self.assertEqual(themes, [shots.THEME % theme for theme in ("dark", "dark", "light", "light")] * 2)
        sizes = [(m["params"]["width"], m["params"]["mobile"])
                 for m in sent if m["method"] == "Emulation.setDeviceMetricsOverride"]
        self.assertEqual(sizes[:2], [(1440, False), (375, True)])
        urls = [m["params"]["url"] for m in sent if m["method"] == "Page.navigate"]
        self.assertEqual(urls, ["http://127.0.0.1:9/tasks"] * 4 + ["http://127.0.0.1:9/"] * 4)
        clips = [m["params"]["clip"]["height"] for m in sent if m["method"] == "Page.captureScreenshot"]
        self.assertEqual(clips, [shots.TALLEST] * 8)

    def test_a_capture_waits_for_its_own_navigation_to_settle(self) -> None:
        # An idle event from an earlier load is not this page's: a shot taken on it draws a half-built page.
        with mock.patch.dict(os.environ, {"FAKE_MODE": "stale"}):
            shots.capture(str(self.chrome), "http://127.0.0.1:9", ["/tasks"], self.out)
        self.assertNotIn({"early": True}, self.sent())

    def test_a_page_that_never_settles_fails_naming_it_and_writes_nothing(self) -> None:
        # A loaded machine answers setup calls late; the 1 s bound is the settle wait's alone (sd:6388).
        slow = {"FAKE_MODE": "never", "FAKE_TARGET_DELAY": "1.5"}
        with mock.patch.dict(os.environ, slow), mock.patch.object(shots, "SETTLE_SECONDS", 1):
            with self.assertRaisesRegex(shots.ShotFailed, "/tasks dark 1440: no network idle within 1 s"):
                shots.capture(str(self.chrome), "http://127.0.0.1:9", ["/tasks"], self.out)
        self.assertEqual(list(self.out.glob("*.png")), [])


class Served(FakeChrome):
    def setUp(self) -> None:
        super().setUp()
        self.database = self.root / "sd.db"
        initialise(self.database)
        connection = connect(self.database)
        create_item(connection, kind="task", title="Seeded row")
        connection.close()
        patch = mock.patch.dict(os.environ, {"CHROME": str(self.chrome),
                                             "XDG_STATE_HOME": str(self.root / "state"),
                                             "SYSTEM_TOOLS_CONFIG": str(self.root / "config")})
        patch.start()
        self.addCleanup(patch.stop)

    def run_main(self, *pages: str) -> tuple[int, str, str]:
        out, err = [], []
        with mock.patch("sys.stdout.write", out.append), mock.patch("sys.stderr.write", err.append):
            code = shots.main(["--database", str(self.database), "--out", str(self.out), *pages])
        return code, "".join(out), "".join(err)


class Main(Served):
    def test_main_serves_a_copy_so_the_store_is_never_written(self) -> None:
        before = self.database.read_bytes()
        served = []
        build = shots.server.build

        def recording(database, **options):
            served.append(Path(database))
            self.assertEqual(Path(database).read_bytes()[:16], b"SQLite format 3\x00")
            return build(database, **options)

        with mock.patch.object(shots.server, "build", recording):
            code, out, err = self.run_main("/tasks")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(served), 1)
        self.assertNotEqual(served[0], self.database)
        self.assertFalse(served[0].exists(), "the copy outlived the run")
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(out.splitlines(), [str(self.out / f"tasks-{t}-{w}.png")
                                            for t in ("dark", "light") for w in (1440, 375)])

    def test_a_page_the_server_does_not_answer_fails_naming_it(self) -> None:
        code, out, err = self.run_main("/no-such-page")
        self.assertEqual(code, 1)
        self.assertIn("/no-such-page answered 404", err)
        self.assertEqual(list(self.out.glob("*.png")), [])

    def test_a_missing_database_fails_rather_than_drawing_empty_pages(self) -> None:
        self.database.unlink()
        code, out, err = self.run_main("/tasks")
        self.assertEqual(code, 1)
        self.assertIn(str(self.database), err)

    def test_no_chrome_fails_naming_it(self) -> None:
        with mock.patch.dict(os.environ, {"CHROME": str(self.root / "absent")}):
            code, out, err = self.run_main("/tasks")
        self.assertEqual(code, 1)
        self.assertIn("no Chrome", err)


class Changed(Served):
    """sd:6728: the lane draws the pages a branch changed, from `--changed BASE`."""

    def setUp(self) -> None:
        super().setUp()
        self.v2 = self.root / "repo" / "v2"
        (self.v2 / "static").mkdir(parents=True)
        for name in ("home.html", "tasks.html", "static/tokens.css"):
            (self.v2 / name).write_text("old\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        patch = mock.patch.object(shots, "V2", self.v2)
        patch.start()
        self.addCleanup(patch.stop)

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.v2), *args], check=True, capture_output=True, text=True).stdout

    def commit(self, name: str) -> None:
        (self.v2 / name).write_text("new\n")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-qam", "change")

    def test_a_change_to_home_html_draws_home_in_every_variant(self) -> None:
        self.commit("home.html")
        code, out, err = self.run_main("--changed", self.base)
        self.assertEqual((code, err), (0, ""))
        self.assertIn(str(self.out / "home-light-1440.png"), out.splitlines())
        self.assertEqual(len(out.splitlines()), 4)

    def test_a_branch_that_changes_no_page_draws_nothing(self) -> None:
        code, out, err = self.run_main("--changed", self.base)
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertFalse(self.out.exists())

    def test_files_map_to_their_pages_and_a_shared_file_to_home(self) -> None:
        self.assertEqual(shots.pages_for(["tasks.html", "static/queue.css", "static/home-kiosk.js", "pages/home.py"]),
                         ["/home", "/queue", "/tasks"])
        self.assertEqual(shots.pages_for(["static/tokens.css"]), ["/home"])
        self.assertEqual(shots.pages_for(["health.html", "static/places.js"]), ["/fleet-health", "/places"])


class Launcher(unittest.TestCase):
    def test_dashboard_sh_runs_shots_under_the_server_interpreter(self) -> None:
        script = Path(__file__).resolve().parents[1] / "dashboard.sh"
        ran = subprocess.run([str(script), "shots"], env={**os.environ, "SD_DASHBOARD_PYTHON": sys.executable},
                             capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(ran.returncode, 2, ran.stderr)
        self.assertIn("--out", ran.stderr)
        helped = subprocess.run([str(script), "help"], capture_output=True, text=True, timeout=60, check=False)
        self.assertIn("shots", helped.stdout)


if __name__ == "__main__":
    unittest.main()
