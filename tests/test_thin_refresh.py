"""Ordinary `install.py TARGET` against a converted consumer (step 9b).

R19-C1's refusal was fail-closed and never the end state. `sd-fleet-refresh`
runs exactly this command against every consumer, so for as long as it
refused, a converted consumer could not receive a pack update at all -- which
means it could not receive a security fix. Nothing was converted yet, which is
the only reason refusing was survivable.

The property under test is narrow on purpose: a refresh updates the *version*
and nothing else. Every way of asking it to also change what is installed is a
conversion decision -- made against a resweep verdict, in a reviewed PR -- not
a side effect of a fleet-wide sweep.
"""

from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
mock = _support.mock
unittest = _support.unittest
Path = _support.Path
install = _support.install
InstallTestCase = _support.InstallTestCase

from installer import conversion, thin  # noqa: E402
from installer.provenance import PIN_KEYS  # noqa: E402


class RefreshFixture(InstallTestCase):
    def setUp(self) -> None:
        self.root = self.make_repo(".claude")
        self.assertEqual(self.run_install(self.root).returncode, 0)
        self.convert()

    def convert(self) -> None:
        manifest_data, files = install.load_manifest()
        receipt = conversion.read_installed_targets_receipt(self.root)
        partition = conversion.load_partition(
            _support.PACK_ROOT / install.SURFACE_PARTITION_FILE
        )
        plan = conversion.build_conversion_plan(
            receipt,
            partition,
            frozenset({"claude"}),
            occupied=conversion.occupied_receipt_targets(self.root, receipt),
        )
        self.assertEqual(plan.blocked, ())
        settings, reason = thin.plan_settings_merge(
            self.root / thin.CLAUDE_SETTINGS_FILE, "sd-ai-command-pack", "sd"
        )
        self.assertIsNone(reason)
        provenance_files = install.read_existing_provenance_files(self.root)
        with mock.patch.object(thin, "flip_registry_mode"):
            thin.apply_conversion(
                _support.PACK_ROOT,
                self.root,
                plan=plan,
                settings=settings,
                manifest_data=manifest_data,
                residual=frozenset(plan.keep) | frozenset(plan.receipts),
                existing_files=provenance_files,
                platforms=("claude",),
                consumer="demo",
                forced=(),
                files_by_target={file.target.as_posix(): file for file in files},
                provenance_files=provenance_files,
                force=False,
                backup=False,
            )
        self.plan = plan

    def provenance(self) -> dict:
        return json.loads(
            (self.root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )

    def rewind_version(self, version: str = "0.0.1") -> None:
        """Make the consumer look a version behind, in both receipts."""
        for receipt in (install.PROVENANCE_FILE, install.PACK_MANIFEST_FILE):
            path = self.root / receipt
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["version"] = version
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class ThinRefreshTests(RefreshFixture):
    def test_a_converted_consumer_refreshes_to_the_new_version(self) -> None:
        self.rewind_version()
        before = self.provenance()["settingsAdditions"]

        result = self.run_install(self.root)
        self.assertEqual(result.returncode, 0, result.stdout)

        after = self.provenance()
        self.assertEqual(after["version"], install.load_manifest()[0]["version"])
        self.assertEqual(after["mode"], conversion.THIN_MODE)
        self.assertEqual(after["settingsAdditions"], before)
        self.assertEqual(after["consumer"], "demo")
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_THIN
        )

    def test_the_machine_payload_is_not_re_created(self) -> None:
        # The whole point. A refresh that reinstalled the deleted surfaces
        # would silently de-thin every converted consumer in the fleet, while
        # the registry went on saying `thin`.
        self.rewind_version()
        self.assertEqual(self.run_install(self.root).returncode, 0)
        for entry in self.plan.delete:
            self.assertFalse((self.root / entry).exists(), f"{entry} came back")

    def test_the_stripped_gitignore_block_is_not_reinstalled(self) -> None:
        # Its entries ignore machine surfaces that no longer live here, and
        # reinstalling it would relist .gitignore as an installed target --
        # making every later inspection report a pending change.
        self.rewind_version()
        self.assertEqual(self.run_install(self.root).returncode, 0)
        installed = (self.root / install.INSTALLED_TARGETS_FILE).read_text(
            encoding="utf-8"
        ).split()
        self.assertNotIn(".gitignore", installed)

    def test_both_thin_witnesses_survive_the_refresh(self) -> None:
        # `thin_pin_state` reads the installed manifest first, so a refresh
        # that carried the pin into provenance alone would leave the earlier
        # witness saying fat and the two receipts disagreeing.
        self.rewind_version()
        self.assertEqual(self.run_install(self.root).returncode, 0)
        manifest = json.loads(
            (self.root / install.PACK_MANIFEST_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["mode"], conversion.THIN_MODE)
        self.assertIsNone(thin.receipt_disagreement_reason(self.root))

    def test_the_refreshed_consumer_reports_current(self) -> None:
        self.rewind_version()
        self.assertEqual(self.run_install(self.root).returncode, 0)
        check = self.run_install(self.root, "--check", "--json")
        self.assertEqual(check.returncode, 0, check.stdout)
        self.assertEqual(json.loads(check.stdout)["state"], "current")

    def test_a_second_refresh_changes_nothing(self) -> None:
        self.rewind_version()
        self.assertEqual(self.run_install(self.root).returncode, 0)
        first = (self.root / install.PROVENANCE_FILE).read_bytes()
        self.assertEqual(self.run_install(self.root).returncode, 0)
        self.assertEqual((self.root / install.PROVENANCE_FILE).read_bytes(), first)

    def test_the_retired_record_survives_a_refresh(self) -> None:
        # R20-C2's list is what revert reports as unrestorable. A refresh that
        # dropped it would silently convert "these two files cannot come back"
        # into "everything came back".
        payload = self.provenance()
        payload["retired"] = ["docs/legacy/retired-guide.md"]
        payload["version"] = "0.0.1"
        (self.root / install.PROVENANCE_FILE).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        manifest_path = self.root / install.PACK_MANIFEST_FILE
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = "0.0.1"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

        self.assertEqual(self.run_install(self.root).returncode, 0)
        self.assertEqual(
            self.provenance()["retired"], ["docs/legacy/retired-guide.md"]
        )


class ThinRefreshRejectionTests(RefreshFixture):
    def assert_rejected(self, result, fragment: str) -> None:
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn(fragment, result.stdout)
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_THIN
        )

    def test_platform_is_rejected_because_the_pin_owns_the_platform_set(self) -> None:
        # Silently re-deriving the residual from a different platform set is
        # how a refresh becomes an unreviewed conversion.
        self.assert_rejected(
            self.run_install(self.root, "--platform", "claude"),
            "owned by its pin",
        )

    def test_all_is_rejected_for_the_same_reason(self) -> None:
        self.assert_rejected(self.run_install(self.root, "--all"), "owned by its pin")

    def test_local_only_is_rejected(self) -> None:
        self.assert_rejected(
            self.run_install(self.root, "--local-only"), "--local-only"
        )

    def test_remove_still_refuses(self) -> None:
        # `--remove` has no thin form: it would delete provenance and leave
        # the plugin enabled and the registry saying `thin`.
        result = self.run_install(self.root, "--remove")
        self.assert_rejected(result, "--revert-thin")
        self.assertTrue((self.root / install.PROVENANCE_FILE).is_file())

    def test_a_pin_with_no_usable_platforms_refuses_rather_than_widening(self) -> None:
        payload = self.provenance()
        payload["platforms"] = ["claude", 7]
        (self.root / install.PROVENANCE_FILE).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        result = self.run_install(self.root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("--check", result.stdout)
        self.assertFalse((self.root / ".claude/commands/sd/check.md").exists())

    def test_a_pin_the_partition_cannot_classify_never_reinstalls_the_payload(
        self,
    ) -> None:
        # The backstop behind `_thin_refresh_rejection`. This pin is
        # well-formed enough to pass every rejection above -- it is `thin`,
        # and its platform list is non-empty -- but the partition cannot
        # classify one of its platforms, so the residual it describes cannot
        # be derived. The fallback for an untrusted pin is the *full* payload,
        # which here would silently reinstall every machine surface the
        # conversion deleted and de-thin the consumer while the registry still
        # reads thin. It has to refuse instead.
        payload = self.provenance()
        payload["platforms"] = ["claude", "not-a-platform"]
        (self.root / install.PROVENANCE_FILE).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

        result = self.run_install(self.root)

        self.assertEqual(result.returncode, 2, result.stdout)
        # The backstop's wording, not `_thin_refresh_rejection`'s: both say
        # "cannot be read against the surface partition", and only the
        # rejection above adds the residual clause. Asserting the shared
        # fragment alone would pass while this path was never reached.
        self.assertIn("cannot be read against", result.stdout)
        self.assertNotIn("the residual to refresh is unknown", result.stdout)
        self.assertFalse((self.root / ".claude/commands/sd/check.md").exists())
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_THIN
        )

    def test_a_malformed_pin_still_refuses_in_both_directions(self) -> None:
        payload = self.provenance()
        del payload["mode"]
        (self.root / install.PROVENANCE_FILE).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        (self.root / install.PACK_MANIFEST_FILE).write_text(
            json.dumps({"name": "sd-ai-command-pack", "version": "0.0.1"}, indent=2),
            encoding="utf-8",
        )
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_MALFORMED
        )
        result = self.run_install(self.root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("cannot be read against", result.stdout)


class FatRefreshUnchangedTests(InstallTestCase):
    def test_a_fat_consumers_refresh_is_untouched(self) -> None:
        # The regression this step could most easily cause: the thin branch
        # sits inside the one code path every consumer in the fleet runs.
        root = self.make_repo(".claude")
        self.assertEqual(self.run_install(root).returncode, 0)
        before = (root / install.PROVENANCE_FILE).read_bytes()
        again = self.run_install(root)
        self.assertEqual(again.returncode, 0, again.stdout)
        self.assertEqual((root / install.PROVENANCE_FILE).read_bytes(), before)
        payload = json.loads(before.decode("utf-8"))
        for key in PIN_KEYS:
            self.assertNotIn(key, payload, "a fat receipt grew a pin key")
        self.assertTrue((root / ".gitignore").is_file())


if __name__ == "__main__":
    unittest.main()
