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


def frontmatter_hooks() -> list[dict]:
    text = AGENT.read_text(encoding="utf-8")
    _, header, _ = text.split("---\n", 2)
    return yaml.safe_load(header)["hooks"]["PreToolUse"]


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
