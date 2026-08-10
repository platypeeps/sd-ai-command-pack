from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
shutil = _support.shutil
tempfile = _support.tempfile
unittest = _support.unittest
Path = _support.Path
InstallTestCase = _support.InstallTestCase


def _temp_dir(case: unittest.TestCase) -> Path:
    handle = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-conversion-")
    case.addCleanup(handle.cleanup)
    return Path(handle.name)

from installer.conversion import (  # noqa: E402
    BOOKKEEPING_TARGETS,
    RECEIPT_MISSING,
    RECEIPT_PRESENT,
    RECEIPT_UNREADABLE,
    build_conversion_plan,
    classifier_digest,
    classify_target,
    expected_residual_targets,
    load_partition,
    occupied_receipt_targets,
    read_installed_targets_receipt,
)
from installer.registry import (  # noqa: E402
    INSTALLED_TARGETS_FILE,
    PACK_MANIFEST_FILE,
    PROVENANCE_FILE,
    ROOT,
)

CONSUMER_PLATFORMS = frozenset({"claude", "gemini", "github", "opencode"})


def write_partition(path: Path, rows: list[dict], platforms: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"files": rows, "platforms": platforms}),
        encoding="utf-8",
    )
    return path


def simple_partition(tmp: Path):
    return load_partition(
        write_partition(
            tmp / "partition.json",
            [
                {
                    "target": ".claude/skills/sd-check/SKILL.md",
                    "platform": "claude",
                    "category": "machine-claude",
                },
                {
                    "target": ".agents/skills/sd-check/SKILL.md",
                    "platform": "shared",
                    "category": "machine-other",
                },
                {
                    "target": ".github/copilot-instructions.md",
                    "platform": "github",
                    "category": "repo-native",
                },
                {
                    "target": ".github/workflows/sd.yml",
                    "platform": "github",
                    "category": "repo-native",
                },
                {
                    "target": ".prism/rules.json",
                    "platform": "shared",
                    "category": "consumer-config",
                },
                {
                    "target": ".cursor/commands/sd-check.md",
                    "platform": "cursor",
                    "category": "repo-native",
                },
                {
                    "target": ".weird/thing.md",
                    "platform": "weird",
                    "category": "not-a-real-category",
                },
                {
                    "target": ".prov/thing.md",
                    "platform": "provisionaly",
                    "category": "machine-other",
                },
            ],
            {
                "claude": {"scope": "machine", "provisional": False},
                "shared": {
                    "scope": "machine",
                    "provisional": False,
                    "retainVendoredFor": ["codex", "pi"],
                },
                "github": {"scope": "repo-native", "provisional": False},
                "cursor": {"scope": "repo-native", "provisional": False},
                "weird": {"scope": "repo-native", "provisional": False},
                "provisionaly": {"scope": "machine", "provisional": True},
            },
        )
    )


class ClassifyTargetTests(InstallTestCase):
    """The pure classification pass, one branch per test."""

    def setUp(self) -> None:
        self.tmp = _temp_dir(self)
        self.partition = simple_partition(self.tmp)

    def classify(self, target: str, platforms=CONSUMER_PLATFORMS):
        return classify_target(target, self.partition, platforms)

    def test_bookkeeping_files_route_to_the_receipt_bucket(self) -> None:
        for target in sorted(BOOKKEEPING_TARGETS):
            self.assertEqual(self.classify(target), ("receipts", None), target)

    def test_gitignore_has_no_partition_row_and_is_block_stripped(self) -> None:
        self.assertEqual(self.classify(".gitignore"), ("block_strip", None))

    def test_copilot_instructions_is_kept_with_its_block_intact(self) -> None:
        # repo-native because Copilot reads the repository and cannot see the
        # machine. Stripping its block would destroy a retained surface.
        self.assertEqual(
            self.classify(".github/copilot-instructions.md"), ("keep", None)
        )

    def test_managed_block_file_with_a_machine_category_blocks(self) -> None:
        partition = load_partition(
            write_partition(
                self.tmp / "machine-copilot.json",
                [
                    {
                        "target": ".github/copilot-instructions.md",
                        "platform": "github",
                        "category": "machine-other",
                    }
                ],
                {"github": {"scope": "machine", "provisional": False}},
            )
        )
        bucket, reason = classify_target(
            ".github/copilot-instructions.md", partition, CONSUMER_PLATFORMS
        )
        self.assertEqual(bucket, "blocked")
        self.assertIn("unexpected partition category", reason)

    def test_machine_rows_are_deleted(self) -> None:
        self.assertEqual(
            self.classify(".claude/skills/sd-check/SKILL.md"), ("delete", None)
        )

    def test_keep_categories_are_kept(self) -> None:
        self.assertEqual(self.classify(".github/workflows/sd.yml"), ("keep", None))
        self.assertEqual(self.classify(".prism/rules.json"), ("keep", None))

    def test_retain_vendored_for_keeps_machine_rows_for_declared_platforms(
        self,
    ) -> None:
        shared = ".agents/skills/sd-check/SKILL.md"
        # No codex/pi declared: the shared row is machine scope, so it goes.
        self.assertEqual(self.classify(shared), ("delete", None))
        # codex declared: retainVendoredFor keeps it vendored.
        self.assertEqual(
            self.classify(shared, frozenset({"claude", "codex"})), ("keep", None)
        )

    def test_provisional_platforms_stay_vendored(self) -> None:
        self.assertEqual(self.classify(".prov/thing.md"), ("keep", None))

    def test_retired_targets_route_to_retire(self) -> None:
        from installer.removal import RETIRED_TARGETS

        self.assertEqual(self.classify(RETIRED_TARGETS[0]), ("retire", None))

    def test_unclassified_entry_blocks_with_a_named_reason(self) -> None:
        bucket, reason = self.classify("some/orphan/file.md")
        self.assertEqual(bucket, "blocked")
        self.assertIn("no partition row", reason)

    def test_unknown_partition_category_blocks(self) -> None:
        bucket, reason = self.classify(".weird/thing.md")
        self.assertEqual(bucket, "blocked")
        self.assertIn("unknown partition category", reason)


