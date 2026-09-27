"""A branch that carries another pull request's pre-squash head (sd:1409).

A squash merge gives the base one new commit whose only parent is the base's
old tip. The pull request's own head never becomes an ancestor of the base.
A second open branch that merged that head, to build on it, then carries the
same content down a history the base never shares. Its next merge of the base
conflicts on every file both sides touched, whatever the content says.

The warning names the carried head and lists the squash's paths, and every
one of them is resolved by hand. No path is called safe for `git checkout
--ours`: tree-entry equality cannot prove it. The base can leave a path and
return to it, before or after the squash, and each rule tried here (the base
equals the carried head; the squash is the base's only change since the merge
base) had a history that made `--ours` discard the base's change.

The merged heads come from this machine's ship receipts: the squash message
does not name the head it squashed, and a merge `sd-ship` did not make has no
receipt here, so this finds what `sd-ship` merged and says nothing of the rest.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from pathlib import Path

import sd_lib
import sd_review_material

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


def squash_paths(root: Path, squash: str) -> list[str] | None:
    """The paths `squash` changed, or None when git cannot list them.

    Read NUL-delimited and unstripped, so a name keeps every space, leading
    ones included; `sd_lib.git_output` strips its output.
    """

    try:
        listed = sd_review_material.read_git_material(
            root, ["diff-tree", "-r", "-z", "--no-renames", "--name-only", "--no-commit-id", f"{squash}^", squash])
    except (ValueError, OSError, subprocess.SubprocessError):
        return None
    return [name for name in listed.split("\0") if name]


def squashed_heads(root: Path, base_ref: str, head: str, receipts: list[dict]) -> list[dict]:
    """Each merged pull request whose pre-squash head this branch carries,
    with the paths its squash changed (None when git cannot list them)."""

    found = []
    for receipt in receipts:
        tip, squash = receipt["head"], receipt["merge_commit"]
        if (not reaches(root, tip, head) or reaches(root, tip, base_ref)
                or not reaches(root, squash, base_ref)):
            continue
        found.append({"item": receipt.get("item"), "head": tip, "merge_commit": squash,
                      "by_hand": squash_paths(root, squash)})
    return found


def warning(entry: dict, base: str) -> str:
    """The receipt warning for one entry of `squashed_heads`."""

    paths = entry["by_hand"]
    listed = ", ".join(paths) if paths else ("none" if paths is not None else "git could not list them")
    return (f"this branch carries {entry['head']}, the pre-squash head of sd:{entry['item']}, "
            f"squash-merged into {base} as {entry['merge_commit']}, so merging {base} conflicts "
            f"on ancestry, not content. No path is proven safe for `git checkout --ours`: resolve "
            f"each conflict by hand against the merge base. The squash changed: {listed} (sd:1409)")
