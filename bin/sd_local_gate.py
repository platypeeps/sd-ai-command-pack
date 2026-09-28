"""The local CI gate: `sd-check` at the exact head, reported as a commit status.

A repository whose `repo.ci` row says `local` runs no GitHub Actions (sd:1843).
Its evidence is produced on this machine instead: `sd-ship merge` checks the
reviewed head out into a clean, detached `git worktree`, runs `sd-check` there,
and posts the result to that commit as the `sd/local-gate` status
(`sd_lib.LOCAL_GATE_CONTEXT`). `every_check` and `ready` in
`bin/sd_ship_remote.py` then read that status where they would have read the
`pull_request` workflow runs.

The worktree, not the operator's checkout: an uncommitted file, an untracked
build product or a stale virtualenv in the checkout must not be what passed.
The one file copied in is `CLAUDE.local.md`, when the checkout has it and does
not track it, because that block is where a repository may say how it spells
`check`; it is configuration, never code under test.

A success is posted only for the commit the worktree held when `sd-check`
finished. `post` refuses any other SHA, so a result cannot be carried to a
head that was never checked.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import sd_lib
from sd_ship_remote import Refusal, git

BIN = pathlib.Path(__file__).resolve().parent
CONTEXT = sd_lib.LOCAL_GATE_CONTEXT
#: GitHub truncates nothing and refuses a description past 140 characters.
DESCRIPTION_LIMIT = 140
#: A bound on the whole `sd-check` run, above its own per-check default.
CHECK_SECONDS = 3600
LOCAL_BLOCK = "CLAUDE.local.md"


def current_gate_status(statuses: list, head: str) -> dict | None:
    """The current `sd/local-gate` status at `head`, or None.

    The statuses endpoint lists newest first, so the first entry for the
    context is the current one; an entry naming another SHA is not evidence
    for this one.
    """
    for entry in statuses:
        if isinstance(entry, dict) and entry.get("context") == CONTEXT:
            return entry if entry.get("sha", head) == head else None
    return None


def check_in_worktree(root: pathlib.Path, head: str, *, timeout: int = CHECK_SECONDS) -> dict[str, Any]:
    """`sd-check --json` in a clean detached worktree of `head`; the worktree is removed after.

    Returns `{"head", "status", "exit_code", "summary"}`, where `head` is the
    commit the worktree held after the run, read back rather than assumed.
    """
    with tempfile.TemporaryDirectory(prefix="sd-local-gate-") as parent:
        tree = pathlib.Path(parent) / "tree"
        git(root, "worktree", "add", "--detach", str(tree), head)
        try:
            local = root / LOCAL_BLOCK
            if local.is_file() and sd_lib.git_output(["ls-files", "--error-unmatch", LOCAL_BLOCK], root) is None:
                shutil.copyfile(local, tree / LOCAL_BLOCK)
            try:
                result = subprocess.run([sys.executable, str(BIN / "sd-check"), "--json"], cwd=tree, text=True,
                                        capture_output=True, timeout=timeout, check=False)
                code, output = result.returncode, result.stdout
            except (OSError, subprocess.SubprocessError) as error:
                code, output = None, f"sd-check could not finish: {error}"
            checked = git(tree, "rev-parse", "HEAD")
        finally:
            # The administrative entry goes with the directory; the temporary
            # directory's own cleanup removes whatever the removal left.
            sd_lib.git_output(["worktree", "remove", "--force", str(tree)], root)
    return {"head": checked, **check_reading(code, output)}


def check_reading(code: int | None, output: str) -> dict[str, Any]:
    """`sd-check`'s answer as a status and a one-line summary.

    Only exit 0 with an overall `pass` is a success. `absent` (no entrypoint),
    `skipped`, a configuration fault (exit 2) and a timeout all fail: nothing
    that did not run the repository's checks may stand in for them.
    """
    try:
        report = json.loads(output) if code in (0, 1) else {}
    except ValueError:
        report = {}
    overall = report.get("status") if isinstance(report, dict) else None
    checks = report.get("checks") if isinstance(report, dict) else None
    named = ", ".join(f"{entry.get('name')} {entry.get('status')}" for entry in checks or []
                      if isinstance(entry, dict) and entry.get("status") != "absent")
    if code == 0 and overall == "pass":
        return {"status": "success", "exit_code": code, "summary": f"sd-check pass ({named})"}
    if code is None:
        return {"status": "failure", "exit_code": code, "summary": output[:DESCRIPTION_LIMIT]}
    words = f"sd-check {overall or 'error'}" + (f" ({named})" if named else f" (exit {code})")
    return {"status": "failure", "exit_code": code, "summary": words}


def post_gate_status(api: Any, head: str, result: dict[str, Any]) -> dict[str, Any]:
    """Post `result` as `sd/local-gate` on `head`; refuse a SHA the run did not check."""
    if result.get("head") != head:
        raise Refusal(f"the local gate checked {str(result.get('head'))[:12]}, not {head[:12]}; "
                      "no status is posted for a commit that was not checked",
                      code="local_gate_mismatch", boundary="ci", state="retryable_failure",
                      next_action="Retry merge from the reviewed head.")
    state = "success" if result.get("status") == "success" else "failure"
    description = f"{head[:12]}: {result.get('summary') or state}"[:DESCRIPTION_LIMIT]
    return api.api(f"{api.prefix}/statuses/{head}", method="POST",
                   body={"state": state, "context": CONTEXT, "description": description})


def local_gate(api: Any, root: pathlib.Path, head: str) -> dict[str, Any]:
    """Run and post the local gate at `head`, unless a success is already posted there.

    A success already at this exact head is reused rather than run again, so
    a merge retried after a mergeability wait does not repeat a full check.
    A failure or a missing status runs the check.
    """
    current = current_gate_status(api.pages(f"{api.prefix}/commits/{head}/statuses"), head)
    if current is not None and current.get("state") == "success":
        return {"head": head, "status": "success", "reused": True, "summary": current.get("description")}
    result = check_in_worktree(root, head)
    post_gate_status(api, head, result)
    return {**result, "reused": False}
