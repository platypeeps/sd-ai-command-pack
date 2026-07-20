from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
os = _support.os
shutil = _support.shutil
subprocess = _support.subprocess
sys = _support.sys
unittest = _support.unittest
Path = _support.Path
install = _support.install
InstallTestCase = _support.InstallTestCase


class ReviewFullCheckTests(InstallTestCase):
    """Tests for the sd-review-pr deterministic full-check selector."""

    def make_review_repo(
        self, package: object | None, *, with_fallback: bool = True
    ) -> tuple[Path, Path, Path]:
        root = self.make_repo()
        scripts_dir = root / "scripts"
        scripts_dir.mkdir()

        for name in (
            "sd-ai-command-pack-review-full-check.sh",
            "sd-ai-command-pack-toolchain.sh",
        ):
            shutil.copy2(install.ROOT / f"templates/scripts/{name}", scripts_dir / name)

        fallback_log = root / "fallback.log"
        if with_fallback:
            fallback = scripts_dir / "sd-ai-command-pack-full-check.sh"
            fallback.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s|%s\\n' "
                '"$SD_AI_COMMAND_PACK_FULL_CHECK_PRISM" '
                '"$SD_AI_COMMAND_PACK_FULL_CHECK_GITO" > "$TEST_FALLBACK_LOG"\n'
                'exit "${TEST_FALLBACK_EXIT:-0}"\n',
                encoding="utf-8",
            )
            fallback.chmod(0o755)

        if package is not None:
            package_text = package if isinstance(package, str) else json.dumps(package)
            (root / "package.json").write_text(package_text + "\n", encoding="utf-8")

        runner_log = root / "runner.log"
        bin_dir = root / "bin"
        bin_dir.mkdir()
        runner = bin_dir / "npm"
        runner.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s|%s|%s\\n' "
            '"$*" "$SD_AI_COMMAND_PACK_FULL_CHECK_PRISM" '
            '"$SD_AI_COMMAND_PACK_FULL_CHECK_GITO" > "$TEST_RUNNER_LOG"\n'
            'exit "${TEST_RUNNER_EXIT:-0}"\n',
            encoding="utf-8",
        )
        runner.chmod(0o755)

        return root, runner_log, fallback_log

    def run_review_full_check(
        self,
        root: Path,
        runner_log: Path,
        fallback_log: Path,
        **extra_env: str,
    ) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
            "SD_AI_COMMAND_PACK_PYTHON": sys.executable,
            "TEST_RUNNER_LOG": str(runner_log),
            "TEST_FALLBACK_LOG": str(fallback_log),
            **extra_env,
        }
        return subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-full-check.sh"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_configured_check_full_uses_package_runner_with_review_tools_disabled(
        self,
    ) -> None:
        root, runner_log, fallback_log = self.make_review_repo(
            {"scripts": {"check:full": "prepare && bash scripts/sd-ai-command-pack-full-check.sh"}}
        )

        result = self.run_review_full_check(
            root,
            runner_log,
            fallback_log,
            SD_AI_COMMAND_PACK_FULL_CHECK_PRISM="required",
            SD_AI_COMMAND_PACK_FULL_CHECK_GITO="1",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(runner_log.read_text(encoding="utf-8"), "run check:full|0|0\n")
        self.assertFalse(fallback_log.exists())

    def test_configured_runner_exit_status_is_propagated(self) -> None:
        root, runner_log, fallback_log = self.make_review_repo(
            {"scripts": {"check:full": "project gate"}}
        )

        result = self.run_review_full_check(
            root, runner_log, fallback_log, TEST_RUNNER_EXIT="17"
        )

        self.assertEqual(result.returncode, 17, result.stdout)
        self.assertTrue(runner_log.exists())
        self.assertFalse(fallback_log.exists())

    def test_missing_or_invalid_configuration_uses_pack_fallback(self) -> None:
        cases: tuple[object | None, ...] = (
            None,
            "{not json",
            [],
            {},
            {"scripts": []},
            {"scripts": {}},
            {"scripts": {"check:full": ""}},
            {"scripts": {"check:full": ["not", "a", "string"]}},
        )

        for package in cases:
            with self.subTest(package=package):
                root, runner_log, fallback_log = self.make_review_repo(package)

                result = self.run_review_full_check(
                    root,
                    runner_log,
                    fallback_log,
                    SD_AI_COMMAND_PACK_FULL_CHECK_PRISM="required",
                    SD_AI_COMMAND_PACK_FULL_CHECK_GITO="1",
                )

                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(
                    fallback_log.read_text(encoding="utf-8"), "0|0\n"
                )
                self.assertFalse(runner_log.exists())

    def test_fallback_exit_status_is_propagated(self) -> None:
        root, runner_log, fallback_log = self.make_review_repo(None)

        result = self.run_review_full_check(
            root, runner_log, fallback_log, TEST_FALLBACK_EXIT="23"
        )

        self.assertEqual(result.returncode, 23, result.stdout)
        self.assertTrue(fallback_log.exists())
        self.assertFalse(runner_log.exists())

    def test_recursive_configuration_is_rejected(self) -> None:
        commands = (
            "sd-review-pr",
            "codex /sd:review-pr",
            "bash .claude/commands/sd/review-pr.md",
            "bash scripts/sd-ai-command-pack-review-full-check.sh",
        )

        for command in commands:
            with self.subTest(command=command):
                root, runner_log, fallback_log = self.make_review_repo(
                    {"scripts": {"check:full": command}}
                )

                result = self.run_review_full_check(root, runner_log, fallback_log)

                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("must not invoke sd-review-pr", result.stdout)
                self.assertFalse(runner_log.exists())
                self.assertFalse(fallback_log.exists())

    def test_missing_configured_runner_is_reported(self) -> None:
        root, runner_log, fallback_log = self.make_review_repo(
            {"scripts": {"check:full": "project gate"}}
        )

        result = self.run_review_full_check(
            root,
            runner_log,
            fallback_log,
            SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_RUNNER="missing-package-runner",
        )

        self.assertEqual(result.returncode, 127, result.stdout)
        self.assertIn("configured package runner not found", result.stdout)
        self.assertFalse(fallback_log.exists())

    def test_toolchain_failure_is_reported_without_fallback(self) -> None:
        root, runner_log, fallback_log = self.make_review_repo(
            {"scripts": {"check:full": "project gate"}}
        )

        result = self.run_review_full_check(
            root,
            runner_log,
            fallback_log,
            SD_AI_COMMAND_PACK_PYTHON=str(root / "missing-python"),
        )

        self.assertEqual(result.returncode, 4, result.stdout)
        self.assertIn("could not inspect package.json", result.stdout)
        self.assertFalse(runner_log.exists())
        self.assertFalse(fallback_log.exists())

    def test_missing_pack_fallback_is_reported(self) -> None:
        root, runner_log, fallback_log = self.make_review_repo(
            None, with_fallback=False
        )

        result = self.run_review_full_check(root, runner_log, fallback_log)

        self.assertEqual(result.returncode, 127, result.stdout)
        self.assertIn(
            "scripts/sd-ai-command-pack-full-check.sh is missing", result.stdout
        )


if __name__ == "__main__":
    _support.unittest.main()
