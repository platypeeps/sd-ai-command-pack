"""Reusable passes require explicit storage and complete current identity."""

from __future__ import annotations

import builtins
import contextlib
import copy
import io
import json
import os
import subprocess
import sys
from unittest import mock

from sd_db import initialise

from tests.test_sd_review import FakeRunner, ReviewFixture, namespace, sd_review

receipts = sd_review.sd_check_receipts
sd_check = sd_review.sd_lib.sibling("receipt_check_under_test", "sd-check")


class ReceiptTests(ReviewFixture):
    def setUp(self):
        super().setUp()
        self.root = self.make_repo()
        self.database = self.tmp / "checks.db"
        initialise(self.database)
        (self.root / ".github").mkdir()
        self.contract = {"schema_version": 1, "complete": True, "network": "none",
                         "dependencies": ["dependency.txt"], "tools": [], "environment": ["TEST_MODE"]}
        (self.root / receipts.CONTRACT).write_text(json.dumps(self.contract))
        (self.root / ".gitignore").write_text("dependency.txt\n")
        (self.root / "dependency.txt").write_text("dependency-v1")
        self.local_block(self.root, f"check: {sys.executable} -c pass")
        self.git("add", "-A")
        self.git("add", "--force", "CLAUDE.local.md")
        self.git("commit", "--quiet", "-m", "check contract")
        self.env = self.environment(TEST_MODE="unit")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def record(self):
        before = receipts.prepare_check_receipt(self.root, self.env, self.database)
        result = sd_check.execute(self.root, sd_review.sd_lib.detect_entrypoints(self.root), None, False, 10,
                                  receipts.receipt_environment(self.contract, self.env))
        revision = receipts.store_check_receipt(self.root, self.env, self.database, before, result)
        return before, result, revision

    def configure_cache_check(self, command, dependencies, ignored):
        self.contract["dependencies"] = dependencies
        (self.root / receipts.CONTRACT).write_text(json.dumps(self.contract))
        (self.root / ".gitignore").write_text(ignored)
        self.local_block(self.root, "check: " + command)
        self.git("add", "-A")
        self.git("add", "--force", "CLAUDE.local.md")
        self.git("commit", "--quiet", "--allow-empty", "-m", "synthetic check identity")

    def actual_check_status(self):
        return sd_check.execute(self.root, sd_review.sd_lib.detect_entrypoints(self.root), None, False, 10,
                                receipts.receipt_environment(self.contract, self.env))["status"]

    def test_declared_empty_directory_addition_and_removal_invalidate(self):
        directory = self.root / "cache"
        directory.mkdir()
        trigger = directory / "trigger"
        for initially_present in (False, True):
            with self.subTest(initially_present=initially_present):
                if initially_present:
                    trigger.mkdir(exist_ok=True)
                expression = "pathlib.Path('cache/trigger').exists()"
                command = f'{sys.executable} -c "import pathlib; assert {expression} is {initially_present}"'
                self.configure_cache_check(command, ["cache"], "dependency.txt\ncache/\n")
                self.record()
                if initially_present:
                    trigger.rmdir()
                else:
                    trigger.mkdir()
                self.assertEqual(self.git("status", "--porcelain"), "")
                self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
                self.assertEqual(self.actual_check_status(), "fail")

    def test_declared_root_and_nested_directory_modes_invalidate(self):
        directory = self.root / "cache"
        child = directory / "nested"
        child.mkdir(parents=True)
        self.configure_cache_check(f"{sys.executable} -c pass", ["cache"], "dependency.txt\ncache/\n")
        for path in (directory, child):
            with self.subTest(path=path):
                path.chmod(0o700)
                self.record()
                path.chmod(0o750)
                self.assertEqual(self.git("status", "--porcelain"), "")
                self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))

    def test_tool_lookup_matches_check_cwd_for_relative_and_empty_path_entries(self):
        (self.root / ".tools").mkdir()
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "placeholder").write_text("fixture")
        global_tool = self.tool_bin / "quality-check"
        global_tool.write_text("#!/bin/sh\nexit 0\n")
        global_tool.chmod(0o700)
        base_path = self.env["PATH"]
        cases = (("quality-check", ".tools", ".tools/quality-check"),
                 ("quality-check", "", "quality-check"),
                 (".tools/quality-check", None, ".tools/quality-check"))
        for command, component, relative in cases:
            with self.subTest(command=command, component=component):
                local_tool = self.root / relative
                local_tool.write_text("#!/bin/sh\nexit 0\n")
                local_tool.chmod(0o700)
                self.configure_cache_check(command, [], "dependency.txt\n.tools/\nquality-check\n")
                self.env["PATH"] = base_path if component is None else component + os.pathsep + base_path
                with contextlib.chdir(nested):
                    before, _, _ = self.record()
                    self.assertEqual(before[0]["tools"][0]["path"], str(local_tool))
                    self.assertEqual(self.actual_check_status(), "pass")
                    local_tool.write_text("#!/bin/sh\nexit 1\n")
                    self.assertEqual(self.git("status", "--porcelain"), "")
                    self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
                    self.assertEqual(self.actual_check_status(), "fail")

    def test_complete_pass_round_trips_without_running_a_check(self):
        _before, _result, revision = self.record()
        reused = receipts.reuse_checked_result(self.root, self.env, self.database)
        self.assertEqual(reused["receipt_revision"], revision)
        self.assertEqual(reused["source"], "receipt")

    def test_storage_and_reuse_import_only_after_the_library_gateway(self):
        before, result, revision = self.record()
        original_import, gateway = builtins.__import__, receipts.sd_lib.import_sd_db
        operations = (
            lambda: receipts.store_check_receipt(self.root, self.env, self.database, (before[0], revision), result),
            lambda: receipts.reuse_checked_result(self.root, self.env, self.database),
        )
        for operation in operations:
            entered = []
            def enter_gateway(entered=entered):
                entered.append(True)
                return gateway()
            def guarded_import(name, *args, entered=entered, **kwargs):
                if name == "sd_db" or name.startswith("sd_db."):
                    self.assertTrue(entered, "receipt imported sd_db before its library gateway")
                return original_import(name, *args, **kwargs)
            with self.subTest(operation=operation), \
                    mock.patch.object(receipts.sd_lib, "import_sd_db", side_effect=enter_gateway), \
                    mock.patch.object(builtins, "__import__", side_effect=guarded_import):
                self.assertIsNotNone(operation())
                self.assertEqual(entered, [True])

    def test_unavailable_library_prevents_receipt_submodule_imports(self):
        before, result, _ = self.record()
        original_import = builtins.__import__
        imports = []
        def observe_import(name, *args, **kwargs):
            if name == "sd_db" or name.startswith("sd_db."):
                imports.append(name)
            return original_import(name, *args, **kwargs)
        missing = receipts.sd_lib.Imported(None, "synthetic unavailable library", "")
        with mock.patch.object(receipts.sd_lib, "import_sd_db", return_value=missing) as gateway, \
                mock.patch.object(builtins, "__import__", side_effect=observe_import):
            with self.assertRaisesRegex(receipts.Unavailable, "requires the shared database library"):
                receipts.store_check_receipt(self.root, self.env, self.database, before, result)
            self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
        self.assertEqual(gateway.call_count, 2)
        self.assertEqual(imports, [])

    def test_each_dirty_state_rejects_a_rich_receipt(self):
        for state in ("unstaged", "staged", "untracked"):
            with self.subTest(state=state):
                self.record()
                target = self.root / ("new.py" if state == "untracked" else "README.md")
                previous = target.read_bytes() if target.exists() else None
                target.write_text("changed\n")
                if state == "staged":
                    self.git("add", target.name)
                self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
                if state == "staged":
                    self.git("restore", "--staged", target.name)
                if previous is None:
                    target.unlink()
                else:
                    target.write_bytes(previous)

    def test_dependency_environment_tool_and_checker_changes_invalidate(self):
        self.record()
        original = (self.root / "dependency.txt").read_text()
        (self.root / "dependency.txt").write_text("dependency-v2")
        self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
        (self.root / "dependency.txt").write_text(original)
        self.assertIsNone(receipts.reuse_checked_result(self.root, dict(self.env, TEST_MODE="other"), self.database))
        with mock.patch.object(receipts, "tool_identity", return_value={"sha256": "changed"}):
            self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
        with mock.patch.object(receipts.sys, "version", "changed"):
            self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
        real_hash = receipts.file_digest
        with mock.patch.object(receipts, "file_digest", side_effect=lambda path: "changed" if path.name == "sd-check" else real_hash(path)):
            self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))

    def test_command_and_policy_changes_invalidate_without_a_git_change(self):
        self.record()
        detection = sd_review.sd_lib.detect_entrypoints(self.root)
        detection.commands["check"] = [sys.executable, "-c", "raise SystemExit(1)"]
        with mock.patch.object(sd_review.sd_lib, "detect_entrypoints", return_value=detection):
            self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
        alternate = self.tmp / "local.md"
        alternate.write_text("different policy")
        with mock.patch.object(sd_review.sd_lib, "local_block_path", return_value=alternate):
            self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))

    def test_failed_narrowed_dry_and_incomplete_results_never_store(self):
        before, good, _ = self.record()
        bad_values = [dict(good, status="fail"), dict(good, dry_run=True), dict(good, checks=[])]
        skipped = copy.deepcopy(good)
        skipped["checks"][0]["status"] = "skipped"
        bad_values.append(skipped)
        for result in bad_values:
            with self.subTest(result=result), self.assertRaises(receipts.Unavailable):
                receipts.store_check_receipt(self.root, self.env, self.database, before, result)

    def test_changed_during_check_and_unknown_dependencies_do_not_store(self):
        before = receipts.prepare_check_receipt(self.root, self.env, self.database)
        result = sd_check.execute(self.root, sd_review.sd_lib.detect_entrypoints(self.root), None, False, 10)
        (self.root / "dependency.txt").write_text("changed during check")
        with self.assertRaises(receipts.Unavailable):
            receipts.store_check_receipt(self.root, self.env, self.database, before, result)
        for update in ({"network": "allowed"}, {"complete": False}, {"dependencies": ["../outside"]},
                       {"environment": ["API_TOKEN"]}, {"unknown": True}):
            value = dict(self.contract, **update)
            (self.root / receipts.CONTRACT).write_text(json.dumps(value))
            self.git("add", receipts.CONTRACT)
            self.git("commit", "--quiet", "-m", "unsupported declaration")
            self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))

    def test_review_requires_per_run_opt_in(self):
        self.record()
        for opt_in, expected_calls in ((False, 1), (True, 0)):
            runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
            result = sd_review.review(self.root, namespace(reuse_check=opt_in, database=self.database),
                                      runner, self.env, self.chatgpt_home())
            self.assertEqual(sum("sd-check" in " ".join(call["argv"]) for call in runner.calls), expected_calls)
            self.assertEqual(result["check"].get("source"), "receipt" if opt_in else None)

    def test_controlled_environment_never_copies_or_hashes_credentials(self):
        env = dict(self.env, API_TOKEN="synthetic-sensitive-value")
        identity = receipts.check_binding(self.root, env)
        self.assertNotIn("synthetic-sensitive-value", json.dumps(identity))
        self.assertNotIn("API_TOKEN", receipts.receipt_environment(self.contract, env))
        self.assertEqual(identity, receipts.check_binding(self.root, self.env))

    def test_recursive_declarations_reject_credential_paths_before_hashing(self):
        directory = self.root / "declared"
        directory.mkdir()
        for name in ("credentials.json", ".git"):
            path = directory / name
            path.write_text("synthetic fixture only")
            with mock.patch.object(receipts, "file_digest") as digest:
                with self.assertRaises(receipts.Unavailable):
                    receipts.dependency_files(self.root, ["declared"])
                digest.assert_not_called()
            path.unlink()

    def test_foreign_checkout_and_malformed_checkpoint_cannot_reuse(self):
        self.record()
        foreign = self.make_repo("foreign")
        self.assertIsNone(receipts.reuse_checked_result(foreign, self.env, self.database))
        from sd_db import connect, ship
        with connect(self.database) as connection:
            revision, row = ship.read(connection, receipts.check_receipt_key(self.root))
            row["binding"]["argv"] = ["echo", "not a check"]
            ship.save(connection, receipts.check_receipt_key(self.root), revision, row)
        connection.close()
        self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))

    def test_a_started_or_failed_rerun_invalidates_the_previous_pass(self):
        self.record()
        before = receipts.prepare_check_receipt(self.root, self.env, self.database)
        self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
        with self.assertRaises(receipts.Unavailable):
            receipts.store_check_receipt(self.root, self.env, self.database, before, {"status": "fail"})
        self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sd_check.sd_lib, "repo_root", return_value=self.root), \
                mock.patch.dict(os.environ, self.env, clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sd_check.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_actual_cli_requires_explicit_storage_and_a_full_run(self):
        with mock.patch.object(receipts, "prepare_check_receipt", side_effect=AssertionError("implicit write")):
            code, out, _ = self.cli("--json")
        self.assertEqual(code, 0)
        self.assertNotIn("receipt_revision", json.loads(out))
        for modifiers in (["--only", "check"], ["--dry-run"]):
            code, _, err = self.cli("--record-receipt", *modifiers)
            self.assertEqual(code, 2)
            self.assertIn("requires an actual full check", err)
        code, out, err = self.cli("--json", "--record-receipt", "--database", str(self.database))
        self.assertEqual((code, err), (0, ""))
        self.assertGreater(json.loads(out)["receipt_revision"], 0)
        self.assertIsNotNone(receipts.reuse_checked_result(self.root, self.env, self.database))

    def test_actual_cli_reports_failed_storage_without_claiming_a_receipt(self):
        with mock.patch.object(receipts, "store_check_receipt", side_effect=receipts.Unavailable("inputs changed")):
            code, out, err = self.cli("--json", "--record-receipt", "--database", str(self.database))
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(json.loads(out)["receipt_error"], "inputs changed")
        self.assertNotIn("receipt_revision", json.loads(out))
        self.assertIsNone(receipts.reuse_checked_result(self.root, self.env, self.database))
