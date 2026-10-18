"""sd:5078. A lane gate goes first in the gate queue, and a builder's `sd gate run` refuses at once beside one.

On 2026-10-18 in mezmo-world-simulator, 3 of 4 lane gates hit the 60-minute
gate limit: builder test runs took the other slot and loaded the machine.
Telling builders to hold failed twice. A run already queued got its slot
later, and the wait counted toward the agent's 600 s foreground limit.

A lane gate is `sd-check`'s own slot wait. These tests run the real
`sd-check` as the lane gate and the real `sd gate run` as the builder.
"""

from __future__ import annotations

import fcntl
import io
import json
import os
import pathlib
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_gate_slots  # noqa: E402
import sd_lib  # noqa: E402

from tests.clean_env import clean_environment  # noqa: E402
from tests.test_sd_gate_queue import (  # noqa: E402
    SD,
    SD_CHECK,
    SLOTS,
    QueueFixture,
    slot_free,
    wait_for,
)

#: The exit code of a builder's run that refused beside a lane gate.
LANE_BUSY = 69

#: A check that says it started, then runs until the test writes `release`, at most 120 s.
HOLDING = """
import pathlib, sys, time
started, release, mark = (pathlib.Path(part) for part in sys.argv[1:4])
started.write_text("")
end = time.monotonic() + 120
while not release.exists() and time.monotonic() < end:
    time.sleep(0.05)
with open(mark, "a") as handle:
    handle.write(sys.argv[4] + ",")
"""

#: A non-lane waiter that neither refuses nor jumps the queue: `acquire` with its defaults, as `wait` does.
PLAIN_WAITER = """
import os, sys
sys.path.insert(0, sys.argv[1])
import sd_gate_slots
slot = sd_gate_slots.acquire(1, os.environ, stream=sys.stderr, label="plain waiter")
with open(sys.argv[2], "a") as handle:
    handle.write("plain,")
slot.release()
"""


