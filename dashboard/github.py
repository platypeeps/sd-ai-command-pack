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
# GitHub's search returns at most 1,000 results per query and reports
# `hasNextPage: false` at that boundary, so the walk cannot tell the end of the
# list from the end of what the API will hand over. Ten pages of 100 lands
# exactly there. `issueCount` is the only thing that disagrees -- measured
# 2026-09-01, a 90-day `author:@me` window said 2,968 while the walk collected
# 1,000 and reported a clean finish -- so the count is what truncation is
# decided against, not the page ceiling alone.
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
    issueCount
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

    `truncated` means rows exist that this walk did not return -- not merely
    that a page boundary was crossed. It is the honest signal the caller
    reports, so a capped collect never renders as a complete one.

    Two things can cut a walk short and only one of them is this module's. The
    page ceiling is: ten pages and stop. GitHub's 1,000-result search cap is
    not, and it is the one that actually fires here -- it arrives disguised as
    `hasNextPage: false`, which is why the finish is checked against
    `issueCount` rather than believed. Found by step 6's own rm-test: an index
    rebuilt from nothing held 1,000 `author` rows to the live index's 1,037 and
    reported a clean collect.
    """
    nodes: list[dict] = []
    cursor: str | None = None
    available = 0
    for _ in range(MAX_PAGES):
        block, error = _page(query, cursor, runner)
        if error:
            return nodes, False, error
        nodes.extend(node for node in (block.get("nodes") or []) if node)
        # The search's own total, which is answered on every page and is the
        # only field that survives the result cap: at 1,000 the walk is told
        # `hasNextPage: false` while this still reads 2,968. Read from every
        # page rather than from the first, so a page that omits it costs
        # nothing; type-checked rather than truth-checked, because a non-int
        # would compare against the row count and raise mid-walk.
        count = block.get("issueCount")
        if isinstance(count, int):
            available = count
        info = block.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            return nodes, len(nodes) < available, ""
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


def fetch_issue(owner: str, repo: str, number: int, runner=None) -> tuple[dict | None, str]:
    """One named issue or pull request, for `sd-trackers ref`. (row, error).

    Not part of the collect path and deliberately not routed through it: the
    index holds `involves:@me` and nothing else, so an issue nobody has
    assigned to you -- the ordinary case when you plan against someone else's
    report -- is not in it and never will be. Reading the index here would make
    the answer depend on whether the operator happens to be involved.

    REST rather than the GraphQL query above, because `repos/{o}/{r}/issues/{n}`
    answers for a pull request too (GitHub numbers them in one sequence and
    serves both from this endpoint), so one call covers both spellings of a
    reference without asking the caller which they meant. `pull_request` in the
    payload is what tells them apart.
    """
    code, out, err = _run(["gh", "api", f"repos/{owner}/{repo}/issues/{number}"], runner)
    if code != 0:
        detail = (err or out).strip().splitlines()
        return None, detail[0] if detail else f"gh api exited {code}"
    try:
        payload = json.loads(out or "null") or {}
    except json.JSONDecodeError as error:
        return None, f"gh api did not return JSON: {error}"
    url = (payload.get("html_url") or "").strip()
    # The URL is taken from the answer, never assembled from the reference: an
    # issue and a pull request differ in that path segment, and constructing it
    # here would produce a link that redirects at best and 404s at worst.
    if not url:
        return None, "gh api returned no html_url"
    pull = payload.get("pull_request") or {}
    # `merged` is a third state here and only here. The index stores open or
    # closed and nothing else, and this row never reaches it: a citation saying
    # a pull request is closed when it landed reads as work abandoned, which is
    # the opposite of what happened.
    state = "merged" if pull.get("merged_at") else (payload.get("state") or "").lower()
    return {
        "tracker": TRACKER,
        "url": url,
        "repo": f"{owner}/{repo}",
        "number": payload.get("number"),
        "kind": "pull" if pull else "issue",
        "title": payload.get("title") or "",
        "state": state,
        "author": (payload.get("user") or {}).get("login") or "",
        "updated_at": payload.get("updated_at") or "",
    }, ""
