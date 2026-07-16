"""Typed status vocabularies for installer result objects."""

from __future__ import annotations

from enum import Enum


class StringStatus(str, Enum):
    """Python 3.10-compatible string enum with stable CLI formatting."""

    def __str__(self) -> str:
        return self.value


class InstallStatus(StringStatus):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    OVERWRITTEN = "overwritten"
    PRESERVED = "preserved"
    CONFLICT = "conflict"
    SYMLINK_CONFLICT = "symlink-conflict"


class RemoveStatus(StringStatus):
    MISSING = "missing"
    PRESERVED = "preserved"
    UNCHANGED = "unchanged"
    UPDATED = "updated"
    REMOVED = "removed"
    WOULD_UPDATE = "would-update"
    WOULD_REMOVE = "would-remove"
    RETIRED = "retired"
    RETIRED_PRESERVED = "retired-preserved"
    WOULD_RETIRE = "would-retire"
    IGNORED = "ignored"


class LocalOnlyStatus(StringStatus):
    TRELLIS_PRESENT = "trellis-present"
    WOULD_INIT_TRELLIS_LOCAL = "would-init-trellis-local"
    INITIALIZED_TRELLIS_LOCAL = "initialized-trellis-local"
    LOCAL_EXCLUDE_UNCHANGED = "local-exclude-unchanged"
    WOULD_UPDATE_LOCAL_EXCLUDE = "would-update-local-exclude"
    LOCAL_EXCLUDE_UPDATED = "local-exclude-updated"
    LOCAL_EXCLUDE_CREATED = "local-exclude-created"
    LOCAL_ONLY_MARKER_UNCHANGED = "local-only-marker-unchanged"
    WOULD_WRITE_LOCAL_ONLY_MARKER = "would-write-local-only-marker"
    LOCAL_ONLY_MARKER_WRITTEN = "local-only-marker-written"


CONFLICT_STATUSES = frozenset(
    {
        InstallStatus.CONFLICT,
        InstallStatus.SYMLINK_CONFLICT,
    }
)
VOUCHABLE_STATUSES = frozenset(
    {
        InstallStatus.CREATED,
        InstallStatus.UPDATED,
        InstallStatus.UNCHANGED,
        InstallStatus.OVERWRITTEN,
    }
)
WRITTEN_REMOVE_STATUSES = frozenset(
    {
        RemoveStatus.REMOVED,
        RemoveStatus.UPDATED,
    }
)


__all__ = [
    "CONFLICT_STATUSES",
    "InstallStatus",
    "LocalOnlyStatus",
    "RemoveStatus",
    "StringStatus",
    "VOUCHABLE_STATUSES",
    "WRITTEN_REMOVE_STATUSES",
]
