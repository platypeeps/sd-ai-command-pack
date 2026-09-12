"""What one gate run may not do to another one in the same checkout.

Item 522. Three writer lanes lost a round to the same defect on one day, each
concluding independently that a red local gate was their own change. It was
not: `run-tests.sh` opened by running `rm -f .coverage .coverage.*` and
truncating `unittest-output.log` at the repo root, so the names it wrote were
shared and mutable from a run's first second to its last. That is harmless
while a checkout holds one run, and a killed parent is how a checkout comes to
hold two without anyone deciding to. The shell is reparented and keeps going,
and the `coverage run` children outlive it either way -- stopping a clean run
left the script alive with two coverage processes still writing.

Every case here was reproduced against the script before it was fixed, which is
why these are the tests that exist and not others:

* an orphan survived its killed parent with its whole shard tree, and
  appended its own output into the *next* run's `unittest-output.log`, which
  is how one lane's log came to describe tests it had not run;
* a run starting in the checkout deleted a live run's coverage shard two
  seconds after it started, leaving the live run to combine data that was no
  longer there -- the "no data collected" failure over a passing suite;
* a publish that could not write the root reported the tests' own exit status,
  handing the next reader a stale log under a zero exit -- once per destructive
  step, since the three guards are independent;
* a launcher that died while the shard logs were being concatenated, after the
  shards themselves were done, left an orphan that published anyway;
* a signal delivered while the root was being rewritten left it holding the old
  shards deleted and the new ones never moved in.

Neither is provable from reading the script, and neither is cheap to
rediscover: the failure presents as a red gate on the lane's own diff, so the
honest response is to go and investigate the diff. So both are asserted here
against the real harness, run against a throwaway repo root.

These tests spend wall-clock time on purpose. The defect only exists in the
window where two runs overlap, and a test that refuses to wait for that window
cannot see it.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / ".github/scripts/run-tests.sh"
SITECUSTOMIZE = REPO_ROOT / "tests/coverage_sitecustomize/sitecustomize.py"

# The slow module holds the run open for as long as the overlap needs; the
# padding is what makes `ls -S` schedule it first, as it does in the real repo.
SLOW_MODULE = '''import os
import time
import unittest


class Slow(unittest.TestCase):
    def test_slow(self):
        time.sleep(float(os.environ.get("HARNESS_FIXTURE_SLEEP", "12")))
        self.assertTrue(True)


# {padding}
'''

FAST_MODULE = """import unittest


class Fast(unittest.TestCase):
    def test_fast(self):
        self.assertTrue(True)
