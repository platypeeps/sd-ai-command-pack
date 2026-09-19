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
# `.github/scripts` whole. Drop it, and `CHANGED` with it.
DROPPED_FROM_FIXTURES = ("PYTHONPATH", "TEST_CHANGED_FILES", "CHANGED")


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

    def test_ci_uses_all_cores_and_local_reserves_one(self) -> None:
        for environment, single_test_shards in (({}, 6), ({"CI": "1"}, 12), ({"GITHUB_ACTIONS": "true"}, 12)):
            with self.subTest(environment=environment):
                result = self.run_harness(workers=None, environment=environment,
                                          **dict.fromkeys(SPLIT_NAMES, FOUR_TESTS))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(len(re.findall(r"^Ran 1 test", result.stdout, re.MULTILINE)),
                                 single_test_shards, result.stdout)

    def test_explicit_worker_limit_is_preserved_in_ci(self) -> None:
        result = self.run_harness(workers="2", environment={"CI": "true"},
                                  **dict.fromkeys(SPLIT_NAMES, FOUR_TESTS))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(re.findall(r"^Ran 2 tests", result.stdout, re.MULTILINE)), 6, result.stdout)

    def test_single_or_zero_reported_cores_still_get_one_worker(self) -> None:
        for cores in ("0", "1"):
            with self.subTest(cores=cores):
                result = self.run_harness(workers=None, environment={"CI": "1", "FIXTURE_CORES": cores})
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
