"""Every write, as a named function. No caller issues SQL.

Requirement 2 and criterion 2 both turn on this file: a grep of the pack,
this repository and the dashboard for `sqlite3.connect` returns only this
library, and every write in the codebase goes through a function named here.
A caller that needs a write nobody wrote adds a function here, in review,
rather than a string somewhere else.

The one rule that is not a matter of taste: **a status change writes its
note in the same transaction**. An item's row holds its current status; its
notes hold the history. The item screen reads the order from them, the age
histogram reads a row's status timestamp from the latest one, and lead time
and days-blocked are sums over them. A status written without its note is a
history with a hole in it, and the hole is unrecoverable -- nothing later can
say when the change happened. So there is no function that writes `status`
except `transition`.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from . import paths
from .database import transaction
from .errors import SdDbError

#: The item statuses, and the note kind a change writes.
STATUSES = ("planning", "ready", "in_progress", "ready_to_send", "blocked", "done")
STATUS_CHANGE = "status_change"

#: The `state` kinds, and the one list: the schema has no CHECK on
#: `state.kind` since migration 031 (sd:3506), so a new kind is added here,
#: with no table rebuild. `record_state` refuses a kind outside it, and
#: `TheStateKindList` holds every raw insert in the pack to it.
STATE_KINDS = ("checkpoint", "verified", "restore", "watermark", "heartbeat", "check", "snooze", "view", "setting")
#: The kinds whose NULL `resolved_at` is open work; the rest are logs and
#: cursors read latest-per-key, where NULL means nothing (sd:2849).
OPEN_STATE_KINDS = ("restore", "verified", "check")


class TransitionRefused(SdDbError):
    """A status change the kind's table does not allow."""