"""

COVERAGERC = """[run]
include =
    tests/*.py
parallel = True
branch = True
"""


PUBLISH_RM_PREFIX = 'rm -f "$REPO_ROOT/.coverage"'


def _widen_publish_window(harness):
    """Hold the publish open for two seconds, in this copy of the script only.

    The window between the destructive `rm` and the `mv` that refills the root
    is a few milliseconds, which is too short for a test to aim a signal at: a
    first version of the signal test below polled for that window, never landed
    a signal in it, and reported a pass having tested nothing. Inserting a sleep
    changes the width of the window and nothing else -- the same statements run
    in the same order with the same traps installed.

    A missing anchor raises rather than no-oping, so a future edit that moves
    the publish block fails this test loudly instead of making it vacuous again.
    """
    lines = harness.read_text().splitlines(keepends=True)
    anchors = [i for i, line in enumerate(lines) if line.startswith(PUBLISH_RM_PREFIX)]
    if len(anchors) != 1:
        raise AssertionError(
            f"expected exactly one publish `rm` line to widen, found {len(anchors)}: "
            "the publish block moved, and this test would otherwise assert nothing"
        )
    lines.insert(anchors[0] + 1, "sleep 2\n")
    harness.write_text("".join(lines))


CONCAT_ANCHOR = 'for module in "${modules[@]}"; do'
CONCAT_SENTINEL = ".harness-assembling"


def _widen_assembly_window(harness):
    """Hold the log-assembly step open, in this copy of the script only.

    Between the shard `wait` and the publish the script concatenates the shard
    logs, and a launcher that dies in there leaves an orphan that goes on to
    write the shared root files -- which is why the watchdog stand-down sits
    after this loop and not before it. That placement had no regression guard:
    moving the stand-down back up left the whole suite green.

    The inserted sentinel is what the test waits on, so the kill lands inside
    the window instead of near it, and a missing anchor raises rather than
    no-oping.
    """
    lines = harness.read_text().splitlines(keepends=True)
    anchors = [i for i, line in enumerate(lines) if line.startswith(CONCAT_ANCHOR)]
    if len(anchors) != 1:
        raise AssertionError(
            f"expected exactly one log-assembly loop to widen, found {len(anchors)}: "
            "the assembly step moved, and this test would otherwise assert nothing"
        )
    lines.insert(anchors[0], f': > "$REPO_ROOT/{CONCAT_SENTINEL}"\nsleep 10\n')
    harness.write_text("".join(lines))


def _build_fixture(root, widen_publish=False, widen_assembly=False):
    """A throwaway repo root the real `run-tests.sh` can be run against.

    The harness derives its own root from `BASH_SOURCE`, so a copy of it under
    `<root>/.github/scripts/` measures this fixture and nothing else. The tests
    it discovers are the two written here, not this repository's suite.
    """
    scripts = root / ".github" / "scripts"
    scripts.mkdir(parents=True)
    harness = scripts / "run-tests.sh"
    shutil.copy2(HARNESS, harness)
    if widen_publish:
        _widen_publish_window(harness)
    if widen_assembly:
        _widen_assembly_window(harness)

    tests = root / "tests"
    (tests / "coverage_sitecustomize").mkdir(parents=True)
    shutil.copy2(SITECUSTOMIZE, tests / "coverage_sitecustomize" / "sitecustomize.py")
    (tests / "test_aaa_slow.py").write_text(SLOW_MODULE.format(padding="x" * 2000))
    (tests / "test_bb_fast.py").write_text(FAST_MODULE)
    (root / ".coveragerc").write_text(COVERAGERC)
    return harness


def _fixture_env(**overrides):
    """The ambient environment minus everything the outer gate run exports.

    Inheriting `COVERAGE_FILE` or `PYTHONPATH` from the run measuring *this*
    file would let the fixture's shards land in the outer run's collection.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COVERAGE_") and key != "PYTHONPATH"
    }
    env["PYTHON_BIN"] = sys.executable
    env["TEST_WORKERS"] = "2"
    env.update(overrides)
    return env


def _process_rows():
    """Every pid `ps` lists, mapped to its parent and its state letter.

    The state is read because a reaped-but-not-collected child still has a row.
    A test that counted those as survivors would report an orphan wherever PID 1
    does not reap promptly -- a container, most of the time -- and the failure
    would look exactly like the defect this module exists to catch.
    """
    proc = subprocess.run(
        ["ps", "-A", "-o", "pid=", "-o", "ppid=", "-o", "state="],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        # A `ps` that failed would otherwise read as an empty process table,
        # which makes every pid look dead and every orphan assertion below pass
        # without having observed anything.
        raise RuntimeError(
            f"ps exited {proc.returncode} and the process table cannot be read: "
            f"{proc.stderr.strip()!r}"
        )
    rows = {}
    for line in proc.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
            state = fields[2] if len(fields) >= 3 else ""
            rows[int(fields[0])] = (int(fields[1]), state)
    if not rows:
        raise RuntimeError("ps returned no usable rows; the process table is unreadable")
    return rows


def _parent_map():
    """Every pid `ps` lists, mapped to its parent."""
    return {pid: parent for pid, (parent, _) in _process_rows().items()}


def _descendants(pid):
    """Every live process under `pid`, parent chain walked from `ps`."""
    table = _parent_map()
    children = {}
    for child, parent in table.items():
        children.setdefault(parent, []).append(child)
    found = []
    stack = list(children.get(pid, []))
    while stack:
        current = stack.pop()
        found.append(current)
        stack.extend(children.get(current, []))
    return found


def _alive(pid):
    """Whether `pid` is still running, a zombie row not being running."""
    row = _process_rows().get(pid)
    return row is not None and not row[1].startswith("Z")


def _wait_for(predicate, timeout, interval=0.25):
    """Poll `predicate` until it is truthy or `timeout` seconds pass."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)
    return predicate()


def _shards(root):
    return sorted(path.name for path in root.glob(".coverage.*"))


def _blocks(root):
    """How many `unittest` summaries the published log holds."""
    log = root / "unittest-output.log"
    if not log.exists():
        return 0
    return sum(1 for line in log.read_text().splitlines() if line.startswith("Ran 1 test"))


class OrphanControlTests(unittest.TestCase):
    """A run whose launcher is gone must not outlive it."""

    def test_a_killed_parent_takes_the_whole_shard_tree_with_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = _build_fixture(root)
            log = root / "run.log"
            parent = subprocess.Popen(
                ["bash", "-c", 'bash "$0" > "$1" 2>&1', str(script), str(log)],
                # Longer than the wait below on purpose: a shard that simply
                # ran out of work would clear the tree without the fix, and
                # the test would then pass on the defect it exists to catch.
                env=_fixture_env(HARNESS_FIXTURE_SLEEP="120"),
            )
            tree = []
            try:
                # The tree is the script, xargs, a wrapper shell and a coverage
                # process; wait for it rather than assuming a startup time.
                tree = _wait_for(
                    lambda: [
                        pid
                        for pid in _descendants(parent.pid)
                        if len(_descendants(parent.pid)) >= 3
                    ],
                    timeout=60,
                )
                self.assertTrue(tree, log.read_text() if log.exists() else "no tree")

                parent.kill()
                parent.wait(timeout=30)

                cleared = _wait_for(
                    lambda: not [pid for pid in tree if _alive(pid)],
                    timeout=30,
                )
                self.assertTrue(
                    cleared,
                    "the shard tree outlived the process that started it: "
                    f"{[pid for pid in tree if _alive(pid)]}",
                )
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=30)
                for pid in tree:
                    # Resolved from this run's own tree, never a name pattern:
                    # the basename is identical in every worktree on the box.
                    try:
                        os.kill(pid, 9)
                    except OSError:
                        pass


class InFlightIsolationTests(unittest.TestCase):
    """A second run starting must not touch the first run's data."""

    def test_a_second_run_leaves_a_live_runs_results_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = _build_fixture(root)
            slow_log = root / "slow.log"
            with open(slow_log, "w", encoding="utf-8") as handle:
                slow = subprocess.Popen(
                    ["bash", str(script)],
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    env=_fixture_env(HARNESS_FIXTURE_SLEEP="30"),
                )
                try:
                    _wait_for(lambda: len(_descendants(slow.pid)) >= 2, timeout=60)

                    fast = subprocess.run(
                        ["bash", str(script)],
                        capture_output=True,
                        text=True,
                        env=_fixture_env(HARNESS_FIXTURE_SLEEP="0"),
                        check=False,
                    )
                    self.assertEqual(fast.returncode, 0, fast.stdout + fast.stderr)
                    self.assertIsNone(
                        slow.poll(),
                        "the long run finished first; the overlap never happened",
                    )

                    self.assertEqual(slow.wait(timeout=180), 0, slow_log.read_text())
                finally:
                    if slow.poll() is None:
                        slow.kill()
                        slow.wait(timeout=30)

            # The long run published last, so the repo root must hold its two
            # modules and its two shards -- not a blend of both runs, which is
            # what the pre-fix script produced here (four blocks, three shards).
            self.assertEqual(_blocks(root), 2, (root / "unittest-output.log").read_text())
            self.assertEqual(len(_shards(root)), 2, _shards(root))


class PublishFailureTests(unittest.TestCase):
    """A publish that cannot land must not report the tests' success.

    One case per destructive step, because the guards are independent: a test
    that only breaks the last of them leaves the other two free to lose their
    `|| publish_status=1` in a later edit with the suite still green.

    None of the three depends on file permissions. A suite running as root
    ignores them, and skipping there is not available either -- `make test`
    fails the gate on any skipped test -- so the failures are arranged with a
    directory where a file has to be written, which refuses every user, and with
    a failing `mv` on PATH.
    """

    def _run(self, root, script, env=None):
        return subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            env=env or _fixture_env(HARNESS_FIXTURE_SLEEP="0"),
            check=False,
        )

    def _assert_reported(self, result):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("could not publish this run's results", result.stderr)

    def test_a_clearing_step_that_fails_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = _build_fixture(root)
            # `rm -f` refuses a directory for every user, root included.
            (root / ".coverage").mkdir()
            self._assert_reported(self._run(root, script))

    def test_a_move_that_fails_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = _build_fixture(root)
            # The shard names carry a pid and a random suffix, so the move
            # cannot be blocked by preparing its destination, and within one
            # filesystem it is a rename that permissions do not stop under root.
            # A failing `mv` earlier on PATH is the portable way in. The sentinel
            # is asserted so that a script which stopped calling `mv` -- or
            # called it by absolute path -- fails here instead of passing.
            shim_dir = root / "shim"
            shim_dir.mkdir()
            sentinel = root / "mv-was-called"
            shim = shim_dir / "mv"
            shim.write_text(f'#!/bin/sh\n: > "{sentinel}"\nexit 1\n')
            shim.chmod(0o755)
            env = _fixture_env(HARNESS_FIXTURE_SLEEP="0")
            env["PATH"] = f"{shim_dir}:{env['PATH']}"

            self._assert_reported(self._run(root, script, env))
            self.assertTrue(sentinel.exists(), "the failing `mv` was never called")

    def test_a_log_write_that_fails_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = _build_fixture(root)
            (root / "unittest-output.log").mkdir()
            self._assert_reported(self._run(root, script))

    def test_an_assembly_write_that_fails_publishes_nothing(self):
        # The run's own log is evidence: `make test` reads it to decide whether
        # anything was skipped, so an append that failed half way would publish
        # a log missing those shards and pass the skip gate by omission. The
        # shim fails the per-shard appends and lets the run's own log through,
        # which is how the two `cat` calls are told apart.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = _build_fixture(root)

            clean = self._run(root, script)
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            published = root / "unittest-output.log"
            published.write_text("PREVIOUS COMPLETE RUN\n" + published.read_text())

            shim_dir = root / "shim"
            shim_dir.mkdir()
            sentinel = root / "cat-was-refused"
            shim = shim_dir / "cat"
            shim.write_text(
                "#!/bin/sh\n"
                "for arg in \"$@\"; do\n"
                "  case \"$arg\" in\n"
                "    */unittest-output.log) exec /bin/cat \"$@\" ;;\n"
                "  esac\n"
                "done\n"
                f': > "{sentinel}"\n'
                "exit 1\n"
            )
            shim.chmod(0o755)
            env = _fixture_env(HARNESS_FIXTURE_SLEEP="0")
            env["PATH"] = f"{shim_dir}:{env['PATH']}"

            blocked = self._run(root, script, env)
            self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
            self.assertIn("could not assemble this run's log", blocked.stderr)
            self.assertTrue(sentinel.exists(), "the failing `cat` was never called")
            self.assertTrue(
                published.read_text().startswith("PREVIOUS COMPLETE RUN"),
                "a run that could not assemble its log published anyway",
            )


