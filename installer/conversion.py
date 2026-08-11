"""Fat-to-thin conversion planning: receipt-first enumeration, classified by the partition.

The plan builder is shared by ``install.py --thin`` and the source-checkout
resweep so the two can never disagree about what a conversion deletes. It is
deliberately split into a pure classification pass and an impure preflight
pass: the resweep needs the former without executing the latter.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from installer.manifest import target_destination
from installer.registry import (
    INSTALLED_TARGETS_FILE,
    PACK_MANIFEST_FILE,
    PROVENANCE_FILE,
)
from installer.removal import MANAGED_BLOCK_REMOVAL_TARGETS, RETIRED_TARGETS

# The three install receipts. Conversion rewrites all three rather than
# deleting any: installer/inspection.py requires every one to be occupied,
# and the structural audit requires provenance to carry a non-empty files map.
BOOKKEEPING_TARGETS = frozenset(
    {
        INSTALLED_TARGETS_FILE.as_posix(),
        PACK_MANIFEST_FILE.as_posix(),
        PROVENANCE_FILE.as_posix(),
    }
)

MACHINE_CATEGORIES = frozenset({"machine-claude", "machine-other"})
KEEP_CATEGORIES = frozenset({"repo-native", "consumer-config"})

# The blocked-entry subject for a platform the partition cannot classify: the
# defect is in the partition-to-registry relationship, not in any one target.
PARTITION_SOURCE = "docs/fleet/surface-partition.json"

RECEIPT_PRESENT = "present"
RECEIPT_MISSING = "missing"
RECEIPT_UNREADABLE = "unreadable"


@dataclass(frozen=True)
class ReceiptLoad:
    """The installed-targets receipt plus *why* it is empty when it is.

    ``read_existing_installed_targets`` returns an empty set for a missing
    file, so the parsed entries alone cannot produce the missing-receipt
    diagnostic conversion must refuse with.
    """

    state: str
    entries: frozenset[str]
    detail: str | None = None


@dataclass(frozen=True)
class PartitionRow:
    target: str
    platform: str
    category: str


@dataclass(frozen=True)
class Partition:
    rows: dict[str, PartitionRow]
    platforms: dict[str, dict]

    def row(self, target: str) -> PartitionRow | None:
        return self.rows.get(target)

    def disposition(self, platform: str) -> dict:
        return self.platforms.get(platform, {})


@dataclass(frozen=True)
class BlockedEntry:
    target: str
    reason: str


@dataclass(frozen=True)
class ConversionPlan:
    """What a conversion would do, computed before anything is written."""

    delete: tuple[str, ...] = ()
    retire: tuple[str, ...] = ()
    block_strip: tuple[str, ...] = ()
    keep: tuple[str, ...] = ()
    receipts: tuple[str, ...] = ()
    blocked: tuple[BlockedEntry, ...] = ()

    @property
    def is_convertible(self) -> bool:
        return not self.blocked


def read_installed_targets_receipt(target: Path) -> ReceiptLoad:
    """Load the receipt with its state, distinguishing missing from unreadable."""
    receipt = target_destination(target, INSTALLED_TARGETS_FILE)
    if not receipt.is_file():
        return ReceiptLoad(
            state=RECEIPT_MISSING,
            entries=frozenset(),
            detail=f"{INSTALLED_TARGETS_FILE.as_posix()} is missing",
        )
    try:
        content = receipt.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return ReceiptLoad(
            state=RECEIPT_UNREADABLE,
            entries=frozenset(),
            detail=f"{INSTALLED_TARGETS_FILE.as_posix()} cannot be read: {error}",
        )
    entries = {
        line
        for line in (raw.strip() for raw in content.splitlines())
        if line and not line.startswith("#")
    }
    return ReceiptLoad(state=RECEIPT_PRESENT, entries=frozenset(entries))


def load_partition(path: Path) -> Partition:
    """Read surface-partition.json into the shape the classifier needs."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = {
        str(entry["target"]): PartitionRow(
            target=str(entry["target"]),
            platform=str(entry["platform"]),
            category=str(entry["category"]),
        )
        for entry in payload["files"]
    }
    platforms = {str(name): dict(body) for name, body in payload["platforms"].items()}
    return Partition(rows=rows, platforms=platforms)


def _retained_for_consumer(
    partition: Partition,
    row: PartitionRow,
    consumer_platforms: frozenset[str],
) -> bool:
    """True when a machine-scope row nonetheless stays vendored in this consumer."""
    disposition = partition.disposition(row.platform)
    # A provisional platform has not been proven safe to serve from the
    # machine, so its rows stay vendored regardless of category.
    if disposition.get("provisional"):
        return True
    retain_for = disposition.get("retainVendoredFor") or ()
    return bool(consumer_platforms.intersection(retain_for))


