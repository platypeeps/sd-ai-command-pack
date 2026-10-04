"""A module `run-tests.sh` splits by test id may not hold a fixture that runs once.

`SPLIT_MODULES` in `.github/scripts/run-tests.sh` names the modules the runner
splits into shards by test id. A split runs a class or module fixture once per
shard that holds one of its tests: with three workers a `setUpClass` ran three
times (review of #913, N2). The runner used to state that the listed modules
have no such fixture; it now checks every module it is about to split and stops
the run, naming the fixture, when one has any.

The harness derives its root from `BASH_SOURCE`, so a copy under a throwaway
`<root>/.github/scripts/` runs against the fixture modules written here. They
take the real split names, which is the only way into the split path.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / ".github/scripts/run-tests.sh"

# Dropped from the fixture run. `PYTHONPATH` would point the copy below at the
# outer run's path; `TEST_CHANGED_FILES` is the changed-files fast path
# (sd:10 criterion 16), which `make check CHANGED=...` exports to this process
# and which that copy reads. It is inert only while this harness copies
# `run-tests.sh` alone and not `select-tests.py`, so an outer narrowed run
# would start narrowing its own nested runs the day a fixture copies
# `.github/scripts` whole. Drop it, and `CHANGED` with it. `SD_GATE_POOL_SIZE`
# is the outer gate's cap (sd:2607), which would set a fixture's worker count.
DROPPED_FROM_FIXTURES = ("PYTHONPATH", "TEST_CHANGED_FILES", "CHANGED", "SD_GATE_POOL_SIZE")


def fixture_env(**overrides: str) -> dict[str, str]:
    """The ambient environment minus everything the outer gate run exports."""
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("COVERAGE_", "SD_COVERAGE_"))
                   and key not in DROPPED_FROM_FIXTURES}
    environment.update(overrides)
    return environment

COVERAGERC = """[run]
include =
    bin/nothing.py
parallel = True
"""

PLAIN = """import unittest


class Plain(unittest.TestCase):
    def setUp(self):
        self.ready = True

    def test_one(self):
        self.assertTrue(self.ready)

    def test_two(self):
        self.assertTrue(self.ready)
"""

FOUR_TESTS = PLAIN + """
    def test_three(self):
        self.assertTrue(self.ready)

    def test_four(self):
        self.assertTrue(self.ready)
"""

CLASS_FIXTURE = """import os
import pathlib
import unittest


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with pathlib.Path(os.environ["FIXTURE_COUNTER"]).open("a") as counter:
            counter.write("x")


class Inherits(Base):
    def test_one(self):
        pass

    def test_two(self):
        pass
"""

MODULE_FIXTURE = """import unittest


def setUpModule():
    pass


class WithModuleFixture(unittest.TestCase):
    def test_one(self):
        pass

    def test_two(self):
        pass
"""

LOAD_TESTS_ELSEWHERE = """import unittest

from tests.test_sd_ship import Plain


def load_tests(loader, standard_tests, pattern):
    return loader.loadTestsFromTestCase(Plain)
"""

# Prints the niceness the shard runs at, so a test can compare it with its own.
# `getpriority` reads it; `os.nice(0)` raises EPERM on macOS at niceness 20,
# which a nested run reaches under an outer gate's `nice -n 10`.
NICENESS_PROBE = """import os
import unittest


class Probe(unittest.TestCase):
    def test_niceness(self):
        print(f"shard niceness={os.getpriority(os.PRIO_PROCESS, 0)}")
"""

#: The header and footer `run-tests.sh` writes on stderr around a run (sd:1407, sd:2080).
START_LINE = r"run-tests: start head=(\S+) dirty=\S+ content=(\S+) pid=(\d+) at=\S+"
END_LINE = r"run-tests: end head=(\S+) content=(\S+) pid=(\d+) exit=\d+ at=\S+"

#: A shard that edits the fixture's tracked file while the run is under way.
EDITS_MID_RUN = PLAIN + """
    def test_three(self):
        import os
        import pathlib
        notes = pathlib.Path(os.environ["FIXTURE_COUNTER"]).parent / "notes.txt"
        notes.write_text("edited mid-run\\n")
