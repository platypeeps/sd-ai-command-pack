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

**A `branch:` field annotates; it does not exclude.** It used to: the presence
of the string was the whole test, so an item naming a branch deleted months ago
was hidden from the sweep permanently -- by exactly the stale metadata the
sweep exists to notice. The field is now resolved once per root against every
head the remote publishes and every head held locally, and the answer rides on
the item as `live`, `gone` or `unknown`. Nothing is hidden by it.

**Age is measured from the last thing that happened, not from the first.** It
used to be the item's own date, which can only ever go up: an item worked on
this morning still read at 74 days and no amount of work on it would lower the
number. 21 of mezmo_benchmark's 24 planning items were due on that basis while
every one of them had been triaged live the day before, so the report was 21
true statements about birth dates and 21 false ones about neglect. `last_active`
is now the basis -- the item's own date, the last commit touching its
directory, and the last stamp its database row or notes carry, latest wins --
and `sd-status`'s `idle-planning` reads the same function, because two
definitions of idle would let this park what that had just cleared.

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
#: whatever its age. A `branch:` field used to be a second exclusion, on the
#: strength of the claim alone; it now buys an annotation and hides nothing.
SWEEPABLE_STATUS = "planning"

#: What a `branch:` field turned out to name. `unknown` is not a third kind of
#: absence: it says the question was not answered, which is a different thing
#: from an answer of no, and it never removes an item from the report.
LIVE, GONE, UNKNOWN = "live", "gone", "unknown"

