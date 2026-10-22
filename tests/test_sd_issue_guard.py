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

import contextlib
import io
import json
import os
import pathlib
import sqlite3
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

    def assert_asked(self, text: str, cwd: pathlib.Path | None = None) -> str:
        code, printed = self.fire(text, cwd)
        self.assertEqual(code, 0)
        self.assertTrue(printed, f"no decision for {text}")
        decision = json.loads(printed)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "ask")
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

    def test_every_sd_command_the_denial_names_parses(self) -> None:
        """sd:2515: the hint said `sd task note <n> "<text>"`, and `note` takes
        the text only as `--body`, so an agent that followed it hit a usage
        error. Each backticked `sd` command is filled in and handed to the
        real parser; a usage error is `SystemExit(2)`."""
        import importlib.machinery
        import importlib.util
        import re
        import shlex

        loader = importlib.machinery.SourceFileLoader("sd_under_test", str(REPO_ROOT / "bin" / "sd"))
        spec = importlib.util.spec_from_loader("sd_under_test", loader)
        sd = importlib.util.module_from_spec(spec)
        loader.exec_module(sd)
        commands = re.findall(r"`(sd [^`]+)`", self.module.REASON)
        self.assertGreaterEqual(len(commands), 2, self.module.REASON)
        for command in commands:
            with self.subTest(command=command):
                argv = shlex.split(command.replace("<n>", "7"))[1:]
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    try:
                        sd.build_parser().parse_args(argv)
                    except SystemExit as error:
                        self.fail(f"{command!r} is a usage error ({error.code}): {stderr.getvalue()}")

    def test_the_spellings_an_agent_actually_uses_are_denied(self) -> None:
        for command in (
            "gh issue new --title x",
            "gh -R example/managed issue create --title x",
            "gh --repo=example/managed issue create",
            "cd src && gh issue create --title x",
            "git status; gh issue create",
            "GH_PAGER= gh issue create",
            "env GH_REPO=example/managed /opt/homebrew/bin/gh issue create",
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


def issue_write(method: Any = "update", **target: Any) -> str:
    fields = {"owner": "example", "repo": "managed", "issue_number": 7, "state": "closed", **target}
    if method is not None:
        fields["method"] = method
    return payload(tool_name="mcp__github__issue_write",
                   tool_input={key: value for key, value in fields.items() if value is not None})


class AManagedRepositoryWithGithubIssuesOn(Fixture):
    """sd:4827. `repo.github_issues` on lets an agent close a reporter's issue
    in this repository, and nothing else: an update aimed at this repository's
    remote passes; filing an issue, and an update aimed anywhere else, do not."""

    def setUp(self) -> None:
        super().setUp()
        self.register(managed=True)
        self.switch("on")

    def switch(self, value: str) -> None:
        connection = sd_db.connect(home=self.home)
        try:
            sd_db.repos.set_github_issues(connection, self.repo, value)
        finally:
            connection.close()

    def test_an_update_of_this_repository_passes(self) -> None:
        self.assert_silent(issue_write())
        self.assert_silent(issue_write(owner="Example", repo="MANAGED"))

    def test_filing_an_issue_is_still_denied(self) -> None:
        self.assertIn("sd task add", self.assert_denied(issue_write("create", title="x")))
        self.assert_denied(bash("gh issue create --title x"))

    def test_an_update_aimed_at_nothing_is_denied(self) -> None:
        for call in (issue_write(owner=None), issue_write(repo=None), issue_write(owner=3),
                     issue_write(owner="example/managed", repo="")):
            with self.subTest(call=call):
                self.assert_denied(call)

    def test_an_update_aimed_at_an_external_repository_asks(self) -> None:
        for call in (issue_write(owner="example", repo="other"), issue_write(owner="someone")):
            with self.subTest(call=call):
                self.assert_asked(call)

    def test_a_missing_or_unknown_method_is_denied(self) -> None:
        for method in (None, "Update", "delete", "", 1, ["update"]):
            with self.subTest(method=method):
                self.assert_denied(issue_write(method))

    def test_off_denies_the_update_again(self) -> None:
        self.switch("off")
        self.assert_denied(issue_write())

    def test_a_linked_worktree_passes_as_its_main_checkout(self) -> None:
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.test",
            "commit", "-q", "--allow-empty", "-m", "seed")
        worktree = self.tmp / "wt"
        git(self.repo, "worktree", "add", "-q", str(worktree))
        self.assert_silent(issue_write(), cwd=worktree)
        self.assert_denied(issue_write("create"), cwd=worktree)

    def test_a_setting_that_cannot_be_read_denies(self) -> None:
        """Failures: once the row is managed, an unread setting is not a pass."""
        with mock.patch.object(sd_db.repos, "github_issues", side_effect=sd_db.errors.SchemaTooOld(34, 35)):
            self.assert_denied(issue_write())