def now() -> str:
    """One clock, in UTC, in one format. Rows are compared as text."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def stamp(value: str) -> str:
    """One caller-supplied instant, in the one shape `now()` writes.

    Rows are compared as text, so two spellings of the same instant are two
    different instants to every reader in this file. `now()` writes
    `+00:00`; `2026-09-06T19:11:39Z` is the same moment and sorts *after* it,
    because `Z` is 0x5A and `+` is 0x2B. Mixed shapes therefore order
    correctly everywhere except at a tie on the same second -- which is
    exactly where `skill_use_since` and `active_trials` are asked their
    question, and exactly the boundary the `timestamp` parameter was added to
    make answerable.

    So the shape is enforced at the write rather than expected of the caller.
    A naive stamp is refused rather than assumed to be UTC: a local stamp
    read as UTC is wrong by the offset, silently, and no caller has one.
    """
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise SdDbError(
            f"{value!r} is not an ISO-8601 timestamp; rows are compared as "
            f"text and must be written in one shape"
        ) from None
    if moment.tzinfo is None:
        raise SdDbError(
            f"{value!r} carries no timezone. Pass an aware UTC stamp -- a "
            f"naive one read as UTC is wrong by the offset and says nothing "
            f"about it"
        )
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _json(value: Any) -> str | None:
    return None if value is None else json.dumps(value, sort_keys=True)


# ---------------------------------------------------------------- repo


def upsert_repo(
    connection: sqlite3.Connection,
    path: str,
    *,
    remote: str | None = None,
    mode: str | None = None,
    runner_merge: str | None = None,
    managed: int | None = None,
    ci: str | None = None,
    pieces_source: str | None = None,
) -> str:
    """Record a repository, or update the fields given.

    `None` means "leave it": a caller that knows the remote and not the mode
    must not blank the mode by passing the row it did not read.

    `path` is a key (sd:1439). An absolute path under `$HOME` is refused
    rather than converted: every caller in the library converts with
    `paths.key` first, so one arriving here bypassed the conversion, and a
    silent fix would hide the writer that did it.
    """
    if path.startswith("/") and paths.key(path) != path:
        raise paths.PathRefused(
            f"{path} is an absolute path under $HOME; a repository is stored as "
            f"its key {paths.key(path)!r}. Convert with `sd_db.paths.key` before "
            f"calling upsert_repo"
        )
    stamp = now()
    with transaction(connection):
        connection.execute(
            "INSERT INTO repo (path, remote, mode, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(path) DO NOTHING",
            (path, remote, mode, stamp, stamp),
        )
        updates = {
            "remote": remote,
            "mode": mode,
            "runner_merge": runner_merge,
            "managed": managed,
            "ci": ci,
            "pieces_source": pieces_source,
        }
        given = {key: value for key, value in updates.items() if value is not None}
        if given:
            assignments = ", ".join(f"{key} = ?" for key in given)
            connection.execute(
                f"UPDATE repo SET {assignments}, updated_at = ? WHERE path = ?",
                (*given.values(), stamp, path),
            )
    return path


# ---------------------------------------------------------------- item


def create_item(
    connection: sqlite3.Connection,
    *,
    kind: str,
    title: str,
    status: str = "planning",
    repo: str | None = None,
    branch: str | None = None,
    path: str | None = None,
    stage: str | None = None,
    priority: int | None = None,
    due: str | None = None,
    source: str | None = None,
    external_id: str | None = None,
    source_commit: str | None = None,
    fields: dict | None = None,
    body: dict | None = None,
    session: str | None = None,
    created_at: str | None = None,
    recurrence: str | None = None,
    recurrence_anchor: str | None = None,
) -> int:
    """Open an item, and write the note that says it was opened.

    The opening note is a `status_change` from nothing, so the history starts
    at the first status rather than at the second.

    `created_at` is an argument because a migration knows something the clock
    does not: an item whose `prd.md` was written in July is not new today.
    Thirty-eight of the sixty-four `docs/work` items predate the forty-five
    day idle threshold, and seeding the clock from the import would offer all
    thirty-eight to the first sweep as freshly touched work. The note keeps
    the real time, so the history still says when the row was written.
    """
    if status not in STATUSES:
        raise TransitionRefused(f"no status {status!r}; the statuses are {', '.join(STATUSES)}")
    repo = paths.key(repo)
    stamp = now()
    opened = created_at or stamp
    with transaction(connection):
        values = {
            "kind": kind, "repo": repo, "branch": branch, "path": path,
            "title": title, "status": status, "stage": stage,
            "priority": priority, "due": due, "source": source,
            "external_id": external_id, "source_commit": source_commit,
            "fields": _json(fields), "body": _json(body),
            "created_at": opened, "updated_at": stamp,
        }
        # Named only when set, so a row without a rule is the same INSERT it
        # was before migration 012 added the columns.
        if recurrence is not None or recurrence_anchor is not None:
            values.update(recurrence=recurrence, recurrence_anchor=recurrence_anchor)
        cursor = connection.execute(
            f"INSERT INTO item ({', '.join(values)}) "
            f"VALUES ({', '.join('?' for _ in values)})",
            tuple(values.values()),
        )
        item = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO note (item, timestamp, kind, body, session) VALUES (?, ?, ?, ?, ?)",
            (item, stamp, STATUS_CHANGE, f"opened as {status}", session),
        )
    return item


def transition(
    connection: sqlite3.Connection,
    item: int,
    target: str,
    *,
    who: str,
    reason: str | None = None,
) -> str:
    """The one function that writes `item.status`.

    The note goes in the same transaction. `who` is recorded because the
    kind's table -- which arrives with the kinds that have one -- decides by
    asker as much as by target, and a change with no asker cannot be judged
    later.
    """
    with transaction(connection):
        row = connection.execute(
            "SELECT id, kind, status, source, fields FROM item WHERE id = ?", (item,)
        ).fetchone()
        if row is not None and row["kind"] == "work" and row["status"] != target and target == "done":
            raise TransitionRefused(
                "work completion requires deliver_work or cancel_work and their verified evidence"
            )
        if row is not None:
            refuse_base_status(row)
        return _transition(connection, item, target, who=who, reason=reason)


def refuse_base_status(row: Any) -> None:
    """Refuse a status write on a vault base row, naming the move that applies (sd:3972).

    Its status is its plugin map's answer to its stage, so only a stage move
    changes it: `records.edit_row`, through `_transition`. Every status write a
    person or a job asks for refuses, one of the current status too.
    """
    # Read when the rule runs: `sources` imports this module.
    from .sources.vault import SOURCE

    if row["source"] != SOURCE:
        return
    try:
        kind = json.loads(row["fields"] or "{}").get("kind")
    except (AttributeError, TypeError, ValueError, RecursionError):
        kind = None
    raise TransitionRefused(
        f"item {row['id']} is a {kind if isinstance(kind, str) and kind else 'base'} row from the vault, "
        f"and it moves by stage only: its plugin's map sets the status from the stage. Move its stage instead")


def _transition(
    connection: sqlite3.Connection, item: int, target: str, *,
    who: str, reason: str | None = None,
) -> str:
    """Trusted status primitive used by source imports and completion policy.

    User-facing callers use transition or the workflow APIs. Imports retain
    historical source truth; completion policy verifies current evidence.
    """
    if target not in STATUSES:
        raise TransitionRefused(f"no status {target!r}; the statuses are {', '.join(STATUSES)}")
    stamp = now()
    with transaction(connection):
        row = connection.execute(
            "SELECT status, kind FROM item WHERE id = ?", (item,)
        ).fetchone()
        if row is None:
            raise TransitionRefused(f"no item {item}")
        current = row["status"]
        if current == target:
            return current
        connection.execute(
            "UPDATE item SET status = ?, updated_at = ? WHERE id = ?",
            (target, stamp, item),
        )
        note = f"{current} -> {target} by {who}"
        if reason:
            note += f": {reason}"
        connection.execute(
            "INSERT INTO note (item, timestamp, kind, body, session) VALUES (?, ?, ?, ?, ?)",
            (item, stamp, STATUS_CHANGE, note, who),
        )
    return current


def set_item_fields(
    connection: sqlite3.Connection,
    item: int,
    **columns: Any,
) -> None:
    """Update an item's columns. `status` is refused here; use `transition`."""
    if "status" in columns:
        raise TransitionRefused(
            "status is written by `transition`, which writes its note in the "
            "same transaction; this function would leave the history with a hole"
        )
    allowed = {
        "kind", "repo", "branch", "path", "title", "stage", "priority", "due",
        "source", "external_id", "shipped_at", "fields", "body", "source_commit",
        "created_at",
        "piece", "parked_at", "gate_generation", "ready_digest",
        "recurrence", "recurrence_anchor",
    }
    unknown = set(columns) - allowed
    if unknown:
        raise SdDbError(f"item has no column(s) {sorted(unknown)}")
    if not columns:
        return
    if columns.get("repo") is not None:
        columns["repo"] = paths.key(columns["repo"])
    for key in ("fields", "body"):
        if key in columns and not isinstance(columns[key], (str, type(None))):
            columns[key] = _json(columns[key])
    assignments = ", ".join(f"{key} = ?" for key in columns)
    with transaction(connection):
        connection.execute(
            f"UPDATE item SET {assignments}, updated_at = ? WHERE id = ?",
            (*columns.values(), now(), item),
        )



