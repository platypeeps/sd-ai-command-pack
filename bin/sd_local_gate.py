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

Nothing is reused: every merge attempt runs `sd-check` and posts a fresh
status, because no digest can name every input a check reads (a tool on
`PATH`, for one). The description carries `inputs <digest>` as provenance: a
digest of the head, the copied `CLAUDE.local.md` (or its absence) and the
pack's own `bin/` files. Anyone with write access can post a status, so
`local_gate_passed` trusts only one the authenticated account posted.

The child gets the caller's environment minus the variables that choose Python
packages (`PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, `CONDA_PREFIX`,
`__PYVENV_LAUNCHER__`), minus `PATH` entries inside the operator's checkout,
and minus any `PATH` entry whose parent holds `pyvenv.cfg`, a virtualenv's
`bin` wherever it lives. So an editable install cannot import the dirty
checkout, and no virtualenv's interpreter answers for `python3`.

This is a self-hosted runner, not a hermetic build. The gate guarantees a clean
tree at the exact head, a scrubbed Python environment and no virtualenv on
`PATH`. The rest of `PATH`, the interpreter running `sd-ship` and the system
tools are this machine's image; the repository's own `check` entrypoint owns a
hermetic environment if it needs one. When the checkout under test is the pack
itself and `sd-ship` runs from it, the gate's own `bin/` is that checkout.
"""

from __future__ import annotations

import hashlib
import json
import os
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
#: The tail of `sd-check`'s own stderr the receipt keeps, as `sd-check` tails each check's.
STDERR_TAIL_CHARS = 4000
LOCAL_BLOCK = "CLAUDE.local.md"
#: Variables that pick Python packages; the child must not inherit the caller's.
DROPPED_ENVIRONMENT = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX", "__PYVENV_LAUNCHER__")


def untracked_local_block(root: pathlib.Path) -> pathlib.Path | None:
    """The checkout's untracked `CLAUDE.local.md`, the one file the worktree gets copied in."""
    local = root / LOCAL_BLOCK
    if local.is_file() and sd_lib.git_output(["ls-files", "--error-unmatch", LOCAL_BLOCK], root) is None:
        return local
    return None


def gate_inputs(root: pathlib.Path, head: str) -> str:
    """A 12-hex digest of what a gate run depends on beyond the commit's own tree."""
    digest = hashlib.sha256(f"head {head}\n".encode())
    local = untracked_local_block(root)
    digest.update(b"local " + (local.read_bytes() if local else b"absent") + b"\n")
    for path in sorted(BIN.iterdir()):
        if path.is_file() and (path.suffix == ".py" or path.name.startswith("sd-")):
            digest.update(f"pack {path.name}\n".encode() + path.read_bytes())
    return digest.hexdigest()[:12]


def gate_environment(root: pathlib.Path, environ: dict[str, str] | None = None) -> dict[str, str]:
    """The caller's environment without package selectors, `PATH` entries inside `root`, or virtualenv `bin`s."""
    source = os.environ if environ is None else environ
    env = {key: value for key, value in source.items() if key not in DROPPED_ENVIRONMENT}
    top = root.resolve()
    kept = [entry for entry in env.get("PATH", "").split(os.pathsep)
            if entry and os.path.isabs(entry) and not pathlib.Path(entry).resolve().is_relative_to(top)
            and not (pathlib.Path(entry).resolve().parent / "pyvenv.cfg").is_file()]
    env["PATH"] = os.pathsep.join(kept)
    return env


def check_in_worktree(root: pathlib.Path, head: str, *, timeout: int = CHECK_SECONDS) -> dict[str, Any]:
    """`sd-check --json` in a clean detached worktree of `head`; the worktree is removed after.

    Returns `{"head", "status", "exit_code", "summary", "report", "stderr"}`,
    where `head` is the commit the worktree held after the run, read back
    rather than assumed. The worktree is gone once this returns, so the
    receipt keeps what `sd-check` said (sd:1872); only the status description
    posted to GitHub is cut short.
    """
    with tempfile.TemporaryDirectory(prefix="sd-local-gate-") as parent:
        tree = pathlib.Path(parent) / "tree"
        git(root, "worktree", "add", "--detach", str(tree), head)
        try:
            if local := untracked_local_block(root):
                shutil.copyfile(local, tree / LOCAL_BLOCK)
            try:
                result = subprocess.run([sys.executable, str(BIN / "sd-check"), "--json"], cwd=tree, text=True,
                                        capture_output=True, timeout=timeout, check=False,
                                        env=gate_environment(root))
                code, output, errors = result.returncode, result.stdout, result.stderr
            except (OSError, subprocess.SubprocessError) as error:
                code, output, errors = None, f"sd-check could not finish: {error}", ""
            checked = git(tree, "rev-parse", "HEAD")
        finally:
            # The administrative entry goes with the directory; the temporary
            # directory's own cleanup removes whatever the removal left.
            sd_lib.git_output(["worktree", "remove", "--force", str(tree)], root)
    return {"head": checked, **check_reading(code, output, errors)}


def check_reading(code: int | None, output: str, errors: str = "") -> dict[str, Any]:
    """`sd-check`'s answer as a status, a one-line summary, and what it said.

    Only exit 0 with an overall `pass` is a success. `absent` (no entrypoint),
    `skipped`, a configuration fault (exit 2) and a timeout all fail: nothing
    that did not run the repository's checks may stand in for them.

    `report` is the parsed `sd-check --json` object, whose per-check output
    `sd-check` has already tailed, or None when there was none to parse.
    `stderr` is the tail of `sd-check`'s own stderr, which is where a
    configuration fault (exit 2) says what is wrong.
    """
    try:
        report = json.loads(output) if code in (0, 1) else None
    except ValueError:
        report = None
    if not isinstance(report, dict):
        report = None
    overall = report.get("status") if report else None
    checks = report.get("checks") if report else None
    named = ", ".join(f"{entry.get('name')} {entry.get('status')}" for entry in checks or []
                      if isinstance(entry, dict) and entry.get("status") != "absent")
    said = {"report": report, "stderr": errors[-STDERR_TAIL_CHARS:]}
    if code == 0 and overall == "pass":
        return {"status": "success", "exit_code": code, "summary": f"sd-check pass ({named})", **said}
    if code is None:
        return {"status": "failure", "exit_code": code, "summary": output[:DESCRIPTION_LIMIT], **said}
    words = f"sd-check {overall or 'error'}" + (f" ({named})" if named else f" (exit {code})")
    return {"status": "failure", "exit_code": code, "summary": words, **said}


def post_gate_status(api: Any, head: str, result: dict[str, Any], inputs: str) -> dict[str, Any]:
    """Post `result` as `sd/local-gate` on `head`, bound to `inputs`; refuse a SHA the run did not check."""
    if result.get("head") != head:
        raise Refusal(f"the local gate checked {str(result.get('head'))[:12]}, not {head[:12]}; "
                      "no status is posted for a commit that was not checked",
                      code="local_gate_mismatch", boundary="ci", state="retryable_failure",
                      next_action="Retry merge from the reviewed head.")
    state = "success" if result.get("status") == "success" else "failure"
    description = f"{head[:12]} inputs {inputs}: {result.get('summary') or state}"[:DESCRIPTION_LIMIT]
    return api.api(f"{api.prefix}/statuses/{head}", method="POST",
                   body={"state": state, "context": CONTEXT, "description": description})


def local_gate(api: Any, root: pathlib.Path, head: str) -> dict[str, Any]:
    """Run `sd-check` at `head` and post the result; every merge attempt runs it afresh."""
    inputs = gate_inputs(root, head)
    result = check_in_worktree(root, head)
    post_gate_status(api, head, result, inputs)
    return {**result, "inputs": inputs}