class AnExternalTargetAsksTheOperator(Fixture):
    """sd:5721. The call's target decides, not the session's checkout: an issue
    for a repository the operator does not manage is the operator's call, made
    in the harness prompt one issue at a time; a managed target stays denied."""

    def setUp(self) -> None:
        super().setUp()
        self.register(managed=True)

    def create(self, owner: str, repo: str) -> str:
        return payload(tool_name="mcp__github__issue_write",
                       tool_input={"method": "create", "owner": owner, "repo": repo, "title": "x"})

    def test_filing_in_an_external_repository_asks(self) -> None:
        reason = self.assert_asked(self.create("mezmo", "aura"))
        self.assertIn("mezmo/aura", reason)

    def test_gh_still_targets_the_checkout(self) -> None:
        """The settings deny list refuses `gh issue create`; the guard keeps its checkout rule."""
        for command in ("gh issue create -R mezmo/aura --title x",
                        "GH_REPO=mezmo/aura gh issue create --title x"):
            with self.subTest(command=command):
                self.assert_denied(bash(command))

    def test_filing_in_the_managed_repository_by_name_is_denied(self) -> None:
        self.assert_denied(self.create("Example", "managed"))

    def test_filing_in_another_managed_repository_is_denied(self) -> None:
        other = self.home / "other"
        other.mkdir()
        git(other, "init", "-q")
        git(other, "remote", "add", "origin", "git@github.com:example/other.git")
        connection = sd_db.connect(home=self.home)
        try:
            key = sd_db.add_repo(connection, other, home=self.home)
            sd_db.writes.upsert_repo(connection, key, managed=1)
            connection.commit()
        finally:
            connection.close()
        self.assert_denied(self.create("example", "other"))

    def test_an_unmanaged_clone_of_a_managed_remote_does_not_hide_it(self) -> None:
        clone = self.home / "a-clone"
        clone.mkdir()
        git(clone, "init", "-q")
        git(clone, "remote", "add", "origin", ORIGIN)
        connection = sd_db.connect(home=self.home)
        try:
            key = sd_db.add_repo(connection, clone, home=self.home)
            sd_db.writes.upsert_repo(connection, key, managed=0)
            connection.commit()
        finally:
            connection.close()
        self.assert_denied(self.create("example", "managed"))

    def test_a_session_outside_any_managed_repository_asks_too(self) -> None:
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        self.assert_asked(self.create("mezmo", "aura"), cwd=elsewhere)


class AManagedRepositoryOnAStoreBefore35(Fixture):
    """Older state: the new hook over a store not yet migrated reads `managed`
    and denies an update, as it did before the setting existed."""

    def test_an_update_is_denied(self) -> None:
        from sd_db.schema import migrations

        through = [m for m in migrations() if m[0] < 35]
        with mock.patch("sd_db.migrate.migrations", return_value=through):
            sd_db.migrate(home=self.home)
        connection = sqlite3.connect(self.home / ".local/share/sd/sd.db")
        try:
            connection.execute(
                "INSERT INTO repo (path, remote, managed, created_at, updated_at) VALUES (?, ?, 1, 't', 't')",
                (str(self.repo), ORIGIN))
            connection.commit()
        finally:
            connection.close()
        self.assert_denied(issue_write())


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