def item_by_external(
    connection: sqlite3.Connection, source: str, external_id: str
) -> sqlite3.Row | None:
    """The row a source already landed, or None. A read, kept beside its write."""
    return connection.execute(
        "SELECT * FROM item WHERE source = ? AND external_id = ?",
        (source, external_id),
    ).fetchone()


#: The columns of an idea's row that promotion keeps in `promoted_from.row` (sd:1994).
PROMOTED_COLUMNS = ("kind", "title", "status", "stage", "path", "created_at", "fields", "body")


def upsert_item(
    connection: sqlite3.Connection,
    *,
    source: str,
    external_id: str,
    kind: str,
    title: str,
    status: str,
    who: str,
    created_at: str | None = None,
    **columns: Any,
) -> tuple[int, str]:
    """Land a row a migration read from a source, once. Returns `(id, what)`.

    `what` is `inserted`, `updated` or `unchanged`, which is what makes the
    second run of a migration assertable: criterion 5 asks each one to report
    the same counts with zero new rows, and a function that returned only an
    id could not tell those apart.

    Identity is `(source, external_id)`, the pair the schema's unique index
    already enforces. A migration that keyed on the title would land a second
    row the day somebody renamed a heading.

    **The status still goes through `transition`.** An import that wrote
    `status` directly would be the one hole in the rule this file exists to
    keep, and it would open on the largest write the system ever makes.
    A source whose status changed since the last import therefore lands a
    `status_change` note like any other change, with `who` naming the
    migration -- which is how criterion 23's "a status change made through the
    old command after the import is read back by the next import" is visible
    at all.
    """
    if columns.get("repo") is not None:
        columns["repo"] = paths.key(columns["repo"])
    found = item_by_external(connection, source, external_id)
    if found is None:
        item = create_item(
            connection,
            kind=kind,
            title=title,
            status=status,
            source=source,
            external_id=external_id,
            created_at=created_at,
            session=who,
            **columns,
        )
        return item, "inserted"

    item = int(found["id"])
    changed = {}
    for key, value in {"kind": kind, "title": title, **columns}.items():
        current = found[key] if key in found.keys() else None
        wanted = _json(value) if key in ("fields", "body") and not isinstance(
            value, (str, type(None))
        ) else value
        if current != wanted:
            changed[key] = value
    # A source that names a creation time owns it, as on insert; one that names
    # none keeps the row's, so a note dated after its first import verifies (sd:4624).
    if created_at is not None and found["created_at"] != created_at:
        changed["created_at"] = created_at
    if changed:
        set_item_fields(connection, item, **changed)
    moved = found["status"] != status
    if moved:
        _transition(connection, item, status, who=who, reason="read from the source")
    if not changed and not moved:
        return item, "unchanged"
    return item, "updated"


# ---------------------------------------------------------------- note


def add_note(
    connection: sqlite3.Connection,
    item: int,
    kind: str,
    body: str,
    *,
    session: str | None = None,
    started: str | None = None,
    ended: str | None = None,
    exit_code: int | None = None,
    output_path: str | None = None,
) -> int:
    """Any note but a status change, which only `transition` writes."""
    if kind == STATUS_CHANGE:
        raise TransitionRefused(
            "a status_change note is written by `transition`, with the status, "
            "in one transaction"
        )
    with transaction(connection):
        cursor = connection.execute(
            "INSERT INTO note (item, timestamp, kind, body, session, started, "
            "ended, exit_code, output_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item, now(), kind, body, session, started, ended, exit_code, output_path),
        )
    return int(cursor.lastrowid)


def resolve_note(connection: sqlite3.Connection, note: int) -> int:
    """Close an open note; the count it closed, 0 for an id that is absent or already closed (sd:3502)."""
    with transaction(connection):
        cursor = connection.execute(
            "UPDATE note SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
            (now(), note),
        )
    return cursor.rowcount


def reopen_note(connection: sqlite3.Connection, note: int) -> None:
    """Undo `resolve_note`: the review queue's withdrawal reopens a ruled question (sd:3635)."""
    with transaction(connection):
        connection.execute("UPDATE note SET resolved_at = NULL WHERE id = ?", (note,))


