"""Bounded, local response handling; no paid provider is called."""

from __future__ import annotations

import io
import json
import pathlib
import unittest
import urllib.error
from unittest import mock

from tests.test_sd_review import FakeClient, FakeRunner, ReviewFixture, sd_review


def finding(severity: str = "low", summary: str = "defect") -> dict:
    return {"path": "src.py", "line": 1, "severity": severity,
            "summary": summary, "family": "correctness"}


class ResponseRegressions(unittest.TestCase):
    def test_unparseable_success_is_not_quota_evidence(self) -> None:
        for content in ("unfinished JSON about rate_limit", "unfinished JSON about parsing"):
            outcome = sd_review._answer("url", sd_review.Completed(0, content, ""), None)
            self.assertEqual(outcome.status, sd_review.UNAVAILABLE)

    def test_failed_process_model_output_is_not_quota_evidence(self) -> None:
        text = json.dumps({"findings": [finding("high", "rate_limit defect")]})
        outcome = sd_review._answer("cli", sd_review.Completed(1, text, "pipe failed"),
                                   sd_review.parse_findings(text))
        self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
        self.assertEqual(outcome.findings[0]["severity"], "high")

    def test_oversized_response_is_refused_before_json_parsing(self) -> None:
        with mock.patch.object(sd_review, "MAX_OUTPUT_BYTES", 100), mock.patch.object(
            sd_review.json, "loads", side_effect=AssertionError("oversized input reached JSON parser")
        ):
            parsed = sd_review.parse_findings("x" * 101)
        self.assertIsNotNone(parsed)
        self.assertIn("limit", parsed.error)
        self.assertTrue(any(row["severity"] == "high" for row in parsed.findings))

    def test_findings_are_bounded_without_hiding_a_late_blocker(self) -> None:
        rows = [finding(summary=str(i)) for i in range(sd_review.MAX_FINDINGS)]
        rows.append(finding("high", "late blocker"))
        parsed = sd_review.parse_findings(json.dumps({"findings": rows}))
        self.assertLessEqual(len(parsed.findings), sd_review.MAX_FINDINGS)
        self.assertIn("limit", parsed.error)
        self.assertTrue(any(row["summary"] == "late blocker" for row in parsed.findings))
        self.assertTrue(any("omitted" in row["summary"] for row in parsed.findings))

    def test_missing_passwd_uid_keeps_only_declared_environment(self) -> None:
        provider = sd_review.sd_registry.Provider(name="local", vendor="local", bill="free", env=("OWN_KEY",))
        with mock.patch.object(sd_review.sd_registry.pwd, "getpwuid", side_effect=KeyError(424242)):
            env = sd_review.sd_registry.provider_environment(provider, {
                "USER": "fixture-user", "OWN_KEY": "owned", "OTHER_KEY": "unrelated"
            })
        self.assertEqual(env, {"OWN_KEY": "owned"})


