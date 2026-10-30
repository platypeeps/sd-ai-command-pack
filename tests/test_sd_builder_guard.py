"""The builder guard: `sd-slice-builder` runs every Bash call in the foreground.

A Bash call that moves to the background never wakes an idle builder when it
exits; one builder lost about 2.5 hours that way on 2026-10-13 (sd:3995). The
agent's frontmatter runs `bin/sd-builder-guard` before Bash and Monitor. Each
test runs the hook as Claude Code does, a JSON payload on stdin, and reads its
stdout and exit code.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shutil
import subprocess  # nosec B404 - fixed argv, running the hook
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from tests.clean_env import clean_environment

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "bin" / "sd-builder-guard"
AGENT = REPO_ROOT / "agents" / "sd-slice-builder.md"


def run(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed argv, the hook under test
        [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, timeout=30,
        env=clean_environment())


def bash(command: str, **fields: Any) -> str:
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                       "tool_input": {"command": command, **fields}})


#: Every form the review rounds of sd:5985 found, each a line the guard must deny.
STASHES = (
    "git stash", "git stash push -m wip", "git stash pop", "git stash drop", "git stash -q",
    "git -C /tmp/wt stash", "git -c core.pager=cat stash apply", "/usr/bin/git stash",
    "cd /tmp/wt && git stash", "make; git stash", "GIT_DIR=x git stash", "rtk git stash",
    "rtk proxy git stash", "git --git-dir=/tmp/wt/.git stash clear",
    "if git stash pop; then echo; fi", "if true; then git stash pop; fi",
    "if false; then :; elif git stash; then :; fi", "if false; then :; else git stash; fi",
    "for f in a; do git stash; done", "while git stash pop; do :; done",
    "until git stash; do :; done", "! git stash", "time git stash", "{ git stash; }",
    "(git stash)", "f() { git stash; }", "case x in x) git stash;; esac",
    "echo $(git stash)", 'echo "$(git stash pop)"', "echo `git stash`", 'echo "`git stash`"',
    "exec git stash", "exec -a name git stash", "xargs git stash", "xargs -n 1 git stash",
    "env -u HOME git stash", "timeout 60 git stash", "timeout -s KILL 60 git stash pop",
    "timeout -k 5 --signal=TERM 60s git stash", "gtimeout 60 git stash", "nice git stash",
    "nice -n 10 git stash", "nohup git stash", "command git stash",
    "timeout 600 nice -n 5 git -C /tmp/wt stash", "sh -c 'git stash'",
    'bash -c "git stash pop"', "bash -lc 'git stash'", "eval git stash", "eval 'git stash'",
    "cat <<EOF\nit's here\nEOF\ngit stash", "echo 'unbalanced; git stash pop",
    'echo "open; git -C /tmp/wt stash', "echo $(echo $(git stash))",
    "git status # x\ngit stash pop", "git stash list; git stash pop",
    "git stash show && git stash drop", "2>/dev/null git stash pop", "/usr/bin/env git stash pop",
    "git \\\nstash pop", "git stash\nlist=done",
)


class Decisions(unittest.TestCase):
    def decision(self, stdin: str) -> dict | None:
        result = run(stdin)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)["hookSpecificOutput"]

    def assertDenied(self, stdin: str, *needles: str) -> None:
        output = self.decision(stdin)
        self.assertIsNotNone(output, "the call passed")
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertNotIn("updatedInput", output)
        for needle in needles:
            self.assertIn(needle, output["permissionDecisionReason"])

    def test_a_background_call_is_denied_with_the_fields_to_re_run_with(self) -> None:
        self.assertDenied(bash("make test", run_in_background=True, timeout=600000),
                          "run_in_background false", "timeout 600000")

    def test_a_timeout_below_600000_is_denied(self) -> None:
        self.assertDenied(bash("make test", timeout=120000), "timeout 600000")

    def test_no_timeout_is_the_120_s_default_and_is_denied(self) -> None:
        self.assertDenied(bash("make test"), "timeout 600000")

    def test_a_foreground_call_with_600000_passes_unchanged(self) -> None:
        self.assertIsNone(self.decision(bash("make test", timeout=600000)))
        self.assertIsNone(self.decision(bash("make test", timeout=600000, run_in_background=False,
                                             description="Run the tests")))

    def test_monitor_is_denied(self) -> None:
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Monitor",
                              "tool_input": {"command": "tail -f log"}})
        self.assertDenied(payload, "never waits in the background")

    def test_a_leading_sleep_is_denied_and_make_test_passes(self) -> None:
        for command in ("sleep 30", "  sleep 30 && make test", "sleep 1; echo hi", "sleep"):
            with self.subTest(command=command):
                self.assertDenied(bash(command, timeout=600000), "never waits in the background")
        for command in ("make test", "sleeper 30", "echo sleep 30"):
            with self.subTest(command=command):
                self.assertIsNone(self.decision(bash(command, timeout=600000)))

    def test_git_stash_in_every_form_is_denied_with_its_reason(self) -> None:
        for command in STASHES:
            with self.subTest(command=command):
                self.assertDenied(bash(command, timeout=600000),
                                  "git stash in a shared worktree hid or dropped "
                                  "another writer's work")

    def test_read_only_stash_and_other_commands_pass(self) -> None:
        for command in ("git stash list", "git -C /tmp/wt stash show -p", "git status",
                        "echo $(git rev-parse HEAD)", "timeout 60 git stash list",
                        "nice -n 10 git status", "grep -n stash notes.txt",
                        "if git status; then echo ok; fi", "bash -c 'git stash list'",
                        "echo 'unbalanced", "cat <<EOF\nit's here\nEOF\ngit status",
                        "git commit -F - <<'EOF'\nfix: drop the stash step\nEOF"):
            with self.subTest(command=command):
                self.assertIsNone(self.decision(bash(command, timeout=600000)))

    def test_a_kill_by_pattern_is_denied_and_a_kill_by_pid_passes(self) -> None:
        """Pack sd:6815: `pkill -f "sd-check --json"` ended another job's queued gate."""
        for command in ('pkill -f "sd-check --json"', "cd /tmp/wt && pkill -f sd-check; grep x y",
                        "killall python3", "/usr/bin/pkill -TERM -f make", "sudo killall sd-check"):
            with self.subTest(command=command):
                self.assertDenied(bash(command, timeout=600000), "another session's gate", "kill <pid>")
        for command in ("kill 4242", "kill -- -4242", "pgrep -f sd-check", "grep -n pkill notes.txt"):
            with self.subTest(command=command):
                self.assertIsNone(self.decision(bash(command, timeout=600000)))

    def test_a_mention_is_an_accepted_false_deny_that_names_the_way_past(self) -> None:
        """A builder is not hostile: a false deny costs a rephrase, a miss costs work."""
        for command in ("echo git stash", "git commit -m 'git stash'", "git log --grep stash",
                        "git -C stash status", "timeout -k 5 60 echo git stash",
                        "cat <<'EOF'\ngit stash\nEOF"):
            with self.subTest(command=command):
                self.assertDenied(bash(command, timeout=600000), "git commit -F")

    def test_other_tools_pass(self) -> None:
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read",
                              "tool_input": {"file_path": "/tmp/x"}})
        self.assertIsNone(self.decision(payload))

    def test_malformed_input_allows_with_a_warning(self) -> None:
        for stdin in ("", "not json", "[]", json.dumps({"tool_name": "Bash"}),
                      json.dumps({"tool_name": "Bash", "tool_input": "make test"})):
            with self.subTest(stdin=stdin):
                result = run(stdin)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("sd-builder-guard: unreadable input, allowing", result.stderr)


