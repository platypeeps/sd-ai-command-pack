"""Local-only acceptance for ordered review attempts and provider isolation."""

from __future__ import annotations

import json
import os
import pathlib
import pwd
import subprocess
import sys
from typing import Any

from sd_db import connect, initialise, read_registry, seed

from tests.test_sd_review import (
    FakeClient,
    FakeRunner,
    ReviewFixture,
    chat_answer,
    namespace,
    sd_review,
)


def finding(severity: str = "high") -> str:
    return json.dumps({"findings": [{"path": "src.py", "line": 1,
                                    "severity": severity, "summary": "defect", "family": "correctness"}]})


class ReviewRunFixture(ReviewFixture):
    def prepare(self, tier: str = "cheap") -> pathlib.Path:
        root = self.make_repo()
        (root / "src.py").write_text("the_review_subject = 123\n")
        (root / ".github").mkdir()
        (root / ".github/sd-review.json").write_text(json.dumps({"default_tier": tier}))
        return root

    def run_review(self, root: pathlib.Path, runner: FakeRunner, **options: Any) -> dict[str, Any]:
        return sd_review.review(root, namespace(**options), runner,
                                self.environment(), self.chatgpt_home())


class FallbackTests(ReviewRunFixture):
    def alternatives(self, root: pathlib.Path, first: str, second: str) -> None:
        registry = self.registry_home / ".local/share/sd/providers.yaml"
        registry.write_text("bills:\n  fixture: {cost: subscription}\nproviders:\n"
            "  claude: {start: 'claude exec', vendor: anthropic, bill: fixture, roles: [reviewer], reader: claude-json}\n"
            + "".join(f"  {name}: {{url: 'https://{name}.example.test/v1', model: fixture, vendor: {name}, "
                      "bill: fixture, roles: [reviewer], env: [REMOTE_KEY]}\n" for name in (first, second))
            + f"roles:\n  author: []\n  reviewer: [claude, {first}, {second}]\n")
        (root / "CLAUDE.local.md").write_text("<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\n"
            f"reviewers: claude@claude, {first}@{first}.example.test, {second}@{second}.example.test\n"
            "<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n")

    def review_alternatives(self, root: pathlib.Path, client: FakeClient) -> dict[str, Any]:
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")}, default=sd_review.Completed(
            0, json.dumps({"type": "result", "subtype": "success", "structured_output": {"findings": []}}), ""))
        return sd_review.review(root, namespace(), runner, self.environment(REMOTE_KEY="fixture"), client=client)

    def test_minimax_and_kimi_replace_each_other_until_two_reviews_complete(self) -> None:
        root = self.prepare("deep")
        for first, second in (("minimax", "kimi"), ("kimi", "minimax")):
            with self.subTest(order=(first, second)):
                self.alternatives(root, first, second)
                client = FakeClient({first: (1, "", "transport failed", True)})
                result = self.review_alternatives(root, client)
                self.assertEqual(result["status"], "clean")
                self.assertEqual((result["requested_reviews"], result["completed_reviews"]), (2, 2))
                self.assertEqual(result["reviewed_by"], ["claude", second])
                self.assertEqual([row["provider"] for row in client.sent], [first, second])
                self.assertEqual([row["backend"] for row in result["outcomes"]], ["claude", first, second])

    def test_successful_alternative_stops_without_calling_its_fallback(self) -> None:
        root = self.prepare("deep")
        for first, second in (("minimax", "kimi"), ("kimi", "minimax")):
            with self.subTest(order=(first, second)):
                self.alternatives(root, first, second)
                client = FakeClient()
                result = self.review_alternatives(root, client)
                self.assertEqual(result["status"], "clean")
                self.assertEqual(result["reviewed_by"], ["claude", first])
                self.assertEqual([row["provider"] for row in client.sent], [first])

    def test_failed_alternative_keeps_adverse_findings_after_clean_fallback(self) -> None:
        root = self.prepare("deep")
        self.alternatives(root, "minimax", "kimi")
        response = chat_answer(finding())
        result = self.review_alternatives(root, FakeClient({"minimax": (1, response[1], "transport failed", True)}))
        self.assertEqual(result["status"], "blocking")
        self.assertEqual(result["reviewed_by"], ["claude", "kimi"])
        self.assertEqual(result["findings"][0]["backend"], "minimax")

    def test_one_completed_review_does_not_satisfy_the_two_review_standard(self) -> None:
        root = self.prepare("deep")
        self.alternatives(root, "minimax", "kimi")
        result = self.review_alternatives(root, FakeClient({
            name: (1, "", "transport failed", True) for name in ("minimax", "kimi")}))
        self.assertEqual((result["requested_reviews"], result["completed_reviews"]), (2, 1))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reviewed_by"], ["claude"])

    def test_each_availability_failure_uses_the_next_entry_and_records_it(self) -> None:
        root = self.prepare()
        failures = [sd_review.Completed(429, "", "HTTP 429"),
                    sd_review.Completed(127, "", "not found", False),
                    sd_review.Completed(1, "", "authentication failed"),
                    sd_review.Completed(1, "", "runtime failed"),
                    sd_review.Completed(124, "", "timeout", False),
                    sd_review.Completed(0, "invalid output", "")]
        for failure in failures:
            with self.subTest(failure=failure):
                runner = FakeRunner({"codex": failure})
                result = self.run_review(root, runner)
                self.assertEqual(result["status"], "clean")
                self.assertEqual([r["backend"] for r in result["outcomes"]], ["codex", "second"])
                self.assertEqual(result["reviewed_by"], ["second"])
                self.assertEqual(result["remaining"], [])

    def test_a_direct_pick_never_falls_back(self) -> None:
        root = self.prepare()
        runner = FakeRunner({"codex": sd_review.Completed(429, "", "HTTP 429")})
        result = self.run_review(root, runner, provider="codex")
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual([r["backend"] for r in result["outcomes"]], ["codex"])
        self.assertEqual(result["reviewed_by"], [])

    def test_authentication_preflight_failure_falls_through_to_another_protocol(self) -> None:
        root = self.prepare()
        path = self.registry_home / ".local/share/sd/providers.yaml"
        path.write_text(path.read_text().replace(
            "roles: [author, reviewer], reader: codex-json", "roles: [author, reviewer], reader: claude-json"))
        runner = FakeRunner({"second": sd_review.Completed(0, json.dumps({"type": "result", "subtype": "success",
                                  "structured_output": {"findings": []}}), "")})
        result = sd_review.review(root, namespace(), runner, self.environment(), self.tmp / "missing-auth")
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["outcomes"][0]["status"], sd_review.REFUSED)
        self.assertEqual(result["reviewed_by"], ["second"])
        self.assertNotIn("codex", [call["argv"][0] for call in runner.calls])

    def test_fallback_reaches_beyond_the_initial_depth_slice(self) -> None:
        root = self.prepare("standard")
        path = self.registry_home / ".local/share/sd/providers.yaml"
        text = path.read_text().replace("roles:\n  author:", "  third: { start: 'third exec', vendor: thirdvendor, bill: second, roles: [reviewer], reader: codex-json }\n\nroles:\n  author:")
        path.write_text(text.replace("reviewer: [codex, second]", "reviewer: [codex, second, third]"))
        local = root / "CLAUDE.local.md"
        local.write_text(local.read_text().replace("second@second", "second@second, third@third"))
        result = self.run_review(root, FakeRunner({"codex": sd_review.Completed(1, "", "failed")}))
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["reviewed_by"], ["second", "third"])
        self.assertEqual(result["completed_reviews"], 2)

    def test_successful_adverse_review_does_not_trigger_a_replacement(self) -> None:
        root = self.prepare()
        for severity, status in (("high", "blocking"), ("low", "advisory")):
            with self.subTest(severity=severity):
                result = self.run_review(root, FakeRunner({"codex": sd_review.Completed(0, finding(severity), "")}))
                self.assertEqual(result["status"], status)
                self.assertEqual(result["reviewed_by"], ["codex"])
                self.assertEqual([r["backend"] for r in result["outcomes"]], ["codex"])

    def test_failed_process_findings_survive_a_clean_fallback(self) -> None:
        root = self.prepare()
        result = self.run_review(root, FakeRunner({"codex": sd_review.Completed(1, finding(), "failed after answer")}))
        self.assertEqual(result["status"], "blocking")
        self.assertEqual(result["reviewed_by"], ["second"])
        self.assertEqual(result["findings"][0]["backend"], "codex")

    def test_invalid_review_evidence_survives_a_clean_fallback(self) -> None:
        root = self.prepare()
        for payload in (finding("HIGH"), '{"findings":[{"severity":"high","summary":"blocker with missing location"}]}', json.dumps({"findings":
                json.loads(finding("low"))["findings"] * 50 + json.loads(finding())["findings"]})):
            with self.subTest(payload=payload[:100]):
                result = self.run_review(root, FakeRunner({"codex": sd_review.Completed(0, payload, "")}))
                self.assertEqual(result["status"], "blocking")
                self.assertEqual(result["reviewed_by"], ["second"])
                self.assertEqual(result["outcomes"][0]["status"], sd_review.UNAVAILABLE)
                self.assertTrue(any(row["severity"] == "high" for row in result["findings"]))

    def test_fallback_never_expands_repository_consent(self) -> None:
        root = self.prepare()
        local = root / "CLAUDE.local.md"
        local.write_text(local.read_text().replace(", second@second", ""))
        result = self.run_review(root, FakeRunner({"codex": sd_review.Completed(1, "", "failed")}))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual([r["backend"] for r in result["outcomes"]], ["codex"])

    def test_same_vendor_is_skipped_and_an_explicit_same_vendor_pick_refuses(self) -> None:
        root = self.prepare()
        for argv in (["checkout", "-b", "topic"], ["add", "."],
                     ["commit", "-m", "change\n\nAuthored-with: codex/openai"]):
            subprocess.run(["git", *argv], cwd=root, check=True, capture_output=True)
        result = self.run_review(root, FakeRunner(), scope="branch")
        self.assertEqual(result["reviewed_by"], ["second"])
        self.assertEqual(result["authored_with"], ["openai"])
        with self.assertRaises(sd_review.sd_registry.ConsentRefusal):
            self.run_review(root, FakeRunner(), scope="branch", provider="codex")


