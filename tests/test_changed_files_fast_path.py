"""`make check` accepts a changed-files fast path; the full suite stays the default.

sd:10 criterion 16. `make check CHANGED="<paths>"` runs the test modules
those paths need plus an always-run set, and skips `coverage combine` and the
installer gate, which only the whole suite can meet. Without `CHANGED` on the
command line, `make check` is what it was. Every doubt runs the whole suite:
a path nobody names, a path most modules name, a path the full suite answers
for, a selector that fails, and a CI runner.

Three layers are tested, each against a throwaway tree rather than this
checkout, so a new test module here cannot move an expected set:

* `.github/scripts/select-tests.py`, the selection itself;
* `.github/scripts/run-tests.sh`, copied into the tree, which runs only what
  the selection names and says so on the log's first line;
* the `Makefile`, copied in, which passes `CHANGED` through only from the
  command line and skips the coverage steps only for a narrowed run.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / ".github/scripts"
SELECTOR = SCRIPTS / "select-tests.py"


def load_selector() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("select_tests", SELECTOR)
    if spec is None or spec.loader is None or not SELECTOR.is_file():
        raise AssertionError(f"{SELECTOR.relative_to(REPO_ROOT)} does not exist")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALWAYS_RUN_NAMES = (
    "test_code_health", "test_doc_citations", "test_loc_caps", "test_no_shipped_shell",
    "test_suite_shape", "test_verb_inventory", "test_workflow_policy",
)

# Each optional module names what it tests the way real ones do: a path, a
# script name, a module stem. `sd_common` is named by four of the six, so it
# is shared. `sd-epsilon` imports `sd_beta`. `test_zeta` names the tooling
# paths, so a rule that sends them to the full suite is what does, and not
# the absence of any test naming them.
OPTIONAL_TESTS = {
    "test_alpha": 'SCRIPT = "bin/sd-alpha"\nSHARED = "sd_common"\n',
    "test_beta": 'MODULE = "sd_beta"  # sd_common\n',
    "test_gamma": 'GUIDE = "docs/guide.md"  # sd_common\n',
    "test_delta": 'NAME = "sd-alphabet"  # a longer name; sd_common\n',
    "test_epsilon": 'SCRIPT = "sd-epsilon"\n',
    "test_eta": 'SERVER = "dashboard/server.py"\n',
    "test_zeta": 'TOOLING = ("Makefile", ".coveragerc", "sd_install", ".github/workflows/tests.yml", "sitecustomize")\n',
}

# Each fixture test leaves its module's name in `RAN_DIR`, which is how a run
# is read back: the published log says how many tests ran, not which.
FIXTURE_TEST = """import os
import pathlib
import unittest


class Only(unittest.TestCase):
    def test_it(self):
        pathlib.Path(os.environ["RAN_DIR"], __name__.rpartition(".")[2]).touch()
"""

COVERAGERC = "[run]\ninclude =\n    bin/nothing.py\nparallel = True\n"


def build_tree(root: pathlib.Path) -> None:
    (root / "tests").mkdir(parents=True)
    for name in ALWAYS_RUN_NAMES:
        (root / "tests" / f"{name}.py").write_text(FIXTURE_TEST)
    for name, text in OPTIONAL_TESTS.items():
        (root / "tests" / f"{name}.py").write_text(text + FIXTURE_TEST)
    (root / "bin").mkdir()
    (root / "bin/sd-alpha").write_text("print('alpha')\n")
    (root / "bin/sd_beta.py").write_text("VALUE = 1\n")
    (root / "bin/sd-epsilon").write_text("import sd_beta\n")
    (root / "bin/sd_common.py").write_text("VALUE = 2\n")
    (root / "dashboard").mkdir()
    (root / "dashboard/collect.py").write_text("VALUE = 3\n")
    (root / "dashboard/server.py").write_text("from . import collect\n")
    (root / "docs").mkdir()
    (root / "docs/guide.md").write_text("# Guide\n")
    (root / "docs/nowhere.md").write_text("# Named by no test\n")
    (root / "docs/it's.md").write_text("# A name with a quote in it\n")
    (root / ".coveragerc").write_text(COVERAGERC)


def clean_environment(**extra: str) -> dict[str, str]:
    """This process's environment without anything that would steer the run under test."""

    dropped = {"PYTHONPATH", "CI", "GITHUB_ACTIONS", "TEST_CHANGED_FILES", "CHANGED",
               "MAKEFLAGS", "MFLAGS", "MAKELEVEL"}
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("COVERAGE_", "SD_COVERAGE_")) and key not in dropped}
    environment.update({"TEST_WORKERS": "4", "PYTHONDONTWRITEBYTECODE": "1", **extra})
    return environment


