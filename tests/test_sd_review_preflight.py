"""Explicit provider protocol probes use canned responses, never real providers."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
from unittest import mock

from tests.test_sd_review import FakeClient, ReviewFixture, namespace, sd_review

REGISTRY = """
bills:
  fixture: { cost: subscription }
providers:
  minimax: { url: "https://minimax.invalid/v1", model: fixture-minimax, vendor: minimax, bill: fixture, roles: [reviewer], env: [KEY] }
  kimi: { url: "https://kimi.invalid/v1", model: fixture-kimi, vendor: moonshot, bill: fixture, roles: [reviewer], env: [KEY] }
  author: { start: "fixture-author", vendor: other, bill: fixture, reader: codex-json, roles: [author, reviewer], env: [] }
roles:
  author: [author]
  reviewer: [minimax, kimi, author]
"""


class ProviderPreflight(ReviewFixture):
    def setUp(self):
        super().setUp()
        self.registry_path = self.registry_home / ".local/share/sd/providers.yaml"
        self.registry_path.write_text(REGISTRY)
        self.root = self.make_repo()
        self.consent("minimax@minimax.invalid, kimi@kimi.invalid, author@fixture-author")
        subprocess.run(["git", "checkout", "-qb", "fixture"], cwd=self.root, check=True, capture_output=True)
        (self.root / "private.py").write_text('private_source = "never-transmit-marker"\n')
        self.commit("human")
        self.client = FakeClient()
        self.runner = mock.Mock(side_effect=AssertionError("preflight called repository checks or a provider CLI"))

    def consent(self, value):
        (self.root / "CLAUDE.local.md").write_text(
            "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\nreviewers: " + value +
            "\ncontext: never-transmit-convention\n<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n")

    def commit(self, author):
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "fixture\n\nAuthored-with: " + author],
                       cwd=self.root, check=True, capture_output=True)

    def probe(self, **values):
        overrides = {"preflight": True, "provider": "minimax", **values}
        with mock.patch.object(sd_review, "local_conventions", side_effect=AssertionError("private conventions read")), mock.patch.object(
            sd_review, "review_material", side_effect=AssertionError("private source read")
        ):
            return sd_review.review(self.root, namespace(**overrides), self.runner,
                                    self.environment(KEY="secret-key-marker"), client=self.client)

    def test_one_selected_probe_is_distinct_from_review_and_sends_no_repository(self):
        before = {str(p.relative_to(self.tmp)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.tmp.rglob("*") if p.is_file()}
        result = self.probe()
        self.assertEqual(result["status"], "preflight_passed")
        self.assertEqual(result["operation"], "provider_preflight")
        self.assertEqual(result["scope"], "provider_preflight")
        self.assertEqual((result["requested_reviews"], result["completed_reviews"], result["reviewed_by"]), (0, 0, []))
        self.assertIsNone(result["check"])
        self.assertEqual(result["probe_calls"], 1)
        self.assertEqual([row["provider"] for row in self.client.sent], ["minimax"])
        for forbidden in ("never-transmit", "private.py", str(self.root), "secret-key-marker"):
            self.assertNotIn(forbidden, self.client.sent[0]["prompt"])
        self.assertIn("Schema:", self.client.sent[0]["prompt"])
        self.assertEqual(before, {str(p.relative_to(self.tmp)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in self.tmp.rglob("*") if p.is_file()})
        output = io.StringIO()
        sd_review.render(result, output)
        self.assertIn("no branch review", output.getvalue())

    def test_probe_cannot_be_used_as_a_prior_branch_review(self):
        result = self.probe()
        saved = self.tmp / "probe.json"
        saved.write_text(json.dumps(result))
        self.client.sent.clear()
        with self.assertRaisesRegex(sd_review.UsageError, "prior review report does not match"):
            sd_review.review(self.root, namespace(scope="branch", provider="minimax", verify_report=str(saved),
                base=result["subject"]["head"]), self.runner, self.environment(KEY="secret"), client=self.client)
        self.assertEqual(self.client.sent, [])

    def test_both_named_providers_use_the_same_protocol_and_one_call_each(self):
        for name in ("minimax", "kimi"):
            with self.subTest(provider=name):
                self.client.sent.clear()
                result = self.probe(provider=name)
                self.assertEqual(result["status"], "preflight_passed")
                self.assertEqual([row["provider"] for row in self.client.sent], [name])

    def test_explain_never_dispatches_or_claims_success(self):
        result = self.probe(explain=True)
        self.assertEqual(result["status"], "preflight_planned")
        self.assertEqual(result["probe_calls"], 0)
        self.assertEqual(result["outcomes"], [])
        self.assertEqual(self.client.sent, [])

    def test_missing_key_is_refused_before_client(self):
        with mock.patch.object(self, "environment", return_value={"HOME": str(self.registry_home)}):
            result = self.probe()
        self.assertEqual(result["status"], "preflight_failed")
        self.assertIn("credential", result["probe_refusal"])
        self.assertEqual((result["probe_calls"], self.client.sent), (0, []))

    def test_consent_disabled_provider_and_matching_author_send_nothing(self):
        self.consent("")
        with self.assertRaises(sd_review.sd_registry.ConsentRefusal):
            self.probe()
        self.consent("minimax@minimax.invalid")
        self.registry_path.write_text(REGISTRY.replace("model: fixture-minimax", "enabled: false, reason: fixture, model: fixture-minimax"))
        with self.assertRaises(sd_review.sd_registry.RegistryError):
            self.probe()
        self.registry_path.write_text(REGISTRY)
        (self.root / "other.py").write_text("x = 1\n")
        self.commit("minimax/minimax")
        with self.assertRaises(sd_review.sd_registry.RegistryError):
            self.probe()
        self.assertEqual(self.client.sent, [])

    def test_unknown_authorship_explain_is_advisory_and_execution_refuses(self):
        (self.root / "other.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "unattributed"], cwd=self.root, check=True, capture_output=True)
        result = self.probe(explain=True)
        self.assertTrue(result["authorship_refusal"])
        self.assertEqual(result["probe_refusal"], "no eligible provider")
        with self.assertRaises(sd_review.Refusal):
            self.probe()
        self.assertEqual(self.client.sent, [])

    def test_incompatible_flags_and_cli_provider_send_nothing(self):
        for values in ({"provider": None}, {"scope": "planning"}, {"scope": "pr"}, {"base": "a" * 40},
                       {"verify_report": "prior.json"}, {"resume_report": "prior.json"}, {"item": "work"},
                       {"draft": True}, {"challenge": True}, {"dry_run": True}, {"expected_timing": "a"},
                       {"provider": "author"}):
            with self.subTest(values=values), self.assertRaises(sd_review.UsageError):
                self.probe(**values)
        self.assertEqual(self.client.sent, [])

    def test_fabricated_findings_fail_the_fixed_empty_protocol_probe(self):
        body = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"findings": [
            {"severity": "high", "family": "correctness", "path": "invented.py", "line": 1,
             "summary": "A fabricated finding without any supplied repository."}]})}}]}
        self.client = FakeClient(default=(0, json.dumps(body), "", True))
        result = self.probe()
        self.assertEqual(result["status"], "preflight_failed")
        self.assertEqual(result["protocol_error"], "synthetic preflight expected an empty findings list")
        self.assertEqual(result["outcomes"][0]["status"], sd_review.FINDINGS)
        self.assertEqual(result["outcomes"][0]["findings"], 1)
        self.assertEqual(result["completed_reviews"], 0)
        self.assertEqual(len(self.client.sent), 1)

    def test_failures_never_fall_back_or_complete_a_review(self):
        cases = [(1, "", "connection failed", False), (429, "{}", "HTTP 429", True),
                 (0, '{"choices":[{"finish_reason":"length","message":{"content":"{\\"findings\\":[]}"}}]}', "", True),
                 (0, '{"choices":[{"message":{"content":"{}"}}]}', "", True)]
        for response in cases:
            self.client = FakeClient(default=response)
            result = self.probe()
            self.assertEqual(result["status"], "preflight_failed")
            self.assertEqual(sd_review.STATUS_EXIT[result["status"]], 5)
            self.assertEqual([row["provider"] for row in self.client.sent], ["minimax"])
            self.assertEqual(result["completed_reviews"], 0)

    def test_actual_cli_explain_has_no_review_or_process_boundary(self):
        with mock.patch.object(sd_review.sd_lib, "repo_root", return_value=self.root), mock.patch.dict(
            sd_review.os.environ, self.environment(KEY="secret-key-marker"), clear=True
        ), mock.patch.object(sd_review, "subprocess_runner", self.runner), mock.patch.object(
            sd_review.sd_registry._OPENER, "open", side_effect=AssertionError("HTTP request")
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            code = sd_review.main(["--preflight", "--provider", "minimax", "--explain", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["operation"], "provider_preflight")
