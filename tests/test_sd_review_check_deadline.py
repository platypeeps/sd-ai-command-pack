"""The gate's deadline ends every process the gate started (sd:1482).

`sd-review` gives `sd-check` its own timeout as `--timeout`, so the two
deadlines are equal, and the parent's starts first. At the parent's deadline
`subprocess.run` killed `sd-check` alone. The check `sd-check` was running
kept going with nobody left to time it out, and so did anything that check
had started. Codex reproduced it on #1174 as "parent terminated; check child
still owns pipe: True". These tests use real processes, because the defect
is in which processes a signal reaches.
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys
import textwrap
import time

from tests.test_sd_review import ReviewFixture, sd_review

#: A check that records its own pid and a background sleeper's, then waits.
ORPHAN_CHECK = 'sleep 60 &\necho "$$ $!" > pids\nwait\n'


def running(pid: int) -> bool:
    """Alive and not a zombie waiting for its parent to reap it."""
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(state) and not state.startswith("Z")


class TheGateDeadlineEndsTheGroup(ReviewFixture):
    def started(self, pids: pathlib.Path) -> list[int]:
        deadline = time.monotonic() + 10
        while not (pids.is_file() and pids.read_text().strip()):
            self.assertLess(time.monotonic(), deadline, "the check never recorded its pids")
            time.sleep(0.05)
        found = [int(word) for word in pids.read_text().split()]
        for pid in found:
            self.addCleanup(self.kill, pid)
        return found

    @staticmethod
    def kill(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def survivors(self, pids: list[int]) -> list[int]:
        """What is still running a moment after the call returned: a killed
        process can take a scheduler tick to die, an orphan never does."""
        deadline = time.monotonic() + 5
        alive = [pid for pid in pids if running(pid)]
        while alive and time.monotonic() < deadline:
            time.sleep(0.1)
            alive = [pid for pid in alive if running(pid)]
        return alive

    def test_a_gate_the_parent_timed_out_leaves_no_check_running(self) -> None:
        """The row's check. The same shape whichever deadline fires first:
        the parent's orphans the check and its sleeper; `sd-check`'s own
        kills the check alone and orphans the sleeper."""
        root = self.make_repo()
        (root / "orphan.sh").write_text(ORPHAN_CHECK, encoding="utf-8")
        self.local_block(root, "check: sh orphan.sh")
        report = sd_review.run_check(root, sd_review.subprocess_runner, self.environment(), 2)
        pids = self.started(root / "pids")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(self.survivors(pids), [], f"left running after the gate's deadline: {pids}")

    def test_a_terminated_review_takes_its_gate_with_it(self) -> None:
        """`sd-ship` ends a review by signalling the review's process group.
        The gate now leads a group of its own, which that signal no longer
        reaches, so the runner has to end it on the way out. Before the gate
        had a group of its own this passed by sharing the caller's; it guards
        the change, not the defect."""
        root = self.make_repo()
        (root / "orphan.sh").write_text(ORPHAN_CHECK, encoding="utf-8")
        harness = textwrap.dedent(f"""\
            import pathlib, sys
            sys.path.insert(0, {str(pathlib.Path(sd_review._BIN))!r})
            import sd_lib
            sd_lib.run_group(["sh", "orphan.sh"], cwd=pathlib.Path("."), env={{"PATH": "/usr/bin:/bin"}}, timeout=60)
            """)
        caller = subprocess.Popen([sys.executable, "-c", harness], cwd=root, start_new_session=True,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.kill, caller.pid)
        pids = self.started(root / "pids")
        os.killpg(caller.pid, signal.SIGTERM)
        self.assertEqual(caller.wait(timeout=10), -signal.SIGTERM)
        self.assertEqual(self.survivors(pids), [], f"left running after the review was terminated: {pids}")

    def test_a_gate_that_finished_leaves_nothing_behind_either(self) -> None:
        """A check that exits and leaves a detached sleeper holding no pipe
        is the same leak without a timeout: the group is ended on every exit."""
        root = self.make_repo()
        (root / "leave.sh").write_text('sleep 60 > /dev/null 2>&1 &\necho "$!" > pids\n', encoding="utf-8")
        self.local_block(root, "check: sh leave.sh")
        report = sd_review.run_check(root, sd_review.subprocess_runner, self.environment(), 60)
        pids = self.started(root / "pids")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(self.survivors(pids), [], f"left running after the gate passed: {pids}")