class LaneFixture(QueueFixture):
    def setUp(self) -> None:
        super().setUp()
        self.release = self.tmp / "release"
        self.order = self.tmp / "order"
        self.addCleanup(self.release.touch)
        self.holding = self.tmp / "holding.py"
        self.holding.write_text(HOLDING, encoding="utf-8")

    def lane_gate(self, name: str, slots: str, *, hold: bool = False, check: str | None = None) -> subprocess.Popen:
        """`sd-check` in a repository called `name`: its slot label is `sd-check <name>`.

        Its check writes `name` to the order file; with `hold` it first waits for the release file.
        """
        root = self.tmp / name
        root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True, env=clean_environment())
        if check is None:
            started = self.tmp / f"{name}.started"
            release = self.release if hold else started
            check = " ".join(shlex.quote(part) for part in (
                sys.executable, str(self.holding), str(started), str(release), str(self.order), name))
        (root / sd_lib.LOCAL_FILE_NAME).write_text(
            f"{sd_lib.LOCAL_BLOCK_START}\ncheck: {check}\n{sd_lib.LOCAL_BLOCK_END}\n", encoding="utf-8")
        gate = subprocess.Popen([sys.executable, str(SD_CHECK), "--json"], cwd=root, env=self.env(SD_GATE_SLOTS=slots),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(gate)
        return gate

    def started(self, name: str) -> bool:
        return (self.tmp / f"{name}.started").exists()

    def builder(self, slots: str, *, max_wait: str = "20", label: str = "wk tests") -> subprocess.Popen:
        """`sd gate run` as a builder runs it; its command marks `ran`."""
        argv = [sys.executable, str(SD), "gate", "run", "--max-wait", max_wait, "--label", label, "--",
                sys.executable, "-c", f"open({str(self.tmp / 'ran')!r}, 'a').write('ran,')"]
        process = subprocess.Popen(argv, env=self.env(SD_GATE_SLOTS=slots), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        return process

    def finish(self, process: subprocess.Popen, timeout: float = 120) -> tuple[int, str, float]:
        began = time.monotonic()
        _, err = process.communicate(timeout=timeout)
        return process.returncode, err, time.monotonic() - began

    def status(self, slots: str) -> dict:
        shown = subprocess.run([sys.executable, str(SLOTS), "status", "--json"], env=self.env(SD_GATE_SLOTS=slots),
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        return json.loads(shown.stdout)


class LanePriority(LaneFixture):
    def test_a_lane_gate_is_admitted_ahead_of_an_earlier_waiter(self):
        holder = self.hold()
        gate = {key: value for key, value in self.env(SD_GATE_SLOTS="1").items() if key.startswith("SD_GATE_")}
        plain = subprocess.Popen([sys.executable, "-c", PLAIN_WAITER, str(REPO_ROOT / "bin"), str(self.order)],
                                 env=clean_environment(**gate), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True)
        self.processes.append(plain)
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        lane = self.lane_gate("lane-a", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 2))
        holder.kill()
        holder.wait()
        code, err, _ = self.finish(lane)
        self.assertEqual(code, 0, err)
        code, err, _ = self.finish(plain)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.order.read_text(), "lane-a,plain,", "the lane gate queued second and must start first")

    def test_a_lane_gate_waits_for_a_builder_that_holds_and_does_not_preempt_it(self):
        started = self.tmp / "builder.started"
        argv = [sys.executable, str(SD), "gate", "run", "--label", "wk tests", "--", sys.executable, str(self.holding),
                str(started), str(self.release), str(self.order), "builder"]
        builder = subprocess.Popen(argv, env=self.env(SD_GATE_SLOTS="1"), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.processes.append(builder)
        self.assertTrue(wait_for(started.exists))
        lane = self.lane_gate("lane-a", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        time.sleep(0.5)
        self.assertIsNone(builder.poll(), "a lane gate must not stop a builder that holds a slot")
        self.assertFalse(self.started("lane-a"))
        self.release.touch()
        code, err, _ = self.finish(builder)
        self.assertEqual(code, 0, err)
        code, err, _ = self.finish(lane)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.order.read_text(), "builder,lane-a,")


class BuilderRefusal(LaneFixture):
    def test_a_builder_run_refuses_at_once_while_a_lane_gate_holds_a_slot(self):
        lane = self.lane_gate("lane-a", "2", hold=True)
        self.assertTrue(wait_for(lambda: self.started("lane-a")))
        code, err, took = self.finish(self.builder("2"))
        self.assertEqual(code, LANE_BUSY, err)
        self.assertLess(took, 10, "a refusal must not wait")
        self.assertFalse((self.tmp / "ran").exists(), "a refused run must not start its command")
        self.assertRegex(err, r"lane gate sd-check lane-a \(pid [0-9]+\) holds slot 1 since "
                              r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
        self.assertRegex(err, rf"exit {LANE_BUSY}\); retry after \d{{4}}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
        self.assertEqual(self.tickets(), [])
        self.release.touch()
        code, err, _ = self.finish(lane)
        self.assertEqual(code, 0, err)

    def test_a_builder_run_refuses_at_once_while_a_lane_gate_waits(self):
        holder = self.hold()
        lane = self.lane_gate("lane-a", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        code, err, took = self.finish(self.builder("1"))
        self.assertEqual(code, LANE_BUSY, err)
        self.assertLess(took, 10, "a refusal must not wait")
        self.assertIn("lane gate sd-check lane-a", err)
        self.assertIn("waits at place 1 since", err)
        self.assertFalse((self.tmp / "ran").exists())
        self.assertEqual(len(self.tickets()), 1, "only the lane gate's ticket may stay")
        holder.kill()
        holder.wait()
        code, err, _ = self.finish(lane)
        self.assertEqual(code, 0, err)

    def test_a_queued_builder_leaves_when_a_lane_gate_arrives(self):
        holder = self.hold()
        builder = self.builder("1", max_wait="60")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        lane = self.lane_gate("lane-a", "1")
        code, err, _ = self.finish(builder)
        self.assertEqual(code, LANE_BUSY, err)
        self.assertIn("lane gate sd-check lane-a", err)
        holder.kill()
        holder.wait()
        code, err, _ = self.finish(lane)
        self.assertEqual(code, 0, err)
        self.assertFalse((self.tmp / "ran").exists(), "a builder that queued before the lane gate must not start later")
        self.assertEqual(self.tickets(), [])

    def test_with_no_lane_gate_a_builder_runs_at_once(self):
        code, err, _ = self.finish(self.builder("2"))
        self.assertEqual(code, 0, err)
        self.assertEqual((self.tmp / "ran").read_text(), "ran,")

    def test_a_gate_run_inside_a_lane_gate_runs(self):
        """A holder's children run with `SD_GATE_SLOTS=0`: a gate inside the lane gate is the lane gate's own."""
        inner = " ".join(shlex.quote(part) for part in (
            sys.executable, str(SD), "gate", "run", "--", sys.executable, "-c",
            f"open({str(self.tmp / 'ran')!r}, 'a').write('ran,')"))
        lane = self.lane_gate("lane-a", "1", check=inner)
        code, err, _ = self.finish(lane)
        self.assertEqual(code, 0, err)
        self.assertEqual((self.tmp / "ran").read_text(), "ran,")

    def test_a_killed_lane_gate_leaves_no_lane_state_behind(self):
        lane = self.lane_gate("lane-a", "1", hold=True)
        self.assertTrue(wait_for(lambda: self.started("lane-a")))
        self.assertEqual([entry["label"] for entry in self.status("1")["lane_gates"]], ["sd-check lane-a"])
        lane.send_signal(signal.SIGKILL)
        lane.wait()
        self.assertTrue(wait_for(lambda: slot_free(self.slots / "slot.1.lock")))
        self.assertTrue(slot_free(self.slots / "slot.1.lane"), "the kernel drops the lane marker with the gate")
        self.assertEqual(self.status("1")["lane_gates"], [])
        code, err, _ = self.finish(self.builder("1"))
        self.assertEqual(code, 0, err)
        self.assertEqual((self.tmp / "ran").read_text(), "ran,")

    def test_a_dead_lane_waiter_does_not_hold_back_a_builder(self):
        holder = self.hold()
        lane = self.lane_gate("lane-a", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        lane.send_signal(signal.SIGKILL)
        lane.wait()
        builder = self.builder("1", max_wait="60")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1 and self.tickets()[0].name != "000000000001.ticket"),
                        [path.name for path in self.tickets()])
        holder.kill()
        holder.wait()
        code, err, _ = self.finish(builder)
        self.assertEqual(code, 0, err)
        self.assertEqual((self.tmp / "ran").read_text(), "ran,")


class LaneStatus(LaneFixture):
    def test_status_names_the_lane_gate_that_holds_and_the_one_that_waits(self):
        first = self.lane_gate("lane-a", "1", hold=True)
        self.assertTrue(wait_for(lambda: self.started("lane-a")))
        second = self.lane_gate("lane-b", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        report = self.status("1")
        for kept in ("directory", "slots", "holders", "waiters", "load", "load_max", "settle_seconds",
                     "rule_source", "last_admitted", "now"):
            self.assertIn(kept, report)
        self.assertEqual([(entry["state"], entry.get("slot"), entry.get("place"), entry["label"], entry["pid"])
                          for entry in report["lane_gates"]],
                         [("holding", 1, None, "sd-check lane-a", first.pid),
                          ("waiting", None, 1, "sd-check lane-b", second.pid)])
        for entry in report["lane_gates"]:
            self.assertRegex(entry["since"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        text = subprocess.run([sys.executable, str(SLOTS), "status"], env=self.env(SD_GATE_SLOTS="1"),
                              capture_output=True, text=True, timeout=60)
        self.assertIn(f"lane: sd-check lane-a (pid {first.pid}) holds slot 1 since", text.stdout)
        self.assertIn(f"sd-check lane-b (pid {second.pid}) waits at place 1 since", text.stdout)
        self.release.touch()
        for gate in (first, second):
            code, err, _ = self.finish(gate)
            self.assertEqual(code, 0, err)


class Admission(unittest.TestCase):
    """The admission step itself, in one process: each open file is its own `flock` owner."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.where = pathlib.Path(tmp.name)
        self.queue = sd_gate_slots.Queue(self.where)
        self.rule = sd_gate_slots.LoadRule(0.0, 0.0, "test")

    def open_pair(self, suffix: str) -> list[int]:
        """Fresh descriptors on `slot.1<suffix>` and `slot.2<suffix>`, as another process would open them."""
        handles = [open(self.where / f"slot.{index}{suffix}", "a") for index in (1, 2)]
        for handle in handles:
            self.addCleanup(handle.close)
        return [handle.fileno() for handle in handles]

    def slots(self) -> list[int]:
        return self.open_pair(".lock")

    def admit(self, ticket, fds, markers=()):
        return self.queue.admit(ticket, fds, self.rule, markers=markers, loadavg=lambda: (1.0, 1.0, 1.0))

    def admitted_lane(self) -> tuple[list[int], list[int]]:
        """A lane gate admitted to slot 1, holding its slot and its marker."""
        fds, markers = self.slots(), self.open_pair(".lane")
        lane = self.queue.enter("sd-check lane-a", "/", lane=True)
        self.assertEqual(self.admit(lane, fds, markers), (0, ""))
        return fds, markers

    def refused(self, builder) -> dict:
        with self.assertRaises(sd_gate_slots.LaneBusy) as raised:
            self.admit(builder, self.slots())
        self.queue.leave(builder)
        return raised.exception.gate

    def test_a_lane_admission_refuses_a_builder_in_the_same_step(self):
        """The marker is locked in the admission step: nothing else runs before the builder looks."""
        fds, markers = self.admitted_lane()
        gate = self.refused(self.queue.enter("wk tests", "/", yields=True))
        self.assertEqual((gate["state"], gate["slot"], gate["label"]), ("holding", 1, "sd-check lane-a"))
        fcntl.flock(markers[0], fcntl.LOCK_UN)
        fcntl.flock(fds[0], fcntl.LOCK_UN)
        again = self.queue.enter("wk tests", "/", yields=True)
        self.assertEqual(self.admit(again, self.slots()), (0, ""), "a released marker counts for nothing")

    def test_a_damaged_state_file_does_not_hide_a_lane_holder(self):
        """Review finding: an unreadable `queue.state` read as no lane holder, and the builder took slot 2."""
        self.admitted_lane()
        (self.where / sd_gate_slots.QUEUE_STATE).write_text("not json", encoding="utf-8")
        builder = self.queue.enter("wk tests", "/", yields=True)
        self.assertEqual(self.refused(builder)["state"], "holding")

    def test_a_marker_that_cannot_be_read_refuses_a_builder(self):
        """Review finding: a probe that failed read as a free slot. A loop stands for any open error."""
        os.symlink("slot.1.lane", self.where / "slot.1.lane")
        gate = self.refused(self.queue.enter("wk tests", "/", yields=True))
        self.assertEqual(gate["state"], "unknown")
        self.assertIn("slot.1.lane", gate["reason"])
        self.assertIn("cannot tell whether a lane gate holds or waits", sd_gate_slots.lane_refusal(gate, 0.0))

    def test_a_ticket_that_cannot_be_read_refuses_a_builder(self):
        other = self.queue.enter("other", "/")
        other.path.write_text("not json", encoding="utf-8")
        self.assertEqual(self.refused(self.queue.enter("wk tests", "/", yields=True))["state"], "unknown")

    def test_a_builder_that_cannot_queue_refuses_and_a_lane_gate_still_marks_its_slot(self):
        """Review finding: a run that could not queue took any free slot without asking about the lane."""
        (self.where / sd_gate_slots.QUEUE_DIR).write_text("not a directory", encoding="utf-8")
        stream = io.StringIO()
        with self.assertRaises(sd_gate_slots.LaneBusy) as raised:
            sd_gate_slots.wait_for_slot(self.slots(), self.where, poll=0.01, stream=stream, yields=True)
        self.assertEqual(raised.exception.gate["state"], "unknown")
        taken = sd_gate_slots.wait_for_slot(self.slots(), self.where, poll=0.01, stream=stream, lane=True,
                                            label="sd-check lane-a", markers=self.open_pair(".lane"))
        self.assertEqual(taken, 0)
        self.assertEqual([(gate["state"], gate["label"]) for gate in sd_gate_slots.lane_gates(self.where, [])],
                         [("holding", "sd-check lane-a")])

    def test_lane_tickets_go_first_and_keep_their_own_order(self):
        plain = self.queue.enter("plain", "/")
        first = self.queue.enter("lane one", "/", lane=True)
        second = self.queue.enter("lane two", "/", lane=True)
        fds = self.slots()[:1]
        self.assertIn("place 3 of 3", self.admit(plain, fds)[1])
        self.assertIn("place 2 of 3", self.admit(second, fds)[1])
        self.assertEqual(self.admit(first, fds), (0, ""))

    def test_a_ticket_without_a_lane_key_is_not_a_lane_gate(self):
        """Older state: a ticket the previous version wrote has no `lane` key."""
        old = self.queue.enter("old gate", "/")
        old.path.write_text(json.dumps({"seq": old.seq, "pid": os.getpid(), "label": "old gate", "cwd": "/",
                                        "since": time.time()}), encoding="utf-8")
        builder = self.queue.enter("wk tests", "/", yields=True)
        self.assertIn("place 2 of 2", self.admit(builder, self.slots())[1])


if __name__ == "__main__":
    unittest.main()
