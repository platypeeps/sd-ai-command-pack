from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import install

SCRIPT_PATH = install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping-result.py"
SPEC = importlib.util.spec_from_file_location(
    "sd_ai_command_pack_housekeeping_result", SCRIPT_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT_PATH}")
result_builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = result_builder
SPEC.loader.exec_module(result_builder)

STATUS_PATH = install.ROOT / "templates/scripts/sd-ai-command-pack-status.py"
STATUS_SPEC = importlib.util.spec_from_file_location(
    "sd_ai_command_pack_status_for_result", STATUS_PATH
)
if STATUS_SPEC is None or STATUS_SPEC.loader is None:
    raise RuntimeError(f"cannot load {STATUS_PATH}")
status_collector = importlib.util.module_from_spec(STATUS_SPEC)
sys.modules[STATUS_SPEC.name] = status_collector
STATUS_SPEC.loader.exec_module(status_collector)

HEAD = "1" * 40


class HousekeepingResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-housekeeping-result-"
        )
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.status_path = self.root / "status.json"
        self.status = {
            "schemaVersion": 2,
            "mode": "local",
            "repository": {"path": "/repo", "name": "repo", "github": "o/r"},
            "git": {"branch": "main", "workingTree": {"state": "clean"}},
            "trellis": {"inProgress": [], "planned": []},
            "anomalies": [],
            "followUps": [],
            "nextSteps": ["No immediate repository action is required."],
        }
        self.write_json(self.status_path, self.status)

    def write_json(self, path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    def args(self, **updates: object) -> Namespace:
        values: dict[str, object] = {
            "status_input": self.status_path,
            "status_error": None,
            "status_exit": 0,
            "repository": Path("/repo"),
            "eligibility_input": None,
            "finish_work_unverified": False,
            "start_branch": "feature/runtime-contract",
            "default_branch": "main",
            "remote": "origin",
            "merge_strategy": "merge",
            "dry_run": False,
            "keep_remote_branch": False,
            "dependency_pr_number": None,
            "action": [["branch_switched", "switched to main"]],
            "anomaly": [],
        }
        values.update(updates)
        return Namespace(**values)

    def eligibility(self, status: str, reasons: list[str]) -> Path:
        path = self.root / "eligibility.json"
        self.write_json(
            path,
            {
                "schemaVersion": 1,
                "status": status,
                "reasonCodes": reasons,
                "pullRequest": {"number": 42, "url": "https://example.test/42"},
                "head": {"startOid": HEAD, "endOid": HEAD, "remoteOid": HEAD},
                "finishWork": {
                    "required": True,
                    "provided": True,
                    "mode": "completion",
                    "completionSubtype": "post-archive-review-successor",
                    "planningSubtype": None,
                    "headOid": HEAD,
                    "matchesCurrentHead": True,
                    "verified": True,
                },
            },
        )
        return path

    def test_clean_result_composes_status_without_recollecting_state(self) -> None:
        path = self.eligibility("eligible", [])
        result = result_builder.build_result(self.args(eligibility_input=path))

        self.assertEqual(result["schemaVersion"], 1)
        self.assertEqual(
            result["outcome"],
            {"verdict": "clean", "status": "clean", "reasonCodes": []},
        )
        self.assertEqual(result["eligibility"]["pullRequest"]["number"], 42)
        self.assertEqual(result["status"], self.status)
        self.assertEqual(result["actions"][0]["code"], "branch_switched")

    def test_blocked_result_preserves_eligibility_and_anomaly_codes(self) -> None:
        path = self.eligibility("blocked", ["checks_blocking"])
        result = result_builder.build_result(
            self.args(
                eligibility_input=path,
                anomaly=[["merge_blocked", "GitHub refused the merge"]],
            )
        )

        self.assertEqual(result["outcome"]["status"], "blocked")
        self.assertEqual(
            result["outcome"]["reasonCodes"],
            ["checks_blocking", "merge_blocked"],
        )

    def test_environment_boundary_anomalies_attach_structured_blocks(self) -> None:
        from sd_ai_command_pack_lib import validate_environment_blocked_evidence

        result = result_builder.build_result(
            self.args(
                status_exit=1,
                anomaly=[
                    ["remote_fetch_failed", "git fetch --prune origin failed"],
                    ["remote_prune_failed", "git fetch --prune origin failed"],
                    ["local_branch_delete_failed", "git branch -D feature failed"],
                    ["remote_branch_delete_failed", "git push --delete origin failed"],
                    ["kb_refresh_failed", "KB refresh exited nonzero"],
                    ["pull_request_not_merged", "PR is CLOSED, not MERGED"],
                ],
            )
        )

        blocks = result["environmentBlocks"]
        by_checkpoint = {block["checkpoint"]: block for block in blocks}
        self.assertEqual(
            set(by_checkpoint),
            {
                "remote-fetch",
                "remote-prune",
                "local-branch-delete",
                "remote-branch-delete",
                "kb-refresh",
            },
        )
        # The policy anomaly (a repository/PR-state fact) must never be labeled a
        # retryable environment boundary.
        self.assertNotIn("pull_request_not_merged", str(blocks))

        self.assertEqual(by_checkpoint["remote-fetch"]["boundary"], "git-metadata")
        self.assertEqual(
            by_checkpoint["remote-fetch"]["mutationState"], "partial-recoverable"
        )
        self.assertEqual(
            by_checkpoint["local-branch-delete"]["mutationState"], "none"
        )
        self.assertEqual(by_checkpoint["kb-refresh"]["boundary"], "kb-target")

        for block in blocks:
            # Every block is a genuine composer product and survives consumer-side
            # validation unchanged; no remote URL or control text leaks into the
            # durable diagnostic.
            self.assertTrue(block["retryable"])
            self.assertEqual(block["recoveryAction"]["kind"], "skill")
            self.assertNotIn("://", block["diagnostic"])
            self.assertEqual(validate_environment_blocked_evidence(block), block)

    def test_policy_anomalies_emit_no_environment_block(self) -> None:
        result = result_builder.build_result(
            self.args(
                status_exit=1,
                anomaly=[
                    ["remote_not_configured", "git remote get-url origin failed"],
                    ["default_remote_ref_missing", "remote default ref absent"],
                    ["working_tree_dirty", "uncommitted changes present"],
                    ["kb_helper_missing", "KB helper not found"],
                ],
            )
        )
        self.assertEqual(result["environmentBlocks"], [])

    def test_environment_block_is_additive_and_does_not_alter_outcome(self) -> None:
        # A clean run carries an empty list; attaching a block never injects a
        # reason code or flips the outcome the anomaly already determined.
        clean = self.eligibility("eligible", [])
        clean_result = result_builder.build_result(
            self.args(eligibility_input=clean)
        )
        self.assertEqual(clean_result["environmentBlocks"], [])
        self.assertEqual(clean_result["outcome"]["status"], "clean")

        blocked = result_builder.build_result(
            self.args(
                status_exit=1,
                anomaly=[["remote_prune_failed", "git fetch --prune origin failed"]],
            )
        )
        self.assertEqual(blocked["outcome"]["status"], "blocked")
        self.assertEqual(blocked["outcome"]["reasonCodes"], ["remote_prune_failed"])
        self.assertEqual(len(blocked["environmentBlocks"]), 1)

    def test_indeterminate_and_status_failure_are_distinct(self) -> None:
        path = self.eligibility("indeterminate", ["review_threads_unavailable"])
        indeterminate = result_builder.build_result(
            self.args(eligibility_input=path)
        )
        failed = result_builder.build_result(self.args(status_exit=127))

        self.assertEqual(indeterminate["outcome"]["status"], "indeterminate")
        self.assertEqual(failed["outcome"]["status"], "failed")
        self.assertEqual(
            failed["outcome"]["reasonCodes"], ["status_collection_failed"]
        )

    def test_missing_status_is_a_typed_failed_result(self) -> None:
        result = result_builder.build_result(
            self.args(
                status_input=None,
                status_error=["status_unavailable", "collector produced no JSON"],
                status_exit=127,
            )
        )

        self.assertIsNone(result["status"])
        self.assertEqual(
            result["statusError"],
            {"code": "status_unavailable", "message": "collector produced no JSON"},
        )
        self.assertEqual(
            result["outcome"],
            {
                "verdict": "failed",
                "status": "failed",
                "reasonCodes": ["status_unavailable"],
            },
        )

    def test_legacy_status_without_details_still_blocks(self) -> None:
        # An embedded document from a collector that predates anomalyDetails
        # carries no severity, so every anomaly blocks under the one opaque
        # code. Fail closed rather than read an unknown severity as advisory.
        self.status["anomalies"] = ["remote source branch still tracked"]
        self.write_json(self.status_path, self.status)

        result = result_builder.build_result(self.args(status_exit=1))

        self.assertEqual(result["outcome"]["status"], "blocked")
        self.assertEqual(result["outcome"]["reasonCodes"], ["status_anomalies"])

    def test_blocking_status_anomalies_name_their_cause(self) -> None:
        self.status["anomalies"] = ["working tree is dirty after housekeeping"]
        self.status["anomalyDetails"] = [
            {
                "code": "working_tree_dirty",
                "severity": "blocking",
                "message": "working tree is dirty after housekeeping",
            }
        ]
        self.write_json(self.status_path, self.status)

        result = result_builder.build_result(self.args(status_exit=1))

        self.assertEqual(result["outcome"]["verdict"], "blocked")
        self.assertEqual(
            result["outcome"]["reasonCodes"], ["status_working_tree_dirty"]
        )

    def test_advisory_status_anomalies_do_not_block(self) -> None:
        self.status["anomalies"] = ["2 local branch(es) are unmerged with no open pull request: a, b"]
        self.status["anomalyDetails"] = [
            {
                "code": "local_branches_unmerged_without_pr",
                "severity": "advisory",
                "message": "2 local branch(es) are unmerged with no open pull request: a, b",
            }
        ]
        self.write_json(self.status_path, self.status)

        result = result_builder.build_result(self.args(status_exit=0))

        self.assertEqual(result["outcome"]["verdict"], "clean")
        self.assertEqual(result["outcome"]["reasonCodes"], [])

    def test_advisory_shell_anomaly_yields_clean_verdict(self) -> None:
        # The absorbed 08-08 case: every merge action succeeded and the only
        # anomalies are that another live worktree holds the default branch.
        # Assert the exact verdict -- `failed` and `indeterminate` would both
        # satisfy a merely-not-blocked assertion.
        anomalies = [
            [
                "default_branch_held_elsewhere",
                "main is checked out in worktree /elsewhere; this checkout stays on feature",
            ],
            [
                "branch_retained_default_held",
                "still on feature because main is held by another worktree; skipped branch deletion",
            ],
        ]

        result = result_builder.build_result(self.args(anomaly=anomalies))

        self.assertEqual(result["outcome"]["verdict"], "clean")
        self.assertEqual(result["outcome"]["reasonCodes"], [])
        self.assertEqual(
            [item["code"] for item in result["anomalies"]],
            ["default_branch_held_elsewhere", "branch_retained_default_held"],
        )

    def test_advisory_code_does_not_outrank_indeterminate(self) -> None:
        anomalies = [
            ["default_branch_held_elsewhere", "main is held by another worktree"],
            ["pull_request_unavailable", "could not read the pull request"],
        ]

        result = result_builder.build_result(self.args(anomaly=anomalies))

        self.assertEqual(result["outcome"]["verdict"], "indeterminate")
        self.assertIn("pull_request_unavailable", result["outcome"]["reasonCodes"])

    def test_advisory_code_sets_agree_across_scripts(self) -> None:
        # The collector mirrors this severity when housekeeping replays its own
        # anomalies through --prior-anomaly. A code that is advisory in one
        # script and blocking in the other produces a clean verdict from a run
        # that exited nonzero, so the two sets are pinned together here.
        self.assertEqual(
            status_collector.ADVISORY_CALLER_ANOMALY_CODES,
            result_builder.ADVISORY_ANOMALY_CODES,
        )

    def test_invalid_schema_code_message_and_symlink_fail_closed(self) -> None:
        self.status["schemaVersion"] = 1
        self.write_json(self.status_path, self.status)
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.build_result(self.args())

        self.status["schemaVersion"] = 2
        self.write_json(self.status_path, self.status)
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.build_result(self.args(action=[["BAD", "message"]]))
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.build_result(
                self.args(action=[["valid_code", "unsafe\nmessage"]])
            )

        symlink = self.root / "status-link.json"
        symlink.symlink_to(self.status_path)
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.build_result(self.args(status_input=symlink))

    def test_delegated_shape_validation_fails_closed(self) -> None:
        invalid_statuses = (
            {**self.status, "mode": "fleet"},
            {**self.status, "git": []},
            {**self.status, "anomalies": [7]},
        )
        for value in invalid_statuses:
            with self.subTest(status=value):
                self.write_json(self.status_path, value)
                with self.assertRaises(result_builder.ResultInputError):
                    result_builder.build_result(self.args())

        self.write_json(self.status_path, self.status)
        path = self.eligibility("eligible", [])
        eligibility_value = json.loads(path.read_text(encoding="utf-8"))
        eligibility_value["status"] = "unknown"
        self.write_json(path, eligibility_value)
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.build_result(self.args(eligibility_input=path))
        eligibility_value["status"] = "eligible"
        eligibility_value["reasonCodes"] = ["BAD"]
        self.write_json(path, eligibility_value)
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.build_result(self.args(eligibility_input=path))

    def test_json_loader_rejects_empty_malformed_and_non_object_inputs(self) -> None:
        for content in ("", "{", "[]"):
            with self.subTest(content=content):
                path = self.root / "invalid.json"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(result_builder.ResultInputError):
                    result_builder.load_json(path, "fixture")
        invalid_utf8 = self.root / "invalid-utf8.json"
        invalid_utf8.write_bytes(b"\xff{\"schemaVersion\": 1}")
        with self.assertRaisesRegex(
            result_builder.ResultInputError,
            "fixture is not readable JSON",
        ):
            result_builder.load_json(invalid_utf8, "fixture")
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.load_json(self.root / "missing.json", "fixture")

    def test_status_contract_requires_exactly_one_result_source(self) -> None:
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.build_result(
                self.args(
                    status_error=["status_unavailable", "missing"],
                )
            )
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.build_result(self.args(status_input=None))
        with self.assertRaises(result_builder.ResultInputError):
            result_builder.validate_event(["only_code"], "fixture")

    def test_unavailable_anomaly_is_indeterminate_and_codes_are_deduplicated(
        self,
    ) -> None:
        result = result_builder.build_result(
            self.args(
                anomaly=[
                    ["pull_request_unavailable", "could not inspect PR"],
                    ["pull_request_unavailable", "PR still unavailable"],
                ]
            )
        )

        self.assertEqual(result["outcome"]["status"], "indeterminate")
        self.assertEqual(
            result["outcome"]["reasonCodes"], ["pull_request_unavailable"]
        )

    def test_cli_emits_result_and_reports_invalid_input_without_traceback(self) -> None:
        argv = [
            "--repository",
            "/repo",
            "--status-input",
            str(self.status_path),
            "--status-exit",
            "0",
            "--remote",
            "origin",
            "--merge-strategy",
            "merge",
        ]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(result_builder.main(argv), 0)
        self.assertEqual(json.loads(stdout.getvalue())["outcome"]["status"], "clean")

        self.status["schemaVersion"] = 1
        self.write_json(self.status_path, self.status)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(result_builder.main(argv), 2)
        self.assertIn("schemaVersion must be 2", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_parser_rejects_invalid_numeric_arguments(self) -> None:
        base = [
            "--repository",
            "/repo",
            "--status-input",
            str(self.status_path),
            "--status-exit",
            "0",
            "--remote",
            "origin",
            "--merge-strategy",
            "merge",
        ]
        for extra in (
            ["--status-exit", "256"],
            ["--dependency-pr-number", "0"],
        ):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    result_builder.parse_args(base + extra)

    def test_finish_work_head_is_retired_and_verified_head_relocated(self) -> None:
        """Schema v1 migration: the retired ``invocation.finishWorkHead`` field is
        absent, and the exact merge head lives only on the verified
        ``identity.finishWork`` object.

        Decision:
        .trellis/tasks/07-28-decide-housekeeping-result-schema-compatibility.
        """

        path = self.eligibility("eligible", [])
        result = result_builder.build_result(self.args(eligibility_input=path))

        self.assertEqual(result["schemaVersion"], 1)
        # Absence semantics: no field named finishWorkHead anywhere in the result.
        self.assertNotIn("finishWorkHead", result["invocation"])
        self.assertNotIn("finishWorkHead", json.dumps(result))
        # The verified head is relocated to identity.finishWork, gated on verified.
        finish_work = result["identity"]["finishWork"]
        self.assertEqual(finish_work["headOid"], HEAD)
        self.assertTrue(finish_work["verified"])
        # invocation carries only a boolean provenance flag, never a head value.
        self.assertIs(result["invocation"]["finishWorkReceiptProvided"], True)

    def test_missing_eligibility_omits_finish_work_head_without_alias(self) -> None:
        """Without an eligibility receipt there is no finish-work head to echo; the
        result still exposes no finishWorkHead alias or fallback."""

        result = result_builder.build_result(self.args())

        self.assertIsNone(result["identity"]["finishWork"])
        self.assertNotIn("finishWorkHead", result["invocation"])
        self.assertNotIn("finishWorkHead", json.dumps(result))
        self.assertIs(result["invocation"]["finishWorkReceiptProvided"], False)

    def test_retired_finish_work_head_cli_is_not_restored(self) -> None:
        """AC4: the caller-trusted ``--finish-work-head`` input stays retired; the
        parser rejects it rather than reviving a trust bypass."""

        base = [
            "--repository",
            "/repo",
            "--status-input",
            str(self.status_path),
            "--status-exit",
            "0",
            "--remote",
            "origin",
            "--merge-strategy",
            "merge",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                result_builder.parse_args(base + ["--finish-work-head", HEAD])


if __name__ == "__main__":
    unittest.main()
