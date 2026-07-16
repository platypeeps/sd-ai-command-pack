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
        neutral_stems = {
            source.stem
            for source in (install.ROOT / "templates/.commands").glob("sd-*.md")
        }

        self.assertEqual(listed_names, neutral_stems)
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


if __name__ == "__main__":
    unittest.main()
