"""The SQLite index: observability only, rebuildable, never an input.

The storage doctrine gives every fact exactly one writable home, and issues do
not live here -- they live in GitHub and Jira. This file is a cache of what the
trackers last saw, so that the Issues tab can render without four network calls
per page load and so "what changed since yesterday" is answerable at all.

Two consequences follow, and both are deliberate rather than incidental:

* `rm ~/.cache/sd-ai-command-pack/index.sqlite` loses *time*, never a fact. The
  next collect rebuilds it from the trackers. Nothing reads this database to
  decide anything -- no gate, no lint rule, no merge check.
* Rows are never deleted. An issue that closes is updated in place with
  `state='closed'`; an issue that stops matching the search is left exactly as
  it was, carrying the `last_seen` that says when the index last had evidence.

The honest gap in that second point, named here rather than discovered later:
because collection is windowed (see `github.py` and `jira.py`), a row whose only change was
a close **outside** the window is never revisited, so the index can hold an
`open` row for something closed months ago. That is why `last_seen` is a column
and why the page shows it. The fix is not a wider window -- it is remembering
that this database is a cache and the tracker is the truth.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

# Kept as one statement per entry so a future migration reads as a diff rather
# than as a rewrite of one long string.
SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS issue (
        id          TEXT PRIMARY KEY,
        tracker     TEXT NOT NULL,
        url         TEXT NOT NULL,
        repo        TEXT NOT NULL,
        number      INTEGER,
        kind        TEXT NOT NULL,
        title       TEXT NOT NULL,
        state       TEXT NOT NULL,
        author      TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        why         TEXT NOT NULL,
        first_seen  TEXT NOT NULL,
        last_seen   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tracker_watermark (
        tracker      TEXT PRIMARY KEY,
        collected_at TEXT NOT NULL,
        window_start TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS issue_by_state ON issue(state, updated_at)",
    "CREATE INDEX IF NOT EXISTS issue_by_tracker ON issue(tracker, last_seen)",
)


def index_path(environ: dict[str, str] | None = None) -> Path:
    """`~/.cache/sd-ai-command-pack/index.sqlite`, honouring `XDG_CACHE_HOME`.

    The cache root, not the state root: `~/.local/state/` holds the handoff
    packets, which are written once and cannot be regenerated, and step 6's
    machine cleanup deletes legacy subdirectories *under that root by name*.
    Putting a rebuildable database beside unrebuildable packets would invite
    exactly the sweep that must never reach them.
    """
    env = os.environ if environ is None else environ
    base = env.get("XDG_CACHE_HOME") or ""
    home = Path(base) if base else Path.home() / ".cache"
    return home / "sd-ai-command-pack" / "index.sqlite"


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) and apply the schema.

    `IF NOT EXISTS` throughout, so this is safe to call on every collect and
    there is no separate "init" step somebody can forget to run.
    """
    target = index_path() if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target))
    connection.row_factory = sqlite3.Row
    # A collect is a burst of small writes; the default journal turns each into
    # a filesystem sync. WAL is the one pragma here and it buys throughput, not
    # durability semantics we depend on -- losing the tail of a collect costs a
    # refresh.
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    for statement in SCHEMA:
        connection.execute(statement)
    connection.commit()
    return connection


def row_id(tracker: str, url: str) -> str:
    """The upsert key: tracker plus canonical URL.

    The URL alone would very nearly do -- two trackers cannot mint the same
    one. Prefixing anyway means a row's key says which collector owns it, so
    "delete everything Jira wrote" stays a one-line statement rather than a
    join, and a future tracker cannot silently adopt another's rows.
    """
    return f"{tracker}:{url}"


