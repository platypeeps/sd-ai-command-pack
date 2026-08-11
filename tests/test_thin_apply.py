"""The write phase against a real installed tree.

`design.md` fixes the write order because there is no rollback: the order
exists so that every interruption lands in a state that is *recognizable*
rather than ambiguous. These tests assert the order's consequences, not the
order itself -- an assertion that the code calls four functions in sequence
would pass on a version that wrote them all to the wrong paths.
"""

from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
unittest = _support.unittest
Path = _support.Path
install = _support.install
InstallTestCase = _support.InstallTestCase

from installer import conversion, thin  # noqa: E402


class ConversionFixture(InstallTestCase):
    def installed_consumer(self) -> Path:
        root = self.make_repo(".claude")
        self.assertEqual(self.run_install(root).returncode, 0)
        return root

    def plan_for(self, root: Path):
        receipt = conversion.read_installed_targets_receipt(root)
        partition = conversion.load_partition(
            _support.PACK_ROOT / install.SURFACE_PARTITION_FILE
        )
        return receipt, conversion.build_conversion_plan(
            receipt,
            partition,
            frozenset({"claude"}),
            occupied=conversion.occupied_receipt_targets(root, receipt),
        )

    def convert(self, root: Path, *, force: bool = False, backup: bool = False):
        manifest_data, files = install.load_manifest()
        receipt, plan = self.plan_for(root)
        self.assertEqual(plan.blocked, (), "fixture plan is not classifiable")
        settings, reason = thin.plan_settings_merge(
            root / thin.CLAUDE_SETTINGS_FILE, "sd-ai-command-pack", "sd"
        )
        self.assertIsNone(reason)
        residual = frozenset(plan.keep) | frozenset(plan.receipts)
        provenance_files = install.read_existing_provenance_files(root)
        written = thin.apply_conversion(
            _support.PACK_ROOT,
            root,
            plan=plan,
            settings=settings,
            manifest_data=manifest_data,
            residual=residual,
            existing_files=provenance_files,
            platforms=("claude",),
            consumer=None,
            forced=(),
            files_by_target={file.target.as_posix(): file for file in files},
            provenance_files=provenance_files,
            force=force,
            backup=backup,
        )
        return plan, residual, written


