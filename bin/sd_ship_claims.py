"""Who else is on this item or these files, said before `prepare` publishes (sd:1151).

Two sessions fixed one defect in the same three files forty minutes apart
(#1120, #1122); both branches were on origin before either pull request
opened, and nothing looked. This reads what already exists -- open pull
requests, their files, and origin's branch names -- and names each overlap as
a warning. It refuses nothing (operator decision 2026-10-03), and a read that
fails is itself a warning, never a stop.
"""

from __future__ import annotations

import pathlib
import re

from sd_ship_remote import Refusal, git

#: Open pull requests read for overlapping files, at most; the rest are named by count.
FILE_READ_LIMIT = 30
#: Paths named per overlap; the rest are counted.
SHOWN_PATHS = 3


def item_pattern(item: int) -> re.Pattern[str]:
    """`sd:N`, `sd-N` or `sdN`, as titles, bodies and branch names spell an item."""
    return re.compile(rf"(?i)(?<![0-9a-z])sd[:_-]?{item}(?![0-9])")


def _paths(shared: list[str]) -> str:
    more = len(shared) - SHOWN_PATHS
    return ", ".join(shared[:SHOWN_PATHS]) + (f" and {more} more" if more > 0 else "")


def _shared(api, number, paths: list[str]) -> list[str] | None:
    """The paths pull request `number` also changes, or None when its files could not be read."""
    try:
        files = api.pages(f"{api.prefix}/pulls/{number}/files")
    except Refusal:
        return None
    return sorted(set(paths) & {str(entry.get("filename")) for entry in files if isinstance(entry, dict)})


def _pull_lines(api, others: list[dict], pattern: re.Pattern[str], item: int, paths: list[str]) -> list[str]:
    """A line per open pull request that names `item` or changes one of `paths`."""
    found: list[str] = []
    unread = 0
    for index, pull in enumerate(others):
        number, ref = pull.get("number"), (pull.get("head") or {}).get("ref") or ""
        text = " ".join(str(pull.get(field) or "") for field in ("title", "body")) + " " + ref
        if pattern.search(text):
            found.append(f"claim check: open pull request #{number} ({ref}) names sd:{item}")
            continue
        if not paths:
            continue
        shared = _shared(api, number, paths) if index < FILE_READ_LIMIT else None
        if shared is None:
            unread += 1
        elif shared:
            found.append(f"claim check: open pull request #{number} ({ref}) also changes {_paths(shared)}")
    if unread:
        found.append(f"claim check: the files of {unread} open pull request(s) were not compared")
    return found


def _branch_lines(root: pathlib.Path, pattern: re.Pattern[str], item: int, skip: set[str]) -> list[str]:
    """A line per origin branch that names `item` and is not in `skip`."""
    try:
        heads = git(root, "ls-remote", "--heads", "origin").splitlines()
    except Refusal as error:
        return [f"claim check: origin's branches could not be read ({error})"]
    names = [line.partition("refs/heads/")[2] for line in heads]
    return [f"claim check: origin branch {name} names sd:{item} and has no open pull request"
            for name in names if name and name not in skip and pattern.search(name)]


def claim_warnings(api, root: pathlib.Path, item: int, branch: str, paths: list[str]) -> list[str]:
    """One line per open pull request or origin branch that names `item` or shares a path."""
    pattern = item_pattern(item)
    try:
        pulls = api.pages(f"{api.prefix}/pulls?state=open")
    except Refusal as error:
        return [f"claim check: open pull requests could not be read ({error}); nothing was compared"]
    others = [pull for pull in pulls if isinstance(pull, dict) and pull.get("state", "open") == "open"
              and (pull.get("head") or {}).get("ref") != branch]
    covered = {str((pull.get("head") or {}).get("ref")) for pull in others}
    return _pull_lines(api, others, pattern, item, paths) + _branch_lines(root, pattern, item, covered | {branch})
