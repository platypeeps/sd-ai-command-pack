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

    def make_portable_status_install(self, root: Path) -> Path:
        scripts = root / "scripts"
        scripts.mkdir(parents=True)
        for name in (
            "sd-ai-command-pack-status.py",
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
        self, root: Path, *args: str
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
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

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
        self.assertEqual(status.resolve_repo(root / "missing"), root.resolve())
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

    def test_invalid_repository_fails_without_traceback(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-status-invalid-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)

        result = self.run_status(root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("error: unable to inspect Git repository", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

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
                {
                    "schemaVersion": 3,
                    "consumers": [
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
                    ],
                }
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
                {
                    "schemaVersion": 3,
                    "consumers": [
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
                    ],
                }
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

        result = subprocess.run(
            [sys.executable, str(status_script), "fleet", "--json", "--no-network"],
            cwd=install_root,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "SD_AI_COMMAND_PACK_FLEET_CONFIG": str(profile),
                "SD_AI_COMMAND_PACK_FLEET_MANIFEST": "",
            },
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