class URLDiagnostics(ReviewFixture):
    def run_response(self, payload: object, exit_code: int = 0, stderr: str = ""):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        client = FakeClient(default=(exit_code, body, stderr, True))
        provider = sd_review.sd_registry.Provider(name="url", vendor="fixture", bill="free",
            url="https://fixture.example/v1", env=("OWN_KEY",))
        return sd_review.run_provider(provider, self.tmp,
            sd_review.Subject("worktree", "HEAD", "worktree", (), 0, ""),
            "private-prompt-marker", FakeRunner(), {"OWN_KEY": "credential-marker"}, 7,
            client=client)

    def envelope(self, content: object, reason: str = "stop", **extra: object) -> dict:
        return {"choices": [{"finish_reason": reason, "message": {"content": content, **extra}}]}

    def test_reasoning_only_does_not_borrow_model_quota_words(self) -> None:
        outcome = self.run_response(self.envelope(None, reasoning_content="rate_limit credential-marker private-prompt-marker"))
        self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
        self.assertEqual(outcome.diagnostic["category"], "reasoning_only")
        self.assertGreater(outcome.diagnostic["reasoning_bytes"], 0)
        encoded = json.dumps(outcome.diagnostic)
        for secret in ("credential-marker", "private-prompt-marker", "rate_limit"):
            self.assertNotIn(secret, encoded)

    def test_length_finish_never_completes_even_with_valid_json(self) -> None:
        for rows in ([], [finding("high", "truncated blocker")]):
            outcome = self.run_response(self.envelope(json.dumps({"findings": rows}), "length"))
            self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
            self.assertEqual(outcome.diagnostic["category"], "truncated")
            self.assertEqual(outcome.diagnostic["schema"], "invalid")
            self.assertEqual(bool(outcome.findings), bool(rows))

    def test_valid_findings_about_rate_limits_complete(self) -> None:
        outcome = self.run_response(self.envelope(json.dumps({"findings": [finding("high", "rate_limit defect")]})))
        self.assertEqual(outcome.status, sd_review.FINDINGS)
        self.assertEqual(outcome.diagnostic["schema"], "valid")

    def test_fenced_or_invalid_json_is_visible_without_text_disclosure(self) -> None:
        for content in ("```json\n{\"findings\": []}\n```", "rate_limit credential-marker"):
            outcome = self.run_response(self.envelope(content))
            self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
            self.assertEqual(outcome.diagnostic["schema"], "unparseable")
            self.assertNotIn(content, json.dumps(outcome.diagnostic))

    def test_schema_failure_preserves_adverse_evidence(self) -> None:
        row = finding("high", "blocker")
        row["extra"] = "untrusted"
        outcome = self.run_response(self.envelope(json.dumps({"findings": [row]})))
        self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
        self.assertEqual(outcome.findings[0]["summary"], "blocker")
        self.assertIn("schema", outcome.diagnostic["validation_error"])

    def test_api_error_and_http_429_have_separate_diagnostics(self) -> None:
        payload = {"error": {"code": "rate_limit", "message": "credential-marker private-prompt-marker"}}
        successful_transport = self.run_response(payload)
        self.assertEqual(successful_transport.status, sd_review.UNAVAILABLE)
        self.assertEqual(successful_transport.diagnostic["category"], "api_error")
        limited = self.run_response(payload, 429, "HTTP 429 from url")
        self.assertEqual(limited.status, sd_review.RATE_LIMITED)
        self.assertEqual(limited.diagnostic["http_status"], 429)
        self.assertNotIn("credential-marker", json.dumps(limited.diagnostic))

    def test_malformed_or_deep_envelope_refuses_without_crashing(self) -> None:
        for payload in ("not JSON", "[" * 2000, [], {"choices": []}, {"choices": [{}]}):
            outcome = self.run_response(payload)
            self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
            self.assertIn(outcome.diagnostic["category"], ("invalid_json", "invalid_envelope"))

    def test_network_limit_is_nonpassing_and_explicitly_preserves_unknown_blockers(self) -> None:
        with mock.patch.object(sd_review.sd_registry, "MAX_RESPONSE_BYTES", 64):
            outcome = self.run_response("rate_limit " + "x" * 65)
        self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
        self.assertEqual(outcome.diagnostic["category"], "response_limit")
        self.assertEqual(outcome.findings[0]["severity"], "high")
        self.assertIn("omitted", outcome.findings[0]["summary"])

    def test_codex_answer_file_uses_a_bounded_read(self) -> None:
        provider = sd_review.sd_registry.Provider(name="fixture", vendor="fixture", bill="free",
            start="fixture exec", reader="codex-json")
        original = pathlib.Path.read_text

        def refuse_unbounded(path: pathlib.Path, *args, **kwargs):
            self.assertNotEqual(path.name, sd_review.CODEX_ANSWER_FILE)
            return original(path, *args, **kwargs)

        def reply(argv, env, cwd, timeout):
            target = pathlib.Path(argv[argv.index("--output-last-message") + 1])
            target.write_text("x" * 101)
            return sd_review.Completed(0, "", "")

        with mock.patch.object(sd_review, "MAX_OUTPUT_BYTES", 100), mock.patch.object(pathlib.Path, "read_text", refuse_unbounded):
            outcome = sd_review.run_provider(provider, self.tmp,
                sd_review.Subject("worktree", "HEAD", "worktree", (), 0, ""), "review", reply,
                self.environment(), 5, self.chatgpt_home())
        self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
        self.assertEqual(outcome.findings[0]["severity"], "high")


class WireBounds(unittest.TestCase):
    def test_success_and_error_reads_are_bounded(self) -> None:
        registry = sd_review.sd_registry
        provider = registry.Provider(name="url", vendor="fixture", bill="free",
            url="https://fixture.example/v1", model="fixture", env=("OWN_KEY",))
        for code in (0, 429):
            class Body(io.BytesIO):
                def __init__(self):
                    super().__init__(b"x" * 1000)
                    self.sizes = []
                def read(self, size=-1):
                    self.sizes.append(size)
                    return super().read(size)
            body = Body()
            error = urllib.error.HTTPError(provider.url, code, "fixture", {}, body) if code else None
            with mock.patch.object(registry, "MAX_RESPONSE_BYTES", 64), mock.patch.object(
                registry._OPENER, "open", side_effect=error if code else None, return_value=body
            ):
                result = registry.chat_completion(provider, "private-prompt-marker", {"OWN_KEY": "credential-marker"}, 7)
            self.assertEqual(body.sizes, [65])
            self.assertTrue(body.closed)
            self.assertEqual(len(result[1].encode()), 65)
            self.assertNotEqual(result[0], 0)
            self.assertNotIn("private-prompt-marker", result[2])
            self.assertNotIn("credential-marker", result[2])
