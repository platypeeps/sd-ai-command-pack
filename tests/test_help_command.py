from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

from installer import registry

contextlib = _support.contextlib
importlib = _support.importlib
io = _support.io
json = _support.json
mock = _support.mock
re = _support.re
tempfile = _support.tempfile
unittest = _support.unittest
Path = _support.Path
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

GENERATOR_SCRIPT = PACK_ROOT / ".github/scripts/generate-command-surfaces.py"
SKILL = PACK_ROOT / "templates/.agents/skills/sd-help/SKILL.md"
EXAMPLES = PACK_ROOT / "templates/.agents/skills/sd-help/references/examples.md"
CATALOG = (
    PACK_ROOT
    / "templates/.agents/skills/sd-help/references/command-catalog.md"
)


def load_surface_generator():
    module_name = "generate_command_surfaces_help_tests"
    module = _support.sys.modules.get(module_name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load generator module from {GENERATOR_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    _support.sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class HelpCommandTests(InstallTestCase):
    def test_command_registry_derives_compatibility_names_and_families(self) -> None:
        expected_families = (
            "orientation-knowledge",
            "planning-backlog",
            "verification-improvement",
            "pull-requests-shipping",
            "maintenance-fleet",
        )

        self.assertEqual(
            tuple(family.id for family in registry.COMMAND_FAMILIES),
            expected_families,
        )
        self.assertEqual(
            registry.COMMAND_NAMES,
            tuple(
                (command.name, command.short)
                for command in registry.COMMAND_REGISTRY
            ),
        )
        self.assertEqual(
            {command.name for command in registry.COMMAND_REGISTRY},
            {path.stem for path in (PACK_ROOT / "templates/.commands").glob("sd-*.md")},
        )
        self.assertEqual(
            {command.family for command in registry.COMMAND_REGISTRY},
            set(expected_families),
        )
        self.assertEqual(
            sum(command.name == "sd-help" for command in registry.COMMAND_REGISTRY),
            1,
        )

    def test_command_registry_validation_rejects_invalid_shapes(self) -> None:
        families = (registry.CommandFamily("one", "One", "One family."),)
        cases = (
            (
                (
                    registry.CommandInfo("sd-one", "one", "one"),
                    registry.CommandInfo("sd-one", "one", "one"),
                ),
                "duplicate command name",
            ),
            ((registry.CommandInfo("one", "one", "one"),), "must start with sd-"),
            (
                (registry.CommandInfo("sd-one", "different", "one"),),
                "short form must match name",
            ),
            (
                (registry.CommandInfo("sd-one", "one", "missing"),),
                "uses unknown family",
            ),
        )
        for commands, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                RuntimeError, message
            ):
                registry.validate_command_registry(commands, families)

        family_cases = (
            (
                (
                    registry.CommandFamily("one", "One", "One family."),
                    registry.CommandFamily("one", "Another", "Another family."),
                ),
                "duplicate family id",
            ),
            ((registry.CommandFamily("", "One", "One family."),), "non-empty"),
        )
        for invalid_families, message in family_cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                RuntimeError, message
            ):
                registry.validate_command_registry((), invalid_families)

        with self.assertRaisesRegex(RuntimeError, "command fields must be non-empty"):
            registry.validate_command_registry(
                (registry.CommandInfo("", "", ""),),
                families,
            )

    def test_command_capabilities_are_conservative_and_validated(self) -> None:
        families = (registry.CommandFamily("one", "One", "One family."),)
        default = registry.CommandInfo("sd-one", "one", "one")

        self.assertTrue(default.executes_checkout_code)
        self.assertFalse(default.trusted_static_only)
        self.assertEqual(
            default.target_families, registry.GENERATED_COMMAND_TARGET_FAMILIES
        )
        self.assertEqual(
            len(registry.command_installed_targets("sd-one", "one")), 25
        )
        self.assertEqual(
            registry.command_installed_targets(
                "sd-one", "one", ("shared", "github")
            ),
            (
                ".agents/skills/sd-one/SKILL.md",
                ".github/prompts/sd-one.prompt.md",
            ),
        )
        self.assertEqual(
            [command.name for command in registry.COMMAND_REGISTRY if command.trusted_static_only],
            ["sd-help"],
        )

        invalid = (
            (
                registry.CommandInfo(
                    "sd-one",
                    "one",
                    "one",
                    executes_checkout_code="yes",  # type: ignore[arg-type]
                ),
                "capability flags must be boolean",
            ),
            (
                registry.CommandInfo(
                    "sd-one",
                    "one",
                    "one",
                    trusted_static_only=True,
                ),
                "trusted_static_only conflicts",
            ),
            (
                registry.CommandInfo(
                    "sd-one",
                    "one",
                    "one",
                    executes_checkout_code=False,
                ),
                "must execute checkout code or be trusted_static_only",
            ),
            (
                registry.CommandInfo("sd-one", "one", "one", safe_mode="../unsafe"),
                "unsafe safe_mode",
            ),
            (
                registry.CommandInfo("sd-one", "one", "one", target_families=()),
                "no generated target families",
            ),
            (
                registry.CommandInfo(
                    "sd-one", "one", "one", target_families=("missing",)
                ),
                "unknown target families",
            ),
            (
                registry.CommandInfo(
                    "sd-one",
                    "one",
                    "one",
                    target_families=("shared", "shared"),
                ),
                "duplicate target families",
            ),
            (
                registry.CommandInfo(
                    "sd-one",
                    "one",
                    "one",
                    target_families=("shared", 1),  # type: ignore[arg-type]
                ),
                "invalid target families",
            ),
            (
                registry.CommandInfo(
                    "sd-one",
                    "one",
                    "one",
                    target_families=["shared"],  # type: ignore[arg-type]
                ),
                "invalid target families",
            ),
            (
                registry.CommandInfo(
                    "sd-one", "one", "one", configuration_keys=("",)
                ),
                "invalid configuration keys",
            ),
            (
                registry.CommandInfo(
                    "sd-one",
                    "one",
                    "one",
                    configuration_keys=("SD_ONE", "SD_ONE"),
                ),
                "duplicate configuration keys",
            ),
        )
        for command, message in invalid:
            with self.subTest(message=message), self.assertRaisesRegex(
                RuntimeError, message
            ):
                registry.validate_command_registry((command,), families)

    def test_retired_command_surface_schema_is_validated(self) -> None:
        command = registry.CommandInfo(
            "sd-one", "one", "orientation-knowledge"
        )
        retirement = registry.RetiredCommandSurface(
            id="old-one",
            identifiers=("sd-old",),
            installed_targets=(".agents/skills/sd-old/SKILL.md",),
            removed_version="1.0.0",
            owner_task="fixture",
        )
        allowance = registry.CommandSurfaceAllowance(
            identifier="sd-old",
            path_pattern="CHANGELOG.md",
            reason="migration history",
        )

        registry.validate_command_surface_registry(
            (command,), (retirement,), (allowance,)
        )
        with self.assertRaisesRegex(RuntimeError, "identifiers are still live"):
            registry.validate_command_surface_registry(
                (command,),
                (
                    registry.RetiredCommandSurface(
                        id="bad",
                        identifiers=("sd-one",),
                        installed_targets=(),
                        removed_version="1.0.0",
                        owner_task="fixture",
                    ),
                ),
                (),
            )
        with self.assertRaisesRegex(RuntimeError, "unsafe command surface allowance"):
            registry.validate_command_surface_registry(
                (command,),
                (retirement,),
                (
                    registry.CommandSurfaceAllowance(
                        identifier="sd-old",
                        path_pattern="**/*",
                        reason="too broad",
                    ),
                ),
            )

    def test_retired_command_surface_schema_rejects_invalid_shapes(self) -> None:
        command = registry.CommandInfo(
            "sd-one",
            "one",
            "orientation-knowledge",
            configuration_keys=("SD_ONE",),
        )

        def retirement(
            *,
            id: str = "old-one",
            identifiers: tuple[str, ...] = ("sd-old",),
            installed_targets: tuple[str, ...] = (),
            removed_version: str = "1.0.0",
            owner_task: str = "fixture",
            source_paths_must_be_absent: bool = True,
            configuration_keys: tuple[str, ...] = (),
        ) -> registry.RetiredCommandSurface:
            return registry.RetiredCommandSurface(
                id=id,
                identifiers=identifiers,
                installed_targets=installed_targets,
                removed_version=removed_version,
                owner_task=owner_task,
                source_paths_must_be_absent=source_paths_must_be_absent,
                configuration_keys=configuration_keys,
            )

        invalid_retirements = (
            ((retirement(), retirement()), "duplicate retirement id"),
            ((retirement(id=""),), "fields must be non-empty"),
            (
                (
                    retirement(
                        source_paths_must_be_absent="yes",  # type: ignore[arg-type]
                    ),
                ),
                "source-path policy must be boolean",
            ),
            (
                (
                    retirement(
                        identifiers=(),
                        installed_targets=(),
                        configuration_keys=(),
                    ),
                ),
                "describes no surface",
            ),
            (
                (retirement(identifiers=("sd-old", "sd-old")),),
                "invalid identifiers",
            ),
            (
                (
                    retirement(
                        identifiers=("sd-old", 1),  # type: ignore[arg-type]
                    ),
                ),
                "invalid identifiers",
            ),
            (
                (
                    retirement(
                        installed_targets=(1,),  # type: ignore[arg-type]
                    ),
                ),
                "invalid installed targets",
            ),
            (
                (
                    retirement(
                        configuration_keys=(1,),  # type: ignore[arg-type]
                    ),
                ),
                "invalid configuration keys",
            ),
            (
                (retirement(installed_targets=("../outside",)),),
                "unsafe installed target",
            ),
            (
                (retirement(identifiers=(), configuration_keys=("SD_ONE",)),),
                "configuration keys are still live",
            ),
            (
                (
                    retirement(id="old-one"),
                    retirement(id="old-two"),
                ),
                "retired identifiers have multiple owners",
            ),
            (
                (
                    retirement(
                        id="old-one",
                        identifiers=(),
                        configuration_keys=("SD_OLD",),
                    ),
                    retirement(
                        id="old-two",
                        identifiers=(),
                        configuration_keys=("SD_OLD",),
                    ),
                ),
                "retired configuration keys have multiple owners",
            ),
        )
        for retirements, message in invalid_retirements:
            with self.subTest(message=message), self.assertRaisesRegex(
                RuntimeError, message
            ):
                registry.validate_command_surface_registry(
                    (command,), retirements, ()
                )

        valid_retirement = retirement()
        invalid_allowances = (
            (
                (
                    registry.CommandSurfaceAllowance(
                        "sd-unknown", "README.md", "history"
                    ),
                ),
                "not retired",
            ),
            (
                (
                    registry.CommandSurfaceAllowance(
                        "sd-old", "README.md", "history"
                    ),
                    registry.CommandSurfaceAllowance(
                        "sd-old", "README.md", "history"
                    ),
                ),
                "duplicate command surface allowance",
            ),
            (
                (
                    registry.CommandSurfaceAllowance(
                        "sd-old", "README.md", ""
                    ),
                ),
                "allowance has no reason",
            ),
            (
                (
                    registry.CommandSurfaceAllowance(
                        1, 2, 3  # type: ignore[arg-type]
                    ),
                ),
                "invalid identifier",
            ),
        )
        for allowances, message in invalid_allowances:
            with self.subTest(message=message), self.assertRaisesRegex(
                RuntimeError, message
            ):
                registry.validate_command_surface_registry(
                    (command,), (valid_retirement,), allowances
                )

    def test_command_target_footprint_rejects_platform_without_pattern(self) -> None:
        invalid_cursor = registry.PlatformInfo(
            directory=".cursor",
            command_kind="command",
            command_target_pattern=None,
        )
        with mock.patch.dict(
            registry.PLATFORM_REGISTRY, {"cursor": invalid_cursor}
        ), self.assertRaisesRegex(RuntimeError, "no command target pattern"):
            registry.command_installed_targets("sd-one", "one")

    def test_retired_surface_lookup_reports_missing_id(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError, "unknown retired command surface id: missing"
        ):
            registry.retired_surface_targets("missing")

    def test_shared_skill_reference_validation_rejects_unknown_and_unsafe(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unknown skill"):
            registry.validate_shared_skill_references(
                (("sd-known", "known"),),
                {"sd-missing": ("references/example.md",)},
            )
        with self.assertRaisesRegex(RuntimeError, "unsafe reference path"):
            registry.validate_shared_skill_references(
                (("sd-known", "known"),),
                {"sd-known": ("../outside.md",)},
            )
        with self.assertRaisesRegex(RuntimeError, "duplicate reference paths"):
            registry.validate_shared_skill_references(
                (("sd-known", "known"),),
                {
                    "sd-known": (
                        "references/example.md",
                        "references/example.md",
                    )
                },
            )

    def test_generated_catalog_uses_registry_frontmatter_and_release_policy(self) -> None:
        generator = load_surface_generator()
        catalog = generator.generate_command_catalog()
        manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))

        self.assertTrue(catalog.startswith("<!-- Generated by"))
        self.assertIn(f"Bundled pack version: `{manifest['version']}`", catalog)
        family_positions = [
            catalog.index(f"## {family.label}")
            for family in registry.COMMAND_FAMILIES
        ]
        self.assertEqual(family_positions, sorted(family_positions))
        for command in registry.COMMAND_REGISTRY:
            with self.subTest(command=command.name):
                self.assertEqual(catalog.count(f"| `{command.name}` |"), 1)
                self.assertIn(generator.skill_description(command.name), catalog)
        self.assertIn("| `sd-fleet-refresh` | source-checkout-only |", catalog)
        self.assertIn("| `sd-help` | included in installed pack |", catalog)

    def test_manifest_derivation_honors_declared_target_families(self) -> None:
        generator = load_surface_generator()

        self.assertEqual(
            generator.derived_manifest_entries(
                "sd-one", "one", ("shared", "github")
            ),
            [
                {
                    "platform": "shared",
                    "kind": "skill",
                    "source": "templates/.agents/skills/sd-one/SKILL.md",
                    "target": ".agents/skills/sd-one/SKILL.md",
                    "install": "always",
                },
                {
                    "platform": "github",
                    "kind": "prompt",
                    "source": "templates/.github/prompts/sd-one.prompt.md",
                    "target": ".github/prompts/sd-one.prompt.md",
                    "anchor": ".github",
                },
            ],
        )

    def test_catalog_generation_is_read_only_and_escapes_markdown(self) -> None:
        generator = load_surface_generator()
        with tempfile.TemporaryDirectory(prefix="sd-help-catalog-") as temp_name:
            root = Path(temp_name)
            (root / "manifest.json").write_text(
                json.dumps({"version": "9.9.9", "files": []}),
                encoding="utf-8",
            )
            for command in registry.COMMAND_REGISTRY:
                source = root / f"templates/.agents/skills/{command.name}/SKILL.md"
                source.parent.mkdir(parents=True, exist_ok=True)
                description = (
                    "Use left | right." if command.name == "sd-help" else "Use safely."
                )
                source.write_text(
                    f"---\nname: {command.name}\ndescription: {description}\n---\n",
                    encoding="utf-8",
                )

            with mock.patch.object(generator, "PACK_ROOT", root):
                catalog = generator.generate_command_catalog()

            self.assertIn("Bundled pack version: `9.9.9`", catalog)
            self.assertIn("Use left \\| right.", catalog)
            self.assertFalse((root / generator.HELP_CATALOG_PATH).exists())

    def test_generation_failure_never_calls_writer(self) -> None:
        generator = load_surface_generator()
        stderr = io.StringIO()
        with (
            mock.patch.object(
                generator,
                "generate_surfaces",
                side_effect=generator.GenerationError("invalid catalog"),
            ),
            mock.patch.object(generator, "write_surfaces") as writer,
            contextlib.redirect_stderr(stderr),
        ):
            result = generator.main([])

        self.assertEqual(result, 1)
        self.assertIn("invalid catalog", stderr.getvalue())
        writer.assert_not_called()

    def test_manifest_fans_help_references_to_every_skill_root(self) -> None:
        generator = load_surface_generator()
        manifest = json.loads(generator.generate_manifest_text())
        entries = [
            entry
            for entry in manifest["files"]
            if entry["source"].startswith(
                "templates/.agents/skills/sd-help/references/"
            )
        ]
        expected_targets = set()
        for reference in registry.SHARED_SKILL_REFERENCES["sd-help"]:
            expected_targets.add(f".agents/skills/sd-help/{reference}")
            expected_targets.update(
                f"{registry.PLATFORM_REGISTRY[platform].directory}/skills/"
                f"sd-help/{reference}"
                for platform in generator.SKILL_FANOUT_PLATFORMS
            )

        self.assertEqual({entry["target"] for entry in entries}, expected_targets)
        self.assertEqual(len(entries), len(expected_targets))

    def test_nested_skill_reference_sources_remain_generator_owned(self) -> None:
        generator = load_surface_generator()

        self.assertEqual(
            generator._candidate_command_pairs(
                {
                    "source": (
                        "templates/.agents/skills/sd-help/references/guides/"
                        "advanced.md"
                    )
                }
            ),
            {("sd-help", "help")},
        )

    def test_manifest_generation_rejects_a_missing_authored_reference(self) -> None:
        generator = load_surface_generator()
        with (
            mock.patch.dict(
                generator.SHARED_SKILL_REFERENCES,
                {"sd-help": ("references/missing.md",)},
                clear=True,
            ),
            self.assertRaisesRegex(
                generator.GenerationError,
                "missing shared skill reference",
            ),
        ):
            generator._skill_reference_entries("sd-help")

    def test_help_skill_pins_modes_discovery_shape_and_read_only_boundary(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        normalized = " ".join(skill.split())

        for section in (
            "## When to use",
            "## Arguments",
            "## Discovery",
            "## Workflow",
            "## Response shape",
            "## Safety rules",
            "## Final response",
        ):
            self.assertIn(section, skill)
        self.assertIn("mode=list|explain|compare|recommend|examples|tour", skill)
        self.assertIn("detail=compact|standard", skill)
        for label in (
            "available now",
            "included in this installed pack but not discoverable",
            "source-checkout-only",
            "unknown/external",
        ):
            self.assertIn(label, skill)
        for field in (
            "required context and prerequisites",
            "expected output or handoff artifact",
            "meaningful side effects, mutation boundary",
            "related commands, closest alternatives",
            "copy-ready platform-native invocation",
        ):
            self.assertIn(field, normalized)
        self.assertIn("at most three commands", normalized)
        self.assertIn("at most one question", normalized)
        self.assertIn("If no `sd-*` skills are discoverable", skill)
        self.assertIn("unknown or ambiguous command/query", skill)
        self.assertIn("limit the result to that family", normalized)
        self.assertIn("small ranked set", normalized)
        self.assertIn("Do not invent a command", normalized)
        self.assertIn("strictly read-only", normalized)
        self.assertIn("separate explicit user request", normalized)
        self.assertIn(".sd-ai-command-pack/manifest.json", skill)
        self.assertNotIn("SD_AI_COMMAND_PACK_", skill)

    def test_authored_examples_name_only_registry_commands(self) -> None:
        examples = EXAMPLES.read_text(encoding="utf-8")
        named = set(re.findall(r"\bsd-[a-z0-9-]+\b", examples))
        known = {command.name for command in registry.COMMAND_REGISTRY}

        self.assertGreater(len(named), 0)
        self.assertEqual(named - known, set())
        for family in registry.COMMAND_FAMILIES:
            self.assertIn(f"## {family.label}", examples)

    def test_generated_adapters_and_catalog_are_committed(self) -> None:
        generator = load_surface_generator()
        outputs = generator.generate_surfaces()

        self.assertIn(generator.HELP_CATALOG_PATH, outputs)
        self.assertEqual(CATALOG.read_text(encoding="utf-8"), outputs[generator.HELP_CATALOG_PATH])
        for relative in (
            "templates/.claude/commands/sd/help.md",
            "templates/.gemini/commands/sd/help.toml",
            "templates/.github/prompts/sd-help.prompt.md",
        ):
            self.assertIn(relative, outputs)
            self.assertEqual(
                (PACK_ROOT / relative).read_text(encoding="utf-8"),
                outputs[relative],
            )

    def test_user_docs_explain_help_modes_examples_and_read_only_boundary(self) -> None:
        readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")
        guide = (
            PACK_ROOT / "templates/docs/SD_AI_COMMAND_PACK.md"
        ).read_text(encoding="utf-8")

        for content in (readme, guide):
            self.assertIn("/sd:help", content)
            self.assertIn("sd-create-pr and sd-ship", content)
            self.assertIn("fix failing CI", content)
            self.assertIn("separate explicit request", content)
        for mode in (
            "list",
            "explain",
            "compare",
            "recommend",
            "examples",
            "tour",
        ):
            self.assertIn(mode, readme)
        self.assertIn("source-checkout-only", guide)
        self.assertIn("bundled-but-undiscoverable", guide)


if __name__ == "__main__":
    unittest.main()
