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
from datetime import datetime, timezone
from pathlib import Path


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


def append(kind: str, target: Path | None = None, **fields: object) -> None:
    """Append one record. Never raises, never blocks a response.

    `at` is stamped here rather than by the caller: three call sites write to
    this file and a criterion that compares their timestamps needs them taken
    the same way.
    """
    record = dict(fields)
    record["kind"] = kind
    record["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    destination = path() if target is None else target
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # 0o600 to match the packets under the same root: this records when
        # this machine's dashboard was reached and by what.
        descriptor = os.open(
            str(destination), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
        )
    except OSError:
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        start = os.lseek(descriptor, 0, os.SEEK_END)
        written = 0
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


def acked(target: Path | None = None) -> frozenset[str]:
    """Every id acked so far, for `now` to drop from its rows.

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
        text = source.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("kind") == "ack":
            identifier = record.get("id")
            if isinstance(identifier, str):
                ids.add(identifier)
    return frozenset(ids)
