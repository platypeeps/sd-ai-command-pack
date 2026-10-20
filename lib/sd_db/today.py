"""The sections `sd today`, `sd-status` and the dashboard show, as plain dicts (sd:5098).

Each function reads the shared database at run time and takes an optional
`repos` filter: the `item.repo` keys (`~/repos/name`) to keep, or None for
every repository. A lane entry is keyed by its GitHub repository, so it is
matched to a key through the `repo` row's remote. Every row carries `id` (the
item), `repo` (its key, or None) and `title`; the rest is per section, as each
docstring says. `sections` reads them all in the one order the renderers use.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .reads import REVIEW_BATCH, _now, _parse, _unparked_clause, open_notes, today_items
from .reporting import _current_basis
from .ship import this_host

#: `sd_lane.KEY_PREFIX`: a lane entry is the newest `checkpoint` row of its key.
LANE_KEY_PREFIX = "lane:v1:"
#: `workflow.ACTIVE_ASSIGNMENTS`, copied because `workflow` imports `reads`, which this reads.
ACTIVE_ASSIGNMENTS = ("queued", "running", "ending")
#: Lane states in the order `landing` lists them; the queue holds the first two.
LANE_ORDER = ("running", "pending", "prepared", "handed_back", "failed", "skipped")
#: The section keys of `sections`, in the order every renderer prints them.
ORDER = ("attention", "operations", "decisions", "landing", "delivered", "planned", "blocked", "unscheduled", "followups", "work")
#: A choice line of a decision, as the dashboard's Decisions reads one (sd:3012).
OPTION_LINE = re.compile(r"^[ \t]*Option:[ \t]*\S", re.MULTILINE)
#: Kinds that are not work to schedule: ideas wait for promotion, reports for acknowledgement.
_UNSCHEDULED_SKIPS = ("idea", "work-idea", "personal-idea", "report")
_DELIVERED_AT = re.compile(r"\bdelivered at ([0-9a-f]{40,64})\b")
_CODE_DELIVERY = re.compile(r"Code delivery (\S+) at ([0-9a-f]{40,64})\b")
_PULL = re.compile(r"/pull/([0-9]+)\b")
_BLOCKED_BECAUSE = re.compile(r"-> blocked by [^:\n]*: *(.*)")
_WAITING = re.compile(r"\s*(?:waiting|waits)\s+(?:on|for)\b", re.IGNORECASE)


def _keep(repos: Iterable[str] | None) -> set[str | None] | None:
    return None if repos is None else set(repos)


def _in(column: str, keep: set[str | None] | None) -> tuple[str, list[Any]]:
    """A SQL condition keeping `keep`'s repositories, and its parameters."""
    if keep is None:
        return "1", []
    named = sorted(key for key in keep if key is not None)
    return f"{column} IN ({', '.join('?' for _ in named)})", named


def _first_line(text: Any) -> str:
    return str(text or "").strip().partition("\n")[0]


def _attention_rows(connection: sqlite3.Connection, keep: set[str | None] | None) -> list[tuple[Any, Any]]:
    """Each open report whose fields say it needs attention, newest first, with that `attention` value."""
    where, values = _in("repo", keep)
    rows = connection.execute(
        f"SELECT * FROM item WHERE kind = 'report' AND source IS NOT 'brief' AND status != 'done' AND {where}"
        " ORDER BY created_at DESC, id DESC", values).fetchall()
    found = []
    for row in rows:
        try:
            why = json.loads(row["fields"] or "{}").get("attention")
        except (ValueError, AttributeError):
            why = "fields unreadable"
        if why:
            found.append((row, why))
    return found


def attention(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None) -> list[dict]:
    """Open reports whose fields say they need attention, newest first: `status`, `why`, `at`.

    Unreadable fields count, as an unknown is no pass.
    """
    return [{"id": row["id"], "repo": row["repo"], "status": row["status"], "title": row["title"],
             "why": why if isinstance(why, str) else "", "at": row["created_at"]}
            for row, why in _attention_rows(connection, _keep(repos))]


#: The finding of a report whose fields do not parse: it may name this machine, so it is a row, not a pass.
FIELDS_UNREAD = "fields unreadable; whether this report names this machine is unknown"


