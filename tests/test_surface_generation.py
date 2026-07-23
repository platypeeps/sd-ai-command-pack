from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
