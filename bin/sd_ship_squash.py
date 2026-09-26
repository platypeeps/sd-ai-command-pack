"""A branch that carries another pull request's pre-squash head (sd:1409).

A squash merge gives the base one new commit whose only parent is the base's
old tip. The pull request's own head never becomes an ancestor of the base.
A second open branch that merged that head, to build on it, then carries the
same content down a history the base never shares. Its next merge of the base
conflicts on every file both sides touched, whatever the content says.

The operator chose the remedy: resolve those conflicts with the branch's own
side, `git checkout --ours`, gated by tree-entry identity against the merge
that is about to happen. A path is safe for `--ours` only when the entries
prove the base side has nothing the branch lacks:

- the base holds the branch's own entry; or
- the base did not change the path since the actual merge base; or
- the squash is the base's only change to it: the merge base holds the
  squash parent's entry, the squash's entry is still the base's, and it is
  the carried head's.

Equality with the carried head alone proves nothing: the base can return to
that entry after both sides moved on, and `--ours` would discard it. Any other
path, and any path whose entry git could not read, is read by hand.

The merged heads come from this machine's ship receipts: the squash message
does not name the head it squashed, and a merge `sd-ship` did not make has no
receipt here, so this finds what `sd-ship` merged and says nothing of the rest.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import sd_lib

SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def merged_receipts(connection: sqlite3.Connection, repository: str) -> list[dict]:
    """The latest ship receipt of every key that merged into `repository`."""

    rows = connection.execute(
        "SELECT body FROM state WHERE id IN (SELECT MAX(id) FROM state "
        "WHERE kind = 'checkpoint' AND key LIKE 'ship:%' GROUP BY key)")
    found = []
    for (body,) in rows:
        try:
            value = json.loads(body)
        except (TypeError, ValueError):
            continue
        if (isinstance(value, dict) and value.get("repository") == repository
                and SHA.fullmatch(str(value.get("head") or ""))
                and SHA.fullmatch(str(value.get("merge_commit") or ""))):
            found.append(value)
    return found


def reaches(root: Path, ancestor: str, descendant: str) -> bool:
    """Whether `ancestor` is reachable from `descendant`.

    A commit this clone does not hold is not an ancestor of anything it holds,
    so git's "unknown object" answer reads as no.
    """

    return sd_lib.git_output(["merge-base", "--is-ancestor", ancestor, descendant], root) is not None


#: The entry of a path a revision does not hold. `None` is not absence: it is
#: a lookup git could not answer, and it proves nothing.
ABSENT = ""


def entry(root: Path, rev: str, path: str) -> str | None:
    """`path`'s tree entry at `rev` (mode, type and id), `ABSENT`, or None when
    git cannot answer."""

    listed = sd_lib.git_output(["ls-tree", "-z", "--full-tree", rev, "--", path], root)
    if listed is None:
        return None
    for record in listed.split("\0"):
        meta, tab, name = record.partition("\t")
        if tab and name == path:
            return meta
    return ABSENT


def merge_sides(root: Path, base_ref: str, head: str, squash: str) -> tuple[str, str] | None:
    """The two sides of the merge the split is about: `head` and the base while
    the base is still to merge, or else the first-parent merge that brought
    the squash in. None when neither can be found."""

    if not reaches(root, base_ref, head):
        return head, base_ref
    merges = sd_lib.git_output(["rev-list", "--first-parent", "--merges", head], root) or ""
    for merge in merges.split():
        if reaches(root, squash, f"{merge}^2") and not reaches(root, squash, f"{merge}^1"):
            return f"{merge}^1", f"{merge}^2"
    return None


def merge_base(root: Path, ours: str, theirs: str) -> str | None:
    """The one merge base of the two sides; None for none, several, or unknown."""

    found = (sd_lib.git_output(["merge-base", "--all", ours, theirs], root) or "").split()
    return found[0] if len(found) == 1 else None


def squash_paths(root: Path, squash: str) -> list[str] | None:
    """The paths `squash` changed, NUL-delimited so a name keeps its spaces."""

    listed = sd_lib.git_output(
        ["diff-tree", "-r", "-z", "--no-renames", "--name-only", "--no-commit-id", f"{squash}^", squash], root)
    return None if listed is None else [name for name in listed.split("\0") if name]


def safe_for_ours(root: Path, path: str, sides: tuple[str, str] | None, base: str | None,
                  tip: str, squash: str) -> bool:
    if sides is None or base is None:
        return False
    ours, theirs = sides
    at = {name: entry(root, rev, path) for name, rev in (
        ("ours", ours), ("theirs", theirs), ("base", base), ("tip", tip),
        ("squash", squash), ("parent", f"{squash}^"))}
    if any(value is None for value in at.values()):
        return False
    return (at["theirs"] == at["ours"] or at["theirs"] == at["base"]
            or (at["base"] == at["parent"] and at["squash"] == at["theirs"] == at["tip"]))


def squashed_heads(root: Path, base_ref: str, head: str, receipts: list[dict]) -> list[dict]:
    """Each merged pull request whose pre-squash head this branch carries.

    Each entry names the paths the squash changed, split by `safe_for_ours`:
    `ours` resolve safely to this branch's side, `by_hand` do not. A squash
    whose paths git cannot list is still reported, with nothing split.
    """

    found = []
    for receipt in receipts:
        tip, squash = receipt["head"], receipt["merge_commit"]
        if (not reaches(root, tip, head) or reaches(root, tip, base_ref)
                or not reaches(root, squash, base_ref)):
            continue
        paths = squash_paths(root, squash)
        sides = merge_sides(root, base_ref, head, squash)
        base = merge_base(root, *sides) if sides else None
        ours = [path for path in paths or () if safe_for_ours(root, path, sides, base, tip, squash)]
        found.append({"item": receipt.get("item"), "head": tip, "merge_commit": squash, "ours": ours,
                      "by_hand": [path for path in paths or () if path not in ours]
                      if paths is not None else ["(git could not list the squash's paths)"]})
    return found


def warning(entry: dict, base: str) -> str:
    """The receipt warning for one entry of `squashed_heads`."""

    return (f"this branch carries {entry['head']}, the pre-squash head of sd:{entry['item']}, "
            f"squash-merged into {base} as {entry['merge_commit']}, so merging {base} conflicts "
            f"on ancestry, not content. `git checkout --ours` is safe for: "
            f"{', '.join(entry['ours']) or 'no path'} (against the merge base, {base} has nothing there the branch lacks); "
            f"read by hand: {', '.join(entry['by_hand']) or 'none'} (sd:1409)")
