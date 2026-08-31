"""Facts about the checkout fleet, derived at request time.

Nothing here is stored as an input to anything. The whole point of the storage
doctrine is that derived state committed anywhere becomes permanent staleness,
so this module reads git and returns a dict; the index is a cache that can be
deleted without losing a fact.
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import subprocess
from pathlib import Path

GIT_WORKERS = 8
REMOTE_PATTERN = re.compile(
    r"(?:git@github\.com:|https://github\.com/)(.+?)(?:\.git)?$"
)


def repo_root(environ: dict[str, str] | None = None) -> Path:
    """Where the checkouts live.

    Read from the environment rather than taken as an argument on the command
    line: R10-D6 says an sd-* command never accepts a path to somebody else's
    repository, and the dashboard is a read-only view over many repos rather
    than an exception to that rule.
    """
    env = os.environ if environ is None else environ
    # Expanded whether it came from the environment or the default: a quoted
    # SD_REPO_ROOT="~/repos" reaches us with the tilde intact, and an
    # unexpanded one names a directory that does not exist, which discovery
    # would report as an empty fleet rather than as a bad setting.
    return Path(os.path.expanduser(env.get("SD_REPO_ROOT") or "~/repos"))


def run(argv: list[str]) -> str:
    """Best-effort git; a checkout that cannot answer is not an error here."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def git_facts(path: Path) -> dict | None:
    """Branch, dirt, divergence and last commit for one checkout.

    Lifted from the system dashboard's `git_facts`, which has been answering
    this question correctly for months. The one change is that a detached HEAD
    or a missing upstream yields None rather than a number, so the page can say
    "unknown" instead of showing a zero it made up.
    """
    if not (path / ".git").exists():
        return None
    p = str(path)
    branch = run(["git", "-C", p, "rev-parse", "--abbrev-ref", "HEAD"]) or "?"
    status = run(["git", "-C", p, "status", "--porcelain"])
    dirty = len([line for line in status.split("\n") if line.strip()])
    last = run(["git", "-C", p, "log", "-1", "--format=%cI%x1f%s%x1f%an"])
    when, subject, author = (last.split("\x1f") + ["", "", ""])[:3]
    ahead: int | None = None
    behind: int | None = None
    counts = run(
        ["git", "-C", p, "rev-list", "--left-right", "--count", "@{upstream}...HEAD"]
    )
    if counts and "\t" in counts:
        left, right = counts.split("\t")[:2]
        behind, ahead = int(left), int(right)
    match = REMOTE_PATTERN.match(run(["git", "-C", p, "remote", "get-url", "origin"]))
    return {
        "branch": branch,
        "dirty": dirty,
        "ahead": ahead,
        "behind": behind,
        "last": when[:10],
        "last_iso": when,
        "subject": subject,
        "author": author,
        "web": "https://github.com/" + match.group(1) if match else "",
    }


def discover_checkouts(root: Path) -> list[tuple[str, Path]]:
    """Every checkout under the root, one level of grouping deep.

    Enumerated from the filesystem, never from a configured list: a checkout
    nobody registered is the interesting one, and a list would only ever show
    the repos someone remembered to add.
    """
    found: list[tuple[str, Path]] = []
    if not root.is_dir():
        return found
    for group in sorted(root.glob("*")):
        if not group.is_dir() or group.name.startswith("."):
            continue
        if (group / ".git").exists():
            found.append((".", group))
            continue
        for repo in sorted(group.glob("*")):
            if repo.is_dir() and (repo / ".git").exists():
                found.append((group.name, repo))
    return found


def collect_repos(root: Path) -> list[dict]:
    """The fleet, newest commit first."""
    checkouts = discover_checkouts(root)
    if not checkouts:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=GIT_WORKERS) as pool:
        facts = list(pool.map(lambda item: git_facts(item[1]), checkouts))
    repos = [
        {"name": repo.name, "group": group, "path": str(repo), **fact}
        for (group, repo), fact in zip(checkouts, facts, strict=True)
        if fact is not None
    ]
    repos.sort(key=lambda row: (row.get("last_iso") or "", row["name"]), reverse=True)
    return repos


def build_state(root: Path) -> dict:
    """The whole payload `/api/state` answers with."""
    repos = collect_repos(root)
    return {
        "root": str(root),
        # An unreadable root and a root holding no checkouts both collect
        # nothing, and only one of them is a mistake. The page needs to tell
        # them apart, so the state says which happened.
        "rootExists": root.is_dir(),
        "repos": repos,
        "counts": {
            "repos": len(repos),
            "dirty": sum(1 for row in repos if row["dirty"]),
            "ahead": sum(1 for row in repos if row["ahead"]),
        },
    }
