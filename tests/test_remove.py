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


class RemoveTests(InstallTestCase):
    """Tests for pack removal behavior and cleanup safeguards."""

    def test_remove_passes_clean_diff_check(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        result = self.run_install(root, "--remove", skip_diff_check=False)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_remove_deletes_pack_files_and_managed_blocks(self) -> None:
        root = self.make_repo(".github")
        copilot_instructions = root / ".github/copilot-instructions.md"
        copilot_instructions.write_text(
            "Keep this repo-specific instruction.\n",
            encoding="utf-8",
        )

        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / ".prism/rules.schema.json").is_file())
        self.assertTrue((root / ".gito/config.toml").is_file())
        self.assertTrue((root / ".gito/sd-ai-command-pack.env").is_file())
        self.assertTrue((root / install.INSTALLED_TARGETS_FILE).is_file())
        self.assertTrue((root / install.PROVENANCE_FILE).is_file())
        self.assertIn(
            install.COPILOT_GUIDANCE_START,
            copilot_instructions.read_text(encoding="utf-8"),
        )

        result = self.run_install(root, "--remove")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: remove", result.stdout)
        self.assertIn("removed", result.stdout)
        self.assertFalse((root / "scripts/sd-ai-command-pack-full-check.sh").exists())
        self.assertFalse((root / ".prism/rules.json").exists())
        self.assertFalse((root / ".prism/rules.schema.json").exists())
        self.assertFalse((root / ".gito/config.toml").exists())
        self.assertFalse((root / ".gito/sd-ai-command-pack.env").exists())
        self.assertFalse((root / install.INSTALLED_TARGETS_FILE).exists())
        self.assertFalse((root / install.PROVENANCE_FILE).exists())
        self.assertFalse((root / ".gitignore").exists())
        copilot_text = copilot_instructions.read_text(encoding="utf-8")
        self.assertIn("Keep this repo-specific instruction.", copilot_text)
        self.assertNotIn(install.COPILOT_GUIDANCE_START, copilot_text)
        self.assertNotIn(install.COPILOT_GUIDANCE_END, copilot_text)

    def test_remove_dry_run_does_not_delete_pack_files(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = self.run_install(root, "--remove", "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: remove", result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertIn("would-remove", result.stdout)
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / install.INSTALLED_TARGETS_FILE).is_file())
        self.assertTrue((root / install.PROVENANCE_FILE).is_file())
        self.assertTrue((root / ".gitignore").is_file())

    def test_remove_preserves_drifted_files_unless_forced(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        script.write_text(
            script.read_text(encoding="utf-8") + "\n# local drift\n",
            encoding="utf-8",
        )

        result = self.run_install(root, "--remove")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("preserved", result.stdout)
        self.assertIn("content differs from installed pack version", result.stdout)
        self.assertTrue(script.is_file())

        result = self.run_install(root, "--remove", "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("backup", result.stdout)
        self.assertFalse(script.exists())
        backup = root / "scripts/sd-ai-command-pack-full-check.sh.bak"
        self.assertTrue(backup.is_file())
        self.assertIn("# local drift", backup.read_text(encoding="utf-8"))

    def test_remove_ignores_tampered_receipts_for_git_and_non_pack_files(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        user_file = root / "USER_DATA.txt"
        user_file.write_text("keep this user file\n", encoding="utf-8")
        self.run_git(root, "add", "USER_DATA.txt")
        git_config = root / ".git/config"

        provenance_path = root / install.PROVENANCE_FILE
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        provenance["files"][".git/config"] = (
            "sha256:" + hashlib.sha256(git_config.read_bytes()).hexdigest()
        )
        provenance["files"]["USER_DATA.txt"] = (
            "sha256:" + hashlib.sha256(user_file.read_bytes()).hexdigest()
        )
        provenance_path.write_text(
            json.dumps(provenance, indent=2) + "\n",
            encoding="utf-8",
        )

        receipt = root / install.INSTALLED_TARGETS_FILE
        receipt.write_text(
            receipt.read_text(encoding="utf-8")
            + ".git/config\n"
            + "./USER_DATA.txt\n",
            encoding="utf-8",
        )

        result = self.run_install(root, "--remove", "--force", "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "ignored        .git/config (refusing to remove .git internals)",
            result.stdout,
        )
        self.assertIn(
            "ignored        USER_DATA.txt (not a recognized sd-ai-command-pack target)",
            result.stdout,
        )
        self.assertTrue(git_config.is_file())
        self.assertTrue(user_file.is_file())

        result = self.run_install(root, "--remove", "--force")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "ignored        .git/config (refusing to remove .git internals)",
            result.stdout,
        )
        self.assertIn(
            "ignored        USER_DATA.txt (not a recognized sd-ai-command-pack target)",
            result.stdout,
        )
        self.assertTrue(git_config.is_file())
        self.assertEqual(
            user_file.read_text(encoding="utf-8"),
            "keep this user file\n",
        )

    def test_remove_pack_file_reports_backup_copy_failures_cleanly(self) -> None:
        root = self.make_repo()
        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        script.parent.mkdir()
        script.write_text("local drift\n", encoding="utf-8")

        with mock.patch.object(
            install.shutil,
            "copyfile",
            side_effect=OSError("blocked backup"),
        ):
            with self.assertRaisesRegex(
                SystemExit,
                "cannot create backup.*blocked backup",
            ):
                install.remove_pack_file(
                    root,
                    Path("scripts/sd-ai-command-pack-full-check.sh"),
                    file=None,
                    recorded_hash=None,
                    force=True,
                    dry_run=False,
                    backup=True,
                )

        self.assertTrue(script.is_file())
        self.assertEqual(script.read_text(encoding="utf-8"), "local drift\n")
        self.assertFalse(
            script.with_name("sd-ai-command-pack-full-check.sh.bak").exists()
        )

    def test_remove_installed_pack_preserves_unsafe_receipt_state(
        self,
    ) -> None:
        root = self.make_repo()
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        (root / ".sd-ai-command-pack").symlink_to(
            Path(outside_tempdir.name),
            target_is_directory=True,
        )
        file = self.valid_pack_file(
            source=PACK_ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            target=Path("scripts/sd-ai-command-pack-full-check.sh"),
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = install.remove_installed_pack(
                {"name": "pack", "version": "1.0.0"},
                [file],
                root,
                platforms=None,
                install_all=False,
                force=False,
                dry_run=False,
                backup=False,
                skip_diff_check=True,
            )

        self.assertEqual(status, 0)
        self.assertIn("preserved", output.getvalue())
        self.assertIn(
            "target path parent resolves outside target repo",
            output.getvalue(),
        )
        self.assertTrue((root / ".sd-ai-command-pack").is_symlink())

    def test_remove_cleans_local_only_marker_and_exclude_block(self) -> None:
        root = self.make_git_repo_without_trellis()
        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        bin_dir = Path(tools_tempdir.name) / "bin"
        trellis_log = Path(tools_tempdir.name) / "trellis-args.log"
        self.write_trellis_stub(bin_dir, trellis_log)

        result = self.run_install(
            root,
            "--local-only",
            "--platform",
            "cursor",
            extra_env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        exclude = Path(
            self.git_output(root, "rev-parse", "--git-path", "info/exclude")
        )
        if not exclude.is_absolute():
            exclude = root / exclude
        self.assertIn(
            install.LOCAL_ONLY_EXCLUDE_START,
            exclude.read_text(encoding="utf-8"),
        )
        self.assertTrue((root / install.LOCAL_ONLY_MARKER_FILE).is_file())

        result = self.run_install(root, "--remove")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: remove", result.stdout)
        self.assertFalse((root / install.LOCAL_ONLY_MARKER_FILE).exists())
        self.assertNotIn(
            install.LOCAL_ONLY_EXCLUDE_START,
            exclude.read_text(encoding="utf-8"),
        )

    def test_remove_text_block_file_preserves_non_regular_and_unchanged_targets(
        self,
    ) -> None:
        root = self.make_repo()
        directory_target = root / ".github/copilot-instructions.md"
        directory_target.mkdir(parents=True)

        result = install.remove_text_block_file(
            root,
            Path(".github/copilot-instructions.md"),
            start_marker=install.COPILOT_GUIDANCE_START,
            end_marker=install.COPILOT_GUIDANCE_END,
            label=".github/copilot-instructions.md",
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(result.detail, "target is not a regular file")

        shutil.rmtree(directory_target)
        directory_target.parent.mkdir(parents=True, exist_ok=True)
        directory_target.write_text("repo-only guidance\n", encoding="utf-8")

        result = install.remove_text_block_file(
            root,
            Path(".github/copilot-instructions.md"),
            start_marker=install.COPILOT_GUIDANCE_START,
            end_marker=install.COPILOT_GUIDANCE_END,
            label=".github/copilot-instructions.md",
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "unchanged")
        self.assertEqual(result.detail, "managed block not present")
        self.assertEqual(
            directory_target.read_text(encoding="utf-8"),
            "repo-only guidance\n",
        )

    def test_remove_text_block_file_preserves_final_symlink_outside_repo(
        self,
    ) -> None:
        root = self.make_repo()
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_target = Path(outside_tempdir.name) / "copilot-instructions.md"
        outside_target.write_text("outside\n", encoding="utf-8")
        destination = root / ".github/copilot-instructions.md"
        destination.parent.mkdir(parents=True)
        destination.symlink_to(outside_target)

        result = install.remove_text_block_file(
            root,
            Path(".github/copilot-instructions.md"),
            start_marker=install.COPILOT_GUIDANCE_START,
            end_marker=install.COPILOT_GUIDANCE_END,
            label=".github/copilot-instructions.md",
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(result.detail, "target is not a regular file")
        self.assertTrue(destination.is_symlink())
        self.assertEqual(outside_target.read_text(encoding="utf-8"), "outside\n")

    def test_remove_text_block_file_handles_invalid_utf8_read_failures(
        self,
    ) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        gitignore.write_text(
            f"{install.TRELLIS_GITIGNORE_START}\n"
            ".trellis/.runtime/\n"
            f"{install.TRELLIS_GITIGNORE_END}\n",
            encoding="utf-8",
        )
        original_read_bytes = Path.read_bytes

        def block_target(path: Path) -> bytes:
            if path == gitignore:
                raise OSError("blocked target")
            return original_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=block_target):
            result = install.remove_text_block_file(
                root,
                install.TRELLIS_GITIGNORE_TARGET,
                start_marker=install.TRELLIS_GITIGNORE_START,
                end_marker=install.TRELLIS_GITIGNORE_END,
                label=".gitignore",
                dry_run=False,
                backup=False,
                preserve_invalid_utf8=True,
            )

        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn("target cannot be read", result.detail)
        self.assertIn(
            install.TRELLIS_GITIGNORE_START,
            gitignore.read_text(encoding="utf-8"),
        )

        gitignore.write_text(
            f"{install.TRELLIS_GITIGNORE_START}\n"
            ".trellis/.runtime/\n",
            encoding="utf-8",
        )

        result = install.remove_text_block_file(
            root,
            install.TRELLIS_GITIGNORE_TARGET,
            start_marker=install.TRELLIS_GITIGNORE_START,
            end_marker=install.TRELLIS_GITIGNORE_END,
            label=".gitignore",
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn("incomplete sd-ai-command-pack markers", result.detail)
        self.assertIn(
            install.TRELLIS_GITIGNORE_START,
            gitignore.read_text(encoding="utf-8"),
        )

    def test_remove_text_block_file_preserves_unsafe_paths_and_read_failures(
        self,
    ) -> None:
        root = self.make_repo()

        result = install.remove_text_block_file(
            root,
            Path("../.gitignore"),
            start_marker=install.TRELLIS_GITIGNORE_START,
            end_marker=install.TRELLIS_GITIGNORE_END,
            label=".gitignore",
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn("unsafe target path", result.detail)

        gitignore = root / ".gitignore"
        gitignore.write_text(
            f"{install.TRELLIS_GITIGNORE_START}\n"
            ".trellis/.runtime/\n"
            f"{install.TRELLIS_GITIGNORE_END}\n",
            encoding="utf-8",
        )
        original_read_text = Path.read_text

        def block_target(path: Path, *args: object, **kwargs: object) -> str:
            if path == gitignore:
                raise OSError("blocked target")
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(
            Path,
            "read_text",
            autospec=True,
            side_effect=block_target,
        ):
            result = install.remove_text_block_file(
                root,
                install.TRELLIS_GITIGNORE_TARGET,
                start_marker=install.TRELLIS_GITIGNORE_START,
                end_marker=install.TRELLIS_GITIGNORE_END,
                label=".gitignore",
                dry_run=False,
                backup=False,
            )

        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn("cannot read .gitignore", result.detail)
        self.assertIn(
            install.TRELLIS_GITIGNORE_START,
            gitignore.read_text(encoding="utf-8"),
        )

    def test_remove_text_block_file_updates_text_around_managed_block(self) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        gitignore.write_text(
            "dist/\n\n"
            f"{install.TRELLIS_GITIGNORE_START}\n"
            ".trellis/.runtime/\n"
            f"{install.TRELLIS_GITIGNORE_END}\n"
            "build/\n",
            encoding="utf-8",
        )

        result = install.remove_text_block_file(
            root,
            install.TRELLIS_GITIGNORE_TARGET,
            start_marker=install.TRELLIS_GITIGNORE_START,
            end_marker=install.TRELLIS_GITIGNORE_END,
            label=".gitignore",
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "updated")
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "dist/\n\nbuild/\n")

    def test_remove_text_block_file_reports_delete_failures_cleanly(self) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        gitignore.write_text(
            f"{install.TRELLIS_GITIGNORE_START}\n"
            ".trellis/.runtime/\n"
            f"{install.TRELLIS_GITIGNORE_END}\n",
            encoding="utf-8",
        )

        with mock.patch.object(Path, "unlink", side_effect=OSError("blocked delete")):
            with self.assertRaisesRegex(
                SystemExit,
                r"cannot remove \.gitignore.*blocked delete",
            ):
                install.remove_text_block_file(
                    root,
                    install.TRELLIS_GITIGNORE_TARGET,
                    start_marker=install.TRELLIS_GITIGNORE_START,
                    end_marker=install.TRELLIS_GITIGNORE_END,
                    label=".gitignore",
                    dry_run=False,
                    backup=False,
                )

        self.assertTrue(gitignore.is_file())
        self.assertIn(
            install.TRELLIS_GITIGNORE_START,
            gitignore.read_text(encoding="utf-8"),
        )

    def test_remove_pack_file_preserves_unsafe_target_nodes(self) -> None:
        root = self.make_repo()
        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        script.parent.mkdir()
        script.write_text("local\n", encoding="utf-8")
        script.unlink()
        script.symlink_to("elsewhere.sh")

        result = install.remove_pack_file(
            root,
            Path("scripts/sd-ai-command-pack-full-check.sh"),
            file=None,
            recorded_hash=None,
            force=False,
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(result.detail, "target is a symlink")
        self.assertTrue(script.is_symlink())

        script.unlink()
        script.mkdir()
        result = install.remove_pack_file(
            root,
            Path("scripts/sd-ai-command-pack-full-check.sh"),
            file=None,
            recorded_hash=None,
            force=True,
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(result.detail, "target is not a regular file")
        self.assertTrue(script.is_dir())

    def test_remove_pack_file_preserves_unsafe_candidate_paths(self) -> None:
        root = self.make_repo()

        result = install.remove_pack_file(
            root,
            Path("../outside.sh"),
            file=None,
            recorded_hash=None,
            force=True,
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn("unsafe target path", result.detail)

        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        (root / "scripts").symlink_to(
            Path(outside_tempdir.name),
            target_is_directory=True,
        )
        result = install.remove_pack_file(
            root,
            Path("scripts/sd-ai-command-pack-full-check.sh"),
            file=None,
            recorded_hash=None,
            force=True,
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn(
            "target path parent resolves outside target repo",
            result.detail,
        )
        self.assertTrue((root / "scripts").is_symlink())

    def test_remove_pack_file_handles_final_symlink_outside_repo(self) -> None:
        root = self.make_repo()
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_target = Path(outside_tempdir.name) / "full-check.sh"
        outside_target.write_text("outside\n", encoding="utf-8")
        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        script.parent.mkdir()
        script.symlink_to(outside_target)

        result = install.remove_pack_file(
            root,
            Path("scripts/sd-ai-command-pack-full-check.sh"),
            file=None,
            recorded_hash=None,
            force=False,
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(result.detail, "target is a symlink")
        self.assertTrue(script.is_symlink())
        self.assertEqual(outside_target.read_text(encoding="utf-8"), "outside\n")

        result = install.remove_pack_file(
            root,
            Path("scripts/sd-ai-command-pack-full-check.sh"),
            file=None,
            recorded_hash=None,
            force=True,
            dry_run=False,
            backup=False,
        )

        self.assertEqual(result.status, "removed")
        self.assertFalse(script.exists())
        self.assertFalse(script.is_symlink())
        self.assertEqual(outside_target.read_text(encoding="utf-8"), "outside\n")

    def test_remove_pack_file_reports_delete_failures_cleanly(self) -> None:
        root = self.make_repo()
        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        script.parent.mkdir()
        script.write_text("installed\n", encoding="utf-8")

        with mock.patch.object(Path, "unlink", side_effect=OSError("blocked delete")):
            with self.assertRaisesRegex(
                SystemExit,
                r"cannot remove scripts/sd-ai-command-pack-full-check\.sh.*blocked delete",
            ):
                install.remove_pack_file(
                    root,
                    Path("scripts/sd-ai-command-pack-full-check.sh"),
                    file=None,
                    recorded_hash=None,
                    force=True,
                    dry_run=False,
                    backup=False,
                )

        self.assertTrue(script.is_file())
        self.assertEqual(script.read_text(encoding="utf-8"), "installed\n")

    def test_may_remove_pack_file_handles_read_failures_cleanly(self) -> None:
        root = self.make_repo()
        destination = root / "scripts/sd-ai-command-pack-full-check.sh"
        destination.parent.mkdir()
        destination.write_text("local\n", encoding="utf-8")
        file = self.valid_pack_file(
            source=PACK_ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            target=Path("scripts/sd-ai-command-pack-full-check.sh"),
        )
        original_read_bytes = Path.read_bytes

        def block_target(path: Path) -> bytes:
            if path == destination:
                raise OSError("blocked target")
            return original_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=block_target):
            removable, detail = install.may_remove_pack_file(
                destination,
                file=None,
                recorded_hash="sha256:" + "0" * 64,
                force=False,
            )

        self.assertFalse(removable)
        self.assertIsNotNone(detail)
        self.assertIn("target cannot be read", detail)

        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=block_target):
            removable, detail = install.may_remove_pack_file(
                destination,
                file=file,
                recorded_hash=None,
                force=False,
            )

        self.assertFalse(removable)
        self.assertIsNotNone(detail)
        self.assertIn("target cannot be read", detail)

        def block_source(path: Path) -> bytes:
            if path == file.source:
                raise OSError("blocked source")
            return original_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=block_source):
            with self.assertRaisesRegex(SystemExit, "pack template cannot be read"):
                install.may_remove_pack_file(
                    destination,
                    file=file,
                    recorded_hash=None,
                    force=False,
                )

    def test_remove_local_only_exclude_handles_missing_and_dry_run(self) -> None:
        root = self.make_repo()
        with mock.patch.object(
            install.localonly,
            "git_info_exclude_path",
            side_effect=SystemExit("no git metadata"),
        ):
            self.assertIsNone(install.remove_local_only_exclude(root, dry_run=False))

        exclude = root / ".git/info/exclude"
        exclude.write_text(
            "manual\n\n"
            f"{install.LOCAL_ONLY_EXCLUDE_START}\n"
            ".sd-ai-command-pack/\n"
            f"{install.LOCAL_ONLY_EXCLUDE_END}\n",
            encoding="utf-8",
        )

        result = install.remove_local_only_exclude(root, dry_run=True)

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "would-update")
        self.assertIn(
            install.LOCAL_ONLY_EXCLUDE_START,
            exclude.read_text(encoding="utf-8"),
        )

        with mock.patch.object(
            install.localonly,
            "validate_resolved_target_path",
            side_effect=SystemExit("error: git exclude path resolves outside target repo"),
        ):
            result = install.remove_local_only_exclude(root, dry_run=False)

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn("git exclude path resolves outside target repo", result.detail)
        self.assertIn(
            install.LOCAL_ONLY_EXCLUDE_START,
            exclude.read_text(encoding="utf-8"),
        )

        with mock.patch.object(Path, "read_text", side_effect=OSError("blocked")):
            result = install.remove_local_only_exclude(root, dry_run=False)

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn("cannot read .git/info/exclude", result.detail)

        exclude.write_bytes(b"not utf-8: \xff\n")
        result = install.remove_local_only_exclude(root, dry_run=False)

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn(".git/info/exclude is not valid UTF-8", result.detail)

        exclude.write_text(
            f"{install.LOCAL_ONLY_EXCLUDE_START}\n"
            ".sd-ai-command-pack/\n",
            encoding="utf-8",
        )

        result = install.remove_local_only_exclude(root, dry_run=False)

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "preserved")
        self.assertIsNotNone(result.detail)
        self.assertIn("incomplete sd-ai-command-pack markers", result.detail)
        self.assertIn(
            install.LOCAL_ONLY_EXCLUDE_START,
            exclude.read_text(encoding="utf-8"),
        )

    def test_remove_runs_diff_check_and_returns_failure(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        with mock.patch.object(install.removal, "run_diff_check", return_value=7):
            status = install.remove_installed_pack(
                {"name": "pack", "version": "1.0.0"},
                self._manifest_files,
                root,
                platforms=None,
                install_all=False,
                force=False,
                dry_run=False,
                backup=False,
                skip_diff_check=False,
            )

        self.assertEqual(status, 7)


if __name__ == "__main__":
    unittest.main()
