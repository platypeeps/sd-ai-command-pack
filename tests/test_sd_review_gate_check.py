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


class GateRepo(ReviewFixture):
    """A branch one commit ahead of `origin/main`, whose check counts its runs."""

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


class GateCheck(GateRepo):
    def test_a_second_prepare_at_the_head_reuses_the_first_ones_pass(self) -> None:
        """sd:1912: one passing check per head. A second prepare at the same head
        and binding reads the first one's receipt instead of running again."""
        root, database = self.repo()
        first, second = self.gate(root, database), self.gate(root, database)
        self.assertEqual((first["status"], first["source"]), ("pass", "gate"), json.dumps(first)[:2000])
        self.assertEqual((second["status"], second["source"]), ("pass", "gate-receipt"))
        self.assertEqual(len((self.tmp / "runs").read_text().splitlines()), 1)

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
        env = self.environment(SD_GATE_SLOTS="1", SD_GATE_SLOTS_DIR=str(slots), SD_GATE_LOAD_MAX="0",
                               SD_GATE_SETTLE_SECONDS="0")
        gate = sd_gate_run.check_in_worktree(root, git(root, "rev-parse", "HEAD"), base=sd_gate_run.base_ref("main"),
                                             database=database, environ=env)
        taken = gate["report"]["gate_slot"]
        self.assertEqual((taken["slots"], taken["source"]), (1, "SD_GATE_SLOTS"))
        self.assertEqual(pathlib.Path(taken["path"]).parent, slots)


class BuilderFixture(GateRepo):
    """`GateRepo` plus a builder's `sd gate check` and a count of the check's runs."""

    def environment(self, **extra: str) -> dict[str, str]:
        """The fixture's environment as a Python child holds it.

        The interpreter adds variables at start (`LC_CTYPE` by locale
        coercion; `__CF_USER_TEXT_ENCODING` on macOS), and the gate binds the
        environment whole. Both sides here start from what a child holds, as a
        builder's `sd gate check` and a lead's `sd-ship prepare` both do.
        """
        shown = subprocess.run([sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ)))"],
                               env=super().environment(**extra), capture_output=True, text=True, check=True)
        return json.loads(shown.stdout)

    def builder(self, root: pathlib.Path, database: pathlib.Path, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(pathlib.Path(sd_review._BIN) / "sd"), "gate", "check",
                               "--base", "main", "--database", str(database)],
                              cwd=root, capture_output=True, text=True, env=self.environment(**extra), timeout=600)

    def runs(self) -> int:
        counter = self.tmp / "runs"
        return len(counter.read_text().splitlines()) if counter.exists() else 0


