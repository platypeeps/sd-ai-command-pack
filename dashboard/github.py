"""The GitHub tracker: what is waiting on you, over there.

One of two collectors -- `jira.py` is the other -- and they share exactly one
thing, the shape of the function `collect.refresh_issues` calls: `TRACKER`, and
`collect(watermark, now, seam)` returning `ok`/`reason`/`issues`/`truncated`/
`window_start`. Everything else differs, because the services do: GitHub is
reached through the `gh` CLI and answers GraphQL, Jira is reached over HTTP with
basic auth and answers JQL. A shared base class would have to abstract over that
split and would buy nothing, since there are two of them and the contract is
five keys.

The shape is four searches rather than one. `involves:@me` looks like it would
do the job in a single call, but it collapses *why* an issue reached you, and
the reason is the whole value: "three people requested your review" and "you
opened three issues" are the same count and completely different mornings. So
each bucket is queried separately and the results are unioned by URL with the
reasons accumulated into `why[]`.

Windowed, with an hour of deliberate overlap. GitHub's `updated:` filter has
second resolution but indexing is eventually consistent, so an issue updated at
the instant of the last collect can be missing from that collect and, without
overlap, from every subsequent one too. An hour is far more than the observed
lag and costs only re-writing rows that are already there -- the upsert makes a
repeat sighting free.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

TRACKER = "github"
GH_TIMEOUT_SECONDS = 60
PAGE_SIZE = 100
# Ten pages per bucket. The steady-state window is an hour wide and returns a
# handful of rows, so this ceiling exists for the first collect and for a
# machine that has been off for a month -- the two cases where one page is
# demonstrably not enough: a 90-day `author:@me` window on this account returned
# a truncated first page on the very first run.
MAX_PAGES = 10
OVERLAP = timedelta(hours=1)
# A first collect has no watermark and an unbounded query would drag in years
# of closed work to render a "needs you" list. Ninety days is the same horizon
# the diagnosis in the plan measured over.
FIRST_RUN_WINDOW = timedelta(days=90)

# (why, search qualifier). The `why` strings are the vocabulary the Issues tab
# groups by, so they are short, lowercase, and fixed.
BUCKETS = (
    ("assigned", "assignee:@me"),
    ("mentioned", "mentions:@me"),
    ("review-requested", "review-requested:@me"),
    ("author", "author:@me"),
)

QUERY = """
query($q: String!, $n: Int!, $after: String) {
  search(query: $q, type: ISSUE, first: $n, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      __typename
      ... on Issue {
        number title url state updatedAt
        author { login }
        repository { nameWithOwner }
      }
      ... on PullRequest {
        number title url state updatedAt
        author { login }
        repository { nameWithOwner }
      }
    }
  }
}
"""

# Worded to match `bin/sd-pr-state`, deliberately: an operator who has already
# read one of these sentences should not have to work out that the other one
# means the same thing. Neither reports the credential -- `gh auth status` is
# consulted for its exit code alone.
NO_GH = "gh is not installed; install it (`brew install gh`) to collect issues"
NO_AUTH = "gh is installed but not authenticated; run `gh auth login`"


def iso(moment: datetime) -> str:
    """UTC, second resolution, the spelling GitHub search accepts."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> datetime | None:
    """Read back what `iso` wrote; None when the stored value is unusable."""
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError):
        return None


def window_start(watermark: str | None, now: datetime) -> datetime:
    """Where this collect starts reading.

    A watermark that cannot be parsed is treated as no watermark at all: a
    corrupt value should widen the window, never narrow it. Narrowing on
    garbage is how a windowed collector silently stops collecting.
    """
    previous = parse_iso(watermark) if watermark else None
    if previous is None:
        return now - FIRST_RUN_WINDOW
    return previous - OVERLAP


def _run(argv: list[str], runner=None) -> tuple[int, str, str]:
    """Fixed-argv subprocess, or the injected runner the tests supply."""
    if runner is not None:
        return runner(argv)
    try:
        done = subprocess.run(  # nosec B603 - fixed argv, shell=False
            argv,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[0]} timed out after {GH_TIMEOUT_SECONDS}s"
    except OSError as error:
        return 127, "", f"cannot run {argv[0]}: {error}"
    return done.returncode, done.stdout, done.stderr


def available(runner=None) -> tuple[bool, str]:
    """Whether this run can read GitHub, and if not, why not.

    Reports the *name* of what is missing and never the credential itself --
    `gh auth status` is consulted for its exit code alone.
    """
    if runner is None and shutil.which("gh") is None:
        return False, NO_GH
    code, _, _ = _run(["gh", "auth", "status"], runner)
    if code != 0:
        return False, NO_AUTH
    return True, ""


