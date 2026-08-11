"""The plan phase of a conversion: verdict binding and the settings merge.

Every test here asserts a refusal or an exact written value. There is no
"does something reasonable" row: the whole reason this phase is separated
from the write phase is that a conversion has no rollback, so a refusal that
happens one step late is a consumer that has already lost files.
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
Path = _support.Path
install = _support.install

from installer import thin  # noqa: E402
from installer.registry import PACK_REPOSITORY  # noqa: E402


def _temp_dir(case: unittest.TestCase) -> Path:
    handle = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-thin-plan-")
    case.addCleanup(handle.cleanup)
    return Path(handle.name)


def verdict_document(**overrides: object) -> dict:
    document = {
        "schemaVersion": 1,
        "kind": "thin-resweep-verdict",
        "verdict": "clear",
        "reasons": [],
        "consumer": "demo",
        "repo": "/checkouts/demo",
        "head": "a" * 40,
        "indexDigest": "sha256:index",
        "worktreeDigest": "sha256:worktree",
        "worktreeClean": True,
        "classifierDigest": "sha256:classifier",
        "counts": {"blockers": 0, "packDefects": 0},
    }
    document.update(overrides)
    return document


class VerdictLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _temp_dir(self)

    def test_a_missing_verdict_and_an_unreadable_one_are_distinguished(self) -> None:
        # The operator responses differ: "run the resweep" versus "the file
        # you archived is not the file you think it is".
        missing = thin.load_verdict(self.root / "absent.json")
        self.assertEqual(missing.state, thin.VERDICT_MISSING)

        broken = self.root / "broken.json"
        broken.write_text("{truncated", encoding="utf-8")
        self.assertEqual(thin.load_verdict(broken).state, thin.VERDICT_UNREADABLE)

    def test_a_json_array_is_unreadable_not_present(self) -> None:
        path = self.root / "array.json"
        path.write_text("[]", encoding="utf-8")
        self.assertEqual(thin.load_verdict(path).state, thin.VERDICT_UNREADABLE)

    def test_a_verdict_document_loads(self) -> None:
        path = self.root / "verdict.json"
        path.write_text(json.dumps(verdict_document()), encoding="utf-8")
        load = thin.load_verdict(path)
        self.assertEqual(load.state, thin.VERDICT_PRESENT)
        self.assertEqual(load.document["consumer"], "demo")


class VerdictBindingTests(unittest.TestCase):
    def reasons(self, **overrides: object) -> tuple[str, ...]:
        return thin.verdict_binding_reasons(verdict_document(**overrides),
                                            verdict_document())

    def test_an_identical_verdict_binds(self) -> None:
        self.assertEqual(self.reasons(), ())

    def test_a_different_checkout_path_still_binds(self) -> None:
        # The binding is about the tree, not about how the path is spelled.
        self.assertEqual(self.reasons(repo="/elsewhere/demo"), ())

    def test_a_blocked_verdict_is_refused_with_its_own_reasons(self) -> None:
        reasons = self.reasons(verdict="blocked", reasons=["7 consumer reference(s)"])
        self.assertIn("7 consumer reference(s)", " ".join(reasons))

    def test_a_moved_head_is_refused(self) -> None:
        self.assertIn("head changed since the resweep", self.reasons(head="b" * 40))

    def test_an_edit_with_head_unchanged_is_refused(self) -> None:
        # The case `head` alone misses: a tracked file changes, HEAD does not.
        self.assertIn(
            "indexDigest changed since the resweep",
            self.reasons(indexDigest="sha256:other"),
        )

    def test_a_classifier_edit_is_refused(self) -> None:
        # Partition, registry entry, builder, and resweep edits all land here:
        # `classifier_digest` hashes every one of them.
        self.assertIn(
            "classifierDigest changed since the resweep",
            self.reasons(classifierDigest="sha256:moved"),
        )

    def test_a_field_the_resweep_records_and_the_verdict_lacks_is_refused(self) -> None:
        archived = verdict_document()
        del archived["worktreeDigest"]
        reasons = thin.verdict_binding_reasons(archived, verdict_document())
        self.assertIn("verdict is missing worktreeDigest", " ".join(reasons))

    def test_a_field_the_verdict_has_and_the_resweep_dropped_is_refused(self) -> None:
        # A resweep that stops recording a field must not silently widen what
        # an old verdict authorizes.
        fresh = verdict_document()
        del fresh["classifierDigest"]
        reasons = thin.verdict_binding_reasons(verdict_document(), fresh)
        self.assertIn("verdict records classifierDigest", " ".join(reasons))

    def test_a_foreign_document_is_refused_before_anything_else(self) -> None:
        reasons = thin.verdict_binding_reasons(
            {"kind": "sd-ship-merge-result"}, verdict_document()
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("not a thin resweep verdict", reasons[0])

    def test_an_older_schema_version_is_refused(self) -> None:
        reasons = thin.verdict_binding_reasons(
            verdict_document(schemaVersion=0), verdict_document()
        )
        self.assertEqual(len(reasons), 1)
        self.assertIn("schema version", reasons[0])


class RemoteNormalizationTests(unittest.TestCase):
    CANONICAL = (
        f"git@github.com:{PACK_REPOSITORY}.git",
        f"https://github.com/{PACK_REPOSITORY}.git",
        f"https://github.com/{PACK_REPOSITORY}",
        f"ssh://git@github.com/{PACK_REPOSITORY}.git",
        f"https://token@github.com/{PACK_REPOSITORY}.git",
    )

    def test_every_spelling_of_the_canonical_remote_normalizes_equal(self) -> None:
        for url in self.CANONICAL:
            with self.subTest(url=url):
                self.assertEqual(thin.normalize_github_remote(url), PACK_REPOSITORY)
                self.assertIsNone(thin.pack_repository_reason(url))

    def test_a_non_github_host_is_refused(self) -> None:
        reason = thin.pack_repository_reason(
            f"git@gitlab.com:{PACK_REPOSITORY}.git"
        )
        self.assertIn("not a GitHub repository URL", reason)

    def test_a_different_owner_is_refused(self) -> None:
        reason = thin.pack_repository_reason(
            "git@github.com:someone-else/sd-ai-command-pack.git"
        )
        self.assertIn("someone-else/sd-ai-command-pack", reason)

    def test_the_same_owners_other_repository_is_refused(self) -> None:
        # R18-C3. This is the row an owner-only check accepts, and it writes
        # the fork's locator into every consumer in the fleet.
        reason = thin.pack_repository_reason(
            "git@github.com:platypeeps/sd-ai-command-pack-fork.git"
        )
        self.assertIn("sd-ai-command-pack-fork", reason)

    def test_a_missing_origin_is_refused(self) -> None:
        self.assertIn("no `origin` remote", thin.pack_repository_reason(None))

    def test_a_three_segment_path_is_refused(self) -> None:
        self.assertIsNone(
            thin.normalize_github_remote(
                "https://github.com/platypeeps/sd-ai-command-pack/tree/main"
            )
        )


class SettingsFixture(unittest.TestCase):
    MARKETPLACE = "sd-ai-command-pack"
    PLUGIN = "sd"

    EXPECTED = {
        "extraKnownMarketplaces": {
            "sd-ai-command-pack": {
                "source": {"source": "github", "repo": PACK_REPOSITORY}
            }
        },
        "enabledPlugins": {"sd@sd-ai-command-pack": True},
    }

    def setUp(self) -> None:
        self.root = _temp_dir(self)
        self.settings = self.root / "settings.json"

    def plan(self):
        return thin.plan_settings_merge(self.settings, self.MARKETPLACE, self.PLUGIN)

    def write(self, payload: object) -> None:
        self.settings.write_text(
            payload if isinstance(payload, str) else json.dumps(payload),
            encoding="utf-8",
        )


class SettingsMergeTests(SettingsFixture):
    def test_the_additions_are_the_literal_the_design_names(self) -> None:
        # Asserted by value, not by shape: a shape assertion passes while the
        # repo slug points at a fork.
        self.assertEqual(
            thin.settings_additions(self.MARKETPLACE, self.PLUGIN), self.EXPECTED
        )

    def test_no_key_named_auto_update_appears_anywhere(self) -> None:
        rendered = json.dumps(thin.settings_additions(self.MARKETPLACE, self.PLUGIN))
        self.assertNotIn("autoUpdate", rendered)

    def test_an_absent_file_is_created_with_both_containers(self) -> None:
        plan, reason = self.plan()
        self.assertIsNone(reason)
        self.assertTrue(plan.created_file)
        self.assertEqual(
            sorted(plan.created_containers),
            ["enabledPlugins", "extraKnownMarketplaces"],
        )
        self.assertEqual(plan.merged, self.EXPECTED)

    def test_unrelated_keys_survive_byte_for_byte(self) -> None:
        self.write({"hooks": {"kept": True}, "model": "opus"})
        plan, reason = self.plan()
        self.assertIsNone(reason)
        self.assertEqual(plan.merged["hooks"], {"kept": True})
        self.assertEqual(plan.merged["model"], "opus")

    def test_an_already_identical_entry_is_not_recorded_as_an_addition(self) -> None:
        # The assertion that separates "already true" from "we made it true".
        # `settingsAdditions` is what a revert undoes, so recording a value
        # the consumer set for itself is how revert deletes their setting.
        self.write(self.EXPECTED)
        plan, reason = self.plan()
        self.assertIsNone(reason)
        self.assertEqual(plan.additions, {})
        self.assertFalse(plan.writes_anything)
        self.assertEqual(plan.merged, self.EXPECTED)

    def test_a_half_present_merge_records_only_the_missing_half(self) -> None:
        self.write({"enabledPlugins": {"sd@sd-ai-command-pack": True}})
        plan, reason = self.plan()
        self.assertIsNone(reason)
        self.assertEqual(list(plan.additions), ["extraKnownMarketplaces"])
        self.assertEqual(plan.created_containers, ("extraKnownMarketplaces",))

    def test_an_unrelated_marketplace_entry_survives(self) -> None:
        self.write({"extraKnownMarketplaces": {"other": {"source": "x"}}})
        plan, reason = self.plan()
        self.assertIsNone(reason)
        self.assertEqual(plan.merged["extraKnownMarketplaces"]["other"], {"source": "x"})


class SettingsCollisionTests(SettingsFixture):
    """One test per row of design.md §4's collision table.

    Every row blocks. The file is consumer-owned -- zero partition rows, no
    ownership proof available -- so there is no way to tell a deliberate
    `false` from a stale one, and guessing costs the consumer a setting they
    chose.
    """

    def assert_blocks(self, fragment: str) -> None:
        plan, reason = self.plan()
        self.assertIsNone(plan)
        self.assertIn(fragment, reason)

    def test_a_marketplace_key_with_a_different_source_blocks(self) -> None:
        self.write(
            {"extraKnownMarketplaces": {"sd-ai-command-pack": {"source": "elsewhere"}}}
        )
        self.assert_blocks("extraKnownMarketplaces['sd-ai-command-pack']")

    def test_the_plugin_entry_set_to_false_blocks(self) -> None:
        self.write({"enabledPlugins": {"sd@sd-ai-command-pack": False}})
        self.assert_blocks("enabledPlugins['sd@sd-ai-command-pack']")

    def test_the_plugin_entry_holding_a_string_or_object_blocks(self) -> None:
        for value in ("true", {"enabled": True}):
            with self.subTest(value=value):
                self.write({"enabledPlugins": {"sd@sd-ai-command-pack": value}})
                self.assert_blocks("enabledPlugins['sd@sd-ai-command-pack']")

    def test_a_settings_file_that_is_an_array_or_a_string_blocks(self) -> None:
        for payload in ([1, 2], '"a string"'):
            with self.subTest(payload=payload):
                self.write(payload)
                self.assert_blocks("not an object")

    def test_a_container_that_is_not_an_object_blocks(self) -> None:
        self.write({"extraKnownMarketplaces": ["sd-ai-command-pack"]})
        self.assert_blocks("extraKnownMarketplaces is a list")

    def test_malformed_json_blocks_rather_than_overwriting(self) -> None:
        self.write("{not json")
        self.assert_blocks("cannot be read as JSON")

    def test_a_symlinked_settings_file_blocks(self) -> None:
        elsewhere = self.root / "real-settings.json"
        elsewhere.write_text("{}", encoding="utf-8")
        self.settings.symlink_to(elsewhere)
        self.assert_blocks("is a symlink")


if __name__ == "__main__":
    unittest.main()


class RemovalInventoryTests(unittest.TestCase):
    """R20-C3: the record that makes "re-run converges" true.

    The write order rewrites the receipts before deleting the payload, so
    from the moment the pin lands the receipt no longer lists what is still
    on disk waiting to be deleted. An interrupted re-run that planned from
    the receipt alone would compute an empty remainder and call the
    half-deleted consumer finished.
    """

    def setUp(self) -> None:
        self.target = _temp_dir(self)
        (self.target / ".sd-ai-command-pack").mkdir()

    def write(self, payload: object) -> Path:
        path = self.target / thin.REMOVAL_INVENTORY_FILE
        path.write_text(
            payload if isinstance(payload, str) else json.dumps(payload),
            encoding="utf-8",
        )
        return path

    def test_a_written_inventory_reads_back_with_every_bucket(self) -> None:
        self.write(
            json.loads(
                thin.removal_inventory_content(
                    delete=("b.md", "a.md"), retire=("r.md",), block_strip=(".gitignore",)
                )
            )
        )
        inventory = thin.read_removal_inventory(self.target)
        self.assertEqual(inventory["delete"], ["a.md", "b.md"])
        self.assertEqual(inventory["retire"], ["r.md"])
        self.assertEqual(inventory["blockStrip"], [".gitignore"])

    def test_an_absent_inventory_means_no_interruption(self) -> None:
        self.assertIsNone(thin.read_removal_inventory(self.target))

    def test_a_partial_inventory_is_refused_rather_than_half_believed(self) -> None:
        # A subset presented as the whole is worse than none: the caller
        # would delete what it names and report the conversion finished.
        for payload in (
            "{truncated",
            [1, 2],
            {"kind": "something-else", "schemaVersion": 1,
             "delete": [], "retire": [], "blockStrip": []},
            {"kind": thin.REMOVAL_INVENTORY_KIND, "schemaVersion": 2,
             "delete": [], "retire": [], "blockStrip": []},
            {"kind": thin.REMOVAL_INVENTORY_KIND, "schemaVersion": 1,
             "delete": [], "retire": []},
            {"kind": thin.REMOVAL_INVENTORY_KIND, "schemaVersion": 1,
             "delete": [7], "retire": [], "blockStrip": []},
        ):
            with self.subTest(payload=payload):
                self.write(payload)
                self.assertIsNone(thin.read_removal_inventory(self.target))

    def test_a_symlinked_inventory_is_not_read_through(self) -> None:
        elsewhere = _temp_dir(self) / "inventory.json"
        elsewhere.write_text(
            thin.removal_inventory_content(delete=("a.md",), retire=(), block_strip=()),
            encoding="utf-8",
        )
        (self.target / thin.REMOVAL_INVENTORY_FILE).symlink_to(elsewhere)
        self.assertIsNone(thin.read_removal_inventory(self.target))


class ResidualReceiptTests(unittest.TestCase):
    MANIFEST = {"name": "sd-ai-command-pack", "version": "0.66.1"}

    def test_the_residual_files_map_comes_from_the_receipt_not_the_partition(
        self,
    ) -> None:
        # The partition has 557 keep rows; this consumer has two of them. A
        # partition-derived residual writes a receipt vouching for files that
        # are not on disk.
        existing = {"kept.md": "sha256:a", "deleted.md": "sha256:b"}
        self.assertEqual(
            thin.residual_provenance_files(existing, frozenset({"kept.md"})),
            {"kept.md": "sha256:a"},
        )

    def test_a_residual_entry_with_no_receipt_digest_is_not_invented(self) -> None:
        self.assertEqual(
            thin.residual_provenance_files({}, frozenset({"kept.md"})), {}
        )

    def test_the_thin_provenance_carries_every_pin_key(self) -> None:
        payload = json.loads(
            thin.thin_provenance_content(
                self.MANIFEST,
                files={"kept.md": "sha256:a"},
                platforms=("claude", "codex"),
                consumer="demo",
                additions={"enabledPlugins": {"sd@sd-ai-command-pack": True}},
                forced=("AGENTS.md",),
            )
        )
        self.assertEqual(payload["mode"], "thin")
        self.assertEqual(payload["platforms"], ["claude", "codex"])
        self.assertEqual(payload["consumer"], "demo")
        self.assertEqual(payload["forced"], ["AGENTS.md"])
        self.assertEqual(payload["files"], {"kept.md": "sha256:a"})
        self.assertEqual(payload["version"], "0.66.1")

    def test_the_installed_manifest_carries_the_durable_thin_marker(self) -> None:
        # The second witness, and the earlier of the two writes.
        payload = json.loads(thin.thin_manifest_content(self.MANIFEST))
        self.assertEqual(payload["mode"], "thin")
        self.assertEqual(payload["name"], "sd-ai-command-pack")

    def test_the_targets_receipt_is_the_sorted_residual(self) -> None:
        self.assertEqual(
            thin.residual_targets_content(frozenset({"b.md", "a.md"})), "a.md\nb.md\n"
        )


class RemoteEdgeTests(unittest.TestCase):
    """The spellings that are not URLs at all, and the one shortcut for them."""

    def test_an_empty_remote_is_not_a_repository(self) -> None:
        self.assertIsNone(thin.normalize_github_remote("   "))

    def test_a_non_git_scheme_is_refused(self) -> None:
        # `file:///srv/mirrors/sd-ai-command-pack.git` is a working git remote
        # and is emphatically not the GitHub marketplace source.
        self.assertIsNone(
            thin.normalize_github_remote("file:///srv/sd-ai-command-pack.git")
        )

    def test_render_settings_is_stable_and_sorted(self) -> None:
        self.assertEqual(
            thin.render_settings({"b": 1, "a": 2}), '{\n  "a": 2,\n  "b": 1\n}\n'
        )

    def test_a_conversion_with_no_registered_consumer_writes_no_consumer_key(
        self,
    ) -> None:
        # `--consumer` is optional, and an absent one must not become a
        # `"consumer": null` a later reader has to special-case.
        payload = json.loads(
            thin.thin_provenance_content(
                {"name": "p", "version": "1"},
                files={},
                platforms=(),
                consumer=None,
                additions={},
                forced=(),
            )
        )
        self.assertNotIn("consumer", payload)


class StalenessTests(unittest.TestCase):
    """A conversion refuses a stale consumer rather than becoming an installer.

    R19-C2: all eight consumer receipts hold 210 entries and none lists
    `scripts/sd-ai-command-pack-pack-update.sh`, which the current manifest
    ships and the partition classifies as a machine row a `codex` consumer
    retains. Converting anyway produces a consumer that passes conversion and
    fails `--check` on the very next command, for a file it never received.
    """

    def test_a_matching_version_is_current(self) -> None:
        self.assertIsNone(thin.version_currency_reason("0.66.1", "0.66.1"))

    def test_a_stale_version_names_both_and_the_fix(self) -> None:
        reason = thin.version_currency_reason("0.65.0", "0.66.1")
        self.assertIn("0.65.0", reason)
        self.assertIn("0.66.1", reason)
        self.assertIn("install.py TARGET", reason)

    def test_a_receipt_with_no_version_at_all_is_refused(self) -> None:
        self.assertIn("records no version", thin.version_currency_reason(None, "1"))

    def test_the_exact_assertion_names_every_missing_target(self) -> None:
        # The check that catches a consumer whose version matches but whose
        # tree was refreshed against a partially applied install -- the case
        # the version comparison is only a proxy for.
        reason = thin.stale_receipt_reason(
            frozenset({"a.md", "b.md", "c.md"}), frozenset({"b.md"})
        )
        self.assertIn("a.md", reason)
        self.assertIn("c.md", reason)
        self.assertIn("2 target(s)", reason)

    def test_a_receipt_that_is_a_superset_is_current(self) -> None:
        self.assertIsNone(
            thin.stale_receipt_reason(frozenset({"a.md"}), frozenset({"a.md", "b.md"}))
        )


class WritabilityTests(unittest.TestCase):
    """Both roots, before either is written."""

    def test_a_writable_directory_passes(self) -> None:
        self.assertIsNone(thin.writability_reason(_temp_dir(self), "target"))

    def test_a_missing_directory_is_named(self) -> None:
        reason = thin.writability_reason(_temp_dir(self) / "absent", "pack root")
        self.assertIn("pack root", reason)
        self.assertIn("not a directory", reason)

    def test_a_read_only_directory_is_refused(self) -> None:
        # Probed by writing, not by `os.access`: access answers the wrong
        # question on a read-only mount and under an ACL.
        root = _temp_dir(self) / "readonly"
        root.mkdir()
        root.chmod(0o500)
        self.addCleanup(root.chmod, 0o700)
        self.assertIn("not writable", thin.writability_reason(root, "target"))


class ResweepModuleTests(unittest.TestCase):
    def test_the_shipped_resweep_imports_as_a_module(self) -> None:
        # Imported rather than reimplemented: the verdict's binding fields are
        # whatever that script computes, and classifier_digest hashes its
        # bytes, so the two are already bound to each other.
        module = thin.load_resweep_module(_support.PACK_ROOT)
        self.assertTrue(callable(module.resweep_consumer))
        self.assertEqual(module.SCHEMA_VERSION, 1)


class ReceiptAgreementTests(unittest.TestCase):
    """Do the two version-bearing receipts describe the same install?

    Narrower than `inspect_receipts` deliberately: that reports per-file
    content drift in the same list, and refusing on the whole list would make
    `--force` unreachable, which is precisely what `--force` is for.
    """

    def setUp(self) -> None:
        self.target = _temp_dir(self)
        (self.target / ".sd-ai-command-pack").mkdir()

    def write(self, receipt, payload) -> None:
        (self.target / receipt).write_text(
            payload if isinstance(payload, str) else json.dumps(payload),
            encoding="utf-8",
        )

    def test_matching_versions_agree(self) -> None:
        for receipt in (install.PACK_MANIFEST_FILE, install.PROVENANCE_FILE):
            self.write(receipt, {"version": "0.66.1"})
        self.assertIsNone(thin.receipt_disagreement_reason(self.target))

    def test_differing_versions_are_reported_with_both_values(self) -> None:
        self.write(install.PACK_MANIFEST_FILE, {"version": "0.66.1"})
        self.write(install.PROVENANCE_FILE, {"version": "0.0.1"})
        reason = thin.receipt_disagreement_reason(self.target)
        self.assertIn("0.66.1", reason)
        self.assertIn("0.0.1", reason)

    def test_an_unreadable_receipt_is_named(self) -> None:
        self.write(install.PACK_MANIFEST_FILE, "{truncated")
        self.assertIn("manifest.json cannot be read",
                      thin.receipt_disagreement_reason(self.target))

    def test_a_receipt_that_is_not_an_object_is_named(self) -> None:
        self.write(install.PACK_MANIFEST_FILE, [1, 2])
        self.assertIn("is not an object",
                      thin.receipt_disagreement_reason(self.target))