class AssemblyWindowTests(unittest.TestCase):
    """A launcher that dies while the log is being assembled leaves no orphan."""

    def test_a_launcher_dying_during_assembly_publishes_nothing(self):
        # The window between the shard `wait` and the publish is why the
        # watchdog stand-down sits after the assembly loop rather than before
        # it. Nothing asserted that until now: moving the stand-down back up to
        # the shard `wait` left every other test in this module green.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = _build_fixture(root, widen_assembly=True)
            env = _fixture_env(HARNESS_FIXTURE_SLEEP="0")

            first = subprocess.run(
                ["bash", str(script)],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            # A marker the orphan would erase by publishing over it.
            published = root / "unittest-output.log"
            marker = "PREVIOUS COMPLETE RUN\n" + published.read_text()
            published.write_text(marker)

            # The first run left one behind; waiting on a stale sentinel would
            # sample the second run before it had started anything.
            sentinel = root / CONCAT_SENTINEL
            sentinel.unlink()

            log = root / "assembly.log"
            parent = subprocess.Popen(
                ["bash", "-c", 'bash "$0" > "$1" 2>&1', str(script), str(log)],
                env=env,
            )
            tree = []
            try:
                self.assertTrue(
                    _wait_for(sentinel.exists, timeout=120),
                    "the run never reached the log-assembly step",
                )
                tree = _descendants(parent.pid)
                self.assertTrue(tree, "the run had already finished")

                parent.kill()
                parent.wait(timeout=30)

                self.assertTrue(
                    _wait_for(
                        lambda: not [pid for pid in tree if _alive(pid)],
                        timeout=60,
                    ),
                    "the run outlived the launcher that died during assembly: "
                    f"{[pid for pid in tree if _alive(pid)]}",
                )
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=30)
                for pid in tree:
                    try:
                        os.kill(pid, 9)
                    except OSError:
                        pass

            self.assertTrue(
                published.read_text().startswith("PREVIOUS COMPLETE RUN"),
                "the orphan published over the last complete run's results",
            )
            self.assertEqual(len(_shards(root)), 2, _shards(root))


