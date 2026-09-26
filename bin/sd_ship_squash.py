"""A branch that carries another pull request's pre-squash head (sd:1409).

A squash merge gives the base one new commit whose only parent is the base's
old tip. The pull request's own head never becomes an ancestor of the base.
A second open branch that merged that head, to build on it, then carries the
same content down a history the base never shares. Its next merge of the base
conflicts on every file both sides touched, whatever the content says.

The operator chose the remedy: resolve those conflicts with the branch's own
side, `git checkout --ours`, gated by blob identity. A path whose blob on the
base equals its blob at the pre-squash head gained nothing on the base beyond
the squash, and the branch already carries the squash's content, so the
branch's side loses nothing. Any other path changed on the base after the
squash, and is a real divergence to read by hand.

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


def blob(root: Path, rev: str, path: str) -> str | None:
    """The blob id of `path` at `rev`, or None where the path is absent."""

    return sd_lib.git_output(["rev-parse", "--verify", "--quiet", f"{rev}:{path}"], root) or None


def squashed_heads(root: Path, base_ref: str, head: str, receipts: list[dict]) -> list[dict]:
    """Each merged pull request whose pre-squash head this branch carries.

    Each entry names the paths the squash changed, split by blob identity:
    `ours` resolve safely to this branch's side, `by_hand` do not.
    """

    found = []
    for receipt in receipts:
        tip, squash = receipt["head"], receipt["merge_commit"]
        if (not reaches(root, tip, head) or reaches(root, tip, base_ref)
                or not reaches(root, squash, base_ref)):
            continue
        paths = (sd_lib.git_output(["diff", "--name-only", "--no-renames", f"{squash}^", squash], root)
                 or "").split()
        ours = [path for path in paths if blob(root, base_ref, path) == blob(root, tip, path)]
        found.append({"item": receipt.get("item"), "head": tip, "merge_commit": squash, "ours": ours,
                      "by_hand": [path for path in paths if path not in ours]})
    return found


def warning(entry: dict, base: str) -> str:
    """The receipt warning for one entry of `squashed_heads`."""

    return (f"this branch carries {entry['head']}, the pre-squash head of sd:{entry['item']}, "
            f"squash-merged into {base} as {entry['merge_commit']}, so merging {base} conflicts "
            f"on ancestry, not content. `git checkout --ours` is safe for: "
            f"{', '.join(entry['ours']) or 'no path'} (the {base} blob equals that head's); "
            f"read by hand: {', '.join(entry['by_hand']) or 'none'} (sd:1409)")
