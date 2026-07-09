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


class ReviewScopeTests(InstallTestCase):
    """Tests for PR-body scope, Prism/Gito config, and PR review skill behavior."""

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
        readme = (install.ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("review-scope and PR-body", readme)
        self.assertIn(
            "[docs/SD_AI_COMMAND_PACK.md](docs/SD_AI_COMMAND_PACK.md#updating-the-pack)",
            readme,
        )
        self.assertNotIn("Tooling/generated scope:", readme)
        self.assertNotIn("CI/review scope:", readme)

        for doc_path in [
            install.ROOT / "docs/SD_AI_COMMAND_PACK.md",
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md",
        ]:
            content = doc_path.read_text(encoding="utf-8")
            self.assertIn("Tooling/generated scope:", content, doc_path)
            self.assertIn("CI/review scope:", content, doc_path)
            self.assertIn("command invocation", content, doc_path)
            self.assertIn("SD_AI_COMMAND_PACK_SCOPE_PR_BODY", content, doc_path)
            self.assertIn("REVIEW_PREFLIGHT_PR_BODY", content, doc_path)

    def test_pr_body_scope_default_rule_patterns_match_representatives(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_pr_body_scope_default_rules",
        )

        def representative(pattern: str) -> str:
            if pattern.endswith("/**"):
                base = pattern[:-3].replace("*", "x")
                return f"{base}/nested/file.md"
            return pattern.replace("*", "x")

        checked = 0
        for rule in module.DEFAULT_RULES:
            for pattern in rule.patterns:
                checked += 1
                candidate = representative(pattern)
                self.assertTrue(
                    module._matches_pattern(candidate, pattern),
                    f"{pattern!r} failed to match its representative {candidate!r}",
                )
                self.assertFalse(
                    module._matches_pattern("src/unrelated/module.py", pattern),
                    f"{pattern!r} unexpectedly matched an unrelated path",
                )
        self.assertGreater(checked, 0)

        wildcard_base_pattern = ".claude/skills/sd-*/**"
        self.assertTrue(
            module._matches_pattern(
                ".claude/skills/sd-review-pr/SKILL.md", wildcard_base_pattern
            )
        )
        self.assertTrue(
            module._matches_pattern(".claude/skills/sd-review-pr", wildcard_base_pattern)
        )
        self.assertFalse(
            module._matches_pattern(
                ".claude/skills/other/SKILL.md", wildcard_base_pattern
            )
        )
        self.assertFalse(
            module._matches_pattern(".claude/skillsX/sd-a/file.md", wildcard_base_pattern)
        )

    def test_pr_body_scope_script_detects_wildcard_base_skill_paths(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        changed_files = root / "changed-files.txt"
        changed_files.write_text(
            ".claude/skills/sd-review-pr/SKILL.md\n"
            ".github/skills/trellis-before-dev/SKILL.md\n",
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
        self.assertIn(".claude/skills/sd-review-pr/SKILL.md", result.stdout)
        self.assertIn(".github/skills/trellis-before-dev/SKILL.md", result.stdout)

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

    def test_pr_body_scope_accepts_markdown_heading_without_colon(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_heading_test",
        )

        self.assertTrue(
            module._body_has_heading(
                "## Tooling/generated scope\n- command-pack refresh.",
                ("Tooling/generated scope:",),
            )
        )
        self.assertFalse(
            module._body_has_heading(
                "Summary mentions Tooling/generated scope in prose.",
                ("Tooling/generated scope:",),
            )
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

    def test_review_scope_script_accepts_markdown_scope_heading_without_colon(
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
            "'{\"title\":\"Product fix\",\"body\":\"## Tooling/generated scope\\n- command-pack refresh.\",\"url\":\"https://example.test/pr/1\"}'\n"
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
            install.ROOT / "templates/.commands/sd-review-pr.md",
            install.ROOT / "templates/.gemini/commands/sd/review-pr.toml",
            install.ROOT / "templates/.github/prompts/sd-review-pr.prompt.md",
            install.ROOT / "templates/.opencode/commands/sd-review-pr.md",
        ]
        detailed_doc_paths = [
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

        readme = (install.ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("### sd-review-pr", readme)
        self.assertIn("configured remote reviewer", readme)
        self.assertIn("Prism and Gito disabled", readme)
        self.assertIn("re-requests review after each pushed fix", readme)
        self.assertIn("sd-review-local", readme)
        self.assertIn("sd-review-local-all", readme)
        self.assertIn(
            "[docs/SD_AI_COMMAND_PACK.md](docs/SD_AI_COMMAND_PACK.md#commands)",
            readme,
        )

        for doc_path in detailed_doc_paths:
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


if __name__ == "__main__":
    unittest.main()
