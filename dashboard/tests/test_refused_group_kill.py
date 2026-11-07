"""A run whose group kill is refused still ends in bounded time (sd:7910).

macOS or a sandbox can answer EPERM to killpg (sd:7900). The runner then kills
the run's own process, but a grandchild, such as the real claude under its
`sh -c`, lives on and holds stdout. A cleanup read with no bound waits for it.
Each test starts such a grandchild and refuses the group kill.
"""

from __future__ import annotations

import os
import signal
import tempfile
import threading
import time
import types
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from sd_dashboard import hoa_download, issue_filing, realm_sweep

#: The run: a grandchild that outlives its parent and holds stdout, its pid in `pid`.
HOLD = "sleep 30 & echo $! > pid; wait"
REFUSED = PermissionError(1, "Operation not permitted")
#: Well under the grandchild's 30 s: a run that waited on it fails.
BOUND = 15


class TheCleanupReadIsBounded(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.addCleanup(self.end_grandchild)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.dir)})
        patch.start()
        self.addCleanup(patch.stop)

    def end_grandchild(self):
        pid = self.dir / "pid"
        if pid.exists() and pid.read_text().strip():
            try:
                os.kill(int(pid.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass

    def bounded(self, module, run):
        began = time.monotonic()
        with mock.patch.object(module.os, "killpg", side_effect=REFUSED):
            answer = run()
        self.assertLess(time.monotonic() - began, BOUND, "the cleanup read waited on the grandchild")
        return answer

    def test_realm_sweep_ask(self):
        code, said, _ = self.bounded(realm_sweep, lambda: realm_sweep.ask(["sh", "-c", HOLD], self.dir, 1, StringIO()))
        self.assertEqual((code, said), (realm_sweep.EXIT_ERROR, "the run passed 1s and was stopped"))

    def test_issue_filing_model(self):
        (self.dir / "input").write_text("a question", encoding="utf-8")
        document = {"input": str(self.dir / "input"), "claude": f"cd {self.dir} && {{ {HOLD}; }}"}
        def run():
            with self.assertRaisesRegex(TimeoutError, "gave no answer in 1 s"):
                issue_filing._model(document, self.dir / "log")

        with mock.patch.object(issue_filing, "MODEL_TIMEOUT", 1):
            self.bounded(issue_filing, run)

    def test_hoa_download_download(self):
        sources = {"x": {"label": "X", "argv": ("sh", "-c", HOLD)}}
        with mock.patch.object(hoa_download, "SOURCES", sources), mock.patch.object(hoa_download, "DOWNLOAD_SECONDS", 1):
            code, said = self.bounded(hoa_download, lambda: hoa_download.download("x", self.dir, (), StringIO()))
        self.assertEqual(code, hoa_download.EXIT_ERROR)
        self.assertIn("and was stopped", said)

    def test_hoa_download_login(self):
        with mock.patch.object(hoa_download, "claude_binary", return_value="sh"), \
                mock.patch.object(hoa_download, "claude_argv", return_value=["sh", "-c", HOLD]), \
                mock.patch.object(hoa_download, "LOGIN_SECONDS", 1):
            code, said = self.bounded(hoa_download, lambda: hoa_download.login("x", "https://example.test", self.dir, (),
                                                                               StringIO(), lambda: None))
        self.assertEqual(code, hoa_download.EXIT_NONE)
        self.assertRegex(said, "^no login within")


class Chatty:
    """A stdout that prints a line each millisecond until `stop`, faster than the reader below takes them."""

    def __init__(self):
        self.stop = threading.Event()

    def __iter__(self):
        while not self.stop.wait(0.001):
            yield "still here\n"

    def close(self):
        pass


class Broken:
    """A stdout whose second line is not UTF-8, as a text-mode pipe reads it."""

    def __iter__(self):
        yield "a line\n"
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    def close(self):
        pass


class TheOutputRead(unittest.TestCase):
    """`_lines` keeps its bound against a chatty survivor and says a failed read (sd:7920)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_a_survivor_that_keeps_printing_does_not_hold_the_read_past_its_bound(self):
        stdout, timer = Chatty(), types.SimpleNamespace(fired=True)
        self.addCleanup(stdout.stop.set)
        began = time.monotonic()
        with mock.patch.object(hoa_download, "REAP_SECONDS", 0.3):
            for _ in hoa_download._lines(types.SimpleNamespace(stdout=stdout), timer):
                time.sleep(0.01)
                if time.monotonic() - began > 3:
                    self.fail("the read still yielded lines 3 s after a 0.3 s bound")

    def test_a_read_that_fails_is_said_at_once(self):
        timer = types.SimpleNamespace(fired=False)
        late = threading.Timer(2, setattr, (timer, "fired", True))
        late.daemon = True
        late.start()
        self.addCleanup(late.cancel)
        with mock.patch.object(hoa_download, "REAP_SECONDS", 0.3), \
                self.assertRaisesRegex(Exception, "UnicodeDecodeError"):
            list(hoa_download._lines(types.SimpleNamespace(stdout=Broken()), timer))


if __name__ == "__main__":
    unittest.main()