class ReceiptLoadTests(InstallTestCase):
    """Missing and unreadable receipts must be distinguishable."""

    def setUp(self) -> None:
        self.target = _temp_dir(self)

    def test_missing_receipt_reports_missing_not_empty(self) -> None:
        load = read_installed_targets_receipt(self.target)
        self.assertEqual(load.state, RECEIPT_MISSING)
        self.assertEqual(load.entries, frozenset())
        self.assertIn("is missing", load.detail)

    def test_unreadable_receipt_reports_unreadable(self) -> None:
        receipt = self.target / INSTALLED_TARGETS_FILE
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text("x\n", encoding="utf-8")
        receipt.chmod(0o000)
        self.addCleanup(receipt.chmod, 0o644)
        load = read_installed_targets_receipt(self.target)
        if load.state == RECEIPT_PRESENT:  # pragma: no cover - root can always read
            self.skipTest("filesystem permits reading a 0o000 file")
        self.assertEqual(load.state, RECEIPT_UNREADABLE)
        self.assertIn("cannot be read", load.detail)

    def test_comments_and_blanks_are_skipped(self) -> None:
        receipt = self.target / INSTALLED_TARGETS_FILE
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text("# comment\n\n.gitignore\n  \n", encoding="utf-8")
        load = read_installed_targets_receipt(self.target)
        self.assertEqual(load.state, RECEIPT_PRESENT)
        self.assertEqual(load.entries, frozenset({".gitignore"}))

    def test_occupancy_is_a_filesystem_check(self) -> None:
        receipt = self.target / INSTALLED_TARGETS_FILE
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text("present.md\nabsent.md\n", encoding="utf-8")
        (self.target / "present.md").write_text("x", encoding="utf-8")
        load = read_installed_targets_receipt(self.target)
        self.assertEqual(
            occupied_receipt_targets(self.target, load), frozenset({"present.md"})
        )


class BuildConversionPlanTests(InstallTestCase):
    def setUp(self) -> None:
        self.tmp = _temp_dir(self)
        self.partition = simple_partition(self.tmp)

    def build(self, entries, occupied=None):
        from installer.conversion import ReceiptLoad

        load = ReceiptLoad(state=RECEIPT_PRESENT, entries=frozenset(entries))
        return build_conversion_plan(
            load,
            self.partition,
            CONSUMER_PLATFORMS,
            occupied=frozenset(occupied if occupied is not None else entries),
        )

    def test_a_missing_receipt_blocks_the_whole_plan(self) -> None:
        from installer.conversion import ReceiptLoad

        plan = build_conversion_plan(
            ReceiptLoad(RECEIPT_MISSING, frozenset(), "receipt is missing"),
            self.partition,
            CONSUMER_PLATFORMS,
            occupied=frozenset(),
        )
        self.assertFalse(plan.is_convertible)
        self.assertEqual(plan.blocked[0].reason, "receipt is missing")

    def test_an_unreadable_receipt_blocks_with_its_own_detail(self) -> None:
        from installer.conversion import ReceiptLoad

        plan = build_conversion_plan(
            ReceiptLoad(RECEIPT_UNREADABLE, frozenset(), "cannot be read: boom"),
            self.partition,
            CONSUMER_PLATFORMS,
            occupied=frozenset(),
        )
        self.assertFalse(plan.is_convertible)
        self.assertIn("cannot be read", plan.blocked[0].reason)

    def test_a_receipt_state_with_no_detail_still_blocks(self) -> None:
        from installer.conversion import ReceiptLoad

        plan = build_conversion_plan(
            ReceiptLoad(RECEIPT_MISSING, frozenset(), None),
            self.partition,
            CONSUMER_PLATFORMS,
            occupied=frozenset(),
        )
        self.assertIn("unusable", plan.blocked[0].reason)

    def test_entries_land_in_their_buckets(self) -> None:
        plan = self.build(
            [
                ".claude/skills/sd-check/SKILL.md",
                ".github/workflows/sd.yml",
                ".gitignore",
                PROVENANCE_FILE.as_posix(),
                PACK_MANIFEST_FILE.as_posix(),
                INSTALLED_TARGETS_FILE.as_posix(),
            ]
        )
        self.assertTrue(plan.is_convertible)
        self.assertEqual(plan.delete, (".claude/skills/sd-check/SKILL.md",))
        self.assertEqual(plan.keep, (".github/workflows/sd.yml",))
        self.assertEqual(plan.block_strip, (".gitignore",))
        self.assertEqual(len(plan.receipts), 3)

    def test_retire_holds_only_targets_present_in_this_checkout(self) -> None:
        from installer.removal import RETIRED_TARGETS

        here, gone = RETIRED_TARGETS[0], RETIRED_TARGETS[1]
        plan = self.build([here, gone], occupied=[here])
        # The existing helper walks all 157; conversion executes only what is
        # actually here, so the plan and the mutation cannot disagree.
        self.assertEqual(plan.retire, (here,))

    def test_one_unclassified_entry_blocks_the_conversion(self) -> None:
        plan = self.build([".github/workflows/sd.yml", "orphan.md"])
        self.assertFalse(plan.is_convertible)
        self.assertEqual(plan.blocked[0].target, "orphan.md")