def set_note_body(connection: sqlite3.Connection, note: int, body: str) -> None:
    """Rewrite a note's body: an `exec` record names its own id, known only after `add_note` (sd:TBD)."""
    with transaction(connection):
        row = connection.execute("SELECT kind FROM note WHERE id = ?", (note,)).fetchone()
        if row is None:
            raise SdDbError(f"no note {note} to rewrite; add it with add_note first")
        if row[0] == STATUS_CHANGE:
            raise TransitionRefused("a status_change note is history that only `transition` writes")
        connection.execute("UPDATE note SET body = ? WHERE id = ?", (body, note))


# ---------------------------------------------------------------- state


def record_state(
    connection: sqlite3.Connection,
    kind: str,
    *,
    key: str | None = None,
    body: Any = None,
    timestamp: str | None = None,
) -> int:
    """One operational record: a checkpoint, a restore, a watermark, a tick.

    These are not items. They live in `state` because a record kind written
    into a table named for something else is how a schema grows by
    convention, which requirement 1 forbids.

    Every body is serialised, a `str` included: a raw string was the one
    body a reader could not parse (sd:3578).
    """
    if kind not in STATE_KINDS:
        raise SdDbError(
            f"no state kind {kind!r}; the kinds are {', '.join(STATE_KINDS)}. "
            f"A new kind is added to this list and the document first."
        )
    with transaction(connection):
        cursor = connection.execute(
            "INSERT INTO state (kind, key, timestamp, body) VALUES (?, ?, ?, ?)",
            (kind, key, timestamp or now(), _json(body)),
        )
    return int(cursor.lastrowid)


def resolve_state(connection: sqlite3.Connection, row: int) -> None:
    """Mark a state record reconciled -- what `sd restore resume` does."""
    with transaction(connection):
        connection.execute(
            "UPDATE state SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
            (now(), row),
        )


def unresolved_state(connection: sqlite3.Connection, kind: str) -> list[sqlite3.Row]:
    """Open records of one kind, oldest first. A read, kept beside its write."""
    return list(
        connection.execute(
            "SELECT * FROM state WHERE kind = ? AND resolved_at IS NULL "
            "ORDER BY timestamp",
            (kind,),
        )
    )


#: The longest a row stays hidden. A row snoozed for longer is a row nobody
#: will see again, which is a delete by another name.
SNOOZE_DAYS = 31
#: A row key is a page and the row's own id (`today:job:nightly:1`).
SNOOZE_KEY_LENGTH = 512
#: `seen` is the page's fingerprint of the row's problem, a short hash.
SNOOZE_SEEN_LENGTH = 128


def snooze(
    connection: sqlite3.Connection,
    key: str,
    until: str | None,
    *,
    seen: str | None = None,
    now: str | None = None,
) -> int:
    """Hide the Today or Health row `key` until `until`, or show it again (sd:1896).

    One `snooze` row per write, through `record_state`: the latest row for a
    key is the answer (`snoozed`), so clearing is the same write with
    `until=None`. Nothing expires a row; the reader compares the time with
    its own clock. `until` must be aware, after `now` and within
    `SNOOZE_DAYS`. `seen` is what the operator saw of the row's problem, the
    page's fingerprint: an id names a resource, not its problem, so a snooze
    holds only while the row still reads `seen` (the page's `snooze.split`).
    """
    if not isinstance(key, str) or not key.strip() or len(key) > SNOOZE_KEY_LENGTH:
        raise SdDbError(f"a snooze needs the row's key, 1 to {SNOOZE_KEY_LENGTH} characters")
    if until is not None:
        if not isinstance(seen, str) or not seen.strip() or len(seen) > SNOOZE_SEEN_LENGTH:
            raise SdDbError(f"a snooze needs what the row showed (seen), 1 to {SNOOZE_SEEN_LENGTH} characters")
        until = stamp(until)
        moment = datetime.fromisoformat(until)
        start = datetime.fromisoformat(stamp(now)) if now else datetime.now(UTC)
        if moment <= start:
            raise SdDbError(f"snooze time {until} is already past; pick a later one")
        if moment - start > timedelta(days=SNOOZE_DAYS):
            raise SdDbError(f"snooze time {until} is more than {SNOOZE_DAYS} days away; pick a nearer one")
    return record_state(connection, "snooze", key=key, body={"until": until, "seen": seen if until else None})


def snoozed(connection: sqlite3.Connection, *, now: str) -> dict[str, dict[str, str]]:
    """Every row key hidden at `now`: the time it shows again, and what it showed when snoozed.

    The latest `snooze` row per key, read through `state_by_kind_key`. A body
    this cannot read hides nothing: an unreadable snooze shows its row, and so
    does one with no `seen`, which binds to no problem.
    """
    at = datetime.fromisoformat(stamp(now))
    found: dict[str, dict[str, str]] = {}
    for row in connection.execute(
        "SELECT key, body FROM state WHERE id IN "
        "(SELECT max(id) FROM state WHERE kind = 'snooze' GROUP BY key)"
    ):
        try:
            body = json.loads(row["body"])
            moment = datetime.fromisoformat(stamp(body.get("until")))
            seen = body["seen"]
        except (TypeError, ValueError, AttributeError, KeyError, SdDbError):
            continue
        if moment > at and isinstance(seen, str) and seen:
            found[row["key"]] = {"until": moment.isoformat(timespec="seconds"), "seen": seen}
    return found


