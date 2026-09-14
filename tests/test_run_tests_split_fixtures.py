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

SPLIT_NAMES = ("test_sd_ship", "test_sd_ship_dispositions", "test_sd_ship_disposition_guards")


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

    def run_harness(self, **modules: str) -> subprocess.CompletedProcess:
        for name in SPLIT_NAMES:
            (self.root / "tests" / f"{name}.py").write_text(modules.get(name, PLAIN))
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("COVERAGE_", "SD_COVERAGE_")) and key != "PYTHONPATH"}
        environment.update({
            "PYTHON_BIN": sys.executable,
            "TEST_WORKERS": "2",
            "FIXTURE_COUNTER": str(self.counter),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return subprocess.run(["bash", str(self.root / ".github/scripts/run-tests.sh")], cwd=self.root,
                              env=environment, text=True, capture_output=True, timeout=300)

    def test_split_modules_without_fixtures_are_split(self) -> None:
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Two tests in each of three modules, two shards each.
        self.assertEqual(len(re.findall(r"^Ran 1 test", result.stdout, re.MULTILINE)), 6, result.stdout)

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


if __name__ == "__main__":
    unittest.main()