"""

SPLIT_NAMES =("test_sd_ship", "test_sd_ship_dispositions", "test_sd_ship_disposition_guards")


class SplitModuleFixtures(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = pathlib.Path(scratch.name).resolve()
        scripts = self.root / ".github/scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(HARNESS, scripts / "run-tests.sh")
        (self.root / "tests").mkdir()
        (self.root / ".coveragerc").write_text(COVERAGERC)
        self.counter = self.root / "setupclass-runs"
        self.programs = self.root / "programs"
        self.programs.mkdir()
        getconf = self.programs / "getconf"
        getconf.write_text('#!/bin/sh\nprintf "%s\\n" "${FIXTURE_CORES:-4}"\n')
        getconf.chmod(0o755)

    def run_harness(self, *, workers="2", environment=None, **modules: str) -> subprocess.CompletedProcess:
        for name in SPLIT_NAMES:
            (self.root / "tests" / f"{name}.py").write_text(modules.get(name, PLAIN))
        env = fixture_env(
            PYTHON_BIN=sys.executable,
            FIXTURE_COUNTER=str(self.counter),
            PYTHONDONTWRITEBYTECODE="1",
            CI="",
            GITHUB_ACTIONS="",
            PATH=str(self.programs) + os.pathsep + os.environ["PATH"],
        )
        env.pop("TEST_WORKERS", None)
        if workers is not None:
            env["TEST_WORKERS"] = workers
        env.update(environment or {})
        return subprocess.run(["bash", str(self.root / ".github/scripts/run-tests.sh")], cwd=self.root,
                              env=env, text=True, capture_output=True, timeout=300)

    def test_ci_uses_all_cores_and_local_uses_half(self) -> None:
        """sd:1955. Two gate slots at half the cores each fill the machine and no more."""
        for environment, workers in (({}, 2), ({"FIXTURE_CORES": "5"}, 2), ({"FIXTURE_CORES": "16"}, 8),
                                     ({"CI": "1"}, 4), ({"GITHUB_ACTIONS": "true"}, 4)):
            with self.subTest(environment=environment):
                result = self.run_harness(workers=None, environment=environment)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"test runner: workers={workers} ", result.stdout)

    def test_local_workers_follow_the_gate_cap_so_the_pool_holds_twice_the_cores(self) -> None:
        """sd:2607: the cap a holder names, else this run's own, sets the workers; CI and an explicit count win."""
        for environment, workers in (({"FIXTURE_CORES": "16", "SD_GATE_POOL_SIZE": "4", "SD_GATE_SLOTS": "0"}, 8),
                                     ({"FIXTURE_CORES": "16", "SD_GATE_POOL_SIZE": "2", "SD_GATE_SLOTS": "0"}, 16),
                                     ({"FIXTURE_CORES": "16", "SD_GATE_POOL_SIZE": "8", "SD_GATE_SLOTS": "0"}, 4),
                                     ({"FIXTURE_CORES": "16", "SD_GATE_POOL_SIZE": "1", "SD_GATE_SLOTS": "0"}, 16),
                                     ({"FIXTURE_CORES": "16", "SD_GATE_POOL_SIZE": "64", "SD_GATE_SLOTS": "0"}, 1),
                                     ({"FIXTURE_CORES": "16", "SD_GATE_POOL_SIZE": "0", "SD_GATE_SLOTS": "0"}, 8),
                                     ({"FIXTURE_CORES": "16", "SD_GATE_POOL_SIZE": "4", "CI": "1"}, 16)):
            with self.subTest(environment=environment):
                result = self.run_harness(workers=None, environment=environment)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"test runner: workers={workers} ", result.stdout)

    def test_local_shards_run_below_the_launcher_priority_and_ci_shards_do_not(self) -> None:
        """sd:1955. A local gate yields the CPU to the runner daemon and the sessions."""
        launcher = os.getpriority(os.PRIO_PROCESS, 0)
        for environment, lowered in (({}, True), ({"CI": "1"}, False)):
            with self.subTest(environment=environment):
                result = self.run_harness(environment=environment, test_sd_ship=NICENESS_PROBE)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                shard = int(re.search(r"^shard niceness=(-?\d+)$", result.stdout, re.MULTILINE).group(1))
                if lowered:
                    self.assertGreater(shard, launcher, result.stdout)
                else:
                    self.assertEqual(shard, launcher, result.stdout)

    def test_explicit_worker_limit_is_preserved_in_ci(self) -> None:
        result = self.run_harness(workers="2", environment={"CI": "true"},
                                  **dict.fromkeys(SPLIT_NAMES, FOUR_TESTS))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(re.findall(r"^Ran 2 tests", result.stdout, re.MULTILINE)), 6, result.stdout)

    def test_single_or_zero_reported_cores_still_get_one_worker(self) -> None:
        for cores, ci in (("0", "1"), ("1", "1"), ("0", ""), ("1", "")):
            with self.subTest(cores=cores, ci=ci):
                result = self.run_harness(workers=None, environment={"CI": ci, "FIXTURE_CORES": cores})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(len(re.findall(r"^Ran 2 tests", result.stdout, re.MULTILINE)), 3, result.stdout)

    def test_invalid_explicit_worker_limit_refuses_before_tests(self) -> None:
        for workers in ("0", "many"):
            with self.subTest(workers=workers):
                result = self.run_harness(workers=workers)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("TEST_WORKERS must be a positive integer", result.stderr)
                self.assertFalse((self.root / "unittest-output.log").exists())

    def test_split_modules_without_fixtures_are_split(self) -> None:
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Two tests in each of three modules, two shards each.
        self.assertEqual(len(re.findall(r"^Ran 1 test", result.stdout, re.MULTILINE)), 6, result.stdout)
        self.assertIn("test runner: workers=2 shards=6", result.stdout)
        summaries = re.findall(r"^shard (\S+): (\d+)s exit=(\d+)$", result.stdout, re.MULTILINE)
        self.assertEqual({name for name, _, _ in summaries},
                         {f"tests.{name}.part{part}of2" for name in SPLIT_NAMES for part in (1, 2)})
        self.assertEqual([status for _, _, status in summaries], ["0"] * 6)

    def commit_fixture(self) -> str:
        """Make the fixture root a repository with one tracked `notes.txt`."""
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        (self.root / ".gitignore").write_text("unittest-output.log\n.coverage\n.coverage.*\n__pycache__/\n")
        (self.root / "notes.txt").write_text("zero\n")
        subprocess.run(git + ["init", "-q"], cwd=self.root, check=True)
        subprocess.run(git + ["add", "-A"], cwd=self.root, check=True)
        subprocess.run(git + ["commit", "-qm", "fixture"], cwd=self.root, check=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def ends(self, result: subprocess.CompletedProcess) -> tuple[re.Match, re.Match]:
        """The run's start and end lines from stderr, each found exactly once."""
        starts = [match for line in result.stderr.splitlines() if (match := re.fullmatch(START_LINE, line))]
        ends = [match for line in result.stderr.splitlines() if (match := re.fullmatch(END_LINE, line))]
        self.assertEqual((len(starts), len(ends)), (1, 1), result.stderr)
        return starts[0], ends[0]

    def test_the_log_names_its_tree_and_each_result_its_shard(self) -> None:
        """sd:2080. The start line names the tree by content, the end line
        closes the same run on the same tree, and every `Ran` line sits inside
        its own shard's start and end lines. A `Ran` printed before its
        shard's only label was credited to the shard above it by any
        positional parse."""
        head = self.commit_fixture()
        contents = []
        # Two edits of one already-dirty file: the dirty-path count is the same
        # for both, so only a content fingerprint tells the runs apart.
        for text in ("one\n", "two\n"):
            (self.root / "notes.txt").write_text(text)
            result = self.run_harness()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            start, end = self.ends(result)
            self.assertEqual((start.group(1), end.group(1)), (head, head))
            # Nothing changed during the run, so it opens and closes on one tree.
            self.assertEqual(end.group(2), start.group(2))
            self.assertEqual(end.group(3), start.group(3))
            contents.append(start.group(2))
        self.assertNotIn("unknown", contents)
        self.assertNotEqual(contents[0], contents[1])
        current, labelled = None, 0
        for line in result.stdout.splitlines():
            if match := re.fullmatch(r"shard (\S+): start", line):
                self.assertIsNone(current, line)
                current = match.group(1)
            elif match := re.fullmatch(r"shard (\S+): \d+s exit=\d+", line):
                self.assertEqual(match.group(1), current, line)
                current, labelled = None, labelled + 1
            elif line.startswith("Ran "):
                self.assertIsNotNone(current, f"{line!r} sits outside any shard")
        self.assertEqual(labelled, 6, result.stdout)

    def test_the_footer_reads_the_tree_after_the_run(self) -> None:
        """sd:2080, Copilot on #1178. Equal fingerprints on an unchanged tree
        cannot tell a footer sampled after the shards from one sampled with
        the header. Here a shard edits a tracked file, so the footer must name
        a different tree from the header -- and the same one the next run
        opens on, which proves it read the tree the shards left behind."""
        self.commit_fixture()
        result = self.run_harness(test_sd_ship=EDITS_MID_RUN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "notes.txt").read_text(), "edited mid-run\n")
        start, end = self.ends(result)
        self.assertNotEqual(end.group(2), start.group(2), "the footer read the tree the run started on")
        # The same modules again, so the only difference is what the shards did.
        after = self.run_harness(test_sd_ship=EDITS_MID_RUN)
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
        self.assertEqual(self.ends(after)[0].group(2), end.group(2))

    def test_an_index_flag_does_not_hide_an_edit_from_the_fingerprint(self) -> None:
        """sd:2080 review. The scratch index starts as a copy of the real one,
        whose assume-unchanged and skip-worktree flags make `git add -A` skip
        a file the tests still read from disk. The fingerprint clears them."""
        self.commit_fixture()
        contents = []
        for flag in ("--assume-unchanged", "--skip-worktree"):
            subprocess.run(["git", "update-index", flag, "notes.txt"], cwd=self.root, check=True)
            for text in (f"{flag} one\n", f"{flag} two\n"):
                (self.root / "notes.txt").write_text(text)
                result = self.run_harness()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                contents.append(self.ends(result)[0].group(2))
            subprocess.run(["git", "update-index", flag.replace("--", "--no-", 1), "notes.txt"],
                           cwd=self.root, check=True)
        self.assertNotIn("unknown", contents)
        self.assertEqual(len(set(contents)), 4, contents)

    def test_shard_timing_does_not_hide_a_failed_test(self) -> None:
        failing = PLAIN.replace("self.assertTrue(self.ready)", "self.assertFalse(self.ready)")
        result = self.run_harness(test_sd_ship=failing)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAILED (failures=1)", result.stdout)
        self.assertRegex(result.stdout, r"shard tests\.test_sd_ship\.part1of2: \d+s exit=1")
        self.assertEqual((self.root / "unittest-output.log").read_text(), result.stdout)

    def test_an_inherited_set_up_class_is_refused_before_anything_runs(self) -> None:
        result = self.run_harness(test_sd_ship=CLASS_FIXTURE)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("error: tests.test_sd_ship is in SPLIT_MODULES", result.stderr)
        self.assertIn("tests.test_sd_ship.Base.setUpClass", result.stderr)
        self.assertFalse(self.counter.exists(), "a shard ran after the refusal")

    def test_a_set_up_module_is_refused(self) -> None:
        result = self.run_harness(test_sd_ship_disposition_guards=MODULE_FIXTURE)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("error: tests.test_sd_ship_disposition_guards is in SPLIT_MODULES", result.stderr)
        self.assertIn("tests.test_sd_ship_disposition_guards.setUpModule", result.stderr)

    def test_a_load_tests_hook_returning_another_modules_tests_is_refused(self) -> None:
        """The hook's module owns none of the loaded classes; it is checked by name."""
        result = self.run_harness(test_sd_ship_dispositions=LOAD_TESTS_ELSEWHERE)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("tests.test_sd_ship_dispositions.load_tests", result.stderr)


if __name__ == "__main__":
    unittest.main()