#: A view key is a Documents root key and a file under it (`system/index.html`).
VIEW_KEY_LENGTH = 512
#: A tag is a word or two the operator types, and a file carries a few.
VIEW_TAG_LENGTH = 64
VIEW_TAGS = 16
#: A file with no view row reads as this: shown, unpinned, untagged.
VIEW_CLEAR: dict[str, Any] = {"pinned": False, "hidden": False, "tags": []}
#: A root's label is the name the Documents page shows for it (sd:3986).
VIEW_LABEL_LENGTH = 60


def set_view(
    connection: sqlite3.Connection,
    key: str,
    *,
    pinned: bool | None = None,
    hidden: bool | None = None,
    tags: list[str] | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Pin, hide or tag the Documents file `key`, or clear any of them (sd:3430).

    A root key (no `/`) also takes `label`, the name the page shows for the
    root, 1 to `VIEW_LABEL_LENGTH` characters; `""` clears it (sd:3986). A
    file key refuses one. The state carries `label` only while one is set.

    One `view` row per write, through `record_state`: the latest row for a
    key is the answer (`views`). A field left `None` keeps the value the
    latest row holds, read in the same transaction, so Undo is the same call
    with the value the page showed before. Tags are trimmed and kept once, in
    the order given; `tags=[]` untags. Nothing expires a row. Returns the
    state written, the shape `views` reads.
    """
    if not isinstance(key, str) or not key.strip() or len(key) > VIEW_KEY_LENGTH:
        raise SdDbError(f"a view needs the file's key, 1 to {VIEW_KEY_LENGTH} characters")
    if pinned is None and hidden is None and tags is None and label is None:
        raise SdDbError("a view write needs pinned, hidden, tags or label")
    if label is not None:
        if "/" in key:
            raise SdDbError("a label names a root; a file key takes none")
        if not isinstance(label, str) or len(label.strip()) > VIEW_LABEL_LENGTH:
            raise SdDbError(f"a label is 1 to {VIEW_LABEL_LENGTH} characters, or empty to clear it")
        label = label.strip()
    for name, flag in (("pinned", pinned), ("hidden", hidden)):
        if flag is not None and not isinstance(flag, bool):
            raise SdDbError(f"{name} is true or false")
    if tags is not None:
        tags = _view_tags(tags)
        if tags is None:
            raise SdDbError(f"tags is a list of up to {VIEW_TAGS} words of 1 to {VIEW_TAG_LENGTH} characters")
    with transaction(connection):
        row = connection.execute(
            "SELECT body FROM state WHERE kind = 'view' AND key = ? ORDER BY id DESC LIMIT 1", (key,)
        ).fetchone()
        state = (_view(row["body"]) if row else None) or VIEW_CLEAR
        kept = state.get("label") if label is None else label
        state = {
            "pinned": state["pinned"] if pinned is None else pinned,
            "hidden": state["hidden"] if hidden is None else hidden,
            "tags": list(state["tags"]) if tags is None else tags,
        }
        if kept:
            state["label"] = kept
        record_state(connection, "view", key=key, body=state)
    return state


def views(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Every Documents file pinned, hidden or tagged: its `pinned`, `hidden` and `tags`.

    A root key carries its `label` too, and a root row with only a label is
    listed. The latest `view` row per key, read through `state_by_kind_key`.
    A key whose latest row clears all of them is not listed, and neither is one
    whose body this cannot read: an unreadable view pins, hides and tags
    nothing.
    """
    found: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        "SELECT key, body FROM state WHERE id IN "
        "(SELECT max(id) FROM state WHERE kind = 'view' GROUP BY key)"
    ):
        state = _view(row["body"])
        if state and state != VIEW_CLEAR:
            found[row["key"]] = state
    return found


def _view(body: str | None) -> dict[str, Any] | None:
    """A view row's body, or `None` when it is not one `set_view` would write.

    The tags pass the writer's own check, so a partial write never carries
    forward a tag the writer would refuse.
    """
    try:
        state = json.loads(body or "")
    except ValueError:
        return None
    if not isinstance(state, dict) or not all(isinstance(state.get(name), bool) for name in ("pinned", "hidden")):
        return None
    tags = _view_tags(state.get("tags"))
    if tags is None:
        return None
    found = {"pinned": state["pinned"], "hidden": state["hidden"], "tags": tags}
    label = state.get("label")
    if isinstance(label, str) and 0 < len(label) <= VIEW_LABEL_LENGTH:
        found["label"] = label
    return found