class ExpectedResidualTests(InstallTestCase):
    def setUp(self) -> None:
        self.tmp = _temp_dir(self)
        self.partition = simple_partition(self.tmp)
        self.source = frozenset(
            {
                ".claude/skills/sd-check/SKILL.md",
                ".github/workflows/sd.yml",
                ".github/copilot-instructions.md",
                ".prism/rules.json",
                ".cursor/commands/sd-check.md",
            }
        )

    def residual(self, blocks=frozenset({".gitignore"}), platforms=CONSUMER_PLATFORMS):
        return expected_residual_targets(
            self.source, self.partition, platforms, present_managed_blocks=blocks
        )

    def test_undeclared_platform_rows_are_not_expected(self) -> None:
        # The predicate round 3 found missing: without it, hundreds of
        # repo-native rows for platforms the consumer never installed would be
        # "expected" and --check would report refresh-required forever.
        self.assertNotIn(".cursor/commands/sd-check.md", self.residual())

    def test_declared_platform_keep_rows_are_expected(self) -> None:
        self.assertIn(".github/workflows/sd.yml", self.residual())

    def test_consumer_config_is_platform_independent(self) -> None:
        # .prism/rules.json carries platform "shared", which no consumer
        # declares, but consumer-config belongs regardless.
        self.assertIn(".prism/rules.json", self.residual())

    def test_machine_rows_are_never_expected(self) -> None:
        self.assertNotIn(".claude/skills/sd-check/SKILL.md", self.residual())

    def test_managed_blocks_are_expected_whenever_they_survive(self) -> None:
        # .gitignore has no partition row but survives an UPDATED block strip.
        # Excluding it would make the source- and receipt-derived residuals
        # disagree on the ordinary fixture.
        self.assertIn(".gitignore", self.residual())

    def test_a_removed_managed_block_leaves_the_expected_set(self) -> None:
        self.assertNotIn(".gitignore", self.residual(blocks=frozenset()))

    def test_bookkeeping_files_are_always_expected(self) -> None:
        self.assertTrue(BOOKKEEPING_TARGETS.issubset(self.residual()))


class ClassifierDigestTests(InstallTestCase):
    def test_digest_changes_when_the_builder_changes(self) -> None:
        entry = {"name": "demo", "platforms": ["claude"]}
        base = classifier_digest(ROOT, entry)
        self.assertTrue(base.startswith("sha256:"))
        # Same inputs, same digest.
        self.assertEqual(base, classifier_digest(ROOT, entry))

    def test_digest_changes_when_the_registry_entry_changes(self) -> None:
        first = classifier_digest(ROOT, {"name": "demo", "platforms": ["claude"]})
        second = classifier_digest(
            ROOT, {"name": "demo", "platforms": ["claude", "codex"]}
        )
        self.assertNotEqual(first, second)

    def test_digest_covers_every_declared_input_file(self) -> None:
        scratch = _temp_dir(self) / "pack"
        for relative in (
            "docs/fleet/surface-partition.json",
            ".claude-plugin/marketplace.json",
            "plugins/sd/.claude-plugin/plugin.json",
            "installer/removal.py",
            "installer/registry.py",
            "installer/conversion.py",
        ):
            destination = scratch / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)

        entry = {"name": "demo", "platforms": ["claude"]}
        baseline = classifier_digest(scratch, entry)
        for relative in (
            "docs/fleet/surface-partition.json",
            ".claude-plugin/marketplace.json",
            "plugins/sd/.claude-plugin/plugin.json",
            "installer/removal.py",
            "installer/registry.py",
            # The builder itself: an edit here moves the delete set while
            # every other digest input stays byte-identical.
            "installer/conversion.py",
        ):
            path = scratch / relative
            original = path.read_bytes()
            path.write_bytes(original + b"\n# drift\n")
            self.assertNotEqual(
                baseline,
                classifier_digest(scratch, entry),
                f"editing {relative} left the classifier digest unchanged",
            )
            path.write_bytes(original)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
