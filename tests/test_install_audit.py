from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
hashlib = _support.hashlib
importlib = _support.importlib
io = _support.io
json = _support.json
os = _support.os
re = _support.re
shutil = _support.shutil
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
mock = _support.mock
Path = _support.Path
yaml = _support.yaml
install = _support.install
PACK_ROOT = _support.PACK_ROOT
INSTALLER = _support.INSTALLER
SECRET_MARKER_PATTERNS = _support.SECRET_MARKER_PATTERNS
InstallTestCase = _support.InstallTestCase


class InstallAuditTests(InstallTestCase):
    """Tests for install audit, provenance, receipts, and legacy advisories."""

    def test_install_audit_discovers_pack_like_files_on_newer_platforms(
        self,
    ) -> None:
        audit = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_scan_bases",
        )
        for pattern in audit.PACK_FILE_PATTERNS:
            self.assertTrue(
                any(
                    pattern == base or pattern.startswith(f"{base}/")
                    for base in audit.pack_scan_bases()
                ),
                f"pattern {pattern} unreachable from derived scan bases",
            )

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        rogue = root / ".qoder/skills/sd-rogue/SKILL.md"
        rogue.parent.mkdir(parents=True, exist_ok=True)
        rogue.write_text("# not installed by the pack\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(".qoder/skills/sd-rogue/SKILL.md", result.stdout)
        self.assertIn(
            "error: pack-like file is not listed in installed targets",
            result.stdout,
        )

    def test_install_audit_allows_source_only_fleet_files_in_source_repo(self) -> None:
        audit = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_source_only",
        )
        root = self.make_repo()
        for marker in audit.SOURCE_REPO_MARKERS:
            path = root / marker
            if marker.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# source marker\n", encoding="utf-8")
            else:
                path.mkdir(parents=True, exist_ok=True)
        for relative_path in audit.SOURCE_ONLY_ALLOWED_PACK_FILES:
            source_only = root / relative_path
            source_only.parent.mkdir(parents=True, exist_ok=True)
            source_only.write_text("# source-only fleet file\n", encoding="utf-8")

        failures, warnings = audit.audit_structural_state(root, set())

        self.assertEqual(failures, [])
        self.assertEqual(warnings, [])
        self.assertEqual(
            audit.SOURCE_ONLY_ALLOWED_PACK_FILES
            - {
                "scripts/sd-ai-command-pack-fleet-candidate-check.py",
                "scripts/sd-ai-command-pack-fleet-finding-classify.py",
                "scripts/sd-ai-command-pack-fleet-preflight.py",
                "scripts/sd-ai-command-pack-fleet-review-classify.py",
                "scripts/sd-ai-command-pack-fleet-timing.py",
                "scripts/sd-ai-command-pack-fleet-wave-plan.py",
                "scripts/sd-ai-command-pack-fleet-controller.py",
                ".agents/skills/sd-fleet-refresh/references/controller-recovery.md",
                "scripts/sd_ai_command_pack_fleet_lib.py",
            },
            set(install.SOURCE_ONLY_COMMAND_TARGETS),
        )

    def test_consumer_audit_does_not_require_source_only_fleet_helpers(self) -> None:
        audit = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_consumer_source_only",
        )
        root = self.make_repo()
        install_result = self.run_install(root)
        self.assertEqual(install_result.returncode, 0, install_result.stdout)

        targets = set(
            (root / ".sd-ai-command-pack/installed-targets.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        source_only_helpers = {
            path
            for path in audit.SOURCE_ONLY_ALLOWED_PACK_FILES
            if path.startswith("scripts/sd-ai-command-pack-fleet-")
        }
        self.assertTrue(source_only_helpers)
        for path in source_only_helpers:
            self.assertNotIn(path, targets)
            self.assertFalse((root / path).exists())

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("SD AI command pack install audit passed", result.stdout)

    def test_install_audit_detects_missing_current_targets(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        (root / ".agents/skills/sd-review-pr/SKILL.md").unlink()

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "installed target is missing: .agents/skills/sd-review-pr/SKILL.md",
            result.stdout,
        )

    def test_install_writes_pack_manifest_snapshot(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        manifest, _ = install.load_manifest()
        installed_manifest = json.loads(
            (root / install.PACK_MANIFEST_FILE).read_text(encoding="utf-8")
        )
        receipt_text = (root / install.INSTALLED_TARGETS_FILE).read_text(
            encoding="utf-8"
        )
        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )

        self.assertEqual(installed_manifest["name"], manifest["name"])
        self.assertEqual(installed_manifest["version"], manifest["version"])
        self.assertIn(install.PACK_MANIFEST_FILE.as_posix(), receipt_text)
        self.assertNotIn(install.PACK_MANIFEST_FILE.as_posix(), provenance["files"])

    def test_install_pack_manifest_file_updates_existing_snapshot(self) -> None:
        root = self.make_repo()
        manifest = {
            "name": "sd-ai-command-pack",
            "version": "9.9.9",
            "files": [],
        }
        destination = root / install.PACK_MANIFEST_FILE
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('{"version": "old"}\n', encoding="utf-8")

        result = install.install_pack_manifest_file(
            manifest,
            root,
            dry_run=False,
        )

        self.assertEqual(result.status, "updated")
        self.assertEqual(
            json.loads(destination.read_text(encoding="utf-8")),
            manifest,
        )

    def test_install_pack_manifest_file_dry_run_reports_update(self) -> None:
        root = self.make_repo()
        manifest = {
            "name": "sd-ai-command-pack",
            "version": "9.9.9",
            "files": [],
        }
        destination = root / install.PACK_MANIFEST_FILE
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('{"version": "old"}\n', encoding="utf-8")

        result = install.install_pack_manifest_file(
            manifest,
            root,
            dry_run=True,
        )

        self.assertEqual(result.status, "updated")
        self.assertEqual(destination.read_text(encoding="utf-8"), '{"version": "old"}\n')

    def test_install_audit_fails_when_expected_target_is_missing_from_receipt(
        self,
    ) -> None:
        root = self.make_repo(".claude")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        target = ".claude/commands/sd/work-backlog.md"
        (root / target).unlink()
        receipt = root / install.INSTALLED_TARGETS_FILE
        receipt.write_text(
            "".join(
                line
                for line in receipt.read_text(encoding="utf-8").splitlines(
                    keepends=True
                )
                if line.strip() != target
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            f"expected installed target is missing from receipt: {target}",
            result.stdout,
        )

    def test_install_audit_expected_platform_catches_absent_platform(self) -> None:
        root = self.make_repo(".claude")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
                "--expected-platform",
                "cursor",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "expected installed target is missing from receipt: "
            ".cursor/commands/sd-continue.md",
            result.stdout,
        )

    def test_refresh_detects_new_target_skipped_with_inactive_claude(self) -> None:
        root = self.make_repo(".claude")
        target = ".claude/commands/sd/work-backlog.md"

        pack_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-legacy-fixture-"
        )
        self.addCleanup(pack_tempdir.cleanup)
        legacy_pack = Path(pack_tempdir.name)
        shutil.copytree(PACK_ROOT / "installer", legacy_pack / "installer")
        shutil.copytree(PACK_ROOT / "templates", legacy_pack / "templates")
        shutil.copyfile(INSTALLER, legacy_pack / "install.py")

        manifest = json.loads(
            (PACK_ROOT / "manifest.json").read_text(encoding="utf-8")
        )
        manifest["version"] = "0.6.99"
        manifest["files"] = [
            record for record in manifest["files"] if record["target"] != target
        ]
        (legacy_pack / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        legacy_env = os.environ.copy()
        legacy_env.pop("COVERAGE_PROCESS_START", None)
        legacy_env.pop("COVERAGE_FILE", None)

        initial = subprocess.run(
            [
                sys.executable,
                str(legacy_pack / "install.py"),
                str(root),
                "--skip-diff-check",
            ],
            cwd=legacy_pack,
            env=legacy_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(initial.returncode, 0, initial.stdout)
        self.assertFalse((root / target).exists())

        for marker in install.ACTIVE_TRELLIS_PLATFORM_MARKERS["claude"]:
            (root / marker).unlink(missing_ok=True)

        refresh = self.run_install(root)

        self.assertEqual(refresh.returncode, 0, refresh.stdout)
        self.assertIn(
            f"skipped     {target} "
            "(active Trellis claude install not detected)",
            refresh.stdout,
        )
        self.assertIn(
            "kept-in-receipt .claude/commands/sd/start.md",
            refresh.stdout,
        )
        receipt = (root / install.INSTALLED_TARGETS_FILE).read_text(
            encoding="utf-8"
        )
        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        self.assertIn(".claude/commands/sd/start.md", receipt)
        self.assertNotIn(target, receipt)
        self.assertFalse((root / target).exists())
        self.assertNotIn(target, provenance["files"])

        audit_script = root / "scripts/sd-ai-command-pack-install-audit.py"
        ordinary_audit = subprocess.run(
            [sys.executable, str(audit_script)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(ordinary_audit.returncode, 1, ordinary_audit.stdout)
        self.assertIn(
            f"expected installed target is missing from receipt: {target}",
            ordinary_audit.stdout,
        )

        fleet_audit = subprocess.run(
            [sys.executable, str(audit_script), "--expected-platform", "claude"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(fleet_audit.returncode, 1, fleet_audit.stdout)
        self.assertIn(
            f"expected installed target is missing from receipt: {target}",
            fleet_audit.stdout,
        )

    def test_install_preserves_receipt_entries_for_undetected_platform(self) -> None:
        root = self.make_repo(".claude")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        receipt = root / install.INSTALLED_TARGETS_FILE
        self.assertIn(".claude/commands/sd/start.md", receipt.read_text(encoding="utf-8"))

        # A checkout where the gitignored Trellis claude markers are absent:
        # the platform is undetected, but the tracked receipt must keep the
        # entries another checkout legitimately installed.
        shutil.rmtree(root / ".claude")
        (root / ".claude").mkdir()

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(".claude/commands/sd/start.md", receipt.read_text(encoding="utf-8"))
        self.assertIn("kept-in-receipt .claude/commands/sd/start.md", result.stdout)
        self.assertIn("claude adapter not selected in this checkout", result.stdout)

    def test_install_platform_filter_preserves_other_receipt_entries(self) -> None:
        root = self.make_repo(".claude", ".gemini")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = self.run_install(root, "--platform", "gemini")

        self.assertEqual(result.returncode, 0, result.stdout)
        receipt_text = (root / install.INSTALLED_TARGETS_FILE).read_text(encoding="utf-8")
        self.assertIn(".claude/commands/sd/start.md", receipt_text)
        self.assertIn("kept-in-receipt .claude/commands/sd/start.md", result.stdout)

    def test_install_drops_receipt_entries_for_removed_tracked_anchor(self) -> None:
        root = self.make_repo(".claude")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        # Anchor removed and not gitignored: reads as intentional platform
        # removal, so the receipt entries drop as before.
        shutil.rmtree(root / ".claude")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        receipt_text = (root / install.INSTALLED_TARGETS_FILE).read_text(encoding="utf-8")
        self.assertNotIn(".claude/commands/sd/start.md", receipt_text)
        self.assertNotIn("kept-in-receipt", result.stdout)

    def test_install_keeps_receipt_entries_for_gitignored_absent_anchor(self) -> None:
        root = self.make_repo(".claude")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        # A fresh checkout of a repo that gitignores .claude/ entirely: the
        # anchor itself is local-only, so its receipt entries must survive.
        shutil.rmtree(root / ".claude")
        gitignore = root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + ".claude/\n",
            encoding="utf-8",
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        receipt_text = (root / install.INSTALLED_TARGETS_FILE).read_text(encoding="utf-8")
        self.assertIn(".claude/commands/sd/start.md", receipt_text)
        self.assertIn("kept-in-receipt .claude/commands/sd/start.md", result.stdout)

    def test_install_audit_downgrades_gitignored_missing_targets(self) -> None:
        root = self.make_repo(".claude")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        shutil.rmtree(root / ".claude")
        gitignore = root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + ".claude/\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "installed target is gitignored and absent in this checkout: "
            ".claude/commands/sd/start.md",
            result.stdout,
        )
        self.assertIn("re-run the pack installer here", result.stdout)
        self.assertIn("install audit passed", result.stdout)

    def test_install_audit_keeps_error_for_missing_targets_without_git(self) -> None:
        root = self.make_repo(".claude")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        shutil.rmtree(root / ".claude")
        gitignore = root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + ".claude/\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            env={**os.environ, "PATH": ""},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "installed target is missing: .claude/commands/sd/start.md",
            result.stdout,
        )

    def test_install_audit_batches_structural_gitignore_candidates(self) -> None:
        audit = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_structural_batch",
        )
        root = self.make_repo()
        missing_target = ".claude/commands/sd/start.md"
        unlisted_pack_file = "scripts/sd-ai-command-pack-extra.py"
        extra_path = root / unlisted_pack_file
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_text("# local-only helper\n", encoding="utf-8")
        calls: list[bytes] = []

        def fake_check_ignore(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            self.assertEqual(args[:4], ["git", "-C", str(root), "check-ignore"])
            input_payload = kwargs["input"]
            self.assertIsInstance(input_payload, bytes)
            calls.append(input_payload)
            ignored = f"{missing_target}\0{unlisted_pack_file}\0".encode()
            return subprocess.CompletedProcess(args, 0, stdout=ignored)

        with mock.patch.object(audit.subprocess, "run", side_effect=fake_check_ignore):
            failures, warnings = audit.audit_structural_state(root, {missing_target})

        self.assertEqual(failures, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            set(calls[0].decode().strip("\0").split("\0")),
            {missing_target, unlisted_pack_file},
        )
        self.assertIn(
            "installed target is gitignored and absent in this checkout: "
            f"{missing_target}",
            "\n".join(warnings),
        )
        self.assertIn(
            "local-only pack-like file is not recorded in installed targets: "
            f"{unlisted_pack_file}",
            "\n".join(warnings),
        )

    def test_install_audit_check_ignore_exit_one_means_no_matches(self) -> None:
        audit = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_check_ignore_none",
        )
        root = self.make_repo()
        missing_target = ".claude/commands/sd/start.md"
        unlisted_pack_file = "scripts/sd-ai-command-pack-extra.py"
        extra_path = root / unlisted_pack_file
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_text("# tracked helper\n", encoding="utf-8")
        calls = 0

        def fake_check_ignore(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            nonlocal calls
            calls += 1
            return subprocess.CompletedProcess(args, 1, stdout=b"")

        with mock.patch.object(audit.subprocess, "run", side_effect=fake_check_ignore):
            failures, warnings = audit.audit_structural_state(root, {missing_target})

        self.assertEqual(warnings, [])
        self.assertEqual(calls, 1)
        self.assertIn(f"installed target is missing: {missing_target}", failures)
        self.assertIn(
            f"pack-like file is not listed in installed targets: {unlisted_pack_file}",
            failures,
        )

    def test_install_audit_batches_expected_target_gitignore_candidates(self) -> None:
        audit = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_expected_batch",
        )
        root = self.make_repo()
        ignored_target = ".claude/commands/sd/start.md"
        missing_target = ".gemini/commands/sd/start.toml"
        manifest = {
            "files": [
                {"platform": "shared", "target": ignored_target},
                {"platform": "shared", "target": missing_target},
            ]
        }
        calls: list[bytes] = []

        def fake_check_ignore(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            input_payload = kwargs["input"]
            self.assertIsInstance(input_payload, bytes)
            calls.append(input_payload)
            return subprocess.CompletedProcess(args, 0, stdout=f"{ignored_target}\0".encode())

        with mock.patch.object(audit.subprocess, "run", side_effect=fake_check_ignore):
            failures, warnings, expected_count, selected_platforms = (
                audit.audit_expected_targets(
                    root,
                    set(),
                    manifest,
                    explicit_platforms=[],
                )
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            set(calls[0].decode().strip("\0").split("\0")),
            {
                ignored_target,
                missing_target,
                install.INSTALLED_TARGETS_FILE.as_posix(),
                install.PACK_MANIFEST_FILE.as_posix(),
                install.PROVENANCE_FILE.as_posix(),
            },
        )
        self.assertEqual(expected_count, 5)
        self.assertEqual(selected_platforms, set())
        self.assertIn(
            f"expected installed target is missing from receipt: {ignored_target}",
            failures,
        )
        self.assertIn(
            f"expected installed target is missing: {missing_target}",
            failures,
        )
        self.assertIn(
            "expected installed target is gitignored and absent in this checkout: "
            f"{ignored_target}",
            "\n".join(warnings),
        )

    def test_install_audit_batches_provenance_missing_targets(self) -> None:
        audit = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_provenance_batch",
        )
        root = self.make_repo()
        ignored_target = ".claude/commands/sd/start.md"
        missing_target = ".gemini/commands/sd/start.toml"
        provenance = root / install.PROVENANCE_FILE
        provenance.parent.mkdir(parents=True, exist_ok=True)
        provenance.write_text(
            json.dumps(
                {
                    "version": "9.9.9",
                    "files": {
                        ignored_target: "sha256:" + "0" * 64,
                        missing_target: "sha256:" + "1" * 64,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        calls: list[bytes] = []

        def fake_check_ignore(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            input_payload = kwargs["input"]
            self.assertIsInstance(input_payload, bytes)
            calls.append(input_payload)
            return subprocess.CompletedProcess(args, 0, stdout=f"{ignored_target}\0".encode())

        with mock.patch.object(audit.subprocess, "run", side_effect=fake_check_ignore):
            failures, version = audit.audit_provenance(root)

        self.assertEqual(version, "9.9.9")
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            set(calls[0].decode().strip("\0").split("\0")),
            {ignored_target, missing_target},
        )
        self.assertEqual(
            failures,
            [f"vouched target is missing: {missing_target}"],
        )

    def test_install_writes_provenance_with_hashed_targets(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        manifest, _ = install.load_manifest()
        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(provenance["pack"], manifest["name"])
        self.assertEqual(provenance["version"], manifest["version"])
        files = provenance["files"]
        self.assertIn("scripts/sd-ai-command-pack-full-check.sh", files)
        self.assertIn("scripts/sd-ai-command-pack-toolchain.sh", files)
        self.assertIn("scripts/sd_ai_command_pack_lib.py", files)
        self.assertTrue(
            files["scripts/sd-ai-command-pack-full-check.sh"].startswith("sha256:")
        )
        helper_target = "scripts/sd-ai-command-pack-update-spec-kb.py"
        helper_source = install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
        helper_content = helper_source.read_bytes()
        self.assertEqual((root / helper_target).read_bytes(), helper_content)
        self.assertEqual(
            files[helper_target],
            "sha256:" + hashlib.sha256(helper_content).hexdigest(),
        )
        # User-tunable and generated files are never vouched.
        self.assertNotIn(".prism/rules.json", files)
        self.assertNotIn(".gitignore", files)
        self.assertNotIn(".sd-ai-command-pack/installed-targets.txt", files)
        self.assertNotIn(".sd-ai-command-pack/manifest.json", files)
        self.assertNotIn(".sd-ai-command-pack/provenance.json", files)
        self.assertIn(
            ".sd-ai-command-pack/provenance.json",
            (root / install.INSTALLED_TARGETS_FILE).read_text(encoding="utf-8"),
        )

    def test_install_audit_flags_drifted_hashed_target(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        script.write_text(
            script.read_text(encoding="utf-8") + "\n# tampered\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("drifted from pack", result.stdout)
        self.assertIn("scripts/sd-ai-command-pack-full-check.sh", result.stdout)

    def test_install_audit_reports_installed_payload_provenance_version(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        manifest, _ = install.load_manifest()
        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("install audit passed", result.stdout)
        self.assertIn(
            "Installed payload provenance: "
            f"version {manifest['version']}; vouched file hashes match.",
            result.stdout,
        )

    def test_install_audit_advises_on_upstream_pack_version(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        manifest, _ = install.load_manifest()

        with tempfile.TemporaryDirectory() as temp_dir:
            reference = Path(temp_dir) / "manifest.json"
            cases = (
                ("99.0.0", "is behind upstream 99.0.0"),
                (manifest["version"], f"is current with upstream {manifest['version']}"),
                ("0.0.1", "is ahead of upstream 0.0.1"),
                ("next", "could not compare"),
            )
            for version, expected in cases:
                with self.subTest(version=version):
                    reference.write_text(
                        json.dumps({"version": version}) + "\n",
                        encoding="utf-8",
                    )
                    audit = subprocess.run(
                        [
                            sys.executable,
                            str(
                                PACK_ROOT
                                / "scripts/sd-ai-command-pack-install-audit.py"
                            ),
                            "--upstream-manifest",
                            str(reference),
                        ],
                        cwd=root,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                    self.assertEqual(audit.returncode, 0, audit.stdout)
                    self.assertIn(expected, audit.stdout)

            missing = subprocess.run(
                [
                    sys.executable,
                    str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
                    "--upstream-manifest",
                    str(Path(temp_dir) / "missing.json"),
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(missing.returncode, 0, missing.stdout)
            self.assertIn("could not determine upstream version", missing.stdout)

            invalid_utf8 = Path(temp_dir) / "invalid-utf8.json"
            invalid_utf8.write_bytes(b'\xff{"version": "99.0.0"}\n')
            malformed = subprocess.run(
                [
                    sys.executable,
                    str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
                    "--upstream-manifest",
                    str(invalid_utf8),
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(malformed.returncode, 0, malformed.stdout)
            self.assertIn("could not determine upstream version", malformed.stdout)

    def test_install_audit_ignores_user_tuned_preserved_files(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        (root / ".prism/rules.json").write_text('{"tuned": true}\n', encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("drifted from pack", result.stdout)

    def test_install_audit_fails_on_malformed_provenance(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        provenance = root / install.PROVENANCE_FILE
        provenance.write_text("not json\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("unreadable or malformed", result.stdout)

        provenance.write_text("{}\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("has no files map", result.stdout)

        provenance.write_text('{"files": {}}\n', encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("has an empty files map", result.stdout)

    def test_install_audit_passes_without_provenance_file(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        # Old installs have no provenance or installed manifest snapshot:
        # remove those files and receipt lines so the audit behaves as before
        # the generated-state checks existed.
        (root / install.PROVENANCE_FILE).unlink()
        (root / install.PACK_MANIFEST_FILE).unlink()
        receipt = root / install.INSTALLED_TARGETS_FILE
        receipt.write_text(
            "".join(
                line
                for line in receipt.read_text(encoding="utf-8").splitlines(
                    keepends=True
                )
                if "provenance.json" not in line and "manifest.json" not in line
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Installed payload provenance:", result.stdout)

    def test_platform_filter_run_keeps_provenance_entries(self) -> None:
        root = self.make_repo(".claude", ".gemini")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        provenance_path = root / install.PROVENANCE_FILE
        before = json.loads(provenance_path.read_text(encoding="utf-8"))["files"]
        self.assertIn(".claude/commands/sd/start.md", before)

        result = self.run_install(root, "--platform", "gemini")

        self.assertEqual(result.returncode, 0, result.stdout)
        after = json.loads(provenance_path.read_text(encoding="utf-8"))["files"]
        self.assertIn(".claude/commands/sd/start.md", after)
        self.assertIn(".gemini/commands/sd/start.toml", after)

    def test_install_drops_hand_vouched_generated_entries(self) -> None:
        root = self.make_repo(".github")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        provenance_path = root / install.PROVENANCE_FILE
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        fake = "sha256:" + "0" * 64
        payload["files"][".sd-ai-command-pack/installed-targets.txt"] = fake
        payload["files"][".sd-ai-command-pack/provenance.json"] = fake
        payload["files"][".gitignore"] = fake
        payload["files"][".github/copilot-instructions.md"] = fake
        provenance_path.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        rebuilt = json.loads(provenance_path.read_text(encoding="utf-8"))["files"]
        self.assertNotIn(".sd-ai-command-pack/installed-targets.txt", rebuilt)
        self.assertNotIn(".sd-ai-command-pack/provenance.json", rebuilt)
        self.assertNotIn(".gitignore", rebuilt)
        self.assertNotIn(".github/copilot-instructions.md", rebuilt)

    def test_install_audit_ignores_stale_never_vouched_entries(self) -> None:
        root = self.make_repo(".github")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        provenance_path = root / install.PROVENANCE_FILE
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        payload["files"][".gitignore"] = "sha256:" + "0" * 64
        provenance_path.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("installed target drifted", result.stdout)

    def test_installed_target_candidates_falls_back_when_receipts_are_unsafe(
        self,
    ) -> None:
        root = self.make_repo()
        file = self.valid_pack_file(
            source=PACK_ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            target=Path("scripts/sd-ai-command-pack-full-check.sh"),
        )

        with (
            mock.patch.object(
                install,
                "read_existing_installed_targets",
                side_effect=SystemExit("error: receipt resolves outside target repo"),
            ),
            mock.patch.object(
                install,
                "read_existing_provenance_files",
                side_effect=SystemExit("error: provenance resolves outside target repo"),
            ),
        ):
            candidates = install.installed_target_candidates(
                [file],
                root,
                platforms=None,
                install_all=False,
            )

        self.assertIn("scripts/sd-ai-command-pack-full-check.sh", candidates)
        self.assertIn(install.INSTALLED_TARGETS_FILE.as_posix(), candidates)
        self.assertIn(install.PROVENANCE_FILE.as_posix(), candidates)

    def test_install_audit_reports_unreadable_vouched_target(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root reads unreadable files")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        script.chmod(0o000)
        self.addCleanup(script.chmod, 0o644)

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "vouched target is unreadable: scripts/sd-ai-command-pack-full-check.sh",
            result.stdout,
        )

    def test_install_audit_flags_symlink_at_vouched_path(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        copy = root / "scripts/full-check-copy.sh"
        copy.write_bytes(script.read_bytes())
        script.unlink()
        script.symlink_to(copy.name)

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "vouched target is not a regular file: "
            "scripts/sd-ai-command-pack-full-check.sh",
            result.stdout,
        )

    def test_install_audit_flags_vouched_target_missing_from_receipt_too(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        # Remove a vouched file AND its receipt line: the structural audit
        # no longer sees it, so provenance must be the tamper-evidence.
        (root / "scripts/sd-ai-command-pack-full-check.sh").unlink()
        receipt = root / install.INSTALLED_TARGETS_FILE
        receipt.write_text(
            "".join(
                line
                for line in receipt.read_text(encoding="utf-8").splitlines(
                    keepends=True
                )
                if "sd-ai-command-pack-full-check.sh" not in line
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "vouched target is missing: scripts/sd-ai-command-pack-full-check.sh",
            result.stdout,
        )

    def test_install_audit_requires_regular_provenance_file(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        provenance = root / install.PROVENANCE_FILE
        aside = root / ".sd-ai-command-pack/provenance-real.json"
        aside.write_bytes(provenance.read_bytes())
        provenance.unlink()
        provenance.symlink_to(aside.name)

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("must be a regular file", result.stdout)

        provenance.unlink()
        provenance.symlink_to("does-not-exist.json")
        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("must be a regular file", result.stdout)

    def test_install_audit_flags_non_regular_file_at_vouched_path(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        script.unlink()
        script.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "vouched target is not a regular file: "
            "scripts/sd-ai-command-pack-full-check.sh",
            result.stdout,
        )

    def test_install_audit_flags_vouched_path_escaping_repo_root(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        outside = Path(tempfile.mkdtemp(prefix="sd-pack-outside-"))
        self.addCleanup(shutil.rmtree, outside, True)
        skill_dir = root / ".agents/skills/sd-continue"
        (outside / "sd-continue").mkdir()
        shutil.copy2(skill_dir / "SKILL.md", outside / "sd-continue/SKILL.md")
        shutil.rmtree(skill_dir)
        skill_dir.symlink_to(outside / "sd-continue", target_is_directory=True)

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "vouched target escapes the repository root: "
            ".agents/skills/sd-continue/SKILL.md",
            result.stdout,
        )

    def test_install_audit_reports_uninspectable_vouched_target(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root bypasses directory permissions")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        skill_dir = root / ".agents/skills/sd-continue"
        skill_dir.chmod(0o000)
        self.addCleanup(skill_dir.chmod, 0o755)

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "vouched target cannot be inspected: "
            ".agents/skills/sd-continue/SKILL.md",
            result.stdout,
        )
        self.assertIn(
            "installed target cannot be inspected: "
            ".agents/skills/sd-continue/SKILL.md",
            result.stdout,
        )

    def test_install_audit_fails_when_provenance_cannot_be_inspected(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root bypasses directory permissions")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        pack_dir = root / ".sd-ai-command-pack"
        pack_dir.chmod(0o000)
        self.addCleanup(pack_dir.chmod, 0o755)

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("cannot be read", result.stdout)
        self.assertIn("cannot be inspected", result.stdout)

    def test_install_conflicts_on_symlinked_provenance(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        provenance = root / install.PROVENANCE_FILE
        target_key = "scripts/sd-ai-command-pack-full-check.sh"

        bogus = root / ".sd-ai-command-pack/bogus.json"
        bogus.write_text(
            json.dumps({"files": {target_key: "sha256:" + "0" * 64}}) + "\n",
            encoding="utf-8",
        )
        provenance.unlink()
        provenance.symlink_to(bogus.name)

        result = self.run_install(root)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("symlink-conflict .sd-ai-command-pack/provenance.json", result.stdout)
        self.assertTrue(provenance.is_symlink())
        self.assertEqual(
            json.loads(bogus.read_text(encoding="utf-8"))["files"][target_key],
            "sha256:" + "0" * 64,
        )

    def test_install_recovers_from_malformed_provenance(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        provenance = root / install.PROVENANCE_FILE

        provenance.write_text("not json\n", encoding="utf-8")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        rebuilt = json.loads(provenance.read_text(encoding="utf-8"))
        self.assertIn("scripts/sd-ai-command-pack-full-check.sh", rebuilt["files"])

        provenance.write_text('{"files": "nope"}\n', encoding="utf-8")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        rebuilt = json.loads(provenance.read_text(encoding="utf-8"))
        self.assertIn("scripts/sd-ai-command-pack-full-check.sh", rebuilt["files"])

    def test_install_audit_warns_for_unlisted_gitignored_pack_files(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        # A local-only adapter deliberately kept out of the receipt (the
        # exclude-and-warn receipt policy).
        extra = root / ".claude/commands/sd/start.md"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("# local-only wrapper\n", encoding="utf-8")
        gitignore = root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + ".claude/\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "local-only pack-like file is not recorded in installed targets: "
            ".claude/commands/sd/start.md",
            result.stdout,
        )
        self.assertIn("install audit passed", result.stdout)

    def test_install_audit_fails_for_unlisted_tracked_pack_files(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        extra = root / ".claude/commands/sd/start.md"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("# unrecorded wrapper\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "pack-like file is not listed in installed targets: "
            ".claude/commands/sd/start.md",
            result.stdout,
        )

    def test_install_audit_normalizes_windows_separators_in_receipt(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        receipt = root / install.INSTALLED_TARGETS_FILE
        receipt.write_text(
            receipt.read_text(encoding="utf-8").replace(
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts\\sd-ai-command-pack-full-check.sh",
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("installed target is missing", result.stdout)

    def test_install_audit_rejects_windows_absolute_installed_targets(self) -> None:
        root = self.make_repo()
        snapshot = root / install.INSTALLED_TARGETS_FILE
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(
            "C:\\Users\\sven\\repo\\scripts\\sd-ai-command-pack-full-check.sh\n"
            "C:relative\\sd-ai-command-pack-full-check.sh\n"
            "\\rooted\\sd-ai-command-pack-full-check.sh\n"
            "\\\\server\\share\\sd-ai-command-pack-full-check.sh\n"
            "..\\outside\\sd-ai-command-pack-full-check.sh\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("contains unsafe target", result.stdout)
        self.assertIn("C:\\\\Users\\\\sven", result.stdout)
        self.assertIn("C:relative", result.stdout)
        self.assertIn("\\\\rooted", result.stdout)
        self.assertIn("\\\\\\\\server\\\\share", result.stdout)
        self.assertIn("..\\\\outside", result.stdout)

    def test_install_audit_warns_about_legacy_pack_names(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        legacy_skill = root / ".agents/skills/trellis-review-pr/SKILL.md"
        legacy_skill.parent.mkdir(parents=True, exist_ok=True)
        legacy_skill.write_text("# Legacy review skill\n", encoding="utf-8")
        (root / "README.md").write_text(
            "Run scripts/trellis-full-check.sh before review.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("legacy pack target remains", result.stdout)
        self.assertIn(".agents/skills/trellis-review-pr", result.stdout)
        self.assertIn("legacy pack reference remains", result.stdout)
        self.assertIn("scripts/trellis-full-check.sh", result.stdout)
        self.assertIn("install audit passed", result.stdout)

    def test_install_audit_prints_warnings_even_with_failures(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / ".agents/skills/sd-review-pr/SKILL.md").unlink()
        legacy = root / "docs/TRELLIS_REVIEW_PR_PACK.md"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("# stale guide\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("error: installed target is missing", result.stdout)
        self.assertIn("warning: legacy pack target remains", result.stdout)
        self.assertLess(
            result.stdout.index("warning: legacy pack target remains"),
            result.stdout.index("error: installed target is missing"),
            "advisory warnings must print before the failure block",
        )

    def test_install_audit_help_works_when_disabled(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
                "--help",
            ],
            env={**os.environ, "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("usage:", result.stdout)
        self.assertNotIn("skipping install audit", result.stdout)

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
                "--definitely-not-a-flag",
            ],
            env={**os.environ, "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_install_audit_reports_unreadable_targets_distinctly(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root bypasses permissions")
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        blocked_dir = root / ".agents/skills/sd-review-pr"
        blocked_dir.chmod(0o000)
        self.addCleanup(blocked_dir.chmod, 0o755)

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("installed target cannot be inspected", result.stdout)
        self.assertNotIn(
            "installed target is missing: .agents/skills/sd-review-pr/SKILL.md",
            result.stdout,
        )

    def test_install_reports_unreadable_receipt_cleanly(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root bypasses permissions")
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        receipt = root / str(install.INSTALLED_TARGETS_FILE)
        receipt.chmod(0o000)
        self.addCleanup(receipt.chmod, 0o644)

        result = self.run_install(root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("cannot read installed-targets receipt", result.stdout)

    def test_install_audit_warns_about_rename_era_legacy_paths(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        rename_era_paths = [
            "docs/TRELLIS_REVIEW_PR_PACK.md",
            ".opencode/commands/sd/start.md",
            "scripts/sd-command-pack-full-check.sh",
        ]
        for relative_path in rename_era_paths:
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# stale pre-rename artifact\n", encoding="utf-8")
        (root / "README.md").write_text(
            "Run scripts/sd-command-pack-full-check.sh before review.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        for relative_path in rename_era_paths:
            self.assertIn(relative_path, result.stdout)
        self.assertIn("legacy pack target remains", result.stdout)
        self.assertIn("legacy pack reference remains", result.stdout)
        self.assertIn("install audit passed", result.stdout)

    def test_install_audit_legacy_advisories_cover_all_pack_scripts(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_legacy_paths",
        )
        current_scripts = sorted(
            path.name
            for path in (install.ROOT / "templates/scripts").iterdir()
            if path.is_file() and path.name.startswith("sd-ai-command-pack-")
        )
        self.assertTrue(current_scripts)
        post_rename_scripts = {
            "sd-ai-command-pack-review-full-check.sh",
            "sd-ai-command-pack-status.py",
            "sd-ai-command-pack-toolchain.sh",
        }
        self.assertLessEqual(post_rename_scripts, set(current_scripts))
        for name in current_scripts:
            if name in post_rename_scripts:
                continue
            legacy = "scripts/" + name.replace(
                "sd-ai-command-pack-", "sd-command-pack-", 1
            )
            self.assertIn(
                legacy,
                module.LEGACY_PACK_PATHS,
                f"missing rename-era advisory for {name}",
            )

    def test_install_audit_legacy_reference_scan_uses_boundaries(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text(
            "The my-trellis-review-pr-project name is not a command.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("legacy pack reference remains", result.stdout)

    def test_install_audit_skips_generated_repomix_map_references(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        repomix_map = root / "docs/repomix-map.md"
        repomix_map.parent.mkdir(parents=True, exist_ok=True)
        repomix_map.write_text(
            "Generated copy mentioning trellis-review-pr and sd-refresh-specs.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("legacy pack reference remains", result.stdout)

    def test_install_audit_ignores_excluded_directories_below_scan_roots(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        cache_dir = root / "scripts/__pycache__"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "tool.pyc").write_text(
            "scripts/trellis-full-check.sh\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("legacy pack reference remains", result.stdout)

    def test_install_audit_skips_inside_pack_source_checkout(self) -> None:
        root = self.make_repo()
        # Recreate the markers unique to the pack's own source tree.
        (root / "install.py").write_text("# installer\n", encoding="utf-8")
        (root / "manifest.json").write_text("{}\n", encoding="utf-8")
        (root / "templates").mkdir()

        result = self.run_source_audit(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("skipping install audit", result.stdout)
        self.assertIn("source checkout", result.stdout)

    def test_install_audit_still_fails_for_missing_targets_in_consumer_repo(
        self,
    ) -> None:
        # No installer/manifest/templates markers -> a consumer repo. A missing
        # installed-targets snapshot must stay a hard failure (guard not loosened).
        root = self.make_repo()

        result = self.run_source_audit(root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("installed-targets.txt is missing", result.stdout)

    def test_install_audit_runs_in_source_checkout_once_installed(self) -> None:
        # Source markers present but an installed footprint exists -> the audit
        # must still run rather than skip (dogfood install case).
        root = self.make_repo()
        (root / "install.py").write_text("# installer\n", encoding="utf-8")
        (root / "manifest.json").write_text("{}\n", encoding="utf-8")
        (root / "templates").mkdir()
        snapshot = root / install.INSTALLED_TARGETS_FILE
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(
            "scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
        )

        result = self.run_source_audit(root)

        self.assertNotIn("skipping install audit", result.stdout)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "installed target is missing: "
            "scripts/sd-ai-command-pack-full-check.sh",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
