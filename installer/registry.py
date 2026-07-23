"""Source of truth for platform adapters, command names, and pack-wide constants."""

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

# Command target families are shared by the generator, installer retirement,
# and command-surface lint. Keep their order byte-stable: it is the historical
# manifest order for one generated command footprint.
BESPOKE_ADAPTER_PLATFORMS = ("claude", "gemini", "github")
NEUTRAL_COMMAND_SOURCE_PLATFORMS = tuple(
    sorted(
        platform
        for platform, info in PLATFORM_REGISTRY.items()
        if info.command_kind and info.command_target_pattern
    )
)
LATER_NEUTRAL_COMMAND_PLATFORMS = tuple(
    platform
    for platform in NEUTRAL_COMMAND_SOURCE_PLATFORMS
    if platform not in ("cursor", "opencode")
)
SKILL_FANOUT_PLATFORMS = (
    "antigravity",
    "codebuddy",
    "devin",
    "droid",
    "kilo",
    "kiro",
    "pi",
    "qoder",
    "reasonix",
    "trae",
)
GENERATED_COMMAND_TARGET_FAMILIES = tuple(
    dict.fromkeys(
        (
            "shared",
            *BESPOKE_ADAPTER_PLATFORMS,
            *NEUTRAL_COMMAND_SOURCE_PLATFORMS,
            *SKILL_FANOUT_PLATFORMS,
        )
    )
)

@dataclass(frozen=True)
class CommandFamily:
    id: str
    label: str
    summary: str


@dataclass(frozen=True)
class CommandInfo:
    name: str
    short: str
    family: str
    executes_checkout_code: bool = True
    mutates_local: bool = False
    mutates_remote: bool = False
    trusted_static_only: bool = False
    safe_mode: str | None = None
    target_families: tuple[str, ...] = GENERATED_COMMAND_TARGET_FAMILIES
    configuration_keys: tuple[str, ...] = ()


COMMAND_FAMILIES: tuple[CommandFamily, ...] = (
    CommandFamily(
        id="orientation-knowledge",
        label="Orientation and knowledge",
        summary="Start or resume work, preserve knowledge, and close a session.",
    ),
    CommandFamily(
        id="planning-backlog",
        label="Planning and backlog",
        summary="Prepare implementation-ready plans and work the task backlog.",
    ),
    CommandFamily(
        id="verification-improvement",
        label="Verification and improvement",
        summary="Check quality, investigate failures, and strengthen the repository.",
    ),
    CommandFamily(
        id="pull-requests-shipping",
        label="Pull requests and shipping",
        summary="Publish, review, watch, merge, and clean up delivery streams.",
    ),
    CommandFamily(
        id="maintenance-fleet",
        label="Maintenance and fleet",
        summary="Maintain dependencies and roll pack releases across repositories.",
    ),
)

