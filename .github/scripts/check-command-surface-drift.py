#!/usr/bin/env python3
"""Fail when the registry and live SD command surfaces drift apart."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

PACK_ROOT = Path(__file__).resolve().parents[2]
if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from installer.registry import (  # noqa: E402
    COMMAND_REGISTRY,
    COMMAND_SURFACE_ALLOWANCES,
    NEUTRAL_COMMAND_SOURCE_PLATFORMS,
    PLATFORM_REGISTRY,
    RETIRED_COMMAND_SURFACES,
    SKILL_FANOUT_PLATFORMS,
    SOURCE_ONLY_COMMAND_NAMES,
    CommandInfo,
    CommandSurfaceAllowance,
    RetiredCommandSurface,
    command_installed_targets,
)

TEXT_SUFFIXES = frozenset(
    {".json", ".md", ".mjs", ".py", ".sh", ".toml", ".txt", ".yaml", ".yml"}
)
TEXT_FILENAMES = frozenset({"Makefile"})
IGNORED_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".obsidian-kb",
        ".pytest_cache",
        ".ruff_cache",
        ".trellis/tasks",
        ".trellis/workspace",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "vendor",
    }
)
IGNORED_PREFIXES = (".trellis/.backup-",)
SKILL_PUBLIC_ROOTS = tuple(
    dict.fromkeys(
        (
            ".agents",
            *(
                PLATFORM_REGISTRY[platform].directory
                for platform in SKILL_FANOUT_PLATFORMS
            ),
        )
    )
)
SKILL_PUBLIC_ROOT_PATTERN = "|".join(
    re.escape(root) for root in SKILL_PUBLIC_ROOTS
)


def _registry_command_path_patterns() -> tuple[tuple[re.Pattern[str], bool], ...]:
    """Compile installed command-adapter paths from the platform registry."""

    patterns: list[tuple[re.Pattern[str], bool]] = []
    for platform in NEUTRAL_COMMAND_SOURCE_PLATFORMS:
        target_pattern = PLATFORM_REGISTRY[platform].command_target_pattern
        if target_pattern is None:
            raise RuntimeError(f"platform has no command target pattern: {platform}")
        if "{filename}" in target_pattern:
            marker = "__SD_COMMAND_FILENAME__"
            expression = re.escape(target_pattern.replace("{filename}", marker))
            expression = expression.replace(
                re.escape(marker), r"(sd-[a-z0-9-]+)\.md"
            )
            patterns.append((re.compile(rf"^{expression}$"), False))
        elif "{name}" in target_pattern:
            marker = "__SD_COMMAND_NAME__"
            expression = re.escape(target_pattern.replace("{name}", marker))
            expression = expression.replace(re.escape(marker), r"([a-z0-9-]+)")
            patterns.append((re.compile(rf"^{expression}$"), True))
        else:
            raise RuntimeError(
                f"platform command target pattern has no name placeholder: {platform}"
            )
    return tuple(patterns)


REGISTRY_COMMAND_PATH_PATTERNS = _registry_command_path_patterns()
PUBLIC_PATH_PATTERNS: tuple[tuple[re.Pattern[str], bool], ...] = (
    (re.compile(r"^\.github/command-sources/(sd-[a-z0-9-]+)\.md$"), False),
    (
        re.compile(
            rf"^(?:templates/)?(?:{SKILL_PUBLIC_ROOT_PATTERN})/skills/"
            r"(sd-[a-z0-9-]+)/(?:SKILL\.md|references/)"
        ),
        False,
    ),
    (re.compile(r"^templates/\.commands/(sd-[a-z0-9-]+)\.md$"), False),
    (
        re.compile(r"^(?:templates/)?\.claude/commands/sd/([a-z0-9-]+)\.md$"),
        True,
    ),
    (
        re.compile(r"^(?:templates/)?\.gemini/commands/sd/([a-z0-9-]+)\.toml$"),
        True,
    ),
    (
        re.compile(
            r"^(?:templates/)?\.github/prompts/(sd-[a-z0-9-]+)\.prompt\.md$"
        ),
        False,
    ),
    *REGISTRY_COMMAND_PATH_PATTERNS,
)
MANIFEST_SOURCE_PATTERNS: tuple[tuple[re.Pattern[str], bool], ...] = (
    (
        re.compile(
            r"^templates/\.agents/skills/(sd-[a-z0-9-]+)/(?:SKILL\.md|references/)"
        ),
        False,
    ),
    (re.compile(r"^templates/\.commands/(sd-[a-z0-9-]+)\.md$"), False),
    (re.compile(r"^templates/\.claude/commands/sd/([a-z0-9-]+)\.md$"), True),
    (re.compile(r"^templates/\.gemini/commands/sd/([a-z0-9-]+)\.toml$"), True),
    (
        re.compile(r"^templates/\.github/prompts/(sd-[a-z0-9-]+)\.prompt\.md$"),
        False,
    ),
)


class SurfaceLintError(RuntimeError):
    """Raised when lint inputs cannot be inspected deterministically."""


@dataclass(frozen=True)
class Finding:
    category: str
    identifier: str
    path: str
    line: int
    message: str
    suggestion: str


@dataclass(frozen=True)
class LintReport:
    files_scanned: int
    suppressed: int
    findings: tuple[Finding, ...]

    def as_json(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.category] = counts.get(finding.category, 0) + 1
        return {
            "schemaVersion": 1,
            "status": "clean" if not self.findings else "failed",
            "filesScanned": self.files_scanned,
            "suppressed": self.suppressed,
            "findingCounts": dict(sorted(counts.items())),
            "findings": [asdict(finding) for finding in self.findings],
        }


def _ignored(relative: PurePosixPath) -> bool:
    text = relative.as_posix()
    return any(
        text == part or text.startswith(f"{part}/") for part in IGNORED_PARTS
    ) or text.startswith(IGNORED_PREFIXES)


def _text_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if _ignored(relative):
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in TEXT_FILENAMES:
            paths.append(path)
    return sorted(paths)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise SurfaceLintError(f"cannot read {path}: {exc}") from exc


def _line_for_literal(text: str, literal: str) -> int:
    index = text.find(literal)
    return 1 if index < 0 else text.count("\n", 0, index) + 1


def _token_pattern(identifier: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![A-Za-z0-9_-]){re.escape(identifier)}(?![A-Za-z0-9_-])"
    )


def _allowance_matches(
    allowance: CommandSurfaceAllowance, identifier: str, path: str
) -> bool:
    return allowance.identifier == identifier and fnmatch.fnmatchcase(
        path, allowance.path_pattern
    )


def _validate_allowances(
    allowances: Sequence[CommandSurfaceAllowance], known_identifiers: set[str]
) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for allowance in allowances:
        key = (allowance.identifier, allowance.path_pattern)
        path = PurePosixPath(allowance.path_pattern)
        message: str | None = None
        if allowance.identifier not in known_identifiers:
            message = "allowance names an identifier that is not retired"
        elif key in seen:
            message = "allowance duplicates an existing identifier/path rule"
        elif (
            path.is_absolute()
            or ".." in path.parts
            or allowance.path_pattern in {"*", "**", "**/*"}
        ):
            message = "allowance path is unsafe or broader than a live root"
        elif not allowance.reason.strip():
            message = "allowance has no reason"
        if message:
            findings.append(
                Finding(
                    category="invalid_allowance",
                    identifier=allowance.identifier,
                    path=allowance.path_pattern,
                    line=1,
                    message=message,
                    suggestion="replace it with a unique bounded path and reason",
                )
            )
        seen.add(key)
    return findings


def _required_source_paths(command: CommandInfo) -> tuple[str, ...]:
    paths = [f".github/command-sources/{command.name}.md"]
    if "shared" in command.target_families or any(
        platform in command.target_families
        for platform in SKILL_FANOUT_PLATFORMS
    ):
        paths.append(f"templates/.agents/skills/{command.name}/SKILL.md")
    if any(
        platform in command.target_families
        for platform in NEUTRAL_COMMAND_SOURCE_PLATFORMS
    ):
        paths.append(f"templates/.commands/{command.name}.md")
    if "claude" in command.target_families:
        paths.append(f"templates/.claude/commands/sd/{command.short}.md")
    if "gemini" in command.target_families:
        paths.append(f"templates/.gemini/commands/sd/{command.short}.toml")
    if "github" in command.target_families:
        paths.append(f"templates/.github/prompts/{command.name}.prompt.md")
    return tuple(paths)


def _manifest_command(source: str, shorts: dict[str, str]) -> str | None:
    for pattern, uses_short in MANIFEST_SOURCE_PATTERNS:
        match = pattern.match(source)
        if not match:
            continue
        token = match.group(1)
        return shorts.get(token, f"sd-{token}") if uses_short else token
    return None


def _path_command(relative: str, shorts: dict[str, str]) -> str | None:
    for pattern, uses_short in PUBLIC_PATH_PATTERNS:
        match = pattern.match(relative)
        if not match:
            continue
        token = match.group(1)
        return shorts.get(token, f"sd-{token}") if uses_short else token
    return None


def _manifest_findings(
    root: Path,
    commands: Sequence[CommandInfo],
    retirements: Sequence[RetiredCommandSurface],
    source_only: frozenset[str],
) -> list[Finding]:
    path = root / "manifest.json"
    text = _read_text(path)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SurfaceLintError(f"cannot parse {path}: {exc}") from exc
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list) or not all(isinstance(item, dict) for item in files):
        raise SurfaceLintError("manifest.json must contain an object files array")

    known = {command.name for command in commands}
    shorts = {command.short: command.name for command in commands}
    retired_names = {
        identifier
        for retirement in retirements
        for identifier in retirement.identifiers
    }
    targets_by_command: dict[str, set[str]] = {name: set() for name in known}
    reported_targets: set[str] = set()
    findings: list[Finding] = []
    for item in files:
        source = item.get("source")
        target = item.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        command_name = _manifest_command(source, shorts)
        if command_name is None:
            continue
        if command_name not in known:
            category = (
                "retired_identifier_live"
                if command_name in retired_names
                else "unregistered_public_target"
            )
            findings.append(
                Finding(
                    category=category,
                    identifier=command_name,
                    path="manifest.json",
                    line=_line_for_literal(text, target),
                    message=f"manifest source {source} is not registered",
                    suggestion="register the command or remove the public target",
                )
            )
            reported_targets.add(target)
            continue
        targets_by_command[command_name].add(target)

    for command in commands:
        actual = targets_by_command[command.name]
        if command.name in source_only:
            for target in sorted(actual):
                findings.append(
                    Finding(
                        category="generated_registry_mismatch",
                        identifier=command.name,
                        path="manifest.json",
                        line=_line_for_literal(text, target),
                        message=f"source-only command still installs {target}",
                        suggestion="remove its consumer manifest entry",
                    )
                )
                reported_targets.add(target)
            continue
        expected = set(
            command_installed_targets(
                command.name, command.short, command.target_families
            )
        )
        for target in sorted(expected - actual):
            findings.append(
                Finding(
                    category="live_identifier_missing_target",
                    identifier=command.name,
                    path="manifest.json",
                    line=1,
                    message=f"registered command is missing target {target}",
                    suggestion="regenerate command surfaces from the registry",
                )
            )

    manifest_targets = {
        str(item.get("target")) for item in files if isinstance(item.get("target"), str)
    }
    for retirement in retirements:
        for target in sorted(
            (set(retirement.installed_targets) & manifest_targets)
            - reported_targets
        ):
            findings.append(
                Finding(
                    category="retired_identifier_live",
                    identifier=retirement.id,
                    path="manifest.json",
                    line=_line_for_literal(text, target),
                    message=f"retired target remains in the live manifest: {target}",
                    suggestion="remove the target and regenerate the manifest",
                )
            )
    return findings


def lint_repository(
    root: Path,
    *,
    commands: Sequence[CommandInfo] = COMMAND_REGISTRY,
    retirements: Sequence[RetiredCommandSurface] = RETIRED_COMMAND_SURFACES,
    allowances: Sequence[CommandSurfaceAllowance] = COMMAND_SURFACE_ALLOWANCES,
    source_only: frozenset[str] = SOURCE_ONLY_COMMAND_NAMES,
) -> LintReport:
    root = root.resolve()
    if not (root / "manifest.json").is_file():
        raise SurfaceLintError(f"missing manifest.json under {root}")

    known = {command.name for command in commands}
    shorts = {command.short: command.name for command in commands}
    retired_identifiers = {
        identifier
        for retirement in retirements
        for identifier in (*retirement.identifiers, *retirement.configuration_keys)
    }
    retired_command_names = {
        identifier
        for retirement in retirements
        for identifier in retirement.identifiers
    }
    retired_targets = {
        target for retirement in retirements for target in retirement.installed_targets
    }
    findings = _validate_allowances(allowances, retired_identifiers)
    matched_allowances: set[tuple[str, str]] = set()
    suppressed = 0

    text_paths = _text_paths(root)
    for path in text_paths:
        relative = path.relative_to(root).as_posix()
        text = _read_text(path)
        lines = text.splitlines()
        for retirement in () if relative == "manifest.json" else retirements:
            for identifier in retirement.identifiers:
                pattern = _token_pattern(identifier)
                for line_number, line in enumerate(lines, start=1):
                    if not pattern.search(line):
                        continue
                    matching = [
                        allowance
                        for allowance in allowances
                        if _allowance_matches(allowance, identifier, relative)
                    ]
                    if matching:
                        suppressed += 1
                        matched_allowances.update(
                            (allowance.identifier, allowance.path_pattern)
                            for allowance in matching
                        )
                        continue
                    findings.append(
                        Finding(
                            category="retired_identifier_live",
                            identifier=identifier,
                            path=relative,
                            line=line_number,
                            message="retired identifier appears in live content",
                            suggestion=(
                                "remove it or add a bounded reasoned historical allowance"
                            ),
                        )
                    )
            for config_key in retirement.configuration_keys:
                pattern = _token_pattern(config_key)
                for line_number, line in enumerate(lines, start=1):
                    if not pattern.search(line):
                        continue
                    matching = [
                        allowance
                        for allowance in allowances
                        if _allowance_matches(allowance, config_key, relative)
                    ]
                    if matching:
                        suppressed += 1
                        matched_allowances.update(
                            (allowance.identifier, allowance.path_pattern)
                            for allowance in matching
                        )
                        continue
                    findings.append(
                        Finding(
                            category="stale_configuration_key",
                            identifier=config_key,
                            path=relative,
                            line=line_number,
                            message="retired configuration key appears in live content",
                            suggestion="remove the key or register bounded migration history",
                        )
                    )

        command_name = _path_command(relative, shorts)
        if command_name and command_name not in known:
            category = (
                "retired_identifier_live"
                if command_name in retired_command_names or relative in retired_targets
                else "unregistered_public_target"
            )
            findings.append(
                Finding(
                    category=category,
                    identifier=command_name,
                    path=relative,
                    line=1,
                    message="public command path has no live registry row",
                    suggestion="register the command or remove the public path",
                )
            )

    for allowance in allowances:
        allowance_key = (allowance.identifier, allowance.path_pattern)
        if allowance_key not in matched_allowances and not any(
            finding.category == "invalid_allowance"
            and finding.identifier == allowance.identifier
            and finding.path == allowance.path_pattern
            for finding in findings
        ):
            findings.append(
                Finding(
                    category="invalid_allowance",
                    identifier=allowance.identifier,
                    path=allowance.path_pattern,
                    line=1,
                    message="allowance matched no retired occurrence",
                    suggestion="remove the stale allowance or narrow it to live history",
                )
            )

    for command in commands:
        if not command.target_families:
            findings.append(
                Finding(
                    category="generated_registry_mismatch",
                    identifier=command.name,
                    path="installer/registry.py",
                    line=1,
                    message="registered command has no generated target families",
                    suggestion="declare its generated target families",
                )
            )
        for relative in _required_source_paths(command):
            if not (root / relative).is_file():
                findings.append(
                    Finding(
                        category="live_identifier_missing_target",
                        identifier=command.name,
                        path=relative,
                        line=1,
                        message="registered command source or generated target is missing",
                        suggestion="restore the source and regenerate command surfaces",
                    )
                )

    for retirement in retirements:
        if not retirement.source_paths_must_be_absent:
            continue
        for relative in retirement.installed_targets:
            if (root / relative).exists():
                findings.append(
                    Finding(
                        category="retired_identifier_live",
                        identifier=retirement.id,
                        path=relative,
                        line=1,
                        message="retired installed target exists in the source checkout",
                        suggestion="remove the obsolete generated target",
                    )
                )

    findings.extend(_manifest_findings(root, commands, retirements, source_only))
    ordered = tuple(
        sorted(
            findings,
            key=lambda item: (
                item.path,
                item.line,
                item.category,
                item.identifier,
                item.message,
            ),
        )
    )
    return LintReport(
        files_scanned=len(text_paths), suppressed=suppressed, findings=ordered
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PACK_ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = lint_repository(args.root)
    except SurfaceLintError as exc:
        print(f"command-surface-lint error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.as_json(), indent=2, sort_keys=True))
    elif report.findings:
        for finding in report.findings:
            print(
                f"{finding.path}:{finding.line}: {finding.category}: "
                f"{finding.identifier}: {finding.message}; {finding.suggestion}",
                file=sys.stderr,
            )
        print(
            f"command surface drift: {len(report.findings)} finding(s), "
            f"{report.suppressed} allowed historical occurrence(s)",
            file=sys.stderr,
        )
    else:
        print(
            f"command surface drift: clean; {report.files_scanned} files scanned, "
            f"{report.suppressed} allowed historical occurrence(s)"
        )
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
