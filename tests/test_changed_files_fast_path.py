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
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
import unittest.mock

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

    def run_in_tree(self, command: list[str], *, expect: int = 0, **extra: str) -> subprocess.CompletedProcess:
        """Run `command` in the throwaway tree and assert its exit status.

        `expect` is asserted rather than defaulted away because the status is
        the subject of part of this module: a narrowed `make test` exits 2
        (sd:840), and a harness that only ever accepted 0 was how that went
        unnoticed. Every call names the status it expects.
        """

        shutil.rmtree(self.ran_dir, ignore_errors=True)
        self.ran_dir.mkdir()
        result = subprocess.run(command, cwd=self.root, text=True, capture_output=True, timeout=600,
                                env=clean_environment(RAN_DIR=str(self.ran_dir), **extra))
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
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

    def test_a_selection_naming_a_module_this_tree_lacks_matches_nothing(self) -> None:
        """A name matches a whole line of the selection, never a substring.

        `tests.test_alphabet` is not a module here. Matched as a substring it
        would pull in `tests.test_alpha`, which the selection never named, and
        the run would report a count the selector did not give. The same
        relaxation is what turns a selection nothing here matches -- which
        must fall back to the full suite -- into a narrowed run under skipped
        coverage gates.
        """

        names = [f"tests.{name}" for name in (*ALWAYS_RUN_NAMES, "test_alphabet")]
        (self.root / ".github/scripts/select-tests.py").write_text(
            f"print({chr(10).join(names)!r})\n")
        ran, first, _ = self.run_harness(TEST_CHANGED_FILES="bin/sd-alpha")
        self.assertEqual(ran, set(ALWAYS_RUN_NAMES))
        self.assertTrue(first.startswith("test selection: changed files"), first)

    def test_a_selection_no_module_here_matches_runs_everything(self) -> None:
        """The whole answer is a name this tree lacks, so nothing is selected."""

        (self.root / ".github/scripts/select-tests.py").write_text(
            "print('tests.test_alphabet')\n")
        ran, first, _ = self.run_harness(TEST_CHANGED_FILES="bin/sd-alpha")
        self.assertEqual(ran, self.everything)
        self.assertNotIn("test selection", first)

    def test_a_long_selection_is_read_to_its_end_for_every_module(self) -> None:
        """A selection longer than a pipe buffer still selects each module it names.

        Matched through `printf | grep -q` under `set -o pipefail`, a name near
        the top of a long selection is found, `grep` exits, `printf` takes
        SIGPIPE on the rest, and the pipeline's 141 reads as "not selected":
        the module the change needs is dropped from a narrowed run. A real
        selection is a few kilobytes and cannot reach it today; the padding
        here is a megabyte of names this tree does not hold.
        """

        always = [f"tests.{name}" for name in ALWAYS_RUN_NAMES]
        padding = [f"tests.not_here_{index:06d}" for index in range(40000)]
        names = ["tests.test_alpha", *padding, *always]
        (self.root / ".github/scripts/select-tests.py").write_text(
            f"print({chr(10).join(names)!r})\n")
        ran, first, _ = self.run_harness(TEST_CHANGED_FILES="bin/sd-alpha")
        self.assertEqual(ran, set(ALWAYS_RUN_NAMES) | {"test_alpha"})
        self.assertTrue(first.startswith("test selection: changed files, 8 of"), first)

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

    def run_make(self, *arguments: str, expect: int = 0, **extra: str) -> subprocess.CompletedProcess:
        return self.run_in_tree(["make", "--no-print-directory", "test", "VENV=venv", *arguments],
                                expect=expect, **extra)

    def make(self, *arguments: str, expect: int = 0, **extra: str) -> tuple[set[str], str]:
        result = self.run_make(*arguments, expect=expect, **extra)
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
        ran, stdout = self.make("CHANGED=bin/sd-alpha", expect=2)
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


class TheNarrowedExitStatus(MakefileTree):
    """sd:840 -- a narrowed run exits 2, and only a full run with both gates exits 0.

    The notice said the coverage gates had not run, and the target exited 0
    all the same: the status a caller reads -- a script, a hook, the left half
    of an `&&` -- said the same thing for a partial run as for a green one,
    and only the transcript held the difference. It says 2 now.

    `make` reports 2 for any failed recipe whatever the recipe itself exited,
    so the status alone cannot tell this 2 from a 1; the recipe's own number
    is on make's `*** [test] Error 2` line, and that line is asserted here so
    the constant in the `Makefile` is pinned rather than swallowed. What the
    status carries, which is what the item asked for, is 0 for the full suite
    with both gates and non-zero for anything less.
    """

    def test_a_narrowed_run_exits_two(self) -> None:
        result = self.run_make("CHANGED=bin/sd-alpha", expect=2)
        self.assertEqual(ran_modules(self.ran_dir), set(ALWAYS_RUN_NAMES) | {"test_alpha"})
        self.assert_coverage_steps(result.stdout, ran=False)
        self.assertIn("Run make check without CHANGED before a push", result.stdout,
                      "the notice stays; the exit status is what changed")
        self.assertRegex(result.stderr, r"\*\*\* \[[^]]*\btest\] Error 2")

    def test_the_full_suite_with_both_gates_is_what_exits_zero(self) -> None:
        """The other half of the contract: 0 still means the gates ran."""

        result = self.run_make(expect=0)
        self.assertEqual(ran_modules(self.ran_dir), self.everything)
        self.assert_coverage_steps(result.stdout, ran=True)