_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def item_date(item: sd_lib.WorkItem) -> datetime.date | None:
    """The item's own date, or None when it cannot be established.

    `created:` first, because it is what the item says about itself; the
    directory prefix second, because every templated item carries one and it is
    what the bulk-park actually sorted on. None is an answer, not a failure.

    **This is not the aging basis.** It decides whether an item can be aged at
    all -- None is `undated` -- and it is the floor `last_active` starts from.
    Ages are measured from `last_active`, because a birth date says when an
    item began and the check that reads it says the item has been neglected.
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


def _item_directory(path: str, work_dir: str) -> str:
    """The item directory a tracked path belongs to, or `""` for anything else.

    `<work_dir>/<name>/<file>` and `<work_dir>/archive/<month>/<name>/<file>`,
    the same two shapes `work_item_dirs` enumerates. A path directly inside
    `<work_dir>` -- `.status-source` is the one this repository has -- names no
    item and must not be read as one, which is what the length test below is.
    """
    parts = path.split("/")
    head = work_dir.split("/")
    if parts[: len(head)] != head:
        return ""
    rest = parts[len(head):]
    if rest[:1] == [sd_lib.ARCHIVE_DIR]:
        rest = rest[2:]
    return rest[0] if len(rest) > 1 else ""


def touched(root: pathlib.Path, work_dir: str = sd_lib.WORK_DIR
            ) -> dict[str, datetime.date]:
    """The day each item directory was last committed to, keyed by directory.

    One `git log` per root, never one per item: the same invariant `branches`
    above states, and the whole of the cost argument here too. `--name-only`
    output is bounded by the commits that touched the item tree rather than by
    the repository's history -- 2,082 lines and 116 KB over this checkout's
    entire history, measured 2026-09-12 -- so no `--since` window is needed
    and none is used. A window would have to be bounded by the oldest
    candidate anyway, and a miss inside one is indistinguishable from no
    activity at all.

    Merge commits carry no diff and contribute no names. That is right rather
    than a gap: this repository squash-merges, and the squash is the commit
    that touched the files.

    An empty map is an answer, and the only one this returns when git refuses.
    `None` would buy a caller nothing: git refusing and git finding nothing
    both leave the aging basis on its other two sources, and a third state
    nobody can act on differently is a state nobody should have to handle.
    """
    listing = sd_lib.git_output(
        ["log", "--format=%x00%cs", "--name-only", "--", work_dir], root
    )
    found: dict[str, datetime.date] = {}
    day: datetime.date | None = None
    for line in (listing or "").splitlines():
        if line.startswith("\0"):
            try:
                day = datetime.date.fromisoformat(line[1:].strip())
            except ValueError:
                day = None
            continue
        name = _item_directory(line, work_dir)
        # Newest commit first, so the first sighting of a path is its latest.
        if day is not None and name and name not in found:
            found[name] = day
    return found


def last_active(when: datetime.date, name: str, activity: str,
                marks: dict[str, datetime.date] | None = None) -> datetime.date:
    """The most recent day this item shows evidence of activity.

    **The one definition of the aging basis.** `scan` below reads it and so
    does `sd-status`'s `idle-planning` producer, for the same reason that
    producer reads `DEFAULT_DAYS` from here rather than restating it: a report
    that stopped calling an item idle while the sweep went on counting from
    its birth date would let the sweep park what the report had just cleared.

    Three sources, latest wins, each of them evidence that something happened:

    * `when`, the item's own date from `item_date` -- `created:` or the
      directory prefix. The floor, never the answer on its own: an item is at
      least as old as its birth, and this is what the check used to read.
    * the last commit touching `name`, its directory, from `marks`.
    * `activity`, the last stamp the database holds against it -- its row's
      `updated_at` or the newest of its notes, which `WorkItem.activity` is.

    Four loose arguments rather than a `WorkItem`, because `sd-status` reads
    the same three facts off the section dict it already built and would
    otherwise have to fabricate an item to ask the question.

    A union rather than a precedence chain, because each source is blind where
    the others see. A `row` checkout records a triage decision as a note and
    touches no file; a `file` checkout has no database at all; an item nobody
    has committed or recorded has only its birth date. Twenty-one of
    mezmo_benchmark's twenty-four planning items read past the threshold on
    birth dates alone while every one of them had been triaged live the day
    before, and the triage was notes.
    """
    days = [when]
    marked = (marks or {}).get(name)
    if marked is not None:
        days.append(marked)
    recorded = _stamp(activity)
    if recorded is not None:
        days.append(recorded)
    return max(days)


def _stamp(text: str) -> datetime.date | None:
    """The day part of a database timestamp, or None when it will not parse."""
    try:
        return datetime.date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def branches(root: pathlib.Path) -> frozenset[str] | None:
    """Every branch name this root publishes or holds, or None when git cannot say.

    Once per root, not once per item. The remote is asked for all its heads
    with no branch argument, because a query filtered by one item's branch can
    only classify that item and answers `gone` for every other branch it was
    not asked about. Local heads join them -- a branch created here and not yet
    pushed is live work, and calling it gone would sweep the item somebody
    just started.

    Five to eight `git` invocations, of which at most one leaves the machine:
    the `ls-remote`, and only when a remote exists. The rest are local reads,
    most of them `upstream` deciding which remote to ask -- the spread is its
    early return when the remote publishes a `HEAD` against its `main`-then-
    `master` fallback when it does not. The invariant, and the whole of the
    cost argument, is that every one of them is per root and none is per item.

    A root with no remote is answered, not refused: it holds every branch it
    has, so its local heads are the whole truth. None means git failed or the
    root is not a checkout, which `sd_lib.git_output` reports the same way and
    which criterion 4 keeps distinct from an empty answer.
    """
    local = sd_lib.git_output(["for-each-ref", "--format=%(refname:short)", "refs/heads"], root)
    if local is None:
        return None
    names = set(local.split())
    remote, _ = sd_lib.upstream(root)
    if remote:
        listed = sd_lib.git_output(["ls-remote", "--heads", remote], root)
        if listed is None:
            return None
        names.update(line.split("refs/heads/", 1)[1] for line in listed.splitlines()
                     if "refs/heads/" in line)
    return frozenset(names)


def scan(root: pathlib.Path, today: datetime.date, days: int = DEFAULT_DAYS,
         heads: frozenset[str] | None = None) -> dict:
    """One repository: what is due, what cannot be dated, how much is live.

    `today` is a parameter rather than a call to the clock so the caller
    decides what day it is. A sweep whose result depends on when it happened to
    run cannot be reproduced by the person asked to act on it.

    **What is due is what is idle, not what is old.** The age below is measured
    from `last_active`, so an item worked on this morning is not due however
    long ago it was opened. `item_date` still decides `undated`: an item with
    no date at all is a different finding and stays one, and a commit or a note
    does not date an item that never dated itself.
    """
    marks = touched(root)
    due: list[dict] = []
    undated: list[dict] = []
    active = 0
    for item in sd_lib.work_items(root):
        if item.archived or item.parked:
            continue
        active += 1
        if item.status != SWEEPABLE_STATUS:
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
        # Only an item that made a claim gets an annotation. Absence of a
        # `branch:` field is not a claim that could not be checked, and
        # `unknown` there would put every item in the state reserved for a
        # root whose git refused.
        if item.branch:
            row["branch"] = item.branch
            row["branch_state"] = (
                UNKNOWN if heads is None else LIVE if item.branch in heads else GONE
            )
        when = item_date(item)
        if when is None:
            undated.append(row)
            continue
        active_on = last_active(when, item.path.name, item.activity, marks)
        age = (today - active_on).days
        # Strictly greater, per `design.md:106` ("idle in `planning` >45 days")
        # and `:550` ("past 45 days"). An item 45 days old has been idle for
        # exactly the threshold, not past it. One character, one day's worth of
        # items, and no summary count would show which way it was read.
        if age > days:
            # `date` is still the item's own; `active` is what the age was
            # measured from. Two fields because they answer two questions, and
            # a reader asked to park an item wants to see both -- collapsing
            # them would hide the evidence the age is now derived from.
            due.append({**row, "age": age, "date": when.isoformat(),
                        "active": active_on.isoformat()})
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
        heads = branches(root)
        result = scan(root, today, days, heads)
        result["branches"] = "unknown" if heads is None else "ok"
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
        # Once per root, not once per item: a root whose git refused says so
        # where its heading is, and every annotation under it reads `unknown`
        # for that one reason.
        if row.get("branches") == "unknown":
            lines.append("        git could not list this repository's branches")
        for item in sorted(row["due"], key=lambda i: (-i["age"], i["slug"])):
            state = item.get("branch_state")
            said = f"  ({item['branch']} {state})" if state else ""
            lines.append(f"  {item['age']:>4}d  {item['slug']}{said}")
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
