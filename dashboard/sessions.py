"""Sessions: the worktrees a parallel run left behind, and what is running now.

The Trellis answer to this was `.runtime/sessions`, a directory the framework
wrote and read. **No hook carries over.** What replaces it is not a smaller
ledger but no ledger at all: a worktree is registered in git's own
`.git/worktrees/`, and a running command is in the process table. Both are
already true without anything having recorded them, which is the same reason
`discover_checkouts` enumerates the fleet rather than reading a list.

**Read from files, not from `git worktree list`.** The fleet is seventy-nine
checkouts and the repo table already fans a `git` process out across all of
them; a second fan-out to ask a question answerable with three `open()` calls
per repository would double the cost of a page load for nothing. What git
writes is what this reads: `gitdir` names the worktree, `HEAD` names its
branch.

**A worktree whose directory is gone is the point of the view.** A parallel
run that ends badly -- or one whose scratchpad is cleared, which is every run
eventually -- leaves the registration behind holding a branch reference. It is
invisible from every other tab, nothing fails because of it, and it
accumulates. That is exactly the shape this dashboard exists to surface.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .collect import discover_checkouts

# One `ps` for the whole machine. Per-process inspection would be a syscall
# storm to answer a question the process table already holds in one table.
PS = ["ps", "-Ao", "pid=,etime=,command="]
PS_SECONDS = 5


def branch_of(head: str) -> str:
    """`ref: refs/heads/x` is a branch; a bare sha is a detached HEAD."""
    head = head.strip()
    if head.startswith("ref: refs/heads/"):
        return head[len("ref: refs/heads/"):]
    return "detached" if head else "?"


def read_worktrees(group: str, repo: Path) -> list[dict]:
    """Every worktree this checkout has registered, live or not."""
    registry = repo / ".git" / "worktrees"
    if not registry.is_dir():
        return []
    where = repo.name if group == "." else f"{group}/{repo.name}"
    out = []
    for entry in sorted(registry.iterdir()):
        if not entry.is_dir():
            continue
        try:
            gitdir = (entry / "gitdir").read_text(encoding="utf-8").strip()
            head = (entry / "HEAD").read_text(encoding="utf-8")
        except OSError:
            # A registration this incomplete is still a registration, and
            # dropping it would hide the one that needs pruning most.
            gitdir, head = "", ""
        # `gitdir` points at the worktree's `.git` file; the worktree is its
        # parent. Reported even when unreadable, as the empty string, because
        # "registered and unnameable" is a state and not an absence.
        path = str(Path(gitdir).parent) if gitdir else ""
        out.append({
            "repo": where,
            "name": entry.name,
            "path": path,
            "branch": branch_of(head),
            # The whole reason this tab is worth a tab.
            "live": bool(gitdir) and Path(gitdir).exists(),
        })
    return out


def running(runner=None) -> list[dict]:
    """Every `sd-*` command on this machine right now.

    Bounded and failure-tolerant on purpose: `ps` not answering is not a
    reason for the page to lose its other half, and this is a view, not a
    supervisor.
    """
    run = runner or (lambda: subprocess.run(
        PS, capture_output=True, text=True, timeout=PS_SECONDS, check=False).stdout)
    try:
        text = run()
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in text.splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        pid, elapsed, command = parts
        # The basename, so a full path and a bare invocation both match, and
        # so a command that merely *mentions* one -- an editor holding the
        # file open, this very grep -- does not.
        head = Path(command.split()[0]).name
        if head.startswith("sd-") or head == "sd":
            out.append({"pid": pid, "elapsed": elapsed, "command": command})
    return out


def fleet_worktrees(root: Path) -> list[dict]:
    """Every registration in the fleet, abandoned ones first.

    Split out from `collect_sessions` because Now wants the count and nothing
    else. Folded together, the ten-second poll behind `/api/now` forked a `ps`
    for a number that never came from it -- and did so whether or not the
    Sessions tab was open. File reads are what this costs now; the subprocess
    belongs to the tab that shows its output.
    """
    trees: list[dict] = []
    for group, repo in discover_checkouts(root):
        trees.extend(read_worktrees(group, repo))
    trees.sort(key=lambda row: (row["live"], row["repo"], row["name"]))
    return trees


def collect_sessions(root: Path, runner=None) -> dict:
    """Every worktree the fleet has registered, and every sd-* now running."""
    trees = fleet_worktrees(root)
    procs = running(runner)
    return {
        "worktrees": trees,
        "processes": procs,
        "abandoned": sum(1 for row in trees if not row["live"]),
        "counts": {"worktrees": len(trees), "processes": len(procs)},
    }