# Command source of truth: one row per sd-* command. Hand-authored bodies live
# at .github/command-sources/<name>.md; the generator writes guarded neutral
# payloads to templates/.commands/<name>.md, then derives the compatibility
# pair list, help catalog, bespoke adapters, and per-command manifest entries.
# New rows conservatively execute checkout code until explicitly proven static.
# Row order remains the canonical regenerated-manifest order.
COMMAND_REGISTRY: tuple[CommandInfo, ...] = (
    CommandInfo(
        "sd-help",
        "help",
        "orientation-knowledge",
        executes_checkout_code=False,
        trusted_static_only=True,
    ),
    CommandInfo("sd-status", "status", "orientation-knowledge"),
    CommandInfo("sd-continue", "continue", "orientation-knowledge", mutates_local=True),
    CommandInfo("sd-start", "start", "orientation-knowledge", mutates_local=True),
    CommandInfo(
        "sd-finish-work", "finish-work", "orientation-knowledge", mutates_local=True
    ),
    CommandInfo(
        "sd-create-pr",
        "create-pr",
        "pull-requests-shipping",
        mutates_local=True,
        mutates_remote=True,
    ),
    CommandInfo(
        "sd-work-backlog",
        "work-backlog",
        "planning-backlog",
        mutates_local=True,
        mutates_remote=True,
    ),
    CommandInfo(
        "sd-work-designs", "work-designs", "planning-backlog", mutates_local=True
    ),
    CommandInfo(
        "sd-audit-repo",
        "audit-repo",
        "verification-improvement",
        mutates_local=True,
    ),
    CommandInfo(
        "sd-watch-pr",
        "watch-pr",
        "pull-requests-shipping",
        mutates_local=True,
        mutates_remote=True,
    ),
    CommandInfo(
        "sd-fix-ci",
        "fix-ci",
        "verification-improvement",
        mutates_local=True,
        mutates_remote=True,
    ),
    CommandInfo(
        "sd-update-deps",
        "update-deps",
        "maintenance-fleet",
        mutates_local=True,
        mutates_remote=True,
    ),
    CommandInfo(
        "sd-fleet-refresh",
        "fleet-refresh",
        "maintenance-fleet",
        mutates_local=True,
        mutates_remote=True,
    ),
    CommandInfo(
        "sd-test-gaps", "test-gaps", "verification-improvement", mutates_local=True
    ),
    CommandInfo("sd-retro", "retro", "orientation-knowledge", mutates_local=True),
    CommandInfo(
        "sd-ship",
        "ship",
        "pull-requests-shipping",
        mutates_local=True,
        mutates_remote=True,
    ),
    CommandInfo(
        "sd-review-pr",
        "review-pr",
        "pull-requests-shipping",
        mutates_local=True,
        mutates_remote=True,
    ),
    CommandInfo(
        "sd-review-local",
        "review-local",
        "verification-improvement",
        mutates_local=True,
    ),
    CommandInfo(
        "sd-review-learnings",
        "review-learnings",
        "verification-improvement",
        mutates_local=True,
    ),
    CommandInfo(
        "sd-full-check", "full-check", "verification-improvement", mutates_local=True
    ),
    CommandInfo(
        "sd-housekeeping",
        "housekeeping",
        "pull-requests-shipping",
        mutates_local=True,
        mutates_remote=True,
    ),
    CommandInfo(
        "sd-update-spec", "update-spec", "orientation-knowledge", mutates_local=True
    ),
)


def validate_command_registry(
    commands: tuple[CommandInfo, ...],
    families: tuple[CommandFamily, ...],
) -> None:
    def duplicates(values: list[str]) -> list[str]:
        seen: set[str] = set()
        repeated: set[str] = set()
        for value in values:
            if value in seen:
                repeated.add(value)
            else:
                seen.add(value)
        return sorted(repeated)

    family_ids = [family.id for family in families]
    duplicate_family_ids = duplicates(family_ids)
    errors: list[str] = []
    if duplicate_family_ids:
        errors.append("duplicate family id(s): " + ", ".join(duplicate_family_ids))
    for family in families:
        if not family.id or not family.label or not family.summary:
            errors.append(f"family fields must be non-empty: {family!r}")

    names = [command.name for command in commands]
    shorts = [command.short for command in commands]
    duplicate_names = duplicates(names)
    duplicate_shorts = duplicates(shorts)
    if duplicate_names:
        errors.append("duplicate command name(s): " + ", ".join(duplicate_names))
    if duplicate_shorts:
        errors.append("duplicate command short form(s): " + ", ".join(duplicate_shorts))

    known_families = set(family_ids)
    for command in commands:
        if not command.name or not command.short or not command.family:
            errors.append(f"command fields must be non-empty: {command!r}")
            continue
        if not command.name.startswith("sd-"):
            errors.append(f"command name must start with sd-: {command.name}")
        elif command.short != command.name.removeprefix("sd-"):
            errors.append(
                f"command short form must match name: {command.name} -> {command.short}"
            )
        if command.family not in known_families:
            errors.append(
                f"command {command.name} uses unknown family: {command.family}"
            )
        capability_values = (
            command.executes_checkout_code,
            command.mutates_local,
            command.mutates_remote,
            command.trusted_static_only,
        )
        if not all(isinstance(value, bool) for value in capability_values):
            errors.append(f"command {command.name} capability flags must be boolean")
            continue
        if command.trusted_static_only and (
            command.executes_checkout_code
            or command.mutates_local
            or command.mutates_remote
            or command.safe_mode is not None
        ):
            errors.append(
                f"command {command.name} trusted_static_only conflicts with "
                "checkout execution or mutation"
            )
        if not command.executes_checkout_code and not command.trusted_static_only:
            errors.append(
                f"command {command.name} must execute checkout code or be "
                "trusted_static_only"
            )
        if command.safe_mode is not None and (
            not isinstance(command.safe_mode, str)
            or not command.safe_mode
            or not command.safe_mode.replace("-", "").replace("_", "").isalnum()
        ):
            errors.append(f"command {command.name} uses unsafe safe_mode")
        if not command.target_families:
            errors.append(f"command {command.name} has no generated target families")
        elif len(command.target_families) != len(set(command.target_families)):
            errors.append(f"command {command.name} has duplicate target families")
        else:
            unknown_targets = sorted(
                set(command.target_families) - set(GENERATED_COMMAND_TARGET_FAMILIES)
            )
            if unknown_targets:
                errors.append(
                    f"command {command.name} has unknown target families: "
                    + ", ".join(unknown_targets)
                )
        if any(
            not isinstance(key, str) or not key.strip()
            for key in command.configuration_keys
        ):
            errors.append(f"command {command.name} has invalid configuration keys")
        elif len(command.configuration_keys) != len(set(command.configuration_keys)):
            errors.append(f"command {command.name} has duplicate configuration keys")

    if errors:
        raise RuntimeError("invalid COMMAND_REGISTRY: " + "; ".join(errors))