def _host_findings(basis: Any, host: str) -> list[str]:
    """The lines of a report's attention basis that name `host`, each cut to its finding.

    A cron report writes `<job> on <host>: <finding>` per line, and a failed
    run `job exited N on <host>`; the second is its own finding. A line that
    only heads the next ones (`App Store updates pending:` over
    `App Store updates pending: <app>`) is dropped, as the lines under it say it.
    """
    pattern = re.compile(rf"^(?P<head>.*?) on {re.escape(host)}(?::[ \t]*(?P<finding>.*)|[ \t]*)$")
    found = [(match["finding"] or match["head"]).strip()
             for match in map(pattern.match, str(basis or "").splitlines()) if match]
    return [text for text in found
            if not (text.endswith(":") and any(other != text and other.startswith(text) for other in found))]


def machine_gate(gate: Any) -> dict | None:
    """`_gate`'s holders and waiters, with the slot cap, the load and its limit when the snapshot has them."""
    found = _gate(gate)
    if found is not None and isinstance(gate, dict):
        found.update({key: gate.get(key) for key in ("slots", "load", "load_max")})
    return found


def operations(connection: sqlite3.Connection, *, host: str | None = None, gate: Any = None) -> dict:
    """This machine's findings and gate (pack sd:5432): `host`, `findings` and `gate` (`machine_gate`).

    The reports are `attention`'s, every repository's: a machine belongs to
    none. Each finding row is one line of a report's current basis
    (`reporting._current_basis`) that names `host`, by default `this_host`,
    `hostname -s` lower-cased: `id`, `repo`, `title`, `job` (the
    `external_id` before `:`) and `finding`. A report with no `fields.report`
    names no host; one whose fields do not parse is a `FIELDS_UNREAD` row.
    """
    host = host or this_host()
    findings = []
    for row, _ in _attention_rows(connection, None):
        try:
            lines = _host_findings(_current_basis({"fields": row["fields"] or "{}"}), host)
        except KeyError:
            lines = []
        except (ValueError, TypeError, AttributeError):
            lines = [FIELDS_UNREAD]
        job = str(row["external_id"] or "").partition(":")[0] or "-"
        findings += [{"id": row["id"], "repo": row["repo"], "title": row["title"], "job": job, "finding": text}
                     for text in lines]
    return {"host": host, "findings": findings, "gate": machine_gate(gate)}


def _notes(connection: sqlite3.Connection, kind: str, keep: set[str | None] | None, *,
           batches: bool = True) -> list[dict]:
    return [{"id": note["item"], "note": note["id"], "repo": note["item_repo"], "status": note["item_status"],
             "title": _first_line(note["body"]),
             "item_title": note["item_title"], "at": note["timestamp"]}
            for note in open_notes(connection, kind, batches=batches) if keep is None or note["item_repo"] in keep]


def decisions(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None) -> list[dict]:
    """Open questions with two or more `Option:` lines, oldest first: `note` (what `--answers` takes),
    `title` (the question's first line), `item_title`, `at`.

    A review batch's questions are `review_questions`' count, not rows: the
    dashboard's Review page labels them, and `sd-next` walks these rows (sd:5130).
    """
    keep = _keep(repos)
    bodies = {note["id"]: note["body"] for note in open_notes(connection, "question", batches=False)}
    return [row for row in _notes(connection, "question", keep, batches=False)
            if len(OPTION_LINE.findall(bodies.get(row["note"], ""))) >= 2]


def review_questions(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None) -> int:
    """How many open questions review batches hold, on items neither done nor parked (sd:5130)."""
    where, values = _in("item.repo", _keep(repos))
    return connection.execute(
        f"SELECT COUNT(*) FROM note JOIN item ON item.id = note.item"
        f" WHERE note.kind = 'question' AND note.resolved_at IS NULL AND item.status != 'done'"
        f" AND {_unparked_clause(connection)} AND {REVIEW_BATCH} AND {where}", values).fetchone()[0]