class ProviderEnvironmentTests(ReviewFixture):
    def test_a_real_child_gets_only_declared_variables_and_verified_auth_home(self) -> None:
        program = self.tmp / "fixture.py"
        receipt = self.tmp / "child-env.json"
        program.write_text("import json, os\nfrom pathlib import Path\n"
                           f"Path({str(receipt)!r}).write_text(json.dumps(dict(os.environ)))\n"
                           "print('{\"findings\": []}')\n")
        provider = sd_review.sd_registry.Provider(
            name="fixture", vendor="openai", bill="first", reader="codex-json",
            start=f"{sys.executable} {program}", env=("OWN_KEY", "CODEX_API_KEY"))
        home = self.chatgpt_home()
        outcome = sd_review.run_provider(provider, self.tmp,
            sd_review.Subject("worktree", "HEAD", "worktree", (), 0, ""), "review",
            sd_review.subprocess_runner,
            {"PATH": "/usr/bin:/bin", "HOME": str(self.registry_home), "OWN_KEY": "fixture-own",
             "OTHER_KEY": "fixture-other", "CODEX_API_KEY": "fixture-metered",
             "BASH_ENV": "/untrusted/startup", "CODEX_HOME": "/unchecked/auth"}, 5, home)
        self.assertEqual(outcome.status, sd_review.CLEAN)
        handed = json.loads(receipt.read_text())
        self.assertEqual(handed["OWN_KEY"], "fixture-own")
        self.assertEqual(handed["CODEX_HOME"], str(home))
        for name in ("OTHER_KEY", "CODEX_API_KEY", "BASH_ENV"):
            self.assertNotIn(name, handed)

    def test_url_transport_receives_its_key_and_the_actual_subject(self) -> None:
        root = self.make_repo()
        (root / "src.py").write_text("exact_source_marker = 456\n")
        provider = sd_review.sd_registry.Provider(name="remote", vendor="remote", bill="first",
                        url="https://api.example.test/v1", model="fixture", env=("OWN_KEY",))
        client = FakeClient()
        outcome = sd_review.run_provider(provider, root, sd_review.resolve_subject(root, "worktree"),
                    "review", FakeRunner(), self.environment(OWN_KEY="mine", OTHER_KEY="not-mine"), 5,
                    client=client)
        self.assertEqual(outcome.status, sd_review.CLEAN)
        self.assertEqual(client.sent[0]["env"], self.environment(OWN_KEY="mine", USER=pwd.getpwuid(os.getuid()).pw_name))
        self.assertIn("exact_source_marker = 456", client.sent[0]["prompt"])

    def test_untracked_symlinks_expose_the_link_not_external_file_contents(self) -> None:
        root = self.make_repo()
        external = self.tmp / "outside.txt"
        external.write_text("private fixture content must not be sent")
        (root / "linked.txt").symlink_to(external)
        material = sd_review.review_material(root, sd_review.resolve_subject(root, "worktree"))
        self.assertIn(f"symlink -> {external}", material)
        self.assertNotIn(external.read_text(), material)


