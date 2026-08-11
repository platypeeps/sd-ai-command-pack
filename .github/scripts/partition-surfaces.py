#!/usr/bin/env python3
"""Partition every manifest payload row into exactly one deployment surface.

Dev-side tooling (run via `make generate`); consumers never execute this
script. It reads `manifest.json` and `installer/registry.py`
`PLATFORM_REGISTRY` and emits the committed artifact
`docs/fleet/surface-partition.json`, assigning each manifest row one of four
categories:

- `machine-claude`: installed once per machine through the Claude Code
  plugin (Claude payload plus the shared `scripts/` toolchain shipped as
  plugin executables).
- `machine-other`: installed once per machine by the non-Claude machine
  installer (shared payload remainder plus the machine-dispositioned
  non-Claude platforms).
- `repo-native`: stays vendored per consumer repository, either by
  construction (`github` workflows/prompts) or because the platform has no
  machine-scope mechanism.
- `consumer-config`: small per-repo configuration a consumer keeps
  regardless of where the payload lives (`.claude/rules`, the contract
  document its rules link, and the review-provider repo configs).

`pack-only` is not a category here: it is the definitional complement.
Repository files outside `manifest.json` are never shipped, so they need no
inventory.

Classification is computed by rule, never from a hand-maintained path list.
Rules are evaluated in order, first match wins:

1. Target-path overrides (`TARGET_OVERRIDES`) — a small reviewed table for
   rows whose destination, not whose platform, decides the category.
2. Platform disposition (`PLATFORM_DISPOSITIONS`) — one `machine` or
   `repo-native` entry per `PLATFORM_REGISTRY` key, enumerated at runtime.
3. Hard error. Platform disposition alone would be a catch-all that can
   never fail, so three independent conditions keep the gate reachable: a
   row whose platform is not a registry key, a row whose `kind` is outside
   `KNOWN_KINDS` (a new manifest kind must be classified deliberately, not
   absorbed), and a target-path override that matches zero rows.

Three flags in the emitted schema carry contracts for downstream consumers
(the plugin build, the machine installer payload, and migration tooling):

- `provisional: true` on a platform means its machine disposition has not
  been verified yet. Consumers must fail closed and treat the platform as
  not installable machine-scope — effectively repo-native — until the
  machine-installer work flips the flag.
- `sharedRuntime: true` on a file means non-Claude surfaces invoke it at
  runtime even though its primary category is `machine-claude`. The machine
  installer consumes the `machine-other` slice plus every `sharedRuntime`
  row; the primary category stays exclusive.
- `retainVendoredFor: [<platform-id>...]` on a machine platform names the
  platforms that still read that platform's rows repo-locally. Migration
  tooling must keep the rows vendored in any consumer that serves a listed
  platform. The field is optional and absent on platforms with no such
  dependants.

`--check` regenerates the artifact in memory and byte-compares it against
the committed file, exiting nonzero on drift. The default mode writes it.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import Sequence

PACK_ROOT = Path(__file__).resolve().parents[2]
if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from installer.registry import PLATFORM_REGISTRY  # noqa: E402

MANIFEST_PATH = "manifest.json"
PARTITION_PATH = "docs/fleet/surface-partition.json"
SCHEMA_VERSION = 1

MACHINE_CLAUDE = "machine-claude"
MACHINE_OTHER = "machine-other"
REPO_NATIVE = "repo-native"
CONSUMER_CONFIG = "consumer-config"
CATEGORIES = (MACHINE_CLAUDE, MACHINE_OTHER, REPO_NATIVE, CONSUMER_CONFIG)

# Every manifest `kind` in use today. Deliberately independent of
# `installer.manifest.KNOWN_MANIFEST_KINDS`: that set is what install
# accepts, this one is what has been given a deployment category. A kind
# outside this set is a hard error rather than a silent fall-through to
# platform disposition, so a new payload shape (`agent` is registered for
# install but ships zero rows today) has to be classified here before it
# can ship.
KNOWN_KINDS = frozenset(
    {
        "skill",
        "command",
        "prompt",
        "workflow",
        "script",
        "config",
        "doc",
        "managed-block",
    }
)

# Rows whose destination decides the category regardless of platform.
# Patterns are fnmatch globs against the manifest `target`; `*` spans path
# separators, so a `**` suffix matches everything below the directory. Each
# pattern must match at least one manifest row or the gate fails (stale
# override).
TARGET_OVERRIDES: tuple[tuple[str, str, bool], ...] = (
    # Consumer-kept repo configuration.
    (".claude/rules/**", CONSUMER_CONFIG, False),
    # The contract document `.claude/rules` links as a repo-relative sibling.
    (".claude/sd-ai-command-pack/**", CONSUMER_CONFIG, False),
    # Review-provider repo configs.
    (".prism/**", CONSUMER_CONFIG, False),
    (".gito/**", CONSUMER_CONFIG, False),
    # The shared toolchain ships as plugin executables, but non-Claude
    # surfaces call these scripts at runtime, so they are also part of the
    # machine installer payload (`sharedRuntime`).
    ("scripts/**", MACHINE_CLAUDE, True),
)

MACHINE = "machine"

# One entry per PLATFORM_REGISTRY key; both directions are checked at
# runtime, so a new registry platform without an entry fails and an entry
# for a removed platform fails. `provisional` marks a machine disposition
# whose installer mechanism is not verified yet.
PLATFORM_DISPOSITIONS: dict[str, tuple[str, bool]] = {
    # Verified: the Claude Code plugin is itself the machine mechanism.
    "claude": (MACHINE, False),
    # Verified by executed user-scope probes against the installed CLIs;
    # see the machine-installer task research (`platform-probes.md`).
    # `shared` is verified through OpenCode's `~/.agents/skills` autoload.
    "shared": (MACHINE, False),
    "gemini": (MACHINE, False),
    "opencode": (MACHINE, False),
    # Repo-native, not provisional: the Codex binary resolves `.agents`
    # against the project root and never reads `~/.agents/skills`; its user
    # root is `$CODEX_HOME/skills`, a target family the pack does not ship.
    "codex": (REPO_NATIVE, False),
    # Repo-native by construction: GitHub reads workflows and prompts from
    # the consumer repository itself.
    "github": (REPO_NATIVE, False),
    # Repo-local-only platforms: no machine-scope mechanism.
    "antigravity": (REPO_NATIVE, False),
    "codebuddy": (REPO_NATIVE, False),
    "cursor": (REPO_NATIVE, False),
    "devin": (REPO_NATIVE, False),
    "droid": (REPO_NATIVE, False),
    "kilo": (REPO_NATIVE, False),
    "kiro": (REPO_NATIVE, False),
    "pi": (REPO_NATIVE, False),
    "qoder": (REPO_NATIVE, False),
    "reasonix": (REPO_NATIVE, False),
    "trae": (REPO_NATIVE, False),
    "zcode": (REPO_NATIVE, False),
}


# Machine platforms whose rows another platform still reads repo-locally.
# `shared` ships `.agents/**`, which OpenCode autoloads from the user scope
# but Codex and Pi resolve against the project root, so those two keep
# needing a vendored copy. Migration tooling reads this list; the executable
# detection rule is documented in the spec and in the emitted artifact's
# consumers: a consumer still serves a listed platform iff its
# `docs/fleet/consumers.json` `platforms` array intersects the list.
PLATFORM_RETAIN_VENDORED_FOR: dict[str, tuple[str, ...]] = {
    "shared": ("codex", "pi"),
}


class PartitionError(Exception):
    """Fail-closed condition in the surface partition."""


def load_manifest(root: Path) -> dict[str, object]:
    path = root / MANIFEST_PATH
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PartitionError(f"manifest not found: {path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise PartitionError(f"manifest is unreadable: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PartitionError(f"manifest is not valid JSON: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise PartitionError(f"manifest is not a JSON object: {path}")
    return loaded


def validate_dispositions(
    dispositions: dict[str, tuple[str, bool]],
    registry: dict[str, object],
) -> None:
    """Both directions: no registry platform unclassified, no stale entry."""
    missing = sorted(set(registry) - set(dispositions))
    if missing:
        raise PartitionError(
            "platform without a scope disposition: "
            + ", ".join(missing)
            + " (add an entry to PLATFORM_DISPOSITIONS)"
        )
    stale = sorted(set(dispositions) - set(registry))
    if stale:
        raise PartitionError(
            "stale disposition entry for platform not in PLATFORM_REGISTRY: "
            + ", ".join(stale)
        )
    for platform, (scope, _provisional) in sorted(dispositions.items()):
        if scope not in (MACHINE, REPO_NATIVE):
            raise PartitionError(
                f"platform {platform} has unknown scope disposition {scope!r}; "
                f"expected {MACHINE!r} or {REPO_NATIVE!r}"
            )


def validate_retentions(
    retentions: dict[str, tuple[str, ...]],
    dispositions: dict[str, tuple[str, bool]],
) -> None:
    """Retention lists name real platforms and only qualify machine rows."""
    for platform, dependants in sorted(retentions.items()):
        if platform not in dispositions:
            raise PartitionError(
                f"retainVendoredFor names platform {platform!r}, which has no "
                "PLATFORM_DISPOSITIONS entry"
            )
        scope, _provisional = dispositions[platform]
        if scope != MACHINE:
            raise PartitionError(
                f"platform {platform} is {scope!r}, so its rows already stay "
                "vendored; retainVendoredFor is meaningless there"
            )
        if not dependants:
            raise PartitionError(
                f"platform {platform} has an empty retainVendoredFor list; "
                "drop the entry instead"
            )
        if len(set(dependants)) != len(dependants):
            raise PartitionError(
                f"platform {platform} repeats a platform in retainVendoredFor"
            )
        unknown = sorted(set(dependants) - set(dispositions))
        if unknown:
            raise PartitionError(
                f"platform {platform} retains rows for unknown platform(s): "
                + ", ".join(unknown)
            )


def override_category(target: str) -> tuple[str, str, bool] | None:
    """First matching override as (pattern, category, sharedRuntime)."""
    for pattern, category, shared_runtime in TARGET_OVERRIDES:
        if fnmatch.fnmatchcase(target, pattern):
            return pattern, category, shared_runtime
    return None


def platform_category(platform: str, dispositions: dict[str, tuple[str, bool]]) -> str:
    scope, _provisional = dispositions[platform]
    if scope == REPO_NATIVE:
        return REPO_NATIVE
    return MACHINE_CLAUDE if platform == "claude" else MACHINE_OTHER


def classify_rows(
    rows: Sequence[dict[str, object]],
    dispositions: dict[str, tuple[str, bool]],
    registry: dict[str, object],
) -> list[dict[str, object]]:
    classified: list[dict[str, object]] = []
    matched_overrides: set[str] = set()
    for row in rows:
        target = str(row.get("target", ""))
        platform = str(row.get("platform", ""))
        kind = str(row.get("kind", ""))
        if not target:
            raise PartitionError(f"manifest row without a target: {row!r}")
        if platform not in registry:
            raise PartitionError(
                f"unknown platform {platform!r} for manifest target {target}; "
                "not a PLATFORM_REGISTRY key"
            )
        if kind not in KNOWN_KINDS:
            raise PartitionError(
                f"unclassified manifest kind {kind!r} for target {target}; "
                "give the kind a deployment category by adding it to "
                "KNOWN_KINDS in .github/scripts/partition-surfaces.py"
            )
        override = override_category(target)
        if override is not None:
            pattern, category, shared_runtime = override
            matched_overrides.add(pattern)
        else:
            category = platform_category(platform, dispositions)
            shared_runtime = False
        classified.append(
            {
                "target": target,
                "platform": platform,
                "category": category,
                "sharedRuntime": shared_runtime,
            }
        )
    unmatched = [
        pattern
        for pattern, _category, _shared in TARGET_OVERRIDES
        if pattern not in matched_overrides
    ]
    if unmatched:
        raise PartitionError(
            "stale target-path override matching zero manifest rows: "
            + ", ".join(unmatched)
        )
    return classified


def build_partition(root: Path) -> dict[str, object]:
    manifest = load_manifest(root)
    raw_rows = manifest.get("files")
    if not isinstance(raw_rows, list):
        raise PartitionError("manifest has no `files` list")
    rows = [row for row in raw_rows if isinstance(row, dict)]
    if len(rows) != len(raw_rows):
        raise PartitionError("manifest `files` holds a non-object entry")

    validate_dispositions(PLATFORM_DISPOSITIONS, dict(PLATFORM_REGISTRY))
    validate_retentions(PLATFORM_RETAIN_VENDORED_FOR, PLATFORM_DISPOSITIONS)
    files = classify_rows(rows, PLATFORM_DISPOSITIONS, dict(PLATFORM_REGISTRY))
    files.sort(key=lambda entry: str(entry["target"]))

    counts = {category: 0 for category in CATEGORIES}
    for entry in files:
        counts[str(entry["category"])] += 1

    platforms: dict[str, dict[str, object]] = {}
    for platform, (scope, provisional) in sorted(PLATFORM_DISPOSITIONS.items()):
        disposition: dict[str, object] = {"scope": scope, "provisional": provisional}
        retained = PLATFORM_RETAIN_VENDORED_FOR.get(platform)
        if retained:
            disposition["retainVendoredFor"] = sorted(retained)
        platforms[platform] = disposition
    return {
        "schemaVersion": SCHEMA_VERSION,
        "manifestVersion": str(manifest.get("version", "")),
        "platforms": platforms,
        "counts": counts,
        "files": files,
    }


def render_partition(root: Path) -> str:
    return json.dumps(build_partition(root), indent=2) + "\n"


def run_check(root: Path, content: str) -> int:
    committed = root / PARTITION_PATH
    if not committed.is_file():
        print(
            f"error: {PARTITION_PATH} is missing; run `make generate`",
            file=sys.stderr,
        )
        return 1
    if committed.read_bytes() != content.encode("utf-8"):
        print(f"drift: {PARTITION_PATH}", file=sys.stderr)
        print(
            f"error: {PARTITION_PATH} drifts from the manifest and registry; "
            "run `make generate`",
            file=sys.stderr,
        )
        return 1
    print(f"check: {PARTITION_PATH} matches the committed tree")
    return 0


def write_partition(root: Path, content: str) -> int:
    destination = root / PARTITION_PATH
    if destination.is_file() and destination.read_bytes() == content.encode("utf-8"):
        print(f"unchanged: {PARTITION_PATH}")
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    print(f"wrote: {PARTITION_PATH}")
    return 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Partition manifest.json payload rows into deployment surfaces "
            "and emit docs/fleet/surface-partition.json."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Regenerate in memory and byte-compare against the committed "
            "artifact instead of writing it; exit 1 on drift"
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=PACK_ROOT,
        help="pack root to read and write; defaults to the repository root",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root).resolve()
    try:
        content = render_partition(root)
    except PartitionError as exc:
        print(f"partition-surfaces error: {exc}", file=sys.stderr)
        return 1
    if args.check:
        return run_check(root, content)
    return write_partition(root, content)


if __name__ == "__main__":
    raise SystemExit(main())
