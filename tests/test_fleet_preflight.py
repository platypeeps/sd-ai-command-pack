from __future__ import annotations

import shlex

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
install = _support.install


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

    def test_read_installed_version_treats_malformed_utf8_as_unreadable(self) -> None:
        fleet = self.load_fleet_module()

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            provenance = root / ".sd-ai-command-pack/provenance.json"
            provenance.parent.mkdir(parents=True)
            provenance.write_bytes(b'{"version": "\xff"}\n')

            self.assertIsNone(fleet.read_installed_version(root))

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
                "platypeeps/people-profiles",
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
            "platypeeps/people-profiles": (),
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
                "people-profiles",
                "anomaly-metric-creator",
            ],
        )
        self.assertEqual(
            [consumer.rollout_priority for consumer in consumers],
            [10, 20, 30, 40, 50, 60, 70, 80, 90],
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
                ("people-profiles", "anomaly-metric-creator"),
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


class ThinFleetPreflightTests(InstallTestCase):
    """R20-C6: a converted consumer at target is not self-evidently healthy.

    Version equality is the fat contract's evidence of health. It does not
    carry over: on a fat checkout the install audit's manifest-derived
    completeness check sees a deleted surface, and a thin install skips that
    check on purpose, because for a converted consumer the receipt *is* the
    allowlist. A residual file that went missing and a machine surface the
    conversion removed look identical to everything else in the sweep, so if
    preflight skips on version alone the damage is never routed anywhere.
    """

    # Same loader and identity stub as the fat suite above; the module under
    # test is one file and its release-identity gate is not what changed.
    load_fleet_module = FleetPreflightTests.load_fleet_module
    verified_identity = FleetPreflightTests.verified_identity

    def make_consumer(self, fleet, root: Path, *, name: str = "converted"):
        return fleet.FleetConsumer(
            name=name,
            github=f"example/{name}",
            path_hint=str(root),
            # Deliberately wider than the pin below: the registry records what
            # the consumer was converted *from*.
            platforms=("claude", "codex"),
            rollout_priority=10,
            candidate_timeout_seconds=60,
            candidate_prepare=(),
            candidate_checks=(),
        )

    def write_consumer(
        self,
        root: Path,
        *,
        version: str = "0.8.5",
        thin: bool = True,
        pinned_platforms: list | None = None,
        targets: tuple[str, ...] = ("docs/SD_AI_COMMAND_PACK.md",),
        create: bool = True,
    ) -> None:
        receipts = root / ".sd-ai-command-pack"
        receipts.mkdir(parents=True, exist_ok=True)
        payload: dict = {"pack": "sd-ai-command-pack", "version": version}
        if thin:
            payload["mode"] = "thin"
            payload["platforms"] = (
                ["claude"] if pinned_platforms is None else pinned_platforms
            )
        payload["files"] = {}
        (receipts / "provenance.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        recorded = (*targets, ".sd-ai-command-pack/installed-targets.txt")
        (receipts / "installed-targets.txt").write_text(
            "\n".join(sorted(recorded)) + "\n", encoding="utf-8"
        )
        if not create:
            return
        for entry in targets:
            path = root / entry
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("payload\n", encoding="utf-8")

    def preflight(self, fleet, root: Path, **kwargs):
        self.write_consumer(root, **kwargs)
        return fleet.preflight_consumer(
            self.make_consumer(fleet, root), target_version="0.8.5"
        )

    def temp_root(self, name: str = "consumer") -> Path:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-thin-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / name
        root.mkdir()
        return root

    def test_an_intact_thin_consumer_at_target_is_still_skipped(self) -> None:
        # The cost of the fix has to stay zero for a healthy fleet: every
        # converted consumer turning into a permanent non-at-target row would
        # make --fail-on-refresh-needed useless.
        fleet = self.load_fleet_module()
        result = self.preflight(fleet, self.temp_root())

        self.assertEqual(result.status, "at-target")
        self.assertEqual(result.mode, "thin")
        self.assertEqual(result.installed_platforms, ("claude",))

    def test_a_thin_consumer_missing_a_recorded_target_is_routed_to_repair(
        self,
    ) -> None:
        fleet = self.load_fleet_module()
        result = self.preflight(fleet, self.temp_root(), create=False)

        self.assertEqual(result.status, "residual-damaged")
        self.assertEqual(result.installed_version, "0.8.5")
        self.assertIn("docs/SD_AI_COMMAND_PACK.md", result.detail)
        self.assertIn("1 recorded target(s) are missing", result.detail)

    def test_a_fat_consumer_is_still_judged_on_version_alone(self) -> None:
        # The asymmetry is deliberate, not an oversight: a fat consumer's
        # missing file is caught by the audit's completeness check on the next
        # sweep that reaches it, and widening the stat to every consumer would
        # change the routing of the whole fleet under a thin-mode finding.
        fleet = self.load_fleet_module()
        result = self.preflight(fleet, self.temp_root(), thin=False, create=False)

        self.assertEqual(result.status, "at-target")
        self.assertIsNone(result.mode)

    def test_the_detail_names_a_sample_and_counts_the_rest(self) -> None:
        fleet = self.load_fleet_module()
        result = self.preflight(
            fleet,
            self.temp_root(),
            targets=tuple(f"docs/gone-{index}.md" for index in range(6)),
            create=False,
        )

        self.assertIn("6 recorded target(s) are missing", result.detail)
        self.assertIn("+3 more", result.detail)
        self.assertNotIn("docs/gone-5.md", result.detail)

    def test_a_receipt_entry_outside_the_checkout_is_never_followed(self) -> None:
        # A receipt is consumer-side content and preflight walks a whole
        # fleet. Neither entry exists, so a reader that resolved them would
        # report the consumer damaged; at-target is the proof they were
        # skipped rather than stat'ed outside the tree it was handed.
        fleet = self.load_fleet_module()
        root = self.temp_root()
        result = self.preflight(
            fleet,
            root,
            targets=("/etc/sd-ai-command-pack-absent", "../outside-absent.md"),
            create=False,
        )

        self.assertEqual(result.status, "at-target")
        self.assertFalse((root.parent / "outside-absent.md").exists())

    def test_a_recorded_target_that_resolves_outside_is_never_stated(self) -> None:
        # Textual containment is not enough: `docs/gone.md` has no `..` and is
        # not absolute, yet it lands outside the checkout the moment `docs` is
        # a link. `exists()` follows it, so before the resolved-path guard this
        # consumer was routed to repair on the strength of a stat taken in
        # somebody else's directory. The outside directory is real and the file
        # inside it is not, which is what makes at-target the discriminator:
        # a reader that follows the link sees False and reports damage.
        fleet = self.load_fleet_module()
        root = self.temp_root()
        self.write_consumer(root, targets=("docs/gone.md",), create=False)
        outside = root.parent / "outside-tree"
        outside.mkdir()
        (root / "docs").symlink_to(outside, target_is_directory=True)

        self.assertEqual(fleet.missing_recorded_targets(root), ())
        result = fleet.preflight_consumer(
            self.make_consumer(fleet, root), target_version="0.8.5"
        )
        self.assertEqual(result.status, "at-target")
        self.assertFalse((outside / "gone.md").exists())

    def test_the_printed_repair_command_is_one_a_thin_consumer_accepts(self) -> None:
        # The headline check. A repair command that a thin-aware refresh
        # rejects is worse than no repair command: the operator runs it, gets
        # exit 2, and the consumer stays damaged.
        fleet = self.load_fleet_module()
        result = self.preflight(fleet, self.temp_root(), create=False)
        command = fleet.install_command(result)

        self.assertNotIn("--platform", command)
        pinned = mock.Mock()
        pinned.platforms = frozenset({"claude"})
        printed = install.parse_args(shlex.split(command)[2:])
        self.assertIsNone(install._thin_refresh_rejection(printed, pinned))

        # And the registry-shaped command this replaces really is rejected --
        # otherwise the assertion above passes for a command that never had a
        # problem.
        registry_shaped = install.parse_args(
            [*shlex.split(command)[2:], "--platform", "claude", "--platform", "codex"]
        )
        self.assertIn(
            "owned by its pin",
            install._thin_refresh_rejection(registry_shaped, pinned) or "",
        )

    def test_a_fat_consumers_command_still_carries_the_registry_platforms(self) -> None:
        fleet = self.load_fleet_module()
        result = self.preflight(fleet, self.temp_root(), thin=False, version="0.7.0")

        command = fleet.install_command(result)
        self.assertIn("--platform claude", command)
        self.assertIn("--platform codex", command)

    def test_a_malformed_pin_keeps_the_fat_contract(self) -> None:
        fleet = self.load_fleet_module()
        root = self.temp_root()
        self.write_consumer(root)
        provenance = root / ".sd-ai-command-pack/provenance.json"
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        payload["platforms"] = "claude"
        provenance.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

        mode, platforms = fleet.read_installed_mode(root)
        self.assertEqual(mode, "thin")
        self.assertEqual(platforms, ())

    def test_an_unreadable_receipt_reports_no_recorded_targets(self) -> None:
        fleet = self.load_fleet_module()
        root = self.temp_root()
        self.write_consumer(root)
        (root / ".sd-ai-command-pack/installed-targets.txt").write_bytes(b"\xff\n")

        self.assertEqual(fleet.read_recorded_targets(root), ())

    def test_a_symlinked_provenance_is_refused_rather_than_followed(self) -> None:
        # Preflight walks a fleet of checkouts it did not write, so a receipt
        # that is a link is a way out of the one it was handed. The link here
        # points at a perfectly legible thin pin: every assertion below fails
        # if the reader resolves it, and none of them can be satisfied by an
        # unreadable file, which is the other way to reach an empty result.
        fleet = self.load_fleet_module()
        root = self.temp_root()
        self.write_consumer(root)
        outside = root.parent / "outside-provenance.json"
        outside.write_text(
            json.dumps(
                {
                    "pack": "sd-ai-command-pack",
                    "version": "9.9.9",
                    "mode": "thin",
                    "platforms": ["claude"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        provenance = root / ".sd-ai-command-pack/provenance.json"
        provenance.unlink()
        provenance.symlink_to(outside)

        self.assertEqual(fleet.read_provenance(root), {})
        self.assertIsNone(fleet.read_installed_version(root))
        self.assertEqual(fleet.read_installed_mode(root), (None, ()))

    def test_a_symlinked_install_receipt_is_refused_rather_than_followed(self) -> None:
        # The same refusal, and more is riding on it: every line this reader
        # returns becomes a filesystem probe, so a followed link would aim
        # those probes with content from outside the checkout.
        fleet = self.load_fleet_module()
        root = self.temp_root()
        self.write_consumer(root)
        outside = root.parent / "outside-targets.txt"
        outside.write_text("docs/SD_AI_COMMAND_PACK.md\n", encoding="utf-8")
        receipt = root / ".sd-ai-command-pack/installed-targets.txt"
        receipt.unlink()
        receipt.symlink_to(outside)

        self.assertEqual(fleet.read_recorded_targets(root), ())

    def test_the_manifest_witness_alone_still_marks_the_consumer_thin(self) -> None:
        # A half-converted consumer: the installed manifest survived, the pin
        # in provenance lost its mode. `thin_pin_state` reads the manifest
        # first and calls this thin, so a thin-aware refresh rejects
        # `--platform` -- and a preflight that read provenance alone would
        # print exactly that flag, handing the operator a command guaranteed
        # to exit 2 on the one consumer that most needs repairing.
        fleet = self.load_fleet_module()
        root = self.temp_root()
        self.write_consumer(root, create=False)
        provenance = root / ".sd-ai-command-pack/provenance.json"
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        del payload["mode"]
        provenance.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        (root / ".sd-ai-command-pack/manifest.json").write_text(
            json.dumps({"version": "0.8.5", "mode": "thin"}, indent=2) + "\n",
            encoding="utf-8",
        )

        self.assertEqual(fleet.read_installed_mode(root), ("thin", ("claude",)))
        result = fleet.preflight_consumer(
            self.make_consumer(fleet, root), target_version="0.8.5"
        )
        self.assertEqual(result.mode, "thin")
        self.assertEqual(result.status, "residual-damaged")

        command = fleet.install_command(result)
        self.assertNotIn("--platform", command)
        pinned = mock.Mock()
        pinned.platforms = frozenset({"claude"})
        printed = install.parse_args(shlex.split(command)[2:])
        self.assertIsNone(install._thin_refresh_rejection(printed, pinned))

    def write_single_consumer_fleet(self, root: Path) -> tuple[Path, Path]:
        fleet_manifest = root.parent / "fleet.json"
        fleet_manifest.write_text(
            json.dumps(
                fleet_manifest_payload(
                    [
                        {
                            "name": "converted",
                            "github": "example/converted",
                            "pathHint": str(root),
                            "platforms": ["claude", "codex"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [["bash", "prepare.sh"]],
                            "candidateChecks": [["bash", "check.sh"]],
                        }
                    ]
                )
            )
            + "\n",
            encoding="utf-8",
        )
        pack_manifest = root.parent / "manifest.json"
        pack_manifest.write_text('{"version": "0.8.5"}\n', encoding="utf-8")
        return fleet_manifest, pack_manifest

    def run_main(self, fleet, root: Path, *extra: str) -> tuple[int, str]:
        fleet_manifest, pack_manifest = self.write_single_consumer_fleet(root)
        argv = [
            "sd-ai-command-pack-fleet-preflight.py",
            "--fleet",
            str(fleet_manifest),
            "--manifest",
            str(pack_manifest),
            *extra,
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
        return exit_code, output.getvalue()

    def test_the_row_and_exit_code_report_a_damaged_residual(self) -> None:
        fleet = self.load_fleet_module()
        root = self.temp_root()
        self.write_consumer(root, create=False)

        exit_code, text = self.run_main(fleet, root, "--fail-on-refresh-needed")
        self.assertEqual(exit_code, 1, text)
        self.assertIn("residual-damaged", text)
        self.assertIn("mode: thin", text)
        # The pinned set, not the registry's: a row printing `codex` reads as
        # though those surfaces are installed here.
        self.assertIn("platforms: claude)", text)
        self.assertIn("install: python3 install.py", text)
        self.assertNotIn("--platform", text)

    def test_the_json_row_carries_the_mode_and_pinned_platforms(self) -> None:
        # The rollout controller reads the JSON, not the text rows: without
        # these two keys it cannot tell a converted consumer from a fat one.
        fleet = self.load_fleet_module()
        root = self.temp_root()
        self.write_consumer(root)

        exit_code, output = self.run_main(fleet, root, "--json")

        self.assertEqual(exit_code, 0, output)
        row = json.loads(output)["consumers"][0]
        self.assertEqual(row["status"], "at-target")
        self.assertEqual(row["mode"], "thin")
        self.assertEqual(row["installedPlatforms"], ["claude"])
        self.assertEqual(row["platforms"], ["claude", "codex"])


if __name__ == "__main__":
    unittest.main()