def followups(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None) -> list[dict]:
    """Open followups, oldest first, except a report's own, which is the report's attention row:
    `note`, `title` (the followup's first line), `item_title`, `at`."""
    reports = {row["id"] for row in attention(connection, repos=repos)}
    return [row for row in _notes(connection, "followup", _keep(repos)) if row["id"] not in reports]


def _closed(connection: sqlite3.Connection, repos: Iterable[str] | None, now: str | None,
            hours: int) -> list[dict]:
    """Every item closed or merged in the last `hours`, newest first, with its `pr` and `commit` or None."""
    cutoff = (_parse(_now(now)) or datetime.now(timezone.utc)) - timedelta(hours=hours)
    where, values = _in("item.repo", _keep(repos))
    rows = connection.execute(
        f"""
        SELECT note.item, note.body, note.timestamp, item.title, item.repo
          FROM note JOIN item ON item.id = note.item
         WHERE substr(note.timestamp, 1, 19) >= ? AND {where}
           AND ((note.kind = 'status_change' AND note.body LIKE '%-> done%')
             OR (note.kind = 'comment' AND note.body LIKE 'Code delivery %'))
         ORDER BY note.id DESC
        """,
        (cutoff.strftime("%Y-%m-%dT%H:%M:%S"), *values),
    ).fetchall()
    found: dict[int, dict] = {}
    for row in rows:
        entry = found.setdefault(row["item"], {"id": row["item"], "repo": row["repo"], "title": row["title"],
                                               "at": row["timestamp"], "pr": None, "commit": None})
        if merge := _CODE_DELIVERY.match(row["body"]):
            pull = _PULL.search(merge.group(1))
            entry["pr"] = entry["pr"] or (int(pull.group(1)) if pull else None)
            entry["commit"] = entry["commit"] or merge.group(2)
        elif done := _DELIVERED_AT.search(row["body"]):
            entry["commit"] = entry["commit"] or done.group(1)
    return list(found.values())


def delivered(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None,
              now: str | None = None, hours: int = 24) -> list[dict]:
    """Items a merged PR or a verified delivery landed in the last `hours`, newest first:
    `pr`, `commit`, `at` (when it landed).

    The commit comes from `sd-ship`'s `delivered at` transition or its
    `Code delivery` note. An item closed by hand has neither and is
    `closed_by_hand`'s, so a bulk close is not a screen of rows.
    """
    return [row for row in _closed(connection, repos, now, hours) if row["commit"]]


def closed_by_hand(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None,
                   now: str | None = None, hours: int = 24) -> list[dict]:
    """Items closed in the last `hours` with no PR or delivered commit, newest first: `delivered`'s fields."""
    return [row for row in _closed(connection, repos, now, hours) if not row["commit"]]


def _repo_keys(connection: sqlite3.Connection) -> dict[str, str]:
    """Each registered repository's key by its lower-case GitHub `owner/name`."""
    from .repos import parse_remote

    keys = {}
    for row in connection.execute("SELECT path, remote FROM repo WHERE remote IS NOT NULL"):
        found = parse_remote(row["remote"])
        if found.kind == "github":
            keys[f"{found.owner}/{found.name}".lower()] = row["path"]
    return keys


def _gate(gate: Any) -> dict | None:
    """`sd gate status --json`'s holders and waiters, or the reason they could not be read."""
    if gate is None:
        return None
    if isinstance(gate, str):
        return {"holders": [], "waiters": [], "error": gate}
    return {"holders": [{key: entry.get(key) for key in ("slot", "label", "since")} for entry in gate.get("holders", [])],
            "waiters": [{key: entry.get(key) for key in ("place", "label", "since")} for entry in gate.get("waiters", [])],
            "error": None}