def ran_modules(ran_dir: pathlib.Path) -> set[str]:
    """The fixture modules whose single test ran."""

    return {path.name for path in ran_dir.iterdir()} if ran_dir.is_dir() else set()


class TreeCase(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = pathlib.Path(scratch.name).resolve()
        build_tree(self.root)
        self.ran_dir = self.root / "ran"
        self.everything = set(ALWAYS_RUN_NAMES) | set(OPTIONAL_TESTS)

    def install_scripts(self) -> pathlib.Path:
        scripts = self.root / ".github/scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(SCRIPTS / "run-tests.sh", scripts / "run-tests.sh")
        if SELECTOR.is_file():
            shutil.copy2(SELECTOR, scripts / "select-tests.py")
        return scripts

    def run_in_tree(self, command: list[str], **extra: str) -> subprocess.CompletedProcess:
        shutil.rmtree(self.ran_dir, ignore_errors=True)
        self.ran_dir.mkdir()
        result = subprocess.run(command, cwd=self.root, text=True, capture_output=True, timeout=600,
                                env=clean_environment(RAN_DIR=str(self.ran_dir), **extra))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result


class TheSelection(TreeCase):
    def setUp(self) -> None:
        super().setUp()
        self.selector = load_selector()
        self.always = {f"tests.{name}" for name in ALWAYS_RUN_NAMES}

    def select(self, *paths: str) -> list[str] | None:
        return self.selector.select(self.root, list(paths))[0]

    def test_the_fixture_always_run_set_is_the_selectors(self) -> None:
        self.assertEqual(set(self.selector.ALWAYS_RUN), self.always)

    def test_a_change_in_one_file_selects_its_tests(self) -> None:
        self.assertEqual(self.select("bin/sd-alpha"), sorted(self.always | {"tests.test_alpha"}))

    def test_a_changed_test_module_selects_itself(self) -> None:
        self.assertEqual(self.select("tests/test_zeta.py"), sorted(self.always | {"tests.test_zeta"}))

    def test_a_module_importing_the_change_brings_its_tests(self) -> None:
        self.assertEqual(self.select("bin/sd_beta.py"),
                         sorted(self.always | {"tests.test_beta", "tests.test_epsilon"}))

    def test_a_relative_import_is_an_import(self) -> None:
        """`dashboard/` imports its own modules as `from . import collect`."""

        self.assertEqual(self.select("dashboard/collect.py"), sorted(self.always | {"tests.test_eta"}))

    def test_an_unmapped_file_selects_the_full_run(self) -> None:
        self.assertIsNone(self.select("docs/nowhere.md"))
        self.assertIsNone(self.select("bin/sd-alpha", "docs/nowhere.md"))

    def test_a_shared_file_selects_the_full_run(self) -> None:
        self.assertIsNone(self.select("bin/sd_common.py"))

    def test_the_paths_the_full_suite_answers_for_select_it(self) -> None:
        (self.root / "tests/coverage_sitecustomize").mkdir()
        for path in ("Makefile", ".github/workflows/tests.yml", ".coveragerc", "bin/sd_install.py",
                     "tests/coverage_sitecustomize/sitecustomize.py", "bin", "/somewhere/else.py"):
            with self.subTest(path=path):
                self.assertIsNone(self.select(path))
                self.assertIsNone(self.select("bin/sd-alpha", path))

    def test_an_empty_change_selects_the_full_run(self) -> None:
        """No path is what a failed or empty `git diff` produces; it must not narrow."""

        self.assertIsNone(self.select())

    def test_a_missing_always_run_module_selects_the_full_run(self) -> None:
        (self.root / "tests/test_loc_caps.py").unlink()
        self.assertIsNone(self.select("bin/sd-alpha"))


class TheSelectorHere(unittest.TestCase):
    def test_every_always_run_module_exists_in_this_checkout(self) -> None:
        selector = load_selector()
        missing = [name for name in selector.ALWAYS_RUN
                   if not (REPO_ROOT / "tests" / f"{name.split('.')[1]}.py").is_file()]
        self.assertEqual(missing, [], "the always-run set names modules that are gone")
        self.assertEqual(set(selector.ALWAYS_RUN), {f"tests.{name}" for name in ALWAYS_RUN_NAMES})

    def test_the_command_line_prints_full_or_module_names(self) -> None:
        load_selector()
        result = subprocess.run([sys.executable, str(SELECTOR), "--", "Makefile"], cwd=REPO_ROOT,
                                env=clean_environment(), text=True, capture_output=True, timeout=120)
        self.assertEqual((result.returncode, result.stdout), (0, "full\n"), result.stderr)
        own = pathlib.Path(__file__).relative_to(REPO_ROOT).as_posix()
        result = subprocess.run([sys.executable, str(SELECTOR), own], cwd=REPO_ROOT,
                                env=clean_environment(), text=True, capture_output=True, timeout=120)
        self.assertIn("tests.test_changed_files_fast_path", result.stdout.split(), result.stderr)


class TheRunner(TreeCase):
    """`run-tests.sh` runs what the selection names, and everything on any doubt."""

    def setUp(self) -> None:
        super().setUp()
        self.install_scripts()

    def run_harness(self, **extra: str) -> tuple[set[str], str, str]:
        result = self.run_in_tree(["bash", str(self.root / ".github/scripts/run-tests.sh")],
                                  PYTHON_BIN=sys.executable, **extra)
        log = (self.root / "unittest-output.log").read_text()
        return ran_modules(self.ran_dir), (log.splitlines() or [""])[0], result.stderr

    def test_without_the_argument_every_module_runs(self) -> None:
        ran, first, _ = self.run_harness()
        self.assertEqual(ran, self.everything)
        self.assertNotIn("test selection", first)

    def test_a_change_runs_its_tests_and_the_always_run_set(self) -> None:
        ran, first, _ = self.run_harness(TEST_CHANGED_FILES="bin/sd-alpha")
        self.assertEqual(ran, set(ALWAYS_RUN_NAMES) | {"test_alpha"})
        self.assertTrue(first.startswith("test selection: changed files"), first)

    def test_an_empty_or_blank_change_runs_everything(self) -> None:
        """A set-but-empty variable is what an empty diff gives; it runs the full suite."""

        for value in ("", "   ", "\n \n"):
            with self.subTest(value=repr(value)):
                ran, first, _ = self.run_harness(TEST_CHANGED_FILES=value)
                self.assertEqual(ran, self.everything)
                self.assertNotIn("test selection", first)

    def test_an_unmapped_change_runs_everything(self) -> None:
        ran, first, _ = self.run_harness(TEST_CHANGED_FILES="bin/sd-alpha\ndocs/nowhere.md")
        self.assertEqual(ran, self.everything)
        self.assertNotIn("test selection", first)

    def test_ci_never_takes_the_fast_path(self) -> None:
        """Any value, not only `true`: a runner is free to export `CI=1`."""

        for variable, value in (("CI", "true"), ("CI", "1"), ("GITHUB_ACTIONS", "true")):
            with self.subTest(variable=variable, value=value):
                ran, first, stderr = self.run_harness(TEST_CHANGED_FILES="bin/sd-alpha", **{variable: value})
                self.assertEqual(ran, self.everything)
                self.assertNotIn("test selection", first)
                self.assertIn("ignored under CI", stderr)

    def test_a_failing_selector_runs_everything(self) -> None:
        (self.root / ".github/scripts/select-tests.py").write_text("import sys\nsys.exit(2)\n")
        ran, first, _ = self.run_harness(TEST_CHANGED_FILES="bin/sd-alpha")
        self.assertEqual(ran, self.everything)
        self.assertNotIn("test selection", first)


class MakefileTree(TreeCase):
    """The repository's own `Makefile`, over a throwaway tree and a venv that only reports."""

    def setUp(self) -> None:
        super().setUp()
        if shutil.which("make") is None:
            self.fail("make is not on PATH")
        scripts = self.install_scripts()
        shutil.copy2(REPO_ROOT / "Makefile", self.root / "Makefile")
        (scripts / "check-installer-coverage.sh").write_text('printf "%s\\n" "installer gate ran"\n')
        # A venv whose python is this one, except that `-m coverage combine`
        # only says it ran: the fixture measures nothing there is to combine.
        venv_bin = self.root / "venv/bin"
        venv_bin.mkdir(parents=True)
        python = venv_bin / "python"
        python.write_text(
            "#!/bin/sh\n"
            'if [ "$1 $2 $3" = "-m coverage combine" ]; then printf "%s\\n" "coverage combine ran"; exit 0; fi\n'
            f'exec "{sys.executable}" "$@"\n')
        python.chmod(python.stat().st_mode | stat.S_IXUSR)

    def make(self, *arguments: str, **extra: str) -> tuple[set[str], str]:
        result = self.run_in_tree(["make", "--no-print-directory", "test", "VENV=venv", *arguments], **extra)
        return ran_modules(self.ran_dir), result.stdout

    def assert_coverage_steps(self, stdout: str, ran: bool) -> None:
        check = self.assertIn if ran else self.assertNotIn
        check("coverage combine ran", stdout)
        check("installer gate ran", stdout)


class TheMakefile(MakefileTree):
    """`CHANGED` counts only from the command line; the coverage steps skip only for a narrowed run."""

    def test_without_changed_the_full_suite_and_its_gates_run(self) -> None:
        ran, stdout = self.make()
        self.assertEqual(ran, self.everything)
        self.assert_coverage_steps(stdout, ran=True)

    def test_changed_on_the_command_line_takes_the_fast_path(self) -> None:
        ran, stdout = self.make("CHANGED=bin/sd-alpha")
        self.assertEqual(ran, set(ALWAYS_RUN_NAMES) | {"test_alpha"})
        self.assert_coverage_steps(stdout, ran=False)
        self.assertIn("Run make check without CHANGED before a push", stdout)

    def test_changed_from_the_environment_is_ignored(self) -> None:
        ran, stdout = self.make(CHANGED="bin/sd-alpha")
        self.assertEqual(ran, self.everything)
        self.assert_coverage_steps(stdout, ran=True)

    def test_an_inherited_runner_variable_is_removed(self) -> None:
        """`TEST_CHANGED_FILES` left in the environment does not narrow a plain `make test`."""

        ran, stdout = self.make(TEST_CHANGED_FILES="bin/sd-alpha")
        self.assertEqual(ran, self.everything)
        self.assert_coverage_steps(stdout, ran=True)

    def test_a_quote_in_a_path_does_not_reach_the_shell(self) -> None:
        ran, stdout = self.make("CHANGED=bin/sd-alpha docs/it's.md")
        self.assertEqual(ran, self.everything, "an unmapped path runs everything")
        self.assert_coverage_steps(stdout, ran=True)

    def test_a_change_widened_to_the_full_suite_keeps_the_gates(self) -> None:
        ran, stdout = self.make("CHANGED=Makefile")
        self.assertEqual(ran, self.everything)
        self.assert_coverage_steps(stdout, ran=True)

    def test_an_empty_changed_runs_everything_with_its_gates(self) -> None:
        """`CHANGED=` is what the documented `$(git diff ...)` recipe gives on an empty diff."""

        ran, stdout = self.make("CHANGED=")
        self.assertEqual(ran, self.everything)
        self.assert_coverage_steps(stdout, ran=True)

    def test_a_blank_changed_runs_everything_with_its_gates(self) -> None:
        """The same for a `CHANGED` holding only whitespace."""

        ran, stdout = self.make("CHANGED=   ")
        self.assertEqual(ran, self.everything)
        self.assert_coverage_steps(stdout, ran=True)


class TheGateMark(MakefileTree):
    """The mark that skips the coverage steps counts on the first line, at its start.

    `test selection: changed files` is written by `run-tests.sh` and by this
    module. The realistic way a *full* run's log carries it is a failing
    assertion in this module printing its expected value -- exactly when the
    coverage steps must not be skipped. `head -n 1` and the `^` anchor are
    what hold that, so each is pinned here with a log this test writes.
    """

    def setUp(self) -> None:
        super().setUp()
        (self.root / ".github/scripts/run-tests.sh").write_text(
            'printf "%s" "$LOG_FIXTURE" > unittest-output.log\n')

    def with_log(self, log: str) -> str:
        return self.make(LOG_FIXTURE=log)[1]

    def test_the_mark_on_the_first_line_skips_the_coverage_steps(self) -> None:
        stdout = self.with_log("test selection: changed files, 7 of 85 modules\n...\nOK\n")
        self.assert_coverage_steps(stdout, ran=False)

    def test_the_mark_below_the_first_line_keeps_the_coverage_steps(self) -> None:
        """A failed `assertTrue(first.startswith(...), first)` prints the mark at column 1."""

        stdout = self.with_log("...\ntest selection: changed files, 7 of 85 modules\nOK\n")
        self.assert_coverage_steps(stdout, ran=True)

    def test_the_mark_inside_the_first_line_keeps_the_coverage_steps(self) -> None:
        stdout = self.with_log("AssertionError: test selection: changed files, 7 of 85 modules\nOK\n")
        self.assert_coverage_steps(stdout, ran=True)


if __name__ == "__main__":
    unittest.main()
