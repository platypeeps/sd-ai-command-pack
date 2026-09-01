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

# Ranks, not severities. 0 is loudest, and the page derives how loud to look
# from the number alone -- `kind` is a category and never a severity (R11-D20).
AHEAD = 3
DIRTY = 4


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
