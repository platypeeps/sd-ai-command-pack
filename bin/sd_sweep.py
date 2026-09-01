"""The 45-day age sweep: what the backlog is accumulating again.

The one-time bulk-park (D2) drained 237 items across seven repositories. The
45-day rule is D2's *intake counterpart* (`design.md:549`) -- the thing that
keeps the backlog from silently refilling once the one-time pass is done. Until
now there was nothing to run it: `sd_lib` defined the `parked:` field and
nothing wrote it on a schedule, so "the sweep keeps it drained" named an
intention rather than a job.

**This reports; it does not park.** The acting half is withheld on this
rollout's own evidence, not on general caution. `git mv` relocates the blob
already in the index, so an edit staged before the move is silently dropped and
the commit still looks clean -- three separate agents hit that during the
bulk-park. Parking also breaks every document citing an item's old path, which
needed hand-written per-repository fixes in four of the seven and was caught by
review rather than by any script. Running that unattended across thirteen
checkouts would reproduce both failures with nobody reading the result. What
was missing was never the ability to move a directory -- that is one `git mv`
-- but the ability to notice the backlog refilling, and that is what this does.

**Undated items are reported, never swept.** An item whose `created:` is absent
or unparseable and whose directory carries no `YYYY-MM-DD-` prefix has no age
this module can prove. Reporting it separately is the point: the alternatives
are to call it zero days old, which hides it forever, or infinitely old, which
sweeps whatever nobody dated.

No path argument, in either mode. R10-D6 says an `sd-*` command never takes a
path to somebody else's repository, so the per-repo mode reads the checkout it
was run in and `--fleet` reads `SD_REPO_ROOT` from the environment -- the same
setting the dashboard reads, rather than a second way to say where the repos
are.
"""

from __future__ import annotations

import datetime
import pathlib
import re

import sd_lib

#: D2's intake counterpart, in days. `--days` exists for asking what a
#: different threshold would have caught, not for redefining the rule.
DEFAULT_DAYS = 45

#: The only state a candidate can be in. `in_progress` is somebody's open work
#: whatever its age, and a `branch:` field claims a branch exists for the item.
#: The bulk-park honoured both exclusions and so does this, which is what makes
#: the two passes comparable.
SWEEPABLE_STATUS = "planning"

_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def item_date(item: sd_lib.WorkItem) -> datetime.date | None:
    """The item's own date, or None when it cannot be established.

    `created:` first, because it is what the item says about itself; the
    directory prefix second, because every templated item carries one and it is
    what the bulk-park actually sorted on. None is an answer, not a failure.
    """
    raw = (item.created or "").strip()
    if raw:
        try:
            return datetime.date.fromisoformat(raw[:10])
        except ValueError:
            pass
    match = _DATE_PREFIX_RE.match(item.path.name)
    if match:
        try:
            return datetime.date.fromisoformat(match.group(1))
        except ValueError:
            return None
    return None


def scan(root: pathlib.Path, today: datetime.date, days: int = DEFAULT_DAYS) -> dict:
    """One repository: what is due, what cannot be dated, how much is live.

    `today` is a parameter rather than a call to the clock so the caller
    decides what day it is. A sweep whose result depends on when it happened to
    run cannot be reproduced by the person asked to act on it.
    """
    due: list[dict] = []
    undated: list[dict] = []
    active = 0
    for item in sd_lib.work_items(root):
        if item.archived or item.parked:
            continue
        active += 1
        if item.status != SWEEPABLE_STATUS or item.branch:
            continue
        # `slug` is what `sd-status` prints and what a person will recognise;
        # `dir` is the directory the date prefix lives on and the thing a
        # `git mv` needs. Reporting only the slug would name an item nobody
        # could locate without reconstructing the prefix.
        row = {
            "slug": item.slug,
            "dir": item.path.name,
            "title": item.title,
            "created": item.created,
        }
        when = item_date(item)
        if when is None:
            undated.append(row)
            continue
        age = (today - when).days
        # Strictly greater, per `design.md:106` ("idle in `planning` >45 days")
        # and `:550` ("past 45 days"). An item 45 days old has been idle for
        # exactly the threshold, not past it. One character, one day's worth of
        # items, and no summary count would show which way it was read.
        if age > days:
            due.append({**row, "age": age, "date": when.isoformat()})
    return {"due": due, "undated": undated, "active": active}


def sweep(roots: list[tuple[str, pathlib.Path]], today: datetime.date,
          days: int = DEFAULT_DAYS) -> dict:
    """The same scan over one repository or over the fleet.

    One shape for both modes so the JSON a scheduled fleet run emits is the
    JSON a person gets from one checkout, and neither output needs its own
    reader.
    """
    repos: list[dict] = []
    for where, root in roots:
        result = scan(root, today, days)
        if not result["active"] and not result["due"] and not result["undated"]:
            # A checkout with no live items has nothing to say. Listing it
            # anyway would bury the handful that do under the fleet's silence.
            continue
        repos.append({"repo": where, **result})
    repos.sort(key=lambda row: (-len(row["due"]), row["repo"]))
    return {
        "days": days,
        "today": today.isoformat(),
        "repos": repos,
        "due": sum(len(row["due"]) for row in repos),
        "undated": sum(len(row["undated"]) for row in repos),
        "active": sum(row["active"] for row in repos),
    }


def render(report: dict) -> list[str]:
    """The report as lines, due items first and oldest first within a repo."""
    lines: list[str] = []
    for row in report["repos"]:
        if not row["due"] and not row["undated"]:
            continue
        lines.append(f"{row['repo']}  ({row['active']} active)")
        for item in sorted(row["due"], key=lambda i: (-i["age"], i["slug"])):
            lines.append(f"  {item['age']:>4}d  {item['slug']}")
        for item in sorted(row["undated"], key=lambda i: i["slug"]):
            lines.append(f"     ?  {item['slug']}  (no date to age it by)")
    if not lines:
        return [f"nothing over {report['days']} days: {report['active']} active"]
    lines.append("")
    lines.append(
        f"{report['due']} over {report['days']} days, "
        f"{report['undated']} undated, {report['active']} active"
    )
    return lines
