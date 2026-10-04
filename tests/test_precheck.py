"""`make precheck` runs first under `sd-check`, and a failure there stops the gate (sd:2604).

Each case runs the real `bin/sd-check` over a throwaway tree holding the
repository's own `Makefile`, `run-precheck.py` and `run-tests.sh`. The fixture
modules are the changed-files fixture's: twelve that carry the always-run line
and six that do not, each recording that it ran. The linters, the audit and
`sd-docs-lint` are stubs behind the fixture venv's `python`, so the cases say
what runs and in which order, not whether this checkout lints clean.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from typing import Any

from tests.test_changed_files_fast_path import (
    ALWAYS_RUN_NAMES,
    MARKER_LINE,
    OPTIONAL_TESTS,
    SCRIPTS,
    MakefileTree,
    clean_environment,
    ran_modules,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD_CHECK = REPO_ROOT / "bin/sd-check"
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402

#: The fixture venv's `python`: ruff fails while `LINT_FAILS` exists, and the
#: other tools `make check` reaches through it only say that they ran.
STUB_PYTHON = """#!/bin/sh
case "$1 $2" in
  "-m ruff")
    if [ -e LINT_FAILS ]; then printf '%s\\n' "bin/sd_beta.py:1:1: F401 unused import"; exit 1; fi
    exit 0 ;;
  "-m mypy") exit 0 ;;
esac
if [ "$1 $2 $3" = "-m coverage combine" ]; then printf '%s\\n' "coverage combine ran"; exit 0; fi
if [ "$1" = "bin/sd-docs-lint" ]; then exit 0; fi
exec "{python}" "$@"
"""

FAILING_TEST = """import unittest


class Broken(unittest.TestCase):
    def test_it(self):
        self.fail("the always-run module fails")
"""


class PrecheckTree(MakefileTree):
    """The repository's gate files over a git tree, with every tool but the tests stubbed."""

    def setUp(self) -> None:
        super().setUp()
        scripts = self.root / ".github/scripts"
        for name in ("run-precheck.py", "check-bash32-syntax.sh"):
            shutil.copy2(SCRIPTS / name, scripts / name)
        venv_bin = self.root / "venv/bin"
        (venv_bin / "python").write_text(STUB_PYTHON.replace("{python}", sys.executable))
        (venv_bin / "bandit").write_text("#!/bin/sh\nexit 0\n")
        for tool in ("python", "bandit"):
            path = venv_bin / tool
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.root, check=True)

    def gate(self, *arguments: str, expect: int) -> tuple[dict[str, Any], set[str]]:
        """`sd-check --json` in the tree: its report and the fixture modules that ran."""

        shutil.rmtree(self.ran_dir, ignore_errors=True)
        self.ran_dir.mkdir()
        result = subprocess.run([sys.executable, str(SD_CHECK), "--json", *arguments], cwd=self.root, text=True,
                                capture_output=True, timeout=600,
                                env=clean_environment(RAN_DIR=str(self.ran_dir), VENV="venv", SD_GATE_SLOTS="0"))
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return json.loads(result.stdout), ran_modules(self.ran_dir)

    def assert_stopped(self, report: dict[str, Any], ran: set[str], expected: set[str]) -> str:
        """The precheck failed and nothing after it ran; returns what the precheck printed."""

        self.assertEqual(ran, expected, "the full test run did not start")
        self.assertNotIn("gate_slot", report, "a failed precheck stops the gate before the slot wait")
        self.assertIn("precheck", report, "sd-check ran the precheck")
        self.assertEqual(report["precheck"]["status"], "fail")
        check = next(row for row in report["checks"] if row["name"] == "check")
        self.assertEqual((check["status"], check["exit_code"]), ("fail", None))
        self.assertEqual(check["reason"], "precheck failed, so this did not run")
        return report["precheck"]["stdout"] + report["precheck"]["stderr"]


class ThePrecheckGate(PrecheckTree):
    def test_a_lint_error_stops_the_gate_before_any_test_and_is_named(self) -> None:
        (self.root / "LINT_FAILS").touch()

        report, ran = self.gate(expect=1)

        said = self.assert_stopped(report, ran, set())
        self.assertIn("F401 unused import", said)
        self.assertRegex(said, r"\*\*\* \[[^]]*\blint\] Error")

    def test_a_failing_always_run_module_stops_the_gate_and_is_named(self) -> None:
        (self.root / "tests/test_ls_files_form.py").write_text(MARKER_LINE + "\n" + FAILING_TEST)

        report, ran = self.gate(expect=1)

        said = self.assert_stopped(report, ran, set(ALWAYS_RUN_NAMES) - {"test_ls_files_form"})
        self.assertIn("precheck: tests.test_ls_files_form FAIL", said)
        self.assertIn("precheck failed: tests.test_ls_files_form\n", said)

    def test_a_clean_precheck_proceeds_to_the_full_run(self) -> None:
        report, ran = self.gate(expect=0)

        self.assertIn("precheck", report, "sd-check ran the precheck")
        self.assertEqual(report["precheck"]["status"], "pass")
        self.assertIn(f"precheck: {len(ALWAYS_RUN_NAMES)} always-run modules pass", report["precheck"]["stdout"])
        self.assertEqual(report["status"], "pass")
        self.assertIn("gate_slot", report)
        self.assertEqual(ran, set(ALWAYS_RUN_NAMES) | set(OPTIONAL_TESTS))
        self.assertIn("coverage combine ran", report["checks"][0]["stdout"])

    def test_only_runs_one_check_without_the_precheck(self) -> None:
        (self.root / "tests/test_ls_files_form.py").write_text(MARKER_LINE + "\n" + FAILING_TEST)

        report, ran = self.gate("--only", "lint", expect=0)

        self.assertNotIn("precheck", report)
        self.assertEqual(ran, set())

    def test_a_tree_with_no_always_run_module_fails_the_precheck(self) -> None:
        for name in ALWAYS_RUN_NAMES:
            path = self.root / "tests" / f"{name}.py"
            path.write_text(path.read_text().replace(MARKER_LINE + "\n", ""))

        said = self.run_in_tree(["make", "--no-print-directory", "precheck", "VENV=venv"], expect=2).stdout

        self.assertIn("precheck failed: no test module carries the always-run line", said)


class TheDetection(unittest.TestCase):
    """`sd-check` runs a precheck only where the Makefile defines the target."""

    def detected(self, makefile: str) -> list[str] | None:
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            (root / "Makefile").write_text(makefile)
            return sd_lib.detect_entrypoints(root).precheck

    def test_a_precheck_target_is_detected(self) -> None:
        self.assertEqual(self.detected("precheck:\n\ttrue\ncheck: precheck\n\ttrue\n"), ["make", "precheck"])

    def test_without_the_target_there_is_none(self) -> None:
        self.assertIsNone(self.detected("check:\n\ttrue\n"))


if __name__ == "__main__":
    unittest.main()