validate_command_registry(COMMAND_REGISTRY, COMMAND_FAMILIES)

# Compatibility view retained for existing installer/generator consumers.
COMMAND_NAMES: tuple[tuple[str, str], ...] = tuple(
    (command.name, command.short) for command in COMMAND_REGISTRY
)

# Commands in this set are generated and available from the pack source
# checkout, but are not included in consumer manifests. Their workflows depend
# on source-only operator files such as the fleet registry and install entrypoint.
SOURCE_ONLY_COMMAND_NAMES = frozenset({"sd-fleet-refresh"})


def command_installed_targets(
    name: str,
    short: str,
    target_families: tuple[str, ...] = GENERATED_COMMAND_TARGET_FAMILIES,
) -> tuple[str, ...]:
    """Return the canonical consumer target footprint for one command."""

    def platform_target(platform: str) -> str:
        pattern = PLATFORM_REGISTRY[platform].command_target_pattern
        if pattern is None:
            raise RuntimeError(f"platform has no command target pattern: {platform}")
        return pattern.format(filename=f"{name}.md", name=short)

    targets: list[str] = []
    if "shared" in target_families:
        targets.append(f".agents/skills/{name}/SKILL.md")
    if "claude" in target_families:
        targets.append(f".claude/commands/sd/{short}.md")
    if "cursor" in target_families:
        targets.append(platform_target("cursor"))
    if "gemini" in target_families:
        targets.append(f".gemini/commands/sd/{short}.toml")
    if "github" in target_families:
        targets.append(f".github/prompts/{name}.prompt.md")
    if "opencode" in target_families:
        targets.append(platform_target("opencode"))
    targets.extend(
        platform_target(platform)
        for platform in LATER_NEUTRAL_COMMAND_PLATFORMS
        if platform in target_families
    )
    targets.extend(
        f"{PLATFORM_REGISTRY[platform].directory}/skills/{name}/SKILL.md"
        for platform in SKILL_FANOUT_PLATFORMS
        if platform in target_families
    )
    return tuple(targets)


@dataclass(frozen=True)
class RetiredCommandSurface:
    id: str
    identifiers: tuple[str, ...]
    installed_targets: tuple[str, ...]
    removed_version: str
    owner_task: str
    source_paths_must_be_absent: bool = True
    configuration_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandSurfaceAllowance:
    identifier: str
    path_pattern: str
    reason: str


RETIRED_COMMAND_SURFACES: tuple[RetiredCommandSurface, ...] = (
    RetiredCommandSurface(
        id="review-local-all-command",
        identifiers=("sd-review-local-all",),
        installed_targets=command_installed_targets(
            "sd-review-local-all", "review-local-all"
        ),
        removed_version="0.13.0",
        owner_task="07-15-skill-review-local-all",
    ),
    RetiredCommandSurface(
        id="fleet-refresh-consumer-targets",
        identifiers=(),
        installed_targets=command_installed_targets(
            "sd-fleet-refresh", "fleet-refresh"
        ),
        removed_version="0.15.1",
        owner_task="07-16-source-only-fleet-refresh-command",
        source_paths_must_be_absent=False,
    ),
)


def retired_surface_targets(surface_id: str) -> tuple[str, ...]:
    """Return one retired footprint or fail with actionable registry context."""

    for surface in RETIRED_COMMAND_SURFACES:
        if surface.id == surface_id:
            return surface.installed_targets
    raise RuntimeError(f"unknown retired command surface id: {surface_id}")

