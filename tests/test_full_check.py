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


class FullCheckTests(InstallTestCase):
    """Tests for full-check orchestration and optional review lanes."""

    def test_full_check_script_writes_gito_reports_to_artifact_dir(self) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR", script)
        self.assertIn(".build/review/gito", script)
        self.assertIn('gito review --vs "$base_ref" --filter "$filters" --out "$out_dir"', script)

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

    def test_full_check_script_warns_when_source_hook_unarmed(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        (root / "manifest.json").write_text(
            json.dumps(
                {"name": "sd-ai-command-pack", "version": "1.0.0", "files": []}
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "install.py").write_text("# source marker\n", encoding="utf-8")
        (root / "templates").mkdir()
        (root / ".githooks").mkdir()
        scripts_dir = root / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            scripts_dir / "sd-ai-command-pack-full-check.sh",
        )
        shutil.copy2(
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
            scripts_dir / "sd-ai-command-pack-shell-lib.sh",
        )

        command = (
            "export SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE=1; "
            "source scripts/sd-ai-command-pack-full-check.sh; "
            "warn_unarmed_pack_source_hook"
        )
        result = subprocess.run(
            [self._bash_path, "-c", command],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "pre-push chore-scope guard is not armed; "
            "run: git config core.hooksPath .githooks",
            result.stdout,
        )

        self.run_git(root, "config", "core.hooksPath", ".githooks")
        result = subprocess.run(
            [self._bash_path, "-c", command],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("pre-push chore-scope guard is not armed", result.stdout)

    def test_full_check_script_skips_source_hook_for_other_pack_identity(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        (root / "manifest.json").write_text(
            json.dumps(
                {"name": "se-ai-command-pack", "version": "1.0.0", "files": []}
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "install.py").write_text("# source marker\n", encoding="utf-8")
        (root / "templates").mkdir()
        (root / ".githooks").mkdir()
        scripts_dir = root / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            scripts_dir / "sd-ai-command-pack-full-check.sh",
        )
        shutil.copy2(
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
            scripts_dir / "sd-ai-command-pack-shell-lib.sh",
        )

        result = subprocess.run(
            [
                self._bash_path,
                "-c",
                "export SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE=1; "
                "source scripts/sd-ai-command-pack-full-check.sh; "
                "warn_unarmed_pack_source_hook",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("pre-push chore-scope guard is not armed", result.stdout)

    def test_full_check_script_explains_source_hook_skip_without_python(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        (root / "manifest.json").write_text(
            json.dumps(
                {"name": "sd-ai-command-pack", "version": "1.0.0", "files": []}
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "install.py").write_text("# source marker\n", encoding="utf-8")
        (root / "templates").mkdir()
        (root / ".githooks").mkdir()
        scripts_dir = root / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            scripts_dir / "sd-ai-command-pack-full-check.sh",
        )
        shutil.copy2(
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
            scripts_dir / "sd-ai-command-pack-shell-lib.sh",
        )

        result = subprocess.run(
            [
                self._bash_path,
                "-c",
                "export SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE=1; "
                "source scripts/sd-ai-command-pack-full-check.sh; "
                'have() { [ "$1" != "python3" ]; }; '
                "warn_unarmed_pack_source_hook",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "cannot verify pack source identity for the source-hook advisory",
            result.stdout,
        )
        self.assertIn("pre-push hook configuration is not checked", result.stdout)
        self.assertNotIn("pre-push chore-scope guard is not armed", result.stdout)

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
        self.assertIn("cleanup_full_check_temp_files()", script)
        self.assertIn("trap cleanup_full_check_temp_files EXIT", script)
        self.assertIn('if [ "${#REVIEW_LOCAL_TEMP_FILES[@]}" -gt 0 ]; then', script)
        self.assertIn('for file in "${REVIEW_LOCAL_TEMP_FILES[@]}"; do', script)
        self.assertIn("full_check_mktemp()", script)
        self.assertIn('mkdir -p -- "$temp_dir"', script)
        self.assertIn('trap \'exit 130\' INT', script)
        self.assertIn('REVIEW_LOCAL_TEMP_FILES+=("$paths_file")', script)
        self.assertIn('REVIEW_LOCAL_TEMP_FILES+=("$patterns_file")', script)
        self.assertIn('REVIEW_LOCAL_TEMP_FILES+=("$changed_paths_file")', script)
        self.assertIn('REVIEW_LOCAL_TEMP_FILES+=("$filters_file")', script)
        self.assertNotIn('collect_reviewable_changed_paths "$base_ref" |', script)
        self.assertNotIn('filters="$(reviewable_changed_filter_csv', script)
        self.assertIn('SCRIPT_NAME="$script_name" node -e', script)
        self.assertIn("process.env.SCRIPT_NAME", script)
        self.assertNotIn("process.argv[1]", script)

    def test_full_check_disjoint_history_warns_and_uses_all_tracked_files(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "head history")
        head_branch = self.git_output(root, "branch", "--show-current")

        self.run_git(root, "switch", "--orphan", "disjoint-base")
        (root / "base-only.txt").write_text("base\n", encoding="utf-8")
        self.run_git(root, "add", "base-only.txt")
        self.run_git(root, "commit", "-m", "disjoint history")
        self.run_git(root, "switch", head_branch)

        result = subprocess.run(
            [
                self._bash_path,
                "-c",
                "source scripts/sd-ai-command-pack-full-check.sh; "
                "collect_reviewable_changed_paths disjoint-base",
            ],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE": "1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Could not find a merge base", result.stdout)
        self.assertIn("scripts/sd-ai-command-pack-full-check.sh", result.stdout)

    def test_full_check_merge_base_git_error_still_fails(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")
        result = subprocess.run(
            [
                self._bash_path,
                "-c",
                "source scripts/sd-ai-command-pack-full-check.sh; "
                "git() { if [ \"$1\" = merge-base ]; then return 2; fi; "
                "command git \"$@\"; }; "
                "collect_reviewable_changed_paths HEAD",
            ],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE": "1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("git merge-base failed", result.stdout)

    def test_full_check_preflight_command_runs_without_login_shell(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        tool_log = root / "preflight-shell.log"

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "PREFLIGHT_SHELL_LOG": str(tool_log),
                "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND": (
                    "case \"$-\" in *l*) printf 'login\\n' ;; *) printf 'non-login\\n' ;; esac > \"$PREFLIGHT_SHELL_LOG\""
                ),
                "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_KB": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PACK_DRIFT": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(tool_log.read_text(encoding="utf-8"), "non-login\n")

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
        shutil.copyfile(
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
            root / "scripts/sd-ai-command-pack-shell-lib.sh",
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

    def test_full_check_script_does_not_retry_gito_when_latest_status_is_not_429(
        self,
    ) -> None:
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
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito attempt %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "printf 'ClientError: 429 Slow down\\n'\n"
            "printf 'Exception: provider summary 500\\n'\n"
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

    def test_full_check_script_skips_gito_cleanly_with_no_changed_files(self) -> None:
        # Prefer the system bash: on macOS that is 3.2, where an empty
        # array expansion under `set -u` is an unbound-variable error.
        system_bash = Path("/bin/bash")
        bash_path = str(system_bash) if system_bash.is_file() else self._bash_path
        if bash_path is None:
            self.skipTest("bash is not available on PATH or at /bin/bash")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.write_gito_pack_env(root)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-full-check-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito invoked %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
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
        self.assertIn(
            "No changed files remain after standard review-scan exclusions; "
            "skipping Gito review.",
            result.stdout,
        )
        self.assertNotIn("unbound variable", result.stdout)
        self.assertFalse(
            log_path.exists(),
            "gito must not be invoked when no reviewable files changed",
        )

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

    def test_full_check_script_sets_writable_uv_dirs_for_gito(self) -> None:
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
            f"printf 'UV_CACHE_DIR=%s\\n' \"$UV_CACHE_DIR\" >> {str(log_path)!r}\n"
            f"printf 'UV_TOOL_DIR=%s\\n' \"$UV_TOOL_DIR\" >> {str(log_path)!r}\n"
            f"printf 'gito %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)
        temp_root = root / "tmp"
        env = {
            **os.environ,
            "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
            "TMPDIR": str(temp_root),
            "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT": "0",
            "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0",
            "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
            "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK": "0",
            "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
            "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
            "SD_AI_COMMAND_PACK_FULL_CHECK_GITO": "1",
            "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF": "HEAD",
        }
        env.pop("UV_CACHE_DIR", None)
        env.pop("UV_TOOL_DIR", None)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        log = log_path.read_text(encoding="utf-8")
        user_root = temp_root / f"sd-ai-command-pack-{os.getuid()}"
        self.assertIn(f"UV_CACHE_DIR={user_root}/uv-cache", log)
        self.assertIn(f"UV_TOOL_DIR={user_root}/uv-tools", log)
        self.assertTrue((user_root / "uv-cache").is_dir())
        self.assertTrue((user_root / "uv-tools").is_dir())
        self.assertIn("gito review --vs HEAD --filter app.txt", log)

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

    def test_full_check_kb_freshness_skips_without_generated_kb(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = self._run_full_check_kb_lane(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "No generated .obsidian-kb folder; skipping Obsidian KB freshness",
            result.stdout,
        )

    def test_full_check_kb_freshness_passes_repairs_and_stays_strict(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Fresh Project\n", encoding="utf-8")
        kb_refresh = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(kb_refresh.returncode, 0, kb_refresh.stdout)

        result = self._run_full_check_kb_lane(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "SD AI command pack Obsidian KB freshness check", result.stdout
        )
        self.assertNotIn("Obsidian KB refresh", result.stdout)

        (root / "README.md").write_text("# Fresh Project, edited\n", encoding="utf-8")
        result = self._run_full_check_kb_lane(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "Generated Obsidian KB is stale; refreshing ignored output automatically",
            result.stdout,
        )
        self.assertIn(
            "SD AI command pack Obsidian KB post-refresh check", result.stdout
        )
        refreshed_check = subprocess.run(
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
        self.assertEqual(refreshed_check.returncode, 0, refreshed_check.stdout)

        copied_readme = root / ".obsidian-kb/Repository Overview/README.md"
        (root / "README.md").write_text("# Strict stale project\n", encoding="utf-8")
        copied_before_required = copied_readme.read_bytes()
        result = self._run_full_check_kb_lane(
            root, {"SD_AI_COMMAND_PACK_FULL_CHECK_KB": "required"}
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Generated Obsidian KB is stale or blocked", result.stdout)
        self.assertIn(
            "python3 scripts/sd-ai-command-pack-update-spec-kb.py", result.stdout
        )
        self.assertNotIn("Obsidian KB refresh", result.stdout)
        self.assertEqual(copied_readme.read_bytes(), copied_before_required)

        result = self._run_full_check_kb_lane(
            root, {"SD_AI_COMMAND_PACK_FULL_CHECK_KB": "0"}
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "Skipping Obsidian KB freshness check because "
            "SD_AI_COMMAND_PACK_FULL_CHECK_KB=0",
            result.stdout,
        )

    def test_full_check_kb_auto_repair_refuses_unignored_state(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Fresh Project\n", encoding="utf-8")
        kb_refresh = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(kb_refresh.returncode, 0, kb_refresh.stdout)

        gitignore = root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8").replace(".obsidian-kb/\n", ""),
            encoding="utf-8",
        )
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", ".obsidian-kb"],
            cwd=root,
            check=False,
        )
        self.assertNotEqual(ignored.returncode, 0)

        copied_readme = root / ".obsidian-kb/Repository Overview/README.md"
        copied_before = copied_readme.read_bytes()
        gitignore_before = gitignore.read_bytes()
        (root / "README.md").write_text("# Unignored stale project\n", encoding="utf-8")
        result = self._run_full_check_kb_lane(root)

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            ".obsidian-kb is not ignored; refusing automatic refresh",
            result.stdout,
        )
        self.assertEqual(copied_readme.read_bytes(), copied_before)
        self.assertEqual(gitignore.read_bytes(), gitignore_before)

    def test_full_check_kb_auto_repair_reports_refresh_failure(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Fresh Project\n", encoding="utf-8")
        helper = root / "scripts/sd-ai-command-pack-update-spec-kb.py"
        kb_refresh = subprocess.run(
            [sys.executable, str(helper)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(kb_refresh.returncode, 0, kb_refresh.stdout)
        helper.write_text(
            "import sys\n"
            "if '--check' in sys.argv[1:]:\n"
            "    print('synthetic stale check')\n"
            "    raise SystemExit(1)\n"
            "print('synthetic refresh failure')\n"
            "raise SystemExit(9)\n",
            encoding="utf-8",
        )

        result = self._run_full_check_kb_lane(root)

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("synthetic refresh failure", result.stdout)
        self.assertIn("Automatic Obsidian KB refresh failed", result.stdout)
        self.assertIn(
            "python3 scripts/sd-ai-command-pack-update-spec-kb.py", result.stdout
        )

    def test_full_check_kb_auto_repair_requires_passing_recheck(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Fresh Project\n", encoding="utf-8")
        helper = root / "scripts/sd-ai-command-pack-update-spec-kb.py"
        kb_refresh = subprocess.run(
            [sys.executable, str(helper)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(kb_refresh.returncode, 0, kb_refresh.stdout)
        helper.write_text(
            "import sys\n"
            "if '--check' in sys.argv[1:]:\n"
            "    print('synthetic stale check')\n"
            "    raise SystemExit(1)\n"
            "print('synthetic refresh success')\n",
            encoding="utf-8",
        )

        result = self._run_full_check_kb_lane(root)

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count("synthetic stale check"), 2)
        self.assertIn("synthetic refresh success", result.stdout)
        self.assertIn(
            "Generated Obsidian KB is still stale or blocked after refresh",
            result.stdout,
        )

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

    def test_full_check_script_runs_pack_source_drift_gates(self) -> None:
        script = (
            install.ROOT / "scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("run_pack_source_drift_gates", script)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_PACK_DRIFT", script)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF", script)
        self.assertIn("template twin pairs compared", script)
        self.assertIn("release version drift", script)
        self.assertIn("undocumented env var", script)
        self.assertIn("shipped scripts or skills", script)
        self.assertIn("in skills", script)


if __name__ == "__main__":
    unittest.main()
