"""The local CI gate (sd:1843): `sd-check` at the exact head, posted as `sd/local-gate`.

Real git and a real `sd-check` child against a throwaway repository; the
GitHub side is a recorder, so nothing leaves the machine.
"""

from __future__ import annotations

import contextlib
import fcntl
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_gate_cache  # noqa: E402
import sd_gate_receipts  # noqa: E402
import sd_gate_run  # noqa: E402
import sd_gate_slots  # noqa: E402
import sd_lib  # noqa: E402
import sd_local_gate  # noqa: E402
from sd_ship_remote import Refusal  # noqa: E402

BLOCK_START, BLOCK_END = sd_lib.LOCAL_BLOCK_START, sd_lib.LOCAL_BLOCK_END


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
        # sd:2735: a fixture gate run outside `sd gate check` must not join the machine's real gate queue.
        state = {"SD_GATE_SLOTS_DIR": str(self.root.parent / "slots"), "XDG_STATE_HOME": str(self.root.parent / "state")}
        patch = mock.patch.dict(os.environ, state)
        patch.start()
        self.addCleanup(patch.stop)
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
    def test_a_fixture_gate_queues_in_its_own_folder_not_the_machines(self) -> None:
        """sd:2735: run directly, this suite's gates took and waited on the real slots under `~/.local/state`."""
        head = self.commit("check:\n\t@echo ok\n")
        with mock.patch.dict(os.environ, {"SD_GATE_LOAD_MAX": "0", "SD_GATE_SETTLE_SECONDS": "0"}):
            for name in ("SD_GATE_SLOTS", "CI", "GITHUB_ACTIONS"):  # each of these takes no slot at all
                os.environ.pop(name, None)
            self.assertEqual(sd_gate_run.check_in_worktree(self.root, head)["status"], "success")
        self.assertTrue((self.root.parent / "slots").is_dir())

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

    def test_a_path_entry_that_names_no_folder_is_dropped(self) -> None:
        """sd:2772. fnm's `cd` hook prepends a per-shell link, here to no installation, so
        `cd <checkout> && sd gate check` bound another environment than `sd-review -C <checkout>`
        and the review ran the whole check again. A folder that does not exist selects no tool."""
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        shell = pathlib.Path(outside.name) / "fnm_multishells" / "3315_1791163917161"
        shell.parent.mkdir()
        shell.symlink_to(pathlib.Path(outside.name) / "no-installation")
        plain = {"PATH": "/usr/bin", "HOME": "/h"}
        after_cd = {**plain, "PATH": os.pathsep.join([str(shell / "bin"), "/usr/bin"])}
        self.assertEqual(sd_gate_run.gate_environment(self.root, after_cd), sd_gate_run.gate_environment(self.root, plain))

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

    def test_a_slot_bound_reaches_sd_check_and_widens_the_childs_limit(self) -> None:
        """sd:2607: the queue for a slot has its own bound, so the child may live for both."""
        head = self.commit("check:\n\t@echo ok\n")
        seen: list[tuple[list[str], int]] = []
        def run(argv: list[str], env: dict[str, str], cwd: pathlib.Path, limit: int) -> tuple[int | None, str, str]:
            seen.append((argv, limit))
            return sd_gate_run.run_child(argv, env, cwd, limit)
        bounded_result = sd_gate_run.check_in_worktree(self.root, head, timeout=60, slot_timeout=300, run=run)
        self.assertEqual(bounded_result["report"]["gate_slot"]["bound_seconds"], 300)
        sd_gate_run.check_in_worktree(self.root, head, timeout=60, run=run)
        (bounded, wide), (plain, narrow) = seen
        self.assertEqual(bounded[bounded.index("--slot-timeout") + 1], "300")
        self.assertEqual(wide, 60 + 300 + sd_gate_run.REPORT_GRACE_SECONDS)
        self.assertNotIn("--slot-timeout", plain)
        self.assertEqual(narrow, 60 + sd_gate_run.REPORT_GRACE_SECONDS)


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

    def test_a_failed_precheck_is_named_first(self) -> None:
        """sd:2604: the checks after a failed precheck did not run, so the summary names the precheck."""
        stopped = ('{"status": "fail", "precheck": {"name": "precheck", "status": "fail"},'
                   ' "checks": [{"name": "check", "status": "fail"}]}')
        self.assertEqual(sd_gate_run.check_reading(1, stopped)["summary"], "sd-check fail (precheck fail, check fail)")


    def test_a_failure_summary_names_the_failed_step(self) -> None:
        """sd:2608: the one line a lane log shows said `check fail` and no step."""
        failed = json.dumps({"status": "fail", "checks": [
            {"name": "check", "status": "fail", "failed_steps": ["shard tests.test_a: 0s exit=1", "make target test"]},
            {"name": "test", "status": "skipped"}, {"name": "lint", "status": "skipped"}]})
        summary = sd_gate_run.check_reading(1, failed)["summary"]
        self.assertEqual(summary, "sd-check fail (check fail: shard tests.test_a: 0s exit=1; make target test,"
                                  " test skipped, lint skipped)")
        kept = "/tmp/example/.git/sd-check-output/20261004T000000Z-1-check.log"
        many = json.dumps({"status": "fail", "checks": [
            {"name": "check", "status": "fail", "output_path": kept,
             "failed_steps": [f"shard tests.test_{n}: 0s exit=1" for n in range(30)]}]})
        steps, said = sd_gate_run.check_reading(1, many)["summary"].split(" whole output: ")
        # The steps keep a status description's bound; the path to the whole output is never cut.
        self.assertTrue(steps.startswith("sd-check fail (check fail: shard tests.test_0: 0s exit=1; "), steps)
        self.assertLessEqual(len(steps), sd_gate_run.DESCRIPTION_LIMIT)
        self.assertEqual(said, kept)


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

    def test_the_posted_description_leaves_out_the_local_output_path(self) -> None:
        """sd:2608. The summary names the file with the whole output for the
        lane log; a commit status is public and the path is a local one."""
        api = Recorder()
        summary = "sd-check fail (check fail: make target test) whole output: /tmp/example/.git/sd-check-output/run.log"
        sd_local_gate.post_gate_status(api, self.HEAD, {"head": self.HEAD, "status": "failure", "summary": summary},
                                       "0" * 12)
        self.assertEqual(api.posts[0][1]["description"],
                         f"{self.HEAD[:12]} inputs {'0' * 12}: sd-check fail (check fail: make target test)")

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

    def test_the_merge_gate_queues_on_the_slot_bound_apart_from_its_check(self) -> None:
        """sd:2611: like `sd gate check`, so a merge queued behind other gates keeps its whole check bound."""
        head = self.commit("check:\n\t@echo ok\n")
        with mock.patch.object(sd_local_gate, "check_in_worktree", wraps=sd_local_gate.check_in_worktree) as checked:
            sd_local_gate.local_gate(Recorder(), self.root, head)
        self.assertEqual(checked.call_args.kwargs["slot_timeout"], sd_lib.GATE_SLOT_SECONDS)

    def test_the_digest_follows_the_local_block(self) -> None:
        """The parsed block, not the file's bytes: notes outside it and comments in it move nothing (sd:2854)."""
        head = self.commit("check:\n\t@echo ok\n")
        before = sd_local_gate.gate_inputs(self.root, head)
        local = self.root / "CLAUDE.local.md"
        local.write_text(f"an operator note\n{BLOCK_START}\n# a comment\n\n{BLOCK_END}\n", encoding="utf-8")
        self.assertEqual(sd_local_gate.gate_inputs(self.root, head), before)
        local.write_text(f"{BLOCK_START}\ncheck: make other\n{BLOCK_END}\n", encoding="utf-8")
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

    def passing(self, during=lambda: None, mode: str = "full", argvs: list | None = None):  # type: ignore[no-untyped-def]
        """A stand-in run that calls `during` while it runs, then passes with scope `mode`; `argvs` collects its argv."""
        def run(argv, env, tree, timeout):  # type: ignore[no-untyped-def]
            during()
            (argvs if argvs is not None else []).append(argv)
            return 0, json.dumps({"status": "pass", "scope": {"mode": mode}, "checks": []}), ""
        return run


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
        (self.root / "CLAUDE.local.md").write_text(f"{BLOCK_START}\nnote: an operator note\n{BLOCK_END}\n", encoding="utf-8")
        self.assertNotIn("reused", self.gate(head))
        with mock.patch.object(sd_gate_run, "gate_inputs", return_value="0" * 12):
            self.assertNotIn("reused", self.gate(head))
        self.assertEqual(self.runs(), 3)

    def test_a_gate_in_a_linked_worktree_reads_the_main_checkouts_local_block(self) -> None:
        """sd:2859. The review reads the main checkout's `CLAUDE.local.md`; the gate read the linked worktree's
        own path, found none, and reused its receipt across an edit to the main checkout's block."""
        head = self.counted()
        linked = self.root.parent / "linked"
        git(self.root, "worktree", "add", "-q", "--detach", str(linked), head)
        gate = lambda: sd_gate_run.check_in_worktree(linked, head, database=self.database)  # noqa: E731
        self.assertEqual(gate()["status"], "success")
        (self.root / "CLAUDE.local.md").write_text(f"{BLOCK_START}\nnote: an edit at the same head\n{BLOCK_END}\n", encoding="utf-8")
        again = gate()
        self.assertNotIn("reused", again)
        self.assertEqual((again["status"], self.runs()), ("success", 2))

    def test_another_repository_records_nothing_when_the_pack_moves_mid_run(self) -> None:
        """The child may open the moved pack, so a landing mid-run drops the pass (sd:2612 review), and says so."""
        head = self.counted()
        pack = self.root.parent / "pack"
        pack.mkdir()
        (pack / "sd-x").write_text("one\n", encoding="utf-8")
        with mock.patch.object(sd_gate_run, "BIN", pack):
            result = self.gate(head, run=self.passing(lambda: (pack / "sd-x").write_text("two\n", encoding="utf-8")))
        self.assertNotIn("receipt_revision", result)
        self.assertEqual(result["receipt_skipped"], "moved during the run: inputs")

    def test_a_pass_left_unrecorded_says_what_moved(self) -> None:
        """A pass whose binding moved during the run leaves no receipt, and the result says why."""
        head = self.counted()
        result = self.gate(head, run=self.passing(mode="docs-only"))
        self.assertEqual(result["status"], "success")
        self.assertNotIn("receipt_revision", result)
        self.assertEqual(result["receipt_skipped"], "moved during the run: scope mode")

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

    def test_the_cpu_cap_reaches_the_check_and_the_receipt_binds_it(self) -> None:
        """sd:2726: a suite can pass on one test thread and fail on eight, so another cap runs the check again."""
        seen = self.root.parent / "seen"
        head = self.counted(f'echo "$$CARGO_BUILD_JOBS $$RUST_TEST_THREADS" >> {seen}')
        config = self.root.parent / "config" / "sd-ai-command-pack" / "config.json"
        config.parent.mkdir(parents=True)
        machine = {"SD_GATE_SLOTS_DIR": str(self.root.parent / "slots"), "SD_GATE_SLOT_POLL": "0.1",
                   "SD_GATE_LOAD_MAX": "0", "SD_GATE_SETTLE_SECONDS": "0", "XDG_CONFIG_HOME": str(config.parents[1])}
        with mock.patch.dict(os.environ, machine):
            # A gate running this suite hands it its own caps; a lower inherited one would win both times.
            for name in ("SD_GATE_SLOTS", "CI", "GITHUB_ACTIONS", *sd_gate_slots.CPU_VARIABLES):
                os.environ.pop(name, None)
            config.write_text(json.dumps({"config": {"sd": {"gate_slots": "1"}}}), encoding="utf-8")
            first = self.gate(head)
            config.write_text(json.dumps({"config": {"sd": {"gate_slots": "2"}}}), encoding="utf-8")
            second, third = self.gate(head), self.gate(head)
        self.assertEqual([first["status"], second["status"], "reused" in second, "reused" in third, self.runs()],
                         ["success", "success", False, True, 2])
        whole, half = (str(sd_gate_slots.cpu_share(slots)) for slots in (1, 2))  # they differ on two or more cores
        self.assertEqual(seen.read_text().splitlines(), [f"{whole} {whole}", f"{half} {half}"])
        with mock.patch.dict(os.environ, machine):
            for name in ("SD_GATE_SLOTS", "CI", "GITHUB_ACTIONS", *sd_gate_slots.CPU_VARIABLES):
                os.environ.pop(name, None)
            raised = self.gate(self.counted("true # another commit"), run=self.passing(
                lambda: config.write_text(json.dumps({"config": {"sd": {"gate_slots": "4"}}}), encoding="utf-8")))
        self.assertEqual(raised["receipt_skipped"], "moved during the run: threads")

    def test_the_binding_keeps_the_caller_thread_counts_the_precheck_runs_on(self) -> None:
        """sd:2726 review: the precheck gets the caller's values, so 16 and 32 bind apart though both cap to 8."""
        head = self.counted()
        with mock.patch.object(os, "cpu_count", return_value=16):
            one, two = (sd_gate_receipts.gate_binding(self.root, head, "0" * 12, None, {
                "SD_GATE_SLOTS": "2", "CARGO_BUILD_JOBS": jobs, "RUST_TEST_THREADS": jobs}) for jobs in ("16", "32"))
        assert one is not None and two is not None
        self.assertEqual((one["threads"], two["threads"]), ({"CARGO_BUILD_JOBS": "8", "RUST_TEST_THREADS": "8"},) * 2)
        self.assertNotEqual(one["environment_sha256"], two["environment_sha256"])

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
        (self.root / "CLAUDE.local.md").write_text(f"{BLOCK_START}\ncheck: make check MODE=other\n{BLOCK_END}\n", encoding="utf-8")
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
        with mock.patch.dict(os.environ):  # a caller that already exports MAKEFLAGS=-s must still differ
            os.environ.pop("MAKEFLAGS", None)
            merged = self.merge(head)
        self.assertEqual(merged["reuse_miss"], {"reason": "binding", "fields": ["environment_sha256"]})
        self.assertEqual(json.loads(json.dumps(merged))["reuse_miss"], merged["reuse_miss"])

    def test_a_session_with_another_home_still_misses_on_the_environment(self) -> None:
        """C-17 (sd:2704): the offload view leaves `HOME` out; local reuse still binds the whole environment."""
        head = self.declare()
        homes = [self.root.parent / name for name in ("one", "two")]
        for home in homes:
            home.mkdir()
        with mock.patch.dict(os.environ, {"HOME": str(homes[0])}):
            self.prepare(head)
        with mock.patch.dict(os.environ, {"HOME": str(homes[1])}):
            merged = self.merge(head)
        self.assertEqual((merged["reuse_miss"], self.runs()),
                         ({"reason": "binding", "fields": ["environment_sha256"]}, 2))

    def test_a_receipt_another_machine_wrote_is_not_reused(self) -> None:
        """sd:2796 (sd:2782 L7): a satellite's own receipts land in the hub's database under the same key when
        the login and checkout path match; the binding names the machine, so the hub never reuses one."""
        head = self.declare()
        with mock.patch.object(sd_gate_receipts.socket, "gethostname", return_value="satellite.example.test"):
            self.prepare(head)
        merged = self.merge(head)
        self.assertEqual((merged["reuse_miss"], self.runs()), ({"reason": "binding", "fields": ["machine"]}, 2))


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


