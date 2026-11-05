"""The hub's RAM disk for the gate's and the tests' temp folders (sd:7557), when it is ready.

The system repository's `tmpdisk` stage keeps an HFS+ RAM disk at `ROOT`, with FSEvents logging and
Spotlight off, and writes `READY` there only after its remount (system sd:7092). Gate trees and test
runs made about 13k of 55k file writes in 30 s under the inherited `TMPDIR`, and fseventsd grew to 17 GB.

`temporary` is the one place both callers ask: `sd_gate_cache.worktree_place` and `tests/__init__.py`;
`reap_places` names where a gate start cleans up.
The disk is ready when `ROOT` is a mount point, holds `READY`, is writable and has `FREE` bytes free.
Any failed probe reads "not ready", never an error, and the inherited temp dir stays: a satellite has
no such disk. A temp dir already inside the disk, or inside an sd folder that names its owner's pid
(`OWNED`), stays too: a check's tests nest in its gate's folder, and a test's gate in its run's (sd:3032).

Dependency-free on purpose: `tests/__init__.py` loads it by path before anything else is imported.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import tempfile
from os.path import ismount

#: The RAM disk's mount point; no setting names it (lead ruling, sd:7557): a machine without it reads "not ready".
ROOT = pathlib.Path("/Volumes/sd-tmp")
#: The marker the `tmpdisk` stage writes once the remount set both markers.
READY = ".tmpdisk-ready"
#: The free space the disk needs: a pack gate tree is about 220 MB, and the peak was 646 MB.
FREE = 1024 ** 3
#: An sd folder that names its owner's pid: a gate's, a test run's (`tests/__init__.py`), or a review's prior report
#: (`bin/sd_ship_review.py`, sd:3059); `sd_gate_cache.reap_temporary` removes it once the pid is gone.
OWNED = re.compile(r"(?:sd-local-gate|sd-tests|sd-ship-verify)-([0-9]{1,9})-[a-z0-9_]+")


def disk_marked() -> bool:
    """Whether `ROOT` is mounted and holds `READY`, whatever its free space; a failed probe is False."""
    try:
        return ismount(ROOT) and (ROOT / READY).is_file()
    except (OSError, ValueError):
        return False


def disk_ready() -> bool:
    """Whether `ROOT` is a mounted, marked, writable disk with `FREE` bytes free; a failed probe is False."""
    try:
        return disk_marked() and os.access(ROOT, os.W_OK) and shutil.disk_usage(ROOT).free >= FREE
    except (OSError, ValueError):
        return False


def within(path: os.PathLike[str] | str) -> bool:
    """Whether `path` resolves to `ROOT` or below it."""
    try:
        return pathlib.Path(path).resolve().is_relative_to(ROOT.resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def owned_inside(path: os.PathLike[str] | str) -> bool:
    """Whether `path` lies in an `OWNED` folder: a gate's, a test run's or a review's."""
    return any(OWNED.fullmatch(part) for part in pathlib.Path(path).parts)


def reap_places(inherited: str) -> list[str]:
    """Where a gate start reaps: the disk when it is marked, whatever its free space, then `inherited`.

    Only placing a folder needs room: a disk that dead gates filled is reaped, so the next gate lands on it
    again (sd:7557 review). A nested `inherited` reaps only itself, as `temporary` keeps it.
    """
    if within(inherited) or owned_inside(inherited) or not disk_marked():
        return [inherited]
    return [str(ROOT), inherited]


def temporary(inherited: str | None = None) -> str:
    """Where an sd temp folder goes: `ROOT` when it is ready, else `inherited` (`tempfile.gettempdir()`).

    `inherited` stays when it already lies on the disk or in an `OWNED` folder, so a nested run stays
    inside the folder its parent cleans up.
    """
    inherited = inherited or tempfile.gettempdir()
    if within(inherited) or owned_inside(inherited) or not disk_ready():
        return inherited
    return str(ROOT)
