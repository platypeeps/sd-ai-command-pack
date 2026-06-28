from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
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

    def git_output(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout.strip()

    def make_housekeeping_repo(self) -> tuple[Path, Path, Path, str]:
        tempdir = tempfile.TemporaryDirectory(prefix="trellis-housekeeping-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        repo = root / "work"
        remote = root / "origin.git"
        stub_bin = root / "bin"
        repo.mkdir()
        remote.mkdir()
        stub_bin.mkdir()

        self.run_git(remote, "init", "--bare")
        self.run_git(repo, "init", "-b", "main")
        self.run_git(repo, "config", "user.email", "test@example.com")
        self.run_git(repo, "config", "user.name", "Test User")
        (repo / ".trellis/scripts").mkdir(parents=True)
        (repo / ".trellis/config.yaml").write_text("# test\n", encoding="utf-8")
        (repo / ".trellis/scripts/get_context.py").write_text(
            "print('(no active tasks assigned to you)')\n",
            encoding="utf-8",
        )
        (repo / "README.md").write_text("# Test\n", encoding="utf-8")
        self.run_git(repo, "add", ".")
        self.run_git(repo, "commit", "-m", "initial")
        self.run_git(repo, "remote", "add", "origin", str(remote))
        self.run_git(repo, "push", "-u", "origin", "main")
        self.run_git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.run_git(repo, "fetch", "origin")
        self.run_git(repo, "remote", "set-head", "origin", "-a")
        self.run_git(repo, "switch", "-c", "feature/cleanup")
        (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
        self.run_git(repo, "add", "feature.txt")
        self.run_git(repo, "commit", "-m", "feature")
        self.run_git(repo, "push", "-u", "origin", "feature/cleanup")
        head_oid = self.git_output(repo, "rev-parse", "HEAD")
        return repo, remote, stub_bin, head_oid

    def write_housekeeping_gh_stub(self, stub_bin: Path, head_oid: str) -> None:
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            f"  printf '6\\tMERGED\\t2026-06-27T17:00:00Z\\thttps://example.test/pr/6\\tfeature/cleanup\\t{head_oid}\\n'\n"
            "elif [ \"${1:-}\" = pr ] && [ \"${2:-}\" = list ]; then\n"
            "  exit 0\n"
            "elif [ \"${1:-}\" = issue ] && [ \"${2:-}\" = list ]; then\n"
            "  exit 0\n"
            "elif [ \"${1:-}\" = repo ] && [ \"${2:-}\" = view ]; then\n"
            "  printf 'main\\n'\n"
            "else\n"
            "  printf 'unexpected gh invocation: %s\\n' \"$*\" >&2\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)

    def write_auto_finalize_gh_stub(
        self,
        stub_bin: Path,
        marker: Path,
        graphql_body: str = "  printf '0\\tfalse\\t\\n'\n",
    ) -> None:
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "branch='feature/cleanup'\n"
            f"marker={str(marker)!r}\n"
            "head_oid() { git rev-parse \"refs/heads/$branch\"; }\n"
            "pr_state() { if [ -f \"$marker\" ]; then printf 'MERGED'; else printf 'OPEN'; fi; }\n"
            "if [ \"${1:-}\" = repo ] && [ \"${2:-}\" = view ]; then\n"
            "  printf 'main\\n'\n"
            "elif [ \"${1:-}\" = api ] && [ \"${2:-}\" = graphql ]; then\n"
            f"{graphql_body}"
            "elif [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            "  state=\"$(pr_state)\"\n"
            "  head=\"$(head_oid)\"\n"
            "  args=\" $* \"\n"
            "  if [[ \"$args\" == *isDraft* ]]; then\n"
            "    printf '6\\t%s\\tfalse\\thttps://example.test/pr/6\\tfeature/cleanup\\t%s\\tmain\\tCLEAN\\t0\\t2\\n' \"$state\" \"$head\"\n"
            "  else\n"
            "    merged_at=''\n"
            "    if [ \"$state\" = MERGED ]; then merged_at='2026-06-27T18:00:00Z'; fi\n"
            "    printf '6\\t%s\\t%s\\thttps://example.test/pr/6\\tfeature/cleanup\\t%s\\n' \"$state\" \"$merged_at\" \"$head\"\n"
            "  fi\n"
            "elif [ \"${1:-}\" = pr ] && [ \"${2:-}\" = merge ]; then\n"
            "  remote=\"$(git remote get-url origin)\"\n"
            "  head=\"$(git rev-parse HEAD)\"\n"
            "  git --git-dir=\"$remote\" update-ref refs/heads/main \"$head\"\n"
            "  touch \"$marker\"\n"
            "elif [ \"${1:-}\" = pr ] && [ \"${2:-}\" = list ]; then\n"
            "  exit 0\n"
            "elif [ \"${1:-}\" = issue ] && [ \"${2:-}\" = list ]; then\n"
            "  exit 0\n"
            "else\n"
            "  printf 'unexpected gh invocation: %s\\n' \"$*\" >&2\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)

    def write_trellis_finalize_stub(self, stub_bin: Path) -> None:
        (stub_bin / "trellis-finalize").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "mkdir -p .trellis/workspace/sdelmas\n"
            "printf 'finalized\\n' >> .trellis/workspace/sdelmas/journal-1.md\n"
            "git add .trellis/workspace/sdelmas/journal-1.md\n"
            "git commit -m 'chore: record journal'\n",
            encoding="utf-8",
        )
        (stub_bin / "trellis-finalize").chmod(0o755)

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
        self.assertTrue((root / ".agents/skills/trellis-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/trellis-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / "scripts/trellis-full-check.sh").is_file())
        self.assertTrue((root / "scripts/trellis-housekeeping.sh").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/TRELLIS_REVIEW_PR_PACK.md").is_file())
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/refresh-specs.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-continue.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-finish-work.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-full-check.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-housekeeping.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-refresh-specs.prompt.md").is_file())
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".claude/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".claude/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".claude/commands/sd/refresh-specs.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/continue.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/refresh-specs.md").exists())

    def test_platform_filter_still_installs_shared_assets(self) -> None:
        root = self.make_repo(".claude", ".gemini", ".github", ".opencode")

        result = self.run_install(root, "--platform", "gemini")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/trellis-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/trellis-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/trellis-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / "scripts/trellis-full-check.sh").is_file())
        self.assertTrue((root / "scripts/trellis-housekeeping.sh").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/TRELLIS_REVIEW_PR_PACK.md").is_file())
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/refresh-specs.toml").is_file())
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".claude/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".claude/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".claude/commands/sd/refresh-specs.md").exists())
        self.assertFalse((root / ".github/prompts/sd-continue.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-finish-work.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-pr.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-full-check.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-housekeeping.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-refresh-specs.prompt.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/continue.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/refresh-specs.md").exists())

    def test_all_installs_every_adapter_without_anchors(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--all")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/trellis-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/trellis-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/trellis-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / "scripts/trellis-full-check.sh").is_file())
        self.assertTrue((root / "scripts/trellis-housekeeping.sh").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/TRELLIS_REVIEW_PR_PACK.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/continue.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/finish-work.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-pr.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/full-check.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/housekeeping.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/refresh-specs.md").is_file())
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/refresh-specs.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-continue.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-finish-work.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-full-check.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-housekeeping.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-refresh-specs.prompt.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd/continue.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd/finish-work.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd/review-pr.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd/full-check.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd/housekeeping.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd/refresh-specs.md").is_file())

    def test_installed_adapters_can_resolve_shared_skill(self) -> None:
        root = self.make_repo(".claude", ".gemini", ".github", ".opencode")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        review_skill = root / ".agents/skills/trellis-review-pr/SKILL.md"
        full_check_skill = root / ".agents/skills/trellis-full-check/SKILL.md"
        housekeeping_skill = root / ".agents/skills/trellis-housekeeping/SKILL.md"
        full_check_script = root / "scripts/trellis-full-check.sh"
        housekeeping_script = root / "scripts/trellis-housekeeping.sh"
        self.assertTrue(review_skill.is_file())
        self.assertTrue(full_check_skill.is_file())
        self.assertTrue(housekeeping_skill.is_file())
        self.assertTrue(full_check_script.is_file())
        self.assertTrue(housekeeping_script.is_file())
        for adapter in [
            root / ".claude/commands/sd/continue.md",
            root / ".gemini/commands/sd/continue.toml",
            root / ".github/prompts/sd-continue.prompt.md",
            root / ".opencode/commands/sd/continue.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                ".agents/skills/trellis-continue/SKILL.md",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/finish-work.md",
            root / ".gemini/commands/sd/finish-work.toml",
            root / ".github/prompts/sd-finish-work.prompt.md",
            root / ".opencode/commands/sd/finish-work.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                ".agents/skills/trellis-finish-work/SKILL.md",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/review-pr.md",
            root / ".gemini/commands/sd/review-pr.toml",
            root / ".github/prompts/sd-review-pr.prompt.md",
            root / ".opencode/commands/sd/review-pr.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                ".agents/skills/trellis-review-pr/SKILL.md",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/full-check.md",
            root / ".gemini/commands/sd/full-check.toml",
            root / ".github/prompts/sd-full-check.prompt.md",
            root / ".opencode/commands/sd/full-check.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn(".agents/skills/trellis-full-check/SKILL.md", content)
            self.assertIn("scripts/trellis-full-check.sh", content)
        for adapter in [
            root / ".claude/commands/sd/housekeeping.md",
            root / ".gemini/commands/sd/housekeeping.toml",
            root / ".github/prompts/sd-housekeeping.prompt.md",
            root / ".opencode/commands/sd/housekeeping.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn(".agents/skills/trellis-housekeeping/SKILL.md", content)
            self.assertIn("scripts/trellis-housekeeping.sh", content)
        for adapter in [
            root / ".claude/commands/sd/refresh-specs.md",
            root / ".gemini/commands/sd/refresh-specs.toml",
            root / ".github/prompts/sd-refresh-specs.prompt.md",
            root / ".opencode/commands/sd/refresh-specs.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("trellis-update-spec/SKILL.md", content)
            self.assertIn("without modifying", content)
            self.assertIn("architectural overview", content)
            self.assertIn("not warranted", content)

    def test_install_removes_legacy_trellis_namespace_adapters(self) -> None:
        root = self.make_repo(".gemini", ".github")
        legacy_gemini = root / ".gemini/commands/trellis/review-pr.toml"
        legacy_github = root / ".github/prompts/review-pr.prompt.md"
        legacy_gemini.parent.mkdir(parents=True)
        legacy_github.parent.mkdir(parents=True)
        legacy_gemini.write_bytes(
            (
                install.ROOT / "templates/.gemini/commands/sd/review-pr.toml"
            ).read_bytes().replace(
                b'description = "SD: ',
                b'description = "Trellis: ',
            )
        )
        legacy_github.write_bytes(
            (
                install.ROOT / "templates/.github/prompts/sd-review-pr.prompt.md"
            ).read_bytes()
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(legacy_gemini.exists())
        self.assertFalse(legacy_github.exists())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertIn("removed", result.stdout)
        self.assertIn(".gemini/commands/trellis/review-pr.toml", result.stdout)
        self.assertIn(".github/prompts/review-pr.prompt.md", result.stdout)

    def test_install_reports_modified_legacy_namespace_adapter_conflict(self) -> None:
        root = self.make_repo(".github")
        legacy_github = root / ".github/prompts/review-pr.prompt.md"
        legacy_github.parent.mkdir(parents=True)
        legacy_github.write_text("custom local command\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(
            legacy_github.read_text(encoding="utf-8"),
            "custom local command\n",
        )
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertIn("legacy-conflict", result.stdout)
        self.assertIn("content differs from pack template", result.stdout)
        self.assertIn("Re-run with --force", result.stdout)

    def test_force_removes_modified_legacy_namespace_adapter(self) -> None:
        root = self.make_repo(".github")
        legacy_github = root / ".github/prompts/review-pr.prompt.md"
        legacy_github.parent.mkdir(parents=True)
        legacy_github.write_text("custom local command\n", encoding="utf-8")

        result = self.run_install(root, "--force")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(legacy_github.exists())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertIn("removed", result.stdout)
        self.assertIn(".github/prompts/review-pr.prompt.md", result.stdout)

    def test_force_removes_legacy_namespace_symlink_without_following_it(self) -> None:
        root = self.make_repo(".github")
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="trellis-review-pr-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_target = Path(outside_tempdir.name) / "outside-command.md"
        outside_target.write_text("outside command\n", encoding="utf-8")
        legacy_github = root / ".github/prompts/review-pr.prompt.md"
        legacy_github.parent.mkdir(parents=True)
        legacy_github.symlink_to(outside_target)

        result = self.run_install(root, "--force")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(legacy_github.exists())
        self.assertFalse(legacy_github.is_symlink())
        self.assertEqual(
            outside_target.read_text(encoding="utf-8"),
            "outside command\n",
        )
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertIn("removed", result.stdout)
        self.assertIn(".github/prompts/review-pr.prompt.md", result.stdout)

    def test_force_does_not_remove_non_pack_refresh_specs_legacy_adapter(self) -> None:
        root = self.make_repo(".github")
        legacy_refresh_specs = root / ".github/prompts/refresh-specs.prompt.md"
        legacy_refresh_specs.parent.mkdir(parents=True)
        legacy_refresh_specs.write_text(
            "custom refresh specs command\n",
            encoding="utf-8",
        )

        result = self.run_install(root, "--force")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            legacy_refresh_specs.read_text(encoding="utf-8"),
            "custom refresh specs command\n",
        )
        self.assertTrue(
            (root / ".github/prompts/sd-refresh-specs.prompt.md").is_file()
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

    def test_force_preserves_existing_prism_rules(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/trellis-review-pr/SKILL.md"
        prism_rules = root / ".prism/rules.json"
        target.parent.mkdir(parents=True)
        prism_rules.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")
        prism_rules.write_text('{"custom": true}\n', encoding="utf-8")

        result = self.run_install(root, "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("preserved", result.stdout)
        self.assertIn(".prism/rules.json", result.stdout)
        self.assertIn("Trellis PR Review Loop", target.read_text(encoding="utf-8"))
        self.assertEqual(
            prism_rules.read_text(encoding="utf-8"),
            '{"custom": true}\n',
        )
        self.assertFalse(prism_rules.with_name("rules.json.bak").exists())

    def test_preserves_existing_prism_rules_without_force(self) -> None:
        root = self.make_repo(".gemini")
        prism_rules = root / ".prism/rules.json"
        prism_rules.parent.mkdir(parents=True)
        prism_rules.write_text('{"custom": true}\n', encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("preserved", result.stdout)
        self.assertIn(".prism/rules.json", result.stdout)
        self.assertNotIn("Conflicts:", result.stdout)
        self.assertNotIn("Re-run with --force", result.stdout)
        self.assertEqual(
            prism_rules.read_text(encoding="utf-8"),
            '{"custom": true}\n',
        )

    def test_force_preserved_prism_rules_are_excluded_from_diff_check(self) -> None:
        root = self.make_repo()
        prism_rules = root / ".prism/rules.json"
        prism_rules.parent.mkdir(parents=True)
        prism_rules.write_text('{"custom": false}\n', encoding="utf-8")
        self.run_git(root, "add", ".prism/rules.json")
        prism_rules.write_text('{"custom": true}   \n', encoding="utf-8")

        result = self.run_install(root, "--force", skip_diff_check=False)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("preserved", result.stdout)
        self.assertEqual(
            prism_rules.read_text(encoding="utf-8"),
            '{"custom": true}   \n',
        )

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
        self.assertFalse((root / ".agents/skills/trellis-full-check/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/trellis-housekeeping/SKILL.md").exists())
        self.assertFalse((root / "scripts/trellis-full-check.sh").exists())
        self.assertFalse((root / "scripts/trellis-housekeeping.sh").exists())
        self.assertFalse((root / ".prism/rules.json").exists())
        self.assertFalse((root / "docs/TRELLIS_REVIEW_PR_PACK.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd/refresh-specs.md").exists())

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

    def test_rejects_existing_target_directory(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/trellis-review-pr/SKILL.md"
        target.mkdir(parents=True)

        result = self.run_install(root, "--force")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target exists and is not a file", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_rejects_existing_broken_target_symlink(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/trellis-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        missing_target = root / ".agents/skills/trellis-review-pr/missing.md"
        target.symlink_to(missing_target)

        result = self.run_install(root, "--force")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target exists and is not a file", result.stdout)
        self.assertNotIn("Traceback", result.stdout)
        self.assertFalse(missing_target.exists())

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
        for target in [
            Path("/tmp/pwn"),
            Path("../outside"),
            Path(".agents/../x"),
            Path(r"C:tmp\pwn"),
            Path("C:/tmp/pwn"),
            Path(r"\\server\share\pwn"),
            Path(r".agents\..\x"),
        ]:
            with self.subTest(target=target):
                with self.assertRaisesRegex(SystemExit, "unsafe target path"):
                    install.validate_manifest([self.valid_pack_file(target=target)])

    def test_manifest_rejects_unsafe_anchor_paths(self) -> None:
        for anchor in [
            Path("/tmp"),
            Path("../.github"),
            Path(".github/../x"),
            Path(r"C:.github"),
            Path(r"\.github"),
            Path(r".github\..\x"),
        ]:
            with self.subTest(anchor=anchor):
                with self.assertRaisesRegex(SystemExit, "unsafe anchor path"):
                    install.validate_manifest([self.valid_pack_file(anchor=anchor)])

    def test_manifest_rejects_unsafe_source_paths(self) -> None:
        for source in [
            Path("/tmp/pwn"),
            install.ROOT / ".." / "outside",
            install.ROOT / r"C:tmp\pwn",
            install.ROOT / r"templates\..\install.py",
        ]:
            with self.subTest(source=source):
                with self.assertRaisesRegex(SystemExit, "unsafe source path"):
                    install.validate_manifest([self.valid_pack_file(source=source)])

    def test_manifest_rejects_source_symlink_resolved_outside_pack_root(self) -> None:
        pack_tempdir = tempfile.TemporaryDirectory(
            prefix="trellis-review-pr-pack-root-"
        )
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="trellis-review-pr-pack-outside-"
        )
        self.addCleanup(pack_tempdir.cleanup)
        self.addCleanup(outside_tempdir.cleanup)
        pack_root = Path(pack_tempdir.name)
        outside_source = Path(outside_tempdir.name) / "secret.md"
        outside_source.write_text("outside\n", encoding="utf-8")
        source = pack_root / "templates/source.md"
        source.parent.mkdir(parents=True)
        source.symlink_to(outside_source)

        with mock.patch.object(install, "ROOT", pack_root):
            with self.assertRaisesRegex(SystemExit, "unsafe source path"):
                install.validate_manifest([self.valid_pack_file(source=source)])

    def test_adapters_reference_installed_shared_assets(self) -> None:
        _, files = install.load_manifest()
        adapter_files = [file for file in files if file.kind in {"command", "prompt"}]

        self.assertGreater(len(adapter_files), 0)
        for file in adapter_files:
            content = file.source.read_text(encoding="utf-8")
            if "continue" in file.target.name:
                self.assertIn(".agents/skills/trellis-continue/SKILL.md", content)
                self.assertIn("Follow that skill exactly", content)
            elif "finish-work" in file.target.name:
                self.assertIn(".agents/skills/trellis-finish-work/SKILL.md", content)
                self.assertIn("Follow that skill exactly", content)
            elif "full-check" in file.target.name:
                self.assertIn(".agents/skills/trellis-full-check/SKILL.md", content)
                self.assertIn("scripts/trellis-full-check.sh", content)
            elif "housekeeping" in file.target.name:
                self.assertIn(
                    ".agents/skills/trellis-housekeeping/SKILL.md",
                    content,
                )
                self.assertIn("scripts/trellis-housekeeping.sh", content)
            elif "refresh-specs" in file.target.name:
                self.assertIn("trellis-update-spec/SKILL.md", content)
                self.assertIn("without modifying", content)
                self.assertIn("architectural overview", content)
                self.assertIn("Do not create a new overview unless", content)
            else:
                self.assertIn(".agents/skills/trellis-review-pr/SKILL.md", content)

    def test_command_adapters_use_pack_owned_sd_namespace(self) -> None:
        _, files = install.load_manifest()

        command_files = [file for file in files if file.kind == "command"]
        github_prompt_files = [
            file for file in files if file.platform == "github" and file.kind == "prompt"
        ]
        self.assertGreater(len(command_files), 0)
        self.assertGreater(len(github_prompt_files), 0)
        for file in command_files:
            source = file.source.relative_to(install.ROOT).as_posix()
            self.assertIn("/commands/sd/", source)
            self.assertIn("/commands/sd/", file.target.as_posix())
            self.assertNotIn("/commands/trellis/", source)
            self.assertNotIn("/commands/trellis/", file.target.as_posix())
        for file in github_prompt_files:
            self.assertTrue(file.source.name.startswith("sd-"), file.source)
            self.assertTrue(file.target.name.startswith("sd-"), file.target)

        self.assertFalse((install.ROOT / "templates/.claude/commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.gemini/commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.opencode/commands/trellis").exists())

    def test_legacy_cleanup_does_not_target_trellis_owned_commands(self) -> None:
        _, files = install.load_manifest()
        protected = [
            file
            for file in files
            if file.target.name.startswith(
                (
                    "continue",
                    "finish-work",
                    "refresh-specs",
                    "sd-continue",
                    "sd-finish-work",
                    "sd-refresh-specs",
                )
            )
        ]

        self.assertGreater(len(protected), 0)
        for file in protected:
            self.assertIsNone(install.legacy_adapter_target(file), file.target)

    def test_refresh_specs_wrappers_include_repospec_and_architecture_gates(self) -> None:
        adapter_paths = [
            install.ROOT / "templates/.claude/commands/sd/refresh-specs.md",
            install.ROOT / "templates/.gemini/commands/sd/refresh-specs.toml",
            install.ROOT / "templates/.github/prompts/sd-refresh-specs.prompt.md",
            install.ROOT / "templates/.opencode/commands/sd/refresh-specs.md",
        ]

        for adapter_path in adapter_paths:
            content = adapter_path.read_text(encoding="utf-8")
            self.assertIn("trellis-update-spec/SKILL.md", content)
            self.assertIn("without modifying", content)
            self.assertIn("repospec artifact", content)
            self.assertIn("maintenance infrastructure", content)
            self.assertIn("instead of hand-editing generated output", content)
            self.assertIn("no infrastructure", content)
            self.assertIn("ARCHITECTURE.md", content)
            self.assertIn("docs/ARCHITECTURE.md", content)
            self.assertIn(".trellis/spec/**/architecture*.md", content)
            self.assertIn("Do not create a new overview unless", content)
            self.assertIn("changes high-level architecture", content)
            self.assertIn("not present", content)
            self.assertIn("not warranted", content)

    def test_full_check_script_writes_gito_reports_to_artifact_dir(self) -> None:
        script = (
            install.ROOT / "templates/scripts/trellis-full-check.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("TRELLIS_FULL_CHECK_GITO_OUT_DIR", script)
        self.assertIn(".build/review/gito", script)
        self.assertIn('gito review --vs "$base_ref" --out "$out_dir"', script)

    def test_full_check_script_warns_when_node_cannot_inspect_scripts(self) -> None:
        script = (
            install.ROOT / "templates/scripts/trellis-full-check.sh"
        ).read_text(encoding="utf-8")

        node_guard = 'elif ! have node; then'
        script_loop = 'for script_name in $scripts; do'
        self.assertIn(node_guard, script)
        self.assertIn(
            "node not found on PATH; cannot inspect package.json scripts; "
            "skipping package scripts.",
            script,
        )
        self.assertLess(script.index(node_guard), script.index(script_loop))

    def test_review_pr_skill_allows_reply_and_resolve_for_addressed_threads(self) -> None:
        skill = (
            install.ROOT
            / "templates/.agents/skills/trellis-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("standing permission to reply", skill)
        self.assertIn("review threads during this loop", skill)
        self.assertIn("fixed, rebutted with evidence", skill)
        self.assertIn("confirmed already addressed", skill)
        self.assertIn("Do not resolve valid unaddressed or ambiguous threads", skill)

    def test_review_pr_skill_auto_dispatches_housekeeping_after_merge(self) -> None:
        skill = (
            install.ROOT
            / "templates/.agents/skills/trellis-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")
        adapter_paths = [
            install.ROOT / "templates/.claude/commands/sd/review-pr.md",
            install.ROOT / "templates/.gemini/commands/sd/review-pr.toml",
            install.ROOT / "templates/.github/prompts/sd-review-pr.prompt.md",
            install.ROOT / "templates/.opencode/commands/sd/review-pr.md",
        ]

        self.assertIn("Post-Merge Auto-Dispatch", skill)
        self.assertIn('PR_STATE" = "MERGED"', skill)
        self.assertIn("bash scripts/trellis-housekeeping.sh", skill)
        self.assertIn("not a background GitHub webhook", skill)
        for adapter_path in adapter_paths:
            content = adapter_path.read_text(encoding="utf-8")
            self.assertIn("becomes merged during the active session", content)
            self.assertIn("housekeeping auto-dispatch", content)

    def test_housekeeping_skill_and_script_describe_expected_clean_state(self) -> None:
        skill = (
            install.ROOT
            / "templates/.agents/skills/trellis-housekeeping/SKILL.md"
        ).read_text(encoding="utf-8")
        script = (
            install.ROOT / "templates/scripts/trellis-housekeeping.sh"
        ).read_text(encoding="utf-8")
        result = subprocess.run(
            [
                "bash",
                "-n",
                str(install.ROOT / "templates/scripts/trellis-housekeeping.sh"),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        for text in [
            "Expected clean state",
            "Anomalies",
            "default branch checked out",
            "no open PRs",
            "no active Trellis tasks",
        ]:
            self.assertIn(text, skill)
        for text in [
            "Expected clean state",
            "Anomalies",
            "open PRs: none",
            "Trellis active tasks: none",
            "--no-auto-finalize",
            "--run-finalize-ci",
            "--merge-strategy",
            "view_open_pr_readiness_for_branch()",
            "unresolved_review_thread_count()",
            "PR #$pr_number is open, green, comment-clean",
            "pushed finalize journal entries to $REMOTE/$START_BRANCH",
            "failed to merge PR #$pr_number after finalize",
            "unable to resolve GitHub PR metadata for $branch",
            "confirmed PR #$pr_number merged",
            'GH_REPO_ARGS=(--repo "$GITHUB_REPO_SLUG")',
            "gh_pr_view()",
            'gh pr view "${GH_REPO_ARGS[@]}" "$@"',
            'gh pr view "$@"',
            'gh_pr_list --state merged --head="$branch"',
            "gh_pr_list --state open",
            "gh_issue_list --state open",
            "pruned $REMOTE after remote branch deletion",
            "default branch is unknown; skipped branch inventory checks",
            'grep -F -x -v "$DEFAULT_BRANCH"',
            'grep -F -x -v "$REMOTE/$DEFAULT_BRANCH"',
            'git remote get-url "$REMOTE"',
            'gh repo view "$GITHUB_REPO_SLUG"',
            "github_repo_from_remote_url()",
            '"${GH_REPO_ARGS[@]}"',
            '-- "$branch"',
            'git rev-parse --verify "refs/heads/$branch^{commit}"',
            'git branch -D -- "$branch"',
            "ls_remote_status",
            'git ls-remote --exit-code "$REMOTE" "refs/heads/$branch"',
            'elif [ "$ls_remote_status" -eq 2 ]; then',
            'git push "$REMOTE" ":refs/heads/$branch"',
            "remote branch $REMOTE/$branch is at $remote_head_oid",
            "left the remote branch untouched",
            'git rev-parse --verify "refs/heads/$DEFAULT_BRANCH^{commit}"',
            'git rev-parse --verify "refs/remotes/$REMOTE/$DEFAULT_BRANCH^{commit}"',
            'kept_remote_branch="$REMOTE/$START_BRANCH"',
            'grep -F -x -v "$kept_remote_branch"',
            "and kept $kept_remote_branch",
            "failed to check whether remote branch $REMOTE/$branch exists",
            "dry-run preview: skipped final git-state verification",
            "would run: git pull --ff-only $REMOTE $DEFAULT_BRANCH",
        ]:
            self.assertIn(text, script)

    def test_housekeeping_dry_run_previews_branch_cleanup_without_final_state_anomaly(
        self,
    ) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        self.write_housekeeping_gh_stub(stub_bin, head_oid)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/trellis-housekeeping.sh"),
                "--dry-run",
            ],
            cwd=repo,
            env={**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("would run: git fetch --prune origin", result.stdout)
        self.assertIn("confirmed PR #6 merged", result.stdout)
        self.assertIn("would switch to main", result.stdout)
        self.assertIn("would run: git pull --ff-only origin main", result.stdout)
        self.assertIn("would delete local branch feature/cleanup", result.stdout)
        self.assertIn("would delete remote branch origin/feature/cleanup", result.stdout)
        self.assertIn("dry-run preview: skipped final git-state verification", result.stdout)
        self.assertNotIn("still on feature/cleanup; skipped branch deletion", result.stdout)
        self.assertNotIn("current branch is feature/cleanup, expected main", result.stdout)
        self.assertEqual(
            self.git_output(repo, "branch", "--show-current"),
            "feature/cleanup",
        )

    def test_housekeeping_skips_remote_delete_when_remote_branch_moved(self) -> None:
        repo, remote, stub_bin, merged_head_oid = self.make_housekeeping_repo()
        self.write_housekeeping_gh_stub(stub_bin, merged_head_oid)
        (repo / "remote-only.txt").write_text("new remote commit\n", encoding="utf-8")
        self.run_git(repo, "add", "remote-only.txt")
        self.run_git(repo, "commit", "-m", "remote branch moved")
        moved_head_oid = self.git_output(repo, "rev-parse", "HEAD")
        self.run_git(repo, "push", "origin", "feature/cleanup")
        self.run_git(repo, "reset", "--hard", merged_head_oid)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/trellis-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "TRELLIS_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("deleted local branch feature/cleanup", result.stdout)
        self.assertIn(
            f"remote branch origin/feature/cleanup is at {moved_head_oid}",
            result.stdout,
        )
        self.assertIn(f"merged PR #6 ended at {merged_head_oid}", result.stdout)
        self.assertIn("left the remote branch untouched", result.stdout)
        self.assertNotIn("deleted remote branch origin/feature/cleanup", result.stdout)
        self.assertEqual(
            self.git_output(remote, "rev-parse", "refs/heads/feature/cleanup"),
            moved_head_oid,
        )

    def test_housekeeping_auto_finalizes_green_comment_clean_pr_then_cleans_up(
        self,
    ) -> None:
        repo, remote, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_finalize_gh_stub(stub_bin, marker)
        self.write_trellis_finalize_stub(stub_bin)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/trellis-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "TRELLIS_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "PR #6 is open, green, comment-clean, and matches local feature/cleanup",
            result.stdout,
        )
        self.assertIn("trellis-finalize created 1 commit(s)", result.stdout)
        self.assertIn("added [skip ci] to the finalize commit", result.stdout)
        self.assertIn(
            "pushed finalize journal entries to origin/feature/cleanup",
            result.stdout,
        )
        self.assertIn("merged PR #6 with merge strategy", result.stdout)
        self.assertIn("deleted local branch feature/cleanup", result.stdout)
        self.assertIn("deleted remote branch origin/feature/cleanup", result.stdout)
        self.assertIn("==> Anomalies\nnone", result.stdout)
        self.assertEqual(self.git_output(repo, "branch", "--show-current"), "main")
        recent_messages = self.git_output(repo, "log", "-5", "--pretty=%B")
        self.assertIn("[skip ci]", recent_messages)
        remote_branch = subprocess.run(
            ["git", "ls-remote", "--exit-code", str(remote), "refs/heads/feature/cleanup"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(remote_branch.returncode, 2, remote_branch.stdout)

    def test_housekeeping_counts_unresolved_review_threads_across_pages(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_finalize_gh_stub(
            stub_bin,
            marker,
            graphql_body=(
                "  args=\" $* \"\n"
                "  if [[ \"$args\" == *\"cursor=PAGE2\"* ]]; then\n"
                "    printf '1\\tfalse\\t\\n'\n"
                "  else\n"
                "    printf '0\\ttrue\\tPAGE2\\n'\n"
                "  fi\n"
            ),
        )
        self.write_trellis_finalize_stub(stub_bin)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/trellis-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "TRELLIS_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 has 1 unresolved review thread(s); skipped auto-finalize and merge",
            result.stdout,
        )
        self.assertNotIn("trellis-finalize created", result.stdout)
        self.assertFalse(marker.exists())
        self.assertEqual(
            self.git_output(repo, "branch", "--show-current"),
            "feature/cleanup",
        )

    def test_housekeeping_rejects_invalid_github_repo_override(self) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_finalize_gh_stub(stub_bin, marker)
        self.write_trellis_finalize_stub(stub_bin)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/trellis-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "TRELLIS_HOUSEKEEPING_GITHUB_REPO": "example",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "TRELLIS_HOUSEKEEPING_GITHUB_REPO must be an owner/repo slug",
            result.stdout,
        )
        self.assertIn(
            "could not derive GitHub repo from origin; skipped auto-finalize and merge",
            result.stdout,
        )
        self.assertNotIn("trellis-finalize created", result.stdout)
        self.assertFalse(marker.exists())

    def test_housekeeping_rejects_invalid_env_merge_strategy_before_finalize(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_finalize_gh_stub(stub_bin, marker)
        self.write_trellis_finalize_stub(stub_bin)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/trellis-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "TRELLIS_HOUSEKEEPING_GITHUB_REPO": "example/repo",
                "TRELLIS_HOUSEKEEPING_MERGE_STRATEGY": "fast-forward",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "merge strategy is invalid; expected merge, squash, or rebase",
            result.stdout,
        )
        self.assertNotIn("trellis-finalize created", result.stdout)
        self.assertFalse((repo / ".trellis/workspace/sdelmas/journal-1.md").exists())
        self.assertFalse(marker.exists())

    def test_housekeeping_reports_review_thread_inspection_failure(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_finalize_gh_stub(
            stub_bin,
            marker,
            graphql_body="  exit 42\n",
        )
        self.write_trellis_finalize_stub(stub_bin)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/trellis-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "TRELLIS_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "failed to inspect review threads for PR #6; skipped auto-finalize and merge",
            result.stdout,
        )
        self.assertIn("==> Expected clean state", result.stdout)
        self.assertIn("==> Anomalies", result.stdout)
        self.assertNotIn("trellis-finalize created", result.stdout)
        self.assertFalse(marker.exists())

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