class BuilderReceipt(BuilderFixture):
    """`sd gate check` (sd:1912): a builder's passing gate at a head is the one prepare's gate reuses.

    A plain `make check` leaves nothing a gate can trust; this verb runs the
    gate's own check, in a clean worktree at HEAD, and records its receipt.
    """

    def test_prepare_reuses_the_builders_pass_at_the_same_head(self) -> None:
        root, database = self.repo()
        done = self.builder(root, database)
        self.assertEqual(done.returncode, 0, done.stderr)
        built = json.loads(done.stdout)
        self.assertEqual((built["status"], built["head"]), ("success", git(root, "rev-parse", "HEAD")))
        self.assertIn("receipt_revision", built)
        gate = self.gate(root, database)
        self.assertEqual((gate["status"], gate["source"]), ("pass", "gate-receipt"), json.dumps(gate)[:2000])
        self.assertEqual(self.runs(), 1)

    def test_a_builder_in_another_agent_session_is_reused(self) -> None:
        """sd:1912, D1: a builder's session and the lead's differ in the agent
        harness's own variables; the gate drops those, so the pass binds equal."""
        root, database = self.repo()
        done = self.builder(root, database, CLAUDE_CODE_SESSION_ID="builder", HERDR_PANE_ID="p1", SHLVL="2",
                            PWD=str(root), TERM_SESSION_ID="t1")
        self.assertEqual(done.returncode, 0, done.stderr)
        gate = sd_review.run_gate_check(root, sd_review.subprocess_runner,
                                        self.environment(CLAUDE_CODE_SESSION_ID="lead", CLAUDE_EFFORT="low"),
                                        120, "main", namespace(database=database))
        self.assertEqual(gate["source"], "gate-receipt", json.dumps(gate)[:2000])
        self.assertEqual(self.runs(), 1)

    def test_a_merge_of_main_is_a_new_head_and_runs_again(self) -> None:
        root, database = self.repo()
        self.assertEqual(self.builder(root, database).returncode, 0)
        git(root, "checkout", "-q", "main")
        (root / "other.py").write_text("y = 2\n", encoding="utf-8")
        git(root, "add", "other.py")
        git(root, "commit", "-q", "-m", "main moved")
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(root, "checkout", "-q", "topic")
        git(root, "merge", "-q", "--no-edit", "main")
        gate = self.gate(root, database)
        self.assertEqual((gate["status"], gate["source"]), ("pass", "gate"))
        self.assertEqual(self.runs(), 2)

    def test_a_failed_builder_run_leaves_nothing_to_reuse(self) -> None:
        root, database = self.repo()
        flag = self.tmp / "fail"
        self.local_block(root, f"check: sh -c 'echo run >> {self.tmp / 'runs'}; test ! -e {flag}'")
        git(root, "add", "-A")
        git(root, "commit", "-q", "--allow-empty", "-m", "check can fail")
        flag.write_text("", encoding="utf-8")
        done = self.builder(root, database)
        self.assertEqual((done.returncode, json.loads(done.stdout)["status"]), (1, "failure"))
        flag.unlink()
        gate = self.gate(root, database)
        self.assertEqual((gate["status"], gate["source"]), ("pass", "gate"))
        self.assertEqual(self.runs(), 2)

    def test_a_run_that_did_not_finish_leaves_nothing_to_reuse(self) -> None:
        """A timed-out check is partial: `sd-check` reports no pass, and nothing is recorded."""
        import sd_gate_run

        root, database = self.repo()
        head = git(root, "rev-parse", "HEAD")
        partial = sd_gate_run.check_in_worktree(root, head, base=sd_gate_run.base_ref("main"), database=database,
                                                environ=self.environment(),
                                                run=lambda argv, env, cwd, limit: (None, "sd-check timed out", ""))
        self.assertEqual(partial["status"], "failure")
        self.assertNotIn("receipt_revision", partial)
        gate = self.gate(root, database)
        self.assertEqual((gate["status"], gate["source"]), ("pass", "gate"))

    def test_a_builder_run_under_another_environment_is_not_reused(self) -> None:
        """The binding holds the gate child's whole environment, so a shell that
        differs in a variable that may choose what runs gets its own check."""
        root, database = self.repo()
        done = self.builder(root, database, MAKEFLAGS="-k")
        self.assertEqual(done.returncode, 0, done.stderr)
        gate = self.gate(root, database)
        self.assertEqual(gate["source"], "gate")
        self.assertEqual(self.runs(), 2)


