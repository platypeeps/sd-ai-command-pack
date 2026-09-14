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
              check: bool = True, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("COVERAGE_", "SD_COVERAGE_")) and key != "PYTHONPATH"}
        environment.update({
            "PYTHONPATH": str(SITECUSTOMIZE) + (os.pathsep + extra_path if extra_path else ""),
            "SD_COVERAGE_PROCESS_START": str(self.root / ".coveragerc"),
            "COVERAGE_FILE": str(self.data / ".coverage"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        environment.update(extra_env or {})
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
                                  "subprocess.run([sys.executable, '-I', 'copy/bin/sd_install.py']).returncode, "
                                  "subprocess.run([sys.executable, '-c', '# python -I bin/sd_install.py']).returncode)")
        self.assertEqual(result.stdout.split()[-4:], ["0", "0", "0", "0"])

    def launch(self, argv: list[str]) -> str:
        """A child that launches `argv` and survives the program being absent."""
        return ("import subprocess\ntry:\n"
                f"    subprocess.run({argv!r}, capture_output=True)\n"
                "except FileNotFoundError:\n    pass\nprint('launched')\n")

    #: Command lines whose interpreter-looking word is not at command position,
    #: or sits in a shell's positional arguments rather than its `-c` string.
    NOT_REFUSED = (
        ["grep", "-e", "python", "-E", "bin/sd_install.py"],
        ["rg", "python", "-S", "bin/sd_install.py"],
        ["bash", "-c", "echo python -I bin/sd_install.py"],
        ["bash", "-c", "true", "python -I bin/sd_install.py"],
        ["bash", "-c", "grep -e python -E bin/sd_install.py; true"],
        ["bash", "-c", "(cd sub && true); python -I ../bin/sd_install.py"],
        ["bash", "-c", "cd sub | true; python -I ../bin/sd_install.py"],
        ["bash", "-c", "cd sub & wait; python -I ../bin/sd_install.py"],
        ["bash", "-c", "true # x; python -I bin/sd_install.py"],
        ["bash", "-c", "a=(python -I bin/sd_install.py)"],
        ["bash", "-c", "a=(\npython -I bin/sd_install.py\n)"],
        # Passes before sd:776 too: `popd` returns to where `pushd` left from.
        ["bash", "-c", "pushd sub; popd; python -I ../bin/sd_install.py"],
        # A subshell's `pushd` leaves the outer stack alone.
        ["bash", "-c", "pushd sub; (pushd other); popd; python -I ../bin/sd_install.py"],
        # A block, and an and-or list, that a `|` or a `&` put in a subshell:
        # the `cd` in it is that subshell's, not the launch's.
        ["bash", "-c", "{ cd sub; } | cat; python -I ../bin/sd_install.py"],
        ["bash", "-c", "{ cd sub; } & wait; python -I ../bin/sd_install.py"],
        ["bash", "-c", "if cd sub; then :; fi | cat; python -I ../bin/sd_install.py"],
        ["bash", "-c", "while cd sub; do break; done & wait; python -I ../bin/sd_install.py"],
        ["bash", "-c", "case x in x) cd sub;; esac | cat; python -I ../bin/sd_install.py"],
        ["bash", "-c", "cd sub && true & wait; python -I ../bin/sd_install.py"],
        # A function body runs where its caller is, and only once it is called.
        ["bash", "-c", "f() { cd sub; }; python -I ../bin/sd_install.py"],
        # Called, the body's `cd` is the caller's: the launch is under `sub`.
        ["bash", "-c", "f() { cd sub; }; f; python -I bin/sd_install.py"],
        ["bash", "-c", "{ f() { cd sub; }; }; f; python -I bin/sd_install.py"],
        ["bash", "-c", "function f() { cd sub; }; f; python -I bin/sd_install.py"],
        # A call in a pipeline runs in that pipeline's subshell.
        ["bash", "-c", "f() { cd sub; }; f | cat; python -I ../bin/sd_install.py"],
        # A name in a body being defined is not a call: nothing there has run.
        ["bash", "-c", "f() { cd sub; }; g() { f; }; f; python -I bin/sd_install.py"],
        # The call in the subshell moved nothing here, so this one is the first.
        ["bash", "-c", "f() { cd sub; }; (f); f; python -I bin/sd_install.py"],
        # A quoted word is a program or an argument, never the shell's own.
        ["bash", "-c", '"if" python -I bin/sd_install.py'],
        ["bash", "-c", "echo ';' python -I bin/sd_install.py"],
        ["bash", "-c", "find . -maxdepth 0 -exec true {} \\; python -I bin/sd_install.py"],
        ["bash", "-c", "python -I 'bin/sd_inst*.py'"],
        # The last command of a pipeline runs in a subshell of its own.
        ["bash", "-c", "true | cd sub; python -I ../bin/sd_install.py"],
        # `pushd -n` adds to the stack without moving; a bare `pushd` swaps,
        # and a bare `pushd -n` does neither.
        ["bash", "-c", "pushd -n sub; python -I ../bin/sd_install.py"],
        ["bash", "-c", "pushd sub; pushd; python -I ../bin/sd_install.py"],
        ["bash", "-c", "pushd sub; pushd -n; python -I bin/sd_install.py"],
    )

    #: Command lines that run a gate-measured file with site skipped.
    REFUSED = (
        ["python3.13", "-E", "bin/sd_install.py"],
        ["/some/where/python", "-S", "bin/sd_install.py"],
        ["env", "python", "-I", "bin/sd_install.py"],
        ["env", "-i", "FOO=1", "python3", "-S", "bin/sd_install.py"],
        ["env", "-S", "python3 -I", "bin/sd_install.py"],
        ["bash", "-c", "cd sub && python -I ../bin/sd_install.py"],
        ["bash", "-ec", "true; FOO=1 python -E bin/sd_install.py", "name", "arg"],
        ["bash", "-c", "true || python -I bin/sd_install.py"],
        ["sh", "-c", "echo hi | python -S bin/sd_install.py"],
        ["sh", "-c", "true\npython -I bin/sd_install.py"],
        ["bash", "-c", "sh -c 'python -I bin/sd_install.py'"],
        ["env", "-C", "sub", "python", "-I", "../bin/sd_install.py"],
        ["env", "--chdir=sub", "python", "-I", "../bin/sd_install.py"],
        ["bash", "-c", ">log python -I bin/sd_install.py"],
        ["bash", "-c", "2> /dev/null FOO=1 python -E bin/sd_install.py"],
        ["bash", "-c", "2>&1 python -S bin/sd_install.py"],
        ["sh", "-c", "! python -I bin/sd_install.py"],
        ["sh", "-c", "if python -I bin/sd_install.py; then true; fi"],
        ["sh", "-c", "if true; then python -E bin/sd_install.py; fi"],
        ["sh", "-c", "if false; then true; elif python -S bin/sd_install.py; then true; fi"],
        ["sh", "-c", "if false; then true; else python -I bin/sd_install.py; fi"],
        ["sh", "-c", "while python -I bin/sd_install.py; do break; done"],
        ["sh", "-c", "until python -I bin/sd_install.py; do break; done"],
        ["sh", "-c", "for f in x; do python -I bin/sd_install.py; done"],
        ["sh", "-c", "{ python -S bin/sd_install.py; }"],
        ["bash", "-c", "time -p python -E bin/sd_install.py"],
        ["bash", "-c", "if cd sub; then python -I ../bin/sd_install.py; fi"],
        ["bash", "-c", "cd sub 2>/dev/null && python -I ../bin/sd_install.py"],
        ["bash", "-c", "cd sub >/dev/null && python -I ../bin/sd_install.py"],
        ["bash", "-c", "cd sub &>/dev/null && python -I ../bin/sd_install.py"],
        ["bash", "-c", "cd sub > /dev/null 2>&1; python -I ../bin/sd_install.py"],
        ["bash", "-c", "x=`python -I bin/sd_install.py`"],
        ["bash", "-c", "# it's here\npython -I bin/sd_install.py"],
        ["env", "-Csub", "python", "-I", "../bin/sd_install.py"],
        ["env", "-iC", "sub", "python", "-I", "../bin/sd_install.py"],
        ["env", "-Spython3 -I", "bin/sd_install.py"],
        ["env", "--split-string=python3 -I", "bin/sd_install.py"],
        ["python", "--check-hash-based-pycs", "never", "-I", "bin/sd_install.py"],
        ["bash", "-c", "pushd sub && python -I ../bin/sd_install.py"],
        # A `#` mid-word is not a comment, and a backslash escapes the quote
        # after it: neither cuts the launch on the next command.
        ["bash", "-c", "echo a#b; python -I bin/sd_install.py"],
        ["bash", "-c", "echo \\'; python -I bin/sd_install.py # it's"],
        # A backslash escape ends a word's first character too: what follows
        # the `#` is the word's, not a comment's.
        ["bash", "-c", "echo \\b#c; python -I bin/sd_install.py"],
        # The `pushd` stack: a bare `pushd` swaps the top two, `+N` rotates,
        # `popd +N` drops an entry without moving, `pushd -n` adds without one.
        ["bash", "-c", "pushd sub; pushd; python -I bin/sd_install.py"],
        ["bash", "-c", "pushd sub; pushd +1; python -I bin/sd_install.py"],
        ["bash", "-c", "pushd sub; pushd ../other; popd +1; popd; python -I bin/sd_install.py"],
        ["bash", "-c", "pushd -n sub; popd; python -I ../bin/sd_install.py"],
        ["bash", "-c", "pushd sub; pushd -n; python -I ../bin/sd_install.py"],
        # `popd +N` and `popd -n` drop an entry and stay where they are, two
        # levels down; the `popd` after one returns to the root, not to `sub`,
        # because the entry it would have returned to is the one that went.
        ["bash", "-c", "pushd sub; pushd deep; popd +1; python -I ../../bin/sd_install.py"],
        ["bash", "-c", "pushd sub; pushd deep; popd -n; python -I ../../bin/sd_install.py"],
        ["bash", "-c", "pushd sub; pushd deep; popd +1; popd; python -I bin/sd_install.py"],
        ["bash", "-c", "pushd sub; pushd deep; popd -n; popd; python -I bin/sd_install.py"],
        # `cd -` goes back to where the `cd` before it left.
        ["bash", "-c", "cd sub; cd -; python -I bin/sd_install.py"],
        # A `\\` newline joins the two lines before any word is read.
        ["bash", "-c", "cd sub && \\\npython -I ../bin/sd_install.py"],
        # A quote closes what it opened: the `)` and the `;` in one are text.
        ["bash", "-c", "(cd sub; echo ')'; python -I ../bin/sd_install.py)"],
        # A `)` that closes a `case` pattern leaves the subshell open.
        ["bash", "-c", "(cd sub; case x in x) python -I ../bin/sd_install.py;; esac)"],
        # A process substitution runs a command line of its own.
        ["bash", "-c", "cat <(python -I bin/sd_install.py)"],
        ["bash", "-c", "eval 'python -I bin/sd_install.py'"],
        ["bash", "-c", "function f { python -I bin/sd_install.py; }; f"],
        # A called function's `cd` moves the launch that follows it, and a
        # second call to it does not move again: the relative `cd` would fail.
        ["bash", "-c", "f() { cd sub; }; f; python -I ../bin/sd_install.py"],
        ["bash", "-c", "f() { cd sub; }; f; f; python -I ../bin/sd_install.py"],
        # A quoted name calls the function, and a body defined inside another
        # body is defined when that one is called.
        ["bash", "-c", 'f() { cd sub; }; "f"; python -I ../bin/sd_install.py'],
        ["bash", "-c", "g() { f() { cd sub; }; }; g; f; python -I ../bin/sd_install.py"],
        # A name in a body being defined is not a call, so this `f` is the
        # first one, and a call in a pipeline leaves the next call the first.
        ["bash", "-c", "f() { cd sub; }; g() { f; }; f; python -I ../bin/sd_install.py"],
        ["bash", "-c", "f() { cd sub; }; f | cat; f; python -I ../bin/sd_install.py"],
        # A definition in a subshell is the subshell's: `f` here is a command
        # that does not exist, and the launch runs where it stands.
        ["bash", "-c", "( f() { cd sub; } ); f; python -I bin/sd_install.py"],
        # A name a `()` follows is a new definition, not a call of the old one;
        # a body that calls a function twice moves once, as a line does.
        ["bash", "-c", "f() { cd sub; }; f() { cd other; }; f; python -I ../bin/sd_install.py"],
        ["bash", "-c", "f() { cd sub; }; g() { f; f; }; g; python -I ../bin/sd_install.py"],
        # A call reached through another function in a pipeline moves only the
        # pipeline, so the launch runs where the line stands.
        ["bash", "-c", "f() { cd sub; }; g() { f; }; g | cat; python -I bin/sd_install.py"],
        ["bash", "-c", "time -- python -I bin/sd_install.py"],
        ["env", "-a", "name", "python", "-I", "bin/sd_install.py"],
        # A pattern is expanded where the command runs, as the shell expands it.
        ["bash", "-c", "python -I bin/sd_inst*.py"],
        # A quote left open ends its line; the lines before it have run.
        ["bash", "-c", "python -I bin/sd_install.py\necho 'unclosed"],
        # A block's own `cd`, with nothing putting the block in a subshell.
        ["bash", "-c", "{ cd sub; python -I ../bin/sd_install.py; }"],
    )

    def test_an_interpreter_word_off_command_position_is_not_refused(self) -> None:
        (self.root / "sub").mkdir()
        (self.root / "other").mkdir()
        (self.root / "sub/deep").mkdir()
        for argv in self.NOT_REFUSED:
            with self.subTest(argv=argv):
                result = self.child("-c", self.launch(argv), check=False)
                self.assertNotIn("would run with -I, -E or -S", result.stderr)
                self.assertEqual((result.returncode, result.stdout.strip()), (0, "launched"), result.stderr)

    def test_an_interpreter_at_command_position_is_refused(self) -> None:
        (self.root / "sub").mkdir()
        (self.root / "other").mkdir()
        (self.root / "sub/deep").mkdir()
        for argv in self.REFUSED:
            with self.subTest(argv=argv):
                self.assert_refused(self.launch(argv))

    def test_a_start_on_the_main_thread_beside_a_live_worker_keeps_its_tracer(self) -> None:
        """PyTracer warns at exit when its thread's trace function was replaced."""
        script = ("import sys, threading; released = threading.Event(); "
                  "worker = threading.Thread(target=released.wait); worker.start(); "
                  "sys.path.insert(0, 'bin'); import sd_install; sd_install.pick(False); "
                  "released.set(); worker.join()")
        arcs = {}
        for start, variable in (("lazy", "SD_COVERAGE_PROCESS_START"), ("eager", "COVERAGE_PROCESS_START")):
            with self.subTest(start=start):
                for stale in self.data_files():
                    stale.unlink()
                result = self.child("-c", script, extra_env={
                    "COVERAGE_CORE": "pytrace", variable: str(self.root / ".coveragerc")})
                self.assertNotIn("Trace function changed", result.stderr)
                self.assert_installer_measured()
                data = coverage.CoverageData(basename=str(self.data_files()[0]))
                data.read()
                arcs[start] = {os.path.realpath(name): sorted(data.arcs(name) or [])
                               for name in data.measured_files()}[os.path.realpath(self.installer)]
        self.assertEqual(sorted(arcs), ["eager", "lazy"])
        # `pick(False)` ran on the main thread after the start: its branch is in.
        self.assertIn((2, 4), arcs["lazy"])
        self.assertEqual(arcs["lazy"], arcs["eager"])

    @unittest.skipUnless(hasattr(sys, "_settraceallthreads"), "no sys._settraceallthreads before Python 3.12")
    def test_a_start_on_a_thread_without_a_tracer_keeps_the_installer(self) -> None:
        """The calling thread gets back only a tracer it had: with none, the installer stays."""
        script = (
            "import importlib.util, sys, threading, types\n"
            f"spec = importlib.util.spec_from_file_location('probe', {str(SITECUSTOMIZE / 'sitecustomize.py')!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "def install(frame, event, arg):\n"
            "    return None\n"
            "collector = types.SimpleNamespace(core=types.SimpleNamespace(systrace=True), _installation_trace=install)\n"
            "current = types.SimpleNamespace(_collector=collector)\n"
            "fake = types.SimpleNamespace(Coverage=types.SimpleNamespace(current=lambda: current))\n"
            "released = threading.Event()\n"
            "worker = threading.Thread(target=released.wait)\n"
            "worker.start()\n"
            "sys.settrace(None)\n"
            "module._trace_existing_threads(fake)\n"
            "print(sys.gettrace() is install)\n"
            "sys.settrace(None)\n"
            "released.set()\n"
            "worker.join()\n"
        )
        # No coverage variable and no PYTHONPATH: loading the module starts nothing.
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("COVERAGE_", "SD_COVERAGE_")) and key != "PYTHONPATH"}
        result = subprocess.run([sys.executable, "-c", script], cwd=self.root, env=environment,
                                text=True, capture_output=True, timeout=60)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "True"), result.stderr)


if __name__ == "__main__":
    unittest.main()
