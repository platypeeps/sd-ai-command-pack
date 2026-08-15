from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

importlib = _support.importlib
json = _support.json
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
Path = _support.Path
mock = _support.mock
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase
registry = importlib.import_module("installer.registry")

PARTITION_SCRIPT = PACK_ROOT / ".github/scripts/partition-surfaces.py"
PARTITION_ARTIFACT = PACK_ROOT / "docs/fleet/surface-partition.json"

# Every TARGET_OVERRIDES pattern must match at least one row or the stale
# override gate fires, so synthetic manifests carry one row per pattern.
BASELINE_ROWS: tuple[dict[str, str], ...] = (
    {"platform": "claude", "kind": "config", "target": ".claude/rules/sd-base.md"},
    {
        "platform": "claude",
        "kind": "doc",
        "target": ".claude/sd-ai-command-pack/contract.md",
    },
    {"platform": "shared", "kind": "config", "target": ".prism/rules.json"},
    {"platform": "shared", "kind": "config", "target": ".gito/config.toml"},
    {
        "platform": "shared",
        "kind": "script",
        "target": "scripts/sd-ai-command-pack-base.sh",
    },
    {
        "platform": "shared",
        "kind": "script",
        "target": ".sd-ai-command-pack/bin/sd-ai-command-pack-base.py",
    },
)


