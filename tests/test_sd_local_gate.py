"""The local CI gate (sd:1843): `sd-check` at the exact head, posted as `sd/local-gate`.

Real git and a real `sd-check` child against a throwaway repository; the
GitHub side is a recorder, so nothing leaves the machine.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_gate_receipts  # noqa: E402
import sd_gate_run  # noqa: E402
import sd_lib  # noqa: E402
import sd_local_gate  # noqa: E402
from sd_ship_remote import Refusal  # noqa: E402


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class Recorder:
    """The `GitHub` calls the gate makes, answered from memory; posts land as `me`'s statuses."""

    prefix = "repos/o/r"

    def __init__(self, statuses: list | None = None) -> None:
        self.statuses = statuses or []
        self.posts: list[tuple[str, dict]] = []

    def viewer_login(self) -> str:
        return "Me"

    def pages(self, path: str, field: str | None = None) -> list:
        return list(self.statuses)

    def api(self, path: str, *, method: str = "GET", body: dict | None = None) -> dict:
        assert method == "POST", method
        self.posts.append((path, body or {}))
        self.statuses.insert(0, {**(body or {}), "sha": path.rsplit("/", 1)[1], "creator": {"login": "Me"}})
        return {"state": (body or {}).get("state")}


class Repository(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")

    def commit(self, makefile: str) -> str:
        (self.root / "Makefile").write_text(makefile, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c")
        return git(self.root, "rev-parse", "HEAD")

    def worktrees(self) -> int:
        return git(self.root, "worktree", "list", "--porcelain").count("worktree ")


class RunCheck(Repository):
    def test_a_passing_check_is_a_success_at_the_head_it_ran_on(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        result = sd_gate_run.check_in_worktree(self.root, head)
        self.assertEqual((result["head"], result["status"]), (head, "success"))
        self.assertIn("check pass", result["summary"])

    def test_a_failing_check_is_a_failure(self) -> None:
        head = self.commit("check:\n\t@false\n")
        result = sd_gate_run.check_in_worktree(self.root, head)
        self.assertEqual(result["status"], "failure")
        self.assertIn("check fail", result["summary"])

    def test_the_check_runs_in_a_clean_worktree_not_the_operators_checkout(self) -> None:
        """An untracked file in the checkout that would fail the check is not seen."""
        head = self.commit("check:\n\t@test ! -e dirty.txt\n")
        (self.root / "dirty.txt").write_text("operator's uncommitted state\n", encoding="utf-8")
        self.assertEqual(sd_gate_run.check_in_worktree(self.root, head)["status"], "success")

    def test_the_named_commit_is_checked_not_the_checkouts_head(self) -> None:
        first = self.commit("check:\n\t@false\n")
        self.commit("check:\n\t@echo ok\n")
        result = sd_gate_run.check_in_worktree(self.root, first)
        self.assertEqual((result["head"], result["status"]), (first, "failure"))

    def test_a_pythonpath_at_the_root_does_not_reach_the_child(self) -> None:
        """An editable install pointed at the dirty checkout must not be importable in the gate."""
        head = self.commit('check:\n\t@test -z "$$PYTHONPATH" && test -z "$$VIRTUAL_ENV"\n')
        with mock.patch.dict(os.environ, {"PYTHONPATH": str(self.root), "VIRTUAL_ENV": str(self.root / ".venv")}):
            self.assertEqual(sd_gate_run.check_in_worktree(self.root, head)["status"], "success")

    def test_the_environment_drops_package_selectors_and_path_entries_in_the_checkout(self) -> None:
        inside, outside = str(self.root / ".venv/bin"), "/usr/bin"
        env = sd_gate_run.gate_environment(self.root, {
            "PATH": os.pathsep.join([inside, outside, "relative/bin"]), "PYTHONPATH": str(self.root),
            "PYTHONHOME": "/x", "VIRTUAL_ENV": inside, "CONDA_PREFIX": "/c", "__PYVENV_LAUNCHER__": "/l", "HOME": "/h"})
        self.assertEqual(env, {"PATH": outside, "HOME": "/h", "SD_LOCAL_GATE": "1", "NO_COLOR": "1",
                               "PYTHON_COLORS": "0"})

    def test_the_operators_colour_settings_do_not_reach_the_check(self) -> None:
        """`FORCE_COLOR=3` in a terminal failed a repository's gate on ANSI-coloured output (sd:2076)."""
        env = sd_gate_run.gate_environment(self.root, {
            "PATH": "/usr/bin", "FORCE_COLOR": "3", "CLICOLOR_FORCE": "1", "PY_COLORS": "1",
            "NO_COLOR": "", "PYTHON_COLORS": "1"})
        self.assertFalse({"FORCE_COLOR", "CLICOLOR_FORCE", "PY_COLORS"} & env.keys())
        self.assertEqual((env["NO_COLOR"], env["PYTHON_COLORS"]), ("1", "0"))

    def test_the_agent_harness_session_variables_do_not_reach_the_check(self) -> None:
        """sd:1912, operator ruling D1 (2026-10-03). Two sessions differ in these
        and nothing else, so their passes must bind equal; MAKEFLAGS still binds."""
        session = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "a", "CLAUDE_PID": "1", "HERDR_PANE_ID": "p1",
                   "ITERM_SESSION_ID": "i1", "TERM_SESSION_ID": "t1", "PWD": "/one", "OLDPWD": "/x",
                   "SHLVL": "1", "_": "/usr/bin/env"}
        other = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "b", "CLAUDE_EFFORT": "high", "HERDR_TAB_ID": "t2",
                 "ITERM_PROFILE": "x", "TERM_SESSION_ID": "t2", "PWD": "/two", "SHLVL": "3", "_": "/bin/sh"}
        base = {"PATH": "/usr/bin", "HOME": "/h"}
        first = sd_gate_run.gate_environment(self.root, {**base, **session})
        self.assertEqual(first, sd_gate_run.gate_environment(self.root, {**base, **other}))
        self.assertEqual(first, sd_gate_run.gate_environment(self.root, base))
        self.assertNotEqual(first, sd_gate_run.gate_environment(self.root, {**base, **session, "MAKEFLAGS": "-k"}))

    def test_the_check_is_told_it_is_the_gate(self) -> None:
        """`SD_LOCAL_GATE=1` is the contract a repository reads to provision instead of borrow (sd:1918)."""
        head = self.commit('check:\n\t@test "$$SD_LOCAL_GATE" = 1\n')
        with mock.patch.dict(os.environ, {"SD_LOCAL_GATE": "0"}):
            self.assertEqual(sd_gate_run.check_in_worktree(self.root, head)["status"], "success")

    def test_a_virtualenv_bin_outside_the_checkout_is_dropped_from_path(self) -> None:
        """A venv's `bin` is found by the `pyvenv.cfg` beside it, wherever it lives."""
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        venv, plain = pathlib.Path(outside.name) / "venv", pathlib.Path(outside.name) / "tools"
        (venv / "bin").mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        plain.mkdir()
        env = sd_gate_run.gate_environment(self.root, {"PATH": os.pathsep.join([str(venv / "bin"), str(plain)])})
        self.assertEqual(env["PATH"], str(plain.resolve()))  # each kept entry resolved (sd:2602)

    def test_the_gates_bound_is_the_per_check_timeout_sd_check_reports(self) -> None:
        """`sd-check`'s own 900 s default must not cut a gate run short; the gate's bound reaches it."""
        head = self.commit("check:\n\t@sleep 5\n")
        result = sd_gate_run.check_in_worktree(self.root, head, timeout=1)
        self.assertEqual((result["status"], result["exit_code"]), ("failure", 1))
        self.assertIn("check fail", result["summary"])

    def test_the_result_keeps_the_full_sd_check_report(self) -> None:
        """The worktree is deleted after the run, so the receipt is the only place its output survives (sd:1872)."""
        head = self.commit("check:\n\t@echo gate-output-marker; false\n")
        result = sd_gate_run.check_in_worktree(self.root, head)
        [check] = [entry for entry in result["report"]["checks"] if entry["name"] == "check"]
        self.assertEqual((result["report"]["status"], check["exit_code"]), ("fail", 2))
        self.assertIn("gate-output-marker", check["stdout"])

    def test_a_configuration_fault_keeps_sd_checks_stderr(self) -> None:
        """Exit 2 prints no report; what is wrong is on sd-check's stderr, and the receipt keeps it."""
        head = self.commit("check:\n\t@echo ok\n")
        (self.root / "CLAUDE.local.md").write_text(
            "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\ncheck: 'unterminated\n<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n",
            encoding="utf-8")
        result = sd_gate_run.check_in_worktree(self.root, head)
        self.assertEqual((result["status"], result["exit_code"], result["report"]), ("failure", 2, None))
        self.assertIn("does not parse", result["stderr"])

    def test_the_worktree_is_removed_after_the_run(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        before = self.worktrees()
        sd_gate_run.check_in_worktree(self.root, head)
        self.assertEqual(self.worktrees(), before)


class Reading(unittest.TestCase):
    def test_only_an_exit_zero_pass_is_a_success(self) -> None:
        passed = '{"status": "pass", "checks": [{"name": "check", "status": "pass"}]}'
        self.assertEqual(sd_gate_run.check_reading(0, passed)["status"], "success")
        for code, output in ((0, '{"status": "absent", "checks": []}'), (0, '{"status": "skipped"}'),
                             (1, '{"status": "fail"}'), (2, ""), (None, "timed out"), (0, "not json")):
            with self.subTest(code=code, output=output):
                self.assertEqual(sd_gate_run.check_reading(code, output)["status"], "failure")


    def test_the_report_and_stderr_tail_are_kept_and_the_summary_stays_one_line(self) -> None:
        passed = '{"status": "pass", "checks": [{"name": "check", "status": "pass", "stdout": "ok"}]}'
        reading = sd_gate_run.check_reading(0, passed, "e" * 5000)
        self.assertEqual(reading["report"]["checks"][0]["stdout"], "ok")
        self.assertEqual(len(reading["stderr"]), sd_gate_run.STDERR_TAIL_CHARS)
        self.assertEqual(reading["summary"], "sd-check pass (check pass)")
        self.assertIsNone(sd_gate_run.check_reading(0, "not json")["report"])


class Post(unittest.TestCase):
    HEAD = "a" * 40

    def test_success_is_posted_to_the_checked_head_under_the_context(self) -> None:
        api = Recorder()
        sd_local_gate.post_gate_status(api, self.HEAD, {"head": self.HEAD, "status": "success", "summary": "sd-check pass"},
                                       "0123456789ab")
        [(path, body)] = api.posts
        self.assertEqual(path, f"repos/o/r/statuses/{self.HEAD}")
        self.assertEqual((body["state"], body["context"]), ("success", "sd/local-gate"))
        self.assertTrue(body["description"].startswith(f"{self.HEAD[:12]} inputs 0123456789ab: "))
        self.assertLessEqual(len(body["description"]), 140)

    def test_a_result_for_another_sha_is_refused_and_nothing_is_posted(self) -> None:
        api = Recorder()
        with self.assertRaisesRegex(Refusal, "no status is posted for a commit that was not checked"):
            sd_local_gate.post_gate_status(api, self.HEAD, {"head": "b" * 40, "status": "success"}, "0" * 12)
        self.assertEqual(api.posts, [])

    def test_a_failure_posts_failure(self) -> None:
        api = Recorder()
        sd_local_gate.post_gate_status(api, self.HEAD, {"head": self.HEAD, "status": "failure", "summary": "x" * 300},
                                       "0" * 12)
        self.assertEqual(api.posts[0][1]["state"], "failure")
        self.assertEqual(len(api.posts[0][1]["description"]), 140)


class Gate(Repository):
    """Every merge attempt runs `sd-check` and posts a fresh status; nothing is reused."""

    def test_a_prior_matching_success_at_the_head_still_runs_the_check(self) -> None:
        head = self.commit("check:\n\t@false\n")
        inputs = sd_local_gate.gate_inputs(self.root, head)
        api = Recorder([{"context": "sd/local-gate", "state": "success", "sha": head, "creator": {"login": "Me"},
                         "description": f"{head[:12]} inputs {inputs}: sd-check pass (check pass)"}])
        result = sd_local_gate.local_gate(api, self.root, head)
        self.assertEqual((result["status"], [body["state"] for _, body in api.posts]), ("failure", ["failure"]))

    def test_a_worktree_fault_is_a_retryable_refusal_and_posts_nothing(self) -> None:
        """`sd_gate_run` raises `GateError`; the merge lane reads it as a runtime refusal, as before the split."""
        head = self.commit("check:\n\t@echo ok\n")
        api = Recorder()
        with mock.patch.object(sd_gate_run, "gate_git", side_effect=sd_gate_run.GateError("worktree refused")):
            with self.assertRaisesRegex(Refusal, "worktree refused") as caught:
                sd_local_gate.local_gate(api, self.root, head)
        self.assertEqual((caught.exception.workflow["blocker"]["code"], api.posts), ("command_failed", []))

    def test_each_attempt_posts_its_own_status_carrying_the_inputs_digest(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        api = Recorder()
        sd_local_gate.local_gate(api, self.root, head)
        sd_local_gate.local_gate(api, self.root, head)
        inputs = sd_local_gate.gate_inputs(self.root, head)
        self.assertEqual([body["state"] for _, body in api.posts], ["success", "success"])
        self.assertTrue(api.posts[1][1]["description"].startswith(f"{head[:12]} inputs {inputs}: "))

    def test_the_digest_follows_the_local_block(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        before = sd_local_gate.gate_inputs(self.root, head)
        (self.root / "CLAUDE.local.md").write_text("check: make other\n", encoding="utf-8")
        self.assertNotEqual(sd_local_gate.gate_inputs(self.root, head), before)


class ReceiptFixture(Repository):
    """A workflow database and a check that counts its real runs."""

    def setUp(self) -> None:
        super().setUp()
        from sd_db import initialise

        self.database = self.root.parent / "sd.db"
        initialise(self.database)
        self.counter = self.root.parent / "runs"

    def counted(self, recipe: str = "true") -> str:
        """A check that appends a line outside the tree each time it really runs."""
        return self.commit(f"check:\n\t@echo run >> {self.counter}; {recipe}\n")

    def runs(self) -> int:
        return len(self.counter.read_text().splitlines()) if self.counter.exists() else 0

    def gate(self, head: str, **kwargs) -> dict:
        return sd_gate_run.check_in_worktree(self.root, head, database=self.database, **kwargs)


class Receipts(ReceiptFixture):
    """One passing gate per head (sd:2041, sd:1912): a matching receipt answers instead of a second run."""

    def test_a_pass_leaves_a_receipt_the_next_run_at_that_head_reuses(self) -> None:
        head = self.counted()
        first, second = self.gate(head), self.gate(head)
        self.assertEqual((first["status"], "reused" in first, second["status"]), ("success", False, "success"))
        self.assertEqual(self.runs(), 1)
        self.assertEqual(second["head"], head)
        self.assertEqual(second["summary"], "sd-check pass (check pass) (reused)")
        self.assertEqual(second["reused"]["revision"], first["receipt_revision"])

    def test_a_failure_leaves_no_receipt(self) -> None:
        head = self.counted("false")
        self.assertEqual([self.gate(head)["status"] for _ in range(2)], ["failure", "failure"])
        self.assertEqual(self.runs(), 2)

    def test_only_a_success_is_recorded_or_read(self) -> None:
        """Both halves refuse a failure: `record_pass` raises, and a failing row is never a receipt."""
        key = sd_gate_receipts.receipt_key(self.root, "a" * 40)
        with self.assertRaisesRegex(ValueError, "only a passing gate run"):
            sd_gate_receipts.record_pass(self.database, key, {"head": "a" * 40}, {"status": "failure"})
        self.assertIsNone(sd_gate_receipts.lookup(self.database, key, {"head": "a" * 40}))

    def test_another_head_runs_its_own_check(self) -> None:
        first = self.counted()
        self.gate(first)
        second = self.counted("true # another commit")
        self.assertNotIn("reused", self.gate(second))
        self.assertEqual(self.runs(), 2)

    def test_each_head_keeps_its_own_receipt(self) -> None:
        """A second head's pass does not replace the first head's: the key names the head."""
        first = self.counted()
        second = self.counted("true # another commit")
        self.gate(first)
        self.gate(second)
        self.assertIn("reused", self.gate(first))
        self.assertEqual(self.runs(), 2)

    def test_changed_gate_inputs_run_the_check_again(self) -> None:
        """A pack upgrade or a new `CLAUDE.local.md` changes `gate_inputs`, so the receipt no longer binds."""
        head = self.counted()
        self.gate(head)
        (self.root / "CLAUDE.local.md").write_text("an operator note\n", encoding="utf-8")
        self.assertNotIn("reused", self.gate(head))
        with mock.patch.object(sd_gate_run, "gate_inputs", return_value="0" * 12):
            self.assertNotIn("reused", self.gate(head))
        self.assertEqual(self.runs(), 3)

    def test_a_different_path_runs_the_check_again(self) -> None:
        head = self.counted()
        self.gate(head)
        with mock.patch.dict(os.environ, {"PATH": os.environ["PATH"] + os.pathsep + str(self.root.parent)}):
            self.assertNotIn("reused", self.gate(head))
        self.assertEqual(self.runs(), 2)

    def test_a_changed_forwarded_variable_runs_the_check_again(self) -> None:
        """The gate forwards the environment whole, so the receipt binds it whole.

        Prepare with a `MAKEFLAGS` that makes the check pass must not leave a
        receipt that a merge without it reuses: there the real check fails.
        """
        head = self.commit(f'check:\n\t@echo run >> {self.counter}; test "$(MODE)" = ok\n')
        with mock.patch.dict(os.environ, {"MAKEFLAGS": "MODE=ok"}):
            self.assertEqual(self.gate(head)["status"], "success")
        with mock.patch.dict(os.environ):
            os.environ.pop("MAKEFLAGS", None)
            merged = self.gate(head)
        self.assertEqual((merged["status"], "reused" in merged, self.runs()), ("failure", False, 2))

    def test_a_receipt_older_than_the_window_is_not_reused(self) -> None:
        """The window is one prepare-to-merge handoff: 30 minutes, not hours.

        Inputs outside the repository are not bound, so the window is what
        limits a change there; 31 minutes after the pass, the check runs.
        """
        head = self.counted()
        self.gate(head)
        now = time.time()
        with mock.patch.object(sd_gate_receipts.time, "time", return_value=now + 29 * 60):
            self.assertIn("reused", self.gate(head))
        with mock.patch.object(sd_gate_receipts.time, "time", return_value=now + 31 * 60):
            self.assertNotIn("reused", self.gate(head))
        self.assertEqual(self.runs(), 2)
        self.assertEqual(sd_gate_receipts.REUSE_WINDOW_SECONDS, 30 * 60)

    def test_without_a_database_nothing_is_read_or_written(self) -> None:
        head = self.counted()
        self.gate(head)
        self.assertNotIn("reused", sd_gate_run.check_in_worktree(self.root, head))
        self.assertEqual(self.runs(), 2)

    def test_the_merge_gate_posts_a_reused_pass_and_says_so(self) -> None:
        head = self.counted()
        self.gate(head)
        api = Recorder()
        result = sd_local_gate.local_gate(api, self.root, head, database=self.database)
        self.assertEqual((result["status"], self.runs()), ("success", 1))
        [(_, body)] = api.posts
        self.assertEqual(body["state"], "success")
        self.assertTrue(body["description"].endswith("sd-check pass (check pass) (reused)"), body["description"])

    def test_the_merge_gate_records_no_receipt(self) -> None:
        """Only prepare's pass is a receipt; a merge gate's pass does not serve a later gate."""
        head = self.counted()
        for _ in range(2):
            self.assertNotIn("reused", sd_local_gate.local_gate(Recorder(), self.root, head, database=self.database))
        self.assertEqual(self.runs(), 2)

    def test_a_receipt_for_another_repository_at_the_same_head_is_not_read(self) -> None:
        head = self.counted()
        self.assertNotEqual(sd_gate_receipts.receipt_key(self.root, head),
                            sd_gate_receipts.receipt_key(self.root.parent, head))


class MergeReuse(ReceiptFixture):
    """`sd-ship merge` posts `sd/local-gate` from prepare's tree receipt, and says why when it cannot (sd:2602).

    Prepare's gate leaves the receipt; the merge gate (`local_gate`, which
    records none) reads it under the same key and window. A run in full keeps
    `reuse_miss`, so a merge that should have reused names what stopped it.
    """

    def declare(self, declared: bool = True) -> str:
        """A branch off `main` whose tree declares the tree key; `origin/main` is the base."""
        self.counted()
        if declared:
            (self.root / ".github").mkdir()
            (self.root / ".github" / "sd-gate-reuse.json").write_text(json.dumps(
                {"schema_version": 1, "key": "tree", "reason": "the check reads no commit history"}), encoding="utf-8")
            git(self.root, "add", "-A")
            git(self.root, "commit", "-q", "-m", "declare")
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.root, "checkout", "-q", "-b", "topic")
        (self.root / "src.txt").write_text("one\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "topic")
        return git(self.root, "rev-parse", "HEAD")

    def prepare(self, head: str) -> dict:
        return self.gate(head, base=sd_gate_run.base_ref("main"))

    def merge(self, head: str, api: Recorder | None = None) -> dict:
        return sd_local_gate.local_gate(api or Recorder(), self.root, head, base="main", database=self.database)

    def test_an_unchanged_tree_is_posted_from_the_receipt_with_no_run(self) -> None:
        prepared = self.declare()
        self.assertEqual(self.prepare(prepared)["status"], "success")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "attribute\n\nAuthored-with: claude/anthropic")
        head, api = git(self.root, "rev-parse", "HEAD"), Recorder()
        merged = self.merge(head, api)
        self.assertEqual((merged["status"], merged["head"], merged["reused"]["head"]), ("success", head, prepared))
        self.assertNotIn("reuse_miss", merged)
        self.assertTrue(api.posts[0][1]["description"].endswith("(reused)"), api.posts)
        self.assertEqual(self.runs(), 1)

    def test_a_changed_tree_runs_in_full_and_names_no_receipt(self) -> None:
        prepared = self.declare()
        self.prepare(prepared)
        (self.root / "src.txt").write_text("two\n", encoding="utf-8")
        git(self.root, "commit", "-q", "-am", "changed")
        merged = self.merge(git(self.root, "rev-parse", "HEAD"))
        self.assertEqual((merged["status"], "reused" in merged, self.runs()), ("success", False, 2))
        self.assertEqual(merged["reuse_miss"], {"reason": "no-receipt"})

    def test_without_the_opt_in_a_new_head_runs_in_full(self) -> None:
        self.prepare(self.declare(declared=False))
        git(self.root, "commit", "-q", "--allow-empty", "-m", "attribute")
        merged = self.merge(git(self.root, "rev-parse", "HEAD"))
        self.assertEqual((merged["status"], "reused" in merged, self.runs()), ("success", False, 2))
        self.assertEqual(merged["reuse_miss"], {"reason": "no-receipt"})

    def test_an_expired_window_runs_in_full_and_names_the_age(self) -> None:
        head = self.declare()
        self.prepare(head)
        later = time.time() + sd_gate_receipts.TREE_REUSE_WINDOW_SECONDS + 60
        with mock.patch.object(sd_gate_receipts.time, "time", return_value=later):
            merged = self.merge(head)
        self.assertEqual((merged["status"], "reused" in merged, self.runs()), ("success", False, 2))
        self.assertEqual((merged["reuse_miss"]["reason"], merged["reuse_miss"]["window_seconds"]),
                         ("expired", sd_gate_receipts.TREE_REUSE_WINDOW_SECONDS))
        self.assertGreater(merged["reuse_miss"]["age_seconds"], sd_gate_receipts.TREE_REUSE_WINDOW_SECONDS)

    def test_a_different_command_runs_in_full_and_names_the_binding_fields(self) -> None:
        """The untracked `CLAUDE.local.md` may respell `check`; the tree is equal and the command is not."""
        head = self.declare()
        self.prepare(head)
        (self.root / "CLAUDE.local.md").write_text("## sd-check\n\ncheck: make check MODE=other\n", encoding="utf-8")
        merged = self.merge(head)
        self.assertEqual(("reused" in merged, self.runs()), (False, 2))
        self.assertEqual(merged["reuse_miss"]["reason"], "binding")
        self.assertIn("inputs", merged["reuse_miss"]["fields"])

    def test_a_run_whose_binding_cannot_be_named_says_so(self) -> None:
        head = self.declare()
        self.prepare(head)
        with mock.patch.object(sd_gate_receipts, "gate_binding", return_value=None):
            merged = self.merge(head)
        self.assertEqual((merged["reuse_miss"], self.runs()), ({"reason": "unbound"}, 2))

    def test_a_miss_is_kept_in_the_ship_receipt_beside_the_result(self) -> None:
        """`sd-ship merge` saves `local_gate` whole, so the miss reaches `sd-ship observe` with no new field."""
        head = self.declare()
        with mock.patch.dict(os.environ, {"MAKEFLAGS": "-s"}):
            self.prepare(head)
        merged = self.merge(head)
        self.assertEqual(merged["reuse_miss"], {"reason": "binding", "fields": ["environment_sha256"]})
        self.assertEqual(json.loads(json.dumps(merged))["reuse_miss"], merged["reuse_miss"])


class FnmShells(ReceiptFixture):
    """fnm gives every shell its own folder (operator ruling, 2026-10-04, sd:2602).

    `FNM_MULTISHELL_PATH` names `fnm_multishells/<pid>_<ms>`, a symlink to the
    node version in use, and `$FNM_MULTISHELL_PATH/bin` leads `PATH`. Two
    shells on one node differed in both, so a builder's receipt never bound
    the lane's prepare. The gate drops the variable and resolves each `PATH`
    entry; a different real node still differs.
    """

    def setUp(self) -> None:
        super().setUp()
        self.fnm = self.root.parent / "fnm"
        for version in ("v20", "v22"):
            (self.fnm / "node-versions" / version / "bin").mkdir(parents=True)
            node = self.fnm / "node-versions" / version / "bin" / "node"
            node.write_text(f"#!/bin/sh\necho {version}\n", encoding="utf-8")
            node.chmod(0o755)
        (self.fnm / "multishells").mkdir()

    def shell(self, name: str, version: str = "v20") -> dict[str, str]:
        """The environment of one shell on `version`, through its own multishell folder."""
        folder = self.fnm / "multishells" / name
        folder.symlink_to(self.fnm / "node-versions" / version)
        return {**os.environ, "FNM_MULTISHELL_PATH": str(folder),
                "PATH": os.pathsep.join([str(folder / "bin"), os.environ["PATH"]])}

    def node_check(self) -> str:
        return self.counted("node")

    def merge(self, head: str, environ: dict[str, str]) -> dict:
        return sd_gate_run.check_in_worktree(self.root, head, database=self.database, environ=environ, record=False)

    def test_two_shells_on_the_same_node_bind_one_receipt(self) -> None:
        head = self.node_check()
        self.assertEqual(self.gate(head, environ=self.shell("1739_1")).get("status"), "success")
        merged = self.merge(head, self.shell("2201_2"))
        self.assertEqual(("reused" in merged, merged.get("reuse_miss"), self.runs()), (True, None, 1))

    def test_a_different_real_node_still_runs_again(self) -> None:
        head = self.node_check()
        self.gate(head, environ=self.shell("1739_1"))
        merged = self.merge(head, self.shell("2201_2", version="v22"))
        self.assertEqual(("reused" in merged, merged["reuse_miss"]["reason"], self.runs()), (False, "binding", 2))

    def test_a_path_entry_through_a_shell_folder_binds_as_the_real_folder(self) -> None:
        head = self.node_check()
        real = {**os.environ, "PATH": os.pathsep.join([str(self.fnm / "node-versions" / "v20" / "bin"), os.environ["PATH"]])}
        self.gate(head, environ=real)
        through = self.shell("2201_2")
        del through["FNM_MULTISHELL_PATH"]
        self.assertIn("reused", self.merge(head, through))
        self.assertEqual(self.runs(), 1)


class DocsScopeGate(Repository):
    """The merge gate passes the base branch, so a declared docs-only change runs the docs command (sd:2072)."""

    def test_a_docs_only_change_posts_docs_only(self) -> None:
        (self.root / ".github").mkdir()
        (self.root / ".github" / "sd-check-scope.json").write_text(
            '{"schema_version": 1, "docs_paths": ["docs/**"], "docs_command": ["true"]}', encoding="utf-8")
        self.commit("check:\n\t@false\n")
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("a\n", encoding="utf-8")
        git(self.root, "add", "docs")
        git(self.root, "commit", "-q", "-m", "docs")
        head = git(self.root, "rev-parse", "HEAD")
        api = Recorder()
        result = sd_local_gate.local_gate(api, self.root, head, base="main")
        self.assertEqual((result["status"], result["summary"]), ("success", "sd-check pass (docs-only)"))
        self.assertTrue(api.posts[0][1]["description"].endswith(": sd-check pass (docs-only)"))
        without = sd_local_gate.local_gate(Recorder(), self.root, head)
        self.assertEqual(without["status"], "failure")


class PostHead(Repository):
    """`sd gate post --head SHA` (sd:1989): the merge gate's run and post, for a repository's own merge path.

    A repository that merges by its own automation (a Dependabot merge, a
    daily script) gets no `sd/local-gate` from `sd-ship merge`, so its
    required check never reports and every merge waits.
    """

    def test_the_named_commit_is_checked_and_posted_at_its_full_sha(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        self.commit("check:\n\t@false\n")
        api = Recorder()
        result = sd_local_gate.post_head(self.root, head[:10], api=api)
        self.assertEqual((result["head"], result["status"]), (head, "success"))
        [(path, body)] = api.posts
        self.assertEqual((path, body["context"], body["state"]), (f"repos/o/r/statuses/{head}", "sd/local-gate", "success"))

    def test_a_failing_check_posts_failure(self) -> None:
        head = self.commit("check:\n\t@false\n")
        api = Recorder()
        self.assertEqual(sd_local_gate.post_head(self.root, head, api=api)["status"], "failure")
        self.assertEqual(api.posts[0][1]["state"], "failure")

    def test_a_name_that_is_no_commit_is_refused_and_nothing_is_posted(self) -> None:
        self.commit("check:\n\t@echo ok\n")
        api = Recorder()
        with self.assertRaisesRegex(Refusal, "names no commit in this checkout"):
            sd_local_gate.post_head(self.root, "f" * 40, api=api)
        self.assertEqual(api.posts, [])

    def docs_only_head(self) -> str:
        """A docs commit on top of a head whose full check fails, under a declared docs-only scope."""
        (self.root / ".github").mkdir()
        (self.root / ".github" / "sd-check-scope.json").write_text(
            '{"schema_version": 1, "docs_paths": ["docs/**"], "docs_command": ["true"]}', encoding="utf-8")
        self.commit("check:\n\t@false\n")
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("a\n", encoding="utf-8")
        git(self.root, "add", "docs")
        git(self.root, "commit", "-q", "-m", "docs")
        return git(self.root, "rev-parse", "HEAD")

    def test_without_a_base_every_check_runs(self) -> None:
        """No --base: the PR's target is unknown, so no docs-only scope is guessed from origin/HEAD.

        A head bound for a release branch can carry code main already has plus
        a docs commit; against main it reads as docs-only, and its success
        would satisfy the release branch's required check unchecked.
        """
        result = sd_local_gate.post_head(self.root, self.docs_only_head(), api=Recorder())
        self.assertEqual(result["status"], "failure")

    def test_a_named_base_applies_the_docs_only_scope(self) -> None:
        """A declared docs-only scope applies as it does in the merge gate, against the named base."""
        result = sd_local_gate.post_head(self.root, self.docs_only_head(), base="main", api=Recorder())
        self.assertEqual((result["status"], result["summary"]), ("success", "sd-check pass (docs-only)"))

    def test_a_base_the_checkout_has_not_fetched_is_refused_and_nothing_is_posted(self) -> None:
        """`sd-check --base` with a missing ref fails, and that failure would be posted as the gate's."""
        head = self.commit("check:\n\t@echo ok\n")
        api = Recorder()
        with self.assertRaisesRegex(Refusal, "refs/remotes/origin/trunk"):
            sd_local_gate.post_head(self.root, head, base="trunk", api=api)
        self.assertEqual(api.posts, [])


class PostCommand(Repository):
    """`sd gate post` end to end, with a recording `gh` on `PATH` standing in for GitHub."""

    def sd(self, *args: str) -> subprocess.CompletedProcess:
        bindir = self.root.parent / "fakebin"
        bindir.mkdir(exist_ok=True)
        self.log = self.root.parent / "gh.log"
        fake = bindir / "gh"
        fake.write_text(
            f"#!{sys.executable}\nimport json, sys\n"
            f"open({str(self.log)!r}, 'a').write(json.dumps([sys.argv[1:], sys.stdin.read()]) + '\\n')\n"
            "print(json.dumps({'state': 'success'}))\n", encoding="utf-8")
        fake.chmod(0o755)
        env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ.get("PATH", ""))
        return subprocess.run([sys.executable, str(REPO_ROOT / "bin" / "sd"), "gate", "post", *args],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=600)

    def test_a_pass_is_posted_and_printed_as_json(self) -> None:
        git(self.root, "remote", "add", "origin", "https://github.com/o/r.git")
        head = self.commit("check:\n\t@echo ok\n")
        done = self.sd("--head", head)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["status"], "success")
        [(argv, body)] = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(argv[:4], ["api", f"repos/o/r/statuses/{head}", "--method", "POST"])
        self.assertEqual(json.loads(body)["context"], "sd/local-gate")

    def test_a_failure_is_posted_and_exits_1(self) -> None:
        git(self.root, "remote", "add", "origin", "https://github.com/o/r.git")
        head = self.commit("check:\n\t@false\n")
        done = self.sd("--head", head)
        self.assertEqual((done.returncode, json.loads(done.stdout)["status"]), (1, "failure"))

    def test_a_refusal_prints_no_json_and_posts_nothing(self) -> None:
        git(self.root, "remote", "add", "origin", "https://github.com/o/r.git")
        self.commit("check:\n\t@echo ok\n")
        done = self.sd("--head", "f" * 40)
        self.assertEqual((done.returncode, done.stdout), (1, ""))
        self.assertIn("names no commit in this checkout", done.stderr)
        self.assertFalse(self.log.exists())


class CiMode(unittest.TestCase):
    """`sd_lib.repo_ci` answers `github` on every doubt, so ci=github is unchanged."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = pathlib.Path(tmp.name).resolve()
        from sd_db import connect, initialise, upsert_repo

        self.database = self.home / ".local/share/sd/sd.db"
        initialise(self.database)
        self.connection = connect(self.database)
        self.addCleanup(self.connection.close)
        self.root = self.home / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        upsert_repo(self.connection, str(self.root), remote=None)

    def columns(self) -> set[str]:
        return {row[1] for row in self.connection.execute("PRAGMA table_info(repo)")}

    def test_a_library_without_the_reader_answers_github(self) -> None:
        import sd_db.repos

        # A schema-15 database: the pinned library creates repo.ci, so drop it.
        if "ci" in self.columns():
            self.connection.execute("ALTER TABLE repo DROP COLUMN ci")
        self.assertNotIn("ci", self.columns())
        with mock.patch.object(sd_db.repos, "repo_ci", None, create=True):
            self.assertEqual(sd_lib.repo_ci(self.connection, self.root), "github")

    def test_the_librarys_local_answer_is_returned(self) -> None:
        import sd_db.repos

        with mock.patch.object(sd_db.repos, "repo_ci", lambda connection, path: "local", create=True):
            self.assertEqual(sd_lib.repo_ci(self.connection, self.root), "local")

    def test_without_the_reader_the_column_is_read_when_present(self) -> None:
        import sd_db.repos

        if "ci" not in self.columns():  # a library older than schema 16
            self.connection.execute("ALTER TABLE repo ADD COLUMN ci TEXT NOT NULL DEFAULT 'github'")
        self.connection.execute("UPDATE repo SET ci = 'local'")
        with mock.patch.object(sd_db.repos, "repo_ci", None, create=True):
            self.assertEqual(sd_lib.repo_ci(self.connection, self.root), "local")

    def test_an_unknown_value_or_a_failing_read_answers_github(self) -> None:
        import sd_db.repos

        def broken(connection, path):
            raise RuntimeError("no such column: ci")

        for reader in (lambda connection, path: "sometimes", broken):
            with self.subTest(reader=reader), mock.patch.object(sd_db.repos, "repo_ci", reader, create=True):
                self.assertEqual(sd_lib.repo_ci(self.connection, self.root), "github")

    def test_ci_mode_with_no_database_answers_github(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": str(self.home / "elsewhere")}):
            self.assertEqual(sd_lib.ci_mode(self.root), "github")


if __name__ == "__main__":
    unittest.main()
