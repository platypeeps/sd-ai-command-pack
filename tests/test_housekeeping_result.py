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

SCRIPT_PATH = install.ROOT / "scripts/sd-ai-command-pack-housekeeping-result.py"
SPEC = importlib.util.spec_from_file_location(
    "sd_ai_command_pack_housekeeping_result", SCRIPT_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT_PATH}")
result_builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = result_builder
SPEC.loader.exec_module(result_builder)

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
            "start_branch": "feature/runtime-contract",
            "default_branch": "main",
            "remote": "origin",
            "merge_strategy": "merge",
            "dry_run": False,
            "keep_remote_branch": False,
            "dependency_pr_number": None,
            "finish_work_head": HEAD,
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
                "finishWork": {"required": True, "providedHead": HEAD},
            },
        )
        return path

    def test_clean_result_composes_status_without_recollecting_state(self) -> None:
        path = self.eligibility("eligible", [])
        result = result_builder.build_result(self.args(eligibility_input=path))

        self.assertEqual(result["schemaVersion"], 1)
        self.assertEqual(result["outcome"], {"status": "clean", "reasonCodes": []})
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
            {"status": "failed", "reasonCodes": ["status_unavailable"]},
        )

    def test_status_anomalies_block_even_without_shell_anomaly(self) -> None:
        self.status["anomalies"] = ["remote source branch still tracked"]
        self.write_json(self.status_path, self.status)

        result = result_builder.build_result(self.args(status_exit=1))

        self.assertEqual(result["outcome"]["status"], "blocked")
        self.assertEqual(result["outcome"]["reasonCodes"], ["status_anomalies"])

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

    def test_parser_rejects_invalid_numeric_and_head_arguments(self) -> None:
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
            ["--finish-work-head", "BAD"],
        ):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    result_builder.parse_args(base + extra)


if __name__ == "__main__":
    unittest.main()
