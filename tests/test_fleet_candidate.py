from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
io = _support.io
json = _support.json
mock = _support.mock
os = _support.os
Path = _support.Path
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

CANDIDATE_SCRIPT = PACK_ROOT / "scripts/sd-ai-command-pack-fleet-candidate-check.py"


class FleetCandidateTests(InstallTestCase):
    """Tests for disposable fleet checks and release evidence."""

    def load_candidate_module(self):
        return self.load_module_from_path(
            CANDIDATE_SCRIPT,
            "sd_ai_command_pack_fleet_candidate",
        )

    def consumer(self, candidate, path_hint: Path, *, name: str = "fixture"):
        return candidate.FleetConsumer(
            name=name,
            github=f"example/{name}",
            path_hint=str(path_hint),
            platforms=("github",),
            rollout_priority=10,
            candidate_timeout_seconds=60,
            candidate_checks=((sys.executable, "check.py"),),
        )

    def write_fleet(self, root: Path, source: Path) -> Path:
        path = root / "fleet.json"
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "consumers": [
                        {
                            "name": "fixture",
                            "github": "example/fixture",
                            "pathHint": str(source),
                            "platforms": ["github"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidateChecks": [[sys.executable, "check.py"]],
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def make_origin_checkout(self, root: Path) -> tuple[Path, str]:
        origin = root / "origin.git"
        source = root / "source"
        origin.mkdir()
        source.mkdir()
        self.run_git(origin, "init", "--bare", "--initial-branch=main")
        self.run_git(source, "init", "--initial-branch=main")
        self.run_git(source, "config", "user.email", "test@example.com")
        self.run_git(source, "config", "user.name", "Test User")
        (source / ".trellis").mkdir()
        (source / ".trellis/config.yaml").write_text("# fixture\n", encoding="utf-8")
        (source / "check.py").write_text(
            "from pathlib import Path\n"
            "raise SystemExit(0 if Path('installed-marker').is_file() else 1)\n",
            encoding="utf-8",
        )
        self.run_git(source, "add", ".")
        self.run_git(source, "commit", "-m", "fixture consumer")
        self.run_git(source, "remote", "add", "origin", str(origin))
        self.run_git(source, "push", "-u", "origin", "main")
        return source, self.git_output(source, "rev-parse", "HEAD")

    def make_fake_pack(self, root: Path) -> Path:
        pack = root / "pack"
        scripts = pack / "scripts"
        scripts.mkdir(parents=True)
        (pack / "install.py").write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "(Path(sys.argv[1]) / 'installed-marker').write_text('ok\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        (scripts / "sd-ai-command-pack-install-audit.py").write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "repo = Path(sys.argv[sys.argv.index('--repo') + 1])\n"
            "raise SystemExit(0 if (repo / 'installed-marker').is_file() else 1)\n",
            encoding="utf-8",
        )
        return pack

    def test_validate_consumer_uses_origin_clone_without_mutating_source(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-candidate-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source, expected_commit = self.make_origin_checkout(root)
        pack = self.make_fake_pack(root)
        work_root = root / "work"
        work_root.mkdir()

        result = candidate.validate_consumer(
            self.consumer(candidate, source),
            pack_root=pack,
            work_root=work_root,
            python_executable=Path(sys.executable),
        )

        self.assertEqual(result.status, "passed", result.detail)
        self.assertEqual(result.base_commit, expected_commit)
        self.assertFalse((source / "installed-marker").exists())
        self.assertTrue((work_root / "fixture/installed-marker").is_file())

    def test_candidate_commands_do_not_inherit_pack_coverage_state(self) -> None:
        candidate = self.load_candidate_module()
        with mock.patch.dict(
            candidate.os.environ,
            {
                "COVERAGE_FILE": "/tmp/pack-coverage",
                "COVERAGE_PROCESS_START": "/tmp/pack-coveragerc",
            },
        ):
            env = candidate.command_environment(Path(sys.executable), Path("/tmp"))

        self.assertNotIn("COVERAGE_FILE", env)
        self.assertNotIn("COVERAGE_PROCESS_START", env)

    def test_run_command_normalizes_timeout_and_start_failures(self) -> None:
        candidate = self.load_candidate_module()
        with mock.patch.object(
            candidate.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["slow"], 1, output=b"partial"),
        ):
            timed_out = candidate.run_command(
                ["slow"], cwd=PACK_ROOT, timeout_seconds=1, env=os.environ.copy()
            )
        with mock.patch.object(
            candidate.subprocess,
            "run",
            side_effect=OSError("missing executable"),
        ):
            missing = candidate.run_command(
                ["missing"], cwd=PACK_ROOT, timeout_seconds=1, env=os.environ.copy()
            )

        self.assertEqual(timed_out.returncode, 124)
        self.assertIn("partial", timed_out.output)
        self.assertIn("timed out", timed_out.output)
        self.assertEqual(missing.returncode, 127)
        self.assertIn("missing executable", missing.output)

    def test_validate_consumer_reports_each_failed_stage(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-stage-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source = root / "source"
        pack = root / "pack"
        work = root / "work"
        source.mkdir()
        pack.mkdir()
        work.mkdir()
        consumer = self.consumer(candidate, source)

        def command_result(returncode: int, output: str = ""):
            return candidate.CommandResult(returncode, output, 0.1)

        scenarios = {
            "origin lookup": [command_result(1, "no origin")],
            "empty URL": [command_result(0, "")],
            "clone": [command_result(0, "origin"), command_result(1, "clone failed")],
            "base commit": [
                command_result(0, "origin"),
                command_result(0),
                command_result(1, "bad head"),
            ],
            "install": [
                command_result(0, "origin"),
                command_result(0),
                command_result(0, "a" * 40),
                command_result(1, "install failed"),
            ],
            "install audit": [
                command_result(0, "origin"),
                command_result(0),
                command_result(0, "a" * 40),
                command_result(0),
                command_result(1, "audit failed"),
            ],
            "candidate check": [
                command_result(0, "origin"),
                command_result(0),
                command_result(0, "a" * 40),
                command_result(0),
                command_result(0),
                command_result(1, "check failed"),
            ],
        }

        for label, results in scenarios.items():
            with self.subTest(stage=label):
                with mock.patch.object(candidate, "run_command", side_effect=results):
                    result = candidate.validate_consumer(
                        consumer,
                        pack_root=pack,
                        work_root=work,
                        python_executable=Path(sys.executable),
                    )
                self.assertEqual(result.status, "failed")
                if label == "empty URL":
                    self.assertIn("empty URL", result.detail)
                else:
                    self.assertIn(label, result.detail)

        missing = candidate.validate_consumer(
            self.consumer(candidate, root / "missing"),
            pack_root=pack,
            work_root=work,
            python_executable=Path(sys.executable),
        )
        self.assertEqual(missing.status, "failed")
        self.assertIn("local checkout not found", missing.detail)

    def test_validate_consumer_terminates_clone_options_before_origin(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-clone-options-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source = root / "source"
        pack = root / "pack"
        work = root / "work"
        source.mkdir()
        pack.mkdir()
        work.mkdir()

        command_result = candidate.CommandResult
        with mock.patch.object(
            candidate,
            "run_command",
            side_effect=[
                command_result(0, "-hostile-origin", 0.1),
                command_result(1, "clone rejected", 0.1),
            ],
        ) as run:
            result = candidate.validate_consumer(
                self.consumer(candidate, source),
                pack_root=pack,
                work_root=work,
                python_executable=Path(sys.executable),
            )

        clone_command = run.call_args_list[1].args[0]
        self.assertEqual(
            clone_command[-3:],
            ["--", "-hostile-origin", str(work / "fixture")],
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("clone", result.detail)

    def test_ledger_detects_payload_and_fleet_drift(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-ledger-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source = root / "source.txt"
        source.write_text("candidate one\n", encoding="utf-8")
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": "1.2.3",
                    "files": [
                        {
                            "source": "source.txt",
                            "target": "source.txt",
                            "platform": "shared",
                            "kind": "guide",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        fleet = self.write_fleet(root, root / "unused")
        version, payload, fleet_digest, consumers = candidate.current_evidence(
            manifest, fleet
        )
        result = candidate.CandidateResult(
            consumer=consumers[0],
            status="passed",
            base_commit="a" * 40,
            detail="passed",
            duration_seconds=1.0,
        )
        ledger = root / "ledger.json"
        candidate.write_ledger(
            ledger,
            candidate.ledger_content(
                version=version,
                payload_digest=payload,
                fleet_digest=fleet_digest,
                results=[result],
            ),
        )

        self.assertEqual(
            candidate.check_ledger(
                manifest_path=manifest,
                fleet_path=fleet,
                ledger_path=ledger,
            ),
            [],
        )

        source.write_text("candidate two\n", encoding="utf-8")
        errors = candidate.check_ledger(
            manifest_path=manifest,
            fleet_path=fleet,
            ledger_path=ledger,
        )
        self.assertTrue(any("payloadDigest" in error for error in errors), errors)

    def test_fleet_library_rejects_malformed_manifests_and_ledgers(self) -> None:
        candidate = self.load_candidate_module()
        fleet_lib = candidate.sys.modules["sd_ai_command_pack_fleet_lib"]
        valid = {
            "name": "fixture",
            "github": "example/fixture",
            "pathHint": "~/fixture",
            "platforms": ["github"],
            "rolloutPriority": 10,
            "candidateTimeoutSeconds": 60,
            "candidateChecks": [["node", "check.mjs"]],
        }
        invalid_manifests = [
            {},
            {"schemaVersion": 2, "consumers": []},
            {"schemaVersion": 2, "consumers": ["bad"]},
            {"schemaVersion": 2, "consumers": [{**valid, "name": ""}]},
            {"schemaVersion": 2, "consumers": [{**valid, "name": ".."}]},
            {"schemaVersion": 2, "consumers": [{**valid, "name": "../escape"}]},
            {"schemaVersion": 2, "consumers": [{**valid, "name": "nested/name"}]},
            {"schemaVersion": 2, "consumers": [{**valid, "name": "nested\\name"}]},
            {"schemaVersion": 2, "consumers": [{**valid, "name": "/absolute"}]},
            {
                "schemaVersion": 2,
                "consumers": [valid, {**valid, "name": "FIXTURE", "rolloutPriority": 20}],
            },
            {"schemaVersion": 2, "consumers": [{**valid, "github": "fixture"}]},
            {"schemaVersion": 2, "consumers": [{**valid, "rolloutPriority": 0}]},
            {
                "schemaVersion": 2,
                "consumers": [valid, {**valid, "name": "two"}],
            },
            {
                "schemaVersion": 2,
                "consumers": [{**valid, "candidateTimeoutSeconds": 0}],
            },
            {"schemaVersion": 2, "consumers": [{**valid, "platforms": []}]},
            {
                "schemaVersion": 2,
                "consumers": [{**valid, "platforms": [1]}],
            },
            {
                "schemaVersion": 2,
                "consumers": [{**valid, "candidateChecks": []}],
            },
            {
                "schemaVersion": 2,
                "consumers": [{**valid, "candidateChecks": [[""]]}],
            },
        ]
        for manifest in invalid_manifests:
            with self.subTest(manifest=manifest):
                with self.assertRaises(candidate.FleetConfigError):
                    fleet_lib.parse_fleet_consumers(manifest)

        consumer = fleet_lib.parse_fleet_consumers(
            {"schemaVersion": 2, "consumers": [valid]}
        )[0]
        malformed_ledger = {
            "schemaVersion": 0,
            "packVersion": "old",
            "payloadDigest": "old",
            "fleetManifestDigest": "old",
            "validatedAt": "",
            "consumers": [
                "bad",
                {"github": "example/no-name"},
                {
                    "name": "fixture",
                    "github": "wrong/fixture",
                    "baseCommit": "bad",
                    "status": "failed",
                    "checks": [],
                },
                {"name": "FIXTURE"},
                {"name": "unknown"},
            ],
        }
        errors = fleet_lib.validate_candidate_ledger(
            malformed_ledger,
            expected_version="1.0.0",
            expected_payload_digest="sha256:payload",
            expected_fleet_digest="sha256:fleet",
            consumers=[consumer],
        )
        for expected in (
            "schemaVersion",
            "packVersion",
            "payloadDigest",
            "fleetManifestDigest",
            "validatedAt",
            "must be an object",
            "has no name",
            "repeats consumer",
            "unknown consumer",
            "github does not match",
            "status",
            "baseCommit",
            "checks do not match",
        ):
            self.assertTrue(any(expected in error for error in errors), (expected, errors))

    def test_payload_digest_rejects_invalid_or_missing_sources(self) -> None:
        candidate = self.load_candidate_module()
        fleet_lib = candidate.sys.modules["sd_ai_command_pack_fleet_lib"]
        for manifest in (
            {"files": "bad"},
            {"files": ["bad"]},
            {"files": [{}]},
            {"files": [{"source": "../outside"}]},
        ):
            with self.subTest(manifest=manifest):
                with self.assertRaises(candidate.FleetConfigError):
                    fleet_lib.payload_digest(
                        manifest,
                        lambda _: fleet_lib.PayloadSource(b"", False),
                    )

        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-source-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        manifest_path = root / "manifest.json"
        manifest_path.write_text(
            json.dumps({"version": "1.0.0", "files": [{"source": "missing"}]})
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(candidate.FleetConfigError):
            fleet_lib.filesystem_payload_digest(manifest_path)

    def test_partial_run_never_writes_canonical_ledger(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-partial-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        consumer = self.consumer(candidate, root)
        result = candidate.CandidateResult(
            consumer=consumer,
            status="passed",
            base_commit="b" * 40,
            detail="passed",
            duration_seconds=1.0,
        )
        ledger = root / "candidate-validation.json"
        output = io.StringIO()

        with (
            mock.patch.object(
                candidate,
                "current_evidence",
                return_value=("1.2.3", "sha256:payload", "sha256:fleet", [consumer]),
            ),
            mock.patch.object(candidate, "validate_consumer", return_value=result),
            contextlib.redirect_stdout(output),
        ):
            exit_code = candidate.main(
                [
                    "--manifest",
                    str(root / "manifest.json"),
                    "--fleet",
                    str(root / "fleet.json"),
                    "--ledger",
                    str(ledger),
                    "--consumer",
                    "fixture",
                ]
            )

        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertFalse(ledger.exists())
        self.assertIn("partial run did not update", output.getvalue())

    def test_failure_preserves_previous_ledger(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-failure-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        consumer = self.consumer(candidate, root)
        result = candidate.CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail="fixture failed",
            duration_seconds=1.0,
        )
        ledger = root / "candidate-validation.json"
        ledger.write_text("previous evidence\n", encoding="utf-8")

        with (
            mock.patch.object(
                candidate,
                "current_evidence",
                return_value=("1.2.3", "sha256:payload", "sha256:fleet", [consumer]),
            ),
            mock.patch.object(candidate, "validate_consumer", return_value=result),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            exit_code = candidate.main(
                [
                    "--manifest",
                    str(root / "manifest.json"),
                    "--fleet",
                    str(root / "fleet.json"),
                    "--ledger",
                    str(ledger),
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(ledger.read_text(encoding="utf-8"), "previous evidence\n")

    def test_main_check_mode_and_full_json_write(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-main-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        consumer = self.consumer(candidate, root)
        result = candidate.CandidateResult(
            consumer=consumer,
            status="passed",
            base_commit="c" * 40,
            detail="passed",
            duration_seconds=1.0,
        )
        ledger = root / "candidate-validation.json"

        with mock.patch.object(candidate, "check_ledger", return_value=["stale"]):
            self.assertEqual(candidate.main(["--check-ledger"]), 1)
        with mock.patch.object(candidate, "check_ledger", return_value=[]):
            self.assertEqual(candidate.main(["--check-ledger"]), 0)
        self.assertEqual(candidate.main(["--check-ledger", "--consumer", "fixture"]), 2)

        output = io.StringIO()
        with (
            mock.patch.object(
                candidate,
                "current_evidence",
                return_value=("1.2.3", "sha256:payload", "sha256:fleet", [consumer]),
            ),
            mock.patch.object(candidate, "validate_consumer", return_value=result),
            contextlib.redirect_stdout(output),
        ):
            exit_code = candidate.main(
                [
                    "--manifest",
                    str(root / "manifest.json"),
                    "--fleet",
                    str(root / "fleet.json"),
                    "--ledger",
                    str(ledger),
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertTrue(ledger.is_file())
        self.assertIn('"status": "passed"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
