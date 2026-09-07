"""Work items across the fleet, read from `docs/work/` at request time.

The system dashboard's Work tab read `.trellis/workspace/journal-*.md`, and
step 2 replaced that layout with `docs/work/`. Exactly one checkout fleet-wide
still has a `.trellis/workspace`, so this is a rewrite against the current
layout rather than the port the parity checklist implies.

An item is a directory under `docs/work/` -- that alone, not a directory that
also holds a `prd.md`. Its state is the `status:` line in that file's
frontmatter when there is one, and the ones with no `prd.md` at all, or a
`prd.md` that never says, are items too: they are reported under `unstated`
rather than skipped. Requiring the file to qualify as an item would hide
exactly the directories nobody finished, which is the reverse of what this is
for, so a later reader tightening this sentence into a filter would be
removing the feature.

Nothing indexes any of it: the directory listing is the index, which is the
same reason `discover_checkouts` enumerates the fleet instead of reading a
configured list. A work item nobody registered anywhere is the one worth
seeing.

**The tab shows what is moving, and moving is defined by exclusion.** Of 57
active items fleet-wide, 47 read `planning` -- and 46 of those sit in a single
frozen repository -- so the full inventory is one value repeated across
thirteen repositories, and a reader learns nothing from it. What is left after
removing `planning` and `done` is six items, which is a view. Step 7's
fleet-wide park cut the active set from 310 to 57 and `planning` from 300 to
47 without moving the ratio the argument rests on, which is the reason to keep
these numbers measured rather than round them into "most".

Defining it by exclusion rather than by an allow-list of interesting statuses
is deliberate: a status this module has
never heard of shows up instead of being silently dropped, and the vocabulary
is not frozen anywhere that would have to be kept in step.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .collect import discover_checkouts

# `bin/` is not a package, and where a status comes from is the one rule this
# module may not keep its own copy of. `sd_lib` owns the `.status-source`
# marker and the database behind it; between the `docs/work` retire and this
# change nothing here knew the marker existed, so every active item in the
# retired checkout read as one whose `prd.md` was templated and then edited.
#
# Only *where*. The value itself is still read the permissive way below: the
# library judges a status against the four words `docs/work` lints for, and
# this tab reads a fleet that does not follow them -- `blocked | phase: check`
# and a status nobody has seen before are things to show, not to normalise
# into `unknown`. Routing the whole read through `sd_lib.work_items` was tried
# and dropped for exactly that.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))
import sd_lib  # noqa: E402

# Read far enough to clear the frontmatter and no further. These files are
# whole PRDs and there are hundreds of them; the state is in the first handful
# of lines and the rest is prose nobody here is asking about.
FRONTMATTER_LINES = 40

# Statuses that mean an item is not asking for anything. Everything else is
# shown, including a value never seen before -- see the module docstring.
SETTLED = frozenset({"planning", "done"})

# A container for finished items, not an item. It matches the same glob as one
# and holds no `prd.md`, so without this it reports as an item whose state
# cannot be read, once per repository.
ARCHIVE = "archive"


def frontmatter(path: Path) -> dict[str, str]:
    """The `key: value` lines above the first closing fence.

    Not a YAML parser and not trying to be: the frontmatter this reads is
    written by `sd` templates, the values are scalars, and importing a parser
    to read `status: planning` would be the larger risk.
    """
    fields: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            first = handle.readline()
            if first.strip() != "---":
                return fields
            for _ in range(FRONTMATTER_LINES):
                line = handle.readline()
                if not line or line.strip() == "---":
                    break
                key, sep, value = line.partition(":")
                # Any leading whitespace, not just a space: a tab-indented
                # line is nested under the field above it, and reading it as
                # top-level would let a nested `status:` outrank the real one.
                if sep and key.strip() and not key[:1].isspace():
                    fields[key.strip()] = value.strip()
    except OSError:
        return {}
    return fields


def split_status(raw: str) -> tuple[str, str]:
    """A status and whatever the item pinned to it.

    `blocked | phase: check | diagnostic: typed sd-check did not pass` is a
    real line from the fleet. The word is the state; the rest is why, and it
    is the most useful thing on the row, so it is kept rather than trimmed
    off as noise.
    """
    head, _, rest = raw.partition("|")
    return head.strip(), rest.strip()


def read_item(path: Path, statuses: "sd_lib.Statuses | None" = None) -> dict:
    """One work item, whether or not it can say what it is."""
    prd = path / "prd.md"
    fields = frontmatter(prd) if prd.is_file() else {}
    raw = fields.get("status", "")
    if statuses is not None and statuses.source != sd_lib.FROM_FILE:
        # The line is gone from this checkout, or says nothing that can be
        # trusted against the row. Either way the file is not the answer here.
        raw = sd_lib.status_report(path, statuses=statuses).status
    status, detail = split_status(raw)
    return {
        "name": path.name,
        "title": fields.get("title", ""),
        "status": status,
        "detail": detail,
        "branch": fields.get("branch", ""),
        "created": fields.get("created", ""),
        # Distinguished because they are different problems: a directory with
        # no `prd.md` was probably started by hand and never templated, while
        # one whose `prd.md` omits `status` was templated and then edited.
        "hasPrd": prd.is_file(),
    }


def label(group: str, repo: Path) -> str:
    """How a row names its checkout. The one spelling, because `deliver`
    resolves it back and a second copy would send a write to the wrong row."""
    return repo.name if group == "." else f"{group}/{repo.name}"


def checkout_of(root: Path, where: str) -> Path | None:
    """The checkout a row's `repo` label names, or None when none does.

    Enumerated rather than joined onto the root: a label is two path segments
    at most and a client sends it back, so building a path out of it is a
    traversal waiting to be written. Nothing here reaches a directory that
    `collect_work` did not already list.
    """
    for group, repo in discover_checkouts(root):
        if label(group, repo) == where:
            return repo
    return None


def collect_work(root: Path) -> dict:
    """Every work item under the fleet: the moving ones listed, all of them counted.

    `counts` covers every status seen, moving included -- it is a breakdown of
    the whole active set, not of the part `moving` leaves out. Returned
    alongside the rows rather than derived from them in the page, because the
    rows are deliberately not the whole set: a view showing six while hiding
    that 300 more exist would be worse than the inventory it replaces, and a
    breakdown that omitted the six would not add up to `active`.
    """
    moving: list[dict] = []
    unstated: list[dict] = []
    counts: dict[str, int] = {}
    archived = 0
    repos = 0

    for group, repo in discover_checkouts(root):
        work = repo / "docs" / "work"
        if not work.is_dir():
            continue
        repos += 1
        where = label(group, repo)
        # Once per repository, not once per item: the marker is a property of
        # the checkout, and opening its database sixty-four times to ask the
        # same question would be the cost of asking it in the wrong place.
        statuses = sd_lib.Statuses.of(repo)
        for item in sorted(work.iterdir()):
            if not item.is_dir():
                continue
            if item.name == ARCHIVE:
                # Directories only, on both levels: an item is a directory,
                # and a README dropped into a month would otherwise be counted
                # as one more thing that shipped.
                archived += sum(
                    1
                    for month in item.iterdir()
                    if month.is_dir()
                    for old in month.iterdir()
                    if old.is_dir()
                )
                continue
            row = {"repo": where, **read_item(item, statuses)}
            if not row["status"]:
                unstated.append(row)
                continue
            # Counted once, on one path: every status the fleet states lands
            # here, and `moving` is a subset chosen afterwards. The increment
            # used to sit in both branches, which is what made it readable as
            # "settled only" and put that error in two docstrings.
            counts[row["status"]] = counts.get(row["status"], 0) + 1
            if row["status"] not in SETTLED:
                moving.append(row)
        statuses.close()

    moving.sort(key=lambda row: (row["status"], row["repo"], row["name"]))
    unstated.sort(key=lambda row: (row["repo"], row["name"]))
    return {
        "moving": moving,
        "unstated": unstated,
        "counts": counts,
        "repos": repos,
        "archived": archived,
        "active": sum(counts.values()) + len(unstated),
    }


#: Who the `status_change` note names, and why. The operator pressed a button
#: on this page; the note says so rather than naming a program, because the
#: claim being recorded is theirs and not the dashboard's.
DELIVERED_BY = "dashboard"
DELIVERED_WHY = "delivered from the dashboard after a merge that carried no trailer"


def deliver(repo: Path, name: str) -> str:
    """One item's row to `done` with `shipped_at`; `""` when the write landed.

    The control for the case `skills/sd-ship/SKILL.md` calls a hand merge: the
    branch merged, the message carried no `Delivers:`, so nothing on the
    default branch claims the item and the row stays `in_progress`. The
    operator is the claim, after the fact, and this is where they make it.

    The write goes to `sd_db` directly, as `bin/sd_install.py` does, and not
    through `sd_lib.Rows` -- that opens read-only and exists so that reading
    sixty-four rows costs one connection, which is not this. The row's *key*
    still comes from `sd_lib`, so the format both sides agree on has exactly
    one definition.

    A sentence back rather than a raise. The caller is an HTTP handler whose
    one job is to say what happened, and answering 200 to a write that never
    landed is the failure this whole tab was fixed for once already.
    """
    try:
        import sd_db  # noqa: PLC0415 - `make setup` provisions it; absent is a state
    except ImportError as error:
        return f"sd_db is not installed here: {error}"
    identity = sd_lib.external_id(repo, repo / name)
    try:
        connection = sd_db.connect(write=True)
    except Exception as error:
        return f"sd_db could not open the database: {error}"
    try:
        row = sd_db.writes.item_by_external(
            connection, sd_lib.ITEM_ROW_SOURCE, identity)
        if row is None:
            return f"the database holds no row for {identity}"
        # No transaction of our own: `transition` opens one, and writes the
        # status and its single note inside it. `shipped_at` is when the item
        # shipped and not when the button was last pressed, so a row already
        # `done` -- which `transition` reports by returning the target back --
        # keeps the moment it has, exactly as a second merge does.
        was = sd_db.writes.transition(connection, row["id"], "done",
                                      who=DELIVERED_BY, reason=DELIVERED_WHY)
        if was != "done":
            sd_db.writes.set_item_fields(
                connection, row["id"], shipped_at=sd_db.writes.now())
    except Exception as error:
        return f"the row for {identity} was not written: {error}"
    finally:
        connection.close()
    return ""
