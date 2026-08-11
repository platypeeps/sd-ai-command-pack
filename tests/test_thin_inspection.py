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
    unusable_thin_pin_reason,
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
        # R20-C2: written even when empty. An absent key and an empty list are
        # the same to a reader that defaults, and revert's report of what it
        # cannot restore depends on telling those apart.
        "retired": [],
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
            retired=(),
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


class ThinPinStateTests(InstallTestCase):
    """R19-C4: fat and damaged are different answers, not both `None`."""

    def setUp(self) -> None:
        self.target = _temp_dir(self)

    def state(self):
        from installer.conversion import thin_pin_state

        return thin_pin_state(self.target)

    def test_absent_provenance_is_fat(self) -> None:
        self.assertEqual(self.state(), "fat")

    def test_a_fat_receipt_is_fat(self) -> None:
        write_provenance(self.target, {"pack": "p", "version": "1", "files": {}})
        self.assertEqual(self.state(), "fat")

    def test_a_thin_receipt_is_thin(self) -> None:
        write_provenance(self.target, thin_payload())
        self.assertEqual(self.state(), "thin")

    def test_unparseable_provenance_is_fat_because_install_rebuilds_it(self) -> None:
        # Not "unknown, therefore refuse": rebuilding a mangled fat receipt is
        # a shipped recovery path (`tests/test_install_audit.py:1417`), and
        # these bytes carry no evidence that this consumer was ever thin.
        write_provenance(self.target, "{not json")
        self.assertEqual(self.state(), "fat")

    def test_non_object_provenance_is_fat(self) -> None:
        write_provenance(self.target, [1, 2, 3])
        self.assertEqual(self.state(), "fat")

    def test_a_corrupt_mode_carrying_pin_keys_is_malformed(self) -> None:
        # The case round 19 demonstrated: `read_thin_receipt` returns None
        # here, so a guard built on it reads "fat" and permits destruction.
        write_provenance(self.target, thin_payload(mode="thin-corrupt"))
        self.assertEqual(self.state(), "malformed")

    def test_a_symlinked_provenance_is_not_read_through(self) -> None:
        # The link points at a thin payload, and this predicate still answers
        # `fat` -- deliberately. Reading through an attacker-placed symlink to
        # decide a guard is worse than not reading it, and install refuses a
        # symlinked provenance on its own (`tests/test_install_audit.py:1389`)
        # before anything can be written through the link.
        elsewhere = _temp_dir(self) / "provenance.json"
        elsewhere.write_text(json.dumps(thin_payload()), encoding="utf-8")
        link = self.target / PROVENANCE_FILE
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(elsewhere)
        self.assertEqual(self.state(), "fat")

    def test_a_provenance_symlink_inside_the_target_is_also_not_read_through(
        self,
    ) -> None:
        inside = self.target / "elsewhere.json"
        inside.write_text(json.dumps(thin_payload()), encoding="utf-8")
        link = self.target / PROVENANCE_FILE
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(inside)
        self.assertEqual(self.state(), "fat")


class SecondThinWitnessTests(InstallTestCase):
    """R19-C4b: `manifest.json` is the witness that survives pin loss.

    The gap the pin cannot close is a thin consumer whose provenance is
    destroyed outright: nothing legible says thin, so it reads fat, and an
    ordinary install rebuilds a fat receipt over a narrowed payload. The
    write order puts `manifest.json` before `provenance.json` precisely so
    that whichever one survives an interruption, the earlier is thin.
    """

    def setUp(self) -> None:
        self.target = _temp_dir(self)

    def state(self):
        from installer.conversion import thin_pin_state

        return thin_pin_state(self.target)

    def write_manifest(self, payload: object) -> Path:
        path = self.target / install.PACK_MANIFEST_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            payload if isinstance(payload, str) else json.dumps(payload),
            encoding="utf-8",
        )
        return path

    def test_a_thin_manifest_alone_reads_thin(self) -> None:
        # The whole point: no provenance at all, and the consumer still does
        # not read as fat.
        self.write_manifest({"mode": "thin", "files": {}})
        self.assertEqual(self.state(), "thin")

    def test_a_thin_manifest_outvotes_a_destroyed_pin(self) -> None:
        self.write_manifest({"mode": "thin", "files": {}})
        write_provenance(self.target, "{truncated")
        self.assertEqual(self.state(), "thin")

    def test_a_fat_manifest_leaves_provenance_to_decide(self) -> None:
        self.write_manifest({"pack": "p", "version": "1", "files": {}})
        write_provenance(self.target, thin_payload(mode="thin-corrupt"))
        self.assertEqual(self.state(), "malformed")

    def test_a_damaged_manifest_is_not_evidence_either_way(self) -> None:
        # Narrower than the provenance reading on purpose: the second witness
        # answers only "does this legibly say thin", so damage here must not
        # manufacture a `malformed` a fat consumer would then trip over.
        for payload in ("{not json", [1, 2, 3], {"mode": "thin-corrupt"}):
            with self.subTest(payload=payload):
                self.write_manifest(payload)
                self.assertEqual(self.state(), "fat")

    def test_a_symlinked_manifest_is_not_read_through(self) -> None:
        elsewhere = _temp_dir(self) / "manifest.json"
        elsewhere.write_text(json.dumps({"mode": "thin"}), encoding="utf-8")
        link = self.target / install.PACK_MANIFEST_FILE
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(elsewhere)
        self.assertEqual(self.state(), "fat")


