"""Open followups for a checkout, read from the row and rendered for a hook.

Continuity used to come from one file. `bin/sd-handoff` wrote a packet, and
`bin/sd-handoff-restore` injected it -- but only if somebody had run the write
by hand, and nothing runs it automatically. A session that dies mid-task
leaves no packet, so the next one starts from nothing. That is the gap item A's
criterion 29 names: a session killed mid-task and restarted in the same
directory should begin from the followups it had named, with none lost.

A followup is already a durable row. `sd_db.add_note(kind='followup')` writes
one, `resolve_note` closes it, and the vocabulary is the `CHECK` on `note.kind`
rather than anything this pack declares. Nothing here has ever called either,
which is why the row is a continuity source in name only until this module
reads it back.

**This module exists because a suffixless file cannot be imported.**
`bin/sd-handoff-restore` and `bin/sd-note` both need the same two answers --
which item a directory means, and what is still open under it -- and Python
cannot import either from the other. Putting the pair here is one header paid
once instead of the same reader written twice and drifting.

**It reads and never claims.** The packet is claimed on injection, by rename,
so exactly one session gets it. A row is not: three sessions restarting in one
directory all deserve the same open followups, and a followup stops appearing
when the work is done and somebody resolves it -- not when a session happened
to read it. Nothing here writes.

**Scope is the checkout, not one item.** The hook knows a directory and no
item name; it cannot ask for "this item's followups" because it has no item.
So the query is every open followup on an active item of this repository,
oldest first. `done` items are excluded: their followups are finished work,
and a session restarting has no use for them.

`sd_db` is imported inside the functions, not at module import, for
`bin/sd_restore.py`'s reason -- the library reaches this virtualenv through the
pack's installer, and before that has run every other verb and hook must keep
working. Callers differ in what they may say about its absence: `bin/sd-note`
prints the remedy, and a `SessionStart` hook must print nothing at all, so this
module raises and lets each caller decide.
"""

from __future__ import annotations

import pathlib

#: Why the reader cannot run yet, when it cannot. Printed by `bin/sd-note`;
#: swallowed by the hooks, which exit 0 silently rather than break a session.
NOT_INSTALLED = (
    "sd_db is not installed in this virtualenv. Followups are rows; install "
    "the library with the pack's installer (`sd-install`), which provisions "
    "it from the `system` checkout at its tag, then run this again."
)

#: The one note kind this module reads. `add_note` accepts six more and
#: `transition` owns the seventh; a session resuming wants only what is left
#: to do.
FOLLOWUP = "followup"

#: Statuses whose followups a restarting session still owes work on. `done`
#: is the omission: a finished item's open followup is a bookkeeping slip,
#: not a thing to hand the next session.
ACTIVE = ("planning", "ready", "in_progress", "ready_to_send", "blocked")


class RowsRefusal(Exception):
    """Something the caller must settle before followups can be read."""


def library():
    """Import `sd_db`, or refuse with the remedy rather than a traceback."""
    try:
        # May or may not be resolvable at type-check time: `sd_db` is built
        # into this virtualenv by the pack's installer, from the `system`
        # checkout, and this repository does not vendor it. `pyproject.toml`
        # carries the override rather than an inline ignore here, which
        # `warn_unused_ignores` turns into a failure on any machine that has
        # run `make setup`. The ImportError below is a supported state.
        import sd_db
    except ImportError:
        raise RowsRefusal(NOT_INSTALLED) from None
    return sd_db


def connect(sd_db, *, write: bool = False):
    try:
        return sd_db.connect(write=write)
    except Exception as error:
        raise RowsRefusal(str(error)) from None


def open_followups(connection, repo: str) -> list[dict]:
    """Every unresolved followup on an active item of `repo`, oldest first.

    Ordered by `(timestamp, id)` and not by timestamp alone: two notes written
    in the same second are ordered by the sequence they were written in, so a
    session gets its own list back in the order it named things.
    """
    rows = connection.execute(
        "SELECT note.id AS id, note.body AS body, note.timestamp AS timestamp, "
        "item.title AS title, item.status AS status "
        "FROM note JOIN item ON item.id = note.item "
        "WHERE note.kind = ? AND note.resolved_at IS NULL AND item.repo = ? "
        "ORDER BY note.timestamp, note.id",
        (FOLLOWUP, repo),
    )
    # `status` is filtered here and not in an `IN (...)` clause, which would
    # need the placeholders interpolated into the statement. Every value would
    # still be a bound parameter, but a query built by string formatting is a
    # shape a reader has to check rather than one they can see is safe -- and
    # the row count this walks is one checkout's open followups.
    return [dict(row) for row in rows if row["status"] in ACTIVE]


def item_for(connection, sd_db, root, item_dir):
    """The row one work-item directory names, or None when there is none.

    The resolver is `sd_lib`'s, so a writer and the dashboard key an item the
    same way: `external_id` builds the identity off the *main* worktree root,
    and `item_by_external` is the unique index that reads it back.
    """
    import sd_lib

    identity = sd_lib.external_id(root, item_dir)
    row = sd_db.writes.item_by_external(connection, sd_lib.ITEM_ROW_SOURCE, identity)
    return None if row is None else dict(row)


def render(rows: list[dict]) -> list[str]:
    """Open followups as context lines, or an empty list when there are none.

    Grouped under the item that owns them, because a checkout with two active
    items hands back two lists and an ungrouped run of bullets says nothing
    about which work each belongs to.
    """
    if not rows:
        return []
    lines = [
        f"Open followups on this checkout ({len(rows)}), read from the "
        "database rather than from a handoff packet. These are work you named "
        "and have not resolved; a finished one is closed with `sd-note "
        "--resolve <id>`.",
    ]
    seen = ""
    for row in rows:
        title = str(row.get("title") or "(untitled item)")
        if title != seen:
            lines.extend(["", f"{title}:"])
            seen = title
        lines.append(f"- [{row['id']}] {row['body']}")
    return lines


def followups_for(root) -> list[str]:
    """The whole read for a hook: open, query, render, close. Never writes.

    `root` is resolved to the main worktree here rather than by the caller.
    Rows are keyed by the registered checkout, and a linked worktree was never
    added to the `repo` table -- so a session started inside one asks about a
    path that holds no rows and silently gets nothing back, which is the exact
    shape of the loss this criterion exists to stop.
    """
    import sd_lib

    sd_db = library()
    connection = connect(sd_db)
    try:
        base = str(sd_lib.main_worktree_root(pathlib.Path(root).resolve()))
        return render(open_followups(connection, base))
    finally:
        connection.close()
