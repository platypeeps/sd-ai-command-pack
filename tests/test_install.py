from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import install


PACK_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PACK_ROOT / "install.py"
SECRET_MARKERS = (
    "AKIA",
    "BEGIN PRIVATE KEY",
    "xoxb-",
    "ghp_",
    "gho_",
    "/Users/",
    "\\Users\\",
)


class InstallTests(unittest.TestCase):
    _bash_path: str | None
    _manifest_files: list[install.PackFile]

    @classmethod
    def setUpClass(cls) -> None:
        cls._bash_path = shutil.which("bash")
        _, cls._manifest_files = install.load_manifest()

    def valid_pack_file(
        self,
        *,
        source: Path | None = None,
        target: Path = Path(".agents/skills/sd-review-pr/SKILL.md"),
        anchor: Path | None = None,
    ) -> install.PackFile:
        if source is None:
            source = (
                install.ROOT
                / "templates/.agents/skills/sd-review-pr/SKILL.md"
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
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)

        root = Path(tempdir.name)
        (root / ".trellis").mkdir()
        (root / ".trellis" / "config.yaml").write_text("# test\n", encoding="utf-8")
        self.run_git(root, "init")
        for platform_dir in platform_dirs:
            (root / platform_dir).mkdir(parents=True, exist_ok=True)
            platform = platform_dir.removeprefix(".")
            if platform in install.ACTIVE_TRELLIS_PLATFORM_MARKERS:
                self.activate_trellis_platform(root, platform)
        return root

    def make_git_repo_without_trellis(self) -> Path:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)

        root = Path(tempdir.name)
        self.run_git(root, "init")
        return root

    def write_trellis_stub(self, bin_dir: Path, log_path: Path, *, exit_code: int = 0) -> None:
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "trellis").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"printf '%s\\n' \"$*\" >> {str(log_path)!r}\n"
            f"if [ {exit_code} -ne 0 ]; then exit {exit_code}; fi\n"
            "if [ \"${1:-}\" = init ]; then\n"
            "  mkdir -p .trellis .agents/skills/trellis-start .codex/hooks\n"
            "  printf '# local trellis\\n' > .trellis/config.yaml\n"
            "  printf '# trellis start\\n' > .agents/skills/trellis-start/SKILL.md\n"
            "  printf '# agents\\n' > AGENTS.md\n"
            "  printf '# codex\\n' > .codex/config.toml\n"
            "  printf '{}\\n' > .codex/hooks.json\n"
            "  printf '# hook\\n' > .codex/hooks/session-start.py\n"
            "  for arg in \"$@\"; do\n"
            "    case \"$arg\" in\n"
            "      --cursor)\n"
            "        mkdir -p .cursor/agents .cursor/commands\n"
            "        printf '# cursor agent\\n' > .cursor/agents/trellis-check.md\n"
            "        printf '# cursor\\n' > .cursor/commands/trellis-continue.md\n"
            "        ;;\n"
            "      --gemini)\n"
            "        mkdir -p .gemini/commands/trellis\n"
            "        printf '# gemini\\n' > .gemini/commands/trellis/continue.toml\n"
            "        ;;\n"
            "      --claude)\n"
            "        mkdir -p .claude/commands/trellis\n"
            "        printf '# claude\\n' > .claude/commands/trellis/continue.md\n"
            "        ;;\n"
            "      --copilot)\n"
            "        mkdir -p .github/hooks\n"
            "        printf '{}\\n' > .github/hooks/trellis.json\n"
            "        ;;\n"
            "      --opencode)\n"
            "        mkdir -p .opencode/commands/trellis\n"
            "        printf '# opencode\\n' > .opencode/commands/trellis/continue.md\n"
            "        ;;\n"
            "    esac\n"
            "  done\n"
            "fi\n",
            encoding="utf-8",
        )
        (bin_dir / "trellis").chmod(0o755)

    def activate_trellis_platform(self, root: Path, platform: str) -> None:
        marker = install.ACTIVE_TRELLIS_PLATFORM_MARKERS[platform][0]
        destination = root / marker
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("# active Trellis platform marker\n", encoding="utf-8")

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

    def shared_manifest_files(self, kind: str) -> list[install.PackFile]:
        return [
            file
            for file in self._manifest_files
            if file.platform == "shared" and file.kind == kind
        ]

    def assert_installed_targets_snapshot_matches_selection(
        self,
        root: Path,
        *,
        platforms: list[str] | None = None,
        install_all: bool = False,
    ) -> None:
        _, files = install.load_manifest()
        selected, _ = install.selected_files(files, root, platforms, install_all)
        snapshot = root / install.INSTALLED_TARGETS_FILE

        self.assertTrue(snapshot.is_file(), snapshot)
        self.assertEqual(
            snapshot.read_text(encoding="utf-8"),
            install.installed_targets_content(selected),
        )

    def assert_shell_syntax_valid(self, script: Path) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        result = subprocess.run(
            [self._bash_path, "-n", str(script)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{script}: {result.stdout}")

    def assert_python_syntax_valid(self, script: Path) -> None:
        pycache_root = Path(tempfile.gettempdir()) / "sd-ai-command-pack-pycache"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script)],
            env={
                **os.environ,
                "PYTHONPYCACHEPREFIX": str(pycache_root),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{script}: {result.stdout}")

    def assert_prism_rules_valid(self, rules_path: Path) -> None:
        rules = json.loads(rules_path.read_text(encoding="utf-8"))

        self.assertIsInstance(rules, dict, f"{rules_path}: root must be an object")
        self.assertEqual(
            set(rules),
            {"focus", "severityOverrides", "required"},
            f"{rules_path}: unexpected Prism rules keys",
        )

        focus = rules["focus"]
        self.assertIsInstance(focus, list, f"{rules_path}: focus must be a list")
        self.assertGreater(len(focus), 0, f"{rules_path}: focus must not be empty")
        for index, item in enumerate(focus):
            self.assertIsInstance(
                item,
                str,
                f"{rules_path}: focus[{index}] must be a string",
            )
            self.assertTrue(item, f"{rules_path}: focus[{index}] must not be empty")

        severity_overrides = rules["severityOverrides"]
        self.assertIsInstance(
            severity_overrides,
            dict,
            f"{rules_path}: severityOverrides must be an object",
        )
        self.assertGreater(
            len(severity_overrides),
            0,
            f"{rules_path}: severityOverrides must not be empty",
        )
        for category, severity in severity_overrides.items():
            self.assertIsInstance(
                category,
                str,
                f"{rules_path}: severityOverrides key must be a string",
            )
            self.assertTrue(
                category,
                f"{rules_path}: severityOverrides key must not be empty",
            )
            self.assertIn(
                severity,
                {"low", "medium", "high"},
                f"{rules_path}: severity for {category!r} is invalid",
            )

        required = rules["required"]
        self.assertIsInstance(
            required,
            list,
            f"{rules_path}: required must be a list",
        )
        self.assertGreater(len(required), 0, f"{rules_path}: required must not be empty")
        seen_ids: set[str] = set()
        for index, check in enumerate(required):
            self.assertIsInstance(
                check,
                dict,
                f"{rules_path}: required[{index}] must be an object",
            )
            self.assertEqual(
                set(check),
                {"id", "text"},
                f"{rules_path}: required[{index}] keys are invalid",
            )
            self.assertIsInstance(
                check["id"],
                str,
                f"{rules_path}: required[{index}].id must be a string",
            )
            self.assertTrue(
                check["id"],
                f"{rules_path}: required[{index}].id must not be empty",
            )
            self.assertNotIn(
                check["id"],
                seen_ids,
                f"{rules_path}: duplicate required id {check['id']!r}",
            )
            seen_ids.add(check["id"])
            self.assertIsInstance(
                check["text"],
                str,
                f"{rules_path}: required[{index}].text must be a string",
            )
            self.assertTrue(
                check["text"],
                f"{rules_path}: required[{index}].text must not be empty",
            )

    def assert_no_secret_markers(self, file_path: Path) -> None:
        content = file_path.read_text(encoding="utf-8")
        for marker in SECRET_MARKERS:
            self.assertNotIn(
                marker,
                content,
                f"{file_path}: contains blocked secret marker {marker!r}",
            )

    def assert_trellis_prerequisite_documented(self, content: str) -> None:
        for expected in (
            "Trellis",
            install.TRELLIS_INSTALL_DOCS_URL,
            "npm install -g @mindfoldhq/trellis@latest",
            "trellis init",
            ".trellis/config.yaml",
        ):
            self.assertIn(expected, content)

    def assert_copilot_guidance_block(self, content: str) -> None:
        self.assertIn(install.COPILOT_GUIDANCE_START, content)
        self.assertIn(install.COPILOT_GUIDANCE_END, content)
        for expected in (
            "Trellis And SD AI Command Pack Review Guidance",
            "Ignore copied-in Trellis runtime/platform files",
            ".trellis/scripts/**",
            ".trellis/agents/**",
            ".agents/skills/trellis-*",
            ".github/agents/trellis-*",
            ".github/copilot/**",
            ".github/hooks/trellis.json",
            ".github/prompts/continue.prompt.md",
            ".github/prompts/finish-work.prompt.md",
            ".github/skills/trellis-*",
            ".claude/",
            ".codex/",
            ".cursor/",
            ".gemini/",
            ".opencode/",
            "Ignore files copied in from `sd-ai-command-pack`",
            ".agents/skills/sd-*",
            ".agents/skills/sd-full-check/",
            ".agents/skills/sd-housekeeping/",
            ".github/prompts/sd-*",
            ".claude/commands/sd/**",
            ".cursor/commands/sd-*",
            ".gemini/commands/sd/**",
            ".opencode/commands/sd-*",
            ".prism/rules.json",
            ".sd-ai-command-pack/installed-targets.txt",
            "docs/SD_AI_COMMAND_PACK.md",
            "scripts/sd-ai-command-pack-full-check.sh",
            "scripts/sd-ai-command-pack-housekeeping.sh",
            "scripts/sd-ai-command-pack-review-scope.sh",
            "scripts/sd-ai-command-pack-review-learnings.py",
            "scripts/sd-ai-command-pack-install-audit.py",
            "scripts/sd-ai-command-pack-pr-body-scope.py",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
            "Do not leave line comments on wording",
            "copied SD command-pack skills/prompts/scripts/docs/rules",
            "app behavior",
            "data contracts",
            "repo-owned scripts",
            "data/access/security boundaries",
            "fail-closed behavior",
            "obvious syntax breakage",
            "secret leakage",
            "direct mismatch",
            "Tooling/generated scope",
            "Automation scope",
            "CI/review scope",
            ".sd-ai-command-pack/pr-body-scope.json",
            "Group duplicate root causes into one comment",
            "deterministic local checks",
            "current, non-outdated unresolved",
            "stale or outdated review threads",
            "copied or generated",
        ):
            self.assertIn(expected, content)

    def make_housekeeping_repo(self) -> tuple[Path, Path, Path, str]:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-housekeeping-test-")
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

    def write_auto_merge_gh_stub(
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

    def run_install(
        self,
        root: Path,
        *args: str,
        skip_diff_check: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(INSTALLER), str(root), *args]
        if skip_diff_check:
            command.append("--skip-diff-check")
        env = self.installer_subprocess_env()
        if extra_env:
            env = {**(env or os.environ.copy()), **extra_env}
        return subprocess.run(
            command,
            cwd=PACK_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def installer_subprocess_env(self) -> dict[str, str] | None:
        if "COVERAGE_PROCESS_START" not in os.environ:
            return None

        env = os.environ.copy()
        sitecustomize_dir = PACK_ROOT / "tests/coverage_sitecustomize"
        pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(sitecustomize_dir)
            if not pythonpath
            else os.pathsep.join([str(sitecustomize_dir), pythonpath])
        )
        return env

    def test_installs_shared_skill_and_existing_platform_adapters(self) -> None:
        root = self.make_repo(".cursor", ".gemini", ".github")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertFalse(
            (root / ".agents/skills/trellis-review-pr/SKILL.md").exists()
        )
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertFalse(
            (root / ".agents/skills/trellis-full-check/SKILL.md").exists()
        )
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertFalse(
            (root / ".agents/skills/trellis-housekeeping/SKILL.md").exists()
        )
        self.assertTrue((root / ".agents/skills/sd-continue/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-start/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-finish-work/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-learnings/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-update-spec/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-housekeeping.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-scope.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-learnings.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-install-audit.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-pr-body-scope.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-update-spec-kb.py").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_installed_targets_snapshot_matches_selection(root)
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/start.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-learnings.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-continue.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-start.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-finish-work.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-learnings.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-full-check.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-housekeeping.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-update-spec.prompt.md").is_file())
        copilot_instructions = root / ".github/copilot-instructions.md"
        self.assertTrue(copilot_instructions.is_file())
        self.assert_copilot_guidance_block(
            copilot_instructions.read_text(encoding="utf-8")
        )
        self.assertTrue((root / ".cursor/commands/sd-continue.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-start.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-finish-work.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-learnings.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-full-check.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-housekeeping.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-update-spec.md").is_file())
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".claude/commands/sd/start.md").exists())
        self.assertFalse((root / ".claude/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-learnings.md").exists())
        self.assertFalse((root / ".claude/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".claude/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".claude/commands/sd/update-spec.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-continue.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-start.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-finish-work.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-learnings.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-update-spec.md").exists())

    def test_default_install_skips_plain_framework_dirs_without_trellis_markers(
        self,
    ) -> None:
        root = self.make_repo()
        for platform_dir in (
            ".claude",
            ".cursor",
            ".gemini",
            ".github",
            ".opencode",
        ):
            (root / platform_dir).mkdir()

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_installed_targets_snapshot_matches_selection(root)
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-continue.md").exists())
        self.assertFalse((root / ".gemini/commands/sd/continue.toml").exists())
        self.assertFalse((root / ".github/prompts/sd-review-pr.prompt.md").exists())
        self.assertFalse((root / ".github/copilot-instructions.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertIn(
            "active Trellis claude install not detected",
            result.stdout,
        )
        self.assertIn(
            "active Trellis cursor install not detected",
            result.stdout,
        )
        self.assertIn(
            "active Trellis gemini install not detected",
            result.stdout,
        )
        self.assertIn(
            "active Trellis github install not detected",
            result.stdout,
        )
        self.assertIn(
            "active Trellis opencode install not detected",
            result.stdout,
        )

    def test_platform_filter_still_installs_shared_assets(self) -> None:
        root = self.make_repo(".claude", ".cursor", ".gemini", ".github", ".opencode")

        result = self.run_install(root, "--platform", "gemini")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-start/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-learnings/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-housekeeping.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-scope.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-learnings.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-pr-body-scope.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-update-spec-kb.py").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_installed_targets_snapshot_matches_selection(
            root,
            platforms=["gemini"],
        )
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/start.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-learnings.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".claude/commands/sd/start.md").exists())
        self.assertFalse((root / ".claude/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-learnings.md").exists())
        self.assertFalse((root / ".claude/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".claude/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".claude/commands/sd/update-spec.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-continue.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-start.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-finish-work.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-learnings.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-update-spec.md").exists())
        self.assertFalse((root / ".github/prompts/sd-continue.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-start.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-finish-work.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-pr.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-learnings.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-full-check.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-housekeeping.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-update-spec.prompt.md").exists())
        self.assertFalse((root / ".github/copilot-instructions.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-continue.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-start.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-finish-work.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-learnings.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-update-spec.md").exists())

    def test_all_installs_every_adapter_without_anchors(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--all")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-start/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-learnings/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-housekeeping.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-scope.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-learnings.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-pr-body-scope.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-update-spec-kb.py").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_installed_targets_snapshot_matches_selection(
            root,
            install_all=True,
        )
        self.assertTrue((root / ".claude/commands/sd/continue.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/start.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/finish-work.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-pr.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-learnings.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/full-check.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/housekeeping.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/update-spec.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-continue.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-start.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-finish-work.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-learnings.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-full-check.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-housekeeping.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-update-spec.md").is_file())
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/start.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-learnings.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-continue.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-start.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-finish-work.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-learnings.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-full-check.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-housekeeping.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-update-spec.prompt.md").is_file())
        copilot_instructions = root / ".github/copilot-instructions.md"
        self.assertTrue(copilot_instructions.is_file())
        self.assert_copilot_guidance_block(
            copilot_instructions.read_text(encoding="utf-8")
        )
        self.assertTrue((root / ".opencode/commands/sd-continue.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-start.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-finish-work.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-learnings.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-full-check.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-housekeeping.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-update-spec.md").is_file())

    def test_installed_adapters_can_resolve_shared_skill(self) -> None:
        root = self.make_repo(".claude", ".cursor", ".gemini", ".github", ".opencode")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        review_skill = root / ".agents/skills/sd-review-pr/SKILL.md"
        review_learnings_skill = root / ".agents/skills/sd-review-learnings/SKILL.md"
        full_check_skill = root / ".agents/skills/sd-full-check/SKILL.md"
        housekeeping_skill = root / ".agents/skills/sd-housekeeping/SKILL.md"
        review_learnings_script = root / "scripts/sd-ai-command-pack-review-learnings.py"
        full_check_script = root / "scripts/sd-ai-command-pack-full-check.sh"
        housekeeping_script = root / "scripts/sd-ai-command-pack-housekeeping.sh"
        self.assertTrue(review_skill.is_file())
        self.assertTrue(review_learnings_skill.is_file())
        self.assertTrue(full_check_skill.is_file())
        self.assertTrue(housekeeping_skill.is_file())
        self.assertTrue(review_learnings_script.is_file())
        self.assertTrue(full_check_script.is_file())
        self.assertTrue(housekeeping_script.is_file())
        for adapter in [
            root / ".claude/commands/sd/start.md",
            root / ".cursor/commands/sd-start.md",
            root / ".gemini/commands/sd/start.toml",
            root / ".github/prompts/sd-start.prompt.md",
            root / ".opencode/commands/sd-start.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                ".agents/skills/trellis-start/SKILL.md",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/continue.md",
            root / ".cursor/commands/sd-continue.md",
            root / ".gemini/commands/sd/continue.toml",
            root / ".github/prompts/sd-continue.prompt.md",
            root / ".opencode/commands/sd-continue.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                ".agents/skills/trellis-continue/SKILL.md",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/finish-work.md",
            root / ".cursor/commands/sd-finish-work.md",
            root / ".gemini/commands/sd/finish-work.toml",
            root / ".github/prompts/sd-finish-work.prompt.md",
            root / ".opencode/commands/sd-finish-work.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                ".agents/skills/trellis-finish-work/SKILL.md",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/review-pr.md",
            root / ".cursor/commands/sd-review-pr.md",
            root / ".gemini/commands/sd/review-pr.toml",
            root / ".github/prompts/sd-review-pr.prompt.md",
            root / ".opencode/commands/sd-review-pr.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                ".agents/skills/sd-review-pr/SKILL.md",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/review-learnings.md",
            root / ".cursor/commands/sd-review-learnings.md",
            root / ".gemini/commands/sd/review-learnings.toml",
            root / ".github/prompts/sd-review-learnings.prompt.md",
            root / ".opencode/commands/sd-review-learnings.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn(".agents/skills/sd-review-learnings/SKILL.md", content)
            self.assertIn("scripts/sd-ai-command-pack-review-learnings.py", content)
        for adapter in [
            root / ".claude/commands/sd/full-check.md",
            root / ".cursor/commands/sd-full-check.md",
            root / ".gemini/commands/sd/full-check.toml",
            root / ".github/prompts/sd-full-check.prompt.md",
            root / ".opencode/commands/sd-full-check.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn(".agents/skills/sd-full-check/SKILL.md", content)
            self.assertIn("scripts/sd-ai-command-pack-full-check.sh", content)
        for adapter in [
            root / ".claude/commands/sd/housekeeping.md",
            root / ".cursor/commands/sd-housekeeping.md",
            root / ".gemini/commands/sd/housekeeping.toml",
            root / ".github/prompts/sd-housekeeping.prompt.md",
            root / ".opencode/commands/sd-housekeeping.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn(".agents/skills/sd-housekeeping/SKILL.md", content)
            self.assertIn("scripts/sd-ai-command-pack-housekeeping.sh", content)
        for adapter in [
            root / ".claude/commands/sd/update-spec.md",
            root / ".cursor/commands/sd-update-spec.md",
            root / ".gemini/commands/sd/update-spec.toml",
            root / ".github/prompts/sd-update-spec.prompt.md",
            root / ".opencode/commands/sd-update-spec.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn(".agents/skills/sd-update-spec/SKILL.md", content)
            self.assertIn("Trellis update-spec first", content)
            self.assertIn(".obsidian-kb", content)

    def test_housekeeping_adapters_run_finish_work_before_housekeeping_script(
        self,
    ) -> None:
        adapters = [
            install.ROOT / "templates/.claude/commands/sd/housekeeping.md",
            install.ROOT / "templates/.cursor/commands/sd-housekeeping.md",
            install.ROOT / "templates/.gemini/commands/sd/housekeeping.toml",
            install.ROOT / "templates/.github/prompts/sd-housekeeping.prompt.md",
            install.ROOT / "templates/.opencode/commands/sd-housekeeping.md",
        ]

        for adapter in adapters:
            content = adapter.read_text(encoding="utf-8")
            finish_index = content.index("finish-work")
            script_index = content.index("bash scripts/sd-ai-command-pack-housekeeping.sh")
            self.assertLess(
                finish_index,
                script_index,
                f"{adapter}: finish-work must run before housekeeping script",
            )

    def test_install_merges_copilot_guidance_preserving_existing_instructions(
        self,
    ) -> None:
        root = self.make_repo(".github")
        copilot_instructions = root / ".github/copilot-instructions.md"
        copilot_instructions.write_text(
            "# Repo Copilot Instructions\n\nKeep the product voice sharp.",
            encoding="utf-8",
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = copilot_instructions.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("# Repo Copilot Instructions"))
        self.assertIn("Keep the product voice sharp.", content)
        self.assert_copilot_guidance_block(content)
        self.assertIn("updated", result.stdout)
        self.assertIn(".github/copilot-instructions.md", result.stdout)

    def test_install_updates_existing_managed_copilot_guidance_block(self) -> None:
        root = self.make_repo(".github")
        copilot_instructions = root / ".github/copilot-instructions.md"
        copilot_instructions.write_text(
            "# Repo Copilot Instructions\n\n"
            f"{install.COPILOT_GUIDANCE_START}\n"
            "stale copied-file guidance\n"
            f"{install.COPILOT_GUIDANCE_END}\n\n"
            "Keep this repo-specific footer.\n",
            encoding="utf-8",
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = copilot_instructions.read_text(encoding="utf-8")
        self.assertIn("# Repo Copilot Instructions", content)
        self.assertIn("Keep this repo-specific footer.", content)
        self.assertNotIn("stale copied-file guidance", content)
        self.assertEqual(content.count(install.COPILOT_GUIDANCE_START), 1)
        self.assertEqual(content.count(install.COPILOT_GUIDANCE_END), 1)
        self.assert_copilot_guidance_block(content)

    def test_install_adopts_unmarked_copilot_guidance_into_managed_block(self) -> None:
        # Pre-marker guidance (key phrases present, no managed markers) must be
        # adopted into a marked, upgradable block rather than left stranded as a
        # block that can never be refreshed by future installs.
        root = self.make_repo(".github")
        copilot_instructions = root / ".github/copilot-instructions.md"
        existing = (
            "# Repo Copilot Instructions\n\n"
            "- Ignore copied-in Trellis runtime/platform files unless this "
            "PR changes Trellis integration.\n"
            "- Ignore files copied in from `sd-ai-command-pack` unless this "
            "PR changes the SD review-pack integration.\n"
        )
        copilot_instructions.write_text(existing, encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = copilot_instructions.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("# Repo Copilot Instructions"))
        self.assertEqual(content.count(install.COPILOT_GUIDANCE_START), 1)
        self.assertEqual(content.count(install.COPILOT_GUIDANCE_END), 1)
        self.assert_copilot_guidance_block(content)
        self.assertIn("updated", result.stdout)
        self.assertIn(".github/copilot-instructions.md", result.stdout)

        # A second run is now idempotent because the block is marker-tracked.
        second = self.run_install(root)
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertEqual(copilot_instructions.read_text(encoding="utf-8"), content)
        self.assertIn("unchanged", second.stdout)

    def test_copilot_guidance_dry_run_does_not_write_instructions(self) -> None:
        root = self.make_repo(".github")

        result = self.run_install(root, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("created", result.stdout)
        self.assertIn(".github/copilot-instructions.md", result.stdout)
        self.assertFalse((root / ".github/copilot-instructions.md").exists())

    def test_rejects_copilot_instruction_symlink_resolved_outside_repo(
        self,
    ) -> None:
        root = self.make_repo(".github")
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_target = Path(outside_tempdir.name) / "copilot-instructions.md"
        outside_target.write_text("outside\n", encoding="utf-8")
        target = root / ".github/copilot-instructions.md"
        target.symlink_to(outside_target)

        result = self.run_install(root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target path resolves outside target repo", result.stdout)
        self.assertEqual(outside_target.read_text(encoding="utf-8"), "outside\n")

    def test_install_removes_legacy_trellis_namespace_adapters(self) -> None:
        root = self.make_repo(".cursor", ".gemini", ".github", ".opencode")
        legacy_cursor = root / ".cursor/commands/trellis-review-pr.md"
        legacy_gemini = root / ".gemini/commands/trellis/review-pr.toml"
        legacy_github = root / ".github/prompts/review-pr.prompt.md"
        legacy_opencode = root / ".opencode/commands/trellis/review-pr.md"
        legacy_cursor.parent.mkdir(parents=True, exist_ok=True)
        legacy_gemini.parent.mkdir(parents=True, exist_ok=True)
        legacy_github.parent.mkdir(parents=True, exist_ok=True)
        legacy_opencode.parent.mkdir(parents=True, exist_ok=True)
        legacy_cursor.write_bytes(
            (
                install.ROOT / "templates/.cursor/commands/sd-review-pr.md"
            ).read_bytes()
        )
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
        legacy_opencode.write_bytes(
            install.strip_yaml_frontmatter(
                (
                    install.ROOT / "templates/.opencode/commands/sd-review-pr.md"
                ).read_bytes()
            )
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(legacy_cursor.exists())
        self.assertFalse(legacy_gemini.exists())
        self.assertFalse(legacy_github.exists())
        self.assertFalse(legacy_opencode.exists())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-pr.md").is_file())
        self.assertIn("removed", result.stdout)
        self.assertIn(".cursor/commands/trellis-review-pr.md", result.stdout)
        self.assertIn(".gemini/commands/trellis/review-pr.toml", result.stdout)
        self.assertIn(".github/prompts/review-pr.prompt.md", result.stdout)
        self.assertIn(".opencode/commands/trellis/review-pr.md", result.stdout)

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
            prefix="sd-ai-command-pack-outside-"
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

    def test_force_does_not_remove_non_pack_update_spec_legacy_adapter(self) -> None:
        root = self.make_repo(".github")
        legacy_update_spec = root / ".github/prompts/update-spec.prompt.md"
        legacy_update_spec.parent.mkdir(parents=True)
        legacy_update_spec.write_text(
            "custom update spec command\n",
            encoding="utf-8",
        )

        result = self.run_install(root, "--force")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            legacy_update_spec.read_text(encoding="utf-8"),
            "custom update spec command\n",
        )
        self.assertTrue(
            (root / ".github/prompts/sd-update-spec.prompt.md").is_file()
        )

    def test_install_removes_obsolete_sd_refresh_specs_files(self) -> None:
        root = self.make_repo(".claude", ".cursor", ".gemini", ".github", ".opencode")
        old_generated_content = (
            b"# Refresh Specs\n\n"
            b"Read `.agents/skills/trellis-update-spec/SKILL.md`.\n"
            b"Refresh the repospec artifact and architectural overview.\n"
            b"Run `python3 scripts/sd-ai-command-pack-refresh-specs-kb.py`.\n"
        )
        old_paths = [
            ".agents/skills/sd-refresh-specs/SKILL.md",
            ".claude/commands/sd/refresh-specs.md",
            ".cursor/commands/sd-refresh-specs.md",
            ".gemini/commands/sd/refresh-specs.toml",
            ".github/prompts/sd-refresh-specs.prompt.md",
            ".opencode/commands/sd-refresh-specs.md",
        ]
        for old_path in old_paths:
            destination = root / old_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(old_generated_content)

        old_helpers = [
            root / "scripts/sd-ai-command-pack-refresh-specs-kb.py",
            root / "scripts/sd-command-pack-refresh-specs-kb.py",
        ]
        for old_helper in old_helpers:
            old_helper.parent.mkdir(parents=True, exist_ok=True)
            old_helper.write_bytes(
                (
                    install.ROOT
                    / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
                ).read_bytes()
            )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        for old_path in old_paths:
            self.assertFalse((root / old_path).exists(), old_path)
            self.assertIn(old_path, result.stdout)
        for old_helper in old_helpers:
            self.assertFalse(old_helper.exists())
            self.assertIn(str(old_helper.relative_to(root)), result.stdout)
        self.assertTrue((root / ".agents/skills/sd-update-spec/SKILL.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/update-spec.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-update-spec.md").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-update-spec.prompt.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-update-spec.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-update-spec-kb.py").is_file())

    def test_installed_shared_scripts_and_prism_rules_are_valid(self) -> None:
        root = self.make_repo(".gemini")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        script_files = self.shared_manifest_files("script")
        self.assertGreater(len(script_files), 0)
        for file in script_files:
            installed_script = root / file.target
            self.assertTrue(installed_script.is_file(), installed_script)
            self.assertEqual(
                installed_script.read_bytes(),
                file.source.read_bytes(),
                f"{installed_script}: installer should copy script bytes exactly",
            )
            if installed_script.suffix == ".sh":
                self.assert_shell_syntax_valid(installed_script)
            elif installed_script.suffix == ".py":
                self.assert_python_syntax_valid(installed_script)
            else:
                self.fail(f"unexpected installed script suffix: {installed_script}")
            self.assert_no_secret_markers(installed_script)

        prism_rules = root / ".prism/rules.json"
        self.assertTrue(prism_rules.is_file())
        self.assert_prism_rules_valid(prism_rules)
        self.assert_no_secret_markers(prism_rules)

    def test_install_removes_obsolete_nested_opencode_adapter(self) -> None:
        root = self.make_repo(".opencode")
        obsolete = root / ".opencode/commands/sd/review-pr.md"
        obsolete.parent.mkdir(parents=True)
        current = (
            install.ROOT / "templates/.opencode/commands/sd-review-pr.md"
        ).read_bytes()
        obsolete.write_bytes(install.strip_yaml_frontmatter(current))

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(obsolete.exists())
        self.assertTrue((root / ".opencode/commands/sd-review-pr.md").is_file())
        self.assertIn("removed", result.stdout)
        self.assertIn(".opencode/commands/sd/review-pr.md", result.stdout)

    def test_install_reports_modified_obsolete_opencode_adapter_conflict(self) -> None:
        root = self.make_repo(".opencode")
        obsolete = root / ".opencode/commands/sd/review-pr.md"
        obsolete.parent.mkdir(parents=True)
        obsolete.write_text("custom local command\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(
            obsolete.read_text(encoding="utf-8"),
            "custom local command\n",
        )
        self.assertTrue((root / ".opencode/commands/sd-review-pr.md").is_file())
        self.assertIn("obsolete-conflict", result.stdout)
        self.assertIn("content differs from pack template", result.stdout)
        self.assertIn("Re-run with --force", result.stdout)

    def test_force_removes_modified_obsolete_opencode_adapter(self) -> None:
        root = self.make_repo(".opencode")
        obsolete = root / ".opencode/commands/sd/review-pr.md"
        obsolete.parent.mkdir(parents=True)
        obsolete.write_text("custom local command\n", encoding="utf-8")

        result = self.run_install(root, "--force")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(obsolete.exists())
        self.assertTrue((root / ".opencode/commands/sd-review-pr.md").is_file())
        self.assertIn("removed", result.stdout)
        self.assertIn(".opencode/commands/sd/review-pr.md", result.stdout)

    def test_install_removes_obsolete_pack_guide(self) -> None:
        root = self.make_repo()
        obsolete = root / "docs/TRELLIS_REVIEW_PR_PACK.md"
        obsolete.parent.mkdir(parents=True)
        current = (
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md"
        ).read_bytes()
        obsolete.write_bytes(install.old_pack_identity_variant(current))

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(obsolete.exists())
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assertIn("removed", result.stdout)
        self.assertIn("docs/TRELLIS_REVIEW_PR_PACK.md", result.stdout)

    def test_install_removes_obsolete_trellis_review_pr_skill(self) -> None:
        root = self.make_repo()
        obsolete = root / ".agents/skills/trellis-review-pr/SKILL.md"
        obsolete.parent.mkdir(parents=True)
        current = (
            install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_bytes()
        obsolete.write_bytes(install.old_review_skill_name_variant(current))

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(obsolete.exists())
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertIn("removed", result.stdout)
        self.assertIn(".agents/skills/trellis-review-pr/SKILL.md", result.stdout)

    def test_obsolete_review_skill_variant_matches_previous_shape(self) -> None:
        current = (
            install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_bytes()
        previous = install.old_review_skill_name_variant(current).decode("utf-8")

        self.assertIn("name: trellis-review-pr", previous)
        self.assertIn("# Trellis PR Review Loop", previous)
        self.assertIn(
            "Use this project-local skill for `/trellis:review-pr` style work.\n"
            "It turns a draft or in-progress PR",
            previous,
        )

    def test_old_shared_skill_variant_leaves_unmapped_files_unchanged(self) -> None:
        file = self.valid_pack_file(target=Path(".agents/skills/other/SKILL.md"))

        self.assertEqual(
            install.old_shared_skill_name_variant(file, b"unchanged\n"),
            b"unchanged\n",
        )

    def test_install_reports_modified_obsolete_trellis_review_pr_skill(self) -> None:
        root = self.make_repo()
        obsolete = root / ".agents/skills/trellis-review-pr/SKILL.md"
        obsolete.parent.mkdir(parents=True)
        obsolete.write_text("custom local review workflow\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(
            obsolete.read_text(encoding="utf-8"),
            "custom local review workflow\n",
        )
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertIn("obsolete-conflict", result.stdout)
        self.assertIn(".agents/skills/trellis-review-pr/SKILL.md", result.stdout)

    def test_install_removes_obsolete_trellis_full_check_and_housekeeping_skills(
        self,
    ) -> None:
        root = self.make_repo()

        cases = [
            (
                ".agents/skills/sd-full-check/SKILL.md",
                ".agents/skills/trellis-full-check/SKILL.md",
            ),
            (
                ".agents/skills/sd-housekeeping/SKILL.md",
                ".agents/skills/trellis-housekeeping/SKILL.md",
            ),
        ]
        for current_target, obsolete_target in cases:
            current_file = self.valid_pack_file(
                source=install.ROOT / "templates" / current_target,
                target=Path(current_target),
            )
            obsolete = root / obsolete_target
            obsolete.parent.mkdir(parents=True)
            obsolete.write_bytes(
                install.old_shared_skill_name_variant(
                    current_file,
                    current_file.source.read_bytes(),
                )
            )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        for current_target, obsolete_target in cases:
            self.assertTrue((root / current_target).is_file())
            self.assertFalse((root / obsolete_target).exists())
            self.assertIn(obsolete_target, result.stdout)

    def test_install_removes_obsolete_trellis_named_scripts(self) -> None:
        root = self.make_repo()

        cases = [
            (
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/trellis-full-check.sh",
            ),
            (
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/trellis-housekeeping.sh",
            ),
        ]
        for current_target, obsolete_target in cases:
            current_file = self.valid_pack_file(
                source=install.ROOT / "templates" / current_target,
                target=Path(current_target),
            )
            obsolete = root / obsolete_target
            obsolete.parent.mkdir(parents=True, exist_ok=True)
            obsolete.write_bytes(
                install.old_trellis_pack_owned_entity_variant(
                    install.old_pack_owned_entity_variant(
                        current_file.source.read_bytes(),
                    )
                )
            )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        for current_target, obsolete_target in cases:
            self.assertTrue((root / current_target).is_file())
            self.assertFalse((root / obsolete_target).exists())
            self.assertIn(obsolete_target, result.stdout)

    def test_install_removes_obsolete_sd_command_pack_named_scripts(self) -> None:
        root = self.make_repo()

        cases = [
            (
                "scripts/sd-ai-command-pack-review-learnings.py",
                "scripts/sd-review-learnings.py",
            ),
            (
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-command-pack-full-check.sh",
            ),
            (
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/sd-command-pack-housekeeping.sh",
            ),
            (
                "scripts/sd-ai-command-pack-review-scope.sh",
                "scripts/sd-command-pack-review-scope.sh",
            ),
            (
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "scripts/sd-command-pack-pr-body-scope.py",
            ),
            (
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "scripts/sd-command-pack-update-spec-kb.py",
            ),
        ]
        for current_target, obsolete_target in cases:
            current_file = self.valid_pack_file(
                source=install.ROOT / "templates" / current_target,
                target=Path(current_target),
            )
            obsolete = root / obsolete_target
            obsolete.parent.mkdir(parents=True, exist_ok=True)
            obsolete.write_bytes(
                install.old_pack_owned_entity_variant(
                    current_file.source.read_bytes(),
                )
            )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        for current_target, obsolete_target in cases:
            self.assertTrue((root / current_target).is_file())
            self.assertFalse((root / obsolete_target).exists())
            self.assertIn(obsolete_target, result.stdout)

    def test_install_reports_modified_obsolete_trellis_named_script(self) -> None:
        root = self.make_repo()
        obsolete = root / "scripts/trellis-full-check.sh"
        obsolete.parent.mkdir(parents=True)
        obsolete.write_text("custom full-check script\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(
            obsolete.read_text(encoding="utf-8"),
            "custom full-check script\n",
        )
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertIn("obsolete-conflict", result.stdout)
        self.assertIn("scripts/trellis-full-check.sh", result.stdout)

    def test_install_reports_modified_obsolete_trellis_full_check_skill(
        self,
    ) -> None:
        root = self.make_repo()
        obsolete = root / ".agents/skills/trellis-full-check/SKILL.md"
        obsolete.parent.mkdir(parents=True)
        obsolete.write_text("custom full-check workflow\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(
            obsolete.read_text(encoding="utf-8"),
            "custom full-check workflow\n",
        )
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertIn("obsolete-conflict", result.stdout)
        self.assertIn(".agents/skills/trellis-full-check/SKILL.md", result.stdout)

    def test_install_reports_modified_obsolete_trellis_housekeeping_skill(
        self,
    ) -> None:
        root = self.make_repo()
        obsolete = root / ".agents/skills/trellis-housekeeping/SKILL.md"
        obsolete.parent.mkdir(parents=True)
        obsolete.write_text("custom housekeeping workflow\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(
            obsolete.read_text(encoding="utf-8"),
            "custom housekeeping workflow\n",
        )
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertIn("obsolete-conflict", result.stdout)
        self.assertIn(".agents/skills/trellis-housekeeping/SKILL.md", result.stdout)

    def test_readme_documents_trellis_prerequisite_and_install_docs(self) -> None:
        readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")

        self.assert_trellis_prerequisite_documented(readme)
        self.assertIn("This pack only works", readme)
        self.assertIn("Prerequisite: install Trellis", readme)
        for expected in (
            "python3 install.py /path/to/trellis/repo",
            "python3 install.py /path/to/repo --dry-run",
            "python3 install.py /path/to/repo --force",
            "python3 install.py /path/to/repo --force --backup",
        ):
            self.assertIn(expected, readme)

    def test_coverage_dependency_is_declared_and_used_by_ci(self) -> None:
        requirements = (PACK_ROOT / "requirements-dev.txt").read_text(
            encoding="utf-8"
        )
        workflow = (
            PACK_ROOT / ".github/workflows/tests.yml"
        ).read_text(encoding="utf-8")
        readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertRegex(requirements, r"(?m)^coverage[<>=!~]")
        for expected in (
            "python3 -m pip install -r requirements-dev.txt",
            "COVERAGE_PROCESS_START=.coveragerc python3 -m coverage run --parallel-mode -m unittest discover -s tests",
            "python3 -m coverage combine",
            "python3 -m coverage report --fail-under=100",
        ):
            self.assertIn(expected, workflow)
            self.assertIn(expected, readme)

    def test_backup_path_skips_existing_numbered_backups(self) -> None:
        root = self.make_repo()
        destination = root / ".agents/skills/sd-review-pr/SKILL.md"
        destination.parent.mkdir(parents=True)
        destination.write_text("current\n", encoding="utf-8")
        destination.with_name("SKILL.md.bak").write_text("backup\n", encoding="utf-8")
        destination.with_name("SKILL.md.bak1").write_text(
            "backup 1\n",
            encoding="utf-8",
        )

        backup = install.next_backup_path(root, destination)

        self.assertEqual(backup, destination.with_name("SKILL.md.bak2"))

    def test_managed_block_helpers_reject_invalid_inputs(self) -> None:
        root = self.make_repo(".github")
        invalid_source = root / "invalid-block.md"
        invalid_source.write_text("missing markers\n", encoding="utf-8")
        invalid_file = self.valid_pack_file(
            source=invalid_source,
            target=Path(".github/copilot-instructions.md"),
        )
        managed_source = (
            install.ROOT / "templates/.github/copilot-instructions.sd-ai-command-pack.md"
        )
        unsupported_target = install.PackFile(
            platform="github",
            kind=install.MANAGED_BLOCK_KIND,
            source=managed_source,
            target=Path(".github/unsupported.md"),
            anchor=Path(".github"),
            install="if-anchor-exists",
        )
        directory_target = install.PackFile(
            platform="github",
            kind=install.MANAGED_BLOCK_KIND,
            source=managed_source,
            target=Path(".github/copilot-instructions.md"),
            anchor=Path(".github"),
            install="if-anchor-exists",
        )

        with self.assertRaisesRegex(SystemExit, "missing markers"):
            install.normalize_managed_block_template(invalid_file)
        with self.assertRaisesRegex(SystemExit, "incomplete"):
            install.merge_managed_block(
                f"{install.COPILOT_GUIDANCE_START}\npartial\n",
                "replacement\n",
            )
        with self.assertRaisesRegex(SystemExit, "unsupported managed block target"):
            install.install_managed_block(
                unsupported_target,
                root,
                dry_run=False,
            )

        destination = root / ".github/copilot-instructions.md"
        destination.mkdir()
        with self.assertRaisesRegex(SystemExit, "target exists and is not a file"):
            install.install_managed_block(directory_target, root, dry_run=False)

    def test_merge_managed_block_inserts_for_empty_and_newline_variants(self) -> None:
        block = (
            f"{install.COPILOT_GUIDANCE_START}\n"
            "managed\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
        )

        self.assertEqual(install.merge_managed_block("", block), block)
        self.assertEqual(
            install.merge_managed_block("Repo\n", block),
            f"Repo\n\n{block}",
        )
        self.assertEqual(
            install.merge_managed_block("Repo\n\n", block),
            f"Repo\n\n{block}",
        )

    def test_merge_managed_block_rejects_reversed_markers(self) -> None:
        reversed_markers = (
            f"{install.COPILOT_GUIDANCE_END}\nbody\n{install.COPILOT_GUIDANCE_START}\n"
        )
        with self.assertRaisesRegex(SystemExit, "incomplete"):
            install.merge_managed_block(reversed_markers, "replacement\n")

    def test_managed_block_update_preserves_invalid_existing_bytes(self) -> None:
        root = self.make_repo(".github")
        managed_file = install.PackFile(
            platform="github",
            kind=install.MANAGED_BLOCK_KIND,
            source=(
                install.ROOT
                / "templates/.github/copilot-instructions.sd-ai-command-pack.md"
            ),
            target=Path(".github/copilot-instructions.md"),
            anchor=Path(".github"),
            install="if-anchor-exists",
        )
        destination = root / managed_file.target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"Repo-specific bytes: \xff\n")

        result = install.install_managed_block(managed_file, root, dry_run=False)

        self.assertEqual(result.status, "updated")
        content = destination.read_bytes()
        self.assertIn(b"Repo-specific bytes: \xff\n", content)
        self.assertIn(install.COPILOT_GUIDANCE_START.encode("utf-8"), content)

    def test_install_file_unit_covers_core_status_branches(self) -> None:
        # Exercise the write/conflict/overwrite engine directly so its coverage
        # does not depend solely on the subprocess-coverage mechanism.
        root = self.make_repo()
        source = root / "source.md"
        source.write_text("pack template\n", encoding="utf-8")
        file = self.valid_pack_file(source=source, target=Path("docs/example.md"))
        destination = root / "docs/example.md"

        created = install.install_file(
            file, root, force=False, dry_run=False, backup=False
        )
        self.assertEqual(created.status, "created")
        self.assertEqual(destination.read_text(encoding="utf-8"), "pack template\n")

        unchanged = install.install_file(
            file, root, force=False, dry_run=False, backup=False
        )
        self.assertEqual(unchanged.status, "unchanged")

        destination.write_text("local edit\n", encoding="utf-8")
        conflict = install.install_file(
            file, root, force=False, dry_run=False, backup=False
        )
        self.assertEqual(conflict.status, "conflict")
        self.assertEqual(destination.read_text(encoding="utf-8"), "local edit\n")

        overwritten = install.install_file(
            file, root, force=True, dry_run=False, backup=True
        )
        self.assertEqual(overwritten.status, "overwritten")
        self.assertIsNotNone(overwritten.backup)
        self.assertEqual(destination.read_text(encoding="utf-8"), "pack template\n")
        self.assertEqual(
            overwritten.backup.read_text(encoding="utf-8"), "local edit\n"
        )

    def test_install_file_preserves_prism_rules(self) -> None:
        root = self.make_repo()
        file = install.PackFile(
            platform="shared",
            kind="config",
            source=install.ROOT / "templates/.prism/rules.json",
            target=Path(".prism/rules.json"),
            anchor=None,
            install="always",
        )
        destination = root / ".prism/rules.json"
        destination.parent.mkdir(parents=True)
        destination.write_text("{}\n", encoding="utf-8")

        result = install.install_file(
            file, root, force=True, dry_run=False, backup=False
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(destination.read_text(encoding="utf-8"), "{}\n")

    def test_install_file_auto_updates_legacy_adapter_content(self) -> None:
        root = self.make_repo()
        file = self.valid_pack_file(
            target=Path(".agents/skills/sd-review-pr/SKILL.md")
        )
        destination = root / ".agents/skills/sd-review-pr/SKILL.md"
        destination.parent.mkdir(parents=True)
        legacy_variant = install.strip_yaml_frontmatter(file.source.read_bytes())
        self.assertNotEqual(legacy_variant, file.source.read_bytes())
        destination.write_bytes(legacy_variant)

        result = install.install_file(
            file, root, force=False, dry_run=False, backup=False
        )

        self.assertEqual(result.status, "updated")
        self.assertEqual(destination.read_bytes(), file.source.read_bytes())

    def test_old_skill_name_variants_match_previous_shapes(self) -> None:
        full_check = install.old_full_check_skill_name_variant(
            b"name: sd-full-check\n# SD Full Check\n"
        )
        self.assertIn(b"name: trellis-full-check", full_check)
        self.assertIn(b"# Trellis Full Check", full_check)

        housekeeping = install.old_housekeeping_skill_name_variant(
            b"name: sd-housekeeping\n# SD Housekeeping\n"
        )
        self.assertIn(b"name: trellis-housekeeping", housekeeping)
        self.assertIn(b"# Trellis Housekeeping", housekeeping)

    def test_old_refresh_specs_match_requires_all_signals(self) -> None:
        self.assertFalse(
            install.old_refresh_specs_generated_content_matches(b"unrelated content")
        )
        # Has the old identity + Trellis foundation but no pack extensions.
        self.assertFalse(
            install.old_refresh_specs_generated_content_matches(
                b"sd-refresh-specs\ntrellis-update-spec/SKILL.md\n"
            )
        )
        matching = (
            b"sd-refresh-specs\n"
            b"trellis-update-spec/SKILL.md\n"
            b"repospec artifact\n"
            b"ARCHITECTURE.md\n"
            b".obsidian-kb\n"
        )
        self.assertTrue(
            install.old_refresh_specs_generated_content_matches(matching)
        )

    def test_subprocess_coverage_bootstrap_is_wired(self) -> None:
        # The 100% coverage gate depends on this bootstrap being present and on
        # parallel/fail-under settings; assert them so a silent break is caught.
        sitecustomize = PACK_ROOT / "tests/coverage_sitecustomize/sitecustomize.py"
        self.assertTrue(sitecustomize.is_file())
        self.assertIn(
            "coverage.process_startup()",
            sitecustomize.read_text(encoding="utf-8"),
        )
        coveragerc = (PACK_ROOT / ".coveragerc").read_text(encoding="utf-8")
        self.assertIn("parallel = True", coveragerc)
        self.assertIn("fail_under = 100", coveragerc)

    def test_main_diff_check_excludes_preserved_targets(self) -> None:
        root = self.make_repo()
        prism = root / ".prism/rules.json"
        prism.parent.mkdir(parents=True)
        prism.write_text('{"local": true}\n', encoding="utf-8")
        captured: dict[str, object] = {}

        def fake_diff_check(target: Path, paths: list[Path] | None = None) -> int:
            captured["paths"] = paths
            return 0

        with mock.patch.object(install, "run_diff_check", fake_diff_check):
            code = install.main([str(root)])

        self.assertEqual(code, 0)
        paths = captured.get("paths")
        self.assertIsInstance(paths, list)
        self.assertNotIn(Path(".prism/rules.json"), paths)
        self.assertIn(install.INSTALLED_TARGETS_FILE, paths)

    def test_force_backup_saves_copies_before_removing_legacy_files(self) -> None:
        root = self.make_repo(".claude", ".github")
        legacy = root / ".github/prompts/review-pr.prompt.md"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("my own prompt\n", encoding="utf-8")
        obsolete = root / ".claude/commands/sd/refresh-specs.md"
        obsolete.parent.mkdir(parents=True, exist_ok=True)
        obsolete.write_text("my own refresh notes\n", encoding="utf-8")

        result = self.run_install(
            root, "--all", "--force", "--backup", "--skip-diff-check"
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(legacy.exists())
        self.assertFalse(obsolete.exists())
        legacy_backup = legacy.with_name("review-pr.prompt.md.bak")
        obsolete_backup = obsolete.with_name("refresh-specs.md.bak")
        self.assertEqual(legacy_backup.read_text(encoding="utf-8"), "my own prompt\n")
        self.assertEqual(
            obsolete_backup.read_text(encoding="utf-8"), "my own refresh notes\n"
        )
        self.assertIn("backup", result.stdout)

    def test_force_backup_preserves_symlink_when_removing_legacy_file(self) -> None:
        root = self.make_repo(".github")
        real = root / "real-prompt.md"
        real.write_text("real\n", encoding="utf-8")
        legacy = root / ".github/prompts/review-pr.prompt.md"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to(real)

        result = self.run_install(
            root, "--platform", "github", "--force", "--backup", "--skip-diff-check"
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(legacy.is_symlink())
        legacy_backup = legacy.with_name("review-pr.prompt.md.bak")
        self.assertTrue(legacy_backup.is_symlink())
        self.assertEqual(os.readlink(legacy_backup), str(real))

    def test_manifest_declares_trellis_requirement(self) -> None:
        raw, _ = install.load_manifest()

        self.assertIs(raw.get("requiresTrellis"), True)
        self.assertIn("Trellis", raw["description"])

    def test_repo_declares_mit_license(self) -> None:
        raw, _ = install.load_manifest()
        readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")
        license_text = (PACK_ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertEqual(raw.get("license"), "MIT")
        self.assertIn("[![License: MIT]", readme)
        self.assertIn("[MIT License](LICENSE)", readme)
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 Platypeeps", license_text)
        self.assertIn("Permission is hereby granted, free of charge", license_text)

    def test_installed_usage_guide_documents_trellis_prerequisite(self) -> None:
        root = self.make_repo()

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        template = (
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md"
        ).read_text(encoding="utf-8")
        installed = (root / "docs/SD_AI_COMMAND_PACK.md").read_text(
            encoding="utf-8"
        )
        self.assert_trellis_prerequisite_documented(template)
        self.assert_trellis_prerequisite_documented(installed)
        self.assertEqual(installed, template)

    def test_installed_targets_snapshot_lists_scope_scripts_and_guide(self) -> None:
        root = self.make_repo(".github")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        snapshot = (root / install.INSTALLED_TARGETS_FILE).read_text(
            encoding="utf-8"
        )
        for expected in (
            "scripts/sd-ai-command-pack-review-scope.sh",
            "scripts/sd-ai-command-pack-review-learnings.py",
            "scripts/sd-ai-command-pack-pr-body-scope.py",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
            "docs/SD_AI_COMMAND_PACK.md",
        ):
            self.assertIn(expected, snapshot)

    def test_installed_targets_snapshot_updates_existing_content(self) -> None:
        root = self.make_repo()
        snapshot = root / install.INSTALLED_TARGETS_FILE
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text("stale\n", encoding="utf-8")
        selected = [self.valid_pack_file()]

        result = install.install_installed_targets_file(
            selected,
            root,
            dry_run=False,
        )

        self.assertEqual(result.status, "updated")
        self.assertEqual(
            snapshot.read_text(encoding="utf-8"),
            install.installed_targets_content(selected),
        )

    def test_conflict_requires_force(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = self.run_install(root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("conflict", result.stdout)
        self.assertEqual(target.read_text(encoding="utf-8"), "local edit\n")

        forced = self.run_install(root, "--force")
        self.assertEqual(forced.returncode, 0, forced.stdout)
        self.assertIn("SD PR Review Loop", target.read_text(encoding="utf-8"))

    def test_install_updates_old_generated_pack_entities_without_force(self) -> None:
        root = self.make_repo()
        target = root / ".agents/skills/sd-full-check/SKILL.md"
        source = install.ROOT / "templates/.agents/skills/sd-full-check/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_bytes(install.old_pack_owned_entity_variant(source.read_bytes()))

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("updated     .agents/skills/sd-full-check/SKILL.md", result.stdout)
        self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertNotIn(
            "scripts/trellis-full-check.sh",
            target.read_text(encoding="utf-8"),
        )

    def test_force_preserves_existing_prism_rules(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        prism_rules = root / ".prism/rules.json"
        target.parent.mkdir(parents=True)
        prism_rules.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")
        prism_rules.write_text('{"custom": true}\n', encoding="utf-8")

        result = self.run_install(root, "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("preserved", result.stdout)
        self.assertIn(".prism/rules.json", result.stdout)
        self.assertIn("SD PR Review Loop", target.read_text(encoding="utf-8"))
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
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = self.run_install(root, "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("backup", result.stdout)
        self.assertEqual(
            (root / ".agents/skills/sd-review-pr/SKILL.md.bak").read_text(
                encoding="utf-8"
            ),
            "local edit\n",
        )
        self.assertIn("SD PR Review Loop", target.read_text(encoding="utf-8"))

    def test_dry_run_force_backup_does_not_report_or_write_backup(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = self.run_install(root, "--dry-run", "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("overwritten", result.stdout)
        self.assertNotIn("backup", result.stdout)
        self.assertFalse(
            (root / ".agents/skills/sd-review-pr/SKILL.md.bak").exists()
        )
        self.assertEqual(target.read_text(encoding="utf-8"), "local edit\n")

    def test_force_backup_does_not_write_through_existing_backup_symlink(self) -> None:
        root = self.make_repo(".gemini")
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_backup = Path(outside_tempdir.name) / "outside-backup"
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
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
        self.assertFalse((root / ".agents/skills/sd-review-pr/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/sd-full-check/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/sd-housekeeping/SKILL.md").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-full-check.sh").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-housekeeping.sh").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-review-scope.sh").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-pr-body-scope.py").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-update-spec-kb.py").exists())
        self.assertFalse((root / ".prism/rules.json").exists())
        self.assertFalse((root / "docs/SD_AI_COMMAND_PACK.md").exists())
        self.assertFalse((root / install.INSTALLED_TARGETS_FILE).exists())
        self.assertIn(".sd-ai-command-pack/installed-targets.txt", result.stdout)
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-update-spec.md").exists())
        self.assertFalse((root / ".github/copilot-instructions.md").exists())

    def test_rejects_non_trellis_repo(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name)

        result = self.run_install(target)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".trellis/config.yaml not found", result.stdout)
        self.assertIn("trellis init", result.stdout)
        self.assertIn(install.TRELLIS_INSTALL_DOCS_URL, result.stdout)
        for unexpected in (
            ".agents",
            ".sd-ai-command-pack",
            ".prism",
            "docs",
            "scripts",
            ".github",
            ".claude",
            ".cursor",
            ".gemini",
            ".opencode",
        ):
            self.assertFalse((target / unexpected).exists(), unexpected)

    def test_local_only_bootstraps_trellis_and_excludes_generated_files(self) -> None:
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
        self.assertIn("mode: local-only", result.stdout)
        self.assertIn("initialized-trellis-local", result.stdout)
        self.assertIn("local-exclude", result.stdout)
        self.assertIn("local-only-marker-written", result.stdout)
        self.assertTrue((root / ".trellis/config.yaml").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertEqual(
            trellis_log.read_text(encoding="utf-8").strip(),
            "init --yes --skip-existing --codex --cursor",
        )

        exclude = Path(
            self.git_output(root, "rev-parse", "--git-path", "info/exclude")
        )
        if not exclude.is_absolute():
            exclude = root / exclude
        exclude_text = exclude.read_text(encoding="utf-8")
        for expected in (
            install.LOCAL_ONLY_EXCLUDE_START,
            "AGENTS.md",
            ".trellis/",
            ".agents/skills/sd-review-pr/SKILL.md",
            ".codex/config.toml",
            ".codex/hooks/",
            ".cursor/agents/trellis-*.md",
            ".cursor/commands/sd-review-pr.md",
            "scripts/sd-ai-command-pack-full-check.sh",
            ".sd-ai-command-pack/",
            ".obsidian-kb/",
            install.LOCAL_ONLY_EXCLUDE_END,
        ):
            self.assertIn(expected, exclude_text)
        self.assertTrue((root / install.LOCAL_ONLY_MARKER_FILE).is_file())
        self.assertEqual(self.git_output(root, "status", "--short"), "")

    def test_local_only_dry_run_does_not_init_trellis_or_write_exclude(self) -> None:
        root = self.make_git_repo_without_trellis()
        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        bin_dir = Path(tools_tempdir.name) / "bin"
        trellis_log = Path(tools_tempdir.name) / "trellis-args.log"
        self.write_trellis_stub(bin_dir, trellis_log)

        result = self.run_install(
            root,
            "--local-only",
            "--dry-run",
            "--platform",
            "gemini",
            extra_env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertIn("mode: local-only", result.stdout)
        self.assertIn("would-init-trellis-local", result.stdout)
        self.assertIn("would-update-local-exclude", result.stdout)
        self.assertIn("would-write-local-only-marker", result.stdout)
        self.assertFalse((root / ".trellis/config.yaml").exists())
        self.assertFalse(trellis_log.exists())
        self.assertFalse((root / install.LOCAL_ONLY_MARKER_FILE).exists())

    def test_local_only_rejects_tracked_framework_paths(self) -> None:
        root = self.make_repo()
        (root / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
        codex_config = root / ".codex/config.toml"
        codex_config.parent.mkdir(parents=True, exist_ok=True)
        codex_config.write_text("hooks = true\n", encoding="utf-8")
        self.run_git(
            root,
            "add",
            ".trellis/config.yaml",
            "AGENTS.md",
            ".codex/config.toml",
        )

        result = self.run_install(root, "--local-only")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("already tracked", result.stdout)
        self.assertIn(".trellis/config.yaml", result.stdout)
        self.assertIn("AGENTS.md", result.stdout)
        self.assertIn(".codex/config.toml", result.stdout)

    def test_local_only_requires_git_repo(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name)

        result = self.run_install(target, "--local-only")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("--local-only requires the target to be a Git repo", result.stdout)

    def test_local_only_skip_trellis_init_requires_existing_trellis(self) -> None:
        root = self.make_git_repo_without_trellis()

        result = self.run_install(root, "--local-only", "--skip-trellis-init")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(".trellis/config.yaml not found", result.stdout)

    def test_local_only_reports_missing_trellis_command(self) -> None:
        root = self.make_git_repo_without_trellis()
        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        bin_dir = Path(tools_tempdir.name) / "bin"
        bin_dir.mkdir()
        git_path = shutil.which("git")
        self.assertIsNotNone(git_path)
        (bin_dir / "git").write_text(
            "#!/bin/sh\n"
            f"exec {git_path!r} \"$@\"\n",
            encoding="utf-8",
        )
        (bin_dir / "git").chmod(0o755)

        result = self.run_install(
            root,
            "--local-only",
            extra_env={"PATH": str(bin_dir)},
        )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("needs `trellis` on PATH", result.stdout)

    def test_skip_trellis_init_requires_local_only(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--skip-trellis-init")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("--skip-trellis-init requires --local-only", result.stdout)

    def test_local_only_git_helpers_handle_errors(self) -> None:
        root = self.make_git_repo_without_trellis()
        subdir = root / "nested"
        subdir.mkdir()

        with self.assertRaisesRegex(SystemExit, "Git repo root"):
            install.require_git_repo_for_local_only(subdir)

        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(install.git_output(root, "status"))
            self.assertEqual(install.tracked_paths(root, ["anything"]), [])

        with mock.patch.object(install, "git_output", return_value=str(root)):
            with mock.patch.object(Path, "resolve", side_effect=OSError("boom")):
                with self.assertRaisesRegex(SystemExit, "cannot resolve target repo"):
                    install.require_git_repo_for_local_only(root)

        with mock.patch.object(install, "git_output", return_value=None):
            with self.assertRaisesRegex(SystemExit, "cannot find .git/info/exclude"):
                install.git_info_exclude_path(root)

        self.assertEqual(install.tracked_paths(root, []), [])
        failed = subprocess.CompletedProcess(
            ["git", "ls-files"],
            1,
            stdout="fatal: bad pathspec\n",
        )
        with mock.patch.object(subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(SystemExit, "git ls-files failed"):
                install.tracked_paths(root, ["bad"])

    def test_local_only_trellis_init_error_paths(self) -> None:
        root = self.make_git_repo_without_trellis()

        self.assertEqual(
            install.trellis_init_platforms(["cursor"], install_all=True),
            sorted(install.TRELLIS_INIT_PLATFORM_FLAGS),
        )

        failed = subprocess.CompletedProcess(
            ["trellis", "init"],
            2,
            stdout="trellis exploded\n",
        )
        with mock.patch.object(shutil, "which", return_value="/bin/trellis"):
            with mock.patch.object(subprocess, "run", return_value=failed):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(SystemExit, "trellis init failed"):
                        install.ensure_trellis_for_local_only(
                            root,
                            platforms=[],
                            install_all=False,
                            dry_run=False,
                            skip_trellis_init=False,
                        )
                self.assertEqual(output.getvalue(), "trellis exploded\n")

        succeeded_without_config = subprocess.CompletedProcess(
            ["trellis", "init"],
            0,
            stdout="",
        )
        with mock.patch.object(shutil, "which", return_value="/bin/trellis"):
            with mock.patch.object(
                subprocess,
                "run",
                return_value=succeeded_without_config,
            ):
                with self.assertRaisesRegex(
                    SystemExit,
                    "trellis init completed",
                ):
                    install.ensure_trellis_for_local_only(
                        root,
                        platforms=[],
                        install_all=False,
                        dry_run=False,
                        skip_trellis_init=False,
                    )

    def test_local_only_tracking_rejection_reports_overflow(self) -> None:
        root = self.make_git_repo_without_trellis()
        tracked = [f"path-{index}.txt" for index in range(22)]

        with mock.patch.object(install, "tracked_paths", return_value=tracked):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(SystemExit, "Remove these paths"):
                    install.reject_tracked_local_only_paths(root, [])

        self.assertIn("path-0.txt", output.getvalue())
        self.assertIn("2 more", output.getvalue())

    def test_local_only_exclude_block_edge_cases(self) -> None:
        block = install.local_only_exclude_block(["one/"])

        with self.assertRaisesRegex(SystemExit, "incomplete"):
            install.merge_local_only_exclude_block(
                f"{install.LOCAL_ONLY_EXCLUDE_START}\none/\n",
                block,
            )

        current = (
            "before\n"
            f"{install.LOCAL_ONLY_EXCLUDE_START}\n"
            "old/\n"
            f"{install.LOCAL_ONLY_EXCLUDE_END}\n"
            "after\n"
        )
        self.assertEqual(
            install.merge_local_only_exclude_block(current, block),
            f"before\n{block}after\n",
        )
        self.assertEqual(install.merge_local_only_exclude_block("", block), block)
        self.assertEqual(
            install.merge_local_only_exclude_block("manual", block),
            f"manual\n\n{block}",
        )

    def test_local_only_exclude_and_marker_are_idempotent(self) -> None:
        root = self.make_git_repo_without_trellis()

        install.ensure_local_only_exclude(root, [], dry_run=False)
        exclude_result = install.ensure_local_only_exclude(root, [], dry_run=False)
        self.assertEqual(exclude_result.status, "local-exclude-unchanged")

        install.write_local_only_marker(root, dry_run=False)
        marker_result = install.write_local_only_marker(root, dry_run=False)
        self.assertEqual(marker_result.status, "local-only-marker-unchanged")

    def test_rejects_target_path_resolved_outside_repo(self) -> None:
        root = self.make_repo()
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside = Path(outside_tempdir.name)
        (root / ".agents").symlink_to(outside, target_is_directory=True)

        result = self.run_install(root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target path resolves outside target repo", result.stdout)
        self.assertFalse((outside / "skills/sd-review-pr/SKILL.md").exists())

    def test_rejects_existing_target_symlink_resolved_outside_repo(self) -> None:
        root = self.make_repo(".gemini")
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_target = Path(outside_tempdir.name) / "outside-target"
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.symlink_to(outside_target)

        result = self.run_install(root, "--force")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target path resolves outside target repo", result.stdout)
        self.assertFalse(outside_target.exists())

    def test_rejects_existing_target_directory(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.mkdir(parents=True)

        result = self.run_install(root, "--force")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target exists and is not a file", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_rejects_existing_broken_target_symlink(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        missing_target = root / ".agents/skills/sd-review-pr/missing.md"
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
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())

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

    def test_manifest_rejects_unknown_duplicate_and_missing_entries(self) -> None:
        source = install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
        unknown_platform = install.PackFile(
            platform="mystery",
            kind="skill",
            source=source,
            target=Path(".agents/skills/sd-review-pr/SKILL.md"),
            anchor=None,
            install="always",
        )
        duplicate_a = self.valid_pack_file()
        duplicate_b = self.valid_pack_file()
        missing_source = self.valid_pack_file(source=install.ROOT / "missing.md")

        with self.assertRaisesRegex(SystemExit, "unknown platform"):
            install.validate_manifest([unknown_platform])
        with self.assertRaisesRegex(SystemExit, "duplicate target"):
            install.validate_manifest([duplicate_a, duplicate_b])
        with self.assertRaisesRegex(SystemExit, "missing pack template"):
            install.validate_manifest([missing_source])

    def test_path_resolution_errors_are_reported_without_tracebacks(self) -> None:
        with mock.patch.object(Path, "resolve", side_effect=OSError("boom")):
            with self.assertRaisesRegex(SystemExit, "cannot resolve source path"):
                install.validate_pack_source(
                    install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
                )

        with mock.patch.object(Path, "resolve", side_effect=OSError("boom")):
            with self.assertRaisesRegex(SystemExit, "cannot resolve target path"):
                install.validate_resolved_target_path(
                    Path("/tmp/repo"),
                    Path("/tmp/repo/file"),
                    "target path",
                )

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
            prefix="sd-ai-command-pack-root-"
        )
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
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

    def test_adapter_cleanup_handles_duplicates_and_directory_conflicts(self) -> None:
        root = self.make_repo()
        cleanup_target = Path(".github/prompts/review-pr.prompt.md")
        file = self.valid_pack_file(
            target=Path(".github/prompts/sd-review-pr.prompt.md")
        )

        no_op_results = install.cleanup_adapter_targets(
            [file, file],
            root,
            dry_run=False,
            force=False,
            backup=False,
            target_for_file=lambda _: cleanup_target,
            conflict_status="legacy-conflict",
        )

        self.assertEqual(no_op_results, [])

        (root / cleanup_target).mkdir(parents=True)
        conflict_results = install.cleanup_adapter_targets(
            [file],
            root,
            dry_run=False,
            force=False,
            backup=False,
            target_for_file=lambda _: cleanup_target,
            conflict_status="legacy-conflict",
        )

        self.assertEqual(len(conflict_results), 1)
        self.assertEqual(conflict_results[0].status, "legacy-conflict")
        self.assertEqual(conflict_results[0].reason, "target exists and is not a file")

    def test_misc_template_variants_keep_original_content_when_no_match(self) -> None:
        content = b"---\ntitle: Missing end\nbody\n"
        self.assertEqual(install.strip_yaml_frontmatter(content), content)
        self.assertEqual(
            install.strip_yaml_frontmatter(b"---\ntitle: Example\n---\nbody\n"),
            b"body\n",
        )
        self.assertEqual(
            install.toml_description_variant(
                b"prompt = \"Run it\"\n",
                "review-pr",
                "Trellis",
            ),
            b"prompt = \"Run it\"\n",
        )
        self.assertEqual(
            install.old_pack_owned_entity_variant(b"unchanged\n"),
            b"unchanged\n",
        )
        file = install.PackFile(
            platform="github",
            kind="command",
            source=install.ROOT
            / "templates/.github/prompts/sd-review-pr.prompt.md",
            target=Path(".github/prompts/sd-review-pr.prompt.md"),
            anchor=Path(".github"),
            install="if-anchor-exists",
        )
        self.assertIsNone(install.legacy_adapter_target(file))

    def test_git_diff_check_missing_git_is_nonfatal(self) -> None:
        root = self.make_repo()
        output = io.StringIO()

        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            with contextlib.redirect_stdout(output):
                result = install.run_diff_check(root, [Path("README.md")])

        self.assertEqual(result, 0)
        self.assertIn("git not found", output.getvalue())

    def test_main_returns_failed_diff_check_status(self) -> None:
        root = self.make_repo()
        output = io.StringIO()

        with mock.patch.object(install, "run_diff_check", return_value=7):
            with contextlib.redirect_stdout(output):
                result = install.main([str(root)])

        self.assertEqual(result, 7)

    def test_adapters_reference_installed_shared_assets(self) -> None:
        _, files = install.load_manifest()
        adapter_files = [file for file in files if file.kind in {"command", "prompt"}]

        self.assertGreater(len(adapter_files), 0)
        for file in adapter_files:
            content = file.source.read_text(encoding="utf-8")
            if "start" in file.target.name:
                self.assertIn(".agents/skills/trellis-start/SKILL.md", content)
                self.assertIn("Follow that skill exactly", content)
            elif "continue" in file.target.name:
                self.assertIn(".agents/skills/trellis-continue/SKILL.md", content)
                self.assertIn("Follow that skill exactly", content)
            elif "finish-work" in file.target.name:
                self.assertIn(".agents/skills/trellis-finish-work/SKILL.md", content)
                self.assertIn("Follow that skill exactly", content)
            elif "full-check" in file.target.name:
                self.assertIn(".agents/skills/sd-full-check/SKILL.md", content)
                self.assertIn("scripts/sd-ai-command-pack-full-check.sh", content)
            elif "housekeeping" in file.target.name:
                self.assertIn(
                    ".agents/skills/sd-housekeeping/SKILL.md",
                    content,
                )
                self.assertIn("scripts/sd-ai-command-pack-housekeeping.sh", content)
            elif "update-spec" in file.target.name:
                self.assertIn(".agents/skills/sd-update-spec/SKILL.md", content)
                self.assertIn("Trellis update-spec first", content)
                self.assertIn(".obsidian-kb", content)
            elif "review-learnings" in file.target.name:
                self.assertIn(".agents/skills/sd-review-learnings/SKILL.md", content)
                self.assertIn("scripts/sd-ai-command-pack-review-learnings.py", content)
            else:
                self.assertIn(".agents/skills/sd-review-pr/SKILL.md", content)

    def test_codex_visible_sd_skill_wrappers_reference_workflows(self) -> None:
        expected = {
            "sd-start": ".agents/skills/trellis-start/SKILL.md",
            "sd-continue": ".agents/skills/trellis-continue/SKILL.md",
            "sd-finish-work": ".agents/skills/trellis-finish-work/SKILL.md",
            "sd-update-spec": "trellis-update-spec/SKILL.md",
        }

        for skill_name, target in expected.items():
            skill_path = (
                install.ROOT / f"templates/.agents/skills/{skill_name}/SKILL.md"
            )
            content = skill_path.read_text(encoding="utf-8")
            self.assertIn(f"name: {skill_name}", content)
            self.assertIn(target, content)

        review_pr = (
            install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-review-pr", review_pr)
        self.assertIn("# SD PR Review Loop", review_pr)
        self.assertIn("standing permission to reply", review_pr)
        self.assertIn("bash scripts/sd-ai-command-pack-full-check.sh", review_pr)

        review_learnings = (
            install.ROOT / "templates/.agents/skills/sd-review-learnings/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-review-learnings", review_learnings)
        self.assertIn("# SD Review Learnings", review_learnings)
        self.assertIn("scripts/sd-ai-command-pack-review-learnings.py", review_learnings)

        full_check = (
            install.ROOT / "templates/.agents/skills/sd-full-check/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-full-check", full_check)
        self.assertIn("# SD Full Check", full_check)
        self.assertIn("bash scripts/sd-ai-command-pack-full-check.sh", full_check)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_GITO", full_check)

        housekeeping = (
            install.ROOT / "templates/.agents/skills/sd-housekeeping/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-housekeeping", housekeeping)
        self.assertIn("# SD Housekeeping", housekeeping)
        self.assertIn("bash scripts/sd-ai-command-pack-housekeeping.sh", housekeeping)
        self.assertIn("Expected clean state", housekeeping)

        update_spec = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("repospec artifact", update_spec)
        self.assertIn("docs/repomix-map.md", update_spec)
        self.assertIn("Architectural overview", update_spec)
        self.assertIn(".obsidian-kb", update_spec)
        self.assertIn("scripts/sd-ai-command-pack-update-spec-kb.py", update_spec)
        self.assertIn("Obsidian vault link", update_spec)

    def test_flat_markdown_entries_are_completion_visible(self) -> None:
        commands = [
            "start",
            "continue",
            "finish-work",
            "review-pr",
            "review-learnings",
            "full-check",
            "housekeeping",
            "update-spec",
        ]

        for command in commands:
            github_path = (
                install.ROOT / f"templates/.github/prompts/sd-{command}.prompt.md"
            )
            github_content = github_path.read_text(encoding="utf-8")
            self.assertTrue(github_content.startswith("---\n"), github_path)
            self.assertIn("description:", github_content)
            self.assertIn("mode: agent", github_content)

            for platform in ("cursor", "opencode"):
                adapter_path = (
                    install.ROOT
                    / f"templates/.{platform}/commands/sd-{command}.md"
                )
                adapter_content = adapter_path.read_text(encoding="utf-8")
                self.assertTrue(adapter_content.startswith("---\n"), adapter_path)
                self.assertIn("description:", adapter_content)

    def test_gemini_entries_use_namespaced_toml_completion_shape(self) -> None:
        expected_descriptions = {
            "start": "Run the Trellis start workflow.",
            "continue": "Run the Trellis continue workflow.",
            "finish-work": "Run the Trellis finish-work workflow.",
            "review-pr": "Run the SD PR review loop.",
            "review-learnings": "Detect and update repo review learnings.",
            "full-check": "Run the SD full-check gate.",
            "housekeeping": "Run SD end-of-stream housekeeping.",
            "update-spec": "Run the SD update-spec workflow.",
        }
        _, files = install.load_manifest()
        gemini_commands = [
            file
            for file in files
            if file.platform == "gemini" and file.kind == "command"
        ]

        self.assertEqual(len(gemini_commands), len(expected_descriptions))
        for file in gemini_commands:
            command_name = file.target.stem
            self.assertIn(command_name, expected_descriptions)
            self.assertEqual(file.target.parent, Path(".gemini/commands/sd"))
            self.assertEqual(
                file.source.parent.relative_to(install.ROOT),
                Path("templates") / file.target.parent,
            )
            self.assertEqual(file.target.suffix, ".toml")
            self.assertFalse(file.target.name.startswith("sd-"), file.target)

            content = file.source.read_text(encoding="utf-8")
            self.assertIn(
                f'description = "{expected_descriptions[command_name]}"',
                content,
            )
            self.assertIn('prompt = """', content)

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
            if file.platform in {"cursor", "opencode"}:
                self.assertEqual(Path(f".{file.platform}/commands"), file.target.parent)
                self.assertTrue(file.source.name.startswith("sd-"), file.source)
                self.assertTrue(file.target.name.startswith("sd-"), file.target)
                self.assertNotIn("/commands/sd/", source)
                self.assertNotIn("/commands/sd/", file.target.as_posix())
            else:
                self.assertIn("/commands/sd/", source)
                self.assertIn("/commands/sd/", file.target.as_posix())
            self.assertNotIn("/commands/trellis/", source)
            self.assertNotIn("/commands/trellis/", file.target.as_posix())
        for file in github_prompt_files:
            self.assertTrue(file.source.name.startswith("sd-"), file.source)
            self.assertTrue(file.target.name.startswith("sd-"), file.target)

        self.assertFalse((install.ROOT / "templates/.claude/commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.cursor/commands/trellis").exists())
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
                    "start",
                    "finish-work",
                    "update-spec",
                    "sd-continue",
                    "sd-start",
                    "sd-finish-work",
                    "sd-update-spec",
                )
            )
        ]

        self.assertGreater(len(protected), 0)
        for file in protected:
            self.assertIsNone(install.legacy_adapter_target(file), file.target)

    def test_update_spec_wrappers_include_repospec_and_architecture_gates(self) -> None:
        shared_skill = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        ).read_text(encoding="utf-8")
        for expected in (
            "trellis-update-spec/SKILL.md",
            ".cursor/skills/trellis-update-spec/SKILL.md",
            "Follow the Trellis update-spec skill exactly",
            "repospec artifact",
            "instead of hand-editing generated output",
            "Repomix",
            "docs/repomix-map.md",
            "no infrastructure",
            "ARCHITECTURE.md",
            "docs/ARCHITECTURE.md",
            ".trellis/spec/**/architecture*.md",
            "Do not create a new overview unless",
            "changes high-level",
            "not present",
            "not warranted",
            ".obsidian-kb",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
            "repo root `.gitignore`",
            "symlinks",
            ".trellis/workflow.md",
            ".trellis/config.yaml",
            ".trellis/spec/**/*.md",
            ".trellis/workspace/",
            "Obsidian KB",
            "Obsidian vault link",
        ):
            self.assertIn(expected, shared_skill)

        adapter_paths = [
            install.ROOT / "templates/.claude/commands/sd/update-spec.md",
            install.ROOT / "templates/.cursor/commands/sd-update-spec.md",
            install.ROOT / "templates/.gemini/commands/sd/update-spec.toml",
            install.ROOT / "templates/.github/prompts/sd-update-spec.prompt.md",
            install.ROOT / "templates/.opencode/commands/sd-update-spec.md",
        ]
        for adapter_path in adapter_paths:
            content = adapter_path.read_text(encoding="utf-8")
            self.assertIn(".agents/skills/sd-update-spec/SKILL.md", content)
            self.assertIn("Trellis update-spec first", content)
            self.assertIn("repospec artifact", content)
            self.assertIn(".obsidian-kb", content)

    def test_update_spec_docs_explain_obsidian_kb_vault_linking(self) -> None:
        doc_paths = [
            install.ROOT / "README.md",
            install.ROOT / "docs/SD_AI_COMMAND_PACK.md",
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md",
        ]

        for doc_path in doc_paths:
            content = doc_path.read_text(encoding="utf-8")
            self.assertIn(".obsidian-kb/", content)
            self.assertIn("scripts/sd-ai-command-pack-update-spec-kb.py", content)
            self.assertIn("ln -s /absolute/path/to/repo/.obsidian-kb", content)
            self.assertIn("New-Item -ItemType SymbolicLink", content)

        gitignore = (install.ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".obsidian-kb/", gitignore)

    def test_full_check_script_writes_gito_reports_to_artifact_dir(self) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR", script)
        self.assertIn(".build/review/gito", script)
        self.assertIn('gito review --vs "$base_ref" --out "$out_dir"', script)

    def test_pack_owned_scripts_use_sd_ai_command_pack_identity(self) -> None:
        raw, files = install.load_manifest()
        manifest_text = json.dumps(raw)
        script_files = [
            file
            for file in files
            if file.platform == "shared" and file.kind == "script"
        ]
        script_targets = {
            file.target.as_posix()
            for file in script_files
        }
        expected_targets = {
            "scripts/sd-ai-command-pack-full-check.sh",
            "scripts/sd-ai-command-pack-housekeeping.sh",
            "scripts/sd-ai-command-pack-review-scope.sh",
            "scripts/sd-ai-command-pack-review-learnings.py",
            "scripts/sd-ai-command-pack-install-audit.py",
            "scripts/sd-ai-command-pack-pr-body-scope.py",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
        }
        script_texts = [
            file.source.read_text(encoding="utf-8")
            for file in script_files
        ]
        full_check = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")
        housekeeping = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        ).read_text(encoding="utf-8")

        self.assertTrue(expected_targets.issubset(script_targets), script_targets)
        self.assertFalse(
            any("scripts/sd-command-pack-" in target for target in script_targets),
            script_targets,
        )
        self.assertNotIn("scripts/trellis-full-check.sh", script_targets)
        self.assertNotIn("scripts/trellis-housekeeping.sh", script_targets)
        audit_script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-install-audit.py"
        ).read_text(encoding="utf-8")
        for content in (manifest_text, *script_texts):
            if content == audit_script:
                continue
            self.assertNotIn("sd-command-pack", content)
            self.assertNotIn("SD_COMMAND_PACK", content)
            self.assertNotIn("sd_command_pack", content)
            self.assertNotIn("trellis-full-check.sh", content)
            self.assertNotIn("trellis-housekeeping.sh", content)
            self.assertNotIn("TRELLIS_FULL_CHECK", content)
            self.assertNotIn("TRELLIS_HOUSEKEEPING", content)
        self.assertIn("SD AI command pack full check", full_check)
        self.assertIn("SD AI command pack housekeeping", housekeeping)

    def test_full_check_script_warns_when_node_cannot_inspect_scripts(self) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")

        node_guard = 'elif ! have node; then'
        script_loop = 'for script_name in $scripts; do'
        self.assertIn(node_guard, script)
        self.assertIn(
            "Node.js not found on PATH; cannot inspect package.json scripts; "
            "skipping package-script checks.",
            script,
        )
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_SCRIPTS", script)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_NPM_SCRIPTS", script)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS", script)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_NPM", script)
        self.assertLess(script.index(node_guard), script.index(script_loop))

    def test_full_check_script_runs_from_repo_root_and_uses_env_script_name(
        self,
    ) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('${BASH_SOURCE[0]}', script)
        self.assertIn('REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"', script)
        self.assertIn('cd "$REPO_ROOT"', script)
        self.assertIn("run_sd_ai_command_pack_scope_check()", script)
        self.assertIn("scripts/sd-ai-command-pack-review-scope.sh", script)
        self.assertIn("run_sd_ai_command_pack_scope_check", script)
        self.assertIn("run_sd_ai_command_pack_pr_body_scope_check()", script)
        self.assertIn("scripts/sd-ai-command-pack-pr-body-scope.py", script)
        self.assertIn("SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK", script)
        self.assertIn("run_sd_ai_command_pack_pr_body_scope_check", script)
        self.assertIn("run_ci_classification_report()", script)
        self.assertIn("scripts/classify-ci-changes.sh", script)
        self.assertIn("scripts/classify_ci_changes.sh", script)
        self.assertIn("CI change classification: current diff", script)
        self.assertIn("sd-ai-command-pack-ci-paths", script)
        self.assertIn("run_review_preflight()", script)
        self.assertIn("scripts/check-review-preflight.mjs", script)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT", script)
        self.assertIn(
            "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND",
            script,
        )
        self.assertIn("run_review_preflight", script)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE", script)
        self.assertIn('SCRIPT_NAME="$script_name" node -e', script)
        self.assertIn("process.env.SCRIPT_NAME", script)
        self.assertNotIn("process.argv[1]", script)

    def test_full_check_script_treats_prism_exit_code_4_as_optional_unless_required(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        script = root / "scripts/sd-ai-command-pack-full-check.sh"
        script.parent.mkdir(parents=True)
        shutil.copyfile(
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            script,
        )
        stub_bin = root / "bin"
        stub_bin.mkdir()
        prism = stub_bin / "prism"
        prism.write_text("#!/usr/bin/env bash\nexit 4\n", encoding="utf-8")
        prism.chmod(0o755)

        def run_fixture(mode: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    self._bash_path,
                    "-c",
                    "source scripts/sd-ai-command-pack-full-check.sh; "
                    "run_prism_command 'Prism fixture' review staged",
                ],
                cwd=root,
                env={
                    **os.environ,
                    "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                    "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": mode,
                    "SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE": "1",
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        optional = run_fixture("auto")
        self.assertEqual(optional.returncode, 0, optional.stdout)
        self.assertIn(
            "Prism provider/model configuration failed with exit code 4",
            optional.stdout,
        )

        required = run_fixture("required")
        self.assertEqual(required.returncode, 4, required.stdout)
        self.assertIn(
            "Prism is required but provider/model configuration failed with exit code 4",
            required.stdout,
        )

    def test_full_check_script_reports_current_diff_ci_classification_when_available(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        classifier = root / "scripts/classify-ci-changes.sh"
        classifier.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = \"--\" ]; then shift; fi\n"
            "count=\"$#\"\n"
            "printf 'docs_only=false\\n'\n"
            "printf 'app_required=true\\n'\n"
            "printf 'expensive_required=false\\n'\n"
            "printf 'fixture_count=%s\\n' \"$count\"\n",
            encoding="utf-8",
        )
        classifier.chmod(0o755)
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs/local.md").write_text("local change\n", encoding="utf-8")

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_NPM": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("CI change classification: current diff", result.stdout)
        self.assertIn("changed_paths=", result.stdout)
        self.assertIn("docs_only=false", result.stdout)
        self.assertIn("app_required=true", result.stdout)
        self.assertIn("fixture_count=", result.stdout)

    def test_full_check_script_preserves_legacy_ci_classifier_file_contract(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        classifier = root / "scripts/classify_ci_changes.sh"
        classifier.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = \"--\" ]; then\n"
            "  printf 'legacy classifier received argv mode\\n' >&2\n"
            "  exit 9\n"
            "fi\n"
            "input=\"${1:-}\"\n"
            "if [ ! -f \"$input\" ]; then\n"
            "  printf 'legacy classifier expected a file path\\n' >&2\n"
            "  exit 8\n"
            "fi\n"
            "count=\"$(grep -c . \"$input\" || true)\"\n"
            "printf 'docs_only=false\\n'\n"
            "printf 'fixture_count=%s\\n' \"$count\"\n",
            encoding="utf-8",
        )
        classifier.chmod(0o755)
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs/local.md").write_text("local change\n", encoding="utf-8")

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_NPM": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("CI change classification: current diff", result.stdout)
        self.assertIn("docs_only=false", result.stdout)
        self.assertIn("fixture_count=", result.stdout)

    def test_full_check_script_runs_repo_local_review_preflight_when_available(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        if shutil.which("node") is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        preflight = root / "scripts/check-review-preflight.mjs"
        preflight.write_text(
            "import { writeFileSync } from 'node:fs';\n"
            "writeFileSync('preflight-ran.txt', 'yes\\n');\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_NPM": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Review preflight", result.stdout)
        self.assertEqual(
            (root / "preflight-ran.txt").read_text(encoding="utf-8"),
            "yes\n",
        )

    def test_full_check_script_runs_configured_review_preflight_command(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND": (
                    "printf 'yes\\n' > preflight-ran.txt"
                ),
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Review preflight", result.stdout)
        self.assertEqual(
            (root / "preflight-ran.txt").read_text(encoding="utf-8"),
            "yes\n",
        )

    def test_full_check_script_fails_required_review_preflight_when_missing(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT": "required",
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_NPM": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 127, result.stdout)
        self.assertIn(
            "Review preflight is required but no command is configured and "
            "scripts/check-review-preflight.mjs is missing",
            result.stdout,
        )

    def test_full_check_script_runs_install_audit(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("SD AI command pack install audit", result.stdout)
        self.assertIn("install audit passed", result.stdout)

    def test_install_audit_detects_missing_and_obsolete_artifacts(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        (root / ".agents/skills/sd-review-pr/SKILL.md").unlink()
        obsolete = root / "scripts/trellis-full-check.sh"
        obsolete.write_text("# obsolete\n", encoding="utf-8")
        obsolete_review_learnings = root / "scripts/sd-review-learnings.py"
        obsolete_review_learnings.write_text("# obsolete\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
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
        self.assertIn(
            "obsolete pack artifact still exists: scripts/trellis-full-check.sh",
            result.stdout,
        )
        self.assertIn(
            "obsolete pack artifact still exists: scripts/sd-review-learnings.py",
            result.stdout,
        )

    def test_install_audit_warns_or_fails_for_stale_repo_map_refs(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        (root / "docs/repomix-map.md").write_text(
            "old docs mention scripts/trellis-full-check.sh\n",
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
        self.assertIn("warning: docs/repomix-map.md mentions obsolete pack names", result.stdout)
        self.assertIn("install audit passed", result.stdout)

        strict_result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-install-audit.py",
                "--strict-references",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(strict_result.returncode, 1, strict_result.stdout)
        self.assertIn(
            "error: docs/repomix-map.md mentions obsolete pack names",
            strict_result.stdout,
        )

    def run_source_audit(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
                "--repo",
                str(root),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

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

    def test_shared_script_templates_are_syntax_valid(self) -> None:
        script_files = self.shared_manifest_files("script")

        self.assertGreater(len(script_files), 0)
        for file in script_files:
            if file.source.suffix == ".sh":
                self.assert_shell_syntax_valid(file.source)
            elif file.source.suffix == ".py":
                self.assert_python_syntax_valid(file.source)
            else:
                self.fail(f"unexpected script template suffix: {file.source}")
            self.assert_no_secret_markers(file.source)

    def test_review_learnings_script_detects_local_patterns(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        tool = root / "scripts/tool.sh"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nscratch=\"$(mktemp)\"\n",
            encoding="utf-8",
        )
        diff = root / "diff.patch"
        diff.write_text(
            "diff --git a/scripts/tool.sh b/scripts/tool.sh\n"
            "new file mode 100755\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/scripts/tool.sh\n"
            "@@ -0,0 +1,3 @@\n"
            "+#!/usr/bin/env bash\n"
            "+set -euo pipefail\n"
            "+scratch=\"$(mktemp)\"\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("[sd-review-learnings:portability]", result.stdout)
        self.assertIn("mktemp", result.stdout)

    def test_review_learnings_script_detects_positional_negative_offset(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        tool = root / "scripts/tool.sh"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nlast=\"${@: -1}\"\n",
            encoding="utf-8",
        )
        diff = root / "diff.patch"
        diff.write_text(
            "diff --git a/scripts/tool.sh b/scripts/tool.sh\n"
            "new file mode 100755\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/scripts/tool.sh\n"
            "@@ -0,0 +1,3 @@\n"
            "+#!/usr/bin/env bash\n"
            "+set -euo pipefail\n"
            "+last=\"${@: -1}\"\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("[sd-review-learnings:portability]", result.stdout)
        self.assertIn("negative array offsets", result.stdout)

    def test_review_learnings_script_allows_shell_default_expansions(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        tool = root / "scripts/tool.sh"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nmode=\"${TOOL_MODE:-0}\"\n",
            encoding="utf-8",
        )
        diff = root / "diff.patch"
        diff.write_text(
            "diff --git a/scripts/tool.sh b/scripts/tool.sh\n"
            "new file mode 100755\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/scripts/tool.sh\n"
            "@@ -0,0 +1,3 @@\n"
            "+#!/usr/bin/env bash\n"
            "+set -euo pipefail\n"
            "+mode=\"${TOOL_MODE:-0}\"\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("no local review-cycle findings detected", result.stdout)

    def test_review_learnings_script_updates_managed_block(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        target = root / "docs/review-learnings.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Review Learnings\n\nHuman notes stay.\n", encoding="utf-8")
        diff = root / "diff.patch"
        diff.write_text("", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
                "--update",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        content = target.read_text(encoding="utf-8")
        self.assertIn("Human notes stay.", content)
        self.assertIn("<!-- sd-review-learnings:start -->", content)
        self.assertIn("No local review-cycle findings detected", content)

    def test_review_learnings_script_resolves_github_repo_generically(self) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        ).read_text(encoding="utf-8")

        self.assertIn("gh", script)
        self.assertIn("repo", script)
        self.assertIn("nameWithOwner", script)
        self.assertNotIn("answerbook", script)
        self.assertNotIn("mezmo_benchmark", script)

    def test_update_spec_kb_script_builds_gitignored_symlink_folder(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        files = {
            "README.md": "# Project\n",
            "AGENTS.md": "# Agent Notes\n",
            "docs/repomix-map.md": "# Repo Map\n",
            "docs/architecture.md": "# Architecture\n",
            ".trellis/workflow.md": "# Workflow\n",
            ".trellis/config.yaml": "project: test\n",
            ".trellis/spec/backend/index.md": "# Backend Spec\n",
            "package.json": "{}\n",
            "packages/api/README.md": "# API Package\n",
            "src/main.py": "print('runtime')\n",
            ".trellis/workspace/sdelmas/journal.md": "# private journal\n",
            "node_modules/pkg/README.md": "# dependency docs\n",
        }
        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (root / ".gitignore").write_text("dist/\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Obsidian KB: .obsidian-kb", result.stdout)
        self.assertIn("gitignore: added", result.stdout)
        self.assertIn("vault link example:", result.stdout)

        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("dist/\n", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb start", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb end", gitignore)
        self.assertEqual(gitignore.count(".obsidian-kb/"), 1)
        for relative_path in (
            "README.md",
            "AGENTS.md",
            "docs/repomix-map.md",
            "docs/architecture.md",
            ".trellis/workflow.md",
            ".trellis/config.yaml",
            ".trellis/spec/backend/index.md",
            "package.json",
            "packages/api/README.md",
        ):
            link = root / ".obsidian-kb" / relative_path
            self.assertTrue(link.is_symlink(), link)
            self.assertEqual(link.resolve(), (root / relative_path).resolve())

        self.assertFalse((root / ".obsidian-kb/src/main.py").exists())
        self.assertFalse(
            (root / ".obsidian-kb/.trellis/workspace/sdelmas/journal.md").exists()
        )
        self.assertFalse((root / ".obsidian-kb/node_modules/pkg/README.md").exists())

        (root / "docs/repomix-map.md").unlink()
        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: present", result.stdout)
        self.assertIn("stale symlinks removed: 1", result.stdout)
        self.assertFalse((root / ".obsidian-kb/docs/repomix-map.md").exists())
        self.assertEqual(
            (root / ".gitignore").read_text(encoding="utf-8").count(".obsidian-kb/"),
            1,
        )

    def test_update_spec_kb_uses_local_exclude_for_local_only_install(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        marker = root / install.LOCAL_ONLY_MARKER_FILE
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("local only\n", encoding="utf-8")
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".gitignore").write_text("dist/\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: local-exclude added", result.stdout)
        self.assertEqual((root / ".gitignore").read_text(encoding="utf-8"), "dist/\n")
        exclude = Path(self.git_output(root, "rev-parse", "--git-path", "info/exclude"))
        if not exclude.is_absolute():
            exclude = root / exclude
        exclude_text = exclude.read_text(encoding="utf-8")
        self.assertIn("# sd-ai-command-pack obsidian-kb start", exclude_text)
        self.assertIn("# sd-ai-command-pack obsidian-kb end", exclude_text)
        self.assertIn(".obsidian-kb/", exclude_text)
        self.assertTrue((root / ".obsidian-kb/README.md").is_symlink())

    def test_update_spec_kb_upgrades_unmarked_gitignore_entry(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".gitignore").write_text(
            "dist/\n.obsidian-kb/\nlogs/\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: updated", result.stdout)
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("dist/\n", gitignore)
        self.assertIn("logs/\n", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb start", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb end", gitignore)
        self.assertEqual(gitignore.count(".obsidian-kb/"), 1)

    def test_update_spec_kb_preserves_invalid_existing_gitignore_bytes(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".gitignore").write_bytes(b"dist-\xff/\n.obsidian-kb/\n")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: updated", result.stdout)
        gitignore = (root / ".gitignore").read_bytes()
        self.assertIn(b"dist-\xff/\n", gitignore)
        self.assertIn(b"# sd-ai-command-pack obsidian-kb start\n", gitignore)

    def test_pr_body_scope_script_warns_without_body(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        changed_files = root / "changed-files.txt"
        changed_files.write_text(
            ".cursor/commands/sd-housekeeping.md\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "--changed-files",
                str(changed_files),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("detected Automation scope", result.stdout)
        self.assertIn("PR body not provided", result.stdout)

    def test_pr_body_scope_script_enforces_configured_runtime_scope(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        config = root / ".sd-ai-command-pack/pr-body-scope.json"
        config.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "label": "Runtime/server scope",
                            "headings": [
                                "Runtime/server scope:",
                                "Runtime scope:",
                            ],
                            "patterns": ["src/**"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        changed_files = root / "changed-files.txt"
        changed_files.write_text("src/service.py\n", encoding="utf-8")

        missing = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "--changed-files",
                str(changed_files),
            ],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY": "Summary only.",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(missing.returncode, 1, missing.stdout)
        self.assertIn("missing Runtime/server scope", missing.stdout)

        covered = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "--changed-files",
                str(changed_files),
            ],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY": (
                    "Runtime/server scope: updates service behavior."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(covered.returncode, 0, covered.stdout)
        self.assertIn("PR body scope sections cover", covered.stdout)

    def test_pr_body_scope_script_reports_malformed_config_without_traceback(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        config = root / ".sd-ai-command-pack/pr-body-scope.json"
        config.write_text('{"rules": [', encoding="utf-8")
        changed_files = root / "changed-files.txt"
        changed_files.write_text("src/service.py\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "--changed-files",
                str(changed_files),
            ],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY": (
                    "Runtime/server scope: updates service behavior."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("cannot parse PR body scope config", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_full_check_script_runs_pack_pr_body_scope_check(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        housekeeping = root / "scripts/sd-ai-command-pack-housekeeping.sh"
        housekeeping.write_text(
            housekeeping.read_text(encoding="utf-8") + "\n# local note\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_NPM": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("SD AI command pack PR-body scope check", result.stdout)
        self.assertIn("detected Automation scope", result.stdout)

    def test_review_scope_script_reports_manifest_driven_pack_changes(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )
        installed_targets = root / install.INSTALLED_TARGETS_FILE
        installed_targets.write_text(
            installed_targets.read_text(encoding="utf-8")
            + "# local note\n",
            encoding="utf-8",
        )
        (root / "docs/repomix-map.md").write_text(
            "# local map\n",
            encoding="utf-8",
        )
        cursor_command = root / ".cursor/commands/trellis-continue.md"
        cursor_command.parent.mkdir(parents=True)
        cursor_command.write_text(
            "# Trellis Continue\n",
            encoding="utf-8",
        )
        workspace_dir = root / ".trellis/workspace/sdelmas"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "journal-1.md").write_text(
            "## Session 1: Test\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "Tooling/generated review-scope files changed",
            result.stdout,
        )
        self.assertIn("Scope categories:", result.stdout)
        self.assertIn("copied/generated Trellis or sd-ai-command-pack files", result.stdout)
        self.assertIn("known repository-map files", result.stdout)
        self.assertIn("Trellis workspace journal/index files", result.stdout)
        self.assertIn("docs/SD_AI_COMMAND_PACK.md", result.stdout)
        self.assertIn(".cursor/commands/trellis-continue.md", result.stdout)
        self.assertIn("docs/repomix-map.md", result.stdout)
        self.assertIn(".trellis/workspace/sdelmas/journal-1.md", result.stdout)
        self.assertIn(".sd-ai-command-pack/installed-targets.txt", result.stdout)

    def test_review_scope_script_requires_pr_body_scope_when_configured(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        stub_bin = root.parent / f"{root.name}-bin"
        stub_bin.mkdir()
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            "  printf '%s\\n' "
            "'{\"title\":\"Product fix\",\"body\":\"Updates behavior.\",\"url\":\"https://example.test/pr/1\"}'\n"
            "else\n"
            "  printf 'unexpected gh invocation: %s\\n' \"$*\" >&2\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)

        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "does not include a Tooling/generated scope: section",
            result.stdout,
        )

    def test_review_scope_script_accepts_explicit_pr_body_scope_section(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        stub_bin = root.parent / f"{root.name}-bin"
        stub_bin.mkdir()
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            "  printf '%s\\n' "
            "'{\"title\":\"Product fix\",\"body\":\"Tooling/generated scope: command-pack refresh.\",\"url\":\"https://example.test/pr/1\"}'\n"
            "else\n"
            "  printf 'unexpected gh invocation: %s\\n' \"$*\" >&2\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)

        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Tooling/generated review-scope files changed", result.stdout)

    def test_review_scope_script_accepts_scope_section_from_explicit_body_env(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": os.defpath,
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
                "SD_AI_COMMAND_PACK_SCOPE_PR_BODY": (
                    "Tooling/generated scope: command-pack refresh."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Tooling/generated review-scope files changed", result.stdout)

    def test_review_scope_script_rejects_invalid_explicit_body_env(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": os.defpath,
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
                "REVIEW_PREFLIGHT_PR_BODY": "Updates behavior.",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "provided PR body does not include a Tooling/generated scope: section",
            result.stdout,
        )

    def test_prism_rules_template_has_valid_shape(self) -> None:
        prism_rules_files = [
            file
            for file in self.shared_manifest_files("config")
            if file.target == Path(".prism/rules.json")
        ]

        self.assertEqual(
            len(prism_rules_files),
            1,
            "manifest must contain exactly one shared .prism/rules.json config",
        )
        self.assert_prism_rules_valid(prism_rules_files[0].source)
        self.assert_no_secret_markers(prism_rules_files[0].source)

    def test_review_pr_skill_allows_reply_and_resolve_for_addressed_threads(self) -> None:
        skill = (
            install.ROOT
            / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("standing permission to reply", skill)
        self.assertIn("review threads during this loop", skill)
        self.assertIn("fixed, rebutted with evidence", skill)
        self.assertIn("confirmed already addressed", skill)
        self.assertIn("Do not resolve valid unaddressed or ambiguous threads", skill)

    def test_review_pr_remote_reviewer_is_configurable(self) -> None:
        skill_paths = [
            install.ROOT / ".agents/skills/sd-review-pr/SKILL.md",
            install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md",
        ]
        adapter_paths = [
            install.ROOT / ".claude/commands/sd/review-pr.md",
            install.ROOT / ".gemini/commands/sd/review-pr.toml",
            install.ROOT / ".github/prompts/sd-review-pr.prompt.md",
            install.ROOT / ".opencode/commands/sd-review-pr.md",
            install.ROOT / "templates/.claude/commands/sd/review-pr.md",
            install.ROOT / "templates/.cursor/commands/sd-review-pr.md",
            install.ROOT / "templates/.gemini/commands/sd/review-pr.toml",
            install.ROOT / "templates/.github/prompts/sd-review-pr.prompt.md",
            install.ROOT / "templates/.opencode/commands/sd-review-pr.md",
        ]
        doc_paths = [
            install.ROOT / "README.md",
            install.ROOT / "docs/SD_AI_COMMAND_PACK.md",
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md",
        ]

        for skill_path in skill_paths:
            skill = skill_path.read_text(encoding="utf-8")
            self.assertIn("configured remote reviewer", skill)
            self.assertIn(
                'REMOTE_REVIEWER="${SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER:-copilot-pull-request-reviewer}"',
                skill,
            )
            self.assertIn(
                'REMOTE_REVIEWER_LABEL="${SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER_LABEL:-GitHub Copilot}"',
                skill,
            )
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_AUTHOR_MATCH", skill)
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND", skill)
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT", skill)
            self.assertIn('-f reviewers[]="$REMOTE_REVIEWER"', skill)
            self.assertIn(
                'gh pr edit "$PR_NUMBER" --add-reviewer "$REMOTE_REVIEWER"',
                skill,
            )
            self.assertNotIn("-f reviewers[]=copilot-pull-request-reviewer", skill)
            self.assertNotIn(
                "gh pr edit \"$PR_NUMBER\" --add-reviewer copilot-pull-request-reviewer",
                skill,
            )

        for adapter_path in adapter_paths:
            adapter = adapter_path.read_text(encoding="utf-8")
            self.assertIn("configured remote reviewer", adapter)
            self.assertIn("configured remote review round limit", adapter)

        for doc_path in doc_paths:
            doc = doc_path.read_text(encoding="utf-8")
            self.assertIn("The default remote reviewer", doc)
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER", doc)

    def test_review_pr_skill_auto_dispatches_housekeeping_after_merge(self) -> None:
        skill = (
            install.ROOT
            / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")
        adapter_paths = [
            install.ROOT / "templates/.claude/commands/sd/review-pr.md",
            install.ROOT / "templates/.cursor/commands/sd-review-pr.md",
            install.ROOT / "templates/.gemini/commands/sd/review-pr.toml",
            install.ROOT / "templates/.github/prompts/sd-review-pr.prompt.md",
            install.ROOT / "templates/.opencode/commands/sd-review-pr.md",
        ]

        self.assertIn("Post-Merge Auto-Dispatch", skill)
        self.assertIn('PR_STATE" = "MERGED"', skill)
        self.assertIn("bash scripts/sd-ai-command-pack-housekeeping.sh", skill)
        self.assertIn("not a background GitHub webhook", skill)
        for adapter_path in adapter_paths:
            content = adapter_path.read_text(encoding="utf-8")
            self.assertIn("becomes merged during the active session", content)
            self.assertIn("housekeeping auto-dispatch", content)

    def test_housekeeping_skill_and_script_describe_expected_clean_state(self) -> None:
        skill = (
            install.ROOT
            / "templates/.agents/skills/sd-housekeeping/SKILL.md"
        ).read_text(encoding="utf-8")
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        ).read_text(encoding="utf-8")
        result = subprocess.run(
            [
                "bash",
                "-n",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
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
            "SD finish-work flow",
            ".agents/skills/sd-finish-work/SKILL.md",
            "--no-auto-merge",
        ]:
            self.assertIn(text, skill)
        for text in [
            "Expected clean state",
            "Anomalies",
            "open PRs: none",
            "Trellis active tasks: none",
            "--no-auto-merge",
            "--merge-strategy",
            "view_open_pr_readiness_for_branch()",
            "unresolved_review_thread_count()",
            "PR #$pr_number is open, green, comment-clean",
            "merge_ready_open_pr()",
            "failed to merge PR #$pr_number; resolve branch protection",
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
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
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
            ["bash", str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
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

    def test_housekeeping_auto_merges_green_comment_clean_pr_then_cleans_up(
        self,
    ) -> None:
        repo, remote, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
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
        self.assertIn("merged PR #6 with merge strategy", result.stdout)
        self.assertIn("deleted local branch feature/cleanup", result.stdout)
        self.assertIn("deleted remote branch origin/feature/cleanup", result.stdout)
        self.assertIn("==> Anomalies\nnone", result.stdout)
        self.assertEqual(self.git_output(repo, "branch", "--show-current"), "main")
        remote_branch = subprocess.run(
            [
                "git",
                "ls-remote",
                "--exit-code",
                str(remote),
                "refs/heads/feature/cleanup",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(remote_branch.returncode, 2, remote_branch.stdout)

    def test_housekeeping_no_auto_merge_leaves_open_pr_untouched(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                "--no-auto-merge",
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 for feature/cleanup is OPEN, not MERGED; left the branch untouched",
            result.stdout,
        )
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
        self.assertFalse(marker.exists())
        self.assertEqual(
            self.git_output(repo, "branch", "--show-current"),
            "feature/cleanup",
        )

    def test_housekeeping_counts_unresolved_review_threads_across_pages(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(
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

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 has 1 unresolved review thread(s); skipped auto-merge",
            result.stdout,
        )
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
        self.assertFalse(marker.exists())
        self.assertEqual(
            self.git_output(repo, "branch", "--show-current"),
            "feature/cleanup",
        )

    def test_housekeeping_rejects_invalid_github_repo_override(self) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO must be an owner/repo slug",
            result.stdout,
        )
        self.assertIn(
            "could not derive GitHub repo from origin; skipped auto-merge",
            result.stdout,
        )
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
        self.assertFalse(marker.exists())

    def test_housekeeping_rejects_invalid_env_merge_strategy_before_merge(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_MERGE_STRATEGY": "fast-forward",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "merge strategy is invalid; expected merge, squash, or rebase; skipped auto-merge",
            result.stdout,
        )
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
        self.assertFalse((repo / ".trellis/workspace/sdelmas/journal-1.md").exists())
        self.assertFalse(marker.exists())

    def test_housekeeping_reports_review_thread_inspection_failure(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(
            stub_bin,
            marker,
            graphql_body="  exit 42\n",
        )

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "failed to inspect review threads for PR #6; skipped auto-merge",
            result.stdout,
        )
        self.assertIn("==> Expected clean state", result.stdout)
        self.assertIn("==> Anomalies", result.stdout)
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
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
