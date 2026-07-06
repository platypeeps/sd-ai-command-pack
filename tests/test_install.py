from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
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
SECRET_MARKER_PATTERNS = (
    re.compile(re.escape("AKIA")),
    re.compile(re.escape("BEGIN PRIVATE KEY")),
    re.compile(re.escape("xoxb-")),
    re.compile(re.escape("ghp_")),
    re.compile(re.escape("gho_")),
    re.compile(r"(?m)(^|[\s'\"=(:])/(?:Users|home)/[^/\s]+/"),
    re.compile(r"(?i)(^|[\s'\"=(:])[A-Z]:\\Users\\[^\\\s]+\\"),
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

    def write_gito_pack_env(self, root: Path, text: str = "MAX_CONCURRENT_TASKS=4\r\n") -> None:
        env_path = root / ".gito/sd-ai-command-pack.env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_bytes(text.encode("utf-8"))

    def _run_git_process(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def run_git(self, root: Path, *args: str) -> None:
        result = self._run_git_process(root, *args)
        self.assertEqual(result.returncode, 0, result.stdout)

    def git_output(self, root: Path, *args: str) -> str:
        result = self._run_git_process(root, *args)
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout.strip()

    def load_module_from_path(self, module_path: Path, module_name: str):
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)
        return module

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
            install.installed_targets_content(
                selected,
                extra_targets=[
                    install.TRELLIS_GITIGNORE_TARGET,
                    install.PROVENANCE_FILE,
                ],
            ),
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

    def assert_node_syntax_valid(self, script: Path) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        result = subprocess.run(
            [node, "--check", str(script)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{script}: {result.stdout}")

    def assert_prism_rules_valid(self, rules_path: Path) -> None:
        rules = json.loads(rules_path.read_text(encoding="utf-8"))

        self.assertIsInstance(rules, dict, f"{rules_path}: root must be an object")
        required_rule_keys = {"focus", "severityOverrides", "required"}
        optional_rule_keys = {"$schema", "description"}
        self.assertEqual(
            set(rules) - required_rule_keys - optional_rule_keys,
            set(),
            f"{rules_path}: unexpected Prism rules keys",
        )
        self.assertTrue(
            required_rule_keys.issubset(rules),
            f"{rules_path}: missing required Prism rules keys",
        )
        if "$schema" in rules:
            self.assertIsInstance(rules["$schema"], str)
            self.assertTrue(rules["$schema"])
        if "description" in rules:
            self.assertIsInstance(rules["description"], str)
            self.assertTrue(rules["description"])

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
        for expected in ("bug", "performance"):
            self.assertIn(expected, focus, f"{rules_path}: focus must include {expected}")

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
        self.assertTrue(
            set(focus).issubset(severity_overrides),
            f"{rules_path}: every focus category must have a severity override",
        )
        self.assertEqual(severity_overrides.get("bug"), "high")
        self.assertEqual(severity_overrides.get("performance"), "medium")

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
        for pattern in SECRET_MARKER_PATTERNS:
            self.assertIsNone(
                pattern.search(content),
                f"{file_path}: contains blocked secret marker pattern {pattern.pattern!r}",
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
            "Trellis is the repository workflow foundation",
            "Software Delivery command wrappers",
            # Vendored-payload guidance with collapsed glob families.
            "payloads as vendored files",
            "narrow-globs: skip - cross-platform generated payload families",
            ".trellis/scripts/**",
            ".trellis/agents/**",
            "**/skills/trellis-*/**",
            "**/skills/sd-*/**",
            ".agent/",
            ".codebuddy/",
            ".factory/",
            ".reasonix/",
            ".zcode/commands/",
            "`continue.prompt.md` and `finish-work.prompt.md`",
            ".github/copilot/**",
            ".github/hooks/trellis.json",
            ".github/agents/trellis-*",
            ".zcode/agents/",
            "scripts/sd-ai-command-pack-*",
            "legacy `scripts/trellis-*.sh`",
            "scripts/update_repomix*",
            ".gito/**",
            ".prism/**",
            ".sd-ai-command-pack/**",
            "docs/SD_AI_COMMAND_PACK.md",
            "legacy `docs/TRELLIS_REVIEW_PR_PACK.md`",
            "Original Trellis-owned runtime/template copies",
            "not valid modification",
            "should not be reviewed",
            "ownership/scope",
            "This does not apply to repo-owned `.trellis/spec/**`",
            "Handoff for sd-ai-command-pack source session",
            "which should not be edited in the consumer repo copy",
            "pack-owned guard",
            "upstream Trellis change",
            # Review-budget and escalation guidance.
            "app behavior",
            "data contracts",
            "repo-owned scripts",
            "data/access/security boundaries",
            "fail-closed behavior",
            "leaks a secret",
            "Tooling/generated scope",
            "Automation scope",
            "CI/review scope",
            ".sd-ai-command-pack/pr-body-scope.json",
            "Group duplicate root causes into one comment",
            "deterministic local checks",
            # Phrases the review-learnings scanner requires
            # (RECOMMENDED_COPILOT_PHRASES).
            "current, non-outdated unresolved",
            "stale or outdated review threads",
            "copied or generated",
        ):
            self.assertIn(expected, content)

        copied_scripts = [
            file.target.as_posix()
            for file in self._manifest_files
            if file.kind == "script"
            and file.target.as_posix().startswith("scripts/sd-ai-command-pack-")
        ]
        self.assertGreater(len(copied_scripts), 0)
        self.assertIn("scripts/sd-ai-command-pack-*", content)

    def assert_trellis_gitignore_block(self, content: str) -> None:
        self.assertIn(install.TRELLIS_GITIGNORE_START, content)
        self.assertIn(install.TRELLIS_GITIGNORE_END, content)
        self.assertIn("DO NOT EDIT MANUALLY", content)
        self.assertIn("# Common local secrets and environment files.", content)
        for expected in install.LOCAL_ENV_GITIGNORE_PATTERNS:
            self.assertIn(expected, content)
        for expected in install.TRELLIS_GITIGNORE_PATTERNS:
            self.assertIn(expected, content)
        for expected in install.REVIEW_ARTIFACT_GITIGNORE_PATTERNS:
            self.assertIn(expected, content)
        for expected in install.PLATFORM_LOCAL_GITIGNORE_PATTERNS:
            self.assertIn(expected, content)
        self.assertNotIn(".trellis/", content.splitlines())
        self.assertNotIn(".trellis", content.splitlines())
        for platform_dir in (
            ".agent/",
            ".agents/",
            ".claude/",
            ".codebuddy/",
            ".codex/",
            ".cursor/",
            ".devin/",
            ".factory/",
            ".gemini/",
            ".github/",
            ".kiro/",
            ".kilocode/",
            ".opencode/",
            ".pi/",
            ".qoder/",
            ".reasonix/",
            ".trae/",
            ".zcode/",
        ):
            self.assertNotIn(platform_dir, content.splitlines())

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
        blocking_check_count: str = "0",
        successful_check_count: str = "2",
        rollup_json: str | None = None,
    ) -> None:
        if rollup_json is None:
            readiness_branch = (
                "    printf '6\\t%s\\tfalse\\thttps://example.test/pr/6\\tfeature/cleanup\\t%s\\tmain\\tCLEAN\\t%s\\t%s\\n' "
                f"\"$state\" \"$head\" {blocking_check_count!r} {successful_check_count!r}\n"
            )
        else:
            # Evaluate the script's real --jq program with real jq against a
            # fixture PR payload so the check-classification logic itself is
            # exercised instead of canned TSV counts.
            readiness_branch = (
                "    prog=''\n"
                "    prev=''\n"
                "    for a in \"$@\"; do\n"
                "      if [ \"$prev\" = '--jq' ]; then prog=\"$a\"; fi\n"
                "      prev=\"$a\"\n"
                "    done\n"
                "    jq -r \"$prog\" <<FIXTURE\n"
                "{\"number\": 6, \"state\": \"$state\", \"isDraft\": false,"
                " \"url\": \"https://example.test/pr/6\","
                " \"headRefName\": \"feature/cleanup\", \"headRefOid\": \"$head\","
                " \"baseRefName\": \"main\", \"mergeStateStatus\": \"CLEAN\","
                f" \"statusCheckRollup\": {rollup_json}}}\n"
                "FIXTURE\n"
            )
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
            + readiness_branch +
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

    def test_install_adds_trellis_gitignore_block(self) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        gitignore.write_text("dist/\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = gitignore.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("dist/\n"))
        self.assert_trellis_gitignore_block(content)
        self.assertIn("updated", result.stdout)
        self.assertIn(".gitignore", result.stdout)

    def test_install_replaces_managed_trellis_gitignore_block(self) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        gitignore.write_text(
            "dist/\n\n"
            f"{install.TRELLIS_GITIGNORE_START}\n"
            "stale trellis ignore rule\n"
            f"{install.TRELLIS_GITIGNORE_END}\n\n"
            "logs/\n",
            encoding="utf-8",
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = gitignore.read_text(encoding="utf-8")
        self.assertIn("dist/\n", content)
        self.assertIn("logs/\n", content)
        self.assertNotIn("stale trellis ignore rule", content)
        self.assertEqual(content.count(install.TRELLIS_GITIGNORE_START), 1)
        self.assertEqual(content.count(install.TRELLIS_GITIGNORE_END), 1)
        self.assert_trellis_gitignore_block(content)

    def test_install_replaces_blanket_trellis_gitignore_entry(self) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        gitignore.write_text("dist/\n.trellis/\nlogs/\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = gitignore.read_text(encoding="utf-8")
        self.assertIn("dist/\n", content)
        self.assertIn("logs/\n", content)
        self.assert_trellis_gitignore_block(content)

    def test_trellis_gitignore_dry_run_does_not_write_file(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("created", result.stdout)
        self.assertIn(".gitignore", result.stdout)
        self.assertFalse((root / ".gitignore").exists())

    def test_trellis_gitignore_rejects_incomplete_marker_block(self) -> None:
        with self.assertRaisesRegex(SystemExit, "incomplete"):
            install.merge_trellis_gitignore_block(
                f"{install.TRELLIS_GITIGNORE_START}\nold\n"
            )

    def test_trellis_gitignore_inserts_after_no_newline_prefix(self) -> None:
        merged = install.merge_trellis_gitignore_block("dist/")

        self.assertTrue(merged.startswith("dist/\n\n"))
        self.assert_trellis_gitignore_block(merged)

    def test_trellis_gitignore_blanket_removal_preserves_blank_only_content(self) -> None:
        self.assertEqual(
            install.remove_unmanaged_trellis_blanket_entries("\n\n"),
            ("\n\n", False),
        )
        self.assertEqual(
            install.remove_unmanaged_trellis_blanket_entries("dist/\n\n.trellis/\n\nlogs/\n"),
            ("dist/\n\n\nlogs/\n", True),
        )

    def test_trellis_gitignore_rejects_existing_directory_target(self) -> None:
        root = self.make_repo()
        (root / ".gitignore").mkdir()

        with self.assertRaisesRegex(SystemExit, "target exists and is not a file"):
            install.install_trellis_gitignore(root, dry_run=False)

    def test_installs_shared_skill_and_existing_platform_adapters(self) -> None:
        root = self.make_repo(".cursor", ".gemini", ".github")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-continue/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-start/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-finish-work/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-learnings/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local-all/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-update-spec/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-housekeeping.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-scope.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-preflight.mjs").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-local.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-learnings.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-install-audit.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-pr-body-scope.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-update-spec-kb.py").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / ".prism/rules.schema.json").is_file())
        self.assertTrue((root / ".gito/config.toml").is_file())
        self.assertTrue((root / ".gito/sd-ai-command-pack.env").is_file())
        self.assertIn(
            "MAX_CONCURRENT_TASKS=4",
            (root / ".gito/sd-ai-command-pack.env").read_text(encoding="utf-8"),
        )
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_trellis_gitignore_block(
            (root / ".gitignore").read_text(encoding="utf-8")
        )
        self.assert_installed_targets_snapshot_matches_selection(root)
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/start.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/create-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local-all.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-learnings.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-continue.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-start.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-finish-work.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-create-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-local.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-local-all.prompt.md").is_file())
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
        self.assertTrue((root / ".cursor/commands/sd-create-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-local.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-local-all.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-learnings.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-full-check.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-housekeeping.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-update-spec.md").is_file())
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".claude/commands/sd/start.md").exists())
        self.assertFalse((root / ".claude/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".claude/commands/sd/create-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-local.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-local-all.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-learnings.md").exists())
        self.assertFalse((root / ".claude/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".claude/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".claude/commands/sd/update-spec.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-continue.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-start.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-finish-work.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-create-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-local.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-local-all.md").exists())
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

    def test_installs_newer_trellis_platform_adapters_when_active(self) -> None:
        root = self.make_repo(".kiro", ".reasonix", ".trae", ".zcode")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".kiro/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".kiro/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".reasonix/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".reasonix/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".trae/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".trae/commands/sd-create-pr.md").is_file())
        self.assertTrue((root / ".trae/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".trae/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".zcode/commands/sd/review-pr.md").is_file())
        self.assertTrue((root / ".zcode/commands/sd/create-pr.md").is_file())
        self.assertFalse((root / ".qoder/commands/sd-review-pr.md").exists())
        self.assert_installed_targets_snapshot_matches_selection(root)

    def test_platform_filter_still_installs_shared_assets(self) -> None:
        root = self.make_repo(".claude", ".cursor", ".gemini", ".github", ".opencode")

        result = self.run_install(root, "--platform", "gemini")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-start/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local-all/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-learnings/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-housekeeping.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-scope.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-preflight.mjs").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-local.sh").is_file())
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
        self.assertTrue((root / ".gemini/commands/sd/create-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local-all.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-learnings.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".claude/commands/sd/start.md").exists())
        self.assertFalse((root / ".claude/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".claude/commands/sd/create-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-local.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-local-all.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-learnings.md").exists())
        self.assertFalse((root / ".claude/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".claude/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".claude/commands/sd/update-spec.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-continue.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-start.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-finish-work.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-create-pr.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-local.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-local-all.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-learnings.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-update-spec.md").exists())
        self.assertFalse((root / ".github/prompts/sd-continue.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-start.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-finish-work.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-create-pr.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-pr.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-local.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-local-all.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-learnings.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-full-check.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-housekeeping.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-update-spec.prompt.md").exists())
        self.assertFalse((root / ".github/copilot-instructions.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-continue.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-start.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-finish-work.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-create-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-local.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-local-all.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-learnings.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-update-spec.md").exists())

    def test_all_installs_every_adapter_without_anchors(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--all")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-start/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local-all/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-learnings/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-housekeeping.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-scope.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-preflight.mjs").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-local.sh").is_file())
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
        self.assertTrue((root / ".claude/commands/sd/create-pr.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-pr.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-local.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-local-all.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-learnings.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/full-check.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/housekeeping.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/update-spec.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-continue.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-start.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-finish-work.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-create-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-local.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-local-all.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-learnings.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-full-check.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-housekeeping.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-update-spec.md").is_file())
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/start.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/create-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local-all.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-learnings.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-continue.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-start.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-finish-work.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-create-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-local.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-local-all.prompt.md").is_file())
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
        self.assertTrue((root / ".opencode/commands/sd-create-pr.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-local.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-local-all.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-learnings.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-full-check.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-housekeeping.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-update-spec.md").is_file())

    def test_installed_adapters_can_resolve_shared_skill(self) -> None:
        root = self.make_repo(".claude", ".cursor", ".gemini", ".github", ".opencode")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        review_skill = root / ".agents/skills/sd-review-pr/SKILL.md"
        create_pr_skill = root / ".agents/skills/sd-create-pr/SKILL.md"
        review_local_skill = root / ".agents/skills/sd-review-local/SKILL.md"
        review_learnings_skill = root / ".agents/skills/sd-review-learnings/SKILL.md"
        full_check_skill = root / ".agents/skills/sd-full-check/SKILL.md"
        housekeeping_skill = root / ".agents/skills/sd-housekeeping/SKILL.md"
        review_local_script = root / "scripts/sd-ai-command-pack-review-local.sh"
        review_learnings_script = root / "scripts/sd-ai-command-pack-review-learnings.py"
        full_check_script = root / "scripts/sd-ai-command-pack-full-check.sh"
        housekeeping_script = root / "scripts/sd-ai-command-pack-housekeeping.sh"
        self.assertTrue(review_skill.is_file())
        self.assertTrue(create_pr_skill.is_file())
        self.assertTrue(review_local_skill.is_file())
        self.assertTrue(review_learnings_skill.is_file())
        self.assertTrue(full_check_skill.is_file())
        self.assertTrue(housekeeping_skill.is_file())
        self.assertTrue(review_local_script.is_file())
        self.assertTrue(review_learnings_script.is_file())
        self.assertTrue(full_check_script.is_file())
        self.assertTrue(housekeeping_script.is_file())
        claude_start = root / ".claude/commands/sd/start.md"
        self.assertTrue(claude_start.is_file(), claude_start)
        claude_start_content = claude_start.read_text(encoding="utf-8")
        self.assertIn("installs no `trellis-start` skill", claude_start_content)
        self.assertIn("./.trellis/scripts/get_context.py", claude_start_content)
        for adapter in [
            root / ".cursor/commands/sd-start.md",
            root / ".gemini/commands/sd/start.toml",
            root / ".github/prompts/sd-start.prompt.md",
            root / ".opencode/commands/sd-start.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                "Resolve the `trellis-start` skill by name",
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
                "Resolve the `trellis-continue` skill by name",
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
                "Resolve the `trellis-finish-work` skill by name",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/create-pr.md",
            root / ".cursor/commands/sd-create-pr.md",
            root / ".gemini/commands/sd/create-pr.toml",
            root / ".github/prompts/sd-create-pr.prompt.md",
            root / ".opencode/commands/sd-create-pr.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-create-pr` skill by name", content)
            self.assertIn("sd-update-spec", content)
            self.assertIn("sd-review-pr", content)
        for adapter in [
            root / ".claude/commands/sd/review-pr.md",
            root / ".cursor/commands/sd-review-pr.md",
            root / ".gemini/commands/sd/review-pr.toml",
            root / ".github/prompts/sd-review-pr.prompt.md",
            root / ".opencode/commands/sd-review-pr.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                "Resolve the `sd-review-pr` skill by name",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/review-local.md",
            root / ".cursor/commands/sd-review-local.md",
            root / ".gemini/commands/sd/review-local.toml",
            root / ".github/prompts/sd-review-local.prompt.md",
            root / ".opencode/commands/sd-review-local.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-review-local` skill by name", content)
            self.assertIn("scripts/sd-ai-command-pack-review-local.sh", content)
        for adapter in [
            root / ".claude/commands/sd/review-local-all.md",
            root / ".cursor/commands/sd-review-local-all.md",
            root / ".gemini/commands/sd/review-local-all.toml",
            root / ".github/prompts/sd-review-local-all.prompt.md",
            root / ".opencode/commands/sd-review-local-all.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-review-local-all` skill by name", content)
            self.assertIn(
                "scripts/sd-ai-command-pack-review-local.sh --full-codebase",
                content,
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
            self.assertIn("Resolve the `sd-review-learnings` skill by name", content)
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
            self.assertIn("Resolve the `sd-full-check` skill by name", content)
            self.assertIn("source of truth for the exact checks", content)
        for adapter in [
            root / ".claude/commands/sd/housekeeping.md",
            root / ".cursor/commands/sd-housekeeping.md",
            root / ".gemini/commands/sd/housekeeping.toml",
            root / ".github/prompts/sd-housekeeping.prompt.md",
            root / ".opencode/commands/sd-housekeeping.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-housekeeping` skill by name", content)
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
            self.assertIn("Resolve the `sd-update-spec` skill by name", content)
            self.assertIn("source of truth for Trellis update-spec delegation", content)
            self.assertNotIn("Trellis " + "update-spec first", content)

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
            script_index = content.index("scripts/sd-ai-command-pack-housekeeping.sh")
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

    def test_tracked_copilot_guidance_matches_template(self) -> None:
        # The tracked file may carry a repo-specific section outside the
        # managed markers (for example the templates-mirror review guidance),
        # but the managed block itself must match the shipped template exactly.
        installed = (install.ROOT / ".github/copilot-instructions.md").read_text(
            encoding="utf-8"
        )
        template = (
            install.ROOT / "templates/.github/copilot-instructions.sd-ai-command-pack.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(installed.count(install.COPILOT_GUIDANCE_START), 1)
        self.assertEqual(installed.count(install.COPILOT_GUIDANCE_END), 1)
        self.assertIn(template.strip("\n"), installed)
        self.assertIn("byte-verified mirrors of `templates/**`", installed)
        self.assertIn("do not repeat the same finding on both copies", installed)

    def test_copilot_block_keeps_scanner_phrases_contiguous(self) -> None:
        # The review-learnings scanner and the guidance-block assertions match
        # these phrases as contiguous substrings; a line-wrap inside one silently
        # breaks both, so pin that they survive as single-line substrings.
        template = (
            install.ROOT / "templates/.github/copilot-instructions.sd-ai-command-pack.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "current, non-outdated unresolved",
            "stale or outdated review threads",
            "copied or generated",
            "data/access/security boundaries",
        ):
            self.assertIn(phrase, template, f"phrase wrapped or missing: {phrase!r}")

    def test_tracked_full_check_skill_matches_template_and_documents_audit(self) -> None:
        installed = (install.ROOT / ".agents/skills/sd-full-check/SKILL.md").read_text(
            encoding="utf-8"
        )
        template = (
            install.ROOT / "templates/.agents/skills/sd-full-check/SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(installed, template)
        for expected in (
            "Structural post-install audit",
            "scripts/sd-ai-command-pack-install-audit.py",
            "SD_AI_COMMAND_PACK_INSTALL_AUDIT=0",
            "SD_AI_COMMAND_PACK_INSTALL_AUDIT=required",
            "post-install audit ran, skipped, or failed",
        ):
            self.assertIn(expected, installed)

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
            elif installed_script.suffix == ".mjs":
                self.assert_node_syntax_valid(installed_script)
            else:
                self.fail(f"unexpected installed script suffix: {installed_script}")
            self.assert_no_secret_markers(installed_script)

        prism_rules = root / ".prism/rules.json"
        self.assertTrue(prism_rules.is_file())
        self.assert_prism_rules_valid(prism_rules)
        self.assert_no_secret_markers(prism_rules)

    def test_readme_documents_trellis_prerequisite_and_install_docs(self) -> None:
        readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")

        self.assert_trellis_prerequisite_documented(readme)
        self.assertIn("This pack only works", readme)
        self.assertIn("Prerequisite: install Trellis", readme)
        self.assertIn("Quick links:", readme)
        self.assertIn("[Install](#install)", readme)
        self.assertIn("sd-ai-command-pack trellis-gitignore start", readme)
        self.assertIn("SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START", readme)
        self.assertIn("quick smoke test", readme)
        self.assertIn("scripts/sd-ai-command-pack-install-audit.py", readme)
        self.assertIn("scripts/sd-ai-command-pack-update-spec-kb.py --dry-run", readme)
        self.assertIn("Normal shared installs should commit that snapshot", readme)
        self.assertIn("keeps `.sd-ai-command-pack/installed-targets.txt`", readme)
        self.assertIn("Base-ref precedence", readme)
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
        for expected in (
            "python -m pip install -r requirements-dev.txt",
            "COVERAGE_PROCESS_START=.coveragerc python -m coverage run --parallel-mode -m unittest discover -s tests",
            "python -m coverage combine",
            "python -m coverage report --fail-under=100",
        ):
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

    def test_install_file_preserves_existing_pull_request_template(self) -> None:
        root = self.make_repo(".github")
        file = install.PackFile(
            platform="github",
            kind="doc",
            source=install.ROOT / "templates/.github/PULL_REQUEST_TEMPLATE.md",
            target=Path(".github/PULL_REQUEST_TEMPLATE.md"),
            anchor=Path(".github"),
            install="if-anchor-exists",
        )
        destination = root / ".github/PULL_REQUEST_TEMPLATE.md"
        destination.write_text("## My custom template\n", encoding="utf-8")

        result = install.install_file(
            file, root, force=True, dry_run=False, backup=False
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(
            destination.read_text(encoding="utf-8"), "## My custom template\n"
        )

    def test_pull_request_template_prompts_for_scope_sections(self) -> None:
        template = (
            install.ROOT / "templates/.github/PULL_REQUEST_TEMPLATE.md"
        ).read_text(encoding="utf-8")

        self.assertIn("## Summary", template)
        self.assertIn("## Test plan", template)
        self.assertIn("## Pre-PR checklist", template)
        self.assertIn("Tooling/generated scope:", template)
        self.assertIn("Automation scope:", template)
        self.assertIn("CI/review scope:", template)
        self.assertIn("sd-ai-command-pack-full-check.sh", template)
        self.assertIn("no mutate-before-success", template)
        self.assertIn("push once", template)
        # An unedited template body must NOT satisfy the pr-body scope check, or
        # every PR would auto-pass. Assert against the real matcher rather than a
        # hand-rolled line check, so this cannot drift from _body_has_heading()
        # (which also matches headings behind Markdown markers like "- "/"> ").
        scope_check = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_pr_body_scope_template_guard",
        )
        for heading in (
            "Tooling/generated scope:",
            "Automation scope:",
            "CI/review scope:",
        ):
            self.assertFalse(
                scope_check._body_has_heading(template, (heading,)),
                f"template body must not satisfy the scope check for {heading!r}",
            )

    def test_install_file_preserves_gito_config(self) -> None:
        root = self.make_repo()
        file = install.PackFile(
            platform="shared",
            kind="config",
            source=install.ROOT / "templates/.gito/config.toml",
            target=Path(".gito/config.toml"),
            anchor=None,
            install="always",
        )
        destination = root / ".gito/config.toml"
        destination.parent.mkdir(parents=True)
        destination.write_text("retries = 1\n", encoding="utf-8")

        result = install.install_file(
            file, root, force=True, dry_run=False, backup=False
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(destination.read_text(encoding="utf-8"), "retries = 1\n")

    def test_install_file_preserves_if_not_exists_targets(self) -> None:
        root = self.make_repo()
        source = root / "source.json"
        source.write_text('{"pack": true}\n', encoding="utf-8")
        file = self.valid_pack_file(
            source=source,
            target=Path(".custom/config.json"),
        )
        file = install.PackFile(
            platform=file.platform,
            kind=file.kind,
            source=file.source,
            target=file.target,
            anchor=file.anchor,
            install=install.IF_NOT_EXISTS,
        )
        destination = root / ".custom/config.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"local": true}\n', encoding="utf-8")

        result = install.install_file(
            file, root, force=True, dry_run=False, backup=True
        )

        self.assertEqual(result.status, "preserved")
        self.assertIsNone(result.backup)
        self.assertEqual(destination.read_text(encoding="utf-8"), '{"local": true}\n')

    def test_load_manifest_reports_missing_manifest_cleanly(self) -> None:
        with mock.patch.object(install, "MANIFEST_PATH", PACK_ROOT / "missing-manifest.json"):
            with self.assertRaisesRegex(SystemExit, "manifest not found"):
                install.load_manifest()

    def test_install_gitignore_rejects_invalid_utf8(self) -> None:
        root = self.make_repo()
        (root / ".gitignore").write_bytes(b"dist-\xff/\n")

        with self.assertRaisesRegex(SystemExit, "not valid UTF-8"):
            install.install_trellis_gitignore(root, dry_run=False)

    def test_read_text_helpers_report_decode_and_os_errors(self) -> None:
        root = self.make_repo()
        invalid = root / "invalid.txt"
        invalid.write_bytes(b"not utf-8: \xff\n")

        with self.assertRaisesRegex(SystemExit, "strict label is not valid UTF-8"):
            install.read_text_strict(invalid, "strict label")
        with mock.patch.object(Path, "read_text", side_effect=OSError("blocked")):
            with self.assertRaisesRegex(SystemExit, "cannot read strict label"):
                install.read_text_strict(root / "blocked.txt", "strict label")
            with self.assertRaisesRegex(SystemExit, "cannot read optional label"):
                install.read_text_if_exists(root / "blocked.txt", "optional label")

    def test_atomic_write_failure_reports_and_cleans_temp_file(self) -> None:
        root = self.make_repo()
        destination = root / "out.txt"

        with mock.patch.object(install.os, "replace", side_effect=OSError("blocked")):
            with mock.patch.object(Path, "unlink", side_effect=FileNotFoundError):
                with self.assertRaisesRegex(SystemExit, "cannot write"):
                    install.atomic_write_bytes(destination, b"content\n")

    def test_managed_block_rejects_duplicate_markers(self) -> None:
        block = (
            f"{install.COPILOT_GUIDANCE_START}\n"
            "pack block\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
        )
        current = (
            f"{install.COPILOT_GUIDANCE_START}\nold\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
            f"{install.COPILOT_GUIDANCE_START}\nolder\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
        )

        with self.assertRaisesRegex(SystemExit, "duplicate"):
            install.merge_managed_block(current, block)

        duplicate_end = (
            f"{install.COPILOT_GUIDANCE_START}\nold\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
        )

        with self.assertRaisesRegex(SystemExit, "duplicate sd-ai-command-pack end"):
            install.merge_managed_block(duplicate_end, block)

    def test_subprocess_coverage_bootstrap_is_wired(self) -> None:
        # The 100% coverage gate depends on this bootstrap being present and on
        # parallel/fail-under settings; assert them so a silent break is caught.
        sitecustomize = PACK_ROOT / "tests/coverage_sitecustomize/sitecustomize.py"
        self.assertTrue(sitecustomize.is_file())
        self.assertIn(
            'getattr(coverage, "process_startup", None)',
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
        for expected in (
            "Quick links:",
            "sd-ai-command-pack trellis-gitignore start",
            "SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START",
            "quick smoke test",
            "SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF",
            "discovered branch-diff",
            "branch: <default>",
            "branch-diff deletions are not reviewed as deleted diff paths",
            "ClientError: 429",
            "installs should commit this file",
            "clone-local exclude list instead",
            "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS",
            "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS",
            "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS",
            "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_MAX_ATTEMPTS",
            "sandbox-local cache directories",
            "PYTHONPYCACHEPREFIX",
            "UV_TOOL_DIR",
            "RUFF_CACHE_DIR",
            "agent-facing final response",
            "numbered `Next Steps` list",
            "open follow-up items from the session",
            "existing Trellis tasks already in progress",
            "high-value Trellis task",
            "candidates to start next",
        ):
            self.assertIn(expected, installed)
        self.assertEqual(installed, template)

    def test_installed_targets_snapshot_lists_scope_scripts_and_guide(self) -> None:
        root = self.make_repo(".github")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        snapshot = (root / install.INSTALLED_TARGETS_FILE).read_text(
            encoding="utf-8"
        )
        for expected in (
            ".gitignore",
            "scripts/sd-ai-command-pack-review-scope.sh",
            "scripts/sd-ai-command-pack-review-preflight.mjs",
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
        self.assertFalse((root / ".agents/skills/sd-create-pr/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/sd-full-check/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/sd-housekeeping/SKILL.md").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-full-check.sh").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-housekeeping.sh").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-review-scope.sh").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-review-preflight.mjs").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-pr-body-scope.py").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-update-spec-kb.py").exists())
        self.assertFalse((root / ".prism/rules.json").exists())
        self.assertFalse((root / "docs/SD_AI_COMMAND_PACK.md").exists())
        self.assertFalse((root / install.INSTALLED_TARGETS_FILE).exists())
        self.assertIn(".sd-ai-command-pack/installed-targets.txt", result.stdout)
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-create-pr.md").exists())
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
        (root / ".gitignore").write_text("dist/\n", encoding="utf-8")
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".gitignore")
        self.run_git(root, "commit", "-m", "baseline")
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
        self.assertTrue((root / ".agents/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-create-pr.md").is_file())
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
            ".agents/skills/sd-create-pr/SKILL.md",
            ".codex/config.toml",
            ".codex/hooks/",
            ".cursor/agents/trellis-*.md",
            ".cursor/commands/sd-review-pr.md",
            ".cursor/commands/sd-create-pr.md",
            "scripts/sd-ai-command-pack-full-check.sh",
            ".sd-ai-command-pack/",
            ".obsidian-kb/",
            install.LOCAL_ONLY_EXCLUDE_END,
        ):
            self.assertIn(expected, exclude_text)
        self.assertEqual((root / ".gitignore").read_text(encoding="utf-8"), "dist/\n")
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

    def test_local_only_reports_existing_trellis_without_bootstrap(self) -> None:
        root = self.make_repo()

        result = install.ensure_trellis_for_local_only(
            root,
            platforms=None,
            install_all=False,
            dry_run=False,
            skip_trellis_init=False,
        )

        self.assertEqual(result.status, "trellis-present")
        self.assertEqual(result.target, Path(".trellis/config.yaml"))

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

    def test_local_only_rejects_tracked_paths_before_bootstrap(self) -> None:
        root = self.make_git_repo_without_trellis()
        (root / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
        pack_script = root / "scripts/sd-ai-command-pack-full-check.sh"
        pack_script.parent.mkdir(parents=True)
        pack_script.write_text("#!/bin/sh\n", encoding="utf-8")
        self.run_git(root, "add", "AGENTS.md", "scripts/sd-ai-command-pack-full-check.sh")
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

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("already tracked", result.stdout)
        self.assertIn("AGENTS.md", result.stdout)
        self.assertIn("scripts/sd-ai-command-pack-full-check.sh", result.stdout)
        self.assertFalse(trellis_log.exists())
        for unexpected in (
            ".trellis",
            ".agents",
            ".codex",
            ".cursor",
            ".sd-ai-command-pack",
        ):
            self.assertFalse((root / unexpected).exists(), unexpected)

    def test_local_only_requires_git_repo(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name)

        result = self.run_install(target, "--local-only")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "failed to verify --local-only target Git repository",
            result.stdout,
        )
        self.assertIn("not a git repository", result.stdout)

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
            with self.assertRaisesRegex(SystemExit, "git is required"):
                install.git_output(
                    root,
                    "status",
                    required=True,
                    context="check status",
                )
            with self.assertRaisesRegex(SystemExit, "git is required"):
                install.tracked_paths(root, ["anything"])

        failed_git = subprocess.CompletedProcess(
            ["git", "status"],
            1,
            stdout="fatal: nope\n",
        )
        with mock.patch.object(subprocess, "run", return_value=failed_git):
            self.assertIsNone(install.git_output(root, "status"))

        with mock.patch.object(install, "git_output", return_value=None):
            with self.assertRaisesRegex(SystemExit, "requires the target to be a Git repo"):
                install.require_git_repo_for_local_only(root)

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

    def test_manifest_declares_current_trellis_platform_adapters(self) -> None:
        _, files = install.load_manifest()
        platforms_with_manifest_entries = {file.platform for file in files}
        expected_platforms = {
            "antigravity",
            "claude",
            "codebuddy",
            "cursor",
            "devin",
            "droid",
            "gemini",
            "github",
            "kilo",
            "kiro",
            "opencode",
            "pi",
            "qoder",
            "reasonix",
            "shared",
            "trae",
            "zcode",
        }

        self.assertEqual(platforms_with_manifest_entries, expected_platforms)
        self.assertIn("codex", install.PLATFORMS)
        self.assertTrue(
            any(
                file.platform == "shared"
                and file.target == Path(".agents/skills/sd-review-pr/SKILL.md")
                for file in files
            )
        )
        for platform in expected_platforms - {"shared"}:
            self.assertIn(platform, install.ACTIVE_TRELLIS_PLATFORM_MARKERS)
            self.assertIn(platform, install.TRELLIS_INIT_PLATFORM_FLAGS)

        expected_targets = {
            ".agent/workflows/sd-review-pr.md",
            ".agent/workflows/sd-create-pr.md",
            ".agent/skills/sd-review-pr/SKILL.md",
            ".agent/skills/sd-create-pr/SKILL.md",
            ".codebuddy/commands/sd/review-pr.md",
            ".codebuddy/commands/sd/create-pr.md",
            ".codebuddy/skills/sd-review-pr/SKILL.md",
            ".codebuddy/skills/sd-create-pr/SKILL.md",
            ".devin/workflows/sd-review-pr.md",
            ".devin/workflows/sd-create-pr.md",
            ".factory/commands/sd/review-pr.md",
            ".factory/commands/sd/create-pr.md",
            ".kilocode/workflows/sd-review-pr.md",
            ".kilocode/workflows/sd-create-pr.md",
            ".kiro/skills/sd-review-pr/SKILL.md",
            ".kiro/skills/sd-create-pr/SKILL.md",
            ".pi/prompts/sd-review-pr.md",
            ".pi/prompts/sd-create-pr.md",
            ".qoder/commands/sd-review-pr.md",
            ".qoder/commands/sd-create-pr.md",
            ".reasonix/skills/sd-review-pr/SKILL.md",
            ".reasonix/skills/sd-create-pr/SKILL.md",
            ".trae/commands/sd-review-pr.md",
            ".trae/commands/sd-create-pr.md",
            ".zcode/commands/sd/review-pr.md",
            ".zcode/commands/sd/create-pr.md",
        }
        actual_targets = {file.target.as_posix() for file in files}
        self.assertTrue(expected_targets.issubset(actual_targets))

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
                if file.platform == "claude":
                    self.assertIn("installs no `trellis-start` skill", content)
                    self.assertIn("./.trellis/scripts/get_context.py", content)
                else:
                    self.assertIn("Resolve the `trellis-start` skill by name", content)
                    self.assertIn("Use that skill as the primary instructions", content)
            elif "continue" in file.target.name:
                self.assertIn("Resolve the `trellis-continue` skill by name", content)
                self.assertIn("Use that skill as the primary instructions", content)
            elif "finish-work" in file.target.name:
                self.assertIn("Resolve the `trellis-finish-work` skill by name", content)
                self.assertIn("Use that skill as the primary instructions", content)
            elif "create-pr" in file.target.name:
                self.assertIn("Resolve the `sd-create-pr` skill by name", content)
                self.assertIn("sd-update-spec", content)
                self.assertIn("sd-review-pr", content)
            elif "full-check" in file.target.name:
                self.assertIn("Resolve the `sd-full-check` skill by name", content)
                self.assertIn("source of truth for the exact checks", content)
            elif "review-local-all" in file.target.name:
                self.assertIn("Resolve the `sd-review-local-all` skill by name", content)
                self.assertIn(
                    "scripts/sd-ai-command-pack-review-local.sh --full-codebase",
                    content,
                )
            elif "review-local" in file.target.name:
                self.assertIn("Resolve the `sd-review-local` skill by name", content)
                self.assertIn("scripts/sd-ai-command-pack-review-local.sh", content)
            elif "housekeeping" in file.target.name:
                self.assertIn(
                    "Resolve the `sd-housekeeping` skill by name",
                    content,
                )
                self.assertIn("scripts/sd-ai-command-pack-housekeeping.sh", content)
            elif "update-spec" in file.target.name:
                self.assertIn("Resolve the `sd-update-spec` skill by name", content)
                self.assertIn("source of truth for Trellis update-spec delegation", content)
            elif "review-learnings" in file.target.name:
                self.assertIn("Resolve the `sd-review-learnings` skill by name", content)
                self.assertIn("scripts/sd-ai-command-pack-review-learnings.py", content)
            else:
                self.assertIn("Resolve the `sd-review-pr` skill by name", content)

    def test_codex_visible_sd_skill_wrappers_reference_workflows(self) -> None:
        expected = {
            "sd-start": "Resolve the `trellis-start` skill by name",
            "sd-continue": "Resolve the `trellis-continue` skill by name",
            "sd-finish-work": "Resolve the `trellis-finish-work` skill by name",
            "sd-update-spec": "Resolve the `trellis-update-spec` skill by name",
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
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0", review_pr)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0", review_pr)

        create_pr = (
            install.ROOT / "templates/.agents/skills/sd-create-pr/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-create-pr", create_pr)
        self.assertIn("# SD Create Pull Request", create_pr)
        self.assertIn("Resolve both `sd-update-spec` and `sd-review-pr`", create_pr)
        self.assertIn("Do not create a duplicate PR", create_pr)
        self.assertIn("Do not assume the base branch is `main`", create_pr)
        self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR", create_pr)
        self.assertIn("Do not run Prism, Gito", create_pr)

        review_local = (
            install.ROOT / "templates/.agents/skills/sd-review-local/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-review-local", review_local)
        self.assertIn("# SD Local Review Loop", review_local)
        self.assertIn("bash scripts/sd-ai-command-pack-review-local.sh", review_local)
        self.assertIn("SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS", review_local)
        self.assertIn("asks the user which findings to fix", review_local)
        self.assertIn("Do not substitute `sd-full-check`", review_local)

        review_local_all = (
            install.ROOT / "templates/.agents/skills/sd-review-local-all/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-review-local-all", review_local_all)
        self.assertIn("# SD Full-Codebase Local Review Loop", review_local_all)
        self.assertIn(
            "bash scripts/sd-ai-command-pack-review-local.sh --full-codebase",
            review_local_all,
        )
        self.assertIn("prism review codebase", review_local_all)
        self.assertIn("empty chunk response", review_local_all)
        self.assertIn("gito review --all --path <repo-root>", review_local_all)
        self.assertIn("replacing `<repo-root>` with the absolute repository root", review_local_all)
        self.assertIn("branch-diff deletions", review_local_all)
        self.assertIn("continue stacking fixes", review_local_all)
        self.assertIn("UV_CACHE_DIR", review_local_all)
        self.assertIn(
            "SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND",
            review_local_all,
        )

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
        # The skill lists common toggles and points at the canonical docs for
        # the full env-var set (deprecated fallbacks included).
        self.assertIn("docs/SD_AI_COMMAND_PACK.md", full_check)
        self.assertIn("Configuration", full_check)
        self.assertIn("sandboxed agent sessions", full_check)
        self.assertIn("PYTHONPYCACHEPREFIX", full_check)
        self.assertIn("UV_TOOL_DIR", full_check)
        self.assertIn("RUFF_CACHE_DIR", full_check)

        housekeeping = (
            install.ROOT / "templates/.agents/skills/sd-housekeeping/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-housekeeping", housekeeping)
        self.assertIn("# SD Housekeeping", housekeeping)
        self.assertIn("bash scripts/sd-ai-command-pack-housekeeping.sh", housekeeping)
        self.assertIn("Expected clean state", housekeeping)
        self.assertIn("general\nrepo maintenance", housekeeping)
        self.assertIn("branch: <default>", housekeeping)

        update_spec = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("do not rebuild", update_spec)
        self.assertIn("`.obsidian-kb/` manually", update_spec)
        self.assertIn("helper as the source of truth for `.obsidian-kb/`", update_spec)
        self.assertNotIn("Ensure `.obsidian-kb/`", update_spec)
        self.assertNotIn("Link every relevant existing repo-knowledge file", update_spec)
        self.assertNotIn("perform the remaining bullets manually", update_spec)

        update_spec = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("repospec artifact", update_spec)
        self.assertIn("docs/repomix-map.md", update_spec)
        self.assertIn("Architectural overview", update_spec)
        self.assertIn(".obsidian-kb", update_spec)
        self.assertIn("scripts/sd-ai-command-pack-update-spec-kb.py", update_spec)
        self.assertIn(".obsidian-kb/Dashboard - <repo>.md", update_spec)
        self.assertIn("Obsidian vault copy", update_spec)

    def test_flat_markdown_entries_are_completion_visible(self) -> None:
        commands = [
            "start",
            "continue",
            "finish-work",
            "create-pr",
            "review-pr",
            "review-local",
            "review-local-all",
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
            "start": "Initialize or resume a task using the Trellis start workflow.",
            "continue": "Resume the current Trellis task or workflow state.",
            "finish-work": "Wrap up the current Trellis coding session.",
            "create-pr": "Create or reuse a PR after SD spec refresh, commit, and push, then run the SD PR review loop.",
            "review-pr": "Run the Software Delivery (SD) pull-request review loop.",
            "review-local": "Run the Software Delivery (SD) local review loop.",
            "review-local-all": "Run the Software Delivery (SD) full-codebase local review loop.",
            "review-learnings": "Detect or update repository review learnings.",
            "full-check": "Run the Software Delivery (SD) full-check gate for deterministic checks, local review, and readiness reporting.",
            "housekeeping": "Run Software Delivery (SD) end-of-stream housekeeping for a completed work stream.",
            "update-spec": "Run the Software Delivery (SD) update-spec workflow for repository knowledge artifacts.",
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
            target = file.target.as_posix()
            if file.platform in {"cursor", "opencode", "qoder", "trae"}:
                self.assertRegex(target, r"/commands/sd-[^/]+\.md$")
                self.assertTrue(file.source.name.startswith("sd-"), file.source)
                self.assertTrue(file.target.name.startswith("sd-"), file.target)
            else:
                self.assertIn("/commands/sd/", target)
            self.assertNotIn("/commands/trellis/", source)
            self.assertNotIn("/commands/trellis/", target)
        for file in github_prompt_files:
            self.assertTrue(file.source.name.startswith("sd-"), file.source)
            self.assertTrue(file.target.name.startswith("sd-"), file.target)

        self.assertFalse((install.ROOT / "templates/.claude/commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.cursor/commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.gemini/commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.opencode/commands/trellis").exists())

    def test_update_spec_wrappers_include_repospec_and_architecture_gates(self) -> None:
        shared_skill = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        ).read_text(encoding="utf-8")
        for expected in (
            "Resolve the `trellis-update-spec` skill by name",
            "skill discovery mechanism",
            "Use the Trellis update-spec skill as the primary instructions",
            "repospec artifact",
            "Makefile",
            "package.json",
            "instead of hand-editing generated",
            "Repomix",
            "docs/repomix-map.md",
            "no infrastructure",
            "ARCHITECTURE.md",
            "docs/ARCHITECTURE.md",
            ".trellis/spec/**/architecture*.md",
            "Do not create a new overview unless",
            "architecture signals",
            "package/module boundaries",
            "not present",
            "not warranted",
            ".obsidian-kb",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
            "exits nonzero",
            "repo root `.gitignore`",
            "copies",
            "visible semantic",
            "file/folder names that start with `.`",
            ".trellis/workflow.md",
            ".trellis/config.yaml",
            ".trellis/spec/**/*.md",
            ".trellis/tasks/**/*.md",
            ".trellis/workspace/",
            ".obsidian-kb/Dashboard - <repo>.md",
            "landing page",
            "Obsidian KB",
            "Obsidian vault copy",
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
            self.assertIn("Resolve the `sd-update-spec` skill by name", content)
            self.assertIn("source of truth for Trellis update-spec delegation", content)
            self.assertNotIn("Trellis " + "update-spec first", content)
            self.assertNotIn("repospec artifact", content)

    def test_trellis_channel_reference_docs_do_not_use_unsupported_tag_flags(self) -> None:
        progress_debugging = (
            install.ROOT
            / ".agents/skills/trellis-channel/references/progress-debugging.md"
        ).read_text(encoding="utf-8")
        workers = (
            install.ROOT
            / ".agents/skills/trellis-channel/references/workers.md"
        ).read_text(encoding="utf-8")
        command_reference = (
            install.ROOT
            / ".agents/skills/trellis-channel/references/command-reference.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("--tag", progress_debugging)
        self.assertNotIn("--tag", workers)
        self.assertIn("--kind interrupt_requested,interrupted", progress_debugging)
        self.assertIn("--kind interrupt_requested,interrupted", workers)
        self.assertIn("Question: check this when you reach the next turn.", workers)
        self.assertIn("interrupt_requested` / `interrupted", command_reference)

    def test_update_spec_docs_explain_obsidian_kb_vault_copying(self) -> None:
        doc_paths = [
            install.ROOT / "README.md",
            install.ROOT / "docs/SD_AI_COMMAND_PACK.md",
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md",
        ]

        for doc_path in doc_paths:
            content = doc_path.read_text(encoding="utf-8")
            self.assertIn(".obsidian-kb/", content)
            self.assertIn(".obsidian-kb/Dashboard - <repo>.md", content)
            self.assertIn(".obsidian-kb/LLM-KB - <repo>.md", content)
            self.assertIn("Markdown landing page", content)
            self.assertIn("GitHub repository link", content)
            self.assertIn("visible semantic category", content)
            self.assertIn("folder names do not start with `.`", content)
            self.assertIn(".trellis/tasks/**/*.md", content)
            self.assertIn("older symlink-based helper", content)
            self.assertIn("scripts/sd-ai-command-pack-update-spec-kb.py", content)
            self.assertIn('cp -R "$(pwd)/.obsidian-kb/."', content)
            self.assertIn("Copy-Item -Recurse -Force", content)
            self.assertNotIn("New-Item -ItemType SymbolicLink", content)
            self.assertNotIn("PowerShell running as Administrator", content)
            self.assertNotIn("Developer Mode enabled", content)

        gitignore = (install.ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".obsidian-kb/", gitignore)
        self.assertIn(".sd-ai-command-pack/installed-targets.txt", gitignore)
        self.assertIn(".sd-ai-command-pack/local-only.txt", gitignore)

    def test_full_check_script_writes_gito_reports_to_artifact_dir(self) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR", script)
        self.assertIn(".build/review/gito", script)
        self.assertIn('gito review --vs "$base_ref" --filter "$filters" --out "$out_dir"', script)

    def test_review_provider_scan_excludes_are_managed_in_scripts(self) -> None:
        script_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-local.sh",
        ]
        expected_dirs = (
            ".agent",
            ".agents",
            ".claude",
            ".codex",
            ".codebuddy",
            ".cursor",
            ".devin",
            ".factory",
            ".gemini",
            ".github",
            ".kiro",
            ".kilocode",
            ".opencode",
            ".pi",
            ".qoder",
            ".reasonix",
            ".trae",
            ".zcode",
            ".build",
            ".git",
            ".pytest_cache",
            ".obsidian-kb",
            ".trellis",
            ".ruff_cache",
            ".venv",
            ".sd-ai-command-pack",
            "node_modules",
        )

        for script_path in script_paths:
            content = script_path.read_text(encoding="utf-8")
            self.assertIn("# sd-ai-command-pack review-scan-excludes start", content)
            self.assertIn("# sd-ai-command-pack review-scan-excludes end", content)
            self.assertIn("--exclude \"$excludes\"", content)
            self.assertIn("--filter \"$filters\"", content)
            for dirname in expected_dirs:
                self.assertIn(f'  "{dirname}"', content, script_path)

    def test_review_scripts_avoid_hardcoded_default_branch_and_regex_scope_paths(
        self,
    ) -> None:
        script_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-scope.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs",
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-scope.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-preflight.mjs",
        ]

        for script_path in script_paths:
            content = script_path.read_text(encoding="utf-8")
            self.assertNotIn("origin/main", content, script_path)
            self.assertIn("origin/HEAD", content, script_path)

        scope_script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-scope.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("normalize_repo_path()", scope_script)
        self.assertNotIn("[[ \"$path\" =~", scope_script)

    def test_review_local_script_runs_gito_after_prism_findings(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        for name, exit_code in (("prism", 1), ("gito", 0)):
            tool = stub_bin / name
            tool.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '{name} %s\\n' \"$*\" >> {str(log_path)!r}\n"
                f"exit {exit_code}\n",
                encoding="utf-8",
            )
            tool.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("prism review unstaged", log)
        self.assertIn(
            "gito review --vs HEAD --filter app.txt --out .build/review/gito",
            log,
        )
        self.assertTrue((root / ".build/review/gito").is_dir())

    def test_review_local_script_preserves_configuration_error_exit_code(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        prism = stub_bin / "prism"
        prism.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'prism %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 1\n",
            encoding="utf-8",
        )
        prism.chmod(0o755)

        result = subprocess.run(
            [
                self._bash_path,
                "scripts/sd-ai-command-pack-review-local.sh",
                "not-configured",
                "prism",
            ],
            cwd=root,
            env={**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("No command configured for local review tool 'not-configured'", result.stdout)
        self.assertIn("prism review unstaged", log_path.read_text(encoding="utf-8"))

    def test_review_local_script_reviews_branch_when_no_local_changes(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("branch\n", encoding="utf-8")
        self.run_git(root, "add", "app.txt")
        self.run_git(root, "commit", "-m", "branch change")
        merge_base = self.git_output(root, "rev-parse", "HEAD~1")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        for name in ("prism", "gito"):
            tool = stub_bin / name
            tool.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '{name} %s\\n' \"$*\" >> {str(log_path)!r}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            tool.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_BASE_REF": "HEAD~1",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD~1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn(f"prism review range {merge_base}..HEAD", log)
        self.assertIn(
            "gito review --vs HEAD~1 --filter app.txt --out .build/review/gito",
            log,
        )

    def test_review_local_script_prefers_local_changes_over_branch_diff(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "branch.txt").write_text("base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "branch.txt").write_text("branch\n", encoding="utf-8")
        self.run_git(root, "add", "branch.txt")
        self.run_git(root, "commit", "-m", "branch change")
        (root / "local.txt").write_text("untracked\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        for name in ("prism", "gito"):
            tool = stub_bin / name
            tool.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '{name} %s\\n' \"$*\" >> {str(log_path)!r}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            tool.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_BASE_REF": "HEAD~1",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD~1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("prism review codebase --paths local.txt", log)
        self.assertNotIn("prism review range", log)
        self.assertIn(
            "gito review --vs HEAD~1 --filter local.txt --out .build/review/gito",
            log,
        )
        self.assertNotIn("branch.txt", log)

    def test_review_local_script_all_scope_runs_codebase_providers(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        for name, exit_code in (("prism", 1), ("gito", 0)):
            tool = stub_bin / name
            tool.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '{name} %s\\n' \"$*\" >> {str(log_path)!r}\n"
                f"exit {exit_code}\n",
                encoding="utf-8",
            )
            tool.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Local review scope: full codebase", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("prism review codebase", log)
        self.assertIn("--exclude .agent,.agent/**", log)
        self.assertIn(".github,.github/**", log)
        self.assertIn(
            f"gito review --all --path {root.resolve()} --filter ",
            log,
        )
        self.assertIn("--out .build/review/gito-all", log)
        gito_line = next(line for line in log.splitlines() if line.startswith("gito "))
        gito_filter = gito_line.split(" --filter ", 1)[1].split(" --out ", 1)[0]
        gito_filter_paths = set(gito_filter.split(","))
        for excluded in (
            ".agent",
            ".agents",
            ".claude",
            ".codex",
            ".codebuddy",
            ".cursor",
            ".devin",
            ".factory",
            ".gemini",
            ".github",
            ".kiro",
            ".kilocode",
            ".opencode",
            ".pi",
            ".qoder",
            ".reasonix",
            ".trae",
            ".zcode",
            ".build",
            ".git",
            ".pytest_cache",
            ".obsidian-kb",
            ".trellis",
            ".ruff_cache",
            ".venv",
            ".sd-ai-command-pack",
            "node_modules",
        ):
            self.assertNotIn(excluded, gito_filter_paths)
        self.assertTrue((root / ".build/review/gito-all").is_dir())

    def test_review_local_script_all_scope_keeps_gito_all_when_tracked_files_deleted(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").unlink()

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Tracked or branch-diff deletions are present", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn(f"gito review --all --path {root.resolve()} --filter ", log)
        gito_line = next(line for line in log.splitlines() if line.startswith("gito "))
        gito_filter = gito_line.split(" --filter ", 1)[1].split(" --out ", 1)[0]
        self.assertNotIn("app.txt", set(gito_filter.split(",")))

    def test_review_local_script_all_scope_keeps_gito_all_when_branch_diff_deletes_files(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "keep.txt").write_text("keep\n", encoding="utf-8")
        (root / "removed.txt").write_text("remove\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "removed.txt").unlink()
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "delete removed file")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD~1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Tracked or branch-diff deletions are present", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn(f"gito review --all --path {root.resolve()} --filter ", log)
        gito_line = next(line for line in log.splitlines() if line.startswith("gito "))
        gito_filter = gito_line.split(" --filter ", 1)[1].split(" --out ", 1)[0]
        gito_filter_paths = set(gito_filter.split(","))
        self.assertIn("keep.txt", gito_filter_paths)
        self.assertNotIn("removed.txt", gito_filter_paths)

    def test_review_local_script_retries_gito_rate_limit(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        state_path = Path(tools_tempdir.name) / "gito-attempts.txt"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"state={str(state_path)!r}\n"
            "count=\"$(cat \"$state\" 2>/dev/null || printf 0)\"\n"
            "count=$((count + 1))\n"
            "printf '%s\\n' \"$count\" > \"$state\"\n"
            f"printf 'gito attempt %s %s\\n' \"$count\" \"$*\" >> {str(log_path)!r}\n"
            "if [ \"$count\" -eq 1 ]; then\n"
            "  printf 'ClientError: 429 Slow down\\n'\n"
            "  printf 'Exception: provider summary 500\\n'\n"
            "  exit 1\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS": "2",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Gito attempt 1/2", result.stdout)
        self.assertIn("Gito appears rate-limited", result.stdout)
        self.assertIn("Gito attempt 2/2", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("gito attempt"), 2, log)
        self.assertIn("gito attempt 2 review --vs HEAD --filter app.txt", log)

    def test_review_local_script_does_not_retry_gito_non_rate_limit_trace(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito attempt %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "printf 'A traceback mentioned provider rate limiting docs.\\n'\n"
            "printf 'Docs mention `ClientError: 429` or `Slow down`.\\n'\n"
            "printf 'ClientError: 404 Not Found\\n'\n"
            "exit 1\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS": "2",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Gito attempt 1/2", result.stdout)
        self.assertNotIn("Gito appears rate-limited", result.stdout)
        self.assertNotIn("Gito attempt 2/2", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("gito attempt"), 1, log)

    def test_review_local_script_prism_codebase_empty_chunk_falls_back_to_batches(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        prism = stub_bin / "prism"
        prism.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'prism %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "paths_arg=''\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"${1:-}\" = --paths ]; then\n"
            "    shift\n"
            "    paths_arg=\"${1:-}\"\n"
            "    break\n"
            "  fi\n"
            "  shift\n"
            "done\n"
            "if [ -z \"$paths_arg\" ] || [[ \"$paths_arg\" == *,* ]]; then\n"
            "  printf 'Error: chunked review: chunk 0: no content in response\\n'\n"
            "  exit 4\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        prism.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "prism"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_BATCH_SIZE": "2",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("empty chunk response", result.stdout)
        self.assertIn("full codebase batch", result.stdout)
        self.assertIn("retrying each path individually", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("prism review codebase --fail-on high", log)
        self.assertIn("prism review codebase --paths", log)
        for line in log.splitlines():
            if " --paths " in line:
                self.assertNotIn("--paths .agents/", line)
                self.assertNotIn("--paths .github/", line)
                self.assertNotIn("--paths .trellis/", line)

    def test_review_local_script_prism_empty_chunk_after_split_is_not_auth(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        prism = stub_bin / "prism"
        prism.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'Error: chunked review: chunk 0: no content in response\\n'\n"
            "exit 4\n",
            encoding="utf-8",
        )
        prism.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "prism"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_BATCH_SIZE": "1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("empty chunk response after fallback splitting", result.stdout)
        self.assertNotIn("authentication or configuration", result.stdout)

    def test_review_local_script_sets_writable_uv_dirs_for_gito(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'UV_CACHE_DIR=%s\\n' \"$UV_CACHE_DIR\" >> {str(log_path)!r}\n"
            f"printf 'UV_TOOL_DIR=%s\\n' \"$UV_TOOL_DIR\" >> {str(log_path)!r}\n"
            f"printf 'gito %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)
        temp_root = root / "tmp"

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "TMPDIR": str(temp_root),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn(f"UV_CACHE_DIR={temp_root}/sd-ai-command-pack-uv-cache", log)
        self.assertIn(f"UV_TOOL_DIR={temp_root}/sd-ai-command-pack-uv-tools", log)
        self.assertTrue((temp_root / "sd-ai-command-pack-uv-cache").is_dir())
        self.assertTrue((temp_root / "sd-ai-command-pack-uv-tools").is_dir())
        self.assertIn("gito review --all", log)
        self.assertIn("--filter ", log)

    def test_review_local_scripts_register_temp_file_cleanup(self) -> None:
        script_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-local.sh",
        ]

        for script_path in script_paths:
            content = script_path.read_text(encoding="utf-8")
            self.assertIn("cleanup_review_local_temp_files()", content, script_path)
            self.assertIn("trap cleanup_review_local_temp_files EXIT", content, script_path)
            self.assertEqual(
                content.count("$(mktemp "),
                content.count('REVIEW_LOCAL_TEMP_FILES+=("$'),
                script_path,
            )

    def test_review_local_script_loads_gito_concurrency_env(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.write_gito_pack_env(root)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'MAX_CONCURRENT_TASKS=%s\\n' \"${{MAX_CONCURRENT_TASKS:-}}\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("MAX_CONCURRENT_TASKS=4", log_path.read_text(encoding="utf-8"))

    def test_review_local_script_preserves_explicit_gito_concurrency_env(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'MAX_CONCURRENT_TASKS=%s\\n' \"${{MAX_CONCURRENT_TASKS:-}}\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "MAX_CONCURRENT_TASKS": "2",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("MAX_CONCURRENT_TASKS=2", log_path.read_text(encoding="utf-8"))

    def test_review_local_script_disabled_provider_smoke(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_MODE": "0",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MODE": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Skipping Prism review", result.stdout)
        self.assertIn("Skipping Gito review", result.stdout)
        self.assertIn("Local review providers completed", result.stdout)

    def test_review_local_script_runs_configured_custom_tool(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        tool_log = root / "custom-tool.log"

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "CUSTOM_TOOL_LOG": str(tool_log),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS": "custom",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_CUSTOM_COMMAND": (
                    "printf 'custom-ok\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("==> Local review: custom", result.stdout)
        self.assertEqual(tool_log.read_text(encoding="utf-8"), "custom-ok\n")

    def test_review_local_script_runs_custom_tool_without_login_shell(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        tool_log = root / "custom-tool.log"

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "CUSTOM_TOOL_LOG": str(tool_log),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS": "custom",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_CUSTOM_COMMAND": (
                    "case \"$-\" in *l*) printf 'login\\n' ;; *) printf 'non-login\\n' ;; esac > \"$CUSTOM_TOOL_LOG\""
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(tool_log.read_text(encoding="utf-8"), "non-login\n")

    def test_review_local_all_scope_prefers_configured_all_custom_tool(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        tool_log = root / "custom-tool.log"

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all"],
            cwd=root,
            env={
                **os.environ,
                "CUSTOM_TOOL_LOG": str(tool_log),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS": "custom",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_CUSTOM_COMMAND": (
                    "printf 'diff-command\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_CUSTOM_COMMAND": (
                    "printf 'all-command\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Local review scope: full codebase", result.stdout)
        self.assertEqual(tool_log.read_text(encoding="utf-8"), "all-command\n")

    def test_review_local_full_codebase_alias_uses_all_custom_tool(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        tool_log = root / "custom-tool.log"

        result = subprocess.run(
            [
                self._bash_path,
                "scripts/sd-ai-command-pack-review-local.sh",
                "--full-codebase",
            ],
            cwd=root,
            env={
                **os.environ,
                "CUSTOM_TOOL_LOG": str(tool_log),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS": "custom",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_CUSTOM_COMMAND": (
                    "printf 'diff-command\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_CUSTOM_COMMAND": (
                    "printf 'full-command\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Local review scope: full codebase", result.stdout)
        self.assertEqual(tool_log.read_text(encoding="utf-8"), "full-command\n")

    def test_review_local_script_lists_supported_tools(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [
                self._bash_path,
                "scripts/sd-ai-command-pack-review-local.sh",
                "--list-tools",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.splitlines(), ["prism", "gito", "all", "default"])

    def test_review_local_script_help_describes_full_codebase_alias(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--help"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--full-codebase", result.stdout)
        self.assertIn("--list-tools", result.stdout)
        self.assertIn("Tool names must use only", result.stdout)

    def test_review_local_script_reports_unknown_tool(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "unknown"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("No command configured for local review tool 'unknown'", result.stdout)

    def test_review_local_script_rejects_unsafe_tool_name(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [
                self._bash_path,
                "scripts/sd-ai-command-pack-review-local.sh",
                "../unknown",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Unsupported local review tool name '../unknown'", result.stdout)

    def test_pack_owned_scripts_use_sd_ai_command_pack_identity(self) -> None:
        raw, files = install.load_manifest()
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
            "scripts/sd-ai-command-pack-review-preflight.mjs",
            "scripts/sd-ai-command-pack-review-local.sh",
            "scripts/sd-ai-command-pack-review-learnings.py",
            "scripts/sd-ai-command-pack-install-audit.py",
            "scripts/sd-ai-command-pack-pr-body-scope.py",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
        }
        full_check = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")
        housekeeping = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        ).read_text(encoding="utf-8")

        self.assertTrue(expected_targets.issubset(script_targets), script_targets)
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
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS", script)
        self.assertLess(script.index(node_guard), script.index(script_loop))

    def test_full_check_script_runs_from_repo_root_and_uses_env_script_name(
        self,
    ) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('${BASH_SOURCE[0]}', script)
        self.assertIn('REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"', script)
        self.assertIn('! cd -- "$REPO_ROOT"', script)
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
        self.assertIn("Running legacy $script with a changed-files list", script)
        self.assertIn("CI change classification: current diff", script)
        self.assertIn("sd-ai-command-pack-ci-paths", script)
        self.assertIn("run_review_preflight()", script)
        self.assertIn("scripts/sd-ai-command-pack-review-preflight.mjs", script)
        self.assertIn("scripts/check-review-preflight.mjs", script)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT", script)
        self.assertIn(
            "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND",
            script,
        )
        self.assertIn(
            "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_SCRIPT",
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

    def test_full_check_script_retries_gito_rate_limit(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.write_gito_pack_env(root)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-full-check-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        state_path = Path(tools_tempdir.name) / "gito-attempts.txt"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"state={str(state_path)!r}\n"
            "count=\"$(cat \"$state\" 2>/dev/null || printf 0)\"\n"
            "count=$((count + 1))\n"
            "printf '%s\\n' \"$count\" > \"$state\"\n"
            f"printf 'gito attempt %s %s\\n' \"$count\" \"$*\" >> {str(log_path)!r}\n"
            "if [ \"$count\" -eq 1 ]; then\n"
            "  printf 'ClientError: 429 Slow down\\n'\n"
            "  exit 1\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT": "0",
                "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF": "HEAD",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_MAX_ATTEMPTS": "2",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_RETRY_DELAY_SECONDS": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Gito attempt 1/2", result.stdout)
        self.assertIn("Gito appears rate-limited", result.stdout)
        self.assertIn("Gito attempt 2/2", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("gito attempt"), 2, log)
        self.assertIn("gito attempt 2 review --vs HEAD --filter app.txt", log)

    def test_full_check_script_loads_gito_concurrency_env(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-full-check-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'MAX_CONCURRENT_TASKS=%s\\n' \"${{MAX_CONCURRENT_TASKS:-}}\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT": "0",
                "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF": "HEAD",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("MAX_CONCURRENT_TASKS=4", log_path.read_text(encoding="utf-8"))

    def test_full_check_script_ignores_invalid_configured_base_ref(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        result = subprocess.run(
            [
                self._bash_path,
                "-c",
                "source scripts/sd-ai-command-pack-full-check.sh; full_check_base_ref; printf '\\n'",
            ],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF": "--not-a-ref",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF=--not-a-ref does not resolve",
            result.stdout,
        )
        self.assertEqual(result.stdout.strip().splitlines()[-1], "HEAD")

    def test_full_check_script_does_not_retry_gito_non_rate_limit_trace(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-full-check-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito attempt %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "printf 'A traceback mentioned provider rate limiting docs.\\n'\n"
            "printf 'Docs mention `ClientError: 429` or `Slow down`.\\n'\n"
            "printf 'ClientError: 404 Not Found\\n'\n"
            "exit 1\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT": "0",
                "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF": "HEAD",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_MAX_ATTEMPTS": "2",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_RETRY_DELAY_SECONDS": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Gito attempt 1/2", result.stdout)
        self.assertNotIn("Gito appears rate-limited", result.stdout)
        self.assertNotIn("Gito attempt 2/2", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("gito attempt"), 1, log)

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
            "if [ \"${1:-}\" != \"--\" ]; then\n"
            "  printf 'missing -- classifier delimiter: %s\\n' \"${1:-}\" >&2\n"
            "  exit 9\n"
            "fi\n"
            "shift\n"
            "printf '%s\\n' \"$@\" > classifier-args.log\n"
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
        (root / "-leading-dash.md").write_text("dash-prefixed path\n", encoding="utf-8")

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
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
        classifier_args = (root / "classifier-args.log").read_text(encoding="utf-8")
        self.assertIn("docs/local.md\n", classifier_args)
        self.assertIn("-leading-dash.md\n", classifier_args)
        self.assertIn("app_required=true", result.stdout)
        self.assertIn("fixture_count=", result.stdout)

    def test_full_check_script_routes_legacy_ci_classifier_to_file_list(
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

        legacy_classifier = root / "scripts/classify_ci_changes.sh"
        legacy_classifier.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = \"--\" ]; then\n"
            "  printf 'legacy classifier should not receive --\\n' >&2\n"
            "  exit 99\n"
            "fi\n"
            "cat \"$1\" > legacy-classifier-paths.log\n"
            "printf 'legacy_classifier=true\\n'\n",
            encoding="utf-8",
        )
        legacy_classifier.chmod(0o755)
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs/local.md").write_text("local change\n", encoding="utf-8")

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
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
        self.assertIn("Using legacy scripts/classify_ci_changes.sh", result.stdout)
        self.assertIn("Running legacy scripts/classify_ci_changes.sh", result.stdout)
        self.assertNotIn("legacy classifier should not receive --", result.stdout)
        self.assertIn("legacy_classifier=true", result.stdout)
        paths = (root / "legacy-classifier-paths.log").read_text(encoding="utf-8")
        self.assertIn("docs/local.md\n", paths)

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
        (root / "scripts/sd-ai-command-pack-review-preflight.mjs").unlink()

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT": "required",
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
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
            "Review preflight is required but no command is configured and neither "
            "scripts/sd-ai-command-pack-review-preflight.mjs nor "
            "scripts/check-review-preflight.mjs exists",
            result.stdout,
        )

    def test_review_preflight_exports_reusable_helpers(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        result = subprocess.run(
            [
                node,
                "--input-type=module",
                "-e",
                """
import assert from 'node:assert/strict';
import {
  copiedTemplateKind,
  extractDocumentationPathReferences,
  parseNumstat,
  parseJournalSessionsFromText,
  parseWorkspaceIndexSessionsFromText,
  shouldCheckDocumentationPathReference,
  validateTrellisJournalSessions,
} from './scripts/sd-ai-command-pack-review-preflight.mjs';

assert.equal(copiedTemplateKind('.trellis/scripts/get_context.py'), 'trellis');
assert.equal(copiedTemplateKind('.zcode/agents/trellis-check.md'), 'trellis');
assert.equal(copiedTemplateKind('.agents/skills/sd-review-pr/SKILL.md'), 'sd-ai-command-pack');
assert.equal(copiedTemplateKind('.qoder/commands/sd-review-pr.md'), 'sd-ai-command-pack');
assert.equal(copiedTemplateKind('scripts/sd-ai-command-pack-review-scope.sh'), 'sd-ai-command-pack');
assert.deepEqual(parseNumstat('1\\t2\\tsrc/file\\tname.js\\0'), [
  { added: 1, deleted: 2, path: 'src/file\\tname.js' },
]);
assert.deepEqual(parseNumstat('3\\t4\\t\\0old\\tname.js\\0new\\tname.js\\0'), [
  { added: 3, deleted: 4, path: 'new\\tname.js' },
]);
assert.deepEqual(
  extractDocumentationPathReferences('docs/guide.md', 'See `docs/current.md` and [missing](../missing.md).').map((item) => item.target),
  ['../missing.md', 'docs/current.md'],
);
assert.equal(shouldCheckDocumentationPathReference('docs/guide:section.md'), true);
assert.equal(shouldCheckDocumentationPathReference('.sd-ai-command-pack/installed-targets.txt'), false);
assert.equal(shouldCheckDocumentationPathReference('.sd-ai-command-pack/local-only.txt'), false);
assert.equal(shouldCheckDocumentationPathReference('.sd-ai-command-pack/pr-body-scope.json'), false);
assert.equal(shouldCheckDocumentationPathReference('.sd-ai-command-pack/review-preflight.json'), false);
assert.equal(shouldCheckDocumentationPathReference('.trellis/.developer'), false);
assert.equal(shouldCheckDocumentationPathReference('.trellis/.template-hashes.json'), false);
assert.equal(shouldCheckDocumentationPathReference('docs/TRELLIS_REVIEW_PR_PACK.md'), false);
assert.equal(shouldCheckDocumentationPathReference('docs/repomix-map.md'), false);
assert.equal(shouldCheckDocumentationPathReference('docs/review-learnings.md'), false);
assert.equal(shouldCheckDocumentationPathReference('package.json'), false);
assert.equal(shouldCheckDocumentationPathReference('https://example.com/docs.md'), false);
assert.equal(shouldCheckDocumentationPathReference('obsidian://open?vault=Repo'), false);
const journal = parseJournalSessionsFromText('.trellis/workspace/dev/journal-1.md', [
  '## Session 1: Done',
  '### Status',
  '- [OK] **Completed**',
  '### Main Changes',
  '(Add details)',
  '### Git Commits',
  '- abcdef1',
].join('\\n'));
const index = parseWorkspaceIndexSessionsFromText('.trellis/workspace/dev/index.md', '| 1 | Done | Completed | 1234567 | note |\\n');
const validation = validateTrellisJournalSessions({
  developerRelative: '.trellis/workspace/dev',
  indexFile: '.trellis/workspace/dev/index.md',
  indexSessions: index,
  journalSessions: journal,
});
assert.equal(validation.completedSessions, 1);
assert.ok(validation.failures.some((failure) => failure.includes('(Add details)')));
assert.ok(validation.failures.some((failure) => failure.includes('commits `1234567` do not match')));
""",
            ],
            cwd=PACK_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_review_preflight_script_detects_trellis_journal_drift(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        workspace = root / ".trellis/workspace/dev"
        workspace.mkdir(parents=True)
        (workspace / "journal-1.md").write_text(
            "\n".join(
                [
                    "## Session 1: Guard fixture",
                    "### Status",
                    "**Completed**",
                    "### Main Changes",
                    "(Add details)",
                    "### Testing",
                    "(Add test results)",
                    "### Git Commits",
                    "- abcdef1",
                ]
            ),
            encoding="utf-8",
        )
        (workspace / "index.md").write_text(
            "| Session | Title | Status | Commits | Notes |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | Guard fixture | Completed | 1234567 | done |\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("completed Session 1 still contains placeholder (Add details)", result.stdout)
        self.assertIn("completed Session 1 still contains placeholder (Add test results)", result.stdout)
        self.assertIn("commits `1234567` do not match", result.stdout)

    def test_review_preflight_allows_configured_linux_service_users(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "docs/service.md").write_text(
            "Use `/home/service-user/app` for the service account.\n",
            encoding="utf-8",
        )
        config = root / ".sd-ai-command-pack/review-preflight.json"
        config.write_text(
            '{"allowedLinuxHomeUsers":["service-user"]}\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("personal absolute paths", result.stdout)

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
        self.assertNotIn("legacy pack reference remains", result.stdout)
        self.assertNotIn("legacy pack target remains", result.stdout)

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

    def test_install_drops_gitignored_anchor_entries_without_git(self) -> None:
        root = self.make_repo(".claude")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        shutil.rmtree(root / ".claude")
        gitignore = root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + ".claude/\n",
            encoding="utf-8",
        )

        # Without git the ignore status cannot be confirmed, so preservation
        # fails closed and the entries drop.
        result = self.run_install(root, extra_env={"PATH": ""})

        self.assertEqual(result.returncode, 0, result.stdout)
        receipt_text = (root / install.INSTALLED_TARGETS_FILE).read_text(encoding="utf-8")
        self.assertNotIn(".claude/commands/sd/start.md", receipt_text)
        self.assertNotIn("kept-in-receipt", result.stdout)

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

    def _seed_trellis_session_tooling(self, root: Path) -> None:
        shutil.copytree(
            PACK_ROOT / ".trellis/scripts",
            root / ".trellis/scripts",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        result = subprocess.run(
            [sys.executable, ".trellis/scripts/init_developer.py", "tester"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_record_session_wrapper_writes_complete_entry(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        (root / "feature.txt").write_text("hi\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "feat: add feature file")
        commit_hash = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

        # Dirty the bootstrap journal AND plant a second modified journal:
        # the before/after delta is then empty and two candidates remain,
        # so detection must disambiguate via the new entry's title.
        pre_journal = next((root / ".trellis/workspace").glob("*/journal-*.md"))
        pre_journal.write_text(
            pre_journal.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        # journal-0 sorts below the active part, so Trellis keeps writing
        # to journal-1 while the wrapper sees two modified candidates.
        decoy = pre_journal.parent / "journal-0.md"
        decoy.write_text("# Journal - tester (Part 0)\n", encoding="utf-8")

        result = run(
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Demo session",
            "--summary",
            "Did the demo work.",
            "--commit",
            commit_hash,
            "--change",
            "added the feature file",
            "--change",
            "- kept the docs current",
            "--test",
            "unit suite green",
            "--test",
            "  [WARN] flaky case quarantined",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        entry = pre_journal.read_text(encoding="utf-8")
        self.assertNotIn("Demo session", decoy.read_text(encoding="utf-8"))
        self.assertIn("feat: add feature file", entry)
        self.assertIn("- added the feature file", entry)
        self.assertIn("- kept the docs current", entry)
        self.assertIn("- [OK] unit suite green", entry)
        self.assertIn("- [WARN] flaky case quarantined", entry)
        self.assertNotIn("-  [WARN]", entry)
        self.assertNotIn("[OK] [WARN]", entry)
        self.assertNotIn("(Add details)", entry)
        self.assertNotIn("(Add test results)", entry)
        self.assertNotIn("(see git log)", entry)
        last_message = run("git", "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(last_message, "chore: record journal")
        committed = run("git", "show", "--name-only", "--format=", "HEAD").stdout
        self.assertIn("journal-1.md", committed)
        self.assertNotIn("journal-0.md", committed)

    def test_record_session_wrapper_prefers_current_branch_over_task_metadata(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        run("git", "branch", "-m", "feature/current")

        task_dir = root / ".trellis/tasks/07-05-demo"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.json").write_text(
            json.dumps(
                {
                    "title": "Demo task",
                    "status": "in_progress",
                    "package": None,
                    "branch": "task/stale",
                    "base_branch": "main",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        sessions_dir = root / ".trellis/.runtime/sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "session.json").write_text(
            json.dumps(
                {
                    "current_task": ".trellis/tasks/07-05-demo",
                    "platform": "test",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: seed task")

        result = run(
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Branch session",
            "--summary",
            "Recorded with current branch.",
            "--change",
            "captured branch context",
            "--test",
            "branch assertion green",
            "--no-commit",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        journals = sorted(
            (root / ".trellis/workspace").glob("*/journal-*.md")
        )
        self.assertEqual(len(journals), 1)
        entry = journals[0].read_text(encoding="utf-8")
        index = journals[0].with_name("index.md").read_text(encoding="utf-8")
        self.assertIn("**Branch**: `feature/current`", entry)
        self.assertNotIn("task/stale", entry)
        self.assertIn("`feature/current` |", index)
        self.assertNotIn("`task/stale`", index)

    def test_record_session_wrapper_fails_fast_on_unknown_hash(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-record-session.py",
                "--title",
                "Demo",
                "--summary",
                "S",
                "--commit",
                "deadbeef",
                "--change",
                "c",
                "--test",
                "t",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("unknown commit hash: deadbeef", result.stdout)
        # Fail-fast means add_session never ran: the bootstrap journal
        # skeleton exists but carries no session entry.
        for journal in (root / ".trellis/workspace").glob("*/journal-*.md"):
            self.assertNotIn(
                "## Session", journal.read_text(encoding="utf-8")
            )

    def test_record_session_wrapper_rejects_bad_commit_arguments(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def record(commit_arg: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [
                    sys.executable,
                    "scripts/sd-ai-command-pack-record-session.py",
                    "--title",
                    "Demo",
                    "--summary",
                    "S",
                    f"--commit={commit_arg}",
                    "--change",
                    "c",
                    "--test",
                    "t",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        result = record("--all")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("invalid commit hash: --all", result.stdout)

        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        ).stdout.strip()
        result = record(f"{head},{head}")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn(f"duplicate commit hash: {head}", result.stdout)

    def test_record_session_wrapper_accepts_empty_commit_subject(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: seed trellis tooling")
        run(
            "git", "commit", "-q", "--allow-empty",
            "--allow-empty-message", "-m", "",
        )
        commit_hash = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

        result = run(
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Empty subject session",
            "--summary",
            "S",
            "--commit",
            commit_hash,
            "--change",
            "c",
            "--test",
            "t",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        journals = sorted(
            (root / ".trellis/workspace").glob("*/journal-*.md")
        )
        self.assertEqual(len(journals), 1)
        entry = journals[0].read_text(encoding="utf-8")
        self.assertIn(f"| `{commit_hash}` | (empty subject) |", entry)

    def test_record_session_wrapper_tolerates_prefilled_trellis_variant(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        # Emulate the Trellis variant that resolves commit subjects itself
        # and seeds a different Testing default (loadsmith's add_session).
        variant = root / ".trellis/scripts/add_session.py"
        source = variant.read_text(encoding="utf-8")
        self.assertIn("(see git log)", source)
        self.assertIn("- [OK] (Add test results)", source)
        source = source.replace("(see git log)", "prefilled subject")
        source = source.replace(
            "- [OK] (Add test results)",
            "- Validation not recorded for this session.",
        )
        variant.write_text(source, encoding="utf-8")

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        # Track the seeded workspace so the wrapper's status scan sees the
        # journal add_session modifies rather than one untracked directory.
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: seed trellis tooling")

        (root / "feature.txt").write_text("feature\n", encoding="utf-8")
        run("git", "add", "feature.txt")
        run("git", "commit", "-q", "-m", "feat: add feature file")
        commit_hash = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

        result = run(
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Variant session",
            "--summary",
            "Recorded against a subject-resolving Trellis.",
            "--commit",
            commit_hash,
            "--change",
            "added the feature file",
            "--test",
            "unit suite green",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        journals = sorted(
            (root / ".trellis/workspace").glob("*/journal-*.md")
        )
        self.assertEqual(len(journals), 1)
        entry = journals[0].read_text(encoding="utf-8")
        self.assertIn("feat: add feature file", entry)
        self.assertNotIn("prefilled subject", entry)
        self.assertIn("- [OK] unit suite green", entry)
        self.assertNotIn("Validation not recorded", entry)
        last_message = run("git", "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(last_message, "chore: record journal")

    def test_chore_scope_pre_push_hook_gates_direct_main_pushes(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        tempdir = tempfile.TemporaryDirectory(prefix="sd-pack-hook-test-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        origin = base / "origin.git"
        subprocess.run(
            ["git", "init", "--bare", "-q", str(origin)],
            check=True,
        )
        clone = base / "clone"
        subprocess.run(
            ["git", "clone", "-q", str(origin), str(clone)],
            check=True,
            stderr=subprocess.DEVNULL,
        )

        def run(*args: str, env: dict[str, str] | None = None):
            return subprocess.run(
                args,
                cwd=clone,
                env={**os.environ, **(env or {})},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        run("git", "checkout", "-q", "-b", "main")
        hooks_dir = clone / ".githooks"
        hooks_dir.mkdir()
        shutil.copy2(PACK_ROOT / ".githooks/pre-push", hooks_dir / "pre-push")
        run("git", "config", "core.hooksPath", ".githooks")

        chore = clone / ".trellis/tasks/07-01-demo/prd.md"
        chore.parent.mkdir(parents=True)
        chore.write_text("# demo\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore(task): demo")

        # Creating remote main directly fails closed (no chore baseline).
        result = run("git", "push", "-q", "origin", "main")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("creating remote main", result.stdout)
        result = run(
            "git",
            "push",
            "-q",
            "origin",
            "main",
            env={"SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)

        # With a baseline, chore-only pushes flow.
        chore.write_text("# demo v2\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore(task): demo v2")
        result = run("git", "push", "-q", "origin", "main")
        self.assertEqual(result.returncode, 0, result.stdout)

        (clone / "code.py").write_text("print('hi')\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "feat: code")
        result = run("git", "push", "-q", "origin", "main")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("chore-scope only", result.stdout)
        self.assertIn("code.py", result.stdout)

        result = run(
            "git",
            "push",
            "-q",
            "origin",
            "main",
            env={"SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("bypassed", result.stdout)

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
        self.assertTrue(
            files["scripts/sd-ai-command-pack-full-check.sh"].startswith("sha256:")
        )
        # User-tunable and generated files are never vouched.
        self.assertNotIn(".prism/rules.json", files)
        self.assertNotIn(".gitignore", files)
        self.assertNotIn(".sd-ai-command-pack/installed-targets.txt", files)
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

    def test_install_audit_passes_without_provenance_file(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        # Old installs have no provenance: remove the file and its receipt
        # line and the audit behaves as before 0.5.10.
        (root / install.PROVENANCE_FILE).unlink()
        receipt = root / install.INSTALLED_TARGETS_FILE
        receipt.write_text(
            "".join(
                line
                for line in receipt.read_text(encoding="utf-8").splitlines(
                    keepends=True
                )
                if "provenance.json" not in line
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
            "installed target is missing: .agents/skills/sd-continue/SKILL.md",
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

    def test_force_overwrite_revouches_drifted_target(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        # Drift a vouched script, then force-refresh: the overwrite must be
        # re-vouched with the template hash (single-pass fleet refreshes
        # produce exactly this "overwritten" status for changed files).
        script = root / "scripts/sd-ai-command-pack-review-local.sh"
        script.write_text(
            script.read_text(encoding="utf-8") + "\n# drift\n",
            encoding="utf-8",
        )

        result = self.run_install(root, "--force")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("overwritten", result.stdout)

        template_digest = "sha256:" + hashlib.sha256(
            (PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-local.sh").read_bytes()
        ).hexdigest()
        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(
            provenance["files"]["scripts/sd-ai-command-pack-review-local.sh"],
            template_digest,
        )

        audit = subprocess.run(
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
        self.assertEqual(audit.returncode, 0, audit.stdout)
        self.assertNotIn("drifted from pack", audit.stdout)

    def test_install_ignores_symlinked_provenance(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        provenance = root / install.PROVENANCE_FILE
        real = json.loads(provenance.read_text(encoding="utf-8"))
        target_key = "scripts/sd-ai-command-pack-full-check.sh"
        real_hash = real["files"][target_key]

        bogus = root / ".sd-ai-command-pack/bogus.json"
        bogus.write_text(
            json.dumps({"files": {target_key: "sha256:" + "0" * 64}}) + "\n",
            encoding="utf-8",
        )
        provenance.unlink()
        provenance.symlink_to(bogus.name)

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(provenance.is_symlink())
        rebuilt = json.loads(provenance.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["files"][target_key], real_hash)

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

    def test_review_preflight_accepts_line_suffixed_doc_references(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        (root / "docs/cite.md").write_text(
            "See [the gate](../scripts/sd-ai-command-pack-full-check.sh:12) and\n"
            "`scripts/sd-ai-command-pack-housekeeping.sh:34-56` for details.\n"
            "Also `scripts/sd-ai-command-pack-install-audit.py:7:3` and\n"
            "`scripts/sd-ai-command-pack-review-local.sh:10-20:4`.\n"
            "Broken: `docs/definitely-missing.md:5`.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "references missing path docs/definitely-missing.md:5",
            result.stdout,
        )
        self.assertNotIn("full-check.sh:12", result.stdout)
        self.assertNotIn("housekeeping.sh:34-56", result.stdout)
        self.assertNotIn("install-audit.py:7:3", result.stdout)
        self.assertNotIn("review-local.sh:10-20:4", result.stdout)

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
            elif file.source.suffix == ".mjs":
                self.assert_node_syntax_valid(file.source)
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

    def test_review_learnings_script_negative_offset_regex_is_specific(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_regex_test",
        )

        self.assertIsNotNone(module._NEGATIVE_ARRAY_OFFSET_RE.search("${@: -1}"))
        self.assertIsNotNone(
            module._NEGATIVE_ARRAY_OFFSET_RE.search("${items[@]: -1}")
        )
        self.assertIsNotNone(
            module._NEGATIVE_ARRAY_OFFSET_RE.search("${items[-1]}")
        )
        self.assertIsNone(module._NEGATIVE_ARRAY_OFFSET_RE.search("${VALUE:-1}"))
        self.assertIsNone(module._NEGATIVE_ARRAY_OFFSET_RE.search("${value: -1}"))

    def test_review_learnings_script_extracts_explicit_env_refs_only(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_env_regex_test",
        )

        self.assertEqual(
            module._extract_env_refs(
                'echo "$SD_FOO" "${GH_BAR}" "${SD_DEFAULT:-0}" SD_BARE',
                ("SD", "GH"),
            ),
            {"SD_FOO", "GH_BAR", "SD_DEFAULT"},
        )

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

    def test_review_learnings_script_rejects_malformed_payload_helpers(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_test",
        )

        with self.assertRaisesRegex(TypeError, "expected object"):
            module._as_dict(None)
        with self.assertRaisesRegex(TypeError, "expected list"):
            module._as_list({})

    def test_review_learnings_main_reports_malformed_payload_without_traceback(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_main_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)

        with mock.patch.object(module, "build_local_diff", return_value=""):
            with mock.patch.object(module, "extract_findings", return_value=[]):
                with mock.patch.object(
                    module,
                    "fetch_recent_copilot_comments",
                    side_effect=TypeError("expected list in review learnings payload"),
                ):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        result = module.main(
                            [
                                "--repo-root",
                                tempdir.name,
                                "--github-days",
                                "1",
                            ]
                        )

        self.assertEqual(result, 2)
        self.assertIn("[sd-review-learnings:github]", stderr.getvalue())
        self.assertIn("expected list in review learnings payload", stderr.getvalue())

    def test_review_learnings_script_rejects_invalid_managed_marker_order(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_marker_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name) / "review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:end -->\n"
            "old\n"
            "<!-- sd-review-learnings:start -->\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "invalid order"):
            module.update_target(target, "<!-- sd-review-learnings:start -->\nnew\n<!-- sd-review-learnings:end -->\n", dry_run=False)

    def test_review_learnings_main_reports_invalid_managed_marker_order(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_marker_main_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        target = root / "review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:end -->\n"
            "old\n"
            "<!-- sd-review-learnings:start -->\n",
            encoding="utf-8",
        )

        with mock.patch.object(module, "build_local_diff", return_value=""):
            with mock.patch.object(module, "extract_findings", return_value=[]):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = module.main(
                        [
                            "--repo-root",
                            str(root),
                            "--target",
                            str(target),
                            "--update",
                        ]
                    )

        self.assertEqual(result, 2)
        self.assertIn("[sd-review-learnings:update]", stderr.getvalue())
        self.assertIn("invalid order", stderr.getvalue())

    def test_review_learnings_script_preserves_text_after_managed_block(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_layout_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name) / "review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:start -->\n"
            "old\n"
            "<!-- sd-review-learnings:end -->\n"
            "Human notes stay.\n",
            encoding="utf-8",
        )

        module.update_target(
            target,
            "<!-- sd-review-learnings:start -->\n"
            "new\n"
            "<!-- sd-review-learnings:end -->\n",
            dry_run=False,
        )

        content = target.read_text(encoding="utf-8")
        self.assertIn("<!-- sd-review-learnings:end -->\nHuman notes stay.", content)

    def test_review_learnings_script_skips_incomplete_github_payloads(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_github_payload_test",
        )

        def fake_run_gh_json(args: list[str], repo_root: Path):
            if args[:2] == ["pr", "list"]:
                return [{"number": 1, "title": "PR", "url": "https://example.test/pr/1"}]
            return {"errors": [{"message": "rate limited"}]}

        with mock.patch.object(module, "github_repo_slug", return_value=("owner", "repo")):
            with mock.patch.object(module, "_run_gh_json", fake_run_gh_json):
                comments = module.fetch_recent_copilot_comments(
                    Path("."),
                    days=1,
                    limit=1,
                )

        self.assertEqual(comments, [])

    def test_review_learnings_script_resolves_github_repo_generically(self) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        ).read_text(encoding="utf-8")

        self.assertIn("gh", script)
        self.assertIn("repo", script)
        self.assertIn("nameWithOwner", script)
        self.assertNotIn("answerbook", script)
        self.assertNotIn("mezmo_benchmark", script)

    def test_update_spec_kb_script_builds_gitignored_copy_folder(self) -> None:
        root = self.make_repo()
        self.run_git(root, "remote", "add", "origin", "git@github.com:example/project.git")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        files = {
            "README.md": "# Project\n",
            "AGENTS.md": "# Agent Notes\n",
            "docs/SD_AI_COMMAND_PACK.md": "# SD Pack\n",
            "docs/repomix-map.md": "# Repo Map\n",
            "docs/architecture.md": "# Architecture\n",
            ".trellis/workflow.md": "# Workflow\n",
            ".trellis/config.yaml": "project: test\n",
            ".trellis/spec/backend/index.md": "# Backend Spec\n",
            ".trellis/tasks/07-01-demo/prd.md": "# Demo PRD\n",
            ".trellis/tasks/archive/2026-07/07-00-old/design.md": "# Old Design\n",
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
        self.assertIn("copies:", result.stdout)
        self.assertIn("dashboard: created", result.stdout)
        self.assertIn("llm overview: created", result.stdout)
        self.assertIn("vault copy example:", result.stdout)

        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("dist/\n", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb start", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb end", gitignore)
        self.assertEqual(gitignore.count(".obsidian-kb/"), 1)
        expected_copies = {
            "README.md": "Repository Overview/README.md",
            "AGENTS.md": "Agent and Platform Guidance/AGENTS.md",
            "docs/repomix-map.md": "Repository Maps/repomix-map.md",
            "docs/architecture.md": "Architecture and Decisions/architecture.md",
            ".trellis/workflow.md": "Workflow and Configuration/workflow.md",
            ".trellis/config.yaml": "Workflow and Configuration/config.yaml",
            ".trellis/spec/backend/index.md": "Backend Specs/index.md",
            ".trellis/tasks/07-01-demo/prd.md": (
                "Task Documentation/07-01-demo-prd.md"
            ),
            ".trellis/tasks/archive/2026-07/07-00-old/design.md": (
                "Task Documentation/archive-2026-07-07-00-old-design.md"
            ),
            ".agents/skills/sd-review-pr/SKILL.md": (
                "Agent and Platform Guidance/codex-sd-review-pr.md"
            ),
            "package.json": "Project Manifests/package.json",
            "packages/api/README.md": "Package Documentation/packages-api-README.md",
        }
        for relative_path, kb_relative_path in expected_copies.items():
            copied = root / ".obsidian-kb" / kb_relative_path
            self.assertTrue(copied.is_file(), copied)
            self.assertFalse(copied.is_symlink(), copied)
            self.assertEqual(
                copied.read_bytes(),
                (root / relative_path).read_bytes(),
            )
        for copied_path in (root / ".obsidian-kb").rglob("*"):
            relative = copied_path.relative_to(root / ".obsidian-kb")
            self.assertFalse(
                any(part.startswith(".") for part in relative.parts),
                relative.as_posix(),
            )
            self.assertNotIn("trellis", relative.as_posix().lower())

        dashboard = root / ".obsidian-kb" / f"Dashboard - {root.name}.md"
        self.assertTrue(dashboard.is_file())
        dashboard_text = dashboard.read_text(encoding="utf-8")
        self.assertIn(f"# Dashboard - {root.name}", dashboard_text)
        self.assertIn(
            "GitHub: [example/project](https://github.com/example/project)",
            dashboard_text,
        )
        self.assertIn(
            f"[LLM-KB - {root.name}.md](LLM-KB%20-%20{root.name}.md)",
            dashboard_text,
        )
        self.assertIn("self-contained copy", dashboard_text)
        self.assertIn(
            "[README.md](Repository%20Overview/README.md) - Repository "
            "overview and primary entrypoint.",
            dashboard_text,
        )
        self.assertIn(
            "[AGENTS.md](Agent%20and%20Platform%20Guidance/AGENTS.md) - "
            "Project instructions for AI coding agents.",
            dashboard_text,
        )
        self.assertIn(
            "[codex-sd-review-pr.md]"
            "(Agent%20and%20Platform%20Guidance/codex-sd-review-pr.md)",
            dashboard_text,
        )
        self.assertIn("## Repository Overview", dashboard_text)
        self.assertIn("## Agent and Platform Guidance", dashboard_text)
        self.assertIn("## Pack Documentation", dashboard_text)
        self.assertIn("## Architecture and Decisions", dashboard_text)
        self.assertIn("## Workflow and Configuration", dashboard_text)
        self.assertIn("## Task Documentation", dashboard_text)
        self.assertIn("## Backend Specs", dashboard_text)
        self.assertIn("## Repository Maps", dashboard_text)
        self.assertIn("## Project Manifests", dashboard_text)
        self.assertIn("## Package Documentation", dashboard_text)
        self.assertNotIn("## Repository root", dashboard_text)
        self.assertNotIn("## docs", dashboard_text)
        self.assertNotIn("## .trellis/spec/backend", dashboard_text)
        self.assertNotIn("## Trellis", dashboard_text)
        self.assertNotIn(".trellis", dashboard_text)
        self.assertIn("[README.md](Repository%20Overview/README.md)", dashboard_text)
        self.assertIn(
            "[repomix-map.md](Repository%20Maps/repomix-map.md)",
            dashboard_text,
        )
        self.assertIn(
            "[index.md](Backend%20Specs/index.md)",
            dashboard_text,
        )
        self.assertIn(
            "[07-01-demo-prd.md](Task%20Documentation/07-01-demo-prd.md)",
            dashboard_text,
        )
        self.assertFalse((root / ".obsidian-kb/Dashboard.md").exists())
        self.assertFalse((root / ".obsidian-kb/LLM-KB.md").exists())

        overview = root / ".obsidian-kb" / f"LLM-KB - {root.name}.md"
        self.assertTrue(overview.is_file())
        overview_text = overview.read_text(encoding="utf-8")
        self.assertIn("# LLM Knowledge Base", overview_text)
        self.assertIn(
            "GitHub: [example/project](https://github.com/example/project)",
            overview_text,
        )
        self.assertIn("Copied knowledge files:", overview_text)
        self.assertIn("[README.md](Repository%20Overview/README.md)", overview_text)
        self.assertIn(
            "[SD_AI_COMMAND_PACK.md](Pack%20Documentation/SD_AI_COMMAND_PACK.md)",
            overview_text,
        )
        self.assertIn(
            "[workflow.md](Workflow%20and%20Configuration/workflow.md)",
            overview_text,
        )
        self.assertIn("### Repository Overview", overview_text)
        self.assertIn("### Agent and Platform Guidance", overview_text)
        self.assertIn("### Pack Documentation", overview_text)
        self.assertIn("### Task Documentation", overview_text)
        self.assertIn("### Backend Specs", overview_text)
        self.assertNotIn("### Repository root", overview_text)
        self.assertNotIn("### docs", overview_text)
        self.assertNotIn("### Trellis", overview_text)
        self.assertNotIn("](.trellis", overview_text)

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
        self.assertIn("stale generated entries removed: 1", result.stdout)
        self.assertIn("dashboard: updated", result.stdout)
        self.assertIn("llm overview: updated", result.stdout)
        self.assertFalse(
            (root / ".obsidian-kb/Repository Maps/repomix-map.md").exists()
        )
        self.assertNotIn(
            "repomix-map.md",
            dashboard.read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "repomix-map.md",
            overview.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (root / ".gitignore").read_text(encoding="utf-8").count(".obsidian-kb/"),
            1,
        )

    def test_update_spec_kb_derives_github_repo_url_from_remote(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
            "sd_ai_command_pack_update_spec_kb_remote_test",
        )

        cases = {
            "git@github.com:owner/repo.git": "https://github.com/owner/repo",
            "ssh://git@github.com/owner/repo.git": "https://github.com/owner/repo",
            "https://github.com/owner/repo.git": "https://github.com/owner/repo",
            "http://github.com/owner/repo": "https://github.com/owner/repo",
        }
        for remote, expected in cases.items():
            with self.subTest(remote=remote):
                self.assertEqual(
                    module.github_repository_url_from_remote(remote),
                    expected,
                )

        self.assertIsNone(module.github_repository_url_from_remote(None))
        self.assertIsNone(module.github_repository_url_from_remote(""))
        self.assertIsNone(
            module.github_repository_url_from_remote("git@example.com:owner/repo.git")
        )

    def test_update_spec_kb_replaces_legacy_generated_dashboard_name(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        legacy_dashboard = root / ".obsidian-kb/Dashboard.md"
        legacy_dashboard.parent.mkdir(parents=True, exist_ok=True)
        legacy_dashboard.write_text(
            "<!-- SD-AI-COMMAND-PACK:OBSIDIAN-KB-DASHBOARD -->\n"
            "# Obsidian KB Dashboard\n",
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
        self.assertIn("stale generated entries removed: 1", result.stdout)
        self.assertFalse(legacy_dashboard.exists())
        dashboard = root / ".obsidian-kb" / f"Dashboard - {root.name}.md"
        self.assertTrue(dashboard.is_file())
        self.assertIn(
            f"# Dashboard - {root.name}",
            dashboard.read_text(encoding="utf-8"),
        )

    def test_update_spec_kb_replaces_legacy_generated_overview_name(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        legacy_overview = root / ".obsidian-kb/LLM-KB.md"
        legacy_overview.parent.mkdir(parents=True, exist_ok=True)
        legacy_overview.write_text(
            "<!-- SD-AI-COMMAND-PACK:LLM-KB-OVERVIEW -->\n"
            "# LLM Knowledge Base\n",
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
        self.assertIn("stale generated entries removed: 1", result.stdout)
        self.assertFalse(legacy_overview.exists())
        overview = root / ".obsidian-kb" / f"LLM-KB - {root.name}.md"
        self.assertTrue(overview.is_file())
        self.assertIn(
            "# LLM Knowledge Base",
            overview.read_text(encoding="utf-8"),
        )

    def test_update_spec_kb_preserves_user_notes_outside_managed_categories(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        initial = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(initial.returncode, 0, initial.stdout)

        custom_note = root / ".obsidian-kb/My Notes.md"
        custom_note.write_text("keep me\n", encoding="utf-8")
        custom_asset = root / ".obsidian-kb/Attachments/diagram.txt"
        custom_asset.parent.mkdir(parents=True)
        custom_asset.write_text("asset\n", encoding="utf-8")
        custom_legacy_name = root / ".obsidian-kb/Dashboard.md"
        custom_legacy_name.write_text("custom dashboard note\n", encoding="utf-8")

        check_result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--check",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(check_result.returncode, 0, check_result.stdout)
        self.assertIn("conflicts: none", check_result.stdout)
        self.assertNotIn("stale generated entries would be removed", check_result.stdout)

        refresh = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(refresh.returncode, 0, refresh.stdout)
        self.assertEqual(custom_note.read_text(encoding="utf-8"), "keep me\n")
        self.assertEqual(custom_asset.read_text(encoding="utf-8"), "asset\n")
        self.assertEqual(
            custom_legacy_name.read_text(encoding="utf-8"),
            "custom dashboard note\n",
        )

    def test_update_spec_kb_quotes_vault_copy_example(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
            "sd_ai_command_pack_update_spec_kb_quote_test",
        )
        root = Path("/tmp/repo with spaces")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.report_kb_state(
                root=root,
                mode=None,
                gitignore_state="present",
                copies=0,
                stale=0,
                dashboard_state="present",
                conflicts=[],
            )

        self.assertIn("cp -R '/tmp/repo with spaces/.obsidian-kb/.'", output.getvalue())

    def test_update_spec_kb_escapes_repo_name_in_overview_link_label(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "repo[docs]"
        root.mkdir()
        (root / ".trellis").mkdir()
        (root / ".trellis/config.yaml").write_text("# test\n", encoding="utf-8")
        self.run_git(root, "init")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        dashboard = root / ".obsidian-kb/Dashboard - repo[docs].md"
        self.assertTrue(dashboard.is_file())
        self.assertIn(
            "[LLM-KB - repo\\[docs\\].md](LLM-KB%20-%20repo%5Bdocs%5D.md)",
            dashboard.read_text(encoding="utf-8"),
        )

    def test_update_spec_kb_replaces_legacy_generated_symlink_with_copy(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        legacy_link = root / ".obsidian-kb/README.md"
        legacy_link.parent.mkdir(parents=True)
        legacy_link.symlink_to("../README.md")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("copies:", result.stdout)
        self.assertIn("conflicts: none", result.stdout)
        self.assertFalse(legacy_link.exists())
        copy = root / ".obsidian-kb/Repository Overview/README.md"
        self.assertTrue(copy.is_file())
        self.assertFalse(copy.is_symlink())
        self.assertEqual(copy.read_text(encoding="utf-8"), "# Project\n")

    def test_update_spec_kb_converts_existing_symlink_tree_to_category_copies(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        files = {
            "README.md": "# Project\n",
            "AGENTS.md": "# Agent Notes\n",
            ".trellis/spec/backend/index.md": "# Backend Spec\n",
        }
        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        legacy_root = root / ".obsidian-kb"
        legacy_root.mkdir()
        (legacy_root / "README.md").symlink_to("../README.md")
        (legacy_root / "AGENTS.md").symlink_to("../AGENTS.md")
        legacy_spec = legacy_root / ".trellis/spec/backend/index.md"
        legacy_spec.parent.mkdir(parents=True)
        legacy_spec.symlink_to("../../../../.trellis/spec/backend/index.md")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("legacy symlinks converted: 3", result.stdout)
        self.assertIn("conflicts: none", result.stdout)
        self.assertFalse((legacy_root / "README.md").exists())
        self.assertFalse((legacy_root / "AGENTS.md").exists())
        self.assertFalse((legacy_root / ".trellis").exists())
        expected_copies = {
            "Repository Overview/README.md": "# Project\n",
            "Agent and Platform Guidance/AGENTS.md": "# Agent Notes\n",
            "Backend Specs/index.md": "# Backend Spec\n",
        }
        for relative_path, content in expected_copies.items():
            copy = legacy_root / relative_path
            self.assertTrue(copy.is_file(), copy)
            self.assertFalse(copy.is_symlink(), copy)
            self.assertEqual(copy.read_text(encoding="utf-8"), content)
        self.assertEqual(
            [
                path
                for path in legacy_root.rglob("*")
                if path.is_symlink()
            ],
            [],
        )

    def test_update_spec_kb_help_is_read_only(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--help",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("usage:", result.stdout)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--check", result.stdout)
        self.assertFalse((root / ".obsidian-kb").exists())

    def test_update_spec_kb_dry_run_does_not_write_files(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".gitignore").write_text("dist/\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertIn("planned copies:", result.stdout)
        self.assertFalse((root / ".obsidian-kb").exists())
        self.assertEqual((root / ".gitignore").read_text(encoding="utf-8"), "dist/\n")

    def test_update_spec_kb_check_detects_and_accepts_current_state(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        stale = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--check",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(stale.returncode, 1, stale.stdout)
        self.assertIn("mode: check", stale.stdout)
        self.assertIn("Repository Overview/README.md is missing", stale.stdout)

        refresh = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(refresh.returncode, 0, refresh.stdout)

        current = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--check",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(current.returncode, 0, current.stdout)
        self.assertIn("conflicts: none", current.stdout)

    def test_update_spec_kb_does_not_overwrite_custom_dashboard(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        dashboard = root / ".obsidian-kb" / f"Dashboard - {root.name}.md"
        dashboard.parent.mkdir(parents=True)
        dashboard.write_text("custom dashboard\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("dashboard: conflict", result.stdout)
        self.assertIn(
            f"Dashboard - {root.name}.md exists and is not generated by this tool",
            result.stdout,
        )
        self.assertEqual(dashboard.read_text(encoding="utf-8"), "custom dashboard\n")
        copy = root / ".obsidian-kb/Repository Overview/README.md"
        self.assertTrue(copy.is_file())
        self.assertFalse(copy.is_symlink())

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
        copy = root / ".obsidian-kb/Repository Overview/README.md"
        self.assertTrue(copy.is_file())
        self.assertFalse(copy.is_symlink())

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

    def test_docs_show_mixed_tooling_and_ci_review_pr_body_scope_example(
        self,
    ) -> None:
        for doc_path in [
            install.ROOT / "README.md",
            install.ROOT / "docs/SD_AI_COMMAND_PACK.md",
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md",
        ]:
            content = doc_path.read_text(encoding="utf-8")
            self.assertIn("Tooling/generated scope:", content, doc_path)
            self.assertIn("CI/review scope:", content, doc_path)
            self.assertIn("command invocation", content, doc_path)
            self.assertIn("SD_AI_COMMAND_PACK_SCOPE_PR_BODY", content, doc_path)
            self.assertIn("REVIEW_PREFLIGHT_PR_BODY", content, doc_path)

    def test_pr_body_scope_script_classifies_review_local_as_ci_review(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        changed_files = root / "changed-files.txt"
        changed_files.write_text(
            "scripts/sd-ai-command-pack-review-local.sh\n"
            "scripts/sd-ai-command-pack-review-learnings.py\n"
            ".qoder/commands/sd-review-local.md\n",
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
        self.assertIn("detected Tooling/generated scope", result.stdout)
        self.assertIn("detected CI/review scope", result.stdout)
        self.assertIn(".qoder/commands/sd-review-local.md", result.stdout)
        self.assertIn("scripts/sd-ai-command-pack-review-local.sh", result.stdout)
        self.assertIn("scripts/sd-ai-command-pack-review-learnings.py", result.stdout)

    def test_pr_body_scope_script_merges_matching_configured_scope(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        config = root / ".sd-ai-command-pack/pr-body-scope.json"
        config.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "label": "CI/review scope",
                            "headings": [
                                "CI/review scope:",
                                "CI scope:",
                                "Workflow scope:",
                            ],
                            "patterns": ["scripts/local-review-wrapper.py"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        changed_files = root / "changed-files.txt"
        changed_files.write_text(
            ".github/workflows/test.yml\n"
            "scripts/local-review-wrapper.py\n",
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
        self.assertEqual(result.stdout.count("detected CI/review scope paths:"), 1)
        self.assertIn(".github/workflows/test.yml", result.stdout)
        self.assertIn("scripts/local-review-wrapper.py", result.stdout)

    def test_pr_body_scope_merge_rules_dedupes_patterns_in_order(self) -> None:
        module_path = install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py"
        module = self.load_module_from_path(
            module_path,
            "sd_ai_command_pack_pr_body_scope_test",
        )

        headings = ("CI/review scope:", "CI scope:")
        merged = module._merge_rules(
            (
                module.ScopeRule(
                    label="CI/review scope",
                    headings=headings,
                    patterns=("scripts/a.sh", "scripts/b.sh"),
                ),
                module.ScopeRule(
                    label="CI/review scope",
                    headings=headings,
                    patterns=("scripts/b.sh", "scripts/c.sh"),
                ),
            )
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0].patterns,
            ("scripts/a.sh", "scripts/b.sh", "scripts/c.sh"),
        )

    def test_pr_body_scope_double_star_patterns_match_nested_paths(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_match_test",
        )

        self.assertTrue(module._matches_pattern("src", "src/**"))
        self.assertTrue(module._matches_pattern("src/file.py", "src/**"))
        self.assertTrue(module._matches_pattern("src/nested/file.py", "src/**"))
        self.assertTrue(module._matches_pattern("src/file.py", "./src/**"))
        self.assertFalse(module._matches_pattern("other/src/file.py", "src/**"))
        self.assertEqual(module._normalize_path("./src\\file.py"), "src/file.py")

    def test_pr_body_scope_split_changed_files_strips_path_whitespace(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_split_test",
        )

        self.assertEqual(
            module._split_changed_files(
                "  leading.py\ntrailing.py  \n\n./src\\file.py\na path/file name.py\n"
            ),
            ["leading.py", "trailing.py", "src/file.py", "a path/file name.py"],
        )

    def test_pr_body_scope_config_rejects_empty_headings(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_config_shape_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-pr-body-scope-test-")
        self.addCleanup(tempdir.cleanup)
        config = Path(tempdir.name) / "scope.json"
        config.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "label": "Runtime/server scope",
                            "headings": [],
                            "patterns": ["src/**"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        rules, error = module._load_config_rules(config)

        self.assertEqual(rules, ())
        self.assertIsNotNone(error)
        self.assertIn("non-empty list of non-empty string headings", error)

    def test_pr_body_scope_config_can_include_installed_targets(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_installed_targets_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-pr-body-scope-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        (root / ".sd-ai-command-pack").mkdir()
        (root / ".sd-ai-command-pack/installed-targets.txt").write_text(
            "custom/generated.md\n",
            encoding="utf-8",
        )
        config = root / "scope.json"
        config.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "label": "Custom generated scope",
                            "headings": ["Custom generated scope:"],
                            "patterns": ["docs/custom.md"],
                            "include_installed_targets": True,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        rules, error = module._rules_for_repo(root, config)

        self.assertIsNone(error)
        custom_rule = next(
            rule for rule in rules if rule.label == "Custom generated scope"
        )
        self.assertIn("custom/generated.md", custom_rule.patterns)

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

    def test_pr_body_scope_script_accepts_legacy_body_env_and_classifier_name(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        changed_files = root / "changed-files.txt"
        changed_files.write_text("scripts/classify_ci_changes.sh\n", encoding="utf-8")

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
                "REVIEW_PREFLIGHT_PR_BODY": (
                    "CI/review scope: migrate classifier compatibility."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("detected CI/review scope", result.stdout)
        self.assertIn("PR body scope sections cover", result.stdout)

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
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
                # The housekeeping edit above is exactly the drift the
                # provenance audit flags; this test exercises the PR-body
                # scope stage, so skip the audit (covered by the dedicated
                # provenance tests).
                "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0",
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

    def test_review_scope_script_accepts_legacy_pr_body_env(self) -> None:
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
                "REVIEW_PREFLIGHT_PR_BODY": (
                    "Tooling/generated scope: refreshed copied pack docs."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("REVIEW_PREFLIGHT_PR_BODY is deprecated", result.stdout)
        self.assertIn("Tooling/generated review-scope files changed", result.stdout)

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
            "does not include a recognized tooling/generated scope section",
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
                "PATH": os.environ["PATH"],
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
                "PATH": os.environ["PATH"],
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
                "SD_AI_COMMAND_PACK_SCOPE_PR_BODY": "Updates behavior.",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "provided PR body does not include a recognized tooling/generated scope section",
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
        self.assertEqual(prism_rules_files[0].install, install.IF_NOT_EXISTS)

    def test_prism_rules_schema_template_is_installed(self) -> None:
        schema_files = [
            file
            for file in self.shared_manifest_files("config")
            if file.target == Path(".prism/rules.schema.json")
        ]

        self.assertEqual(len(schema_files), 1)
        schema = json.loads(schema_files[0].source.read_text(encoding="utf-8"))
        self.assertIn("$schema", schema)
        self.assertIn("severityOverrides", schema["properties"])

    def test_gito_config_templates_are_installed(self) -> None:
        config_files = [
            file
            for file in self.shared_manifest_files("config")
            if file.target == Path(".gito/config.toml")
        ]
        env_files = [
            file
            for file in self.shared_manifest_files("config")
            if file.target == Path(".gito/sd-ai-command-pack.env")
        ]

        self.assertEqual(len(config_files), 1)
        self.assertEqual(config_files[0].install, install.IF_NOT_EXISTS)
        config_text = config_files[0].source.read_text(encoding="utf-8")
        self.assertIn("exclude_files = [", config_text)
        self.assertIn('".trellis/**"', config_text)
        self.assertIn("[prompt_vars]", config_text)
        self.assert_no_secret_markers(config_files[0].source)

        self.assertEqual(len(env_files), 1)
        self.assertEqual(env_files[0].install, install.ALWAYS_INSTALL)
        env_text = env_files[0].source.read_text(encoding="utf-8")
        self.assertIn("MAX_CONCURRENT_TASKS=4", env_text)
        self.assert_no_secret_markers(env_files[0].source)

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
        self.assertIn('COMMENT_DATABASE_ID="<review comment database id>"', skill)
        self.assertIn(
            '"repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments/$COMMENT_DATABASE_ID/replies"',
            skill,
        )
        self.assertIn('THREAD_NODE_ID="<review thread node id>"', skill)
        self.assertIn('-F threadId="$THREAD_NODE_ID"', skill)
        self.assertNotIn("{comment_database_id}", skill)
        self.assertNotIn('-F threadId="THREAD_NODE_ID"', skill)

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
            self.assertIn("deterministic local full-check gate", skill)
            self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0", skill)
            self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0", skill)
            self.assertIn("sd-review-local", skill)
            self.assertIn("sd-review-local-all", skill)
            self.assertNotIn("any available local review providers", skill)
            self.assertNotIn("optional local review providers", skill)
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
            self.assertIn("after every pushed review-fix commit", skill)
            self.assertIn(
                "before each configured remote-review request",
                skill,
            )
            self.assertIn(
                "fixes for review comments that existed before this command was",
                skill,
            )
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
            self.assertIn("deterministic local full-check gate", adapter)
            self.assertIn("Prism/Gito disabled", adapter)
            self.assertIn("automatic re-review after pushed fixes", adapter)
            self.assertIn("configured remote review round limit", adapter)
            self.assertNotIn("any available local review providers", adapter)
            self.assertNotIn("optional local review providers", adapter)

        for doc_path in doc_paths:
            doc = doc_path.read_text(encoding="utf-8")
            self.assertRegex(doc, r"(?i)the\s+default remote reviewer")
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER", doc)
            self.assertIn("review-fix commit made", doc)
            self.assertRegex(
                doc,
                r"disables\s+Prism(?:\s+and\s+Gito|[\s\S]*disables\s+Gito)",
            )
            self.assertIn("sd-review-local", doc)
            self.assertIn("sd-review-local-all", doc)

    def test_tracked_pack_targets_match_templates(self) -> None:
        # Every tracked installed twin must match its manifest source so this
        # repo's own footprint can never drift from the shipped templates.
        # (The managed copilot block has its own dedicated full-file test.)
        _, files = install.load_manifest()
        compared = 0
        drifted: list[str] = []
        for file in files:
            if file.kind == install.MANAGED_BLOCK_KIND:
                continue
            installed = install.ROOT / file.target
            if not installed.exists():
                continue
            compared += 1
            if installed.read_bytes() != file.source.read_bytes():
                drifted.append(file.target.as_posix())
        self.assertGreaterEqual(compared, 50)
        self.assertEqual(drifted, [])

    ENV_VAR_DOC_EXEMPT = frozenset(
        {
            # Internal test hook, intentionally undocumented.
            "SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE",
            # Legacy rename hint prefixes emitted by the install audit.
            "SD_AI_COMMAND_PACK_FULL_CHECK",
            "SD_AI_COMMAND_PACK_HOUSEKEEPING",
        }
    )

    def test_shipped_env_vars_are_documented(self) -> None:
        var_re = re.compile(r"SD_AI_COMMAND_PACK_[A-Z0-9_]+")
        script_vars: set[str] = set()
        for path in (install.ROOT / "scripts").iterdir():
            if path.suffix in {".sh", ".py", ".mjs"}:
                script_vars |= set(var_re.findall(path.read_text(encoding="utf-8")))
        skill_vars: set[str] = set()
        for path in (install.ROOT / "templates/.agents/skills").glob("*/SKILL.md"):
            skill_vars |= set(var_re.findall(path.read_text(encoding="utf-8")))
        documented = set(
            var_re.findall(
                (install.ROOT / "docs/SD_AI_COMMAND_PACK.md").read_text(
                    encoding="utf-8"
                )
            )
        )

        undocumented = sorted(script_vars - documented - self.ENV_VAR_DOC_EXEMPT)
        self.assertEqual(
            undocumented,
            [],
            "env vars read by shipped scripts but missing from the installed guide",
        )
        stale = sorted(documented - script_vars - skill_vars)
        self.assertEqual(
            stale,
            [],
            "env vars documented in the installed guide but consumed by no "
            "shipped script or skill",
        )

    def test_full_check_script_runs_pack_source_drift_gates(self) -> None:
        script = (
            install.ROOT / "scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("run_pack_source_drift_gates", script)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_PACK_DRIFT", script)
        self.assertIn("template twin pairs compared", script)
        self.assertIn("undocumented env var", script)

    def test_review_learnings_reports_subprocess_timeout_as_setup_failure(
        self,
    ) -> None:
        # Regression: a hung git/gh call must surface the [sd-review-learnings:*]
        # exit-2 contract, not a raw subprocess.TimeoutExpired traceback.
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_timeout_regression",
        )
        root = self.make_repo()

        with mock.patch.object(
            module,
            "build_local_diff",
            side_effect=module.subprocess.TimeoutExpired("git", 120),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = module.main(["--repo-root", str(root)])
        self.assertEqual(code, 2)
        self.assertIn("[sd-review-learnings:findings]", stderr.getvalue())

        diff_file = root / "empty.diff"
        diff_file.write_text("", encoding="utf-8")
        with mock.patch.object(
            module,
            "fetch_recent_copilot_comments",
            side_effect=module.subprocess.TimeoutExpired("gh", 60),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = module.main(
                    [
                        "--repo-root",
                        str(root),
                        "--diff-from",
                        str(diff_file),
                        "--github-days",
                        "7",
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("[sd-review-learnings:github]", stderr.getvalue())

    def test_review_preflight_reports_malformed_config_as_failure(self) -> None:
        # Regression: a malformed review-preflight.json must FAIL, not be wiped
        # by the failure-buffer reset and pass on defaults.
        if shutil.which("node") is None:
            self.skipTest("node is not available on PATH")
        root = self.make_repo()
        # The script resolves its repo root to its own parent dir, so it must be
        # run from inside the target repo's scripts/ as it is when installed.
        scripts_dir = root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            install.ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs",
            scripts_dir / "sd-ai-command-pack-review-preflight.mjs",
        )
        config_dir = root / ".sd-ai-command-pack"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "review-preflight.json").write_text(
            "{ not valid json", encoding="utf-8"
        )

        result = subprocess.run(
            ["node", "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("could not be parsed as JSON", result.stdout)

    def test_review_preflight_resolves_pytest_node_ids_to_files(self) -> None:
        # Regression: docs referencing pytest node ids (tests/x.py::test_y) must
        # resolve the file part only — present file passes, missing file fails.
        if shutil.which("node") is None:
            self.skipTest("node is not available on PATH")
        root = self.make_repo()
        scripts_dir = root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            install.ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs",
            scripts_dir / "sd-ai-command-pack-review-preflight.mjs",
        )
        (root / "tests").mkdir()
        (root / "tests/test_real.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
        docs = root / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text(
            "Run `tests/test_real.py::test_ok` before merging.\n",
            encoding="utf-8",
        )

        def run_preflight() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["node", "scripts/sd-ai-command-pack-review-preflight.mjs"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        result = run_preflight()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("test_real.py", result.stdout.replace("PASS", ""))

        (docs / "guide.md").write_text(
            "Run `tests/test_missing.py::test_gone` before merging.\n",
            encoding="utf-8",
        )
        result = run_preflight()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("tests/test_missing.py", result.stdout)

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

        self.assertIn("Post-Merge Handoff", skill)
        self.assertIn('PR_STATE" = "MERGED"', skill)
        self.assertIn("bash scripts/sd-ai-command-pack-housekeeping.sh", skill)
        self.assertIn("not a background GitHub webhook", skill)
        for adapter_path in adapter_paths:
            content = adapter_path.read_text(encoding="utf-8")
            self.assertIn("If the PR is merged while this command is running", content)
            self.assertIn("post-merge cleanup workflow", content)

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
            "repo-wide open PRs",
            "inventory, not as blockers",
            "current stream cleanup",
            "SD finish-work flow",
            "execute the `sd-finish-work` flow",
            "Housekeeping completed cleanly.",
            "Final state:",
            "PR #<number>: merged at <timestamp>",
            "Insight:",
            "evidence-backed observation",
            "Do not add filler insights",
            "No follow-up needed for this cleanup stream.",
            "numbered `Next Steps` list",
            "open follow-up items discovered during this session",
            "existing Trellis tasks that are already `in_progress`",
            "high-value Trellis task candidates",
            "python3 ./.trellis/scripts/task.py list",
            "Either `No follow-up needed for this cleanup stream.`",
            "--no-auto-merge",
        ]:
            self.assertIn(text, skill)
        for text in [
            "Expected clean state",
            "Inventory",
            "Anomalies",
            "open PRs: none",
            "open issues: none",
            "Trellis active tasks: none assigned",
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
            "remote source branch kept: $REMOTE/$START_BRANCH",
            "remote source branch absent: $REMOTE/$START_BRANCH",
            "remote source branch still tracked: $REMOTE/$START_BRANCH",
            "failed to check whether remote branch $REMOTE/$branch exists",
            "dry-run preview: skipped final git-state verification",
            "would fast-forward $DEFAULT_BRANCH from $REMOTE/$DEFAULT_BRANCH",
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
        self.assertIn("would fast-forward main from origin/main", result.stdout)
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

    def test_housekeeping_rejects_undeterminable_check_counts_before_auto_merge(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(
            stub_bin,
            marker,
            blocking_check_count="unknown",
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
            "PR #6 has undeterminable check counts; skipped auto-merge",
            result.stdout,
        )
        self.assertFalse(marker.exists())

    def run_housekeeping_with_rollup(
        self, rollup_json: str
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        if shutil.which("jq") is None:
            self.skipTest("jq is not available on PATH")
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker, rollup_json=rollup_json)
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
        return result, marker

    def test_housekeeping_auto_merges_with_skipped_and_neutral_checks(self) -> None:
        # Regression: classifier-skipped lanes (SKIPPED/NEUTRAL conclusions)
        # must not block the merge gate when executed checks are green.
        result, marker = self.run_housekeeping_with_rollup(
            '[{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},'
            ' {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"},'
            ' {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "NEUTRAL"},'
            ' {"__typename": "StatusContext", "state": "SUCCESS"}]'
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("merged PR #6 with merge strategy", result.stdout)
        self.assertTrue(marker.exists())

    def test_housekeeping_skips_auto_merge_when_all_checks_skipped(self) -> None:
        # An all-skipped run executed nothing, so it must not merge.
        result, marker = self.run_housekeeping_with_rollup(
            '[{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"},'
            ' {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"}]'
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 has no successful executed checks; skipped auto-merge",
            result.stdout,
        )
        self.assertFalse(marker.exists())

    def test_housekeeping_skips_auto_merge_with_pending_or_failed_checks(self) -> None:
        result, marker = self.run_housekeeping_with_rollup(
            '[{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},'
            ' {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": null}]'
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 has non-green checks; skipped auto-merge",
            result.stdout,
        )
        self.assertFalse(marker.exists())

        result, marker = self.run_housekeeping_with_rollup(
            '[{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},'
            ' {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}]'
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 has non-green checks; skipped auto-merge",
            result.stdout,
        )
        self.assertFalse(marker.exists())

    def test_housekeeping_self_test_passes_hermetically(self) -> None:
        # The self-test must pass from a non-git directory with no gh on PATH,
        # exercising only the vendored gate logic.
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-selftest-")
        self.addCleanup(tempdir.cleanup)

        result = subprocess.run(
            [
                self._bash_path,
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                "--self-test",
            ],
            cwd=tempdir.name,
            env={"PATH": tempdir.name, "HOME": tempdir.name},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("self-test: all scenarios passed", result.stdout)
        for scenario in (
            "green executed checks merge",
            "single executed success suffices",
            "blocking checks refuse",
            "zero successful checks refuse",
            "undeterminable counts refuse",
            "non-clean merge state refuses",
            "draft PR refuses",
            "unresolved review threads refuse",
        ):
            self.assertIn(f"self-test: {scenario}: ok", result.stdout)

    def test_housekeeping_self_test_detects_a_neutered_gate(self) -> None:
        # Meta-regression: a sabotaged blocking-check gate must fail the
        # self-test, proving it verifies behavior rather than always passing.
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-sabotage-")
        self.addCleanup(tempdir.cleanup)
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        ).read_text(encoding="utf-8")
        needle = '[ "$blocking_check_count" -ne 0 ]'
        self.assertIn(needle, script)
        sabotaged = Path(tempdir.name) / "sabotaged.sh"
        sabotaged.write_text(
            script.replace(needle, '[ "$blocking_check_count" -lt 0 ]'),
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, str(sabotaged), "--self-test"],
            cwd=tempdir.name,
            env={"PATH": tempdir.name, "HOME": tempdir.name},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("self-test: blocking checks refuse: FAIL", result.stdout)

    def test_housekeeping_self_test_reports_named_failures_on_stub_errors(
        self,
    ) -> None:
        # A scenario whose collaborators error (unexpected git call) must
        # produce named FAIL lines and a failure summary, never a silent exit.
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-stuberr-")
        self.addCleanup(tempdir.cleanup)
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        ).read_text(encoding="utf-8")
        needle = '("rev-parse --verify refs/heads/feature^{commit}")'
        self.assertIn(needle, script)
        sabotaged = Path(tempdir.name) / "sabotaged.sh"
        sabotaged.write_text(
            script.replace(needle, '("never-matches")'), encoding="utf-8"
        )

        result = subprocess.run(
            [self._bash_path, str(sabotaged), "--self-test"],
            cwd=tempdir.name,
            env={"PATH": tempdir.name, "HOME": tempdir.name},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("self-test: green executed checks merge: FAIL", result.stdout)
        self.assertIn("scenario(s) FAILED", result.stdout)

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
