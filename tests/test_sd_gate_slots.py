"""sd:1996. Every repository gate takes a machine-wide slot, not only the pack's own tests.

On 2026-09-28 nine `sd-ship` gates across repositories ran at once, the load
average reached 141 on 16 cores, and a repository's gate failed tests that
assert nothing about time. `sd-check` is where every `repo.ci = local` gate
passes, so it takes a slot from `bin/sd_gate_slots.py`, the one implementation
`.github/scripts/run-tests.sh` uses too. These run the real executable.
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
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD_CHECK = REPO_ROOT / "bin" / "sd-check"
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_gate_slots  # noqa: E402
import sd_lib  # noqa: E402

PY = shlex.quote(sys.executable)

#: A check that counts itself in and out under a lock and keeps the highest
#: count it saw, so the test reads how many checks ran at once.
COUNTING_CHECK = """
import fcntl, os, sys, time
counter = sys.argv[1]
def step(delta):
    with open(counter, "a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        now, peak = (int(part) for part in (handle.read().split() or ["0", "0"]))
        now += delta
        handle.seek(0)
        handle.truncate()
        handle.write(f"{now} {max(now, peak)}")
step(1)
time.sleep(1.5)
step(-1)
"""

#: A check that fails unless its parent `sd-check` holds the slot and wrote its pid there.
HOLDER_CHECK = """
import fcntl, os, sys
lock = sys.argv[1]
with open(lock, "a") as handle:
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        pass
    else:
        sys.exit("the slot was free while the check ran")
if open(lock).read().split() != [str(os.getppid())]:
    sys.exit("the slot does not name the sd-check that holds it")
"""


def slot_free(lock: pathlib.Path) -> bool:
    with open(lock, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle, fcntl.LOCK_UN)
    return True


class GateSlotFixture(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name).resolve()
        self.slots = self.tmp / "slots"

    def repo(self, name: str, check: str) -> pathlib.Path:
        root = self.tmp / name
        root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
        (root / sd_lib.LOCAL_FILE_NAME).write_text(
            f"{sd_lib.LOCAL_BLOCK_START}\ncheck: {check}\n{sd_lib.LOCAL_BLOCK_END}\n", encoding="utf-8")
        return root

    def script(self, name: str, body: str) -> pathlib.Path:
        path = self.tmp / name
        path.write_text(body, encoding="utf-8")
        return path

    def env(self, **overrides: str) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items()
               if key not in ("CI", "GITHUB_ACTIONS", sd_gate_slots.SLOTS_VARIABLE)}
        # The sd:2262 load rule is off: these tests measure the cap, not the machine's load.
        env.update(SD_GATE_SLOTS_DIR=str(self.slots), SD_GATE_SLOT_POLL="0.1", SD_GATE_LOAD_MAX="0",
                   SD_GATE_SETTLE_SECONDS="0", XDG_CONFIG_HOME=str(self.tmp / "config"))
        env.update(overrides)
        return env

    def start(self, root: pathlib.Path, env: dict[str, str], *args: str) -> subprocess.Popen[str]:
        return subprocess.Popen([sys.executable, str(SD_CHECK), "--json", *args], cwd=root, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def finish(self, process: subprocess.Popen[str]) -> tuple[int, dict, str]:
        out, err = process.communicate(timeout=300)
        return process.returncode, json.loads(out) if out.strip() else {}, err


class ConcurrentGates(GateSlotFixture):
    def test_n_concurrent_gates_never_run_more_checks_than_the_cap(self):
        counter = self.tmp / "counter"
        counting = self.script("count.py", COUNTING_CHECK)
        root = self.repo("repo", f"{PY} {shlex.quote(str(counting))} {shlex.quote(str(counter))}")
        gates = [self.start(root, self.env(SD_GATE_SLOTS="2")) for _ in range(5)]
        results = [self.finish(gate) for gate in gates]
        for code, report, err in results:
            self.assertEqual(code, 0, err)
            self.assertEqual(report["status"], "pass", report)
        now, peak = (int(part) for part in counter.read_text().split())
        self.assertEqual(now, 0)
        self.assertLessEqual(peak, 2, f"{peak} checks ran at once under a cap of 2")
        # Five gates on two slots: the cap was reached, so the test measured a queue.
        self.assertEqual(peak, 2)
        self.assertTrue(any("waiting for a gate slot" in err for _, _, err in results))
        self.assertTrue(all(slot_free(self.slots / f"slot.{index}.lock") for index in (1, 2)))

    def test_a_queued_gate_spends_its_timeout_waiting_and_reports_it(self):
        """The wait counts against `--timeout`, so the gate answers inside its caller's bound."""
        root = self.repo("repo", f"{PY} -c pass")
        self.slots.mkdir()
        with open(self.slots / "slot.1.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            started = time.monotonic()
            code, report, err = self.finish(self.start(root, self.env(SD_GATE_SLOTS="1"), "--timeout", "2"))
            elapsed = time.monotonic() - started
        self.assertEqual(code, 1, err)
        self.assertIn("waiting for a gate slot", err)
        check = report["checks"][0]
        self.assertEqual((check["status"], check["exit_code"]), ("fail", None))
        self.assertEqual(check["reason"], "no gate slot came free within 2s")
        self.assertLess(elapsed, 60)


class SlotOwnership(GateSlotFixture):
    def test_a_dead_holders_slot_is_reclaimed_without_a_wait(self):
        """A lock file naming a dead pid is not held: only the kernel lock counts."""
        self.slots.mkdir()
        lock = self.slots / "slot.1.lock"
        gone = subprocess.Popen(["true"])
        gone.wait()
        lock.write_text(f"{gone.pid}\n")
        holder = self.script("holder.py", HOLDER_CHECK)
        root = self.repo("repo", f"{PY} {shlex.quote(str(holder))} {shlex.quote(str(lock))}")
        code, report, err = self.finish(self.start(root, self.env(SD_GATE_SLOTS="1")))
        self.assertEqual(code, 0, f"{err}\n{report}")
        self.assertNotIn("waiting for a gate slot", err)
        self.assertEqual(report["gate_slot"]["path"], str(lock))
        self.assertTrue(slot_free(lock))

    def test_a_nested_gate_runs_inside_its_parents_slot(self):
        """The holder's checks see `SD_GATE_SLOTS=0`: a gate inside a gate never waits on its parent."""
        seen = self.tmp / "seen"
        inner = self.repo("inner", f"{PY} -c " + shlex.quote(
            f"import os; open({str(seen)!r}, 'w').write(os.environ.get('SD_GATE_SLOTS', 'unset'))"))
        outer = self.repo("outer", f"{PY} {shlex.quote(str(SD_CHECK))} -C {shlex.quote(str(inner))}")
        code, report, err = self.finish(self.start(outer, self.env(SD_GATE_SLOTS="1"), "--timeout", "120"))
        self.assertEqual(code, 0, f"{err}\n{report}")
        self.assertEqual(seen.read_text(), "0")
        self.assertEqual(report["gate_slot"]["slots"], 1)
        self.assertNotIn("waiting for a gate slot", report["checks"][0]["stderr"])

    def test_no_cap_and_a_dry_run_take_no_slot(self):
        root = self.repo("repo", f"{PY} -c pass")
        for args, env in ((("--dry-run",), self.env(SD_GATE_SLOTS="1")), ((), self.env(SD_GATE_SLOTS="0")),
                          ((), self.env(CI="true"))):
            with self.subTest(args=args):
                code, report, err = self.finish(self.start(root, env, *args))
                self.assertEqual(code, 0, err)
        self.assertFalse(self.slots.exists())


class SlotCount(unittest.TestCase):
    def test_the_variable_then_ci_then_the_machine_setting_then_a_quarter_of_the_cores(self):
        configured = sd_gate_slots.configured
        self.assertEqual(configured({"SD_GATE_SLOTS": "3", "CI": "1"}, "7"), (3, "SD_GATE_SLOTS"))
        self.assertEqual(configured({"CI": "1"}, "7"), (0, "CI"))
        self.assertEqual(configured({}, "7"), (7, "sd.gate_slots"))
        self.assertEqual(configured({}, None), (sd_gate_slots.default_slots(), "default"))
        self.assertEqual([sd_gate_slots.default_slots(cores) for cores in (1, 4, 8, 16, 32)], [1, 1, 2, 4, 8])
        for bad in ("", "-1", "two", "٣"):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                configured({"SD_GATE_SLOTS": bad}, None)

    def test_the_machine_setting_is_a_declared_core_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / "sd-ai-command-pack" / "config.json"
            config.parent.mkdir()
            config.write_text(json.dumps({"config": {"sd": {"gate_slots": "3"}}}))
            self.assertEqual(sd_lib.core_setting("gate_slots", {"XDG_CONFIG_HOME": tmp}), "3")
            config.write_text(json.dumps({"config": {"sd": {"gate_slots": "three"}}}))
            with self.assertRaises(sd_lib.ConfigError):
                sd_lib.core_setting("gate_slots", {"XDG_CONFIG_HOME": tmp})

    def test_a_waiter_reports_while_queued_and_stops_at_its_deadline(self):
        with tempfile.TemporaryDirectory() as tmp, open(pathlib.Path(tmp) / "slot.1.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with open(pathlib.Path(tmp) / "slot.1.lock", "a") as mine:
                ticks = iter(range(0, 1000, 30))
                stream = io.StringIO()
                taken = sd_gate_slots.wait_for_slot([mine.fileno()], pathlib.Path(tmp), poll=0.001, stream=stream,
                                                    deadline=150, clock=lambda: float(next(ticks)))
        self.assertIsNone(taken)
        lines = stream.getvalue().splitlines()
        self.assertTrue(lines[0].startswith("waiting for a gate slot: 1 of 1 in use"), lines)
        self.assertTrue(any(line.startswith("still waiting for a gate slot after") for line in lines), lines)


class SignalForwarding(unittest.TestCase):
    def test_a_stop_signal_for_a_group_that_is_gone_is_not_an_error(self):
        """sd:2402. macOS answers `killpg` on a group that already exited with EPERM, not only ESRCH."""
        handlers: dict[int, object] = {}

        class Child:
            pid = 999999

            def wait(self) -> int:
                handlers[signal.SIGTERM](signal.SIGTERM, None)
                return 0

        def record(signum: int, handler: object) -> object:
            handlers[signum] = handler
            return signal.SIG_DFL

        for error in (PermissionError, ProcessLookupError):
            with self.subTest(error=error.__name__), \
                    mock.patch.object(sd_gate_slots.subprocess, "Popen", return_value=Child()), \
                    mock.patch.object(sd_gate_slots.signal, "signal", side_effect=record), \
                    mock.patch.object(sd_gate_slots.os, "killpg", side_effect=error) as killpg:
                code = sd_gate_slots.run_gated(["true"], {}, slots=0, rule=sd_gate_slots.LoadRule(0, 0, "off"),
                                               stream=io.StringIO())
                self.assertEqual(code, 0)
                killpg.assert_called_once_with(Child.pid, signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
