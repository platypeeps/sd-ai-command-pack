"""Fixtures for bin/sd-check: real repositories, real subprocesses, real exits.

Every case here runs the executable the way a user would, so the exit code
under test is the exit code a caller sees. The checks the fixtures declare are
short `python3 -c` commands rather than `make` targets: the runner's contract
is about statuses and exit codes, not about which build tool happens to be
installed on the machine running the suite.
"""

from __future__ import annotations

import json
import os
import pathlib
import shlex
import signal
import subprocess
import sys
import tempfile
import time
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
        # `core.excludesFile` is set per-repo to nowhere because the machine
        # running these tests may have the pack installed, and the one line the
        # installer puts in the user's global excludes is `CLAUDE.local.md` --
        # the very file the purity test expects `git status` to report as
        # untracked. Without this the fixture inherits the developer's global
        # excludes and the assertion below silently depends on machine state.
        for args in (
            ("init", "-b", "main"),
            ("config", "user.email", "test@example.com"),
            ("config", "user.name", "Test User"),
            ("config", "core.excludesFile", "/dev/null"),
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


class HiddenBuildFileTests(CheckFixture):
    """sd:1894: the local block replaces build-file detection whole, so say what it hides."""

    def package(self, root: pathlib.Path, *names: str) -> None:
        scripts = {name: "exit 0" for name in names}
        (root / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")

    def test_a_block_without_check_names_the_check_script_it_hides(self) -> None:
        root = self.make_repo()
        self.package(root, "check", "test", "lint")
        self.declare(root, test=f"{PY} -c pass", lint=f"{PY} -c pass")
        result = self.run_json(root)
        self.assertEqual(result["source"], "local-block")
        [warning] = result["warnings"]
        self.assertIn("package.json defines check (npm run check)", warning)
        self.assertIn("warning: CLAUDE.local.md replaces package.json detection", self.run_check(root).stdout)

    def test_a_block_that_omits_a_makefile_target_names_it(self) -> None:
        root = self.make_repo()
        (root / "Makefile").write_text("test:\n\t@true\nlint:\n\t@true\n", encoding="utf-8")
        self.declare(root, test=f"{PY} -c pass")
        [warning] = self.run_json(root)["warnings"]
        self.assertIn("Makefile defines lint (make lint)", warning)

    def test_a_block_that_declares_check_hides_nothing(self) -> None:
        root = self.make_repo()
        self.package(root, "check", "test", "lint")
        self.declare(root, check=f"{PY} -c pass")
        self.assertEqual(self.run_json(root)["warnings"], [])

    def test_no_build_file_or_an_unreadable_one_warns_about_nothing(self) -> None:
        bare, broken = self.make_repo("bare"), self.make_repo("broken")
        (broken / "package.json").write_text("{not json", encoding="utf-8")
        for root in (bare, broken):
            with self.subTest(root=root.name):
                self.declare(root, test=f"{PY} -c pass")
                result = self.run_json(root)
                self.assertEqual((result["_exit"], result["warnings"]), (0, []))

    def test_a_build_file_answering_alone_carries_no_warning(self) -> None:
        root = self.make_repo()
        (root / "Makefile").write_text("check:\n\t@true\n", encoding="utf-8")
        result = self.run_json(root)
        self.assertEqual((result["source"], result["warnings"]), ("makefile", []))


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
                    "output_path",
                    "failed_shards",
                    "failed_steps",
                    "failure",
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


class WholeOutputTests(CheckFixture):
    """sd:2558. The report keeps each stream's tail, so a shard that failed
    early in a long run was in neither; prepare named a failed gate without
    the test that failed it."""

    SHARD = "shard tests.test_middle: 4s exit=1"

    def long_failing_run(self, root: pathlib.Path) -> None:
        (root / "suite.py").write_text(
            "import sys\n"
            "print('first line of the run')\n"
            "for index in range(3000):\n"
            "    print(f'filler {index}')\n"
            "    if index == 1500:\n"
            f"        print('shard tests.test_fine: 2s exit=0')\n"
            f"        print({self.SHARD!r})\n"
            "print('last line of the run')\n"
            "sys.exit(1)\n",
            encoding="utf-8",
        )
        self.declare(root, check=f"{PY} suite.py")

    def test_a_failed_shard_in_the_middle_is_named_and_the_file_holds_everything(self) -> None:
        root = self.make_repo()
        self.long_failing_run(root)
        result = self.run_json(root)
        record = {row["name"]: row for row in result["checks"]}["check"]
        self.assertEqual(record["status"], "fail")
        self.assertTrue(record["output_truncated"])
        self.assertNotIn(self.SHARD, record["stdout"])
        self.assertEqual(record["failed_shards"], [self.SHARD])
        kept = pathlib.Path(record["output_path"])
        self.assertEqual(kept.parent, (root / ".git" / "sd-check-output").resolve())
        text = kept.read_text(encoding="utf-8")
        for line in ("first line of the run", "filler 0", self.SHARD, "filler 2999", "last line of the run"):
            self.assertIn(line, text)

    def test_the_human_report_names_the_failed_shard_and_the_file(self) -> None:
        root = self.make_repo()
        self.long_failing_run(root)
        completed = self.run_check(root)
        self.assertEqual(completed.returncode, 1)
        self.assertIn(f"failed {self.SHARD}", completed.stdout)
        self.assertIn("whole output: ", completed.stdout)

    def test_a_passing_check_keeps_no_file(self) -> None:
        root = self.make_repo()
        self.declare(root, check=f"{PY} -c pass")
        record = self.run_json(root)["checks"][0]
        self.assertIsNone(record["output_path"])
        self.assertFalse((root / ".git" / "sd-check-output").exists())


class FailedStepTests(CheckFixture):
    """sd:2608. A failed gate read `failed_shards: []` on every row a reader
    looked at when the step that failed was no shard: a make target, a suite
    of another runner, or a command that names nothing. A failed check now
    always names its step and carries the failing part of its output."""

    def run_failing(self, root: pathlib.Path, script: str, *args: str) -> dict[str, Any]:
        (root / "run.py").write_text(script, encoding="utf-8")
        self.declare(root, check=f"{PY} run.py")
        result = self.run_json(root, *args)
        self.assertEqual(result["status"], "fail")
        return {row["name"]: row for row in result["checks"]}["check"]

    def test_a_make_target_that_fails_outside_a_shard_is_the_step(self) -> None:
        root = self.make_repo()
        (root / "Makefile").write_text(
            "check: docs-lint test\n"
            "docs-lint:\n\t@echo 'docs-lint: README.md cites a missing anchor' && exit 3\n"
            "test:\n\t@echo 'shard tests.test_fine: 1s exit=0'\n",
            encoding="utf-8",
        )
        record = {row["name"]: row for row in self.run_json(root)["checks"]}["check"]
        self.assertEqual(record["status"], "fail")
        self.assertEqual(record["failed_shards"], [])
        self.assertEqual(record["failed_steps"], ["make target docs-lint"])
        self.assertIn("README.md cites a missing anchor", record["failure"])

    def test_a_suite_another_runner_names_as_failed_is_the_step(self) -> None:
        record = self.run_failing(self.make_repo(), (
            "import sys\n"
            "print('== shared')\nprint('FAIL: test_one (tests.test_shared.Case.test_one)')\n"
            "print('AssertionError: 2 != 3')\n"
            "sys.stderr.write('check.sh: failed: shared macos; logs kept in /tmp/example\\n')\n"
            "sys.exit(1)\n"))
        self.assertEqual(record["failed_steps"], ["suite shared", "suite macos"])
        self.assertIn("FAIL: test_one (tests.test_shared.Case.test_one)", record["failure"])
        self.assertIn("AssertionError: 2 != 3", record["failure"])

    def test_a_failure_that_names_no_step_names_the_check_and_its_exit(self) -> None:
        record = self.run_failing(self.make_repo(), "import sys\nprint('boom at the end')\nsys.exit(4)\n")
        self.assertEqual(record["failed_steps"], ["check exit 4"])
        self.assertIn("boom at the end", record["failure"])

    def test_a_check_that_timed_out_names_the_timeout(self) -> None:
        record = self.run_failing(self.make_repo(), "import time\ntime.sleep(30)\n", "--timeout", "2")
        self.assertEqual(record["failed_steps"], ["check: timed out after 2s"])

    def test_a_failed_shard_carries_its_own_failure_though_the_tail_misses_it(self) -> None:
        record = self.run_failing(self.make_repo(), (
            "import sys\n"
            "print('shard tests.test_before: start')\nprint('ValueError: logged by a passing shard')\n"
            "print('shard tests.test_before: 0s exit=0')\n"
            "print('shard tests.test_early: start')\n"
            "print('FAIL: test_cap (tests.test_early.Budget.test_cap)')\n"
            "print('AssertionError: 4689 not less than or equal to 4683')\n"
            "for index in range(40):\n"
            "    print(f'  traceback frame {index} of the failing test')\n"
            "print('FAILED (failures=1)')\n"
            "print('shard tests.test_early: 0s exit=1')\n"
            "for index in range(3000):\n"
            "    print(f'shard tests.test_late_{index}: 0s exit=0')\n"
            "sys.stderr.write('make: *** [test] Error 1\\n')\n"
            "sys.exit(2)\n"))
        self.assertNotIn("AssertionError: 4689", record["stdout"])
        self.assertEqual(record["failed_steps"], ["shard tests.test_early: 0s exit=1", "make target test"])
        self.assertIn("FAIL: test_cap (tests.test_early.Budget.test_cap)", record["failure"])
        self.assertIn("AssertionError: 4689 not less than or equal to 4683", record["failure"])
        self.assertNotIn("test_late_2999", record["failure"])
        self.assertNotIn("logged by a passing shard", record["failure"])

    def test_the_human_report_names_the_step_and_the_failure(self) -> None:
        root = self.make_repo()
        self.declare(root, check=f"{PY} -c \"import sys; print('it broke'); sys.exit(5)\"")
        completed = self.run_check(root)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("failed step: check exit 5", completed.stdout)
        self.assertIn("[failure]\nit broke", completed.stdout)

    def test_a_passing_or_skipped_check_names_no_step(self) -> None:
        root = self.make_repo()
        self.declare(root, check=f"{PY} -c pass", lint=f"{PY} -c pass")
        for record in self.run_json(root)["checks"]:
            self.assertEqual((record["failed_steps"], record["failure"]), ([], ""), record["name"])


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


def witness_snippet(witness: pathlib.Path) -> str:
    """A Python snippet that creates `witness`, as one shell word.

    The two quoting layers are separate and must stay that way: `!r` produces
    the Python string literal, and the caller wraps the whole snippet in
    `shlex.quote` for the shell. Quoting for the shell first and then taking
    `!r` would bake the shell quotes into the Python string, so a path that
    needed quoting would be created under a different name -- and every
    assertion below that the command did NOT run would pass for the wrong
    reason.
    """
    return f"open({str(witness)!r}, 'w').close()"


class DryRunTests(CheckFixture):
    def test_prints_the_plan_and_runs_nothing(self) -> None:
        root = self.make_repo()
        witness = root / "witness"
        self.declare(
            root,
            check=f"{PY} -c {shlex.quote(witness_snippet(witness))}",
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
            check=f"{PY} -c {shlex.quote(witness_snippet(witness))}",
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


#: A check that records its own pid and a background sleeper's, then waits.
ORPHAN_CHECK = 'sleep 60 &\necho "$$ $!" > pids\nwait\n'


def running(pid: int) -> bool:
    """Alive and not a zombie waiting for its parent to reap it."""
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(state) and not state.startswith("Z")


def default_interrupt() -> None:
    """A child of a runner that ignores SIGINT inherits that; the test needs Python's own handler."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)


class ProcessGroupTests(CheckFixture):
    """A stopped or timed-out `sd-check` ends every process its check started (sd:1815).

    `subprocess.run(timeout=)` kills the one process it started, and a signal
    to `sd-check` alone reached no child at all: `make check` and its test
    workers ran on with ppid 1. Real processes, because the defect is in
    which processes a signal reaches.
    """

    def orphan_repo(self) -> pathlib.Path:
        root = self.make_repo()
        (root / "orphan.sh").write_text(ORPHAN_CHECK, encoding="utf-8")
        self.declare(root, check="sh orphan.sh")
        return root

    @staticmethod
    def kill(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def started(self, pids: pathlib.Path) -> list[int]:
        deadline = time.monotonic() + 10
        while not (pids.is_file() and pids.read_text().strip()):
            self.assertLess(time.monotonic(), deadline, "the check never recorded its pids")
            time.sleep(0.05)
        found = [int(word) for word in pids.read_text().split()]
        for pid in found:
            self.addCleanup(self.kill, pid)
        return found

    def survivors(self, pids: list[int]) -> list[int]:
        """What is still running a moment later: a killed process can take a tick to die, an orphan never does."""
        deadline = time.monotonic() + 5
        alive = [pid for pid in pids if running(pid)]
        while alive and time.monotonic() < deadline:
            time.sleep(0.1)
            alive = [pid for pid in alive if running(pid)]
        return alive

    def stopped(self, number: int) -> tuple[int, str, list[int]]:
        """Start `sd-check` on the orphan check, send `number` to it alone, as `pkill` does."""
        root = self.orphan_repo()
        runner = subprocess.Popen([sys.executable, str(SD_CHECK)], cwd=str(root), stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, text=True, preexec_fn=default_interrupt)
        self.addCleanup(self.kill, runner.pid)
        pids = self.started(root / "pids")
        runner.send_signal(number)
        _, errors = runner.communicate(timeout=30)
        return runner.returncode, errors, self.survivors(pids)

    def test_a_timed_out_check_leaves_nothing_running(self) -> None:
        root = self.orphan_repo()
        result = self.run_json(root, "--timeout", "1")
        pids = self.started(root / "pids")
        self.assertEqual(result["checks"][0]["reason"], "timed out after 1s")
        self.assertEqual(self.survivors(pids), [], f"left running after the timeout: {pids}")

    def test_a_terminated_run_takes_its_check_with_it(self) -> None:
        code, _, alive = self.stopped(signal.SIGTERM)
        self.assertEqual(code, -signal.SIGTERM)
        self.assertEqual(alive, [], "left running after sd-check was terminated")

    def test_an_interrupted_run_takes_its_check_with_it(self) -> None:
        code, errors, alive = self.stopped(signal.SIGINT)
        self.assertEqual(code, -signal.SIGINT)
        self.assertNotIn("Traceback", errors)
        self.assertEqual(alive, [], "left running after sd-check was interrupted")

    def test_a_finished_check_leaves_nothing_behind_either(self) -> None:
        root = self.make_repo()
        (root / "leave.sh").write_text('sleep 60 > /dev/null 2>&1 &\necho "$!" > pids\n', encoding="utf-8")
        self.declare(root, check="sh leave.sh")
        result = self.run_json(root)
        pids = self.started(root / "pids")
        self.assertEqual(result["_exit"], 0)
        self.assertEqual(self.survivors(pids), [], f"left running after the check passed: {pids}")


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