class CargoBuildCache(Repository):
    """A Rust repository's gates share warm build folders instead of compiling every dependency cold (sd:2493)."""

    def setUp(self) -> None:
        super().setUp()
        self.cache = self.root.parent / "cache"
        self.seen = self.root.parent / "seen"

    def rust(self, recipe: str = 'echo "$$CARGO_TARGET_DIR" >> {seen}') -> str:
        (self.root / "Cargo.toml").write_text('[package]\nname = "fixture"\nversion = "0.1.0"\n', encoding="utf-8")
        return self.commit(f"check:\n\t@{recipe.format(seen=self.seen)}\n")

    def environ(self, **extra: str) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items()
               if key not in ("CARGO_TARGET_DIR", sd_gate_cache.CARGO_TARGETS_VARIABLE)}
        return {**env, sd_gate_cache.CACHE_VARIABLE: str(self.cache), **extra}

    def folders(self) -> list[str]:
        return self.seen.read_text(encoding="utf-8").splitlines()

    def test_two_gates_of_one_repository_build_into_the_same_folder_outside_the_worktree(self) -> None:
        head = self.rust()
        for _ in range(2):
            result = sd_gate_run.check_in_worktree(self.root, head, environ=self.environ())
            self.assertEqual(result["status"], "success", result)
        first, second = self.folders()
        self.assertEqual(first, second)
        self.assertTrue(pathlib.Path(first).is_relative_to(self.cache), first)

    def test_gates_that_run_at_once_never_share_a_folder(self) -> None:
        """A shared folder is safe in sequence only: nextest runs binaries after cargo's lock is released,
        so a second gate's build could replace them mid-run. A held folder is skipped; past the pool, cold."""
        self.rust()
        env = self.environ()
        with sd_gate_cache.cargo_target(self.root, self.root, env) as first, \
                sd_gate_cache.cargo_target(self.root, self.root, env) as second, \
                sd_gate_cache.cargo_target(self.root, self.root, env) as third:
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertNotEqual(first, second)
            self.assertIsNone(third, f"the default pool is {sd_gate_cache.DEFAULT_CARGO_TARGETS}")
        with sd_gate_cache.cargo_target(self.root, self.root, env) as again:
            self.assertEqual(again, first, "a released folder is the first one taken again")

    def test_a_warm_folder_builds_without_incremental_state(self) -> None:
        """Each gate's worktree is new, so incremental sessions never pay off; measured on a Rust repository
        on macOS, they and their object files grew a warm folder by about 4 GB a gate, against 0.26 GB without."""
        self.rust()
        with sd_gate_cache.cargo_environment(self.root, self.root, self.environ(CARGO_INCREMENTAL="1")) as warm:
            self.assertEqual(warm["CARGO_INCREMENTAL"], "0")
        cold = self.environ(CARGO_INCREMENTAL="1", **{sd_gate_cache.CARGO_TARGETS_VARIABLE: "0"})
        with sd_gate_cache.cargo_environment(self.root, self.root, cold) as child:
            self.assertEqual(child["CARGO_INCREMENTAL"], "1", "a cold build in the worktree runs as it always did")

    def test_another_repository_gets_its_own_folder(self) -> None:
        self.rust()
        other = self.root.parent / "other"
        other.mkdir()
        git(other, "init", "-q", "-b", "main")
        (other / "Cargo.toml").write_text("", encoding="utf-8")
        git(other, "add", "Cargo.toml")
        env = self.environ()
        with sd_gate_cache.cargo_target(self.root, self.root, env) as mine, \
                sd_gate_cache.cargo_target(other, other, env) as theirs:
            self.assertNotEqual(pathlib.Path(mine).parent, pathlib.Path(theirs).parent)

    def test_the_operators_cargo_target_dir_never_reaches_the_check(self) -> None:
        """The gate borrows nothing from the operator: with the cache off it builds in its own worktree."""
        head = self.rust('test -z "$$CARGO_TARGET_DIR"')
        environ = self.environ(CARGO_TARGET_DIR=str(self.root / "target"), **{sd_gate_cache.CARGO_TARGETS_VARIABLE: "0"})
        self.assertEqual(sd_gate_run.check_in_worktree(self.root, head, environ=environ)["status"], "success")
        self.assertFalse(self.cache.exists())
        self.assertNotIn("CARGO_TARGET_DIR", sd_gate_run.gate_environment(self.root, environ))

    def test_a_repository_without_cargo_takes_no_folder(self) -> None:
        head = self.commit('check:\n\t@test -z "$$CARGO_TARGET_DIR"\n')
        environ = self.environ(CARGO_TARGET_DIR="/operator/target")
        self.assertEqual(sd_gate_run.check_in_worktree(self.root, head, environ=environ)["status"], "success")
        self.assertFalse(self.cache.exists())

    def test_a_nested_cargo_workspace_counts(self) -> None:
        (self.root / "rust").mkdir()
        (self.root / "rust" / "Cargo.toml").write_text("", encoding="utf-8")
        head = self.commit('check:\n\t@echo "$$CARGO_TARGET_DIR" >> ' + str(self.seen) + "\n")
        self.assertEqual(sd_gate_run.check_in_worktree(self.root, head, environ=self.environ())["status"], "success")
        self.assertTrue(pathlib.Path(self.folders()[0]).is_relative_to(self.cache))

    def test_a_pass_in_one_folder_is_reused_from_another(self) -> None:
        """The folder is a cache, not an input: which one a run took does not bind its receipt."""
        from sd_db import initialise

        database = self.root.parent / "sd.db"
        initialise(database)
        head = self.rust()
        env = self.environ()
        with sd_gate_cache.cargo_target(self.root, self.root, env):  # another gate holds the first folder
            first = sd_gate_run.check_in_worktree(self.root, head, environ=env, database=database)
        second = sd_gate_run.check_in_worktree(self.root, head, environ=env, database=database)
        self.assertEqual((first["status"], "reused" in second), ("success", True), second)
        self.assertEqual(len(self.folders()), 1)