def stop(message: str | None, transcript: Path | None, **fields: Any) -> str:
    """A `SubagentStop` payload as Claude Code sends it; `None` drops the field."""
    payload: dict[str, Any] = {"hook_event_name": "SubagentStop", "stop_hook_active": False,
                               "agent_id": "a1", "agent_type": "sd-slice-builder", **fields}
    if message is not None:
        payload["last_assistant_message"] = message
    if transcript is not None:
        payload["agent_transcript_path"] = str(transcript)
    return json.dumps(payload)


def edit(path: str, tool: str = "Edit") -> dict:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t1", "name": tool, "input": {key: path}}]}}


PASS = "Focused run: `Ran 12 tests in 0.41s` then `OK`."
FAIL_FIRST = "Fail-first on origin/main: `FAILED (failures=1)`."


class Reports(unittest.TestCase):
    """The Stop check: a builder's final report quotes its check output (sd:6021)."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)

    def transcript(self, *entries: dict) -> Path:
        path = self.root / "agent.jsonl"
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
        return path

    def outcome(self, stdin: str) -> dict | None:
        result = run(stdin)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def assertBlocked(self, stdin: str, *needles: str) -> None:
        output = self.outcome(stdin)
        self.assertIsNotNone(output, "the report passed")
        self.assertEqual(output["decision"], "block")
        self.assertIn("not verified: <reason>", output["reason"])
        for needle in needles:
            self.assertIn(needle, output["reason"])

    def test_a_result_line_passes_a_report_that_touched_no_code(self) -> None:
        docs = self.transcript(edit("/wt/README.md"), edit("/wt/docs/a.md", "Write"))
        for report in (PASS, "Ran 1 test in 0.01s\n\nOK", "tests: 5 passed in 0.2s",
                       "check.sh: `3 passed, 0 failed`", "test result: ok. 4 passed; 0 failed"):
            with self.subTest(report=report):
                self.assertIsNone(self.outcome(stop(report, docs)))

    def test_a_report_with_no_result_line_is_blocked(self) -> None:
        docs = self.transcript(edit("/wt/README.md"))
        for report in ("Done. Branch x, head abc1234. All tests pass.", "Ran 0 tests in 0.0s\n\nOK",
                       "OK", "Ran 12 tests", "0 passed", ""):
            with self.subTest(report=report):
                self.assertBlocked(stop(report, docs), "result line")

    def test_not_verified_with_a_reason_passes(self) -> None:
        code = self.transcript(edit("/wt/bin/tool.py"))
        for report in ("Not verified: docs only, no check runs them.",
                       "Head abc1234. not verified - the suite needs the hub."):
            with self.subTest(report=report):
                self.assertIsNone(self.outcome(stop(report, code)))
        for report in ("not verified", "Not verified:\n"):
            with self.subTest(report=report):
                self.assertBlocked(stop(report, code))

    def test_a_code_change_needs_a_fail_first_line_too(self) -> None:
        for tool, path in (("Edit", "/wt/bin/tool.py"), ("Write", "/wt/bin/sd-new"),
                           ("MultiEdit", "/wt/lib/a.sh"), ("NotebookEdit", "/wt/n.ipynb")):
            with self.subTest(tool=tool):
                code = self.transcript(edit("/wt/README.md"), edit(path, tool))
                self.assertBlocked(stop(PASS, code), "fail-first")
                self.assertIsNone(self.outcome(stop(f"{FAIL_FIRST}\n{PASS}", code)))
        code = self.transcript(edit("/wt/bin/tool.py"))
        for fail_first in ("FAIL: test_x (tests.test_a.T.test_x)", "1 failed, 3 passed",
                           "AssertionError: 2 != 3"):
            with self.subTest(fail_first=fail_first):
                self.assertIsNone(self.outcome(stop(f"{fail_first}\n{PASS}", code)))
        self.assertBlocked(stop(f"0 failed\n{PASS}", code), "fail-first")

    def test_an_unreadable_transcript_counts_as_a_code_change(self) -> None:
        """An unknown is not a negative answer: the stricter rule holds, `not verified` still ends."""
        broken = self.root / "broken.jsonl"
        broken.write_text("{not json\n", encoding="utf-8")
        for transcript in (self.root / "missing.jsonl", broken, None):
            with self.subTest(transcript=transcript):
                self.assertBlocked(stop(PASS, transcript), "fail-first")
                self.assertIsNone(self.outcome(stop(f"{FAIL_FIRST}\n{PASS}", transcript)))

    def test_the_main_session_stop_reads_transcript_path(self) -> None:
        code = self.transcript(edit("/wt/bin/tool.py"))
        payload = json.dumps({"hook_event_name": "Stop", "stop_hook_active": False,
                              "transcript_path": str(code), "last_assistant_message": PASS})
        self.assertBlocked(payload, "fail-first")
        docs = self.transcript(edit("/wt/README.md"))
        payload = json.dumps({"hook_event_name": "Stop", "stop_hook_active": False,
                              "transcript_path": str(docs), "last_assistant_message": PASS})
        self.assertIsNone(self.outcome(payload))

    def test_a_block_holds_on_the_second_stop_too(self) -> None:
        """`stop_hook_active` does not let a bare report through; `not verified` is the way out."""
        docs = self.transcript(edit("/wt/README.md"))
        self.assertBlocked(stop("Done.", docs, stop_hook_active=True))

    def test_malformed_stop_input_allows_with_a_warning(self) -> None:
        docs = self.transcript(edit("/wt/README.md"))
        for stdin in (stop(None, docs), stop(None, None),
                      json.dumps({"hook_event_name": "SubagentStop", "last_assistant_message": 7})):
            with self.subTest(stdin=stdin):
                result = run(stdin)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("sd-builder-guard: unreadable input, allowing", result.stderr)


def frontmatter_hooks(event: str = "PreToolUse") -> list[dict]:
    text = AGENT.read_text(encoding="utf-8")
    _, header, _ = text.split("---\n", 2)
    return yaml.safe_load(header)["hooks"][event]


def load_installer():
    spec = importlib.util.spec_from_file_location("sd_install_guard", REPO_ROOT / "bin" / "sd_install.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Registration(unittest.TestCase):
    def test_the_frontmatter_runs_the_guard_on_bash_and_monitor_only(self) -> None:
        (entry,) = frontmatter_hooks()
        # Claude Code reads a matcher with `^` or `$` as an unanchored regex.
        matcher = re.compile(entry["matcher"])
        for tool in ("Bash", "Monitor"):
            self.assertTrue(matcher.search(tool), tool)
        for tool in ("Read", "Edit", "BashOutput", "PowerShell"):
            self.assertFalse(matcher.search(tool), tool)
        self.assertEqual(entry["hooks"], [{"type": "command", "command": HOOK.name}])
        self.assertTrue(os.access(HOOK, os.X_OK))

    def test_the_frontmatter_runs_the_guard_at_stop(self) -> None:
        """Claude Code turns a subagent's frontmatter `Stop` hook into `SubagentStop`."""
        (entry,) = frontmatter_hooks("Stop")
        self.assertNotIn("matcher", entry)
        self.assertEqual(entry["hooks"], [{"type": "command", "command": HOOK.name}])

    def test_the_installed_agent_finds_the_guard_on_the_linked_path(self) -> None:
        """The installer copies the agent verbatim, so the hook names a command, not a path.

        `--user` links every `bin/` executable into `~/.local/bin`; the installed
        agent's command resolves there and runs this checkout's script.
        """
        with tempfile.TemporaryDirectory() as scratch:
            home = Path(scratch).resolve()
            rc = load_installer().main(["--user", "--home", str(home)], out=io.StringIO())
            self.assertEqual(rc, 0)
            installed = home / ".claude" / "agents" / AGENT.name
            self.assertEqual(installed.read_bytes(), AGENT.read_bytes())
            (entry,) = frontmatter_hooks()
            command = entry["hooks"][0]["command"]
            found = shutil.which(command, path=str(home / ".local" / "bin"))
            self.assertIsNotNone(found, f"{command} is not linked into ~/.local/bin")
            self.assertEqual(Path(found).resolve(), HOOK.resolve())


if __name__ == "__main__":
    unittest.main()