COMMAND_SURFACE_ALLOWANCES: tuple[CommandSurfaceAllowance, ...] = (
    CommandSurfaceAllowance(
        identifier="sd-review-local-all",
        path_pattern="README.md",
        reason="bounded migration note for the 0.13.0 command fold",
    ),
    CommandSurfaceAllowance(
        identifier="sd-review-local-all",
        path_pattern="installer/registry.py",
        reason="canonical retired-surface declaration",
    ),
    CommandSurfaceAllowance(
        identifier="sd-review-local-all",
        path_pattern="CHANGELOG.md",
        reason="bounded historical release record",
    ),
    CommandSurfaceAllowance(
        identifier="sd-review-local-all",
        path_pattern="tests/test_install_core.py",
        reason="migration behavior regression fixture",
    ),
    CommandSurfaceAllowance(
        identifier="sd-review-local-all",
        path_pattern="tests/test_retired_targets.py",
        reason="retired-target cleanup regression fixture",
    ),
    CommandSurfaceAllowance(
        identifier="sd-review-local-all",
        path_pattern="tests/test_command_surface_drift.py",
        reason="command-surface lint fixture",
    ),
)


def validate_command_surface_registry(
    commands: tuple[CommandInfo, ...],
    retirements: tuple[RetiredCommandSurface, ...],
    allowances: tuple[CommandSurfaceAllowance, ...],
) -> None:
    """Validate retired command metadata and its bounded history allowances."""

    errors: list[str] = []
    live_identifiers = {command.name for command in commands}
    live_configuration_keys = {
        key for command in commands for key in command.configuration_keys
    }
    retirement_ids = [retirement.id for retirement in retirements]
    if len(retirement_ids) != len(set(retirement_ids)):
        errors.append("duplicate retirement id")

    retired_identifiers: set[str] = set()
    retired_configuration_keys: set[str] = set()
    for retirement in retirements:
        if not (
            retirement.id.strip()
            and retirement.removed_version.strip()
            and retirement.owner_task.strip()
        ):
            errors.append(f"retirement fields must be non-empty: {retirement!r}")
        if not isinstance(retirement.source_paths_must_be_absent, bool):
            errors.append(
                f"retirement {retirement.id} source-path policy must be boolean"
            )
        if not (
            retirement.identifiers
            or retirement.installed_targets
            or retirement.configuration_keys
        ):
            errors.append(f"retirement {retirement.id} describes no surface")
        for label, values in (
            ("identifiers", retirement.identifiers),
            ("installed targets", retirement.installed_targets),
            ("configuration keys", retirement.configuration_keys),
        ):
            if len(values) != len(set(values)) or any(not value.strip() for value in values):
                errors.append(f"retirement {retirement.id} has invalid {label}")
        for target in retirement.installed_targets:
            path = Path(target)
            if path.is_absolute() or ".." in path.parts:
                errors.append(
                    f"retirement {retirement.id} has unsafe installed target: {target}"
                )
        overlap = live_identifiers.intersection(retirement.identifiers)
        if overlap:
            errors.append(
                f"retirement {retirement.id} identifiers are still live: "
                + ", ".join(sorted(overlap))
            )
        config_overlap = live_configuration_keys.intersection(
            retirement.configuration_keys
        )
        if config_overlap:
            errors.append(
                f"retirement {retirement.id} configuration keys are still live: "
                + ", ".join(sorted(config_overlap))
            )
        repeated_identifiers = retired_identifiers.intersection(
            retirement.identifiers
        )
        repeated_keys = retired_configuration_keys.intersection(
            retirement.configuration_keys
        )
        if repeated_identifiers:
            errors.append(
                "retired identifiers have multiple owners: "
                + ", ".join(sorted(repeated_identifiers))
            )
        if repeated_keys:
            errors.append(
                "retired configuration keys have multiple owners: "
                + ", ".join(sorted(repeated_keys))
            )
        retired_identifiers.update(retirement.identifiers)
        retired_configuration_keys.update(retirement.configuration_keys)

    known_allowance_identifiers = retired_identifiers | retired_configuration_keys
    seen_allowances: set[tuple[str, str]] = set()
    for allowance in allowances:
        key = (allowance.identifier, allowance.path_pattern)
        path = Path(allowance.path_pattern)
        if allowance.identifier not in known_allowance_identifiers:
            errors.append(
                f"allowance names an identifier that is not retired: {allowance.identifier}"
            )
        if key in seen_allowances:
            errors.append(
                f"duplicate command surface allowance: {allowance.identifier} "
                f"{allowance.path_pattern}"
            )
        if (
            path.is_absolute()
            or ".." in path.parts
            or allowance.path_pattern in {"*", "**", "**/*"}
        ):
            errors.append(
                f"unsafe command surface allowance path: {allowance.path_pattern}"
            )
        if not allowance.reason.strip():
            errors.append(
                f"command surface allowance has no reason: {allowance.path_pattern}"
            )
        seen_allowances.add(key)

    if errors:
        raise RuntimeError("invalid command surface registry: " + "; ".join(errors))