def upsert_issues(
    connection: sqlite3.Connection, issues: list[dict], now: str
) -> tuple[int, int]:
    """Write the collected issues, returning (inserted, updated).

    `first_seen` survives an update and `last_seen` moves: the pair is what
    makes "new to me since Friday" answerable without a separate event log,
    which is the shape the journals took and the reason they are gone.

    `why[]` is replaced rather than merged, because the tracker already unioned
    the buckets for this collect and a stale reason is worse than a missing
    one: an issue that no longer requests your review should stop saying it
    does the moment the collector notices.
    """
    inserted = 0
    updated = 0
    for issue in issues:
        key = row_id(issue["tracker"], issue["url"])
        why = json.dumps(sorted(issue.get("why") or []))
        existing = connection.execute(
            "SELECT first_seen FROM issue WHERE id = ?", (key,)
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO issue (id, tracker, url, repo, number, kind, title,
                                   state, author, updated_at, why,
                                   first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    issue["tracker"],
                    issue["url"],
                    issue.get("repo", ""),
                    issue.get("number"),
                    issue.get("kind", ""),
                    issue.get("title", ""),
                    issue.get("state", ""),
                    issue.get("author", ""),
                    issue.get("updated_at", ""),
                    why,
                    now,
                    now,
                ),
            )
            inserted += 1
            continue
        connection.execute(
            """
            UPDATE issue
               SET tracker = ?, url = ?, repo = ?, number = ?, kind = ?,
                   title = ?, state = ?, author = ?, updated_at = ?, why = ?,
                   last_seen = ?
             WHERE id = ?
            """,
            (
                issue["tracker"],
                issue["url"],
                issue.get("repo", ""),
                issue.get("number"),
                issue.get("kind", ""),
                issue.get("title", ""),
                issue.get("state", ""),
                issue.get("author", ""),
                issue.get("updated_at", ""),
                why,
                now,
                key,
            ),
        )
        updated += 1
    connection.commit()
    return inserted, updated


def watermark(connection: sqlite3.Connection, tracker: str) -> str | None:
    """When this tracker last collected successfully, or None on a first run."""
    row = connection.execute(
        "SELECT collected_at FROM tracker_watermark WHERE tracker = ?", (tracker,)
    ).fetchone()
    return row["collected_at"] if row else None


def set_watermark(
    connection: sqlite3.Connection, tracker: str, collected_at: str, window_start: str
) -> None:
    """Record a *successful* collect.

    Only ever called after a collect that returned without error. A failed or
    partial collect deliberately leaves the watermark where it was, so the next
    run re-queries the window that was missed instead of stepping over it --
    the one way a windowed collector loses data permanently.
    """
    connection.execute(
        """
        INSERT INTO tracker_watermark (tracker, collected_at, window_start)
        VALUES (?, ?, ?)
        ON CONFLICT(tracker) DO UPDATE SET
            collected_at = excluded.collected_at,
            window_start = excluded.window_start
        """,
        (tracker, collected_at, window_start),
    )
    connection.commit()


# The two reasons that mean somebody is waiting on *you*. Everything else --
# `mentioned`, `author`, `filed`, `watching`, `matched` -- is information about
# work you are near, not work that is blocked on you.
#
# Defined here rather than in each surface because "needs you" is one claim: a
# dashboard tab and an `sd-status` line that disagreed about it would be two
# answers to the same question, and the one you happened to read would be the
# one you believed.
NEEDS_YOU = frozenset({"assigned", "review-requested"})


def needs_you(row: dict) -> bool:
    """Whether this row is waiting on the operator. Closed rows never are."""
    return row.get("state") == "open" and bool(NEEDS_YOU & set(row.get("why") or []))


def issues(connection: sqlite3.Connection, state: str | None = None) -> list[dict]:
    """Every indexed issue, newest activity first; `why` decoded back to a list."""
    if state is None:
        rows = connection.execute(
            "SELECT * FROM issue ORDER BY updated_at DESC"
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM issue WHERE state = ? ORDER BY updated_at DESC", (state,)
        ).fetchall()
    out = []
    for row in rows:
        record = dict(row)
        try:
            record["why"] = json.loads(record["why"])
        except (TypeError, ValueError):
            record["why"] = []
        out.append(record)
    return out
