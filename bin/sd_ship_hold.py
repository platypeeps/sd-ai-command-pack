"""sd:2035. A held merge lane: the repository's ship lock reserved for one item.

The ship lock is a flock that lasts one command. A lane that prepares, waits
for review and merges one item runs several commands, and between them any
other session's prepare took the lock: on 2026-09-28 two did, and the held
item lost an attempt to each. A hold is a record beside the lock files that
names one item, its holder and its expiry. `sd-ship hold` writes it under the
lock; `prepare` and `merge` for any other item refuse while it stands, before
the lock and again under it. The held item's merge ends it, `sd-ship release`
ends it by hand, and an expired record holds nothing, so a lane that died
blocks the repository for at most its window.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
from datetime import datetime, timedelta, timezone

from sd_ship_remote import Refusal

#: The directory beside the database that holds one hold file per repository,
#: next to the ship lock files.
HOLD_DIRECTORY = "ship-holds"
#: How long a hold lasts unless `--for` says otherwise: a prepare, its review
#: and a merge gate fit in it, and a lane that died frees the repository in it.
DEFAULT_SECONDS = 3600
#: The longest window `--for` accepts, so no hold outlives a day unrenewed.
MAXIMUM_SECONDS = 86400
#: A record is small; a longer file is not one.
RECORD_BYTES = 4096


def now() -> datetime:
    return datetime.now(timezone.utc)


def seconds(value: str) -> int:
    """`--for`: whole seconds from 1 to MAXIMUM_SECONDS."""
    import argparse
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number of seconds") from None
    if not 0 < number <= MAXIMUM_SECONDS:
        raise argparse.ArgumentTypeError(f"a hold lasts 1 to {MAXIMUM_SECONDS} seconds")
    return number


def hold_file(database: pathlib.Path, repository: str) -> pathlib.Path:
    return database.parent / HOLD_DIRECTORY / (hashlib.sha256(repository.encode()).hexdigest() + ".json")


def standing(database: pathlib.Path, repository: str) -> dict | None:
    """The hold that stands on `repository`, or None when none does.

    An expired record, an unreadable one and one for another repository hold
    nothing: a hold refuses other sessions' work, so only a record that says
    exactly what it holds may do that.
    """
    try:
        raw = hold_file(database, repository).read_bytes()[:RECORD_BYTES + 1]
        record = json.loads(raw) if len(raw) <= RECORD_BYTES else None
        expires = datetime.fromisoformat(record["expires_at"])
    except (OSError, ValueError, TypeError, KeyError):
        return None
    if (not isinstance(record, dict) or record.get("repository") != repository
            or type(record.get("item")) is not int or expires.tzinfo is None or expires <= now()):
        return None
    return record


def held_text(record: dict) -> str:
    return f"sd:{record['item']} by {record.get('holder') or 'an unnamed holder'} until {record['expires_at']}"


def refuse_other(database: pathlib.Path, repository: str, item: int | None) -> None:
    """Refuse a prepare or merge for anything but the held item."""
    record = standing(database, repository)
    if record is None or record["item"] == item:
        return
    raise Refusal(f"the merge lane for {repository} is held for {held_text(record)}; "
                  f"only sd:{record['item']} may prepare or merge while it stands",
                  code="lane_held", boundary="policy", state="retryable_failure",
                  next_action=f"Wait for the hold on sd:{record['item']} to end, or ask its holder to run "
                              f"sd-ship release --item {record['item']}.")


def take(database: pathlib.Path, repository: str, item: int, *, window: int, holder: str | None,
         command: str) -> dict:
    """Write or renew the hold for `item`; the caller holds the repository's ship lock."""
    current = standing(database, repository)
    if current is not None and current["item"] != item:
        refuse_other(database, repository, item)
    moment = now()
    record = {"repository": repository, "item": item, "holder": holder or None, "command": command,
              "taken_at": (current or {}).get("taken_at") or moment.isoformat(),
              "renewed_at": moment.isoformat(), "expires_at": (moment + timedelta(seconds=window)).isoformat()}
    target = hold_file(database, repository)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)
    return record


def end_hold(database: pathlib.Path, repository: str, item: int) -> dict | None:
    """End the hold for `item`; refuse one that stands for another item.

    Returns the record that ended, or None when nothing stood.
    """
    record = standing(database, repository)
    if record is None:
        return None
    if record["item"] != item:
        raise Refusal(f"the merge lane for {repository} is held for {held_text(record)}, not for sd:{item}; "
                      "only the held item's release ends it",
                      code="lane_held", boundary="policy", state="operator_decision",
                      next_action=f"Release with --item {record['item']}, or wait for the hold to expire.")
    try:
        hold_file(database, repository).unlink()
    except FileNotFoundError:
        pass
    return record


def end_after_merge(database: pathlib.Path, repository: str, item: int | None, result: dict) -> None:
    """The held item's verified merge ends its hold; nothing else does."""
    if item is not None and result.get("phase") == "merged":
        record = standing(database, repository)
        if record is not None and record["item"] == item:
            end_hold(database, repository, item)