def _view_tags(tags: Any) -> list[str] | None:
    """`tags` trimmed and kept once, in the order given; `None` when they break a limit."""
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        return None
    kept = list(dict.fromkeys(tag.strip() for tag in tags))
    if any(not tag or len(tag) > VIEW_TAG_LENGTH for tag in kept) or len(kept) > VIEW_TAGS:
        return None
    return kept


# ---------------------------------------------------------------- settings


#: A setting key is a dotted lower-case name: `sd.copilot_review`, `dashboard.home_tiles`.
SETTING_KEY = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")
SETTING_KEY_LENGTH = 128
#: The longest value: the Home tile list's text is the largest one written.
SETTING_VALUE_LENGTH = 16384
#: `set_setting`'s `before` when the caller asks for no stale check.
UNCHECKED: Any = object()


class SettingStale(SdDbError):
    """`set_setting` was told what the value was, and the row says otherwise."""


def set_setting(
    connection: sqlite3.Connection,
    key: str,
    value: str | None,
    *,
    before: Any = UNCHECKED,
) -> str | None:
    """Set the fleet-wide setting `key` to `value`, or clear it with `None` (sd:3989).

    One `setting` row per write, through `record_state`: the latest row for a
    key is the answer (`read_settings`), and a cleared key is a row too, so an old
    file value cannot come back. `before`, when given, is the value the caller
    showed (`None` for unset); a row that holds another refuses with
    `SettingStale`, read in the same transaction. Returns the value the key
    held before, `None` when unset or never held.
    """
    _setting_key(key)
    if value is not None and (not isinstance(value, str) or not value or len(value) > SETTING_VALUE_LENGTH):
        raise SdDbError(f"a setting value is text of 1 to {SETTING_VALUE_LENGTH} characters, or none to unset")
    with transaction(connection):
        was = _read_settings(connection, [key]).get(key)
        if before is not UNCHECKED and before != was:
            raise SettingStale(f"{key} changed since it was read; read it again")
        record_state(connection, "setting", key=key, body={"value": value})
    return was


def read_settings(connection: sqlite3.Connection, keys: list[str]) -> dict[str, str | None]:
    """The latest `setting` row for each of `keys` the database has held: its value, `None` when cleared.

    A key with no row is absent from the answer, which is how a caller tells
    "never held" (read the old file) from "cleared" (read nothing). A body
    this cannot read raises: a setting nobody can read is unknown, not unset.
    """
    for key in keys:
        _setting_key(key)
    return _read_settings(connection, keys)


def _read_settings(connection: sqlite3.Connection, keys: list[str]) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for key in keys:
        row = connection.execute(
            "SELECT body FROM state WHERE kind = 'setting' AND key = ? ORDER BY id DESC LIMIT 1", (key,)
        ).fetchone()
        if row is None:
            continue
        try:
            value = json.loads(row["body"] or "")["value"]
        except (ValueError, TypeError, KeyError):
            raise SdDbError(f"the {key} setting row does not read; set it again") from None
        if value is not None and not isinstance(value, str):
            raise SdDbError(f"the {key} setting row holds a {type(value).__name__}, not text; set it again")
        found[key] = value
    return found


def _setting_key(key: Any) -> None:
    if not isinstance(key, str) or len(key) > SETTING_KEY_LENGTH or not SETTING_KEY.fullmatch(key):
        raise SdDbError(f"a setting key is a dotted lower-case name of up to {SETTING_KEY_LENGTH} characters")


# ---------------------------------------------------------------- shadow


def upsert_shadow(
    connection: sqlite3.Connection,
    *,
    tracker: str,
    url: str,
    repo: str | None = None,
    number: int | None = None,
    kind: str | None = None,
    title: str | None = None,
    state: str | None = None,
    author: str | None = None,
    reason: str | None = None,
    merged_at: str | None = None,
    closed_at: str | None = None,
    branch: str | None = None,
    linked_issues: list[str] | None = None,
) -> None:
    """A tracker's row, keyed by `(tracker, url)`. Seen once, then kept current.

    `reason` (migration 34) is `assigned`, `filed` or `watched`. None is
    unknown and keeps the stored value: an importer names none, and a collect
    whose stronger bucket failed cannot say the row lost it.

    `merged_at` and `closed_at` (migration 38, sd:5303) follow the same rule,
    except that a row written `open` loses both: a reopened row is not settled.

    `branch` and `linked_issues` (migration 38, sd:5315) are a pull request's
    head branch and the urls of the issues it closes; None keeps the stored
    value, and `[]` says it closes none.

    The conflict target is both columns, so this updates only the row this
    tracker already owns. Until sd:603 it was `url` alone and the update set
    `tracker = excluded.tracker`, which meant the last collector to see a url
    took the row from whoever held it -- silently, because reassigning an
    owner violates no constraint. A second tracker writing the same url now
    gets its own row instead.
    """
    stamp = now()
    with transaction(connection):
        connection.execute(
            "INSERT INTO shadow (tracker, repo, url, number, kind, title, state, "
            "author, reason, merged_at, closed_at, branch, linked_issues, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(tracker, url) DO UPDATE SET "
            "repo = excluded.repo, number = excluded.number, kind = excluded.kind, "
            "title = excluded.title, state = excluded.state, "
            "author = excluded.author, reason = COALESCE(excluded.reason, shadow.reason), "
            "merged_at = CASE WHEN excluded.state = 'open' THEN NULL "
            "ELSE COALESCE(excluded.merged_at, shadow.merged_at) END, "
            "closed_at = CASE WHEN excluded.state = 'open' THEN NULL "
            "ELSE COALESCE(excluded.closed_at, shadow.closed_at) END, "
            "branch = COALESCE(excluded.branch, shadow.branch), "
            "linked_issues = COALESCE(excluded.linked_issues, shadow.linked_issues), "
            "last_seen = excluded.last_seen",
            (tracker, repo, url, number, kind, title, state, author, reason, merged_at, closed_at, branch,
             None if linked_issues is None else json.dumps(list(linked_issues)), stamp, stamp),
        )


