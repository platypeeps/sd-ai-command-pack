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

**The tab shows what is moving, and moving is defined by exclusion.** Of 310
active items fleet-wide, 300 read `planning` -- so the full inventory is one
value repeated three hundred times across twelve repositories, and a reader
learns nothing from it. What is left after removing `planning` and `done` is
six items, which is a view. Defining it by exclusion rather than by an
allow-list of interesting statuses is deliberate: a status this module has
never heard of shows up instead of being silently dropped, and the vocabulary
is not frozen anywhere that would have to be kept in step.
"""

from __future__ import annotations

from pathlib import Path

from .collect import discover_checkouts

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


def read_item(path: Path) -> dict:
    """One work item, whether or not it can say what it is."""
    prd = path / "prd.md"
    fields = frontmatter(prd) if prd.is_file() else {}
    status, detail = split_status(fields.get("status", ""))
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
        where = repo.name if group == "." else f"{group}/{repo.name}"
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
            row = {"repo": where, **read_item(item)}
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
