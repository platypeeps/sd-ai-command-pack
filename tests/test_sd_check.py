"""Fixtures for bin/sd-check: real repositories, real subprocesses, real exits.

Every case here runs the executable the way a user would, so the exit code
under test is the exit code a caller sees. The checks the fixtures declare are
short `python3 -c` commands rather than `make` targets: the runner's contract
is about statuses and exit codes, not about which build tool happens to be
installed on the machine running the suite.
"""

from __future__ import annotations

import json
import pathlib
import shlex
import subprocess
import sys
import tempfile
import unittest
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD_CHECK = REPO_ROOT / "bin" / "sd-check"
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402

PY = shlex.quote(sys.executable)


class CheckFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()

    def make_repo(self, name: str = "repo") -> pathlib.Path:
        root = self.tmp / name
        root.mkdir(parents=True)
        for args in (
            ("init", "-b", "main"),
            ("config", "user.email", "test@example.com"),
            ("config", "user.name", "Test User"),
        ):
            subprocess.run(
                ["git", *args], cwd=str(root), check=True, capture_output=True, text=True
            )
        return root

    def declare(self, root: pathlib.Path, **commands: str) -> None:
        body = "".join(f"{name}: {value}\n" for name, value in commands.items())
        (root / sd_lib.LOCAL_FILE_NAME).write_text(
            f"{sd_lib.LOCAL_BLOCK_START}\n{body}{sd_lib.LOCAL_BLOCK_END}\n",
            encoding="utf-8",
        )

    def run_check(
        self, root: pathlib.Path, *args: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SD_CHECK), *args],
            cwd=str(root),
            capture_output=True,
            text=True,
        )

    def run_json(self, root: pathlib.Path, *args: str) -> dict[str, Any]:
        completed = self.run_check(root, "--json", *args)
        self.assertNotEqual(completed.returncode, 2, completed.stderr)
        loaded = json.loads(completed.stdout)
        assert isinstance(loaded, dict)
        loaded["_exit"] = completed.returncode
        return loaded

    def statuses(self, result: dict[str, Any]) -> dict[str, str]:
        return {record["name"]: record["status"] for record in result["checks"]}


class ExitCodeTests(CheckFixture):
    def test_all_green_exits_zero(self) -> None:
        root = self.make_repo()
        self.declare(root, check=f"{PY} -c pass")
        completed = self.run_check(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("sd-check: pass", completed.stdout)

    def test_a_failing_check_exits_one(self) -> None:
        root = self.make_repo()
        self.declare(root, check=f'{PY} -c "raise SystemExit(3)"')
        completed = self.run_check(root)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("sd-check: fail", completed.stdout)

    def test_controlled_errors_exit_two_without_a_traceback(self) -> None:
        loose = self.tmp / "loose"
        loose.mkdir()
        repo = self.make_repo("declared")
        self.declare(repo, check=f"{PY} -c pass")
        broken = self.make_repo("broken")
        (broken / sd_lib.LOCAL_FILE_NAME).write_text(
            f"{sd_lib.LOCAL_BLOCK_START}\ncheck: true\n", encoding="utf-8"
        )
        bare = self.make_repo("bare")

        cases = [
            ("outside a repository", loose, ()),
            ("unknown --only name", repo, ("--only", "bogus")),
            ("--only an undetected check", repo, ("--only", "lint")),
            ("unterminated local block", broken, ()),
            ("non-positive timeout", repo, ("--timeout", "0")),
            ("--only with nothing detected", bare, ("--only", "check")),
        ]
        for label, root, args in cases:
            with self.subTest(label):
                completed = self.run_check(root, *args)
                self.assertEqual(completed.returncode, 2, completed.stdout)
                self.assertIn("sd-check: error:", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)


class JsonShapeTests(CheckFixture):
    def test_one_object_naming_every_check(self) -> None:
        root = self.make_repo()
        self.declare(
            root,
            check=f'{PY} -c "print(\'hello\')"',
            lint=f"{PY} -c pass",
        )
        result = self.run_json(root)
        self.assertEqual(result["_exit"], 0)
        self.assertEqual(result["tool"], "sd-check")
        self.assertEqual(result["source"], "local-block")
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["dry_run"])
        self.assertEqual(
            [record["name"] for record in result["checks"]], list(sd_lib.CHECK_NAMES)
        )
        by_name = {record["name"]: record for record in result["checks"]}
        self.assertEqual(by_name["check"]["status"], "pass")
        self.assertEqual(by_name["check"]["exit_code"], 0)
        self.assertIn("hello", by_name["check"]["stdout"])
        self.assertGreaterEqual(by_name["check"]["duration_seconds"], 0.0)
        self.assertEqual(by_name["test"]["status"], "absent")
        self.assertIsNone(by_name["test"]["command"])
        self.assertEqual(by_name["lint"]["status"], "skipped")
        self.assertEqual(by_name["lint"]["reason"], "covered by the check entrypoint")
        for record in result["checks"]:
            self.assertEqual(
                set(record),
                {
                    "name",
                    "command",
                    "status",
                    "exit_code",
                    "duration_seconds",
                    "reason",
                    "stdout",
                    "stderr",
                    "output_truncated",
                },
            )
            self.assertIn(record["status"], {"pass", "fail", "skipped", "absent"})

    def test_failure_is_attributed_to_the_check_that_failed(self) -> None:
        root = self.make_repo()
        self.declare(
            root,
            test=f'{PY} -c "import sys; sys.stderr.write(\'boom\'); raise SystemExit(2)"',
            lint=f"{PY} -c pass",
        )
        result = self.run_json(root)
        self.assertEqual(result["_exit"], 1)
        self.assertEqual(result["status"], "fail")
        by_name = {record["name"]: record for record in result["checks"]}
        self.assertEqual(by_name["test"]["status"], "fail")
        self.assertEqual(by_name["test"]["exit_code"], 2)
        self.assertIn("boom", by_name["test"]["stderr"])
        self.assertEqual(by_name["lint"]["status"], "pass")
        self.assertEqual(by_name["lint"]["stderr"], "")


