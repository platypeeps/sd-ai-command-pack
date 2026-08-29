from __future__ import annotations

import ast

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

    def load_recovery_module(self):
        return self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-recovery-artifacts.py",
            "status_test_recovery",
        )

    def collect_with_temp_helper(self, status, collector, helper_name, source, root):
        """Run a status collector against a REAL temp sibling helper.

        Writes ``source`` to ``helper_name`` beside a faux status ``__file__`` so
        the collector's atomic loader reads and execs actual bytes (no importlib
        seam mock). Returns the collector result.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / helper_name).write_text(source, encoding="utf-8")
            fake_status = tmp_path / "sd-ai-command-pack-status.py"
            with mock.patch.object(status, "__file__", str(fake_status)):
                return getattr(status, collector)(root)

    def seed_needs_review_stash(self, root: Path, state_root: Path) -> str:
        """Create a real stash and record a dead-owner receipt for it.

        The stash is not provably redundant and its owner is not live, so the
        recovery classifier reports it as ``needs-review`` -- an actionable but
        conservative state that exercises the status summary and next steps.
        """
        recovery = self.load_recovery_module()
        (root / "README.md").write_text("# Status fixture edit\n", encoding="utf-8")
        self.run_git(
            root, "stash", "push", "-m", "sd-ai-command-pack recovery: status test"
        )
        oid = self.git_output(root, "rev-parse", "stash@{0}")
        recovery.register(
            repo=root,
            artifact_type="stash",
            git_identity={"object": oid, "subject": "recovery stash"},
            created_by="sd-recover",
            run={"runId": "r-dead", "hostname": "not-this-host-xyz", "pid": 4242},
            purpose="protect wip",
            original_head=self.git_output(root, "rev-parse", "HEAD"),
            expected_outcome="restored",
            state_root=state_root,
        )
        return oid

    def make_portable_status_install(self, root: Path) -> Path:
        scripts = root / "scripts"
        scripts.mkdir(parents=True)
        for name in (
            "sd-ai-command-pack-status.py",
            "sd-ai-command-pack-work-loop.py",
            "sd_ai_command_pack_lib.py",
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
        # Emit the one documented `current --json` shape: at the supported
        # vendored-Trellis floor the collector parses that and nothing else.
        (scripts_dir / "task.py").write_text(
            "import json, sys\n"
            "from pathlib import Path\n"
            "task_dir = Path('.trellis/tasks/status-fixture')\n"
            "if '--json' in sys.argv:\n"
            "    print(json.dumps({\n"
            "        'current_task': {'dir': str(task_dir),\n"
            "                         'id': 'status-fixture'},\n"
            "        'source': 'file',\n"
            "        'stale': False,\n"
            "    }))\n"
            "else:\n"
            "    print(task_dir)\n",
            encoding="utf-8",
        )
        (root / ".trellis/.version").write_text("0.6.16-sd.7\n", encoding="utf-8")
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

    def machine_scratch(self) -> tuple[Path, Path]:
        """A scratch home and state root for machine-scope reporting.

        Nothing in these tests may read or write the developer's real
        ``~/.agents`` or state directory, so both are always overridden.
        """
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-machine-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        home = base / "home"
        home.mkdir()
        return home, base / "state"

    def write_machine_receipt(
        self,
        state_home: Path,
        *,
        pack_version: str = "9.9.9",
        raw: str | None = None,
    ) -> Path:
        """Write a machine receipt the engine accepts, or arbitrary bytes."""
        machine_dir = state_home / "machine"
        machine_dir.mkdir(parents=True, exist_ok=True)
        receipt = machine_dir / "machine-receipt.json"
        if raw is not None:
            receipt.write_text(raw, encoding="utf-8")
            return receipt
        digest = "sha256:" + hashlib.sha256(b"machine payload row").hexdigest()
        receipt.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "packVersion": pack_version,
                    "payloadDigest": digest,
                    "installedAt": "2026-08-09T00:00:00Z",
                    "sourceRoot": "/plugin/machine-payload",
                    "files": [
                        {
                            "family": "agents-skills",
                            "path": "sd-check/SKILL.md",
                            "digest": digest,
                            "executable": False,
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return receipt

    def machine_state_env(self, state_home: Path) -> dict[str, str]:
        return {"SD_AI_COMMAND_PACK_STATE_HOME": str(state_home)}

    def machine_section(self, status, root: Path, home: Path, state_home: Path):
        """Collect machine scope with every destination root inside the scratch.

        The module under test is the canonical ``templates/scripts/`` copy,
        which has no sibling ``installer/``; the installed arrangement does, so
        ``__file__`` points at the mirror the pack actually ships.
        """
        installed_status = PACK_ROOT / "scripts/sd-ai-command-pack-status.py"
        with mock.patch.object(status, "__file__", str(installed_status)):
            return status.collect_machine_scope(
                root,
                home=home,
                environ={"XDG_CONFIG_HOME": str(home / ".config")},
                state_home=state_home,
            )

    def plugin_listing(self, *entries: dict[str, str]) -> str:
        return json.dumps(list(entries))

    @contextlib.contextmanager
    def stub_claude(self, status, listing: object, *, returncode: int = 0):
        """Answer `claude plugin list --json` without a real CLI on PATH."""
        with (
            mock.patch.object(
                status.shutil,
                "which",
                side_effect=lambda name: "/usr/bin/claude" if name == "claude" else None,
            ),
            mock.patch.object(
                status,
                "run_command",
                return_value=status.CommandResult(
                    returncode,
                    listing if isinstance(listing, str) else json.dumps(listing),
                ),
            ),
        ):
            yield

    def write_stub_claude_cli(self, directory: Path, listing: object) -> Path:
        """A real executable `claude` for end-to-end subprocess coverage."""
        directory.mkdir(parents=True, exist_ok=True)
        script = directory / "claude"
        payload = listing if isinstance(listing, str) else json.dumps(listing)
        script.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = plugin ] && [ \"$2\" = list ]; then\n"
            f"  cat <<'JSON'\n{payload}\nJSON\n"
            "  exit 0\n"
            "fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

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

    def recovery_state_snapshot(self, state_root: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for path in sorted(state_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            snapshot[path.relative_to(state_root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        return snapshot

    def _held_default_git(self, **overrides):
        """A post-merge snapshot with the default branch held by a worktree.

        The reporting worktree is on the source branch because it could not
        switch away; the holder is a second, live worktree. Every override
        exists so a single field can be flipped back to its ordinary value and
        the expectation it drives re-checked in isolation.
        """

        git = {
            "branch": "feature/cleanup",
            "workingTree": {"state": "clean"},
            "defaultBranch": "main",
            "defaultLocalExists": True,
            "defaultRemoteExists": True,
            "defaultMatchesRemote": False,
            "defaultBehindRemote": True,
            "localBranches": ["main", "feature/cleanup"],
            "remoteBranches": ["origin/main"],
            "worktrees": {
                "status": "ok",
                "rows": [
                    {
                        "path": "/repos/wt-a",
                        "branch": "feature/cleanup",
                        "current": True,
                    },
                    {"path": "/repos/primary", "branch": "main", "current": False},
                ],
            },
        }
        git.update(overrides)
        return git

    def _strict(self, git, **kwargs):
        status = self.load_status_module()
        params = {
            "default": "main",
            "remote": "origin",
            "source_branch": "feature/cleanup",
            "keep_remote_branch": False,
            "dry_run": False,
        }
        params.update(kwargs)
        return {
            code: severity for code, severity, _ in status.strict_anomalies(git, **params)
        }

    def test_held_default_branch_demotes_only_its_own_consequences(self) -> None:
        codes = self._strict(self._held_default_git())

        self.assertEqual(codes.get("current_branch_default_held_elsewhere"), "advisory")
        self.assertEqual(
            codes.get("local_source_branch_held_by_this_worktree"), "advisory"
        )
        self.assertEqual(codes.get("default_branch_behind_held_elsewhere"), "advisory")
        self.assertNotIn("current_branch_unexpected", codes)
        self.assertNotIn("local_source_branch_retained", codes)
        self.assertNotIn("default_branch_diverged", codes)
        self.assertNotIn("remote_source_branch_retained", codes)
        self.assertFalse([code for code, severity in codes.items() if severity != "advisory"])

    def test_unheld_default_branch_keeps_every_expectation_blocking(self) -> None:
        # The same shape with nothing holding the default branch: the run simply
        # did not finish, and each code keeps its ordinary blocking severity.
        codes = self._strict(
            self._held_default_git(
                worktrees={
                    "status": "ok",
                    "rows": [
                        {
                            "path": "/repos/wt-a",
                            "branch": "feature/cleanup",
                            "current": True,
                        }
                    ],
                }
            )
        )

        self.assertEqual(codes.get("current_branch_unexpected"), "blocking")
        self.assertEqual(codes.get("default_branch_diverged"), "blocking")
        self.assertNotIn("current_branch_default_held_elsewhere", codes)
        self.assertNotIn("default_branch_behind_held_elsewhere", codes)

    def test_source_branch_with_no_holder_still_blocks(self) -> None:
        codes = self._strict(
            self._held_default_git(
                worktrees={
                    "status": "ok",
                    "rows": [
                        {"path": "/repos/primary", "branch": "main", "current": False},
                        {"path": "/repos/wt-a", "branch": None, "current": True},
                    ],
                }
            )
        )

        self.assertEqual(codes.get("local_source_branch_retained"), "blocking")
        self.assertNotIn("local_source_branch_held_by_this_worktree", codes)

    def test_genuinely_retained_remote_branch_still_blocks_when_default_is_held(
        self,
    ) -> None:
        codes = self._strict(
            self._held_default_git(
                remoteBranches=["origin/main", "origin/feature/cleanup"]
            )
        )

        self.assertEqual(codes.get("remote_source_branch_retained"), "blocking")

    def test_diverged_default_branch_still_blocks_when_it_is_not_behind(self) -> None:
        # Held elsewhere, but the local tip is not an ancestor of the remote
        # tip: a fast-forward would not have reconciled this, so the deferred
        # cleanup does not explain it.
        codes = self._strict(self._held_default_git(defaultBehindRemote=False))

        self.assertEqual(codes.get("default_branch_diverged"), "blocking")
        self.assertNotIn("default_branch_behind_held_elsewhere", codes)

    def test_unavailable_worktree_inventory_demotes_nothing(self) -> None:
        codes = self._strict(
            self._held_default_git(worktrees={"status": "unavailable", "rows": None})
        )

        self.assertEqual(codes.get("current_branch_unexpected"), "blocking")
        self.assertEqual(codes.get("local_source_branch_retained"), "blocking")
        self.assertEqual(codes.get("default_branch_diverged"), "blocking")

    def test_branch_merged_only_into_the_remote_default_is_classified_merged(
        self,
    ) -> None:
        # The local default could not be fast-forwarded because another worktree
        # holds it, so the merge this run performed is reachable only from the
        # remote-tracking tip. Reading merge evidence from the local tip alone
        # reported the just-merged branch as unmerged with no open pull request.
        status = self.load_status_module()
        git = self._held_default_git(
            mergedIntoDefault=["main"],
            mergedIntoRemoteDefault=["main", "feature/cleanup"],
        )
        classification = status.classify_local_branches(
            git, {"openPrsStatus": "available", "openPrs": []}
        )

        rows = {row["branch"]: row["disposition"] for row in classification["rows"]}
        self.assertEqual(rows["feature/cleanup"], "merged")
        self.assertEqual(
            status.branch_classification_anomalies(classification),
            [],
        )

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
        self.assertEqual(report["schemaVersion"], 2)
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
        self.assertEqual(report["followUps"], [])
        self.assertEqual(
            [task["selectionId"] for task in report["trellis"]["tasks"]],
            ["T-1"],
        )
        self.assertEqual(report["trellis"]["tasks"][0]["id"], "status-fixture")
        self.assertNotIn("roadmap", report["trellis"])
        self.assertEqual(self.working_files_snapshot(root), before_files)
        self.assertEqual(
            self.git_output(root, "for-each-ref", "--format=%(refname) %(objectname)"),
            before_refs,
        )

    def test_active_task_resolves_from_current_json_payload(self) -> None:
        # At the supported floor `task.py current --json` emits a JSON document
        # and the collector reads current_task.dir from it.
        root = self.make_status_repo()
        (root / ".trellis/scripts/task.py").write_text(
            "import json\n"
            "import sys\n"
            "if '--json' in sys.argv:\n"
            "    print(json.dumps({\n"
            "        'current_task': {'dir': '.trellis/tasks/status-fixture'},\n"
            "        'source': 'file',\n"
            "        'stale': False,\n"
            "    }))\n"
            "else:\n"
            "    print('.trellis/tasks/status-fixture')\n",
            encoding="utf-8",
        )

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["trellis"]["activeTask"]["id"], "status-fixture")

    def test_active_task_absent_when_json_flag_is_ignored(self) -> None:
        # A variant that ignores unknown flags prints the bare task path with
        # exit 0. Below the supported floor that prose was parsed as a path;
        # at the floor it is not the documented interface, so the answer is
        # "no active task" rather than a guess at the output's shape.
        root = self.make_status_repo()
        (root / ".trellis/scripts/task.py").write_text(
            "print('.trellis/tasks/status-fixture')\n",
            encoding="utf-8",
        )

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertIsNone(report["trellis"]["activeTask"])

    def test_active_task_absent_when_current_json_fails(self) -> None:
        # At the supported floor `current --json` is the only interface. A
        # non-zero exit means no active task -- the collector must not fall
        # back to parsing the bare-path prose output.
        root = self.make_status_repo()
        (root / ".trellis/scripts/task.py").write_text(
            "import sys\n"
            "if '--json' in sys.argv:\n"
            "    print('task.py: error: unrecognized arguments: --json',\n"
            "          file=sys.stderr)\n"
            "    sys.exit(2)\n"
            "print('.trellis/tasks/status-fixture')\n",
            encoding="utf-8",
        )

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertIsNone(report["trellis"]["activeTask"])

    def test_active_task_reports_a_stale_pointer(self) -> None:
        # `stale` is the runtime's own verdict on its pointer; a report that
        # drops it shows a healthy active task where there is drift.
        root = self.make_status_repo()
        (root / ".trellis/scripts/task.py").write_text(
            "import json\n"
            "print(json.dumps({\n"
            "    'current_task': {'dir': '.trellis/tasks/status-fixture',\n"
            "                     'id': 'status-fixture'},\n"
            "    'source': 'file',\n"
            "    'stale': True,\n"
            "}))\n",
            encoding="utf-8",
        )

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["trellis"]["activeTaskStale"])

        human = self.run_status(root)

        self.assertEqual(human.returncode, 0, human.stdout)
        self.assertIn("[stale pointer]", human.stdout)

    def test_a_dangling_stale_pointer_names_what_it_points_at(self) -> None:
        # The runtime calls a pointer stale when its directory is gone
        # (`_active_from_ref`: `stale = resolved is None or not
        # resolved.is_dir()`), so this -- not a resolvable record -- is the
        # ordinary stale case. "none active [stale pointer]" would read as a
        # contradiction, and a bare "none active" would hide the drift.
        root = self.make_status_repo()
        (root / ".trellis/scripts/task.py").write_text(
            "import json\n"
            "print(json.dumps({\n"
            "    'current_task': {'dir': '.trellis/tasks/vanished',\n"
            "                     'id': 'vanished'},\n"
            "    'source': 'file',\n"
            "    'stale': True,\n"
            "}))\n",
            encoding="utf-8",
        )

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["trellis"]["activeTaskStale"])
        self.assertIsNone(report["trellis"]["activeTask"])

        human = self.run_status(root)

        self.assertEqual(human.returncode, 0, human.stdout)
        self.assertIn(
            "current Trellis task: none active "
            "[stale pointer to .trellis/tasks/vanished]",
            human.stdout,
        )

    def test_a_stale_pointer_cannot_break_the_report_across_lines(self) -> None:
        # The pointer is another repo's `task.py` output, not ours. A `dir`
        # carrying a newline would split the human line in two and let the
        # tail impersonate a report field.
        root = self.make_status_repo()
        (root / ".trellis/scripts/task.py").write_text(
            "import json\n"
            "print(json.dumps({\n"
            "    'current_task': {'dir': 'tasks/a\\nb- forged: value',\n"
            "                     'id': 'forged'},\n"
            "    'source': 'file',\n"
            "    'stale': True,\n"
            "}))\n",
            encoding="utf-8",
        )

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        pointer = json.loads(result.stdout)["trellis"]["activeTaskPointer"]
        self.assertNotIn("\n", pointer)

        human = self.run_status(root)

        self.assertEqual(human.returncode, 0, human.stdout)
        line = next(
            entry
            for entry in human.stdout.splitlines()
            if entry.startswith("- current Trellis task:")
        )
        self.assertIn("stale pointer to", line)
        self.assertIn("forged: value", line)
        self.assertNotIn("- forged: value", human.stdout.replace(line, ""))

    def test_no_active_task_reports_none_without_a_stale_suffix(self) -> None:
        root = self.make_status_repo()
        (root / ".trellis/scripts/task.py").write_text(
            "import json\n"
            "print(json.dumps({'current_task': None,\n"
            "                  'source': 'file', 'stale': False}))\n",
            encoding="utf-8",
        )

        human = self.run_status(root)

        self.assertEqual(human.returncode, 0, human.stdout)
        self.assertIn("- current Trellis task: none active\n", human.stdout)
        self.assertNotIn("stale pointer", human.stdout)

    def test_local_human_output_always_lists_selectable_sections(self) -> None:
        root = self.make_status_repo()

        result = self.run_status(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("==> Follow-ups\nnone", result.stdout)
        self.assertIn(
            "==> Tasks\nT-1 [in_progress, P1]: Status fixture task",
            result.stdout,
        )
        self.assertNotIn("==> Roadmap", result.stdout)
        self.assertLess(
            result.stdout.index("==> Follow-ups"),
            result.stdout.index("==> Tasks"),
        )

    def test_trellis_inventory_ids_are_complete_and_deterministic(self) -> None:
        root = self.make_status_repo()

        def write_task(
            directory: str,
            *,
            title: str,
            status_value: str,
            priority: str,
            parent: str | None = None,
        ) -> None:
            task_dir = root / ".trellis/tasks" / directory
            task_dir.mkdir()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "id": directory,
                        "title": title,
                        "status": status_value,
                        "priority": priority,
                        "parent": parent,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

        write_task(
            "child-planning",
            title="Child planning",
            status_value="planning",
            priority="P0",
            parent=" status-fixture\x00 ",
        )
        write_task(
            "root-planning",
            title="Root planning",
            status_value="planning",
            priority="P2",
        )
        write_task(
            "completed-root",
            title="Completed root",
            status_value="completed",
            priority="P0",
        )
        write_task(
            "blank-parent",
            title="Blank parent",
            status_value="planning",
            priority="P0",
            parent="   ",
        )
        malformed_parent = root / ".trellis/tasks/malformed-parent"
        malformed_parent.mkdir()
        (malformed_parent / "task.json").write_text(
            json.dumps(
                {
                    "id": "malformed-parent",
                    "title": "Malformed parent",
                    "status": "planning",
                    "priority": "P0",
                    "parent": ["status-fixture"],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        first = json.loads(self.run_status(root, "--json").stdout)["trellis"]
        second = json.loads(self.run_status(root, "--json").stdout)["trellis"]

        self.assertEqual(first["tasks"], second["tasks"])
        self.assertEqual(
            [(task["selectionId"], task["id"]) for task in first["tasks"]],
            [
                ("T-1", "status-fixture"),
                ("T-2", "child-planning"),
                ("T-3", "root-planning"),
                ("T-4", "completed-root"),
            ],
        )
        self.assertEqual(first["tasks"][1]["parent"], "status-fixture")
        self.assertNotIn(
            "blank-parent",
            [task["id"] for task in first["tasks"]],
        )
        self.assertNotIn(
            "malformed-parent",
            [task["id"] for task in first["tasks"]],
        )
        self.assertNotIn("roadmap", first)

    def test_empty_trellis_inventory_sections_print_none(self) -> None:
        root = self.make_status_repo()
        shutil.rmtree(root / ".trellis/tasks/status-fixture")

        machine = json.loads(self.run_status(root, "--json").stdout)
        human = self.run_status(root)

        self.assertEqual(machine["trellis"]["tasks"], [])
        self.assertNotIn("roadmap", machine["trellis"])
        self.assertIn("==> Tasks\nnone", human.stdout)
        self.assertNotIn("==> Roadmap", human.stdout)

    def test_roadmap_source_items_join_follow_ups_with_source_evidence(self) -> None:
        root = self.make_status_repo()
        (root / "ROADMAP.md").write_text(
            "# Roadmap\n"
            "- [ ] First roadmap item\n"
            "  - nested explanation\n"
            "  - [ ] Nested checkbox item\n"
            "- Top-level unmarked item\n"
            "  - Nested unmarked item\n"
            "1. Ordered roadmap item\n"
            "- [x] Completed item\n",
            encoding="utf-8",
        )
        docs = root / "docs"
        docs.mkdir()
        (docs / "PROGRAM-DESIGN.txt").write_text(
            "+ Program design item\n",
            encoding="utf-8",
        )
        proposals = root / "proposals"
        proposals.mkdir()
        (proposals / "feature.mdx").write_text(
            "* Proposal item\n",
            encoding="utf-8",
        )
        (docs / "notes.md").write_text(
            "- Ordinary documentation bullet\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "add roadmap sources")
        self.run_git(root, "push")

        machine = json.loads(self.run_status(root, "--json").stdout)
        human = self.run_status(root)
        roadmap = [item for item in machine["followUps"] if item["kind"] == "roadmap"]

        self.assertEqual(
            [
                (item["selectionId"], item["summary"], item["path"], item["line"])
                for item in roadmap
            ],
            [
                ("F-1", "Program design item", "docs/PROGRAM-DESIGN.txt", 1),
                ("F-2", "Proposal item", "proposals/feature.mdx", 1),
                ("F-3", "First roadmap item", "ROADMAP.md", 2),
                ("F-4", "Nested checkbox item", "ROADMAP.md", 4),
                ("F-5", "Top-level unmarked item", "ROADMAP.md", 5),
                ("F-6", "Ordered roadmap item", "ROADMAP.md", 7),
            ],
        )
        self.assertNotIn("Completed item", str(machine["followUps"]))
        self.assertNotIn("Nested unmarked item", str(machine["followUps"]))
        self.assertNotIn("Ordinary documentation bullet", str(machine["followUps"]))
        self.assertIn(
            "F-1 [roadmap]: Program design item (docs/PROGRAM-DESIGN.txt:1)",
            human.stdout,
        )
        self.assertNotIn("==> Roadmap", human.stdout)

    def test_roadmap_scan_includes_untracked_not_ignored_sources(self) -> None:
        root = self.make_status_repo()
        rfcs = root / "rfcs"
        rfcs.mkdir()
        (rfcs / "next.md").write_text(
            "- Untracked RFC item\n",
            encoding="utf-8",
        )
        status = self.load_status_module()

        candidates, diagnostics = status.collect_roadmap_candidates(
            root,
            status.collect_trellis(root)["tasks"],
        )

        self.assertEqual(diagnostics, [])
        self.assertEqual(
            [
                (item["summary"], item["path"], item["line"])
                for item in candidates
            ],
            [("Untracked RFC item", "rfcs/next.md", 1)],
        )

    def test_roadmap_candidates_deduplicate_against_tasks_and_sources(self) -> None:
        root = self.make_status_repo()
        parked = root / ".trellis/tasks/parked-fixture"
        parked.mkdir()
        (parked / "task.json").write_text(
            json.dumps(
                {
                    "id": "parked-fixture",
                    "title": "PARKED: Deferred delivery item",
                    "status": "planning",
                    "priority": "P2",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        literal_marker = root / ".trellis/tasks/literal-marker-fixture"
        literal_marker.mkdir()
        (literal_marker / "task.json").write_text(
            json.dumps(
                {
                    "id": "literal-marker-fixture",
                    "title": "FooBar",
                    "status": "planning",
                    "priority": "P2",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "BACKLOG.md").write_text(
            "- **Shared candidate**\n"
            "- Status fixture task\n"
            "- Deferred delivery item\n"
            "- See `status-fixture`\n"
            "- [Status fixture task](.trellis/tasks/status-fixture)\n"
            "- Status fixture task plus extra detail\n"
            "- See tasks/status-fixture-extra\n"
            "- See status-fixture.\n"
            "- Foo_Bar\n",
            encoding="utf-8",
        )
        (root / "ROADMAP.md").write_text(
            "- Shared candidate\n"
            "- PARKED: Deferred delivery item\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "add tracked roadmap references")
        self.run_git(root, "push")

        report = json.loads(self.run_status(root, "--json").stdout)
        roadmap = [item for item in report["followUps"] if item["kind"] == "roadmap"]

        self.assertEqual(
            [(item["summary"], item["path"], item["line"]) for item in roadmap],
            [
                ("Shared candidate", "BACKLOG.md", 1),
                ("Status fixture task plus extra detail", "BACKLOG.md", 6),
                ("See tasks/status-fixture-extra", "BACKLOG.md", 7),
                ("Foo_Bar", "BACKLOG.md", 9),
            ],
        )

    def test_roadmap_scan_skips_ignored_symlinked_and_oversized_sources(self) -> None:
        root = self.make_status_repo()
        (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        vendor = root / "vendor"
        vendor.mkdir()
        (vendor / "ROADMAP.md").write_text(
            "- Generated vendor roadmap item\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", ".gitignore", "vendor/ROADMAP.md")
        self.run_git(root, "commit", "-m", "add generated roadmap fixture")
        self.run_git(root, "push")
        ignored = root / "ignored"
        ignored.mkdir()
        (ignored / "ROADMAP.md").write_text(
            "- Ignored roadmap item\n",
            encoding="utf-8",
        )
        external = root.parent / "external-roadmap.md"
        external.write_text("- Symlinked roadmap item\n", encoding="utf-8")
        try:
            (root / "ROADMAP-link.md").symlink_to(external)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")
        status = self.load_status_module()
        (root / "TODO.txt").write_text(
            "- " + ("x" * status.MAX_ROADMAP_SOURCE_BYTES) + "\n",
            encoding="utf-8",
        )

        report = json.loads(self.run_status(root, "--json").stdout)

        self.assertFalse(
            any(item["kind"] == "roadmap" for item in report["followUps"])
        )
        self.assertTrue(
            any("roadmap source scan incomplete" in item for item in report["anomalies"])
        )
        self.assertNotIn("Ignored roadmap item", str(report))
        self.assertNotIn("Generated vendor roadmap item", str(report))
        self.assertNotIn("Symlinked roadmap item", str(report))

    def test_roadmap_scan_diagnostics_are_sanitized_and_bounded(self) -> None:
        root = self.make_status_repo()
        source = root / "roadmap"
        for character in "abcdefg":
            source /= character * 110
        source.mkdir(parents=True)
        unsafe_path = source / "TODO-\nunsafe.txt"
        unsafe_path.write_text(
            "- " + ("x" * self.load_status_module().MAX_ROADMAP_SOURCE_BYTES) + "\n",
            encoding="utf-8",
        )

        report = json.loads(self.run_status(root, "--json").stdout)
        roadmap_diagnostics = [
            item
            for item in report["anomalies"]
            if item.startswith("roadmap source scan incomplete:")
        ]
        issue_followups = [
            item
            for item in report["followUps"]
            if item["source"] == "anomalies"
        ]

        self.assertEqual(len(roadmap_diagnostics), 1)
        self.assertLessEqual(len(roadmap_diagnostics[0]), 500)
        self.assertFalse(any(char in roadmap_diagnostics[0] for char in "\r\n\t"))
        self.assertEqual(len(issue_followups), 1)
        self.assertLessEqual(len(issue_followups[0]["summary"]), 500)
        self.assertFalse(
            any(char in issue_followups[0]["summary"] for char in "\r\n\t")
        )

    def test_trellis_inventory_rejects_empty_normalized_identity_and_status(
        self,
    ) -> None:
        root = self.make_status_repo()

        def write_task(directory: str, payload: dict[str, object]) -> None:
            task_dir = root / ".trellis/tasks" / directory
            task_dir.mkdir()
            (task_dir / "task.json").write_text(
                json.dumps(payload) + "\n",
                encoding="utf-8",
            )

        write_task(
            "empty-id",
            {"id": "\x00", "title": "Empty ID", "status": "planning"},
        )
        write_task(
            "empty-status",
            {"id": "empty-status", "title": "Empty status", "status": "\x00"},
        )
        write_task(
            "fallback-fields",
            {
                "id": "fallback-fields",
                "title": "\x00",
                "status": "planning",
                "priority": "\x00",
            },
        )

        tasks = json.loads(self.run_status(root, "--json").stdout)["trellis"]["tasks"]
        tasks_by_id = {task["id"]: task for task in tasks}

        self.assertNotIn("empty-id", tasks_by_id)
        self.assertNotIn("empty-status", tasks_by_id)
        self.assertEqual(tasks_by_id["fallback-fields"]["title"], "fallback-fields")
        self.assertEqual(
            tasks_by_id["fallback-fields"]["priority"],
            "unprioritized",
        )

    def test_follow_up_ids_classify_and_sort_supported_evidence(self) -> None:
        status = self.load_status_module()
        report = {
            "anomalies": ["status collector warning"],
            "git": {
                "workingTree": {"state": "dirty"},
                "syncState": "ahead",
            },
            "github": {
                "currentPr": {"number": 42, "state": "OPEN"},
                "openIssuesStatus": "available",
                "openIssues": [
                    {"number": 9, "title": "Later issue"},
                    {"number": 2, "title": "Earlier issue"},
                ],
            },
            "workLoop": {"status": "none"},
            "trellis": {"completedOutsideArchive": []},
            "versions": {"packState": "different"},
        }

        follow_ups = status.collect_follow_ups(report)

        self.assertEqual(
            [item["selectionId"] for item in follow_ups],
            [f"F-{index}" for index in range(1, 8)],
        )
        self.assertEqual(
            [item["kind"] for item in follow_ups],
            [
                "issue",
                "action",
                "action",
                "action",
                "recommendation",
                "issue",
                "issue",
            ],
        )
        self.assertIn("#2: Earlier issue", follow_ups[5]["summary"])
        self.assertIn("#9: Later issue", follow_ups[6]["summary"])

    def test_select_items_owns_generated_selection_ids(self) -> None:
        status = self.load_status_module()
        selected = status.select_items(
            [{"selectionId": "untrusted", "id": "task-id"}],
            prefix="T",
        )

        self.assertEqual(selected[0]["selectionId"], "T-1")
        self.assertEqual(selected[0]["id"], "task-id")

    def test_resume_and_archive_follow_ups_are_actions(self) -> None:
        status = self.load_status_module()
        for loop_status in ("active", "paused"):
            with self.subTest(loop_status=loop_status):
                follow_ups = status.collect_follow_ups(
                    {
                        "workLoop": {
                            "status": loop_status,
                            "runId": "run-1",
                            "iteration": 2,
                            "phase": "implement",
                        },
                        "trellis": {"completedOutsideArchive": [{"id": "done"}]},
                    }
                )

                self.assertEqual(
                    [(item["source"], item["kind"]) for item in follow_ups],
                    [
                        ("workLoop.status", "action"),
                        ("trellis.completedOutsideArchive", "action"),
                    ],
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
        selectable_tasks = report["trellis"]["tasks"]
        self.assertIn("completed-record-id", [task["id"] for task in selectable_tasks])
        self.assertNotIn("roadmap", report["trellis"])
        self.assertTrue(
            any(
                item["source"] == "trellis.completedOutsideArchive"
                for item in report["followUps"]
            )
        )
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

        def run(source: str) -> dict:
            return self.collect_with_temp_helper(
                status,
                "collect_work_loop",
                "sd-ai-command-pack-work-loop.py",
                source,
                root,
            )

        # Helper missing the status_snapshot contract entrypoint.
        missing_contract = run("VALUE = 1\n")
        self.assertEqual(missing_contract["status"], "invalid")
        self.assertIn("status_snapshot", missing_contract["error"])

        # Compile-time failure (syntax error) in helper source.
        syntax_failure = run("def status_snapshot(repo):\n    return (\n")
        self.assertEqual(syntax_failure["status"], "invalid")

        # Runtime failure raised by the helper contract.
        malformed_state = run(
            "def status_snapshot(repo):\n    raise KeyError('mode')\n"
        )
        self.assertEqual(malformed_state["status"], "invalid")
        self.assertIn("mode", malformed_state["error"])

    def test_collect_work_loop_validates_helper_snapshot_shapes(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()

        def collect(snapshot: object) -> dict[str, object]:
            source = "def status_snapshot(repo):\n    return " + repr(snapshot) + "\n"
            return self.collect_with_temp_helper(
                status,
                "collect_work_loop",
                "sd-ai-command-pack-work-loop.py",
                source,
                root,
            )

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

    def test_collect_work_loop_bytecode_suppression_scope_and_restore(self) -> None:
        # R4: assert all three properties, not merely restoration (a restore-only
        # check passes even if suppression were removed entirely):
        #   (a) module execution observes dont_write_bytecode == True;
        #   (b) the helper callable, invoked OUTSIDE the suppress block, observes
        #       the prior value;
        #   (c) the prior value is restored after both failure and success.
        root = self.make_status_repo()
        status = self.load_status_module()
        helper = "sd-ai-command-pack-work-loop.py"

        # (a) + (c-failure): suppression active during load; restored after failure.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            probe = tmp_path / "load-probe.txt"
            fail_source = (
                "import sys, pathlib\n"
                f"pathlib.Path({str(probe)!r}).write_text(str(sys.dont_write_bytecode))\n"
                "raise SyntaxError('corrupt helper')\n"
            )
            (tmp_path / helper).write_text(fail_source, encoding="utf-8")
            fake_status = tmp_path / "sd-ai-command-pack-status.py"
            with (
                mock.patch.object(status.sys, "dont_write_bytecode", False),
                mock.patch.object(status, "__file__", str(fake_status)),
            ):
                failure = status.collect_work_loop(root)
                self.assertFalse(status.sys.dont_write_bytecode)
            self.assertEqual(probe.read_text(encoding="utf-8"), "True")
        self.assertEqual(failure["status"], "invalid")

        # (b) + (c-success): status_snapshot runs outside the suppress block, so it
        # observes the prior value; restored after a successful load.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            probe = tmp_path / "call-probe.txt"
            ok_source = (
                "import sys, pathlib\n"
                "def status_snapshot(repo):\n"
                f"    pathlib.Path({str(probe)!r}).write_text(str(sys.dont_write_bytecode))\n"
                "    return {'status': 'none'}\n"
            )
            (tmp_path / helper).write_text(ok_source, encoding="utf-8")
            fake_status = tmp_path / "sd-ai-command-pack-status.py"
            with (
                mock.patch.object(status.sys, "dont_write_bytecode", False),
                mock.patch.object(status, "__file__", str(fake_status)),
            ):
                success = status.collect_work_loop(root)
                self.assertFalse(status.sys.dont_write_bytecode)
            self.assertEqual(probe.read_text(encoding="utf-8"), "False")
        self.assertEqual(success["status"], "none")

    def test_summarize_recovery_filters_active_and_bounds_fields(self) -> None:
        status = self.load_status_module()
        classified = {
            "schemaVersion": 1,
            "repository": {"digest": "d", "label": "repo"},
            "counts": {
                "active": 1,
                "safe-cleanable": 1,
                "needs-review": 1,
                "unowned-artifact": 1,
                "bogus": -3,  # negative counts are dropped
                7: 2,  # non-string keys are dropped
                "flag": True,  # booleans are dropped
            },
            "receipts": [
                {
                    "type": "stash",
                    "classification": "active",
                    "reference": "aaaaaaaa",
                    "detail": "in use",
                },
                {
                    "type": "worktree",
                    "classification": "safe-cleanable",
                    "reference": "b" * 400,
                    "detail": "c" * 400,
                },
                "not-a-mapping",
            ],
            "unowned": [
                {"type": "stash", "reference": "dddddddd", "detail": "orphan"},
                42,
            ],
            "corrupt": [{"reference": "broken.json", "reason": "bad json"}],
        }

        summary = status.summarize_recovery(classified)

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(
            summary["counts"],
            {
                "active": 1,
                "safe-cleanable": 1,
                "needs-review": 1,
                "unowned-artifact": 1,
            },
        )
        self.assertEqual(summary["total"], 4)
        classes = [item["classification"] for item in summary["actionable"]]
        self.assertNotIn("active", classes)
        self.assertIn("safe-cleanable", classes)
        self.assertIn("unowned-artifact", classes)
        self.assertIn("corrupt", classes)
        cleanable = next(
            item
            for item in summary["actionable"]
            if item["classification"] == "safe-cleanable"
        )
        self.assertLessEqual(len(cleanable["reference"]), 200)
        self.assertLessEqual(len(cleanable["detail"]), 200)

    def _collect_recovery_with_helper(self, status, source, root):
        return self.collect_with_temp_helper(
            status,
            "collect_recovery",
            "sd-ai-command-pack-recovery-artifacts.py",
            source,
            root,
        )

    def test_collect_recovery_reports_invalid_helper_without_traceback(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        result = self._collect_recovery_with_helper(
            status,
            "def classify_repository(repo):\n"
            "    raise KeyError('corrupt recovery helper')\n",
            root,
        )
        self.assertEqual(result["status"], "invalid")
        self.assertIn("corrupt recovery helper", result["error"])

    def test_collect_recovery_rejects_unexpected_schema_version(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        result = self._collect_recovery_with_helper(
            status,
            "SCHEMA_VERSION = 1\n"
            "def classify_repository(repo):\n"
            "    return {'schemaVersion': 99, 'counts': {}}\n",
            root,
        )
        self.assertEqual(result["status"], "invalid")
        self.assertIn("schema version", result["error"])

    def test_collect_recovery_rejects_helper_missing_schema_version(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        # No module-level SCHEMA_VERSION: reading it must fail closed to "invalid".
        result = self._collect_recovery_with_helper(
            status,
            "def classify_repository(repo):\n"
            "    return {'schemaVersion': 1, 'counts': {}}\n",
            root,
        )
        self.assertEqual(result["status"], "invalid")
        self.assertIn("schema version", result["error"])

    def test_collect_recovery_rejects_symlinked_helper(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "real-recovery.py"
            target.write_text(
                "def classify_repository(repo):\n    return {}\n", encoding="utf-8"
            )
            link = tmp_path / "sd-ai-command-pack-recovery-artifacts.py"
            link.symlink_to(target)
            fake_status = tmp_path / "sd-ai-command-pack-status.py"
            with mock.patch.object(status, "__file__", str(fake_status)):
                result = status.collect_recovery(root)
        self.assertEqual(result["status"], "unavailable")
        # A present-but-symlinked helper is refused, not absent: the diagnostic
        # must say so rather than the misleading "not installed" (C7/AC7.a).
        self.assertIn("present but refused (symlink)", result["error"])
        self.assertNotIn("not installed", result["error"])

    def test_collect_work_loop_rejects_symlinked_helper(self) -> None:
        root = self.make_status_repo()
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "real-work-loop.py"
            target.write_text(
                "def status_snapshot(repo):\n    return {}\n", encoding="utf-8"
            )
            link = tmp_path / "sd-ai-command-pack-work-loop.py"
            link.symlink_to(target)
            fake_status = tmp_path / "sd-ai-command-pack-status.py"
            with mock.patch.object(status, "__file__", str(fake_status)):
                result = status.collect_work_loop(root)
        self.assertEqual(result["status"], "unavailable")
        # Present-but-symlinked → refused, not absent (C7/AC7.a).
        self.assertIn("present but refused (symlink)", result["error"])
        self.assertNotIn("not installed", result["error"])

    def test_local_status_reports_recovery_artifacts_read_only(self) -> None:
        root = self.make_status_repo()
        state_root = root.parent / "recovery-state"
        oid = self.seed_needs_review_stash(root, state_root)
        env = {"SD_AI_COMMAND_PACK_STATE_HOME": str(state_root)}

        before_repo = self.working_files_snapshot(root)
        before_state = self.recovery_state_snapshot(state_root)

        machine = self.run_status(root, "--json", extra_env=env)
        human = self.run_status(root, extra_env=env)

        self.assertEqual(machine.returncode, 0, machine.stdout)
        report = json.loads(machine.stdout)
        recovery = report["recoveryArtifacts"]
        self.assertEqual(recovery["status"], "ok")
        self.assertEqual(recovery["counts"].get("needs-review"), 1)
        self.assertGreaterEqual(recovery["total"], 1)
        references = [item["reference"] for item in recovery["actionable"]]
        self.assertIn(oid[:12], references)
        classes = {item["classification"] for item in recovery["actionable"]}
        self.assertIn("needs-review", classes)
        self.assertTrue(
            any("Inspect 1 recovery artifact" in step for step in report["nextSteps"])
        )

        self.assertEqual(human.returncode, 0, human.stdout)
        self.assertIn("==> Recovery Artifacts", human.stdout)
        self.assertIn("needs-review", human.stdout)
        self.assertIn(oid[:12], human.stdout)

        self.assertEqual(self.working_files_snapshot(root), before_repo)
        self.assertEqual(self.recovery_state_snapshot(state_root), before_state)

    def test_recovery_section_reports_no_artifacts_on_clean_repo(self) -> None:
        root = self.make_status_repo()
        state_root = root.parent / "empty-recovery-state"
        state_root.mkdir()
        env = {"SD_AI_COMMAND_PACK_STATE_HOME": str(state_root)}

        machine = self.run_status(root, "--json", extra_env=env)
        human = self.run_status(root, extra_env=env)

        recovery = json.loads(machine.stdout)["recoveryArtifacts"]
        self.assertEqual(recovery["status"], "ok")
        self.assertEqual(recovery["total"], 0)
        self.assertEqual(recovery["actionable"], [])
        self.assertIn("no tracked recovery artifacts", human.stdout)

    def worktree_index_bytes(self, worktree: Path) -> bytes:
        git_dir = Path(self.git_output(worktree, "rev-parse", "--absolute-git-dir"))
        index = git_dir / "index"
        return index.read_bytes() if index.exists() else b""

    def test_worktree_inventory_rows_match_porcelain(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "worktree", "add", "-b", "wt-branch", str(root.parent / "wt-a"))
        self.run_git(root, "worktree", "add", "--detach", str(root.parent / "wt-b"))

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        rows = json.loads(result.stdout)["git"]["worktrees"]["rows"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(1 for row in rows if row["current"]), 1)
        expected: list[dict[str, object]] = []
        for line in self.git_output(root, "worktree", "list", "--porcelain").splitlines():
            if line.startswith("worktree "):
                expected.append(
                    {"path": line.removeprefix("worktree "), "branch": None, "detached": False}
                )
            elif line.startswith("branch "):
                expected[-1]["branch"] = line.removeprefix("branch ").removeprefix(
                    "refs/heads/"
                )
            elif line == "detached":
                expected[-1]["detached"] = True
        self.assertEqual(
            [(row["path"], row["branch"], row["detached"]) for row in rows],
            [(row["path"], row["branch"], row["detached"]) for row in expected],
        )

    def test_held_branch_marking_matches_checkout_refusals(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "branch", "free-branch")
        self.run_git(root, "worktree", "add", "-b", "held-branch", str(root.parent / "wt-held"))

        machine = self.run_status(root, "--json")
        human = self.run_status(root)
        self.assertEqual(machine.returncode, 0, machine.stdout)
        report = json.loads(machine.stdout)

        no_hooks = root.parent / "no-hooks"
        no_hooks.mkdir(exist_ok=True)
        initial_branch = self.git_output(root, "rev-parse", "--abbrev-ref", "HEAD")
        refused: set[str] = set()
        try:
            for name in report["git"]["localBranches"]:
                attempt = subprocess.run(
                    ["git", "-c", f"core.hooksPath={no_hooks}", "checkout", name],
                    cwd=root,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if attempt.returncode != 0 and "already used by worktree" in attempt.stderr:
                    refused.add(name)
        finally:
            subprocess.run(
                ["git", "-c", f"core.hooksPath={no_hooks}", "checkout", initial_branch],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(set(report["git"]["branchesHeldElsewhere"]), refused)
        self.assertIn("held-branch [worktree]", human.stdout)
        self.assertNotIn("free-branch [worktree]", human.stdout)
        self.assertNotIn("main [worktree]", human.stdout)

    def test_non_branch_worktree_ref_stays_out_of_held_set(self) -> None:
        root = self.make_status_repo()
        worktree = root.parent / "wt-oddref"
        self.run_git(root, "worktree", "add", "-b", "odd-branch", str(worktree))
        oid = self.git_output(root, "rev-parse", "HEAD")
        self.run_git(worktree, "update-ref", "refs/odd/pin", oid)
        self.run_git(worktree, "symbolic-ref", "HEAD", "refs/odd/pin")

        result = self.run_status(root, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        held = report["git"]["branchesHeldElsewhere"]
        self.assertEqual(held, [])
        self.assertTrue(
            set(held).issubset(set(report["git"]["localBranches"]))
        )

    # --- leftover-branch classification and anomaly severity -----------------

    def collect_git_for(self, root):
        status = self.load_status_module()
        git, _ = status.collect_git(
            root,
            remote="origin",
            supplied_default=None,
            refs_refreshed=False,
        )
        return status, git

    def github_evidence(
        self,
        *,
        status_value="available",
        prs=(),
        closed_prs=(),
        closed_status=None,
    ):
        return {
            "openPrs": list(prs),
            "openPrsStatus": status_value,
            "closedPrs": list(closed_prs),
            "closedPrsStatus": closed_status or status_value,
        }

    def remote_only_branch(self, root, name: str, *, merged: bool = False) -> None:
        """Leave `name` on the remote with no local ref, as an abandonment does."""

        if merged:
            self.run_git(root, "branch", name)
        else:
            self.unmerged_branch(root, name)
        self.run_git(root, "push", "origin", name)
        self.run_git(root, "branch", "-D", name)

    def unmerged_branch(self, root, name: str) -> None:
        self.run_git(root, "switch", "-c", name)
        (root / f"{name.replace('/', '-')}.txt").write_text("work\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", f"work on {name}")
        self.run_git(root, "switch", "main")

    def dispositions(self, classification) -> dict:
        return {
            row["branch"]: row["disposition"] for row in classification["rows"]
        }

    def test_remote_only_branch_is_classified(self) -> None:
        """A branch with no local ref is classified by nothing else."""

        root = self.make_status_repo()
        self.remote_only_branch(root, "feat/abandoned")

        status, git = self.collect_git_for(root)
        classification = status.classify_remote_branches(git, self.github_evidence())

        self.assertEqual(classification["status"], "ok")
        self.assertEqual(
            self.dispositions(classification),
            {"origin/feat/abandoned": "unmerged-without-pull-request"},
        )
        # The local classifier sees nothing here, which is the defect: without
        # the remote pass the branch reaches no row, follow-up, or anomaly.
        self.assertEqual(
            status.classify_local_branches(git, self.github_evidence())["rows"],
            [],
        )

    def test_remote_branch_with_closed_unmerged_pr_is_distinguished(self) -> None:
        root = self.make_status_repo()
        self.remote_only_branch(root, "feat/closed-pr")
        self.remote_only_branch(root, "feat/never-had-one")

        status, git = self.collect_git_for(root)
        classification = status.classify_remote_branches(
            git,
            self.github_evidence(
                closed_prs=[
                    {"number": 570, "head": "feat/closed-pr", "merged": False},
                ]
            ),
        )

        # "Someone decided not to ship this" and "nobody ever opened one" call
        # for different operator action, so they are different dispositions.
        self.assertEqual(
            self.dispositions(classification),
            {
                "origin/feat/closed-pr": "unmerged-with-closed-pull-request",
                "origin/feat/never-had-one": "unmerged-without-pull-request",
            },
        )
        rows = {row["branch"]: row for row in classification["rows"]}
        self.assertEqual(rows["origin/feat/closed-pr"]["pullRequest"], 570)

        codes = dict(
            status.branch_classification_anomalies(classification, scope="remote")
        )
        self.assertIn("remote_branches_pull_request_closed_unmerged", codes)
        self.assertIn(
            "origin/feat/closed-pr",
            codes["remote_branches_pull_request_closed_unmerged"],
        )
        # Status never fetches, so an advisory row must not read as a claim
        # about the remote as it is right now.
        self.assertIn(
            "cached remote-tracking refs",
            codes["remote_branches_pull_request_closed_unmerged"],
        )
        self.assertIn("remote_branches_unmerged_without_pr", codes)

    def test_remote_branch_reachable_from_default_reads_merged(self) -> None:
        """Merge evidence must come from a ref that can witness it.

        The local classifier walks `--merged refs/heads`, which no remote-only
        ref appears in; reusing it here would report every remote branch
        unmerged.
        """

        root = self.make_status_repo()
        self.remote_only_branch(root, "chore/already-merged", merged=True)

        status, git = self.collect_git_for(root)
        self.assertNotIn(
            "origin/chore/already-merged",
            git.get("mergedIntoDefault") or [],
        )
        classification = status.classify_remote_branches(git, self.github_evidence())

        self.assertEqual(
            self.dispositions(classification),
            {"origin/chore/already-merged": "merged"},
        )
        self.assertEqual(
            status.branch_classification_anomalies(classification, scope="remote"),
            [],
        )

    def test_truncated_pr_evidence_leaves_remote_rows_unknown(self) -> None:
        root = self.make_status_repo()
        self.remote_only_branch(root, "feat/unknowable")

        status, git = self.collect_git_for(root)
        max_items = status.MAX_ITEMS
        classification = status.classify_remote_branches(
            git,
            self.github_evidence(
                prs=[
                    {"number": index, "head": f"other/{index}"}
                    for index in range(max_items)
                ]
            ),
        )

        # A full page proves nothing about a branch missing from it: the
        # absence claim is withheld, exactly as it is for a local branch.
        self.assertEqual(
            self.dispositions(classification),
            {"origin/feat/unknowable": "unknown"},
        )
        self.assertEqual(
            classification["evidence"]["pullRequests"], "pr_evidence_truncated"
        )
        codes = dict(
            status.branch_classification_anomalies(classification, scope="remote")
        )
        self.assertIn("remote_branches_pr_state_unknown", codes)
        self.assertIn("pr_evidence_truncated", codes["remote_branches_pr_state_unknown"])
        self.assertIn("not a claim", codes["remote_branches_pr_state_unknown"])

        closed_truncated = status.classify_remote_branches(
            git,
            self.github_evidence(
                closed_prs=[
                    {"number": index, "head": f"other/{index}", "merged": True}
                    for index in range(max_items)
                ]
            ),
        )
        self.assertEqual(
            self.dispositions(closed_truncated),
            {"origin/feat/unknowable": "unknown"},
        )

    def test_branch_on_both_sides_yields_exactly_one_row(self) -> None:
        root = self.make_status_repo()
        self.unmerged_branch(root, "feat/still-local")
        self.run_git(root, "push", "origin", "feat/still-local")

        status, git = self.collect_git_for(root)
        self.assertIn("origin/feat/still-local", git["remoteBranches"])
        local = status.classify_local_branches(git, self.github_evidence())
        remote = status.classify_remote_branches(git, self.github_evidence())

        self.assertEqual(
            self.dispositions(local),
            {"feat/still-local": "unmerged-without-pull-request"},
        )
        self.assertEqual(remote["rows"], [])

    def test_default_branch_and_head_are_excluded_from_remote_rows(self) -> None:
        root = self.make_status_repo()

        status, git = self.collect_git_for(root)
        self.assertIn("origin/HEAD", git["remoteBranches"])
        self.assertIn("origin/main", git["remoteBranches"])
        classification = status.classify_remote_branches(git, self.github_evidence())

        self.assertEqual(classification["rows"], [])

    def test_json_report_exposes_remote_branch_rows(self) -> None:
        root = self.make_status_repo()
        self.remote_only_branch(root, "feat/abandoned")

        result = self.run_status(root, "--json", "--no-network")
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)

        classification = payload["remoteBranchClassification"]
        self.assertEqual(classification["status"], "ok")
        self.assertEqual(
            [row["branch"] for row in classification["rows"]],
            ["origin/feat/abandoned"],
        )
        # --no-network leaves no pull-request evidence, so the absence claim is
        # withheld rather than asserted.
        self.assertEqual(
            classification["rows"][0]["disposition"],
            "unknown",
        )

    def test_status_collector_issues_no_network_mutating_git_command(self) -> None:
        """Status is read-only and never fetches; this enumerates, not greps.

        Every git argv the collector can build is read off the AST, so a new
        mutating or ref-updating subcommand fails here rather than silently
        shipping. The allowlist is not "no network": `ls-remote` reads the
        remote without touching a ref or the working tree, which is the line
        this guard draws.
        """

        source = (
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-status.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        read_only = {
            "for-each-ref",
            "log",
            "ls-files",
            "ls-remote",
            "merge-base",
            "remote",
            "rev-parse",
            "show-ref",
            "stash",
            "status",
            "symbolic-ref",
            "worktree",
        }

        def first_subcommand(values: list[str]) -> str | None:
            for value in values:
                if value.startswith("-"):
                    continue
                return value
            return None

        seen: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            args: list[str] | None = None
            if isinstance(node.func, ast.Name) and node.func.id == "git_output":
                args = [
                    arg.value
                    for arg in node.args[1:]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                ]
            elif node.args and isinstance(node.args[0], ast.List):
                literals = [
                    element.value
                    for element in node.args[0].elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                ]
                if literals[:1] != ["git"]:
                    continue
                args = literals[1:]
            if not args:
                continue
            subcommand = first_subcommand(args)
            if subcommand and subcommand != "-C":
                seen.add(subcommand)

        self.assertTrue(seen)
        self.assertEqual(seen - read_only, set())
        for forbidden in ("fetch", "pull", "push", "prune"):
            self.assertNotIn(forbidden, seen)

    def test_branch_dispositions_separate_merged_unmerged_and_prless(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "branch", "chore/merged")
        self.unmerged_branch(root, "chore/open-pr")
        self.unmerged_branch(root, "chore/no-pr")

        status, git = self.collect_git_for(root)
        classification = status.classify_local_branches(
            git,
            self.github_evidence(prs=[{"number": 7, "head": "chore/open-pr"}]),
        )

        self.assertEqual(
            self.dispositions(classification),
            {
                "chore/merged": "merged",
                "chore/open-pr": "unmerged-with-pull-request",
                "chore/no-pr": "unmerged-without-pull-request",
            },
        )
        rows = {row["branch"]: row for row in classification["rows"]}
        self.assertEqual(rows["chore/open-pr"]["pullRequest"], 7)
        self.assertIsNone(rows["chore/no-pr"]["pullRequest"])
        self.assertFalse(classification["truncated"])

    def test_held_branch_carries_worktree_path_on_every_disposition(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "branch", "chore/merged-held")
        self.unmerged_branch(root, "chore/prless-held")
        merged_tree = root.parent / "wt-merged-held"
        prless_tree = root.parent / "wt-prless-held"
        self.run_git(root, "worktree", "add", str(merged_tree), "chore/merged-held")
        self.run_git(root, "worktree", "add", str(prless_tree), "chore/prless-held")

        status, git = self.collect_git_for(root)
        classification = status.classify_local_branches(git, self.github_evidence())
        rows = {row["branch"]: row for row in classification["rows"]}

        # Held-ness is an independent axis: both dispositions survive it.
        self.assertEqual(rows["chore/merged-held"]["disposition"], "merged")
        self.assertEqual(
            rows["chore/prless-held"]["disposition"],
            "unmerged-without-pull-request",
        )
        # git reports the resolved path; on macOS /var is a symlink to
        # /private/var, so compare resolved paths rather than the literal ones.
        self.assertEqual(
            Path(rows["chore/merged-held"]["heldByWorktree"]).resolve(),
            merged_tree.resolve(),
        )
        self.assertEqual(
            Path(rows["chore/prless-held"]["heldByWorktree"]).resolve(),
            prless_tree.resolve(),
        )

    def test_unavailable_pr_evidence_reports_unknown_not_prless(self) -> None:
        root = self.make_status_repo()
        self.unmerged_branch(root, "chore/unknown-pr")

        status, git = self.collect_git_for(root)
        classification = status.classify_local_branches(
            git,
            self.github_evidence(status_value="unavailable"),
        )

        self.assertEqual(
            self.dispositions(classification), {"chore/unknown-pr": "unknown"}
        )
        self.assertEqual(
            classification["evidence"]["pullRequests"], "github_unavailable"
        )

    def test_full_pr_page_reports_unknown_not_prless(self) -> None:
        root = self.make_status_repo()
        self.unmerged_branch(root, "chore/maybe-has-pr")

        status, git = self.collect_git_for(root)
        # Exactly MAX_ITEMS rows means the listing may have been cut off, so a
        # branch missing from it proves nothing.
        saturated = [
            {"number": index, "head": f"other/{index}"}
            for index in range(status.MAX_ITEMS)
        ]
        classification = status.classify_local_branches(
            git,
            self.github_evidence(prs=saturated),
        )

        self.assertEqual(
            self.dispositions(classification), {"chore/maybe-has-pr": "unknown"}
        )
        self.assertEqual(
            classification["evidence"]["pullRequests"], "pr_evidence_truncated"
        )

    def test_stale_default_branch_reports_unknown_not_prless(self) -> None:
        root = self.make_status_repo()
        self.unmerged_branch(root, "chore/after-stale")
        (root / "later.txt").write_text("later\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "local default advances")

        status, git = self.collect_git_for(root)
        self.assertIsNot(git["defaultMatchesRemote"], True)
        classification = status.classify_local_branches(git, self.github_evidence())

        self.assertEqual(
            self.dispositions(classification), {"chore/after-stale": "unknown"}
        )
        self.assertEqual(classification["evidence"]["defaultBranch"], "stale")

    def test_branch_advisories_stay_within_the_anomaly_size_budget(self) -> None:
        """Several externally controlled names per message, one shared budget.

        Branch names and worktree paths both come from outside, and one advisory
        names up to HUMAN_ITEM_LIMIT of each, so the assembled string is the
        place the bound has to hold.
        """

        status = self.load_status_module()
        rows = [
            {
                "branch": "chore/" + "b" * 114,
                "disposition": "unmerged-without-pull-request",
                "pullRequest": None,
                "heldByWorktree": "/tmp/" + "w" * 295,
            }
            for _ in range(status.HUMAN_ITEM_LIMIT + 3)
        ]
        anomalies = status.branch_classification_anomalies(
            {
                "status": "ok",
                "evidence": {"pullRequests": "available", "defaultBranch": "current"},
                "rows": rows,
                "truncated": False,
            }
        )

        self.assertEqual([code for code, _ in anomalies], ["local_branches_unmerged_without_pr"])
        for _, message in anomalies:
            self.assertLessEqual(len(message), 500)

    def test_an_open_pull_request_survives_stale_merge_evidence(self) -> None:
        """The evidence gates guard the absence claim, not this presence one.

        A stale default branch is the ordinary case between two fetches. An open
        pull request is direct evidence from another channel, so gating it on the
        reachability walk would report ``unknown`` for the most informative row
        in the inventory.
        """

        root = self.make_status_repo()
        self.unmerged_branch(root, "chore/open-pr")
        (root / "later.txt").write_text("later\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "local default advances")

        status, git = self.collect_git_for(root)
        self.assertIsNot(git["defaultMatchesRemote"], True)
        classification = status.classify_local_branches(
            git,
            self.github_evidence(prs=[{"number": 41, "head": "chore/open-pr"}]),
        )

        self.assertEqual(classification["evidence"]["defaultBranch"], "stale")
        self.assertEqual(
            self.dispositions(classification),
            {"chore/open-pr": "unmerged-with-pull-request"},
        )
        self.assertEqual(classification["rows"][0]["pullRequest"], 41)

    def test_advisory_and_strict_report_the_same_branch_findings(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "branch", "chore/merged-leftover")
        self.unmerged_branch(root, "chore/unmerged-leftover")

        advisory = self.run_status(root, "--json")
        strict = self.run_status(root, "--json", "--expect-clean")

        self.assertEqual(advisory.returncode, 0, advisory.stdout)
        self.assertEqual(strict.returncode, 0, strict.stdout)
        advisory_report = json.loads(advisory.stdout)
        strict_report = json.loads(strict.stdout)
        self.assertEqual(
            advisory_report["localBranchClassification"]["rows"],
            strict_report["localBranchClassification"]["rows"],
        )
        branch_codes = {
            "local_branches_unmerged_without_pr",
            "local_branches_pr_state_unknown",
        }
        self.assertEqual(
            {
                item["code"]
                for item in advisory_report["anomalyDetails"]
                if item["code"] in branch_codes
            },
            {
                item["code"]
                for item in strict_report["anomalyDetails"]
                if item["code"] in branch_codes
            },
        )
        # The reported shape the PRD objects to -- one surface saying nothing is
        # wrong while the other blocks on the same repository -- cannot occur:
        # neither surface blocks, and both carry the same entries.
        self.assertEqual(advisory_report["anomalies"], strict_report["anomalies"])

    def test_leftover_branches_alone_exit_zero_under_expect_clean(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "branch", "chore/leftover")
        self.unmerged_branch(root, "chore/stranded")

        result = self.run_status(root, "--json", "--expect-clean")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(
            [
                item["code"]
                for item in report["anomalyDetails"]
                if item["severity"] != "advisory"
            ],
            [],
        )
        self.assertNotIn("extra local branches remain", result.stdout)

    def test_dirty_tree_still_exits_nonzero_under_expect_clean(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "branch", "chore/leftover")
        (root / "README.md").write_text("dirty\n", encoding="utf-8")

        result = self.run_status(root, "--json", "--expect-clean")

        self.assertEqual(result.returncode, 1, result.stdout)
        report = json.loads(result.stdout)
        self.assertIn(
            "working_tree_dirty",
            [item["code"] for item in report["anomalyDetails"]],
        )

    def test_retained_source_branch_still_blocks(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "branch", "task/not-deleted")

        result = self.run_status(
            root,
            "--json",
            "--expect-clean",
            "--source-branch",
            "task/not-deleted",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        report = json.loads(result.stdout)
        blocking = {
            item["code"]
            for item in report["anomalyDetails"]
            if item["severity"] != "advisory"
        }
        self.assertIn("local_source_branch_retained", blocking)

    def test_retained_source_branch_held_elsewhere_is_advisory(self) -> None:
        root = self.make_status_repo()
        self.run_git(root, "branch", "task/held-source")
        holder = root.parent / "wt-held-source"
        self.run_git(root, "worktree", "add", str(holder), "task/held-source")

        result = self.run_status(
            root,
            "--json",
            "--expect-clean",
            "--source-branch",
            "task/held-source",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        held = [
            item
            for item in report["anomalyDetails"]
            if item["code"] == "local_source_branch_held_elsewhere"
        ]
        self.assertEqual(len(held), 1, report["anomalyDetails"])
        self.assertEqual(held[0]["severity"], "advisory")
        self.assertIn(holder.name, held[0]["message"])

    def test_anomaly_details_parallel_the_anomaly_list(self) -> None:
        root = self.make_status_repo()
        self.unmerged_branch(root, "chore/parallel")
        (root / "README.md").write_text("dirty\n", encoding="utf-8")

        result = self.run_status(root, "--json", "--expect-clean")

        report = json.loads(result.stdout)
        self.assertEqual(
            report["anomalies"],
            [item["message"] for item in report["anomalyDetails"]],
        )

    def test_blocking_prior_anomaly_code_still_exits_nonzero(self) -> None:
        root = self.make_status_repo()

        result = self.run_status(
            root,
            "--expect-clean",
            "--prior-anomaly",
            "local_branch_delete_failed",
            "could not delete the merged branch",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("could not delete the merged branch", result.stdout)

    def test_advisory_prior_anomaly_code_does_not_block(self) -> None:
        root = self.make_status_repo()

        result = self.run_status(
            root,
            "--json",
            "--expect-clean",
            "--prior-anomaly",
            "default_branch_held_elsewhere",
            "main is checked out in worktree /elsewhere",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        replayed = [
            item
            for item in report["anomalyDetails"]
            if item["code"] == "default_branch_held_elsewhere"
        ]
        self.assertEqual(len(replayed), 1, report["anomalyDetails"])
        self.assertEqual(replayed[0]["severity"], "advisory")

    def test_prior_anomaly_requires_a_code_and_message(self) -> None:
        root = self.make_status_repo()

        result = self.run_status(
            root,
            "--expect-clean",
            "--prior-anomaly",
            "message only",
        )

        self.assertEqual(result.returncode, 2, result.stdout)

    def test_worktree_empty_state_is_explicit(self) -> None:
        root = self.make_status_repo()

        machine = self.run_status(root, "--json")
        human = self.run_status(root)

        report = json.loads(machine.stdout)
        self.assertEqual(len(report["git"]["worktrees"]["rows"]), 1)
        self.assertEqual(report["git"]["branchesHeldElsewhere"], [])
        self.assertIn("- linked worktrees: none", human.stdout)

    def test_worktree_inventory_is_read_only(self) -> None:
        root = self.make_status_repo()
        state_root = root.parent / "worktree-recovery-state"
        self.seed_needs_review_stash(root, state_root)
        worktree = root.parent / "wt-ro"
        self.run_git(root, "worktree", "add", "-b", "ro-branch", str(worktree))
        env = {"SD_AI_COMMAND_PACK_STATE_HOME": str(state_root)}

        before_listing = self.git_output(root, "worktree", "list", "--porcelain")
        before_receipts = self.recovery_state_snapshot(state_root)
        before_index = self.worktree_index_bytes(worktree)
        self.assertNotEqual(before_receipts, {})

        machine = self.run_status(root, "--json", extra_env=env)
        human = self.run_status(root, extra_env=env)
        self.assertEqual(machine.returncode, 0, machine.stdout)
        self.assertEqual(human.returncode, 0, human.stdout)

        self.assertEqual(
            self.git_output(root, "worktree", "list", "--porcelain"), before_listing
        )
        self.assertEqual(self.recovery_state_snapshot(state_root), before_receipts)
        self.assertEqual(self.worktree_index_bytes(worktree), before_index)

    def test_worktree_inventory_leaves_recovery_classification_unchanged(self) -> None:
        root = self.make_status_repo()
        state_root = root.parent / "empty-worktree-recovery"
        state_root.mkdir()
        env = {"SD_AI_COMMAND_PACK_STATE_HOME": str(state_root)}

        before = self.run_status(root, "--json", extra_env=env)
        recovery_before = json.loads(before.stdout)["recoveryArtifacts"]

        self.run_git(root, "worktree", "add", "-b", "foreign-branch", str(root.parent / "wt-foreign"))
        after = self.run_status(root, "--json", extra_env=env)
        recovery_after = json.loads(after.stdout)["recoveryArtifacts"]

        self.assertEqual(recovery_after, recovery_before)
        self.assertEqual(recovery_after["total"], 0)

    def test_prunable_worktree_is_reported_and_not_pruned(self) -> None:
        root = self.make_status_repo()
        gone = root.parent / "wt-gone"
        self.run_git(root, "worktree", "add", "-b", "gone-branch", str(gone))
        shutil.rmtree(gone)

        result = self.run_status(root, "--json")

        rows = json.loads(result.stdout)["git"]["worktrees"]["rows"]
        gone_rows = [row for row in rows if row["branch"] == "gone-branch"]
        self.assertEqual(len(gone_rows), 1)
        self.assertTrue(gone_rows[0]["prunable"])
        self.assertIsNone(gone_rows[0]["clean"])
        self.assertIn(
            "refs/heads/gone-branch",
            self.git_output(root, "worktree", "list", "--porcelain"),
        )

    def test_dirty_linked_worktree_reports_clean_false(self) -> None:
        root = self.make_status_repo()
        worktree = root.parent / "wt-dirty"
        self.run_git(root, "worktree", "add", "-b", "dirty-branch", str(worktree))
        (worktree / "scratch.txt").write_text("dirty\n", encoding="utf-8")

        result = self.run_status(root, "--json")

        rows = json.loads(result.stdout)["git"]["worktrees"]["rows"]
        by_branch = {row["branch"]: row for row in rows}
        self.assertIs(by_branch["dirty-branch"]["clean"], False)
        self.assertIs(by_branch["main"]["clean"], True)

    def test_unavailable_worktree_inventory_is_explicit(self) -> None:
        root = self.make_status_repo()
        real_git = shutil.which("git")
        assert real_git is not None
        stub_bin = root.parent / "stub-bin"
        stub_bin.mkdir()
        stub = stub_bin / "git"
        stub.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "worktree" ]; then exit 1; fi\n'
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
        env = {"PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"}

        machine = self.run_status(root, "--json", extra_env=env)
        human = self.run_status(root, extra_env=env)

        self.assertEqual(machine.returncode, 0, machine.stdout)
        report = json.loads(machine.stdout)
        self.assertEqual(report["git"]["worktrees"], {"status": "unavailable"})
        self.assertIsNone(report["git"]["branchesHeldElsewhere"])
        self.assertIn("- worktrees: unavailable", human.stdout)

    def test_worktree_porcelain_parser_keeps_raw_adversarial_values(self) -> None:
        status = self.load_status_module()
        newline_path = "/tmp/evil\nname"
        long_path = "/tmp/" + "a" * 400
        blob = (
            f"worktree {newline_path}\0HEAD {'1' * 40}\0branch refs/heads/tricky\0\0"
            f"worktree {long_path}\0HEAD {'2' * 40}\0detached\0\0"
            f"worktree /tmp/locked\0HEAD {'3' * 40}\0locked gone away\0"
            "futureattr value\0\0"
        )

        rows = status.parse_worktree_porcelain(blob)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["path"], newline_path)
        self.assertEqual(rows[0]["branch"], "tricky")
        self.assertEqual(rows[1]["path"], long_path)
        self.assertTrue(rows[1]["detached"])
        self.assertTrue(rows[2]["locked"])
        self.assertEqual(rows[2]["reason"], "gone away")

    def test_long_path_worktree_is_probed_and_display_bounded(self) -> None:
        root = self.make_status_repo()
        deep = root.parent
        while len(str(deep)) < 320:
            deep = deep / ("x" * 40)
        deep.parent.mkdir(parents=True, exist_ok=True)
        self.run_git(root, "worktree", "add", "-b", "long-branch", str(deep))

        result = self.run_status(root, "--json")

        rows = json.loads(result.stdout)["git"]["worktrees"]["rows"]
        by_branch = {row["branch"]: row for row in rows}
        long_row = by_branch["long-branch"]
        self.assertIs(long_row["clean"], True)
        self.assertLessEqual(len(long_row["path"]), 300)

    def test_status_from_linked_worktree_marks_linked_row_current(self) -> None:
        root = self.make_status_repo()
        worktree = root.parent / "wt-linked"
        self.run_git(root, "worktree", "add", "-b", "linked-branch", str(worktree))

        result = self.run_status(worktree, "--json")

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        rows = report["git"]["worktrees"]["rows"]
        porcelain_paths = [
            line.removeprefix("worktree ")
            for line in self.git_output(
                worktree, "worktree", "list", "--porcelain"
            ).splitlines()
            if line.startswith("worktree ")
        ]
        self.assertEqual([row["path"] for row in rows], porcelain_paths)
        current = [row for row in rows if row["current"]]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["branch"], "linked-branch")
        self.assertFalse(rows[0]["current"])
        self.assertIn("main", report["git"]["branchesHeldElsewhere"])

    def test_stale_worktree_path_reused_by_stranger_is_not_probed(self) -> None:
        root = self.make_status_repo()
        reused = root.parent / "wt-reused"
        self.run_git(root, "worktree", "add", "-b", "reused-branch", str(reused))
        shutil.rmtree(reused)
        reused.mkdir()
        self.run_git(reused, "init")
        (reused / "stranger.txt").write_text("dirty stranger\n", encoding="utf-8")

        result = self.run_status(root, "--json")

        rows = json.loads(result.stdout)["git"]["worktrees"]["rows"]
        reused_rows = [row for row in rows if row["branch"] == "reused-branch"]
        self.assertEqual(len(reused_rows), 1)
        self.assertIsNone(reused_rows[0]["clean"])

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
        self.assertIn(
            ("git_stash_unavailable", "blocking", "git stash inventory is unavailable"),
            anomalies,
        )

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
            "local_branch_delete_failed",
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
        self.assertEqual(
            [item["selectionId"] for item in report["followUps"]],
            ["F-1", "F-2"],
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status.render_fleet(report)
        rendered = output.getvalue()
        self.assertLess(rendered.index("fast-stale"), rendered.index("slow-current"))
        self.assertIn(f"Target pack: {PACK_VERSION}", rendered)
        self.assertIn("slow-current: clean; main; cached:synchronized; pack", rendered)
        self.assertIn("stashes 1", rendered)
        self.assertIn("PRs unavailable", rendered)
        self.assertIn("==> Follow-ups", rendered)
        self.assertIn("F-1 [action]", rendered)

    def test_fleet_collection_isolates_a_raising_consumer(self) -> None:
        status = self.load_status_module()
        alpha = self.make_status_repo(pack_version=PACK_VERSION)
        raiser = self.make_status_repo(pack_version=PACK_VERSION)
        omega = self.make_status_repo(pack_version=PACK_VERSION)
        manifest = alpha.parent / "fleet.json"
        manifest.write_text(
            json.dumps(
                fleet_manifest(
                    [
                        {
                            "name": "omega",
                            "github": "example/omega",
                            "pathHint": str(omega),
                            "platforms": ["claude"],
                            "rolloutPriority": 90,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["bash", "check.sh"]],
                        },
                        {
                            "name": "raiser",
                            "github": "example/raiser",
                            "pathHint": str(raiser),
                            "platforms": ["claude"],
                            "rolloutPriority": 50,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["bash", "check.sh"]],
                        },
                        {
                            "name": "alpha",
                            "github": "example/alpha",
                            "pathHint": str(alpha),
                            "platforms": ["claude"],
                            "rolloutPriority": 10,
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

        real_collect_local = status.collect_local

        def flaky_collect_local(path, **kwargs):
            if kwargs.get("github_repo") == "example/raiser":
                raise RuntimeError("simulated collect_local failure")
            return real_collect_local(path, **kwargs)

        with mock.patch.object(status, "collect_local", flaky_collect_local):
            report = status.collect_fleet(
                PACK_ROOT,
                fleet_path=manifest,
                network=False,
                refs_refreshed=False,
            )

        rows = report["repositories"]
        # Registry rollout order (ascending rolloutPriority) is preserved even
        # though the middle consumer raised.
        self.assertEqual(
            [row["name"] for row in rows], ["alpha", "raiser", "omega"]
        )
        by_name = {row["name"]: row for row in rows}
        # The raising consumer is rendered as a degraded row and does not abort
        # the run; the other two consumers still report.
        self.assertEqual(by_name["raiser"]["status"], "unavailable")
        self.assertIsNone(by_name["raiser"]["report"])
        self.assertEqual(by_name["alpha"]["status"], "available")
        self.assertIsNotNone(by_name["alpha"]["report"])
        self.assertEqual(by_name["omega"]["status"], "available")
        self.assertIsNotNone(by_name["omega"]["report"])

    def fleet_consumer_entry(
        self,
        name: str,
        path: Path,
        *,
        priority: int,
        **extra: object,
    ) -> dict[str, object]:
        entry: dict[str, object] = {
            "name": name,
            "github": f"example/{name}",
            "pathHint": str(path),
            "platforms": ["claude"],
            "rolloutPriority": priority,
            "candidateTimeoutSeconds": 60,
            "candidatePrepare": [],
            "candidateChecks": [["bash", "check.sh"]],
        }
        entry.update(extra)
        return entry

    def write_fleet_manifest(self, path: Path, entries: list[dict[str, object]]) -> Path:
        path.write_text(json.dumps(fleet_manifest(entries)) + "\n", encoding="utf-8")
        return path

    def machine_scope_fixture(
        self,
        *,
        state: str = "installed",
        pack_version: str | None = "9.9.9",
        plugin_version: str = "9.9.9",
        comparison: str = "current",
    ) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "state": state,
            "packVersion": pack_version,
            "receiptPath": "/scratch/machine-receipt.json",
            "detail": None,
            "pluginId": "sd@sd-ai-command-pack",
            "pluginVersion": plugin_version,
            "pluginDetail": None,
            "comparison": comparison,
        }

    def collect_fleet_with_machine(self, status, manifest: Path, scope: object):
        """Collect a fleet against a fixed machine inventory.

        The machine probe is stubbed rather than staged on disk so each test
        states the machine half it is asserting about, and so the once-per-run
        property can be asserted by call count.
        """
        probe = mock.Mock(return_value=scope)
        with mock.patch.object(status, "collect_machine_scope", probe):
            report = status.collect_fleet(
                PACK_ROOT,
                fleet_path=manifest,
                network=False,
                refs_refreshed=False,
            )
        return report, probe

    def test_local_machine_scope_regression_reports_both_halves(self) -> None:
        # PRD requirement 1: local mode reports the plugin and receipt versions,
        # and labels an absent source `unavailable` rather than empty-healthy.
        status = self.load_status_module()
        root = self.make_status_repo()

        home, state_home = self.machine_scratch()
        self.write_machine_receipt(state_home, pack_version="9.9.9")
        with self.stub_claude(
            status, [{"id": status.MACHINE_PLUGIN_ID, "version": "9.9.9"}]
        ):
            installed = self.machine_section(status, root, home, state_home)
        self.assertEqual(installed["packVersion"], "9.9.9")
        self.assertEqual(installed["pluginVersion"], "9.9.9")
        self.assertEqual(installed["comparison"], "current")

        home, state_home = self.machine_scratch()
        with mock.patch.object(status.shutil, "which", return_value=None):
            absent = self.machine_section(status, root, home, state_home)
        self.assertEqual(absent["pluginVersion"], "unavailable")
        self.assertTrue(absent["pluginDetail"])
        self.assertIsNone(absent["packVersion"])
        # An unreadable half must never present as agreement.
        self.assertEqual(absent["comparison"], "unknown")

    def test_status_pin_path_default_matches_the_fleet_library(self) -> None:
        # The status fallback exists only for a FleetConsumer that predates
        # schema 5; a drift between the two constants would silently read a
        # different file than the registry documents.
        status = self.load_status_module()
        fleet = self.load_fleet_lib()
        self.assertEqual(
            status.DEFAULT_CONSUMER_PIN_PATH, fleet.DEFAULT_FLEET_PIN_PATH
        )

    def test_fleet_registry_rejects_bad_mode_and_escaping_pin_path(self) -> None:
        status = self.load_status_module()
        fleet = self.load_fleet_lib()
        root = self.make_status_repo()
        default = fleet.DEFAULT_FLEET_PIN_PATH
        cases = (
            ({"mode": "thick"}, "mode must be one of"),
            # Wrong types, not just wrong values: JSON can carry a number or a
            # bool where the registry documents a string.
            ({"mode": 5}, "mode must be one of"),
            ({"mode": True}, "mode must be one of"),
            ({"pinPath": 5}, "pinPath must be a non-empty string"),
            ({"pinPath": ["a"]}, "pinPath must be a non-empty string"),
            ({"pinPath": "/etc/passwd"}, "pinPath must be a relative path"),
            ({"pinPath": "../escape.json"}, "pinPath must be a relative path"),
            ({"pinPath": "C:\\escape.json"}, "pinPath must be a relative path"),
            ({"pinPath": "   "}, "pinPath must be a non-empty string"),
        )
        for index, (override, expected) in enumerate(cases):
            with self.subTest(override=override):
                manifest = self.write_fleet_manifest(
                    root.parent / f"fleet-bad-{index}.json",
                    [
                        self.fleet_consumer_entry(
                            "alpha", root, priority=10, **override
                        )
                    ],
                )
                with self.assertRaisesRegex(fleet.FleetConfigError, expected) as caught:
                    fleet.load_fleet_consumers(manifest)
                self.assertIn("alpha", str(caught.exception))
                # The same failure reaches status as a usable configuration error.
                with self.assertRaisesRegex(ValueError, expected):
                    status.load_fleet(PACK_ROOT, manifest)

        # Both fields are optional: omitting them reproduces schema-4 behaviour.
        manifest = self.write_fleet_manifest(
            root.parent / "fleet-default.json",
            [self.fleet_consumer_entry("alpha", root, priority=10)],
        )
        consumer = fleet.load_fleet_consumers(manifest)[0]
        self.assertEqual(consumer.mode, "fat")
        self.assertEqual(consumer.pin_path, fleet.DEFAULT_FLEET_PIN_PATH)

        # Surrounding whitespace is stripped rather than carried into the read:
        # an unstripped value passes validation and then names a file that does
        # not exist, reporting a healthy consumer as `absent`.
        padded = self.write_fleet_manifest(
            root.parent / "fleet-padded.json",
            [
                self.fleet_consumer_entry(
                    "alpha", root, priority=10, pinPath=f"  {default}\t"
                )
            ],
        )
        self.assertEqual(fleet.load_fleet_consumers(padded)[0].pin_path, default)

    def test_consumer_pin_reader_classifies_every_state(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        default = status.DEFAULT_CONSUMER_PIN_PATH

        present = status.read_consumer_pin(root, default)
        self.assertEqual(present["state"], "present")
        self.assertEqual(present["version"], PACK_VERSION)
        self.assertEqual(present["source"], default)

        absent = status.read_consumer_pin(root, "nowhere/pin.json")
        self.assertEqual(absent["state"], "absent")
        self.assertIsNone(absent["version"])
        self.assertIn("does not exist", absent["detail"])

        broken = root / "broken-pin.json"
        broken.write_text("{not json\n", encoding="utf-8")
        result = status.read_consumer_pin(root, "broken-pin.json")
        self.assertEqual(result["state"], "unreadable")
        self.assertIsNone(result["version"])

        versionless = root / "versionless-pin.json"
        versionless.write_text(json.dumps({"pack": "sd"}) + "\n", encoding="utf-8")
        result = status.read_consumer_pin(root, "versionless-pin.json")
        self.assertEqual(result["state"], "unreadable")
        self.assertIn("no version string", result["detail"])

        # Load-time validation cannot see this: the registry path is relative
        # and contains no "..", but the symlink leaves the checkout.
        outside = root.parent / "outside-pin.json"
        outside.write_text(json.dumps({"version": "6.6.6"}) + "\n", encoding="utf-8")
        (root / "escaping-pin.json").symlink_to(outside)
        result = status.read_consumer_pin(root, "escaping-pin.json")
        self.assertEqual(result["state"], "unreadable")
        self.assertIsNone(result["version"])

    def test_fleet_all_fat_registry_ignores_machine_state(self) -> None:
        # AC3 and the fleet-level gate together: with no thin consumer the
        # machine inventory cannot change a single row, so a schema-5 registry
        # naming no mode reports exactly as the schema-4 registry it replaces.
        status = self.load_status_module()
        current = self.make_status_repo(pack_version=PACK_VERSION)
        stale = self.make_status_repo(pack_version="0.18.0")
        manifest = self.write_fleet_manifest(
            current.parent / "fleet.json",
            [
                self.fleet_consumer_entry("current", current, priority=10),
                self.fleet_consumer_entry("stale", stale, priority=20),
            ],
        )

        healthy, _ = self.collect_fleet_with_machine(
            status, manifest, self.machine_scope_fixture()
        )
        broken, _ = self.collect_fleet_with_machine(
            status,
            manifest,
            self.machine_scope_fixture(
                state="none",
                pack_version=None,
                plugin_version="unavailable",
                comparison="unknown",
            ),
        )

        def comparable(report):
            rows = [
                {key: value for key, value in row.items() if key not in {"pin", "installMode"}}
                for row in report["repositories"]
            ]
            return rows, report["nextSteps"], report["followUps"]

        self.assertEqual(comparable(healthy), comparable(broken))
        for row in healthy["repositories"]:
            self.assertEqual(row["installMode"], "fat")
            self.assertIsNone(row["pin"])
        # The inventory itself is still published; only the rows are gated.
        self.assertIsInstance(healthy["machineScope"], dict)
        self.assertTrue(
            any("Refresh stale SD pack installations" in step for step in healthy["nextSteps"])
        )
        for step in healthy["nextSteps"]:
            self.assertNotIn("machine SD install", step)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status.render_fleet(healthy)
        rendered = output.getvalue()
        self.assertNotIn("Machine scope:", rendered)
        self.assertIn("stale: clean; main; cached:synchronized; pack 0.18.0", rendered)

    def test_fleet_thin_consumer_reports_pin_and_skew(self) -> None:
        status = self.load_status_module()
        fat = self.make_status_repo(pack_version="0.18.0")
        thin = self.make_status_repo(pack_version="0.30.0")
        manifest = self.write_fleet_manifest(
            fat.parent / "fleet.json",
            [
                self.fleet_consumer_entry("fatty", fat, priority=10),
                self.fleet_consumer_entry("thinny", thin, priority=20, mode="thin"),
            ],
        )

        report, _ = self.collect_fleet_with_machine(
            status,
            manifest,
            self.machine_scope_fixture(pack_version="0.31.0", plugin_version="0.31.0"),
        )

        rows = {row["name"]: row for row in report["repositories"]}
        self.assertEqual(rows["fatty"]["installMode"], "fat")
        self.assertIsNone(rows["fatty"]["pin"])
        self.assertEqual(rows["thinny"]["installMode"], "thin")
        self.assertEqual(rows["thinny"]["pin"]["state"], "present")
        self.assertEqual(rows["thinny"]["pin"]["version"], "0.30.0")

        steps = report["nextSteps"]
        # The thin consumer's pin lags the machine install, and the machine
        # install lags the target: two distinct skew rows, neither a tree diff.
        self.assertTrue(any("thinny" in step and "0.31.0" in step for step in steps))
        self.assertTrue(any("Update the machine SD install (0.31.0)" in step for step in steps))
        stale_rows = [step for step in steps if "Refresh stale SD pack installations" in step]
        self.assertEqual(len(stale_rows), 1)
        self.assertIn("fatty", stale_rows[0])
        self.assertNotIn("thinny", stale_rows[0])
        self.assertTrue(
            any("thinny" in item["summary"] for item in report["followUps"])
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status.render_fleet(report)
        rendered = output.getvalue()
        self.assertIn("Machine scope: installed 0.31.0", rendered)
        self.assertIn("thinny: clean; main; cached:synchronized; pin 0.30.0", rendered)
        self.assertIn("fatty: clean; main; cached:synchronized; pack 0.18.0", rendered)
        # Both consumers need attention, by two different measures.
        self.assertIn("2 need attention", rendered)

    def test_fleet_thin_pin_states_and_unavailable_machine(self) -> None:
        status = self.load_status_module()
        thin = self.make_status_repo(pack_version=PACK_VERSION)
        (thin / ".sd-ai-command-pack/provenance.json").unlink()
        manifest = self.write_fleet_manifest(
            thin.parent / "fleet.json",
            [self.fleet_consumer_entry("thinny", thin, priority=10, mode="thin")],
        )

        report, _ = self.collect_fleet_with_machine(
            status,
            manifest,
            self.machine_scope_fixture(
                state="none",
                pack_version=None,
                plugin_version="unavailable",
                comparison="unknown",
            ),
        )

        row = report["repositories"][0]
        self.assertEqual(row["pin"]["state"], "absent")
        steps = report["nextSteps"]
        self.assertTrue(any("Repair missing or unreadable thin consumer pins" in s for s in steps))
        # An unavailable machine inventory is reported as unavailable, never as
        # agreement with whatever the consumer pinned.
        self.assertTrue(any("inventory is unavailable" in step for step in steps))
        self.assertTrue(any("Install or repair the machine SD install" in s for s in steps))
        summaries = [item["summary"] for item in report["followUps"]]
        self.assertTrue(any("inventory is unavailable" in summary for summary in summaries))

    def test_fleet_reports_plugin_versus_receipt_divergence(self) -> None:
        status = self.load_status_module()
        thin = self.make_status_repo(pack_version=PACK_VERSION)
        manifest = self.write_fleet_manifest(
            thin.parent / "fleet.json",
            [self.fleet_consumer_entry("thinny", thin, priority=10, mode="thin")],
        )

        report, _ = self.collect_fleet_with_machine(
            status,
            manifest,
            self.machine_scope_fixture(
                pack_version=PACK_VERSION,
                plugin_version="0.1.0",
                comparison="skew",
            ),
        )

        steps = report["nextSteps"]
        divergence = [step for step in steps if step.startswith("Reconcile the SD plugin")]
        self.assertEqual(len(divergence), 1)
        self.assertIn("0.1.0", divergence[0])
        self.assertIn(PACK_VERSION, divergence[0])
        # The pin agrees with the machine receipt, so this row is the plugin's
        # own divergence and not a restatement of pin skew.
        self.assertFalse(any("Reconcile thin consumer pins" in step for step in steps))

    def test_fleet_skew_rows_survive_human_truncation(self) -> None:
        status = self.load_status_module()
        skewed = self.make_status_repo(pack_version="0.1.0")
        broken = self.make_status_repo(pack_version=PACK_VERSION)
        (broken / ".sd-ai-command-pack/provenance.json").unlink()
        dirty = self.make_status_repo(pack_version=PACK_VERSION)
        (dirty / "README.md").write_text("uncommitted\n", encoding="utf-8")
        stale = self.make_status_repo(pack_version="0.18.0")
        manifest = self.write_fleet_manifest(
            skewed.parent / "fleet.json",
            [
                self.fleet_consumer_entry("skewed", skewed, priority=10, mode="thin"),
                self.fleet_consumer_entry("broken", broken, priority=20, mode="thin"),
                self.fleet_consumer_entry("dirty", dirty, priority=30),
                self.fleet_consumer_entry("stale", stale, priority=40),
                self.fleet_consumer_entry(
                    "gone", skewed.parent / "gone", priority=50
                ),
            ],
        )

        report, _ = self.collect_fleet_with_machine(
            status,
            manifest,
            self.machine_scope_fixture(
                pack_version="0.2.0", plugin_version="0.3.0", comparison="skew"
            ),
        )

        # Four skew rows and three advisory rows: more than the human list can
        # hold, which is exactly the case that used to lose a skew row.
        self.assertEqual(len(report["nextSteps"]), status.HUMAN_ITEM_LIMIT)
        self.assertEqual(len(report["followUps"]), 7)
        skew_prefixes = (
            "Repair missing or unreadable thin consumer pins",
            "Reconcile thin consumer pins",
            "Update the machine SD install",
            "Reconcile the SD plugin",
        )
        for prefix in skew_prefixes:
            with self.subTest(row=prefix):
                # Every skew row survives truncation in the human list...
                self.assertTrue(
                    any(step.startswith(prefix) for step in report["nextSteps"])
                )
        # ...because the four of them are ranked ahead of every advisory row.
        self.assertTrue(
            all(
                step.startswith(skew_prefixes)
                for step in report["nextSteps"][: len(skew_prefixes)]
            ),
            report["nextSteps"],
        )
        # Follow-ups still carry the advisory rows truncation dropped.
        summaries = [item["summary"] for item in report["followUps"]]
        for advisory in (
            "Resolve uncommitted fleet work",
            "Refresh stale SD pack installations",
        ):
            with self.subTest(row=advisory):
                self.assertTrue(any(s.startswith(advisory) for s in summaries))
                self.assertFalse(
                    any(step.startswith(advisory) for step in report["nextSteps"])
                )

    def test_fleet_collects_machine_scope_once_per_run(self) -> None:
        status = self.load_status_module()
        repos = [self.make_status_repo(pack_version=PACK_VERSION) for _ in range(3)]
        manifest = self.write_fleet_manifest(
            repos[0].parent / "fleet.json",
            [
                self.fleet_consumer_entry(f"member{index}", repo, priority=10 + index)
                for index, repo in enumerate(repos)
            ],
        )

        report, probe = self.collect_fleet_with_machine(
            status, manifest, self.machine_scope_fixture()
        )

        # One machine probe for the whole run, not one per consumer: each
        # consumer row keeps include_machine_scope=False.
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(len(report["repositories"]), 3)
        for row in report["repositories"]:
            self.assertIsNone(row["report"]["machineScope"])

    # ------------------------------------------------------- release target

    def release_listing(self, *tags: str) -> str:
        return "".join(f"{'a' * 40}\trefs/tags/{tag}\n" for tag in tags)

    def test_release_target_is_disabled_without_network(self) -> None:
        # PRD criterion 2: --no-network must label the target, not omit it, and
        # must not reach the network at all. The call count is the real
        # assertion; the status alone would pass a lazy implementation.
        status = self.load_status_module()
        with mock.patch.object(status, "run_command") as run_command:
            result = status.collect_release_target(PACK_ROOT, network=False)
        self.assertEqual(run_command.call_count, 0)
        self.assertEqual(result["status"], "disabled")
        self.assertIsNone(result["version"])

    def test_release_target_without_an_origin_is_not_configured(self) -> None:
        status = self.load_status_module()
        with mock.patch.object(
            status,
            "run_command",
            side_effect=[status.CommandResult(2, "")],
        ):
            result = status.collect_release_target(PACK_ROOT, network=True)
        self.assertEqual(result["status"], "not-configured")
        self.assertIsNone(result["version"])

    def test_release_target_is_unavailable_when_the_remote_refuses(self) -> None:
        status = self.load_status_module()
        with mock.patch.object(
            status,
            "run_command",
            side_effect=[
                status.CommandResult(0, "git@github.com:o/r.git\n"),
                status.CommandResult(128, ""),
            ],
        ):
            result = status.collect_release_target(PACK_ROOT, network=True)
        self.assertEqual(result["status"], "unavailable")

    def test_release_target_ignores_refs_that_are_not_release_tags(self) -> None:
        # A remote with only pre-release or hand-made tags has published
        # nothing this comparison can use. It reports that, rather than
        # coercing "v1.0-rc1" into a version.
        status = self.load_status_module()
        with mock.patch.object(
            status,
            "run_command",
            side_effect=[
                status.CommandResult(0, "git@github.com:o/r.git\n"),
                status.CommandResult(
                    0, self.release_listing("v1.0-rc1", "nightly", "1.2.3")
                ),
            ],
        ):
            result = status.collect_release_target(PACK_ROOT, network=True)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["version"])

    def test_release_target_orders_by_version_not_by_tag_string(self) -> None:
        # The defect a string max() ships: "v0.9.2" sorts above "v0.71.8", so
        # the report would name a years-old version as newest and look
        # perfectly well-formed doing it. Every other case here passes under
        # the broken implementation.
        status = self.load_status_module()
        with mock.patch.object(
            status,
            "run_command",
            side_effect=[
                status.CommandResult(0, "git@github.com:o/r.git\n"),
                status.CommandResult(
                    0, self.release_listing("v0.8.6", "v0.9.2", "v0.71.8", "v0.10.0")
                ),
            ],
        ):
            result = status.collect_release_target(PACK_ROOT, network=True)
        self.assertEqual(result["version"], "0.71.8")
        self.assertEqual(result["tag"], "v0.71.8")

    def test_release_target_reports_version_and_tag(self) -> None:
        status = self.load_status_module()
        with mock.patch.object(
            status,
            "run_command",
            side_effect=[
                status.CommandResult(0, "git@github.com:o/r.git\n"),
                status.CommandResult(0, self.release_listing("v0.71.8")),
            ],
        ):
            result = status.collect_release_target(PACK_ROOT, network=True)
        self.assertEqual(
            result, {"status": "available", "version": "0.71.8", "tag": "v0.71.8"}
        )

    def test_release_target_issues_only_read_only_commands(self) -> None:
        # PRD criterion 3: status stays read-only. Both commands used here are,
        # but only an argv assertion stops a later edit from adding a fetch.
        status = self.load_status_module()
        with mock.patch.object(
            status,
            "run_command",
            side_effect=[
                status.CommandResult(0, "git@github.com:o/r.git\n"),
                status.CommandResult(0, self.release_listing("v0.71.8")),
            ],
        ) as run_command:
            status.collect_release_target(PACK_ROOT, network=True)
        self.assertEqual(
            [call.args[0] for call in run_command.call_args_list],
            [
                ["git", "remote", "get-url", "origin"],
                ["git", "ls-remote", "--tags", "--refs", "origin"],
            ],
        )

    def release_records(self, status, release: object) -> list[str]:
        return [
            record["summary"]
            for record in status.fleet_step_records([], "0.71.8", release_target=release)
            if "published release" in record["summary"]
        ]

    def test_release_skew_emits_exactly_one_fleet_record(self) -> None:
        # One record, not one per consumer: the checkout is a property of the
        # operator, and asserting the count is what catches a duplicate.
        status = self.load_status_module()
        summaries = self.release_records(
            status,
            {"status": "available", "version": "0.72.0", "tag": "v0.72.0"},
        )
        self.assertEqual(len(summaries), 1)
        self.assertIn("0.71.8", summaries[0])
        self.assertIn("0.72.0", summaries[0])
        # "differs from", never "is behind": an unreleased working copy is
        # ahead, and that is one of the two cases this exists to surface.
        self.assertNotIn("behind", summaries[0])

    def test_release_matching_the_checkout_emits_no_record(self) -> None:
        status = self.load_status_module()
        self.assertEqual(
            self.release_records(
                status,
                {"status": "available", "version": "0.71.8", "tag": "v0.71.8"},
            ),
            [],
        )

    def test_unresolved_release_target_emits_no_record(self) -> None:
        status = self.load_status_module()
        for state in ("disabled", "not-configured", "unavailable"):
            with self.subTest(state=state):
                self.assertEqual(
                    self.release_records(
                        status, {"status": state, "version": None, "tag": None}
                    ),
                    [],
                )
        self.assertEqual(self.release_records(status, None), [])

    def test_fleet_report_carries_a_labeled_release_target(self) -> None:
        # PRD criterion 2's "complete report" clause: with the lookup
        # suppressed, the key is present and labeled, and every pre-existing
        # top-level key survives.
        status = self.load_status_module()
        repo = self.make_status_repo(pack_version=PACK_VERSION)
        manifest = self.write_fleet_manifest(
            repo.parent / "fleet.json",
            [self.fleet_consumer_entry("member0", repo, priority=10)],
        )

        report, _ = self.collect_fleet_with_machine(
            status, manifest, self.machine_scope_fixture()
        )

        self.assertEqual(
            report["releaseTarget"],
            {"status": "disabled", "version": None, "tag": None},
        )
        for key in (
            "schemaVersion",
            "mode",
            "targetPackVersion",
            "machineScope",
            "refsFreshness",
            "configuration",
            "repositories",
            "followUps",
            "nextSteps",
        ):
            self.assertIn(key, report)

    def test_machine_scope_api_loads_the_engine_beside_the_script(self) -> None:
        status = self.load_status_module()
        # The installed arrangement: scripts/ beside installer/. The canonical
        # templates/scripts/ copy has no sibling package, which is the absence
        # covered by the next test.
        installed_status = PACK_ROOT / "scripts/sd-ai-command-pack-status.py"
        root_path = str(PACK_ROOT.resolve())
        original_path = [entry for entry in status.sys.path if entry != root_path]

        with (
            mock.patch.object(status, "__file__", str(installed_status)),
            mock.patch.object(status.sys, "path", original_path.copy()),
        ):
            machinescope, rung, root, refusals = status.machine_scope_api()

            self.assertEqual(status.sys.path, original_path)
        self.assertTrue(hasattr(machinescope, "receipt_path"))
        self.assertTrue(hasattr(machinescope, "status"))
        # The rung matters, not merely that something resolved: a ladder that
        # quietly answered from PATH here would still pass a success-only
        # assertion while loading a different copy than it used to.
        self.assertEqual(rung, "adjacent")
        self.assertEqual(root, PACK_ROOT.resolve())
        self.assertEqual(refusals, [])

    def machine_install_arrangement(self, tmp: Path) -> Path:
        """A machine install: `bin/` holding a real copy, with no sibling package.

        A real file, deliberately, not a symlink: `Path.resolve()` follows a
        symlink back into the plugin root, so a symlinked fixture would resolve
        through the script-adjacent rung and prove nothing about this defect.
        """
        binary_dir = tmp / "bin"
        binary_dir.mkdir(parents=True)
        collector = binary_dir / "sd-ai-command-pack-status.py"
        collector.write_text("# machine payload copy\n", encoding="utf-8")
        self.assertFalse((tmp / "installer").exists())
        return collector

    def test_machine_scope_api_resolves_a_trusted_root_from_path(self) -> None:
        """Issue #496: a machine install has no sibling `installer/` to find.

        `parent.parent` of `~/.agents/bin/` is `~/.agents`, which ships no
        installer package in any arrangement, so the documented thin-consumer
        path could never resolve the engine. The pack checkout on `PATH` is a
        root that does carry it.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            collector = self.machine_install_arrangement(Path(raw))
            environ = {"PATH": str(PACK_ROOT / "scripts")}
            root_path = str(PACK_ROOT.resolve())
            original_path = [entry for entry in status.sys.path if entry != root_path]

            with (
                mock.patch.object(status, "__file__", str(collector)),
                mock.patch.object(status.sys, "path", original_path.copy()),
            ):
                machinescope, rung, root, _refusals = status.machine_scope_api(
                    environ=environ
                )

                self.assertEqual(status.sys.path, original_path)

        self.assertTrue(hasattr(machinescope, "receipt_path"))
        self.assertTrue(hasattr(machinescope, "status"))
        self.assertEqual(rung, "path")
        self.assertEqual(root, PACK_ROOT.resolve())

    def engine_api_result(self, engine: object) -> tuple[object, str, Path, list[dict[str, str]]]:
        """The `machine_scope_api()` 4-tuple around a stub engine.

        Stated once so a later change to the tuple's shape lands in one place
        rather than in every caller that only cares about the engine.
        """
        return (engine, "adjacent", PACK_ROOT.resolve(), [])

    def decoy_engine_root(self, root: Path, *, identity: str | None) -> Path:
        """A root that holds the file the loader wants, with chosen identity.

        `identity` selects the marker spelling: `manifest` for a checkout,
        `plugin` for the plugin cache arrangement, `None` for a bare decoy that
        carries the engine and nothing that vouches for it.
        """
        package = root / "installer"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "machinescope.py").write_text(
            "STATUS_SCHEMA_VERSION = 1\n"
            "def receipt_path(*a, **k):\n    return None\n"
            "def status(**k):\n    return {}\n",
            encoding="utf-8",
        )
        if identity == "manifest":
            (root / "manifest.json").write_text(
                json.dumps({"name": "sd-ai-command-pack"}), encoding="utf-8"
            )
        elif identity == "plugin":
            marker = root / ".claude-plugin"
            marker.mkdir()
            (marker / "plugin.json").write_text(
                json.dumps({"name": "sd", "version": "0.0.1"}), encoding="utf-8"
            )
        binary_dir = root / "bin"
        binary_dir.mkdir()
        (binary_dir / "sd-ai-command-pack-toolchain.sh").write_text(
            "#!/bin/sh\n", encoding="utf-8"
        )
        return binary_dir

    def test_machine_engine_refusal_accepts_plugin_only_identity(self) -> None:
        """The plugin cache root carries no manifest.json -- only plugin.json.

        Keying identity on manifest.json alone would reject the one
        arrangement the PATH rung exists to reach, shipping a fix that fixes
        nothing. Both spellings are asserted so that cannot regress silently.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            for identity in ("manifest", "plugin"):
                root = Path(raw) / identity
                self.decoy_engine_root(root, identity=identity)
                self.assertIsNone(
                    status.machine_engine_refusal(root), f"{identity} identity refused"
                )

    def test_machine_engine_refusal_rejects_an_unvouched_root(self) -> None:
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "decoy"
            self.decoy_engine_root(root, identity=None)
            refusal = status.machine_engine_refusal(root)
        self.assertIsNotNone(refusal)
        self.assertIn("no pack identity", refusal)

    def test_machine_engine_refusal_rejects_a_world_writable_root(self) -> None:
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "open"
            self.decoy_engine_root(root, identity="manifest")
            engine = root / "installer" / "machinescope.py"
            engine.chmod(engine.stat().st_mode | status.stat.S_IWOTH)
            refusal = status.machine_engine_refusal(root)
        self.assertIsNotNone(refusal)
        self.assertIn("world-writable", refusal)

    def test_machine_engine_candidates_follow_path_order(self) -> None:
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            first = Path(raw) / "first"
            second = Path(raw) / "second"
            first_bin = self.decoy_engine_root(first, identity="manifest")
            second_bin = self.decoy_engine_root(second, identity="plugin")
            script = self.machine_install_arrangement(Path(raw) / "machine")
            environ = {"PATH": os.pathsep.join([str(first_bin), str(second_bin)])}

            candidates = status.machine_engine_candidates(script, environ)

        self.assertEqual([rung for rung, _ in candidates], ["adjacent", "path", "path"])
        self.assertEqual(
            [root for _, root in candidates[1:]], [first.resolve(), second.resolve()]
        )

    def test_machine_scope_api_reports_every_refused_candidate(self) -> None:
        """A refusal is reported, never silently skipped.

        A skip would degrade to a bare `unavailable` -- the uninformative
        failure this ladder exists to remove -- and would also hide a candidate
        that had no business being on PATH.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            decoy = Path(raw) / "decoy"
            decoy_bin = self.decoy_engine_root(decoy, identity=None)
            trusted_bin = PACK_ROOT / "scripts"
            script = self.machine_install_arrangement(Path(raw) / "machine")
            environ = {"PATH": os.pathsep.join([str(decoy_bin), str(trusted_bin)])}
            root_path = str(PACK_ROOT.resolve())
            original_path = [entry for entry in status.sys.path if entry != root_path]

            with (
                mock.patch.object(status, "__file__", str(script)),
                mock.patch.object(status.sys, "path", original_path.copy()),
            ):
                _engine, rung, root, refusals = status.machine_scope_api(environ=environ)

        self.assertEqual(rung, "path")
        self.assertEqual(root, PACK_ROOT.resolve())
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["root"], str(decoy.resolve()))
        self.assertIn("no pack identity", refusals[0]["reason"])

    def test_machine_scope_api_names_every_candidate_when_none_answer(self) -> None:
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            decoy = Path(raw) / "decoy"
            decoy_bin = self.decoy_engine_root(decoy, identity=None)
            script = self.machine_install_arrangement(Path(raw) / "machine")
            environ = {"PATH": str(decoy_bin)}

            with mock.patch.object(status, "__file__", str(script)):
                with self.assertRaises(RuntimeError) as raised:
                    status.machine_scope_api(environ=environ)

            message = str(raised.exception)
            self.assertIn(str(Path(raw) / "machine"), message)
            self.assertIn(str(decoy.resolve()), message)
            self.assertIn("no pack identity", message)

    def test_machine_scope_line_shows_engine_provenance_under_version_skew(self) -> None:
        """The skew issue #496 reports, rendered.

        An engine loaded from a version-qualified plugin root can describe an
        install of a different release. Naming the root is what makes that
        defensible; a line without it reads as an ordinary report.
        """
        status = self.load_status_module()
        line = status.format_machine_scope(
            {
                "state": "installed",
                "packVersion": "0.71.22",
                "engineRung": "path",
                "engineRoot": "/home/u/.claude/plugins/cache/sd-ai-command-pack/sd/0.71.26",
                "engineRefusals": [],
                "pluginVersion": "0.71.26",
                "comparison": "behind",
            }
        )
        self.assertIn("installed 0.71.22", line)
        self.assertIn("engine via path", line)
        self.assertIn("sd/0.71.26", line)

    def test_machine_scope_line_omits_provenance_for_the_adjacent_rung(self) -> None:
        status = self.load_status_module()
        line = status.format_machine_scope(
            {
                "state": "installed",
                "packVersion": "0.71.26",
                "engineRung": "adjacent",
                "engineRoot": "/repo",
                "engineRefusals": [],
                "pluginVersion": "0.71.26",
                "comparison": "current",
            }
        )
        self.assertNotIn("engine via", line)
        self.assertEqual(line, "installed 0.71.26; plugin 0.71.26; current")

    def test_machine_scope_row_is_real_for_a_thin_consumer_install(self) -> None:
        """The acceptance criterion, end to end.

        The unit tests prove the ladder resolves. Only this one proves the row
        a reader actually sees stopped saying `unavailable` for the machine
        install the `sd-status` skill routes thin consumers to.
        """
        status = self.load_status_module()
        repo = self.make_status_repo()
        with tempfile.TemporaryDirectory() as raw:
            script = self.machine_install_arrangement(Path(raw) / "machine")
            home = Path(raw) / "home"
            home.mkdir()
            environ = {"PATH": str(PACK_ROOT / "scripts"), "HOME": str(home)}

            with (
                mock.patch.object(status, "__file__", str(script)),
                self.stub_claude(status, []),
            ):
                section = status.collect_machine_scope(
                    repo, home=home, environ=environ, state_home=Path(raw) / "state"
                )

        self.assertNotEqual(section["state"], "unavailable")
        self.assertIn(section["state"], status.MACHINE_RECEIPT_STATES)
        self.assertEqual(section["engineRung"], "path")
        self.assertEqual(section["engineRoot"], str(PACK_ROOT.resolve()))
        self.assertIn("engine via path", status.format_machine_scope(section))

    def test_machine_scope_api_resolves_a_symlinked_bin_through_the_adjacent_rung(
        self,
    ) -> None:
        """`~/.agents/bin` as a symlink into a pack root is not the defect.

        `Path(__file__).resolve()` follows the link, so that arrangement was
        always served by the first rung. Pinned so the ladder is not later
        credited with a case it never needed to handle.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            link_parent = Path(raw) / "agents"
            link_parent.mkdir()
            link = link_parent / "bin"
            link.symlink_to(PACK_ROOT / "scripts", target_is_directory=True)
            script = link / "sd-ai-command-pack-status.py"

            with mock.patch.object(status, "__file__", str(script)):
                _engine, rung, root, refusals = status.machine_scope_api(
                    environ={"PATH": ""}
                )

        self.assertEqual(rung, "adjacent")
        self.assertEqual(root, PACK_ROOT.resolve())
        self.assertEqual(refusals, [])

    def test_machine_scope_api_restores_sys_path_on_success_and_on_failure(self) -> None:
        """`sys.path` is process-global; a rung that widens it must narrow it.

        Both exits are asserted, because the one that leaks is the exception
        path -- where a `finally` is easy to omit and nothing downstream
        complains until an unrelated import resolves out of a pack root.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            broken = Path(raw) / "broken"
            broken_bin = self.decoy_engine_root(broken, identity="manifest")
            (broken / "installer" / "machinescope.py").write_text(
                "import sd_definitely_not_a_real_module\n", encoding="utf-8"
            )
            script = self.machine_install_arrangement(Path(raw) / "machine")
            root_path = str(PACK_ROOT.resolve())
            baseline = [entry for entry in status.sys.path if entry != root_path]

            # Success path.
            with (
                mock.patch.object(status, "__file__", str(script)),
                mock.patch.object(status.sys, "path", baseline.copy()),
            ):
                status.machine_scope_api(environ={"PATH": str(PACK_ROOT / "scripts")})
                after_success = list(status.sys.path)

            # Failure path: gate passes, import does not. The engine is
            # evicted from `sys.modules` first -- the success block above
            # cached it, and a cached module would make the broken one import
            # cleanly and quietly test nothing.
            with (
                mock.patch.object(status, "__file__", str(script)),
                mock.patch.object(status.sys, "path", baseline.copy()),
                mock.patch.dict(status.sys.modules),
            ):
                for name in list(status.sys.modules):
                    if name == "installer" or name.startswith("installer."):
                        del status.sys.modules[name]
                with self.assertRaises(RuntimeError):
                    status.machine_scope_api(environ={"PATH": str(broken_bin)})
                after_failure = list(status.sys.path)

        self.assertEqual(after_success, baseline)
        self.assertEqual(after_failure, baseline)

    def test_machine_engine_refusal_rejects_a_world_writable_package_initializer(
        self,
    ) -> None:
        """`__init__.py` runs before the engine, so it is gated like the engine.

        Locking down `machinescope.py` while leaving the package initializer
        world-writable gates the wrong file: `from installer import
        machinescope` executes `__init__.py` first, so the attacker's code runs
        before the module the gate protected is ever reached.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "open-init"
            self.decoy_engine_root(root, identity="manifest")
            initializer = root / "installer" / "__init__.py"
            initializer.chmod(initializer.stat().st_mode | status.stat.S_IWOTH)
            refusal = status.machine_engine_refusal(root)
        self.assertIsNotNone(refusal)
        self.assertIn("world-writable", refusal)
        self.assertIn("__init__.py", refusal)

    def test_machine_scope_api_passes_over_a_half_populated_adjacent_root(self) -> None:
        """A partial `installer/` beside the script must not end the ladder.

        `machinescope.py` without `__init__.py` is not an importable package.
        Proceeding on it raises out of the loop, so a later rung that would
        have answered is never reached -- the row reports an opaque import
        error instead of the install it could have found.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            adjacent = Path(raw) / "adjacent"
            package = adjacent / "installer"
            package.mkdir(parents=True)
            (package / "machinescope.py").write_text("", encoding="utf-8")
            self.assertFalse((package / "__init__.py").exists())
            binary_dir = adjacent / "bin"
            binary_dir.mkdir()
            script = binary_dir / "sd-ai-command-pack-status.py"
            script.write_text("", encoding="utf-8")

            with mock.patch.object(status, "__file__", str(script)):
                _engine, rung, root, _refusals = status.machine_scope_api(
                    environ={"PATH": str(PACK_ROOT / "scripts")}
                )

        self.assertEqual(rung, "path")
        self.assertEqual(root, PACK_ROOT.resolve())

    def test_machine_scope_api_steps_over_a_candidate_that_fails_to_import(self) -> None:
        """A gated candidate can still fail to import; that ends it, not the ladder.

        Raising on the first import failure would strand the collector on a
        corrupt engine while a perfectly good root sat later in `PATH`. The
        reason is not lost -- it is recorded as a refusal.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            broken = Path(raw) / "broken"
            broken_bin = self.decoy_engine_root(broken, identity="manifest")
            (broken / "installer" / "machinescope.py").write_text(
                "import sd_definitely_not_a_real_module\n", encoding="utf-8"
            )
            script = self.machine_install_arrangement(Path(raw) / "machine")
            environ = {
                "PATH": os.pathsep.join([str(broken_bin), str(PACK_ROOT / "scripts")])
            }
            root_path = str(PACK_ROOT.resolve())
            baseline = [entry for entry in status.sys.path if entry != root_path]

            with (
                mock.patch.object(status, "__file__", str(script)),
                mock.patch.object(status.sys, "path", baseline.copy()),
                mock.patch.dict(status.sys.modules),
            ):
                for name in list(status.sys.modules):
                    if name == "installer" or name.startswith("installer."):
                        del status.sys.modules[name]
                _engine, rung, root, refusals = status.machine_scope_api(environ=environ)

        self.assertEqual(rung, "path")
        self.assertEqual(root, PACK_ROOT.resolve())
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["root"], str(broken.resolve()))
        self.assertIn("cannot import", refusals[0]["reason"])

    def test_machine_engine_candidates_use_the_raw_path_entry(self) -> None:
        """A `PATH` entry is a filesystem path, not display text.

        `path_pack_bins()` stores its `directory` through `safe_text()`, which
        rewrites every control character (`CONTROL_RE` is `[\x00-\x1f\x7f]+`,
        tab included) to a space, strips the ends, and truncates past 500
        characters. Rebuilding a `Path` from that names a DIFFERENT directory
        than the one probed, so a legitimate install silently stops being a
        candidate. A tab in a directory name is the smallest case that tells
        the raw entry and the display text apart.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "pa\tck"
            binary_dir = self.decoy_engine_root(root, identity="manifest")

            # The sanitized spelling is a real divergence, not a rounding of it.
            sanitized = Path(status.safe_text(str(binary_dir), limit=500)).parent
            self.assertNotEqual(str(sanitized), str(root))
            self.assertFalse(sanitized.exists())

            script = self.machine_install_arrangement(Path(raw) / "machine")
            candidates = status.machine_engine_candidates(
                script, {"PATH": str(binary_dir)}
            )

        self.assertEqual([rung for rung, _ in candidates], ["adjacent", "path"])
        self.assertEqual(candidates[1][1], root.resolve())

    def test_machine_scope_api_resolves_a_plugin_root_through_the_adjacent_rung(
        self,
    ) -> None:
        """A plugin root holding a real copy still resolves through rung 1.

        Asserted on the resolved path, not on success: a ladder that silently
        answered from a later rung would pass a success-only assertion while
        loading a different copy of the engine.
        """
        status = self.load_status_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "plugin-root"
            binary_dir = self.decoy_engine_root(root, identity="plugin")
            script = binary_dir / "sd-ai-command-pack-status.py"
            script.write_text("", encoding="utf-8")

            with mock.patch.object(status, "__file__", str(script)):
                _engine, rung, resolved, refusals = status.machine_scope_api(
                    environ={"PATH": ""}
                )

        self.assertEqual(rung, "adjacent")
        self.assertEqual(resolved, root.resolve())
        self.assertEqual(refusals, [])

    def test_machine_scope_line_names_a_refused_candidate(self) -> None:
        """A refusal reaches the reader, rather than vanishing into the row.

        A silent skip degrades to plain `unavailable` -- the uninformative
        failure this ladder exists to remove -- and hides a directory on `PATH`
        that had no business supplying executable code.
        """
        status = self.load_status_module()
        line = status.format_machine_scope(
            {
                "state": "installed",
                "packVersion": "0.71.52",
                "engineRung": "path",
                "engineRoot": "/opt/pack",
                "engineRefusals": [
                    {"root": "/tmp/decoy", "reason": "world-writable: /tmp/decoy"}
                ],
                "pluginVersion": "0.71.52",
                "comparison": "current",
            }
        )
        self.assertIn("refused", line)
        self.assertIn("/tmp/decoy", line)
        self.assertIn("world-writable", line)

    def test_machine_scope_without_the_engine_is_unavailable_not_none(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        home, state_home = self.machine_scratch()
        # A vendored consumer repository carries the scripts without the
        # installer package: the receipt cannot be read at all, which is
        # neither "no install recorded" nor a corrupt one.
        with tempfile.TemporaryDirectory() as tmp:
            fake_status = Path(tmp) / "scripts/sd-ai-command-pack-status.py"
            fake_status.parent.mkdir(parents=True)
            with (
                mock.patch.object(status, "__file__", str(fake_status)),
                self.stub_claude(status, [{"id": status.MACHINE_PLUGIN_ID, "version": "9.9.9"}]),
            ):
                section = status.collect_machine_scope(
                    root,
                    home=home,
                    environ={"XDG_CONFIG_HOME": str(home / ".config")},
                    state_home=state_home,
                )

        self.assertEqual(section["state"], "unavailable")
        self.assertNotEqual(section["state"], "none")
        self.assertIn("not installed beside this script", section["detail"])
        # A known plugin version cannot make an unreadable machine "current".
        self.assertEqual(section["pluginVersion"], "9.9.9")
        self.assertEqual(section["comparison"], "unknown")

    def test_machine_scope_reports_receipt_states_and_comparisons(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        cases = (
            # (receipt, plugin version, expected state, expected comparison)
            (None, "9.9.9", "none", "skew"),
            ("9.9.9", "9.9.9", "installed", "current"),
            ("9.9.8", "9.9.9", "installed", "skew"),
            (None, None, "none", "unknown"),
            ("9.9.9", None, "installed", "unknown"),
        )
        for receipt_version, plugin_version, expected_state, expected_comparison in cases:
            with self.subTest(receipt=receipt_version, plugin=plugin_version):
                home, state_home = self.machine_scratch()
                if receipt_version is not None:
                    self.write_machine_receipt(state_home, pack_version=receipt_version)
                listing = (
                    [{"id": status.MACHINE_PLUGIN_ID, "version": plugin_version}]
                    if plugin_version
                    else []
                )
                with self.stub_claude(status, listing):
                    section = self.machine_section(status, root, home, state_home)

                self.assertEqual(section["schemaVersion"], 2)
                self.assertEqual(section["state"], expected_state)
                self.assertEqual(section["comparison"], expected_comparison)
                self.assertEqual(section["packVersion"], receipt_version)
                self.assertEqual(section["pluginId"], status.MACHINE_PLUGIN_ID)
                self.assertEqual(
                    section["pluginVersion"], plugin_version or "unavailable"
                )
                self.assertIsNone(section["detail"])
                self.assertIn("machine-receipt.json", section["receiptPath"])

    def test_malformed_machine_receipt_is_invalid_not_none(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        home, state_home = self.machine_scratch()
        self.write_machine_receipt(state_home, raw="{broken\n")

        with self.stub_claude(
            status, [{"id": status.MACHINE_PLUGIN_ID, "version": "9.9.9"}]
        ):
            section = self.machine_section(status, root, home, state_home)

        # A corrupt receipt is an anomaly, not an absent install: reporting
        # "none" here would invite a silent reinstall over unknown state.
        self.assertEqual(section["state"], "invalid")
        self.assertNotEqual(section["state"], "none")
        self.assertIsNone(section["packVersion"])
        self.assertIn("receipt is unreadable", section["detail"])
        self.assertEqual(section["comparison"], "skew")

    def test_receipt_the_engine_refuses_is_invalid(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        home, state_home = self.machine_scratch()
        # Well-formed JSON, but an entry naming a family the engine does not
        # own: the receipt authorizes deletions, so it fails closed as a whole.
        self.write_machine_receipt(
            state_home,
            raw=json.dumps(
                {
                    "schemaVersion": 1,
                    "packVersion": "9.9.9",
                    "payloadDigest": "sha256:" + "0" * 64,
                    "installedAt": "2026-08-09T00:00:00Z",
                    "sourceRoot": "/plugin/machine-payload",
                    "files": [
                        {
                            "family": "somewhere-else",
                            "path": "sd-check/SKILL.md",
                            "digest": "sha256:" + "0" * 64,
                            "executable": False,
                        }
                    ],
                }
            ),
        )

        with self.stub_claude(status, []):
            section = self.machine_section(status, root, home, state_home)

        self.assertEqual(section["state"], "invalid")
        self.assertIn("unknown family", section["detail"])
        self.assertEqual(section["comparison"], "unknown")

    def test_every_plugin_discovery_failure_reports_unavailable_and_unknown(
        self,
    ) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        plugin_id = status.MACHINE_PLUGIN_ID
        cases = (
            ("cli absent", None, 0, "the Claude Code CLI is not on PATH"),
            ("nonzero exit", "[]", 3, "exited 3"),
            ("malformed json", "{not json", 0, "output is not JSON"),
            ("not an array", '{"id": "sd"}', 0, "did not return a plugin array"),
            ("plugin missing", '[{"id": "other@market", "version": "1"}]', 0, "is not installed"),
            (
                "plugin listed at conflicting versions",
                json.dumps(
                    [
                        {"id": plugin_id, "version": "9.9.9"},
                        {"id": plugin_id, "version": "9.9.8"},
                    ]
                ),
                0,
                "conflicting versions (9.9.8, 9.9.9)",
            ),
            (
                "entry without a version",
                json.dumps([{"id": plugin_id}]),
                0,
                "carries a version",
            ),
        )
        for label, listing, returncode, expected_detail in cases:
            with self.subTest(failure=label):
                home, state_home = self.machine_scratch()
                # An installed, readable receipt: only the plugin half fails,
                # so nothing but a guess could report "current" here.
                self.write_machine_receipt(state_home, pack_version="9.9.9")
                if listing is None:
                    context = mock.patch.object(
                        status.shutil, "which", return_value=None
                    )
                else:
                    context = self.stub_claude(status, listing, returncode=returncode)
                with context:
                    section = self.machine_section(status, root, home, state_home)

                self.assertEqual(section["state"], "installed")
                self.assertEqual(section["pluginVersion"], "unavailable")
                self.assertIn(expected_detail, section["pluginDetail"])
                self.assertEqual(section["comparison"], "unknown")

    def test_agreeing_duplicate_plugin_entries_resolve_to_that_version(self) -> None:
        # The live shape of `claude plugin list --json`: one user-scope
        # registration plus one per project that enables the plugin. Every
        # entry describes the same install, so the version is knowable, and
        # reporting it unavailable would hide the machine's real currency.
        status = self.load_status_module()
        root = self.make_status_repo()
        plugin_id = status.MACHINE_PLUGIN_ID
        home, state_home = self.machine_scratch()
        self.write_machine_receipt(state_home, pack_version="9.9.9")
        listing = self.plugin_listing(
            {"id": plugin_id, "version": "9.9.9", "scope": "user"},
            {"id": plugin_id, "version": "9.9.9", "scope": "project"},
            {"id": plugin_id, "version": "9.9.9", "scope": "project"},
        )

        with self.stub_claude(status, listing):
            section = self.machine_section(status, root, home, state_home)

        self.assertEqual(section["pluginVersion"], "9.9.9")
        self.assertIsNone(section["pluginDetail"])
        self.assertEqual(section["comparison"], "current")

    def test_duplicate_versions_are_compared_after_normalization(self) -> None:
        # Reconciliation compares the canonical value, not the raw one. Two
        # entries differing only past `safe_text`'s 80-character limit are the
        # same version to every consumer of this field, so treating them as a
        # conflict would refuse on a difference nothing can observe.
        status = self.load_status_module()
        root = self.make_status_repo()
        plugin_id = status.MACHINE_PLUGIN_ID
        home, state_home = self.machine_scratch()
        long_version = "9.9.9+" + ("b" * 100)
        truncated = status.safe_text(long_version, limit=80)
        self.assertNotEqual(truncated, long_version)
        self.write_machine_receipt(state_home, pack_version=truncated)
        listing = self.plugin_listing(
            {"id": plugin_id, "version": long_version, "scope": "user"},
            {"id": plugin_id, "version": long_version + "TAIL", "scope": "project"},
        )

        with self.stub_claude(status, listing):
            section = self.machine_section(status, root, home, state_home)

        self.assertEqual(section["pluginVersion"], truncated)
        self.assertIsNone(section["pluginDetail"])
        self.assertEqual(section["comparison"], "current")

    def test_agreeing_duplicate_entries_still_reach_a_skew_verdict(self) -> None:
        # The alarm the refusal suppressed. The fleet skew tests inject
        # `comparison="skew"` through the section fixture, so they prove the
        # row renders without ever asking whether the collector can produce
        # that input from a duplicated listing.
        status = self.load_status_module()
        root = self.make_status_repo()
        plugin_id = status.MACHINE_PLUGIN_ID
        home, state_home = self.machine_scratch()
        self.write_machine_receipt(state_home, pack_version="9.9.8")
        listing = self.plugin_listing(
            {"id": plugin_id, "version": "9.9.9", "scope": "user"},
            {"id": plugin_id, "version": "9.9.9", "scope": "project"},
        )

        with self.stub_claude(status, listing):
            section = self.machine_section(status, root, home, state_home)

        self.assertEqual(section["pluginVersion"], "9.9.9")
        self.assertEqual(section["packVersion"], "9.9.8")
        self.assertEqual(section["comparison"], "skew")

    def test_machine_scope_survives_an_engine_that_raises(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()

        class BrokenEngine:
            STATUS_SCHEMA_VERSION = 1

            @staticmethod
            def status(**kwargs: object) -> dict[str, object]:
                raise RuntimeError("cannot resolve state root")

        with (
            mock.patch.object(
                status, "machine_scope_api", return_value=self.engine_api_result(BrokenEngine)
            ),
            self.stub_claude(status, []),
        ):
            section = status.collect_machine_scope(root)

        self.assertEqual(section["state"], "unavailable")
        self.assertIn("cannot resolve state root", section["detail"])
        self.assertEqual(section["comparison"], "unknown")

    def test_machine_scope_rejects_an_unexpected_engine_schema_or_state(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()

        class SchemaSkewEngine:
            STATUS_SCHEMA_VERSION = 1

            @staticmethod
            def status(**kwargs: object) -> dict[str, object]:
                return {"schemaVersion": 99, "state": "installed"}

        class UnknownStateEngine:
            STATUS_SCHEMA_VERSION = 1

            @staticmethod
            def status(**kwargs: object) -> dict[str, object]:
                return {"schemaVersion": 1, "state": "probably-fine"}

        for engine, expected in (
            (SchemaSkewEngine, "unexpected schema version"),
            (UnknownStateEngine, "unsupported state"),
        ):
            with self.subTest(engine=engine.__name__):
                with (
                    mock.patch.object(
                        status,
                        "machine_scope_api",
                        return_value=self.engine_api_result(engine),
                    ),
                    self.stub_claude(status, []),
                ):
                    section = status.collect_machine_scope(root)

                self.assertEqual(section["state"], "unavailable")
                self.assertIn(expected, section["detail"])
                self.assertEqual(section["comparison"], "unknown")

    def test_machine_scope_human_line_spells_out_both_halves(self) -> None:
        status = self.load_status_module()

        self.assertEqual(
            status.format_machine_scope(
                {
                    "state": "installed",
                    "packVersion": "9.9.9",
                    "detail": None,
                    "pluginVersion": "9.9.9",
                    "pluginDetail": None,
                    "comparison": "current",
                }
            ),
            "installed 9.9.9; plugin 9.9.9; current",
        )
        self.assertEqual(
            status.format_machine_scope(
                {
                    "state": "none",
                    "packVersion": None,
                    "detail": None,
                    "pluginVersion": "unavailable",
                    "pluginDetail": "the Claude Code CLI is not on PATH",
                    "comparison": "unknown",
                }
            ),
            "none; plugin unavailable (the Claude Code CLI is not on PATH); unknown",
        )
        self.assertEqual(
            status.format_machine_scope(
                {
                    "state": "invalid",
                    "packVersion": None,
                    "detail": "receipt is unreadable",
                    "pluginVersion": "9.9.9",
                    "pluginDetail": None,
                    "comparison": "skew",
                }
            ),
            "invalid (receipt is unreadable); plugin 9.9.9; skew",
        )
        self.assertEqual(
            status.format_machine_scope(None),
            "not collected; plugin unavailable; unknown",
        )

    def write_toolchain(self, directory: Path) -> Path:
        """A stand-in toolchain; resolution tests only ask whether it exists."""
        directory.mkdir(parents=True, exist_ok=True)
        script = directory / "sd-ai-command-pack-toolchain.sh"
        script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
        return script

    def test_a_source_checkout_is_bound_when_no_pack_bin_is_on_path(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        home, _ = self.machine_scratch()
        checkout = self.write_toolchain(root / "scripts")

        for path_value in ("", str(root / "scripts")):
            with self.subTest(path=path_value or "<empty>"):
                resolution = status.collect_toolchain_resolution(
                    root,
                    home=home,
                    environ={"PATH": path_value},
                )

                # Both are bound for different reasons: no pack bin answers at
                # all, and a pack bin that answers with the same install.
                self.assertEqual(resolution["verdict"], "bound")
                self.assertEqual(resolution["source"], "checkout")
                self.assertEqual(resolution["toolchain"], str(checkout))
                self.assertEqual(resolution["installRoot"], str(root))

    def test_a_pack_bin_on_path_from_another_install_is_shadowed(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        home, _ = self.machine_scratch()
        self.write_toolchain(root / "scripts")
        stale = self.write_toolchain(home / "cache/sd/0.0.1/bin")
        # A non-pack directory ahead of it must not be reported: the row names
        # the entries that could answer, not every entry on PATH.
        noise = home / "usr/bin"
        noise.mkdir(parents=True)

        resolution = status.collect_toolchain_resolution(
            root,
            home=home,
            environ={"PATH": os.pathsep.join([str(noise), str(stale.parent)])},
        )

        self.assertEqual(resolution["verdict"], "shadowed")
        self.assertEqual(resolution["installRoot"], str(root))
        self.assertEqual(
            resolution["pathPackBins"],
            [{"directory": str(stale.parent), "toolchain": str(stale)}],
        )

    def test_a_thin_consumer_resolves_from_the_machine_install(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        home, _ = self.machine_scratch()
        # The defect this reporting exists for: a consumer checkout has no
        # `scripts/` directory at all, so candidate 2 misses and the machine
        # install answers. It is bound, not unresolved.
        self.assertFalse((root / "scripts").exists())
        machine = self.write_toolchain(home / ".agents/bin")

        resolution = status.collect_toolchain_resolution(
            root,
            home=home,
            environ={"PATH": str(machine.parent)},
        )

        self.assertEqual(resolution["verdict"], "bound")
        self.assertEqual(resolution["source"], "machine")
        self.assertEqual(resolution["toolchain"], str(machine))
        self.assertEqual(resolution["installRoot"], str(home / ".agents"))

        # And with nothing installed anywhere, the verdict is about the missing
        # toolchain rather than about PATH.
        empty_home, _ = self.machine_scratch()
        missing = status.collect_toolchain_resolution(
            root,
            home=empty_home,
            environ={"PATH": ""},
        )

        self.assertEqual(missing["verdict"], "unresolved")
        self.assertEqual(missing["source"], "none")
        self.assertIsNone(missing["toolchain"])
        self.assertIsNone(missing["installRoot"])

    def test_the_override_wins_and_an_empty_override_falls_through(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()
        home, _ = self.machine_scratch()
        checkout = self.write_toolchain(root / "scripts")
        override = self.write_toolchain(home / "wip/scripts")

        chosen = status.collect_toolchain_resolution(
            root,
            home=home,
            environ={"PATH": "", "SD_AI_COMMAND_PACK_TOOLCHAIN": str(override)},
        )

        self.assertEqual(chosen["source"], "override")
        self.assertEqual(chosen["toolchain"], str(override))

        # `[ -f "" ]` is false in the bootstrap, so an exported-but-empty
        # override must not shadow the candidates behind it.
        fell_through = status.collect_toolchain_resolution(
            root,
            home=home,
            environ={"PATH": "", "SD_AI_COMMAND_PACK_TOOLCHAIN": ""},
        )

        self.assertEqual(fell_through["source"], "checkout")
        self.assertEqual(fell_through["toolchain"], str(checkout))

    def test_the_helper_resolution_row_names_the_verdict_first(self) -> None:
        status = self.load_status_module()

        self.assertEqual(
            status.format_toolchain_resolution(
                {
                    "resolution": {
                        "verdict": "shadowed",
                        "toolchain": "/m/.agents/bin/sd-ai-command-pack-toolchain.sh",
                        "source": "machine",
                        "installRoot": "/m/.agents",
                        "pathPackBins": [
                            {"directory": "/cache/0.0.1/bin", "toolchain": "/x"},
                            {"directory": "/cache/0.0.2/bin", "toolchain": "/y"},
                        ],
                    }
                }
            ),
            "shadowed; /m/.agents/bin/sd-ai-command-pack-toolchain.sh "
            "(via machine, root /m/.agents); PATH pack bins (2, in order): "
            "/cache/0.0.1/bin, /cache/0.0.2/bin",
        )
        self.assertEqual(
            status.format_toolchain_resolution(
                {
                    "resolution": {
                        "verdict": "bound",
                        "toolchain": "/repo/scripts/sd-ai-command-pack-toolchain.sh",
                        "source": "checkout",
                        "installRoot": "/repo",
                        "pathPackBins": [],
                    }
                }
            ),
            "bound; /repo/scripts/sd-ai-command-pack-toolchain.sh "
            "(via checkout, root /repo); no pack bin on PATH",
        )
        self.assertEqual(
            status.format_toolchain_resolution(
                {
                    "resolution": {
                        "verdict": "unresolved",
                        "toolchain": None,
                        "source": "none",
                        "installRoot": None,
                        "pathPackBins": [],
                    }
                }
            ),
            "unresolved; no toolchain found "
            "(checked override, scripts/, ~/.agents/bin)",
        )
        # A fleet consumer row carries no machine scope at all.
        self.assertEqual(status.format_toolchain_resolution(None), "not collected")
        self.assertEqual(status.format_toolchain_resolution({}), "not collected")

    def test_a_shadowed_path_stays_in_its_row_and_never_becomes_an_anomaly(
        self,
    ) -> None:
        """Machine scope describes the machine, not this repository.

        Promoting it would make `--expect-clean` in any repository depend on
        which unrelated installs sit on the operator's `PATH`, and would put a
        repository gate under a value the repository cannot change. This
        follows the existing rule for a `skew` comparison, which is likewise
        reported in its row alone.
        """

        status = self.load_status_module()
        root = self.make_status_repo()

        section = {
            "state": "installed",
            "resolution": {
                "verdict": "shadowed",
                "toolchain": "/repo/scripts/sd-ai-command-pack-toolchain.sh",
                "source": "checkout",
                "installRoot": "/repo",
                "pathPackBins": [{"directory": "/cache/0.0.1/bin", "toolchain": "/x"}],
            },
        }
        with mock.patch.object(status, "collect_machine_scope", return_value=section):
            report = status.collect_local(
                root,
                remote="origin",
                supplied_default=None,
                source_branch=None,
                github_repo=None,
                network=False,
                refs_refreshed=False,
                expect_clean=False,
                keep_remote_branch=False,
                dry_run=False,
                prior_anomalies=(),
            )

        self.assertEqual(
            [anomaly for anomaly in report["anomalies"] if "PATH" in anomaly],
            [],
        )
        self.assertEqual(
            [
                detail
                for detail in report["anomalyDetails"]
                if "toolchain" in str(detail.get("code"))
            ],
            [],
        )
        # The row is the reporting surface, and it still says so plainly.
        self.assertIn(
            "shadowed", status.format_toolchain_resolution(report["machineScope"])
        )

    def test_only_an_invalid_machine_receipt_becomes_a_status_anomaly(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()

        def report_for(section: dict) -> dict:
            with mock.patch.object(
                status, "collect_machine_scope", return_value=section
            ):
                return status.collect_local(
                    root,
                    remote="origin",
                    supplied_default=None,
                    source_branch=None,
                    github_repo=None,
                    network=False,
                    refs_refreshed=False,
                    expect_clean=False,
                    keep_remote_branch=False,
                    dry_run=False,
                    prior_anomalies=(),
                )

        # A corrupt receipt is promoted exactly like an invalid work-loop or
        # recovery-artifact ledger: it gates --expect-clean and earns a
        # follow-up. An unreadable one does not, matching those same two.
        invalid = report_for(
            {"state": "invalid", "detail": "receipt is unreadable"}
        )
        self.assertTrue(
            any(
                "machine-scope receipt is invalid" in anomaly
                and "receipt is unreadable" in anomaly
                for anomaly in invalid["anomalies"]
            ),
            invalid["anomalies"],
        )

        for state in ("unavailable", "none", "installed"):
            with self.subTest(state=state):
                other = report_for({"state": state, "detail": "engine is absent"})
                self.assertFalse(
                    [
                        anomaly
                        for anomaly in other["anomalies"]
                        if "machine-scope" in anomaly
                    ],
                    other["anomalies"],
                )

    def test_fleet_consumer_reports_omit_machine_scope(self) -> None:
        status = self.load_status_module()
        root = self.make_status_repo()

        report = status.collect_local(
            root,
            remote="origin",
            supplied_default=None,
            source_branch=None,
            github_repo=None,
            network=False,
            refs_refreshed=False,
            expect_clean=False,
            keep_remote_branch=False,
            dry_run=False,
            prior_anomalies=(),
            include_machine_scope=False,
        )

        # Machine scope describes the machine, so a fleet run must not repeat
        # one identical answer (and one `claude` invocation) per consumer.
        self.assertIsNone(report["machineScope"])

    def test_installed_status_reports_machine_scope_end_to_end(self) -> None:
        # The installed arrangement (scripts/ beside installer/) with a real
        # `claude` stub on PATH: the only test that exercises the engine seam,
        # the CLI seam, and the human line together.
        status_script = PACK_ROOT / "scripts/sd-ai-command-pack-status.py"
        root = self.make_status_repo()
        home, state_home = self.machine_scratch()
        self.write_machine_receipt(state_home, pack_version="9.9.9")
        stub_bin = home / "stub-bin"
        self.write_stub_claude_cli(
            stub_bin,
            [
                {
                    "id": "sd@sd-ai-command-pack",
                    "version": "9.9.9",
                    "scope": "user",
                    "enabled": True,
                }
            ],
        )
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(home),
            "PATH": f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            **self.machine_state_env(state_home),
        }

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(status_script), "--repo", str(root), "--no-network", *args],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        machine = run("--json")
        human = run()

        self.assertEqual(machine.returncode, 0, machine.stdout)
        section = json.loads(machine.stdout)["machineScope"]
        self.assertEqual(section["schemaVersion"], 2)
        self.assertEqual(section["state"], "installed")
        self.assertEqual(section["packVersion"], "9.9.9")
        self.assertEqual(section["pluginVersion"], "9.9.9")
        self.assertEqual(section["comparison"], "current")
        self.assertEqual(section["pluginId"], "sd@sd-ai-command-pack")
        # Advisory only: machine skew never changes the exit status.
        self.assertEqual(human.returncode, 0, human.stdout)
        self.assertIn(
            "- machine scope: installed 9.9.9; plugin 9.9.9; current", human.stdout
        )

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

    def test_the_pack_source_is_searched_for_not_computed(self) -> None:
        fleet = self.load_fleet_lib()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-pack-source-")
        self.addCleanup(tempdir.cleanup)
        outside = Path(tempdir.name)

        self.assertEqual(
            fleet.find_pack_source(PACK_ROOT / "scripts"), PACK_ROOT.resolve()
        )
        self.assertEqual(fleet.find_pack_source(PACK_ROOT), PACK_ROOT.resolve())
        self.assertIsNone(fleet.find_pack_source(outside))

    def test_the_fleet_root_asks_the_working_directory_before_its_own_path(
        self,
    ) -> None:
        """A machine install is not one `parents[1]` step from the checkout.

        `~/.agents/bin/../` is `~/.agents`, which is not a pack source, so the
        last rung of `resolve_fleet_configuration` refused and `sd-status
        fleet` reported missing configuration even when it ran from inside the
        checkout holding the manifest.
        """

        status = self.load_status_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-fleet-root-")
        self.addCleanup(tempdir.cleanup)
        machine_bin = Path(tempdir.name) / "home/.agents/bin"
        machine_bin.mkdir(parents=True)
        # `fleet_api()` imports the helper from beside the script, so a faux
        # machine install has to carry it the way a real one does.
        shutil.copy2(
            PACK_ROOT / "templates/scripts/sd_ai_command_pack_fleet_lib.py",
            machine_bin / "sd_ai_command_pack_fleet_lib.py",
        )
        elsewhere = Path(tempdir.name) / "elsewhere"
        elsewhere.mkdir()

        original = status.__file__
        status.__file__ = str(machine_bin / "sd-ai-command-pack-status.py")
        try:
            from_checkout = status.runtime_pack_root(cwd=PACK_ROOT / "scripts")
            from_nowhere = status.runtime_pack_root(cwd=elsewhere)
        finally:
            status.__file__ = original

        self.assertEqual(from_checkout, PACK_ROOT.resolve())
        # No pack anywhere: still the script's own root, so the caller gets the
        # same "run install.py --configure-fleet" refusal it always got.
        self.assertEqual(from_nowhere, machine_bin.parent.resolve())

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

    def test_provider_config_states_classify_against_shipped_digests(self) -> None:
        status = self.load_status_module()
        pack_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pack_root, ignore_errors=True)
        consumer = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, consumer, ignore_errors=True)

        current = hashlib.sha256(b"current\n").hexdigest()
        old = hashlib.sha256(b"old\n").hexdigest()
        record = pack_root / status.PROVIDER_CONFIG_HISTORY_SOURCE
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sources": {
                        "templates/.gito/config.toml": {
                            "target": ".gito/config.toml",
                            "current": current,
                            "digests": [old, current],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        target = consumer / ".gito/config.toml"
        target.parent.mkdir(parents=True, exist_ok=True)

        for content, expected in (
            (b"current\n", "current"),
            (b"old\n", "superseded"),
            (b"mine\n", "local"),
        ):
            with self.subTest(state=expected):
                target.write_bytes(content)
                self.assertEqual(
                    status.provider_config_states(pack_root, consumer),
                    [{"target": ".gito/config.toml", "state": expected}],
                )

        target.unlink()
        self.assertEqual(
            status.provider_config_states(pack_root, consumer),
            [{"target": ".gito/config.toml", "state": "absent"}],
        )

        # A symlink is a local decision the installer preserves, not a missing
        # file; reporting it `absent` would say the opposite of what it is.
        elsewhere = consumer / "elsewhere.toml"
        elsewhere.write_bytes(b"current\n")
        target.symlink_to(elsewhere)
        self.assertEqual(
            status.provider_config_states(pack_root, consumer),
            [{"target": ".gito/config.toml", "state": "local"}],
        )

    def test_a_malformed_entry_is_reported_rather_than_skipped(self) -> None:
        # Skipping it shrinks the list toward the same clean-looking row an
        # unreadable record used to produce.
        status = self.load_status_module()
        pack_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pack_root, ignore_errors=True)
        consumer = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, consumer, ignore_errors=True)
        record = pack_root / status.PROVIDER_CONFIG_HISTORY_SOURCE
        record.parent.mkdir(parents=True, exist_ok=True)

        for label, entry in (
            ("not an object", 5),
            ("no target", {"current": "a" * 64, "digests": []}),
            ("no current", {"target": ".gito/config.toml", "digests": []}),
        ):
            with self.subTest(shape=label):
                record.write_text(
                    json.dumps(
                        {
                            "schemaVersion": 1,
                            "sources": {"templates/.gito/config.toml": entry},
                        }
                    ),
                    encoding="utf-8",
                )
                self.assertEqual(
                    status.provider_config_states(pack_root, consumer),
                    [
                        {
                            "target": "templates/.gito/config.toml",
                            "state": "unknown",
                        }
                    ],
                )

    def test_an_unreadable_record_reports_unknown_rather_than_nothing(self) -> None:
        # An empty list renders as a consumer with no provider configs, which
        # is indistinguishable from a clean one. The gap has to stay visible.
        status = self.load_status_module()
        pack_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pack_root, ignore_errors=True)
        consumer = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, consumer, ignore_errors=True)
        record = pack_root / status.PROVIDER_CONFIG_HISTORY_SOURCE
        record.parent.mkdir(parents=True, exist_ok=True)

        for label, payload in (
            ("missing", None),
            ("not json", b"{not json"),
            ("invalid utf-8", b'{"schemaVersion": 1, "sources": {"\xff": {}}}'),
            ("unsupported version", b'{"schemaVersion": 99, "sources": {}}'),
        ):
            with self.subTest(shape=label):
                if payload is None:
                    record.unlink(missing_ok=True)
                else:
                    record.write_bytes(payload)
                states = status.provider_config_states(pack_root, consumer)
                self.assertEqual(
                    states,
                    [
                        {
                            "target": status.PROVIDER_CONFIG_HISTORY_SOURCE.as_posix(),
                            "state": "unknown",
                        }
                    ],
                )

        step = [
            record["summary"]
            for record in status.fleet_step_records(
                [{"name": "consumer-a", "providerConfigs": states}], "0.0.0"
            )
            if "could not be determined" in record["summary"]
        ]
        self.assertEqual(len(step), 1, step)
        self.assertIn("consumer-a", step[0])


if __name__ == "__main__":
    unittest.main()
