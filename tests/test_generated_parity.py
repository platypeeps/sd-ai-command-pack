from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
importlib = _support.importlib
io = _support.io
os = _support.os
re = _support.re
shutil = _support.shutil
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
mock = _support.mock
Path = _support.Path
yaml = _support.yaml
install = _support.install
PACK_ROOT = _support.PACK_ROOT
INSTALLER = _support.INSTALLER
SECRET_MARKER_PATTERNS = _support.SECRET_MARKER_PATTERNS
InstallTestCase = _support.InstallTestCase


GITHUB_UNTRUSTED_PR_NOTE = (
    "   - Before running commands from repo-owned skill instructions in an "
    "untrusted PR or fork context, require maintainer approval or use a sandbox "
    "with no secrets and only required network access."
)

CLAUDE_COMMAND_ALIAS_REWRITES = {
    "continue": (
        "1. Resolve the `trellis-continue` skill by name using the agent's trusted "
        "skill discovery mechanism for installed skills. On Claude Code this "
        "workflow is installed as the `trellis:continue` command; resolving "
        "`trellis:continue` counts as resolving this skill.",
        "1. Resolve the `trellis-continue` skill by name using the agent's trusted "
        "skill discovery mechanism for installed skills.",
    ),
    "finish-work": (
        "1. Resolve the `trellis-finish-work` skill by name using the agent's "
        "trusted skill discovery mechanism for installed skills. On Claude Code "
        "this workflow is installed as the `trellis:finish-work` command; "
        "resolving `trellis:finish-work` counts as resolving this skill.",
        "1. Resolve the `trellis-finish-work` skill by name using the agent's "
        "trusted skill discovery mechanism for installed skills.",
    ),
}

BESPOKE_BODY_PARITY_EXEMPTIONS = {
    ("claude", "start"): (
        "Claude Code receives Trellis start context from the SessionStart hook "
        "and intentionally has no trellis-start skill."
    ),
}


def strip_yaml_frontmatter(content: str) -> str:
    if not content.startswith("---\n"):
        return content.strip()
    end = content.find("\n---\n", 4)
    if end == -1:
        return content.strip()
    return content[end + len("\n---\n") :].strip()


def extract_gemini_prompt_body(content: str, path: Path) -> str:
    match = re.search(r'prompt = """\n(.*)\n"""\s*$', content, re.DOTALL)
    if not match:
        raise AssertionError(f"{path}: missing Gemini prompt body")
    return match.group(1).strip()


def normalize_shared_command_body(content: str) -> str:
    lines: list[str] = []
    for line in content.strip().splitlines():
        if line in {
            "In this pack, SD means Software Delivery.",
            (
                "In this pack, SD means Software Delivery. A skill is a "
                "project-installed Markdown instruction bundle resolved by the "
                "agent's trusted installed-skill resolver."
            ),
        }:
            continue
        if line.startswith("# SD "):
            line = "# " + line[len("# SD ") :]
        lines.append(line.rstrip())
    normalized = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", normalized)


def apply_platform_body_deviations(platform: str, command: str, body: str) -> str:
    if platform == "github":
        body = body.replace(f"\n{GITHUB_UNTRUSTED_PR_NOTE}", "")
    if platform == "claude" and command in CLAUDE_COMMAND_ALIAS_REWRITES:
        platform_text, neutral_text = CLAUDE_COMMAND_ALIAS_REWRITES[command]
        body = body.replace(platform_text, neutral_text)
    return body


def neutral_command_sources() -> list[Path]:
    return sorted((install.ROOT / "templates/.commands").glob("sd-*.md"))


def command_name_from_source(source: Path) -> str:
    return source.stem.removeprefix("sd-")


