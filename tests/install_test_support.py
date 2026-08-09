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
    "fleet_manifest",
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


def fleet_manifest(consumers: list[dict[str, object]]) -> dict[str, object]:
    """Build the smallest valid schema-4 fleet around test consumer rows."""
    ordered = sorted(
        consumers,
        key=lambda consumer: (
            consumer["rolloutPriority"],
            str(consumer["name"]).casefold(),
        ),
    )
    return {
        "schemaVersion": 4,
        "rolloutPolicy": {
            "defaultConcurrency": 1,
            "cohorts": [
                {
                    "name": "canary",
                    "strategy": "sequential",
                    "consumers": [consumer["name"] for consumer in ordered],
                }
            ],
        },
        "consumers": consumers,
    }


class InstallTestCase(unittest.TestCase):
    _bash_path: str | None

    # The real bash binary, independent of any coverage-shim override. Tests
    # that need bash's directory on PATH (not just something to invoke) must use
    # this: _bash_path may point at the kcov shim, whose directory has no bash.
    _real_bash_path: str | None

    _manifest_files: list[install.PackFile]

    # Per-class cache of (template_root, head_oid) for make_housekeeping_repo.
    # Set lazily on the concrete subclass; read via __dict__ so subclasses do
    # not share a parent's template.
    _housekeeping_template: tuple[Path, str] | None

    @classmethod
    def setUpClass(cls) -> None:
        # CI's shell-coverage lane sets SD_AI_COMMAND_PACK_TEST_BASH to a kcov
        # shim so the bash the subprocess tests spawn runs under coverage.
        # Unset (local runs), fall back to the bash on PATH — identical
        # behaviour to before this override existed.
        cls._real_bash_path = shutil.which("bash")
        override_bash = os.environ.get("SD_AI_COMMAND_PACK_TEST_BASH")
        if override_bash and not (
            os.path.isfile(override_bash) and os.access(override_bash, os.X_OK)
        ):
            # Fail immediately with an actionable message instead of letting a
            # bad override surface much later as a FileNotFoundError from the
            # first subprocess.run that spawns bash. (An unset override keeps the
            # old behaviour: fall back to PATH bash, skip when none is found.)
            raise RuntimeError(
                "SD_AI_COMMAND_PACK_TEST_BASH points at "
                f"{override_bash!r}, which is not an executable file. "
                "Point it at the kcov shim, or unset it to use the bash on PATH."
            )
        cls._bash_path = override_bash or cls._real_bash_path
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
        # gc.auto=0 disables git's automatic (and by default detached) garbage
        # collection for every git command issued through this helper -- which
        # includes the run_git/git_output calls that build the per-class template
        # repos. Auto-gc writes transient objects/bitmap-ref-tips_* files while
        # repacking; those templates are later shutil.copytree-cloned by each
        # test, and a copy racing a still-running detached gc raises shutil.Error
        # when such a temp file vanishes mid-copy. This closes the client side;
        # the bare remote's server-side receive-pack auto-gc is disabled
        # separately in the template builders (see _build_housekeeping_template).
        return subprocess.run(
            ["git", "-c", "gc.auto=0", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def _git_failure_context(self, root: Path) -> str:
        # Bounded repo-state capture for UNEXPECTED git failures only (the
        # kcov-lane flake's second fingerprint died on `fatal: could not
        # parse HEAD` with nothing to distinguish a torn HEAD read from a
        # missing ref or lock contention). Runs solely on the failing
        # assertion path; passing runs never call this. Direct
        # _run_git_process callers that expect nonzero exits are untouched.
        lines = ["--- git repo-state context ---"]
        try:
            git_path = root / ".git"
            git_dir = git_path
            if git_path.is_file():
                pointer = git_path.read_bytes()[:200]
                lines.append(f".git is a worktree pointer file: {pointer!r}")
                pointer_text = pointer.decode("utf-8", errors="replace").strip()
                if pointer_text.startswith("gitdir:"):
                    target = Path(pointer_text[len("gitdir:") :].strip())
                    git_dir = target if target.is_absolute() else root / target
            common_dir = git_dir
            common_file = git_dir / "commondir"
            if common_file.is_file():
                common_text = common_file.read_text(
                    encoding="utf-8", errors="replace"
                ).strip()
                common_target = Path(common_text)
                common_dir = (
                    common_target
                    if common_target.is_absolute()
                    else git_dir / common_target
                )
                lines.append(f"commondir: {common_text}")
            head_path = git_dir / "HEAD"
            if head_path.is_file():
                head_bytes = head_path.read_bytes()[:200]
                lines.append(f"HEAD bytes: {head_bytes!r}")
                head_text = head_bytes.decode("utf-8", errors="replace").strip()
                if head_text.startswith("ref:"):
                    ref_name = head_text[len("ref:") :].strip()
                    loose = common_dir / ref_name
                    lines.append(
                        f"loose ref {ref_name}: "
                        f"{'exists' if loose.is_file() else 'MISSING'}"
                    )
                    packed = common_dir / "packed-refs"
                    if packed.is_file():
                        entry = None
                        with packed.open(encoding="utf-8", errors="replace") as handle:
                            for packed_line in handle:
                                if packed_line.rstrip("\n").endswith(f" {ref_name}"):
                                    entry = packed_line.rstrip("\n")
                                    break
                        lines.append(
                            f"packed-refs entry for {ref_name}: "
                            f"{entry if entry is not None else 'ABSENT'}"
                        )
                    else:
                        lines.append("packed-refs: absent")
            else:
                lines.append("HEAD: MISSING")
            # Bounded lock scan: only the directories where git takes ref /
            # index / packfile locks, not the whole .git tree (objects/**
            # can be arbitrarily large).
            lock_paths: list[str] = []
            for lock_dir, recursive in (
                (common_dir, False),
                (common_dir / "refs", True),
                (common_dir / "logs", True),
                (common_dir / "objects" / "pack", False),
            ):
                if not lock_dir.is_dir():
                    continue
                pattern = "**/*.lock" if recursive else "*.lock"
                lock_paths.extend(
                    str(path.relative_to(common_dir))
                    for path in lock_dir.glob(pattern)
                )
            locks = sorted(lock_paths)[:10]
            lines.append(f"lock files: {locks if locks else 'none'}")
        except OSError as error:
            lines.append(f"context capture failed: {error}")
        return "\n".join(lines)

    def _assert_git_success(
        self, root: Path, args: tuple[str, ...], result: subprocess.CompletedProcess[str]
    ) -> None:
        if result.returncode == 0:
            return
        self.fail(
            f"git {' '.join(args)} exited {result.returncode}: {result.stdout}\n"
            f"{self._git_failure_context(root)}"
        )

    def run_git(self, root: Path, *args: str) -> None:
        result = self._run_git_process(root, *args)
        self._assert_git_success(root, args, result)

    def git_output(self, root: Path, *args: str) -> str:
        result = self._run_git_process(root, *args)
        self._assert_git_success(root, args, result)
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
        # Claude is committed by default like every other platform: the block
        # must not blanket-ignore .claude/ or carry any .claude allow-list
        # negation (the old blanket-punch-through scheme).
        block_lines = content.splitlines()
        self.assertNotIn(".claude/**", block_lines)
        self.assertEqual(
            [line for line in block_lines if line.startswith("!.claude/")],
            [],
            "managed block must carry no .claude allow-list negations",
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
        # Persist gc-disabling config on both repos. _run_git_process already
        # passes `-c gc.auto=0` on the client, but that does not reach the bare
        # remote's server-side receive-pack: after `git push`, the bare repo
        # runs its OWN post-receive auto-gc (receive.autoGc, on by default),
        # governed by the bare repo's config, not the pushing client's -c flag.
        # That detached repack renames pack files and prunes loose-object dirs in
        # origin.git/objects; when a test copytree-clones this template mid-gc,
        # copytree raises "No such file or directory". Disabling gc persistently
        # on the remote closes the gap the client-side -c flag leaves open (the
        # kcov-shim job's slower git widened the window enough to hit it).
        for git_dir in (remote, repo):
            self.run_git(git_dir, "config", "gc.auto", "0")
            self.run_git(git_dir, "config", "receive.autoGc", "false")
            self.run_git(git_dir, "config", "maintenance.auto", "false")
        self.run_git(repo, "config", "user.email", "test@example.com")
        self.run_git(repo, "config", "user.name", "Test User")
        (repo / ".trellis/scripts").mkdir(parents=True)
        (repo / ".trellis/config.yaml").write_text("# test\n", encoding="utf-8")
        (repo / ".trellis/scripts/get_context.py").write_text(
            "print('(no active tasks assigned to you)')\n",
            encoding="utf-8",
        )
        (repo / ".gitignore").write_text(
            "# sd-ai-command-pack obsidian-kb start\n"
            "# Generated by scripts/sd-ai-command-pack-update-spec-kb.py. DO NOT EDIT MANUALLY.\n"
            "# Generated Obsidian KB copy folder; source docs remain in normal repo paths.\n"
            "/.obsidian-kb\n"
            "# sd-ai-command-pack obsidian-kb end\n",
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
        active_task = repo / ".trellis/tasks/07-25-housekeeping-receipt"
        active_task.mkdir(parents=True)
        task_record = {
            "id": "housekeeping-receipt",
            "name": "housekeeping-receipt",
            "title": "Housekeeping receipt fixture",
            "description": "Exercise exact finish-work receipt validation.",
            "status": "in_progress",
            "createdAt": "2026-07-25",
            "completedAt": None,
            "branch": "feature/cleanup",
            "base_branch": "main",
            "parent": None,
            "children": [],
        }
        (active_task / "task.json").write_text(
            json.dumps(task_record, indent=2) + "\n", encoding="utf-8"
        )
        (active_task / "prd.md").write_text(
            "# Housekeeping receipt fixture\n\nValidated fixture.\n",
            encoding="utf-8",
        )
        (active_task / "implement.jsonl").write_text("", encoding="utf-8")
        (active_task / "check.jsonl").write_text("", encoding="utf-8")
        (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
        self.run_git(repo, "add", "feature.txt", ".trellis/tasks")
        self.run_git(repo, "commit", "-m", "feature")
        work_commit = self.git_output(repo, "rev-parse", "HEAD")

        archive_task = (
            repo
            / ".trellis/tasks/archive/2026-07/07-25-housekeeping-receipt"
        )
        archive_task.parent.mkdir(parents=True)
        active_task.rename(archive_task)
        task_record["status"] = "completed"
        task_record["completedAt"] = "2026-07-25"
        (archive_task / "task.json").write_text(
            json.dumps(task_record, indent=2) + "\n", encoding="utf-8"
        )
        self.run_git(repo, "add", "-A", ".trellis/tasks")
        self.run_git(repo, "commit", "-m", "archive housekeeping fixture")

        workspace = repo / ".trellis/workspace/dev"
        workspace.mkdir(parents=True)
        (workspace / "journal-1.md").write_text(
            "# Development Journal\n\n"
            "## Session 1: Housekeeping receipt fixture\n\n"
            "### Summary\n\nValidated housekeeping receipt integration.\n\n"
            "### Main Changes\n\n- Added one canonical completed task fixture.\n\n"
            "### Git Commits\n\n| Hash | Message |\n|------|---------|\n"
            f"| `{work_commit[:12]}` | feature |\n\n"
            "### Testing\n\n- [OK] housekeeping fixture\n\n"
            "### Status\n\n[OK] **Completed**\n\n"
            "### Next Steps\n\n- None\n",
            encoding="utf-8",
        )
        (workspace / "index.md").write_text(
            "# Sessions\n\n"
            "| # | Date | Title | Commits | Branch |\n"
            "|---|------|-------|---------|--------|\n"
            f"| 1 | 2026-07-25 | Housekeeping receipt fixture | `{work_commit[:12]}` | `feature/cleanup` |\n",
            encoding="utf-8",
        )
        self.run_git(repo, "add", ".trellis/workspace")
        self.run_git(repo, "commit", "-m", "record housekeeping fixture journal")

        (repo / "feature.txt").write_text("feature review fix\n", encoding="utf-8")
        self.run_git(repo, "add", "feature.txt")
        self.run_git(repo, "commit", "-m", "fix housekeeping review finding")
        self.run_git(repo, "push", "-u", "origin", "feature/cleanup")
        return self.git_output(repo, "rev-parse", "HEAD")

    def write_finish_work_receipt(self, repo: Path, head_oid: str) -> Path:
        receipt = repo.parent / "finish-work-receipt.json"
        result = subprocess.run(
            [
                "node",
                str(PACK_ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs"),
                "final-bundle",
                "--mode",
                "completion",
                "--base",
                head_oid,
                "--head",
                head_oid,
                "--repo",
                str(repo),
                "--json",
            ],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        receipt.write_text(result.stdout, encoding="utf-8")
        return receipt

    def write_planning_finish_work_receipt(
        self, repo: Path, base_oid: str, head_oid: str
    ) -> Path:
        """Write a planning-mode finish-work receipt for ``base_oid..head_oid``.

        Unlike the completion variant this spans a real (non-empty) planning
        delta, so ``base_oid`` is the PR merge-base and ``head_oid`` is the
        branch head the receipt binds to.
        """
        receipt = repo.parent / "finish-work-receipt.json"
        result = subprocess.run(
            [
                "node",
                str(PACK_ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs"),
                "final-bundle",
                "--mode",
                "planning",
                "--base",
                base_oid,
                "--head",
                head_oid,
                "--repo",
                str(repo),
                "--json",
            ],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        receipt.write_text(result.stdout, encoding="utf-8")
        return receipt

    def make_planning_housekeeping_repo(
        self,
    ) -> tuple[Path, Path, Path, str, str]:
        """Return ``(repo, remote, stub_bin, base_oid, head_oid)`` for a PR
        #244-shaped planning-only finalization.

        The ``feature/cleanup`` branch adds multiple new planning tasks and a
        journal successor on top of one preserved current planning task, with no
        product/runtime path. ``base_oid`` is the PR merge-base; ``head_oid`` is
        the branch head the planning receipt binds to. Single-use (not cached)
        because only the planning-merge integration test needs this shape.
        """
        tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-planning-hk-"
        )
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
        # Persist gc-disabling config on both repos. _run_git_process already
        # passes `-c gc.auto=0` on the client, but that does not reach the bare
        # remote's server-side receive-pack: after `git push`, the bare repo
        # runs its OWN post-receive auto-gc (receive.autoGc, on by default),
        # governed by the bare repo's config, not the pushing client's -c flag.
        # That detached repack renames pack files and prunes loose-object dirs in
        # origin.git/objects; when a test copytree-clones this template mid-gc,
        # copytree raises "No such file or directory". Disabling gc persistently
        # on the remote closes the gap the client-side -c flag leaves open (the
        # kcov-shim job's slower git widened the window enough to hit it).
        for git_dir in (remote, repo):
            self.run_git(git_dir, "config", "gc.auto", "0")
            self.run_git(git_dir, "config", "receive.autoGc", "false")
            self.run_git(git_dir, "config", "maintenance.auto", "false")
        self.run_git(repo, "config", "user.email", "test@example.com")
        self.run_git(repo, "config", "user.name", "Test User")
        (repo / ".trellis/scripts").mkdir(parents=True)
        (repo / ".trellis/config.yaml").write_text("# test\n", encoding="utf-8")
        (repo / ".trellis/scripts/get_context.py").write_text(
            "print('(no active tasks assigned to you)')\n", encoding="utf-8"
        )
        (repo / ".gitignore").write_text(
            "# sd-ai-command-pack obsidian-kb start\n"
            "# Generated by scripts/sd-ai-command-pack-update-spec-kb.py. DO NOT EDIT MANUALLY.\n"
            "# Generated Obsidian KB copy folder; source docs remain in normal repo paths.\n"
            "/.obsidian-kb\n"
            "# sd-ai-command-pack obsidian-kb end\n",
            encoding="utf-8",
        )
        (repo / "README.md").write_text("# Test\n", encoding="utf-8")

        def planning_task(name: str) -> dict[str, object]:
            return {
                "id": name,
                "name": name,
                "title": "Planning finalization fixture",
                "description": "A bounded planning-only fixture task.",
                "status": "planning",
                "createdAt": "2026-07-25",
                "completedAt": None,
                "branch": None,
                "base_branch": "main",
                "parent": None,
                "children": [],
            }

        def write_planning_task(task_dir: str, record: dict[str, object]) -> None:
            task = repo / task_dir
            task.mkdir(parents=True)
            (task / "task.json").write_text(
                json.dumps(record, indent=2) + "\n", encoding="utf-8"
            )
            (task / "prd.md").write_text(
                "# Fixture\n\nValidated planning task.\n", encoding="utf-8"
            )
            (task / "implement.jsonl").write_text("", encoding="utf-8")
            (task / "check.jsonl").write_text("", encoding="utf-8")

        # One preserved current planning task committed at the merge-base.
        write_planning_task(
            ".trellis/tasks/07-25-planning-preserved",
            planning_task("planning-preserved"),
        )
        self.run_git(repo, "add", ".")
        self.run_git(repo, "commit", "-m", "initial")
        self.run_git(repo, "remote", "add", "origin", str(remote))
        self.run_git(repo, "push", "-u", "origin", "main")
        self.run_git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.run_git(repo, "fetch", "origin")
        self.run_git(repo, "remote", "set-head", "origin", "-a")
        self.run_git(repo, "switch", "-c", "feature/cleanup")
        base_oid = self.git_output(repo, "rev-parse", "HEAD")

        # Multiple new planning tasks form the planning delta (no product path).
        write_planning_task(
            ".trellis/tasks/07-25-planning-alpha", planning_task("planning-alpha")
        )
        write_planning_task(
            ".trellis/tasks/07-25-planning-beta", planning_task("planning-beta")
        )
        self.run_git(repo, "add", ".trellis/tasks")
        self.run_git(repo, "commit", "-m", "plan additional work")
        work_commit = self.git_output(repo, "rev-parse", "HEAD")

        workspace = repo / ".trellis/workspace/dev"
        workspace.mkdir(parents=True)
        (workspace / "journal-1.md").write_text(
            "# Development Journal\n\n"
            "## Session 1: Planning finalization fixture\n\n"
            "### Summary\n\nValidated planning-only finalization.\n\n"
            "### Main Changes\n\n- Added two new planning tasks.\n\n"
            "### Git Commits\n\n| Hash | Message |\n|------|---------|\n"
            f"| `{work_commit[:12]}` | plan additional work |\n\n"
            "### Testing\n\n- [OK] planning fixture\n\n"
            "### Status\n\n[OK] **Completed**\n\n"
            "### Next Steps\n\n- None\n",
            encoding="utf-8",
        )
        (workspace / "index.md").write_text(
            "# Sessions\n\n"
            "| # | Date | Title | Commits | Branch |\n"
            "|---|------|-------|---------|--------|\n"
            f"| 1 | 2026-07-25 | Planning finalization fixture | `{work_commit[:12]}` | `feature/cleanup` |\n",
            encoding="utf-8",
        )
        self.run_git(repo, "add", ".trellis/workspace")
        self.run_git(repo, "commit", "-m", "record planning journal")
        head_oid = self.git_output(repo, "rev-parse", "HEAD")
        self.run_git(repo, "push", "-u", "origin", "feature/cleanup")
        return repo, remote, stub_bin, base_oid, head_oid

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

    def write_pr_lifecycle_gh_stub(
        self, stub_bin: Path, head_oid: str, state: str
    ) -> None:
        """Write a gh stub that reports a fixed PR lifecycle ``state``.

        ``state`` is emitted verbatim as the PR ``state`` field for
        ``gh pr view`` (already reduced to the FIELD_SEPARATOR-joined identity
        the script's ``--jq`` would produce). A non-``MERGED`` state carries an
        empty ``mergedAt``. An empty ``state`` makes both ``gh pr view`` and the
        merged ``gh pr list`` fallback return nothing, so the branch has no
        resolvable PR. ``repo view`` and the ``issue``/``pr list`` status probes
        always answer so the downstream status collector never sees an
        unexpected invocation.
        """
        if state:
            merged_at = "2026-06-27T17:00:00Z" if state == "MERGED" else ""
            view_body = (
                f"  printf '6\\037{state}\\037{merged_at}\\037"
                f"https://example.test/pr/6\\037feature/cleanup\\037{head_oid}\\n'\n"
            )
        else:
            view_body = "  exit 0\n"
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            + view_body
            + "elif [ \"${1:-}\" = pr ] && [ \"${2:-}\" = list ]; then\n"
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
        graphql_body: str = (
            "  printf '%s\\n' "
            "'{\"data\":{\"repository\":{\"pullRequest\":{\"reviewThreads\":"
            "{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false,\"endCursor\":null}}}}}}'\n"
        ),
        blocking_check_count: str = "0",
        successful_check_count: str = "2",
        rollup_json: str | None = None,
        auto_delete_remote_branch: bool = False,
        pr_head_oid: str | None = None,
    ) -> None:
        # Simulate GitHub's auto-delete-head-branch: the remote drops the
        # feature branch at merge time (after housekeeping's initial prune),
        # leaving a stale local tracking ref for cleanup to reconcile.
        auto_delete_line = (
            "  git --git-dir=\"$remote\" update-ref -d \"refs/heads/$branch\"\n"
            if auto_delete_remote_branch
            else ""
        )
        if rollup_json is None:
            if blocking_check_count.isdigit() and successful_check_count.isdigit():
                rollup = [
                    {
                        "__typename": "CheckRun",
                        "name": f"success-{index + 1}",
                        "status": "COMPLETED",
                        "conclusion": "SUCCESS",
                    }
                    for index in range(int(successful_check_count))
                ]
                rollup.extend(
                    {
                        "__typename": "CheckRun",
                        "name": f"blocking-{index + 1}",
                        "status": "COMPLETED",
                        "conclusion": "FAILURE",
                    }
                    for index in range(int(blocking_check_count))
                )
                rollup_json = json.dumps(rollup)
            else:
                rollup_json = json.dumps({"invalid": "check-counts"})
        readiness_branch = (
            "    cat <<FIXTURE\n"
            "{\"number\": 6, \"state\": \"$state\", \"isDraft\": false,"
            " \"url\": \"https://example.test/pr/6\","
            " \"headRefName\": \"feature/cleanup\", \"headRefOid\": \"$head\","
            " \"baseRefName\": \"main\", \"mergeStateStatus\": \"CLEAN\","
            f" \"statusCheckRollup\": {rollup_json}}}\n"
            "FIXTURE\n"
        )
        head_function = (
            f"head_oid() {{ printf '%s\\n' {pr_head_oid!r}; }}\n"
            if pr_head_oid is not None
            else "head_oid() { git rev-parse \"refs/heads/$branch\"; }\n"
        )
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "branch='feature/cleanup'\n"
            f"marker={str(marker)!r}\n"
            + head_function +
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
            "  elif [[ \"$args\" == *'--json headRefOid'* ]]; then\n"
            "    printf '{\"headRefOid\":\"%s\"}\\n' \"$head\"\n"
            "  else\n"
            "    merged_at=''\n"
            "    if [ \"$state\" = MERGED ]; then merged_at='2026-06-27T18:00:00Z'; fi\n"
            "    printf '6\\037%s\\037%s\\037https://example.test/pr/6\\037feature/cleanup\\037%s\\n' \"$state\" \"$merged_at\" \"$head\"\n"
            "  fi\n"
            "elif [ \"${1:-}\" = pr ] && [ \"${2:-}\" = merge ]; then\n"
            "  remote=\"$(git remote get-url origin)\"\n"
            "  head=\"$(git rev-parse HEAD)\"\n"
            "  git --git-dir=\"$remote\" update-ref refs/heads/main \"$head\"\n"
            + auto_delete_line +
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
        if skip_diff_check and not ({"--status", "--check"} & set(args)):
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
        if skip_diff_check and not ({"--status", "--check"} & set(args)):
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
        lint_dir = root / ".github/scripts"
        lint_dir.mkdir(parents=True)
        (lint_dir / "check-command-surface-drift.py").write_text(
            "#!/usr/bin/env python3\n"
            "# Synthetic pack fixtures exercise linter orchestration only.\n"
            "raise SystemExit(0)\n",
            encoding="utf-8",
        )
        surface_fixture = (
            "#!/usr/bin/env python3\n"
            "# Synthetic pack fixtures exercise validator orchestration only.\n"
            "raise SystemExit(0)\n"
        )
        (root / "scripts/sd-ai-command-pack-surface-check.py").write_text(
            surface_fixture, encoding="utf-8"
        )
        (root / "templates/scripts/sd-ai-command-pack-surface-check.py").write_text(
            surface_fixture, encoding="utf-8"
        )
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
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        receipt = self.write_finish_work_receipt(repo, head_oid)
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker, rollup_json=rollup_json)
        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                "--finish-work-receipt",
                str(receipt),
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
        return result, marker