def landing(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None, gate: Any = None) -> dict:
    """The lane: `entries`, each item's newest entry that neither merged nor was cancelled, running first,
    and `gate`, the machine's gate slots.

    An entry carries `entry` (its lane id), `repository` (GitHub `owner/name`),
    `status`, `step`, `place` and `since`. Newest is by the order the hub took
    the entries in, as `sd_lane.newest_entry` reads it; an entry of a done
    item shows only while it is still queued. `place` counts the
    repository's running and pending entries by position. `since` is when
    the entry started running, else when the hub queued it. The lane records
    no ETA, so none is given.

    `gate` is what the caller read from `sd gate status --json` (the slots
    are files on this machine, not rows), or the text of why that read
    failed; it returns as `holders`, `waiters` and `error`, or None.
    """
    rows = connection.execute(
        """
        SELECT state.key, state.body, first, queued.timestamp AS queued_at
          FROM state JOIN (SELECT MAX(id) AS last, MIN(id) AS first FROM state
                            WHERE kind = 'checkpoint' AND substr(key, 1, ?) = ? GROUP BY key)
            ON state.id = last
          JOIN state AS queued ON queued.id = first
        """,
        (len(LANE_KEY_PREFIX), LANE_KEY_PREFIX),
    ).fetchall()
    keys, keep = _repo_keys(connection), _keep(repos)
    newest: dict[tuple[str, Any], tuple[int, dict]] = {}
    for row in rows:
        entry = json.loads(row["body"])
        repository = row["key"][len(LANE_KEY_PREFIX):].rpartition(":")[0]
        if keep is not None and keys.get(repository.lower()) not in keep:
            continue
        key = (repository, entry.get("item"))
        if entry.get("status") != "cancelled" and row["first"] > newest.get(key, (0, {}))[0]:
            newest[key] = (row["first"], {**entry, "repository": repository, "queued_at": row["queued_at"]})
    live = [entry for _, entry in newest.values() if entry.get("status") != "merged"]
    items = {row["id"]: row for row in connection.execute(
        f"SELECT id, title, status FROM item WHERE id IN ({', '.join('?' for _ in live)})",
        [entry.get("item") for entry in live]).fetchall()}
    queued = LANE_ORDER[:2]
    live = [entry for entry in live
            if entry.get("status") in queued or items.get(entry.get("item"), {"status": ""})["status"] != "done"]
    live.sort(key=lambda entry: (entry.get("position") or 0, entry["id"]))
    places: dict[str, int] = {}
    found = []
    for entry in live:
        row, repository = items.get(entry.get("item")), entry["repository"]
        place = None
        if entry.get("status") in queued:
            place = places[repository] = places.get(repository, 0) + 1
        found.append({"id": entry.get("item"), "repo": keys.get(repository.lower()), "entry": entry["id"],
                      "repository": repository, "status": entry.get("status"), "step": entry.get("step"),
                      "place": place, "since": entry.get("started_at") or entry["queued_at"],
                      "title": row["title"] if row is not None else entry.get("title", "")})
    rank = {status: index for index, status in enumerate(LANE_ORDER)}
    found.sort(key=lambda entry: rank.get(str(entry["status"]), len(rank)))
    return {"entries": found, "gate": _gate(gate)}


def planned(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None,
            now: str | None = None) -> list[dict]:
    """Open unparked items due after today, soonest first: `status`, `due`, `priority`.

    Today's and overdue ones are `work`.
    """
    where, values = _in("item.repo", _keep(repos))
    return [{"id": row["id"], "repo": row["repo"], "status": row["status"], "title": row["title"],
             "due": row["due"], "priority": row["priority"]} for row in connection.execute(
        f"""
        SELECT item.* FROM item
         WHERE item.status != 'done' AND item.due > ? AND {_unparked_clause(connection)} AND {where}
         ORDER BY item.due ASC, item.priority IS NULL, item.priority ASC, item.id ASC
        """,
        (_now(now)[:10], *values),
    )]


def unscheduled(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None) -> list[dict]:
    """Open work with no due date, lane entry or active assignment, highest priority first:
    `status`, `priority`, `created_at`.

    Blocked items are `blocked`'s, and in-progress ones are `work`'s.
    """
    laned = {entry["id"] for entry in landing(connection, repos=repos)["entries"]}
    where, values = _in("item.repo", _keep(repos))
    rows = connection.execute(
        f"""
        SELECT item.* FROM item
         WHERE item.status IN ('planning', 'ready') AND item.due IS NULL
           AND item.kind NOT IN ({', '.join('?' for _ in _UNSCHEDULED_SKIPS)})
           AND {_unparked_clause(connection)} AND {where}
           AND NOT EXISTS (SELECT 1 FROM assignment WHERE assignment.item = item.id
                            AND assignment.status IN ({', '.join('?' for _ in ACTIVE_ASSIGNMENTS)}))
         ORDER BY item.priority IS NULL, item.priority ASC, item.id ASC
        """,
        (*_UNSCHEDULED_SKIPS, *values, *ACTIVE_ASSIGNMENTS),
    ).fetchall()
    return [{"id": row["id"], "repo": row["repo"], "status": row["status"], "title": row["title"],
             "priority": row["priority"], "created_at": row["created_at"]}
            for row in rows if row["id"] not in laned]


