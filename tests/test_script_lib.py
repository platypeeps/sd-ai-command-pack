from __future__ import annotations

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


class ScriptLibTests(InstallTestCase):
    def load_lib(self):
        return self.load_module_from_path(
            install.ROOT / "scripts/sd_ai_command_pack_lib.py",
            "sd_ai_command_pack_lib_test",
        )

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
