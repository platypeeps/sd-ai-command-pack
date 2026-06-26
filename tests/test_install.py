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

    def test_manifest_sources_exist_and_targets_are_unique(self) -> None:
        _, files = install.load_manifest()

        install.validate_manifest(files)
        self.assertEqual(len({file.target for file in files}), len(files))
        for file in files:
            self.assertTrue(file.source.is_file(), file.source)

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
