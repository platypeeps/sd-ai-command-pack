from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import install


PACK_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PACK_ROOT / "install.py"


class InstallTests(unittest.TestCase):
    def valid_pack_file(
        self,
        *,
        source: Path | None = None,
        target: Path = Path(".agents/skills/trellis-review-pr/SKILL.md"),
        anchor: Path | None = None,
    ) -> install.PackFile:
        if source is None:
            source = (
                install.ROOT
                / "templates/.agents/skills/trellis-review-pr/SKILL.md"
            )
        return install.PackFile(
            platform="shared",
            kind="skill",
            source=source,
            target=target,
            anchor=anchor,
            install="always",
        )

    def make_repo(self, *platform_dirs: str) -> Path:
        tempdir = tempfile.TemporaryDirectory(prefix="trellis-review-pr-pack-test-")
        self.addCleanup(tempdir.cleanup)

        root = Path(tempdir.name)
        (root / ".trellis").mkdir()
        (root / ".trellis" / "config.yaml").write_text("# test\n", encoding="utf-8")
        self.run_git(root, "init")
        for platform_dir in platform_dirs:
            (root / platform_dir).mkdir(parents=True, exist_ok=True)
        return root

    def run_git(self, root: Path, *args: str) -> None:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def run_install(
        self,
        root: Path,
        *args: str,
        skip_diff_check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(INSTALLER), str(root), *args]
        if skip_diff_check:
            command.append("--skip-diff-check")
        return subprocess.run(
            command,
            cwd=PACK_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_installs_shared_skill_and_existing_platform_adapters(self) -> None:
        root = self.make_repo(".gemini", ".github")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/trellis-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".gemini/commands/trellis/review-pr.toml").is_file())
        self.assertTrue((root / ".github/prompts/review-pr.prompt.md").is_file())
        self.assertFalse((root / ".opencode/commands/trellis/review-pr.md").exists())

    def test_platform_filter_still_installs_shared_skill(self) -> None:
        root = self.make_repo(".gemini", ".github", ".opencode")

        result = self.run_install(root, "--platform", "gemini")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/trellis-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".gemini/commands/trellis/review-pr.toml").is_file())
        self.assertFalse((root / ".github/prompts/review-pr.prompt.md").exists())
        self.assertFalse((root / ".opencode/commands/trellis/review-pr.md").exists())

    def test_all_installs_every_adapter_without_anchors(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--all")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/trellis-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".gemini/commands/trellis/review-pr.toml").is_file())
        self.assertTrue((root / ".github/prompts/review-pr.prompt.md").is_file())
        self.assertTrue((root / ".opencode/commands/trellis/review-pr.md").is_file())

    def test_installed_adapters_can_resolve_shared_skill(self) -> None:
        root = self.make_repo(".gemini", ".github", ".opencode")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        shared_skill = root / ".agents/skills/trellis-review-pr/SKILL.md"
        self.assertTrue(shared_skill.is_file())
        for adapter in [
            root / ".gemini/commands/trellis/review-pr.toml",
            root / ".github/prompts/review-pr.prompt.md",
            root / ".opencode/commands/trellis/review-pr.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                ".agents/skills/trellis-review-pr/SKILL.md",
                adapter.read_text(encoding="utf-8"),
            )

    def test_conflict_requires_force(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/trellis-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = self.run_install(root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("conflict", result.stdout)
        self.assertEqual(target.read_text(encoding="utf-8"), "local edit\n")

        forced = self.run_install(root, "--force")
        self.assertEqual(forced.returncode, 0, forced.stdout)
        self.assertIn("Trellis PR Review Loop", target.read_text(encoding="utf-8"))

    def test_force_backup_preserves_overwritten_file(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/trellis-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = self.run_install(root, "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("backup", result.stdout)
        self.assertEqual(
            (root / ".agents/skills/trellis-review-pr/SKILL.md.bak").read_text(
                encoding="utf-8"
            ),
            "local edit\n",
        )
        self.assertIn("Trellis PR Review Loop", target.read_text(encoding="utf-8"))

    def test_dry_run_force_backup_does_not_report_or_write_backup(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/trellis-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = self.run_install(root, "--dry-run", "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("overwritten", result.stdout)
        self.assertNotIn("backup", result.stdout)
        self.assertFalse(
            (root / ".agents/skills/trellis-review-pr/SKILL.md.bak").exists()
        )
        self.assertEqual(target.read_text(encoding="utf-8"), "local edit\n")

    def test_force_backup_does_not_write_through_existing_backup_symlink(self) -> None:
        root = self.make_repo(".gemini")
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="trellis-review-pr-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_backup = Path(outside_tempdir.name) / "outside-backup"
        target = root / ".agents/skills/trellis-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")
        target.with_name("SKILL.md.bak").symlink_to(outside_backup)

        result = self.run_install(root, "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("SKILL.md.bak1", result.stdout)
        self.assertEqual(
            target.with_name("SKILL.md.bak1").read_text(encoding="utf-8"),
            "local edit\n",
        )
        self.assertFalse(outside_backup.exists())

    def test_backup_requires_force(self) -> None:
        root = self.make_repo(".gemini")

        result = self.run_install(root, "--backup")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--backup requires --force", result.stdout)

    def test_dry_run_does_not_write_files(self) -> None:
        root = self.make_repo(".opencode")

        result = self.run_install(root, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertFalse((root / ".agents/skills/trellis-review-pr/SKILL.md").exists())
        self.assertFalse((root / ".opencode/commands/trellis/review-pr.md").exists())

    def test_rejects_non_trellis_repo(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="trellis-review-pr-pack-test-")
        self.addCleanup(tempdir.cleanup)

        result = self.run_install(Path(tempdir.name))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".trellis/config.yaml not found", result.stdout)

    def test_rejects_target_path_resolved_outside_repo(self) -> None:
        root = self.make_repo()
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="trellis-review-pr-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside = Path(outside_tempdir.name)
        (root / ".agents").symlink_to(outside, target_is_directory=True)

        result = self.run_install(root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target path resolves outside target repo", result.stdout)
        self.assertFalse((outside / "skills/trellis-review-pr/SKILL.md").exists())

    def test_rejects_existing_target_symlink_resolved_outside_repo(self) -> None:
        root = self.make_repo(".gemini")
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="trellis-review-pr-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_target = Path(outside_tempdir.name) / "outside-target"
        target = root / ".agents/skills/trellis-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.symlink_to(outside_target)

        result = self.run_install(root, "--force")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target path resolves outside target repo", result.stdout)
        self.assertFalse(outside_target.exists())

    def test_diff_check_is_limited_to_installed_paths(self) -> None:
        root = self.make_repo(".gemini")
        unrelated = root / "unrelated.txt"
        unrelated.write_text("clean\n", encoding="utf-8")
        self.run_git(root, "add", "unrelated.txt")
        unrelated.write_text("bad   \n", encoding="utf-8")

        result = self.run_install(root, skip_diff_check=False)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/trellis-review-pr/SKILL.md").is_file())

    def test_scoped_diff_check_reports_selected_path_failures(self) -> None:
        root = self.make_repo()
        bad = root / "bad.txt"
        bad.write_text("clean\n", encoding="utf-8")
        self.run_git(root, "add", "bad.txt")
        bad.write_text("bad   \n", encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            bad_result = install.run_diff_check(root, [Path("bad.txt")])
            missing_result = install.run_diff_check(root, [Path("missing.txt")])

        self.assertNotEqual(bad_result, 0)
        self.assertEqual(missing_result, 0)

    def test_empty_scoped_diff_check_does_not_run_repo_wide(self) -> None:
        root = self.make_repo()
        bad = root / "bad.txt"
        bad.write_text("clean\n", encoding="utf-8")
        self.run_git(root, "add", "bad.txt")
        bad.write_text("bad   \n", encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = install.run_diff_check(root, [])

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "")

    def test_manifest_sources_exist_and_targets_are_unique(self) -> None:
        _, files = install.load_manifest()

        install.validate_manifest(files)
        self.assertEqual(len({file.target for file in files}), len(files))
        for file in files:
            self.assertTrue(file.source.is_file(), file.source)

    def test_manifest_rejects_unsafe_target_paths(self) -> None:
        for target in [Path("/tmp/pwn"), Path("../outside"), Path(".agents/../x")]:
            with self.subTest(target=target):
                with self.assertRaisesRegex(SystemExit, "unsafe target path"):
                    install.validate_manifest([self.valid_pack_file(target=target)])

    def test_manifest_rejects_unsafe_anchor_paths(self) -> None:
        for anchor in [Path("/tmp"), Path("../.github"), Path(".github/../x")]:
            with self.subTest(anchor=anchor):
                with self.assertRaisesRegex(SystemExit, "unsafe anchor path"):
                    install.validate_manifest([self.valid_pack_file(anchor=anchor)])

    def test_manifest_rejects_unsafe_source_paths(self) -> None:
        for source in [Path("/tmp/pwn"), install.ROOT / ".." / "outside"]:
            with self.subTest(source=source):
                with self.assertRaisesRegex(SystemExit, "unsafe source path"):
                    install.validate_manifest([self.valid_pack_file(source=source)])

    def test_adapters_reference_installed_shared_skill(self) -> None:
        _, files = install.load_manifest()
        adapter_files = [file for file in files if file.kind in {"command", "prompt"}]

        self.assertGreater(len(adapter_files), 0)
        for file in adapter_files:
            content = file.source.read_text(encoding="utf-8")
            self.assertIn(".agents/skills/trellis-review-pr/SKILL.md", content)

    def test_manifest_sources_do_not_have_trailing_whitespace(self) -> None:
        _, files = install.load_manifest()

        for file in files:
            for line_number, line in enumerate(
                file.source.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                self.assertFalse(
                    line.endswith((" ", "\t")),
                    f"{file.source}:{line_number} has trailing whitespace",
                )


if __name__ == "__main__":
    unittest.main()