class DatabaseProviderStateTests(ReviewRunFixture):
    def prepare_state(self) -> tuple[pathlib.Path, pathlib.Path]:
        root = self.prepare()
        path = self.registry_home / ".local/share/sd/providers.yaml"
        text = path.read_text().replace("roles:\n  author:", "  third: { start: 'third exec', vendor: thirdvendor, bill: second, roles: [reviewer], reader: codex-json }\n\nroles:\n  author:")
        path.write_text(text.replace("reviewer: [codex, second]", "reviewer: [codex, second, third]"))
        local = root / "CLAUDE.local.md"
        local.write_text(local.read_text().replace("second@second", "second@second, third@third"))
        database = path.parent / "sd.db"
        initialise(database)
        connection = connect(database)
        try:
            seed(connection, read_registry(path))
        finally:
            connection.close()
        return root, database

    def test_row_reordering_and_disable_changes_control_the_real_review_chain(self) -> None:
        root, database = self.prepare_state()
        connection = connect(database)
        try:
            connection.execute("UPDATE provider SET reviewer_rank=10 WHERE name='codex'")
            connection.execute("UPDATE provider SET reviewer_rank=0 WHERE name='third'")
        finally:
            connection.close()
        before = database.read_bytes()
        result = self.run_review(root, FakeRunner())
        self.assertEqual(result["reviewed_by"], ["third"])
        self.assertEqual(database.read_bytes(), before, "provider resolution must not write the database")
        connection = connect(database)
        try:
            connection.execute("UPDATE provider SET enabled=0 WHERE name='third'")
            connection.execute("UPDATE provider SET reviewer_rank=0 WHERE name='codex'")
        finally:
            connection.close()
        result = self.run_review(root, FakeRunner())
        self.assertEqual(result["reviewed_by"], ["codex"])
        self.assertNotIn("third", [row["provider"] for row in result["chain"]])
        with self.assertRaises(sd_review.sd_registry.RegistryError):
            self.run_review(root, FakeRunner(), provider="third")

    def test_missing_database_uses_file_pins_without_creating_a_database(self) -> None:
        root = self.prepare()
        result = self.run_review(root, FakeRunner())
        self.assertEqual(result["reviewed_by"], ["codex"])
        self.assertFalse((self.registry_home / ".local/share/sd/sd.db").exists())

    def test_an_alternate_registry_file_still_reads_the_operator_database(self) -> None:
        _, database = self.prepare_state()
        alternate = self.tmp / "alternate-providers.yaml"
        alternate.write_text((self.registry_home / ".local/share/sd/providers.yaml").read_text())
        connection = connect(database)
        try:
            connection.execute("UPDATE provider SET enabled=0 WHERE name='third'")
        finally:
            connection.close()
        registry = sd_review.sd_registry.read_runtime(alternate, home=self.registry_home)
        self.assertFalse(registry.providers["third"].enabled)

    def test_unreadable_database_refuses_instead_of_ignoring_its_controls(self) -> None:
        root = self.prepare()
        (self.registry_home / ".local/share/sd/sd.db").write_bytes(b"invalid fixture database")
        runner = FakeRunner()
        result = self.run_review(root, runner)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("cannot read provider state", result["registry_refusal"])
        self.assertEqual(result["outcomes"], [])


