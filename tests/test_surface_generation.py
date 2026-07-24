from __future__ import annotations

from dataclasses import replace

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

importlib = _support.importlib
subprocess = _support.subprocess
sys = _support.sys
unittest = _support.unittest
Path = _support.Path
install = _support.install
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase
registry = importlib.import_module("installer.registry")

GENERATOR_SCRIPT = PACK_ROOT / ".github/scripts/generate-command-surfaces.py"


def load_surface_generator():
    module = sys.modules.get("generate_command_surfaces")
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(
        "generate_command_surfaces", GENERATOR_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load generator module from {GENERATOR_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_command_surfaces"] = module
    spec.loader.exec_module(module)
    return module


class SurfaceGenerationTests(InstallTestCase):
    """Drift gate: committed command surfaces must match regeneration."""

    def test_generator_check_mode_is_clean_on_committed_tree(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR_SCRIPT), "--check"],
            cwd=PACK_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            "generated command surfaces drift from the committed tree; run "
            f"`make generate`:\n{result.stdout}{result.stderr}",
        )
        self.assertIn(
            "override (hand-authored): templates/.claude/commands/sd/start.md",
            result.stdout,
        )

    def test_command_names_match_neutral_body_sources(self) -> None:
        generator = load_surface_generator()
        listed_names = {name for name, _ in generator.COMMAND_NAMES}
        authored_stems = {
            source.stem
            for source in (install.ROOT / ".github/command-sources").glob("sd-*.md")
        }
        generated_stems = {
            source.stem
            for source in (install.ROOT / "templates/.commands").glob("sd-*.md")
        }

        self.assertEqual(listed_names, authored_stems)
        self.assertEqual(listed_names, generated_stems)
        self.assertEqual(
            len(generator.COMMAND_NAMES),
            len({short for _, short in generator.COMMAND_NAMES}),
            "COMMAND_NAMES short forms must be unique",
        )

    def test_every_bespoke_adapter_is_generated_or_an_override(self) -> None:
        generator = load_surface_generator()
        generated = set(generator.generate_adapters())
        overrides = set(generator.override_adapter_paths())

        self.assertEqual(generated & overrides, set())
        on_disk = {
            path.relative_to(install.ROOT).as_posix()
            for pattern in (
                "templates/.claude/commands/sd/*.md",
                "templates/.gemini/commands/sd/*.toml",
                "templates/.github/prompts/*.prompt.md",
            )
            for path in install.ROOT.glob(pattern)
        }

        self.assertEqual(on_disk, generated | overrides)

    def test_claude_review_local_adds_native_codex_fanout_only(self) -> None:
        generator = load_surface_generator()
        generated = generator.generate_adapters()
        neutral = generator.generate_neutral_adapters()
        claude_path = "templates/.claude/commands/sd/review-local.md"
        claude = generated[claude_path]

        for expected in (
            "Claude Code native Codex lane",
            "command -v codex",
            "codex review --uncommitted",
            "codex review --base <resolved-ref>",
            "background Bash tasks before waiting",
            "`BashOutput`",
            "Codex: skipped (CLI unavailable or",
            "runner result remains",
            "native Codex review has no equivalent scope",
        ):
            self.assertIn(expected, claude)
        for forbidden in (
            "codex-companion.mjs",
            "CLAUDE_PLUGIN_ROOT",
            "codex@openai-codex",
        ):
            self.assertNotIn(forbidden, claude)

        self.assertNotIn(
            "Claude Code native Codex lane",
            neutral["templates/.commands/sd-review-local.md"],
        )
        for path in (
            "templates/.gemini/commands/sd/review-local.toml",
            "templates/.github/prompts/sd-review-local.prompt.md",
        ):
            self.assertNotIn("Claude Code native Codex lane", generated[path])
            self.assertNotIn("codex review --uncommitted", generated[path])

    def test_claude_body_insertion_requires_unique_anchor(self) -> None:
        generator = load_surface_generator()
        with self.assertRaisesRegex(
            generator.GenerationError,
            "unique Claude body-insertion anchor",
        ):
            generator.claude_adapter(
                "sd-review-local",
                "review-local",
                "# SD Local Review\n\n1. Resolve the skill.\n",
            )

    def test_checkout_trust_policy_covers_every_command_adapter(self) -> None:
        generator = load_surface_generator()
        preflight = generator.CHECKOUT_TRUST_POLICY_MARKER
        exemption = generator.CHECKOUT_TRUST_EXEMPTION_MARKER
        generated_neutral = generator.generate_neutral_adapters()
        trusted_static = {
            command.name
            for command in generator.COMMAND_REGISTRY
            if command.trusted_static_only
        }

        self.assertEqual(trusted_static, {"sd-help"})
        for command in generator.COMMAND_REGISTRY:
            source = install.ROOT / f".github/command-sources/{command.name}.md"
            authored = source.read_text(encoding="utf-8")
            neutral_path = f"templates/.commands/{command.name}.md"
            neutral = generated_neutral[neutral_path]
            expected = exemption if command.trusted_static_only else preflight
            unexpected = preflight if command.trusted_static_only else exemption
            with self.subTest(command=command.name):
                self.assertNotIn(preflight, authored)
                self.assertNotIn(exemption, authored)
                self.assertEqual(neutral.count(expected), 1)
                self.assertNotIn(unexpected, neutral)
                self.assertLess(neutral.index(expected), neutral.index("1. Resolve"))
                self.assertNotIn("require maintainer approval", neutral)
                self.assertIn("checkout-trust:", neutral)
                if command.executes_checkout_code:
                    for reason in (
                        "trusted_local_branch",
                        "trusted_same_repo_pr",
                        "untrusted_fork_pr",
                        "indeterminate_detached_head",
                        "indeterminate_origin_unreadable",
                        "indeterminate_pr_identity_unavailable",
                        "indeterminate_conflicting_metadata",
                    ):
                        self.assertIn(reason, neutral)
                    for checkout_content in (
                        "repository scripts",
                        "hooks",
                        "package commands",
                        "provider adapters",
                        "command-bearing configs",
                        "changed skill instructions",
                    ):
                        self.assertIn(checkout_content, neutral)
                    self.assertIn(
                        "Continue to step 1 only from a `trusted` state", neutral
                    )

                short = command.short
                adapter_paths = (
                    install.ROOT / f"templates/.claude/commands/sd/{short}.md",
                    install.ROOT / f"templates/.gemini/commands/sd/{short}.toml",
                    install.ROOT
                    / f"templates/.github/prompts/{command.name}.prompt.md",
                )
                for path in adapter_paths:
                    content = path.read_text(encoding="utf-8")
                    self.assertEqual(content.count(expected), 1, path)
                    self.assertNotIn(unexpected, content, path)
                    self.assertIn("checkout-trust:", content, path)
                    self.assertLess(content.index(expected), content.index("\n1."), path)

    def test_checkout_trust_generation_fails_closed(self) -> None:
        generator = load_surface_generator()
        command = next(
            command
            for command in generator.COMMAND_REGISTRY
            if command.name == "sd-status"
        )
        valid_body = "# Status\n\n1. Resolve the `sd-status` skill by name.\n"

        with self.assertRaisesRegex(generator.GenerationError, "exactly one"):
            generator.guarded_command_body(command, "# Status\n")
        with self.assertRaisesRegex(generator.GenerationError, "exactly one"):
            generator.guarded_command_body(command, valid_body + valid_body)
        with self.assertRaisesRegex(generator.GenerationError, "must not contain"):
            generator.guarded_command_body(
                command,
                generator.CHECKOUT_TRUST_PREFLIGHT + "\n" + valid_body,
            )
        with self.assertRaisesRegex(
            generator.GenerationError, "capability-appropriate"
        ):
            generator.validate_guarded_override(
                command,
                Path("templates/.claude/commands/sd/status.md"),
                "1. Resolve the `sd-status` skill by name.\n",
            )

    def test_interaction_registry_enforces_portable_question_shape(self) -> None:
        tools = {
            platform: info.structured_question_tool
            for platform, info in registry.PLATFORM_REGISTRY.items()
            if info.structured_question_tool is not None
        }
        self.assertEqual(
            tools,
            {"claude": "AskUserQuestion", "codex": "request_user_input"},
        )

        registry.validate_interaction_registry(
            registry.PLATFORM_REGISTRY,
            registry.INTERACTION_DECISIONS,
            registry.COMMAND_REGISTRY,
        )
        for decision in registry.INTERACTION_DECISIONS:
            with self.subTest(decision=decision.id):
                self.assertLessEqual(
                    len(decision.header), registry.INTERACTION_HEADER_MAX_LENGTH
                )
                self.assertTrue(decision.question.endswith("?"))
                self.assertIn(
                    decision.noninteractive,
                    registry.INTERACTION_NONINTERACTIVE_BEHAVIORS,
                )
                if decision.option_source is None:
                    self.assertGreaterEqual(
                        len(decision.options), registry.INTERACTION_MIN_OPTIONS
                    )
                    self.assertLessEqual(
                        len(decision.options), registry.INTERACTION_MAX_OPTIONS
                    )
                    self.assertTrue(decision.options[0].recommended)
                    self.assertFalse(
                        any(option.recommended for option in decision.options[1:])
                    )
                    self.assertTrue(
                        all(option.consequence for option in decision.options)
                    )
                else:
                    self.assertTrue(decision.multi_select)
                    self.assertEqual(decision.options, ())

    def test_interaction_registry_rejects_malformed_descriptors(self) -> None:
        decision = registry.INTERACTION_DECISIONS[0]
        command = registry.CommandInfo(
            "sd-one",
            "one",
            "one",
            interaction_decisions=(decision.id,),
        )
        invalid_cases = (
            (replace(decision, id="bad..id"), "invalid interaction decision id"),
            (replace(decision, category="unknown"), "unknown category"),
            (replace(decision, header="header is too long"), "header must be"),
            (replace(decision, question="Not a question"), "must end with"),
            (replace(decision, multi_select="yes"), "must be boolean"),
            (replace(decision, noninteractive="continue"), "invalid noninteractive"),
            (
                replace(decision, options=(), option_source=None),
                "exactly one option source",
            ),
            (replace(decision, options=decision.options[:1]), "must have 2-3"),
            (
                replace(
                    decision,
                    options=(
                        decision.options[0],
                        replace(decision.options[1], label=decision.options[0].label),
                    ),
                ),
                "duplicate option labels",
            ),
            (
                replace(
                    decision,
                    options=(
                        replace(decision.options[0], recommended=False),
                        *decision.options[1:],
                    ),
                ),
                "recommendation first",
            ),
            (
                replace(
                    decision,
                    options=(
                        replace(decision.options[0], consequence=""),
                        *decision.options[1:],
                    ),
                ),
                "incomplete option",
            ),
            (
                replace(
                    decision,
                    options=(),
                    option_source="runtime findings",
                    multi_select=False,
                ),
                "require multi-select",
            ),
        )
        platforms = {"shared": registry.PlatformInfo(directory=".agents")}
        families = (registry.CommandFamily("one", "One", "One family."),)
        registry.validate_command_registry((command,), families)
        for invalid, message in invalid_cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                RuntimeError, message
            ):
                registry.validate_interaction_registry(
                    platforms,
                    (invalid,),
                    (command,),
                )

    def test_interaction_registry_rejects_invalid_links_and_capabilities(self) -> None:
        decision = registry.INTERACTION_DECISIONS[0]
        command = registry.CommandInfo(
            "sd-one",
            "one",
            "one",
            interaction_decisions=(decision.id,),
        )

        invalid_cases = (
            (
                {"bad": registry.PlatformInfo(".bad", structured_question_tool="bad-tool")},
                (decision,),
                (command,),
                "invalid structured-question tool",
            ),
            (
                {"shared": registry.PlatformInfo(".agents")},
                (decision, decision),
                (command,),
                "duplicate interaction decision id",
            ),
            (
                {"shared": registry.PlatformInfo(".agents")},
                (decision,),
                (replace(command, interaction_decisions=("missing",)),),
                "unknown interaction decisions",
            ),
            (
                {"shared": registry.PlatformInfo(".agents")},
                (decision,),
                (),
                "unreferenced interaction decision",
            ),
        )
        for platforms, decisions, commands, message in invalid_cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                RuntimeError, message
            ):
                registry.validate_interaction_registry(platforms, decisions, commands)

    def test_command_registry_rejects_invalid_interaction_links(self) -> None:
        command = registry.CommandInfo("sd-one", "one", "one")
        families = (registry.CommandFamily("one", "One", "One family."),)

        for interaction_decisions, message in (
            (("",), "invalid interaction decisions"),
            (("one", "one"), "duplicate interaction decisions"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                RuntimeError, message
            ):
                registry.validate_command_registry(
                    (replace(command, interaction_decisions=interaction_decisions),),
                    families,
                )

    def test_generated_interaction_guidance_is_capability_scoped(self) -> None:
        generator = load_surface_generator()
        outputs = generator.generate_surfaces()
        mapped = {
            command.name: command
            for command in registry.COMMAND_REGISTRY
            if command.interaction_decisions
        }

        for name, command in mapped.items():
            short = command.short
            claude = outputs[f"templates/.claude/commands/sd/{short}.md"]
            generic_paths = (
                f"templates/.commands/{name}.md",
                f"templates/.gemini/commands/sd/{short}.toml",
                f"templates/.github/prompts/{name}.prompt.md",
            )
            with self.subTest(command=name, platform="claude"):
                self.assertIn(generator.INTERACTION_POLICY_MARKER, claude)
                self.assertIn("`AskUserQuestion`", claude)
                for decision_id in command.interaction_decisions:
                    self.assertIn(f"`{decision_id}`", claude)
            for path in generic_paths:
                content = outputs[path]
                with self.subTest(command=name, platform=path):
                    self.assertIn(generator.INTERACTION_POLICY_MARKER, content)
                    self.assertNotIn("AskUserQuestion", content)
                    self.assertNotIn("request_user_input", content)
                    self.assertIn("Do not invent a tool name", content)

        for command in registry.COMMAND_REGISTRY:
            if command.interaction_decisions:
                continue
            content = outputs[f"templates/.commands/{command.name}.md"]
            with self.subTest(command=command.name, platform="neutral"):
                self.assertNotIn(generator.INTERACTION_POLICY_MARKER, content)

    def test_generated_interaction_reference_and_skills_share_one_contract(self) -> None:
        generator = load_surface_generator()
        outputs = generator.generate_surfaces()
        reference = outputs[generator.STRUCTURED_QUESTION_REFERENCE_PATH]
        normalized = " ".join(reference.split())

        self.assertNotIn("AskUserQuestion", reference)
        self.assertNotIn("request_user_input", reference)
        self.assertEqual(registry.INTERACTION_MAX_QUESTIONS_PER_BATCH, 3)
        self.assertIn("no more than 3 independent", reference)
        self.assertIn("2-3 mutually exclusive options", reference)
        self.assertIn("recommended option first", reference)
        self.assertIn("noninteractive", reference)
        for command in registry.COMMAND_REGISTRY:
            if not command.interaction_decisions:
                continue
            skill = (
                PACK_ROOT / f"templates/.agents/skills/{command.name}/SKILL.md"
            ).read_text(encoding="utf-8")
            with self.subTest(command=command.name):
                reference_link = (
                    "references/structured-questions.md"
                    if command.name == "sd-help"
                    else "../sd-help/references/structured-questions.md"
                )
                self.assertIn(reference_link, skill)
                for decision_id in command.interaction_decisions:
                    self.assertIn(f"`{decision_id}`", skill)
                    self.assertIn(f"### `{decision_id}`", reference)

        for routine in (
            "deterministic checks",
            "ordinary low-risk in-scope fixes",
            "bounded retries or polls",
            "review-thread replies or",
            "normal backlog iterations",
            "housekeeping merge",
        ):
            self.assertIn(routine, normalized)

    def test_manifest_fans_interaction_reference_with_help_to_every_skill_root(
        self,
    ) -> None:
        generator = load_surface_generator()
        manifest = _support.json.loads(generator.generate_manifest_text())
        entries = [
            entry
            for entry in manifest["files"]
            if entry["source"] == generator.STRUCTURED_QUESTION_REFERENCE_PATH
        ]
        expected_targets = {
            ".agents/skills/sd-help/references/structured-questions.md"
        }
        expected_targets.update(
            f"{registry.PLATFORM_REGISTRY[platform].directory}/skills/"
            "sd-help/references/structured-questions.md"
            for platform in registry.SKILL_FANOUT_PLATFORMS
        )

        self.assertEqual({entry["target"] for entry in entries}, expected_targets)
        self.assertEqual(len(entries), len(expected_targets))


if __name__ == "__main__":
    unittest.main()