def load_partitioner():
    module = sys.modules.get("partition_surfaces")
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(
        "partition_surfaces", PARTITION_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load partition module from {PARTITION_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["partition_surfaces"] = module
    spec.loader.exec_module(module)
    return module


class PartitionSurfacesTests(InstallTestCase):
    """Fail-closed classifier over manifest rows and PLATFORM_REGISTRY."""

    def setUp(self) -> None:
        super().setUp()
        self.partition = load_partitioner()

    def build_root(
        self, rows: list[dict[str, str]], *, baseline: bool = True
    ) -> Path:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        entries = ([*BASELINE_ROWS] if baseline else []) + rows
        (root / "manifest.json").write_text(
            json.dumps({"version": "9.9.9", "files": entries}, indent=2) + "\n",
            encoding="utf-8",
        )
        return root

    # --- committed-tree gate ---------------------------------------------

    def test_check_mode_is_clean_on_committed_tree(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PARTITION_SCRIPT), "--check"],
            cwd=PACK_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            "docs/fleet/surface-partition.json drifts from manifest.json and "
            f"the registry; run `make generate`:\n{result.stdout}{result.stderr}",
        )

    def test_committed_artifact_covers_every_manifest_row(self) -> None:
        manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        committed = json.loads(PARTITION_ARTIFACT.read_text(encoding="utf-8"))

        self.assertEqual(committed["schemaVersion"], self.partition.SCHEMA_VERSION)
        self.assertEqual(committed["manifestVersion"], manifest["version"])
        self.assertEqual(len(committed["files"]), len(manifest["files"]))
        self.assertEqual(
            {row["target"] for row in manifest["files"]},
            {entry["target"] for entry in committed["files"]},
        )
        self.assertEqual(sum(committed["counts"].values()), len(manifest["files"]))
        self.assertEqual(set(committed["counts"]), set(self.partition.CATEGORIES))
        self.assertEqual(set(committed["platforms"]), set(registry.PLATFORM_REGISTRY))

    def test_committed_dispositions_match_known_decisions(self) -> None:
        committed = json.loads(PARTITION_ARTIFACT.read_text(encoding="utf-8"))

        self.assertEqual(
            committed["platforms"]["github"],
            {"scope": "repo-native", "provisional": False},
        )
        self.assertEqual(
            committed["platforms"]["claude"],
            {"scope": "machine", "provisional": False},
        )
        # Verified by executed user-scope probes against the installed CLIs.
        for platform in ("gemini", "opencode"):
            with self.subTest(platform=platform):
                self.assertEqual(
                    committed["platforms"][platform],
                    {"scope": "machine", "provisional": False},
                )
        # Codex is repo-native because the pack ships no `.codex/**` rows at
        # all, not because of where it reads skills from: an executed probe
        # (`08-09-codex-home-skills-family/research/codex-skills-resolution-probe.md`)
        # shows it merges project-root `.agents/skills`, `$HOME/.agents/skills`,
        # and `$CODEX_HOME/skills`. That is why it is absent from the retention
        # list below while still being repo-native here -- the two say different
        # things, and an earlier revision conflated them.
        self.assertEqual(
            committed["platforms"]["codex"],
            {"scope": "repo-native", "provisional": False},
        )
        self.assertEqual(
            committed["platforms"]["shared"],
            {
                "scope": "machine",
                "provisional": False,
                "retainVendoredFor": ["pi"],
            },
        )

    def test_retain_vendored_for_is_absent_on_every_other_platform(self) -> None:
        committed = json.loads(PARTITION_ARTIFACT.read_text(encoding="utf-8"))

        carriers = {
            platform
            for platform, entry in committed["platforms"].items()
            if "retainVendoredFor" in entry
        }

        # Additive optional field: consumers reading only scope/provisional
        # keep working, so it may appear nowhere else without review.
        self.assertEqual(carriers, {"shared"})

    def test_retained_platforms_are_repo_native_and_registered(self) -> None:
        committed = json.loads(PARTITION_ARTIFACT.read_text(encoding="utf-8"))

        for platform in committed["platforms"]["shared"]["retainVendoredFor"]:
            with self.subTest(platform=platform):
                # A retained platform must actually be the repo-local reader
                # the carve-out exists for.
                self.assertIn(platform, registry.PLATFORM_REGISTRY)
                self.assertEqual(
                    committed["platforms"][platform]["scope"], "repo-native"
                )

    def test_no_consumer_currently_serves_a_retained_platform(self) -> None:
        # The executable detection rule migration tooling applies: a consumer
        # keeps the vendored rows iff its registry `platforms` array
        # intersects `retainVendoredFor`. Pinning it here means a consumer that
        # starts declaring a retained platform surfaces as a deliberate change.
        # It reads the list rather than naming its members, so retiring one --
        # as `codex` was, on probe evidence -- does not silently weaken it.
        committed = json.loads(PARTITION_ARTIFACT.read_text(encoding="utf-8"))
        fleet = json.loads(
            (PACK_ROOT / "docs/fleet/consumers.json").read_text(encoding="utf-8")
        )
        retained = set(committed["platforms"]["shared"]["retainVendoredFor"])

        serving = {
            consumer["name"]
            for consumer in fleet["consumers"]
            if retained & set(consumer.get("platforms", []))
        }

        self.assertEqual(serving, set())

    def test_committed_consumer_config_and_shared_runtime_slices(self) -> None:
        committed = json.loads(PARTITION_ARTIFACT.read_text(encoding="utf-8"))
        by_category: dict[str, list[str]] = {}
        for entry in committed["files"]:
            by_category.setdefault(entry["category"], []).append(entry["target"])

        for target in by_category["consumer-config"]:
            with self.subTest(target=target):
                self.assertTrue(
                    target.startswith(
                        (
                            ".claude/rules/",
                            ".claude/sd-ai-command-pack/",
                            ".prism/",
                            ".gito/",
                            ".sd-ai-command-pack/bin/",
                        )
                    )
                )
        shared_runtime = [
            entry["target"] for entry in committed["files"] if entry["sharedRuntime"]
        ]
        self.assertTrue(shared_runtime)
        for target in shared_runtime:
            with self.subTest(target=target):
                self.assertTrue(target.startswith("scripts/"))
        # github ships repo-native by construction.
        self.assertTrue(
            any(target.startswith(".github/") for target in by_category["repo-native"])
        )

    # --- rule order --------------------------------------------------------

    def test_target_override_wins_over_platform_disposition(self) -> None:
        root = self.build_root(
            [
                {
                    "platform": "shared",
                    "kind": "skill",
                    "target": ".agents/skills/sd-thing/SKILL.md",
                }
            ]
        )

        partition = self.partition.build_partition(root)
        by_target = {entry["target"]: entry for entry in partition["files"]}

        # shared is machine-dispositioned, so its default is machine-other; the
        # scripts/ override moves those rows to machine-claude + sharedRuntime.
        self.assertEqual(
            by_target[".agents/skills/sd-thing/SKILL.md"]["category"], "machine-other"
        )
        self.assertFalse(by_target[".agents/skills/sd-thing/SKILL.md"]["sharedRuntime"])
        self.assertEqual(
            by_target["scripts/sd-ai-command-pack-base.sh"]["category"],
            "machine-claude",
        )
        self.assertTrue(by_target["scripts/sd-ai-command-pack-base.sh"]["sharedRuntime"])
        # claude is machine-dispositioned, but .claude/rules is consumer config.
        self.assertEqual(
            by_target[".claude/rules/sd-base.md"]["category"], "consumer-config"
        )
        self.assertEqual(
            by_target[".claude/sd-ai-command-pack/contract.md"]["category"],
            "consumer-config",
        )
        # A `script` row is machine-claude everywhere else; under this
        # override it is consumer-config, which is the whole point of the
        # entry -- the resolver has to survive the conversion that removes the
        # scripts it resolves.
        for target in (
            ".prism/rules.json",
            ".gito/config.toml",
            ".sd-ai-command-pack/bin/sd-ai-command-pack-base.py",
        ):
            with self.subTest(target=target):
                self.assertEqual(by_target[target]["category"], "consumer-config")

    def test_platform_disposition_splits_claude_from_other_machine(self) -> None:
        root = self.build_root(
            [
                {
                    "platform": "claude",
                    "kind": "skill",
                    "target": ".claude/skills/sd-thing/SKILL.md",
                },
                {
                    "platform": "gemini",
                    "kind": "command",
                    "target": ".gemini/commands/sd/thing.toml",
                },
                {
                    "platform": "github",
                    "kind": "prompt",
                    "target": ".github/prompts/sd-thing.prompt.md",
                },
                {
                    "platform": "cursor",
                    "kind": "command",
                    "target": ".cursor/commands/sd-thing.md",
                },
            ]
        )

        partition = self.partition.build_partition(root)
        by_target = {entry["target"]: entry["category"] for entry in partition["files"]}

        self.assertEqual(by_target[".claude/skills/sd-thing/SKILL.md"], "machine-claude")
        self.assertEqual(by_target[".gemini/commands/sd/thing.toml"], "machine-other")
        self.assertEqual(by_target[".github/prompts/sd-thing.prompt.md"], "repo-native")
        self.assertEqual(by_target[".cursor/commands/sd-thing.md"], "repo-native")

    def test_provisional_flag_round_trips_into_the_schema(self) -> None:
        root = self.build_root([])
        dispositions = dict(self.partition.PLATFORM_DISPOSITIONS)
        dispositions["claude"] = ("machine", True)

        with mock.patch.object(self.partition, "PLATFORM_DISPOSITIONS", dispositions):
            partition = self.partition.build_partition(root)

        self.assertTrue(partition["platforms"]["claude"]["provisional"])
        self.assertFalse(partition["platforms"]["github"]["provisional"])
        self.assertEqual(partition["manifestVersion"], "9.9.9")
        self.assertEqual(
            set(partition["platforms"]), set(registry.PLATFORM_REGISTRY)
        )

    def test_files_are_emitted_in_target_order(self) -> None:
        root = self.build_root(
            [
                {
                    "platform": "claude",
                    "kind": "skill",
                    "target": ".claude/skills/sd-zebra/SKILL.md",
                },
                {
                    "platform": "claude",
                    "kind": "skill",
                    "target": ".claude/skills/sd-alpha/SKILL.md",
                },
            ]
        )

        partition = self.partition.build_partition(root)
        targets = [entry["target"] for entry in partition["files"]]

        self.assertEqual(targets, sorted(targets))

    # --- fail-closed conditions -------------------------------------------

    def test_unknown_platform_fails(self) -> None:
        root = self.build_root(
            [
                {
                    "platform": "nonesuch",
                    "kind": "skill",
                    "target": ".nonesuch/skills/sd-thing/SKILL.md",
                }
            ]
        )

        with self.assertRaisesRegex(
            self.partition.PartitionError, "unknown platform 'nonesuch'"
        ):
            self.partition.build_partition(root)

    def test_unknown_kind_fails(self) -> None:
        root = self.build_root(
            [
                {
                    "platform": "claude",
                    "kind": "hook",
                    "target": ".claude/hooks/sd-thing.py",
                }
            ]
        )

        with self.assertRaisesRegex(
            self.partition.PartitionError, "unclassified manifest kind 'hook'"
        ):
            self.partition.build_partition(root)

    def test_install_accepted_kind_still_needs_a_category(self) -> None:
        manifest = importlib.import_module("installer.manifest")
        unclassified = set(manifest.KNOWN_MANIFEST_KINDS) - self.partition.KNOWN_KINDS

        # `agent` is registered for install but ships zero rows; the partition
        # gate must still demand a deliberate category before one lands.
        self.assertEqual(unclassified, {"agent"})
        root = self.build_root(
            [
                {
                    "platform": "claude",
                    "kind": "agent",
                    "target": ".claude/agents/sd-thing.md",
                }
            ]
        )

        with self.assertRaisesRegex(
            self.partition.PartitionError, "unclassified manifest kind 'agent'"
        ):
            self.partition.build_partition(root)

    def test_registry_platform_without_a_disposition_fails(self) -> None:
        root = self.build_root([])
        dispositions = dict(self.partition.PLATFORM_DISPOSITIONS)
        del dispositions["gemini"]

        with mock.patch.object(self.partition, "PLATFORM_DISPOSITIONS", dispositions):
            with self.assertRaisesRegex(
                self.partition.PartitionError,
                "platform without a scope disposition: gemini",
            ):
                self.partition.build_partition(root)

    def test_stale_disposition_entry_fails(self) -> None:
        root = self.build_root([])
        dispositions = dict(self.partition.PLATFORM_DISPOSITIONS)
        dispositions["retired-platform"] = ("repo-native", False)

        with mock.patch.object(self.partition, "PLATFORM_DISPOSITIONS", dispositions):
            with self.assertRaisesRegex(
                self.partition.PartitionError,
                "stale disposition entry .*retired-platform",
            ):
                self.partition.build_partition(root)

    def test_unknown_scope_value_fails(self) -> None:
        root = self.build_root([])
        dispositions = dict(self.partition.PLATFORM_DISPOSITIONS)
        dispositions["claude"] = ("plugin", False)

        with mock.patch.object(self.partition, "PLATFORM_DISPOSITIONS", dispositions):
            with self.assertRaisesRegex(
                self.partition.PartitionError, "unknown scope disposition 'plugin'"
            ):
                self.partition.build_partition(root)

    def test_retention_for_unknown_platform_fails(self) -> None:
        root = self.build_root([])
        retentions = {"shared": ("codex", "nonesuch")}

        with mock.patch.object(
            self.partition, "PLATFORM_RETAIN_VENDORED_FOR", retentions
        ):
            with self.assertRaisesRegex(
                self.partition.PartitionError,
                "retains rows for unknown platform.*nonesuch",
            ):
                self.partition.build_partition(root)

    def test_retention_on_an_unregistered_carrier_fails(self) -> None:
        root = self.build_root([])
        retentions = {"nonesuch": ("codex",)}

        with mock.patch.object(
            self.partition, "PLATFORM_RETAIN_VENDORED_FOR", retentions
        ):
            with self.assertRaisesRegex(
                self.partition.PartitionError,
                "retainVendoredFor names platform 'nonesuch'",
            ):
                self.partition.build_partition(root)

    def test_retention_on_a_repo_native_carrier_fails(self) -> None:
        root = self.build_root([])
        retentions = {"github": ("codex",)}

        with mock.patch.object(
            self.partition, "PLATFORM_RETAIN_VENDORED_FOR", retentions
        ):
            with self.assertRaisesRegex(
                self.partition.PartitionError,
                "already stay.*vendored",
            ):
                self.partition.build_partition(root)

    def test_empty_or_duplicated_retention_list_fails(self) -> None:
        root = self.build_root([])

        with mock.patch.object(
            self.partition, "PLATFORM_RETAIN_VENDORED_FOR", {"shared": ()}
        ):
            with self.assertRaisesRegex(
                self.partition.PartitionError, "empty retainVendoredFor list"
            ):
                self.partition.build_partition(root)

        with mock.patch.object(
            self.partition,
            "PLATFORM_RETAIN_VENDORED_FOR",
            {"shared": ("codex", "codex")},
        ):
            with self.assertRaisesRegex(
                self.partition.PartitionError, "repeats a platform"
            ):
                self.partition.build_partition(root)

    def test_retention_field_round_trips_and_stays_sorted(self) -> None:
        root = self.build_root([])

        with mock.patch.object(
            self.partition, "PLATFORM_RETAIN_VENDORED_FOR", {"shared": ("pi", "codex")}
        ):
            partition = self.partition.build_partition(root)

        self.assertEqual(
            partition["platforms"]["shared"]["retainVendoredFor"], ["codex", "pi"]
        )
        self.assertNotIn("retainVendoredFor", partition["platforms"]["claude"])

    def test_stale_target_override_fails(self) -> None:
        root = self.build_root([])
        overrides = self.partition.TARGET_OVERRIDES + (
            (".retired/**", "consumer-config", False),
        )

        with mock.patch.object(self.partition, "TARGET_OVERRIDES", overrides):
            with self.assertRaisesRegex(
                self.partition.PartitionError,
                r"stale target-path override .*\.retired/\*\*",
            ):
                self.partition.build_partition(root)

    def test_row_without_a_target_fails(self) -> None:
        root = self.build_root([{"platform": "claude", "kind": "skill"}])

        with self.assertRaisesRegex(
            self.partition.PartitionError, "manifest row without a target"
        ):
            self.partition.build_partition(root)

    def test_missing_manifest_files_list_fails(self) -> None:
        root = self.build_root([])
        (root / "manifest.json").write_text(
            json.dumps({"version": "9.9.9"}) + "\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(self.partition.PartitionError, "no `files` list"):
            self.partition.build_partition(root)

    def test_malformed_manifest_json_fails_controlled(self) -> None:
        root = self.build_root([])
        (root / "manifest.json").write_text("{not json", encoding="utf-8")

        with self.assertRaisesRegex(
            self.partition.PartitionError, "manifest is not valid JSON"
        ):
            self.partition.build_partition(root)

    def test_non_object_manifest_fails(self) -> None:
        root = self.build_root([])
        (root / "manifest.json").write_text("[]\n", encoding="utf-8")

        with self.assertRaisesRegex(
            self.partition.PartitionError, "manifest is not a JSON object"
        ):
            self.partition.build_partition(root)

    def test_non_object_manifest_row_fails(self) -> None:
        root = self.build_root([])
        (root / "manifest.json").write_text(
            json.dumps({"version": "9.9.9", "files": [*BASELINE_ROWS, "scripts/x.sh"]}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            self.partition.PartitionError, "non-object entry"
        ):
            self.partition.build_partition(root)

    def test_non_list_files_field_fails(self) -> None:
        root = self.build_root([])
        (root / "manifest.json").write_text(
            json.dumps({"version": "9.9.9", "files": {}}), encoding="utf-8"
        )

        with self.assertRaisesRegex(self.partition.PartitionError, "no `files` list"):
            self.partition.build_partition(root)

    def test_missing_manifest_fails(self) -> None:
        root = self.build_root([])
        (root / "manifest.json").unlink()

        with self.assertRaisesRegex(
            self.partition.PartitionError, "manifest not found"
        ):
            self.partition.build_partition(root)

    # --- write / check round trip -----------------------------------------

    def test_write_then_check_is_idempotent(self) -> None:
        root = self.build_root([])
        artifact = root / self.partition.PARTITION_PATH

        self.assertEqual(self.partition.main(["--root", str(root)]), 0)
        first = artifact.read_bytes()
        self.assertEqual(self.partition.main(["--root", str(root)]), 0)

        self.assertEqual(artifact.read_bytes(), first)
        self.assertEqual(self.partition.main(["--check", "--root", str(root)]), 0)

    def test_check_mode_reports_drift(self) -> None:
        root = self.build_root([])
        artifact = root / self.partition.PARTITION_PATH

        self.assertEqual(self.partition.main(["--root", str(root)]), 0)
        stale = json.loads(artifact.read_text(encoding="utf-8"))
        stale["counts"]["repo-native"] = 999
        artifact.write_text(json.dumps(stale, indent=2) + "\n", encoding="utf-8")

        self.assertEqual(self.partition.main(["--check", "--root", str(root)]), 1)

    def test_check_mode_reports_a_missing_artifact(self) -> None:
        root = self.build_root([])

        self.assertEqual(self.partition.main(["--check", "--root", str(root)]), 1)

    def test_cli_reports_errors_without_raising(self) -> None:
        root = self.build_root(
            [
                {
                    "platform": "nonesuch",
                    "kind": "skill",
                    "target": ".nonesuch/skills/sd-thing/SKILL.md",
                }
            ]
        )

        self.assertEqual(self.partition.main(["--root", str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