def blocked(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None) -> list[dict]:
    """Open items that are blocked or whose newest comment says they wait on someone:
    `status`, `why` (the reason on the newest move to blocked, else that comment), `since`."""
    where, values = _in("item.repo", _keep(repos))
    rows = connection.execute(
        f"""
        SELECT item.id, item.title, item.status, item.repo,
               (SELECT body FROM note WHERE note.item = item.id AND note.kind = 'status_change'
                  AND note.body LIKE '%-> blocked%' ORDER BY note.id DESC LIMIT 1) AS moved,
               (SELECT timestamp FROM note WHERE note.item = item.id AND note.kind = 'status_change'
                 ORDER BY note.id DESC LIMIT 1) AS moved_at,
               (SELECT body FROM note WHERE note.item = item.id AND note.kind = 'comment'
                 ORDER BY note.id DESC LIMIT 1) AS comment,
               item.updated_at
          FROM item
         WHERE item.status != 'done' AND {_unparked_clause(connection)} AND {where}
         ORDER BY item.id ASC
        """,
        values,
    ).fetchall()
    found = []
    for row in rows:
        waiting = row["comment"] if row["comment"] and _WAITING.match(row["comment"]) else ""
        if row["status"] != "blocked" and not waiting:
            continue
        because = _BLOCKED_BECAUSE.search(row["moved"] or "") if row["status"] == "blocked" else None
        why = because.group(1) if because and because.group(1).strip() else waiting
        found.append({"id": row["id"], "repo": row["repo"], "status": row["status"], "title": row["title"],
                      "why": _first_line(why), "since": row["moved_at"] or row["updated_at"]})
    return found


def work(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None,
         now: str | None = None) -> list[dict]:
    """`today_items` as dicts, in its order: every item column, and `status_since`."""
    keep = _keep(repos)
    return [dict(row) for row in today_items(connection, now=now) if keep is None or row["repo"] in keep]


def sections(connection: sqlite3.Connection, *, repos: Iterable[str] | None = None,
             now: str | None = None, gate: Any = None) -> dict[str, Any]:
    """Every section in `ORDER`, read once, with `summary` counts first and `closed_by_hand` last.

    `summary["review_questions"]` counts what `decisions` leaves out.
    """
    keep = None if repos is None else sorted(set(repos))
    found: dict[str, Any] = {
        "attention": attention(connection, repos=keep),
        "operations": operations(connection, gate=gate),
        "decisions": decisions(connection, repos=keep),
        "landing": landing(connection, repos=keep, gate=gate),
        "delivered": delivered(connection, repos=keep, now=now),
        "planned": planned(connection, repos=keep, now=now),
        "blocked": blocked(connection, repos=keep),
        "unscheduled": unscheduled(connection, repos=keep),
        "followups": followups(connection, repos=keep),
        "work": work(connection, repos=keep, now=now),
    }
    by_hand = closed_by_hand(connection, repos=keep, now=now)
    week = ((_parse(_now(now)) or datetime.now(timezone.utc)) + timedelta(days=7)).strftime("%Y-%m-%d")
    summary = {key: len(found[key]) for key in ORDER if key not in ("landing", "operations")}
    summary["landing"] = len(found["landing"]["entries"])
    summary["operations"] = len(found["operations"]["findings"])
    summary["planned_this_week"] = sum(1 for row in found["planned"] if row["due"] <= week)
    summary["closed_by_hand"] = len(by_hand)
    summary["review_questions"] = review_questions(connection, repos=keep)
    return {"summary": summary, **{key: found[key] for key in ORDER}, "closed_by_hand": by_hand}