def open_shadow_issues(connection: sqlite3.Connection, *, tracker: str, repos: tuple[str, ...]) -> list[sqlite3.Row]:
    """The stored open issue rows of `repos`, matched in any case as GitHub reads them (sd:4880).

    Pull requests and other repositories are left out.
    """
    lowered = [repo.lower() for repo in repos]
    if not lowered:
        return []
    return connection.execute(
        "SELECT id, url FROM shadow WHERE tracker = ? AND kind = 'issue' AND state = 'open' "
        f"AND lower(repo) IN ({', '.join('?' * len(lowered))}) ORDER BY id", (tracker, *lowered)).fetchall()


def close_shadow(connection: sqlite3.Connection, *, tracker: str, closed: dict[str, str | None]) -> int:
    """Close the open rows of `closed`'s urls, each one a direct read said is no open issue (sd:4880).

    Each url maps to the close time that read gave, or None when it gave none
    (sd:5303). Returns the count.
    """
    with transaction(connection):
        cursor = connection.executemany(
            "UPDATE shadow SET state = 'closed', closed_at = ? WHERE tracker = ? AND url = ? AND state = 'open'",
            [(at, tracker, url) for url, at in closed.items()])
    return cursor.rowcount


# ----------------------------------------------------------- assignment


def create_assignment(
    connection: sqlite3.Connection,
    *,
    role: str,
    status: str,
    item: int | None = None,
    provider: str | None = None,
    after: int | None = None,
    parent: int | None = None,
    lane: str = "serial",
    budget_minutes: int | None = None,
    budget_usd: float | None = None,
) -> int:
    with transaction(connection):
        cursor = connection.execute(
            "INSERT INTO assignment (item, role, provider, status, started, after, "
            "parent, lane, budget_minutes, budget_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item, role, provider, status, now(), after, parent, lane,
             budget_minutes, budget_usd),
        )
    return int(cursor.lastrowid)


def update_assignment(connection: sqlite3.Connection, assignment: int, **columns: Any) -> None:
    """Update assignment details; entering running is an atomic queue claim.

    A caller may dispatch only after this succeeds. A cancelled assignment is
    terminal, so a worker holding an old queue snapshot cannot resurrect it.
    """
    allowed = {"provider", "status", "started", "ended", "cost", "result",
               "after", "parent", "lane", "budget_minutes", "budget_usd", "phase"}
    unknown = set(columns) - allowed
    if unknown:
        raise SdDbError(f"assignment has no column(s) {sorted(unknown)}")
    if not columns:
        return
    assignments = ", ".join(f"{key} = ?" for key in columns)
    with transaction(connection):
        current = connection.execute("SELECT status FROM assignment WHERE id = ?", (assignment,)).fetchone()
        if current is None:
            raise SdDbError(f"no assignment {assignment}")
        if current["status"] == "cancelled" and columns.get("status", "cancelled") != "cancelled":
            raise SdDbError(f"assignment {assignment} is cancelled and cannot be reopened")
        if columns.get("status") == "running" and current["status"] != "queued":
            raise SdDbError(f"assignment {assignment} is not queued; cannot claim it")
        connection.execute(
            f"UPDATE assignment SET {assignments} WHERE id = ?",
            (*columns.values(), assignment),
        )


# ---------------------------------------------------------------- cost


def record_cost(
    connection: sqlite3.Connection,
    *,
    source: str,
    provider: str | None = None,
    bill: str | None = None,
    call_id: str | None = None,
    role: str | None = None,
    repo: str | None = None,
    assignment: int | None = None,
    pass_: str | None = None,
    owner_pid: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    usd: float | None = None,
    window_minutes: int | None = None,
    used_percent: float | None = None,
) -> int:
    """One cost row. `source` says what kind of number it is."""
    repo = paths.key(repo)
    with transaction(connection):
        cursor = connection.execute(
            "INSERT INTO cost (call_id, timestamp, provider, bill, role, repo, "
            "assignment, pass, owner_pid, tokens_in, tokens_out, usd, "
            "window_minutes, used_percent, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (call_id, now(), provider, bill, role, repo, assignment, pass_,
             owner_pid, tokens_in, tokens_out, usd, window_minutes,
             used_percent, source),
        )
    return int(cursor.lastrowid)