def classify_target(
    target: str,
    partition: Partition,
    consumer_platforms: frozenset[str],
) -> tuple[str, str | None]:
    """Return ``(bucket, reason)`` for one receipt entry.

    Pure: no filesystem access. ``reason`` is populated only for ``blocked``.
    """
    if target in BOOKKEEPING_TARGETS:
        return "receipts", None

    if target in MANAGED_BLOCK_REMOVAL_TARGETS:
        # Two files carry pack-owned blocks inside consumer-owned files, and
        # their fates differ. .github/copilot-instructions.md is repo-native
        # because Copilot reads the repository and cannot see the machine, so
        # its block stays. .gitignore has no partition row and lists vendored
        # paths this conversion deletes, so its block goes.
        row = partition.row(target)
        if row is None:
            return "block_strip", None
        if row.category in KEEP_CATEGORIES:
            return "keep", None
        return (
            "blocked",
            f"managed-block file has an unexpected partition category: {row.category}",
        )

    if target in RETIRED_TARGETS:
        return "retire", None

    row = partition.row(target)
    if row is None:
        return "blocked", "no partition row classifies this installed target"

    if row.category in KEEP_CATEGORIES:
        return "keep", None

    if row.category in MACHINE_CATEGORIES:
        if _retained_for_consumer(partition, row, consumer_platforms):
            return "keep", None
        return "delete", None

    return "blocked", f"unknown partition category: {row.category}"


def build_conversion_plan(
    receipt: ReceiptLoad,
    partition: Partition,
    consumer_platforms: frozenset[str],
    *,
    occupied: frozenset[str],
) -> ConversionPlan:
    """Build the full plan from the receipt, the partition, and occupancy.

    ``occupied`` is the set of receipt-relative paths that exist in the
    checkout. It is passed in rather than probed so the classification stays
    testable and the resweep can reuse it without a second walk.
    """
    if receipt.state != RECEIPT_PRESENT:
        detail = receipt.detail or "installed-targets receipt is unusable"
        return ConversionPlan(
            blocked=(BlockedEntry(INSTALLED_TARGETS_FILE.as_posix(), detail),)
        )

    # R17-C2: an unknown platform has no disposition, so `_retained_for_consumer`
    # returns False for every row and the conversion deletes the machine surfaces
    # a retained platform would have kept -- silently, with `blocked` empty. A
    # platform this partition cannot classify is a question, not a permission.
    unknown = sorted(
        platform for platform in consumer_platforms if platform not in partition.platforms
    )
    if unknown:
        return ConversionPlan(
            blocked=tuple(
                BlockedEntry(
                    PARTITION_SOURCE,
                    f"consumer declares platform {platform!r}, which the surface "
                    f"partition does not classify",
                )
                for platform in unknown
            )
        )

    buckets: dict[str, list[str]] = {
        "delete": [],
        "retire": [],
        "block_strip": [],
        "keep": [],
        "receipts": [],
    }
    blocked: list[BlockedEntry] = []

    for target in sorted(receipt.entries):
        bucket, reason = classify_target(target, partition, consumer_platforms)
        if bucket == "blocked":
            blocked.append(BlockedEntry(target, reason or "unclassified"))
            continue
        buckets[bucket].append(target)

    # The existing retirement helper walks all 157 RETIRED_TARGETS; conversion
    # executes only the candidates that are actually here, so the plan and the
    # mutation cannot disagree about what gets touched.
    retire = [target for target in buckets["retire"] if target in occupied]

    return ConversionPlan(
        delete=tuple(buckets["delete"]),
        retire=tuple(retire),
        block_strip=tuple(buckets["block_strip"]),
        keep=tuple(buckets["keep"]),
        receipts=tuple(buckets["receipts"]),
        blocked=tuple(blocked),
    )


def occupied_receipt_targets(target: Path, receipt: ReceiptLoad) -> frozenset[str]:
    """Return the receipt entries that exist in this checkout."""
    return frozenset(
        entry
        for entry in receipt.entries
        if target_destination(target, Path(entry)).exists()
    )


def expected_residual_targets(
    source_targets: frozenset[str],
    partition: Partition,
    consumer_platforms: frozenset[str],
    *,
    present_managed_blocks: frozenset[str],
) -> frozenset[str]:
    """The residual slice a converted consumer should hold, computed from source.

    This is deliberately *not* the receipt-derived residual conversion writes.
    Deriving the expected set from the receipt would freeze it: a newly shipped
    repo-native file would never appear in a converted consumer and --check
    would report `current` forever. Deriving it from every partition keep row
    fails the other way -- 557 rows against the ~27 a consumer can install.
    """
    expected: set[str] = set()
    for target in source_targets:
        row = partition.row(target)
        if row is None:
            continue
        if row.category in KEEP_CATEGORIES:
            # consumer-config rows are platform-independent (they carry
            # platform "shared"); everything else must be a platform the
            # consumer actually declares, or it is not installable here.
            if row.platform in consumer_platforms or row.category == "consumer-config":
                expected.add(target)
            continue
        # R17-C1: a machine row the consumer's platform choice retains is part
        # of the residual, and this function used to compute the residual from
        # keep categories alone. `classify_target` puts a retained machine row
        # in `keep`, so a consumer declaring codex converts to 102 residual
        # targets while this said 27 -- and `--check` measured the wrong tree.
        # The two must ask `_retained_for_consumer` the same way or the
        # converter and the inspector disagree by construction.
        if row.category in MACHINE_CATEGORIES and _retained_for_consumer(
            partition, row, consumer_platforms
        ):
            expected.add(target)
    # Managed-block files belong whenever they still exist, partition row or
    # not: a .gitignore whose block strip returned UPDATED survives, and
    # excluding it would make the source- and receipt-derived sets disagree on
    # the ordinary fixture.
    return frozenset(expected | set(present_managed_blocks) | set(BOOKKEEPING_TARGETS))


