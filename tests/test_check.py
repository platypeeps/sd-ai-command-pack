from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
os = _support.os
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
Path = _support.Path
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase


class CheckTests(InstallTestCase):
    """Tests for the deterministic read-only sd-check coordinator."""

    SCRIPT = PACK_ROOT / "templates/scripts/sd-ai-command-pack-check.py"

    def make_check_repo(self) -> Path:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-check-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "repo"
        root.mkdir()
        self.run_git(root, "init", "--initial-branch=main")
        self.run_git(root, "config", "user.name", "Check Test")
        self.run_git(root, "config", "user.email", "check@example.com")
        (root / "README.md").write_text("# check fixture\n", encoding="utf-8")
        scripts = root / "scripts"
        scripts.mkdir()
        helpers = {
            "sd-ai-command-pack-review-preflight.mjs": "process.exit(0);\n",
            "sd-ai-command-pack-install-audit.py": "raise SystemExit(0)\n",
            "sd-ai-command-pack-review-scope.sh": "#!/usr/bin/env bash\nexit 0\n",
            "sd-ai-command-pack-pr-body-scope.py": "raise SystemExit(0)\n",
        }
        for name, content in helpers.items():
            (scripts / name).write_text(content, encoding="utf-8")
        self.run_git(root, "add", "README.md")
        self.run_git(root, "commit", "-m", "seed check fixture")
        return root

    def run_check(
        self,
        root: Path,
        *,
        extra_env: dict[str, str] | None = None,
        json_output: bool = True,
        extra_args: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        cache_dir = Path(root.parent) / "cache"
        cache_dir.mkdir(mode=0o700, exist_ok=True)
        command = [sys.executable, str(self.SCRIPT), "--repo", str(root)]
        if json_output:
            command.append("--json")
        command.extend(extra_args)
        return subprocess.run(
            command,
            cwd=root,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "SD_AI_COMMAND_PACK_CACHE_ROOT": str(cache_dir),
                **(extra_env or {}),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def write_config(self, root: Path, value: object) -> Path:
        path = root / ".sd-ai-command-pack/check.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def command_entry(
        self,
        identifier: str,
        argv: list[str],
        *,
        cwd: str = ".",
        timeout: int = 10,
    ) -> dict[str, object]:
        return {
            "id": identifier,
            "argv": argv,
            "cwd": cwd,
            "timeoutSeconds": timeout,
        }

    def config(
        self,
        *,
        prerequisites: list[dict[str, object]] | None = None,
        checks: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "prerequisites": prerequisites or [],
            "checks": checks or [],
        }

    def parse_report(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"sd-check did not emit JSON: {error}\n{result.stdout}")
        self.assertIsInstance(parsed, dict)
        return parsed

    def snapshot_repo(self, root: Path) -> tuple[str, str, dict[str, bytes]]:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        ).stdout
        files = {
            str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(root).parts
        }
        return head, status, files

    def test_default_check_is_typed_and_preserves_repository(self) -> None:
        root = self.make_check_repo()
        before = self.snapshot_repo(root)

        result = self.run_check(root)
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["command"], "sd-check")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["stateGuard"]["status"], "passed")
        self.assertEqual(before, self.snapshot_repo(root))
        rows = {row["id"]: row for row in report["checks"]}
        self.assertEqual(rows["git.whitespace.unstaged"]["status"], "passed")
        self.assertEqual(rows["git.whitespace.staged"]["status"], "passed")
        self.assertEqual(rows["pack.install-audit"]["status"], "passed")
        self.assertEqual(rows["knowledge.obsidian-kb"]["status"], "skipped")

    def test_configured_argv_check_runs_without_shell_interpolation(self) -> None:
        root = self.make_check_repo()
        helper = root.parent / "pass-check.py"
        helper.write_text("print('configured pass')\n", encoding="utf-8")
        self.write_config(
            root,
            self.config(
                checks=[
                    self.command_entry("unit", [sys.executable, str(helper)])
                ]
            ),
        )
        before = self.snapshot_repo(root)

        result = self.run_check(root)
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 0, result.stdout)
        row = next(row for row in report["checks"] if row["id"] == "unit")
        self.assertEqual(row["status"], "passed")
        self.assertEqual(row["command"]["argumentCount"], 1)
        self.assertEqual(before, self.snapshot_repo(root))

    def test_failure_and_unavailable_are_not_reported_as_success(self) -> None:
        root = self.make_check_repo()
        helper = root.parent / "fail-check.py"
        helper.write_text(
            "import sys\nprint('deterministic failure', file=sys.stderr)\nraise SystemExit(7)\n",
            encoding="utf-8",
        )
        self.write_config(
            root,
            self.config(
                checks=[
                    self.command_entry("failure", [sys.executable, str(helper)]),
                    self.command_entry("missing", ["sd-check-missing-binary"]),
                ]
            ),
        )

        result = self.run_check(root)
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(report["status"], "failed")
        rows = {row["id"]: row for row in report["checks"]}
        self.assertEqual(rows["failure"]["status"], "failed")
        self.assertIn("deterministic failure", rows["failure"]["diagnostic"])
        self.assertEqual(rows["missing"]["status"], "unavailable")

    def test_prerequisite_failure_skips_declared_checks(self) -> None:
        root = self.make_check_repo()
        helper = root.parent / "fail-prerequisite.py"
        helper.write_text("raise SystemExit(2)\n", encoding="utf-8")
        marker = root.parent / "must-not-run"
        check = root.parent / "write-marker.py"
        check.write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )
        self.write_config(
            root,
            self.config(
                prerequisites=[
                    self.command_entry("tooling", [sys.executable, str(helper)])
                ],
                checks=[
                    self.command_entry("unit", [sys.executable, str(check)])
                ],
            ),
        )

        result = self.run_check(root)
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        rows = {row["id"]: row for row in report["checks"]}
        self.assertEqual(rows["tooling"]["status"], "failed")
        self.assertEqual(rows["unit"]["status"], "skipped")
        self.assertFalse(marker.exists())

    def test_stale_kb_is_reported_without_refresh_or_provider_dispatch(self) -> None:
        root = self.make_check_repo()
        (root / ".obsidian-kb").mkdir()
        stale = root / ".obsidian-kb/stale.md"
        stale.write_text("stale\n", encoding="utf-8")
        scripts = root / "scripts"
        helper = scripts / "sd-ai-command-pack-update-spec-kb.py"
        helper.write_text(
            "import sys\n"
            "assert sys.argv[1:] == ['--check']\n"
            "print('knowledge export is stale')\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        before = self.snapshot_repo(root)
        bin_dir = root.parent / "bin"
        bin_dir.mkdir()
        logs: list[Path] = []
        for name in ("gh", "gito", "prism"):
            log = root.parent / f"{name}.log"
            executable = bin_dir / name
            executable.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" >> {str(log)!r}\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            logs.append(log)

        result = self.run_check(
            root,
            extra_env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        )
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        row = next(
            row for row in report["checks"] if row["id"] == "knowledge.obsidian-kb"
        )
        self.assertEqual(row["status"], "failed")
        self.assertIn("sd-update-spec", row["remediation"])
        self.assertEqual(before, self.snapshot_repo(root))
        for log in logs:
            self.assertFalse(log.exists(), f"unexpected provider dispatch: {log}")

    def test_state_guard_detects_configured_repository_mutation(self) -> None:
        root = self.make_check_repo()
        helper = root.parent / "mutate.py"
        helper.write_text(
            "from pathlib import Path\nPath('created.txt').write_text('changed', encoding='utf-8')\n",
            encoding="utf-8",
        )
        self.write_config(
            root,
            self.config(
                checks=[
                    self.command_entry("mutating", [sys.executable, str(helper)])
                ]
            ),
        )

        result = self.run_check(root)
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(report["stateGuard"]["status"], "failed")
        self.assertIn("worktree", report["stateGuard"]["changed"])
        guard = next(row for row in report["checks"] if row["id"] == "state-guard")
        self.assertEqual(guard["status"], "failed")

    def test_invalid_configuration_fails_before_configured_execution(self) -> None:
        invalid_values = (
            {"schemaVersion": 2, "prerequisites": [], "checks": []},
            {"schemaVersion": 1, "prerequisites": [], "checks": "echo test"},
            self.config(checks=[self.command_entry("shell", ["bash", "-c", "true"])]),
            self.config(
                checks=[self.command_entry("shell-bundle", ["bash", "-lc", "true"])]
            ),
            self.config(
                checks=[
                    self.command_entry(
                        "inline-eval", ["node", "-e", "process.exit(0)"]
                    )
                ]
            ),
            self.config(
                checks=[
                    self.command_entry("perl-inline", ["perl", "-e", "exit 0"])
                ]
            ),
            self.config(
                checks=[
                    self.command_entry("ruby-inline", ["ruby", "-e", "exit 0"])
                ]
            ),
            self.config(checks=[self.command_entry("git-push", ["git", "push"])]),
            self.config(
                checks=[
                    self.command_entry("git-commit", ["git", "commit", "-m", "x"])
                ]
            ),
            self.config(checks=[self.command_entry("remote", ["gh", "pr", "view"])]),
            self.config(checks=[self.command_entry("escape", ["true"], cwd="../outside")]),
            self.config(checks=[self.command_entry("timeout", ["true"], timeout=3601)]),
        )
        for index, value in enumerate(invalid_values):
            with self.subTest(index=index):
                root = self.make_check_repo()
                self.write_config(root, value)
                result = self.run_check(root)
                report = self.parse_report(result)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertEqual(report["status"], "invalid")
                self.assertEqual(report["checks"][0]["id"], "configuration")

    def test_config_path_cannot_select_external_policy(self) -> None:
        root = self.make_check_repo()
        external = root.parent / "check.json"
        external.write_text(json.dumps(self.config()), encoding="utf-8")

        result = self.run_check(root, extra_args=("--config", str(external)))
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(report["status"], "invalid")
        self.assertIn("repository-owned", report["checks"][0]["diagnostic"])

    def test_human_output_is_concise_and_keeps_skips_visible(self) -> None:
        root = self.make_check_repo()
        result = self.run_check(root, json_output=False)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Status: passed", result.stdout)
        self.assertIn("knowledge.obsidian-kb: skipped", result.stdout)
        self.assertIn("State guard: passed", result.stdout)

    def test_timeout_is_indeterminate_and_preserves_repository(self) -> None:
        root = self.make_check_repo()
        helper = root.parent / "slow-check.py"
        helper.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
        self.write_config(
            root,
            self.config(
                checks=[
                    self.command_entry(
                        "slow",
                        [sys.executable, str(helper)],
                        timeout=1,
                    )
                ]
            ),
        )
        before = self.snapshot_repo(root)

        result = self.run_check(root)
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 3, result.stdout)
        row = next(row for row in report["checks"] if row["id"] == "slow")
        self.assertEqual(row["status"], "indeterminate")
        self.assertEqual(report["status"], "indeterminate")
        self.assertEqual(before, self.snapshot_repo(root))

    def test_repository_local_cache_configuration_is_unavailable(self) -> None:
        root = self.make_check_repo()

        result = self.run_check(
            root,
            extra_env={"SD_AI_COMMAND_PACK_CACHE_ROOT": str(root / ".cache")},
        )
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["checks"][0]["id"], "configuration")
        self.assertIn("outside the repository", report["checks"][0]["diagnostic"])

    def test_missing_shipped_helper_is_unavailable_not_skipped(self) -> None:
        root = self.make_check_repo()
        (root / "scripts/sd-ai-command-pack-install-audit.py").unlink()

        result = self.run_check(root)
        report = self.parse_report(result)

        self.assertEqual(result.returncode, 3, result.stdout)
        row = next(
            row for row in report["checks"] if row["id"] == "pack.install-audit"
        )
        self.assertEqual(row["status"], "unavailable")
        self.assertEqual(report["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
