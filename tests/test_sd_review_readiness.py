"""Explanation and early refusal perform no review, meter, gate, or writes.

One local process is allowed and named here: `codex debug prompt-input`, the
skill-suppression probe (sd:1248). It renders a prompt offline, asks no API,
and bills nothing -- measured on codex-cli 0.155.1, which answers it with
`CODEX_HOME` pointed at an empty directory and no login at all. Every
assertion below names that call rather than relaxing to "some calls".
"""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import chdir, contextmanager
from unittest import mock

from tests.test_sd_review import (
    FakeClient,
    FakeRunner,
    ReviewFixture,
    namespace,
    sd_review,
)
from tests.test_sd_review_ledger import LedgerFixture


@contextmanager
def read_only_connections():
    connection = sd_review.Ledger.connection

    def connect(ledger, *, write):
        if write:
            raise AssertionError("no writes")
        return connection(ledger, write=False)

    with mock.patch.object(sd_review.Ledger, "connection", connect):
        yield


class ReadinessTests(ReviewFixture):
    def call(self, **options):
        root = self.make_repo()
        (root / "src.py").write_text("x = 1")
        runner, client = FakeRunner(), FakeClient()
        with read_only_connections():
            result = sd_review.review(root, namespace(explain=True, **options), runner,
                                      self.environment(), self.chatgpt_home(), client=client,
                                      meter=lambda *args: self.fail("no quota calls"))
        self.assert_no_session_started(runner)
        self.assertEqual(client.sent, [])
        self.assertEqual(result["status"], "explained")
        self.assertEqual(result["readiness"]["runtime_approval"], "not_observable")
        return result

    def test_ready_explanation_is_zero_call_and_read_only(self):
        result = self.call()
        self.assertEqual(result["readiness"]["status"], "ready")
        self.assertEqual(result["readiness"]["blockers"], [])

    def test_missing_executable_blocks_before_the_gate(self):
        root = self.make_repo()
        (root / "src.py").write_text("x = 1")
        runner = FakeRunner()
        result = sd_review.review(root, namespace(), runner, self.environment(PATH="/nonexistent"), self.chatgpt_home())
        self.assertEqual(result["readiness"]["status"], "blocked")
        self.assertEqual({row["code"] for row in result["readiness"]["blockers"]}, {"executable_missing"})
        # Blocked readiness dispatches nothing, so not even the skill probe
        # runs: it is taken under `--explain` and before a codex dispatch.
        self.assertEqual(runner.calls, [])
        self.assertIsNone(result["check"])

    def test_executable_lookup_matches_dispatch_cwd(self):
        root = self.make_repo()
        (root / "tools").mkdir()
        nested = root / "nested"
        nested.mkdir()
        for component, relative in (("tools", "tools/fixture-reviewer"), ("", "fixture-reviewer")):
            with self.subTest(component=component):
                target = root / relative
                target.write_text("#!/bin/sh\nexit 0\n")
                target.chmod(0o700)
                env = self.environment(PATH=component + os.pathsep + os.defpath)
                provider = sd_review.sd_registry.Provider(name="fixture", vendor="fixture", bill="fixture",
                                                          start="fixture-reviewer", reader="claude-json")
                with chdir(nested):
                    issues = sd_review.sd_review_readiness.provider_issues(provider, {}, env, str(root))
                    actual = subprocess.run(["fixture-reviewer"], cwd=root, env=env, capture_output=True)
                self.assertEqual(actual.returncode, 0)
                self.assertEqual(issues, [])

    def test_unrelated_codex_authentication_is_never_read(self):
        path = self.registry_home / ".local/share/sd/providers.yaml"
        path.write_text(path.read_text().replace("reader: codex-json", "reader: claude-json"))
        with mock.patch.object(sd_review, "codex_preflight_state", side_effect=AssertionError("unrelated auth")):
            result = self.call(provider="second")
        self.assertEqual(result["codex_preflight"]["reason"], "not selected")
        self.assertEqual(result["readiness"]["status"], "ready")

    def test_codex_auth_failure_is_actionable_before_gate(self):
        root = self.make_repo()
        (root / "src.py").write_text("x = 1")
        runner = FakeRunner()
        result = sd_review.review(root, namespace(), runner, self.environment(), self.chatgpt_home(mode="apikey"))
        self.assertEqual(result["readiness"]["status"], "blocked")
        self.assertIn("authentication_refused", [row["code"] for row in result["readiness"]["blockers"]])
        self.assertEqual(runner.calls, [])

    def test_consent_failure_has_no_provider_or_gate_call(self):
        root = self.make_repo()
        (root / "src.py").write_text("x = 1")
        (root / "CLAUDE.local.md").write_text("")
        runner = FakeRunner()
        result = sd_review.review(root, namespace(explain=True), runner, self.environment(), self.chatgpt_home())
        self.assertEqual(result["readiness"]["status"], "blocked")
        self.assertEqual(runner.calls, [])
        self.assertTrue(all(set(row) == {"code", "boundary", "provider", "next_action"} for row in result["readiness"]["blockers"]))

    def test_explicit_unavailable_selection_is_machine_readable(self):
        result = self.call(provider="not-configured")
        self.assertEqual(result["readiness"]["status"], "blocked")
        self.assertIn("reviewer_unavailable", [row["code"] for row in result["readiness"]["blockers"]])

    def test_transport_limits_preserve_required_reviewer_count_and_other_refusals(self):
        root = self.make_repo()
        providers = [sd_review.sd_registry.Provider(name=name, vendor=name, bill=name,
                     start=name, reader="codex-json") for name in ("codex", "second")]
        result = {"repo": str(root), "codex_preflight": {"ok": True}, "requested_reviews": 1,
                  "input_manifest": {"status": "oversized", "limit_bytes": 100,
                                     "transport_bytes": {"codex": 50, "second": 101}}}
        readiness = sd_review.sd_review_readiness.review_readiness
        self.assertEqual(readiness(result, providers, self.environment())["status"], "ready")
        for failure in ("count", "auth", "all_oversized"):
            candidate = {**result, "input_manifest": dict(result["input_manifest"])}
            if failure == "count":
                candidate["requested_reviews"] = 2
            elif failure == "auth":
                candidate["codex_preflight"] = {"ok": False, "reason": "fixture refusal"}
            else:
                candidate["input_manifest"]["transport_bytes"] = {"codex": 101, "second": 101}
            with self.subTest(failure=failure):
                outcome = readiness(candidate, providers, self.environment())
                self.assertEqual(outcome["status"], "blocked")
                self.assertIn("input_oversized", [row["code"] for row in outcome["blockers"]])


class LedgerReadinessTests(LedgerFixture):
    def test_explanation_does_not_release_orphans_or_write_ledger(self):
        self.seed()
        before = self.rows()
        client = FakeClient()
        with read_only_connections():
            result = self.review(client, explain=True)
        self.assertEqual(result["status"], "explained")
        self.assertEqual(before, self.rows())
        self.assertEqual(client.sent, [])
        self.assertEqual(self.runner.calls, [])
        self.assertNotIn("fixture", json.dumps(result["readiness"]))
