"""Now: the one view that outranks its own tabs.

Everything the operator has to see is here, ranked, whatever produced it.
Six sources fed the view this replaces; after the plugin split three of them
-- cron, vault, ports -- are plugin rows and arrive through the loader, and
what is left on the backbone side is the fleet itself.

**The merge is here rather than in the page.** The rows arrive on two clocks
and from two routes, and the page could join them; doing it server-side means
the ranking, the ids and the row text are one function with one test suite
instead of behaviour that only exists once a browser is running. What stays in
the page is what cannot leave it: the severity band, which is a rendering
choice, and the panel a row links to, which is an id the renderer assigns.

**An id is an ack key** (R11-D20), so it identifies one alert and not one
source. The repository rows key on the count as well as the name, which is
deliberate the other way: a repo that gains a commit is a new fact, and an ack
of "2 unpushed" should not silently cover "9 unpushed" tomorrow.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

# Ranks, not severities. 0 is loudest, and the page derives how loud to look
# from the number alone -- `kind` is a category and never a severity (R11-D20).
AHEAD = 3
DIRTY = 4
# A pull request nobody has touched for a fortnight, and one that is simply
# open. `FRESH` shares rank 4 with `DIRTY` deliberately: both are reminders
# rather than problems, and the two tie into one band that the page paints
# `queued`. Nothing decides between them and nothing should -- an ordering
# between "uncommitted files" and "an open PR" would be invented, not derived.
# Ties break on `id`, which only has to be stable, not meaningful.
STALE = 2
FRESH = 4


def plural(count: int, one: str, many: str) -> str:
    return one if count == 1 else many


def backbone_rows(repos: list[dict]) -> list[dict]:
    """The fleet's own half of Now.

    Ahead and dirty are one row, not two: a repo with unpushed commits and a
    dirty tree has one thing wrong with it, and the branch that says so is
    the more urgent of the pair. Splitting them put the same repository on
    two lines at two ranks, which reads as two problems.
    """
    out: list[dict] = []
    for repo in repos:
        name, branch = repo["name"], repo.get("branch") or "?"
        ahead, dirty = repo.get("ahead") or 0, repo.get("dirty") or 0
        if ahead:
            out.append({
                "rank": AHEAD,
                "kind": "ahead",
                "id": f"ahead:{name}:{ahead}",
                "what": f"{name} has {ahead} unpushed "
                        f"{plural(ahead, 'commit', 'commits')}",
                "detail": f"{branch} · "
                          + (f"{dirty} dirty {plural(dirty, 'file', 'files')}"
                             if dirty else "clean tree"),
                "source": "repos",
            })
        elif dirty:
            out.append({
                "rank": DIRTY,
                "kind": "dirty",
                "id": f"dirty:{name}:{dirty}",
                "what": f"{name} has {dirty} uncommitted "
                        f"{plural(dirty, 'file', 'files')}",
                "detail": f"{branch} · last commit {repo.get('last') or '?'}",
                "source": "repos",
            })
    return out


# A pull request nobody has touched in this long is the one worth a row.
# **Staleness, not age.** The system view this replaces ranked on how long ago
# a PR was opened, and the index cannot answer that -- it stores `updated_at`
# and there is no `created_at` column. Rather than migrate a cache for it, the
# question changed to the better one: a three-week PR still being pushed to is
# working as intended, and a four-day-old one nobody has looked at is not.
STALE_DAYS = 14


def stale_days(updated: str, today: str) -> int | None:
    """Whole days between two `YYYY-MM-DD` prefixes, or None if either is unusable.

    Compared as dates rather than parsed as timestamps because the index
    stores whatever the tracker returned, and a row with a malformed stamp
    must still render -- it just cannot be ranked by one.
    """
    try:
        was = date.fromisoformat(updated[:10])
        now = date.fromisoformat(today[:10])
    except (TypeError, ValueError):
        return None
    return (now - was).days


def pr_rows(payload: dict, today: str = "") -> list[dict]:
    """Open pull requests, loudest when they have gone quiet.

    Keyed without the age, so acking a PR does not un-ack itself tomorrow --
    the row identifies the pull request, and how long it has been sitting is
    a property of it rather than a different alert.
    """
    if not payload.get("available"):
        return []
    today = today or datetime.now(timezone.utc).date().isoformat()
    out = []
    for pr in [*payload.get("needsYou", []), *payload.get("other", [])]:
        days = stale_days(pr.get("updated_at") or "", today)
        quiet = days is not None and days >= STALE_DAYS
        out.append({
            "rank": STALE if quiet else FRESH,
            "kind": "pr",
            "id": f"pr:{pr.get('repo')}#{pr.get('number')}",
            "what": f"{pr.get('repo')}#{pr.get('number')} open"
                    + (f", quiet {days}d" if quiet else ""),
            "detail": pr.get("title") or "",
            "source": "prs",
        })
    return out


# One row for all of them, not one row each. Eight abandoned worktrees are
# one piece of housekeeping, and eight rows would push the fleet's real
# problems off the top of the view to say so eight times.
ABANDONED = 3


def session_rows(trees: list[dict]) -> list[dict]:
    """Worktrees the fleet has registered whose directories are gone.

    Takes the registrations rather than the whole Sessions payload, so the
    ten-second poll behind Now never has to run the `ps` that payload also
    carries.

    Keyed on the count, like the repository rows and for the same reason: the
    ack should cover the eight that were dismissed, not whatever number this
    grows to next week.
    """
    count = sum(1 for tree in trees if not tree.get("live"))
    if not count:
        return []
    return [{
        "rank": ABANDONED,
        "kind": "worktree",
        "id": f"worktrees:{count}",
        "what": f"{count} abandoned {plural(count, 'worktree', 'worktrees')}",
        "detail": "registered in .git/worktrees with no directory left; "
                  "`git worktree prune` clears them",
        "source": "sessions",
    }]


def merge(backbone: list[dict], plugin: list[dict]) -> list[dict]:
    """Every row there is, loudest first.

    Sorted on `(rank, id)` rather than on rank alone. Rank ties are the common
    case -- a fleet of twelve contributes a dozen rows at one rank -- and a
    sort that leaves them in collection order reshuffles the list under the
    operator every time a thread pool returns in a different order.
    """
    rows = [*plugin, *backbone]
    rows.sort(key=lambda row: (row.get("rank", 9), row.get("id", "")))
    return rows
