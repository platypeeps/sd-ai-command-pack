"""The Jira tracker: the same five-key contract, a completely different service.

Ported from the system dashboard's `jira_search`/`jira_me`/`collect_jira`, which
have been answering this question for months. Three things are carried over
verbatim because each was learned the hard way, and three are deliberately
changed. Both lists are here so the next reader can tell which is which.

**Carried over.**

* `myself` is the availability check, not the search. Bad credentials do not
  make a JQL search fail -- Jira answers 200 with `{"issues": [], "isLast":
  true}`, because `currentUser()` resolves to anonymous, who is assigned
  nothing. So the search cannot tell "your credentials are wrong" from "you have
  no open issues", and something else has to say which before it is believed.
* The account id, not the email address, is what issues are matched against.
  Jira hides `emailAddress` on any site with the privacy setting on, and an
  empty email compared against an empty email marks every issue as both assigned
  and filed.
* `watches.isWatching` is read rather than derived. Jira has already computed it
  for the authenticated user, so it stays correct even if someone points the JQL
  at a queue that is not theirs.

**Changed, and why.**

* **No default base URL.** The system dashboard falls back to a specific
  Atlassian host. This backbone must carry no employer footprint of any kind, so
  an unset `JIRA_BASE_URL` is "not configured" and never a guess. That is also
  the honest behaviour: a default host silently pointed at the wrong tenant is
  worse than a row saying which variable to set.
* **The window replaces the open-only filter.** The system dashboard's JQL asks
  for open issues, because it renders a worklist. An index wants the opposite:
  if closed issues never appear, a ticket that closes simply stops matching and
  its row keeps saying `open` forever. So the default JQL selects by involvement
  and recency, and lets the store record the close.
* **The window is expressed in relative minutes, never as a timestamp.** JQL
  date literals are interpreted in the *Jira account's* configured timezone,
  which this machine has no way to know; a `-90m` offset has no timezone to get
  wrong. This is the one place the port would have been a defect rather than a
  copy.

Credentials come from the environment and nowhere else. This module never reads
another project's `.env`: standing rule 1 says the framework does not touch repo
files for its own purposes, and a credentials file belonging to a different
repository is the last place to make an exception.
"""

from __future__ import annotations

import base64
import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta

TRACKER = "jira"
TIMEOUT_SECONDS = 30
PAGE_SIZE = 50
# Ten pages, matching the GitHub collector's ceiling for the same reason: the
# steady-state window is minutes wide, and this exists for the first collect.
MAX_PAGES = 10
OVERLAP = timedelta(hours=1)
FIRST_RUN_WINDOW = timedelta(days=90)

FIELDS = [
    "summary",
    "status",
    "updated",
    "assignee",
    "reporter",
    "project",
    "watches",
]

# Involvement plus recency. Deliberately *not* filtered to open issues -- see
# the module docstring. `{minutes}` is filled with the window width.
DEFAULT_JQL = (
    "(assignee = currentUser() OR watcher = currentUser() "
    "OR reporter = currentUser()) "
    "AND updated >= -{minutes}m ORDER BY updated DESC"
)

ENV_BASE = "JIRA_BASE_URL"
ENV_EMAIL = "JIRA_EMAIL"
ENV_TOKEN = "JIRA_API_TOKEN"


def settings(environ: dict[str, str] | None = None) -> dict[str, str]:
    """The three environment variables, trimmed. Values are never reported."""
    env = os.environ if environ is None else environ
    return {
        "base": (env.get(ENV_BASE) or "").strip().rstrip("/"),
        "email": (env.get(ENV_EMAIL) or "").strip(),
        "token": (env.get(ENV_TOKEN) or "").strip(),
        "jql": (env.get("JIRA_JQL") or "").strip(),
    }


def missing(config: dict[str, str]) -> list[str]:
    """Which variables are absent, **by name**.

    Names and presence only, never values -- the whole point of reporting this
    at all is to tell an operator what to set without the report itself
    becoming somewhere a credential can be read.
    """
    return [
        name
        for name, key in ((ENV_BASE, "base"), (ENV_EMAIL, "email"), (ENV_TOKEN, "token"))
        if not config[key]
    ]


def window_start(watermark: str | None, now: datetime) -> datetime:
    """Same rule as the GitHub collector: overlap on a mark, wide on nothing.

    The *parser* is shared -- `github.parse_iso` reads back exactly what
    `github.iso` wrote, and both trackers store their watermark in that one
    spelling, so a second implementation of it could only ever drift. The
    *constants* are deliberately not shared: `OVERLAP` and `FIRST_RUN_WINDOW`
    are declared in each module, so widening one tracker's window is a decision
    about that tracker rather than a change that silently moves the other.
    """
    from . import github

    previous = github.parse_iso(watermark) if watermark else None
    if previous is None:
        return now - FIRST_RUN_WINDOW
    return previous - OVERLAP


def window_minutes(start: datetime, now: datetime) -> int:
    """The window as whole minutes, rounded up and never below one.

    Rounded up because truncation would shave the oldest edge off the window,
    which is precisely the overlap that exists to stop an issue falling between
    two collects.
    """
    seconds = max((now - start).total_seconds(), 60.0)
    return int(math.ceil(seconds / 60.0))


