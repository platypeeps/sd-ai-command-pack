from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support


PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase


class ToolchainPreflightTests(InstallTestCase):
    def setUp(self) -> None:
        super().setUp()
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        self.script = (
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-toolchain.sh"
        )

    def _repo(self) -> Path:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-toolchain-test-")
        self.addCleanup(tempdir.cleanup)
        return Path(tempdir.name)

    def _python_wrapper(self, path: Path, log: Path | None = None) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        log_line = ""
        if log is not None:
            log_line = f"printf 'invocation\\n' >> {shlex.quote(str(log))}\n"
        path.write_text(
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            f"{log_line}"
            f"exec {shlex.quote(sys.executable)} \"$@\"\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def _run(
        self,
        root: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self._bash_path, str(self.script), *args],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_REPO_ROOT": str(root),
                **(env or {}),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_explicit_python_override_and_required_module(self) -> None:
        root = self._repo()
        wrapper = self._python_wrapper(root / "custom-python")

        result = self._run(
            root,
            "python",
            "--require-module",
            "json",
            env={"SD_AI_COMMAND_PACK_PYTHON": str(wrapper)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(wrapper))

    def test_repo_venv_precedes_active_virtualenv(self) -> None:
        root = self._repo()
        repo_python = self._python_wrapper(root / ".venv/bin/python")
        active_python = self._python_wrapper(root / "active/bin/python")

        result = self._run(
            root,
            "python",
            env={"VIRTUAL_ENV": str(active_python.parent.parent)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(repo_python))

    def test_windows_style_repo_venv_is_supported(self) -> None:
        root = self._repo()
        windows_python = self._python_wrapper(root / ".venv/Scripts/python.exe")

        result = self._run(root, "python")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(windows_python))

    def test_active_virtualenv_is_selected_without_repo_venv(self) -> None:
        root = self._repo()
        active_python = self._python_wrapper(root / "active/bin/python")

        result = self._run(
            root,
            "python",
            env={"VIRTUAL_ENV": str(active_python.parent.parent)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(active_python))

    def test_invalid_repo_venv_stops_without_path_fallback(self) -> None:
        root = self._repo()
        bad_log = root / "bad.log"
        fallback_log = root / "fallback.log"
        bad_python = root / ".venv/bin/python"
        bad_python.parent.mkdir(parents=True)
        bad_python.write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' \"$*\" >> {shlex.quote(str(bad_log))}\n"
            "exit 1\n",
            encoding="utf-8",
        )
        bad_python.chmod(0o755)
        fallback_bin = root / "bin"
        self._python_wrapper(fallback_bin / "python3", fallback_log)

        result = self._run(
            root,
            "python",
            env={"PATH": f"{fallback_bin}{os.pathsep}{os.environ['PATH']}"},
        )

        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn(str(bad_python), result.stderr)
        self.assertIn("make setup", result.stderr)
        self.assertTrue(bad_log.exists())
        self.assertFalse(fallback_log.exists())

    def test_zero_exit_non_python_executable_is_rejected(self) -> None:
        root = self._repo()
        fake_python = root / "fake-python"
        fake_python.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'not-python\\n'\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)

        result = self._run(
            root,
            "python",
            env={"SD_AI_COMMAND_PACK_PYTHON": str(fake_python)},
        )

        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("did not report a valid Python version", result.stderr)
        self.assertIn(str(fake_python), result.stderr)

    def test_homebrew_prefix_candidates_are_testable_and_ordered(self) -> None:
        root = self._repo()
        first_prefix = root / "opt-homebrew"
        second_prefix = root / "usr-local"
        first_python = self._python_wrapper(first_prefix / "bin/python3.13")
        self._python_wrapper(second_prefix / "bin/python3.13")

        result = self._run(
            root,
            "python",
            env={
                "SD_AI_COMMAND_PACK_TOOLCHAIN_PLATFORM": "Darwin",
                "SD_AI_COMMAND_PACK_TOOLCHAIN_HOMEBREW_PREFIXES": (
                    f"{first_prefix}:{second_prefix}"
                ),
                "VIRTUAL_ENV": "",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(first_python))

    def test_intel_homebrew_prefix_is_used_when_apple_prefix_is_absent(self) -> None:
        root = self._repo()
        first_prefix = root / "opt-homebrew"
        second_prefix = root / "usr-local"
        second_python = self._python_wrapper(second_prefix / "bin/python3.13")

        result = self._run(
            root,
            "python",
            env={
                "SD_AI_COMMAND_PACK_TOOLCHAIN_PLATFORM": "Darwin",
                "SD_AI_COMMAND_PACK_TOOLCHAIN_HOMEBREW_PREFIXES": (
                    f"{first_prefix}:{second_prefix}"
                ),
                "VIRTUAL_ENV": "",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(second_python))

    def test_path_python_is_used_after_platform_candidates(self) -> None:
        root = self._repo()
        path_bin = root / "bin"
        path_python = self._python_wrapper(path_bin / "python3")

        result = self._run(
            root,
            "python",
            env={
                "PATH": f"{path_bin}{os.pathsep}{Path(self._bash_path).parent}",
                "SD_AI_COMMAND_PACK_TOOLCHAIN_PLATFORM": "Linux",
                "VIRTUAL_ENV": "",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(path_python))

    def test_missing_python_reports_exit_three(self) -> None:
        root = self._repo()

        result = self._run(
            root,
            "python",
            env={
                "PATH": str(root / "empty-bin"),
                "SD_AI_COMMAND_PACK_TOOLCHAIN_PLATFORM": "Linux",
                "VIRTUAL_ENV": "",
            },
        )

        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("Homebrew Python 3.13", result.stderr)

    def test_unsupported_selected_python_reports_exit_four(self) -> None:
        root = self._repo()
        wrapper = root / "old-python"
        wrapper.write_text("#!/usr/bin/env bash\nexit 10\n", encoding="utf-8")
        wrapper.chmod(0o755)

        result = self._run(
            root,
            "python",
            env={"SD_AI_COMMAND_PACK_PYTHON": str(wrapper)},
        )

        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("older than 3.10", result.stderr)
        self.assertIn(str(wrapper), result.stderr)

    def test_missing_required_module_fails_without_workload(self) -> None:
        root = self._repo()
        marker = root / "workload-ran"

        result = self._run(
            root,
            "run-python",
            "--require-module",
            "sd_ai_command_pack_missing_module_xyz",
            "--",
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
            env={"SD_AI_COMMAND_PACK_PYTHON": sys.executable},
        )

        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertFalse(marker.exists())

    def test_invalid_module_name_is_usage_error(self) -> None:
        root = self._repo()

        for module_name in (".bad-module", "bad..module", "9module"):
            with self.subTest(module_name=module_name):
                result = self._run(
                    root, "python", "--require-module", module_name
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("invalid Python module name", result.stderr)

    def test_python_subcommand_rejects_run_separator(self) -> None:
        root = self._repo()

        result = self._run(root, "python", "--")

        self.assertEqual(result.returncode, 2, result.stderr)

    def test_run_python_executes_workload_once(self) -> None:
        root = self._repo()
        invocation_log = root / "python.log"
        marker = root / "workload.log"
        wrapper = self._python_wrapper(root / "custom-python", invocation_log)

        result = self._run(
            root,
            "run-python",
            "--require-module",
            "json",
            "--",
            "-c",
            (
                "from pathlib import Path; "
                f"p=Path({str(marker)!r}); "
                "p.write_text((p.read_text() if p.exists() else '') + 'run\\n')"
            ),
            env={"SD_AI_COMMAND_PACK_PYTHON": str(wrapper)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "run\n")
        self.assertEqual(len(invocation_log.read_text().splitlines()), 2)

    def test_doctor_reports_candidates_without_executing_them(self) -> None:
        root = self._repo()
        scripts = root / "scripts"
        scripts.mkdir()
        preflight = scripts / "preflight-pr.sh"
        preflight.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
        preflight.chmod(0o755)
        recursive_check = scripts / "check.sh"
        recursive_check.write_text(
            "#!/usr/bin/env bash\n"
            "bash scripts/sd-ai-command-pack-full-check.sh\n",
            encoding="utf-8",
        )
        recursive_check.chmod(0o755)
        (root / "Makefile").write_text(
            "test:\n\t@true\n"
            "check:\n\tbash scripts/sd-ai-command-pack-full-check.sh\n",
            encoding="utf-8",
        )
        (root / "package.json").write_text(
            json.dumps(
                {
                    "scripts": {
                        "lint": "exit 98",
                        "check": "bash scripts/sd-ai-command-pack-full-check.sh",
                        "other": "true",
                    }
                }
            ),
            encoding="utf-8",
        )

        result = self._run(
            root,
            "doctor",
            "--json",
            env={
                "SD_AI_COMMAND_PACK_PYTHON": sys.executable,
                "SD_AI_COMMAND_PACK_PROJECT_CHECK_COMMAND": "make test",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["project_check"], "make test")
        self.assertEqual(payload["python"]["path"], sys.executable)
        self.assertRegex(payload["python"]["version"], r"^\d+\.\d+\.\d+$")
        self.assertIn("make:test", payload["project_check_candidates"])
        self.assertIn("make:check (recursive)", payload["project_check_candidates"])
        self.assertIn("package:lint", payload["project_check_candidates"])
        self.assertIn(
            "package:check (recursive)", payload["project_check_candidates"]
        )
        self.assertIn("script:preflight-pr.sh", payload["project_check_candidates"])
        self.assertIn(
            "script:check.sh (recursive)", payload["project_check_candidates"]
        )

    def test_installer_distributes_toolchain_helper(self) -> None:
        root = self.make_repo()

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(
            (root / "scripts/sd-ai-command-pack-toolchain.sh").is_file()
        )
        self.assertTrue(
            os.access(root / "scripts/sd-ai-command-pack-toolchain.sh", os.X_OK)
        )


if __name__ == "__main__":
    unittest.main()