def _page(query: str, cursor: str | None, runner=None) -> tuple[dict, str]:
    """One page of one search. Returns (search block, error-sentence)."""
    argv = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={QUERY}",
        "-f",
        f"q={query}",
        "-F",
        f"n={PAGE_SIZE}",
    ]
    # Omitted rather than passed empty on the first page: `-F after=` sends an
    # empty string, and GraphQL treats that as a cursor rather than as absent.
    if cursor:
        argv += ["-f", f"after={cursor}"]
    code, out, err = _run(argv, runner)
    if code != 0:
        detail = (err or out).strip().splitlines()
        return {}, detail[0] if detail else f"gh api graphql exited {code}"
    try:
        payload = json.loads(out or "null")
    except json.JSONDecodeError as error:
        return {}, f"gh api graphql did not return JSON: {error}"
    payload = payload or {}
    # GraphQL reports per-field failures in a top-level `errors` array, and it
    # can do so *alongside* usable `data` -- a partial answer. Measured on this
    # machine, `gh` exits 1 in both cases (a malformed query and a partial
    # NOT_FOUND), so the exit check above already catches them. This is checked
    # anyway because that behaviour is `gh`'s, not a contract: the failure it
    # would otherwise cause is the expensive kind -- a short page read as a
    # complete one, and a watermark advanced past the issues that were dropped.
    errors = payload.get("errors")
    if errors:
        first = errors[0] if isinstance(errors, list) and errors else {}
        message = first.get("message") if isinstance(first, dict) else ""
        return {}, f"gh api graphql returned errors: {message or errors}"
    block = (payload.get("data") or {}).get("search")
    # An absent `search` is malformed, an empty one is a legitimate result with
    # no matches. Collapsing both to `{}` would turn the first into a silent
    # empty page, which is the same silent-drop failure in a different coat.
    if block is None:
        return {}, "gh api graphql returned no search block"
    return block, ""


def search(query: str, runner=None) -> tuple[list[dict], bool, str]:
    """One search, followed across pages. Returns (nodes, truncated, error).

    `truncated` means the ceiling stopped the walk with more still to come --
    not merely that a page boundary was crossed. It is the honest signal the
    caller reports, so a capped collect never renders as a complete one.
    """
    nodes: list[dict] = []
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        block, error = _page(query, cursor, runner)
        if error:
            return nodes, False, error
        nodes.extend(node for node in (block.get("nodes") or []) if node)
        info = block.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            return nodes, False, ""
        cursor = info.get("endCursor") or None
        # A next page with no cursor to reach it would loop on page one
        # forever; stop and say the walk was cut short.
        if not cursor:
            return nodes, True, ""
    return nodes, True, ""


def normalize(node: dict, why: str) -> dict | None:
    """One search result as an index row, or None when it is unusable.

    A node with no URL cannot be keyed, unioned, or opened, so it is dropped
    rather than stored under an empty string where it would collide with the
    next one.
    """
    url = (node.get("url") or "").strip()
    if not url:
        return None
    return {
        "tracker": TRACKER,
        "url": url,
        "repo": (node.get("repository") or {}).get("nameWithOwner") or "",
        "number": node.get("number"),
        "kind": "pull" if node.get("__typename") == "PullRequest" else "issue",
        "title": node.get("title") or "",
        "state": (node.get("state") or "").lower(),
        "author": (node.get("author") or {}).get("login") or "",
        "updated_at": node.get("updatedAt") or "",
        "why": [why],
    }


def collect(watermark: str | None, now: datetime, runner=None) -> dict:
    """Every bucket, unioned by URL.

    A bucket that errors makes the whole collect unsuccessful -- `ok` goes
    false and the caller must not advance the watermark. Returning the rows
    that did arrive is still right: they are real, and the index is a cache.
    What must not happen is treating a partial collect as a complete one and
    stepping the window past the part that failed.
    """
    ok, reason = available(runner)
    start = window_start(watermark, now)
    if not ok:
        return {
            "ok": False,
            "reason": reason,
            "issues": [],
            "truncated": [],
            "window_start": iso(start),
        }
    since = f"updated:>={iso(start)}"
    merged: dict[str, dict] = {}
    truncated: list[str] = []
    errors: list[str] = []
    for why, qualifier in BUCKETS:
        nodes, cut, error = search(f"{qualifier} {since}", runner)
        if error:
            errors.append(f"{why}: {error}")
            continue
        if cut:
            truncated.append(why)
        for node in nodes:
            row = normalize(node, why)
            if row is None:
                continue
            found = merged.get(row["url"])
            if found is None:
                merged[row["url"]] = row
            elif why not in found["why"]:
                found["why"].append(why)
    rows = sorted(merged.values(), key=lambda row: row["updated_at"], reverse=True)
    for row in rows:
        row["why"].sort()
    return {
        "ok": not errors,
        "reason": "; ".join(errors),
        "issues": rows,
        "truncated": truncated,
        "window_start": iso(start),
    }