class PackGatesItself(ReceiptFixture):
    """The pack gating itself runs and binds its own tree, not the checkout's `bin/` (sd:2613)."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = self.root / "bin"
        self.pack.mkdir()
        (self.pack / "sd-check").write_text("#!/bin/sh\n", encoding="utf-8")
        (self.root / ".github").mkdir()
        (self.root / ".github" / "sd-gate-reuse.json").write_text(json.dumps(
            {"schema_version": 1, "key": "tree", "reason": "a fixture", "tool": "tree"}), encoding="utf-8")
        self.head = self.counted()

    def land(self) -> None:
        """A pack merge lands in the checkout the gate runs from."""
        (self.pack / "sd-x").write_text(f"{time.time()}\n", encoding="utf-8")

    def test_the_pack_reuses_its_pass_after_the_checkout_moves(self) -> None:
        with mock.patch.object(sd_gate_run, "BIN", self.pack):
            self.gate(self.head, run=self.passing())
            self.land()
            self.assertIn("reused", self.gate(self.head, run=self.passing()))

    def test_the_pack_runs_its_own_sd_check(self) -> None:
        argvs: list = []
        with mock.patch.object(sd_gate_run, "BIN", self.pack):
            self.gate(self.head, run=self.passing(argvs=argvs))
        self.assertTrue(argvs[0][1].endswith("/tree/bin/sd-check"), argvs[0][1])

    def test_a_pack_landing_mid_run_still_records_for_the_pack(self) -> None:
        with mock.patch.object(sd_gate_run, "BIN", self.pack):
            result = self.gate(self.head, run=self.passing(self.land))
        self.assertIn("receipt_revision", result)

    def test_a_foreign_declaration_still_binds_the_checkout(self) -> None:
        """Another repository's `"tool": "tree"` is ignored: its gate runs and binds the checkout's pack."""
        foreign = self.root.parent / "pack"
        foreign.mkdir()
        (foreign / "sd-check").write_text("#!/bin/sh\n", encoding="utf-8")
        argvs: list = []
        with mock.patch.object(sd_gate_run, "BIN", foreign):
            self.gate(self.head, run=self.passing(argvs=argvs))
            (foreign / "sd-check").write_text("#!/bin/sh\n# landed\n", encoding="utf-8")
            self.assertNotIn("reused", self.gate(self.head, run=self.passing(argvs=argvs)))
        self.assertEqual(argvs[0][1], str(foreign / "sd-check"))


class PackImportClosure(ReceiptFixture):
    """sd:2722: a repository whose reviewed tree declares that its check runs no pack command but `sd-check`
    binds the pack files `sd-check` imports, not every `bin/` file, so a pack landing that leaves them alone
    does not void a receipt still in flight. Without the declaration every file binds: a check may run
    `sd-docs-lint` from `PATH`, and the binding names only the command it starts."""

    FILES = {"sd-check": "import sd_a\n",
             "sd_a.py": "def later():\n    import sd_b\n    return sd_lib.sibling('sd_c', 'sd-c')\n",
             "sd_b.py": "", "sd-c": "", "sd_lane.py": "", "sd-ship": "",
             "sd_gate_run.py": "import sd_gate_cache\n", "sd_gate_cache.py": ""}
    EVERY = ["sd-c", "sd-check", "sd-ship", "sd_a.py", "sd_b.py", "sd_gate_cache.py", "sd_gate_run.py", "sd_lane.py"]

    def setUp(self) -> None:
        super().setUp()
        self.pack = self.root.parent / "pack"
        self.pack.mkdir()
        for name, text in self.FILES.items():
            (self.pack / name).write_text(text, encoding="utf-8")
        self.undeclared = self.counted()
        self.head = self.declare({"pack": "sd-check"})

    def declare(self, fields: dict) -> str:
        (self.root / ".github").mkdir(exist_ok=True)
        (self.root / ".github" / "sd-gate-reuse.json").write_text(json.dumps(
            {"schema_version": 1, "key": "tree", "reason": "a fixture", **fields}), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "declare")
        return git(self.root, "rev-parse", "HEAD")

    def landed_outside(self, head: str) -> dict:
        """The gate at `head`, again after a landing outside the closure."""
        with mock.patch.object(sd_gate_run, "BIN", self.pack):
            self.gate(head, run=self.passing())
            for name in ("sd_lane.py", "sd-ship"):
                with (self.pack / name).open("a", encoding="utf-8") as stream:
                    stream.write("# landed\n")
            return self.gate(head, run=self.passing())

    def test_the_closure_follows_nested_imports_and_siblings(self) -> None:
        self.assertEqual([path.name for path in sd_gate_receipts.pack_files(self.pack, closure=True)],
                         ["sd-c", "sd-check", "sd_a.py", "sd_b.py", "sd_gate_cache.py", "sd_gate_run.py"])

    def test_a_change_to_the_gates_own_modules_runs_again(self) -> None:
        """Prepare review at 00716c92: the gate's own code sets up what the check runs under, such as
        `cargo_environment`, so `sd_gate_run` and what it imports bind beside `sd-check`'s closure."""
        with mock.patch.object(sd_gate_run, "BIN", self.pack):
            self.gate(self.head, run=self.passing())
            with (self.pack / "sd_gate_cache.py").open("a", encoding="utf-8") as stream:
                stream.write("WARM_ENVIRONMENT = {}\n")
            again = self.gate(self.head, run=self.passing())
        self.assertEqual(("reused" in again, again["reuse_miss"]), (False, {"reason": "binding", "fields": ["inputs"]}))

    def test_a_pack_landing_outside_the_closure_leaves_the_receipt_standing(self) -> None:
        self.assertIn("reused", self.landed_outside(self.head))

    def test_without_the_declaration_every_pack_file_binds(self) -> None:
        self.assertEqual([path.name for path in sd_gate_receipts.pack_files(self.pack)], self.EVERY)
        self.assertNotIn("reused", self.landed_outside(self.undeclared))

    def test_only_the_exact_field_narrows_and_the_tree_key_still_reads(self) -> None:
        self.assertTrue(sd_gate_receipts.pack_scope(self.root, self.head))
        self.assertTrue(sd_gate_receipts.keyed_by_tree(self.root))
        for fields in ({"pack": "all"}, {"pack": True}, {"schema_version": 2, "pack": "sd-check"}):
            with self.subTest(fields=fields):
                self.assertFalse(sd_gate_receipts.pack_scope(self.root, self.declare(fields)))
        self.assertFalse(sd_gate_receipts.pack_scope(self.root, self.undeclared))

    def test_a_change_inside_the_closure_runs_again(self) -> None:
        with mock.patch.object(sd_gate_run, "BIN", self.pack):
            self.gate(self.head, run=self.passing())
            for name in ("sd-check", "sd_a.py", "sd_b.py", "sd-c"):
                with self.subTest(name=name):
                    with (self.pack / name).open("a", encoding="utf-8") as stream:
                        stream.write("# landed\n")
                    self.assertNotIn("reused", self.gate(self.head, run=self.passing()))

    def test_a_closure_that_cannot_be_read_binds_every_pack_file(self) -> None:
        (self.pack / "sd_a.py").write_text("def (:\n", encoding="utf-8")
        self.assertEqual([path.name for path in sd_gate_receipts.pack_files(self.pack, closure=True)], self.EVERY)

    def test_the_real_closure_holds_sd_check_and_the_gate_and_not_the_lane(self) -> None:
        names = {path.name for path in sd_gate_receipts.pack_files(sd_gate_run.BIN, closure=True)}
        self.assertLessEqual({"sd-check", "sd_lib.py", "sd_check_receipts.py", "sd_check_scope.py", "sd_gate_slots.py",
                              "sd_gate_run.py", "sd_gate_receipts.py", "sd_gate_cache.py"}, names)
        self.assertEqual(names & {"sd-ship", "sd_lane.py"}, set())


