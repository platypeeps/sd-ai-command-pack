from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
fleet_manifest_payload = _support.fleet_manifest
Path = _support.Path
contextlib = _support.contextlib
io = _support.io
mock = _support.mock
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase


class FleetPreflightTests(InstallTestCase):
    """Tests for source-owned fleet inventory and refresh preflight."""

    def load_fleet_module(self):
        return self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-fleet-preflight.py",
            "sd_ai_command_pack_fleet_preflight",
        )

    def write_provenance(self, root: Path, version: str) -> None:
        provenance = root / ".sd-ai-command-pack/provenance.json"
        provenance.parent.mkdir(parents=True, exist_ok=True)
        provenance.write_text(
            json.dumps(
                {
                    "pack": "sd-ai-command-pack",
                    "version": version,
                    "files": {"scripts/sd-ai-command-pack-full-check.sh": "sha256:0"},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def verified_identity(self, fleet, version: str = "0.8.5"):
        identity = mock.Mock()
        identity.status = "verified"
        identity.version = version
        identity.tag = f"v{version}"
        identity.commit_sha = "1" * 40
        identity.payload_digest = "sha256:" + "2" * 64
        identity.as_json.return_value = {
            "status": identity.status,
            "version": identity.version,
            "tag": identity.tag,
            "commit": identity.commit_sha,
            "payloadDigest": identity.payload_digest,
        }
        return identity

    def write_fleet_fixture(self, root: Path) -> tuple[Path, Path]:
        at_target = root / "at-target"
        outdated = root / "outdated"
        missing = root / "missing"
        at_target.mkdir()
        outdated.mkdir()
        self.write_provenance(at_target, "0.8.5")
        self.write_provenance(outdated, "0.7.0")

        fleet_manifest = root / "fleet.json"
        fleet_manifest.write_text(
            json.dumps(
                fleet_manifest_payload(
                    [
                        {
                            "name": "at-target",
                            "github": "example/at-target",
                            "pathHint": str(at_target),
                            "platforms": ["claude", "github"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [["bash", "prepare.sh"]],
                            "candidateChecks": [["node", "check.mjs"]],
                        },
                        {
                            "name": "outdated",
                            "github": "example/outdated",
                            "pathHint": str(outdated),
                            "platforms": ["claude", "github"],
                            "rolloutPriority": 20,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [["bash", "prepare-outdated.sh"]],
                            "candidateChecks": [["bash", "check.sh"]],
                        },
                        {
                            "name": "missing",
                            "github": "example/missing",
                            "pathHint": str(missing),
                            "platforms": ["claude", "github"],
                            "rolloutPriority": 30,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [["python3", "prepare.py"]],
                            "candidateChecks": [["python3", "check.py"]],
                        },
                    ]
                )
            )
            + "\n",
            encoding="utf-8",
        )
        pack_manifest = root / "manifest.json"
        pack_manifest.write_text('{"version": "0.8.5"}\n', encoding="utf-8")
        return fleet_manifest, pack_manifest

    def test_checked_in_fleet_manifest_lists_real_consumers(self) -> None:
        fleet = self.load_fleet_module()

        consumers = fleet.load_fleet_consumers(PACK_ROOT / "docs/fleet/consumers.json")
        by_slug = {consumer.github: consumer for consumer in consumers}

        self.assertEqual(
            set(by_slug),
            {
                "platypeeps/anomaly-metric-creator",
                "platypeeps/hoa-manager",
                "platypeeps/loadsmith",
                "platypeeps/rwbp-coordinator",
                "platypeeps/rwbp-website",
                "platypeeps/sd-github-review",
                "platypeeps/se-ai-command-pack",
                "answerbook/mezmo_benchmark",
            },
        )
        for consumer in by_slug.values():
            self.assertNotIn("cursor", consumer.platforms)
            self.assertIn("claude", consumer.platforms)
            self.assertIn("gemini", consumer.platforms)
            self.assertIn("github", consumer.platforms)
            self.assertIn("opencode", consumer.platforms)

        expected_map_prepare = (("bash", "scripts/update_repomix"),)
        expected_prepares = {
            "answerbook/mezmo_benchmark": expected_map_prepare,
            "platypeeps/anomaly-metric-creator": expected_map_prepare,
            "platypeeps/hoa-manager": expected_map_prepare,
            "platypeeps/loadsmith": expected_map_prepare,
            "platypeeps/rwbp-coordinator": expected_map_prepare,
            "platypeeps/rwbp-website": expected_map_prepare,
            "platypeeps/sd-github-review": (("npm", "ci"),),
            "platypeeps/se-ai-command-pack": (),
        }
        for name, consumer in by_slug.items():
            expected_prepare = expected_prepares.get(name)
            self.assertIsNotNone(
                expected_prepare,
                f"missing candidate preparation expectation for {name}",
            )
            self.assertEqual(consumer.candidate_prepare, expected_prepare)

        github_review = by_slug["platypeeps/sd-github-review"]
        self.assertEqual(github_review.path_hint, "~/repos/platypeeps/sd-github-review")
        self.assertEqual(
            github_review.platforms,
            ("claude", "gemini", "github", "opencode"),
        )
        self.assertEqual(github_review.candidate_timeout_seconds, 180)
        self.assertEqual(
            github_review.candidate_checks,
            (
                ("npm", "test"),
                ("npm", "run", "check"),
                ("npm", "run", "validate:metadata"),
            ),
        )

        self.assertEqual(
            [consumer.name for consumer in consumers],
            [
                "rwbp-coordinator",
                "loadsmith",
                "hoa-manager",
                "rwbp-website",
                "mezmo_benchmark",
                "se-ai-command-pack",
                "sd-github-review",
                "anomaly-metric-creator",
            ],
        )
        self.assertEqual(
            [consumer.rollout_priority for consumer in consumers],
            [10, 20, 30, 40, 50, 60, 70, 90],
        )

        rollout_policy = fleet.fleet_lib.load_fleet_rollout_policy(
            PACK_ROOT / "docs/fleet/consumers.json"
        )
        self.assertEqual(
            [cohort.name for cohort in rollout_policy.cohorts],
            ["canary", "post-canary", "final"],
        )
        self.assertEqual(
            [cohort.consumers for cohort in rollout_policy.cohorts],
            [
                ("rwbp-coordinator", "loadsmith", "hoa-manager"),
                (
                    "rwbp-website",
                    "mezmo_benchmark",
                    "se-ai-command-pack",
                    "sd-github-review",
                ),
                ("anomaly-metric-creator",),
            ],
        )
        self.assertEqual(rollout_policy.cohorts[1].max_concurrency, 2)
        self.assertEqual(rollout_policy.cohorts[-1].strategy, "sequential")

        manifest_text = (PACK_ROOT / "docs/fleet/consumers.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("/Users/", manifest_text)
        self.assertIn("green-button-manager", manifest_text)
        self.assertIn("trellis-review-pr-pack", manifest_text)

    def test_preflight_skips_at_target_and_flags_refresh_needed(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest, pack_manifest = self.write_fleet_fixture(root)

        consumers = fleet.load_fleet_consumers(fleet_manifest)
        target_version = fleet.pack_version(pack_manifest)
        results = {
            result.consumer.name: result
            for result in (
                fleet.preflight_consumer(
                    consumer,
                    target_version=target_version,
                )
                for consumer in consumers
            )
        }

        self.assertEqual(results["at-target"].status, "at-target")
        self.assertEqual(results["outdated"].status, "refresh-needed")
        self.assertEqual(results["outdated"].installed_version, "0.7.0")
        self.assertEqual(results["missing"].status, "missing-local-clone")
        self.assertIn("--expected-platform claude", fleet.audit_command(results["outdated"]))
        self.assertIn("--platform claude", fleet.install_command(results["outdated"]))

    def test_prepare_commands_are_scoped_to_the_consumer_checkout(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "repo with spaces"
        root.mkdir()
        consumer = fleet.FleetConsumer(
            name="prepared",
            github="example/prepared",
            path_hint=str(root),
            platforms=("claude",),
            rollout_priority=10,
            candidate_timeout_seconds=60,
            candidate_prepare=(("bash", "scripts/update map"),),
            candidate_checks=(),
        )
        result = fleet.FleetPreflightResult(
            consumer=consumer,
            repo_path=root,
            status="refresh-needed",
            installed_version="0.7.0",
            target_version="0.8.5",
            detail="refresh needed",
        )

        self.assertEqual(
            fleet.prepare_commands(result),
            [f"(cd '{root}' && bash 'scripts/update map')"],
        )

    def test_main_prints_json_output(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest, pack_manifest = self.write_fleet_fixture(root)
        output = io.StringIO()

        with mock.patch.object(
            fleet,
            "verify_release_identity",
            return_value=self.verified_identity(fleet),
        ):
            with mock.patch.object(
                sys,
                "argv",
                [
                    "sd-ai-command-pack-fleet-preflight.py",
                    "--fleet",
                    str(fleet_manifest),
                    "--manifest",
                    str(pack_manifest),
                    "--json",
                ],
            ):
                with contextlib.redirect_stdout(output):
                    exit_code = fleet.main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["releaseIdentity"]["status"], "verified")
        self.assertEqual(payload["releaseIdentity"]["tag"], "v0.8.5")
        consumers = payload["consumers"]
        self.assertEqual(
            [item["name"] for item in consumers],
            ["at-target", "outdated", "missing"],
        )
        self.assertEqual(consumers[0]["status"], "at-target")
        self.assertEqual(consumers[1]["installedVersion"], "0.7.0")
        self.assertEqual(consumers[2]["status"], "missing-local-clone")
        self.assertEqual(consumers[0]["targetVersion"], "0.8.5")
        self.assertEqual(consumers[0]["rolloutPriority"], 10)
        self.assertEqual(consumers[0]["candidatePrepare"], [["bash", "prepare.sh"]])
        self.assertEqual(consumers[0]["candidateChecks"], [["node", "check.mjs"]])

    def test_main_rejects_unknown_consumer(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest, pack_manifest = self.write_fleet_fixture(root)

        with mock.patch.object(
            fleet,
            "verify_release_identity",
            return_value=self.verified_identity(fleet),
        ):
            with mock.patch.object(
                sys,
                "argv",
                [
                    "sd-ai-command-pack-fleet-preflight.py",
                    "--fleet",
                    str(fleet_manifest),
                    "--manifest",
                    str(pack_manifest),
                    "--consumer",
                    "ghost",
                ],
            ):
                with self.assertRaises(SystemExit) as error:
                    fleet.main()

        self.assertIn("unknown fleet consumer(s): ghost", str(error.exception))

    def test_text_output_and_fail_on_refresh_needed(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest, pack_manifest = self.write_fleet_fixture(root)
        argv = [
            "sd-ai-command-pack-fleet-preflight.py",
            "--fleet",
            str(fleet_manifest),
            "--manifest",
            str(pack_manifest),
        ]

        output = io.StringIO()
        with mock.patch.object(
            fleet,
            "verify_release_identity",
            return_value=self.verified_identity(fleet),
        ):
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(output):
                    exit_code = fleet.main()

        text_output = output.getvalue()
        self.assertEqual(exit_code, 0, text_output)
        self.assertIn("release identity: verified v0.8.5", text_output)
        self.assertIn("sd-ai-command-pack fleet target: 0.8.5", text_output)
        self.assertIn("at-target", text_output)
        self.assertIn("refresh-needed", text_output)
        self.assertIn("missing-local-clone", text_output)
        self.assertIn("install: python3 install.py", text_output)
        self.assertIn("--platform claude", text_output)
        self.assertIn(
            "audit:   python3 scripts/sd-ai-command-pack-install-audit.py",
            text_output,
        )
        self.assertIn(
            f"prepare[1]: (cd {root / 'outdated'} && bash prepare-outdated.sh)",
            text_output,
        )

        fail_output = io.StringIO()
        with mock.patch.object(
            fleet,
            "verify_release_identity",
            return_value=self.verified_identity(fleet),
        ):
            with mock.patch.object(sys, "argv", [*argv, "--fail-on-refresh-needed"]):
                with contextlib.redirect_stdout(fail_output):
                    fail_code = fleet.main()

        self.assertEqual(fail_code, 1, fail_output.getvalue())
        self.assertIn("refresh-needed", fail_output.getvalue())

    def test_release_identity_failure_stops_before_consumer_inventory(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest, pack_manifest = self.write_fleet_fixture(root)
        error_output = io.StringIO()

        with mock.patch.object(
            fleet,
            "verify_release_identity",
            side_effect=fleet.ReleaseIdentityError(
                "local release tag refs/tags/v0.8.5 is missing; fetch tags and rerun"
            ),
        ):
            with mock.patch.object(fleet, "load_fleet_consumers") as load_consumers:
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "sd-ai-command-pack-fleet-preflight.py",
                        "--fleet",
                        str(fleet_manifest),
                        "--manifest",
                        str(pack_manifest),
                    ],
                ):
                    with contextlib.redirect_stderr(error_output):
                        exit_code = fleet.main()

        self.assertEqual(exit_code, 1)
        load_consumers.assert_not_called()
        self.assertIn("release identity error:", error_output.getvalue())
        self.assertIn("fetch tags and rerun", error_output.getvalue())

    def test_fleet_manifest_rejects_duplicate_consumer_platforms(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest = root / "fleet.json"
        fleet_manifest.write_text(
            json.dumps(
                fleet_manifest_payload(
                    [
                        {
                            "name": "duplicate",
                            "github": "example/duplicate",
                            "pathHint": "~/repos/example/duplicate",
                            "platforms": ["github", "github"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["node", "check.mjs"]],
                        },
                    ]
                )
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(SystemExit) as error:
            fleet.load_fleet_consumers(fleet_manifest)

        self.assertIn("repeats platform github", str(error.exception))

    def test_fleet_manifest_rejects_shell_string_candidate_check(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        fleet_manifest = Path(tempdir.name) / "fleet.json"
        fleet_manifest.write_text(
            json.dumps(
                fleet_manifest_payload(
                    [
                        {
                            "name": "unsafe",
                            "github": "example/unsafe",
                            "pathHint": "~/repos/example/unsafe",
                            "platforms": ["github"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": ["node check.mjs"],
                        }
                    ]
                )
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(SystemExit) as error:
            fleet.load_fleet_consumers(fleet_manifest)

        self.assertIn("must be a non-empty argv array", str(error.exception))

    def test_fleet_manifest_sorts_priority_independently_of_json_order(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest, _ = self.write_fleet_fixture(root)
        payload = json.loads(fleet_manifest.read_text(encoding="utf-8"))
        payload["consumers"].reverse()
        fleet_manifest.write_text(
            json.dumps(payload) + "\n",
            encoding="utf-8",
        )

        consumers = fleet.load_fleet_consumers(fleet_manifest)

        self.assertEqual(
            [consumer.name for consumer in consumers],
            ["at-target", "outdated", "missing"],
        )


if __name__ == "__main__":
    unittest.main()
