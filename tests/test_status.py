from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
hashlib = _support.hashlib
io = _support.io
json = _support.json
fleet_manifest = _support.fleet_manifest
os = _support.os
shutil = _support.shutil
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
mock = _support.mock
Path = _support.Path
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase
PACK_VERSION = json.loads(
    (PACK_ROOT / "manifest.json").read_text(encoding="utf-8")
)["version"]


class StatusTests(InstallTestCase):
    """Tests for read-only local and fleet status reporting."""

    def load_status_module(self):
        return self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-status.py",
            "sd_ai_command_pack_status",
        )

    def load_fleet_lib(self):
        return self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd_ai_command_pack_fleet_lib.py",
            "status_test_fleet_lib",
        )

    def load_work_loop_module(self):
        return self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-work-loop.py",
            "status_test_work_loop",
        )

    def make_portable_status_install(self, root: Path) -> Path:
        scripts = root / "scripts"
        scripts.mkdir(parents=True)
        for name in (
            "sd-ai-command-pack-status.py",
            "sd-ai-command-pack-work-loop.py",
            "sd_ai_command_pack_fleet_lib.py",
        ):
            shutil.copyfile(PACK_ROOT / "templates/scripts" / name, scripts / name)
        (root / "manifest.json").write_text(
            '{"name": "consumer-repo", "version": "1.0.0"}\n',
            encoding="utf-8",
        )
        return scripts / "sd-ai-command-pack-status.py"

    def make_status_repo(self, *, pack_version: str = PACK_VERSION) -> Path:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "repo"
        remote = Path(tempdir.name) / "remote.git"
        root.mkdir()
        self.run_git(root, "init", "--initial-branch=main")
        self.run_git(root, "config", "user.name", "Status Test")
        self.run_git(root, "config", "user.email", "status@example.com")

        (root / "README.md").write_text("# Status fixture\n", encoding="utf-8")
        task_dir = root / ".trellis/tasks/status-fixture"
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(
            json.dumps(
                {
                    "id": "status-fixture",
                    "title": "Status fixture task",
                    "status": "in_progress",
                    "priority": "P1",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        scripts_dir = root / ".trellis/scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "task.py").write_text(
            "from pathlib import Path\n"
            "print(Path('.trellis/tasks/status-fixture'))\n",
            encoding="utf-8",
        )
        (root / ".trellis/.version").write_text("0.6.7\n", encoding="utf-8")
        provenance = root / ".sd-ai-command-pack/provenance.json"
        provenance.parent.mkdir(parents=True)
        provenance.write_text(
            json.dumps({"pack": "sd-ai-command-pack", "version": pack_version})
            + "\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "seed status fixture")
        self.run_git(remote.parent, "init", "--bare", str(remote))
        self.run_git(root, "remote", "add", "origin", str(remote))
        self.run_git(root, "push", "--set-upstream", "origin", "main")
        self.run_git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.run_git(root, "remote", "set-head", "origin", "main")
        return root

    def run_status(
        self,
        root: Path,
        *args: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "templates/scripts/sd-ai-command-pack-status.py"),
                "--repo",
                str(root),
                "--no-network",
                *args,
            ],
            cwd=root,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                **(extra_env or {}),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def start_loop_state(
        self,
        root: Path,
        state_root: Path,
        *,
        status: str = "active",
        phase: str = "implementing",
    ) -> dict[str, object]:
        loop = self.load_work_loop_module()
        identity = loop.repository_identity(root)
        state = loop.new_state(
            identity,
            mode="backlog",
            selector="all",
            focus=loop.normalize_focus(preferred=["CI pipeline"]),
            until="merge",
            run_id="status-loop-run",
        )
        state["status"] = status
        state["phase"] = phase
        state["current"]["task"] = "ci-pipeline-task"
        state["current"]["branch"] = "codex/ci-pipeline-task"
        state["current"]["prNumber"] = 42
        state["counters"]["completed"] = 2
        state_path, lock_path = loop.state_paths(identity, state_root)
        if status == "active":
            loop.acquire_lock(lock_path, state)
        loop.validate_state(state)
        loop.atomic_write_json(state_path, state)
        return state

    def working_files_snapshot(self, root: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if ".git" in relative.parts or not path.is_file():
                continue
            snapshot[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        return snapshot

    def test_resolve_repo_accepts_file_within_repository(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()

        self.assertEqual(status.resolve_repo(root / "README.md"), root.resolve())
        self.assertIsNone(status.resolve_repo(root / "missing"))
        self.assertIsNone(status.resolve_repo(root / "missing/nested"))

    def test_resolve_repo_accepts_relative_file_within_repository(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        previous_cwd = Path.cwd()
        self.addCleanup(os.chdir, previous_cwd)
        os.chdir(root)

        self.assertEqual(status.resolve_repo(Path("README.md")), root.resolve())

    def test_resolve_repo_runs_git_from_candidate_directory(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()

        with mock.patch.object(
            status,
            "run_command",
            return_value=status.CommandResult(0, f"{root}\n"),
        ) as run_command:
            self.assertEqual(status.resolve_repo(root / "README.md"), root.resolve())

        run_command.assert_called_once_with(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            cwd=root,
        )

    def test_local_json_is_read_only_and_reports_cached_state(self) -> None:
        root = self.make_status_repo()
        before_files = self.working_files_snapshot(root)
        before_refs = self.git_output(
            root,
            "for-each-ref",
            "--format=%(refname) %(objectname)",
        )

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["mode"], "local")
        self.assertEqual(report["git"]["branch"], "main")
        self.assertEqual(report["git"]["workingTree"]["state"], "clean")
        self.assertEqual(report["git"]["stashCount"], 0)
        self.assertEqual(report["git"]["syncState"], "synchronized")
        self.assertEqual(report["git"]["refsFreshness"], "cached")
        self.assertIn("origin/HEAD", report["git"]["remoteBranches"])
        self.assertEqual(report["github"]["status"], "disabled")
        self.assertEqual(report["github"]["openPrsStatus"], "unavailable")
        self.assertEqual(report["trellis"]["activeTask"]["id"], "status-fixture")
        self.assertEqual(self.working_files_snapshot(root), before_files)
        self.assertEqual(
            self.git_output(root, "for-each-ref", "--format=%(refname) %(objectname)"),
            before_refs,
        )

    def test_local_status_reports_active_work_loop_in_json_and_human_output(
        self,
    ) -> None:
        root = self.make_status_repo()
        state_root = root.parent / "loop-state"
        self.start_loop_state(root, state_root)
        env = {"SD_AI_COMMAND_PACK_STATE_HOME": str(state_root)}

        machine = self.run_status(root, "--json", extra_env=env)
        human = self.run_status(root, extra_env=env)

        self.assertEqual(machine.returncode, 0, machine.stdout)
        loop = json.loads(machine.stdout)["workLoop"]
        self.assertEqual(loop["status"], "active")
        self.assertEqual(loop["runId"], "status-loop-run")
        self.assertEqual(loop["iteration"], 1)
        self.assertEqual(loop["phase"], "implementing")
        self.assertEqual(loop["task"], "ci-pipeline-task")
        self.assertEqual(loop["prNumber"], 42)
        self.assertEqual(loop["focusMode"], "prefer")
        self.assertEqual(loop["focus"], ["CI pipeline"])
        self.assertEqual(loop["contextHealth"]["level"], "green")
        self.assertEqual(loop["counters"]["completed"], 2)
        self.assertEqual(human.returncode, 0, human.stdout)
        self.assertIn("==> Work Loop", human.stdout)
        self.assertIn("status-loop-run [active]", human.stdout)
        self.assertIn("context health green", human.stdout)
        self.assertIn("Resume active SD work loop status-loop-run", human.stdout)

    def test_status_reports_verified_terminal_reconciliation_as_historical(self) -> None:
        root = self.make_status_repo()
        state_root = root.parent / "loop-state"
        state = self.start_loop_state(
            root, state_root, status="stopped", phase="stopped"
        )
        loop = self.load_work_loop_module()
        head = self.git_output(root, "rev-parse", "HEAD")
        state["contextHealth"] = {"level": "green", "epoch": 2, "reasons": []}
        state["checkpoint"] = {
            "state": "completed",
            "target": "terminal-reconciliation",
            "reason": "verified external completion",
        }
        state["terminalReconciliation"] = {
            "status": "verified",
            "reconciledAt": "2026-07-20T12:00:00Z",
            "archivedTask": ".trellis/tasks/archive/2026-07/07-20-status-fixture",
            "taskId": "status-fixture",
            "delivery": {
                "prNumber": 147,
                "prUrl": "https://example.test/pull/147",
                "head": head,
                "mergeCommit": head,
            },
            "bookkeeping": {
                "prNumber": 148,
                "prUrl": "https://example.test/pull/148",
                "head": head,
                "mergeCommit": head,
            },
            "observed": {"branch": "main", "head": head},
        }
        identity = loop.repository_identity(root)
        state_path, _lock_path = loop.state_paths(identity, state_root)
        loop.atomic_write_json(state_path, state)
        env = {"SD_AI_COMMAND_PACK_STATE_HOME": str(state_root)}

        machine = self.run_status(root, "--json", extra_env=env)
        human = self.run_status(root, extra_env=env)

        report = json.loads(machine.stdout)
        terminal = report["workLoop"]["terminalReconciliation"]
        self.assertEqual(terminal["status"], "verified")
        self.assertEqual(terminal["delivery"]["prNumber"], 147)
        self.assertFalse(
            any("Reconcile the red SD work-loop" in step for step in report["nextSteps"])
        )
        red_historical = dict(report)
        red_historical["workLoop"] = dict(report["workLoop"])
        red_historical["workLoop"]["contextHealth"] = {
            "level": "red",
            "epoch": 3,
            "reasons": ["stale historical reason"],
        }
        status = self.load_status_module()
        self.assertFalse(
            any(
                "Reconcile the red SD work-loop" in step
                for step in status.next_steps(red_historical)
            )
        )
        self.assertIn("verified historical external completion", human.stdout)
        self.assertIn("delivery PR #147; bookkeeping PR #148", human.stdout)
        self.assertIn("counters (loop-owned)", human.stdout)

    def test_completed_active_root_tasks_are_anomalous_and_archived_tasks_are_ignored(
        self,
    ) -> None:
        root = self.make_status_repo()
        stranded = root / ".trellis/tasks/completed-fixture"
        stranded.mkdir()
        (stranded / "task.json").write_text(
            json.dumps(
                {
                    "id": "completed-record-id",
                    "title": "Completed fixture",
                    "status": "completed",
                    "priority": "P2",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        archived = root / ".trellis/tasks/archive/2026-07/archived-fixture"
        archived.mkdir(parents=True)
        (archived / "task.json").write_text(
            '{"id":"archived-fixture","status":"completed"}\n',
            encoding="utf-8",
        )
        outside = root / "outside-completed-task"
        outside.mkdir()
        (outside / "task.json").write_text(
            '{"id":"symlinked-fixture","status":"completed"}\n',
            encoding="utf-8",
        )
        try:
            (root / ".trellis/tasks/symlinked-fixture").symlink_to(
                outside, target_is_directory=True
            )
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        machine = self.run_status(root, "--json")
        human = self.run_status(root)

        self.assertEqual(machine.returncode, 0, machine.stdout)
        report = json.loads(machine.stdout)
        completed = report["trellis"]["completedOutsideArchive"]
        self.assertEqual([task["id"] for task in completed], ["completed-record-id"])
        self.assertEqual([task["path"] for task in completed], ["tasks/completed-fixture"])
        self.assertTrue(
            any(
                "1 completed Trellis task(s) remain outside" in anomaly
                and "tasks/completed-fixture" in anomaly
                and "completed-record-id" not in anomaly
                for anomaly in report["anomalies"]
            )
        )
        self.assertTrue(
            any("task.py archive <task-dir>" in step for step in report["nextSteps"])
        )
        self.assertEqual(human.returncode, 0, human.stdout)
        self.assertIn("SD status: attention", human.stdout)
        self.assertIn("completed Trellis tasks outside archive (1)", human.stdout)
        self.assertIn("completed-record-id", human.stdout)

    def test_local_status_reports_paused_stopped_and_completed_loop_states(
        self,
    ) -> None:
        root = self.make_status_repo()
        for loop_status in ("paused", "stopped", "completed"):
            with self.subTest(status=loop_status):
                state_root = root.parent / f"loop-state-{loop_status}"
                self.start_loop_state(
                    root,
                    state_root,
                    status=loop_status,
                    phase="stopped",
                )
                result = self.run_status(
                    root,
                    "--json",
                    extra_env={"SD_AI_COMMAND_PACK_STATE_HOME": str(state_root)},
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(json.loads(result.stdout)["workLoop"]["status"], loop_status)

    def test_invalid_work_loop_state_is_an_explicit_status_anomaly(self) -> None:
        root = self.make_status_repo()
        loop = self.load_work_loop_module()
        state_root = root.parent / "loop-state-invalid"
        identity = loop.repository_identity(root)
        state_path, _lock_path = loop.state_paths(identity, state_root)
        state_path.parent.mkdir(parents=True)
        state_path.write_text("not-json\n", encoding="utf-8")

        result = self.run_status(
            root,
            extra_env={"SD_AI_COMMAND_PACK_STATE_HOME": str(state_root)},
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("SD status: attention", result.stdout)
        self.assertIn("- state: invalid", result.stdout)
        self.assertIn("work-loop state is invalid", result.stdout)

    def test_collect_work_loop_handles_helper_contract_and_syntax_failures(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        spec = mock.Mock()
        spec.loader = mock.Mock()

        with (
            mock.patch.object(
                status.importlib.util,
                "spec_from_file_location",
                return_value=spec,
            ),
            mock.patch.object(
                status.importlib.util,
                "module_from_spec",
                return_value=object(),
            ),
        ):
            missing_contract = status.collect_work_loop(root)

        self.assertEqual(missing_contract["status"], "invalid")
        self.assertIn("status_snapshot", missing_contract["error"])

        spec.loader.exec_module.side_effect = SyntaxError("corrupt helper")
        with mock.patch.object(
            status.importlib.util,
            "spec_from_file_location",
            return_value=spec,
        ):
            syntax_failure = status.collect_work_loop(root)

        self.assertEqual(syntax_failure["status"], "invalid")
        self.assertIn("corrupt helper", syntax_failure["error"])

        module = mock.Mock()
        module.status_snapshot.side_effect = KeyError("mode")
        spec.loader.exec_module.side_effect = None
        with (
            mock.patch.object(
                status.importlib.util,
                "spec_from_file_location",
                return_value=spec,
            ),
            mock.patch.object(
                status.importlib.util,
                "module_from_spec",
                return_value=module,
            ),
        ):
            malformed_state = status.collect_work_loop(root)

        self.assertEqual(malformed_state["status"], "invalid")
        self.assertIn("mode", malformed_state["error"])

    def test_collect_work_loop_validates_helper_snapshot_shapes(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        spec = mock.Mock()
        spec.loader = mock.Mock()
        module = mock.Mock()

        def collect(snapshot: object) -> dict[str, object]:
            module.status_snapshot.return_value = snapshot
            with (
                mock.patch.object(
                    status.importlib.util,
                    "spec_from_file_location",
                    return_value=spec,
                ),
                mock.patch.object(
                    status.importlib.util,
                    "module_from_spec",
                    return_value=module,
                ),
            ):
                return status.collect_work_loop(root)

        for loop_status in ("none", "unavailable"):
            with self.subTest(valid_terminal=loop_status):
                snapshot = {"status": loop_status}
                self.assertEqual(collect(snapshot), snapshot)

        for missing_error in (None, "", "   ", "\x00"):
            with self.subTest(invalid_without_diagnostics=missing_error):
                snapshot = {"status": "invalid"}
                if missing_error is not None:
                    snapshot["error"] = missing_error
                result = collect(snapshot)
                self.assertEqual(result["status"], "invalid")
                self.assertIn("without diagnostics", result["error"])

        terminal_error = "first line\nsecond\x00line" + ("x" * 600)
        for loop_status in ("invalid", "unavailable"):
            with self.subTest(sanitized_terminal=loop_status):
                result = collect(
                    {
                        "status": loop_status,
                        "error": terminal_error,
                        "token": "do-not-render",
                    }
                )
                self.assertEqual(result["status"], loop_status)
                self.assertEqual(set(result), {"status", "error"})
                self.assertNotRegex(result["error"], r"[\x00-\x1f\x7f]")
                self.assertLessEqual(len(result["error"]), 500)
                self.assertTrue(result["error"].endswith("..."))

        self.assertEqual(
            collect({"status": "none", "error": terminal_error, "token": "secret"}),
            {"status": "none"},
        )
        invalid_terminal_error = collect({"status": "unavailable", "error": ["bad"]})
        self.assertEqual(invalid_terminal_error["status"], "invalid")
        self.assertIn("terminal snapshot field: error", invalid_terminal_error["error"])
        for blank_error in ("", " \n\t ", "\x00"):
            with self.subTest(unavailable_blank_error=repr(blank_error)):
                unavailable_blank_error = collect(
                    {"status": "unavailable", "error": blank_error}
                )
                self.assertEqual(unavailable_blank_error["status"], "invalid")
                self.assertIn(
                    "terminal snapshot field: error",
                    unavailable_blank_error["error"],
                )

        valid_run = {
            "status": "active",
            "runId": "run-1",
            "mode": "backlog",
            "selector": "all",
            "iteration": 2,
            "phase": "implementing",
            "focusMode": "none",
            "focus": [],
            "heartbeatAt": "2026-07-19T00:00:00Z",
            "counters": {},
            "contextHealth": {"level": "green"},
            "checkpoint": {"state": "none"},
        }
        for loop_status in ("active", "paused", "stopped", "completed"):
            with self.subTest(valid_run=loop_status):
                snapshot = {**valid_run, "status": loop_status}
                self.assertEqual(collect(snapshot), snapshot)

        terminal_pr = {
            "prNumber": 42,
            "prUrl": "https://example.test/pull/42",
            "head": "a" * 40,
            "mergeCommit": "b" * 40,
        }
        terminal = {
            "status": "verified",
            "reconciledAt": "2026-07-20T12:00:00Z",
            "archivedTask": ".trellis/tasks/archive/2026-07/07-20-task",
            "taskId": "task",
            "delivery": terminal_pr,
            "bookkeeping": None,
            "observed": {"branch": "main", "head": "b" * 40},
        }
        for run_status in ("active", "paused"):
            with self.subTest(terminal_reconciliation_on_live_run=run_status):
                result = collect(
                    {
                        **valid_run,
                        "status": run_status,
                        "terminalReconciliation": terminal,
                    }
                )
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(
                    result["error"],
                    "work-loop helper returned invalid run snapshot field: "
                    "terminalReconciliation",
                )

        invalid_terminal_status = collect(
            {
                **valid_run,
                "status": "completed",
                "phase": "stopped",
                "terminalReconciliation": {**terminal, "status": "pending"},
            }
        )
        self.assertEqual(invalid_terminal_status["status"], "invalid")
        self.assertEqual(
            invalid_terminal_status["error"],
            "work-loop helper returned invalid run snapshot field: "
            "terminalReconciliation.status",
        )

        for url in (
            "https://example.test:bad/pull/42",
            "https://[::1/pull/42",
        ):
            with self.subTest(malformed_terminal_pr_url=url):
                malformed_pr = {**terminal_pr, "prUrl": url}
                result = collect(
                    {
                        **valid_run,
                        "status": "completed",
                        "phase": "stopped",
                        "terminalReconciliation": {
                            **terminal,
                            "delivery": malformed_pr,
                        },
                    }
                )
                self.assertEqual(result["status"], "invalid")
                self.assertIn("terminalReconciliation.delivery", result["error"])

        optional_string_fields = (
            "until",
            "task",
            "branch",
            "head",
            "baseBranch",
            "prUrl",
            "lastShippedSha",
            "stopReason",
        )
        for field in optional_string_fields:
            nullable_snapshot = {**valid_run, field: None}
            with self.subTest(nullable_optional_string=field):
                self.assertEqual(collect(nullable_snapshot), nullable_snapshot)
            for blank_value in ("", " \n\t ", "\x00"):
                with self.subTest(
                    blank_optional_string=field,
                    value=repr(blank_value),
                ):
                    result = collect({**valid_run, field: blank_value})
                    self.assertEqual(result["status"], "invalid")
                    self.assertIn(field, result["error"])

        nullable_nested_snapshot = {
            **valid_run,
            "checkpoint": {
                "state": "none",
                "target": None,
                "reason": None,
                "resumePhase": None,
            },
            "lock": {"present": False, "stale": False, "runId": None},
        }
        self.assertEqual(collect(nullable_nested_snapshot), nullable_nested_snapshot)
        for field in ("target", "reason", "resumePhase"):
            for blank_value in ("", " \n\t ", "\x00"):
                with self.subTest(
                    blank_checkpoint_string=field,
                    value=repr(blank_value),
                ):
                    result = collect(
                        {
                            **valid_run,
                            "checkpoint": {
                                "state": "none",
                                field: blank_value,
                            },
                        }
                    )
                    self.assertEqual(result["status"], "invalid")
                    self.assertIn(f"checkpoint.{field}", result["error"])
        for blank_value in ("", " \n\t ", "\x00"):
            with self.subTest(blank_lock_run_id=repr(blank_value)):
                result = collect(
                    {
                        **valid_run,
                        "lock": {
                            "present": True,
                            "stale": False,
                            "runId": blank_value,
                        },
                    }
                )
                self.assertEqual(result["status"], "invalid")
                self.assertIn("lock.runId", result["error"])

        unsafe_text = "first\nsecond\x00line" + ("x" * 600)
        sanitized_run = collect(
            {
                **valid_run,
                "runId": unsafe_text,
                "focus": [unsafe_text],
                "task": unsafe_text,
                "stopReason": unsafe_text,
                "counters": {"completed\x00count": 1},
                "contextHealth": {
                    "level": "green",
                    "epoch": 2,
                    "reasons": [unsafe_text],
                    "token": "do-not-render",
                },
                "checkpoint": {
                    "state": "paused",
                    "target": unsafe_text,
                    "reason": unsafe_text,
                    "resumePhase": unsafe_text,
                    "token": "do-not-render",
                },
                "lock": {
                    "present": True,
                    "stale": False,
                    "runId": unsafe_text,
                    "token": "do-not-render",
                },
                "token": "do-not-render",
            }
        )
        self.assertEqual(
            set(sanitized_run),
            {
                *valid_run,
                "task",
                "stopReason",
                "lock",
            },
        )
        sanitized_strings = [
            sanitized_run["runId"],
            sanitized_run["focus"][0],
            sanitized_run["task"],
            sanitized_run["stopReason"],
            next(iter(sanitized_run["counters"])),
            sanitized_run["contextHealth"]["reasons"][0],
            sanitized_run["checkpoint"]["target"],
            sanitized_run["checkpoint"]["reason"],
            sanitized_run["checkpoint"]["resumePhase"],
            sanitized_run["lock"]["runId"],
        ]
        for value in sanitized_strings:
            self.assertNotRegex(value, r"[\x00-\x1f\x7f]")
        self.assertLessEqual(len(sanitized_run["runId"]), 120)
        self.assertLessEqual(len(sanitized_run["focus"][0]), 160)
        self.assertLessEqual(len(sanitized_run["task"]), 160)
        self.assertLessEqual(len(sanitized_run["stopReason"]), 500)
        self.assertEqual(sanitized_run["counters"], {"completed count": 1})
        self.assertNotIn("token", sanitized_run["contextHealth"])
        self.assertNotIn("token", sanitized_run["checkpoint"])
        self.assertNotIn("token", sanitized_run["lock"])

        self.assertIn(
            "prNumber",
            collect({**valid_run, "prNumber": True})["error"],
        )
        self.assertIn(
            "contextHealth.reasons",
            collect(
                {
                    **valid_run,
                    "contextHealth": {"level": "green", "reasons": [1]},
                }
            )["error"],
        )

        missing_status = collect({})
        self.assertEqual(missing_status["status"], "invalid")
        self.assertIn("valid status", missing_status["error"])

        unsupported_status = collect(
            {"status": "secret-status-value", "token": "do-not-render"}
        )
        self.assertEqual(unsupported_status["status"], "invalid")
        self.assertEqual(
            unsupported_status["error"],
            "work-loop helper returned unsupported status",
        )
        self.assertNotIn("secret-status-value", unsupported_status["error"])

        malformed_fields = (
            ("runId", None, "runId"),
            ("iteration", True, "iteration"),
            ("focus", ["CI", 42], "focus"),
            ("counters", [], "counters"),
            ("contextHealth", {}, "contextHealth.level"),
            ("checkpoint", {"state": ""}, "checkpoint.state"),
        )
        for field, value, expected in malformed_fields:
            with self.subTest(malformed_field=field):
                snapshot = {**valid_run, field: value}
                result = collect(snapshot)
                self.assertEqual(result["status"], "invalid")
                self.assertIn(expected, result["error"])

    def test_collect_work_loop_restores_bytecode_setting_after_loader_failure(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        spec = mock.Mock()
        spec.loader = mock.Mock()
        observed: list[bool] = []

        def fail_while_loading(_module: object) -> None:
            observed.append(status.sys.dont_write_bytecode)
            raise SyntaxError("corrupt helper")

        spec.loader.exec_module.side_effect = fail_while_loading
        with (
            mock.patch.object(status.sys, "dont_write_bytecode", False),
            mock.patch.object(
                status.importlib.util,
                "spec_from_file_location",
                return_value=spec,
            ),
        ):
            result = status.collect_work_loop(root)
            self.assertFalse(status.sys.dont_write_bytecode)

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(observed, [True])

    def test_local_status_counts_stashes_without_marking_attention(self) -> None:
        root = self.make_status_repo()
        for index in range(2):
            (root / "README.md").write_text(
                f"stashed change {index}\n",
                encoding="utf-8",
            )
            self.run_git(root, "stash", "push", "-m", f"status fixture {index}")

        machine = self.run_status(root, "--json")
        human = self.run_status(root)

        self.assertEqual(machine.returncode, 0, machine.stdout)
        self.assertEqual(json.loads(machine.stdout)["git"]["stashCount"], 2)
        self.assertEqual(human.returncode, 0, human.stdout)
        self.assertIn("SD status: healthy", human.stdout)
        self.assertIn("- git stashes: 2", human.stdout)

    def test_unavailable_stash_inventory_is_explicit(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        real_git_output = status.git_output

        def git_output_without_stashes(repo: Path, *args: str) -> str | None:
            if args[:2] == ("stash", "list"):
                return None
            return real_git_output(repo, *args)

        with mock.patch.object(
            status,
            "git_output",
            side_effect=git_output_without_stashes,
        ):
            git, anomalies = status.collect_git(
                root,
                remote="origin",
                supplied_default=None,
                refs_refreshed=False,
            )

        self.assertIsNone(git["stashCount"])
        self.assertIn("git stash inventory is unavailable", anomalies)

    def test_dirty_state_is_advisory_unless_housekeeping_requests_strict_mode(
        self,
    ) -> None:
        root = self.make_status_repo()
        (root / "README.md").write_text("dirty\n", encoding="utf-8")

        advisory = self.run_status(root)
        strict = self.run_status(
            root,
            "--expect-clean",
            "--prior-anomaly",
            "cleanup helper failed\x07",
        )

        self.assertEqual(advisory.returncode, 0, advisory.stdout)
        self.assertIn("SD status: attention", advisory.stdout)
        self.assertIn("working tree: dirty", advisory.stdout)
        self.assertIn("1. Review and commit", advisory.stdout)
        self.assertEqual(strict.returncode, 1, strict.stdout)
        self.assertIn("working tree is dirty after housekeeping", strict.stdout)
        self.assertIn("cleanup helper failed", strict.stdout)
        self.assertNotIn("\x07", strict.stdout)

    def test_detached_head_and_refreshed_label_are_explicit(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "switch", "--detach", "HEAD")

        result = self.run_status(root, "--json", "--refs-refreshed")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["git"]["detached"])
        self.assertIsNone(report["git"]["branch"])
        self.assertEqual(report["git"]["refsFreshness"], "refreshed")

    def test_diverged_history_is_advisory_and_actionable(self) -> None:
        root = self.make_status_repo()
        peer = root.parent / "peer"
        self.run_git(root.parent, "clone", str(root.parent / "remote.git"), str(peer))
        self.run_git(peer, "config", "user.name", "Status Peer")
        self.run_git(peer, "config", "user.email", "peer@example.com")
        (peer / "peer.txt").write_text("remote\n", encoding="utf-8")
        self.run_git(peer, "add", "peer.txt")
        self.run_git(peer, "commit", "-m", "remote change")
        self.run_git(peer, "push", "origin", "main")
        (root / "local.txt").write_text("local\n", encoding="utf-8")
        self.run_git(root, "add", "local.txt")
        self.run_git(root, "commit", "-m", "local change")
        self.run_git(root, "fetch", "origin")

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["git"]["syncState"], "diverged")
        self.assertEqual(report["git"]["ahead"], 1)
        self.assertEqual(report["git"]["behind"], 1)
        self.assertTrue(
            any("diverged" in step for step in report["nextSteps"]),
            report["nextSteps"],
        )

    def test_github_tool_absence_is_reported_explicitly(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()

        with mock.patch.object(status.shutil, "which", return_value=None):
            report = status.collect_github(
                root,
                slug="example/repo",
                branch="main",
                network=True,
            )

        self.assertEqual(report["status"], "gh-unavailable")
        self.assertEqual(report["openPrs"], [])
        self.assertEqual(report["openPrsStatus"], "unavailable")
        self.assertEqual(report["openIssues"], [])

    def test_relevant_pr_uses_unpaginated_graphql_review_total(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        separator = status.PR_SEPARATOR
        pr_output = separator.join(
            [
                "42",
                "OPEN",
                "",
                "https://github.com/example/repo/pull/42",
                "feature",
                "a" * 40,
            ]
        )

        with mock.patch.object(
            status,
            "run_command",
            side_effect=[
                status.CommandResult(0, f"{pr_output}\n"),
                status.CommandResult(0, '{"pass": 2}\n'),
                status.CommandResult(0, "47\n"),
            ],
        ) as run_command:
            report = status.collect_relevant_pr(
                root,
                "example/repo",
                "feature",
            )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["reviewCount"], 47)
        review_argv = run_command.call_args_list[2].args[0]
        self.assertEqual(review_argv[:3], ["gh", "api", "graphql"])
        self.assertIn("owner=example", review_argv)
        self.assertIn("name=repo", review_argv)
        self.assertIn("number=42", review_argv)
        self.assertTrue(
            any("reviews{totalCount}" in argument for argument in review_argv)
        )
        self.assertNotIn("repos/example/repo/pulls/42/reviews", review_argv)

    def test_invalid_repository_fails_without_traceback(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-invalid-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)

        result = self.run_status(root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("error: unable to inspect Git repository", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_parse_args_accepts_positional_repository_and_reserved_fleet(self) -> None:
        status = self.load_status_module()
        root = Path("/tmp/status repo")

        positional = status.parse_args([str(root), "--json", "--no-network"])
        explicit = status.parse_args(["--repo", str(root), "--json"])
        relative = status.parse_args(["../status-repo"])
        option_like = status.parse_args(["--", "-status-repo"])
        fleet = status.parse_args(["fleet", "--no-network"])
        current = status.parse_args([])

        self.assertIsNone(positional.mode)
        self.assertEqual(positional.repo, root)
        self.assertTrue(positional.json)
        self.assertTrue(positional.no_network)
        self.assertIsNone(explicit.mode)
        self.assertEqual(explicit.repo, root)
        self.assertEqual(relative.repo, Path("../status-repo"))
        self.assertEqual(option_like.repo, Path("-status-repo"))
        self.assertEqual(fleet.mode, "fleet")
        self.assertEqual(current.repo, Path.cwd())

    def test_main_rejects_missing_positional_repository_path(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        previous_cwd = Path.cwd()
        self.addCleanup(os.chdir, previous_cwd)
        os.chdir(root)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = status.main(["repoo", "--no-network"])

        self.assertEqual(result, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("unable to inspect Git repository: repoo", stderr.getvalue())

    def test_parse_args_rejects_positional_repository_conflicts(self) -> None:
        status = self.load_status_module()
        conflicts = (
            ["/tmp/one", "--repo", "/tmp/two"],
            ["fleet", "--repo", "/tmp/two"],
            ["/tmp/one", "/tmp/two"],
        )

        for argv in conflicts:
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        status.parse_args(argv)
                self.assertEqual(raised.exception.code, 2)

    def test_git_status_failure_stops_before_rendering(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        output = io.StringIO()

        with (
            mock.patch.object(
                status,
                "collect_git",
                return_value=({}, ["git status is unavailable"]),
            ),
            contextlib.redirect_stderr(output),
        ):
            result = status.main(["--repo", str(root), "--no-network"])

        self.assertEqual(result, 1)
        self.assertIn("error: unable to inspect Git repository", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_fleet_helper_import_restores_sys_path(self) -> None:
        status = self.load_status_module()
        scripts_path = str(
            (PACK_ROOT / "templates/scripts").resolve()
        )
        original_path = [entry for entry in status.sys.path if entry != scripts_path]

        with mock.patch.object(status.sys, "path", original_path.copy()):
            fleet = status.fleet_api()

            self.assertEqual(status.sys.path, original_path)
            self.assertTrue(hasattr(fleet, "resolve_fleet_configuration"))

    def test_fleet_report_uses_priority_and_surfaces_stale_and_missing_repos(
        self,
    ) -> None:
        status = self.load_status_module()
        current = self.make_status_repo(pack_version=PACK_VERSION)
        stale = self.make_status_repo(pack_version="0.18.0")
        (current / "README.md").write_text("fleet stash\n", encoding="utf-8")
        self.run_git(current, "stash", "push", "-m", "fleet status fixture")
        missing = current.parent / "missing"
        manifest = current.parent / "fleet.json"
        manifest.write_text(
            json.dumps(
                fleet_manifest(
                    [
                        {
                            "name": "slow-current",
                            "github": "example/slow-current",
                            "pathHint": str(current),
                            "platforms": ["claude"],
                            "rolloutPriority": 90,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["bash", "check.sh"]],
                        },
                        {
                            "name": "fast-stale",
                            "github": "example/fast-stale",
                            "pathHint": str(stale),
                            "platforms": ["claude"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["bash", "check.sh"]],
                        },
                        {
                            "name": "missing",
                            "github": "example/missing",
                            "pathHint": str(missing),
                            "platforms": ["claude"],
                            "rolloutPriority": 20,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["bash", "check.sh"]],
                        },
                    ]
                )
            )
            + "\n",
            encoding="utf-8",
        )

        report = status.collect_fleet(
            PACK_ROOT,
            fleet_path=manifest,
            network=False,
            refs_refreshed=False,
        )

        self.assertIsNotNone(report)
        self.assertEqual(report["mode"], "fleet")
        self.assertEqual(
            [item["name"] for item in report["repositories"]],
            ["fast-stale", "missing", "slow-current"],
        )
        self.assertEqual(report["repositories"][0]["report"]["versions"]["packState"], "different")
        self.assertEqual(report["repositories"][1]["status"], "missing")
        self.assertIn("missing", report["nextSteps"][0])
        self.assertTrue(any("fast-stale" in step for step in report["nextSteps"]))

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status.render_fleet(report)
        rendered = output.getvalue()
        self.assertLess(rendered.index("fast-stale"), rendered.index("slow-current"))
        self.assertIn(f"Target pack: {PACK_VERSION}", rendered)
        self.assertIn("slow-current: clean; main; cached:synchronized; pack", rendered)
        self.assertIn("stashes 1", rendered)
        self.assertIn("PRs unavailable", rendered)

    def test_fleet_loader_requires_pack_identity(self) -> None:
        status = self.load_status_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-pack-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        (root / "manifest.json").write_text(
            '{"name": "another-pack", "version": "1.0.0"}\n',
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "cannot associate fleet manifest"):
            status.load_fleet(root, root / "fleet.json")

    def test_fleet_profile_resolution_precedence_and_default_paths(self) -> None:
        fleet = self.load_fleet_lib()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-config-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        config = root / "profile.json"
        profile_manifest = root / "profile-fleet.json"
        env_manifest = root / "env-fleet.json"
        cli_manifest = root / "cli-fleet.json"
        config.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "packSource": str(PACK_ROOT),
                    "fleetManifest": str(profile_manifest),
                    "pathOverrides": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        env = {
            fleet.FLEET_CONFIG_ENV: str(config),
            fleet.FLEET_MANIFEST_ENV: str(env_manifest),
        }

        explicit = fleet.resolve_fleet_configuration(
            PACK_ROOT,
            fleet_manifest=cli_manifest,
            environ=env,
        )
        environment = fleet.resolve_fleet_configuration(PACK_ROOT, environ=env)
        profile = fleet.resolve_fleet_configuration(
            root,
            environ={fleet.FLEET_CONFIG_ENV: str(config)},
        )
        source = fleet.resolve_fleet_configuration(
            PACK_ROOT,
            environ={fleet.FLEET_CONFIG_ENV: str(root / "missing.json")},
        )

        self.assertEqual(explicit.manifest_path, cli_manifest.resolve())
        self.assertEqual(explicit.source, "command line")
        self.assertEqual(environment.manifest_path, env_manifest.resolve())
        self.assertEqual(environment.source, fleet.FLEET_MANIFEST_ENV)
        self.assertEqual(profile.manifest_path, profile_manifest.resolve())
        self.assertEqual(profile.source, "machine profile")
        self.assertEqual(
            source.manifest_path,
            (PACK_ROOT / "docs/fleet/consumers.json").resolve(),
        )
        self.assertEqual(
            fleet.fleet_profile_path({}, home=root),
            (root / ".config/sd-ai-command-pack/config.json").resolve(),
        )
        self.assertEqual(
            fleet.fleet_profile_path({"XDG_CONFIG_HOME": str(root / "xdg")}),
            (root / "xdg/sd-ai-command-pack/config.json").resolve(),
        )
        with self.assertRaisesRegex(ValueError, "XDG_CONFIG_HOME must be an absolute"):
            fleet.fleet_profile_path({"XDG_CONFIG_HOME": "relative"})

    def test_profile_writer_is_opt_in_atomic_and_preserves_path_overrides(self) -> None:
        fleet = self.load_fleet_lib()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-profile-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        profile_path = root / "config.json"
        env = {fleet.FLEET_CONFIG_ENV: str(profile_path)}

        planned = fleet.configure_fleet_profile(
            PACK_ROOT,
            environ=env,
            dry_run=True,
        )
        self.assertEqual(planned.status, "planned")
        self.assertFalse(profile_path.exists())

        created = fleet.configure_fleet_profile(PACK_ROOT, environ=env)
        self.assertEqual(created.status, "created")
        self.assertEqual(profile_path.stat().st_mode & 0o777, 0o600)
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        payload["pathOverrides"] = {"Example": "../checkouts/example"}
        profile_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        updated = fleet.configure_fleet_profile(PACK_ROOT, environ=env)
        self.assertEqual(updated.status, "updated")
        refreshed = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(
            refreshed["pathOverrides"],
            {"Example": "../checkouts/example"},
        )
        self.assertEqual(
            fleet.configure_fleet_profile(PACK_ROOT, environ=env).status,
            "current",
        )

        profile_path.write_text("{broken\n", encoding="utf-8")
        before = profile_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "fleet profile is not valid"):
            fleet.configure_fleet_profile(PACK_ROOT, environ=env)
        self.assertEqual(profile_path.read_bytes(), before)

    def test_installed_status_uses_machine_profile_and_checkout_override(self) -> None:
        root = self.make_status_repo(pack_version=PACK_VERSION)
        install_root = root.parent / "consumer"
        status_script = self.make_portable_status_install(install_root)
        manifest = root.parent / "portable-fleet.json"
        manifest.write_text(
            json.dumps(
                fleet_manifest(
                    [
                        {
                            "name": "portable",
                            "github": "example/portable",
                            "pathHint": str(root.parent / "wrong"),
                            "platforms": ["claude"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["bash", "check.sh"]],
                        }
                    ]
                )
            )
            + "\n",
            encoding="utf-8",
        )
        profile = root.parent / "fleet-profile.json"
        profile.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "packSource": str(PACK_ROOT),
                    "fleetManifest": str(manifest),
                    "pathOverrides": {"portable": str(root)},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        before = profile.read_bytes()

        child_env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}
        }
        child_env.update(
            {
                "SD_AI_COMMAND_PACK_FLEET_CONFIG": str(profile),
                "SD_AI_COMMAND_PACK_FLEET_MANIFEST": "",
            }
        )
        result = subprocess.run(
            [sys.executable, str(status_script), "fleet", "--json", "--no-network"],
            cwd=install_root,
            env=child_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["configuration"]["source"], "machine profile")
        self.assertEqual(report["repositories"][0]["path"], str(root.resolve()))
        self.assertEqual(profile.read_bytes(), before)
        self.assertFalse((status_script.parent / "__pycache__").exists())

    def test_installed_status_reports_missing_or_malformed_profile_cleanly(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-portable-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        status_script = self.make_portable_status_install(root / "consumer")
        profile = root / "config.json"
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "SD_AI_COMMAND_PACK_FLEET_CONFIG": str(profile),
            "SD_AI_COMMAND_PACK_FLEET_MANIFEST": "",
        }

        missing = subprocess.run(
            [sys.executable, str(status_script), "fleet", "--no-network"],
            cwd=status_script.parents[1],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(missing.returncode, 1, missing.stdout)
        self.assertIn("--configure-fleet", missing.stdout)
        self.assertNotIn("Traceback", missing.stdout)

        profile.write_text("{broken\n", encoding="utf-8")
        malformed = subprocess.run(
            [sys.executable, str(status_script), "fleet", "--no-network"],
            cwd=status_script.parents[1],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(malformed.returncode, 1, malformed.stdout)
        self.assertIn("fleet profile is unusable", malformed.stdout)
        self.assertNotIn("Traceback", malformed.stdout)

        profile.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "packSource": str(root / "moved-pack"),
                    "pathOverrides": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        stale = subprocess.run(
            [sys.executable, str(status_script), "fleet", "--no-network"],
            cwd=status_script.parents[1],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(stale.returncode, 1, stale.stdout)
        self.assertIn("fleet profile is unusable", stale.stdout)
        self.assertIn("pack manifest not found", stale.stdout)
        self.assertNotIn("Traceback", stale.stdout)


if __name__ == "__main__":
    unittest.main()
