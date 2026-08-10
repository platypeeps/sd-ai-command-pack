"""Thin-aware `install.py --status` / `--check`.

A thin consumer is missing its machine surfaces on purpose. The whole point of
these tests is that exactly one predicate -- ``mode: "thin"`` in the provenance
receipt -- switches the inspection onto the residual comparison, and that every
fat consumer keeps the unchanged path.
"""

from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
tempfile = _support.tempfile
unittest = _support.unittest
mock = _support.mock
Path = _support.Path
InstallTestCase = _support.InstallTestCase

import install  # noqa: E402
from installer import inspection  # noqa: E402
from installer.conversion import (  # noqa: E402
    ThinReceipt,
    load_partition,
    read_thin_receipt,
    residual_source_files,
)
from installer.provenance import (  # noqa: E402
    PIN_KEYS,
    provenance_content,
    read_existing_provenance_pin,
)
from installer.registry import PROVENANCE_FILE, ROOT  # noqa: E402

THIN_PLATFORMS = ["claude", "gemini", "github", "opencode"]


def _temp_dir(case: unittest.TestCase) -> Path:
    handle = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-thin-")
    case.addCleanup(handle.cleanup)
    return Path(handle.name)


def write_provenance(target: Path, payload: object) -> Path:
    path = target / PROVENANCE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )
    return path


def thin_payload(**overrides: object) -> dict:
    payload = {
        "pack": "sd-ai-command-pack",
        "version": "1.2.3",
        "mode": "thin",
        "platforms": list(THIN_PLATFORMS),
        "consumer": "demo",
        "settingsAdditions": {"hooks": {}},
        "forced": ["AGENTS.md"],
        "files": {},
    }
    payload.update(overrides)
    return payload


class ReadThinReceiptTests(InstallTestCase):
    def setUp(self) -> None:
        self.target = _temp_dir(self)

    def test_absent_provenance_is_not_thin(self) -> None:
        self.assertIsNone(read_thin_receipt(self.target))

    def test_unparseable_provenance_is_not_thin(self) -> None:
        write_provenance(self.target, "{not json")
        self.assertIsNone(read_thin_receipt(self.target))

    def test_non_object_provenance_is_not_thin(self) -> None:
        write_provenance(self.target, [1, 2, 3])
        self.assertIsNone(read_thin_receipt(self.target))

    def test_fat_provenance_is_not_thin(self) -> None:
        write_provenance(self.target, {"pack": "p", "version": "1", "files": {}})
        self.assertIsNone(read_thin_receipt(self.target))

    def test_thin_provenance_reads_every_pinned_field(self) -> None:
        write_provenance(self.target, thin_payload())
        receipt = read_thin_receipt(self.target)
        self.assertTrue(receipt.is_thin)
        self.assertEqual(receipt.version, "1.2.3")
        self.assertEqual(receipt.platforms, frozenset(THIN_PLATFORMS))
        self.assertEqual(receipt.consumer, "demo")
        self.assertEqual(receipt.settings_additions, {"hooks": {}})
        self.assertEqual(receipt.forced, ("AGENTS.md",))

    def test_malformed_pin_fields_degrade_to_empty_rather_than_raising(self) -> None:
        write_provenance(
            self.target,
            thin_payload(
                version="   ",
                platforms="claude",
                consumer="",
                settingsAdditions=[],
                forced="AGENTS.md",
            ),
        )
        receipt = read_thin_receipt(self.target)
        self.assertTrue(receipt.is_thin)
        self.assertIsNone(receipt.version)
        self.assertEqual(receipt.platforms, frozenset())
        self.assertIsNone(receipt.consumer)
        self.assertEqual(receipt.settings_additions, {})
        self.assertEqual(receipt.forced, ())

    def test_non_string_version_is_dropped(self) -> None:
        write_provenance(self.target, thin_payload(version=7))
        self.assertIsNone(read_thin_receipt(self.target).version)

    def test_is_thin_is_false_for_another_mode(self) -> None:
        receipt = ThinReceipt(
            mode="fat",
            version=None,
            platforms=frozenset(),
            consumer=None,
            settings_additions={},
            forced=(),
        )
        self.assertFalse(receipt.is_thin)