def _request(url: str, config: dict[str, str], body: dict | None, transport=None):
    """One authenticated call. Returns (payload, error-sentence).

    `transport` is the test seam: a callable taking (url, headers, body) and
    returning a payload dict, so nothing in the suite opens a socket.
    """
    auth = base64.b64encode(
        f"{config['email']}:{config['token']}".encode()
    ).decode()
    headers = {"Authorization": "Basic " + auth, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if transport is not None:
        return transport(url, headers, body)
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310 - https URL from configuration
            return json.loads(response.read().decode()), ""
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            return None, (
                f"Jira rejected the credentials ({error.code} {error.reason}); "
                f"check {ENV_EMAIL} and {ENV_TOKEN}"
            )
        return None, f"Jira returned {error.code} {error.reason}"
    except (urllib.error.URLError, OSError, ValueError) as error:
        return None, f"could not reach Jira: {type(error).__name__}: {error}"


def account_id(config: dict[str, str], transport=None) -> tuple[str, str]:
    """(accountId, error). The availability check -- see the module docstring."""
    payload, error = _request(config["base"] + "/rest/api/3/myself", config, None, transport)
    if error:
        return "", error
    found = (payload or {}).get("accountId") or ""
    return found, "" if found else "Jira accepted the request but named no account"


def search(jql: str, config: dict[str, str], transport=None) -> tuple[list[dict], bool, str]:
    """Paged JQL. Returns (issues, truncated, error-sentence).

    The endpoint reports neither a total nor a page count -- only `isLast` and a
    `nextPageToken` -- so the ceiling is what stops this, not a number the
    server hands back. Hitting it is reported, never swallowed.
    """
    url = config["base"] + "/rest/api/3/search/jql"
    found: list[dict] = []
    token: str | None = None
    for _ in range(MAX_PAGES):
        body: dict = {"jql": jql, "maxResults": PAGE_SIZE, "fields": FIELDS}
        if token:
            body["nextPageToken"] = token
        payload, error = _request(url, config, body, transport)
        if error:
            return found, False, error
        page = payload or {}
        found.extend(page.get("issues") or [])
        if page.get("isLast"):
            return found, False, ""
        token = page.get("nextPageToken")
        # `isLast: false` with no token to reach the next page is a malformed
        # answer, not the end of the results. Reading it as the end would drop
        # the remainder while reporting a complete walk -- the same failure the
        # GitHub collector already guards against, and the reason both say so
        # out loud rather than returning a bare False.
        if not token:
            return found, True, ""
    return found, True, ""


def normalize(raw: dict, config: dict[str, str], me: str) -> dict | None:
    """One Jira issue as an index row, or None when it has no key.

    `state` collapses to open/closed from the status *category*, which Jira
    derives itself, so it catches Done, Closed, Cancelled and whatever else a
    project calls its end state. The human-readable status name is deliberately
    not stored: the schema has no column for it, and adding one in the same
    change that adds the second tracker would mean a migration on a table whose
    first tracker has been live for one day.
    """
    key = (raw.get("key") or "").strip()
    if not key:
        return None
    fields = raw.get("fields") or {}
    status = fields.get("status") or {}
    category = ((status.get("statusCategory") or {}).get("name") or "").lower()

    def person(name: str) -> dict:
        value = fields.get(name) or {}
        return {
            "id": value.get("accountId") or "",
            "name": value.get("displayName") or "",
            "email": (value.get("emailAddress") or "").lower(),
        }

    def is_me(who: dict) -> bool:
        # The id when both sides have one; the email only as a fallback, and
        # never when either side is empty -- an empty-equals-empty comparison
        # marks every issue as yours.
        if me and who["id"]:
            return who["id"] == me
        return bool(who["email"]) and who["email"] == config["email"].lower()

    assignee, reporter = person("assignee"), person("reporter")
    why = []
    if is_me(assignee):
        why.append("assigned")
    if is_me(reporter):
        why.append("filed")
    if (fields.get("watches") or {}).get("isWatching"):
        why.append("watching")
    return {
        "tracker": TRACKER,
        "url": f"{config['base']}/browse/{key}",
        "repo": (fields.get("project") or {}).get("key") or "",
        "number": None,
        "kind": "issue",
        "title": fields.get("summary") or "",
        "state": "closed" if category == "done" else "open",
        "author": reporter["name"],
        "updated_at": fields.get("updated") or "",
        # `matched` rather than an empty list: the JQL selected it for some
        # reason, and a row with no reason at all reads as a collector bug
        # rather than as "your JQL is wider than the three named cases".
        "why": why or ["matched"],
    }


def collect(watermark: str | None, now: datetime, seam=None, environ=None) -> dict:
    """Every involved issue touched inside the window."""
    config = settings(environ)
    start = window_start(watermark, now)
    from . import github

    absent = missing(config)
    if absent:
        # "A, B and C" rather than "A and B and C": three variables are the
        # common case on a machine that has never configured Jira, and the
        # naive join reads like a bug in the sentence.
        named = (
            absent[0]
            if len(absent) == 1
            else f"{', '.join(absent[:-1])} and {absent[-1]}"
        )
        return {
            "ok": False,
            "reason": f"{named} not set",
            "issues": [],
            "truncated": [],
            "window_start": github.iso(start),
        }
    me, error = account_id(config, seam)
    if error:
        return {
            "ok": False,
            "reason": error,
            "issues": [],
            "truncated": [],
            "window_start": github.iso(start),
        }
    jql = config["jql"] or DEFAULT_JQL.format(minutes=window_minutes(start, now))
    raw, cut, error = search(jql, config, seam)
    rows = [row for row in (normalize(item, config, me) for item in raw) if row]
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return {
        "ok": not error,
        "reason": error,
        "issues": rows,
        "truncated": ["jql"] if cut else [],
        "window_start": github.iso(start),
    }
