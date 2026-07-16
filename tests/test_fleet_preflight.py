from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
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
                {
                    "schemaVersion": 1,
                    "consumers": [
                        {
                            "name": "at-target",
                            "github": "example/at-target",
                            "pathHint": str(at_target),
                            "platforms": ["claude", "github"],
                        },
                        {
                            "name": "outdated",
                            "github": "example/outdated",
                            "pathHint": str(outdated),
                            "platforms": ["claude", "github"],
                        },
                        {
                            "name": "missing",
                            "github": "example/missing",
                            "pathHint": str(missing),
                            "platforms": ["claude", "github"],
                        },
                    ],
                }
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
                "answerbook/mezmo_benchmark",
            },
        )
        for consumer in by_slug.values():
            self.assertNotIn("cursor", consumer.platforms)
            self.assertIn("claude", consumer.platforms)
            self.assertIn("gemini", consumer.platforms)
            self.assertIn("github", consumer.platforms)
            self.assertIn("opencode", consumer.platforms)

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

    def test_main_prints_json_output(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest, pack_manifest = self.write_fleet_fixture(root)
        output = io.StringIO()

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
        self.assertEqual(
            [item["name"] for item in payload],
            ["at-target", "outdated", "missing"],
        )
        self.assertEqual(payload[0]["status"], "at-target")
        self.assertEqual(payload[1]["installedVersion"], "0.7.0")
        self.assertEqual(payload[2]["status"], "missing-local-clone")
        self.assertEqual(payload[0]["targetVersion"], "0.8.5")

    def test_main_rejects_unknown_consumer(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest, pack_manifest = self.write_fleet_fixture(root)

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

    def test_subprocess_text_output_and_fail_on_refresh_needed(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest, pack_manifest = self.write_fleet_fixture(root)
        command = [
            sys.executable,
            str(PACK_ROOT / "scripts/sd-ai-command-pack-fleet-preflight.py"),
            "--fleet",
            str(fleet_manifest),
            "--manifest",
            str(pack_manifest),
        ]

        text_result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(text_result.returncode, 0, text_result.stdout)
        self.assertIn("sd-ai-command-pack fleet target: 0.8.5", text_result.stdout)
        self.assertIn("at-target", text_result.stdout)
        self.assertIn("refresh-needed", text_result.stdout)
        self.assertIn("missing-local-clone", text_result.stdout)
        self.assertIn("install: python3 install.py", text_result.stdout)
        self.assertIn("--platform claude", text_result.stdout)
        self.assertIn("audit:   python3 scripts/sd-ai-command-pack-install-audit.py", text_result.stdout)

        fail_result = subprocess.run(
            [*command, "--fail-on-refresh-needed"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(fail_result.returncode, 1, fail_result.stdout)
        self.assertIn("refresh-needed", fail_result.stdout)

    def test_fleet_manifest_rejects_duplicate_consumer_platforms(self) -> None:
        fleet = self.load_fleet_module()
        tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-preflight-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        fleet_manifest = root / "fleet.json"
        fleet_manifest.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "consumers": [
                        {
                            "name": "duplicate",
                            "github": "example/duplicate",
                            "pathHint": "~/repos/example/duplicate",
                            "platforms": ["github", "github"],
                        },
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(SystemExit) as error:
            fleet.load_fleet_consumers(fleet_manifest)

        self.assertIn("repeats platform github", str(error.exception))


if __name__ == "__main__":
    unittest.main()