class WriteOrderTests(ConversionFixture):
    def test_the_conversion_deletes_exactly_the_planned_set(self) -> None:
        # Compared against the pre-conversion receipt, not against the
        # partition: a partition-only comparison is the ~531-missing
        # regression in miniature.
        root = self.installed_consumer()
        before = conversion.read_installed_targets_receipt(root).entries
        plan, residual, _ = self.convert(root)

        for entry in plan.delete:
            self.assertFalse((root / entry).exists(), f"{entry} survived")
        for entry in residual:
            self.assertTrue((root / entry).exists(), f"{entry} was removed")
        self.assertEqual(before, frozenset(plan.delete) | frozenset(plan.retire)
                         | frozenset(plan.block_strip) | residual)

    def test_the_receipts_describe_the_residual_and_none_is_deleted(self) -> None:
        root = self.installed_consumer()
        _, residual, _ = self.convert(root)

        for receipt in (install.PACK_MANIFEST_FILE, install.PROVENANCE_FILE,
                        install.INSTALLED_TARGETS_FILE):
            self.assertTrue((root / receipt).is_file(), f"{receipt} was deleted")

        targets = (root / install.INSTALLED_TARGETS_FILE).read_text(encoding="utf-8")
        self.assertEqual(set(targets.split()), set(residual))

        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(provenance["mode"], "thin")
        self.assertTrue(provenance["files"], "a thin provenance still needs a files map")
        self.assertTrue(set(provenance["files"]) <= set(residual))

    def test_both_thin_witnesses_are_written(self) -> None:
        root = self.installed_consumer()
        self.convert(root)
        manifest = json.loads(
            (root / install.PACK_MANIFEST_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["mode"], "thin")
        self.assertEqual(conversion.thin_pin_state(root), conversion.PIN_STATE_THIN)

    def test_a_completed_conversion_leaves_no_removal_inventory(self) -> None:
        # Its presence means unfinished. It is deleted after the removals it
        # authorizes, so surviving would make every later command think a
        # conversion was interrupted.
        root = self.installed_consumer()
        self.convert(root)
        self.assertFalse((root / thin.REMOVAL_INVENTORY_FILE).exists())
        self.assertIsNone(thin.read_removal_inventory(root))

    def test_the_settings_merge_lands_with_the_exact_locator(self) -> None:
        root = self.installed_consumer()
        self.convert(root)
        settings = json.loads(
            (root / thin.CLAUDE_SETTINGS_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(
            settings["extraKnownMarketplaces"],
            {
                "sd-ai-command-pack": {
                    "source": {"source": "github",
                               "repo": "platypeeps/sd-ai-command-pack"}
                }
            },
        )
        self.assertEqual(settings["enabledPlugins"], {"sd@sd-ai-command-pack": True})
        self.assertNotIn("autoUpdate", json.dumps(settings))

    def test_the_recorded_additions_are_what_the_conversion_actually_added(
        self,
    ) -> None:
        root = self.installed_consumer()
        self.convert(root)
        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        # The two provenance flags are part of the record, not decoration:
        # "remove what we added" is ambiguous at the container boundary, and
        # `tests/test_thin_revert.py` is where dropping them showed up as an
        # empty `extraKnownMarketplaces` surviving every revert.
        self.assertEqual(
            sorted(provenance["settingsAdditions"]),
            [
                "createdContainers",
                "createdFile",
                "enabledPlugins",
                "extraKnownMarketplaces",
            ],
        )
        self.assertEqual(
            sorted(provenance["settingsAdditions"]["createdContainers"]),
            ["enabledPlugins", "extraKnownMarketplaces"],
        )
        self.assertIs(provenance["settingsAdditions"]["createdFile"], True)

    def test_a_second_conversion_of_the_same_tree_adds_no_settings_twice(self) -> None:
        # The idempotent row: re-running after an interruption must not record
        # an addition it did not make, because that record is what a revert
        # undoes.
        root = self.installed_consumer()
        self.convert(root)
        settings_before = (root / thin.CLAUDE_SETTINGS_FILE).read_bytes()

        plan, _, _ = self.convert(root)
        self.assertEqual(plan.delete, (), "nothing was left to delete")
        self.assertEqual(
            (root / thin.CLAUDE_SETTINGS_FILE).read_bytes(), settings_before
        )
        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(
            provenance["settingsAdditions"],
            {"createdContainers": [], "createdFile": False},
        )


class InterruptionTests(ConversionFixture):
    """The states the write order is designed to make recognizable."""

    def test_an_interruption_before_the_pin_leaves_a_readable_thin_witness(
        self,
    ) -> None:
        # The order writes manifest.json before provenance.json precisely so
        # that a run cut short between them still reads as thin rather than as
        # fat-with-a-narrowed-payload -- the one state no re-run can tell from
        # a botched manual deletion.
        root = self.installed_consumer()
        manifest_data, _ = install.load_manifest()
        (root / install.PACK_MANIFEST_FILE).write_text(
            thin.thin_manifest_content(manifest_data), encoding="utf-8"
        )
        self.assertEqual(conversion.thin_pin_state(root), conversion.PIN_STATE_THIN)

    def test_the_inventory_names_the_remainder_a_receipt_can_no_longer_describe(
        self,
    ) -> None:
        # R20-C3. After the receipts are rewritten the receipt lists only the
        # residual, so a re-run planning from it computes an empty remainder
        # and calls a half-deleted consumer finished. The inventory is what
        # makes the remainder enumerable.
        root = self.installed_consumer()
        _, plan = self.plan_for(root)
        (root / thin.REMOVAL_INVENTORY_FILE).write_text(
            thin.removal_inventory_content(
                delete=plan.delete, retire=plan.retire, block_strip=plan.block_strip
            ),
            encoding="utf-8",
        )
        residual = frozenset(plan.keep) | frozenset(plan.receipts)
        (root / install.INSTALLED_TARGETS_FILE).write_text(
            thin.residual_targets_content(residual), encoding="utf-8"
        )

        rerun = conversion.read_installed_targets_receipt(root)
        self.assertEqual(rerun.entries & frozenset(plan.delete), frozenset())

        inventory = thin.read_removal_inventory(root)
        self.assertEqual(set(inventory["delete"]), set(plan.delete))


class DriftPreflightTests(ConversionFixture):
    """Drift refuses across all three removal buckets, before any write."""

    def reasons(self, root: Path, *, force: bool = False) -> tuple[str, ...]:
        manifest_data, files = install.load_manifest()
        _, plan = self.plan_for(root)
        provenance_files = install.read_existing_provenance_files(root)
        return thin.removal_preflight_reasons(
            root,
            plan,
            files_by_target={file.target.as_posix(): file for file in files},
            provenance_files=provenance_files,
            force=force,
        )

    def test_a_clean_tree_has_no_drift(self) -> None:
        self.assertEqual(self.reasons(self.installed_consumer()), ())

    def test_a_drifted_delete_target_refuses_and_force_overrides_it(self) -> None:
        root = self.installed_consumer()
        drifted = root / ".claude/commands/sd/check.md"
        drifted.write_text("edited by the consumer\n", encoding="utf-8")

        reasons = self.reasons(root)
        self.assertTrue(any(".claude/commands/sd/check.md" in r for r in reasons))
        self.assertEqual(self.reasons(root, force=True), ())

    def test_an_unstrippable_managed_block_refuses(self) -> None:
        # `remove_marked_block` comes back PRESERVED on a malformed target
        # (installer/fileops.py:683). Validating only ordinary delete drift
        # would let the conversion complete while the block survived -- the
        # half-converted state the thin pin would then certify as clean.
        root = self.installed_consumer()
        _, plan = self.plan_for(root)
        self.assertIn(".gitignore", plan.block_strip)
        # A half-block: the opener with no closer. A file with *no* markers at
        # all is a no-op rather than a refusal -- there is nothing to strip and
        # nothing ambiguous about that -- so the drifted case has to be one
        # the remover genuinely cannot complete.
        (root / ".gitignore").write_text(
            f"{install.TRELLIS_GITIGNORE_START}\nnode_modules/\n", encoding="utf-8"
        )

        reasons = self.reasons(root)
        self.assertTrue(any(".gitignore" in reason for reason in reasons), reasons)


if __name__ == "__main__":
    unittest.main()


class RetentionFixtureTests(ConversionFixture):
    """`retainVendoredFor` across the whole shared platform, not one row of it.

    The disposition is declared per *platform* -- `shared` retains for `codex`
    and `pi` -- so a fixture that checks one `.agents/` file proves nothing
    about `scripts/`, and a retention bug that spared one directory and not
    the other would pass it. This asserts the whole platform and requires
    both directories to be represented.

    **No live consumer exercises this path.** The fleet registry declares no
    `codex` or `pi` consumer today, so this coverage is synthetic and must not
    be reported as fleet-proven.
    """

    VENDOR_PLATFORMS = frozenset({"claude", "codex"})

    def shared_machine_rows(self, root: Path) -> frozenset[str]:
        partition = conversion.load_partition(
            _support.PACK_ROOT / install.SURFACE_PARTITION_FILE
        )
        installed = conversion.read_installed_targets_receipt(root).entries
        return frozenset(
            target
            for target in installed
            if (row := partition.row(target)) is not None
            and row.platform == "shared"
            and row.category in conversion.MACHINE_CATEGORIES
        )

    def plan_with_codex(self, root: Path):
        receipt = conversion.read_installed_targets_receipt(root)
        partition = conversion.load_partition(
            _support.PACK_ROOT / install.SURFACE_PARTITION_FILE
        )
        return conversion.build_conversion_plan(
            receipt,
            partition,
            self.VENDOR_PLATFORMS,
            occupied=conversion.occupied_receipt_targets(root, receipt),
        )

    def test_every_shared_machine_row_is_kept_for_a_codex_consumer(self) -> None:
        root = self.installed_consumer()
        retained = self.shared_machine_rows(root)
        self.assertTrue(retained, "the fixture installed no shared machine rows")
        # Both halves of the platform must be represented, or the assertion
        # below is satisfied by a partition that only ever ships one of them.
        self.assertTrue(any(entry.startswith(".agents/") for entry in retained))
        self.assertTrue(any(entry.startswith("scripts/") for entry in retained))

        plan = self.plan_with_codex(root)
        self.assertEqual(retained - frozenset(plan.keep), frozenset())
        self.assertEqual(retained & frozenset(plan.delete), frozenset())

    def test_the_same_rows_are_deleted_without_the_vendor_platform(self) -> None:
        # The other direction, and the one that makes the test above mean
        # something: retention that kept these rows for every consumer would
        # satisfy it while converting nothing.
        root = self.installed_consumer()
        retained = self.shared_machine_rows(root)
        _, plan = self.plan_for(root)
        self.assertEqual(retained - frozenset(plan.delete), frozenset())

    def test_a_real_conversion_leaves_them_on_disk(self) -> None:
        # The plan and the write agreeing: a `keep` bucket the writer ignores
        # is a plan that describes a conversion nobody performed.
        root = self.installed_consumer()
        retained = self.shared_machine_rows(root)
        manifest_data, files = install.load_manifest()
        plan = self.plan_with_codex(root)
        settings, _ = thin.plan_settings_merge(
            root / thin.CLAUDE_SETTINGS_FILE, "sd-ai-command-pack", "sd"
        )
        provenance_files = install.read_existing_provenance_files(root)
        thin.apply_conversion(
            _support.PACK_ROOT,
            root,
            plan=plan,
            settings=settings,
            manifest_data=manifest_data,
            residual=frozenset(plan.keep) | frozenset(plan.receipts),
            existing_files=provenance_files,
            platforms=tuple(sorted(self.VENDOR_PLATFORMS)),
            consumer=None,
            forced=(),
            files_by_target={file.target.as_posix(): file for file in files},
            provenance_files=provenance_files,
            force=False,
            backup=False,
        )
        for entry in sorted(retained):
            self.assertTrue((root / entry).is_file(), f"{entry} was deleted")
        residual = (root / install.INSTALLED_TARGETS_FILE).read_text(
            encoding="utf-8"
        ).split()
        self.assertEqual(retained - frozenset(residual), frozenset())


class RegistryFlipTests(InstallTestCase):
    """The last write, against a fixture registry rather than the real one."""

    def make_registry(self, *names: str) -> Path:
        root = self.make_repo()
        (root / "docs/fleet").mkdir(parents=True, exist_ok=True)
        (root / "docs/fleet/consumers.json").write_text(
            json.dumps(
                {"consumers": [{"name": name, "mode": "fat"} for name in names]}
            ),
            encoding="utf-8",
        )
        return root

    def test_the_named_consumers_row_flips_and_no_other_does(self) -> None:
        root = self.make_registry("alpha", "beta")
        thin.flip_registry_mode(root, "beta")
        payload = json.loads(
            (root / "docs/fleet/consumers.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {entry["name"]: entry["mode"] for entry in payload["consumers"]},
            {"alpha": "fat", "beta": "thin"},
        )

    def test_an_unregistered_consumer_is_an_error_not_a_silent_no_op(self) -> None:
        # A silent no-op here is the pin-vs-mode skew with nothing to report
        # it: the consumer converts and the fleet never learns.
        root = self.make_registry("alpha")
        with self.assertRaises(SystemExit) as raised:
            thin.flip_registry_mode(root, "missing")
        self.assertIn("missing", str(raised.exception))


class UnknownManagedBlockTests(ConversionFixture):
    def test_a_block_file_with_no_known_markers_refuses(self) -> None:
        # `MANAGED_BLOCK_REMOVAL_TARGETS` is a frozenset the plan builder
        # enumerates; a third member added later reaches this table, and
        # guessing its marker pair is how a consumer loses a surface silently.
        root = self.installed_consumer()
        _, plan = self.plan_for(root)
        widened = conversion.ConversionPlan(
            delete=(), retire=(), block_strip=(".well-known/agents.md",),
            keep=plan.keep, receipts=plan.receipts,
        )
        reasons = thin.removal_preflight_reasons(
            root, widened, files_by_target={}, provenance_files={}, force=False
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("no known managed block", reasons[0])


class RegistryWriteDuringConversionTests(ConversionFixture):
    def test_a_named_consumer_gets_its_registry_row_flipped_by_the_conversion(
        self,
    ) -> None:
        # The convert() helper above passes `consumer=None` because a fixture
        # is not in the real registry. This covers the other branch against a
        # fixture pack root, so the last write is exercised rather than
        # assumed.
        root = self.installed_consumer()
        pack = self.make_repo()
        (pack / "docs/fleet").mkdir(parents=True, exist_ok=True)
        (pack / "docs/fleet/consumers.json").write_text(
            json.dumps({"consumers": [{"name": "demo", "mode": "fat"}]}),
            encoding="utf-8",
        )
        manifest_data, files = install.load_manifest()
        _, plan = self.plan_for(root)
        settings, _ = thin.plan_settings_merge(
            root / thin.CLAUDE_SETTINGS_FILE, "sd-ai-command-pack", "sd"
        )
        provenance_files = install.read_existing_provenance_files(root)
        written = thin.apply_conversion(
            pack,
            root,
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
        self.assertIn("registry", [entry.step for entry in written])
        payload = json.loads(
            (pack / "docs/fleet/consumers.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["consumers"][0]["mode"], "thin")
