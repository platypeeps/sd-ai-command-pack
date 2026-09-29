"""`sd-review --gate-check`: prepare's check is the local gate's, and its receipt serves the merge (sd:2041).

Also the gate's bound: with no `--timeout`, the repository gate gets
`sd_lib.GATE_CHECK_SECONDS`, the merge gate's own, not the reviewers' 1800.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from tests.test_sd_review import FakeRunner, ReviewFixture, namespace, sd_review


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True, text=True).stdout.strip()


class GateBound(ReviewFixture):
    def test_without_a_timeout_the_gate_gets_the_local_gates_bound(self) -> None:
        self.assertEqual(sd_review.gate_seconds(namespace(timeout=None)), sd_review.sd_lib.GATE_CHECK_SECONDS)
        self.assertEqual(sd_review.phase_seconds(namespace(timeout=None)), sd_review.DEFAULT_TIMEOUT_SECONDS)

    def test_an_explicit_timeout_still_bounds_both(self) -> None:
        """sd:1475: `--timeout` is the one limit every phase is planned with when the operator gives it."""
        args = namespace(timeout=90)
        self.assertEqual((sd_review.gate_seconds(args), sd_review.phase_seconds(args)), (90, 90))

    def test_the_timing_plan_carries_the_gates_bound_and_the_watchdog_counts_it(self) -> None:
        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        report = sd_review.review(root, namespace(explain=True, timeout=None), FakeRunner(), self.environment(),
                                   self.chatgpt_home())
        timing = report["timing"]
        self.assertEqual((timing["check_seconds"], timing["phase_seconds"]),
                         (sd_review.sd_lib.GATE_CHECK_SECONDS, sd_review.DEFAULT_TIMEOUT_SECONDS))
        self.assertEqual(timing["execution_seconds"], timing["setup_seconds"] + timing["check_seconds"]
                         + timing["phase_seconds"] * len(timing["candidates"]))

    def test_the_default_check_is_handed_the_gates_bound(self) -> None:
        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner({"sd-check": sd_review.Completed(1, '{"checks": []}', "")})
        report = sd_review.review(root, namespace(timeout=None), runner, self.environment(), self.chatgpt_home())
        self.assertEqual(report["status"], "gate_failed")
        [call] = [call for call in runner.calls if any("sd-check" in word for word in call["argv"])]
        self.assertEqual(call["argv"][call["argv"].index("--timeout") + 1], str(sd_review.sd_lib.GATE_CHECK_SECONDS))


class GateCheck(ReviewFixture):
    def repo(self) -> tuple[pathlib.Path, pathlib.Path]:
        from sd_db import initialise

        root = self.make_repo()
        counter = self.tmp / "runs"
        self.local_block(root, f"check: sh -c 'echo run >> {counter}'")
        git(root, "add", "-A")  # the block is tracked, or globally ignored and copied in as untracked
        git(root, "commit", "-q", "--allow-empty", "-m", "check")
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(root, "checkout", "-q", "-b", "topic")
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        git(root, "add", "src.py")
        git(root, "commit", "-q", "-m", "change")
        database = self.tmp / "sd.db"
        initialise(database)
        return root, database

    def gate(self, root: pathlib.Path, database: pathlib.Path) -> dict:
        return sd_review.run_gate_check(root, sd_review.subprocess_runner, self.environment(), 120, "main",
                                        namespace(database=database))

    def test_the_second_gate_check_at_a_head_reads_the_first_ones_receipt(self) -> None:
        root, database = self.repo()
        first, second = self.gate(root, database), self.gate(root, database)
        self.assertEqual((first["status"], first["source"]), ("pass", "gate"), json.dumps(first)[:2000])
        self.assertEqual((second["status"], second["source"]), ("pass", "gate-receipt"))
        self.assertEqual(len((self.tmp / "runs").read_text().splitlines()), 1)
        self.assertEqual(second["head"], git(root, "rev-parse", "HEAD"))

    def test_the_merge_gate_reads_prepares_receipt(self) -> None:
        import sd_gate_run

        root, database = self.repo()
        self.gate(root, database)
        with_env = dict(self.environment())
        from unittest import mock

        with mock.patch.dict("os.environ", with_env, clear=True):
            merged = sd_gate_run.check_in_worktree(root, git(root, "rev-parse", "HEAD"),
                                                   base=sd_gate_run.base_ref("main"), database=database)
        self.assertIn("reused", merged)
        self.assertEqual(len((self.tmp / "runs").read_text().splitlines()), 1)

    def test_a_gate_that_cannot_make_its_worktree_fails_the_gate(self) -> None:
        """A `git worktree` fault is a failed gate with its reason, not a crash and never a pass."""
        from unittest import mock

        import sd_gate_run

        root, database = self.repo()
        with mock.patch.object(sd_gate_run, "gate_git", side_effect=sd_gate_run.GateError("worktree refused")):
            gate = self.gate(root, database)
        self.assertEqual((gate["status"], gate["detail"]), ("fail", "worktree refused"))
        self.assertFalse((self.tmp / "runs").exists())

    def test_gate_check_needs_branch_scope(self) -> None:
        root, _ = self.repo()
        completed = subprocess.run([sys.executable, str(pathlib.Path(sd_review._BIN) / "sd-review"), "--gate-check", "main"],
                                   cwd=root, capture_output=True, text=True, env=self.environment())
        self.assertEqual(completed.returncode, sd_review.EXIT_USAGE, completed.stderr)
        self.assertIn("--gate-check checks the committed head", completed.stderr)

    def test_the_gate_check_takes_a_machine_wide_gate_slot(self) -> None:
        """sd:1996's cap reaches prepare's gate: the child `sd-check` takes a slot from the shared directory."""
        import sd_gate_run

        root, database = self.repo()
        slots = self.tmp / "slots"
        env = self.environment(SD_GATE_SLOTS="1", SD_GATE_SLOTS_DIR=str(slots))
        gate = sd_gate_run.check_in_worktree(root, git(root, "rev-parse", "HEAD"), base=sd_gate_run.base_ref("main"),
                                             database=database, environ=env)
        taken = gate["report"]["gate_slot"]
        self.assertEqual((taken["slots"], taken["source"]), (1, "SD_GATE_SLOTS"))
        self.assertEqual(pathlib.Path(taken["path"]).parent, slots)
