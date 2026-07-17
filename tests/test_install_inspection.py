from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
hashlib = _support.hashlib
io = _support.io
json = _support.json
mock = _support.mock
os = _support.os
subprocess = _support.subprocess
sys = _support.sys
Path = _support.Path
install = _support.install
INSTALLER = _support.INSTALLER
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase


class InstallInspectionTests(InstallTestCase):
    """Read-only installer status/check contract and receipt validation."""

    def run_inspection(
        self,
        root: Path,
        *args: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = self.installer_subprocess_env()
        if extra_env:
            env = {**(env or os.environ.copy()), **extra_env}
        return subprocess.run(
            [sys.executable, str(INSTALLER), str(root), *args],
            cwd=PACK_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def target_snapshot(self, root: Path) -> dict[str, tuple[int, bytes | str]]:
        snapshot: dict[str, tuple[int, bytes | str]] = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if relative == ".git" or relative.startswith(".git/"):
                continue
            if path.is_symlink():
                snapshot[relative] = (path.lstat().st_mode, os.readlink(path))
            elif path.is_file():
                snapshot[relative] = (path.stat().st_mode, path.read_bytes())
        return snapshot

    def install_current_fixture(self, *platforms: str) -> Path:
        root = self.make_repo(*platforms)
        result = self.run_install_inproc(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        return root

    def test_status_and_check_are_documented_in_help(self) -> None:
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "--help"],
            cwd=PACK_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        for option in ("--status", "--check", "--audit", "--json"):
            self.assertIn(option, result.stdout)

    def test_inspection_argument_combinations_use_argparse_errors(self) -> None:
        cases = (
            ("--status", "--check"),
            ("--audit",),
            ("--json",),
            ("--status", "--platform", "gemini"),
            ("--status", "--all"),
            ("--status", "--remove"),
            ("--status", "--force"),
            ("--status", "--backup"),
            ("--status", "--local-only"),
            ("--status", "--skip-trellis-init"),
            ("--status", "--dry-run"),
            ("--status", "--skip-diff-check"),
        )
        for args in cases:
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, str(INSTALLER), *args],
                    cwd=PACK_ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("error:", result.stdout)

    def test_not_installed_status_and_check_have_distinct_exit_codes(self) -> None:
        root = self.make_repo()
        before = self.target_snapshot(root)

        status = self.run_inspection(root, "--status", "--json")
        check = self.run_inspection(root, "--check", "--json")

        self.assertEqual(status.returncode, 0, status.stdout)
        self.assertEqual(check.returncode, install.inspection.REFRESH_REQUIRED_EXIT)
        for result, audit_requested in ((status, False), (check, True)):
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schemaVersion"], 1)
            self.assertEqual(payload["state"], "not-installed")
            self.assertEqual(payload["versionRelation"], "not-installed")
            self.assertEqual(payload["audit"]["status"], "not-applicable")
            self.assertEqual(payload["audit"]["requested"], audit_requested)
        self.assertEqual(self.target_snapshot(root), before)

    def test_status_reports_invalid_target_and_missing_trellis_as_json(self) -> None:
        missing = self.make_repo().parent / "missing-target"
        without_trellis = self.make_git_repo_without_trellis()
        for root in (missing, without_trellis):
            with self.subTest(root=root):
                result = self.run_inspection(root, "--status", "--json")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(json.loads(result.stdout)["state"], "invalid")

    def test_inspection_supports_non_trellis_manifest_and_planner_errors(self) -> None:
        root = self.make_git_repo_without_trellis()
        args = install.parse_args([str(root), "--status", "--json"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            returncode = install._run_inspection(
                args,
                root,
                {
                    "name": "sd-ai-command-pack",
                    "version": "0.16.0",
                    "requiresTrellis": False,
                },
                [],
            )
        self.assertEqual(returncode, 0)
        self.assertEqual(json.loads(output.getvalue())["state"], "not-installed")

        root = self.install_current_fixture()
        manifest_data, files = install.load_manifest()
        args = install.parse_args([str(root), "--status", "--json"])
        output = io.StringIO()
        with mock.patch.object(
            install, "selected_files", side_effect=SystemExit("error: plan failed")
        ), contextlib.redirect_stdout(output):
            returncode = install._run_inspection(
                args, root, manifest_data, files
            )
        self.assertEqual(returncode, 1)
        self.assertIn("plan failed", output.getvalue())

    def test_status_and_check_report_current_install_without_writes(self) -> None:
        root = self.install_current_fixture(".gemini")
        before = self.target_snapshot(root)

        status = self.run_inspection(root, "--status")
        check = self.run_inspection(
            root,
            "--check",
            "--json",
            extra_env={"SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0"},
        )

        self.assertEqual(status.returncode, 0, status.stdout)
        self.assertIn("state: current", status.stdout)
        self.assertIn("audit: not-requested", status.stdout)
        payload = json.loads(check.stdout)
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertEqual(payload["state"], "current")
        self.assertEqual(payload["versionRelation"], "current")
        self.assertEqual(payload["platforms"]["installed"], ["gemini"])
        self.assertEqual(payload["platforms"]["active"], ["gemini"])
        self.assertEqual(payload["changeCount"], 0)
        self.assertEqual(payload["audit"]["status"], "passed")
        self.assertIn("audit passed", payload["audit"]["output"])
        self.assertNotIn("skipping install audit", payload["audit"]["output"])
        self.assertEqual(self.target_snapshot(root), before)

    def test_valid_behind_and_ahead_receipts_require_refresh(self) -> None:
        for installed_version, relation in (
            ("0.15.6", "behind"),
            ("9.0.0", "ahead"),
        ):
            with self.subTest(installed_version=installed_version):
                root = self.install_current_fixture()
                for relative in (
                    install.PACK_MANIFEST_FILE,
                    install.PROVENANCE_FILE,
                ):
                    path = root / relative
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["version"] = installed_version
                    path.write_text(
                        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                    )

                result = self.run_inspection(root, "--check", "--json")

                self.assertEqual(
                    result.returncode,
                    install.inspection.REFRESH_REQUIRED_EXIT,
                    result.stdout,
                )
                payload = json.loads(result.stdout)
                self.assertEqual(payload["state"], "refresh-required")
                self.assertEqual(payload["versionRelation"], relation)
                self.assertGreater(payload["changeCount"], 0)

    def test_audit_clean_source_changed_target_requires_refresh(self) -> None:
        root = self.install_current_fixture()
        provenance_path = root / install.PROVENANCE_FILE
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        relative = sorted(provenance["files"])[0]
        changed = b"valid content from the installed release\n"
        (root / relative).write_bytes(changed)
        provenance["files"][relative] = (
            "sha256:" + hashlib.sha256(changed).hexdigest()
        )
        provenance_path.write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
        )

        result = self.run_inspection(root, "--check", "--json")

        self.assertEqual(
            result.returncode, install.inspection.REFRESH_REQUIRED_EXIT, result.stdout
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "refresh-required")
        self.assertEqual(payload["audit"]["status"], "passed")
        self.assertGreater(payload["counts"]["conflict"], 0)

    def test_vouched_content_drift_is_invalid_with_or_without_audit(self) -> None:
        root = self.install_current_fixture()
        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        target = sorted(provenance["files"])[0]
        (root / target).write_text("locally drifted\n", encoding="utf-8")

        for args in (("--status", "--json"), ("--check", "--json")):
            with self.subTest(args=args):
                result = self.run_inspection(root, *args)
                self.assertEqual(result.returncode, 1, result.stdout)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["state"], "invalid")
                self.assertTrue(
                    any("content drifted" in reason for reason in payload["reasons"])
                )

    def test_malformed_and_partial_receipts_are_invalid_json_reports(self) -> None:
        cases = ("partial", "manifest-json", "unsafe-target", "provenance-shape")
        for case in cases:
            with self.subTest(case=case):
                root = self.install_current_fixture()
                if case == "partial":
                    (root / install.PROVENANCE_FILE).unlink()
                elif case == "manifest-json":
                    (root / install.PACK_MANIFEST_FILE).write_text(
                        "{not json", encoding="utf-8"
                    )
                elif case == "unsafe-target":
                    (root / install.INSTALLED_TARGETS_FILE).write_text(
                        "../outside\n", encoding="utf-8"
                    )
                else:
                    (root / install.PROVENANCE_FILE).write_text(
                        '{"pack": "sd-ai-command-pack", "version": "0.16.0", '
                        '"files": []}\n',
                        encoding="utf-8",
                    )

                result = self.run_inspection(root, "--status", "--json")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(json.loads(result.stdout)["state"], "invalid")

    def test_status_audit_failure_is_invalid_and_keeps_diagnostics(self) -> None:
        root = self.install_current_fixture()
        failure = install.inspection.AuditResult(True, "failed", 1, "error: broken")
        output = io.StringIO()
        with mock.patch.object(
            install.inspection, "run_install_audit", return_value=failure
        ), contextlib.redirect_stdout(output):
            returncode = install.main([str(root), "--status", "--audit", "--json"])

        self.assertEqual(returncode, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["state"], "invalid")
        self.assertEqual(payload["audit"]["output"], "error: broken")

    def test_audit_runner_reports_timeout_and_spawn_errors(self) -> None:
        root = self.make_repo()
        timeout = subprocess.TimeoutExpired("audit", 60, output="partial\n")
        with mock.patch.object(
            install.inspection.subprocess, "run", side_effect=timeout
        ):
            result = install.inspection.run_install_audit(root)
        self.assertEqual(result.status, "error")
        self.assertIn("partial", result.output)
        self.assertIn("timed out", result.output)

        timeout = subprocess.TimeoutExpired("audit", 60, output=b"bytes\n")
        with mock.patch.object(
            install.inspection.subprocess, "run", side_effect=timeout
        ):
            result = install.inspection.run_install_audit(root)
        self.assertIn("bytes", result.output)

        with mock.patch.object(
            install.inspection.subprocess, "run", side_effect=OSError("missing")
        ):
            result = install.inspection.run_install_audit(root)
        self.assertEqual(result.status, "error")
        self.assertIn("cannot run", result.output)

    def test_version_relation_handles_all_stable_and_unknown_cases(self) -> None:
        relation = install.inspection.version_relation
        self.assertEqual(relation(None, "0.16.0"), "not-installed")
        self.assertEqual(relation("0.15.7", "0.16.0"), "behind")
        self.assertEqual(relation("0.16.0", "0.16.0"), "current")
        self.assertEqual(relation("1.0.0", "0.16.0"), "ahead")
        self.assertEqual(relation("dev", "0.16.0"), "unknown")

    def test_receipt_reader_defensive_validation_paths(self) -> None:
        module = install.inspection
        root = self.make_repo()
        errors: list[str] = []

        self.assertIsNone(module._load_json_object(root / "missing", "test", errors))
        payload_path = root / "payload.json"
        payload_path.write_text("[]\n", encoding="utf-8")
        self.assertIsNone(module._load_json_object(payload_path, "test", errors))
        with mock.patch.object(Path, "read_text", side_effect=UnicodeError("bad")):
            self.assertIsNone(module._load_json_object(payload_path, "test", errors))

        for unsafe in ("", "/absolute", "C:\\absolute", "a/../b", "..\\b"):
            self.assertFalse(module._safe_receipt_target(unsafe), unsafe)
        self.assertTrue(module._safe_receipt_target("scripts/check.py"))

        receipt = root / "targets.txt"
        self.assertEqual(module._read_target_receipt(receipt, errors), frozenset())
        receipt.write_text(
            "\n# comment\nscripts/check.py\nscripts/check.py\n../unsafe\n",
            encoding="utf-8",
        )
        self.assertEqual(
            module._read_target_receipt(receipt, errors),
            frozenset({"scripts/check.py"}),
        )
        with mock.patch.object(Path, "read_text", side_effect=OSError("denied")):
            self.assertEqual(module._read_target_receipt(receipt, errors), frozenset())
        self.assertTrue(any("duplicate" in error for error in errors))
        self.assertTrue(any("unsafe" in error for error in errors))

    def test_manifest_and_provenance_defensive_validation_paths(self) -> None:
        module = install.inspection
        root = self.make_repo()
        errors: list[str] = []
        self.assertEqual(module._manifest_platforms(None, frozenset(), errors), (None, ()))
        self.assertEqual(
            module._manifest_platforms({"version": 1, "files": {}}, frozenset(), errors),
            (None, ()),
        )
        version, platforms = module._manifest_platforms(
            {
                "version": "1.0.0",
                "files": [
                    "bad",
                    {"target": "shared", "platform": "shared"},
                    {"target": "other", "platform": "gemini"},
                    {"target": "adapter", "platform": 3},
                    {"target": "adapter", "platform": "gemini"},
                ],
            },
            frozenset({"shared", "adapter"}),
            errors,
        )
        self.assertEqual(version, "1.0.0")
        self.assertEqual(platforms, ("gemini",))

        module._validate_provenance(root, None, None, frozenset(), errors)
        module._validate_provenance(
            root,
            {"pack": "wrong", "version": "2.0.0", "files": []},
            "1.0.0",
            frozenset(),
            errors,
        )
        good = root / "good.txt"
        good.write_text("good\n", encoding="utf-8")
        digest = "sha256:" + hashlib.sha256(good.read_bytes()).hexdigest()
        provenance = {
            "pack": "sd-ai-command-pack",
            "version": "1.0.0",
            "files": {
                3: digest,
                "absent-from-receipt.txt": "bad",
                "missing.txt": digest,
                "good.txt": digest,
                "drift.txt": digest,
            },
        }
        drift = root / "drift.txt"
        drift.write_text("drift\n", encoding="utf-8")
        module._validate_provenance(
            root,
            provenance,
            "1.0.0",
            frozenset({"missing.txt", "good.txt", "drift.txt"}),
            errors,
        )
        with mock.patch.object(Path, "read_bytes", side_effect=OSError("denied")):
            module._validate_provenance(
                root,
                {
                    "pack": "sd-ai-command-pack",
                    "version": "1.0.0",
                    "files": {"good.txt": digest},
                },
                "1.0.0",
                frozenset({"good.txt"}),
                errors,
            )
        expected = (
            "missing a string version",
            "missing its files array",
            "non-object file entry",
            "unexpected pack name",
            "versions do not match",
            "missing its files object",
            "unsafe target",
            "absent from installed-targets",
            "invalid digest",
            "missing or invalid",
            "content drifted",
            "cannot read vouched target",
        )
        for phrase in expected:
            self.assertTrue(any(phrase in error for error in errors), phrase)

    def test_receipt_inspection_detects_missing_recorded_target(self) -> None:
        empty_root = self.make_repo()
        self.assertFalse(install.inspection.inspect_receipts(empty_root).present)

        root = self.install_current_fixture()
        receipt = root / install.INSTALLED_TARGETS_FILE
        with receipt.open("a", encoding="utf-8") as stream:
            stream.write("missing-recorded-target.txt\n")

        state = install.inspection.inspect_receipts(root)

        self.assertTrue(state.present)
        self.assertTrue(any("installed target is missing" in item for item in state.errors))

        (root / install.PROVENANCE_FILE).unlink()
        partial = install.inspection.inspect_receipts(root)
        self.assertTrue(any("footprint is incomplete" in item for item in partial.errors))

    def test_audit_runner_captures_pass_and_failure_and_clears_disable_env(self) -> None:
        root = self.make_repo()
        completed = subprocess.CompletedProcess([], 0, stdout="passed\n")
        with mock.patch.dict(
            os.environ, {"SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0"}
        ), mock.patch.object(
            install.inspection.subprocess, "run", return_value=completed
        ) as run:
            result = install.inspection.run_install_audit(root)
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.output, "passed")
        self.assertNotIn("SD_AI_COMMAND_PACK_INSTALL_AUDIT", run.call_args.kwargs["env"])

        completed = subprocess.CompletedProcess([], 7, stdout="failed\n")
        with mock.patch.object(
            install.inspection.subprocess, "run", return_value=completed
        ):
            result = install.inspection.run_install_audit(root)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.exit_code, 7)

    def test_report_helpers_cover_refresh_removal_and_human_diagnostics(self) -> None:
        module = install.inspection
        root = self.make_repo()
        manifest_data = {"name": "sd-ai-command-pack", "version": "0.16.0"}
        receipts = module.ReceiptState(
            True, "0.16.0", frozenset(), ("gemini",), ()
        )
        file = self.valid_pack_file()
        install_results = [
            install.InstallResult(file, status)
            for status in (
                install.InstallStatus.CREATED,
                install.InstallStatus.UPDATED,
                install.InstallStatus.OVERWRITTEN,
                install.InstallStatus.CONFLICT,
                install.InstallStatus.SYMLINK_CONFLICT,
                install.InstallStatus.UNCHANGED,
                install.InstallStatus.PRESERVED,
            )
        ]
        retired_results = [
            install.RemoveResult(Path("old"), status)
            for status in (
                install.RemoveStatus.UPDATED,
                install.RemoveStatus.REMOVED,
                install.RemoveStatus.WOULD_UPDATE,
                install.RemoveStatus.WOULD_REMOVE,
                install.RemoveStatus.RETIRED,
                install.RemoveStatus.RETIRED_PRESERVED,
                install.RemoveStatus.WOULD_RETIRE,
                install.RemoveStatus.UNCHANGED,
            )
        ]
        audit = module.not_requested_audit()
        report = module.build_report(
            manifest_data=manifest_data,
            target=root,
            receipts=receipts,
            install_results=install_results,
            retired_results=retired_results,
            audit=audit,
        )
        self.assertEqual(report.state, "refresh-required")
        self.assertEqual(report.change_count, 12)
        self.assertIn("result counts:", module.render_human(report))
        self.assertEqual(module.report_exit_code(report, check=True), 3)
        self.assertEqual(module.report_exit_code(report, check=False), 0)

        failed = module.build_report(
            manifest_data=manifest_data,
            target=root,
            receipts=receipts,
            install_results=[],
            retired_results=[],
            audit=module.AuditResult(True, "error", None, "line one\nline two"),
        )
        human = module.render_human(failed)
        self.assertIn("audit output:", human)
        self.assertIn("  line two", human)
        self.assertEqual(module.report_exit_code(failed, check=False), 1)

        invalid = module.build_report(
            manifest_data=manifest_data,
            target=root,
            receipts=module.ReceiptState(
                True, "0.16.0", frozenset(), (), ("bad receipt",)
            ),
            install_results=[],
            retired_results=[],
            audit=audit,
        )
        self.assertEqual(invalid.state, "invalid")

        missing = module.build_report(
            manifest_data=manifest_data,
            target=root,
            receipts=module.ReceiptState(False, None, frozenset(), (), ()),
            install_results=[],
            retired_results=[],
            audit=module.not_requested_audit(applicable=False, requested=True),
        )
        self.assertEqual(missing.state, "not-installed")
        self.assertTrue(missing.audit.requested)

        behind = module.build_report(
            manifest_data=manifest_data,
            target=root,
            receipts=module.ReceiptState(
                True, "0.15.0", frozenset(), (), ()
            ),
            install_results=[],
            retired_results=[],
            audit=audit,
        )
        self.assertEqual(behind.state, "refresh-required")
        self.assertTrue(any("behind" in reason for reason in behind.reasons))

        current = module.build_report(
            manifest_data=manifest_data,
            target=root,
            receipts=receipts,
            install_results=[],
            retired_results=[],
            audit=audit,
        )
        self.assertEqual(current.state, "current")

        empty_report = module.InspectionReport(
            pack="sd-ai-command-pack",
            target=root,
            source_version="0.16.0",
            installed_version="0.16.0",
            version_relation="current",
            state="current",
            installed_platforms=(),
            active_platforms=(),
            counts={},
            change_count=0,
            reasons=(),
            audit=audit,
        )
        self.assertNotIn("reasons:", module.render_human(empty_report))


if __name__ == "__main__":
    _support.unittest.main()
