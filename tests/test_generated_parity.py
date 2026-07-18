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


def _load_surface_generator():
    """Load the dev-side surface generator that single-sources adapter
    transform data (alias rewrites, untrusted-PR note, body overrides)."""
    module = sys.modules.get("generate_command_surfaces")
    if module is not None:
        return module
    generator_script = PACK_ROOT / ".github/scripts/generate-command-surfaces.py"
    spec = importlib.util.spec_from_file_location(
        "generate_command_surfaces", generator_script
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load generator module from {generator_script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_command_surfaces"] = module
    spec.loader.exec_module(module)
    return module


_surface_generator = _load_surface_generator()
GITHUB_UNTRUSTED_PR_NOTE = _surface_generator.GITHUB_UNTRUSTED_PR_NOTE
CLAUDE_COMMAND_ALIAS_REWRITES = _surface_generator.CLAUDE_COMMAND_ALIAS_REWRITES
BESPOKE_BODY_PARITY_EXEMPTIONS = _surface_generator.OVERRIDE_BODIES

NODE_BUILTIN_MODULES = {
    "assert",
    "buffer",
    "child_process",
    "crypto",
    "events",
    "fs",
    "fs/promises",
    "os",
    "path",
    "process",
    "stream",
    "timers",
    "url",
    "util",
}
OPENCODE_MODULE_EXTENSIONS = (".js", ".mjs", ".cjs")


def strip_js_comments(content: str) -> str:
    without_block_comments = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return "\n".join(
        line.split("//", 1)[0] for line in without_block_comments.splitlines()
    )


def collect_js_from_specifier(lines: list[str], index: int, *, stop_at_brace: bool) -> tuple[str | None, int]:
    statement = lines[index]
    from_match = re.search(r'\bfrom\s+["\']([^"\']+)["\']', statement)
    while from_match is None and index + 1 < len(lines):
        if stop_at_brace and "}" in statement:
            break
        index += 1
        statement = f"{statement}\n{lines[index]}"
        from_match = re.search(r'\bfrom\s+["\']([^"\']+)["\']', statement)
    if from_match:
        return from_match.group(1), index
    return None, index


def find_js_module_specifiers(content: str) -> list[str]:
    stripped = strip_js_comments(content)
    specifiers: list[str] = []
    lines = stripped.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped_line = line.lstrip()

        side_effect_import = re.match(
            r'^\s*import\s+["\']([^"\']+)["\']',
            line,
        )
        if side_effect_import:
            specifiers.append(side_effect_import.group(1))
            index += 1
            continue

        if stripped_line.startswith("import "):
            imported, index = collect_js_from_specifier(
                lines,
                index,
                stop_at_brace=False,
            )
            if imported:
                specifiers.append(imported)
        elif stripped_line.startswith("export *"):
            imported, index = collect_js_from_specifier(
                lines,
                index,
                stop_at_brace=False,
            )
            if imported:
                specifiers.append(imported)
        elif stripped_line.startswith("export {"):
            imported, index = collect_js_from_specifier(
                lines,
                index,
                stop_at_brace=True,
            )
            if imported:
                specifiers.append(imported)

        index += 1

    call_patterns = (
        r'\brequire\s*\(\s*["\']([^"\']+)["\']\s*\)',
        r'\bimport\s*\(\s*["\']([^"\']+)["\']\s*\)',
    )
    for pattern in call_patterns:
        specifiers.extend(re.findall(pattern, stripped, re.MULTILINE))
    return specifiers


def is_node_builtin_module(imported: str) -> bool:
    module_root = imported.split("/", 1)[0]
    return imported in NODE_BUILTIN_MODULES or module_root in NODE_BUILTIN_MODULES


def opencode_module_sources(root: Path) -> list[Path]:
    opencode_root = root / ".opencode"
    sources: list[Path] = []
    for suffix in OPENCODE_MODULE_EXTENSIONS:
        sources.extend(opencode_root.glob(f"**/*{suffix}"))
    return sorted(sources)


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
        self.assert_paths_are_files(
            root,
            [
                ".agents/skills/sd-review-pr/SKILL.md",
                ".agents/skills/sd-create-pr/SKILL.md",
                ".agents/skills/sd-work-backlog/SKILL.md",
                ".agents/skills/sd-work-designs/SKILL.md",
                ".agents/skills/sd-audit-repo/SKILL.md",
                ".agents/skills/sd-watch-pr/SKILL.md",
                ".agents/skills/sd-ship/SKILL.md",
                ".agents/skills/sd-fix-ci/SKILL.md",
                ".agents/skills/sd-update-deps/SKILL.md",
                ".agents/skills/sd-test-gaps/SKILL.md",
                ".agents/skills/sd-retro/SKILL.md",
                ".agents/skills/sd-full-check/SKILL.md",
                ".agents/skills/sd-housekeeping/SKILL.md",
                ".agents/skills/sd-continue/SKILL.md",
                ".agents/skills/sd-start/SKILL.md",
                ".agents/skills/sd-finish-work/SKILL.md",
                ".agents/skills/sd-review-learnings/SKILL.md",
                ".agents/skills/sd-review-local/SKILL.md",
                ".agents/skills/sd-update-spec/SKILL.md",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-shell-lib.sh",
                "scripts/sd-ai-command-pack-toolchain.sh",
                "scripts/sd_ai_command_pack_lib.py",
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/sd-ai-command-pack-review-scope.sh",
                "scripts/sd-ai-command-pack-review-preflight.mjs",
                "scripts/sd-ai-command-pack-review-local.sh",
                "scripts/sd-ai-command-pack-review-learnings.py",
                "scripts/sd-ai-command-pack-install-audit.py",
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                ".prism/rules.json",
                ".prism/rules.schema.json",
                ".gito/config.toml",
                ".gito/sd-ai-command-pack.env",
            ],
        )
        self.assertIn(
            "MAX_CONCURRENT_TASKS=4",
            (root / ".gito/sd-ai-command-pack.env").read_text(encoding="utf-8"),
        )
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_trellis_gitignore_block(
            (root / ".gitignore").read_text(encoding="utf-8")
        )
        self.assert_installed_targets_snapshot_matches_selection(root)
        self.assert_paths_are_files(
            root,
            [
                ".gemini/commands/sd/continue.toml",
                ".gemini/commands/sd/start.toml",
                ".gemini/commands/sd/finish-work.toml",
                ".gemini/commands/sd/create-pr.toml",
                ".gemini/commands/sd/work-backlog.toml",
                ".gemini/commands/sd/work-designs.toml",
                ".gemini/commands/sd/audit-repo.toml",
                ".gemini/commands/sd/watch-pr.toml",
                ".gemini/commands/sd/ship.toml",
                ".gemini/commands/sd/fix-ci.toml",
                ".gemini/commands/sd/update-deps.toml",
                ".gemini/commands/sd/test-gaps.toml",
                ".gemini/commands/sd/retro.toml",
                ".gemini/commands/sd/review-pr.toml",
                ".gemini/commands/sd/review-local.toml",
                ".gemini/commands/sd/review-learnings.toml",
                ".gemini/commands/sd/full-check.toml",
                ".gemini/commands/sd/housekeeping.toml",
                ".gemini/commands/sd/update-spec.toml",
                ".github/prompts/sd-continue.prompt.md",
                ".github/prompts/sd-start.prompt.md",
                ".github/prompts/sd-finish-work.prompt.md",
                ".github/prompts/sd-create-pr.prompt.md",
                ".github/prompts/sd-work-backlog.prompt.md",
                ".github/prompts/sd-work-designs.prompt.md",
                ".github/prompts/sd-audit-repo.prompt.md",
                ".github/prompts/sd-watch-pr.prompt.md",
                ".github/prompts/sd-ship.prompt.md",
                ".github/prompts/sd-fix-ci.prompt.md",
                ".github/prompts/sd-update-deps.prompt.md",
                ".github/prompts/sd-test-gaps.prompt.md",
                ".github/prompts/sd-retro.prompt.md",
                ".github/prompts/sd-review-pr.prompt.md",
                ".github/prompts/sd-review-local.prompt.md",
                ".github/prompts/sd-review-learnings.prompt.md",
                ".github/prompts/sd-full-check.prompt.md",
                ".github/prompts/sd-housekeeping.prompt.md",
                ".github/prompts/sd-update-spec.prompt.md",
            ],
        )
        copilot_instructions = root / ".github/copilot-instructions.md"
        self.assertTrue(copilot_instructions.is_file())
        self.assert_copilot_guidance_block(
            copilot_instructions.read_text(encoding="utf-8")
        )
        self.assert_paths_are_files(
            root,
            [
                ".cursor/commands/sd-continue.md",
                ".cursor/commands/sd-start.md",
                ".cursor/commands/sd-finish-work.md",
                ".cursor/commands/sd-create-pr.md",
                ".cursor/commands/sd-work-backlog.md",
                ".cursor/commands/sd-work-designs.md",
                ".cursor/commands/sd-audit-repo.md",
                ".cursor/commands/sd-watch-pr.md",
                ".cursor/commands/sd-ship.md",
                ".cursor/commands/sd-fix-ci.md",
                ".cursor/commands/sd-update-deps.md",
                ".cursor/commands/sd-test-gaps.md",
                ".cursor/commands/sd-retro.md",
                ".cursor/commands/sd-review-pr.md",
                ".cursor/commands/sd-review-local.md",
                ".cursor/commands/sd-review-learnings.md",
                ".cursor/commands/sd-full-check.md",
                ".cursor/commands/sd-housekeeping.md",
                ".cursor/commands/sd-update-spec.md",
            ],
        )
        self.assert_paths_absent(
            root,
            [
                ".claude/commands/sd/continue.md",
                ".claude/commands/sd/start.md",
                ".claude/commands/sd/finish-work.md",
                ".claude/commands/sd/create-pr.md",
                ".claude/commands/sd/work-backlog.md",
                ".claude/commands/sd/work-designs.md",
                ".claude/commands/sd/audit-repo.md",
                ".claude/commands/sd/watch-pr.md",
                ".claude/commands/sd/ship.md",
                ".claude/commands/sd/fix-ci.md",
                ".claude/commands/sd/update-deps.md",
                ".claude/commands/sd/fleet-refresh.md",
                ".claude/commands/sd/test-gaps.md",
                ".claude/commands/sd/retro.md",
                ".claude/commands/sd/review-pr.md",
                ".claude/commands/sd/review-local.md",
                ".claude/commands/sd/review-learnings.md",
                ".claude/commands/sd/full-check.md",
                ".claude/commands/sd/housekeeping.md",
                ".claude/commands/sd/update-spec.md",
                ".opencode/commands/sd-continue.md",
                ".opencode/commands/sd-start.md",
                ".opencode/commands/sd-finish-work.md",
                ".opencode/commands/sd-create-pr.md",
                ".opencode/commands/sd-work-backlog.md",
                ".opencode/commands/sd-work-designs.md",
                ".opencode/commands/sd-audit-repo.md",
                ".opencode/commands/sd-watch-pr.md",
                ".opencode/commands/sd-ship.md",
                ".opencode/commands/sd-fix-ci.md",
                ".opencode/commands/sd-update-deps.md",
                ".opencode/commands/sd-fleet-refresh.md",
                ".opencode/commands/sd-test-gaps.md",
                ".opencode/commands/sd-retro.md",
                ".opencode/commands/sd-review-pr.md",
                ".opencode/commands/sd-review-local.md",
                ".opencode/commands/sd-review-learnings.md",
                ".opencode/commands/sd-full-check.md",
                ".opencode/commands/sd-housekeeping.md",
                ".opencode/commands/sd-update-spec.md",
            ],
        )

    def test_installs_newer_trellis_platform_adapters_when_active(self) -> None:
        root = self.make_repo(".kiro", ".reasonix", ".trae", ".zcode")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assert_paths_are_files(
            root,
            [
                ".kiro/skills/sd-review-pr/SKILL.md",
                ".kiro/skills/sd-create-pr/SKILL.md",
                ".kiro/skills/sd-work-backlog/SKILL.md",
                ".kiro/skills/sd-work-designs/SKILL.md",
                ".kiro/skills/sd-audit-repo/SKILL.md",
                ".kiro/skills/sd-watch-pr/SKILL.md",
                ".kiro/skills/sd-ship/SKILL.md",
                ".kiro/skills/sd-fix-ci/SKILL.md",
                ".kiro/skills/sd-update-deps/SKILL.md",
                ".kiro/skills/sd-test-gaps/SKILL.md",
                ".kiro/skills/sd-retro/SKILL.md",
                ".reasonix/skills/sd-review-pr/SKILL.md",
                ".reasonix/skills/sd-create-pr/SKILL.md",
                ".reasonix/skills/sd-work-backlog/SKILL.md",
                ".reasonix/skills/sd-work-designs/SKILL.md",
                ".reasonix/skills/sd-audit-repo/SKILL.md",
                ".reasonix/skills/sd-watch-pr/SKILL.md",
                ".reasonix/skills/sd-ship/SKILL.md",
                ".reasonix/skills/sd-fix-ci/SKILL.md",
                ".reasonix/skills/sd-update-deps/SKILL.md",
                ".reasonix/skills/sd-test-gaps/SKILL.md",
                ".reasonix/skills/sd-retro/SKILL.md",
                ".trae/commands/sd-review-pr.md",
                ".trae/commands/sd-create-pr.md",
                ".trae/commands/sd-work-backlog.md",
                ".trae/commands/sd-work-designs.md",
                ".trae/commands/sd-audit-repo.md",
                ".trae/commands/sd-watch-pr.md",
                ".trae/commands/sd-ship.md",
                ".trae/commands/sd-fix-ci.md",
                ".trae/commands/sd-update-deps.md",
                ".trae/commands/sd-test-gaps.md",
                ".trae/commands/sd-retro.md",
                ".trae/skills/sd-review-pr/SKILL.md",
                ".trae/skills/sd-create-pr/SKILL.md",
                ".trae/skills/sd-work-backlog/SKILL.md",
                ".trae/skills/sd-work-designs/SKILL.md",
                ".trae/skills/sd-audit-repo/SKILL.md",
                ".trae/skills/sd-watch-pr/SKILL.md",
                ".trae/skills/sd-ship/SKILL.md",
                ".trae/skills/sd-fix-ci/SKILL.md",
                ".trae/skills/sd-update-deps/SKILL.md",
                ".trae/skills/sd-test-gaps/SKILL.md",
                ".trae/skills/sd-retro/SKILL.md",
                ".zcode/commands/sd/review-pr.md",
                ".zcode/commands/sd/create-pr.md",
                ".zcode/commands/sd/work-backlog.md",
                ".zcode/commands/sd/work-designs.md",
                ".zcode/commands/sd/audit-repo.md",
                ".zcode/commands/sd/watch-pr.md",
                ".zcode/commands/sd/ship.md",
                ".zcode/commands/sd/fix-ci.md",
                ".zcode/commands/sd/update-deps.md",
                ".zcode/commands/sd/test-gaps.md",
                ".zcode/commands/sd/retro.md",
            ],
        )
        self.assertFalse((root / ".qoder/commands/sd-review-pr.md").exists())
        self.assert_installed_targets_snapshot_matches_selection(root)

    def test_all_installs_every_adapter_without_anchors(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--all")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assert_paths_are_files(
            root,
            [
                ".agents/skills/sd-start/SKILL.md",
                ".agents/skills/sd-create-pr/SKILL.md",
                ".agents/skills/sd-work-backlog/SKILL.md",
                ".agents/skills/sd-work-designs/SKILL.md",
                ".agents/skills/sd-audit-repo/SKILL.md",
                ".agents/skills/sd-watch-pr/SKILL.md",
                ".agents/skills/sd-ship/SKILL.md",
                ".agents/skills/sd-fix-ci/SKILL.md",
                ".agents/skills/sd-update-deps/SKILL.md",
                ".agents/skills/sd-test-gaps/SKILL.md",
                ".agents/skills/sd-retro/SKILL.md",
                ".agents/skills/sd-review-pr/SKILL.md",
                ".agents/skills/sd-review-local/SKILL.md",
                ".agents/skills/sd-review-learnings/SKILL.md",
                ".agents/skills/sd-full-check/SKILL.md",
                ".agents/skills/sd-housekeeping/SKILL.md",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-toolchain.sh",
                "scripts/sd_ai_command_pack_lib.py",
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/sd-ai-command-pack-review-scope.sh",
                "scripts/sd-ai-command-pack-review-preflight.mjs",
                "scripts/sd-ai-command-pack-review-local.sh",
                "scripts/sd-ai-command-pack-review-learnings.py",
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                ".prism/rules.json",
                "docs/SD_AI_COMMAND_PACK.md",
            ],
        )
        self.assert_installed_targets_snapshot_matches_selection(
            root,
            install_all=True,
        )
        self.assert_paths_are_files(
            root,
            [
                ".claude/commands/sd/continue.md",
                ".claude/commands/sd/start.md",
                ".claude/commands/sd/finish-work.md",
                ".claude/commands/sd/create-pr.md",
                ".claude/commands/sd/work-backlog.md",
                ".claude/commands/sd/work-designs.md",
                ".claude/commands/sd/audit-repo.md",
                ".claude/commands/sd/watch-pr.md",
                ".claude/commands/sd/ship.md",
                ".claude/commands/sd/fix-ci.md",
                ".claude/commands/sd/update-deps.md",
                ".claude/commands/sd/test-gaps.md",
                ".claude/commands/sd/retro.md",
                ".claude/commands/sd/review-pr.md",
                ".claude/commands/sd/review-local.md",
                ".claude/commands/sd/review-learnings.md",
                ".claude/commands/sd/full-check.md",
                ".claude/commands/sd/housekeeping.md",
                ".claude/commands/sd/update-spec.md",
                ".cursor/commands/sd-continue.md",
                ".cursor/commands/sd-start.md",
                ".cursor/commands/sd-finish-work.md",
                ".cursor/commands/sd-create-pr.md",
                ".cursor/commands/sd-work-backlog.md",
                ".cursor/commands/sd-work-designs.md",
                ".cursor/commands/sd-audit-repo.md",
                ".cursor/commands/sd-watch-pr.md",
                ".cursor/commands/sd-ship.md",
                ".cursor/commands/sd-fix-ci.md",
                ".cursor/commands/sd-update-deps.md",
                ".cursor/commands/sd-test-gaps.md",
                ".cursor/commands/sd-retro.md",
                ".cursor/commands/sd-review-pr.md",
                ".cursor/commands/sd-review-local.md",
                ".cursor/commands/sd-review-learnings.md",
                ".cursor/commands/sd-full-check.md",
                ".cursor/commands/sd-housekeeping.md",
                ".cursor/commands/sd-update-spec.md",
                ".gemini/commands/sd/continue.toml",
                ".gemini/commands/sd/start.toml",
                ".gemini/commands/sd/finish-work.toml",
                ".gemini/commands/sd/create-pr.toml",
                ".gemini/commands/sd/work-backlog.toml",
                ".gemini/commands/sd/work-designs.toml",
                ".gemini/commands/sd/audit-repo.toml",
                ".gemini/commands/sd/watch-pr.toml",
                ".gemini/commands/sd/ship.toml",
                ".gemini/commands/sd/fix-ci.toml",
                ".gemini/commands/sd/update-deps.toml",
                ".gemini/commands/sd/test-gaps.toml",
                ".gemini/commands/sd/retro.toml",
                ".gemini/commands/sd/review-pr.toml",
                ".gemini/commands/sd/review-local.toml",
                ".gemini/commands/sd/review-learnings.toml",
                ".gemini/commands/sd/full-check.toml",
                ".gemini/commands/sd/housekeeping.toml",
                ".gemini/commands/sd/update-spec.toml",
                ".github/prompts/sd-continue.prompt.md",
                ".github/prompts/sd-start.prompt.md",
                ".github/prompts/sd-finish-work.prompt.md",
                ".github/prompts/sd-create-pr.prompt.md",
                ".github/prompts/sd-work-backlog.prompt.md",
                ".github/prompts/sd-work-designs.prompt.md",
                ".github/prompts/sd-audit-repo.prompt.md",
                ".github/prompts/sd-watch-pr.prompt.md",
                ".github/prompts/sd-ship.prompt.md",
                ".github/prompts/sd-fix-ci.prompt.md",
                ".github/prompts/sd-update-deps.prompt.md",
                ".github/prompts/sd-test-gaps.prompt.md",
                ".github/prompts/sd-retro.prompt.md",
                ".github/prompts/sd-review-pr.prompt.md",
                ".github/prompts/sd-review-local.prompt.md",
                ".github/prompts/sd-review-learnings.prompt.md",
                ".github/prompts/sd-full-check.prompt.md",
                ".github/prompts/sd-housekeeping.prompt.md",
                ".github/prompts/sd-update-spec.prompt.md",
            ],
        )
        copilot_instructions = root / ".github/copilot-instructions.md"
        self.assertTrue(copilot_instructions.is_file())
        self.assert_copilot_guidance_block(
            copilot_instructions.read_text(encoding="utf-8")
        )
        self.assert_paths_are_files(
            root,
            [
                ".opencode/commands/sd-continue.md",
                ".opencode/commands/sd-start.md",
                ".opencode/commands/sd-finish-work.md",
                ".opencode/commands/sd-create-pr.md",
                ".opencode/commands/sd-work-backlog.md",
                ".opencode/commands/sd-work-designs.md",
                ".opencode/commands/sd-audit-repo.md",
                ".opencode/commands/sd-watch-pr.md",
                ".opencode/commands/sd-ship.md",
                ".opencode/commands/sd-fix-ci.md",
                ".opencode/commands/sd-update-deps.md",
                ".opencode/commands/sd-test-gaps.md",
                ".opencode/commands/sd-retro.md",
                ".opencode/commands/sd-review-pr.md",
                ".opencode/commands/sd-review-local.md",
                ".opencode/commands/sd-review-learnings.md",
                ".opencode/commands/sd-full-check.md",
                ".opencode/commands/sd-housekeeping.md",
                ".opencode/commands/sd-update-spec.md",
            ],
        )

    def test_installed_adapters_can_resolve_shared_skill(self) -> None:
        root = self.make_repo(".claude", ".cursor", ".gemini", ".github", ".opencode")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assert_paths_are_files(
            root,
            [
                ".agents/skills/sd-review-pr/SKILL.md",
                ".agents/skills/sd-create-pr/SKILL.md",
                ".agents/skills/sd-work-backlog/SKILL.md",
                ".agents/skills/sd-work-designs/SKILL.md",
                ".agents/skills/sd-audit-repo/SKILL.md",
                ".agents/skills/sd-watch-pr/SKILL.md",
                ".agents/skills/sd-ship/SKILL.md",
                ".agents/skills/sd-fix-ci/SKILL.md",
                ".agents/skills/sd-update-deps/SKILL.md",
                ".agents/skills/sd-test-gaps/SKILL.md",
                ".agents/skills/sd-retro/SKILL.md",
                ".agents/skills/sd-review-local/SKILL.md",
                ".agents/skills/sd-review-learnings/SKILL.md",
                ".agents/skills/sd-full-check/SKILL.md",
                ".agents/skills/sd-housekeeping/SKILL.md",
                "scripts/sd-ai-command-pack-review-local.sh",
                "scripts/sd-ai-command-pack-review-learnings.py",
                "scripts/sd_ai_command_pack_lib.py",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-housekeeping.sh",
            ],
        )
        claude_start = root / ".claude/commands/sd/start.md"
        self.assertTrue(claude_start.is_file(), claude_start)
        claude_start_content = claude_start.read_text(encoding="utf-8")
        self.assertIn("installs no `trellis-start` skill", claude_start_content)
        self.assertIn("./.trellis/scripts/get_context.py", claude_start_content)
        adapter_expectations: list[tuple[list[Path], list[str], list[str]]] = [
            (
                [
                    root / ".cursor/commands/sd-start.md",
                    root / ".gemini/commands/sd/start.toml",
                    root / ".github/prompts/sd-start.prompt.md",
                    root / ".opencode/commands/sd-start.md",
                ],
                ["Resolve the `trellis-start` skill by name"],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/continue.md",
                    root / ".cursor/commands/sd-continue.md",
                    root / ".gemini/commands/sd/continue.toml",
                    root / ".github/prompts/sd-continue.prompt.md",
                    root / ".opencode/commands/sd-continue.md",
                ],
                ["Resolve the `trellis-continue` skill by name"],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/finish-work.md",
                    root / ".cursor/commands/sd-finish-work.md",
                    root / ".gemini/commands/sd/finish-work.toml",
                    root / ".github/prompts/sd-finish-work.prompt.md",
                    root / ".opencode/commands/sd-finish-work.md",
                ],
                ["Resolve the `trellis-finish-work` skill by name"],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/create-pr.md",
                    root / ".cursor/commands/sd-create-pr.md",
                    root / ".gemini/commands/sd/create-pr.toml",
                    root / ".github/prompts/sd-create-pr.prompt.md",
                    root / ".opencode/commands/sd-create-pr.md",
                ],
                [
                    "Resolve the `sd-create-pr` skill by name",
                    "sd-update-spec",
                    "sd-review-pr",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/work-backlog.md",
                    root / ".cursor/commands/sd-work-backlog.md",
                    root / ".gemini/commands/sd/work-backlog.toml",
                    root / ".github/prompts/sd-work-backlog.prompt.md",
                    root / ".opencode/commands/sd-work-backlog.md",
                ],
                [
                    "Resolve the `sd-work-backlog` skill by name",
                    "one task per iteration",
                    "sd-create-pr",
                    "sd-housekeeping",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/work-designs.md",
                    root / ".cursor/commands/sd-work-designs.md",
                    root / ".gemini/commands/sd/work-designs.toml",
                    root / ".github/prompts/sd-work-designs.prompt.md",
                    root / ".opencode/commands/sd-work-designs.md",
                ],
                [
                    "Resolve the `sd-work-designs` skill by name",
                    "design.md",
                    "implement.md",
                    "numbered list",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/audit-repo.md",
                    root / ".cursor/commands/sd-audit-repo.md",
                    root / ".gemini/commands/sd/audit-repo.toml",
                    root / ".github/prompts/sd-audit-repo.prompt.md",
                    root / ".opencode/commands/sd-audit-repo.md",
                ],
                [
                    "Resolve the `sd-audit-repo` skill by name",
                    ".agents/skills/sd-audit-repo/charters/",
                    ".trellis/audit/ledger.md",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/watch-pr.md",
                    root / ".cursor/commands/sd-watch-pr.md",
                    root / ".gemini/commands/sd/watch-pr.toml",
                    root / ".github/prompts/sd-watch-pr.prompt.md",
                    root / ".opencode/commands/sd-watch-pr.md",
                ],
                [
                    "Resolve the `sd-watch-pr` skill by name",
                    "sd-housekeeping",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/fix-ci.md",
                    root / ".cursor/commands/sd-fix-ci.md",
                    root / ".gemini/commands/sd/fix-ci.toml",
                    root / ".github/prompts/sd-fix-ci.prompt.md",
                    root / ".opencode/commands/sd-fix-ci.md",
                ],
                [
                    "Resolve the `sd-fix-ci` skill by name",
                    "weaken tests",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/update-deps.md",
                    root / ".cursor/commands/sd-update-deps.md",
                    root / ".gemini/commands/sd/update-deps.toml",
                    root / ".github/prompts/sd-update-deps.prompt.md",
                    root / ".opencode/commands/sd-update-deps.md",
                ],
                [
                    "Resolve the `sd-update-deps` skill by name",
                    "Majors are always manual",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/test-gaps.md",
                    root / ".cursor/commands/sd-test-gaps.md",
                    root / ".gemini/commands/sd/test-gaps.toml",
                    root / ".github/prompts/sd-test-gaps.prompt.md",
                    root / ".opencode/commands/sd-test-gaps.md",
                ],
                [
                    "Resolve the `sd-test-gaps` skill by name",
                    "test files and fixtures only",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/retro.md",
                    root / ".cursor/commands/sd-retro.md",
                    root / ".gemini/commands/sd/retro.toml",
                    root / ".github/prompts/sd-retro.prompt.md",
                    root / ".opencode/commands/sd-retro.md",
                ],
                [
                    "Resolve the `sd-retro` skill by name",
                    "explicit user consent",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/review-pr.md",
                    root / ".cursor/commands/sd-review-pr.md",
                    root / ".gemini/commands/sd/review-pr.toml",
                    root / ".github/prompts/sd-review-pr.prompt.md",
                    root / ".opencode/commands/sd-review-pr.md",
                ],
                ["Resolve the `sd-review-pr` skill by name"],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/review-local.md",
                    root / ".cursor/commands/sd-review-local.md",
                    root / ".gemini/commands/sd/review-local.toml",
                    root / ".github/prompts/sd-review-local.prompt.md",
                    root / ".opencode/commands/sd-review-local.md",
                ],
                [
                    "Resolve the `sd-review-local` skill by name",
                    "scripts/sd-ai-command-pack-review-local.sh",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/ship.md",
                    root / ".cursor/commands/sd-ship.md",
                    root / ".gemini/commands/sd/ship.toml",
                    root / ".github/prompts/sd-ship.prompt.md",
                    root / ".opencode/commands/sd-ship.md",
                ],
                [
                    "Resolve the `sd-ship` skill by name",
                    "adds no new gate logic; every stage's own gates remain "
                    "authoritative",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/review-learnings.md",
                    root / ".cursor/commands/sd-review-learnings.md",
                    root / ".gemini/commands/sd/review-learnings.toml",
                    root / ".github/prompts/sd-review-learnings.prompt.md",
                    root / ".opencode/commands/sd-review-learnings.md",
                ],
                [
                    "Resolve the `sd-review-learnings` skill by name",
                    "scripts/sd-ai-command-pack-review-learnings.py",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/full-check.md",
                    root / ".cursor/commands/sd-full-check.md",
                    root / ".gemini/commands/sd/full-check.toml",
                    root / ".github/prompts/sd-full-check.prompt.md",
                    root / ".opencode/commands/sd-full-check.md",
                ],
                [
                    "Resolve the `sd-full-check` skill by name",
                    "source of truth for the exact checks",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/housekeeping.md",
                    root / ".cursor/commands/sd-housekeeping.md",
                    root / ".gemini/commands/sd/housekeeping.toml",
                    root / ".github/prompts/sd-housekeeping.prompt.md",
                    root / ".opencode/commands/sd-housekeeping.md",
                ],
                [
                    "Resolve the `sd-housekeeping` skill by name",
                    "scripts/sd-ai-command-pack-housekeeping.sh",
                ],
                [],
            ),
            (
                [
                    root / ".claude/commands/sd/update-spec.md",
                    root / ".cursor/commands/sd-update-spec.md",
                    root / ".gemini/commands/sd/update-spec.toml",
                    root / ".github/prompts/sd-update-spec.prompt.md",
                    root / ".opencode/commands/sd-update-spec.md",
                ],
                [
                    "Resolve the `sd-update-spec` skill by name",
                    "source of truth for Trellis update-spec delegation",
                ],
                ["Trellis " + "update-spec first"],
            ),
        ]
        for adapters, present, absent in adapter_expectations:
            for adapter in adapters:
                with self.subTest(adapter=adapter):
                    self.assertTrue(adapter.is_file(), adapter)
                    content = adapter.read_text(encoding="utf-8")
                    for phrase in present:
                        self.assertIn(phrase, content)
                    for phrase in absent:
                        self.assertNotIn(phrase, content)

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
            "### sd-help",
            "### sd-start",
            "### sd-create-pr",
            "### sd-work-backlog",
            "### sd-work-designs",
            "### sd-audit-repo",
            "### sd-watch-pr",
            "### sd-ship",
            "### sd-fix-ci",
            "### sd-update-deps",
            "### sd-fleet-refresh",
            "### sd-test-gaps",
            "### sd-retro",
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
            "needs: [unittest, lint, security, release-payload-gate, main-push-scope]",
            "RELEASE_PAYLOAD_GATE_RESULT",
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
            "bash .github/scripts/run-tests.sh",
            "python3 -m coverage combine",
            'python3 -m coverage report --include="install.py,installer/*"'
            " --fail-under=100",
            "bash .github/scripts/check-shipped-script-coverage.sh",
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
            "bash .github/scripts/run-tests.sh",
            "python -m coverage combine",
            'python -m coverage report --include="install.py,installer/*"'
            " --fail-under=100",
            "PYTHON_BIN=python bash .github/scripts/check-shipped-script-coverage.sh",
        ):
            self.assertIn(expected, readme)
        coverage_gate = (
            PACK_ROOT / ".github/scripts/check-shipped-script-coverage.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '--include="scripts/sd-ai-command-pack-*.py,scripts/sd_ai_command_pack_lib.py,scripts/sd_ai_command_pack_fleet_lib.py"',
            coverage_gate,
        )
        self.assertIn("--fail-under=76", coverage_gate)
        self.assertIn(
            "scripts/sd-ai-command-pack-fleet-candidate-check.py 90",
            coverage_gate,
        )
        self.assertIn(
            "scripts/sd_ai_command_pack_fleet_lib.py 90",
            coverage_gate,
        )
        # The parallel test runner owns the coverage rig contract that used to
        # live inline in the workflow/README: the absolute coverage env plus
        # per-module --parallel-mode sharding.
        runner = (
            PACK_ROOT / ".github/scripts/run-tests.sh"
        ).read_text(encoding="utf-8")
        for expected in (
            'COVERAGE_PROCESS_START="$REPO_ROOT/.coveragerc"',
            'COVERAGE_FILE="$REPO_ROOT/.coverage"',
            "tests/coverage_sitecustomize",
            "coverage run --parallel-mode -m unittest",
        ):
            self.assertIn(expected, runner)

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
                "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
            ),
            6,
        )
        self.assertEqual(
            workflow.count(
                "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
            ),
            3,
        )
        self.assertIn("main-push-scope:", workflow)
        self.assertIn("release-payload-gate:", workflow)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF", workflow)
        self.assertIn("run_pack_source_drift_gates", workflow)
        self.assertIn('"${{ github.event.before }}" "${{ github.sha }}"', workflow)
        self.assertIn("git diff --no-renames --name-only -z", main_push_guard)
        self.assertIn(
            ".trellis/tasks/*|.trellis/workspace/*|.trellis/audit/*",
            main_push_guard,
        )

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
            "Do not track `.opencode/package.json` or any `.opencode` Bun lockfile",
            "cd .opencode",
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

    def test_opencode_plugins_do_not_require_local_dependency_manifest(
        self,
    ) -> None:
        opencode_package_path = PACK_ROOT / ".opencode/package.json"
        opencode_lock_paths = (
            PACK_ROOT / ".opencode/bun.lock",
            PACK_ROOT / ".opencode/bun.lockb",
        )

        self.assertFalse(
            opencode_package_path.exists(),
            ".opencode/package.json is only needed when plugins import packages",
        )
        for lock_path in opencode_lock_paths:
            self.assertFalse(
                lock_path.exists(),
                f"{lock_path.relative_to(PACK_ROOT)} should not be tracked "
                "without package deps",
            )

        external_imports: list[str] = []
        for source in opencode_module_sources(PACK_ROOT):
            text = source.read_text(encoding="utf-8")
            for imported in find_js_module_specifiers(text):
                if not imported.startswith((".", "/", "node:")) and not is_node_builtin_module(
                    imported
                ):
                    external_imports.append(
                        f"{source.relative_to(PACK_ROOT)} imports {imported}"
                    )

        self.assertEqual([], external_imports)

    def test_opencode_dependency_scan_covers_common_module_forms(self) -> None:
        specifiers = find_js_module_specifiers(
            """
            import fs from "fs"
            import sibling from "./sibling.js"
            import {
                value,
            } from "external-multiline"
            import "external-side-effect"
            export { value } from "external-reexport"
            export {
                value,
            } from "external-reexport-multiline"
            export default function plugin() {}
            import later from "external-after-default"
            export { localValue }
            import afterLocalExport from "external-after-local-export"
            const required = require("external-require")
            const dynamic = await import("external-dynamic")
            // require("ignored-comment")
            /* import "ignored-block-comment" */
            """
        )

        self.assertEqual(
            [
                "fs",
                "./sibling.js",
                "external-multiline",
                "external-side-effect",
                "external-reexport",
                "external-reexport-multiline",
                "external-after-default",
                "external-after-local-export",
                "external-require",
                "external-dynamic",
            ],
            specifiers,
        )

    def test_opencode_dependency_scan_covers_module_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            opencode_root = root / ".opencode"
            opencode_root.mkdir()
            for filename in ("plugin.js", "tool.mjs", "helper.cjs", "ignored.ts"):
                (opencode_root / filename).write_text("", encoding="utf-8")

            self.assertEqual(
                [
                    opencode_root / "helper.cjs",
                    opencode_root / "plugin.js",
                    opencode_root / "tool.mjs",
                ],
                opencode_module_sources(root),
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
            "numbered `Next Steps` section",
            "even on a verification-only",
            "open follow-up items from the session",
            "high-value Trellis task candidates",
            "roadmap items to start next",
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
            "scripts/sd_ai_command_pack_lib.py",
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

    def test_source_only_command_is_generated_but_not_consumer_shipped(
        self,
    ) -> None:
        self.assertEqual(
            install.SOURCE_ONLY_COMMAND_NAMES,
            frozenset({"sd-fleet-refresh"}),
        )
        _, files = install.load_manifest()
        manifest_targets = {file.target.as_posix() for file in files}

        self.assertTrue(
            set(install.SOURCE_ONLY_COMMAND_TARGETS).isdisjoint(manifest_targets)
        )
        for path in (
            "templates/.agents/skills/sd-fleet-refresh/SKILL.md",
            "templates/.commands/sd-fleet-refresh.md",
            "templates/.claude/commands/sd/fleet-refresh.md",
            "templates/.gemini/commands/sd/fleet-refresh.toml",
            "templates/.github/prompts/sd-fleet-refresh.prompt.md",
            ".agents/skills/sd-fleet-refresh/SKILL.md",
            ".claude/commands/sd/fleet-refresh.md",
            ".gemini/commands/sd/fleet-refresh.toml",
            ".github/prompts/sd-fleet-refresh.prompt.md",
        ):
            with self.subTest(path=path):
                self.assertTrue((install.ROOT / path).is_file(), path)

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
            ".agent/workflows/sd-audit-repo.md",
            ".agent/workflows/sd-watch-pr.md",
            ".agent/workflows/sd-ship.md",
            ".agent/workflows/sd-fix-ci.md",
            ".agent/workflows/sd-update-deps.md",
            ".agent/workflows/sd-test-gaps.md",
            ".agent/workflows/sd-retro.md",
            ".agent/skills/sd-review-pr/SKILL.md",
            ".agent/skills/sd-create-pr/SKILL.md",
            ".agent/skills/sd-work-backlog/SKILL.md",
            ".agent/skills/sd-work-designs/SKILL.md",
            ".agent/skills/sd-audit-repo/SKILL.md",
            ".agent/skills/sd-watch-pr/SKILL.md",
            ".agent/skills/sd-ship/SKILL.md",
            ".agent/skills/sd-fix-ci/SKILL.md",
            ".agent/skills/sd-update-deps/SKILL.md",
            ".agent/skills/sd-test-gaps/SKILL.md",
            ".agent/skills/sd-retro/SKILL.md",
            ".codebuddy/commands/sd/review-pr.md",
            ".codebuddy/commands/sd/create-pr.md",
            ".codebuddy/commands/sd/work-backlog.md",
            ".codebuddy/commands/sd/work-designs.md",
            ".codebuddy/commands/sd/audit-repo.md",
            ".codebuddy/commands/sd/watch-pr.md",
            ".codebuddy/commands/sd/ship.md",
            ".codebuddy/commands/sd/fix-ci.md",
            ".codebuddy/commands/sd/update-deps.md",
            ".codebuddy/commands/sd/test-gaps.md",
            ".codebuddy/commands/sd/retro.md",
            ".codebuddy/skills/sd-review-pr/SKILL.md",
            ".codebuddy/skills/sd-create-pr/SKILL.md",
            ".codebuddy/skills/sd-work-backlog/SKILL.md",
            ".codebuddy/skills/sd-work-designs/SKILL.md",
            ".codebuddy/skills/sd-audit-repo/SKILL.md",
            ".codebuddy/skills/sd-watch-pr/SKILL.md",
            ".codebuddy/skills/sd-ship/SKILL.md",
            ".codebuddy/skills/sd-fix-ci/SKILL.md",
            ".codebuddy/skills/sd-update-deps/SKILL.md",
            ".codebuddy/skills/sd-test-gaps/SKILL.md",
            ".codebuddy/skills/sd-retro/SKILL.md",
            ".devin/workflows/sd-review-pr.md",
            ".devin/workflows/sd-create-pr.md",
            ".devin/workflows/sd-work-backlog.md",
            ".devin/workflows/sd-work-designs.md",
            ".devin/workflows/sd-audit-repo.md",
            ".devin/workflows/sd-watch-pr.md",
            ".devin/workflows/sd-ship.md",
            ".devin/workflows/sd-fix-ci.md",
            ".devin/workflows/sd-update-deps.md",
            ".devin/workflows/sd-test-gaps.md",
            ".devin/workflows/sd-retro.md",
            ".factory/commands/sd/review-pr.md",
            ".factory/commands/sd/create-pr.md",
            ".factory/commands/sd/work-backlog.md",
            ".factory/commands/sd/work-designs.md",
            ".factory/commands/sd/audit-repo.md",
            ".factory/commands/sd/watch-pr.md",
            ".factory/commands/sd/ship.md",
            ".factory/commands/sd/fix-ci.md",
            ".factory/commands/sd/update-deps.md",
            ".factory/commands/sd/test-gaps.md",
            ".factory/commands/sd/retro.md",
            ".kilocode/workflows/sd-review-pr.md",
            ".kilocode/workflows/sd-create-pr.md",
            ".kilocode/workflows/sd-work-backlog.md",
            ".kilocode/workflows/sd-work-designs.md",
            ".kilocode/workflows/sd-audit-repo.md",
            ".kilocode/workflows/sd-watch-pr.md",
            ".kilocode/workflows/sd-ship.md",
            ".kilocode/workflows/sd-fix-ci.md",
            ".kilocode/workflows/sd-update-deps.md",
            ".kilocode/workflows/sd-test-gaps.md",
            ".kilocode/workflows/sd-retro.md",
            ".kiro/skills/sd-review-pr/SKILL.md",
            ".kiro/skills/sd-create-pr/SKILL.md",
            ".kiro/skills/sd-work-backlog/SKILL.md",
            ".kiro/skills/sd-work-designs/SKILL.md",
            ".kiro/skills/sd-audit-repo/SKILL.md",
            ".kiro/skills/sd-watch-pr/SKILL.md",
            ".kiro/skills/sd-ship/SKILL.md",
            ".kiro/skills/sd-fix-ci/SKILL.md",
            ".kiro/skills/sd-update-deps/SKILL.md",
            ".kiro/skills/sd-test-gaps/SKILL.md",
            ".kiro/skills/sd-retro/SKILL.md",
            ".pi/prompts/sd-review-pr.md",
            ".pi/prompts/sd-create-pr.md",
            ".pi/prompts/sd-work-backlog.md",
            ".pi/prompts/sd-work-designs.md",
            ".pi/prompts/sd-audit-repo.md",
            ".pi/prompts/sd-watch-pr.md",
            ".pi/prompts/sd-ship.md",
            ".pi/prompts/sd-fix-ci.md",
            ".pi/prompts/sd-update-deps.md",
            ".pi/prompts/sd-test-gaps.md",
            ".pi/prompts/sd-retro.md",
            ".qoder/commands/sd-review-pr.md",
            ".qoder/commands/sd-create-pr.md",
            ".qoder/commands/sd-work-backlog.md",
            ".qoder/commands/sd-work-designs.md",
            ".qoder/commands/sd-audit-repo.md",
            ".qoder/commands/sd-watch-pr.md",
            ".qoder/commands/sd-ship.md",
            ".qoder/commands/sd-fix-ci.md",
            ".qoder/commands/sd-update-deps.md",
            ".qoder/commands/sd-test-gaps.md",
            ".qoder/commands/sd-retro.md",
            ".reasonix/skills/sd-review-pr/SKILL.md",
            ".reasonix/skills/sd-create-pr/SKILL.md",
            ".reasonix/skills/sd-work-backlog/SKILL.md",
            ".reasonix/skills/sd-work-designs/SKILL.md",
            ".reasonix/skills/sd-audit-repo/SKILL.md",
            ".reasonix/skills/sd-watch-pr/SKILL.md",
            ".reasonix/skills/sd-ship/SKILL.md",
            ".reasonix/skills/sd-fix-ci/SKILL.md",
            ".reasonix/skills/sd-update-deps/SKILL.md",
            ".reasonix/skills/sd-test-gaps/SKILL.md",
            ".reasonix/skills/sd-retro/SKILL.md",
            ".trae/commands/sd-review-pr.md",
            ".trae/commands/sd-create-pr.md",
            ".trae/commands/sd-work-backlog.md",
            ".trae/commands/sd-work-designs.md",
            ".trae/commands/sd-audit-repo.md",
            ".trae/commands/sd-watch-pr.md",
            ".trae/commands/sd-ship.md",
            ".trae/commands/sd-fix-ci.md",
            ".trae/commands/sd-update-deps.md",
            ".trae/commands/sd-test-gaps.md",
            ".trae/commands/sd-retro.md",
            ".zcode/commands/sd/review-pr.md",
            ".zcode/commands/sd/create-pr.md",
            ".zcode/commands/sd/work-backlog.md",
            ".zcode/commands/sd/work-designs.md",
            ".zcode/commands/sd/audit-repo.md",
            ".zcode/commands/sd/watch-pr.md",
            ".zcode/commands/sd/ship.md",
            ".zcode/commands/sd/fix-ci.md",
            ".zcode/commands/sd/update-deps.md",
            ".zcode/commands/sd/test-gaps.md",
            ".zcode/commands/sd/retro.md",
        }
        actual_targets = {file.target.as_posix() for file in files}
        self.assertTrue(expected_targets.issubset(actual_targets))

    def test_adapters_reference_installed_shared_assets(self) -> None:
        _, files = install.load_manifest()
        adapter_files = [file for file in files if file.kind in {"command", "prompt"}]

        self.assertGreater(len(adapter_files), 0)
        for file in adapter_files:
            content = file.source.read_text(encoding="utf-8")
            if "help" in file.target.name:
                self.assertIn("Resolve the `sd-help` skill by name", content)
                self.assertIn("references/command-catalog.md", content)
                self.assertIn("separate explicit request", content)
            elif "start" in file.target.name:
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
            elif "audit-repo" in file.target.name:
                self.assertIn("Resolve the `sd-audit-repo` skill by name", content)
                self.assertIn(".agents/skills/sd-audit-repo/charters/", content)
                self.assertIn(".trellis/audit/ledger.md", content)
                self.assertIn("explicit user consent", content)
            elif "watch-pr" in file.target.name:
                self.assertIn("Resolve the `sd-watch-pr` skill by name", content)
                self.assertIn("sd-housekeeping", content)
            elif "fix-ci" in file.target.name:
                self.assertIn("Resolve the `sd-fix-ci` skill by name", content)
                self.assertIn("weaken tests", content)
            elif "update-deps" in file.target.name:
                self.assertIn("Resolve the `sd-update-deps` skill by name", content)
                self.assertIn("Majors are always manual", content)
            elif "test-gaps" in file.target.name:
                self.assertIn("Resolve the `sd-test-gaps` skill by name", content)
                self.assertIn("test files and fixtures only", content)
            elif "retro" in file.target.name:
                self.assertIn("Resolve the `sd-retro` skill by name", content)
                self.assertIn("explicit user consent", content)
            elif "work-backlog" in file.target.name:
                self.assertIn("Resolve the `sd-work-backlog` skill by name", content)
                self.assertIn("one task per iteration", content)
                self.assertIn("sd-create-pr", content)
                self.assertIn("sd-housekeeping", content)
            elif "full-check" in file.target.name:
                self.assertIn("Resolve the `sd-full-check` skill by name", content)
                self.assertIn("source of truth for the exact checks", content)
            elif "ship" in file.target.name:
                self.assertIn("Resolve the `sd-ship` skill by name", content)
                self.assertIn("only merge authority", content)
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
            elif "status" in file.target.name:
                self.assertIn("Resolve the `sd-status` skill by name", content)
                self.assertIn("scripts/sd-ai-command-pack-toolchain.sh", content)
                self.assertIn("read-only", content)
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

    def test_review_pr_remote_round_limit_defaults_to_five(self) -> None:
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
                    "SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`, default `5`",
                    content,
                )
                self.assertNotIn(
                    "SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`, default `2`",
                    content,
                )

        skill = (
            install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'REMOTE_REVIEW_ROUND_LIMIT="${SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT:-5}"',
            skill,
        )
        self.assertIn("configured remote round limit, default five", skill)
        self.assertNotIn("configured remote round limit, default two", skill)

        readme = (install.ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "| `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT` | Max remote "
            "review request/fix rounds before asking whether to continue. | `5` |",
            readme,
        )
        guide = (
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "The round limit\ndefaults to five configured remote-review requests",
            guide,
        )

    def test_neutral_command_fanout_matches_registry(self) -> None:
        _, files = install.load_manifest()
        neutral_sources = {
            source.name: source.relative_to(install.ROOT).as_posix()
            for source in neutral_command_sources()
            if source.stem not in install.SOURCE_ONLY_COMMAND_NAMES
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
            "audit-repo",
            "watch-pr",
            "ship",
            "fix-ci",
            "update-deps",
            "test-gaps",
            "retro",
            "review-pr",
            "review-local",
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
            "help": "Discover, compare, and understand Software Delivery commands without running the selected workflow.",
            "status": "Report read-only local repository or configured fleet status with actionable next steps.",
            "start": "Initialize or resume a task using the Trellis start workflow.",
            "continue": "Resume the current Trellis task or workflow state.",
            "finish-work": "Wrap up the current Trellis coding session.",
            "create-pr": "Create or reuse a PR after SD spec refresh, commit, and push, then run the SD PR review loop.",
            "work-backlog": "Work through the Trellis backlog one task at a time through SD PR review and housekeeping.",
            "work-designs": "Add Trellis design and implementation-plan artifacts for tasks that need planning before implementation.",
            "audit-repo": "Run a formal multi-dimension repository audit that produces a canonical report and updates the committed findings ledger.",
            "watch-pr": "Watch the current branch's open pull request until it settles, then hand off to the housekeeping merge gate or report the blockers.",
            "fix-ci": "Triage failing CI runs, classify each failure, and drive the run back to green without weakening tests or bypassing guards.",
            "update-deps": "Batch-triage open dependency-bot pull requests, merging the safe classes sequentially through the housekeeping gate criteria and parking the rest.",
            "test-gaps": "Close the worst per-file coverage gaps by authoring focused tests for the lowest-covered shipped files.",
            "retro": "Capture a structured retrospective for a debugging stream or incident, record it in the journal, and propose consent-gated prevention tasks.",
            "review-pr": "Run the Software Delivery (SD) pull-request review loop.",
            "review-local": "Run the Software Delivery (SD) local review loop.",
            "ship": "Take the current branch from committed work to a merged pull request by sequencing the standard SD create-pr, review-pr, watch-pr, and housekeeping stages.",
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
            "scripts/sd_ai_command_pack_lib.py",
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
