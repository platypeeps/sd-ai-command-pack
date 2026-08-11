"""The plan phase of a thin conversion: verdict binding and the settings merge.

Everything here answers "may this conversion proceed, and what exactly would
it write" without writing anything. The separation is the contract, not a
style preference: `design.md` §3 fixes the write order precisely because
there is no rollback, and every refusal in this task is required to happen
before the first byte lands.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from installer.fileops import remove_text_block_file
from installer.registry import (
    COPILOT_GUIDANCE_END,
    COPILOT_GUIDANCE_START,
    COPILOT_INSTRUCTIONS_TARGET,
    INSTALLED_TARGETS_FILE,
    PACK_MANIFEST_FILE,
    PACK_REPOSITORY,
    PROVENANCE_FILE,
    TRELLIS_GITIGNORE_END,
    TRELLIS_GITIGNORE_START,
    TRELLIS_GITIGNORE_TARGET,
)
from installer.removal import remove_pack_file
from installer.status import RemoveStatus

# The verdict document's `repo` records where the resweep found the checkout.
# A conversion run against the same tree by a different path -- a symlinked
# home, a worktree, `--repo` versus `pathHint` -- is the same tree, and every
# field that actually describes its contents is compared. Excluding the path
# is what keeps the binding about the tree rather than about the spelling.
BINDING_EXEMPT_FIELDS = frozenset({"repo"})

# The pack's own fleet registry. Read by revert to resolve a consumer name and
# written by both directions to record the mode; declared once so the reader
# and the writer cannot drift onto two paths.
FLEET_REGISTRY_FILE = Path("docs/fleet/consumers.json")

# The consumer-owned settings file the conversion merges into. Zero
# partition rows: the pack has never owned a byte of it.
CLAUDE_SETTINGS_FILE = Path(".claude/settings.json")

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

    @property
    def record(self) -> dict:
        """`settingsAdditions` as the receipt carries it -- the shape revert reads.

        The added pairs alone are not enough, and the revert tests are what
        found it: "remove what we added" is ambiguous at the container
        boundary. A consumer who already had an `enabledPlugins` object with
        three other plugins must keep it; one whose `enabledPlugins` we created
        must not be left holding `{}`. Recording the pairs and dropping the two
        provenance flags left revert unable to tell those apart, so it left an
        empty container behind on every conversion that created one.
        """
        return {
            **self.additions,
            "createdContainers": list(self.created_containers),
            "createdFile": self.created_file,
        }


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
    retired: tuple[str, ...],
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
    # R20-C2: written even when empty, because an absent key and an empty list
    # are the same to a reader that defaults, and revert's promise depends on
    # telling "nothing was unrestorable" from "this receipt predates the field".
    payload["retired"] = list(retired)
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


def load_resweep_module(root: Path):
    """Import the shipped resweep script as a module.

    By path, because the file name has hyphens. Importing it rather than
    reimplementing its digests is the point: the verdict's binding fields are
    whatever that script computes, so recomputing them anywhere else would be
    a second implementation to keep in step -- and `classifier_digest` hashes
    that script's bytes, so the two are already bound to each other.
    """
    import importlib.util

    path = root / "scripts/sd-ai-command-pack-thin-resweep.py"
    spec = importlib.util.spec_from_file_location("sd_thin_resweep", path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise SystemExit(f"error: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def writability_reason(root: Path, label: str) -> str | None:
    """Why this root cannot be written, checked before either root is.

    `--thin` writes the consumer *and* the pack registry. Discovering an
    unwritable registry after 166 consumer deletions is the worse ordering,
    not the safer one, so both are probed up front -- by actually creating and
    removing a file, because `os.access` answers the wrong question on a
    read-only mount and under an ACL.
    """
    if not root.is_dir():
        return f"{label} {root} is not a directory"
    probe = root / ".sd-ai-command-pack-writability-probe"
    try:
        probe.touch()
        probe.unlink()
    except OSError as error:
        return f"{label} {root} is not writable: {error}"
    return None


def version_currency_reason(
    installed_version: str | None, source_version: str
) -> str | None:
    """Why this consumer is too stale to convert.

    The cheap proxy for the real question, which is whether the receipt still
    describes what the pack ships. It is a proxy and not the answer: R19-C2
    measured a consumer whose receipt was a version behind and therefore
    missing `scripts/sd-ai-command-pack-pack-update.sh`, which the current
    manifest ships and the partition classifies as a machine row a `codex`
    consumer retains. A receipt-derived residual would convert cleanly and
    fail `--check` on the very next command, for a file the conversion never
    had a chance to keep. The exact assertion -- source-derived residual is a
    subset of the receipt-derived one -- runs alongside this, not instead.
    """
    if installed_version is None:
        return (
            "this consumer's provenance records no version, so the receipt "
            "cannot be shown to describe what the pack ships; run "
            "`install.py TARGET` first"
        )
    if installed_version != source_version:
        return (
            f"this consumer has {installed_version} installed and the pack "
            f"ships {source_version}; run `install.py TARGET` first, because a "
            "conversion plan built from a stale receipt cannot keep a file the "
            "consumer never received"
        )
    return None


def receipt_disagreement_reason(target: Path) -> str | None:
    """Why this consumer's two version-bearing receipts describe different installs.

    Narrower than `inspect_receipts` on purpose. That reports per-file content
    drift in the same list, and refusing on the whole list would make `--force`
    unreachable -- overriding removal drift is precisely what `--force` is for.
    This asks only whether the receipts agree about *which install* they
    describe, which is the input the conversion rewrites all three from.
    """
    versions: dict[str, object] = {}
    for receipt in (PACK_MANIFEST_FILE, PROVENANCE_FILE):
        path = target / receipt
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return f"{receipt.as_posix()} cannot be read: {error}"
        if not isinstance(payload, dict):
            return f"{receipt.as_posix()} is not an object"
        versions[receipt.as_posix()] = payload.get("version")
    if len(set(versions.values())) != 1:
        rendered = ", ".join(
            f"{name} says {value!r}" for name, value in sorted(versions.items())
        )
        return f"installed manifest and provenance versions do not match: {rendered}"
    return None


def stale_receipt_reason(
    source_residual: frozenset[str], receipt_residual: frozenset[str]
) -> str | None:
    """The exact assertion the version comparison only approximates."""
    missing = sorted(source_residual - receipt_residual)
    if not missing:
        return None
    return (
        "this consumer's receipt does not list "
        f"{len(missing)} target(s) a thin install must retain, so converting "
        "would leave `--check` reporting refresh-required immediately: "
        + ", ".join(missing)
        + ". Run `install.py TARGET` first."
    )


def load_install_audit_module(root: Path):
    """Import the shipped install audit as a module.

    By path, for the same reason `load_resweep_module` is: the file name has
    hyphens. Importing rather than shelling out is what makes the *structural*
    half reachable on its own -- `inspection.run_install_audit` runs the whole
    script and answers with one exit code, and refusing `--thin` on that answer
    would fold content drift into the refusal and make `--force` unreachable.
    """
    import importlib.util

    scripts = root / "scripts"
    path = scripts / "sd-ai-command-pack-install-audit.py"
    spec = importlib.util.spec_from_file_location("sd_install_audit", path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise SystemExit(f"error: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # The audit imports its sibling `sd_ai_command_pack_lib` by bare name,
    # which resolves only because a direct `python scripts/...` invocation puts
    # that directory on `sys.path[0]`. A spec load gets no such entry, so the
    # import fails partway through `exec_module`. Supplied here and removed
    # again rather than left behind, because this runs inside the installer.
    # And the audit sets `sys.dont_write_bytecode` at import time, which is an
    # entrypoint's decision to make about its own process. Executing the module
    # here makes it ours, permanently, for every import the installer performs
    # afterwards. Restored for the same reason the path entry is: a loader that
    # runs inside another program leaves that program as it found it.
    added = str(scripts) not in sys.path
    bytecode = sys.dont_write_bytecode
    if added:
        sys.path.insert(0, str(scripts))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = bytecode
        if added:
            sys.path.remove(str(scripts))
    return module


def structural_audit_reasons(root: Path, target: Path) -> tuple[str, ...]:
    """Structural damage the receipt comparison cannot see.

    The receipt comparisons above read *from* the receipt: they ask whether
    every path it lists is accounted for. Nothing asks the other direction --
    whether a pack-like file on disk is absent from the receipt. Such a file is
    in neither `plan.keep` nor `plan.delete`, because the plan is computed from
    the receipt, so conversion walks straight past it and it survives into the
    thin tree as an orphan while every receipt check still passes.

    The audit already decides this (`audit_structural_state`), so this asks it
    rather than reimplementing the pack-like scan, the allow-lists, and the
    gitignore policy a second time and keeping them in step.

    Only the structural failures are consulted. The audit's provenance half is
    per-file content drift, and refusing on it here would make `--force`
    unreachable -- overriding drift is what `--force` is for, which is the same
    boundary `receipt_disagreement_reason` draws.
    """
    audit = load_install_audit_module(root)
    targets, receipt_reasons = audit.load_installed_targets(target)
    if receipt_reasons:
        return tuple(receipt_reasons)
    failures, _warnings = audit.audit_structural_state(target, targets)
    return tuple(failures)


BLOCK_MARKERS = {
    TRELLIS_GITIGNORE_TARGET.as_posix(): (
        TRELLIS_GITIGNORE_START,
        TRELLIS_GITIGNORE_END,
        ".gitignore",
        False,
    ),
    COPILOT_INSTRUCTIONS_TARGET.as_posix(): (
        COPILOT_GUIDANCE_START,
        COPILOT_GUIDANCE_END,
        ".github/copilot-instructions.md",
        True,
    ),
}


def removal_preflight_reasons(
    target: Path,
    plan,
    *,
    files_by_target: dict,
    provenance_files: dict[str, str],
    force: bool,
) -> tuple[str, ...]:
    """Drift across all three removal buckets, found before anything is written.

    Not just `delete`. `retire_stale_targets` preserves a drifted retired file
    and keeps going (`installer/removal.py:263`), and managed-block removal
    can come back `PRESERVED` on a malformed or unreadable target
    (`installer/fileops.py:683`). Validating only ordinary delete drift would
    let a conversion complete while a retired file or an unstrippable block
    survives -- exactly the half-converted state the thin pin would then
    certify as clean.

    `--force` overrides removal drift in all three buckets and nothing else
    (R19-C5): not a settings collision, not a stale receipt, not an unwritable
    root, not a missing verdict.
    """
    reasons: list[str] = []
    for entry in (*plan.delete, *plan.retire):
        result = remove_pack_file(
            target,
            Path(entry),
            file=files_by_target.get(entry),
            recorded_hash=provenance_files.get(entry),
            force=force,
            dry_run=True,
            backup=False,
        )
        if result.status is RemoveStatus.PRESERVED:
            reasons.append(f"{entry} cannot be removed: {result.detail}")
    for entry in plan.block_strip:
        markers = BLOCK_MARKERS.get(entry)
        if markers is None:
            # A managed-block file the conversion plan named and this table
            # does not know how to strip. Guessing a marker pair is how a
            # consumer loses a surface silently.
            reasons.append(f"{entry} carries no known managed block to strip")
            continue
        start, end, label, invalid_utf8 = markers
        result = remove_text_block_file(
            target,
            Path(entry),
            start_marker=start,
            end_marker=end,
            label=label,
            dry_run=True,
            backup=False,
            preserve_invalid_utf8=invalid_utf8,
        )
        if result.status is RemoveStatus.PRESERVED:
            reasons.append(f"{entry} block cannot be stripped: {result.detail}")
    return tuple(reasons)


@dataclass(frozen=True)
class ConversionWrite:
    """One completed write, so an interrupted run can report which half landed."""

    step: str
    detail: str


class PartialConversion(Exception):
    """The second root failed after the first one was written.

    Both roots are probed for writability before either is touched, so
    reaching here means something changed underneath a validated plan -- a
    mount going read-only, a concurrent edit, a full disk. There is no
    rollback and inventing one would be worse than the skew: the consumer is
    converted and the registry still says otherwise, which is exactly the
    pin-vs-mode skew `sd-status fleet` already reports. So the command says
    which half landed, names the one-line fix, and exits nonzero.
    """

    def __init__(self, written: tuple[ConversionWrite, ...], detail: str):
        super().__init__(detail)
        self.written = written
        self.detail = detail


def apply_conversion(
    root: Path,
    target: Path,
    *,
    plan,
    settings: SettingsPlan,
    manifest_data: dict,
    residual: frozenset[str],
    existing_files: dict[str, str],
    platforms: tuple[str, ...],
    consumer: str | None,
    forced: tuple[str, ...],
    files_by_target: dict,
    provenance_files: dict[str, str],
    force: bool,
    backup: bool,
) -> list[ConversionWrite]:
    """Execute the validated plan in the order design.md fixes, and only that order.

    The order is part of the contract because there is no rollback: it exists
    so that every interruption lands in a state that is *recognizable* rather
    than ambiguous. Settings first (a pure addition, reversible by deleting
    keys); then the receipts with provenance last, because the pin is the
    discriminator every other command reads and therefore the commit point;
    then the payload; then the registry.

    Deleting the payload before writing the pin would produce the one state
    that is not recognizable -- a consumer with no machine surfaces and a fat
    receipt, which `--check` calls `invalid` and which no re-run can tell from
    a botched manual deletion.
    """
    written: list[ConversionWrite] = []

    if settings.writes_anything:
        settings.path.parent.mkdir(parents=True, exist_ok=True)
        settings.path.write_text(render_settings(settings.merged), encoding="utf-8")
        written.append(ConversionWrite("settings", str(settings.path)))

    # The removal inventory rides with the receipts, before the pin, because
    # the pin is what makes the receipt stop describing the remainder.
    inventory = target / REMOVAL_INVENTORY_FILE
    inventory.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_text(
        removal_inventory_content(
            delete=plan.delete, retire=plan.retire, block_strip=plan.block_strip
        ),
        encoding="utf-8",
    )
    written.append(ConversionWrite("removal-inventory", str(inventory)))

    (target / PACK_MANIFEST_FILE).write_text(
        thin_manifest_content(manifest_data), encoding="utf-8"
    )
    written.append(ConversionWrite("manifest", PACK_MANIFEST_FILE.as_posix()))

    (target / INSTALLED_TARGETS_FILE).write_text(
        residual_targets_content(residual), encoding="utf-8"
    )
    written.append(ConversionWrite("installed-targets", INSTALLED_TARGETS_FILE.as_posix()))

    (target / PROVENANCE_FILE).write_text(
        thin_provenance_content(
            manifest_data,
            files=residual_provenance_files(existing_files, residual),
            platforms=platforms,
            consumer=consumer,
            additions=settings.record,
            forced=forced,
            retired=tuple(plan.retire),
        ),
        encoding="utf-8",
    )
    written.append(ConversionWrite("provenance", PROVENANCE_FILE.as_posix()))

    for entry in (*plan.delete, *plan.retire):
        remove_pack_file(
            target,
            Path(entry),
            file=files_by_target.get(entry),
            recorded_hash=provenance_files.get(entry),
            force=force,
            dry_run=False,
            backup=backup,
        )
    for entry in plan.block_strip:
        start, end, label, invalid_utf8 = BLOCK_MARKERS[entry]
        remove_text_block_file(
            target,
            Path(entry),
            start_marker=start,
            end_marker=end,
            label=label,
            dry_run=False,
            backup=backup,
            preserve_invalid_utf8=invalid_utf8,
        )
    written.append(
        ConversionWrite(
            "payload",
            f"{len(plan.delete)} deleted, {len(plan.retire)} retired, "
            f"{len(plan.block_strip)} block(s) stripped",
        )
    )

    # Last, and only now: the inventory's removals have all been performed, so
    # its presence from here on would mean unfinished work that is finished.
    inventory.unlink()
    written.append(ConversionWrite("removal-inventory-cleared", str(inventory)))

    if consumer is not None:
        try:
            flip_registry_mode(root, consumer)
        except OSError as error:
            raise PartialConversion(tuple(written), str(error)) from None
        written.append(ConversionWrite("registry", f"{consumer} -> thin"))
    return written


def flip_registry_mode(root: Path, consumer: str, mode: str = "thin") -> None:
    """Record the consumer's new mode in the pack's own fleet registry.

    Written last. An unwritable registry is refused in the preflight, so
    reaching here and failing is a genuine mid-operation failure -- reported
    as "consumer converted, registry did not", which is the pin-vs-mode skew
    the parent design already accepts and `sd-status fleet` already reports.
    """
    path = root / FLEET_REGISTRY_FILE
    payload = json.loads(path.read_text(encoding="utf-8"))
    for entry in payload.get("consumers", ()):
        if entry.get("name") == consumer:
            entry["mode"] = mode
            break
    else:
        raise SystemExit(f"error: {consumer} is not in {path}")
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_registry(root: Path) -> dict:
    """The pack's own fleet registry, keyed by consumer name."""
    payload = json.loads(
        (root / FLEET_REGISTRY_FILE).read_text(encoding="utf-8")
    )
    return {str(entry["name"]): entry for entry in payload.get("consumers", ())}


