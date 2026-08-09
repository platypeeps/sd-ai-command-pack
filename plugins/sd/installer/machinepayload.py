"""Machine-scope payload model: destination families, partition gate, digest.

Shared by the machine installer engine (`installer.machinescope`) and by the
plugin generator that bundles the same payload under the plugin root, so the
family table, the executable rule, and the payload digest have exactly one
implementation. A payload root is a target-relative tree (`.agents/skills/...`,
`scripts/...`, `docs/...`, `.gemini/commands/...`, `.opencode/commands/...`)
plus the `partition.json` copy that gates it.

Nothing here raises: an unmapped target returns `None` and a gate violation
returns a reason string, because the two callers report failures in their own
error models (the generator fails the build, the engine exits the CLI).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PARTITION_FILE = "partition.json"
MACHINE_OTHER = "machine-other"
MACHINE_SCOPE = "machine"

# Library modules are imported by their installed siblings, never invoked as
# commands; the plugin generator applies the same rule to its own bin/.
LIBRARY_PREFIX = "sd_ai_command_pack_"

DIGEST_DOMAIN = b"sd-ai-command-pack-machine-payload-v1\0"


@dataclass(frozen=True)
class DestinationFamily:
    """One machine destination root and the payload prefix that feeds it.

    `root_parts` is resolved against the user's home directory, except for
    `opencode-commands`, whose root is XDG-derived (see `family_roots`).
    """

    name: str
    prefix: str
    executable: bool


# Prefixes are the exact subtrees the pack ships. A future `.agents/agents/`
# row matches no family and fails closed rather than landing somewhere by
# accident, which is what keeps the two inventories from drifting silently.
FAMILIES: tuple[DestinationFamily, ...] = (
    DestinationFamily("agents-skills", ".agents/skills/", False),
    DestinationFamily("agents-bin", "scripts/", True),
    DestinationFamily("agents-docs", "docs/", False),
    DestinationFamily("gemini-commands", ".gemini/commands/", False),
    DestinationFamily("opencode-commands", ".opencode/commands/", False),
)
FAMILIES_BY_NAME: dict[str, DestinationFamily] = {
    family.name: family for family in FAMILIES
}


@dataclass(frozen=True)
class PayloadEntry:
    """One payload file: where it came from, where it lands, and its identity."""

    target: str
    family: DestinationFamily
    relative: str
    content: bytes
    executable: bool

    @property
    def digest(self) -> str:
        return content_digest(self.content)


def content_digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def family_for_target(target: str) -> DestinationFamily | None:
    """The destination family for a payload-relative target, or None."""

    for family in FAMILIES:
        if target.startswith(family.prefix) and len(target) > len(family.prefix):
            return family
    return None


def entry_is_executable(family: DestinationFamily, relative: str) -> bool:
    """Executable bit for a payload file, derived from the family, not the mode.

    Deriving it keeps the payload digest identical across checkouts that lost
    their mode bits, and mirrors the plugin generator's bin/ rule so a script
    and its library land with the same modes under both roots.
    """

    if not family.executable:
        return False
    return not PurePosixPath(relative).name.startswith(LIBRARY_PREFIX)


def family_roots(*, home: Path, environ: Mapping[str, str]) -> dict[str, Path]:
    """Absolute destination root per family for one machine.

    OpenCode reads its global commands from the XDG config root, so that root
    is honored rather than a hardcoded `~/.config`; every other family hangs
    off the home directory.
    """

    agents = home / ".agents"
    config_home = home / ".config"
    xdg = environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        candidate = Path(xdg).expanduser()
        if candidate.is_absolute():
            config_home = candidate
    return {
        "agents-skills": agents / "skills",
        "agents-bin": agents / "bin",
        "agents-docs": agents / "docs",
        "gemini-commands": home / ".gemini" / "commands",
        "opencode-commands": config_home / "opencode" / "commands",
    }


def payload_digest(entries: Sequence[PayloadEntry]) -> str:
    """Canonical payload identity: sorted targets, executable bits, contents.

    Domain-separated and order-independent, so the generator can stamp the
    digest of what it bundles and the installer can record the digest of what
    it wrote and have the two compare equal.

    Deliberately not the release-candidate digest in
    `sd_ai_command_pack_fleet_lib`: that one identifies a manifest plus the
    sources it names, this one identifies an installed tree of target paths.
    The domains differ so the two can never be compared by accident.
    """

    digest = hashlib.sha256()
    digest.update(DIGEST_DOMAIN)
    for entry in sorted(entries, key=lambda item: item.target):
        digest.update(entry.target.encode("utf-8"))
        digest.update(b"\0x\0" if entry.executable else b"\0-\0")
        digest.update(hashlib.sha256(entry.content).digest())
    return f"sha256:{digest.hexdigest()}"


@dataclass(frozen=True)
class PartitionGate:
    """The machine-payload admission rules read from a bundled partition copy."""

    pack_version: str
    rows: dict[str, tuple[str, bool, str]]
    platforms: dict[str, tuple[str, bool]]

    def reject_reason(self, target: str) -> str | None:
        """Why `target` may not be installed machine-scope, or None."""

        row = self.rows.get(target)
        if row is None:
            return "no surface-partition row"
        category, shared_runtime, platform = row
        if category != MACHINE_OTHER and not shared_runtime:
            return f"category {category} is not machine-installable"
        entry = self.platforms.get(platform)
        if entry is None:
            return f"platform {platform} has no surface-partition disposition"
        scope, provisional = entry
        if scope != MACHINE_SCOPE:
            return f"platform {platform} is {scope}, not machine-scope"
        if provisional:
            return f"platform {platform} is provisional"
        return None


def parse_partition(raw: object) -> PartitionGate | str:
    """Build the gate from parsed partition JSON, or return a reason string."""

    if not isinstance(raw, dict):
        return "partition is not a JSON object"
    version = raw.get("manifestVersion")
    if not isinstance(version, str) or not version.strip():
        return "partition has no manifestVersion"
    raw_files = raw.get("files")
    if not isinstance(raw_files, list):
        return "partition has no files array"
    raw_platforms = raw.get("platforms")
    if not isinstance(raw_platforms, dict):
        return "partition has no platforms object"
    rows: dict[str, tuple[str, bool, str]] = {}
    for row in raw_files:
        if not isinstance(row, dict):
            return "partition files holds a non-object entry"
        target = row.get("target")
        category = row.get("category")
        platform = row.get("platform")
        if not isinstance(target, str) or not isinstance(category, str):
            return "partition row has no target/category"
        if not isinstance(platform, str):
            return f"partition row {target} has no platform"
        rows[target] = (category, bool(row.get("sharedRuntime")), platform)
    platforms: dict[str, tuple[str, bool]] = {}
    for name, entry in raw_platforms.items():
        if not isinstance(entry, dict):
            return f"partition platform {name} is not an object"
        scope = entry.get("scope")
        if not isinstance(scope, str):
            return f"partition platform {name} has no scope"
        platforms[name] = (scope, bool(entry.get("provisional")))
    return PartitionGate(version.strip(), rows, platforms)


def read_partition(path: Path) -> PartitionGate | str:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"bundled partition not found: {path}"
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return f"bundled partition is unreadable: {path}: {error}"
    return parse_partition(raw)


def payload_targets(root: Path) -> list[str] | str:
    """Sorted payload-relative targets under `root`, or a reason string.

    Symlinks are refused outright: the payload is a generated tree, and a link
    inside it would let the digest describe content the installer never read.
    """

    targets: list[str] = []
    try:
        walk = sorted(root.rglob("*"))
    except OSError as error:  # pragma: no cover - rglob defers OS errors
        return f"cannot read payload root {root}: {error}"
    for path in walk:
        if path.is_symlink():
            return f"payload contains a symlink: {path.relative_to(root).as_posix()}"
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == PARTITION_FILE or "__pycache__" in path.parts:
            continue
        targets.append(relative)
    return targets


__all__ = [
    "DIGEST_DOMAIN",
    "FAMILIES",
    "FAMILIES_BY_NAME",
    "LIBRARY_PREFIX",
    "MACHINE_OTHER",
    "MACHINE_SCOPE",
    "PARTITION_FILE",
    "DestinationFamily",
    "PartitionGate",
    "PayloadEntry",
    "content_digest",
    "entry_is_executable",
    "family_for_target",
    "family_roots",
    "parse_partition",
    "payload_digest",
    "payload_targets",
    "read_partition",
]
