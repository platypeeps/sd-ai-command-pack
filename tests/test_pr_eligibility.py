from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import install

SCRIPT_PATH = install.ROOT / "scripts/sd-ai-command-pack-pr-eligibility.py"
SPEC = importlib.util.spec_from_file_location("sd_ai_command_pack_pr_eligibility", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT_PATH}")
eligibility = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = eligibility
sys.path.insert(0, str(SCRIPT_PATH.parent))
try:
    SPEC.loader.exec_module(eligibility)
finally:
    sys.path.pop(0)

HEAD = "1" * 40
OTHER_HEAD = "2" * 40


def finish_work_receipt(
    *,
    head: str = HEAD,
    branch: str = "feature/eligibility",
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "kind": "trellis-bookkeeping-validation",
        "status": "valid",
        "command": "final-bundle",
        "mode": "completion",
        "reasonCodes": ["completion_bundle_valid"],
        "evidence": {
            "baseOid": head,
            "headOid": head,
            "taskDirectories": [
                ".trellis/tasks/archive/2026-07/07-25-eligibility"
            ],
            "changedPaths": [],
            "repository": {
                "branch": branch,
                "rootDigest": f"sha256:{'a' * 64}",
            },
            "journalSessions": [],
            "completionSubtype": "post-archive-review-successor",
        },
        "findings": [],
    }


def check_run(
    conclusion: str | None,
    *,
    status: str = "COMPLETED",
    name: str = "ci",
) -> dict[str, Any]:
    return {
        "__typename": "CheckRun",
        "name": name,
        "workflowName": "CI",
        "status": status,
        "conclusion": conclusion,
        "detailsUrl": "https://example.test/check",
    }


def thread_page(
    nodes: list[bool],
    *,
    has_next: bool = False,
    cursor: str | None = None,
) -> dict[str, Any]:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [{"isResolved": value} for value in nodes],
                        "pageInfo": {
                            "hasNextPage": has_next,
                            "endCursor": cursor,
                        },
                    }
                }
            }
        }
    }


class FixtureRunner:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.local_heads = [HEAD, HEAD]
        self.pr_head_result: Any | None = None
        self.remote_head = HEAD
        self.git_status = ""
        self.git_status_returncode = 0
        self.remote_returncode = 0
        self.pr_failure = False
        self.finish_work_result = finish_work_receipt()
        self.finish_work_returncode = 0
        self.thread_failure = False
        self.thread_pages = [thread_page([])]
        self.pr_payload: dict[str, Any] = {
            "number": 42,
            "state": "OPEN",
            "isDraft": False,
            "url": "https://example.test/pr/42",
            "headRefName": "feature/eligibility",
            "headRefOid": HEAD,
            "baseRefName": "main",
            "mergeStateStatus": "CLEAN",
            "statusCheckRollup": [check_run("SUCCESS")],
        }
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self, argv: list[str] | tuple[str, ...], cwd: Path, timeout: int
    ) -> Any:
        del cwd, timeout
        args = tuple(argv)
        self.calls.append(args)
        if args == ("git", "rev-parse", "--show-toplevel"):
            return eligibility.CommandResult(0, f"{self.repo}\n")
        if args[:3] == ("git", "rev-parse", "--verify"):
            value = self.local_heads.pop(0) if self.local_heads else HEAD
            return eligibility.CommandResult(0, f"{value}\n")
        if args == ("git", "status", "--porcelain"):
            return eligibility.CommandResult(
                self.git_status_returncode, self.git_status
            )
        if args[:3] == ("git", "ls-remote", "--exit-code"):
            return eligibility.CommandResult(
                self.remote_returncode,
                f"{self.remote_head}\trefs/heads/feature/eligibility\n",
            )
        if args[:1] == ("node",):
            return eligibility.CommandResult(
                self.finish_work_returncode,
                json.dumps(self.finish_work_result),
            )
        if args[:3] == ("gh", "pr", "view"):
            if self.pr_failure:
                return eligibility.CommandResult(1, "")
            if args[-1] == "headRefOid":
                if self.pr_head_result is not None:
                    return self.pr_head_result
                return eligibility.CommandResult(
                    0, json.dumps({"headRefOid": self.pr_payload["headRefOid"]})
                )
            return eligibility.CommandResult(0, json.dumps(self.pr_payload))
        if args[:3] == ("gh", "api", "graphql"):
            if self.thread_failure:
                return eligibility.CommandResult(1, "")
            page = self.thread_pages.pop(0)
            return eligibility.CommandResult(0, json.dumps(page))
        return eligibility.CommandResult(127, "")


class PrEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-eligibility-"
        )
        self.addCleanup(self.tempdir.cleanup)
        self.repo = Path(self.tempdir.name).resolve()

    def local_request(self, **updates: Any) -> dict[str, Any]:
        request: dict[str, Any] = {
            "schemaVersion": 1,
            "mode": "local-branch",
            "repository": str(self.repo),
            "branch": "feature/eligibility",
            "pullRequestNumber": None,
            "remote": "origin",
            "defaultBranch": "main",
            "finishWorkRequired": True,
            "finishWorkReceipt": finish_work_receipt(),
            "githubRepository": "example/repo",
        }
        request.update(updates)
        return request

    def dependency_request(self, **updates: Any) -> dict[str, Any]:
        request: dict[str, Any] = {
            "schemaVersion": 1,
            "mode": "dependency-pr",
            "repository": str(self.repo),
            "branch": None,
            "pullRequestNumber": 42,
            "remote": "origin",
            "defaultBranch": "main",
            "finishWorkRequired": False,
            "finishWorkReceipt": None,
            "githubRepository": "example/repo",
        }
        request.update(updates)
        return request

    def evaluate(self, request: dict[str, Any], runner: FixtureRunner) -> dict[str, Any]:
        return eligibility.evaluate_request(
            request,
            runner=runner,
            now=lambda: "2026-07-23T00:00:00Z",
        )

    def test_local_branch_eligible_receipt_is_exact_head_and_read_only(self) -> None:
        runner = FixtureRunner(self.repo)
        result = self.evaluate(self.local_request(), runner)

        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["reasonCodes"], [])
        self.assertEqual(result["head"]["startOid"], HEAD)
        self.assertEqual(result["head"]["endOid"], HEAD)
        self.assertEqual(result["head"]["remoteOid"], HEAD)
        self.assertEqual(result["pullRequest"]["headOid"], HEAD)
        self.assertEqual(result["pullRequest"]["finalHeadOid"], HEAD)
        self.assertTrue(result["finishWork"]["matchesCurrentHead"])
        self.assertTrue(result["finishWork"]["verified"])
        self.assertEqual(
            result["finishWork"]["completionSubtype"],
            "post-archive-review-successor",
        )
        self.assertEqual(result["checks"]["successfulCount"], 1)
        self.assertEqual(result["reviewThreads"]["unresolvedCount"], 0)
        commands = {call[:3] for call in runner.calls}
        self.assertNotIn(("gh", "pr", "merge"), commands)
        self.assertFalse(any(call[:2] == ("git", "push") for call in runner.calls))
        self.assertEqual(
            [call for call in runner.calls if call[-1:] == ("headRefOid",)],
            [
                (
                    "gh",
                    "pr",
                    "view",
                    "42",
                    "--repo",
                    "example/repo",
                    "--json",
                    "headRefOid",
                )
            ],
        )

    def test_combined_adapter_preserves_json_and_shell_receipt(self) -> None:
        result = self.evaluate(self.local_request(), FixtureRunner(self.repo))

        json_line, shell_line = eligibility.render_json_shell(result).splitlines()

        self.assertEqual(json.loads(json_line), result)
        self.assertEqual(shell_line, eligibility.render_shell(result))
        self.assertNotIn("\n", json_line)

    def test_skipped_and_neutral_checks_do_not_block(self) -> None:
        runner = FixtureRunner(self.repo)
        runner.pr_payload["statusCheckRollup"] = [
            check_run("SUCCESS"),
            check_run("SKIPPED", name="skip"),
            check_run("NEUTRAL", name="neutral"),
        ]
        result = self.evaluate(self.local_request(), runner)
        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["checks"]["blockingCount"], 0)

    def test_blocking_check_returns_stable_blocked_reason(self) -> None:
        runner = FixtureRunner(self.repo)
        runner.pr_payload["statusCheckRollup"] = [
            check_run("SUCCESS"),
            check_run("FAILURE", name="red"),
        ]
        result = self.evaluate(self.local_request(), runner)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasonCodes"], ["checks_blocking"])

    def test_missing_and_stale_finish_work_receipts_are_blocked(self) -> None:
        missing = self.evaluate(
            self.local_request(finishWorkReceipt=None), FixtureRunner(self.repo)
        )
        stale = self.evaluate(
            self.local_request(
                finishWorkReceipt=finish_work_receipt(head=OTHER_HEAD)
            ),
            FixtureRunner(self.repo),
        )
        self.assertEqual(missing["reasonCodes"], ["finish_work_missing"])
        self.assertEqual(stale["reasonCodes"], ["finish_work_stale"])

    def test_forged_or_unavailable_finish_work_receipt_fails_closed(self) -> None:
        mismatch_runner = FixtureRunner(self.repo)
        mismatch_runner.finish_work_result = finish_work_receipt()
        mismatch_runner.finish_work_result["evidence"]["taskDirectories"] = []
        mismatch = self.evaluate(self.local_request(), mismatch_runner)
        self.assertEqual(mismatch["status"], "blocked")
        self.assertEqual(
            mismatch["reasonCodes"], ["finish_work_receipt_mismatch"]
        )
        self.assertFalse(
            any(call[:1] == ("gh",) for call in mismatch_runner.calls)
        )

        invalid_runner = FixtureRunner(self.repo)
        invalid_runner.finish_work_returncode = 1
        invalid_runner.finish_work_result = {
            **finish_work_receipt(),
            "status": "invalid",
            "reasonCodes": ["completion_successor_scope_invalid"],
        }
        invalid = self.evaluate(self.local_request(), invalid_runner)
        self.assertEqual(invalid["status"], "blocked")
        self.assertEqual(invalid["reasonCodes"], ["finish_work_invalid"])
        self.assertFalse(
            any(call[:1] == ("gh",) for call in invalid_runner.calls)
        )

        unavailable_runner = FixtureRunner(self.repo)
        unavailable_runner.finish_work_returncode = 127
        unavailable_runner.finish_work_result = {}
        unavailable = self.evaluate(self.local_request(), unavailable_runner)
        self.assertEqual(unavailable["status"], "indeterminate")
        self.assertEqual(unavailable["reasonCodes"], ["finish_work_unavailable"])
        self.assertFalse(
            any(call[:1] == ("gh",) for call in unavailable_runner.calls)
        )

        indeterminate_runner = FixtureRunner(self.repo)
        indeterminate_runner.finish_work_returncode = 1
        indeterminate_runner.finish_work_result = {
            **finish_work_receipt(),
            "status": "indeterminate",
            "reasonCodes": ["completion_successor_history_unavailable"],
        }
        indeterminate = self.evaluate(self.local_request(), indeterminate_runner)
        self.assertEqual(indeterminate["status"], "indeterminate")
        self.assertEqual(
            indeterminate["reasonCodes"], ["finish_work_unavailable"]
        )
        self.assertFalse(
            any(call[:1] == ("gh",) for call in indeterminate_runner.calls)
        )

    def test_head_change_overrides_other_evidence_as_retryable(self) -> None:
        runner = FixtureRunner(self.repo)
        runner.local_heads = [HEAD, OTHER_HEAD]
        result = self.evaluate(self.local_request(), runner)
        self.assertEqual(result["status"], "indeterminate")
        self.assertEqual(result["reasonCodes"], ["head_changed"])
        self.assertTrue(result["retryable"])
        self.assertEqual(result["pullRequest"]["finalHeadOid"], HEAD)

    def test_pr_head_change_overrides_stable_local_head_as_retryable(self) -> None:
        runner = FixtureRunner(self.repo)
        runner.pr_head_result = eligibility.CommandResult(
            0, json.dumps({"headRefOid": OTHER_HEAD})
        )
        result = self.evaluate(self.local_request(), runner)

        self.assertEqual(result["status"], "indeterminate")
        self.assertEqual(result["reasonCodes"], ["head_changed"])
        self.assertTrue(result["retryable"])
        self.assertEqual(result["head"]["endOid"], HEAD)
        self.assertEqual(result["pullRequest"]["headOid"], HEAD)
        self.assertEqual(result["pullRequest"]["finalHeadOid"], OTHER_HEAD)
        self.assertIn("PR #42 changed", result["diagnostic"])

    def test_final_pr_head_unavailable_payloads_fail_closed(self) -> None:
        scenarios = (
            (eligibility.CommandResult(1, ""), "provider failure"),
            (eligibility.CommandResult(127, ""), "timeout equivalent"),
            (eligibility.CommandResult(0, "{"), "malformed JSON"),
            (eligibility.CommandResult(0, "[]"), "non-object JSON"),
            (eligibility.CommandResult(0, "{}"), "missing field"),
            (
                eligibility.CommandResult(0, json.dumps({"headRefOid": 42})),
                "invalid type",
            ),
            (
                eligibility.CommandResult(0, json.dumps({"headRefOid": "abc"})),
                "invalid OID",
            ),
        )
        for pr_head_result, label in scenarios:
            with self.subTest(label=label):
                runner = FixtureRunner(self.repo)
                runner.pr_head_result = pr_head_result
                result = self.evaluate(self.local_request(), runner)

                self.assertEqual(result["status"], "indeterminate")
                self.assertEqual(result["reasonCodes"], ["head_unavailable"])
                self.assertTrue(result["retryable"])
                self.assertEqual(result["head"]["endOid"], HEAD)
                self.assertIsNone(result["pullRequest"]["finalHeadOid"])
                self.assertIn("PR #42 head became unavailable", result["diagnostic"])

    def test_unresolved_threads_are_counted_across_pages(self) -> None:
        runner = FixtureRunner(self.repo)
        runner.thread_pages = [
            thread_page([True], has_next=True, cursor="PAGE2"),
            thread_page([False]),
        ]
        result = self.evaluate(self.local_request(), runner)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasonCodes"], ["review_threads_unresolved"])
        self.assertEqual(result["reviewThreads"]["pageCount"], 2)
        self.assertEqual(result["reviewThreads"]["unresolvedCount"], 1)

    def test_pr_and_thread_provider_failures_are_indeterminate(self) -> None:
        pr_runner = FixtureRunner(self.repo)
        pr_runner.pr_failure = True
        pr_result = self.evaluate(self.local_request(), pr_runner)
        thread_runner = FixtureRunner(self.repo)
        thread_runner.thread_failure = True
        thread_result = self.evaluate(self.local_request(), thread_runner)
        self.assertEqual(pr_result["reasonCodes"], ["pull_request_unavailable"])
        self.assertEqual(thread_result["reasonCodes"], ["review_threads_unavailable"])
        self.assertEqual(pr_result["status"], "indeterminate")
        self.assertEqual(thread_result["status"], "indeterminate")

    def test_malformed_check_payload_fails_closed(self) -> None:
        runner = FixtureRunner(self.repo)
        runner.pr_payload["statusCheckRollup"] = {"not": "a list"}
        result = self.evaluate(self.local_request(), runner)
        self.assertEqual(result["status"], "indeterminate")
        self.assertEqual(result["reasonCodes"], ["pull_request_unavailable"])

    def test_unknown_schema_and_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "schemaVersion"):
            eligibility.validate_request(self.local_request(schemaVersion=2))
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "unknown field"):
            eligibility.validate_request({**self.local_request(), "extra": True})

    def test_mode_specific_finish_work_policy_is_strict(self) -> None:
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "must be true"):
            eligibility.validate_request(
                self.local_request(
                    finishWorkRequired=False, finishWorkReceipt=None
                )
            )
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "must be false"):
            eligibility.validate_request(
                self.dependency_request(finishWorkRequired=True)
            )

    def test_dependency_mode_uses_pr_head_without_local_branch_mutation(self) -> None:
        runner = FixtureRunner(self.repo)
        result = self.evaluate(self.dependency_request(), runner)
        self.assertEqual(result["status"], "eligible")
        self.assertFalse(result["finishWork"]["required"])
        self.assertEqual(result["pullRequest"]["headOid"], HEAD)
        self.assertEqual(result["pullRequest"]["finalHeadOid"], HEAD)
        self.assertFalse(any(call[:2] == ("git", "status") for call in runner.calls))
        self.assertFalse(any(call[:2] == ("git", "ls-remote") for call in runner.calls))
        self.assertTrue(
            any(call[:3] == ("gh", "pr", "view") and call[-1] == "headRefOid" for call in runner.calls)
        )

    def test_dependency_mode_detects_rebased_head(self) -> None:
        runner = FixtureRunner(self.repo)
        runner.pr_head_result = eligibility.CommandResult(
            0, json.dumps({"headRefOid": OTHER_HEAD})
        )
        result = self.evaluate(self.dependency_request(), runner)
        self.assertEqual(result["status"], "indeterminate")
        self.assertEqual(result["reasonCodes"], ["head_changed"])
        self.assertTrue(result["retryable"])
        self.assertEqual(result["pullRequest"]["finalHeadOid"], OTHER_HEAD)

    def test_request_validation_rejects_unsafe_mode_specific_values(self) -> None:
        invalid_requests = (
            (None, "JSON object"),
            (self.local_request(mode="other"), "mode"),
            (self.local_request(pullRequestNumber=1), "must be null"),
            (self.dependency_request(branch="feature"), "must be null"),
            (self.dependency_request(pullRequestNumber=True), "positive integer"),
            (self.local_request(remote="--upload-pack=x"), "must not start"),
            (self.local_request(finishWorkRequired="yes"), "must be a boolean"),
            (self.local_request(finishWorkReceipt="ABC"), "JSON object"),
            (
                self.dependency_request(finishWorkReceipt=finish_work_receipt()),
                "must be null when finishWorkRequired is false",
            ),
            (self.local_request(githubRepository="not-a-slug"), "owner/repo"),
        )
        for request, diagnostic in invalid_requests:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaisesRegex(
                    eligibility.EligibilityInputError, diagnostic
                ):
                    eligibility.validate_request(request)

    def test_request_file_loader_accepts_json_and_rejects_unsafe_files(self) -> None:
        request_path = self.repo / "request.json"
        request_path.write_text(json.dumps(self.local_request()), encoding="utf-8")
        self.assertEqual(
            eligibility.load_request(request_path)["schemaVersion"], 1
        )

        request_path.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "cannot read"):
            eligibility.load_request(request_path)

        request_path.write_text("x" * (eligibility.MAX_INPUT_BYTES + 1), encoding="utf-8")
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "exceeds"):
            eligibility.load_request(request_path)

        link = self.repo / "request-link.json"
        link.symlink_to(request_path)
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "regular file"):
            eligibility.load_request(link)

    def test_finish_work_receipt_loader_is_strict_and_regular_file_only(self) -> None:
        receipt_path = self.repo / "finish-work.json"
        receipt_path.write_text(json.dumps(finish_work_receipt()), encoding="utf-8")
        self.assertEqual(
            eligibility.load_finish_work_receipt(receipt_path)["status"], "valid"
        )

        malformed = finish_work_receipt()
        malformed["evidence"]["repository"]["rootDigest"] = str(self.repo)
        receipt_path.write_text(json.dumps(malformed), encoding="utf-8")
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "rootDigest"):
            eligibility.load_finish_work_receipt(receipt_path)

        malformed = finish_work_receipt()
        malformed["evidence"]["completionSubtype"] = 7
        receipt_path.write_text(json.dumps(malformed), encoding="utf-8")
        with self.assertRaisesRegex(
            eligibility.EligibilityInputError, "completionSubtype.*non-empty string"
        ):
            eligibility.load_finish_work_receipt(receipt_path)

        malformed = finish_work_receipt()
        malformed["evidence"]["planningSubtype"] = "journal-only-recovery"
        receipt_path.write_text(json.dumps(malformed), encoding="utf-8")
        with self.assertRaisesRegex(
            eligibility.EligibilityInputError,
            "planningSubtype must be null in completion mode",
        ):
            eligibility.load_finish_work_receipt(receipt_path)

        planning = finish_work_receipt()
        planning["mode"] = "planning"
        planning["reasonCodes"] = ["planning_bundle_valid"]
        planning["evidence"].pop("completionSubtype")
        planning["evidence"]["planningSubtype"] = "journal-only-recovery"
        receipt_path.write_text(json.dumps(planning), encoding="utf-8")
        self.assertEqual(
            eligibility.load_finish_work_receipt(receipt_path)["mode"], "planning"
        )

        planning["evidence"]["completionSubtype"] = "post-archive-review-successor"
        receipt_path.write_text(json.dumps(planning), encoding="utf-8")
        with self.assertRaisesRegex(
            eligibility.EligibilityInputError,
            "completionSubtype must be null in planning mode",
        ):
            eligibility.load_finish_work_receipt(receipt_path)

        receipt_path.write_text(json.dumps(finish_work_receipt()), encoding="utf-8")
        link = self.repo / "finish-work-link.json"
        link.symlink_to(receipt_path)
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "regular file"):
            eligibility.load_finish_work_receipt(link)

    def test_parse_helpers_fail_closed_and_classify_status_contexts(self) -> None:
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "unavailable"):
            eligibility.parse_json_object(eligibility.CommandResult(1, ""), "fixture")
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "malformed"):
            eligibility.parse_json_object(eligibility.CommandResult(0, "{"), "fixture")
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "non-object"):
            eligibility.parse_json_object(eligibility.CommandResult(0, "[]"), "fixture")

        checks, blocking, successful = eligibility.parse_checks(
            [
                {"__typename": "StatusContext", "context": "legacy", "state": "SUCCESS"},
                {"__typename": "StatusContext", "context": "red", "state": "FAILURE"},
                check_run(None, status="IN_PROGRESS"),
            ]
        )
        self.assertEqual(len(checks), 3)
        self.assertEqual((blocking, successful), (2, 1))
        for malformed in ([None], [{"__typename": "Other"}], [{"__typename": "StatusContext", "state": 1}]):
            with self.subTest(malformed=malformed):
                with self.assertRaises(eligibility.EligibilityInputError):
                    eligibility.parse_checks(malformed)

    def test_local_branch_rejects_pr_identity_and_readiness_mismatches(self) -> None:
        scenarios = (
            ("state", "CLOSED", "pull_request_not_open"),
            ("isDraft", True, "pull_request_draft"),
            ("headRefName", "other", "pull_request_branch_mismatch"),
            ("baseRefName", "develop", "pull_request_base_mismatch"),
            ("headRefOid", OTHER_HEAD, "pull_request_head_mismatch"),
            ("mergeStateStatus", "BEHIND", "merge_state_not_clean"),
        )
        for field, value, reason in scenarios:
            with self.subTest(field=field):
                runner = FixtureRunner(self.repo)
                runner.pr_payload[field] = value
                result = self.evaluate(self.local_request(), runner)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reasonCodes"], [reason])

    def test_local_branch_rejects_unverifiable_local_and_remote_state(self) -> None:
        dirty = FixtureRunner(self.repo)
        dirty.git_status = " M file\n"
        unavailable = FixtureRunner(self.repo)
        unavailable.git_status_returncode = 1
        missing_slug = FixtureRunner(self.repo)
        missing_remote = FixtureRunner(self.repo)
        missing_remote.remote_returncode = 2
        moved_remote = FixtureRunner(self.repo)
        moved_remote.remote_head = OTHER_HEAD

        cases = (
            (dirty, self.local_request(), "working_tree_dirty", "blocked"),
            (
                unavailable,
                self.local_request(),
                "working_tree_unavailable",
                "indeterminate",
            ),
            (
                missing_slug,
                self.local_request(githubRepository=None),
                "github_repository_unavailable",
                "indeterminate",
            ),
            (
                missing_remote,
                self.local_request(),
                "remote_head_unavailable",
                "indeterminate",
            ),
            (
                moved_remote,
                self.local_request(),
                "remote_head_mismatch",
                "blocked",
            ),
        )
        for runner, request, reason, status in cases:
            with self.subTest(reason=reason):
                result = self.evaluate(request, runner)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["reasonCodes"], [reason])

    def test_local_branch_requires_a_successful_executed_check(self) -> None:
        runner = FixtureRunner(self.repo)
        runner.pr_payload["statusCheckRollup"] = [check_run("SKIPPED")]
        result = self.evaluate(self.local_request(), runner)
        self.assertEqual(result["reasonCodes"], ["checks_no_success"])

    def test_dependency_mode_covers_all_blocked_and_indeterminate_gates(self) -> None:
        scenarios = (
            ("number", 99, "pull_request_identity_mismatch"),
            ("state", "MERGED", "pull_request_not_open"),
            ("isDraft", True, "pull_request_draft"),
            ("baseRefName", "develop", "pull_request_base_mismatch"),
            ("mergeStateStatus", "BLOCKED", "merge_state_not_clean"),
        )
        for field, value, reason in scenarios:
            with self.subTest(field=field):
                runner = FixtureRunner(self.repo)
                runner.pr_payload[field] = value
                result = self.evaluate(self.dependency_request(), runner)
                self.assertEqual(result["reasonCodes"], [reason])

        no_success = FixtureRunner(self.repo)
        no_success.pr_payload["statusCheckRollup"] = [check_run("SKIPPED")]
        self.assertEqual(
            self.evaluate(self.dependency_request(), no_success)["reasonCodes"],
            ["checks_no_success"],
        )
        blocked = FixtureRunner(self.repo)
        blocked.pr_payload["statusCheckRollup"] = [
            check_run("SUCCESS"),
            check_run("FAILURE"),
        ]
        self.assertEqual(
            self.evaluate(self.dependency_request(), blocked)["reasonCodes"],
            ["checks_blocking"],
        )
        unresolved = FixtureRunner(self.repo)
        unresolved.thread_pages = [thread_page([False])]
        self.assertEqual(
            self.evaluate(self.dependency_request(), unresolved)["reasonCodes"],
            ["review_threads_unresolved"],
        )
        thread_failure = FixtureRunner(self.repo)
        thread_failure.thread_failure = True
        self.assertEqual(
            self.evaluate(self.dependency_request(), thread_failure)["reasonCodes"],
            ["review_threads_unavailable"],
        )
        missing_head = FixtureRunner(self.repo)
        missing_head.pr_head_result = eligibility.CommandResult(1, "")
        self.assertEqual(
            self.evaluate(self.dependency_request(), missing_head)["reasonCodes"],
            ["head_unavailable"],
        )

    def test_review_thread_parser_rejects_incomplete_or_malformed_pages(self) -> None:
        malformed_pages = (
            {"errors": [{"message": "rate limited"}]},
            {"data": {}},
            {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": {}, "pageInfo": {}}}}}},
            thread_page([True], has_next=True, cursor=None),
            {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [{"isResolved": "yes"}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}},
        )
        for page in malformed_pages:
            with self.subTest(page=page):
                runner = FixtureRunner(self.repo)
                runner.thread_pages = [page]
                result = self.evaluate(self.local_request(), runner)
                self.assertEqual(
                    result["reasonCodes"], ["review_threads_unavailable"]
                )

    def test_cli_request_adapter_and_shell_render_are_strict(self) -> None:
        args = eligibility.parse_args(
            [
                "--repo",
                str(self.repo),
                "--dependency-pr-number",
                "42",
                "--remote",
                "origin",
                "--default-branch",
                "main",
                "--github-repository",
                "example/repo",
            ]
        )
        request = eligibility.request_from_args(args)
        self.assertEqual(request["mode"], "dependency-pr")
        self.assertFalse(request["finishWorkRequired"])

        with self.assertRaisesRegex(eligibility.EligibilityInputError, "mutually exclusive"):
            eligibility.request_from_args(
                eligibility.parse_args(
                    [
                        "--branch",
                        "feature",
                        "--dependency-pr-number",
                        "42",
                        "--remote",
                        "origin",
                        "--default-branch",
                        "main",
                    ]
                )
            )
        result = self.evaluate(self.dependency_request(), FixtureRunner(self.repo))
        fields = eligibility.render_shell(result).split(eligibility.FIELD_SEPARATOR)
        self.assertEqual(fields[0], "eligible")
        self.assertEqual(fields[2], "42")


if __name__ == "__main__":
    unittest.main()
