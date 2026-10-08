"""Retired with `CHANGELOG.md` (sd:3013): a stub until sd:3014 drops `bin/sd-ship`'s catch-up import."""

from __future__ import annotations

import pathlib


def resolve_keep_both(root: pathlib.Path) -> bool:
    """Nothing to resolve; a catch-up conflict takes the ordinary abort path."""
    return False


def keep_both_note(base: str) -> str:
    """Never reached while `resolve_keep_both` answers False."""
    return ""
