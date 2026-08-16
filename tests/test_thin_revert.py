"""`install.py TARGET --revert-thin`: the undo, and what it will not undo.

The headline check is a round trip -- install, convert, revert, and compare
the two trees byte for byte -- because every narrower assertion here has a
version that passes while the payload comes back subtly wrong. Restoring 178
of 179 paths, restoring them from the wrong version, or restoring them and
leaving the pin thin all satisfy "revert ran and exited zero".

The registry is doubled, deliberately and narrowly. `flip_registry_mode`
writes the pack's *own* `docs/fleet/consumers.json`, so a test that let it run
for real would edit a tracked file in this repository. Its behavior has direct
tests against a fixture root in `tests/test_thin_apply.py`; what these tests
own is that revert resolves the right name and asks for `fat`.
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

PLUGIN_KEY = "sd@sd-ai-command-pack"


class RevertFixture(InstallTestCase):
    """An installed consumer, converted through `apply_conversion`, then reverted."""

    # The platform set is a fixture knob because the round trip is only as
    # wide as the tree it runs on: a `claude`-only consumer has no
    # `.github/PULL_REQUEST_TEMPLATE.md`, and that is a *kept* surface the
    # conversion repoints in place rather than deletes, so nothing here would
    # have noticed it coming back unrepointed.
    PLATFORM_DIRS = (".claude",)
    PLATFORMS = ("claude",)

    def setUp(self) -> None:
        self.root = self.make_repo(*self.PLATFORM_DIRS)
        self.assertEqual(self.run_install(self.root).returncode, 0)
        self.before = self.snapshot()
        self.flips: list[tuple[str, str]] = []
        self.registry = {
            "demo": {"name": "demo", "pathHint": str(self.root), "mode": "thin"}
        }

    def snapshot(self) -> dict[str, bytes]:
        """Every tracked-shaped file under the target, `.git` excluded."""
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
            and ".git" not in path.relative_to(self.root).parts
        }

    def convert(self, *, consumer: str | None = "demo", settings_seed=None) -> None:
        if settings_seed is not None:
            path = self.root / thin.CLAUDE_SETTINGS_FILE
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(settings_seed), encoding="utf-8")
        manifest_data, files = install.load_manifest()
        receipt = conversion.read_installed_targets_receipt(self.root)
        partition = conversion.load_partition(
            _support.PACK_ROOT / install.SURFACE_PARTITION_FILE
        )
        plan = conversion.build_conversion_plan(
            receipt,
            partition,
            frozenset(self.PLATFORMS),
            occupied=conversion.occupied_receipt_targets(self.root, receipt),
        )
        self.assertEqual(plan.blocked, (), "fixture plan is not classifiable")
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
                platforms=self.PLATFORMS,
                consumer=consumer,
                forced=(),
                files_by_target={file.target.as_posix(): file for file in files},
                provenance_files=provenance_files,
                force=False,
                backup=False,
            )
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_THIN
        )

    def run_revert(self, *extra: str):
        def record(root, consumer, mode="thin"):
            self.flips.append((consumer, mode))

        with mock.patch.object(
            thin, "read_registry", return_value=self.registry
        ), mock.patch.object(thin, "flip_registry_mode", side_effect=record):
            return self.run_install_inproc(
                self.root, "--revert-thin", *extra, skip_diff_check=False
            )

    def assert_refused(self, result, fragment: str) -> None:
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("nothing was written", result.stdout)
        self.assertIn(fragment, result.stdout)
        self.assertEqual(
            conversion.thin_pin_state(self.root),
            conversion.PIN_STATE_THIN,
            "a refusal reverted the pin anyway",
        )
        self.assertEqual(self.flips, [], "a refusal still touched the registry")

    def patch_receipt(self, **fields) -> None:
        path = self.root / install.PROVENANCE_FILE
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(fields)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class RoundTripTests(RevertFixture):
    def test_the_tree_comes_back_byte_for_byte(self) -> None:
        # The acceptance criterion, and the reason it is scoped to an unforced
        # conversion: `--thin --force` deletes a drifted file and revert can
        # only restore the source bytes, which are not the bytes that were
        # there. Nothing was forced here, so the promise is unqualified.
        self.convert()
        result = self.run_revert()
        self.assertEqual(result.returncode, 0, result.stdout)

        after = self.snapshot()
        settings = thin.CLAUDE_SETTINGS_FILE.as_posix()
        self.assertEqual(
            {path: content for path, content in after.items() if path != settings},
            {path: content for path, content in self.before.items() if path != settings},
        )
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_FAT
        )
        self.assertEqual(self.flips, [("demo", "fat")])

    def test_the_only_surviving_difference_is_the_disable_marker(self) -> None:
        # `settings.json` is the documented exception to byte-identity: a fat
        # consumer with the plugin merely *absent* re-enables on the next
        # `claude plugin` interaction, which is the state the marker exists to
        # prevent.
        self.convert()
        self.assertNotIn(thin.CLAUDE_SETTINGS_FILE.as_posix(), self.before)
        self.assertEqual(self.run_revert().returncode, 0)
        self.assertEqual(
            json.loads(
                (self.root / thin.CLAUDE_SETTINGS_FILE).read_text(encoding="utf-8")
            ),
            {"enabledPlugins": {PLUGIN_KEY: False}},
        )

    def test_a_tree_with_no_adopted_rules_reverts_anyway(self) -> None:
        # A consumer converted before 0.71.20, where the conversion deleted the
        # ignore rules instead of handing them over. There is no adopted
        # section to take out, and the restore still has to put the managed
        # block back.
        self.convert()
        gitignore = self.root / ".gitignore"
        gitignore.write_text("node_modules/\n", encoding="utf-8")

        result = self.run_revert()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("adopted rules removed", result.stdout)
        restored = gitignore.read_text(encoding="utf-8")
        self.assertIn(install.TRELLIS_GITIGNORE_START, restored)
        self.assertIn("node_modules/", restored)

    def test_a_reverted_consumer_installs_again(self) -> None:
        # The two guards meeting from the other side: the R19-C1 refusal reads
        # the pin, so a revert that left either witness thin would make an
        # ordinary install refuse forever.
        self.convert()
        self.assertEqual(self.run_revert().returncode, 0)
        again = self.run_install(self.root)
        self.assertEqual(again.returncode, 0, again.stdout)

    def test_reverting_twice_is_a_refusal_not_a_second_restore(self) -> None:
        self.convert()
        self.assertEqual(self.run_revert().returncode, 0)
        repeat = self.run_revert()
        self.assertEqual(repeat.returncode, 2, repeat.stdout)
        self.assertIn("carries no thin pin", repeat.stdout)

    def test_an_interrupted_conversions_inventory_is_cleared(self) -> None:
        # Its whole meaning is "removals are outstanding". After a restore
        # they are not outstanding; they are undone.
        self.convert()
        inventory = self.root / thin.REMOVAL_INVENTORY_FILE
        inventory.write_text(
            thin.removal_inventory_content(
                delete=(".claude/commands/sd/check.md",), retire=(), block_strip=()
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.run_revert().returncode, 0)
        self.assertFalse(inventory.exists())


class SettingsOwnershipTests(RevertFixture):
    """R18-C4 and R19-C5: revert removes only what it still owns."""

    def settings(self) -> dict:
        return json.loads(
            (self.root / thin.CLAUDE_SETTINGS_FILE).read_text(encoding="utf-8")
        )

    def test_a_settings_file_deleted_after_conversion_is_reported_not_recreated(
        self,
    ) -> None:
        # Not an error, and not a rewrite either: the consumer deleted the
        # file, so there is nothing of ours left in it to remove. Revert has
        # to say so -- silence here reads as "the entries were removed" --
        # and it must not write the file back to prove a point.
        self.convert()
        (self.root / thin.CLAUDE_SETTINGS_FILE).unlink()

        result = self.run_revert()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.root / thin.CLAUDE_SETTINGS_FILE).exists())
        self.assertNotIn("settings    ", result.stdout)
        self.assertIn("no recorded settings were removed", result.stdout)

    def test_an_unrelated_key_added_after_conversion_survives(self) -> None:
        self.convert()
        document = self.settings()
        document["hooks"] = {"PreToolUse": []}
        (self.root / thin.CLAUDE_SETTINGS_FILE).write_text(
            json.dumps(document), encoding="utf-8"
        )
        self.assertEqual(self.run_revert().returncode, 0)
        self.assertEqual(self.settings()["hooks"], {"PreToolUse": []})

    def test_a_recorded_key_edited_after_conversion_is_left_and_named(self) -> None:
        self.convert()
        document = self.settings()
        document[thin.MARKETPLACE_KEY]["sd-ai-command-pack"] = {
            "source": {"source": "github", "repo": "someone/fork"}
        }
        (self.root / thin.CLAUDE_SETTINGS_FILE).write_text(
            json.dumps(document), encoding="utf-8"
        )
        result = self.run_revert()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("was edited after the conversion", result.stdout)
        self.assertEqual(
            self.settings()[thin.MARKETPLACE_KEY]["sd-ai-command-pack"]["source"][
                "repo"
            ],
            "someone/fork",
        )

    def test_a_recorded_key_already_absent_is_not_an_error(self) -> None:
        self.convert()
        document = self.settings()
        del document[thin.MARKETPLACE_KEY]["sd-ai-command-pack"]
        (self.root / thin.CLAUDE_SETTINGS_FILE).write_text(
            json.dumps(document), encoding="utf-8"
        )
        result = self.run_revert()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("was already absent", result.stdout)

    def test_a_container_the_consumer_already_had_keeps_its_other_entries(self) -> None:
        self.convert(settings_seed={"enabledPlugins": {"other@elsewhere": True}})
        self.assertEqual(self.run_revert().returncode, 0)
        self.assertEqual(
            self.settings()["enabledPlugins"],
            {"other@elsewhere": True, PLUGIN_KEY: False},
        )

    def test_an_edited_plugin_key_is_left_rather_than_marked(self) -> None:
        # design.md §5's second row. The marker is only ever written over a
        # value this conversion wrote and still owns.
        self.convert()
        document = self.settings()
        document["enabledPlugins"][PLUGIN_KEY] = "yes"
        (self.root / thin.CLAUDE_SETTINGS_FILE).write_text(
            json.dumps(document), encoding="utf-8"
        )
        result = self.run_revert()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.settings()["enabledPlugins"][PLUGIN_KEY], "yes")
        self.assertIn("was edited after the conversion", result.stdout)

    def test_a_plugin_the_consumer_enabled_is_never_disabled(self) -> None:
        # design.md §5's third row, and the one that would be silently wrong:
        # it disables a plugin the consumer enabled themselves.
        self.convert(settings_seed={"enabledPlugins": {PLUGIN_KEY: True}})
        recorded = conversion.read_thin_receipt(self.root).settings_additions
        self.assertNotIn(PLUGIN_KEY, recorded.get("enabledPlugins", {}))

        result = self.run_revert()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIs(self.settings()["enabledPlugins"][PLUGIN_KEY], True)
        self.assertIn("this pack did not add", result.stdout)


class SettingsPlanUnitTests(InstallTestCase):
    """The cases the CLI fixture cannot reach, against the planner directly."""

    def plan(self, content, additions):
        root = self.make_repo()
        path = root / "settings.json"
        if content is not None:
            path.write_text(
                content if isinstance(content, str) else json.dumps(content),
                encoding="utf-8",
            )
        return thin.plan_settings_revert(path, additions, plugin_key=PLUGIN_KEY)

    def test_a_symlinked_settings_file_refuses(self) -> None:
        root = self.make_repo()
        elsewhere = root / "elsewhere.json"
        elsewhere.write_text("{}", encoding="utf-8")
        path = root / "settings.json"
        path.symlink_to(elsewhere)
        plan, reason = thin.plan_settings_revert(path, {}, plugin_key=PLUGIN_KEY)
        self.assertIsNone(plan)
        self.assertIn("symlink", reason)

    def test_an_absent_file_is_reported_rather_than_refused(self) -> None:
        plan, reason = self.plan(None, {"enabledPlugins": {PLUGIN_KEY: True}})
        self.assertIsNone(reason)
        self.assertEqual(plan.action, "none")
        self.assertIn("is absent", " ".join(plan.notes))

    def test_unreadable_json_refuses(self) -> None:
        plan, reason = self.plan("{truncated", {})
        self.assertIsNone(plan)
        self.assertIn("cannot be read as JSON", reason)

    def test_a_non_object_document_refuses(self) -> None:
        plan, reason = self.plan([1, 2], {})
        self.assertIsNone(plan)
        self.assertIn("not a JSON object", reason)

    def test_a_recorded_container_that_is_no_longer_an_object_is_left(self) -> None:
        plan, reason = self.plan(
            {thin.MARKETPLACE_KEY: "moved to a string"},
            {thin.MARKETPLACE_KEY: {"sd-ai-command-pack": {}}},
        )
        self.assertIsNone(reason)
        self.assertEqual(plan.action, "none")
        self.assertIn("no longer an object", " ".join(plan.notes))

    def test_a_created_file_left_empty_is_deleted(self) -> None:
        plan, reason = self.plan(
            {thin.MARKETPLACE_KEY: {"sd-ai-command-pack": {"source": 1}}},
            {
                thin.MARKETPLACE_KEY: {"sd-ai-command-pack": {"source": 1}},
                "createdContainers": [thin.MARKETPLACE_KEY],
                "createdFile": True,
            },
        )
        self.assertIsNone(reason)
        self.assertEqual(plan.action, "delete")

    def test_a_created_file_still_holding_the_marker_is_written_not_deleted(self) -> None:
        plan, reason = self.plan(
            {thin.PLUGINS_KEY: {PLUGIN_KEY: True}},
            {
                thin.PLUGINS_KEY: {PLUGIN_KEY: True},
                "createdContainers": [thin.PLUGINS_KEY],
                "createdFile": True,
            },
        )
        self.assertIsNone(reason)
        self.assertEqual(plan.action, "write")
        self.assertEqual(plan.merged, {thin.PLUGINS_KEY: {PLUGIN_KEY: False}})

    def test_apply_writes_deletes_or_does_nothing(self) -> None:
        root = self.make_repo()
        path = root / "settings.json"
        self.assertIsNone(
            thin.apply_settings_revert(thin.SettingsRevert(path, "none", {}))
        )
        self.assertFalse(path.exists())
        thin.apply_settings_revert(thin.SettingsRevert(path, "write", {"a": 1}))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1})
        thin.apply_settings_revert(thin.SettingsRevert(path, "delete", {}))
        self.assertFalse(path.exists())


class CollisionTests(RevertFixture):
    """R19-C3: a consumer may have put a file where the payload goes."""

    def test_an_occupied_restore_path_refuses_before_any_write(self) -> None:
        self.convert()
        occupied = self.root / ".claude/commands/sd/check.md"
        occupied.parent.mkdir(parents=True, exist_ok=True)
        occupied.write_text("mine now\n", encoding="utf-8")
        sibling = self.root / ".claude/commands/sd/ship.md"

        result = self.run_revert()
        self.assert_refused(result, ".claude/commands/sd/check.md")
        self.assertIn("--force is not accepted here", result.stdout)
        self.assertEqual(occupied.read_text(encoding="utf-8"), "mine now\n")
        self.assertFalse(sibling.exists(), "a refusal restored 178 of 179 paths")

    def test_every_occupied_path_is_named_not_just_the_first(self) -> None:
        self.convert()
        for name in ("check.md", "ship.md", "status.md"):
            path = self.root / ".claude/commands/sd" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("mine now\n", encoding="utf-8")
        result = self.run_revert()
        for name in ("check.md", "ship.md", "status.md"):
            self.assertIn(name, result.stdout)

    def test_a_path_recreated_with_the_source_bytes_is_not_a_collision(self) -> None:
        # Refusing here would block revert on a consumer who simply re-created
        # a pack file correctly.
        self.convert()
        _, files = install.load_manifest()
        source = next(
            file
            for file in files
            if file.target.as_posix() == ".claude/commands/sd/check.md"
        )
        recreated = self.root / source.target
        recreated.parent.mkdir(parents=True, exist_ok=True)
        recreated.write_bytes(source.source.read_bytes())

        result = self.run_revert()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_FAT
        )

    def test_a_symlinked_receipt_refuses_before_the_payload_lands(self) -> None:
        self.convert()
        provenance = self.root / install.PROVENANCE_FILE
        copy = self.root / "provenance-copy.json"
        copy.write_bytes(provenance.read_bytes())
        provenance.unlink()
        provenance.symlink_to(copy)

        result = self.run_revert()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("receipt cannot be written in place", result.stdout)
        self.assertFalse((self.root / ".claude/commands/sd/ship.md").exists())

    def test_force_is_rejected_by_the_parser_not_by_a_later_check(self) -> None:
        self.convert()
        with _support.contextlib.redirect_stderr(_support.io.StringIO()) as noise:
            with self.assertRaises(SystemExit):
                install.parse_args([str(self.root), "--revert-thin", "--force"])
        self.assertIn("--force cannot be combined with --revert-thin", noise.getvalue())


class IdentityTests(RevertFixture):
    def test_a_checkout_at_no_known_path_hint_still_reverts(self) -> None:
        self.convert()
        self.registry = {
            "demo": {"name": "demo", "pathHint": "/nowhere/demo", "mode": "thin"}
        }
        self.assertEqual(self.run_revert().returncode, 0)
        self.assertEqual(self.flips, [("demo", "fat")])

    def test_another_consumers_path_hint_is_looked_at_and_passed_over(self) -> None:
        # The cross-check walks every row. A registry holding a second
        # consumer elsewhere must not refuse, and a loop that only ever saw
        # the row it was already told about would never find the collision the
        # row below tests.
        self.registry["other"] = {"name": "other", "pathHint": "/nowhere/other"}
        self.registry["nameless"] = {"name": "nameless"}
        self.convert()
        self.assertEqual(self.run_revert().returncode, 0)
        self.assertEqual(self.flips, [("demo", "fat")])

    def test_a_flag_contradicting_the_receipt_refuses(self) -> None:
        self.convert()
        self.registry["other"] = {"name": "other", "pathHint": "/nowhere/other"}
        result = self.run_revert("--consumer", "other")
        self.assert_refused(result, "will not choose between them")
        self.assertIn("demo", result.stdout)
        self.assertIn("other", result.stdout)

    def test_a_path_hint_naming_a_different_consumer_refuses(self) -> None:
        self.convert()
        self.registry["other"] = {"name": "other", "pathHint": str(self.root)}
        self.assert_refused(self.run_revert(), "is registered as other")

    def test_a_receipt_with_no_consumer_refuses_and_names_the_flag(self) -> None:
        self.convert(consumer=None)
        self.assert_refused(self.run_revert(), "--consumer NAME")

    def test_a_receipt_with_no_consumer_reverts_when_the_flag_supplies_one(self) -> None:
        self.convert(consumer=None)
        self.assertEqual(self.run_revert("--consumer", "demo").returncode, 0)
        self.assertEqual(self.flips, [("demo", "fat")])

    def test_an_unregistered_name_refuses_and_lists_the_known_ones(self) -> None:
        self.convert()
        self.registry = {"alpha": {"name": "alpha", "pathHint": "/nowhere"}}
        self.assert_refused(self.run_revert(), "known consumers: alpha")

    def test_an_unreadable_registry_refuses(self) -> None:
        self.convert()
        with mock.patch.object(
            thin, "read_registry", side_effect=ValueError("bad json")
        ), mock.patch.object(thin, "flip_registry_mode", side_effect=AssertionError):
            result = self.run_install_inproc(
                self.root, "--revert-thin", skip_diff_check=False
            )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("fleet registry cannot be read", result.stdout)


class RegistryReaderTests(InstallTestCase):
    def test_the_registry_reads_keyed_by_name(self) -> None:
        root = self.make_repo()
        (root / thin.FLEET_REGISTRY_FILE).parent.mkdir(parents=True, exist_ok=True)
        (root / thin.FLEET_REGISTRY_FILE).write_text(
            json.dumps({"consumers": [{"name": "alpha", "pathHint": "/a"}]}),
            encoding="utf-8",
        )
        self.assertEqual(
            thin.read_registry(root)["alpha"]["pathHint"], "/a"
        )

    def test_the_reverting_flip_writes_fat_not_thin(self) -> None:
        root = self.make_repo()
        (root / thin.FLEET_REGISTRY_FILE).parent.mkdir(parents=True, exist_ok=True)
        (root / thin.FLEET_REGISTRY_FILE).write_text(
            json.dumps({"consumers": [{"name": "alpha", "mode": "thin"}]}),
            encoding="utf-8",
        )
        thin.flip_registry_mode(root, "alpha", "fat")
        payload = json.loads(
            (root / thin.FLEET_REGISTRY_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["consumers"][0]["mode"], "fat")


class VersionAndPinTests(RevertFixture):
    def test_a_pin_from_another_version_refuses_naming_both(self) -> None:
        # Byte restoration is not reconstructible across versions: install
        # builds from the *current* checkout's manifest, and the pin carries
        # only a version string.
        self.convert()
        self.patch_receipt(version="0.0.1")
        result = self.run_revert()
        self.assert_refused(result, "0.0.1")
        self.assertIn(install.load_manifest()[0]["version"], result.stdout)

    def test_a_pin_with_no_version_refuses(self) -> None:
        self.convert()
        self.patch_receipt(version="")
        self.assert_refused(self.run_revert(), "records no version")

    def test_a_platform_activated_after_conversion_is_not_restored_into(self) -> None:
        # The pin's platform set is what revert restores, never a fresh
        # detection. A consumer who activated another Trellis platform while
        # converted would otherwise get that platform's payload installed by a
        # command that only claimed to undo something -- and the receipts would
        # then vouch for files the pre-conversion tree never had.
        self.convert()
        for marker in install.ACTIVE_TRELLIS_PLATFORM_MARKERS["gemini"]:
            path = self.root / marker
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# activated after the conversion\n", encoding="utf-8")

        self.assertEqual(self.run_revert().returncode, 0)
        installed = (
            self.root / install.INSTALLED_TARGETS_FILE
        ).read_text(encoding="utf-8").split()
        self.assertEqual(
            [entry for entry in installed if entry.startswith(".gemini/")],
            [],
            "revert installed a platform the pin never recorded",
        )

    def test_a_pin_declaring_no_platforms_refuses(self) -> None:
        # Never re-detected from the tree: a converted consumer has had its
        # platform directories deleted, so anchor detection would answer "no
        # platform is active here" and restore a narrower payload than the one
        # that was taken away.
        self.convert()
        self.patch_receipt(platforms=["claude", 7])
        self.assert_refused(self.run_revert(), "declares no usable platform set")

    def test_a_fat_consumer_has_nothing_to_revert(self) -> None:
        result = self.run_revert()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("carries no thin pin", result.stdout)

    def test_an_unwritable_pack_checkout_refuses_before_any_restore(self) -> None:
        # The mirror of the conversion's row, and it matters more here: revert
        # writes ~179 files into the consumer before it reaches the registry,
        # so a registry discovered unwritable at the end is the worse ordering.
        self.convert()

        def unwritable(root, label):
            return f"{label} {root} is not writable" if label == "pack root" else None

        with mock.patch.object(thin, "writability_reason", side_effect=unwritable):
            result = self.run_revert()
        self.assert_refused(result, "pack root")
        self.assertFalse((self.root / ".claude/commands/sd/check.md").exists())

    def test_an_unwritable_target_refuses(self) -> None:
        self.convert()
        self.root.chmod(0o500)
        self.addCleanup(self.root.chmod, 0o700)
        self.assert_refused(self.run_revert(), "not writable")


class UnrestorableTests(RevertFixture):
    """R20-C2: what revert cannot bring back, said rather than assumed."""

    def test_retired_paths_are_named_as_not_restored(self) -> None:
        # All 13 live retired files are in the receipts and absent from the
        # manifest, the source tree, and the templates; provenance keeps
        # hashes, not bytes. A same-version checkout cannot recreate them, so
        # revert reports them instead of reporting success over a gap.
        self.convert()
        self.patch_receipt(retired=["docs/legacy/retired-guide.md"])
        result = self.run_revert()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("not-restored docs/legacy/retired-guide.md", result.stdout)
        self.assertIn("the pack no longer ships it", result.stdout)

    def test_forced_paths_are_reported_as_restored_to_source(self) -> None:
        # Asserting byte-identity for these would be asserting something
        # impossible: the drifted bytes no longer exist anywhere.
        self.convert()
        self.patch_receipt(forced=[".claude/commands/sd/check.md"])
        result = self.run_revert()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "restored-to-source .claude/commands/sd/check.md", result.stdout
        )

    def test_an_unforced_conversion_records_neither_list(self) -> None:
        self.convert()
        payload = json.loads(
            (self.root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        # Written even when empty: an absent key and an empty list read the
        # same to a defaulting reader, and revert's promise depends on telling
        # "nothing was unrestorable" from "this receipt predates the field".
        self.assertEqual(payload["forced"], [])
        self.assertEqual(payload["retired"], [])


class PartialCompletionTests(RevertFixture):
    """One root written, the second failing. Preflight tests do not reach here."""

    def test_a_revert_that_cannot_write_the_registry_says_which_half_landed(
        self,
    ) -> None:
        self.convert()
        with mock.patch.object(
            thin, "read_registry", return_value=self.registry
        ), mock.patch.object(
            thin, "flip_registry_mode", side_effect=OSError("read-only file system")
        ):
            result = self.run_install_inproc(
                self.root, "--revert-thin", skip_diff_check=False
            )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("is fat again and the registry still reads thin", result.stdout)
        self.assertIn("nothing is rolled back", result.stdout)
        # The half that landed really did land -- a diagnostic that named a
        # state the tree is not in would be worse than no diagnostic.
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_FAT
        )
        self.assertTrue((self.root / ".claude/commands/sd/check.md").is_file())

    def test_the_recovery_is_the_hand_edit_not_a_re_run(self) -> None:
        # A re-run would refuse with "carries no thin pin" and leave the row
        # wrong, so advising it would send an operator in a circle.
        self.convert()
        with mock.patch.object(
            thin, "read_registry", return_value=self.registry
        ), mock.patch.object(thin, "flip_registry_mode", side_effect=OSError("nope")):
            result = self.run_install_inproc(
                self.root, "--revert-thin", skip_diff_check=False
            )
        self.assertIn("by hand", result.stdout)
        self.assertNotIn("--revert-thin re-run", result.stdout)
        repeat = self.run_revert()
        self.assertEqual(repeat.returncode, 2)
        self.assertIn("carries no thin pin", repeat.stdout)


class DryRunTests(RevertFixture):
    def test_a_dry_run_names_the_whole_change_set_and_writes_nothing(self) -> None:
        self.convert()
        before = self.snapshot()
        result = self.run_revert("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertIn("would-created", result.stdout)
        for receipt in (
            install.PACK_MANIFEST_FILE,
            install.INSTALLED_TARGETS_FILE,
            install.PROVENANCE_FILE,
        ):
            self.assertIn(f"would-rewrite  {receipt.as_posix()}", result.stdout)
        self.assertIn("would-settings write", result.stdout)
        self.assertIn("would-registry demo -> fat", result.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.flips, [])
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_THIN
        )

    def test_the_dry_run_announces_what_it_will_not_restore_and_what_it_leaves(
        self,
    ) -> None:
        # The two categories an operator most needs *before* running it: a
        # path that cannot come back, and a recorded key revert will not
        # touch. Announcing them only afterwards is announcing them too late.
        self.convert()
        self.patch_receipt(retired=["docs/legacy/retired-guide.md"])
        document = json.loads(
            (self.root / thin.CLAUDE_SETTINGS_FILE).read_text(encoding="utf-8")
        )
        del document[thin.MARKETPLACE_KEY]["sd-ai-command-pack"]
        (self.root / thin.CLAUDE_SETTINGS_FILE).write_text(
            json.dumps(document), encoding="utf-8"
        )

        result = self.run_revert("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("would-not-restore docs/legacy/retired-guide.md", result.stdout)
        self.assertIn("was already absent", result.stdout)

    def test_a_settings_file_that_cannot_be_planned_refuses(self) -> None:
        self.convert()
        settings = self.root / thin.CLAUDE_SETTINGS_FILE
        elsewhere = self.root / "settings-elsewhere.json"
        elsewhere.write_bytes(settings.read_bytes())
        settings.unlink()
        settings.symlink_to(elsewhere)
        self.assert_refused(self.run_revert(), "symlink")

    def test_the_dry_run_set_matches_what_the_real_run_creates(self) -> None:
        # "The tree was unchanged" is satisfied by an empty or wrong printout,
        # so the printed set is compared against the executed run's actual
        # creations rather than merely existing.
        self.convert()
        printed = {
            line.split()[-1]
            for line in self.run_revert("--dry-run").stdout.splitlines()
            if line.startswith("would-created")
        }
        before = set(self.snapshot())
        self.assertEqual(self.run_revert().returncode, 0)
        created = set(self.snapshot()) - before
        self.assertTrue(printed, "the dry run announced no creations")
        self.assertEqual(created - printed, set())


class GithubRoundTripTests(RoundTripTests):
    """The same round trip on a tree that has the `github` kept surfaces.

    `RoundTripTests` runs on `.claude` alone, where the conversion is almost
    entirely deletion. Subclassing rather than copying keeps the byte-for-byte
    promise one assertion: a restore that regresses only for `github` fails
    the inherited test, not a parallel one somebody forgot to update.
    """

    PLATFORM_DIRS = (".claude", ".github")
    PLATFORMS = ("claude", "github")

    def test_the_kept_surfaces_come_back_unrepointed(self) -> None:
        """Lives here and not on the base, which has no such surface.

        A conversion does not delete a kept surface -- it rewrites the pack
        references inside it in place, which is a different operation with a
        different inverse. `.github/PULL_REQUEST_TEMPLATE.md` is the widest of
        them, and the inherited byte-for-byte round trip would report its
        regression among two hundred other paths. This names it.
        """

        template = Path(".github/PULL_REQUEST_TEMPLATE.md")
        fat_bytes = self.before[template.as_posix()]

        self.convert()
        self.assertNotEqual(
            (self.root / template).read_bytes(),
            fat_bytes,
            "the conversion did not repoint the kept surface, so the inverse "
            "this test checks is vacuous",
        )

        self.assertEqual(self.run_revert().returncode, 0)

        self.assertEqual((self.root / template).read_bytes(), fat_bytes)

    def test_the_dry_run_names_the_kept_surfaces_it_would_unrepoint(self) -> None:
        """And touches none of them, which is the half a dry run can get wrong.

        The undo is computed before the payload restore and applied after it,
        so a dry run that reported the plan by computing it twice could report
        one thing and do another. This asserts the announcement against the
        files themselves.
        """

        self.convert()
        converted = self.snapshot()

        result = self.run_revert("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout)

        announced = {
            line.split(None, 1)[1]
            for line in result.stdout.splitlines()
            if line.startswith("would-unrepoint ")
        }
        self.assertIn(".github/PULL_REQUEST_TEMPLATE.md", announced)
        self.assertEqual(self.snapshot(), converted)
        self.assertEqual(self.flips, [], "a dry run touched the registry")


class UninvertibleRepointTests(RevertFixture):
    """A kept file whose relocated reference has no traceable origin."""

    PLATFORM_DIRS = (".claude", ".github")
    PLATFORMS = ("claude", "github")

    def test_a_reference_the_inverse_cannot_reproduce_refuses(self) -> None:
        """And refuses before anything is written, not halfway through.

        The undo is the thin rewrite read backwards, so it is only as sound
        as the forward rule is injective. A machine path inside a URL is the
        readable case: the inverse rewrites it to a repository path, and the
        forward rule's root-relative boundary then declines to rewrite it
        back -- proof that the restoration is not what the conversion
        consumed. Guessing there would corrupt a link in a file the consumer
        owns, so the whole revert stops and names the file.
        """

        self.convert()
        template = self.root / ".github/PULL_REQUEST_TEMPLATE.md"
        template.write_text(
            template.read_text(encoding="utf-8")
            + "see https://example.test/~/.agents/bin/"
            "sd-ai-command-pack-toolchain.sh\n",
            encoding="utf-8",
        )
        occupied = template.read_bytes()

        self.assert_refused(self.run_revert(), ".github/PULL_REQUEST_TEMPLATE.md")
        self.assertEqual(template.read_bytes(), occupied)


if __name__ == "__main__":
    unittest.main()
