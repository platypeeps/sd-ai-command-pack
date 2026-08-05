from __future__ import annotations

import io
import json
import re
import stat
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout

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

    def test_tool_environment_namespace_path_embeds_current_uid(self) -> None:
        lib = self.load_lib()
        repo, cache_root = self.cache_fixture()
        _, cache_paths, namespace = lib.build_tool_environment(
            repo=repo,
            environ={lib.CACHE_ROOT_ENV: str(cache_root)},
        )
        self.assertTrue(namespace.name.startswith("sd-ai-command-pack-"))
        if hasattr(os, "getuid"):
            uid = str(os.getuid())
            self.assertIn(uid, namespace.name)
            # Every default per-tool cache (Python bytecode, uv, uv tools, ruff,
            # ...) inherits the uid-scoped namespace, so no class escapes it.
            for variable, path in cache_paths.items():
                with self.subTest(variable=variable):
                    self.assertIn(uid, str(path))

    def test_ensure_private_directory_rejects_foreign_owned_path(self) -> None:
        lib = self.load_lib()
        if not hasattr(lib.os, "getuid"):
            self.skipTest("POSIX ownership semantics unavailable")
        _repo, cache_root = self.cache_fixture()
        planted = cache_root / "sd-ai-command-pack-planted"
        planted.mkdir(parents=True, mode=0o700)
        self.addCleanup(planted.chmod, 0o700)
        foreign_uid = lib.os.getuid() + 1
        with mock.patch.object(lib.os, "getuid", return_value=foreign_uid):
            with self.assertRaisesRegex(
                lib.CacheSetupError, "not owned by the current user"
            ):
                lib._ensure_private_directory(planted, label="pack cache namespace")

    def test_tool_environment_rejects_foreign_owned_namespace(self) -> None:
        lib = self.load_lib()
        if not hasattr(lib.os, "getuid"):
            self.skipTest("POSIX ownership semantics unavailable")
        repo, cache_root = self.cache_fixture()
        cache_root.mkdir(mode=0o700)
        # A co-tenant pre-creates the victim's deterministic namespace at 0700.
        fixed_name = "sd-ai-command-pack-planted-namespace"
        planted = cache_root / fixed_name
        planted.mkdir(mode=0o700)
        self.addCleanup(planted.chmod, 0o700)
        foreign_uid = lib.os.getuid() + 1
        with (
            mock.patch.object(lib, "_cache_namespace_name", return_value=fixed_name),
            mock.patch.object(lib.os, "getuid", return_value=foreign_uid),
        ):
            with self.assertRaisesRegex(
                lib.CacheSetupError, "not owned by the current user"
            ):
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

    # -- environment-blocked recovery evidence ------------------------------

    def test_environment_evidence_builds_every_boundary(self) -> None:
        lib = self.load_lib()
        for boundary in lib.ENVIRONMENT_BOUNDARIES:
            fragment = lib.build_environment_blocked_evidence(
                boundary=boundary,
                operation="probe",
                checkpoint="pre-mutation",
                mutation_state="none",
                retryable=True,
            )
            self.assertEqual(fragment["reasonCode"], "environment_blocked")
            self.assertEqual(fragment["schemaVersion"], 1)
            self.assertEqual(fragment["boundary"], boundary)
            self.assertIsNone(fragment["recoveryAction"])
            # A well-formed fragment validates and normalizes to itself.
            self.assertEqual(lib.validate_environment_blocked_evidence(fragment), fragment)

    def test_environment_evidence_rejects_unknown_boundary_and_state(self) -> None:
        lib = self.load_lib()
        with self.assertRaises(lib.EnvironmentEvidenceError):
            lib.build_environment_blocked_evidence(
                boundary="network",
                operation="op",
                checkpoint="c",
                mutation_state="none",
                retryable=False,
            )
        with self.assertRaises(lib.EnvironmentEvidenceError):
            lib.build_environment_blocked_evidence(
                boundary="git-metadata",
                operation="op",
                checkpoint="c",
                mutation_state="rolled-back",
                retryable=False,
            )

    def test_environment_evidence_retry_requires_known_mutation_state(self) -> None:
        lib = self.load_lib()
        with self.assertRaises(lib.EnvironmentEvidenceError):
            lib.build_environment_blocked_evidence(
                boundary="user-state",
                operation="persist-lock",
                checkpoint="lock-held",
                mutation_state="unknown",
                retryable=True,
            )
        # Not retryable with an unknown mutation state is allowed.
        fragment = lib.build_environment_blocked_evidence(
            boundary="user-state",
            operation="persist-lock",
            checkpoint="lock-held",
            mutation_state="unknown",
            retryable=False,
        )
        self.assertFalse(fragment["retryable"])
        self.assertEqual(fragment["mutationState"], "unknown")

    def test_environment_evidence_redacts_and_bounds_diagnostic(self) -> None:
        lib = self.load_lib()
        secret = (
            "clone failed for https://user:s3cr3t@example.com/repo.git "
            "with token ghp_ABCDEFGH012345678 and Bearer aa.bb.cc-DDDD "
            "line1\nline2\ttabbed"
        )
        fragment = lib.build_environment_blocked_evidence(
            boundary="git-metadata",
            operation="fetch-prune",
            checkpoint="pre-fetch",
            mutation_state="none",
            retryable=True,
            diagnostic=secret + " " + ("x" * 900),
        )
        diagnostic = fragment["diagnostic"]
        # Assert the credential BODY alone, never prefix+body as one literal: a
        # prefix-only substituter that leaves the body behind must fail here.
        self.assertNotIn("s3cr3t", diagnostic)
        self.assertNotIn("ABCDEFGH012345678", diagnostic)
        self.assertNotIn("aa.bb.cc-DDDD", diagnostic)
        self.assertIn("[redacted]@example.com", diagnostic)
        self.assertNotIn("\n", diagnostic)
        self.assertNotIn("\t", diagnostic)
        self.assertLessEqual(len(diagnostic), lib.ENVIRONMENT_DIAGNOSTIC_LIMIT)
        self.assertTrue(diagnostic.endswith("…"))

    def test_environment_evidence_redacts_shared_secret_shapes(self) -> None:
        # R1/R4: every shape the shared set covers is SUBSTITUTED in the lib
        # path, with the secret BODY absent and surrounding context preserved.
        # The github_pat_ case fails on the pre-consolidation redactor (AC2):
        # gh[pousr]_ excludes the "i" and no other old alternative applied.
        lib = self.load_lib()
        cases = [
            # (input, secret body that must NOT survive, context that must)
            (
                "token ghp_ABCDEFGH012345678 here",
                "ABCDEFGH012345678",
                ("token", "here"),
            ),
            (
                "auth failed for github_pat_11ABCDE_xyzXYZ0123456789 in remote",
                "11ABCDE_xyzXYZ0123456789",
                ("auth failed for", "in remote"),
            ),
            (
                "slack xoxb-1111-2222-abcdefghij done",
                "xoxb-1111-2222-abcdefghij",
                ("slack", "done"),
            ),
            (
                "openai sk-ABCDEF0123456789 leaked",
                "ABCDEF0123456789",
                ("openai", "leaked"),
            ),
            (
                "password: hunter2trailing next",
                "hunter2trailing",
                ("password", "next"),
            ),
            (
                "api_key=SECRETVALUE1234 next",
                "SECRETVALUE1234",
                ("api_key", "next"),
            ),
        ]
        for text, body, context in cases:
            with self.subTest(text=text):
                out = lib._redact_environment_text(
                    text, limit=lib.ENVIRONMENT_DIAGNOSTIC_LIMIT
                )
                self.assertNotIn(body, out)
                self.assertIn("[redacted]", out)
                for fragment in context:
                    self.assertIn(fragment, out)

    def test_environment_evidence_redacts_pem_private_key_block(self) -> None:
        # R1: PEM needs a multi-line SPAN, not a header match. A header-only
        # substituter would leave the entire key body in the diagnostic.
        lib = self.load_lib()
        body = "MIIBAAAAKEYMATERIAL0123456789abcdef"
        text = (
            "clone failed before "
            "-----BEGIN RSA PRIVATE KEY-----\n" + body + "\n"
            "-----END RSA PRIVATE KEY----- and after"
        )
        out = lib._redact_environment_text(
            text, limit=lib.ENVIRONMENT_DIAGNOSTIC_LIMIT
        )
        self.assertNotIn(body, out)
        self.assertNotIn("PRIVATE KEY", out)
        self.assertIn("before", out)
        self.assertIn("after", out)

    def test_environment_evidence_preserves_context_around_key_value(self) -> None:
        # R3: the bounded key-value substituter must not swallow trailing
        # punctuation. The old fleet detector's \S+ turned
        # "password: hunter2trailing, then continue" into "[redacted] ..."
        # -- losing the comma and the key. The bounded form keeps both.
        lib = self.load_lib()
        out = lib._redact_environment_text(
            "password: hunter2trailing, then continue",
            limit=lib.ENVIRONMENT_DIAGNOSTIC_LIMIT,
        )
        self.assertNotIn("hunter2trailing", out)
        self.assertIn("password:", out)
        self.assertIn(", then continue", out)

    def test_environment_evidence_redactor_never_weakens(self) -> None:
        # R7: keep the pre-consolidation lib pattern as TEST-ONLY data and
        # require every span it redacted is still redacted by the new set --
        # both the whole match and, decisively, the secret body tail (the
        # prefix-only-leak regression this task is most likely to introduce).
        lib = self.load_lib()
        old = re.compile(
            r"(?i)(?:bearer\s+|(?:access[_-]?|api[_-]?)?token[=:]\s*|gh[pousr]_)"
            r"[A-Za-z0-9._\-]{8,}"
        )
        corpus = [
            "clone failed for https://user:s3cr3t@example.com/repo.git "
            "with token ghp_ABCDEFGH012345678 and Bearer aa.bb.cc-DDDD",
            "access_token: ghp_ZZZZZZZZ99999999 rejected",
            "api-token=abcdefgh12345678 boundary",
            "github_pat_11ABCDE_xyzXYZ0123456789 leaked",
            "xoxb-1111-2222-abcdefghij and sk-ABCDEF0123456789",
        ]
        for text in corpus:
            with self.subTest(text=text):
                new_out = lib._redact_environment_text(text, limit=10000)
                for match in old.finditer(text):
                    span = match.group(0)
                    self.assertNotIn(span, new_out)
                    body = re.search(r"[A-Za-z0-9._-]+$", span).group(0)
                    self.assertNotIn(body, new_out)

    def test_environment_evidence_openai_prefix_requires_token_boundary(self) -> None:
        # The bare "sk-" prefix must only match at a token boundary. Without the
        # leading (?<![A-Za-z0-9]) guard, ordinary hyphenated words whose tail
        # starts "sk-" ("task-management" -> "sk-management") were over-redacted
        # by the lib and spuriously rejected by the fleet detector.
        lib = self.load_lib()
        detector = lib.compiled_secret_detector()
        for benign in (
            "task-management-summary",
            "mask-alignment-data",
            "risk-assessment-done",
        ):
            with self.subTest(benign=benign):
                out = lib._redact_environment_text(
                    benign, limit=lib.ENVIRONMENT_DIAGNOSTIC_LIMIT
                )
                self.assertEqual(out, benign)
                self.assertIsNone(detector.search(benign))
        for real in ("sk-abcdefghij012345", "token sk-proj-abcd1234efgh"):
            with self.subTest(real=real):
                out = lib._redact_environment_text(
                    real, limit=lib.ENVIRONMENT_DIAGNOSTIC_LIMIT
                )
                self.assertIn("[redacted]", out)
                self.assertNotIn("abcd", out)
                self.assertIsNotNone(detector.search(real))

    def test_environment_evidence_redacts_unterminated_pem_block(self) -> None:
        # A truncated / unterminated PRIVATE KEY (no END footer within the bound)
        # must still have its body redacted from the fail-open lib path, not just
        # detected by the fail-closed fleet path. The END-anchored span alone
        # left the key body in the diagnostic.
        lib = self.load_lib()
        body = "MIIBSECRETKEYMATERIAL0123456789abcdef"
        text = "cfg: -----BEGIN RSA PRIVATE KEY-----\n" + body + "\nMOREKEY tail"
        out = lib._redact_environment_text(
            text, limit=lib.ENVIRONMENT_DIAGNOSTIC_LIMIT
        )
        self.assertNotIn(body, out)
        self.assertNotIn("PRIVATE KEY", out)
        self.assertIn("[redacted]", out)
        self.assertIsNotNone(lib.compiled_secret_detector().search(text))

    def test_environment_evidence_renders_paths_and_preserves_plain_urls(self) -> None:
        lib = self.load_lib()
        fragment = lib.build_environment_blocked_evidence(
            boundary="tool-cache",
            operation="cache-setup",
            checkpoint="cache-setup",
            mutation_state="none",
            retryable=True,
            diagnostic=(
                "pack cache namespace is not writable: /Users/alex/secret/ns "
                "after cloning https://example.com/org/repo.git"
            ),
        )
        diagnostic = fragment["diagnostic"]
        # Arbitrary raw filesystem paths must be rendered, never leaked verbatim.
        self.assertNotIn("/Users/alex/secret/ns", diagnostic)
        self.assertIn("[path]", diagnostic)
        # Plain (credential-free) remote URLs remain permitted diagnostic context.
        self.assertIn("https://example.com/org/repo.git", diagnostic)

    def test_environment_evidence_recovery_action_argv_is_bounded_data(self) -> None:
        lib = self.load_lib()
        fragment = lib.build_environment_blocked_evidence(
            boundary="tool-cache",
            operation="cache-setup",
            checkpoint="cache-missing",
            mutation_state="none",
            retryable=True,
            recovery_action={
                "kind": "argv",
                "argv": ["sd-toolchain", "doctor", "--repo", "."] + ["x"] * 40,
            },
        )
        action = fragment["recoveryAction"]
        self.assertEqual(action["kind"], "argv")
        self.assertIsInstance(action["argv"], list)
        # Token count is capped; the value is a token list, never a shell string.
        self.assertLessEqual(len(action["argv"]), 32)
        self.assertEqual(action["argv"][0], "sd-toolchain")

    def test_environment_evidence_recovery_action_rejects_malformed(self) -> None:
        lib = self.load_lib()
        for bad in (
            {"kind": "argv", "argv": []},
            {"kind": "argv", "argv": ["\x00\x1f"]},
            {"kind": "skill", "instruction": ""},
            {"kind": "exec", "argv": ["x"]},
            "rm -rf /",
        ):
            with self.assertRaises(lib.EnvironmentEvidenceError):
                lib.build_environment_blocked_evidence(
                    boundary="managed-payload",
                    operation="install",
                    checkpoint="pre-write",
                    mutation_state="none",
                    retryable=False,
                    recovery_action=bad,
                )

    def test_environment_evidence_validator_rejects_and_drops_unknown(self) -> None:
        lib = self.load_lib()
        with self.assertRaises(lib.EnvironmentEvidenceError):
            lib.validate_environment_blocked_evidence("not-a-mapping")
        with self.assertRaises(lib.EnvironmentEvidenceError):
            lib.validate_environment_blocked_evidence(
                {"reasonCode": "other", "schemaVersion": 1}
            )
        with self.assertRaises(lib.EnvironmentEvidenceError):
            lib.validate_environment_blocked_evidence(
                {
                    "reasonCode": "environment_blocked",
                    "schemaVersion": 2,
                    "boundary": "git-metadata",
                    "mutationState": "none",
                    "retryable": False,
                }
            )
        # Unknown extra fields are dropped by re-normalization.
        normalized = lib.validate_environment_blocked_evidence(
            {
                "schemaVersion": 1,
                "reasonCode": "environment_blocked",
                "boundary": "kb-target",
                "operation": "kb-refresh",
                "retryable": False,
                "checkpoint": "pre-refresh",
                "mutationState": "partial-recoverable",
                "recoveryAction": None,
                "diagnostic": "linked kb target is not writable",
                "surprise": "ignored",
            }
        )
        self.assertNotIn("surprise", normalized)
        self.assertEqual(normalized["boundary"], "kb-target")

    # -- tool-cache boundary: cache-setup classifier and CLI ---------------

    def test_cache_setup_blocked_evidence_is_retryable_tool_cache(self) -> None:
        lib = self.load_lib()
        evidence = lib.cache_setup_blocked_evidence(
            lib.CacheSetupError(
                "cache setup failed for external tools: "
                "https://user:s3cr3t@example.com denied"
            ),
            operation="record session",
        )
        self.assertEqual(evidence["boundary"], "tool-cache")
        self.assertEqual(evidence["mutationState"], "none")
        self.assertTrue(evidence["retryable"])
        self.assertEqual(evidence["recoveryAction"]["kind"], "skill")
        self.assertIn(lib.CACHE_ROOT_ENV, evidence["recoveryAction"]["instruction"])
        self.assertNotIn("s3cr3t", evidence["diagnostic"])
        # A consumer can validate exactly what the owner emitted.
        self.assertEqual(lib.validate_environment_blocked_evidence(evidence), evidence)

    def test_cache_env_main_json_success_emits_cache_env(self) -> None:
        lib = self.load_lib()
        fake_env = {variable: f"/cache/{variable}" for variable in lib.CACHE_ENV_KEYS}
        stream = io.StringIO()
        with mock.patch.object(
            lib, "build_tool_environment", return_value=(fake_env, {}, Path("/ns"))
        ), redirect_stdout(stream):
            code = lib._cache_env_main(["cache-env", "--repo", "/repo", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["outcome"], "ok")
        self.assertEqual(set(payload["cacheEnv"]), set(lib.CACHE_ENV_KEYS))
        self.assertNotIn("environmentBlocked", payload)

    def test_cache_env_main_json_failure_emits_validated_fragment(self) -> None:
        lib = self.load_lib()
        stream = io.StringIO()
        with mock.patch.object(
            lib,
            "build_tool_environment",
            side_effect=lib.CacheSetupError(
                "cache setup failed for external tools: boom"
            ),
        ), redirect_stdout(stream):
            code = lib._cache_env_main(["cache-env", "--repo", "/repo", "--json"])
        self.assertEqual(code, 2)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["outcome"], "blocked")
        fragment = payload["environmentBlocked"]
        self.assertEqual(fragment["boundary"], "tool-cache")
        self.assertTrue(fragment["retryable"])
        # The emitted fragment survives consumer validation unchanged.
        self.assertEqual(lib.validate_environment_blocked_evidence(fragment), fragment)

    def test_cache_env_main_plaintext_paths_are_unchanged(self) -> None:
        lib = self.load_lib()
        fake_env = {variable: f"/cache/{variable}" for variable in lib.CACHE_ENV_KEYS}
        out = io.StringIO()
        with mock.patch.object(
            lib, "build_tool_environment", return_value=(fake_env, {}, Path("/ns"))
        ), redirect_stdout(out):
            code = lib._cache_env_main(["cache-env", "--repo", "/repo"])
        self.assertEqual(code, 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(
            lines,
            [f"{variable}=/cache/{variable}" for variable in lib.CACHE_ENV_KEYS],
        )
        # Failure still goes to stderr as a bounded plaintext error, not JSON.
        err = io.StringIO()
        with mock.patch.object(
            lib, "build_tool_environment", side_effect=lib.CacheSetupError("boom")
        ), redirect_stderr(err):
            fail_code = lib._cache_env_main(["cache-env", "--repo", "/repo"])
        self.assertEqual(fail_code, 2)
        self.assertTrue(err.getvalue().startswith("error:"))


if __name__ == "__main__":
    _support.unittest.main()
