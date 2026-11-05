"""GitHub > Tracked (pack sd:7525): every open pull request and issue `sd shadow sync` keeps, of every tracker.

Operations > Trackers drew these rows until pack sd:7525 (sd:719 step 4 brought them from the pack's PRs and Issues
tabs). The other GitHub views list what is the operator's (`today_github`, `issues`); this one lists the whole open
snapshot, so a watched row, another repository's pull request and a Jira issue nobody assigned have a home. It reads
the rows `sd shadow sync` keeps in `shadow` through `progress.tracker_items`, and each tracker's health through
`progress.tracker_freshness`; it adds no query of its own, and `/api/github/tracked` serves it to `tracked.js`.

A row's reference is the last path segment of its URL, `url.rpartition("/")[2]`, for both trackers -- the rule sd:361
step 7b wrote into the pack's `where`. It is derived and not stored: a `key` column would be a second copy of a fact the
URL already holds (sd:603). For Jira it is the ticket, `LOG-23818`; the `repo` column is the project, `LOG`, and showing
that would name the wrong thing. A GitHub row reads `repo#tail`. A URL that is not https with a host is no link.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from urllib.parse import urlsplit

from sd_db import progress
from sd_db.errors import SdDbError
from sd_db.shadow_sync import TRACKERS

#: The kinds listed: Trackers' PRs view held GitHub `pull` rows, its Issues view every tracker's `issue` rows.
KINDS = ("pull", "issue")
READ_ERRORS = (SdDbError, sqlite3.Error, ValueError, TypeError, KeyError)


def reference(row):
    """What names the row: `LOG-23818`, or `acme/widgets#4321` on GitHub."""
    tail = (row["url"] or "").rpartition("/")[2]
    return f"{row['repo']}#{tail}" if row["tracker"] == "github" and row["repo"] else tail


def _safe(url):
    try:
        parsed = urlsplit(url or "")
        # `hostname`, not `netloc`: `https://@/x` has an authority and no host.
        return url if parsed.scheme == "https" and parsed.hostname else None
    except ValueError:
        return None


def document(connection: sqlite3.Connection, *, now: str) -> dict:
    """`rows`, every open pull request and issue of every tracker, last seen first; `trackers`, each one's health;
    `error`, the reason nothing could be read, else ""."""
    moment = datetime.fromisoformat(now.replace("Z", "+00:00"))
    try:
        trackers, rows = [], []
        for tracker in TRACKERS:
            health = progress.tracker_freshness(connection, tracker=tracker, now=moment)
            trackers.append({"tracker": tracker, **{k: health[k] for k in ("state", "last_success_at", "reason")}})
            rows += [{"key": row["url"], "tracker": tracker, "kind": row["kind"], "ref": reference(row),
                      "title": row["title"] or "", "repo": row["repo"] or "", "author": row["author"] or "",
                      "state": row["state"] or "", "last_seen": row["last_seen"], "url": _safe(row["url"])}
                     for row in progress.tracker_items(connection, tracker=tracker) if row["kind"] in KINDS]
    except READ_ERRORS as failure:
        return {"rows": [], "trackers": [], "error": str(failure) or "the tracker rows could not be read"}
    rows.sort(key=lambda row: row["last_seen"] or "", reverse=True)
    return {"rows": rows, "trackers": trackers, "error": ""}
