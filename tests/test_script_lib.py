from __future__ import annotations

import stat
from concurrent.futures import ThreadPoolExecutor

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

subprocess = _support.subprocess
mock = _support.mock
install = _support.install
InstallTestCase = _support.InstallTestCase
Path = _support.Path
os = _support.os
tempfile = _support.tempfile


class ScriptLibTests(InstallTestCase):
    def load_lib(self):
        return self.load_module_from_path(
            install.ROOT / "scripts/sd_ai_command_pack_lib.py",
            "sd_ai_command_pack_lib_test",
        )

    def cache_fixture(self) -> tuple[Path, Path]:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-script-lib-cache-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        repo = root / "repo"
        repo.mkdir()
        return repo, root / "cache-root"

    def test_tool_environment_routes_cache_classes_and_preserves_credentials(self) -> None:
        lib = self.load_lib()
        repo, cache_root = self.cache_fixture()
        gh_config = str(repo.parent / "existing-gh-config")
        inherited = {
            "HOME": str(repo / "unwritable-home"),
            "PATH": os.environ.get("PATH", ""),
            "GH_CONFIG_DIR": gh_config,
            "GH_TOKEN": "credential-marker",
            "CUSTOM_ENV": "preserved",
            lib.CACHE_ROOT_ENV: str(cache_root),
        }

        environment, cache_paths, namespace = lib.build_tool_environment(
            repo=repo,
            environ=inherited,
        )
        second_environment, _, second_namespace = lib.build_tool_environment(
            repo=repo,
            environ=inherited,
        )

        self.assertEqual(namespace, second_namespace)
        self.assertEqual(environment["GH_CONFIG_DIR"], gh_config)
        self.assertEqual(environment["GH_TOKEN"], "credential-marker")
        self.assertEqual(environment["CUSTOM_ENV"], "preserved")
        self.assertEqual(set(cache_paths), set(lib.CACHE_ENV_KEYS))
        self.assertNotIn(str(repo), namespace.name)
        self.assertEqual(stat.S_IMODE(namespace.stat().st_mode), 0o700)
        for variable, path in cache_paths.items():
            with self.subTest(variable=variable):
                self.assertEqual(environment[variable], str(path))
                self.assertEqual(second_environment[variable], str(path))
                self.assertTrue(path.is_dir())
                self.assertFalse(path.is_relative_to(repo))
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_tool_environment_falls_back_from_unwritable_home_to_temp_root(self) -> None:
        lib = self.load_lib()
        repo, cache_root = self.cache_fixture()
        environment, _, namespace = lib.build_tool_environment(
            repo=repo,
            environ={
                "HOME": str(repo / "unwritable-home"),
                "TMPDIR": str(cache_root),
                "GH_CONFIG_DIR": "/existing/gh-config",
            },
        )

        self.assertEqual(namespace.parent, cache_root.resolve())
        self.assertEqual(environment["GH_CONFIG_DIR"], "/existing/gh-config")

    def test_tool_environment_reuses_generated_xdg_namespace(self) -> None:
        lib = self.load_lib()
        repo, cache_root = self.cache_fixture()
        environment, _, namespace = lib.build_tool_environment(
            repo=repo,
            environ={"TMPDIR": str(cache_root)},
        )

        second_environment, _, second_namespace = lib.build_tool_environment(
            repo=repo,
            environ=environment,
        )

        self.assertEqual(second_namespace, namespace)
        self.assertEqual(second_environment["XDG_CACHE_HOME"], environment["XDG_CACHE_HOME"])
        self.assertEqual(namespace.parent, cache_root.resolve())

    def test_tool_environment_preserves_valid_individual_cache_override(self) -> None:
        lib = self.load_lib()
        repo, cache_root = self.cache_fixture()
        pip_override = repo.parent / "pip-override"
        pip_override.mkdir(mode=0o700)

        environment, _, _ = lib.build_tool_environment(
            repo=repo,
            environ={
                lib.CACHE_ROOT_ENV: str(cache_root),
                "PIP_CACHE_DIR": str(pip_override),
            },
        )

        self.assertEqual(environment["PIP_CACHE_DIR"], str(pip_override.resolve()))

    def test_tool_environment_rejects_unsafe_explicit_roots(self) -> None:
        lib = self.load_lib()
        repo, cache_root = self.cache_fixture()
        non_directory = repo.parent / "not-a-directory"
        non_directory.write_text("not a directory", encoding="utf-8")
        symlink = repo.parent / "cache-link"
        symlink.symlink_to(cache_root)
        cases = {
            "relative": Path("relative-cache"),
            "repository-contained": repo / "cache",
            "symlink": symlink,
            "non-directory": non_directory,
        }

        for label, value in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(lib.CacheSetupError):
                    lib.build_tool_environment(
                        repo=repo,
                        environ={lib.CACHE_ROOT_ENV: str(value)},
                    )

    def test_tool_environment_uses_worktree_root_for_subdirectory_input(self) -> None:
        lib = self.load_lib()
        repo, _ = self.cache_fixture()
        (repo / ".git").mkdir()
        subdirectory = repo / "nested" / "work"
        subdirectory.mkdir(parents=True)
        repository_cache = repo / ".cache"

        with self.assertRaisesRegex(lib.CacheSetupError, "outside the repository"):
            lib.build_tool_environment(
                repo=subdirectory,
                environ={lib.CACHE_ROOT_ENV: str(repository_cache)},
            )

        self.assertFalse(repository_cache.exists())

    def test_tool_environment_rejects_non_private_namespace(self) -> None:
        lib = self.load_lib()
        repo, cache_root = self.cache_fixture()
        _, _, namespace = lib.build_tool_environment(
            repo=repo,
            environ={lib.CACHE_ROOT_ENV: str(cache_root)},
        )
        namespace.chmod(0o755)
        self.addCleanup(namespace.chmod, 0o700)

        with self.assertRaisesRegex(lib.CacheSetupError, "permissions"):
            lib.build_tool_environment(
                repo=repo,
                environ={lib.CACHE_ROOT_ENV: str(cache_root)},
            )

    def test_tool_environment_skips_posix_metadata_checks_on_windows(self) -> None:
        lib = self.load_lib()
        _repo, cache_root = self.cache_fixture()
        cache_root.mkdir()
        cache_root.chmod(0o777)
        self.addCleanup(cache_root.chmod, 0o700)

        with (
            mock.patch.object(lib.os, "name", "nt"),
            mock.patch.object(lib.os, "getuid", return_value=999_999),
        ):
            validated = lib._ensure_private_directory(
                cache_root,
                label="test cache",
            )

        self.assertEqual(validated, cache_root)

    def test_tool_environment_concurrent_creation_is_stable(self) -> None:
        lib = self.load_lib()
        repo, cache_root = self.cache_fixture()
        inherited = {lib.CACHE_ROOT_ENV: str(cache_root)}

        with ThreadPoolExecutor(max_workers=8) as executor:
            namespaces = list(
                executor.map(
                    lambda _: lib.build_tool_environment(
                        repo=repo,
                        environ=inherited,
                    )[2],
                    range(16),
                )
            )

        self.assertEqual(len(set(namespaces)), 1)

    def test_run_command_routes_stubbed_gh_cache_without_hiding_auth(self) -> None:
        lib = self.load_lib()
        repo, cache_root = self.cache_fixture()
        bin_dir = repo.parent / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/usr/bin/env python3\n"
            "import os\n"
            "print(os.environ['XDG_CACHE_HOME'])\n"
            "print(os.environ['GH_CONFIG_DIR'])\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)

        result = lib.run_command(
            ["gh", "run", "view", "--log-failed"],
            cwd=repo,
            env={
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                "HOME": str(repo / "unwritable-home"),
                "GH_CONFIG_DIR": "/existing/gh-config",
                lib.CACHE_ROOT_ENV: str(cache_root),
            },
            check=True,
            context="read failed run logs",
        )

        xdg_cache, gh_config = result.stdout.splitlines()
        self.assertTrue(Path(xdg_cache).is_dir())
        self.assertFalse(Path(xdg_cache).is_relative_to(repo))
        self.assertEqual(gh_config, "/existing/gh-config")

    def test_invalid_cache_setup_stops_before_command_invocation(self) -> None:
        lib = self.load_lib()
        repo, _ = self.cache_fixture()

        with mock.patch("subprocess.run") as run:
            with self.assertRaisesRegex(lib.CacheSetupError, "outside the repository"):
                lib.run_command(
                    ["gh", "auth", "status"],
                    cwd=repo,
                    env={lib.CACHE_ROOT_ENV: str(repo / "cache")},
                )
        run.assert_not_called()

    def test_pack_entry_points_delegate_cache_policy_to_shared_builder(self) -> None:
        shell_lib = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("prepare_tool_cache_env()", shell_lib)
        self.assertIn(
            'lib_dir="$(cd -- "$lib_dir" 2>/dev/null && pwd -P)"', shell_lib
        )
        self.assertNotIn("prepare_gito_uv_env", shell_lib)
        self.assertNotIn("SD_AI_COMMAND_PACK_REVIEW_LOCAL_UV_", shell_lib)

        for name in (
            "sd-ai-command-pack-full-check.sh",
            "sd-ai-command-pack-review-local.sh",
            "sd-ai-command-pack-review-scope.sh",
            "sd-ai-command-pack-housekeeping.sh",
        ):
            content = (install.ROOT / "templates/scripts" / name).read_text(
                encoding="utf-8"
            )
            self.assertIn("prepare_tool_cache_env", content, name)

        for name in (
            "sd-ai-command-pack-status.py",
            "sd-ai-command-pack-pr-eligibility.py",
            "sd-ai-command-pack-install-audit.py",
            "sd-ai-command-pack-work-loop.py",
        ):
            content = (install.ROOT / "templates/scripts" / name).read_text(
                encoding="utf-8"
            )
            self.assertIn("build_tool_environment", content, name)

    def test_shared_shell_cache_parser_strips_crlf(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        tempdir = tempfile.TemporaryDirectory(prefix="sd-shell-cache-crlf-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        scripts = root / "scripts"
        scripts.mkdir()
        shell_lib = scripts / "sd-ai-command-pack-shell-lib.sh"
        shell_lib.write_text(
            (
                install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh"
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        toolchain = scripts / "sd-ai-command-pack-toolchain.sh"
        toolchain.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'XDG_CACHE_HOME=/cache/xdg\\r\\n'\n"
            "printf 'PYTHONPYCACHEPREFIX=/cache/python\\r\\n'\n"
            "printf 'UV_CACHE_DIR=/cache/uv\\r\\n'\n"
            "printf 'UV_TOOL_DIR=/cache/uv-tools\\r\\n'\n"
            "printf 'PIP_CACHE_DIR=/cache/pip\\r\\n'\n"
            "printf 'RUFF_CACHE_DIR=/cache/ruff\\r\\n'\n"
            "printf 'NPM_CONFIG_CACHE=/cache/npm\\r\\n'\n",
            encoding="utf-8",
        )
        toolchain.chmod(0o755)

        result = subprocess.run(
            [
                self._bash_path,
                "-c",
                (
                    "warn() { printf '%s\\n' \"$*\" >&2; }; "
                    "source \"$1\"; "
                    "export SD_AI_COMMAND_PACK_REPO_ROOT=\"$2\"; "
                    "prepare_tool_cache_env; "
                    "printf '<%s>\\n' \"$XDG_CACHE_HOME\" \"$NPM_CONFIG_CACHE\""
                ),
                "bash",
                str(shell_lib),
                str(root),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["</cache/xdg>", "</cache/npm>"])

    def test_shared_shell_cache_failure_suppresses_nested_stderr(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        tempdir = tempfile.TemporaryDirectory(prefix="sd-shell-cache-failure-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        scripts = root / "scripts"
        scripts.mkdir()
        shell_lib = scripts / "sd-ai-command-pack-shell-lib.sh"
        shell_lib.write_text(
            (
                install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh"
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        toolchain = scripts / "sd-ai-command-pack-toolchain.sh"
        toolchain.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'raw nested helper diagnostic /host/path\\n' >&2\n"
            "exit 5\n",
            encoding="utf-8",
        )
        toolchain.chmod(0o755)

        result = subprocess.run(
            [
                self._bash_path,
                "-c",
                (
                    "warn() { printf 'WARN:%s\\n' \"$*\" >&2; }; "
                    "source \"$1\"; "
                    "export SD_AI_COMMAND_PACK_REPO_ROOT=\"$2\"; "
                    "prepare_tool_cache_env"
                ),
                "bash",
                str(shell_lib),
                str(root),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertNotIn("raw nested helper", result.stderr)
        self.assertEqual(len(result.stderr.splitlines()), 1)
        self.assertIn("WARN:cache setup failed", result.stderr)

    def test_github_workflow_skills_require_argv_safe_cache_wrapper(self) -> None:
        for name in (
            "sd-create-pr",
            "sd-review-pr",
            "sd-watch-pr",
            "sd-fix-ci",
            "sd-update-deps",
            "sd-review-learnings",
            "sd-audit-repo",
        ):
            content = (
                install.ROOT / "templates/.agents/skills" / name / "SKILL.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "scripts/sd-ai-command-pack-toolchain.sh run -- <tool>",
                content,
                name,
            )
            self.assertIn("do not retry the tool bare", content, name)
            self.assertIn("GH_CONFIG_DIR", content, name)

    def test_command_detail_uses_stdout_or_fallback(self) -> None:
        lib = self.load_lib()

        stdout = subprocess.CompletedProcess(
            ["cmd"],
            1,
            stdout="useful stdout\n",
            stderr="",
        )
        empty = subprocess.CompletedProcess(["cmd"], 1, stdout="", stderr="")

        self.assertEqual(
            lib.command_detail(stdout, fallback="fallback detail"),
            "useful stdout",
        )
        self.assertEqual(
            lib.command_detail(empty, fallback="fallback detail"),
            "fallback detail",
        )

    def test_run_command_rejects_empty_command(self) -> None:
        lib = self.load_lib()

        with self.assertRaisesRegex(lib.CommandError, "cannot run an empty command"):
            lib.run_command([])

    def test_run_command_returns_completed_process(self) -> None:
        lib = self.load_lib()
        completed = subprocess.CompletedProcess(
            ["git", "status"],
            0,
            stdout="clean\n",
            stderr="",
        )

        with mock.patch("subprocess.run", return_value=completed) as run:
            result = lib.run_command(["git", "status"], context="check status")

        self.assertIs(result, completed)
        self.assertEqual(run.call_args.kwargs["timeout"], lib.DEFAULT_COMMAND_TIMEOUT)
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    def test_run_command_missing_binary_has_actionable_message(self) -> None:
        lib = self.load_lib()

        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(
                lib.CommandError,
                "missing-tool not found while trying to inspect tool",
            ):
                lib.run_command(["missing-tool"], context="inspect tool")

    def test_run_command_timeout_has_actionable_message(self) -> None:
        lib = self.load_lib()

        with mock.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(["git", "fetch"], timeout=3),
        ):
            with self.assertRaisesRegex(
                lib.CommandError,
                "git timed out after 3s while trying to fetch origin",
            ):
                lib.run_command(
                    ["git", "fetch"],
                    timeout=3,
                    context="fetch origin",
                )

    def test_run_command_checked_failure_uses_process_detail(self) -> None:
        lib = self.load_lib()
        completed = subprocess.CompletedProcess(
            ["gh", "pr", "view"],
            1,
            stdout="",
            stderr="not found\n",
        )

        with mock.patch("subprocess.run", return_value=completed):
            with self.assertRaisesRegex(
                lib.CommandError,
                "failed to inspect PR: not found",
            ):
                lib.run_command(["gh", "pr", "view"], check=True, context="inspect PR")

    def test_run_gh_wraps_command_with_gh_binary(self) -> None:
        lib = self.load_lib()
        completed = subprocess.CompletedProcess(["gh", "auth", "status"], 0, stdout="")

        with mock.patch("subprocess.run", return_value=completed) as run:
            result = lib.run_gh(["auth", "status"], context="check auth")

        self.assertIs(result, completed)
        self.assertEqual(run.call_args.args[0], ["gh", "auth", "status"])
        self.assertEqual(run.call_args.kwargs["timeout"], lib.DEFAULT_GH_TIMEOUT)

    def test_git_stdout_required_reports_git_failure(self) -> None:
        lib = self.load_lib()
        completed = subprocess.CompletedProcess(
            ["git", "rev-parse"],
            128,
            stdout="",
            stderr="fatal: not a git repository\n",
        )

        with mock.patch("subprocess.run", return_value=completed):
            with self.assertRaisesRegex(
                lib.CommandError,
                "failed to resolve repository root: fatal: not a git repository",
            ):
                lib.git_stdout(
                    ["rev-parse", "--show-toplevel"],
                    context="resolve repository root",
                    required=True,
                )

    def test_repo_root_uses_git_toplevel_or_cwd_fallback(self) -> None:
        lib = self.load_lib()
        completed = subprocess.CompletedProcess(
            ["git", "rev-parse", "--show-toplevel"],
            0,
            stdout="/tmp/example\n",
            stderr="",
        )

        with mock.patch("subprocess.run", return_value=completed):
            self.assertEqual(lib.repo_root(), Path("/tmp/example").resolve())

        failed = subprocess.CompletedProcess(
            ["git", "rev-parse", "--show-toplevel"],
            128,
            stdout="",
            stderr="fatal\n",
        )
        with mock.patch("subprocess.run", return_value=failed):
            self.assertEqual(lib.repo_root(fallback_to_cwd=True), install.ROOT.resolve())


if __name__ == "__main__":
    _support.unittest.main()
