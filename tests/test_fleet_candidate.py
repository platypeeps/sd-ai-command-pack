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
mock = _support.mock
os = _support.os
Path = _support.Path
shutil = _support.shutil
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

CANDIDATE_SCRIPT = PACK_ROOT / "scripts/sd-ai-command-pack-fleet-candidate-check.py"
FLEET_LIB = PACK_ROOT / "scripts/sd_ai_command_pack_fleet_lib.py"


class FleetCandidateTests(InstallTestCase):
    """Tests for disposable fleet checks and release evidence."""

    def load_candidate_module(self):
        return self.load_module_from_path(
            CANDIDATE_SCRIPT,
            "sd_ai_command_pack_fleet_candidate",
        )

    def write_validator_source(self, root: Path, content: str = "# validator\n") -> None:
        """Materialize the sources `CANDIDATE_VALIDATOR_SOURCES` names.

        The digest loader fails closed on an absent source, so a fixture tree
        that omits these looks identical to a checkout whose validator was
        deleted. Fixtures carry a stand-in body: the digest binds the bytes,
        never their meaning.
        """
        fleet = self.load_module_from_path(FLEET_LIB, "fleet_candidate_test_fleet_lib")
        for source in fleet.CANDIDATE_VALIDATOR_SOURCES:
            path = root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def consumer(
        self,
        candidate,
        path_hint: Path,
        *,
        name: str = "fixture",
        prepare: bool = True,
    ):
        return candidate.FleetConsumer(
            name=name,
            github=f"example/{name}",
            path_hint=str(path_hint),
            platforms=("github",),
            rollout_priority=10,
            candidate_timeout_seconds=60,
            candidate_prepare=(
                ((sys.executable, "prepare.py"),) if prepare else ()
            ),
            candidate_checks=((sys.executable, "check.py"),),
        )

    def stub_artifact_lane(self, candidate, *, ok: bool = True):
        """A passing thin artifact lane, for tests about the ledger.

        `main` derives the pack root from the manifest path, so a fixture
        manifest in a temporary directory aims the real lane at a tree with no
        plugin, no generator, and no installer. These tests mock
        `validate_consumer` for the same reason; the lane gets the same
        treatment, and its own behavior is covered directly elsewhere.
        """

        steps = (
            candidate.ArtifactStep(
                name="plugin build and drift check",
                status=candidate.STATUS_PASSED if ok else candidate.STATUS_FAILED,
                detail="passed" if ok else "failed",
                duration_seconds=0.1,
            ),
        )
        return mock.patch.object(
            candidate,
            "run_thin_artifact_lane",
            return_value=candidate.ArtifactLaneResult(
                steps=steps,
                machine_home=None,
                machine_state=None,
            ),
        )

    def write_fleet(self, root: Path, source: Path) -> Path:
        path = root / "fleet.json"
        path.write_text(
            json.dumps(
                fleet_manifest(
                    [
                        {
                            "name": "fixture",
                            "github": "example/fixture",
                            "pathHint": str(source),
                            "platforms": ["github"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [[sys.executable, "prepare.py"]],
                            "candidateChecks": [[sys.executable, "check.py"]],
                        }
                    ]
                ),
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
        (source / "prepare.py").write_text(
            "from pathlib import Path\n"
            "Path('prepared-marker').write_text('ok\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        (source / "check.py").write_text(
            "from pathlib import Path\n"
            "ready = Path('installed-marker').is_file() and Path('prepared-marker').is_file()\n"
            "raise SystemExit(0 if ready else 1)\n",
            encoding="utf-8",
        )
        self.run_git(source, "add", ".")
        self.run_git(source, "commit", "-m", "fixture consumer")
        self.run_git(source, "remote", "add", "origin", str(origin))
        self.run_git(source, "push", "-u", "origin", "main")
        return source, self.git_output(source, "rev-parse", "HEAD")

    def stub_installer_modules(
        self,
        candidate,
        *,
        pin: str = "fat",
        verdict: dict | None = None,
    ):
        """Patch out the pack-root import for tests about stage sequencing.

        The stage tests drive `validate_consumer` on a `run_command` mock and
        an empty pack directory: nothing is cloned, so there is no tree for a
        real resweep to read. They are about which stage reports which failure,
        not about conversion behavior, and the fixture pack that carries real
        machinery belongs to the tests that exercise it.
        """

        conversion = mock.Mock()
        conversion.PIN_STATE_MALFORMED = "malformed"
        conversion.PIN_STATE_THIN = "thin"
        conversion.thin_pin_state.return_value = pin
        resweep = mock.Mock()
        resweep.resweep_consumer.return_value = verdict or {
            "verdict": "clear",
            "blockers": [],
            "packDefects": [],
            "missingFiles": [],
            "worktreeClean": True,
        }
        return mock.patch.object(
            candidate,
            "_installer_modules",
            return_value=(conversion, mock.Mock(), resweep),
        )

    def copy_pack_machinery(self, pack: Path) -> None:
        """Give a fixture pack root the real conversion and resweep machinery.

        `validate_consumer` imports `installer` from the pack root under test
        and loads that root's resweep script, so a fixture pack with neither
        cannot reach any of the behavior these tests are about. Stubbing them
        would mean maintaining a second `rewrite_text`, `check_text_residue`,
        and classifier -- the exact duplication `_installer_modules` exists to
        avoid. The fixture copies the real ones instead, and enumerates what to
        copy from `conversion` rather than re-typing a list that drifts.
        """

        shutil.copytree(PACK_ROOT / "installer", pack / "installer")
        (pack / "scripts").mkdir(parents=True, exist_ok=True)
        for name in (
            "sd-ai-command-pack-thin-resweep.py",
            "sd_ai_command_pack_lib.py",
        ):
            shutil.copy2(PACK_ROOT / "scripts" / name, pack / "scripts" / name)
        conversion = self.load_module_from_path(
            PACK_ROOT / "installer/conversion.py",
            "fleet_candidate_test_conversion",
        )
        sources = (
            "manifest.json",
            "docs/fleet/surface-partition.json",
            *conversion.CLASSIFIER_DIGEST_PATHS,
            *conversion.force_preserved_template_sources(PACK_ROOT),
        )
        for relative in sources:
            destination = pack / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(PACK_ROOT / relative, destination)

    def write_fixture_registry(self, pack: Path, source: Path) -> None:
        """A one-consumer fleet registry the copied resweep can resolve.

        `resolve_consumer` fails closed on an unregistered name, so the fixture
        consumer needs a record. It is the real registry's first entry with the
        name and path replaced: hand-authoring one would encode this test's
        idea of the schema rather than the schema.
        """

        payload = json.loads(
            (PACK_ROOT / "docs/fleet/consumers.json").read_text(encoding="utf-8")
        )
        entry = dict(payload["consumers"][0])
        entry["name"] = "fixture"
        entry["github"] = "example/fixture"
        entry["pathHint"] = str(source)
        payload["consumers"] = [entry]
        path = pack / "docs/fleet/consumers.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def make_fake_pack(self, root: Path, source: Path | None = None) -> Path:
        pack = root / "pack"
        scripts = pack / "scripts"
        scripts.mkdir(parents=True)
        self.copy_pack_machinery(pack)
        self.write_fixture_registry(pack, source if source is not None else root)
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
        pack = self.make_fake_pack(root, source)
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
        self.assertFalse((source / "prepared-marker").exists())
        self.assertTrue((work_root / "fixture/installed-marker").is_file())
        self.assertTrue((work_root / "fixture/prepared-marker").is_file())
        self.assertIn("1 preparation(s)", result.detail)

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

    def test_command_environment_does_not_add_empty_path_entry(self) -> None:
        candidate = self.load_candidate_module()
        python = Path(sys.executable)
        python_bin = str(python.resolve().parent)

        with mock.patch.dict(candidate.os.environ, {"PATH": ""}):
            empty_path_env = candidate.command_environment(python, Path("/tmp"))
        with mock.patch.dict(candidate.os.environ, {"PATH": "/usr/bin"}):
            populated_path_env = candidate.command_environment(python, Path("/tmp"))

        self.assertEqual(empty_path_env["PATH"], python_bin)
        self.assertEqual(
            populated_path_env["PATH"],
            os.pathsep.join([python_bin, "/usr/bin"]),
        )

    def test_command_environment_forces_disposable_tool_caches(self) -> None:
        candidate = self.load_candidate_module()
        work_root = Path("/tmp/candidate-work")
        with mock.patch.dict(
            candidate.os.environ,
            {
                "NPM_CONFIG_CACHE": "/custom/npm-cache",
                "UV_CACHE_DIR": "/custom/uv-cache",
            },
        ):
            env = candidate.command_environment(Path(sys.executable), work_root)

        namespace = Path(env["UV_CACHE_DIR"]).parent
        self.assertEqual(Path(env["NPM_CONFIG_CACHE"]), namespace / "npm")
        self.assertEqual(Path(env["UV_CACHE_DIR"]), namespace / "uv")
        self.assertEqual(Path(env["PYTHONPYCACHEPREFIX"]), namespace / "python")
        self.assertEqual(namespace.parent, work_root.resolve())

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
            # The install is committed in the disposable clone before the
            # resweep reads it, so `git add` and `git commit` sit between the
            # audit and the consumer's own commands.
            "staging the candidate install": [
                command_result(0, "origin"),
                command_result(0),
                command_result(0, "a" * 40),
                command_result(0),
                command_result(0),
                command_result(1, "add failed"),
            ],
            "candidate preparation": [
                command_result(0, "origin"),
                command_result(0),
                command_result(0, "a" * 40),
                command_result(0),
                command_result(0),
                command_result(0),
                command_result(0),
                command_result(1, "prepare failed"),
            ],
            "candidate check": [
                command_result(0, "origin"),
                command_result(0),
                command_result(0, "a" * 40),
                command_result(0),
                command_result(0),
                command_result(0),
                command_result(0),
                command_result(0),
                command_result(1, "check failed"),
            ],
        }

        for label, results in scenarios.items():
            with self.subTest(stage=label):
                with (
                    mock.patch.object(candidate, "run_command", side_effect=results),
                    self.stub_installer_modules(candidate),
                ):
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

        with (
            mock.patch.object(
                candidate,
                "run_command",
                side_effect=[command_result(0, "origin")]
                + [command_result(0)] * 3
                + [command_result(0, "audit passed")]
                + [command_result(0)] * 2
                + [command_result(0, "check passed")],
            ) as run,
            self.stub_installer_modules(candidate),
        ):
            empty_prepare = candidate.validate_consumer(
                self.consumer(candidate, source, prepare=False),
                pack_root=pack,
                work_root=work,
                python_executable=Path(sys.executable),
            )
        self.assertEqual(empty_prepare.status, "passed", empty_prepare.detail)
        self.assertEqual(run.call_count, 8)
        self.assertIn("0 preparation(s)", empty_prepare.detail)

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
        self.write_validator_source(root)
        version, payload, fleet_digest, validator, consumers = (
            candidate.current_evidence(manifest, fleet)
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
                validator_digest=validator,
                results=[result],
            ),
        )
        ledger_payload = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertEqual(
            ledger_payload["consumers"][0]["prepares"],
            [[sys.executable, "prepare.py"]],
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

        # The defect this task fixes: the validator has no manifest row, so an
        # edit to it moves no payload source. Only `validatorDigest` can make
        # the ledger stale, and only a stale ledger makes release-prep run the
        # validator at all.
        source.write_text("candidate one\n", encoding="utf-8")
        self.assertEqual(
            candidate.check_ledger(
                manifest_path=manifest,
                fleet_path=fleet,
                ledger_path=ledger,
            ),
            [],
        )
        fleet_lib = candidate.sys.modules["sd_ai_command_pack_fleet_lib"]
        validator_source = root / fleet_lib.CANDIDATE_VALIDATOR_SOURCES[0]
        validator_source.write_text("# validator, edited\n", encoding="utf-8")
        errors = candidate.check_ledger(
            manifest_path=manifest,
            fleet_path=fleet,
            ledger_path=ledger,
        )
        self.assertTrue(any("validatorDigest" in error for error in errors), errors)
        self.assertFalse(any("payloadDigest" in error for error in errors), errors)

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
            "candidatePrepare": [],
            "candidateChecks": [["node", "check.mjs"]],
        }
        missing_prepare = dict(valid)
        missing_prepare.pop("candidatePrepare")
        malformed_consumer = fleet_manifest([valid])
        malformed_consumer["consumers"] = ["bad"]
        invalid_manifests = [
            ({}, "schemaVersion must be 5"),
            ({"schemaVersion": 4, "consumers": []}, "schemaVersion must be 5"),
            (malformed_consumer, "consumers[0] must be an object"),
            (fleet_manifest([{**valid, "name": ""}]), "has invalid name"),
            (fleet_manifest([{**valid, "name": ".."}]), "name must be a non-path"),
            (
                fleet_manifest([{**valid, "name": "../escape"}]),
                "name must be a non-path",
            ),
            (
                fleet_manifest([{**valid, "name": "nested/name"}]),
                "name must be a non-path",
            ),
            (
                fleet_manifest([{**valid, "name": "nested\\name"}]),
                "name must be a non-path",
            ),
            (
                fleet_manifest([{**valid, "name": "/absolute"}]),
                "name must be a non-path",
            ),
            (
                fleet_manifest(
                    [valid, {**valid, "name": "FIXTURE", "rolloutPriority": 20}]
                ),
                "duplicate fleet consumer name",
            ),
            (
                fleet_manifest([{**valid, "github": "fixture"}]),
                "invalid github slug",
            ),
            (
                fleet_manifest([{**valid, "rolloutPriority": 0}]),
                "invalid rolloutPriority",
            ),
            (
                fleet_manifest([valid, {**valid, "name": "two"}]),
                "duplicate fleet rolloutPriority",
            ),
            (
                fleet_manifest([{**valid, "candidateTimeoutSeconds": 0}]),
                "candidateTimeoutSeconds must be between",
            ),
            (fleet_manifest([{**valid, "platforms": []}]), "must list platforms"),
            (fleet_manifest([{**valid, "platforms": [1]}]), "has invalid platform"),
            (fleet_manifest([missing_prepare]), "must list candidatePrepare"),
            (
                fleet_manifest(
                    [{**valid, "candidatePrepare": "python prepare.py"}]
                ),
                "must list candidatePrepare",
            ),
            (
                fleet_manifest([{**valid, "candidatePrepare": [[""]]}]),
                "candidatePrepare[0] must contain non-empty string arguments",
            ),
            (
                fleet_manifest([{**valid, "candidateChecks": []}]),
                "must list candidateChecks",
            ),
            (
                fleet_manifest([{**valid, "candidateChecks": [[""]]}]),
                "candidateChecks[0] must contain non-empty string arguments",
            ),
        ]
        for manifest, expected_error in invalid_manifests:
            with self.subTest(manifest=manifest):
                with self.assertRaises(candidate.FleetConfigError) as raised:
                    fleet_lib.parse_fleet_consumers(manifest)
                self.assertIn(expected_error, str(raised.exception))

        consumer = fleet_lib.parse_fleet_consumers(fleet_manifest([valid]))[0]
        malformed_ledger = {
            "schemaVersion": 0,
            "packVersion": "old",
            "payloadDigest": "old",
            "fleetManifestDigest": "old",
            "validatorDigest": "old",
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
            expected_validator_digest="sha256:validator",
            consumers=[consumer],
        )
        for expected in (
            "schemaVersion",
            "packVersion",
            "payloadDigest",
            "fleetManifestDigest",
            "validatorDigest",
            "validatedAt",
            "must be an object",
            "has no name",
            "repeats consumer",
            "unknown consumer",
            "github does not match",
            "status",
            "baseCommit",
            "prepares do not match",
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

    def test_payload_digest_frames_executable_marker_with_delimiters(self) -> None:
        candidate = self.load_candidate_module()
        fleet_lib = candidate.sys.modules["sd_ai_command_pack_fleet_lib"]
        manifest = {"version": "1.0.0", "files": [{"source": "bin/tool"}]}
        content = b"tool payload\n"

        expected = hashlib.sha256()
        expected.update(b"sd-ai-command-pack-candidate-payload-v1\0")
        expected.update(
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        )
        expected.update(b"\0bin/tool\0x\0")
        expected.update(hashlib.sha256(content).digest())

        self.assertEqual(
            fleet_lib.payload_digest(
                manifest,
                lambda _: fleet_lib.PayloadSource(content, True),
            ),
            f"sha256:{expected.hexdigest()}",
        )

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
                return_value=(
                    "1.2.3",
                    "sha256:payload",
                    "sha256:fleet",
                    "sha256:validator",
                    [consumer],
                ),
            ),
            mock.patch.object(candidate, "validate_consumer", return_value=result),
            self.stub_artifact_lane(candidate),
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
                return_value=(
                    "1.2.3",
                    "sha256:payload",
                    "sha256:fleet",
                    "sha256:validator",
                    [consumer],
                ),
            ),
            mock.patch.object(candidate, "validate_consumer", return_value=result),
            # Without this the run would exit nonzero because the artifact lane
            # failed, and the test would pass without ever proving that a failed
            # *consumer* preserves the previous ledger.
            self.stub_artifact_lane(candidate),
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

    def test_a_failed_artifact_lane_skips_consumer_validation(self) -> None:
        # The lane's install step is what produces `machine_home`, so once the
        # lane fails every thin consumer would come back `failed` for a
        # pack-side reason with the consumer's name on it -- eight clone and
        # install cycles spent manufacturing misdirected blame.
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-artifact-skip-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        consumer = self.consumer(candidate, root)
        ledger = root / "candidate-validation.json"
        ledger.write_text("previous evidence\n", encoding="utf-8")
        stderr = io.StringIO()

        with (
            mock.patch.object(
                candidate,
                "current_evidence",
                return_value=(
                    "1.2.3",
                    "sha256:payload",
                    "sha256:fleet",
                    "sha256:validator",
                    [consumer],
                ),
            ),
            mock.patch.object(candidate, "validate_consumer") as validate,
            self.stub_artifact_lane(candidate, ok=False),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(stderr),
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
        validate.assert_not_called()
        self.assertIn("1 consumer(s) were not validated", stderr.getvalue())
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
                return_value=(
                    "1.2.3",
                    "sha256:payload",
                    "sha256:fleet",
                    "sha256:validator",
                    [consumer],
                ),
            ),
            mock.patch.object(candidate, "validate_consumer", return_value=result),
            self.stub_artifact_lane(candidate),
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


    def test_artifact_lane_reports_each_step_and_an_absent_claude(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-artifact-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        pack = root / "pack"
        work = root / "work"
        empty_path = root / "empty-path"
        for directory in (pack, work, empty_path):
            directory.mkdir()

        def command_result(returncode: int, output: str = ""):
            return candidate.CommandResult(returncode, output, 0.1)

        # An empty PATH is the honest form of "claude is not installed": the
        # lane resolves the executable with `shutil.which` against this exact
        # value, so nothing about the mechanism is mocked away.
        absent_env = {"PATH": str(empty_path)}
        with mock.patch.object(
            candidate, "run_command", side_effect=[command_result(0)] * 2
        ):
            unavailable = candidate.run_thin_artifact_lane(
                pack_root=pack,
                work_root=work,
                python_executable=Path(sys.executable),
                env=absent_env,
            )

        statuses = {step.name: step.status for step in unavailable.steps}
        self.assertEqual(
            statuses[candidate.ARTIFACT_STEP_PLUGIN_VALIDATE],
            candidate.STATUS_UNAVAILABLE,
        )
        self.assertFalse(unavailable.ok)
        self.assertEqual(
            [step.name for step in unavailable.failures],
            [candidate.ARTIFACT_STEP_PLUGIN_VALIDATE],
        )
        validate_step = next(
            step
            for step in unavailable.steps
            if step.name == candidate.ARTIFACT_STEP_PLUGIN_VALIDATE
        )
        self.assertIn("not a skip", validate_step.detail)

        present_path = root / "bin"
        present_path.mkdir()
        claude = present_path / "claude"
        claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        claude.chmod(0o755)
        present_env = {"PATH": str(present_path)}
        breaks = {
            candidate.ARTIFACT_STEP_PLUGIN_BUILD: 0,
            candidate.ARTIFACT_STEP_PLUGIN_VALIDATE: 1,
            candidate.ARTIFACT_STEP_MACHINE_INSTALL: 2,
        }
        for name, index in breaks.items():
            with self.subTest(step=name):
                results = [command_result(0)] * 3
                results[index] = command_result(1, f"{name} broke")
                with mock.patch.object(
                    candidate, "run_command", side_effect=results
                ):
                    lane = candidate.run_thin_artifact_lane(
                        pack_root=pack,
                        work_root=work,
                        python_executable=Path(sys.executable),
                        env=present_env,
                    )
                self.assertFalse(lane.ok)
                self.assertEqual([step.name for step in lane.failures], [name])
                if name == candidate.ARTIFACT_STEP_MACHINE_INSTALL:
                    # A failed machine install must not hand a prefix to the
                    # thin lane; HOME would then point at an empty directory
                    # and every thin check would resolve nothing.
                    self.assertIsNone(lane.machine_home)
                else:
                    self.assertEqual(lane.machine_home, work / "home")

    def test_unresolvable_thin_checks_only_covers_manifest_targets(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-d6-test-")
        self.addCleanup(tempdir.cleanup)
        clone = Path(tempdir.name) / "clone"
        (clone / "scripts").mkdir(parents=True)
        (clone / "scripts/present.py").write_text("# present\n", encoding="utf-8")
        manifest_targets = frozenset({"scripts/sd-ai-command-pack-review.py"})

        relocated = candidate.unresolvable_thin_checks(
            [("python3", "scripts/sd-ai-command-pack-review.py", "--check")],
            clone=clone,
            manifest_targets=manifest_targets,
        )
        self.assertEqual(len(relocated), 1)
        self.assertIn("~/.agents/bin/sd-ai-command-pack-review.py", relocated[0])
        self.assertIn("scripts/sd-ai-command-pack-review.py", relocated[0])

        # A missing path the pack does not own is the consumer's own broken
        # check. Reporting it as `blocked` would excuse a real defect.
        self.assertEqual(
            candidate.unresolvable_thin_checks(
                [("python3", "scripts/consumer-owned.py")],
                clone=clone,
                manifest_targets=manifest_targets,
            ),
            [],
        )
        self.assertEqual(
            candidate.unresolvable_thin_checks(
                [("python3", "scripts/present.py"), ("npm", "test")],
                clone=clone,
                manifest_targets=manifest_targets,
            ),
            [],
        )

    def test_thin_clone_blocks_on_a_relocated_check_but_fails_on_its_own(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-d6-lane-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source = root / "source"
        pack = root / "pack"
        work = root / "work"
        machine_home = root / "machine-home"
        for directory in (source, pack, work, machine_home):
            directory.mkdir()
        (pack / "manifest.json").write_text(
            json.dumps({"files": [{"target": "scripts/sd-ai-command-pack-review.py"}]}),
            encoding="utf-8",
        )

        def command_result(returncode: int, output: str = ""):
            return candidate.CommandResult(returncode, output, 0.1)

        def consumer_naming(path: str):
            return candidate.FleetConsumer(
                name="fixture",
                github="example/fixture",
                path_hint=str(source),
                platforms=("github",),
                rollout_priority=10,
                candidate_timeout_seconds=60,
                candidate_prepare=(),
                candidate_checks=((sys.executable, path),),
            )

        def run_lane(path: str, check_returncode: int):
            # origin, clone, rev-parse, install, audit, git add, git commit,
            # then the consumer's single check.
            results = [command_result(0, "origin")] + [command_result(0)] * 6
            results[2] = command_result(0, "a" * 40)
            results.append(command_result(check_returncode, "check failed"))
            with (
                mock.patch.object(candidate, "run_command", side_effect=results),
                self.stub_installer_modules(candidate, pin="thin"),
            ):
                return candidate.validate_consumer(
                    consumer_naming(path),
                    pack_root=pack,
                    work_root=work,
                    python_executable=Path(sys.executable),
                    machine_home=machine_home,
                )

        # A manifest-declared path the conversion relocates: the consumer's
        # registry record still describes its fat shape, which is that
        # consumer's conversion work, not a broken pack.
        blocked = run_lane("scripts/sd-ai-command-pack-review.py", 0)
        self.assertEqual(blocked.status, candidate.STATUS_BLOCKED)
        self.assertEqual(len(blocked.reasons), 1)
        self.assertIn("~/.agents/bin/sd-ai-command-pack-review.py", blocked.reasons[0])
        self.assertIn("registered command", blocked.reasons[0])

        # A path the pack never owned is the consumer's own broken check, and
        # the command runs and fails on its own terms.
        failed = run_lane("scripts/consumer-owned.py", 1)
        self.assertEqual(failed.status, "failed")
        self.assertIn("candidate check 1", failed.detail)
        self.assertEqual(failed.reasons, ())

    def test_surviving_pack_defects_measures_residue_after_the_rewrite(self) -> None:
        candidate = self.load_candidate_module()
        references = self.load_module_from_path(
            PACK_ROOT / "installer/references.py",
            "fleet_candidate_test_references",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-residue-test-")
        self.addCleanup(tempdir.cleanup)
        clone = Path(tempdir.name) / "clone"
        clone.mkdir(parents=True)
        # A plain citation is repointed by `THIN_PROFILE`, so the resweep
        # counting it pre-rewrite says nothing about the release.
        (clone / "repointed.md").write_text(
            "see scripts/sd-ai-command-pack-review.py\n", encoding="utf-8"
        )
        # A glob is not a path the rewrite can repoint, so it survives.
        (clone / "glob.md").write_text(
            "matches scripts/sd-ai-command-pack-*.py\n", encoding="utf-8"
        )

        verdict = {
            "packDefects": [
                {"file": "repointed.md", "detail": "cites a removed script"}
            ]
        }
        self.assertEqual(
            candidate.surviving_pack_defects(
                verdict, clone=clone, references=references
            ),
            [],
        )

        verdict = {"packDefects": [{"file": "glob.md", "detail": "cites a glob"}]}
        surviving = candidate.surviving_pack_defects(
            verdict, clone=clone, references=references
        )
        self.assertEqual(len(surviving), 1)
        self.assertIn("glob.md", surviving[0])

        # A flagged file that is not there at all cannot be proven repointed.
        verdict = {"packDefects": [{"file": "gone.md", "detail": "absent"}]}
        self.assertEqual(
            candidate.surviving_pack_defects(
                verdict, clone=clone, references=references
            ),
            ["gone.md: absent"],
        )

    def test_pin_selects_the_lane_and_the_thin_lane_redirects_home(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-pin-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source = root / "source"
        pack = root / "pack"
        work = root / "work"
        machine_home = root / "machine-home"
        for directory in (source, pack, work, machine_home):
            directory.mkdir()
        # The thin branch reads the manifest to tell a relocated pack target
        # from a consumer's own missing file.
        (pack / "manifest.json").write_text(
            json.dumps({"files": [{"target": "scripts/sd-ai-command-pack-review.py"}]}),
            encoding="utf-8",
        )
        consumer = self.consumer(candidate, source)

        def command_result(returncode: int, output: str = ""):
            return candidate.CommandResult(returncode, output, 0.1)

        def run_lane(pin: str):
            # origin, clone, rev-parse, install, audit, git add, git commit,
            # one preparation, one check.
            results = [command_result(0, "origin")] + [command_result(0)] * 8
            results[2] = command_result(0, "a" * 40)
            with (
                mock.patch.object(
                    candidate, "run_command", side_effect=results
                ) as run,
                self.stub_installer_modules(candidate, pin=pin),
            ):
                result = candidate.validate_consumer(
                    consumer,
                    pack_root=pack,
                    work_root=work,
                    python_executable=Path(sys.executable),
                    machine_home=machine_home,
                )
            return result, run

        thin_result, thin_run = run_lane("thin")
        fat_result, fat_run = run_lane("fat")
        self.assertEqual(thin_result.status, "passed", thin_result.detail)
        self.assertEqual(fat_result.status, "passed", fat_result.detail)
        self.assertIn("thin install", thin_result.detail)
        self.assertIn("fat install", fat_result.detail)

        thin_install = thin_run.call_args_list[3].args[0]
        fat_install = fat_run.call_args_list[3].args[0]
        self.assertNotIn("--platform", thin_install)
        self.assertEqual(fat_install[-2:], ["--platform", "github"])
        # `install.py --thin --consumer` is what flips this pack's own fleet
        # registry. The loop must never reach that code path.
        self.assertNotIn("--consumer", thin_install)
        self.assertNotIn("--consumer", fat_install)

        thin_audit = thin_run.call_args_list[4].args[0]
        fat_audit = fat_run.call_args_list[4].args[0]
        self.assertNotIn("--expected-platform", thin_audit)
        self.assertIn("--expected-platform", fat_audit)
        self.assertTrue(
            any("--expected-platform" in note for note in thin_result.notes),
            thin_result.notes,
        )

        # The consumer's own commands are calls 8 and 9 (prepare, then check):
        # HOME must be the run's scratch prefix for a thin clone and the
        # inherited value for a fat one. Asserting the environment, not the
        # outcome -- a check that happened to pass under the wrong HOME would
        # look identical.
        thin_env = thin_run.call_args_list[7].kwargs["env"]
        fat_env = fat_run.call_args_list[7].kwargs["env"]
        self.assertEqual(thin_env["HOME"], str(machine_home.resolve()))
        self.assertEqual(fat_env.get("HOME"), os.environ.get("HOME"))

    def test_thin_lane_blocks_without_a_machine_prefix(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-nohome-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source = root / "source"
        pack = root / "pack"
        work = root / "work"
        for directory in (source, pack, work):
            directory.mkdir()

        def command_result(returncode: int, output: str = ""):
            return candidate.CommandResult(returncode, output, 0.1)

        with (
            mock.patch.object(
                candidate,
                "run_command",
                side_effect=[
                    command_result(0, "origin"),
                    command_result(0),
                    command_result(0, "a" * 40),
                ],
            ),
            self.stub_installer_modules(candidate, pin="thin"),
        ):
            result = candidate.validate_consumer(
                self.consumer(candidate, source),
                pack_root=pack,
                work_root=work,
                python_executable=Path(sys.executable),
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("no machine install", result.detail)

    def test_malformed_pin_fails_instead_of_guessing_a_shape(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-malformed-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source = root / "source"
        pack = root / "pack"
        work = root / "work"
        for directory in (source, pack, work):
            directory.mkdir()

        def command_result(returncode: int, output: str = ""):
            return candidate.CommandResult(returncode, output, 0.1)

        with (
            mock.patch.object(
                candidate,
                "run_command",
                side_effect=[
                    command_result(0, "origin"),
                    command_result(0),
                    command_result(0, "a" * 40),
                ],
            ),
            self.stub_installer_modules(candidate, pin="malformed"),
        ):
            result = candidate.validate_consumer(
                self.consumer(candidate, source),
                pack_root=pack,
                work_root=work,
                python_executable=Path(sys.executable),
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("malformed", result.detail)

    def test_consumer_owned_blockers_produce_blocked_with_reasons(self) -> None:
        candidate = self.load_candidate_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-blocked-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source = root / "source"
        pack = root / "pack"
        work = root / "work"
        for directory in (source, pack, work):
            directory.mkdir()

        def command_result(returncode: int, output: str = ""):
            return candidate.CommandResult(returncode, output, 0.1)

        results = [command_result(0, "origin")] + [command_result(0)] * 8
        results[2] = command_result(0, "a" * 40)
        with (
            mock.patch.object(candidate, "run_command", side_effect=results),
            self.stub_installer_modules(
                candidate,
                verdict={
                    "verdict": "blocked",
                    "counts": {"blockers": 12, "packDefects": 3},
                    "packDefects": [],
                    "missingFiles": ["docs/gone.md"],
                    "worktreeClean": False,
                },
            ),
        ):
            result = candidate.validate_consumer(
                self.consumer(candidate, source),
                pack_root=pack,
                work_root=work,
                python_executable=Path(sys.executable),
            )

        self.assertEqual(result.status, candidate.STATUS_BLOCKED)
        self.assertEqual(len(result.reasons), 3)
        self.assertIn("12 consumer-authored reference(s)", result.reasons[0])
        self.assertIn("1 manifest file(s) missing", result.reasons[1])
        self.assertIn("uncommitted changes", result.reasons[2])
        # Every stage ran and passed, so the detail still records what ran.
        self.assertIn("check(s) passed", result.detail)
        # A pre-rewrite pack-defect count with no surviving residue is a note,
        # never a failure.
        self.assertTrue(
            any("repointed by the conversion" in note for note in result.notes),
            result.notes,
        )

    def test_ledger_requires_reasons_for_every_blocked_consumer(self) -> None:
        candidate = self.load_candidate_module()
        fleet = self.load_module_from_path(FLEET_LIB, "fleet_blocked_ledger_lib")
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-ledger-status-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        source = root / "source"
        source.mkdir()
        fleet_path = self.write_fleet(root, source)
        consumers = fleet.load_fleet_consumers(fleet_path)

        # Built by the real writer and then mutated, so the fixture cannot
        # drift into agreeing with the validator about a shape neither the
        # loop nor the release actually produces.
        def ledger(**overrides) -> dict:
            content = candidate.ledger_content(
                version="1.2.3",
                payload_digest="sha256:payload",
                fleet_digest="sha256:fleet",
                validator_digest="sha256:validator",
                results=[
                    candidate.CandidateResult(
                        consumer=consumers[0],
                        status=candidate.STATUS_PASSED,
                        base_commit="a" * 40,
                        detail="passed",
                        duration_seconds=1.0,
                    )
                ],
            )
            content["consumers"][0].update(overrides)
            return content

        cases = {
            "passed": ({}, None),
            "blocked with reasons": (
                {"status": "blocked", "reasons": ["12 consumer-authored references"]},
                None,
            ),
            "blocked with no reasons": (
                {"status": "blocked", "reasons": []},
                "blocked with no reasons",
            ),
            "blocked with a missing reasons array": (
                {"status": "blocked", "reasons": None},
                "blocked with no reasons",
            ),
            "blocked with an empty reason": (
                {"status": "blocked", "reasons": [""]},
                "empty or non-string blocked reason",
            ),
            "blocked with a non-string reason": (
                {"status": "blocked", "reasons": [7]},
                "empty or non-string blocked reason",
            ),
            "failed": ({"status": "failed"}, "status is 'failed'"),
            "unknown status": ({"status": "skipped"}, "status is 'skipped'"),
        }
        for label, (overrides, expected) in cases.items():
            with self.subTest(case=label):
                errors = fleet.validate_candidate_ledger(
                    ledger(**overrides),
                    consumers=consumers,
                    expected_version="1.2.3",
                    expected_payload_digest="sha256:payload",
                    expected_fleet_digest="sha256:fleet",
                    expected_validator_digest="sha256:validator",
                )
                if expected is None:
                    self.assertEqual(errors, [], label)
                else:
                    self.assertTrue(
                        any(expected in error for error in errors),
                        f"{label}: {errors}",
                    )


if __name__ == "__main__":
    unittest.main()
