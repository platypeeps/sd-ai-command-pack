"""sd:5078 and sd:5409. Lane gates and builder runs share the gate queue in arrival order.

On 2026-10-18 in mezmo-world-simulator, 3 of 4 lane gates hit the 60-minute
gate limit: builder test runs took the other slot and loaded the machine.
sd:5078 put lane gates first and had a builder's `sd gate run` refuse, exit 69,
while a lane gate held or waited. On 2026-10-19 three builders then waited 1.5
to 2 h: a lane gate nearly always held a slot, and each time one ended the next
queued before the builder tried again.

Now every waiter is admitted in the order it queued, and a builder's run
queues as any other does, bounded by `--max-wait`. A lane gate still marks the
slot it holds, so `sd gate status` names it. These tests run the real
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

#: A check that says it started, then runs until the test writes `release`, at most 120 s.
HOLDING = """
import os, pathlib, sys, time
started, release, mark = (pathlib.Path(part) for part in sys.argv[1:4])
started.write_text(str(os.getpid()))
end = time.monotonic() + 120
while not release.exists() and time.monotonic() < end:
    time.sleep(0.05)
with open(mark, "a") as handle:
    handle.write(sys.argv[4] + ",")
"""

#: Enters the queue under `argv[1]`, prints its sequence number, and keeps its ticket until stdin closes.
ENTERING = """
import pathlib, sys
sys.path.insert(0, sys.argv[2])
import sd_gate_slots
ticket = sd_gate_slots.Queue(pathlib.Path(sys.argv[1])).enter("together", "/")
print(ticket.seq, flush=True)
sys.stdin.read()
"""


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def previous_order(entries: list[dict]) -> list[int]:
    """The order sd:5078's admission gave: tickets with `lane: true` first, then by sequence number."""
    return [entry["seq"] for entry in sorted(entries, key=lambda entry: (entry.get("lane") is not True, entry["seq"]))]


