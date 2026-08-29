from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import install

SCRIPT_PATH = install.ROOT / "templates/scripts/sd-ai-command-pack-pr-eligibility.py"
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
                "lineageDigest": f"sha256:{'a' * 64}",
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
    workflow: str = "CI",
    started_at: str | None = None,
) -> dict[str, Any]:
    row = {
        "__typename": "CheckRun",
        "name": name,
        "workflowName": workflow,
        "status": status,
        "conclusion": conclusion,
        "detailsUrl": "https://example.test/check",
    }
    # Omitted rather than nulled when unset, so every pre-existing caller keeps
    # producing the exact fixture it produced before supersession existed.
    if started_at is not None:
        row["startedAt"] = started_at
    return row


# The PR #360 rollup shape (platypeeps/anomaly-metric-creator, 2026-08-07):
# marking the PR ready triggered a run whose concurrency group cancelled the
# in-flight run, and both stayed attached to the head.
SUPERSEDED_AT = "2026-08-07T18:10:00Z"
REPLACEMENT_AT = "2026-08-07T18:22:41Z"
PR_360_NAMES = (
    ("CI Result", "SUCCESS"),
    ("test", "SUCCESS"),
    ("quick test", "SKIPPED"),
    ("socket", "SUCCESS"),
    ("Windows collection (advisory)", "SUCCESS"),
)


def pr_360_rollup(*, include_replacements: bool = True) -> list[dict[str, Any]]:
    rows = [
        check_run("CANCELLED", name=name, started_at=SUPERSEDED_AT)
        for name, _ in PR_360_NAMES
    ]
    if include_replacements:
        rows.extend(
            check_run(conclusion, name=name, started_at=REPLACEMENT_AT)
            for name, conclusion in PR_360_NAMES
        )
    return rows