def revert_consumer_identity(
    root: Path,
    target: Path,
    *,
    receipt_consumer: str | None,
    flag_consumer: str | None,
) -> tuple[str | None, str | None]:
    """Which registry row this revert flips, or why it will not guess.

    `--revert-thin` receives only `TARGET`, and it must flip exactly one row.
    Inferring the name from `pathHint` fails for a disposable checkout, a
    worktree, or an alternate clone, and picking the wrong row mislabels two
    consumers at once -- the converted one stays `thin` forever and an
    untouched one is announced as fat-again. So the receipt carries the name,
    `--consumer` overrides it, and every disagreement refuses.

    The path lookup is a cross-check and never a source: a checkout at no
    known `pathHint` still reverts on the receipt's name, and a checkout whose
    `pathHint` names a *different* consumer refuses rather than choosing which
    of the two evidences to believe.
    """
    if (
        receipt_consumer is not None
        and flag_consumer is not None
        and receipt_consumer != flag_consumer
    ):
        return None, (
            f"--consumer names {flag_consumer} and the thin receipt records "
            f"{receipt_consumer}; revert will not choose between them"
        )
    name = flag_consumer or receipt_consumer
    if name is None:
        return None, (
            "the thin receipt records no consumer name, so the registry row to "
            "flip back to fat is unknown; pass --consumer NAME"
        )
    try:
        entries = read_registry(root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return None, f"the fleet registry cannot be read: {error}"
    if name not in entries:
        known = ", ".join(sorted(entries)) or "none"
        return None, (
            f"{name} is not a registered consumer; known consumers: {known}"
        )
    for other, entry in sorted(entries.items()):
        hint = entry.get("pathHint")
        if other == name or not isinstance(hint, str):
            continue
        if Path(hint).expanduser().resolve() == target:
            return None, (
                f"{target} is registered as {other}, and this revert was told "
                f"{name}; revert will not choose between them"
            )
    return name, None


def revert_version_reason(
    pin_version: str | None, source_version: str
) -> str | None:
    """Why this checkout cannot reproduce the payload this pin recorded.

    `install.py` installs from the *current* checkout's manifest, so a newer
    pack cannot reconstruct an older payload's bytes from a pin that carries
    only a version string. Restoring the newer bytes would be a fat re-install
    at a different version -- a legitimate thing to want, and not what "restore
    to the pre-conversion state" promises.
    """
    if pin_version is None:
        return (
            "this consumer's thin pin records no version, so the payload it "
            "was converted from cannot be identified"
        )
    if pin_version != source_version:
        return (
            f"this consumer was converted from {pin_version} and this checkout "
            f"is {source_version}; byte-identical restoration is version-bound. "
            f"Check out {pin_version} and re-run, or re-install at "
            f"{source_version} instead of reverting"
        )
    return None


@dataclass(frozen=True)
class SettingsRevert:
    """What revert does to `settings.json`, decided before it does any of it."""

    path: Path
    action: str  # "write", "delete", or "none"
    merged: dict
    notes: tuple[str, ...] = ()


def plan_settings_revert(
    path: Path, additions: dict, *, plugin_key: str
) -> tuple[SettingsRevert | None, str | None]:
    """Undo exactly what the conversion recorded, and nothing else.

    Two rules from `design.md` collide here and ownership wins (R19-C5). §4
    says revert leaves a recorded value that has since been edited; §5 says
    revert writes the `enabledPlugins` disable marker. For a key that was
    already `true` before the conversion, or edited after it, both cannot
    happen -- so the marker is only ever written over a value this conversion
    wrote and still owns.

    Where the marker is *not* written, revert says so, because a fat consumer
    running the plugin as well is a real double-surface state and an operator
    has to know. What revert must never do is disable a plugin somebody else
    enabled: that is a decision about their tooling, made by a command they ran
    to undo ours.
    """
    if path.is_symlink():
        return None, (
            f"{path} is a symlink; the pack edits regular files only, and "
            "following it would write outside the target"
        )
    if not path.exists():
        # Not an error. The consumer may have deleted the file, and there is
        # then nothing of ours left in it to remove.
        return (
            SettingsRevert(
                path,
                "none",
                {},
                (f"{path.name} is absent; no recorded settings were removed",),
            ),
            None,
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, f"{path} cannot be read as JSON ({error})"
    if not isinstance(document, dict):
        return None, f"{path} is not a JSON object; there is nothing to undo in it"

    before = json.dumps(document, sort_keys=True)
    notes: list[str] = []
    marker_written = False
    plugin_recorded = False
    for container_key in (MARKETPLACE_KEY, PLUGINS_KEY):
        recorded = additions.get(container_key)
        if not isinstance(recorded, dict) or not recorded:
            continue
        container = document.get(container_key)
        if not isinstance(container, dict):
            notes.append(
                f"{container_key} is no longer an object; its recorded entries "
                "were left in place"
            )
            continue
        for name, value in sorted(recorded.items()):
            is_marker_key = container_key == PLUGINS_KEY and name == plugin_key
            plugin_recorded = plugin_recorded or is_marker_key
            if name not in container:
                notes.append(f"{container_key}.{name} was already absent")
                continue
            if container[name] != value:
                notes.append(
                    f"{container_key}.{name} was edited after the conversion "
                    "and was left as it is"
                )
                continue
            if is_marker_key:
                container[name] = False
                marker_written = True
            else:
                del container[name]

    created = additions.get("createdContainers")
    for container_key in created if isinstance(created, list) else ():
        container = document.get(container_key)
        if isinstance(container, dict) and not container:
            del document[container_key]

    plugins = document.get(PLUGINS_KEY)
    if (
        not marker_written
        and isinstance(plugins, dict)
        and plugins.get(plugin_key) is not False
        and plugin_key in plugins
        and not plugin_recorded
    ):
        notes.append(
            f"{plugin_key} remains enabled by a setting this pack did not add; "
            "this consumer now runs both the plugin and the installed files"
        )

    if additions.get("createdFile") is True and not document:
        return SettingsRevert(path, "delete", {}, tuple(notes)), None
    if json.dumps(document, sort_keys=True) == before:
        return SettingsRevert(path, "none", document, tuple(notes)), None
    return SettingsRevert(path, "write", document, tuple(notes)), None


def apply_settings_revert(plan: SettingsRevert) -> str | None:
    """Execute a planned settings revert; returns what it did, or None."""
    if plan.action == "write":
        plan.path.write_text(render_settings(plan.merged), encoding="utf-8")
        return f"rewrote {plan.path}"
    if plan.action == "delete":
        plan.path.unlink()
        return f"removed {plan.path}"
    return None


__all__ = [
    "BLOCK_MARKERS",
    "CLAUDE_SETTINGS_FILE",
    "ConversionWrite",
    "FLEET_REGISTRY_FILE",
    "PartialConversion",
    "SettingsRevert",
    "apply_conversion",
    "apply_settings_revert",
    "flip_registry_mode",
    "plan_settings_revert",
    "read_registry",
    "revert_consumer_identity",
    "revert_version_reason",
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
    "load_resweep_module",
    "load_verdict",
    "normalize_github_remote",
    "pack_repository_reason",
    "plan_settings_merge",
    "read_removal_inventory",
    "receipt_disagreement_reason",
    "removal_inventory_content",
    "removal_preflight_reasons",
    "render_settings",
    "residual_provenance_files",
    "residual_targets_content",
    "settings_additions",
    "stale_receipt_reason",
    "thin_manifest_content",
    "thin_provenance_content",
    "verdict_binding_reasons",
    "version_currency_reason",
    "writability_reason",
]
