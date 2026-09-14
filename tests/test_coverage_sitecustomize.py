"""Pin the lazy subprocess-coverage start in tests/coverage_sitecustomize.

`run-tests.sh` exports `SD_COVERAGE_PROCESS_START`, and the sitecustomize
starts coverage in a child only when that child runs a file `[run] include`
names. The installer gate cannot prove the lazy start still reaches a child:
most installer lines are measured in the `coverage run` shard itself, so a
hook that never fired in a subprocess could leave the gate green. These cases
run real children and read the data files they leave.

Each way a module body gets executed is its own case, because each hands the
`exec` audit event a code object named differently -- absolute, relative as
the caller wrote it, or through a symlink -- and a regression in one leaves the
others passing. The script on the command line is one of them: there used to
be a separate startup check of `sys.orig_argv` for it, removed because the
interpreter raises the same `exec` event for the main script, which
`test_the_script_on_the_command_line_is_measured` pins.

Matching is pinned from both sides: a symlink to the installer and a symlinked
directory on its path only match through the real path, and a `bin` that is
itself a symlink, or a relative name with a `.` in it, only through the
absolute path as written. A thread case pins the start reaching threads that
were already running. The refusal cases pin the known ways a child goes
unmeasured -- `-I`, `-E` or `-S`, which never load the sitecustomize -- failing
the launching test instead of passing it silently.
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

    def child(self, *argv: str, cwd: pathlib.Path | None = None, extra_path: str = "",
              check: bool = True) -> subprocess.CompletedProcess:
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
        if check:
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

    def test_a_symlinked_launcher_is_measured(self) -> None:
        (self.root / "bin/sd-install").symlink_to("sd_install.py")
        self.child("bin/sd-install")
        self.assert_installer_measured()

    def test_a_script_through_a_symlinked_directory_is_measured(self) -> None:
        (self.root / "linked").symlink_to("bin", target_is_directory=True)
        self.child("linked/sd_install.py")
        self.assert_installer_measured()

    def test_runpy_on_a_symlink_is_measured(self) -> None:
        (self.root / "bin/sd-install").symlink_to("sd_install.py")
        self.child("-c", "import runpy; runpy.run_path('bin/sd-install')")
        self.assert_installer_measured()

    def test_a_pattern_directory_that_is_a_symlink_is_measured(self) -> None:
        """Coverage resolves the pattern too; only the path as written still says `bin`."""
        (self.root / "bin").rename(self.root / "tools")
        (self.root / "bin").symlink_to("tools", target_is_directory=True)
        self.child("bin/sd_install.py")
        self.assert_installer_measured()

    def test_a_relative_name_that_does_not_end_in_the_pattern_is_measured(self) -> None:
        self.child("-c", "import importlib.machinery as m, importlib.util as u; "
                         "loader = m.SourceFileLoader('renamed', 'bin/./sd_install.py'); "
                         "module = u.module_from_spec(u.spec_from_loader('renamed', loader)); "
                         "loader.exec_module(module)")
        self.assert_installer_measured()

    def test_a_module_first_imported_on_a_worker_thread_is_measured_on_the_main_thread(self) -> None:
        """Line 4 runs only on the main thread, after a worker ran the module body."""
        self.child("-c", "import sys, threading; sys.path.insert(0, 'bin'); "
                         "worker = threading.Thread(target=__import__, args=('sd_install',)); "
                         "worker.start(); worker.join(); "
                         "import sd_install; sd_install.pick(False)")
        self.assert_installer_measured()
        data = coverage.CoverageData(basename=str(self.data_files()[0]))
        data.read()
        lines = {os.path.realpath(name): data.lines(name) for name in data.measured_files()}
        self.assertIn(4, lines[os.path.realpath(self.installer)])

    def assert_refused(self, launch: str) -> None:
        result = self.child("-c", launch, check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("would run with -I, -E or -S", result.stderr)
        self.assertEqual(self.data_files(), [])

    def test_a_measured_file_under_dash_capital_i_is_refused(self) -> None:
        self.assert_refused("import subprocess, sys; subprocess.run([sys.executable, '-I', 'bin/sd_install.py'])")

    def test_a_measured_file_under_a_flag_cluster_in_a_shell_line_is_refused(self) -> None:
        self.assert_refused("import subprocess, sys; "
                            "subprocess.run(sys.executable + ' -uE bin/sd_install.py', shell=True)")

    def test_a_measured_file_under_dash_capital_s_through_exec_is_refused(self) -> None:
        self.assert_refused("import os, sys; os.execv(sys.executable, [sys.executable, '-S', 'bin/sd_install.py'])")

    def test_a_measured_file_whose_shebang_skips_site_is_refused(self) -> None:
        self.installer.write_text("#!/usr/bin/env -S python3 -I\n" + INSTALLER)
        self.installer.chmod(0o755)
        (self.root / "bin/sd-install").symlink_to("sd_install.py")
        self.assert_refused("import subprocess; subprocess.run(['bin/sd-install'])")

    def test_launches_the_gate_does_not_measure_are_not_refused(self) -> None:
        elsewhere = self.root / "copy/bin"
        elsewhere.mkdir(parents=True)
        (elsewhere / "sd_install.py").write_text(INSTALLER)
        result = self.child("-c", "import subprocess, sys; "
                                  "print(subprocess.run([sys.executable, '-I', 'bin/other.py']).returncode, "
                                  "subprocess.run([sys.executable, '-I', '-c', 'pass', 'bin/sd_install.py']).returncode, "
                                  "subprocess.run([sys.executable, '-I', 'copy/bin/sd_install.py']).returncode)")
        self.assertEqual(result.stdout.split()[-3:], ["0", "0", "0"])


if __name__ == "__main__":
    unittest.main()