def thread_page(
    nodes: list[bool],
    *,
    has_next: bool = False,
    cursor: str | None = None,
    outdated: list[bool] | None = None,
) -> dict[str, Any]:
    """Build one page of review threads.

    ``nodes`` carries each thread's ``isResolved``; ``outdated`` its
    ``isOutdated``, defaulting to a page where nothing is outdated. Both are
    required fields on the wire -- the reader fails closed on a node missing
    either -- so a fixture cannot omit one and still be representative.
    """

    flags = outdated if outdated is not None else [False] * len(nodes)
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {"isResolved": value, "isOutdated": stale}
                            for value, stale in zip(nodes, flags, strict=True)
                        ],
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
        # Successive `gh pr view --json ...` reads, consumed in order; the
        # last entry repeats once exhausted. Empty means "always pr_payload",
        # which is how GitHub behaves for a settled merge state.
        self.pr_payload_queue: list[dict[str, Any]] = []
        self.sleeps: list[float] = []
        self.calls: list[tuple[str, ...]] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

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
        if (
            len(args) == 12
            and args[0] == "node"
            and Path(args[1]).name == "sd-ai-command-pack-review-preflight.mjs"
            and args[2] == "final-bundle"
            and args[3] == "--mode"
            and args[5] == "--base"
            and args[7] == "--head"
            and args[9] == "--repo"
            and args[11] == "--json"
        ):
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
            if self.pr_payload_queue:
                payload = (
                    self.pr_payload_queue.pop(0)
                    if len(self.pr_payload_queue) > 1
                    else self.pr_payload_queue[0]
                )
                return eligibility.CommandResult(0, json.dumps(payload))
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
            sleeper=runner.sleep,
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
            [call[2:] for call in runner.calls if call[:1] == ("node",)],
            [
                (
                    "final-bundle",
                    "--mode",
                    "completion",
                    "--base",
                    HEAD,
                    "--head",
                    HEAD,
                    "--repo",
                    str(self.repo),
                    "--json",
                )
            ],
        )
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

    def test_finish_work_stale_names_the_mismatched_half(self) -> None:
        # The PRD hit the confusing case: a receipt generated on a temporary
        # rebase branch reported `matchesCurrentHead: true` alongside "does not
        # match the current branch and exact head". One message for two facts
        # tells the caller to re-run finish-work without telling them why the
        # last run did not count.
        head_only = self.evaluate(
            self.local_request(finishWorkReceipt=finish_work_receipt(head=OTHER_HEAD)),
            FixtureRunner(self.repo),
        )
        branch_only = self.evaluate(
            self.local_request(
                finishWorkReceipt=finish_work_receipt(branch="tmp/rebase")
            ),
            FixtureRunner(self.repo),
        )
        both = self.evaluate(
            self.local_request(
                finishWorkReceipt=finish_work_receipt(
                    head=OTHER_HEAD, branch="tmp/rebase"
                )
            ),
            FixtureRunner(self.repo),
        )
        for result in (head_only, branch_only, both):
            self.assertEqual(result["reasonCodes"], ["finish_work_stale"], result)

        # The call site appends "rerun sd-finish-work for the current head
        # before housekeeping", so only the leading clause is this message.
        def records(result) -> str:
            return result["diagnostic"].split(";")[0]

        self.assertIn("head", records(head_only))
        self.assertNotIn("branch", records(head_only))

        self.assertIn("branch", records(branch_only))
        self.assertIn("tmp/rebase", records(branch_only))
        self.assertNotIn("head", records(branch_only))

        self.assertIn("branch", records(both))
        self.assertIn("head", records(both))

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

    def test_the_outdated_share_is_reported_and_named_in_the_diagnostic(self) -> None:
        """The two readers disagree by design; the output has to say so.

        `sd-review` excludes outdated threads because their findings are no
        longer in the diff, and this reader counts them because GitHub's
        conversation-resolution requirement does. Reported bare, the two counts
        read as a contradiction and the diagnostic sends an operator hunting
        for a finding the review stage has just called clean.
        """

        runner = FixtureRunner(self.repo)
        runner.thread_pages = [
            thread_page(
                [True, True, False, False],
                outdated=[False, False, True, True],
            )
        ]
        result = self.evaluate(self.local_request(), runner)

        self.assertEqual(result["reviewThreads"]["totalCount"], 4)
        self.assertEqual(result["reviewThreads"]["unresolvedCount"], 2)
        self.assertEqual(result["reviewThreads"]["outdatedUnresolvedCount"], 2)
        self.assertIn("all outdated against earlier heads", result["diagnostic"])

        mixed = FixtureRunner(self.repo)
        mixed.thread_pages = [
            thread_page([False, False], outdated=[True, False])
        ]
        partial = self.evaluate(self.local_request(), mixed)

        self.assertEqual(partial["reviewThreads"]["outdatedUnresolvedCount"], 1)
        self.assertIn("1 of them outdated against earlier heads", partial["diagnostic"])

        # Nothing outdated: the diagnostic keeps its original wording rather
        # than growing a clause that says zero.
        plain = FixtureRunner(self.repo)
        plain.thread_pages = [thread_page([False])]
        unaffected = self.evaluate(self.local_request(), plain)

        self.assertEqual(unaffected["reviewThreads"]["outdatedUnresolvedCount"], 0)
        self.assertNotIn("outdated", unaffected["diagnostic"])

    def test_a_thread_node_without_is_outdated_fails_closed(self) -> None:
        """The rule needs the field, so a node missing it is not evidence."""

        runner = FixtureRunner(self.repo)
        runner.thread_pages = [
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [{"isResolved": False}],
                                "pageInfo": {
                                    "hasNextPage": False,
                                    "endCursor": None,
                                },
                            }
                        }
                    }
                }
            }
        ]
        result = self.evaluate(self.local_request(), runner)

        self.assertEqual(result["status"], "indeterminate")
        self.assertEqual(result["reasonCodes"], ["review_threads_unavailable"])

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

        eligibility_schema = eligibility.SCHEMA_VERSION
        eligibility.SCHEMA_VERSION = eligibility_schema + 1
        try:
            self.assertEqual(
                eligibility.load_finish_work_receipt(receipt_path)["schemaVersion"],
                eligibility.FINISH_WORK_RECEIPT_SCHEMA_VERSION,
            )
        finally:
            eligibility.SCHEMA_VERSION = eligibility_schema

        malformed = finish_work_receipt()
        malformed["schemaVersion"] = eligibility.FINISH_WORK_RECEIPT_SCHEMA_VERSION + 1
        receipt_path.write_text(json.dumps(malformed), encoding="utf-8")
        with self.assertRaisesRegex(
            eligibility.EligibilityInputError,
            f"schemaVersion must be {eligibility.FINISH_WORK_RECEIPT_SCHEMA_VERSION}",
        ):
            eligibility.load_finish_work_receipt(receipt_path)

        malformed = finish_work_receipt()
        malformed["evidence"]["repository"]["lineageDigest"] = str(self.repo)
        receipt_path.write_text(json.dumps(malformed), encoding="utf-8")
        with self.assertRaisesRegex(eligibility.EligibilityInputError, "lineageDigest"):
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

    def test_finish_work_receipt_tolerates_advisory_fields(self) -> None:
        planning = finish_work_receipt()
        planning["mode"] = "planning"
        planning["reasonCodes"] = ["planning_bundle_valid"]
        planning["evidence"].pop("completionSubtype")
        planning["evidence"]["advisoriesDropped"] = 3
        planning["advisories"] = [
            {
                "reasonCode": "task_metadata_invalid",
                "path": ".trellis/tasks/07-25-fixture/task.json",
                "message": "field description must be a non-empty string",
            }
        ]
        validated = eligibility.validate_finish_work_receipt(planning)
        self.assertEqual(validated["mode"], "planning")
        self.assertEqual(validated["reasonCodes"], ["planning_bundle_valid"])

    def test_finish_work_receipt_accepts_maintenance_recovery_shape(self) -> None:
        planning = finish_work_receipt()
        planning["mode"] = "planning"
        planning["reasonCodes"] = ["planning_bundle_valid"]
        planning["evidence"].pop("completionSubtype")
        planning["evidence"]["planningSubtype"] = "journal-only-recovery"
        planning["evidence"]["taskDirectories"] = []
        planning["advisories"] = []
        validated = eligibility.validate_finish_work_receipt(planning)
        self.assertEqual(
            validated["evidence"]["planningSubtype"], "journal-only-recovery"
        )
        self.assertEqual(validated["evidence"]["taskDirectories"], [])

    def test_finish_work_receipt_accepts_active_task_successor_shape(self) -> None:
        # AC8 / R4: the new active-task-review-successor completion subtype
        # is a free-form string (require_string(..., limit=100), no enum),
        # so it flows through with no eligibility code change -- same
        # contract journal-only-recovery already proved for planning mode.
        receipt = finish_work_receipt()
        receipt["evidence"]["completionSubtype"] = "active-task-review-successor"
        receipt["evidence"]["taskDirectories"] = [
            ".trellis/tasks/07-25-active-task-fixture"
        ]
        validated = eligibility.validate_finish_work_receipt(receipt)
        self.assertEqual(
            validated["evidence"]["completionSubtype"],
            "active-task-review-successor",
        )
        self.assertEqual(
            validated["evidence"]["taskDirectories"],
            [".trellis/tasks/07-25-active-task-fixture"],
        )

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
            # A non-CLEAN merge state is now classified into an actionable reason
            # (finding #2) while still blocking: BEHIND → update-the-branch.
            ("mergeStateStatus", "BEHIND", "merge_blocked_out_of_date"),
        )
        for field, value, reason in scenarios:
            with self.subTest(field=field):
                runner = FixtureRunner(self.repo)
                runner.pr_payload[field] = value
                result = self.evaluate(self.local_request(), runner)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reasonCodes"], [reason])

    def test_blocked_but_mergeable_is_classified_but_never_eligible(self) -> None:
        # AC3.c (finding #2): a BLOCKED-but-mergeable PR earns an actionable
        # diagnosis, yet stays blocked and NEVER reaches ``gh pr merge``. This is
        # the additive-only invariant — classification enriches the reason code,
        # it does not manufacture eligibility.

        # 1) BLOCKED, green checks, unresolved review threads → conversation.
        conversation = FixtureRunner(self.repo)
        conversation.pr_payload["mergeStateStatus"] = "BLOCKED"
        conversation.pr_payload["mergeable"] = "MERGEABLE"
        conversation.thread_pages = [thread_page([False, True])]
        result = self.evaluate(self.local_request(), conversation)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasonCodes"], ["merge_blocked_conversation"])
        self.assertIn("1 unresolved", result["diagnostic"])

        # 2) BLOCKED, green checks, no unresolved threads → protection/approval.
        review = FixtureRunner(self.repo)
        review.pr_payload["mergeStateStatus"] = "BLOCKED"
        review.pr_payload["mergeable"] = "MERGEABLE"
        result2 = self.evaluate(self.local_request(), review)
        self.assertEqual(result2["status"], "blocked")
        self.assertEqual(result2["reasonCodes"], ["merge_blocked_review"])

        # Invariant: neither run is eligible, and the auto-merge path is never
        # entered regardless of how mergeable the PR looks.
        for runner in (conversation, review):
            self.assertNotIn(
                ("gh", "pr", "merge"), [call[:3] for call in runner.calls]
            )

    def test_stale_blocked_snapshot_is_unsettled_not_a_protection_verdict(
        self,
    ) -> None:
        # GitHub recomputes mergeability asynchronously, so the read right after
        # a push or a draft-to-ready transition can report a BLOCKED that clears
        # itself. That is indistinguishable from a real branch-protection block
        # in one snapshot, so the probe re-reads under a fixed bound.

        def blocked_then(second: str) -> FixtureRunner:
            runner = FixtureRunner(self.repo)
            stale = {**runner.pr_payload, "mergeStateStatus": "BLOCKED"}
            stale["mergeable"] = "MERGEABLE"
            runner.pr_payload = stale
            runner.pr_payload_queue = [
                stale,
                {**stale, "mergeStateStatus": second},
            ]
            return runner

        # 1) BLOCKED then CLEAN: the first snapshot was stale. Never
        #    merge_blocked_review, never eligible — a retryable indeterminate
        #    that names the real cause.
        stale = blocked_then("CLEAN")
        result = self.evaluate(self.local_request(), stale)
        self.assertEqual(result["status"], "indeterminate")
        self.assertEqual(result["reasonCodes"], ["merge_state_unsettled"])
        self.assertTrue(result["retryable"])
        self.assertIn("had not recomputed mergeability", result["diagnostic"])
        self.assertNotIn("branch-protection rule is unsatisfied", result["diagnostic"])
        self.assertEqual(result["mergeStateRecheck"]["settledStatus"], "CLEAN")
        # Early stop: one changed read already proves staleness.
        self.assertEqual(stale.sleeps, [eligibility.MERGE_STATE_RECHECK_DELAY_SECONDS])

        # 2) BLOCKED on every read: the branch-protection diagnosis survives,
        #    and the re-read work is bounded by the module constants.
        stable = FixtureRunner(self.repo)
        stable.pr_payload["mergeStateStatus"] = "BLOCKED"
        stable.pr_payload["mergeable"] = "MERGEABLE"
        stable_result = self.evaluate(self.local_request(), stable)
        self.assertEqual(stable_result["status"], "blocked")
        self.assertEqual(stable_result["reasonCodes"], ["merge_blocked_review"])
        self.assertFalse(stable_result["retryable"])
        self.assertEqual(
            stable.sleeps,
            [eligibility.MERGE_STATE_RECHECK_DELAY_SECONDS]
            * eligibility.MERGE_STATE_RECHECK_ATTEMPTS,
        )
        full_reads = [
            call
            for call in stable.calls
            if call[:3] == ("gh", "pr", "view") and call[-1] != "headRefOid"
        ]
        self.assertEqual(
            len(full_reads), 1 + eligibility.MERGE_STATE_RECHECK_ATTEMPTS
        )

        # 3) An unreadable re-read degrades to the generic block: unknown
        #    evidence never earns the terminal-sounding verdict, and never
        #    earns eligibility either.
        unreadable = FixtureRunner(self.repo)
        unreadable.pr_payload["mergeStateStatus"] = "BLOCKED"
        unreadable.pr_payload["mergeable"] = "MERGEABLE"
        original_call = unreadable.__call__

        def fail_second_full_read(
            argv: list[str] | tuple[str, ...], cwd: Path, timeout: int
        ) -> Any:
            args = tuple(argv)
            if (
                args[:3] == ("gh", "pr", "view")
                and args[-1] != "headRefOid"
                and any(
                    call[:3] == ("gh", "pr", "view") and call[-1] != "headRefOid"
                    for call in unreadable.calls
                )
            ):
                unreadable.calls.append(args)
                return eligibility.CommandResult(1, "")
            return original_call(argv, cwd, timeout)

        unreadable_result = eligibility.evaluate_request(
            self.local_request(),
            runner=fail_second_full_read,
            now=lambda: "2026-07-23T00:00:00Z",
            sleeper=unreadable.sleep,
        )
        self.assertEqual(unreadable_result["status"], "blocked")
        self.assertEqual(unreadable_result["reasonCodes"], ["merge_state_not_clean"])

        # 4) A re-read that lands on a different pull request is not evidence
        #    about this one, so it degrades the same way.
        moved = FixtureRunner(self.repo)
        moved.pr_payload["mergeStateStatus"] = "BLOCKED"
        moved.pr_payload["mergeable"] = "MERGEABLE"
        moved.pr_payload_queue = [
            dict(moved.pr_payload),
            {**moved.pr_payload, "number": 99},
        ]
        moved_result = self.evaluate(self.local_request(), moved)
        self.assertEqual(moved_result["status"], "blocked")
        self.assertEqual(moved_result["reasonCodes"], ["merge_state_not_clean"])

        # Invariant across every shape above: the gate never merges.
        for runner in (stale, stable, unreadable, moved):
            self.assertNotIn(
                ("gh", "pr", "merge"), [call[:3] for call in runner.calls]
            )

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

    def test_superseded_cancelled_runs_do_not_block_the_merge(self) -> None:
        """Issue #414: a cancelled run replaced by a later one must not block.

        A concurrency group that cancels superseded in-progress runs leaves both
        the cancelled run and its replacement attached to the head. Branch
        protection reads the latest result per context and reported PR #360
        CLEAN/MERGEABLE while this probe reported it blocked.
        """

        # Baseline: an ordinary eligible probe with a single green check.
        baseline_runner = FixtureRunner(self.repo)
        self.evaluate(self.local_request(), baseline_runner)
        baseline_gh = [c for c in baseline_runner.calls if c[:1] == ("gh",)]

        runner = FixtureRunner(self.repo)
        runner.pr_payload["statusCheckRollup"] = pr_360_rollup()

        result = self.evaluate(self.local_request(), runner)

        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["reasonCodes"], [])
        self.assertEqual(result["checks"]["blockingCount"], 0)
        # Only the replacements count as green; the cancelled rows count as
        # nothing at all.
        self.assertEqual(result["checks"]["successfulCount"], 4)
        # R5: the rule is a second pass over a list already in memory, so the
        # eligible path costs exactly what it cost before.
        gh_calls = [call for call in runner.calls if call[:1] == ("gh",)]
        self.assertEqual(len(gh_calls), len(baseline_gh), runner.calls)
        rollup_calls = [
            call
            for call in gh_calls
            if call[:3] == ("gh", "pr", "view") and "statusCheckRollup" in call[-1]
        ]
        self.assertEqual(len(rollup_calls), 1, runner.calls)

        # Negative half of the same check: strip the replacements and the same
        # rollup must block again. If it does not, the rule has become a
        # blanket CANCELLED allow-list, which R2 forbids.
        stripped = FixtureRunner(self.repo)
        stripped.pr_payload["statusCheckRollup"] = pr_360_rollup(
            include_replacements=False
        )
        self.assertEqual(
            self.evaluate(self.local_request(), stripped)["reasonCodes"],
            ["checks_no_success"],
        )
        self.assertEqual(
            self.evaluate(
                self.local_request(),
                self._runner_with_rollup(
                    pr_360_rollup(include_replacements=False)
                    + [check_run("SUCCESS", name="unrelated")]
                ),
            )["reasonCodes"],
            ["checks_blocking"],
        )

    def _runner_with_rollup(self, rollup: list[dict[str, Any]]) -> FixtureRunner:
        runner = FixtureRunner(self.repo)
        runner.pr_payload["statusCheckRollup"] = rollup
        return runner

    def test_cancelled_run_without_a_replacement_still_blocks(self) -> None:
        """R2: cancellation is not evidence of success."""

        runner = FixtureRunner(self.repo)
        runner.pr_payload["statusCheckRollup"] = [
            check_run("SUCCESS", name="other", started_at=REPLACEMENT_AT),
            check_run("CANCELLED", name="ci", started_at=SUPERSEDED_AT),
        ]
        result = self.evaluate(self.local_request(), runner)
        self.assertEqual(result["reasonCodes"], ["checks_blocking"])

    def test_rollup_of_only_superseded_rows_is_refused_explicitly(self) -> None:
        """R3: dropping every blocking row must not manufacture eligibility."""

        runner = FixtureRunner(self.repo)
        runner.pr_payload["statusCheckRollup"] = [
            check_run("CANCELLED", name="ci", started_at=SUPERSEDED_AT),
            check_run("CANCELLED", name="ci", started_at=REPLACEMENT_AT),
        ]
        result = self.evaluate(self.local_request(), runner)
        # checks_no_success is evaluated before checks_blocking, so the refusal
        # names the real problem: nothing on this head ever passed.
        self.assertEqual(result["reasonCodes"], ["checks_no_success"])
        self.assertEqual(result["checks"]["successfulCount"], 0)
        # The later cancellation is unexplained and is still counted blocking.
        self.assertEqual(result["checks"]["blockingCount"], 1)

    def test_supersession_rule_identity_ordering_and_evidence(self) -> None:
        # R4: the evidence names which row replaced the discounted one. A
        # StatusContext sits ahead of the pair so an off-by-one between the
        # input index and the items position fails here.
        checks, blocking, successful = eligibility.parse_checks(
            [
                {"__typename": "StatusContext", "context": "legacy", "state": "SUCCESS"},
                check_run("CANCELLED", name="ci", started_at=SUPERSEDED_AT),
                check_run("SUCCESS", name="ci", started_at=REPLACEMENT_AT),
            ]
        )
        self.assertEqual((blocking, successful), (0, 2))
        self.assertTrue(checks[1]["superseded"])
        self.assertEqual(checks[1]["supersededBy"]["index"], 3)
        self.assertEqual(checks[1]["supersededBy"]["startedAt"], REPLACEMENT_AT)
        self.assertEqual(checks[2].get("name"), "ci")
        self.assertNotIn("superseded", checks[2])
        self.assertNotIn("superseded", checks[0])

        # Equal timestamps are no evidence of ordering.
        _, tied_blocking, _ = eligibility.parse_checks(
            [
                check_run("CANCELLED", name="ci", started_at=SUPERSEDED_AT),
                check_run("SUCCESS", name="ci", started_at=SUPERSEDED_AT),
            ]
        )
        self.assertEqual(tied_blocking, 1)

        # Matrix template and expansion are different names, so different
        # identities; a later expansion never discounts the template's row.
        _, matrix_blocking, _ = eligibility.parse_checks(
            [
                check_run(
                    "CANCELLED",
                    name="test heavy (py${{ matrix.python-version }})",
                    started_at=SUPERSEDED_AT,
                ),
                check_run(
                    "SUCCESS", name="test heavy (py3.14)", started_at=REPLACEMENT_AT
                ),
            ]
        )
        self.assertEqual(matrix_blocking, 1)

        # Same name under two workflows is two identities.
        _, workflow_blocking, _ = eligibility.parse_checks(
            [
                check_run(
                    "CANCELLED", name="build", workflow="A", started_at=SUPERSEDED_AT
                ),
                check_run(
                    "SUCCESS", name="build", workflow="B", started_at=REPLACEMENT_AT
                ),
            ]
        )
        self.assertEqual(workflow_blocking, 1)

        # Nameless rows never bucket together: the "unnamed" display
        # placeholder is not an identity.
        nameless_cancelled = check_run("CANCELLED", started_at=SUPERSEDED_AT)
        nameless_cancelled.pop("name")
        nameless_later = check_run("SUCCESS", started_at=REPLACEMENT_AT)
        nameless_later.pop("name")
        _, nameless_blocking, _ = eligibility.parse_checks(
            [nameless_cancelled, nameless_later]
        )
        self.assertEqual(nameless_blocking, 1)

    def test_started_at_absent_blocks_and_malformed_fails_closed(self) -> None:
        # Absent: no evidence of ordering, so the row is not superseded. This
        # can only keep a block, never create eligibility.
        _, blocking, _ = eligibility.parse_checks(
            [
                check_run("CANCELLED", name="ci"),
                check_run("SUCCESS", name="ci", started_at=REPLACEMENT_AT),
            ]
        )
        self.assertEqual(blocking, 1)

        # Present but unusable: malformed input, refused like a non-string
        # status is.
        for bad in ("not-a-timestamp", 17):
            with self.subTest(started_at=bad):
                with self.assertRaises(eligibility.EligibilityInputError):
                    eligibility.parse_checks(
                        [
                            check_run("CANCELLED", name="ci", started_at=SUPERSEDED_AT),
                            {
                                **check_run("SUCCESS", name="ci"),
                                "startedAt": bad,
                            },
                        ]
                    )

        # A rollup with no cancelled row never reads the field, so a malformed
        # timestamp there cannot start failing a probe that used to pass.
        _, untouched_blocking, untouched_successful = eligibility.parse_checks(
            [{**check_run("SUCCESS", name="ci"), "startedAt": "not-a-timestamp"}]
        )
        self.assertEqual((untouched_blocking, untouched_successful), (0, 1))

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
            # BLOCKED with green checks and no unresolved threads → a required
            # approval / protection rule is unsatisfied (still blocked, finding #2).
            ("mergeStateStatus", "BLOCKED", "merge_blocked_review"),
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
            {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [{"isResolved": "yes", "isOutdated": False}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}},
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