validate_command_surface_registry(
    COMMAND_REGISTRY,
    RETIRED_COMMAND_SURFACES,
    COMMAND_SURFACE_ALLOWANCES,
)

# Extra files that must travel with an installed shared skill. Relative paths
# are rooted inside templates/.agents/skills/<skill>/ and are fanned out by the
# command-surface generator to every supported skill root.
SHARED_SKILL_REFERENCES: dict[str, tuple[str, ...]] = {
    "sd-help": (
        "references/command-catalog.md",
        "references/examples.md",
    ),
    "sd-work-backlog": ("references/autonomous-loop.md",),
}


def validate_shared_skill_references(
    command_names: tuple[tuple[str, str], ...],
    references: dict[str, tuple[str, ...]],
) -> None:
    known_commands = {name for name, _short in command_names}
    unknown = sorted(set(references) - known_commands)
    errors = ["unknown skill(s): " + ", ".join(unknown)] if unknown else []
    for name, paths in references.items():
        if len(paths) != len(set(paths)):
            errors.append(f"{name} contains duplicate reference paths")
        for value in paths:
            path = Path(value)
            if (
                path.is_absolute()
                or ".." in path.parts
                or len(path.parts) < 2
                or path.parts[0] != "references"
                or path.suffix != ".md"
            ):
                errors.append(f"{name} contains unsafe reference path: {value}")
    if errors:
        raise RuntimeError("invalid SHARED_SKILL_REFERENCES: " + "; ".join(errors))


def validate_source_only_command_names(
    command_names: tuple[tuple[str, str], ...],
    source_only_names: frozenset[str],
) -> None:
    unknown = source_only_names - {name for name, _short in command_names}
    if unknown:
        raise RuntimeError(
            "SOURCE_ONLY_COMMAND_NAMES contains unknown command(s): "
            + ", ".join(sorted(unknown))
        )


validate_source_only_command_names(COMMAND_NAMES, SOURCE_ONLY_COMMAND_NAMES)
validate_shared_skill_references(COMMAND_NAMES, SHARED_SKILL_REFERENCES)

# Pack-owned .gito defaults are not a platform but share the local-gitignore
# grouping; kept here so the managed block order below stays byte-stable.
PACK_LOCAL_GITIGNORE_GROUP_NAME = "__pack__"
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
_LOCAL_GITIGNORE_GROUP_ORDER = ("antigravity", "claude", "codebuddy", "codex", "cursor", "devin", "droid", "gemini", PACK_LOCAL_GITIGNORE_GROUP_NAME, "kiro", "kilo", "opencode", "pi", "qoder", "reasonix", "trae", "zcode",)
_LOCAL_ONLY_GROUP_ORDER = ("antigravity", "shared", "claude", "codebuddy", "codex", "cursor", "devin", "droid", "gemini", "github", "kiro", "kilo", "opencode", "pi", "qoder", "reasonix", "trae", "zcode",)

PLATFORMS = tuple(sorted(PLATFORM_REGISTRY))
ALWAYS_INSTALL = "always"
IF_ANCHOR_EXISTS = "if-anchor-exists"
IF_NOT_EXISTS = "if-not-exists"
KNOWN_INSTALL_MODES = frozenset({ALWAYS_INSTALL, IF_ANCHOR_EXISTS, IF_NOT_EXISTS})


def _ordered_platform_groups_with_local_gitignore() -> frozenset[str]:
    return frozenset(
        platform
        for platform, info in PLATFORM_REGISTRY.items()
        if info.local_gitignore_patterns
    ) | frozenset({PACK_LOCAL_GITIGNORE_GROUP_NAME})


def _ordered_platform_groups_with_local_only() -> frozenset[str]:
    return frozenset(
        platform
        for platform, info in PLATFORM_REGISTRY.items()
        if info.trellis_local_only
    )


