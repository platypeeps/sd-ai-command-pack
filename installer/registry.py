"""Part of the sd-ai-command-pack installer package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The package lives one level below the pack root that hosts install.py,
# manifest.json, and templates/.
ROOT = Path(__file__).resolve().parent.parent
# One registry row per platform id; every per-platform table below derives
# from it. Adding a platform means one registry row (plus manifest records)
# and, when the row carries gitignore/local-only entries, a slot in the
# byte-stability order tuples further down — a test invariant fails if a
# row's entries are left out of those orders.
@dataclass(frozen=True)
class PlatformInfo:
    directory: str
    markers: tuple[str, ...] = ()
    init_flag: str | None = None
    local_gitignore_patterns: tuple[str, ...] = ()
    trellis_local_only: tuple[str, ...] = ()
    command_kind: str | None = None
    command_target_pattern: str | None = None


PLATFORM_REGISTRY: dict[str, PlatformInfo] = {
    "antigravity": PlatformInfo(
        directory=".agent",
        markers=(
            ".agent/workflows/continue.md",
            ".agent/workflows/start.md",
            ".agent/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--antigravity",
        local_gitignore_patterns=(
            ".agent/**/*.local.*",
            ".agent/**/.cache/",
            ".agent/**/cache/",
            ".agent/**/logs/",
            ".agent/**/tmp/",
            ".agent/**/*.log",
        ),
        trellis_local_only=(
            ".agent/workflows/start.md",
            ".agent/workflows/continue.md",
            ".agent/workflows/finish-work.md",
            ".agent/skills/trellis-*/",
        ),
        command_kind="workflow",
        command_target_pattern=".agent/workflows/{filename}",
    ),
    "claude": PlatformInfo(
        directory=".claude",
        markers=(
            ".claude/commands/trellis/continue.md",
            ".claude/hooks/session-start.py",
            ".claude/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--claude",
        local_gitignore_patterns=(
            ".claude/**",
            "!.claude/commands/",
            "!.claude/commands/sd/",
            "!.claude/commands/sd/*.md",
            ".claude/settings.local.json",
            ".claude/**/*.local.*",
            ".claude/**/.cache/",
            ".claude/**/cache/",
            ".claude/**/logs/",
            ".claude/**/*.log",
        ),
        trellis_local_only=(
            ".claude/commands/trellis/",
            ".claude/hooks/",
            ".claude/skills/trellis-*/",
        ),
    ),
    "codebuddy": PlatformInfo(
        directory=".codebuddy",
        markers=(
            ".codebuddy/commands/trellis/continue.md",
            ".codebuddy/hooks/session-start.py",
            ".codebuddy/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--codebuddy",
        local_gitignore_patterns=(
            ".codebuddy/**/*.local.*",
            ".codebuddy/**/.cache/",
            ".codebuddy/**/cache/",
            ".codebuddy/**/logs/",
            ".codebuddy/**/tmp/",
            ".codebuddy/**/*.log",
        ),
        trellis_local_only=(
            ".codebuddy/agents/trellis-*.md",
            ".codebuddy/commands/trellis/",
            ".codebuddy/hooks/",
            ".codebuddy/settings.json",
            ".codebuddy/skills/trellis-*/",
        ),
        command_kind="command",
        command_target_pattern=".codebuddy/commands/sd/{name}.md",
    ),
    "codex": PlatformInfo(
        directory=".codex",
        local_gitignore_patterns=(
            ".codex/**/*.local.*",
            ".codex/**/.cache/",
            ".codex/**/cache/",
            ".codex/**/logs/",
            ".codex/**/sessions/",
            ".codex/**/tmp/",
            ".codex/**/*.log",
        ),
        trellis_local_only=(
            ".codex/agents/trellis-*.toml",
            ".codex/config.toml",
            ".codex/hooks.json",
            ".codex/hooks/",
        ),
    ),
    "cursor": PlatformInfo(
        directory=".cursor",
        markers=(
            ".cursor/commands/trellis-continue.md",
            ".cursor/hooks.json",
            ".cursor/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--cursor",
        local_gitignore_patterns=(
            ".cursor/**/*.local.*",
            ".cursor/**/.cache/",
            ".cursor/**/cache/",
            ".cursor/**/logs/",
            ".cursor/**/tmp/",
            ".cursor/**/*.log",
        ),
        trellis_local_only=(
            ".cursor/agents/trellis-*.md",
            ".cursor/commands/trellis-*.md",
            ".cursor/hooks.json",
            ".cursor/hooks/",
            ".cursor/skills/trellis-*/",
        ),
        command_kind="command",
        command_target_pattern=".cursor/commands/{filename}",
    ),
    "devin": PlatformInfo(
        directory=".devin",
        markers=(
            ".devin/workflows/trellis-continue.md",
            ".devin/workflows/trellis-start.md",
            ".devin/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--devin",
        local_gitignore_patterns=(
            ".devin/**/*.local.*",
            ".devin/**/.cache/",
            ".devin/**/cache/",
            ".devin/**/logs/",
            ".devin/**/tmp/",
            ".devin/**/*.log",
        ),
        trellis_local_only=(
            ".devin/workflows/trellis-*.md",
            ".devin/skills/trellis-*/",
        ),
        command_kind="workflow",
        command_target_pattern=".devin/workflows/{filename}",
    ),
    "droid": PlatformInfo(
        directory=".factory",
        markers=(
            ".factory/commands/trellis/continue.md",
            ".factory/hooks/session-start.py",
            ".factory/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--droid",
        local_gitignore_patterns=(
            ".factory/**/*.local.*",
            ".factory/**/.cache/",
            ".factory/**/cache/",
            ".factory/**/logs/",
            ".factory/**/tmp/",
            ".factory/**/*.log",
        ),
        trellis_local_only=(
            ".factory/commands/trellis/",
            ".factory/droids/trellis-*.md",
            ".factory/hooks/",
            ".factory/settings.json",
            ".factory/skills/trellis-*/",
        ),
        command_kind="command",
        command_target_pattern=".factory/commands/sd/{name}.md",
    ),
    "gemini": PlatformInfo(
        directory=".gemini",
        markers=(
            ".gemini/commands/trellis/continue.toml",
            ".gemini/hooks/session-start.py",
            ".gemini/agents/trellis-check.md",
        ),
        init_flag="--gemini",
        local_gitignore_patterns=(
            ".gemini/settings.local.json",
            ".gemini/**/*.local.*",
            ".gemini/**/.cache/",
            ".gemini/**/cache/",
            ".gemini/**/logs/",
            ".gemini/**/tmp/",
            ".gemini/**/*.log",
        ),
        trellis_local_only=(
            ".gemini/commands/trellis/",
            ".gemini/hooks/",
            ".gemini/agents/trellis-*.md",
        ),
    ),
    "github": PlatformInfo(
        directory=".github",
        markers=(
            ".github/hooks/trellis.json",
            ".github/copilot/hooks.json",
            ".github/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--copilot",
        trellis_local_only=(
            ".github/hooks/trellis.json",
            ".github/copilot/hooks.json",
            ".github/skills/trellis-*/",
        ),
    ),
    "kilo": PlatformInfo(
        directory=".kilocode",
        markers=(
            ".kilocode/workflows/continue.md",
            ".kilocode/workflows/start.md",
            ".kilocode/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--kilo",
        local_gitignore_patterns=(
            ".kilocode/**/*.local.*",
            ".kilocode/**/.cache/",
            ".kilocode/**/cache/",
            ".kilocode/**/logs/",
            ".kilocode/**/tmp/",
            ".kilocode/**/*.log",
        ),
        trellis_local_only=(
            ".kilocode/workflows/start.md",
            ".kilocode/workflows/continue.md",
            ".kilocode/workflows/finish-work.md",
            ".kilocode/skills/trellis-*/",
        ),
        command_kind="workflow",
        command_target_pattern=".kilocode/workflows/{filename}",
    ),
    "kiro": PlatformInfo(
        directory=".kiro",
        markers=(
            ".kiro/skills/trellis-continue/SKILL.md",
            ".kiro/hooks/inject-workflow-state.py",
            ".kiro/agents/trellis.json",
        ),
        init_flag="--kiro",
        local_gitignore_patterns=(
            ".kiro/**/*.local.*",
            ".kiro/**/.cache/",
            ".kiro/**/cache/",
            ".kiro/**/logs/",
            ".kiro/**/tmp/",
            ".kiro/**/*.log",
        ),
        trellis_local_only=(
            ".kiro/agents/trellis*.json",
            ".kiro/hooks/",
            ".kiro/skills/trellis-*/",
        ),
    ),
    "opencode": PlatformInfo(
        directory=".opencode",
        markers=(
            ".opencode/commands/trellis/continue.md",
            ".opencode/lib/trellis-context.js",
            ".opencode/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--opencode",
        local_gitignore_patterns=(
            ".opencode/**/*.local.*",
            ".opencode/**/.cache/",
            ".opencode/**/cache/",
            ".opencode/**/logs/",
            ".opencode/**/tmp/",
            ".opencode/**/state/",
            ".opencode/**/sessions/",
            ".opencode/node_modules/",
            ".opencode/**/*.log",
        ),
        trellis_local_only=(
            ".opencode/commands/trellis/",
            ".opencode/lib/trellis-context.js",
            ".opencode/skills/trellis-*/",
        ),
        command_kind="command",
        command_target_pattern=".opencode/commands/{filename}",
    ),
    "pi": PlatformInfo(
        directory=".pi",
        markers=(
            ".pi/prompts/trellis-continue.md",
            ".pi/extensions/trellis/index.ts",
            ".pi/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--pi",
        local_gitignore_patterns=(
            ".pi/**/*.local.*",
            ".pi/**/.cache/",
            ".pi/**/cache/",
            ".pi/**/logs/",
            ".pi/**/tmp/",
            ".pi/**/*.log",
        ),
        trellis_local_only=(
            ".pi/agents/trellis-*.md",
            ".pi/extensions/trellis/",
            ".pi/prompts/trellis-*.md",
            ".pi/settings.json",
            ".pi/skills/trellis-*/",
        ),
        command_kind="prompt",
        command_target_pattern=".pi/prompts/{filename}",
    ),
    "qoder": PlatformInfo(
        directory=".qoder",
        markers=(
            ".qoder/commands/trellis-continue.md",
            ".qoder/hooks/session-start.py",
            ".qoder/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--qoder",
        local_gitignore_patterns=(
            ".qoder/**/*.local.*",
            ".qoder/**/.cache/",
            ".qoder/**/cache/",
            ".qoder/**/logs/",
            ".qoder/**/tmp/",
            ".qoder/**/*.log",
        ),
        trellis_local_only=(
            ".qoder/agents/trellis-*.md",
            ".qoder/commands/trellis-*.md",
            ".qoder/hooks/",
            ".qoder/settings.json",
            ".qoder/skills/trellis-*/",
        ),
        command_kind="command",
        command_target_pattern=".qoder/commands/{filename}",
    ),
    "reasonix": PlatformInfo(
        directory=".reasonix",
        markers=(
            ".reasonix/skills/trellis-continue/SKILL.md",
            ".reasonix/skills/trellis-start/SKILL.md",
            ".reasonix/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--reasonix",
        local_gitignore_patterns=(
            ".reasonix/**/*.local.*",
            ".reasonix/**/.cache/",
            ".reasonix/**/cache/",
            ".reasonix/**/logs/",
            ".reasonix/**/tmp/",
            ".reasonix/**/*.log",
        ),
        trellis_local_only=(
            ".reasonix/skills/trellis-*/",
        ),
    ),
    "shared": PlatformInfo(
        directory=".agents",
        trellis_local_only=(
            ".agents/skills/trellis-*/",
        ),
    ),
    "trae": PlatformInfo(
        directory=".trae",
        markers=(
            ".trae/commands/trellis-continue.md",
            ".trae/hooks/session-start.py",
            ".trae/skills/trellis-before-dev/SKILL.md",
        ),
        init_flag="--trae",
        local_gitignore_patterns=(
            ".trae/**/*.local.*",
            ".trae/**/.cache/",
            ".trae/**/cache/",
            ".trae/**/logs/",
            ".trae/**/tmp/",
            ".trae/**/*.log",
        ),
        trellis_local_only=(
            ".trae/agents/trellis-*.md",
            ".trae/commands/trellis-*.md",
            ".trae/hooks.json",
            ".trae/hooks/",
            ".trae/skills/trellis-*/",
        ),
        command_kind="command",
        command_target_pattern=".trae/commands/{filename}",
    ),
    "zcode": PlatformInfo(
        directory=".zcode",
        markers=(
            ".zcode/commands/trellis/continue.md",
            ".zcode/agents/trellis-check.md",
            ".zcode/cli/agents/trellis-check.md",
        ),
        init_flag="--zcode",
        local_gitignore_patterns=(
            ".zcode/**/*.local.*",
            ".zcode/**/.cache/",
            ".zcode/**/cache/",
            ".zcode/**/logs/",
            ".zcode/**/tmp/",
            ".zcode/**/*.log",
        ),
        trellis_local_only=(
            ".zcode/agents/trellis-*.md",
            ".zcode/cli/agents/trellis-*.md",
            ".zcode/commands/trellis/",
        ),
        command_kind="command",
        command_target_pattern=".zcode/commands/sd/{name}.md",
    ),
}

# Command-list source of truth: one (name, short form) row per sd-* command
# that ships a neutral body at templates/.commands/<name>.md. The bespoke
# claude/gemini/github adapters and the per-command manifest entries are
# generated from this list by .github/scripts/generate-command-surfaces.py
# (`make generate`); adding a command means adding the skill, the neutral
# body, and one row here. Row order is the canonical per-command order of
# the regenerated manifest.
COMMAND_NAMES: tuple[tuple[str, str], ...] = (
    ("sd-continue", "continue"),
    ("sd-start", "start"),
    ("sd-finish-work", "finish-work"),
    ("sd-create-pr", "create-pr"),
    ("sd-work-backlog", "work-backlog"),
    ("sd-work-designs", "work-designs"),
    ("sd-audit-repo", "audit-repo"),
    ("sd-watch-pr", "watch-pr"),
    ("sd-fix-ci", "fix-ci"),
    ("sd-update-deps", "update-deps"),
    ("sd-fleet-refresh", "fleet-refresh"),
    ("sd-test-gaps", "test-gaps"),
    ("sd-retro", "retro"),
    ("sd-ship", "ship"),
    ("sd-review-pr", "review-pr"),
    ("sd-review-local", "review-local"),
    ("sd-review-learnings", "review-learnings"),
    ("sd-full-check", "full-check"),
    ("sd-housekeeping", "housekeeping"),
    ("sd-update-spec", "update-spec"),
)

# Pack-owned .gito defaults are not a platform but share the local-gitignore
# grouping; kept here so the managed block order below stays byte-stable.
PACK_LOCAL_GITIGNORE_GROUP = (
    ".gito/**/*.local.*",
    ".gito/**/.cache/",
    ".gito/**/cache/",
    ".gito/**/logs/",
    ".gito/**/tmp/",
    ".gito/**/*.log",
)

# Hand-curated group order preserved from the pre-registry literal so the
# managed .gitignore block content does not churn in consumer repos.
_LOCAL_GITIGNORE_GROUP_ORDER = ("antigravity", "claude", "codebuddy", "codex", "cursor", "devin", "droid", "gemini", "__pack__", "kiro", "kilo", "opencode", "pi", "qoder", "reasonix", "trae", "zcode",)
_LOCAL_ONLY_GROUP_ORDER = ("antigravity", "shared", "claude", "codebuddy", "codex", "cursor", "devin", "droid", "gemini", "github", "kiro", "kilo", "opencode", "pi", "qoder", "reasonix", "trae", "zcode",)

PLATFORMS = tuple(sorted(PLATFORM_REGISTRY))
ALWAYS_INSTALL = "always"
IF_NOT_EXISTS = "if-not-exists"
ACTIVE_TRELLIS_PLATFORM_MARKERS = {
    platform: tuple(Path(marker) for marker in info.markers)
    for platform, info in PLATFORM_REGISTRY.items()
    if info.markers
}
TRELLIS_INIT_PLATFORM_FLAGS = {
    platform: info.init_flag
    for platform, info in PLATFORM_REGISTRY.items()
    if info.init_flag
}
NEUTRAL_COMMAND_SOURCE_PLATFORMS = tuple(
    sorted(
        platform
        for platform, info in PLATFORM_REGISTRY.items()
        if info.command_kind and info.command_target_pattern
    )
)
PLATFORM_LOCAL_GITIGNORE_PATTERNS = tuple(
    pattern
    for group in _LOCAL_GITIGNORE_GROUP_ORDER
    for pattern in (
        PACK_LOCAL_GITIGNORE_GROUP
        if group == "__pack__"
        else PLATFORM_REGISTRY[group].local_gitignore_patterns
    )
) + ("node_modules/",)
LOCAL_ONLY_TRELLIS_EXCLUDES = (
    "AGENTS.md",
    ".trellis/",
    *(
        pattern
        for platform in _LOCAL_ONLY_GROUP_ORDER
        for pattern in PLATFORM_REGISTRY[platform].trellis_local_only
    ),
    ".obsidian-kb/",
)
LOCAL_ONLY_TRACKED_CHECK_PATHS = (
    "AGENTS.md",
    ".trellis",
    *(
        pattern.rstrip("/")
        for platform in _LOCAL_ONLY_GROUP_ORDER
        for pattern in PLATFORM_REGISTRY[platform].trellis_local_only
    ),
)
TRELLIS_INSTALL_DOCS_URL = "https://docs.trytrellis.app/start/install-and-first-task"
FORCE_PRESERVED_TARGETS = frozenset(
    {
        Path(".prism/rules.json"),
        Path(".gito/config.toml"),
        Path(".github/PULL_REQUEST_TEMPLATE.md"),
    }
)
INSTALLED_TARGETS_FILE = Path(".sd-ai-command-pack/installed-targets.txt")
PROVENANCE_FILE = Path(".sd-ai-command-pack/provenance.json")
PACK_MANIFEST_FILE = Path(".sd-ai-command-pack/manifest.json")
LOCAL_ONLY_MARKER_FILE = Path(".sd-ai-command-pack/local-only.txt")
LOCAL_ONLY_EXCLUDE_START = "# sd-ai-command-pack local-only start"
LOCAL_ONLY_EXCLUDE_END = "# sd-ai-command-pack local-only end"
TRELLIS_GITIGNORE_TARGET = Path(".gitignore")
TRELLIS_GITIGNORE_START = "# sd-ai-command-pack trellis-gitignore start"
TRELLIS_GITIGNORE_END = "# sd-ai-command-pack trellis-gitignore end"
LOCAL_ENV_GITIGNORE_PATTERNS = (
    ".env",
    ".env.*",
    "!.env.example",
    "!.env.ci",
    "!.env.test",
)
TRELLIS_GITIGNORE_PATTERNS = (
    ".trellis/.developer",
    ".trellis/.backup-*",
    ".trellis/worktrees/",
    ".trellis/.template-hashes.json",
    ".trellis/.runtime/",
    ".trellis/.cache/",
)
REVIEW_ARTIFACT_GITIGNORE_PATTERNS = (
    ".build/",
    "code-review-report.json",
    "code-review-report.md",
    "sd-ai-command-pack-gito.*",
    "sd-ai-command-pack-review-paths.*",
    "sd-ai-command-pack-review-filters.*",
    "sd-ai-command-pack-prism-codebase.*",
    "sd-ai-command-pack-ci-paths.*",
    "sd-ai-command-pack-uv-cache/",
    "sd-ai-command-pack-uv-tools/",
)
TRELLIS_BLANKET_GITIGNORE_ENTRIES = frozenset(
    {
        ".trellis",
        ".trellis/",
        "/.trellis",
        "/.trellis/",
    }
)
MANAGED_BLOCK_KIND = "managed-block"
COPILOT_INSTRUCTIONS_TARGET = Path(".github/copilot-instructions.md")
COPILOT_GUIDANCE_START = "<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START -->"
COPILOT_GUIDANCE_END = "<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:END -->"

__all__ = [
    "ACTIVE_TRELLIS_PLATFORM_MARKERS",
    "ALWAYS_INSTALL",
    "COMMAND_NAMES",
    "COPILOT_GUIDANCE_END",
    "COPILOT_GUIDANCE_START",
    "COPILOT_INSTRUCTIONS_TARGET",
    "FORCE_PRESERVED_TARGETS",
    "IF_NOT_EXISTS",
    "INSTALLED_TARGETS_FILE",
    "LOCAL_ENV_GITIGNORE_PATTERNS",
    "LOCAL_ONLY_EXCLUDE_END",
    "LOCAL_ONLY_EXCLUDE_START",
    "LOCAL_ONLY_MARKER_FILE",
    "LOCAL_ONLY_TRACKED_CHECK_PATHS",
    "LOCAL_ONLY_TRELLIS_EXCLUDES",
    "MANAGED_BLOCK_KIND",
    "NEUTRAL_COMMAND_SOURCE_PLATFORMS",
    "PACK_LOCAL_GITIGNORE_GROUP",
    "PACK_MANIFEST_FILE",
    "PLATFORM_LOCAL_GITIGNORE_PATTERNS",
    "PLATFORM_REGISTRY",
    "PLATFORMS",
    "PROVENANCE_FILE",
    "PlatformInfo",
    "REVIEW_ARTIFACT_GITIGNORE_PATTERNS",
    "ROOT",
    "TRELLIS_BLANKET_GITIGNORE_ENTRIES",
    "TRELLIS_GITIGNORE_END",
    "TRELLIS_GITIGNORE_PATTERNS",
    "TRELLIS_GITIGNORE_START",
    "TRELLIS_GITIGNORE_TARGET",
    "TRELLIS_INIT_PLATFORM_FLAGS",
    "TRELLIS_INSTALL_DOCS_URL",
]