class GeneratedParityTests(InstallTestCase):
    """Tests for generated payload, adapter parity, docs, and template validation."""

    def test_installs_shared_skill_and_existing_platform_adapters(self) -> None:
        root = self.make_repo(".cursor", ".gemini", ".github")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-work-backlog/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-work-designs/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-continue/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-start/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-finish-work/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-learnings/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local-all/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-update-spec/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-shell-lib.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-toolchain.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-housekeeping.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-scope.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-preflight.mjs").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-local.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-learnings.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-install-audit.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-pr-body-scope.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-update-spec-kb.py").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / ".prism/rules.schema.json").is_file())
        self.assertTrue((root / ".gito/config.toml").is_file())
        self.assertTrue((root / ".gito/sd-ai-command-pack.env").is_file())
        self.assertIn(
            "MAX_CONCURRENT_TASKS=4",
            (root / ".gito/sd-ai-command-pack.env").read_text(encoding="utf-8"),
        )
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_trellis_gitignore_block(
            (root / ".gitignore").read_text(encoding="utf-8")
        )
        self.assert_installed_targets_snapshot_matches_selection(root)
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/start.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/create-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/work-backlog.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/work-designs.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local-all.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-learnings.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-continue.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-start.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-finish-work.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-create-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-work-backlog.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-work-designs.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-local.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-local-all.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-learnings.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-full-check.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-housekeeping.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-update-spec.prompt.md").is_file())
        copilot_instructions = root / ".github/copilot-instructions.md"
        self.assertTrue(copilot_instructions.is_file())
        self.assert_copilot_guidance_block(
            copilot_instructions.read_text(encoding="utf-8")
        )
        self.assertTrue((root / ".cursor/commands/sd-continue.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-start.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-finish-work.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-create-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-work-backlog.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-work-designs.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-local.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-local-all.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-learnings.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-full-check.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-housekeeping.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-update-spec.md").is_file())
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".claude/commands/sd/start.md").exists())
        self.assertFalse((root / ".claude/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".claude/commands/sd/create-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/work-backlog.md").exists())
        self.assertFalse((root / ".claude/commands/sd/work-designs.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-local.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-local-all.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-learnings.md").exists())
        self.assertFalse((root / ".claude/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".claude/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".claude/commands/sd/update-spec.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-continue.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-start.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-finish-work.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-create-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-work-backlog.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-work-designs.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-local.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-local-all.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-learnings.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-update-spec.md").exists())

    def test_installs_newer_trellis_platform_adapters_when_active(self) -> None:
        root = self.make_repo(".kiro", ".reasonix", ".trae", ".zcode")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".kiro/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".kiro/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".kiro/skills/sd-work-backlog/SKILL.md").is_file())
        self.assertTrue((root / ".kiro/skills/sd-work-designs/SKILL.md").is_file())
        self.assertTrue((root / ".reasonix/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".reasonix/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".reasonix/skills/sd-work-backlog/SKILL.md").is_file())
        self.assertTrue((root / ".reasonix/skills/sd-work-designs/SKILL.md").is_file())
        self.assertTrue((root / ".trae/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".trae/commands/sd-create-pr.md").is_file())
        self.assertTrue((root / ".trae/commands/sd-work-backlog.md").is_file())
        self.assertTrue((root / ".trae/commands/sd-work-designs.md").is_file())
        self.assertTrue((root / ".trae/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".trae/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".trae/skills/sd-work-backlog/SKILL.md").is_file())
        self.assertTrue((root / ".trae/skills/sd-work-designs/SKILL.md").is_file())
        self.assertTrue((root / ".zcode/commands/sd/review-pr.md").is_file())
        self.assertTrue((root / ".zcode/commands/sd/create-pr.md").is_file())
        self.assertTrue((root / ".zcode/commands/sd/work-backlog.md").is_file())
        self.assertTrue((root / ".zcode/commands/sd/work-designs.md").is_file())
        self.assertFalse((root / ".qoder/commands/sd-review-pr.md").exists())
        self.assert_installed_targets_snapshot_matches_selection(root)

    def test_all_installs_every_adapter_without_anchors(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--all")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-start/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-work-backlog/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-work-designs/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local-all/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-learnings/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-toolchain.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-housekeeping.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-scope.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-preflight.mjs").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-local.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-learnings.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-pr-body-scope.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-update-spec-kb.py").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_installed_targets_snapshot_matches_selection(
            root,
            install_all=True,
        )
        self.assertTrue((root / ".claude/commands/sd/continue.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/start.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/finish-work.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/create-pr.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/work-backlog.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/work-designs.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-pr.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-local.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-local-all.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/review-learnings.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/full-check.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/housekeeping.md").is_file())
        self.assertTrue((root / ".claude/commands/sd/update-spec.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-continue.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-start.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-finish-work.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-create-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-work-backlog.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-work-designs.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-local.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-local-all.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-learnings.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-full-check.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-housekeeping.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-update-spec.md").is_file())
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/start.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/create-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/work-backlog.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/work-designs.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local-all.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-learnings.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertTrue((root / ".github/prompts/sd-continue.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-start.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-finish-work.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-create-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-work-backlog.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-work-designs.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-pr.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-local.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-local-all.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-review-learnings.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-full-check.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-housekeeping.prompt.md").is_file())
        self.assertTrue((root / ".github/prompts/sd-update-spec.prompt.md").is_file())
        copilot_instructions = root / ".github/copilot-instructions.md"
        self.assertTrue(copilot_instructions.is_file())
        self.assert_copilot_guidance_block(
            copilot_instructions.read_text(encoding="utf-8")
        )
        self.assertTrue((root / ".opencode/commands/sd-continue.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-start.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-finish-work.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-create-pr.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-work-backlog.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-work-designs.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-local.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-local-all.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-review-learnings.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-full-check.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-housekeeping.md").is_file())
        self.assertTrue((root / ".opencode/commands/sd-update-spec.md").is_file())

    def test_installed_adapters_can_resolve_shared_skill(self) -> None:
        root = self.make_repo(".claude", ".cursor", ".gemini", ".github", ".opencode")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        review_skill = root / ".agents/skills/sd-review-pr/SKILL.md"
        create_pr_skill = root / ".agents/skills/sd-create-pr/SKILL.md"
        work_backlog_skill = root / ".agents/skills/sd-work-backlog/SKILL.md"
        work_designs_skill = root / ".agents/skills/sd-work-designs/SKILL.md"
        review_local_skill = root / ".agents/skills/sd-review-local/SKILL.md"
        review_learnings_skill = root / ".agents/skills/sd-review-learnings/SKILL.md"
        full_check_skill = root / ".agents/skills/sd-full-check/SKILL.md"
        housekeeping_skill = root / ".agents/skills/sd-housekeeping/SKILL.md"
        review_local_script = root / "scripts/sd-ai-command-pack-review-local.sh"
        review_learnings_script = root / "scripts/sd-ai-command-pack-review-learnings.py"
        full_check_script = root / "scripts/sd-ai-command-pack-full-check.sh"
        housekeeping_script = root / "scripts/sd-ai-command-pack-housekeeping.sh"
        self.assertTrue(review_skill.is_file())
        self.assertTrue(create_pr_skill.is_file())
        self.assertTrue(work_backlog_skill.is_file())
        self.assertTrue(work_designs_skill.is_file())
        self.assertTrue(review_local_skill.is_file())
        self.assertTrue(review_learnings_skill.is_file())
        self.assertTrue(full_check_skill.is_file())
        self.assertTrue(housekeeping_skill.is_file())
        self.assertTrue(review_local_script.is_file())
        self.assertTrue(review_learnings_script.is_file())
        self.assertTrue(full_check_script.is_file())
        self.assertTrue(housekeeping_script.is_file())
        claude_start = root / ".claude/commands/sd/start.md"
        self.assertTrue(claude_start.is_file(), claude_start)
        claude_start_content = claude_start.read_text(encoding="utf-8")
        self.assertIn("installs no `trellis-start` skill", claude_start_content)
        self.assertIn("./.trellis/scripts/get_context.py", claude_start_content)
        for adapter in [
            root / ".cursor/commands/sd-start.md",
            root / ".gemini/commands/sd/start.toml",
            root / ".github/prompts/sd-start.prompt.md",
            root / ".opencode/commands/sd-start.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                "Resolve the `trellis-start` skill by name",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/continue.md",
            root / ".cursor/commands/sd-continue.md",
            root / ".gemini/commands/sd/continue.toml",
            root / ".github/prompts/sd-continue.prompt.md",
            root / ".opencode/commands/sd-continue.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                "Resolve the `trellis-continue` skill by name",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/finish-work.md",
            root / ".cursor/commands/sd-finish-work.md",
            root / ".gemini/commands/sd/finish-work.toml",
            root / ".github/prompts/sd-finish-work.prompt.md",
            root / ".opencode/commands/sd-finish-work.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                "Resolve the `trellis-finish-work` skill by name",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/create-pr.md",
            root / ".cursor/commands/sd-create-pr.md",
            root / ".gemini/commands/sd/create-pr.toml",
            root / ".github/prompts/sd-create-pr.prompt.md",
            root / ".opencode/commands/sd-create-pr.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-create-pr` skill by name", content)
            self.assertIn("sd-update-spec", content)
            self.assertIn("sd-review-pr", content)
        for adapter in [
            root / ".claude/commands/sd/work-backlog.md",
            root / ".cursor/commands/sd-work-backlog.md",
            root / ".gemini/commands/sd/work-backlog.toml",
            root / ".github/prompts/sd-work-backlog.prompt.md",
            root / ".opencode/commands/sd-work-backlog.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-work-backlog` skill by name", content)
            self.assertIn("one task per iteration", content)
            self.assertIn("sd-create-pr", content)
            self.assertIn("sd-housekeeping", content)
        for adapter in [
            root / ".claude/commands/sd/work-designs.md",
            root / ".cursor/commands/sd-work-designs.md",
            root / ".gemini/commands/sd/work-designs.toml",
            root / ".github/prompts/sd-work-designs.prompt.md",
            root / ".opencode/commands/sd-work-designs.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-work-designs` skill by name", content)
            self.assertIn("design.md", content)
            self.assertIn("implement.md", content)
            self.assertIn("numbered list", content)
        for adapter in [
            root / ".claude/commands/sd/review-pr.md",
            root / ".cursor/commands/sd-review-pr.md",
            root / ".gemini/commands/sd/review-pr.toml",
            root / ".github/prompts/sd-review-pr.prompt.md",
            root / ".opencode/commands/sd-review-pr.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            self.assertIn(
                "Resolve the `sd-review-pr` skill by name",
                adapter.read_text(encoding="utf-8"),
            )
        for adapter in [
            root / ".claude/commands/sd/review-local.md",
            root / ".cursor/commands/sd-review-local.md",
            root / ".gemini/commands/sd/review-local.toml",
            root / ".github/prompts/sd-review-local.prompt.md",
            root / ".opencode/commands/sd-review-local.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-review-local` skill by name", content)
            self.assertIn("scripts/sd-ai-command-pack-review-local.sh", content)
        for adapter in [
            root / ".claude/commands/sd/review-local-all.md",
            root / ".cursor/commands/sd-review-local-all.md",
            root / ".gemini/commands/sd/review-local-all.toml",
            root / ".github/prompts/sd-review-local-all.prompt.md",
            root / ".opencode/commands/sd-review-local-all.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-review-local-all` skill by name", content)
            self.assertIn(
                "scripts/sd-ai-command-pack-review-local.sh --full-codebase",
                content,
            )
        for adapter in [
            root / ".claude/commands/sd/review-learnings.md",
            root / ".cursor/commands/sd-review-learnings.md",
            root / ".gemini/commands/sd/review-learnings.toml",
            root / ".github/prompts/sd-review-learnings.prompt.md",
            root / ".opencode/commands/sd-review-learnings.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-review-learnings` skill by name", content)
            self.assertIn("scripts/sd-ai-command-pack-review-learnings.py", content)
        for adapter in [
            root / ".claude/commands/sd/full-check.md",
            root / ".cursor/commands/sd-full-check.md",
            root / ".gemini/commands/sd/full-check.toml",
            root / ".github/prompts/sd-full-check.prompt.md",
            root / ".opencode/commands/sd-full-check.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-full-check` skill by name", content)
            self.assertIn("source of truth for the exact checks", content)
        for adapter in [
            root / ".claude/commands/sd/housekeeping.md",
            root / ".cursor/commands/sd-housekeeping.md",
            root / ".gemini/commands/sd/housekeeping.toml",
            root / ".github/prompts/sd-housekeeping.prompt.md",
            root / ".opencode/commands/sd-housekeeping.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-housekeeping` skill by name", content)
            self.assertIn("scripts/sd-ai-command-pack-housekeeping.sh", content)
        for adapter in [
            root / ".claude/commands/sd/update-spec.md",
            root / ".cursor/commands/sd-update-spec.md",
            root / ".gemini/commands/sd/update-spec.toml",
            root / ".github/prompts/sd-update-spec.prompt.md",
            root / ".opencode/commands/sd-update-spec.md",
        ]:
            self.assertTrue(adapter.is_file(), adapter)
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-update-spec` skill by name", content)
            self.assertIn("source of truth for Trellis update-spec delegation", content)
            self.assertNotIn("Trellis " + "update-spec first", content)

    def test_readme_documents_trellis_prerequisite_and_install_docs(self) -> None:
        readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")

        self.assert_trellis_prerequisite_documented(readme)
        self.assertIn("This pack only works", readme)
        self.assertIn("Prerequisite: install Trellis", readme)
        self.assertIn("Quick links:", readme)
        self.assertIn("[Overview](#overview)", readme)
        self.assertIn("[Commands](#commands)", readme)
        self.assertIn("[Configuration Quick Reference](#configuration-quick-reference)", readme)
        self.assertIn("[Install](#install)", readme)
        for command_heading in (
            "### sd-start",
            "### sd-create-pr",
            "### sd-work-backlog",
            "### sd-work-designs",
            "### sd-review-local-all",
            "### sd-update-spec",
            "### sd-housekeeping",
        ):
            self.assertIn(command_heading, readme)
        self.assertIn(
            "[docs/SD_AI_COMMAND_PACK.md](docs/SD_AI_COMMAND_PACK.md#commands)",
            readme,
        )
        self.assertIn("avoid duplicate README drift", readme)
        self.assertNotIn("sd-ai-command-pack trellis-gitignore start", readme)
        self.assertNotIn("SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START", readme)
        self.assertIn("quick smoke test", readme)
        self.assertIn("SANDBOX_TMP", readme)
        self.assertIn("PYTHONPYCACHEPREFIX", readme)
        self.assertIn("UV_CACHE_DIR", readme)
        self.assertIn("RUFF_CACHE_DIR", readme)
        self.assertIn("scripts/sd-ai-command-pack-install-audit.py", readme)
        self.assertIn("scripts/sd-ai-command-pack-update-spec-kb.py --dry-run", readme)
        self.assertIn("Normal shared installs should commit that snapshot", readme)
        self.assertIn("keeps `.sd-ai-command-pack/installed-targets.txt`", readme)
        for expected in (
            "python3 install.py /path/to/trellis/repo",
            "python3 install.py /path/to/repo --dry-run",
            "python3 install.py /path/to/repo --force",
            "python3 install.py /path/to/repo --force --backup",
            "python3 install.py /path/to/repo --remove",
        ):
            self.assertIn(expected, readme)

    def test_coverage_dependency_is_declared_and_used_by_ci(self) -> None:
        requirements = (PACK_ROOT / "requirements-dev.txt").read_text(
            encoding="utf-8"
        )
        workflow = (
            PACK_ROOT / ".github/workflows/tests.yml"
        ).read_text(encoding="utf-8")
        readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")
        pyproject = (PACK_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        gitignore = (PACK_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertRegex(requirements, r"(?m)^coverage[<>=!~]")
        self.assertRegex(requirements, r"(?m)^ruff==\d+\.\d+\.\d+$")
        self.assertRegex(requirements, r"(?m)^mypy==\d+\.\d+\.\d+$")
        for expected in (
            "runs-on: ${{ matrix.os }}",
            "fail-fast: false",
            "os: macos-latest",
            "unittest-output.log",
            "skipped=[1-9][0-9]*",
            "python3 -m ruff check install.py installer scripts templates/scripts tests",
            "node --check scripts/sd-ai-command-pack-review-preflight.mjs",
            "node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs",
            "bash .github/scripts/check-opencode-js.sh",
            "python3 -m mypy installer",
            "needs: [unittest, lint, security, main-push-scope]",
            "LINT_RESULT",
        ):
            self.assertIn(expected, workflow)
        for expected in (
            "[tool.ruff]",
            "[tool.mypy]",
            'target-version = "py310"',
            'python_version = "3.10"',
            'select = ["E4", "E7", "E9", "F", "I", "B"]',
            '".ruff_cache"',
        ):
            self.assertIn(expected, pyproject)
        self.assertNotIn("[tool.ruff.lint.per-file-ignores]", pyproject)
        self.assertIn(".ruff_cache/", gitignore)
        self.assertIn("unittest-output.log", gitignore)
        for expected in (
            "python3 -m pip install -r requirements-dev.txt",
            'COVERAGE_PROCESS_START="$(pwd)/.coveragerc"',
            'COVERAGE_FILE="$(pwd)/.coverage"',
            'PYTHONPATH="$(pwd)/tests/coverage_sitecustomize'
            '${PYTHONPATH:+:$PYTHONPATH}"',
            "python3 -m coverage run --parallel-mode -m unittest discover -s tests",
            "python3 -m coverage combine",
            'python3 -m coverage report --include="install.py,installer/*"'
            " --fail-under=100",
            'python3 -m coverage report'
            ' --include="scripts/sd-ai-command-pack-*" --fail-under=76',
        ):
            self.assertIn(expected, workflow)
        for expected in (
            "python -m pip install -r requirements-dev.txt",
            "python -m ruff check install.py installer scripts templates/scripts tests",
            "command -v node >/dev/null 2>&1",
            "node --check scripts/sd-ai-command-pack-review-preflight.mjs",
            "node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs",
            "bash .github/scripts/check-opencode-js.sh",
            "warning: node not found; skipping JavaScript syntax checks.",
            'COVERAGE_PROCESS_START="$(pwd)/.coveragerc"',
            'COVERAGE_FILE="$(pwd)/.coverage"',
            'PYTHONPATH="$(pwd)/tests/coverage_sitecustomize'
            '${PYTHONPATH:+:$PYTHONPATH}"',
            "python -m coverage run --parallel-mode -m unittest discover -s tests",
            "python -m coverage combine",
            'python -m coverage report --include="install.py,installer/*"'
            " --fail-under=100",
            'python -m coverage report'
            ' --include="scripts/sd-ai-command-pack-*" --fail-under=76',
        ):
            self.assertIn(expected, readme)

    def test_opencode_javascript_syntax_gate_checks_tracked_files(self) -> None:
        script = PACK_ROOT / ".github/scripts/check-opencode-js.sh"
        current = subprocess.run(
            ["bash", str(script)],
            cwd=PACK_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(current.returncode, 0, current.stderr)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            copied_script = root / ".github/scripts/check-opencode-js.sh"
            copied_script.parent.mkdir(parents=True)
            shutil.copy2(script, copied_script)
            bad_js = root / ".opencode/lib/bad.js"
            bad_js.parent.mkdir(parents=True)
            bad_js.write_text("const = ;\n", encoding="utf-8")
            (bad_js.parent / "valid name.js").write_text(
                "export const valid = true;\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "add", "-f", "."],
                cwd=root,
                check=True,
                capture_output=True,
            )
            tracked = subprocess.run(
                ["git", "ls-files", "--", "*.js"],
                cwd=root,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn(".opencode/lib/bad.js", tracked.stdout)

            invalid = subprocess.run(
                ["bash", str(copied_script)],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(
                invalid.returncode,
                0,
                f"stdout={invalid.stdout!r} stderr={invalid.stderr!r}",
            )
            self.assertIn("bad.js", invalid.stderr)

    def test_ci_dependency_and_main_push_guards_are_bounded(self) -> None:
        workflow = (PACK_ROOT / ".github/workflows/tests.yml").read_text(
            encoding="utf-8"
        )
        dependabot = yaml.safe_load(
            (PACK_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
        )
        main_push_guard = (
            PACK_ROOT / ".github/scripts/check-main-push-scope.sh"
        ).read_text(encoding="utf-8")

        self.assertNotRegex(
            workflow,
            r"uses: actions/(?:checkout|setup-python)@v\d+",
        )
        self.assertEqual(
            workflow.count(
                "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5"
            ),
            5,
        )
        self.assertEqual(
            workflow.count(
                "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
            ),
            3,
        )
        self.assertIn("main-push-scope:", workflow)
        self.assertIn('"${{ github.event.before }}" "${{ github.sha }}"', workflow)
        self.assertIn("git diff --no-renames --name-only -z", main_push_guard)
        self.assertIn(".trellis/tasks/*|.trellis/workspace/*", main_push_guard)

        updates = dependabot["updates"]
        self.assertEqual(
            {entry["package-ecosystem"] for entry in updates},
            {"pip", "github-actions"},
        )
        for entry in updates:
            self.assertEqual(entry["schedule"]["interval"], "monthly")
            self.assertEqual(entry["open-pull-requests-limit"], 2)

    def test_contributor_workflow_is_documented(self) -> None:
        readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")
        contributing = (PACK_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        makefile = (PACK_ROOT / "Makefile").read_text(encoding="utf-8")

        for expected in (
            "make setup",
            "make check",
            "[CONTRIBUTING.md](CONTRIBUTING.md)",
            "git config core.hooksPath .githooks",
        ):
            self.assertIn(expected, readme)
        for expected in (
            "make setup",
            "make test",
            "make lint",
            "make audit",
            "make full-check",
            "make check",
            "pack JavaScript syntax checks when Node is available",
            "Missing optional tools print warnings",
            "Bump `manifest.json` whenever shipped payload changes",
            "Treat `templates/**` as the source of truth",
            "sd-ai-command-pack-toolchain.sh run-python -- install.py . --force",
            "Keep Trellis-owned platform files in their Trellis-managed state",
            "Track `.opencode/bun.lock`",
            "`.claude/settings.local.json`",
            ".trellis/spec/frontend/adapter-guidelines.md",
            ".trellis/spec/backend/manifest-and-filesystem.md",
        ):
            self.assertIn(expected, contributing)
        for target in (
            "setup:",
            "hooks:",
            "test:",
            "lint:",
            "audit:",
            "full-check:",
            "check:",
            "git config core.hooksPath .githooks",
            "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0",
            "SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0",
            "command -v node >/dev/null 2>&1",
            "warning: node not found; skipping JavaScript syntax checks.",
            'skipped=[1-9][0-9]*',
            '"$(VENV_PYTHON)" -m mypy installer',
        ):
            self.assertIn(target, makefile)

    def test_opencode_dependency_uses_canonical_range_and_locked_resolution(
        self,
    ) -> None:
        opencode_package_path = PACK_ROOT / ".opencode/package.json"
        opencode_package = opencode_package_path.read_text(encoding="utf-8")
        opencode_lock = (
            PACK_ROOT / ".opencode/bun.lock"
        ).read_text(encoding="utf-8")

        self.assertIn('"@opencode-ai/plugin": "^1.14.39"', opencode_package)
        self.assertIn('"@opencode-ai/plugin": "^1.14.39"', opencode_lock)
        plugin_resolution = re.search(
            r'"@opencode-ai/plugin": \['
            r'"@opencode-ai/plugin@(\d+\.\d+\.\d+)",.*'
            r'"sha512-[A-Za-z0-9+/=]+"\]',
            opencode_lock,
        )
        self.assertIsNotNone(
            plugin_resolution,
            ".opencode/bun.lock must pin an integrity-checked plugin version",
        )

    def test_repo_declares_mit_license(self) -> None:
        raw, _ = install.load_manifest()
        readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")
        license_text = (PACK_ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertEqual(raw.get("license"), "MIT")
        self.assertIn("[![License: MIT]", readme)
        self.assertIn("[MIT License](LICENSE)", readme)
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 Platypeeps", license_text)
        self.assertIn("Permission is hereby granted, free of charge", license_text)

    def test_installed_usage_guide_documents_trellis_prerequisite(self) -> None:
        root = self.make_repo()

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        template = (
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md"
        ).read_text(encoding="utf-8")
        installed = (root / "docs/SD_AI_COMMAND_PACK.md").read_text(
            encoding="utf-8"
        )
        self.assert_trellis_prerequisite_documented(template)
        self.assert_trellis_prerequisite_documented(installed)
        for expected in (
            "Quick links:",
            "sd-ai-command-pack trellis-gitignore start",
            "SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START",
            "quick smoke test",
            "SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF",
            "discovered branch-diff",
            "branch: <default>",
            "branch-diff deletions are not reviewed as deleted diff paths",
            "ClientError: 429",
            "installs should commit this file",
            "clone-local exclude list instead",
            "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS",
            "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS",
            "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS",
            "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_MAX_ATTEMPTS",
            "sandbox-local cache directories",
            "PYTHONPYCACHEPREFIX",
            "UV_TOOL_DIR",
            "RUFF_CACHE_DIR",
            "agent-facing final response",
            "numbered `Next Steps` list",
            "open follow-up items from the session",
            "existing Trellis tasks already in progress",
            "high-value Trellis task",
            "candidates to start next",
        ):
            self.assertIn(expected, installed)
        self.assertEqual(installed, template)

    def test_installer_modules_use_explicit_public_import_surfaces(self) -> None:
        installer_paths = [PACK_ROOT / "install.py", *sorted((PACK_ROOT / "installer").glob("*.py"))]
        for path in installer_paths:
            content = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(PACK_ROOT).as_posix()):
                self.assertNotIn(" import *", content)
                if path.name != "__init__.py":
                    self.assertIn("__all__ = [", content)

        self.assertIs(install.install_file, install.fileops.install_file)
        self.assertIs(install.load_manifest, install.manifest.load_manifest)
        self.assertIs(install.remove_installed_pack, install.removal.remove_installed_pack)

    def test_installed_targets_snapshot_lists_scope_scripts_and_guide(self) -> None:
        root = self.make_repo(".github")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        snapshot = (root / install.INSTALLED_TARGETS_FILE).read_text(
            encoding="utf-8"
        )
        for expected in (
            ".gitignore",
            "scripts/sd-ai-command-pack-review-scope.sh",
            "scripts/sd-ai-command-pack-review-preflight.mjs",
            "scripts/sd-ai-command-pack-review-learnings.py",
            "scripts/sd-ai-command-pack-pr-body-scope.py",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
            "docs/SD_AI_COMMAND_PACK.md",
        ):
            self.assertIn(expected, snapshot)

    def test_installed_targets_snapshot_updates_existing_content(self) -> None:
        root = self.make_repo()
        snapshot = root / install.INSTALLED_TARGETS_FILE
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text("stale\n", encoding="utf-8")
        selected = [self.valid_pack_file()]

        result = install.install_installed_targets_file(
            selected,
            root,
            dry_run=False,
        )

        self.assertEqual(result.status, "updated")
        self.assertEqual(
            snapshot.read_text(encoding="utf-8"),
            install.installed_targets_content(selected),
        )

    def test_manifest_sources_exist_and_targets_are_unique(self) -> None:
        _, files = install.load_manifest()

        install.validate_manifest(files)
        self.assertEqual(len({file.target for file in files}), len(files))
        for file in files:
            self.assertTrue(file.source.is_file(), file.source)

    def test_manifest_declares_current_trellis_platform_adapters(self) -> None:
        _, files = install.load_manifest()
        platforms_with_manifest_entries = {file.platform for file in files}
        expected_platforms = {
            "antigravity",
            "claude",
            "codebuddy",
            "cursor",
            "devin",
            "droid",
            "gemini",
            "github",
            "kilo",
            "kiro",
            "opencode",
            "pi",
            "qoder",
            "reasonix",
            "shared",
            "trae",
            "zcode",
        }

        self.assertEqual(platforms_with_manifest_entries, expected_platforms)
        self.assertIn("codex", install.PLATFORMS)
        self.assertTrue(
            any(
                file.platform == "shared"
                and file.target == Path(".agents/skills/sd-review-pr/SKILL.md")
                for file in files
            )
        )
        for platform in expected_platforms - {"shared"}:
            self.assertIn(platform, install.ACTIVE_TRELLIS_PLATFORM_MARKERS)
            self.assertIn(platform, install.TRELLIS_INIT_PLATFORM_FLAGS)

        expected_targets = {
            ".agent/workflows/sd-review-pr.md",
            ".agent/workflows/sd-create-pr.md",
            ".agent/workflows/sd-work-backlog.md",
            ".agent/workflows/sd-work-designs.md",
            ".agent/skills/sd-review-pr/SKILL.md",
            ".agent/skills/sd-create-pr/SKILL.md",
            ".agent/skills/sd-work-backlog/SKILL.md",
            ".agent/skills/sd-work-designs/SKILL.md",
            ".codebuddy/commands/sd/review-pr.md",
            ".codebuddy/commands/sd/create-pr.md",
            ".codebuddy/commands/sd/work-backlog.md",
            ".codebuddy/commands/sd/work-designs.md",
            ".codebuddy/skills/sd-review-pr/SKILL.md",
            ".codebuddy/skills/sd-create-pr/SKILL.md",
            ".codebuddy/skills/sd-work-backlog/SKILL.md",
            ".codebuddy/skills/sd-work-designs/SKILL.md",
            ".devin/workflows/sd-review-pr.md",
            ".devin/workflows/sd-create-pr.md",
            ".devin/workflows/sd-work-backlog.md",
            ".devin/workflows/sd-work-designs.md",
            ".factory/commands/sd/review-pr.md",
            ".factory/commands/sd/create-pr.md",
            ".factory/commands/sd/work-backlog.md",
            ".factory/commands/sd/work-designs.md",
            ".kilocode/workflows/sd-review-pr.md",
            ".kilocode/workflows/sd-create-pr.md",
            ".kilocode/workflows/sd-work-backlog.md",
            ".kilocode/workflows/sd-work-designs.md",
            ".kiro/skills/sd-review-pr/SKILL.md",
            ".kiro/skills/sd-create-pr/SKILL.md",
            ".kiro/skills/sd-work-backlog/SKILL.md",
            ".kiro/skills/sd-work-designs/SKILL.md",
            ".pi/prompts/sd-review-pr.md",
            ".pi/prompts/sd-create-pr.md",
            ".pi/prompts/sd-work-backlog.md",
            ".pi/prompts/sd-work-designs.md",
            ".qoder/commands/sd-review-pr.md",
            ".qoder/commands/sd-create-pr.md",
            ".qoder/commands/sd-work-backlog.md",
            ".qoder/commands/sd-work-designs.md",
            ".reasonix/skills/sd-review-pr/SKILL.md",
            ".reasonix/skills/sd-create-pr/SKILL.md",
            ".reasonix/skills/sd-work-backlog/SKILL.md",
            ".reasonix/skills/sd-work-designs/SKILL.md",
            ".trae/commands/sd-review-pr.md",
            ".trae/commands/sd-create-pr.md",
            ".trae/commands/sd-work-backlog.md",
            ".trae/commands/sd-work-designs.md",
            ".zcode/commands/sd/review-pr.md",
            ".zcode/commands/sd/create-pr.md",
            ".zcode/commands/sd/work-backlog.md",
            ".zcode/commands/sd/work-designs.md",
        }
        actual_targets = {file.target.as_posix() for file in files}
        self.assertTrue(expected_targets.issubset(actual_targets))

    def test_adapters_reference_installed_shared_assets(self) -> None:
        _, files = install.load_manifest()
        adapter_files = [file for file in files if file.kind in {"command", "prompt"}]

        self.assertGreater(len(adapter_files), 0)
        for file in adapter_files:
            content = file.source.read_text(encoding="utf-8")
            if "start" in file.target.name:
                if file.platform == "claude":
                    self.assertIn("installs no `trellis-start` skill", content)
                    self.assertIn("./.trellis/scripts/get_context.py", content)
                else:
                    self.assertIn("Resolve the `trellis-start` skill by name", content)
                    self.assertIn("Use that skill as the primary instructions", content)
            elif "continue" in file.target.name:
                self.assertIn("Resolve the `trellis-continue` skill by name", content)
                self.assertIn("Use that skill as the primary instructions", content)
            elif "finish-work" in file.target.name:
                self.assertIn("Resolve the `trellis-finish-work` skill by name", content)
                self.assertIn("Use that skill as the primary instructions", content)
            elif "create-pr" in file.target.name:
                self.assertIn("Resolve the `sd-create-pr` skill by name", content)
                self.assertIn("sd-update-spec", content)
                self.assertIn("sd-review-pr", content)
            elif "work-designs" in file.target.name:
                self.assertIn("Resolve the `sd-work-designs` skill by name", content)
                self.assertIn("design.md", content)
                self.assertIn("implement.md", content)
                self.assertIn("numbered list", content)
            elif "work-backlog" in file.target.name:
                self.assertIn("Resolve the `sd-work-backlog` skill by name", content)
                self.assertIn("one task per iteration", content)
                self.assertIn("sd-create-pr", content)
                self.assertIn("sd-housekeeping", content)
            elif "full-check" in file.target.name:
                self.assertIn("Resolve the `sd-full-check` skill by name", content)
                self.assertIn("source of truth for the exact checks", content)
            elif "review-local-all" in file.target.name:
                self.assertIn("Resolve the `sd-review-local-all` skill by name", content)
                self.assertIn(
                    "scripts/sd-ai-command-pack-review-local.sh --full-codebase",
                    content,
                )
            elif "review-local" in file.target.name:
                self.assertIn("Resolve the `sd-review-local` skill by name", content)
                self.assertIn("scripts/sd-ai-command-pack-review-local.sh", content)
            elif "housekeeping" in file.target.name:
                self.assertIn(
                    "Resolve the `sd-housekeeping` skill by name",
                    content,
                )
                self.assertIn("scripts/sd-ai-command-pack-housekeeping.sh", content)
            elif "update-spec" in file.target.name:
                self.assertIn("Resolve the `sd-update-spec` skill by name", content)
                self.assertIn("source of truth for Trellis update-spec delegation", content)
            elif "review-learnings" in file.target.name:
                self.assertIn("Resolve the `sd-review-learnings` skill by name", content)
                self.assertIn("scripts/sd-ai-command-pack-review-learnings.py", content)
            else:
                self.assertIn("Resolve the `sd-review-pr` skill by name", content)

    def test_bespoke_command_bodies_match_neutral_sources(self) -> None:
        platform_paths = {
            "claude": lambda command: (
                install.ROOT / f"templates/.claude/commands/sd/{command}.md"
            ),
            "gemini": lambda command: (
                install.ROOT / f"templates/.gemini/commands/sd/{command}.toml"
            ),
            "github": lambda command: (
                install.ROOT / f"templates/.github/prompts/sd-{command}.prompt.md"
            ),
        }

        for neutral_source in neutral_command_sources():
            command = command_name_from_source(neutral_source)
            neutral_body = normalize_shared_command_body(
                strip_yaml_frontmatter(neutral_source.read_text(encoding="utf-8"))
            )
            for platform, path_for_command in platform_paths.items():
                path = path_for_command(command)
                if not path.exists():
                    continue
                with self.subTest(platform=platform, command=command):
                    exemption = BESPOKE_BODY_PARITY_EXEMPTIONS.get((platform, command))
                    content = path.read_text(encoding="utf-8")
                    if exemption:
                        self.assertIn("installs no `trellis-start` skill", content)
                        continue
                    if platform == "gemini":
                        body = extract_gemini_prompt_body(content, path)
                    else:
                        body = strip_yaml_frontmatter(content)
                    adapter_body = normalize_shared_command_body(
                        apply_platform_body_deviations(platform, command, body)
                    )
                    self.assertEqual(adapter_body, neutral_body)

    def test_review_pr_remote_round_limit_defaults_to_two(self) -> None:
        _, files = install.load_manifest()
        review_command_sources = {
            file.source
            for file in files
            if file.kind in {"command", "prompt"}
            and "review-pr" in file.target.name
        }

        self.assertGreater(len(review_command_sources), 0)
        for source in review_command_sources:
            with self.subTest(source=source.relative_to(install.ROOT).as_posix()):
                content = source.read_text(encoding="utf-8")
                self.assertIn(
                    "SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`, default `2`",
                    content,
                )
                self.assertNotIn(
                    "SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`, default `5`",
                    content,
                )

        skill = (
            install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'REMOTE_REVIEW_ROUND_LIMIT="${SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT:-2}"',
            skill,
        )
        self.assertIn("configured remote round limit, default two", skill)
        self.assertNotIn("configured remote round limit, default five", skill)

        readme = (install.ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT` | Max remote "
            "review request/fix rounds before asking whether to continue. | `2` |",
            readme,
        )
        guide = (
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "The round limit\ndefaults to two configured remote-review requests",
            guide,
        )

    def test_neutral_command_fanout_matches_registry(self) -> None:
        _, files = install.load_manifest()
        neutral_sources = {
            source.name: source.relative_to(install.ROOT).as_posix()
            for source in neutral_command_sources()
        }
        expected_entries = set()

        for platform in install.NEUTRAL_COMMAND_SOURCE_PLATFORMS:
            info = install.PLATFORM_REGISTRY[platform]
            self.assertIsNotNone(info.command_kind, platform)
            self.assertIsNotNone(info.command_target_pattern, platform)
            for filename, source in neutral_sources.items():
                command = filename.removeprefix("sd-").removesuffix(".md")
                target = info.command_target_pattern.format(
                    filename=filename,
                    name=command,
                )
                expected_entries.add((platform, info.command_kind, source, target))

        actual_entries = {
            (
                file.platform,
                file.kind,
                file.source.relative_to(install.ROOT).as_posix(),
                file.target.as_posix(),
            )
            for file in files
            if file.platform in install.NEUTRAL_COMMAND_SOURCE_PLATFORMS
            and file.source.relative_to(install.ROOT).parts[:2]
            == ("templates", ".commands")
        }

        self.assertEqual(actual_entries, expected_entries)
        self.assertEqual(
            list((install.ROOT / "templates/.opencode/commands").glob("sd-*.md")),
            [],
        )

    def test_shared_skill_frontmatter_is_strict_yaml(self) -> None:
        allowed_keys = {"name", "description", "license", "allowed-tools", "metadata"}
        skill_paths = sorted((install.ROOT / "templates/.agents/skills").glob("*/SKILL.md"))

        self.assertGreater(len(skill_paths), 0)
        for skill_path in skill_paths:
            with self.subTest(skill=skill_path.relative_to(install.ROOT).as_posix()):
                content = skill_path.read_text(encoding="utf-8")
                match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
                self.assertIsNotNone(match, f"{skill_path}: missing YAML frontmatter")
                frontmatter = yaml.safe_load(match.group(1))
                self.assertIsInstance(frontmatter, dict)
                self.assertIn("name", frontmatter)
                self.assertIn("description", frontmatter)
                self.assertIsInstance(frontmatter["name"], str)
                self.assertIsInstance(frontmatter["description"], str)
                unexpected_keys = set(frontmatter) - allowed_keys
                self.assertEqual(
                    unexpected_keys,
                    set(),
                    f"{skill_path}: unexpected frontmatter keys: {sorted(unexpected_keys)}",
                )

    def test_flat_markdown_entries_are_completion_visible(self) -> None:
        _, files = install.load_manifest()
        opencode_files = {
            file.target.name: file
            for file in files
            if file.platform == "opencode" and file.kind == "command"
        }
        commands = [
            "start",
            "continue",
            "finish-work",
            "create-pr",
            "work-backlog",
            "work-designs",
            "review-pr",
            "review-local",
            "review-local-all",
            "review-learnings",
            "full-check",
            "housekeeping",
            "update-spec",
        ]

        for command in commands:
            github_path = (
                install.ROOT / f"templates/.github/prompts/sd-{command}.prompt.md"
            )
            github_content = github_path.read_text(encoding="utf-8")
            self.assertTrue(github_content.startswith("---\n"), github_path)
            self.assertIn("description:", github_content)
            self.assertIn("mode: agent", github_content)

            generic_path = install.ROOT / f"templates/.commands/sd-{command}.md"
            generic_content = generic_path.read_text(encoding="utf-8")
            self.assertTrue(generic_content.startswith("---\n"), generic_path)
            self.assertIn("description:", generic_content)

            opencode_file = opencode_files[f"sd-{command}.md"]
            self.assertEqual(opencode_file.source, generic_path)

    def test_gemini_entries_use_namespaced_toml_completion_shape(self) -> None:
        expected_descriptions = {
            "start": "Initialize or resume a task using the Trellis start workflow.",
            "continue": "Resume the current Trellis task or workflow state.",
            "finish-work": "Wrap up the current Trellis coding session.",
            "create-pr": "Create or reuse a PR after SD spec refresh, commit, and push, then run the SD PR review loop.",
            "work-backlog": "Work through the Trellis backlog one task at a time through SD PR review and housekeeping.",
            "work-designs": "Add Trellis design and implementation-plan artifacts for tasks that need planning before implementation.",
            "review-pr": "Run the Software Delivery (SD) pull-request review loop.",
            "review-local": "Run the Software Delivery (SD) local review loop.",
            "review-local-all": "Run the Software Delivery (SD) full-codebase local review loop.",
            "review-learnings": "Detect or update repository review learnings.",
            "full-check": "Run the Software Delivery (SD) full-check gate for deterministic checks, local review, and readiness reporting.",
            "housekeeping": "Run Software Delivery (SD) end-of-stream housekeeping for a completed work stream.",
            "update-spec": "Run the Software Delivery (SD) update-spec workflow for repository knowledge artifacts.",
        }
        _, files = install.load_manifest()
        gemini_commands = [
            file
            for file in files
            if file.platform == "gemini" and file.kind == "command"
        ]

        self.assertEqual(len(gemini_commands), len(expected_descriptions))
        for file in gemini_commands:
            command_name = file.target.stem
            self.assertIn(command_name, expected_descriptions)
            self.assertEqual(file.target.parent, Path(".gemini/commands/sd"))
            self.assertEqual(
                file.source.parent.relative_to(install.ROOT),
                Path("templates") / file.target.parent,
            )
            self.assertEqual(file.target.suffix, ".toml")
            self.assertFalse(file.target.name.startswith("sd-"), file.target)

            content = file.source.read_text(encoding="utf-8")
            self.assertIn(
                f'description = "{expected_descriptions[command_name]}"',
                content,
            )
            self.assertIn('prompt = """', content)

    def test_command_adapters_use_pack_owned_sd_namespace(self) -> None:
        _, files = install.load_manifest()

        command_files = [file for file in files if file.kind == "command"]
        github_prompt_files = [
            file for file in files if file.platform == "github" and file.kind == "prompt"
        ]
        self.assertGreater(len(command_files), 0)
        self.assertGreater(len(github_prompt_files), 0)
        for file in command_files:
            source = file.source.relative_to(install.ROOT).as_posix()
            target = file.target.as_posix()
            if file.platform in {"cursor", "opencode", "qoder", "trae"}:
                self.assertRegex(target, r"/commands/sd-[^/]+\.md$")
                self.assertTrue(file.source.name.startswith("sd-"), file.source)
                self.assertTrue(file.target.name.startswith("sd-"), file.target)
            else:
                self.assertIn("/commands/sd/", target)
            self.assertNotIn("/commands/trellis/", source)
            self.assertNotIn("/commands/trellis/", target)
        for file in github_prompt_files:
            self.assertTrue(file.source.name.startswith("sd-"), file.source)
            self.assertTrue(file.target.name.startswith("sd-"), file.target)

        self.assertFalse((install.ROOT / "templates/.claude/commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.cursor/commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.gemini/commands/trellis").exists())
        self.assertFalse((install.ROOT / "templates/.opencode/commands/trellis").exists())

    def test_pack_owned_scripts_use_sd_ai_command_pack_identity(self) -> None:
        raw, files = install.load_manifest()
        script_files = [
            file
            for file in files
            if file.platform == "shared" and file.kind == "script"
        ]
        script_targets = {
            file.target.as_posix()
            for file in script_files
        }
        expected_targets = {
            "scripts/sd-ai-command-pack-full-check.sh",
            "scripts/sd-ai-command-pack-shell-lib.sh",
            "scripts/sd-ai-command-pack-toolchain.sh",
            "scripts/sd-ai-command-pack-housekeeping.sh",
            "scripts/sd-ai-command-pack-review-scope.sh",
            "scripts/sd-ai-command-pack-review-preflight.mjs",
            "scripts/sd-ai-command-pack-review-local.sh",
            "scripts/sd-ai-command-pack-review-learnings.py",
            "scripts/sd-ai-command-pack-install-audit.py",
            "scripts/sd-ai-command-pack-pr-body-scope.py",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
        }
        full_check = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh"
        ).read_text(encoding="utf-8")
        housekeeping = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        ).read_text(encoding="utf-8")

        self.assertTrue(expected_targets.issubset(script_targets), script_targets)
        self.assertIn("SD AI command pack full check", full_check)
        self.assertIn("SD AI command pack housekeeping", housekeeping)


if __name__ == "__main__":
    unittest.main()