class TheCheckOrder(unittest.TestCase):
    """`check` runs `test` last, so a narrowed run still reaches the other three lanes.

    sd:840. `test` exits 2 when the selector narrowed the run, and `make`
    stops at the first prerequisite that fails -- so the last prerequisite is
    the one whose status `check` carries, and anything listed after `test`
    would not run at all on the changed-files fast path. With `test` last,
    `make check CHANGED="<paths>"` still runs `lint`, `audit` and `docs-lint`
    whole, which is what CONTRIBUTING.md promises of the fast path, and still
    comes out non-zero. Move `test` back to the front and both halves break
    without a sound: three lanes stop running on the fast path, that promise
    becomes false, and nothing fails to say so. Hence a test for the order of
    four words.

    Only the position of `test` is pinned. The three cheap lanes may be
    reordered among themselves; nothing depends on which of them goes first.
    """

    def prerequisites(self) -> list[str]:
        rules = re.findall(r"^check:(.*)$", (REPO_ROOT / "Makefile").read_text(encoding="utf-8"),
                           flags=re.MULTILINE)
        self.assertEqual(len(rules), 1, "the Makefile has exactly one `check` rule")
        return rules[0].split()

    def test_test_is_the_last_gate_check_runs(self) -> None:
        self.assertEqual(self.prerequisites()[-1], "test")

    def test_check_still_runs_all_four_gates(self) -> None:
        self.assertEqual(set(self.prerequisites()), {"lint", "audit", "docs-lint", "test"})


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

    def with_log(self, log: str, expect: int = 0) -> str:
        return self.make(LOG_FIXTURE=log, expect=expect)[1]

    def test_the_mark_on_the_first_line_skips_the_coverage_steps(self) -> None:
        stdout = self.with_log("test selection: changed files, 7 of 85 modules\n...\nOK\n", expect=2)
        self.assert_coverage_steps(stdout, ran=False)

    def test_the_mark_below_the_first_line_keeps_the_coverage_steps(self) -> None:
        """A failed `assertTrue(first.startswith(...), first)` prints the mark at column 1."""

        stdout = self.with_log("...\ntest selection: changed files, 7 of 85 modules\nOK\n")
        self.assert_coverage_steps(stdout, ran=True)

    def test_the_mark_inside_the_first_line_keeps_the_coverage_steps(self) -> None:
        stdout = self.with_log("AssertionError: test selection: changed files, 7 of 85 modules\nOK\n")
        self.assert_coverage_steps(stdout, ran=True)


class TheFixtureHarnesses(unittest.TestCase):
    """The harnesses that copy `run-tests.sh` drop the fast-path variable.

    `make check CHANGED="<paths>"` exports `TEST_CHANGED_FILES` to every
    recipe and so to every test process. Both modules below build a throwaway
    tree, copy `run-tests.sh` into it and run it, and that copy reads the
    variable it inherits. It is inert only while neither copies
    `select-tests.py` as well -- the selector call then fails and the nested
    run widens to the whole fixture suite -- so an outer narrowed run would
    start narrowing its own nested runs the day one of them copies
    `.github/scripts` whole. The scrub is pinned here rather than left to
    that accident.
    """

    def test_an_inherited_fast_path_variable_does_not_reach_a_fixture_run(self) -> None:
        from tests import test_gate_harness_isolation, test_run_tests_split_fixtures

        builders = (
            ("test_gate_harness_isolation", test_gate_harness_isolation._fixture_env),
            ("test_run_tests_split_fixtures", test_run_tests_split_fixtures.fixture_env),
        )
        ambient = {"TEST_CHANGED_FILES": "bin/sd-alpha", "CHANGED": "bin/sd-alpha"}
        with unittest.mock.patch.dict(os.environ, ambient):
            for name, builder in builders:
                with self.subTest(module=name):
                    environment = builder()
                    self.assertNotIn("TEST_CHANGED_FILES", environment)
                    self.assertNotIn("CHANGED", environment)


if __name__ == "__main__":
    unittest.main()