class PackDeclaresTreeReuse(unittest.TestCase):
    """The pack keys its own gate receipts by tree (sd:2610): `make check` reads no commit history."""

    def test_the_pack_keys_its_gate_receipts_by_tree(self) -> None:
        self.assertTrue(sd_gate_receipts.keyed_by_tree(REPO_ROOT), sd_gate_receipts.REUSE_DECLARATION)

    def test_the_pack_gates_itself(self) -> None:
        """sd:2613: the pack's gate runs and binds the pack's own tree."""
        self.assertTrue(sd_gate_receipts.gates_itself(REPO_ROOT, REPO_ROOT, sd_gate_run.BIN))

    def test_the_check_lints_docs_without_history(self) -> None:
        """The declaration rests on this: without `--no-history`, docs-lint fetches and reads `git log` (sd:2606)."""
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        recipe = makefile.split("\ndocs-lint:\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("bin/sd-docs-lint --no-history", recipe)


class CacheBound(Repository):
    """The warm folders stay under a bound: the least recently used free folder goes first (sd:2598)."""

    def setUp(self) -> None:
        super().setUp()
        self.cache = self.root.parent / "cache"

    def folder(self, name: str, used: float, size: int = 1000) -> pathlib.Path:
        """A filled warm folder whose lock file says it was last taken `used` seconds after the epoch."""
        folder = self.cache / name
        folder.mkdir(parents=True)
        (folder / "build").write_bytes(b"x" * size)
        lock = folder.parent / f"{folder.name}.lock"
        lock.touch()
        os.utime(lock, (used, used))
        return folder

    def test_over_the_bound_the_least_recently_used_folder_goes_first(self) -> None:
        old, mid, new = (self.folder(f"repo-{n}/cargo-target.1", used) for n, used in (("a", 100), ("b", 200), ("c", 300)))
        pruned = sd_gate_cache.prune(self.cache, new, 2500)
        self.assertEqual([path for path, _ in pruned], [old])
        self.assertEqual((old.exists(), mid.exists(), new.exists()), (False, True, True))

    def test_a_folder_in_use_is_never_pruned(self) -> None:
        old = self.folder("repo-a/cargo-target.1", 100)
        mid = self.folder("repo-a/cargo-target.2", 200)
        new = self.folder("repo-b/cargo-target.1", 300)
        with open(old.parent / "cargo-target.1.lock", "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)  # another gate is building in it
            pruned = sd_gate_cache.prune(self.cache, new, 2500)
        self.assertEqual([path for path, _ in pruned], [mid])
        self.assertTrue(old.exists())

    def test_the_held_folder_goes_last_and_only_when_the_rest_is_not_enough(self) -> None:
        other = self.folder("repo-a/cargo-target.1", 300)
        held = self.folder("repo-b/cargo-target.1", 100, size=3000)
        pruned = sd_gate_cache.prune(self.cache, held, 2500)
        self.assertEqual([path for path, _ in pruned], [other, held])

    def test_under_the_bound_or_with_no_bound_nothing_goes(self) -> None:
        old = self.folder("repo-a/cargo-target.1", 100)
        new = self.folder("repo-b/cargo-target.1", 200)
        self.assertEqual(sd_gate_cache.prune(self.cache, new, 2000), [])
        self.assertEqual(sd_gate_cache.prune(self.cache, new, 0), [])
        self.assertTrue(old.exists())

    def test_the_bound_reads_the_variable_then_the_setting_then_the_default(self) -> None:
        gib = 1024 ** 3
        home = {"XDG_CONFIG_HOME": str(self.root.parent / "config")}
        self.assertEqual(sd_gate_cache.cache_bound(home), sd_gate_cache.DEFAULT_CACHE_GB * gib)
        self.assertEqual(sd_gate_cache.cache_bound({**home, sd_gate_cache.CACHE_GB_VARIABLE: "0.5"}), gib // 2)
        self.assertEqual(sd_gate_cache.cache_bound({**home, sd_gate_cache.CACHE_GB_VARIABLE: "0"}), 0)
        with mock.patch.object(sd_lib, "core_setting", return_value="7"):
            self.assertEqual(sd_gate_cache.cache_bound(home), 7 * gib)

    def test_the_gate_names_what_it_pruned(self) -> None:
        old = self.folder("other-0123456789ab/cargo-target.1", 100)
        (self.root / "Cargo.toml").write_text("", encoding="utf-8")
        git(self.root, "add", "Cargo.toml")
        env = {key: value for key, value in os.environ.items() if key != sd_gate_cache.CARGO_TARGETS_VARIABLE}
        env.update({sd_gate_cache.CACHE_VARIABLE: str(self.cache), sd_gate_cache.CACHE_GB_VARIABLE: "0.0000005"})
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), sd_gate_cache.cargo_target(self.root, self.root, env) as target:
            self.assertIsNotNone(target)
        self.assertFalse(old.exists())
        self.assertIn(f"sd gate: pruned {old}", errors.getvalue())


class StaleGateWorktrees(Repository):
    """sd:2739: a killed gate skips its `finally`; the next gate start removes its worktree, never a live one's."""

    def left(self, owner: str, head: str, folder: pathlib.Path | None = None) -> pathlib.Path:
        """A worktree registered as `<folder>/tree`; by default a gate's folder in the temp dir, as a killed gate leaves it."""
        if folder is None:
            folder = pathlib.Path(tempfile.mkdtemp(prefix=f"{sd_gate_cache.GATE_PREFIX}{owner}-"))
            self.addCleanup(shutil.rmtree, folder, True)
        git(self.root, "worktree", "add", "-q", "--detach", str(folder / "tree"), head)
        return folder / "tree"

    def dead(self) -> str:
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait()
        return str(gone.pid)

    def test_a_dead_gates_worktree_is_removed_at_the_next_gate_start(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        tree = self.left(self.dead(), head)
        self.assertEqual(sd_gate_run.check_in_worktree(self.root, head)["status"], "success")
        self.assertEqual((self.worktrees(), tree.exists()), (1, False))

    def test_a_live_gates_worktree_and_one_that_names_no_pid_stay(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(live.wait)
        self.addCleanup(live.kill)
        trees = [self.left(str(live.pid), head), self.left("abc", head)]
        self.assertEqual(sd_gate_run.check_in_worktree(self.root, head)["status"], "success")
        self.assertEqual((self.worktrees(), [tree.exists() for tree in trees]), (3, [True, True]))

    def test_a_like_named_checkout_outside_the_temp_dir_or_past_the_pid_range_stays(self) -> None:
        """Review round 2: the name alone selected a user's checkout, and a 24-digit pid raised `OverflowError`."""
        head = self.commit("check:\n\t@echo ok\n")
        trees = [self.left("", head, self.root.parent / f"{sd_gate_cache.GATE_PREFIX}{self.dead()}-x"),
                 self.left("9" * 24, head)]
        self.assertEqual(sd_gate_run.check_in_worktree(self.root, head)["status"], "success")
        self.assertEqual((self.worktrees(), [tree.exists() for tree in trees]), (3, [True, True]))


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
