from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PACK_ROOT / "install.py"


def make_repo(*platform_dirs: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="trellis-review-pr-pack-test-"))
    (root / ".trellis").mkdir()
    (root / ".trellis" / "config.yaml").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.PIPE)
    for platform_dir in platform_dirs:
        (root / platform_dir).mkdir(parents=True, exist_ok=True)
    return root


def run_install(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALLER), str(root), *args, "--skip-diff-check"],
        cwd=PACK_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


class InstallTests(unittest.TestCase):
    def test_installs_shared_skill_and_existing_platform_adapters(self) -> None:
        root = make_repo(".gemini", ".github")

        result = run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/trellis-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".gemini/commands/trellis/review-pr.toml").is_file())
        self.assertTrue((root / ".github/prompts/review-pr.prompt.md").is_file())
        self.assertFalse((root / ".opencode/commands/trellis/review-pr.md").exists())

    def test_conflict_requires_force(self) -> None:
        root = make_repo(".gemini")
        target = root / ".agents/skills/trellis-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = run_install(root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("conflict", result.stdout)
        self.assertEqual(target.read_text(encoding="utf-8"), "local edit\n")

        forced = run_install(root, "--force")
        self.assertEqual(forced.returncode, 0, forced.stdout)
        self.assertIn("Trellis PR Review Loop", target.read_text(encoding="utf-8"))

    def test_dry_run_does_not_write_files(self) -> None:
        root = make_repo(".opencode")

        result = run_install(root, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertFalse((root / ".agents/skills/trellis-review-pr/SKILL.md").exists())
        self.assertFalse((root / ".opencode/commands/trellis/review-pr.md").exists())


if __name__ == "__main__":
    unittest.main()
