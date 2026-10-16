"""`sd_db.follow.attempt`: a refused build follows the hub's pins once and runs the command again (sd:4748).

Every follow here is a shell script in the test's own folder, registered as
a plugin root that holds `local-repo-sync/repo-sync.sh`. The re-run is a
recorder in place of `os.execve`. No hub: the mismatch is built by hand, as
`Hub.open` would hand it over (`tests/sd_db/test_hub.py` proves that hand-over).
"""

from __future__ import annotations

import io
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from sd_db import follow, remote

LIB = Path(__file__).resolve().parents[2] / "lib"

MISMATCH = remote.BuildMismatch("build", "1111111111111111", "2222222222222222", hub_build="2222222222222222")


class FollowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / "follow.log"
        self.reruns: list[tuple[list[str], dict[str, str]]] = []
        self.out = io.StringIO()
        # A fresh process: nothing opened yet. The environment is built per call.
        patched = mock.patch.object(remote, "_opened", 0)
        patched.start()
        self.addCleanup(patched.stop)
        # stdin is `/dev/null` unless a test passes one: the runner's own may be a pipe.
        self.devnull = os.open(os.devnull, os.O_RDONLY)
        self.addCleanup(os.close, self.devnull)

    def script(self, body: str, root: str = "system") -> Path:
        """A plugin root whose `local-repo-sync/repo-sync.sh` runs `body` and logs its arguments."""
        path = self.root / root / follow.SCRIPT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'#!/bin/sh\necho "args=$* marker=${{{follow.MARKER}:-unset}} '
                        f'wait=${{REPO_SYNC_DRAIN_WAIT:-unset}} stdin=$(cat | wc -c | tr -d \' \')" >> "{self.log}"\n'
                        f"{body}\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path.parents[1]

    def attempt(self, roots, environ=None, **options) -> str:
        follow.attempt(MISMATCH, roots, environ={"PATH": "/usr/bin:/bin", **(environ or {})},
                       argv=["bin/sd", "task", "show", "1"], out=self.out, stdin=options.pop("stdin", self.devnull),
                       rerun=lambda argv, env: self.reruns.append((argv, env)), **options)
        return self.out.getvalue()

    def logged(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []


class TheFollow(FollowCase):
    def test_a_follow_that_exits_zero_reruns_the_command_with_the_marker(self):
        root = self.script("exit 0")
        text = self.attempt([self.root / "unrelated", root])
        self.assertEqual(self.logged(), ["args=follow marker=1 wait=120 stdin=0"])
        self.assertEqual(len(self.reruns), 1)
        argv, env = self.reruns[0]
        self.assertEqual(argv, ["bin/sd", "task", "show", "1"])
        self.assertEqual(env[follow.MARKER], "1")
        self.assertEqual(env["PATH"], "/usr/bin:/bin")
        self.assertRegex(text, r"sd_db build [0-9a-f]{16} here, 2222222222222222 on the hub")
        self.assertRegex(text, r"follow exited 0 after \d+ s; running the command again")

    def test_the_digests_named_are_this_build_and_the_hubs(self):
        with mock.patch.object(remote, "build_digest", return_value="1111111111111111"):
            text = self.attempt([self.script("exit 0")])
        self.assertIn("sd_db build 1111111111111111 here, 2222222222222222 on the hub", text.splitlines()[0])

    def test_a_follow_that_fails_leaves_the_refusal_and_shows_its_last_lines(self):
        root = self.script('echo "follow  : refused, nothing moved"\nexit 1')
        text = self.attempt([root])
        self.assertEqual(self.reruns, [])
        self.assertRegex(text, r"follow exited 1 after \d+ s; the refusal stands")
        self.assertIn("  follow: follow  : refused, nothing moved", text)

    def test_a_follow_past_the_bound_is_killed_and_leaves_the_refusal(self):
        root = self.script("sleep 30")
        text = self.attempt([root], timeout=0.5)
        self.assertEqual(self.reruns, [])
        self.assertIn("follow timed out after 0.5 s; the refusal stands", text)

    def test_a_timeout_kills_the_follows_descendants_not_just_its_shell(self):
        # The real follow execs refresh_drain.py, which holds the refresh and
        # lane locks and may start `make setup`; killing only the shell leaves
        # them writing. The child here stands in for that descendant: it
        # outlives its parent shell and would touch `marker` unless its whole
        # group is killed (sd:4748, codex review).
        marker = self.root / "descendant-ran"
        root = self.script(f'sh -c \'sleep 2; : > "{marker}"\' &\nsleep 30')
        self.attempt([root], timeout=0.5)
        time.sleep(3)
        self.assertFalse(marker.exists(), "a follow descendant survived the timeout and went on writing")

    def test_an_interrupt_during_the_follow_takes_the_group_with_it(self):
        # Ctrl-C while sd waits for the follow: the interrupt reaches sd, not
        # the detached group, so the group must be killed before the
        # exception propagates or the follow goes on writing (sd:4748, codex).
        # The real Popen still starts the group; only the wait raises, then
        # the reap inside `_kill_group` returns, as a drained pipe would.
        marker = self.root / "descendant-ran"
        root = self.script(f'sh -c \'sleep 2; : > "{marker}"\' &\nsleep 30')
        with mock.patch.object(follow.subprocess.Popen, "communicate", autospec=True) as communicate:
            communicate.side_effect = [KeyboardInterrupt(), ("", "")]
            with self.assertRaises(KeyboardInterrupt):
                self.attempt([root], timeout=5)
        time.sleep(3)
        self.assertFalse(marker.exists(), "a follow descendant survived an interrupt and went on writing")

    def test_a_sigterm_to_sd_during_the_follow_takes_the_group_with_it(self):
        # SIGTERM or SIGHUP (a closed terminal, a kill) would end sd without
        # unwinding, orphaning the detached follow group with its locks held.
        # A child running _run_follow is sent SIGTERM; its marker-writing
        # grandchild must never appear, and the child must die (sd:4748, codex).
        marker = self.root / "descendant-ran"
        script = self.script(f'sh -c \'sleep 2; : > "{marker}"\' &\nsleep 30') / follow.SCRIPT
        runner = self.root / "runner.py"
        runner.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(LIB)!r})\n"
            "from sd_db import follow\n"
            f"follow._run_follow({str(script)!r}, {{'PATH': '/usr/bin:/bin'}}, 30)\n")
        child = subprocess.Popen([sys.executable, str(runner)], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        time.sleep(1)  # let the follow script start its grandchild
        child.send_signal(signal.SIGTERM)
        self.assertEqual(child.wait(timeout=10), -signal.SIGTERM)
        time.sleep(3)
        self.assertFalse(marker.exists(), "a follow descendant survived a SIGTERM to sd and went on writing")

    def test_a_lock_wait_is_a_failed_follow_the_drain_wait_bounds(self):
        # The follow's own drain reads `REPO_SYNC_DRAIN_WAIT` and refuses past
        # it; the script stands in for that refusal, and the environment it
        # ran under carries the cap.
        root = self.script('[ "$REPO_SYNC_DRAIN_WAIT" = 120 ] || exit 9\necho "refresh.lock is held"; exit 1')
        text = self.attempt([root])
        self.assertEqual(self.reruns, [])
        self.assertIn("follow exited 1", text)
        self.assertIn("  follow: refresh.lock is held", text)
        self.assertEqual(follow.DRAIN_WAIT, 120)


class TheGuards(FollowCase):
    def test_the_marker_stops_a_second_follow(self):
        root = self.script("exit 0")
        text = self.attempt([root], environ={follow.MARKER: "1"})
        self.assertEqual(self.logged(), [])
        self.assertEqual(self.reruns, [])
        self.assertIn("still refused after a follow in this process chain; the refusal stands", text)

    def test_a_process_past_its_first_session_keeps_the_refusal(self):
        root = self.script("exit 0")
        with mock.patch.object(remote, "_opened", 1):
            text = self.attempt([root])
        self.assertEqual(self.logged(), [])
        self.assertEqual(self.reruns, [])
        self.assertIn("the hub changed while this command ran; the refusal stands", text)

    def test_no_registered_follow_keeps_the_refusal_and_names_the_remedy(self):
        (self.root / "plain").mkdir()
        text = self.attempt([self.root / "plain", self.root / "absent"])
        self.assertEqual(self.reruns, [])
        self.assertIn(f"no registered plugin holds {follow.SCRIPT}", text)
        self.assertIn("`sd plugin add`", text)

    def test_a_pipe_on_stdin_keeps_the_refusal_and_names_the_hand_run(self):
        root = self.script("exit 0")
        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        os.write(writer, b"body the re-run could not read\n")
        os.close(writer)
        text = self.attempt([root], stdin=reader)
        self.assertEqual(self.logged(), [], "a pipe-fed command must not follow")
        self.assertEqual(self.reruns, [])
        self.assertIn("stdin is a pipe, which a re-run cannot read again; the refusal stands, "
                      "run the command again after `repo-sync.sh follow`", text)

    def test_a_file_on_stdin_already_read_keeps_the_refusal(self):
        root = self.script("exit 0")
        body = self.root / "body.txt"
        body.write_text("line one\nline two\n")
        with body.open("rb") as handle:
            handle.readline()
            text = self.attempt([root], stdin=handle.fileno())
        self.assertEqual(self.reruns, [])
        self.assertIn("stdin is a file already read, which a re-run cannot read again", text)

    def test_a_terminal_devnull_or_unread_file_on_stdin_reruns(self):
        root = self.script("exit 0")
        body = self.root / "body.txt"
        body.write_text("unread\n")
        with body.open("rb") as unread, open(os.devnull, "rb") as devnull:
            for fd in (unread.fileno(), devnull.fileno()):
                self.assertIsNone(follow.stdin_consumed(fd))
        self.assertIsNone(follow.stdin_consumed(-1), "a closed stdin is closed for the re-run too")
        with body.open("rb") as unread:
            text = self.attempt([root], stdin=unread.fileno())
        self.assertEqual(len(self.reruns), 1, text)

    def test_a_follow_that_cannot_start_keeps_the_refusal(self):
        root = self.script("exit 0")
        with mock.patch.object(follow.subprocess, "Popen", side_effect=OSError("no sh")):
            text = self.attempt([root])
        self.assertEqual(self.reruns, [])
        self.assertIn("follow could not start (no sh); the refusal stands", text)

    def test_the_bound_is_ten_minutes_and_the_exec_keeps_the_interpreter(self):
        self.assertEqual(follow.TIMEOUT, 600.0)
        with mock.patch.object(follow.os, "execve") as execve:
            follow._exec(["bin/sd", "today"], {"A": "b"})
        execve.assert_called_once_with(follow.sys.executable, [follow.sys.executable, "bin/sd", "today"], {"A": "b"})


class SessionsOpened(unittest.TestCase):
    def test_the_count_reads_the_module_counter(self):
        with mock.patch.object(remote, "_opened", 3):
            self.assertEqual(remote.sessions_opened(), 3)


if __name__ == "__main__":
    unittest.main()
