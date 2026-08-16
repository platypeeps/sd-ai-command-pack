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

    def _write_kb_check_helper(
        self, root: Path, *, exit_code: int, message: str
    ) -> None:
        helper = root / "scripts/sd-ai-command-pack-update-spec-kb.py"
        helper.write_text(
            "import sys\n"
            "assert sys.argv[1:] == ['--check']\n"
            f"print({message!r})\n"
            f"raise SystemExit({exit_code})\n",
            encoding="utf-8",
        )

    def _kb_row(self, report: dict[str, object]) -> dict[str, object]:
        return next(
            row for row in report["checks"] if row["id"] == "knowledge.obsidian-kb"
        )

    def test_external_symlink_kb_failure_is_advisory_skipped(self) -> None:
        # Case (b): .obsidian-kb symlinks to a live external vault; a --check
        # failure is non-deterministic drift and must be downgraded to a
        # non-blocking advisory rather than gate the merge.
        root = self.make_check_repo()
        external = root.parent / "external-vault"
        external.mkdir()
        (external / "note.md").write_text("live vault\n", encoding="utf-8")
        (root / ".obsidian-kb").symlink_to(external, target_is_directory=True)
        self._write_kb_check_helper(
            root, exit_code=1, message="knowledge export is stale"
        )

        result = self.run_check(root)
        report = self.parse_report(result)

        row = self._kb_row(report)
        self.assertEqual(row["status"], "skipped", result.stdout)
        self.assertIn("advisory", row["diagnostic"])
        # The original blocking diagnostics survive for the operator.
        self.assertIn("knowledge export is stale", row["diagnostic"])
        self.assertEqual(row["exitCode"], 1)
        self.assertIsNotNone(row["command"])
        self.assertIn("sd-update-spec", row["remediation"])
        # Advisory downgrade must not gate the merge.
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotEqual(report["status"], "failed")

    def test_external_symlink_kb_pass_stays_passed(self) -> None:
        # Case (c): an external-symlinked KB whose --check passes is a normal
        # pass — the advisory downgrade fires only on failure.
        root = self.make_check_repo()
        external = root.parent / "external-vault"
        external.mkdir()
        (root / ".obsidian-kb").symlink_to(external, target_is_directory=True)
        self._write_kb_check_helper(
            root, exit_code=0, message="knowledge export is fresh"
        )

        result = self.run_check(root)
        report = self.parse_report(result)

        row = self._kb_row(report)
        self.assertEqual(row["status"], "passed", result.stdout)
        self.assertNotIn("advisory", str(row.get("diagnostic") or ""))
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_in_repo_symlink_kb_failure_still_blocks(self) -> None:
        # Case (e): an in-repo symlink resolves under the repo and stays
        # deterministic against HEAD, so a --check failure keeps blocking —
        # closing the is_symlink()-alone hole.
        root = self.make_check_repo()
        store = root / "kb-store"
        store.mkdir()
        (store / "note.md").write_text("in-repo kb\n", encoding="utf-8")
        (root / ".obsidian-kb").symlink_to(store, target_is_directory=True)
        self._write_kb_check_helper(
            root, exit_code=1, message="knowledge export is stale"
        )

        result = self.run_check(root)
        report = self.parse_report(result)

        row = self._kb_row(report)
        self.assertEqual(row["status"], "failed", result.stdout)
        self.assertNotIn("advisory", str(row.get("diagnostic") or ""))
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_is_external_symlink_discriminates_by_resolved_target(self) -> None:
        module = self.load_module_from_path(
            self.SCRIPT, "sd_ai_command_pack_check_under_test"
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-check-symlink-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        repo = base / "repo"
        repo.mkdir()

        # External symlink whose target resolves outside the repo -> advisory.
        external_target = base / "external-vault"
        external_target.mkdir()
        external_link = repo / "external-kb"
        external_link.symlink_to(external_target, target_is_directory=True)
        self.assertTrue(module._is_external_symlink(external_link, repo))

        # In-repo symlink whose target resolves under the repo -> keeps blocking.
        in_repo_target = repo / "kb-store"
        in_repo_target.mkdir()
        in_repo_link = repo / "in-repo-kb"
        in_repo_link.symlink_to(in_repo_target, target_is_directory=True)
        self.assertFalse(module._is_external_symlink(in_repo_link, repo))

        # A real (non-symlink) directory is never advisory.
        real_dir = repo / "real-kb"
        real_dir.mkdir()
        self.assertFalse(module._is_external_symlink(real_dir, repo))

        # A broken link resolves to its declared target: external -> advisory,
        # in-repo -> keeps blocking so the breakage surfaces.
        broken_external = repo / "broken-external-kb"
        broken_external.symlink_to(base / "missing-external", target_is_directory=True)
        self.assertTrue(module._is_external_symlink(broken_external, repo))
        broken_in_repo = repo / "broken-in-repo-kb"
        broken_in_repo.symlink_to(repo / "missing-in-repo", target_is_directory=True)
        self.assertFalse(module._is_external_symlink(broken_in_repo, repo))

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

    # -- thin-install helper resolution -------------------------------------
    #
    # A converted consumer keeps none of `scripts/sd-ai-command-pack-*`: the
    # payload moved to the machine install and `pack.install-audit` fails any
    # attempt to put it back. Resolving only `repo/scripts/` therefore reported
    # five `unavailable` rows for helpers that were installed and working, and
    # since `unavailable` outranks `passed` in AGGREGATE_PRECEDENCE, sd-check
    # could never pass and sd-review failed closed ahead of dispatch. Measured
    # on `sd-github-review` at 0.71.24.

    THIN_HELPERS = (
        "sd-ai-command-pack-review-preflight.mjs",
        "sd-ai-command-pack-install-audit.py",
        "sd-ai-command-pack-review-scope.sh",
        "sd-ai-command-pack-pr-body-scope.py",
    )

    def convert_to_thin(
        self, root: Path, *, machine_helpers: tuple[str, ...] | None = None
    ) -> dict[str, str]:
        """Convert a fat fixture the way a real conversion converts a consumer.

        Conversion removes the vendored payload, pins the mode in the consumer
        receipt, and rewrites `installed-targets.txt` down to the residual
        slice rather than deleting it -- that survival is exactly what made
        mode-by-existence call converted consumers fat.
        """

        for name in self.THIN_HELPERS:
            (root / "scripts" / name).unlink()

        directory = root / ".sd-ai-command-pack"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "provenance.json").write_text(
            json.dumps({"mode": "thin", "version": "0.71.24", "consumer": "fixture"}),
            encoding="utf-8",
        )
        (directory / "installed-targets.txt").write_text(
            ".sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py\n",
            encoding="utf-8",
        )

        installed = self.THIN_HELPERS if machine_helpers is None else machine_helpers
        home = root.parent / "home"
        agents_bin = home / ".agents" / "bin"
        agents_bin.mkdir(parents=True, exist_ok=True)
        bodies = {
            "sd-ai-command-pack-review-preflight.mjs": "process.exit(0);\n",
            "sd-ai-command-pack-install-audit.py": "raise SystemExit(0)\n",
            "sd-ai-command-pack-review-scope.sh": "#!/usr/bin/env bash\nexit 0\n",
            "sd-ai-command-pack-pr-body-scope.py": "raise SystemExit(0)\n",
            "sd-ai-command-pack-update-spec-kb.py": (
                "import sys\n"
                "assert sys.argv[1:] == ['--check']\n"
                "raise SystemExit(0)\n"
            ),
        }
        for name in installed:
            (agents_bin / name).write_text(bodies[name], encoding="utf-8")

        state_root = root.parent / "state"
        receipt = state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "files": [
                        {"family": "agents-bin", "path": name, "executable": True}
                        for name in installed
                    ],
                }
            ),
            encoding="utf-8",
        )
        return {
            "HOME": str(home),
            "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
        }

    def test_thin_consumer_resolves_shipped_helpers_from_the_machine_install(
        self,
    ) -> None:
        root = self.make_check_repo()
        env = self.convert_to_thin(root)
        for name in self.THIN_HELPERS:
            self.assertFalse(
                (root / "scripts" / name).exists(),
                f"{name} must be absent from the converted consumer",
            )

        result = self.run_check(root, extra_env=env)
        report = self.parse_report(result)

        rows = {row["id"]: row for row in report["checks"]}
        for identifier in (
            "pack.review-preflight",
            "pack.install-audit",
            "pack.review-scope",
            "pack.pr-body-scope",
        ):
            self.assertEqual(
                rows[identifier]["status"], "passed", rows[identifier]
            )
        self.assertEqual(report["status"], "passed", result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_thin_consumer_without_the_machine_helper_stays_unavailable(self) -> None:
        """Widening where the check looks must not widen what counts as present.

        The helper is absent from the repository *and* from the machine
        install, so the honest answer is still `unavailable` -- the same row
        the vendored fixture produces when its own copy is deleted.
        """

        root = self.make_check_repo()
        env = self.convert_to_thin(
            root,
            machine_helpers=tuple(
                name
                for name in self.THIN_HELPERS
                if name != "sd-ai-command-pack-install-audit.py"
            ),
        )

        result = self.run_check(root, extra_env=env)
        report = self.parse_report(result)

        rows = {row["id"]: row for row in report["checks"]}
        self.assertEqual(rows["pack.install-audit"]["status"], "unavailable")
        self.assertEqual(
            rows["pack.install-audit"]["diagnostic"],
            "installed payload audit helper is not present",
        )
        self.assertEqual(rows["pack.review-scope"]["status"], "passed")
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(result.returncode, 3, result.stdout)

    def test_vendored_consumer_still_resolves_its_own_helpers(self) -> None:
        """The fat layout is unchanged, proven against a populated machine install.

        `repo/scripts/` wins where it exists, so a consumer that still vendors
        the payload cannot silently start executing a different copy of it.
        """

        root = self.make_check_repo()
        env = self.convert_to_thin(root)
        # Put the vendored payload back and drop the thin pin: a fat consumer
        # with a machine install present must still read its own scripts/.
        for name in self.THIN_HELPERS:
            (root / "scripts" / name).write_text(
                (root.parent / "home" / ".agents" / "bin" / name).read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
        (root / ".sd-ai-command-pack" / "provenance.json").write_text(
            json.dumps({"mode": "fat", "version": "0.71.24", "consumer": "fixture"}),
            encoding="utf-8",
        )
        (root / ".sd-ai-command-pack" / "installed-targets.txt").write_text(
            "\n".join(f"scripts/{name}" for name in self.THIN_HELPERS) + "\n",
            encoding="utf-8",
        )
        (root / "scripts" / "sd-ai-command-pack-install-audit.py").unlink()

        result = self.run_check(root, extra_env=env)
        report = self.parse_report(result)

        rows = {row["id"]: row for row in report["checks"]}
        self.assertEqual(rows["pack.install-audit"]["status"], "unavailable")
        self.assertEqual(result.returncode, 3, result.stdout)


def _load_check_module():
    import importlib.util

    scripts_dir = PACK_ROOT / "scripts"
    script = scripts_dir / "sd-ai-command-pack-check.py"
    spec = importlib.util.spec_from_file_location("sd_ai_command_pack_check", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # Insert the scripts dir only if absent and always remove it afterwards, so
    # the check module's `from sd_ai_command_pack_lib import ...` resolves during
    # exec without leaking a permanent sys.path entry that could make the suite
    # import-order dependent.
    script_dir = str(scripts_dir)
    inserted = script_dir not in sys.path
    if inserted:
        sys.path.insert(0, script_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(script_dir)
    return module


class WorktreeHashCacheTests(unittest.TestCase):
    """A-101 R1/R2: the per-run content-hash cache and its detection guarantees.

    These exercise the hashing primitives directly on a plain directory (no git),
    which is exactly how the guarded-path snapshot walks the tree. The three AC1
    mutations must each change a *fresh* (cache-free) hash — that is the run's
    final authoritative snapshot — and the same-size/mtime-restored rewrite must
    additionally document the run-level granularity trade: a snapshot sharing the
    pre-mutation cache cannot see it, while the fresh snapshot still does.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_check_module()

    def _dir_with_file(self, contents: bytes = b"AAAA"):
        tempdir = tempfile.TemporaryDirectory(prefix="sd-check-cache-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "tree"
        (root / "nested").mkdir(parents=True)
        target = root / "nested" / "file.bin"
        target.write_bytes(contents)
        return root, target

    def test_ordinary_edit_changes_a_fresh_hash(self) -> None:
        root, target = self._dir_with_file(b"AAAA")
        before = self.mod._hash_path(root, self.mod._WorktreeHashCache())
        target.write_bytes(b"AAAA-and-more")  # size changes
        after = self.mod._hash_path(root, self.mod._WorktreeHashCache())
        self.assertNotEqual(before, after)

    def test_symlink_retarget_changes_hash_even_with_shared_cache(self) -> None:
        root, _ = self._dir_with_file()
        (root / "old").write_bytes(b"x")
        (root / "new").write_bytes(b"y")
        link = root / "nested" / "link"
        link.symlink_to("../old")
        cache = self.mod._WorktreeHashCache()
        before = self.mod._hash_path(root, cache)
        link.unlink()
        link.symlink_to("../new")
        # Symlinks are never cached, so the retarget is caught at every snapshot,
        # including one reusing the pre-mutation cache.
        self.assertNotEqual(before, self.mod._hash_path(root, cache))
        self.assertNotEqual(before, self.mod._hash_path(root, self.mod._WorktreeHashCache()))

    def test_same_size_mtime_restored_rewrite_is_caught_only_by_a_fresh_hash(self) -> None:
        root, target = self._dir_with_file(b"AAAA")
        original = target.stat()
        cache = self.mod._WorktreeHashCache()
        before = self.mod._hash_path(root, cache)  # cold pass fills the cache
        target.write_bytes(b"BBBB")  # same size
        os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))  # restore mtime
        self.assertEqual(target.stat().st_size, original.st_size)
        self.assertEqual(target.stat().st_mtime_ns, original.st_mtime_ns)
        # Documented trade: a snapshot reusing the pre-mutation cache misses it...
        self.assertEqual(before, self.mod._hash_path(root, cache))
        # ...but the run's final, cache-free snapshot re-hashes and still catches it.
        self.assertNotEqual(before, self.mod._hash_path(root, self.mod._WorktreeHashCache()))

    def test_content_reads_are_two_passes_regardless_of_snapshot_count(self) -> None:
        # AC2: snapshot content-hashing is flat in the number of rows. Simulate a
        # run: one cold `before` pass, several cache-reusing per-row snapshots, and
        # one fresh `final` pass. Only the cold and final passes read file content.
        tempdir = tempfile.TemporaryDirectory(prefix="sd-check-count-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "tree"
        root.mkdir(parents=True)
        file_count = 5
        for index in range(file_count):
            (root / f"f{index}.bin").write_bytes(f"content-{index}".encode())

        reads = {"count": 0}
        original = self.mod._hash_regular_file

        def counting(path, digest):
            reads["count"] += 1
            return original(path, digest)

        self.mod._hash_regular_file = counting
        self.addCleanup(setattr, self.mod, "_hash_regular_file", original)

        run_cache = self.mod._WorktreeHashCache()
        self.mod._hash_path(root, run_cache)  # cold before
        for _ in range(4):  # four unchanged per-row snapshots
            self.mod._hash_path(root, run_cache)
        self.mod._hash_path(root, self.mod._WorktreeHashCache())  # fresh final

        # Exactly two full passes over the file set: cold + final. The four per-row
        # snapshots read nothing. A per-row re-hash would make this 6 * file_count.
        self.assertEqual(reads["count"], 2 * file_count)


if __name__ == "__main__":
    unittest.main()