class ProvenancePinTests(InstallTestCase):
    def setUp(self) -> None:
        self.target = _temp_dir(self)

    def test_absent_provenance_has_no_pin(self) -> None:
        self.assertEqual(read_existing_provenance_pin(self.target), {})

    def test_unparseable_provenance_has_no_pin(self) -> None:
        write_provenance(self.target, "{not json")
        self.assertEqual(read_existing_provenance_pin(self.target), {})

    def test_non_object_provenance_has_no_pin(self) -> None:
        write_provenance(self.target, [1, 2, 3])
        self.assertEqual(read_existing_provenance_pin(self.target), {})

    def test_symlinked_provenance_has_no_pin(self) -> None:
        real = self.target / "real.json"
        real.write_text(json.dumps(thin_payload()), encoding="utf-8")
        link = self.target / PROVENANCE_FILE
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(real)
        self.assertEqual(read_existing_provenance_pin(self.target), {})

    def test_thin_provenance_yields_only_the_pin_keys(self) -> None:
        write_provenance(self.target, thin_payload())
        pin = read_existing_provenance_pin(self.target)
        self.assertEqual(sorted(pin), sorted(PIN_KEYS))

    def test_fat_provenance_yields_an_empty_pin(self) -> None:
        write_provenance(self.target, {"pack": "p", "version": "1", "files": {}})
        self.assertEqual(read_existing_provenance_pin(self.target), {})

    def test_content_without_a_pin_is_byte_identical_to_the_fat_shape(self) -> None:
        manifest = {"name": "p", "version": "1"}
        baseline = provenance_content(
            manifest,
            [],
            existing_files={},
            receipt_targets=set(),
            never_vouched=set(),
        )
        self.assertEqual(
            baseline,
            provenance_content(
                manifest,
                [],
                existing_files={},
                receipt_targets=set(),
                never_vouched=set(),
                pin={},
            ),
        )
        self.assertEqual(json.loads(baseline), {"pack": "p", "version": "1", "files": {}})

    def test_pin_keys_are_emitted_between_version_and_files(self) -> None:
        content = provenance_content(
            {"name": "p", "version": "1"},
            [],
            existing_files={},
            receipt_targets=set(),
            never_vouched=set(),
            pin={"mode": "thin", "platforms": ["claude"], "unrelated": "dropped"},
        )
        self.assertEqual(
            list(json.loads(content)),
            ["pack", "version", "mode", "platforms", "files"],
        )


class PinnedPlatformTests(InstallTestCase):
    """A thin receipt no longer proves which platforms the consumer selected."""

    def test_fat_payload_keeps_the_manifest_derived_platforms(self) -> None:
        self.assertEqual(inspection._thin_pinned_platforms(None), ())
        self.assertEqual(inspection._thin_pinned_platforms({"files": {}}), ())

    def test_thin_payload_reports_its_pinned_platforms_sorted(self) -> None:
        self.assertEqual(
            inspection._thin_pinned_platforms(
                {"mode": "thin", "platforms": ["github", "claude", "claude"]}
            ),
            ("claude", "github"),
        )

    def test_thin_payload_with_unusable_platforms_falls_back(self) -> None:
        self.assertEqual(
            inspection._thin_pinned_platforms({"mode": "thin", "platforms": "claude"}),
            (),
        )
        self.assertEqual(
            inspection._thin_pinned_platforms({"mode": "thin", "platforms": ["", 7]}),
            (),
        )


class ResidualSelectionTests(InstallTestCase):
    """`_residual_files_for_thin` is the one place the thin branch is entered."""

    def setUp(self) -> None:
        self.target = _temp_dir(self)
        _, self.files = install.load_manifest()

    def test_a_fat_consumer_inspects_the_whole_payload(self) -> None:
        write_provenance(self.target, {"pack": "p", "version": "1", "files": {}})
        narrowed, is_thin = install._residual_files_for_thin(self.files, self.target)
        self.assertFalse(is_thin)
        self.assertIs(narrowed, self.files)

    def test_every_shipped_fixture_repository_is_fat(self) -> None:
        # The predicate must be false for the repositories the rest of the
        # suite builds, or "the existing tests still pass" would prove nothing
        # about the fat path being unchanged.
        for candidate in (ROOT, self.target):
            _, is_thin = install._residual_files_for_thin(self.files, candidate)
            self.assertFalse(is_thin, candidate)

    def test_a_thin_consumer_inspects_only_the_residual(self) -> None:
        write_provenance(self.target, thin_payload())
        narrowed, is_thin = install._residual_files_for_thin(self.files, self.target)
        self.assertTrue(is_thin)
        self.assertLess(len(narrowed), len(self.files))
        partition = load_partition(ROOT / install.SURFACE_PARTITION_FILE)
        for file in narrowed:
            row = partition.row(file.target.as_posix())
            self.assertIsNotNone(row, file.target)
            self.assertIn(row.category, {"repo-native", "consumer-config"})

    def test_an_unreadable_partition_falls_back_to_the_full_payload(self) -> None:
        write_provenance(self.target, thin_payload())
        with mock.patch.object(
            install.conversion,
            "load_partition",
            side_effect=ValueError("broken"),
        ):
            narrowed, is_thin = install._residual_files_for_thin(
                self.files, self.target
            )
        self.assertFalse(is_thin)
        self.assertIs(narrowed, self.files)

    def test_a_present_managed_block_stays_in_the_residual(self) -> None:
        write_provenance(self.target, thin_payload())
        partition = load_partition(ROOT / install.SURFACE_PARTITION_FILE)
        receipt = read_thin_receipt(self.target)
        without = {
            file.target.as_posix()
            for file in residual_source_files(
                self.files, self.target, partition, receipt
            )
        }
        copilot = self.target / ".github" / "copilot-instructions.md"
        copilot.parent.mkdir(parents=True, exist_ok=True)
        copilot.write_text("# consumer\n", encoding="utf-8")
        with_block = {
            file.target.as_posix()
            for file in residual_source_files(
                self.files, self.target, partition, receipt
            )
        }
        self.assertEqual(with_block, without)
        self.assertIn(".github/copilot-instructions.md", with_block)


