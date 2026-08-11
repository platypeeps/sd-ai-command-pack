"""The plan phase of a thin conversion: verdict binding and the settings merge.

Everything here answers "may this conversion proceed, and what exactly would
it write" without writing anything. The separation is the contract, not a
style preference: `design.md` §3 fixes the write order precisely because
there is no rollback, and every refusal in this task is required to happen
before the first byte lands.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from installer.registry import PACK_REPOSITORY

# The verdict document's `repo` records where the resweep found the checkout.
# A conversion run against the same tree by a different path -- a symlinked
# home, a worktree, `--repo` versus `pathHint` -- is the same tree, and every
# field that actually describes its contents is compared. Excluding the path
# is what keeps the binding about the tree rather than about the spelling.
BINDING_EXEMPT_FIELDS = frozenset({"repo"})

MARKETPLACE_KEY = "extraKnownMarketplaces"
PLUGINS_KEY = "enabledPlugins"

VERDICT_MISSING = "missing"
VERDICT_UNREADABLE = "unreadable"
VERDICT_PRESENT = "present"


@dataclass(frozen=True)
class VerdictLoad:
    """A verdict file's bytes and why they could not be used, if they could not.

    `missing` and `unreadable` are separate states because the operator
    responses differ: one means "run the resweep", the other means "the file
    you archived is not the file you think it is".
    """

    state: str
    document: dict | None = None
    detail: str | None = None


def load_verdict(path: Path) -> VerdictLoad:
    if not path.is_file():
        return VerdictLoad(
            state=VERDICT_MISSING,
            detail=f"{path} does not exist; run the thin resweep first",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return VerdictLoad(
            state=VERDICT_UNREADABLE,
            detail=f"{path} cannot be read as a verdict document: {error}",
        )
    if not isinstance(payload, dict):
        return VerdictLoad(
            state=VERDICT_UNREADABLE,
            detail=f"{path} is not a verdict document: expected an object",
        )
    return VerdictLoad(state=VERDICT_PRESENT, document=payload)


def verdict_binding_reasons(archived: dict, fresh: dict) -> tuple[str, ...]:
    """Why this archived verdict does not authorize this conversion.

    The comparison is whole-document rather than field-by-field, and that is
    deliberate. A named list of binding fields is a list somebody has to
    remember to extend: the resweep already grew `indexFlagsDigest`,
    `hiddenBytesDigest`, `symlinkTargetsDigest`, and `platformMarkerDigest`
    across four review rounds, and each was added because an earlier named
    list had missed the state it covers. Comparing everything means a field
    added to the resweep tomorrow binds tomorrow, with no edit here.

    `fresh` is produced by re-running the resweep against the consumer, so
    the classifier inputs are covered too: a partition, registry, builder, or
    resweep edit between sweep and conversion moves `classifierDigest`.
    """
    reasons: list[str] = []
    if archived.get("kind") != "thin-resweep-verdict":
        return (
            f"not a thin resweep verdict: kind is {archived.get('kind')!r}",
        )
    if archived.get("schemaVersion") != fresh.get("schemaVersion"):
        return (
            f"verdict schema version {archived.get('schemaVersion')!r} is not "
            f"the {fresh.get('schemaVersion')!r} this installer writes",
        )
    if archived.get("verdict") != "clear":
        reasons.append(
            "verdict is "
            f"{archived.get('verdict')!r}: "
            + "; ".join(str(reason) for reason in archived.get("reasons") or ())
        )
    for key in sorted(set(archived) | set(fresh)):
        if key in BINDING_EXEMPT_FIELDS:
            continue
        if key not in archived:
            reasons.append(f"verdict is missing {key}, which the resweep records")
        elif key not in fresh:
            reasons.append(f"verdict records {key}, which the resweep no longer does")
        elif archived[key] != fresh[key]:
            reasons.append(f"{key} changed since the resweep")
    return tuple(reasons)


def normalize_github_remote(url: str) -> str | None:
    """`<owner>/<name>` for a GitHub remote, or None for anything else.

    Non-GitHub hosts return None rather than a normalized slug: the locator
    written into a consumer says `"source": "github"`, so a GitLab remote is
    not a different spelling of the same thing, it is a different claim.
    """
    text = url.strip()
    if not text:
        return None
    if text.startswith("git@") or (
        "://" not in text and ":" in text and "/" in text.split(":", 1)[1]
    ):
        host, _, path = text.partition(":")
        host = host.rpartition("@")[2]
    else:
        parsed = urlsplit(text)
        if parsed.scheme not in {"https", "http", "ssh", "git"}:
            return None
        # Strip any userinfo: `https://token@github.com/...` is the same host.
        host = parsed.netloc.rpartition("@")[2].partition(":")[0]
        path = parsed.path
    if host.lower() != "github.com":
        return None
    segments = [segment for segment in path.strip("/").split("/") if segment]
    if len(segments) != 2:
        return None
    owner, name = segments
    return f"{owner}/{name.removesuffix('.git')}"


def pack_repository_reason(origin_url: str | None) -> str | None:
    """Why this pack checkout may not name itself as a marketplace source.

    R18-C3: the check is exact equality against `PACK_REPOSITORY`, not an
    owner match. An owner-only rule accepts
    `platypeeps/sd-ai-command-pack-fork` and writes that locator into every
    consumer in the fleet, where it stays until somebody reads a settings
    file by hand.
    """
    if origin_url is None:
        return (
            "this pack checkout has no `origin` remote, so the marketplace "
            f"source cannot be validated against {PACK_REPOSITORY}"
        )
    slug = normalize_github_remote(origin_url)
    if slug is None:
        return (
            f"`origin` ({origin_url}) is not a GitHub repository URL; the "
            "marketplace locator this conversion writes claims one"
        )
    if slug != PACK_REPOSITORY:
        return (
            f"this pack checkout is {slug}, not {PACK_REPOSITORY}; converting "
            "from it would point every consumer at the wrong marketplace"
        )
    return None


def settings_additions(marketplace_name: str, plugin_name: str) -> dict:
    """The exact additions a conversion merges, derived rather than hardcoded.

    Both names are read from the shipped manifests -- `marketplace.json` and
    `plugins/sd/.claude-plugin/plugin.json` -- so renaming either in one place
    cannot leave consumers enabling a plugin that no longer exists. Both
    manifests are classifier-digest inputs, so a rename also invalidates every
    outstanding verdict.

    No `autoUpdate` key: a consumer's update cadence is the consumer's.
    """
    return {
        MARKETPLACE_KEY: {
            marketplace_name: {
                "source": {"source": "github", "repo": PACK_REPOSITORY}
            }
        },
        PLUGINS_KEY: {f"{plugin_name}@{marketplace_name}": True},
    }


@dataclass(frozen=True)
class SettingsPlan:
    """What the settings merge would write, computed before it writes it."""

    path: Path
    merged: dict
    # Only what this conversion actually adds. An entry already present with
    # the right value is absent here on purpose: `settingsAdditions` is the
    # record a revert undoes, and undoing something the consumer set for
    # itself is the failure mode that record exists to prevent.
    additions: dict = field(default_factory=dict)
    created_file: bool = False
    created_containers: tuple[str, ...] = ()

    @property
    def writes_anything(self) -> bool:
        return bool(self.additions) or self.created_file


def plan_settings_merge(
    settings_path: Path,
    marketplace_name: str,
    plugin_name: str,
) -> tuple[SettingsPlan | None, str | None]:
    """Return `(plan, None)` or `(None, reason)` -- never a partial write.

    Every row of `design.md` §4's collision table blocks rather than
    overwrites. The file is consumer-owned: zero partition rows, no pack
    ownership proof available, and no way to tell a deliberate `false` from a
    stale one. Blocking costs an operator one edit; guessing costs them a
    setting they chose.
    """
    desired = settings_additions(marketplace_name, plugin_name)
    created_file = False
    if not settings_path.exists():
        existing: dict = {}
        created_file = True
    elif settings_path.is_symlink():
        return None, f"{settings_path} is a symlink; refusing to write through it"
    else:
        try:
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return None, f"{settings_path} cannot be read as JSON: {error}"
        if not isinstance(payload, dict):
            return None, (
                f"{settings_path} is a JSON {type(payload).__name__}, not an "
                "object; refusing to replace it"
            )
        existing = payload

    merged = json.loads(json.dumps(existing))
    additions: dict = {}
    created_containers: list[str] = []

    for container, entries in desired.items():
        current = merged.get(container)
        if container not in merged:
            merged[container] = {}
            created_containers.append(container)
            current = merged[container]
        elif not isinstance(current, dict):
            return None, (
                f"{settings_path}: {container} is a "
                f"{type(current).__name__}, not an object"
            )
        for key, value in entries.items():
            if key not in current:
                current[key] = value
                additions.setdefault(container, {})[key] = value
            elif current[key] != value:
                return None, (
                    f"{settings_path}: {container}[{key!r}] is already set to "
                    f"{json.dumps(current[key], sort_keys=True)}, which is not "
                    f"{json.dumps(value, sort_keys=True)}"
                )
            # Equal already: nothing to add, and deliberately nothing recorded.

    return (
        SettingsPlan(
            path=settings_path,
            merged=merged,
            additions=additions,
            created_file=created_file,
            created_containers=tuple(created_containers),
        ),
        None,
    )


def render_settings(merged: dict) -> str:
    return json.dumps(merged, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# The write phase.
# ---------------------------------------------------------------------------

# R20-C3. The write order rewrites the receipts *before* deleting the payload,
# so from the moment the pin lands the receipt no longer lists what is still
# on disk waiting to be deleted. An interrupted conversion re-run therefore
# recomputes its plan from a receipt that has already forgotten the remainder,
# and "re-running converges" -- which the design's recovery table promises for
# four of its five interrupted states -- is false without a second record.
#
# This is that record: written with the receipts, in the same step, naming
# every path the conversion still intends to remove. A re-run reads it, so the
# remainder is enumerated from what the interrupted run recorded rather than
# rediscovered from a receipt that can no longer describe it. It is deleted
# last, after the removals it authorizes, so its presence means unfinished.
REMOVAL_INVENTORY_FILE = Path(".sd-ai-command-pack/pending-removal.json")

REMOVAL_INVENTORY_KIND = "thin-conversion-pending-removal"


def removal_inventory_content(
    *, delete: tuple[str, ...], retire: tuple[str, ...], block_strip: tuple[str, ...]
) -> str:
    return (
        json.dumps(
            {
                "schemaVersion": 1,
                "kind": REMOVAL_INVENTORY_KIND,
                "delete": sorted(delete),
                "retire": sorted(retire),
                "blockStrip": sorted(block_strip),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def read_removal_inventory(target: Path) -> dict | None:
    """The unfinished conversion's remainder, or None when there is none.

    Fails closed to `None` on anything unreadable: a caller that gets `None`
    plans from the receipt, which is the pre-R20-C3 behavior and is correct
    whenever no interruption happened. Returning a partial inventory would be
    worse than returning none, because the remainder it names would be a
    subset presented as the whole.
    """
    path = target / REMOVAL_INVENTORY_FILE
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("kind") != REMOVAL_INVENTORY_KIND:
        return None
    if payload.get("schemaVersion") != 1:
        return None
    buckets = ("delete", "retire", "blockStrip")
    if not all(
        isinstance(payload.get(bucket), list)
        and all(isinstance(entry, str) for entry in payload[bucket])
        for bucket in buckets
    ):
        return None
    return payload


def residual_provenance_files(
    existing_files: dict[str, str], residual: frozenset[str]
) -> dict[str, str]:
    """The provenance `files` map narrowed to the residual payload.

    Derived from the pre-conversion receipt minus what was removed -- never
    from the partition's kept rows. The partition describes what the pack
    ships (557 keep rows); the receipt describes what this consumer has (26 of
    them). Building the residual from the former writes a receipt vouching for
    files that are not there.
    """
    return {
        target: digest
        for target, digest in sorted(existing_files.items())
        if target in residual
    }


def thin_provenance_content(
    manifest: dict,
    *,
    files: dict[str, str],
    platforms: tuple[str, ...],
    consumer: str | None,
    additions: dict,
    forced: tuple[str, ...],
) -> str:
    payload: dict = {
        "pack": manifest["name"],
        "version": manifest["version"],
        "mode": "thin",
        "platforms": list(platforms),
    }
    if consumer is not None:
        payload["consumer"] = consumer
    payload["settingsAdditions"] = additions
    payload["forced"] = list(forced)
    payload["files"] = dict(sorted(files.items()))
    return json.dumps(payload, indent=2) + "\n"


def thin_manifest_content(manifest: dict) -> str:
    """The installed pack manifest, carrying the durable thin marker.

    This is the earlier of the two thin witnesses (`thin_pin_state` reads it
    first), so a conversion interrupted between the receipt writes still
    leaves a consumer that reads as thin rather than as fat-with-a-narrowed-
    payload.
    """
    return json.dumps({**manifest, "mode": "thin"}, indent=2) + "\n"


def residual_targets_content(residual: frozenset[str]) -> str:
    return "\n".join(sorted(residual)) + "\n"


__all__ = [
    "REMOVAL_INVENTORY_FILE",
    "REMOVAL_INVENTORY_KIND",
    "BINDING_EXEMPT_FIELDS",
    "MARKETPLACE_KEY",
    "PLUGINS_KEY",
    "SettingsPlan",
    "VERDICT_MISSING",
    "VERDICT_PRESENT",
    "VERDICT_UNREADABLE",
    "VerdictLoad",
    "load_verdict",
    "normalize_github_remote",
    "pack_repository_reason",
    "plan_settings_merge",
    "read_removal_inventory",
    "removal_inventory_content",
    "render_settings",
    "residual_provenance_files",
    "residual_targets_content",
    "settings_additions",
    "thin_manifest_content",
    "thin_provenance_content",
    "verdict_binding_reasons",
]
