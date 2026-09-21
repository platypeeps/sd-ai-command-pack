"""Contract tests use fakes; the opt-in OS probe reports separate evidence."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import reviewer_isolation_probe as probe
from tests.test_sd_review import FakeRunner, ReviewFixture, sd_review


def completed(**changes: str) -> subprocess.CompletedProcess[str]:
    observations = {**probe.READ_EXPECTATIONS, **probe.WRITE_EXPECTATIONS, **changes}
    return subprocess.CompletedProcess([], 0, "\n".join(f"{key}={value}" for key, value in observations.items()), "")


class IsolationProbeTests(unittest.TestCase):
    def test_os_pass_never_claims_instruction_or_production_isolation(self) -> None:
        report = probe.assess(completed())
        self.assertEqual(report["status"], "os_probe_passed")
        self.assertEqual(report["os_confinement"]["status"], "passed")
        self.assertEqual(report["file_read_access"]["status"], "passed")
        self.assertEqual(report["instruction_sources"]["status"], "not_measured")
        self.assertEqual(report["production_review_isolation"], "not_established")

    def test_each_forbidden_read_and_write_fails_closed(self) -> None:
        denied = {key for key, value in {**probe.READ_EXPECTATIONS, **probe.WRITE_EXPECTATIONS}.items()
                  if value == "denied"}
        for key in denied:
            with self.subTest(key=key):
                report = probe.assess(completed(**{key: "written" if key.startswith("write_") else "read"}))
                self.assertEqual(report["status"], "blocked")
                self.assertEqual(report["os_confinement"]["status"], "failed")
                self.assertTrue(report["blockers"])

    def test_denied_positive_control_is_not_isolation_success(self) -> None:
        report = probe.assess(completed(allowed_payload="denied"))
        self.assertEqual(report["blockers"][0]["code"], "read_confinement_failed")

    def test_startup_failure_preserves_stderr_without_a_pass(self) -> None:
        error = "sandbox-exec: sandbox_apply: Operation not permitted"
        report = probe.assess(subprocess.CompletedProcess([], 71, "", error))
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["blockers"][0]["code"], "sandbox_start_or_execution_failed")
        self.assertEqual(report["process"]["stderr"], error)
        self.assertEqual(report["os_confinement"]["status"], "not_measured")

    def test_incomplete_duplicate_unknown_and_malformed_output_cannot_pass(self) -> None:
        good = completed().stdout
        for output in ("", "missing separator", good + "\nunknown=read", good + "\nallowed_payload=read"):
            with self.subTest(output=output):
                self.assertEqual(probe.assess(subprocess.CompletedProcess([], 0, output, ""))["status"], "blocked")

    def test_synthetic_fixtures_stay_under_temporary_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            paths = probe.fixtures(root)
            for path in paths.values():
                self.assertTrue(path.resolve().is_relative_to(root))
            self.assertEqual(paths["symlink_escape"].resolve(), paths["forbidden_sibling"])
            self.assertIn("NOT_A_REAL_TOKEN", paths["fake_home_auth"].read_text())

    def test_runner_gets_no_parent_secrets_and_only_sandbox_subcommand(self) -> None:
        def fake(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(argv[:2], ["/fake/codex", "sandbox"])
            self.assertIn(f"permissions.{probe.PROFILE}.network.enabled=false", argv)
            self.assertNotIn("exec", argv)
            env = kwargs["env"]
            self.assertEqual(set(env), {"PATH", "HOME", "CODEX_HOME"})
            self.assertTrue(Path(env["HOME"]).name == "fake-home")
            self.assertNotEqual(env["HOME"], "/synthetic-parent-home")
            self.assertEqual(kwargs["timeout"], 20)
            self.assertIn('":root"="deny"', " ".join(argv))
            return completed()

        with patch.dict(os.environ, {"HOME": "/synthetic-parent-home", "OPENAI_API_KEY": "SYNTHETIC_PARENT_SECRET"}):
            self.assertEqual(probe.run_probe("/fake/codex", fake)["status"], "os_probe_passed")

    def test_missing_runner_timeout_and_oserror_have_named_blockers(self) -> None:
        with patch.object(probe.shutil, "which", return_value=None):
            self.assertEqual(probe.run_probe()["blockers"][0]["code"], "sandbox_runner_missing")
        for error, code in ((subprocess.TimeoutExpired("fake", 20), "sandbox_probe_timeout"),
                            (OSError("unavailable fixture"), "sandbox_runner_unavailable")):
            with self.subTest(code=code), patch.object(probe.subprocess, "run", side_effect=error) as runner:
                self.assertEqual(probe.run_probe("/fake/codex", runner)["blockers"][0]["code"], code)


class InstructionArgumentContracts(ReviewFixture):
    """Fake responses prove requested argv controls, not actual instruction loading."""

    def test_codex_protocol_requests_suppression_without_claiming_read_confinement(self) -> None:
        root = self.make_repo()
        (root / "AGENTS.md").write_text("SYNTHETIC_INSTRUCTION_CANARY\n")
        runner = FakeRunner()
        provider = sd_review.sd_registry.Provider(name="codex", vendor="openai", bill="first",
                    start="codex exec", reader="codex-json", env=())
        outcome = sd_review.run_provider(provider, root, sd_review.resolve_subject(root, "worktree"),
            "Review synthetic material", runner, self.environment(), 5, self.chatgpt_home())
        self.assertEqual(outcome.status, sd_review.CLEAN)
        argv = runner.calls[0]["argv"]
        for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral",
                     "project_doc_max_bytes=0", "skills.include_instructions=false"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertEqual(runner.calls[0]["stdin"], "Review synthetic material")

    def test_claude_protocol_requests_restricted_tools_not_an_os_sandbox(self) -> None:
        root = self.make_repo()
        (root / "AGENTS.md").write_text("SYNTHETIC_INSTRUCTION_CANARY\n")
        runner = FakeRunner(default=sd_review.Completed(0, json.dumps({
            "type": "result", "subtype": "success", "is_error": False,
            "structured_output": {"findings": []}}), ""))
        provider = sd_review.sd_registry.Provider(name="claude", vendor="anthropic", bill="first",
                    start="claude -p", reader="claude-json", env=())
        outcome = sd_review.run_provider(provider, root, sd_review.resolve_subject(root, "worktree"),
            "Review synthetic material", runner, self.environment(), 5)
        self.assertEqual(outcome.status, sd_review.CLEAN)
        argv = runner.calls[0]["argv"]
        for flag in ("--safe-mode", "--restricted", "--strict-mcp-config", "--no-session-persistence"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(json.loads(argv[argv.index("--mcp-config") + 1]), {"mcpServers": {}})


if __name__ == "__main__":
    unittest.main()
