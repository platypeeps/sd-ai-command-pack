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
from collections.abc import Iterable
from pathlib import Path
from unittest import mock

import yaml

import install

__all__ = [
    "contextlib",
    "hashlib",
    "importlib",
    "io",
    "json",
    "os",
    "re",
    "shutil",
    "subprocess",
    "sys",
    "tempfile",
    "unittest",
    "mock",
    "Path",
    "yaml",
    "install",
    "PACK_ROOT",
    "INSTALLER",
    "SECRET_MARKER_PATTERNS",
    "InstallTestCase",
]

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


class InstallTestCase(unittest.TestCase):
    _bash_path: str | None

    _manifest_files: list[install.PackFile]

    # Per-class cache of (template_root, head_oid) for make_housekeeping_repo.
    # Set lazily on the concrete subclass; read via __dict__ so subclasses do
    # not share a parent's template.
    _housekeeping_template: tuple[Path, str] | None

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
        module_dir = str(module_path.parent)
        inserted = module_dir not in sys.path
        if inserted:
            sys.path.insert(0, module_dir)
        try:
            spec.loader.exec_module(module)
        finally:
            if inserted:
                try:
                    sys.path.remove(module_dir)
                except ValueError:
                    pass
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
                    install.PACK_MANIFEST_FILE,
                    install.PROVENANCE_FILE,
                ],
            ),
        )

    def assert_paths_are_files(
        self, root: Path, relative_paths: Iterable[str]
    ) -> None:
        """Assert every ``relative_path`` under ``root`` is an existing file.

        Each path runs in its own ``subTest`` so a single missing file reports
        exactly which path failed instead of aborting the rest of the run.
        """
        for relative_path in relative_paths:
            with self.subTest(path=relative_path):
                self.assertTrue((root / relative_path).is_file(), root / relative_path)

    def assert_paths_absent(
        self, root: Path, relative_paths: Iterable[str]
    ) -> None:
        """Assert every ``relative_path`` under ``root`` does not exist."""
        for relative_path in relative_paths:
            with self.subTest(path=relative_path):
                self.assertFalse((root / relative_path).exists(), root / relative_path)

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
            "`.github/prompts/` (including `continue.prompt.md`",
            "legacy `scripts/trellis-*.sh`",
            "scripts/update_repomix*",
            "The `.gito/`, `.prism/`, and `.sd-ai-command-pack/` directories",
            "docs/SD_AI_COMMAND_PACK.md",
            "legacy `docs/TRELLIS_REVIEW_PR_PACK.md`",
            "Original Trellis-owned runtime/template copies",
            "not valid modification",
            "should not be reviewed",
            "ownership/scope",
            "narrow-globs: skip - optional Trellis-owned payload locations",
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
        claude_command_rules = (
            ".claude/**",
            "!.claude/commands/",
            "!.claude/commands/sd/",
            "!.claude/commands/sd/*.md",
        )
        for expected in claude_command_rules:
            self.assertIn(expected, content)
        block_lines = content.splitlines()
        self.assertEqual(
            [block_lines.index(rule) for rule in claude_command_rules],
            sorted(block_lines.index(rule) for rule in claude_command_rules),
        )
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

    def _build_housekeeping_template(self, root: Path) -> str:
        """Populate ``root`` with the canonical housekeeping layout.

        Creates ``work/`` (feature/cleanup checked out, origin tracking set up),
        the bare ``origin.git/`` remote, and an empty ``bin/`` stub dir. Returns
        the feature/cleanup HEAD oid. This is the ~15-git-subprocess body that
        used to run per test; it now runs once per class into a template dir.
        """
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
        return self.git_output(repo, "rev-parse", "HEAD")

    def make_housekeeping_repo(self) -> tuple[Path, Path, Path, str]:
        """Return an isolated ``(repo, remote, stub_bin, head_oid)`` tuple.

        The canonical repo is built once per test class into a template dir; each
        call ``copytree``-clones that template and only repoints ``work``'s
        origin remote at this copy's bare remote. A copy plus one git command is
        far cheaper than the ~15 git subprocesses of a full rebuild. Every clone
        is a fully independent tree (its own ``work/`` and ``origin.git/``), so
        tests that merge PRs or delete branches never observe each other's state.
        """
        cls = type(self)
        cached = cls.__dict__.get("_housekeeping_template")
        if cached is None:
            template_root = Path(
                tempfile.mkdtemp(prefix="sd-ai-command-pack-housekeeping-template-")
            )
            head_oid = self._build_housekeeping_template(template_root)
            cls.addClassCleanup(shutil.rmtree, template_root, ignore_errors=True)
            cached = (template_root, head_oid)
            cls._housekeeping_template = cached
        template_root, head_oid = cached

        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-housekeeping-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "repo"
        shutil.copytree(template_root, root)
        repo = root / "work"
        remote = root / "origin.git"
        stub_bin = root / "bin"
        # The cloned work tree still points origin at the template's bare remote;
        # repoint it at this copy so every test's pushes/merges stay isolated.
        self.run_git(repo, "remote", "set-url", "origin", str(remote))
        return repo, remote, stub_bin, head_oid

    def write_housekeeping_gh_stub(self, stub_bin: Path, head_oid: str) -> None:
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            f"  printf '6\\037MERGED\\0372026-06-27T17:00:00Z\\037https://example.test/pr/6\\037feature/cleanup\\037{head_oid}\\n'\n"
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
        graphql_body: str = "  printf '0\\037false\\037\\n'\n",
        blocking_check_count: str = "0",
        successful_check_count: str = "2",
        rollup_json: str | None = None,
    ) -> None:
        if rollup_json is None:
            readiness_branch = (
                "    printf '6\\037%s\\037false\\037https://example.test/pr/6\\037feature/cleanup\\037%s\\037main\\037CLEAN\\037%s\\037%s\\n' "
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
            "    printf '6\\037%s\\037%s\\037https://example.test/pr/6\\037feature/cleanup\\037%s\\n' \"$state\" \"$merged_at\" \"$head\"\n"
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

    def run_install_inproc(
        self,
        root: Path,
        *args: str,
        skip_diff_check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """In-process ``install.main`` twin of :meth:`run_install`.

        Returns a ``CompletedProcess`` with the same ``returncode``/``stdout``
        shape (stdout and stderr merged, matching ``run_install``'s
        ``stderr=STDOUT``) so happy-path callers can swap the two without
        touching their assertions, while skipping interpreter + subprocess
        coverage startup.

        Use only for tests that install then inspect the filesystem/return code.
        Tests that depend on process semantics — argv/CLI parsing, ``os.environ``
        / PATH isolation, ``SystemExit`` as process exit status, or the
        symlink-exec entry — must keep :meth:`run_install`.
        """
        argv = [str(root), *args]
        if skip_diff_check:
            argv.append("--skip-diff-check")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            returncode = install.main(argv)
        return subprocess.CompletedProcess(
            args=argv, returncode=returncode, stdout=output.getvalue()
        )

    def make_pack_source_fixture(self) -> Path:
        root = self.make_git_repo_without_trellis()
        for dirname in ("templates", "scripts", "docs"):
            shutil.copytree(PACK_ROOT / dirname, root / dirname)
        shutil.copyfile(PACK_ROOT / "manifest.json", root / "manifest.json")
        shutil.copyfile(PACK_ROOT / "CHANGELOG.md", root / "CHANGELOG.md")
        (root / "install.py").write_text("# source repo marker\n", encoding="utf-8")
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        return root

    def run_pack_source_drift_gates(
        self,
        root: Path,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        env = {
            **os.environ,
            "SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE": "1",
            "SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF": "HEAD",
        }
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [
                self._bash_path,
                "-c",
                "source scripts/sd-ai-command-pack-full-check.sh; "
                "if [ -n \"${SD_AI_COMMAND_PACK_FULL_CHECK_TEST_RUNTIME_PATH:-}\" ]; "
                "then PATH=\"$SD_AI_COMMAND_PACK_FULL_CHECK_TEST_RUNTIME_PATH\"; fi; "
                "run_pack_source_drift_gates",
            ],
            cwd=root,
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

    def archived_task_description_failures(
        self, archive_root: Path, *, base_root: Path
    ) -> list[str]:
        missing_descriptions: list[str] = []

        for task_json in sorted(archive_root.glob("**/task.json")):
            if task_json.is_symlink() or not task_json.is_file():
                continue

            task_dir = task_json.parent
            prd = task_dir / "prd.md"
            if prd.is_symlink() or not prd.is_file():
                continue

            task = json.loads(task_json.read_text(encoding="utf-8"))
            if task.get("status") != "completed":
                continue

            description = task.get("description")
            if not isinstance(description, str) or not description.strip():
                missing_descriptions.append(task_json.relative_to(base_root).as_posix())

        return missing_descriptions

    def _run_full_check_kb_lane(self, root, extra_env=None):
        env = {
            **os.environ,
            "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT": "0",
            "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
            "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
            "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
            "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK": "0",
            "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0",
            "SD_AI_COMMAND_PACK_FULL_CHECK_KB": "auto",
        }
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
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

    ENV_VAR_DOC_EXEMPT = frozenset(
        {
            # Internal test hook, intentionally undocumented.
            "SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE",
            # Source-only fleet candidate marker, never read by consumers.
            "SD_AI_COMMAND_PACK_CANDIDATE_CHECK",
            # Legacy rename hint prefixes emitted by the install audit.
            "SD_AI_COMMAND_PACK_FULL_CHECK",
            "SD_AI_COMMAND_PACK_HOUSEKEEPING",
        }
    )

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