class LaneFixture(QueueFixture):
    def setUp(self) -> None:
        super().setUp()
        self.release = self.tmp / "release"
        self.order = self.tmp / "order"
        self.addCleanup(self.release.touch)
        self.holding = self.tmp / "holding.py"
        self.holding.write_text(HOLDING, encoding="utf-8")

    def reap(self) -> None:
        """The queue fixture's reap, plus the pipes of each process a test killed rather than finished."""
        super().reap()
        for process in self.processes:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

    def lane_gate(self, name: str, slots: str, *, hold: bool = False, check: str | None = None) -> subprocess.Popen:
        """`sd-check` in a repository called `name`: its slot label is `sd-check <name>`.

        Its check writes `name` to the order file; with `hold` it first waits for the release file.
        """
        root = self.tmp / name
        root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True, env=clean_environment())
        if check is None:
            check = shlex.join(self.marking(name, hold))
        (root / sd_lib.LOCAL_FILE_NAME).write_text(
            f"{sd_lib.LOCAL_BLOCK_START}\ncheck: {check}\n{sd_lib.LOCAL_BLOCK_END}\n", encoding="utf-8")
        gate = subprocess.Popen([sys.executable, str(SD_CHECK), "--json"], cwd=root, env=self.env(SD_GATE_SLOTS=slots),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(gate)
        return gate

    def marking(self, name: str, hold: bool) -> list[str]:
        """A command that writes `<name>.started`, waits for the release file with `hold`, then writes `name` to the order file."""
        started = self.tmp / f"{name}.started"
        return [sys.executable, str(self.holding), str(started), str(self.release if hold else started),
                str(self.order), name]

    def started(self, name: str) -> bool:
        return (self.tmp / f"{name}.started").exists()

    def check_pid(self, name: str) -> int:
        """The pid of `name`'s check, which `sd-check` runs in its own session."""
        return int((self.tmp / f"{name}.started").read_text())

    def builder(self, slots: str, *, name: str = "builder", max_wait: str = "60", hold: bool = False) -> subprocess.Popen:
        """`sd gate run` as a builder runs it: its command writes `name` to the order file."""
        argv = [sys.executable, str(SD), "gate", "run", "--max-wait", max_wait, "--label", f"wk {name}", "--",
                *self.marking(name, hold)]
        process = subprocess.Popen(argv, env=self.env(SD_GATE_SLOTS=slots), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        return process

    def finish(self, process: subprocess.Popen, timeout: float = 120) -> tuple[int, str, float]:
        began = time.monotonic()
        _, err = process.communicate(timeout=timeout)
        return process.returncode, err, time.monotonic() - began

    def finish_all(self, *processes: subprocess.Popen) -> None:
        for process in processes:
            code, err, _ = self.finish(process)
            self.assertEqual(code, 0, err)

    def status(self, slots: str) -> dict:
        shown = subprocess.run([sys.executable, str(SLOTS), "status", "--json"], env=self.env(SD_GATE_SLOTS=slots),
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        return json.loads(shown.stdout)

    def ran(self) -> str:
        return self.order.read_text() if self.order.exists() else ""


class ArrivalOrder(LaneFixture):
    def test_a_builder_queued_before_a_lane_gate_starts_first(self):
        """sd:5409: the lane gate that queued second no longer jumps the builder, nor sends it away."""
        holder = self.hold()
        builder = self.builder("1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        lane = self.lane_gate("lane-a", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 2))
        holder.kill()
        holder.wait()
        self.finish_all(builder, lane)
        self.assertEqual(self.ran(), "builder,lane-a,", "the builder queued first and must start first")

    def test_a_lane_gate_queued_before_a_builder_starts_first_and_the_builder_waits(self):
        holder = self.hold()
        lane = self.lane_gate("lane-a", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        builder = self.builder("1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 2))
        holder.kill()
        holder.wait()
        self.finish_all(lane, builder)
        self.assertEqual(self.ran(), "lane-a,builder,")

    def test_a_lane_gate_that_ends_does_not_let_the_next_one_overtake_a_waiting_builder(self):
        """The 2026-10-19 evidence: lane-a holds, the builder waits, lane-b queues; lane-a ends."""
        first = self.lane_gate("lane-a", "1", hold=True)
        self.assertTrue(wait_for(lambda: self.started("lane-a")))
        builder = self.builder("1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        second = self.lane_gate("lane-b", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 2))
        self.release.touch()
        self.finish_all(first, builder, second)
        self.assertEqual(self.ran(), "lane-a,builder,lane-b,")

    def test_a_builder_takes_a_free_slot_beside_a_lane_gate_that_holds_one(self):
        lane = self.lane_gate("lane-a", "2", hold=True)
        self.assertTrue(wait_for(lambda: self.started("lane-a")))
        code, err, took = self.finish(self.builder("2"))
        self.assertEqual(code, 0, err)
        self.assertLess(took, 30)
        self.assertEqual(self.ran(), "builder,")
        self.release.touch()
        self.finish_all(lane)

    def test_a_lane_gate_waits_for_a_builder_that_holds_and_does_not_preempt_it(self):
        builder = self.builder("1", hold=True)
        self.assertTrue(wait_for(lambda: self.started("builder")))
        lane = self.lane_gate("lane-a", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        time.sleep(0.5)
        self.assertIsNone(builder.poll(), "a lane gate must not stop a builder that holds a slot")
        self.assertFalse(self.started("lane-a"))
        self.release.touch()
        self.finish_all(builder, lane)
        self.assertEqual(self.ran(), "builder,lane-a,")

    def test_a_builder_past_its_max_wait_exits_75_names_the_lane_gate_and_leaves_no_ticket(self):
        lane = self.lane_gate("lane-a", "1", hold=True)
        self.assertTrue(wait_for(lambda: self.started("lane-a")))
        code, err, _ = self.finish(self.builder("1", max_wait="1"))
        self.assertEqual(code, sd_gate_slots.RUN_NO_SLOT, err)
        self.assertIn("place 1 of 1 in the queue", err)
        self.assertIn("slot 1 held by sd-check lane-a", err)
        self.assertEqual(self.tickets(), [])
        self.assertEqual(self.ran(), "")
        self.release.touch()
        self.finish_all(lane)

    def test_a_builder_killed_while_queued_does_not_hold_back_the_lane_gate_behind_it(self):
        holder = self.hold()
        builder = self.builder("1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 1))
        lane = self.lane_gate("lane-a", "1")
        self.assertTrue(wait_for(lambda: len(self.tickets()) == 2))
        builder.send_signal(signal.SIGKILL)
        builder.wait()
        holder.kill()
        holder.wait()
        self.finish_all(lane)
        self.assertEqual(self.ran(), "lane-a,")
        self.assertEqual(self.tickets(), [], "the next admission removes the dead builder's ticket")

    def test_a_gate_run_inside_a_lane_gate_runs(self):
        """A holder's children run with `SD_GATE_SLOTS=0`: a gate inside the lane gate is the lane gate's own."""
        inner = shlex.join([sys.executable, str(SD), "gate", "run", "--", *self.marking("inner", False)])
        lane = self.lane_gate("lane-a", "1", check=inner)
        self.finish_all(lane)
        self.assertEqual(self.ran(), "inner,")

    def test_a_killed_lane_gate_leaves_no_lane_state_behind(self):
        lane = self.lane_gate("lane-a", "1", hold=True)
        self.assertTrue(wait_for(lambda: self.started("lane-a")))
        self.assertEqual([entry["label"] for entry in self.status("1")["lane_gates"]], ["sd-check lane-a"])
        check = self.check_pid("lane-a")
        lane.send_signal(signal.SIGKILL)
        lane.wait()
        self.assertTrue(wait_for(lambda: slot_free(self.slots / "slot.1.lock")))
        self.assertFalse(wait_for(lambda: not alive(check), timeout=2),
                         "a killed sd-check leaves its check running")
        # The orphan woke on cleanup's release and wrote into the temp
        # directory while it was being removed (sd:6401): end it first.
        os.killpg(check, signal.SIGKILL)
        self.assertTrue(wait_for(lambda: not alive(check)), "the check outlived the test")
        self.assertTrue(slot_free(self.slots / "slot.1.lane"), "the kernel drops the lane marker with the gate")
        self.assertEqual(self.status("1")["lane_gates"], [])
        self.finish_all(self.builder("1"))
        self.assertEqual(self.ran(), "builder,")


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
        self.finish_all(first, second)


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

    def test_every_waiter_is_admitted_in_the_order_it_queued_lane_or_not(self):
        plain = self.queue.enter("plain", "/")
        lane = self.queue.enter("lane one", "/", lane=True)
        builder = self.queue.enter("wk tests", "/")
        later = self.queue.enter("lane two", "/", lane=True)
        fds = self.slots()[:1]
        for ticket, place in ((later, "place 4 of 4"), (builder, "place 3 of 4"), (lane, "place 2 of 4")):
            self.assertIn(place, self.admit(ticket, fds)[1])
        self.assertEqual(self.admit(plain, fds), (0, ""))
        fcntl.flock(fds[0], fcntl.LOCK_UN)
        self.assertIn("place 2 of 3", self.admit(builder, fds)[1], "the lane gate queued before the builder")
        self.assertEqual(self.admit(lane, fds), (0, ""))

    def test_a_builder_is_admitted_beside_a_lane_gate_that_holds_a_slot(self):
        fds, markers = self.slots(), self.open_pair(".lane")
        lane = self.queue.enter("sd-check lane-a", "/", lane=True)
        self.assertEqual(self.admit(lane, fds, markers), (0, ""))
        builder = self.queue.enter("wk tests", "/")
        self.assertEqual(self.admit(builder, self.slots()), (1, ""))
        self.assertEqual([gate["state"] for gate in sd_gate_slots.lane_gates(self.where, [])], ["holding"])

    def test_a_lane_ticket_does_not_carry_the_key_the_previous_version_put_first(self):
        """Older state: a waiter still on sd:5078's code orders tickets by `lane: true` first.
        A ticket that said so would make it and this version each wait for the other."""
        plain = self.queue.enter("run-tests.sh", "/")
        lane = self.queue.enter("sd-check lane-a", "/", lane=True)
        written = json.loads(lane.path.read_text(encoding="utf-8"))
        self.assertNotIn("lane", written)
        self.assertEqual(written["role"], "lane")
        self.assertEqual(previous_order(self.queue_entries()), [plain.seq, lane.seq])
        self.assertEqual([entry["seq"] for entry in sd_gate_slots.admission_order(self.queue_entries())],
                         [plain.seq, lane.seq])

    def test_a_previous_version_lane_ticket_waits_its_turn_and_status_still_names_it(self):
        """Older state: a lane gate on sd:5078's code wrote `lane: true`. This version's admission orders it by
        number and `status` still names it; that gate's own code still puts itself first until it ends."""
        plain = self.queue.enter("plain", "/")
        old = self.queue.enter("sd-check old", "/")
        old.path.write_text(json.dumps({"seq": old.seq, "pid": os.getpid(), "label": "sd-check old", "cwd": "/",
                                        "since": time.time(), "lane": True}), encoding="utf-8")
        fds = self.slots()[:1]
        self.assertIn("place 2 of 2", self.admit(old, fds)[1])
        self.assertEqual(self.admit(plain, fds), (0, ""))
        with self.queue.admission_lock():
            lanes = sd_gate_slots.lane_gates(self.where, self.queue.waiters(prune=False))
        self.assertEqual([(gate["state"], gate["label"]) for gate in lanes], [("waiting", "sd-check old")])

    def queue_entries(self) -> list[dict]:
        with self.queue.admission_lock():
            return self.queue.waiters(prune=False)

    def test_waiters_that_enter_together_each_get_their_own_place(self):
        """Eight processes enter at once: each sequence number is taken under `queue.lock`, so none repeats."""
        self.where.joinpath(sd_gate_slots.QUEUE_DIR).mkdir()
        entering = [subprocess.Popen([sys.executable, "-c", ENTERING, str(self.where), str(REPO_ROOT / "bin")],
                                     env=clean_environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True) for _ in range(8)]
        try:
            seqs = sorted(int(process.stdout.readline()) for process in entering)
            self.assertEqual(seqs, list(range(1, 9)))
            mine = self.queue.enter("after", "/")
            self.assertIn("place 9 of 9", self.admit(mine, self.slots())[1])
        finally:
            for process in entering:
                process.stdin.close()
                process.wait()
                process.stdout.close()

    def test_a_kill_between_the_number_and_the_ticket_leaves_a_gap_the_queue_skips(self):
        """`enter` writes the next number, then the ticket: a waiter killed between them leaves only a gap."""
        self.queue.tickets.mkdir()
        self.queue.write_state({"next": 5})
        ticket = self.queue.enter("after the gap", "/")
        self.assertEqual(ticket.seq, 5)
        self.queue.write_state({**self.queue.state(), "next": 9})
        behind = self.queue.enter("behind", "/")
        self.assertEqual(behind.seq, 9)
        self.assertEqual(self.admit(ticket, self.slots()[:1]), (0, ""))

    def test_a_damaged_state_file_does_not_change_the_order(self):
        first = self.queue.enter("first", "/")
        second = self.queue.enter("sd-check lane-a", "/", lane=True)
        (self.where / sd_gate_slots.QUEUE_STATE).write_text("not json", encoding="utf-8")
        fds = self.slots()[:1]
        self.assertIn("place 2 of 2", self.admit(second, fds)[1])
        self.assertEqual(self.admit(first, fds), (0, ""))

    def test_a_waiter_that_cannot_queue_takes_a_free_slot_and_a_lane_gate_still_marks_it(self):
        (self.where / sd_gate_slots.QUEUE_DIR).write_text("not a directory", encoding="utf-8")
        stream = io.StringIO()
        taken = sd_gate_slots.wait_for_slot(self.slots(), self.where, poll=0.01, stream=stream, lane=True,
                                            label="sd-check lane-a", markers=self.open_pair(".lane"))
        self.assertEqual(taken, 0)
        self.assertIn("cannot queue", stream.getvalue())
        self.assertEqual([(gate["state"], gate["label"]) for gate in sd_gate_slots.lane_gates(self.where, [])],
                         [("holding", "sd-check lane-a")])

    def test_a_ticket_that_cannot_be_opened_stays_out_of_the_order(self):
        other = self.queue.enter("sd-check lane-a", "/", lane=True)
        other.path.unlink()
        os.symlink(other.path.name, other.path)
        plain = self.queue.enter("plain", "/")
        self.assertEqual(self.admit(plain, self.slots()), (0, ""), "an unprobed ticket holds nobody back")
        with self.queue.admission_lock():
            lanes = sd_gate_slots.lane_gates(self.where, self.queue.waiters(prune=False))
        self.assertEqual([gate["state"] for gate in lanes], ["unknown"], "status says it cannot tell")

    def test_a_lane_gate_takes_no_slot_while_its_marker_is_held(self):
        """A lane gate that lost its marker to a probe would hold a slot `status` cannot show."""
        probe = self.open_pair(".lane")
        fcntl.flock(probe[0], fcntl.LOCK_EX | fcntl.LOCK_NB)
        fds, markers = self.slots(), self.open_pair(".lane")
        lane = self.queue.enter("sd-check lane-a", "/", lane=True)
        self.assertEqual(self.admit(lane, fds, markers), (None, "the lane marker of slot 1 is held"))
        self.assertEqual(sd_gate_slots.take_free(fds, markers, "sd-check lane-a", 0.0),
                         (None, "the lane marker of slot 1 is held"))
        self.assertTrue(sd_gate_slots.try_lock(self.slots()[0]), "the slot must be free again")

    def test_a_lane_marker_that_cannot_be_opened_keeps_the_cap_and_says_so(self):
        os.symlink("slot.1.lane", self.where / "slot.1.lane")
        stream = io.StringIO()
        slot = sd_gate_slots.acquire(1, {"SD_GATE_SLOTS_DIR": str(self.where), "SD_GATE_SLOT_POLL": "0.01"},
                                     stream=stream, rule=self.rule, label="sd-check lane-a", lane=True)
        self.addCleanup(slot.release)
        self.assertIsNotNone(slot.handle, "the lane gate keeps its slot")
        self.assertIsNone(slot.marker)
        self.assertIn("cannot open a lane marker", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
