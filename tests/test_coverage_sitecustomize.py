"""Pin the lazy subprocess-coverage start in tests/coverage_sitecustomize.

`run-tests.sh` exports `SD_COVERAGE_PROCESS_START`, and the sitecustomize
starts coverage in a child only when that child runs a file `[run] include`
names. The installer gate cannot prove the lazy start still reaches a child:
most installer lines are measured in the `coverage run` shard itself, so a
hook that never fired in a subprocess could leave the gate green. These cases
run real children and read the data files they leave.

Each way a module body gets executed is its own case, because the hook sees
them differently -- the script on the command line is checked at startup, the
rest arrive as `exec` audit events -- and a regression in one leaves the others
passing.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

import coverage

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SITECUSTOMIZE = REPO_ROOT / "tests/coverage_sitecustomize"

INSTALLER = """def pick(flag):
    if flag:
        return "yes"
    return "no"


BODY_RAN = pick(True)
"""

CONFIG = """[run]
include =
    bin/sd_install.py
parallel = True
branch = True
"""


class LazySubprocessCoverage(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = pathlib.Path(scratch.name).resolve()
        (self.root / "bin").mkdir()
        self.installer = self.root / "bin/sd_install.py"
        self.installer.write_text(INSTALLER)
        (self.root / "bin/other.py").write_text("import sys\nprint('coverage' in sys.modules)\n")
        (self.root / ".coveragerc").write_text(CONFIG)
        self.data = self.root / "data"
        self.data.mkdir()

    def child(self, *argv: str, cwd: pathlib.Path | None = None, extra_path: str = "") -> subprocess.CompletedProcess:
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("COVERAGE_", "SD_COVERAGE_")) and key != "PYTHONPATH"}
        environment.update({
            "PYTHONPATH": str(SITECUSTOMIZE) + (os.pathsep + extra_path if extra_path else ""),
            "SD_COVERAGE_PROCESS_START": str(self.root / ".coveragerc"),
            "COVERAGE_FILE": str(self.data / ".coverage"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        result = subprocess.run([sys.executable, *argv], cwd=cwd or self.root, env=environment,
                                text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def data_files(self) -> list[pathlib.Path]:
        return sorted(self.data.glob(".coverage.*"))

    def assert_installer_measured(self) -> None:
        files = self.data_files()
        self.assertEqual(len(files), 1, files)
        data = coverage.CoverageData(basename=str(files[0]))
        data.read()
        measured = {os.path.realpath(name): data.lines(name) for name in data.measured_files()}
        lines = measured.get(os.path.realpath(self.installer))
        self.assertTrue(lines, f"sd_install.py was not measured: {measured}")
        # Line 1 is the `def`, executed by the module body: coverage was
        # tracing before the body's first line ran.
        self.assertIn(1, lines)
        self.assertIn(7, lines)

    def test_an_import_starts_coverage_before_the_module_body(self) -> None:
        self.child("-c", "import sys; sys.path.insert(0, 'bin'); import sd_install")
        self.assert_installer_measured()

    def test_the_script_on_the_command_line_is_measured(self) -> None:
        self.child("bin/sd_install.py")
        self.assert_installer_measured()

    def test_a_source_file_loader_with_a_relative_path_is_measured(self) -> None:
        self.child("-c", "import importlib.machinery as m, importlib.util as u; "
                         "loader = m.SourceFileLoader('renamed', 'bin/sd_install.py'); "
                         "module = u.module_from_spec(u.spec_from_loader('renamed', loader)); "
                         "loader.exec_module(module)")
        self.assert_installer_measured()

    def test_runpy_is_measured(self) -> None:
        self.child("-c", "import runpy; runpy.run_path('bin/sd_install.py')")
        self.assert_installer_measured()

    def test_dash_m_is_measured(self) -> None:
        self.child("-m", "sd_install", extra_path=str(self.root / "bin"))
        self.assert_installer_measured()

    def test_a_child_that_runs_nothing_measured_never_loads_coverage(self) -> None:
        result = self.child("bin/other.py")
        self.assertEqual(result.stdout.strip(), "False")
        self.assertEqual(self.data_files(), [])

    def test_the_standard_variable_does_not_leak_to_grandchildren(self) -> None:
        """Left set, coverage's `.pth` would start eagerly in every grandchild."""
        result = self.child("-c", "import os, subprocess, sys; sys.path.insert(0, 'bin'); import sd_install; "
                                  "print(os.environ.get('COVERAGE_PROCESS_START')); "
                                  "print(subprocess.run([sys.executable, '-c', "
                                  "'import os; print(os.environ.get(\"COVERAGE_PROCESS_START\"))'], "
                                  "capture_output=True, text=True).stdout.strip())")
        self.assertEqual(result.stdout.split(), ["None", "None"])
        self.assert_installer_measured()


if __name__ == "__main__":
    unittest.main()
