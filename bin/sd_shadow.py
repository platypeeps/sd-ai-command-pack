"""`sd shadow sync` — the verb over the collector the library already ships.

`sd_db.shadow_sync`'s own docstring settles the split in as many words: "This
module is the collector, not the command. `sd shadow sync` is a verb and verbs
live in the pack." So nothing here collects. It opens the connection, calls
`sd_db.sync_shadow`, and turns the `Synced` it gets back into a line an
operator can act on.

The one thing worth stating twice is the order the collector guarantees and
this verb must not obscure: rows are written whether or not the collect
succeeded, because a partial answer is still true, and the watermark moves only
on the collect's own success. A run that reports "wrote 4, cursor held" is
therefore not a contradiction -- it is the design -- and the report says both
numbers rather than one summary word that would have to pick.

Nothing here closes anything. `sync` calls `collect`, `store` and
`write_watermark` and no fourth thing, which is why criterion 28's "the fixture
saw no close call" is a fact about the library rather than a rule this verb has
to keep.
"""

from __future__ import annotations

import argparse
import math
import re
from datetime import datetime, timezone


def timestamp(value: str) -> datetime:
    """Require a timezone and normalize conservative whole-second UTC bounds."""
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
        r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value,
    ):
        raise argparse.ArgumentTypeError("use an ISO timestamp with Z or an explicit timezone offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(microsecond=0)
    except (ValueError, OverflowError):
        raise argparse.ArgumentTypeError("use a valid timezone-aware ISO timestamp") from None


def positive_requests(value: str) -> int:
    """A request budget counts whole requests, with at least one permitted."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_seconds(value: str) -> float:
    """Reject NaN and infinity, which do not impose a useful time budget."""
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive finite number") from None
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return parsed


def _rows():
    """`bin/sd_handoff_rows.py`, which owns the library frame and its refusal."""
    import sd_handoff_rows  # noqa: PLC0415 - deferred, as the module docstring says

    return sd_handoff_rows


def shadow_sync(args) -> int:
    """Run one sync and report what moved. Writes rows; never closes anything."""
    rows = _rows()
    since = getattr(args, "since", None)
    until = getattr(args, "until", None)
    current = datetime.now(timezone.utc).replace(microsecond=0)
    if until is not None and until > current:
        raise rows.RowsRefusal("--until must not be in the future")
    if since is not None and since > (until if until is not None else current):
        raise rows.RowsRefusal("--since must not be after --until (or the current time)")
    options = {
        name: value for name, value in (
            ("since", since), ("now", until),
            ("max_requests", getattr(args, "max_requests", None)),
            ("max_seconds", getattr(args, "max_seconds", None)),
        ) if value is not None
    }
    sd_db = rows.library()
    connection = rows.connect(sd_db, write=True)
    try:
        result = sd_db.sync_shadow(connection, **options)
    finally:
        connection.close()

    print(f"wrote {result.written} shadow row(s)")
    if result.truncated:
        # Named, because a truncated page means the next run starts from the
        # same watermark and there is more behind it than this run saw.
        print("coverage is incomplete; retry a smaller window or increase the request/time limits")
    if result.ok:
        if result.watermark_moved:
            print(f"cursor moved to cover from {result.window_start}")
        else:
            print(f"coverage completed from {result.window_start}; existing cursor retained")
        return 0
    # The rows above are still written and still true. Only the cursor held,
    # so the next run re-reads the same window rather than skipping it.
    print(f"cursor held: {result.reason or 'the collect did not succeed'}")
    return 1 if args.strict else 0