class AbsentTests(CheckFixture):
    def test_a_repository_with_no_entrypoints_is_absent_not_failed(self) -> None:
        root = self.make_repo()
        result = self.run_json(root)
        self.assertEqual(result["_exit"], 0)
        self.assertEqual(result["status"], "absent")
        self.assertIsNone(result["source"])
        self.assertEqual(
            self.statuses(result), {"check": "absent", "test": "absent", "lint": "absent"}
        )

    def test_absent_is_distinct_from_skipped(self) -> None:
        root = self.make_repo()
        self.declare(root, check=f"{PY} -c pass", test=f"{PY} -c pass")
        self.assertEqual(
            self.statuses(self.run_json(root)),
            {"check": "pass", "test": "skipped", "lint": "absent"},
        )


class DryRunTests(CheckFixture):
    def test_prints_the_plan_and_runs_nothing(self) -> None:
        root = self.make_repo()
        witness = root / "witness"
        self.declare(
            root,
            check=f"{PY} -c \"open({shlex.quote(str(witness))!r}, 'w').close()\"",
        )
        completed = self.run_check(root, "--dry-run")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("dry run", completed.stdout)
        self.assertFalse(witness.exists())

    def test_dry_run_json_reports_the_command_it_would_run(self) -> None:
        root = self.make_repo()
        self.declare(root, check=f"{PY} -c pass")
        result = self.run_json(root, "--dry-run")
        self.assertEqual(result["_exit"], 0)
        self.assertTrue(result["dry_run"])
        by_name = {record["name"]: record for record in result["checks"]}
        self.assertEqual(by_name["check"]["status"], "skipped")
        self.assertEqual(by_name["check"]["reason"], "dry run")
        self.assertEqual(by_name["check"]["command"][:2], [sys.executable, "-c"])

    def test_a_dry_run_of_a_failing_check_still_exits_zero(self) -> None:
        root = self.make_repo()
        self.declare(root, check=f'{PY} -c "raise SystemExit(1)"')
        self.assertEqual(self.run_check(root, "--dry-run").returncode, 0)


class OnlyTests(CheckFixture):
    def test_only_runs_one_and_skips_the_rest(self) -> None:
        root = self.make_repo()
        witness = root / "witness"
        self.declare(
            root,
            check=f"{PY} -c \"open({shlex.quote(str(witness))!r}, 'w').close()\"",
            lint=f"{PY} -c pass",
        )
        result = self.run_json(root, "--only", "lint")
        self.assertEqual(result["_exit"], 0)
        self.assertEqual(
            self.statuses(result), {"check": "skipped", "test": "absent", "lint": "pass"}
        )
        self.assertFalse(witness.exists())


class TimeoutTests(CheckFixture):
    def test_a_check_past_its_timeout_fails_with_a_reason(self) -> None:
        root = self.make_repo()
        self.declare(root, check=f'{PY} -c "import time; time.sleep(30)"')
        result = self.run_json(root, "--timeout", "1")
        self.assertEqual(result["_exit"], 1)
        record = result["checks"][0]
        self.assertEqual(record["status"], "fail")
        self.assertIsNone(record["exit_code"])
        self.assertIn("timed out", record["reason"])


class PurityTests(CheckFixture):
    def test_the_runner_leaves_the_repository_alone(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "seed"], cwd=str(root), check=True, capture_output=True
        )
        self.declare(root, check=f"{PY} -c pass")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertEqual(self.run_check(root).returncode, 0)
        after = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertEqual(after.split(), ["??", sd_lib.LOCAL_FILE_NAME])
        self.assertEqual(
            head,
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                check=True,
                capture_output=True,
                text=True,
            ).stdout,
        )


if __name__ == "__main__":
    unittest.main()