class TreeReceipt(BuilderFixture):
    """`.github/sd-gate-reuse.json` (sd:1912): a check that reads no commit history is keyed by its tree.

    Two heads with one tree -- an `sd attribute` commit, a message-only amend --
    differ only in commit metadata. A repository that declares its check reads
    none of it reuses the first head's pass at the second; one that does not
    declare keeps the head key, since a commit-message lint can pass at one
    head and fail at the other.
    """

    def declared(self) -> tuple[pathlib.Path, pathlib.Path]:
        root, database = self.repo()
        (root / ".github").mkdir(exist_ok=True)
        (root / ".github" / "sd-gate-reuse.json").write_text(
            json.dumps({"schema_version": 1, "key": "tree",
                        "reason": "the check reads no commit message, range or tag"}), encoding="utf-8")
        git(root, "add", ".github/sd-gate-reuse.json")
        git(root, "commit", "-q", "-m", "declare tree reuse")
        return root, database

    def test_a_declared_tree_reuses_the_pass_at_a_new_head_with_the_same_tree(self) -> None:
        root, database = self.declared()
        self.assertEqual(self.builder(root, database).returncode, 0)
        git(root, "commit", "-q", "--allow-empty", "-m", "attribute\n\nAuthored-with: claude/anthropic")
        gate = self.gate(root, database)
        self.assertEqual((gate["status"], gate["source"]), ("pass", "gate-receipt"), json.dumps(gate)[:2000])
        self.assertEqual(self.runs(), 1)

    def test_the_merge_gate_reads_a_tree_receipt_at_a_new_head(self) -> None:
        import sd_gate_run

        root, database = self.declared()
        built = git(root, "rev-parse", "HEAD")
        self.assertEqual(self.builder(root, database).returncode, 0)
        git(root, "commit", "-q", "--amend", "-m", "declare tree reuse, reworded")
        merged = sd_gate_run.check_in_worktree(root, git(root, "rev-parse", "HEAD"), base=sd_gate_run.base_ref("main"),
                                               database=database, environ=self.environment(), record=False)
        self.assertEqual((merged["status"], merged["head"]), ("success", git(root, "rev-parse", "HEAD")))
        self.assertEqual(merged["reused"]["head"], built)  # the head that passed, which the binding no longer names
        self.assertEqual(self.runs(), 1)

    def test_without_the_declaration_a_new_head_with_the_same_tree_runs_again(self) -> None:
        root, database = self.repo()
        self.assertEqual(self.builder(root, database).returncode, 0)
        git(root, "commit", "-q", "--allow-empty", "-m", "attribute")
        gate = self.gate(root, database)
        self.assertEqual((gate["status"], gate["source"]), ("pass", "gate"))
        self.assertEqual(self.runs(), 2)

    def test_a_declared_tree_that_changed_runs_again(self) -> None:
        root, database = self.declared()
        self.assertEqual(self.builder(root, database).returncode, 0)
        (root / "src.py").write_text("x = 2\n", encoding="utf-8")
        git(root, "commit", "-q", "-am", "one byte")
        gate = self.gate(root, database)
        self.assertEqual((gate["status"], gate["source"]), ("pass", "gate"))
        self.assertEqual(self.runs(), 2)

    def test_a_declaration_that_names_another_key_keeps_the_head_key(self) -> None:
        root, database = self.declared()
        (root / ".github" / "sd-gate-reuse.json").write_text(json.dumps({"schema_version": 1, "key": "content", "reason": "x"}), encoding="utf-8")
        git(root, "commit", "-q", "-am", "unknown key")
        self.assertEqual(self.builder(root, database).returncode, 0)
        git(root, "commit", "-q", "--allow-empty", "-m", "attribute")
        gate = self.gate(root, database)
        self.assertEqual(gate["source"], "gate")
        self.assertEqual(self.runs(), 2)

    def test_a_declared_tree_at_a_new_merge_base_runs_again(self) -> None:
        """The merge base is bound: main moved by an empty commit leaves the tree equal and the history not."""
        root, database = self.declared()
        self.assertEqual(self.builder(root, database).returncode, 0)
        git(root, "checkout", "-q", "main")
        git(root, "commit", "-q", "--allow-empty", "-m", "main moved, tree did not")
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(root, "checkout", "-q", "topic")
        tree = git(root, "rev-parse", "HEAD^{tree}")
        git(root, "merge", "-q", "--no-edit", "main")
        self.assertEqual(git(root, "rev-parse", "HEAD^{tree}"), tree)
        gate = self.gate(root, database)
        self.assertEqual((gate["status"], gate["source"]), ("pass", "gate"))
        self.assertEqual(self.runs(), 2)

    def test_a_declared_tree_with_no_base_keeps_the_head_key(self) -> None:
        import sd_gate_run

        root, database = self.declared()
        for _ in range(2):
            ran = sd_gate_run.check_in_worktree(root, git(root, "rev-parse", "HEAD"), database=database,
                                                environ=self.environment())
            self.assertEqual((ran["status"], "reused" in ran), ("success", False))
            git(root, "commit", "-q", "--allow-empty", "-m", "attribute")
        self.assertEqual(self.runs(), 2)