class ConvertedConsumerInspectionTests(InstallTestCase):
    """End to end: convert a real install, then ask --check what it sees.

    This is the acceptance test the whole step exists for. `install.py --check`
    decides state by dry-running an install and counting would-be changes, so
    before this change a converted consumer reported `refresh-required`
    permanently -- and `fleet-review-classify` refuses anything but `current`.
    """

    def convert(self, root: Path) -> None:
        """Delete the machine payload and rewrite the receipts as thin.

        Deliberately built from the shared plan builder and the ordinary
        receipt writer rather than a hand-written fixture: the receipts must
        come from exactly the inputs the inspection recomputes, or `--check`
        reports a change that the conversion did not actually leave behind.
        """
        manifest_data, files = install.load_manifest()
        partition = load_partition(ROOT / install.SURFACE_PARTITION_FILE)
        receipt = install.conversion.read_installed_targets_receipt(root)
        plan = install.conversion.build_conversion_plan(
            receipt,
            partition,
            frozenset(THIN_PLATFORMS),
            occupied=install.conversion.occupied_receipt_targets(root, receipt),
        )
        self.assertEqual(plan.blocked, (), "conversion plan must classify everything")
        for entry in (*plan.delete, *plan.retire, *plan.block_strip):
            path = root / entry
            if path.is_file() or path.is_symlink():
                path.unlink()

        pin = {
            "mode": "thin",
            "platforms": sorted(THIN_PLATFORMS),
            "consumer": "fixture",
            "settingsAdditions": {},
            "forced": [],
        }
        thin = read_thin_receipt(root) or ThinReceipt(
            mode="thin",
            version=manifest_data["version"],
            platforms=frozenset(THIN_PLATFORMS),
            consumer="fixture",
            settings_additions={},
            forced=(),
        )
        residual = residual_source_files(files, root, partition, thin)
        selected, skipped = install.selected_files(residual, root, None, False)
        results, generated = install._install_payload(
            selected,
            root,
            local_only=False,
            force=False,
            dry_run=True,
            backup=False,
            install_gitignore=False,
        )
        install._install_receipt_files(
            manifest_data,
            files,
            root,
            selected=selected,
            skipped=skipped,
            results=results,
            generated_targets=generated,
            dry_run=False,
            pin=pin,
        )

    def install_fat(self) -> Path:
        root = self.make_repo()
        args: list[str] = []
        for platform in THIN_PLATFORMS:
            args += ["--platform", platform]
        result = self.run_install_inproc(root, *args)
        self.assertEqual(result.returncode, 0, result.stdout)
        return root

    def test_a_converted_consumer_reports_current(self) -> None:
        root = self.install_fat()
        self.convert(root)
        result = self.run_install_inproc(root, "--check", "--json")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "current", result.stdout)
        self.assertEqual(payload["changeCount"], 0)
        self.assertEqual(result.returncode, 0)

    def test_a_converted_consumer_still_reports_its_pinned_platforms(self) -> None:
        # Every fleet reader compares installed platforms against the
        # registry. Inferring them from a thin receipt would shrink the set to
        # whatever happens to be repo-native and reject the consumer.
        root = self.install_fat()
        self.convert(root)
        payload = json.loads(self.run_install_inproc(root, "--check", "--json").stdout)
        self.assertEqual(payload["platforms"]["installed"], sorted(THIN_PLATFORMS))

    def test_a_half_converted_consumer_is_reported_invalid(self) -> None:
        # Payload deleted, receipts left fat: the thin predicate is false, so
        # the unchanged fat path runs and every deleted target is named.
        root = self.install_fat()
        manifest_data, files = install.load_manifest()
        partition = load_partition(ROOT / install.SURFACE_PARTITION_FILE)
        receipt = install.conversion.read_installed_targets_receipt(root)
        plan = install.conversion.build_conversion_plan(
            receipt,
            partition,
            frozenset(THIN_PLATFORMS),
            occupied=install.conversion.occupied_receipt_targets(root, receipt),
        )
        for entry in plan.delete:
            path = root / entry
            if path.is_file():
                path.unlink()

        _, is_thin = install._residual_files_for_thin(files, root)
        self.assertFalse(is_thin)
        result = self.run_install_inproc(root, "--check", "--json")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            any(
                reason.startswith("installed target is missing or invalid: ")
                for reason in payload["reasons"]
            ),
            payload["reasons"][:3],
        )

    def test_a_fat_consumer_is_unaffected(self) -> None:
        root = self.install_fat()
        result = self.run_install_inproc(root, "--check", "--json")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "current", result.stdout)
        self.assertEqual(payload["platforms"]["installed"], sorted(THIN_PLATFORMS))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
