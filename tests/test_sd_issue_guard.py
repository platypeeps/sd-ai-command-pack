"""The issue guard: a managed repository's work goes to `sd task add`, not GitHub.

The operator's repositories track work in sd, and their GitHub issues are off.
An agent that reaches for `gh issue create` or `mcp__github__issue_write`
there gets a refusal that names the tracker, rather than a 410 from GitHub or,
worse, an issue nobody reads (sd:2256).

Every test runs against a real `sd_db` under a `HOME` nothing else shares,
because the claim is about which row decides: `repo.managed`. A double would
assert that a lookup happened, not that the right repository was found.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import subprocess  # nosec B404 - fixed argv, running the hook and git
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "bin" / "sd-issue-guard"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_db  # noqa: E402 - installed into this virtualenv by `make setup`
import sd_install  # noqa: E402 - bin/ is on sys.path above

ORIGIN = "https://github.com/example/managed"


def payload(**fields: Any) -> str:
    return json.dumps({"hook_event_name": "PreToolUse", **fields})


def bash(command: str, **fields: Any) -> str:
    return payload(tool_name="Bash", tool_input={"command": command}, **fields)


def git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run(  # nosec B603 B607 - fixed argv, a scratch repository
        ["git", *args], cwd=cwd, check=True, capture_output=True)


class Fixture(unittest.TestCase):
    """One checkout, one HOME, and the hook loaded in process."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.repo = self.home / "checkout"
        (self.repo / "src").mkdir(parents=True)
        git(self.repo, "init", "-q")
        git(self.repo, "remote", "add", "origin", ORIGIN)

        patched = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patched.start()
        self.addCleanup(patched.stop)

        self.module = self.load()

    def load(self) -> Any:
        """The hook, imported from a file whose name has no `.py` suffix."""
        import importlib.util

        spec = importlib.util.spec_from_loader(
            "sd_issue_guard_under_test",
            importlib.machinery.SourceFileLoader(
                "sd_issue_guard_under_test", str(HOOK)),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def register(self, *, managed: bool) -> None:
        sd_db.initialise(home=self.home)
        connection = sd_db.connect(home=self.home)
        try:
            key = sd_db.add_repo(connection, self.repo, home=self.home)
            sd_db.writes.upsert_repo(connection, key, managed=int(managed))
            connection.commit()
        finally:
            connection.close()

    def fire(self, text: str, cwd: pathlib.Path | None = None) -> tuple[int, str]:
        env = {"HOME": str(self.home), "PWD": str(cwd or self.repo / "src")}
        out = io.StringIO()
        code = self.module.guard_call(text, env, out)
        return code, out.getvalue()

    def assert_denied(self, text: str, cwd: pathlib.Path | None = None) -> str:
        code, printed = self.fire(text, cwd)
        self.assertEqual(code, 0)
        self.assertTrue(printed, f"no decision for {text}")
        decision = json.loads(printed)["hookSpecificOutput"]
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertEqual(decision["permissionDecision"], "deny")
        return decision["permissionDecisionReason"]

    def assert_silent(self, text: str, cwd: pathlib.Path | None = None) -> None:
        code, printed = self.fire(text, cwd)
        self.assertEqual((code, printed), (0, ""), text)


class AManagedRepositoryIsDenied(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.register(managed=True)

    def test_gh_issue_create_is_denied_and_pointed_at_sd(self) -> None:
        reason = self.assert_denied(bash('gh issue create --title "x" --body y'))
        self.assertIn("sd task add", reason)

    def test_the_mcp_issue_writer_is_denied_and_pointed_at_sd(self) -> None:
        reason = self.assert_denied(payload(
            tool_name="mcp__github__issue_write",
            tool_input={"method": "create", "owner": "example", "repo": "managed",
                        "title": "x"}))
        self.assertIn("sd task add", reason)

    def test_the_spellings_an_agent_actually_uses_are_denied(self) -> None:
        for command in (
            "gh issue new --title x",
            "gh -R example/other issue create --title x",
            "gh --repo=example/other issue create",
            "cd src && gh issue create --title x",
            "git status; gh issue create",
            "GH_PAGER= gh issue create",
            "env GH_REPO=example/x /opt/homebrew/bin/gh issue create",
            "rtk gh issue create --title x",
            "true\ngh issue create --title x",
        ):
            with self.subTest(command=command):
                self.assert_denied(bash(command))

    def test_a_linked_worktree_of_the_repository_is_denied(self) -> None:
        """The row holds the main checkout; a worktree is found by its origin."""
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.test",
            "commit", "-q", "--allow-empty", "-m", "seed")
        worktree = self.tmp / "wt"
        git(self.repo, "worktree", "add", "-q", str(worktree))
        self.assert_denied(bash("gh issue create"), cwd=worktree)

    def test_other_gh_and_issue_text_is_left_alone(self) -> None:
        for command in (
            "gh issue list",
            "gh issue view 3",
            "gh pr create --title 'gh issue create'",
            'echo "gh issue create"',
            "echo gh issue create",
            "git commit -m 'never run gh issue create'",
            "ls",
        ):
            with self.subTest(command=command):
                self.assert_silent(bash(command))

    def test_another_tool_is_left_alone(self) -> None:
        self.assert_silent(payload(
            tool_name="mcp__github__issue_read",
            tool_input={"method": "get", "owner": "example", "repo": "managed"}))


class ASessionElsewhereKeepsWorking(Fixture):
    """Outside a managed repository the hook says nothing and blocks nothing."""

    def test_a_registered_but_unmanaged_repository_is_not_denied(self) -> None:
        self.register(managed=False)
        self.assert_silent(bash("gh issue create --title x"))
        self.assert_silent(payload(tool_name="mcp__github__issue_write",
                                   tool_input={"method": "create"}))

    def test_an_unregistered_directory_is_not_denied(self) -> None:
        self.register(managed=True)
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        self.assert_silent(bash("gh issue create"), cwd=elsewhere)

    def test_with_no_database_at_all_it_is_silent(self) -> None:
        self.assert_silent(bash("gh issue create"))

    def test_the_opt_out_is_silent(self) -> None:
        self.register(managed=True)
        out = io.StringIO()
        env = {"HOME": str(self.home), "PWD": str(self.repo),
               "SD_ISSUE_GUARD": "0"}
        self.assertEqual(self.module.guard_call(bash("gh issue create"), env, out), 0)
        self.assertEqual(out.getvalue(), "")

    def test_garbage_on_stdin_is_silent(self) -> None:
        for text in ("", "   ", "not json", "[]", "null",
                     payload(tool_name="Bash"),
                     payload(tool_name="Bash", tool_input={"command": 3}),
                     bash("gh issue create 'unterminated")):
            self.assert_silent(text)

    def test_another_event_is_silent(self) -> None:
        self.register(managed=True)
        self.assert_silent(json.dumps({
            "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_input": {"command": "gh issue create"}}))

    def test_run_as_a_program_it_denies_through_stdout(self) -> None:
        """The installed form: no `bin/` on the path but its own directory."""
        self.register(managed=True)
        done = subprocess.run(  # nosec B603 - fixed argv, the hook as installed
            [sys.executable, str(HOOK)], input=bash("gh issue create"),
            capture_output=True, text=True, cwd=self.repo,
            env={**os.environ, "HOME": str(self.home), "PWD": str(self.repo)},
            check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        decision = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")


class TheGuardIsShipped(unittest.TestCase):
    def test_the_installer_registers_it_on_the_two_tools(self) -> None:
        self.assertIn(
            ("bin/sd-issue-guard", "PreToolUse", ("Bash|mcp__github__issue_write",)),
            sd_install.HOOK_SPECS)

    def test_the_pack_settings_deny_both_tools(self) -> None:
        deny = json.loads(SETTINGS.read_text(encoding="utf-8"))["permissions"]["deny"]
        self.assertIn("Bash(gh issue create:*)", deny)
        self.assertIn("mcp__github__issue_write", deny)


if __name__ == "__main__":
    unittest.main()
