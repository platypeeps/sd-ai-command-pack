from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

install = _support.install
InstallTestCase = _support.InstallTestCase

GUIDE_TEMPLATE = install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md"
README = install.ROOT / "README.md"

SKILL_SECTIONS = (
    "## When to use",
    "## Arguments",
    "## Workflow",
    "## Safety rules",
    "## Final report",
)

# name -> (short form, skill pins, adapter pins)
COMMANDS = {
    "sd-watch-pr": (
        "watch-pr",
        [
            "timeout-minutes=",
            "no-merge",
            "never merges directly",
            "sd-housekeeping",
        ],
        ["sd-housekeeping"],
    ),
    "sd-fix-ci": (
        "fix-ci",
        [
            "real-code",
            "flake",
            "infra",
            "stale-baseline",
            "max-reruns=",
            "weaken tests",
        ],
        ["weaken tests"],
    ),
    "sd-update-deps": (
        "update-deps",
        [
            "include-runtime-minor",
            "dry-run",
            "majors are always manual",
            "sequential",
        ],
        ["Majors are always manual"],
    ),
    "sd-fleet-refresh": (
        "fleet-refresh",
        [
            "consumer=",
            "no-merge",
            "dry-run",
            "one consumer at a time",
            "FLEET_ROLLOUT.md",
            "fleet-preflight",
        ],
        ["one consumer at a time"],
    ),
    "sd-test-gaps": (
        "test-gaps",
        [
            "file=",
            "max-gaps=",
            "test files and fixtures only",
            "baseline",
        ],
        ["test files and fixtures only"],
    ),
    "sd-retro": (
        "retro",
        [
            "Retro: <topic>",
            "never auto-create",
            "sd-ai-command-pack-record-session.py",
            "explicit user consent",
        ],
        ["explicit user consent"],
    ),
}


class SdlcCommandsTests(InstallTestCase):
    """Format-drift protection for the six SDLC edge-loop command skills."""

    def _skill_text(self, name: str) -> str:
        path = install.ROOT / f"templates/.agents/skills/{name}/SKILL.md"
        return path.read_text(encoding="utf-8")

    def test_skill_sections_frontmatter_and_pins(self) -> None:
        for name, (_short, pins, _adapter_pins) in COMMANDS.items():
            with self.subTest(skill=name):
                skill = self._skill_text(name)
                self.assertIn(f"name: {name}", skill)
                self.assertIn("description: Use when", skill)
                last = -1
                for section in SKILL_SECTIONS:
                    pos = skill.find(section)
                    self.assertGreater(pos, last, f"{name}: {section} order")
                    last = pos
                for pin in pins:
                    self.assertIn(pin, skill, f"{name}: missing pin {pin!r}")

    def test_skills_declare_no_environment_variables(self) -> None:
        for name in COMMANDS:
            with self.subTest(skill=name):
                skill = self._skill_text(name)
                self.assertNotIn("SD_AI_COMMAND_PACK_", skill)

    def test_skills_state_unknown_argument_rule_and_scannable_report(self) -> None:
        for name in COMMANDS:
            with self.subTest(skill=name):
                skill = self._skill_text(name)
                self.assertIn("error", skill.split("## Arguments")[1].split("##")[0].lower())
                report = skill.split("## Final report")[1]
                self.assertIn("explicitly", report)

    def test_command_adapters_share_contract(self) -> None:
        for name, (short, _pins, adapter_pins) in COMMANDS.items():
            adapters = [
                install.ROOT / f"templates/.commands/{name}.md",
                install.ROOT / f"templates/.claude/commands/sd/{short}.md",
                install.ROOT / f"templates/.gemini/commands/sd/{short}.toml",
                install.ROOT / f"templates/.github/prompts/{name}.prompt.md",
            ]
            for adapter in adapters:
                with self.subTest(adapter=adapter.name):
                    content = adapter.read_text(encoding="utf-8")
                    self.assertIn(
                        f"Resolve the `{name}` skill by name", content
                    )
                    for pin in adapter_pins:
                        self.assertIn(pin, content)
                    self.assertIn("final-report format", content)

    def test_usage_guide_documents_all_six(self) -> None:
        guide = GUIDE_TEMPLATE.read_text(encoding="utf-8")
        for name, (short, _pins, _apins) in COMMANDS.items():
            with self.subTest(command=name):
                self.assertIn(f"`.agents/skills/{name}/SKILL.md`", guide)
                self.assertIn(f"/sd:{short}", guide)
                self.assertIn(f"/sd-{short}", guide)
                self.assertIn(f"The `{name}` command", guide)
        for pin in [
            "whose gate remains the only merge authority",
            "never deletes, skips, or weakens tests",
            "Majors are\nalways manual",
            "one consumer at a time",
            "test files and fixtures only",
            "auto-creates tasks and makes no code changes",
        ]:
            self.assertIn(pin, guide)

    def test_readme_documents_all_six(self) -> None:
        readme = README.read_text(encoding="utf-8")
        for name in COMMANDS:
            with self.subTest(command=name):
                self.assertIn(f"### {name}", readme)


if __name__ == "__main__":
    _support.unittest.main()