class ClaudeReaderTests(ReviewFixture):
    def test_typed_quota_errors_preserve_their_classification(self) -> None:
        for fields in ({"errors": ["API Error: rate limit reached"]},
                       {"api_error_status": 429, "result": "request rejected"},
                       {"result": "API Error: rate limit reached"}):
            with self.subTest(fields=fields):
                result, parsed = sd_review.claude_answer(sd_review.Completed(0, json.dumps({
                    "type": "result", "subtype": "error_during_execution", "is_error": True, **fields}), ""))
                self.assertEqual(sd_review._answer("claude", result, parsed).status, sd_review.RATE_LIMITED)

    def test_successful_model_quota_text_and_untyped_status_do_not_fake_an_error(self) -> None:
        for fields in ({"result": "rate limit reached"}, {"errors": ["rate limit reached"]},
                       {"api_error_status": 429}):
            with self.subTest(fields=fields):
                result, parsed = sd_review.claude_answer(sd_review.Completed(0, json.dumps({
                    "type": "result", "subtype": "success", "is_error": False,
                    "structured_output": {"findings": []}, **fields}), ""))
                self.assertEqual(sd_review._answer("claude", result, parsed).status, sd_review.CLEAN)

    def test_typed_nonquota_or_malformed_errors_remain_unavailable(self) -> None:
        for fields in ({"errors": ["request rejected"]}, {"errors": "rate limit reached"},
                       {"errors": [{"message": "rate limit reached"}]}, {"api_error_status": "429"},
                       {"api_error_status": 429.0}):
            with self.subTest(fields=fields):
                result, parsed = sd_review.claude_answer(sd_review.Completed(0, json.dumps({
                    "type": "result", "subtype": "error_during_execution", "is_error": True, **fields}), ""))
                self.assertEqual(sd_review._answer("claude", result, parsed).status, sd_review.UNAVAILABLE)

    def test_quota_metadata_does_not_discard_adverse_findings(self) -> None:
        result, parsed = sd_review.claude_answer(sd_review.Completed(0, json.dumps({
            "type": "result", "subtype": "success", "is_error": True, "api_error_status": 429,
            "structured_output": json.loads(finding())}), ""))
        outcome = sd_review._answer("claude", result, parsed)
        self.assertEqual(outcome.status, sd_review.RATE_LIMITED)
        self.assertEqual(outcome.findings[0]["severity"], "high")

    def execute(self, envelope: Any, exit_code: int = 0) -> tuple[Any, list[dict[str, Any]]]:
        root = self.make_repo()
        (root / "src.py").write_text("claude_exact_subject = True\n")
        provider = sd_review.sd_registry.Provider(name="claude", vendor="anthropic", bill="first",
                        start="claude -p", reader="claude-json", env=())
        calls: list[dict[str, Any]] = []

        def reply(argv: Any, env: Any, cwd: Any, timeout: Any) -> Any:
            material = pathlib.Path(argv[argv.index("--add-dir") + 1]) / "review-subject.md"
            calls.append({"argv": argv, "env": env, "material": material.read_text()})
            return sd_review.Completed(exit_code, json.dumps(envelope), "")

        outcome = sd_review.run_provider(provider, root, sd_review.resolve_subject(root, "worktree"),
            "instructions", reply, self.environment(OTHER_KEY="fixture-unrelated"), 5)
        return outcome, calls

    def test_structured_output_runs_with_read_only_tools_and_exact_subject(self) -> None:
        outcome, calls = self.execute({"type": "result", "subtype": "success", "is_error": False,
                                      "structured_output": {"findings": []}})
        self.assertEqual(outcome.status, sd_review.CLEAN)
        argv = calls[0]["argv"]
        for flag in ("--safe-mode", "--restricted", "--strict-mcp-config", "--no-session-persistence"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Grep,Glob")
        self.assertNotIn("OTHER_KEY", calls[0]["env"])
        self.assertIn("claude_exact_subject = True", calls[0]["material"])

    def test_structured_blocking_findings_survive_an_error_envelope(self) -> None:
        outcome, _ = self.execute({"type": "result", "subtype": "error_during_execution", "is_error": True,
                                  "structured_output": json.loads(finding())})
        self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
        self.assertEqual(outcome.findings[0]["severity"], "high")

    def test_missing_structured_output_and_error_envelopes_are_not_clean(self) -> None:
        for i, envelope in enumerate(({}, {"type": "result", "subtype": "success", "result": "clean"},
                                     {"type": "result", "subtype": "error_max_turns", "is_error": True,
                                      "structured_output": {"findings": []}},
                                     {"type": "result", "subtype": "success", "is_error": False,
                                      "structured_output": {"findings": [{"summary": "missing path"}]}})):
            with self.subTest(envelope=envelope):
                # Each execution owns a fresh fixture repository.
                self.tmp = self.tmp / f"case-{i}"
                self.tmp.mkdir()
                outcome, _ = self.execute(envelope)
                self.assertNotEqual(outcome.status, sd_review.CLEAN)


class SchemaAcrossTransportsTests(ReviewFixture):
    def execute(self, transport: str, payload: dict[str, Any]) -> Any:
        provider = sd_review.sd_registry.Provider(name="fixture", vendor="fixture", bill="first",
            start=None if transport == "url" else "fixture exec",
            url="https://fixture.example/v1" if transport == "url" else None,
            reader=None if transport == "url" else transport)
        envelope = ({"type": "result", "subtype": "success", "is_error": False,
                     "structured_output": payload} if transport == "claude-json" else payload)
        client = FakeClient(default=(0, json.dumps({"choices": [{"message": {"content": json.dumps(payload)}}]}), "", True))
        return sd_review.run_provider(provider, self.tmp,
            sd_review.Subject("worktree", "HEAD", "worktree", (), 0, ""), "review",
            FakeRunner(default=sd_review.Completed(0, json.dumps(envelope), "")), self.environment(), 5,
            self.chatgpt_home(), client)

    def test_schema_violations_never_complete_a_review_on_any_transport(self) -> None:
        valid = json.loads(finding())["findings"][0]
        invalid_rows = [{"summary": "missing path"}, {**valid, "severity": "HIGH"},
                        {"severity": "high", "summary": "blocker with missing location"},
                        {**valid, "line": True}, {**valid, "line": "1"},
                        {**valid, "family": None}, {**valid, "unexpected": "extra"},
                        {key: value for key, value in valid.items() if key != "family"}]
        payloads = [{"findings": [row]} for row in invalid_rows]
        payloads += [{"findings": [], "unexpected": "extra"},
                     {"findings": json.loads(finding("low"))["findings"] * 50 + [valid]},
                     {"findings": [{**valid, "summary": "x" * (sd_review.MAX_OUTPUT_BYTES + 1)}]}]
        for transport in sd_review.READERS + ("url",):
            for payload in payloads:
                with self.subTest(transport=transport, keys=list(payload), rows=len(payload["findings"])):
                    outcome = self.execute(transport, payload)
                    self.assertEqual(outcome.status, sd_review.UNAVAILABLE)
                    if any(row.get("severity", "").lower() == "high" for row in payload["findings"]):
                        self.assertTrue(any(row["severity"] == "high" for row in outcome.findings))

    def test_valid_blocking_answers_still_complete_on_each_transport(self) -> None:
        for transport in sd_review.READERS + ("url",):
            with self.subTest(transport=transport):
                outcome = self.execute(transport, json.loads(finding()))
                self.assertEqual(outcome.status, sd_review.FINDINGS)
                self.assertEqual(outcome.findings[0]["severity"], "high")