class PublishSignalTests(unittest.TestCase):
    """An operator's signal must not cut the publish in half."""

    def test_a_signal_during_the_publish_cannot_halve_the_root(self):
        # Standing the watchdog down does not make the publish uninterruptible:
        # the INT/TERM/HUP trap would still fire between the `rm` and the `mv`
        # and exit with the old shards deleted and the new ones never moved in.
        # Reproduced with the window held open, before the signals were masked:
        # `exit=143 terms=13 blocks=2 shards=0` -- no coverage at the root at
        # all, under a log describing the run before it, which is what a later
        # `coverage combine` reports as "no data collected" over a passing suite.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = _build_fixture(root, widen_publish=True)
            env = _fixture_env(HARNESS_FIXTURE_SLEEP="1")

            first = subprocess.run(
                ["bash", str(script)],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            log = root / "second.log"
            with open(log, "w", encoding="utf-8") as handle:
                second = subprocess.Popen(
                    ["bash", str(script)],
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                try:
                    self.assertTrue(
                        _wait_for(lambda: bool(_descendants(second.pid)), timeout=60),
                        "the shard phase never started",
                    )
                    # The window is read off the filesystem rather than off the
                    # process tree: the first run left two shards at the root, so
                    # a live run with none there is one that has run the
                    # destructive `rm` and not yet the `mv`. Counting processes
                    # instead does not work -- the widening sleep is a child of
                    # the script, so the tree never empties.
                    _wait_for(
                        lambda: second.poll() is not None or not _shards(root),
                        timeout=120,
                    )
                    delivered = 0
                    while second.poll() is None:
                        try:
                            os.kill(second.pid, signal.SIGTERM)
                        except OSError:
                            break
                        delivered += 1
                        time.sleep(0.05)
                    self.assertGreater(
                        delivered,
                        0,
                        "no signal reached the run; this assertion tested nothing",
                    )
                finally:
                    if second.poll() is None:
                        second.kill()
                    second.wait(timeout=30)

            self.assertEqual(second.returncode, 0, log.read_text())
            self.assertEqual(_blocks(root), 2, (root / "unittest-output.log").read_text())
            self.assertEqual(len(_shards(root)), 2, _shards(root))


if __name__ == "__main__":
    unittest.main()