class GithubSlugDerivationTests(unittest.TestCase):
    """The probe must accept every remote URL the merge gate accepts.

    ``sd-ai-command-pack-housekeeping.sh`` resolves the slug from the remote,
    so a repository with an SSH remote merges fine while this probe reported
    ``github_repository_unavailable`` with a diagnostic claiming derivation had
    been attempted. These cases are the shell twin's four accepted prefixes.
    """

    def test_accepts_every_form_the_shell_twin_accepts(self) -> None:
        for url, expected in (
            ("git@github.com:owner/repo.git", "owner/repo"),
            ("ssh://git@github.com/owner/repo.git", "owner/repo"),
            ("https://github.com/owner/repo", "owner/repo"),
            ("https://github.com/owner/repo/", "owner/repo"),
            ("http://github.com/owner/repo.git", "owner/repo"),
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    eligibility.github_slug_from_remote_url(url), expected
                )

    def test_rejects_non_github_and_malformed_urls(self) -> None:
        for url in (
            "git@gitlab.com:owner/repo.git",
            "https://github.com/owner/repo/extra",
            "https://github.com/owner",
            "",
        ):
            with self.subTest(url=url):
                self.assertIsNone(eligibility.github_slug_from_remote_url(url))

    def test_derives_from_remote_when_slug_is_absent(self) -> None:
        calls: list[list[str]] = []

        def runner(args, cwd, timeout):  # noqa: ANN001, ARG001
            calls.append(list(args))
            return eligibility.CommandResult(0, "git@github.com:owner/repo.git\n")

        self.assertEqual(
            eligibility.derive_github_slug(Path("/repo"), "origin", runner),
            "owner/repo",
        )
        self.assertEqual(calls, [["git", "remote", "get-url", "origin"]])

    def test_derivation_failure_yields_none_not_an_exception(self) -> None:
        def failing(args, cwd, timeout):  # noqa: ANN001, ARG001
            return eligibility.CommandResult(128, "")

        self.assertIsNone(
            eligibility.derive_github_slug(Path("/repo"), "origin", failing)
        )

        def control_chars(args, cwd, timeout):  # noqa: ANN001, ARG001
            return eligibility.CommandResult(0, "git@github.com:own\x01er/repo\n")

        self.assertIsNone(
            eligibility.derive_github_slug(Path("/repo"), "origin", control_chars)
        )

    def test_missing_remote_name_is_not_derivable(self) -> None:
        def unreached(args, cwd, timeout):  # noqa: ANN001, ARG001
            raise AssertionError("git must not run without a remote name")

        self.assertIsNone(eligibility.derive_github_slug(Path("/repo"), None, unreached))
        self.assertIsNone(eligibility.derive_github_slug(Path("/repo"), "", unreached))


if __name__ == "__main__":
    unittest.main()