def _duplicate_order_groups(order: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for group in order:
        if group in seen:
            duplicates.add(group)
        seen.add(group)
    return sorted(duplicates)


def _validate_registry_group_order(
    name: str,
    order: tuple[str, ...],
    expected_groups: frozenset[str],
) -> None:
    actual_groups = set(order)
    missing_groups = sorted(expected_groups - actual_groups)
    unexpected_groups = sorted(actual_groups - expected_groups)
    duplicate_groups = _duplicate_order_groups(order)
    if not (missing_groups or unexpected_groups or duplicate_groups):
        return

    issues: list[str] = []
    if missing_groups:
        issues.append(f"missing group(s): {', '.join(missing_groups)}")
    if unexpected_groups:
        issues.append(f"unexpected group(s): {', '.join(unexpected_groups)}")
    if duplicate_groups:
        issues.append(f"duplicate group(s): {', '.join(duplicate_groups)}")
    raise RuntimeError(
        f"{name} is inconsistent with PLATFORM_REGISTRY: {'; '.join(issues)}"
    )


def _validate_registry_group_orders() -> None:
    _validate_registry_group_order(
        "_LOCAL_GITIGNORE_GROUP_ORDER",
        _LOCAL_GITIGNORE_GROUP_ORDER,
        _ordered_platform_groups_with_local_gitignore(),
    )
    _validate_registry_group_order(
        "_LOCAL_ONLY_GROUP_ORDER",
        _LOCAL_ONLY_GROUP_ORDER,
        _ordered_platform_groups_with_local_only(),
    )


_validate_registry_group_orders()

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
PLATFORM_LOCAL_GITIGNORE_PATTERNS = tuple(
    pattern
    for group in _LOCAL_GITIGNORE_GROUP_ORDER
    for pattern in (
        PACK_LOCAL_GITIGNORE_GROUP
        if group == PACK_LOCAL_GITIGNORE_GROUP_NAME
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
    "BESPOKE_ADAPTER_PLATFORMS",
    "COMMAND_FAMILIES",
    "COMMAND_SURFACE_ALLOWANCES",
    "COMMAND_REGISTRY",
    "COMMAND_NAMES",
    "CommandSurfaceAllowance",
    "CommandFamily",
    "CommandInfo",
    "COPILOT_GUIDANCE_END",
    "COPILOT_GUIDANCE_START",
    "COPILOT_INSTRUCTIONS_TARGET",
    "FORCE_PRESERVED_TARGETS",
    "IF_NOT_EXISTS",
    "IF_ANCHOR_EXISTS",
    "INSTALLED_TARGETS_FILE",
    "KNOWN_INSTALL_MODES",
    "LOCAL_ENV_GITIGNORE_PATTERNS",
    "LOCAL_ONLY_EXCLUDE_END",
    "LOCAL_ONLY_EXCLUDE_START",
    "LOCAL_ONLY_MARKER_FILE",
    "LOCAL_ONLY_TRACKED_CHECK_PATHS",
    "LOCAL_ONLY_TRELLIS_EXCLUDES",
    "MANAGED_BLOCK_KIND",
    "GENERATED_COMMAND_TARGET_FAMILIES",
    "LATER_NEUTRAL_COMMAND_PLATFORMS",
    "NEUTRAL_COMMAND_SOURCE_PLATFORMS",
    "PACK_LOCAL_GITIGNORE_GROUP",
    "PACK_LOCAL_GITIGNORE_GROUP_NAME",
    "PACK_MANIFEST_FILE",
    "PLATFORM_LOCAL_GITIGNORE_PATTERNS",
    "PLATFORM_REGISTRY",
    "PLATFORMS",
    "PROVENANCE_FILE",
    "PlatformInfo",
    "RETIRED_COMMAND_SURFACES",
    "RetiredCommandSurface",
    "REVIEW_ARTIFACT_GITIGNORE_PATTERNS",
    "ROOT",
    "SHARED_SKILL_REFERENCES",
    "SKILL_FANOUT_PLATFORMS",
    "SOURCE_ONLY_COMMAND_NAMES",
    "TRELLIS_BLANKET_GITIGNORE_ENTRIES",
    "TRELLIS_GITIGNORE_END",
    "TRELLIS_GITIGNORE_PATTERNS",
    "TRELLIS_GITIGNORE_START",
    "TRELLIS_GITIGNORE_TARGET",
    "TRELLIS_INIT_PLATFORM_FLAGS",
    "TRELLIS_INSTALL_DOCS_URL",
    "_ordered_platform_groups_with_local_gitignore",
    "_ordered_platform_groups_with_local_only",
    "_validate_registry_group_order",
    "_validate_registry_group_orders",
    "validate_command_registry",
    "validate_command_surface_registry",
    "command_installed_targets",
    "validate_shared_skill_references",
    "validate_source_only_command_names",
]