class UnusableThinPinTests(InstallTestCase):
    """R18-C1: the pin is a file on a consumer's disk, not a proof."""

    def setUp(self) -> None:
        self.partition = load_partition(ROOT / install.SURFACE_PARTITION_FILE)
        self.target_dir = _temp_dir(self)

    def pin(self, platforms) -> ThinReceipt:
        return ThinReceipt(
            mode="thin",
            version="1.2.3",
            platforms=frozenset(platforms),
            consumer="demo",
            settings_additions={},
            forced=(),
            retired=(),
        )

    def test_a_classifiable_platform_set_is_usable(self) -> None:
        self.assertIsNone(
            unusable_thin_pin_reason(self.pin(THIN_PLATFORMS), self.partition)
        )

    def test_an_empty_platform_set_is_unusable(self) -> None:
        self.assertEqual(
            unusable_thin_pin_reason(self.pin([]), self.partition),
            "thin pin declares no platforms",
        )

    def test_an_invalid_list_element_makes_the_whole_pin_unusable(self) -> None:
        # R19-C4: `["claude", 1]` filtered element-wise yields {"claude"} --
        # a set that looks like a deliberate single-platform declaration.
        # All-or-nothing instead, and the non-string never reaches the
        # message, where joining it raised TypeError.
        write_provenance(self.target_dir, thin_payload(platforms=["claude", 1]))
        receipt = read_thin_receipt(self.target_dir)
        self.assertEqual(receipt.platforms, frozenset())
        self.assertEqual(
            unusable_thin_pin_reason(receipt, self.partition),
            "thin pin declares no platforms",
        )

    def test_every_unclassifiable_platform_is_named(self) -> None:
        reason = unusable_thin_pin_reason(
            self.pin(["claude", "zeta-platform", "alpha-platform"]), self.partition
        )
        self.assertIn("alpha-platform, zeta-platform", reason)
        self.assertNotIn("claude", reason)


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

    def test_a_pin_naming_an_unclassifiable_platform_falls_back(self) -> None:
        # R18-C1. The pin chooses the residual it is then measured against, so
        # an unusable pin that still narrows would certify itself: the slice it
        # produces is intact by construction and --check answers `current`.
        write_provenance(
            self.target,
            thin_payload(platforms=[*THIN_PLATFORMS, "not-a-platform"]),
        )
        narrowed, is_thin = install._residual_files_for_thin(self.files, self.target)
        self.assertFalse(is_thin)
        self.assertIs(narrowed, self.files)

    def test_a_pin_with_no_platforms_falls_back(self) -> None:
        # The same failure with no name to report: an empty set retains
        # nothing, narrows to consumer-config plus bookkeeping, and finds all
        # of it present.
        write_provenance(self.target, thin_payload(platforms=[]))
        narrowed, is_thin = install._residual_files_for_thin(self.files, self.target)
        self.assertFalse(is_thin)
        self.assertIs(narrowed, self.files)

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
            "retired": [],
        }
        thin = read_thin_receipt(root) or ThinReceipt(
            mode="thin",
            version=manifest_data["version"],
            platforms=frozenset(THIN_PLATFORMS),
            consumer="fixture",
            settings_additions={},
            forced=(),
            retired=(),
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
            # The installed manifest carries `mode: "thin"` too: it is the
            # first witness `thin_pin_state` reads, and a fixture that writes
            # only the provenance pin is a half-converted consumer that the
            # inspection correctly reports as needing a refresh.
            install._receipt_manifest(manifest_data, is_thin=True),
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

    def test_a_converted_consumer_with_a_corrupt_pin_is_not_current(self) -> None:
        # R18-C1, end to end and the way round 18 demonstrated it: convert a
        # real install, then edit the pin to name a platform the partition
        # cannot classify. Before the guard this reported
        # `{"state": "current", "changeCount": 0}` -- the corrupt pin picked
        # the comparison that could not fail.
        root = self.install_fat()
        self.convert(root)
        provenance = root / PROVENANCE_FILE
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        payload["platforms"] = [*sorted(THIN_PLATFORMS), "not-a-platform"]
        provenance.write_text(json.dumps(payload), encoding="utf-8")

        corrupt = json.loads(self.run_install_inproc(root, "--check", "--json").stdout)
        self.assertNotEqual(corrupt["state"], "current")
        # State alone does not discriminate here: editing the pin already
        # moves this fixture off `current` by one change even without the
        # guard. What the guard controls is *which comparison runs*, so
        # measure that. Narrowed by the corrupt pin: 1 change. Full payload,
        # which is what an untrusted pin must fall back to: 79, one per
        # machine surface the conversion deleted.
        self.assertGreater(corrupt["changeCount"], 50, corrupt)

    def test_ordinary_install_does_not_de_thin_a_consumer(self) -> None:
        # R19-C1, and the shape it settled into. A plain refresh once exited
        # 0, rewrote provenance without the pin, and discarded
        # settingsAdditions -- while the plugin stayed enabled and the
        # registry still read `thin`. R19-C1's fix was to refuse, which was
        # fail-closed and never the end state: this is the routine command a
        # fleet refresh runs, so a consumer it could not refresh was a
        # consumer that could not receive a security fix. Step 9b made it a
        # thin-aware refresh. The property under test is the one that never
        # changed -- the refresh must not de-thin -- not the exit code that
        # temporarily enforced it. `tests/test_thin_refresh.py` owns the rest.
        root = self.install_fat()
        self.convert(root)
        before = json.loads((root / PROVENANCE_FILE).read_text(encoding="utf-8"))

        result = self.run_install_inproc(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        after = json.loads((root / PROVENANCE_FILE).read_text(encoding="utf-8"))
        for key in ("mode", "platforms", "consumer", "settingsAdditions", "forced"):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after["files"], before["files"])

    def test_remove_refuses_on_a_thin_consumer(self) -> None:
        # R18-C2, with the three facts round 18's probe found false:
        # provenance survives, settings are untouched, exit is nonzero.
        root = self.install_fat()
        self.convert(root)
        before = (root / PROVENANCE_FILE).read_bytes()

        result = self.run_install_inproc(root, "--remove", "--skip-diff-check")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertTrue((root / PROVENANCE_FILE).is_file())
        self.assertEqual((root / PROVENANCE_FILE).read_bytes(), before)

    def test_a_receipt_with_a_corrupt_mode_also_refuses(self) -> None:
        # `malformed` is not `fat`: a receipt that carried the pin and has
        # since been edited must not be treated as an unconverted consumer.
        root = self.install_fat()
        self.convert(root)
        provenance = root / PROVENANCE_FILE
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        payload["mode"] = "thin-corrupt"
        provenance.write_text(json.dumps(payload), encoding="utf-8")

        self.assertEqual(self.run_install_inproc(root, "--remove").returncode, 2)
        self.assertEqual(self.run_install_inproc(root).returncode, 2)

    def test_a_fat_consumer_still_installs_and_removes(self) -> None:
        # The guard must add nothing to the path every existing consumer
        # takes. Both commands are the shipped ones, unchanged.
        root = self.install_fat()
        self.assertEqual(self.run_install_inproc(root).returncode, 0)
        self.assertEqual(
            self.run_install_inproc(root, "--remove", "--skip-diff-check").returncode, 0
        )

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
