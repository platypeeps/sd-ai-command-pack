"""The dashboard's one durable fact, kept out of `dashboard/` on purpose.

An ack is what the operator decided and a mutation record is the evidence
R11-D10 is evaluated against, so neither can live in the SQLite index, whose
own first line calls it "observability only, rebuildable, never an input"
(D-1). It goes under the state root beside the handoff packets.

**It lives in `bin/` rather than in `dashboard/`, and that is a budget decision
the PRD anticipated** -- "where its fix lands is a budget decision, not only a
design one". `dashboard/` had 110 lines of total headroom and this mechanism
needs more than that; `bin/` has 1,783. The dependency already runs one way,
`bin/sd-dashboard` imports `dashboard`, so the writer is passed *down* into
`serve` and `make_handler` as a callable. `dashboard/` gains a parameter, not
an import, and stays a library that knows nothing about where its records go.

`bin/sd-handoff-restore:157` is the same shape. Its retry-and-give-up lock loop
is not copied -- that exists so a SessionStart hook cannot block, and a POST
handler that has already spent a subprocess can afford to wait.

**Nothing here raises** (D-6). A write is a byproduct of serving, never a
precondition. The cost is that an unwritable ledger produces zero rows, and
zero is the reading that deletes the write path -- which is why `serve` writes
a `bind` row on every start, and why the criterion treats a ledger with no
`bind` rows as "no evidence" rather than as a zero.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from datetime import datetime
from pathlib import Path

# A two-second budget, taken in fiftieths. The first draft of this bound was
# three tries a tenth apart and it lost eight of forty concurrent writes in its
# own test -- which trades a stall the dashboard has never had for a wrong
# count, the one thing the ledger exists to produce. Long enough that real
# contention (one operator, occasional POSTs) never loses a row; short enough
# that a lock held by something dead costs a row rather than the request.
LOCK_TRIES = 50
LOCK_WAIT = 0.04


def path(environ: dict[str, str] | None = None) -> Path:
    """`~/.local/state/sd-ai-command-pack/dashboard/ledger.jsonl`.

    The state root, honouring `XDG_STATE_HOME` the way `bin/sd-handoff:162`
    does. Deliberately not `index_path`'s cache root: step 6's machine cleanup
    sweeps rebuildable things, and this is not one.
    """
    env = os.environ if environ is None else environ
    base = env.get("XDG_STATE_HOME") or ""
    home = Path(base) if base else Path.home() / ".local" / "state"
    return home / "sd-ai-command-pack" / "dashboard" / "ledger.jsonl"


def append(kind: str, target: Path | None = None, **fields: object) -> bool:
    """Append one record. Never raises, never blocks a response.

    Returns whether the record reached the file, so a caller that is serving a
    *command* rather than emitting telemetry can tell the operator the truth.
    The mutation and bind sites ignore it; `/api/ack` does not.

    `at` is stamped in **local** time, with its offset, rather than in UTC.
    Both are unambiguous instants; only one makes `at[:10]` the operator's day.
    `acked` expires an ack at the end of the day it was taken, and a UTC stamp
    put that boundary at 18:00 for a machine in America/Denver -- an alert
    dismissed after dinner reappearing before bed. Found in review.

    Three call sites write to this file, and a criterion that compares their
    timestamps needs them all taken the same way, which is why the stamp is
    here and not at the callers.
    """
    try:
        record = dict(fields)
        record["kind"] = kind
        record["at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
        destination = path() if target is None else target
    except Exception:
        # Inside the guard, not above it. These four lines sat outside the
        # `try` and `json.dumps` raises `TypeError` on a field nothing checked
        # -- which propagated into `do_POST` between `actions.run` and
        # `send_body`, turning a mutation that had already happened into a 500.
        # A function documented as unable to raise has to actually not raise.
        return False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # 0o600 to match the packets under the same root: this records when
        # this machine's dashboard was reached and by what.
        descriptor = os.open(
            str(destination), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
        )
    except OSError:
        return False
    written = 0
    try:
        # Bounded, not blocking. `LOCK_EX` alone parks the calling thread for
        # as long as whoever holds the lock wants it, and this runs inside an
        # HTTP handler: a stale lock from a crashed writer would stall the
        # request rather than cost it a row. D-6 says a write can only cost a
        # row, so a lock that will not come is a dropped record. Found in
        # review.
        for attempt in range(LOCK_TRIES):
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if attempt == LOCK_TRIES - 1:
                    return False  # the `finally` closes it; closing here too
                    # could land on an fd another thread has since opened
                time.sleep(LOCK_WAIT)
        start = os.lseek(descriptor, 0, os.SEEK_END)
        try:
            while written < len(payload):
                progress = os.write(descriptor, payload[written:])
                if progress <= 0:
                    break
                written += progress
        finally:
            # A half-line is worse than no line: `json.loads` raises on it
            # rather than skipping it, so one torn record makes the whole
            # ledger unreadable to the command that evaluates R11-D10. Under
            # the lock with `O_APPEND` nothing else has written past `start`,
            # so this can only remove this record's own bytes.
            if written != len(payload):
                try:
                    os.ftruncate(descriptor, start)
                except OSError:
                    pass
    except OSError:
        pass
    finally:
        try:
            os.close(descriptor)  # releases the lock
        except OSError:
            pass
    return written == len(payload)


def acked(target: Path | None = None) -> frozenset[str]:
    """Every id acked *today*, for `now` to drop from its rows.

    Frozen because it is handed to a renderer. An unreadable or absent ledger
    is an empty set and not an error -- the dashboard renders without acks
    rather than not at all, which is the same trade `append` makes.

    Unparseable lines are skipped rather than fatal. `append` rolls back a torn
    record so this should not happen; if the file is damaged some other way, an
    ack lost is a row shown twice, and a crash here is a page nobody can load.
    """
    source = path() if target is None else target
    ids: set[str] = set()
    try:
        # `errors="replace"` and not a bare `read_text`: a damaged byte raises
        # `UnicodeDecodeError`, which is a `ValueError` and not an `OSError`,
        # so it escaped the guard below and 500'd the page this function
        # exists to keep renderable. Found in review. A mangled line then
        # fails `json.loads` and is skipped like any other damaged line.
        text = source.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return frozenset()
    # Local, to match the stamp `append` writes. An ack taken at 19:00 in
    # America/Denver is stamped with that day and expires at the end of it,
    # rather than at 18:00 the next afternoon when UTC rolls over.
    today = datetime.now().astimezone().date().isoformat()
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("kind") != "ack":
            continue
        identifier = record.get("id")
        # An ack holds for the day it was taken and no longer. D-2 said
        # permanent, on the reasoning that a changing count mints a new id so
        # a recurrence cannot hide under an old ack. That is true when a count
        # *changes* and false when it *returns*: dismiss `dirty:repo:1`, and
        # the next unrelated single dirty file in that repo is suppressed
        # forever. Review found it; the day bound closes the whole class
        # without needing to know which ids are count-keyed.
        stamp = record.get("at")
        if isinstance(identifier, str) and isinstance(stamp, str) \
                and stamp[:10] == today:
            ids.add(identifier)
    return frozenset(ids)