# ----------------------------------------------------- skills and trials


def record_skill_use(
    connection: sqlite3.Connection,
    skill: str,
    *,
    surface: str | None = None,
    mode: str | None = None,
    cwd: str | None = None,
    timestamp: str | None = None,
) -> int:
    """One use of one skill. `timestamp` defaults to now, and often must not.

    A `PreToolUse` hook records a use as it happens and takes the default.
    The nightly parse of `~/.codex/sessions` does not: it reads sessions that
    ran while it was asleep, and stamping them with the parse time would file
    a week of Codex use under the morning the parse first ran. The parameter
    exists for the reader that knows when the thing happened.
    """
    cwd = paths.key(cwd)
    with transaction(connection):
        cursor = connection.execute(
            "INSERT INTO skill_use (timestamp, skill, surface, mode, cwd) "
            "VALUES (?, ?, ?, ?, ?)",
            (now() if timestamp is None else stamp(timestamp), skill, surface, mode, cwd),
        )
    return int(cursor.lastrowid)


def start_trial(connection: sqlite3.Connection, skill: str, expires: str) -> None:
    with transaction(connection):
        connection.execute(
            "INSERT INTO trial (skill, started, expires) VALUES (?, ?, ?) "
            "ON CONFLICT(skill) DO UPDATE SET started = excluded.started, "
            "expires = excluded.expires",
            (skill, now(), stamp(expires)),
        )


def end_trial(connection: sqlite3.Connection, skill: str) -> bool:
    """Remove a trial row. True when there was one, so a caller can say so.

    The installer removes an expired trial that earned no use, and the
    sentence it prints is the reason the boolean is returned rather than
    discarded: "removed, no use in thirty days" is a different report from
    "nothing to remove", and a caller that cannot tell them apart prints the
    first one when the second is true.
    """
    with transaction(connection):
        cursor = connection.execute("DELETE FROM trial WHERE skill = ?", (skill,))
    return cursor.rowcount > 0


def trials(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every trial row, in skill order. The installer's second input.

    Unfiltered on purpose. The installer needs the expired ones too -- an
    expired trial with no use is what it removes -- so a reader that returned
    only the active ones would make the removal invisible to the one caller
    that has to perform it. `active_trials` is the filtered view, and it is
    built from this one rather than from a second query.
    """
    return list(connection.execute("SELECT * FROM trial ORDER BY skill"))


def active_trials(
    connection: sqlite3.Connection, moment: str | None = None
) -> list[sqlite3.Row]:
    """The trials that have not expired, at `moment` or now.

    Criterion 24's "the union of the paths plus active trials" is exactly
    this list. The comparison is a string comparison over ISO-8601 UTC
    stamps, which orders correctly because every stamp reaching a row went
    through `stamp()` and comes back out in one shape. It used to say the
    caller was *expected* to use that shape, which is not a property a
    reader can rely on; `start_trial` normalizes now, and so does the
    `moment` a caller passes here.
    """
    when = now() if moment is None else stamp(moment)
    return [row for row in trials(connection) if row["expires"] > when]


def skill_use_since(
    connection: sqlite3.Connection, skill: str, since: str
) -> int:
    """How many times a skill was used at or after `since`.

    Criterion 25 removes an expired trial "with no `skill_use` rows", and the
    window that matters is the trial's own: a row from before the trial
    started is not evidence the trial earned anything. So the caller passes
    the trial's `started`, never a bare zero, and the count answers a
    question about the trial rather than about the skill's whole history.

    `since` is normalized for the same reason the writes are: a `...Z` stamp
    and a `...+00:00` stamp of the same second compare differently, and this
    comparison is the one that lives on that boundary.
    """
    row = connection.execute(
        "SELECT count(*) AS uses FROM skill_use WHERE skill = ? AND timestamp >= ?",
        (skill, stamp(since)),
    ).fetchone()
    return int(row["uses"])


# --------------------------------------------------- providers and bills


def set_provider_state(
    connection: sqlite3.Connection,
    name: str,
    *,
    enabled: bool | None = None,
    reason: str | None = None,
    author_rank: int | None = None,
    reviewer_rank: int | None = None,
) -> None:
    """What the dashboard changes about a provider. Identity stays in the file."""
    columns: dict[str, Any] = {}
    if enabled is not None:
        columns["enabled"] = int(enabled)
    if reason is not None:
        columns["reason"] = reason
    if author_rank is not None:
        columns["author_rank"] = author_rank
    if reviewer_rank is not None:
        columns["reviewer_rank"] = reviewer_rank
    if not columns:
        return
    assignments = ", ".join(f"{key} = ?" for key in columns)
    with transaction(connection):
        connection.execute(
            f"UPDATE provider SET {assignments} WHERE name = ?",
            (*columns.values(), name),
        )


def set_bill_cap(connection: sqlite3.Connection, name: str, cap_usd_month: float | None) -> None:
    with transaction(connection):
        connection.execute(
            "UPDATE bill SET cap_usd_month = ? WHERE name = ?", (cap_usd_month, name)
        )