def residual_source_files(
    files: list,
    target: Path,
    partition: Partition,
    receipt: "ThinReceipt",
) -> list:
    """Narrow the source payload to the slice a thin consumer should hold.

    ``install.py --check`` decides its state by dry-running an install of the
    full payload and counting would-be changes. A thin consumer is missing its
    machine surfaces by design, so against the full payload it reports
    refresh-required forever -- and fleet-review-classify requires `current`.
    Narrowing the payload first makes the same comparison ask the right
    question: does the residual slice match the source's residual slice?
    """
    expected = expected_residual_targets(
        frozenset(file.target.as_posix() for file in files),
        partition,
        receipt.platforms,
        present_managed_blocks=frozenset(
            managed
            for managed in MANAGED_BLOCK_REMOVAL_TARGETS
            if target_destination(target, Path(managed)).exists()
        ),
    )
    return [file for file in files if file.target.as_posix() in expected]


THIN_MODE = "thin"


@dataclass(frozen=True)
class ThinReceipt:
    """The thin pin, read back from the provenance receipt.

    ``mode`` is the single discriminator every thin-aware reader keys on. A
    conversion that deleted the payload but left the receipt alone would
    otherwise report a healthy pin at the old version, so a half-converted
    repository could masquerade as a converted one.
    """

    mode: str
    version: str | None
    platforms: frozenset[str]
    consumer: str | None
    settings_additions: dict
    forced: tuple[str, ...]

    @property
    def is_thin(self) -> bool:
        return self.mode == THIN_MODE


def read_thin_receipt(target: Path) -> ThinReceipt | None:
    """Return the thin pin, or None when this consumer is not thin.

    Any unreadable or non-thin provenance yields None so the caller keeps the
    unchanged fat path; a malformed receipt is the inspection layer's problem
    to report, not this reader's to guess at.
    """
    provenance = target_destination(target, PROVENANCE_FILE)
    try:
        payload = json.loads(provenance.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("mode") != THIN_MODE:
        return None
    version = payload.get("version")
    consumer = payload.get("consumer")
    platforms = payload.get("platforms")
    additions = payload.get("settingsAdditions")
    forced = payload.get("forced")
    return ThinReceipt(
        mode=THIN_MODE,
        version=version if isinstance(version, str) and version.strip() else None,
        platforms=frozenset(platforms) if isinstance(platforms, list) else frozenset(),
        consumer=consumer if isinstance(consumer, str) and consumer.strip() else None,
        settings_additions=additions if isinstance(additions, dict) else {},
        forced=tuple(forced) if isinstance(forced, list) else (),
    )


def classifier_digest(root: Path, consumer_entry: dict) -> str:
    """Hash everything that determines what a conversion does.

    Binding the consumer worktree alone is not enough: the resweep and the
    conversion are separate processes, and a shared builder only guarantees a
    shared result when its inputs match. Pack HEAD is deliberately excluded --
    it would bind a commit while leaving uncommitted edits to these same files
    invisible.
    """
    digest = hashlib.sha256()
    for relative in (
        "docs/fleet/surface-partition.json",
        ".claude-plugin/marketplace.json",
        "plugins/sd/.claude-plugin/plugin.json",
        "installer/removal.py",
        "installer/registry.py",
        "installer/conversion.py",
    ):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    digest.update(
        json.dumps(consumer_entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return f"sha256:{digest.hexdigest()}"


__all__ = [
    "BOOKKEEPING_TARGETS",
    "BlockedEntry",
    "ConversionPlan",
    "KEEP_CATEGORIES",
    "MACHINE_CATEGORIES",
    "Partition",
    "PartitionRow",
    "RECEIPT_MISSING",
    "RECEIPT_PRESENT",
    "RECEIPT_UNREADABLE",
    "ReceiptLoad",
    "THIN_MODE",
    "ThinReceipt",
    "build_conversion_plan",
    "classifier_digest",
    "classify_target",
    "expected_residual_targets",
    "load_partition",
    "occupied_receipt_targets",
    "read_installed_targets_receipt",
    "read_thin_receipt",
    "residual_source_files",
]
