"""The local gate's run: `sd-check` at the exact head, in a clean worktree, with no way to post.

`sd_local_gate` posts what this returns as the `sd/local-gate` status, and
`sd-review --gate-check` reads it as the review's deterministic gate; this
module is the half they share, so the review lane imports no code that
posts (sd:2041).

The worktree, not the operator's checkout: an uncommitted file, an untracked
build product or a stale virtualenv in the checkout must not be what passed.
The one file copied in is `CLAUDE.local.md`, when the checkout has it and does
not track it, because that block is where a repository may say how it spells
`check`; it is configuration, never code under test.

Given a database, a run reuses a passing receipt `sd_gate_receipts` holds for
the same head (or declared tree) and binding instead of running the check again
(sd:2041, sd:1912); that module's docstring names the binding, its short window,
its trust boundary and the tree key. A reused pass says so in its summary.

Given a base ref, the run passes `--base` to `sd-check`, so a repository that
declares a docs-only scope (`sd_check_scope`, sd:2072) runs only its docs
command for a change that touches only docs paths, and the summary says
`(docs-only)`.

The child gets the caller's environment minus the variables that choose Python
packages (`PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, `CONDA_PREFIX`,
`__PYVENV_LAUNCHER__`), minus `PATH` entries inside the operator's checkout,
and minus any `PATH` entry whose parent holds `pyvenv.cfg`, a virtualenv's
`bin` wherever it lives. So an editable install cannot import the dirty
checkout, and no virtualenv's interpreter answers for `python3`.

It also gets `SD_LOCAL_GATE=1` (`GATE_VARIABLE`), and that is the gate's
contract with the repository under test: this run is the gate, so build what
the check needs here and borrow nothing from the operator. The pack's own
Makefile reads it to provision a pinned in-tree virtualenv (sd:1918); a
repository that does not read it runs as it always did.
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
from typing import Any, Callable, Mapping

import sd_gate_cache
import sd_gate_receipts
import sd_lib

BIN = pathlib.Path(__file__).resolve().parent
#: GitHub truncates nothing and refuses a description past 140 characters.
DESCRIPTION_LIMIT = 140
#: What a failed summary ends with before the local file holding the whole output; a posted status leaves it out.
WHOLE_OUTPUT = " whole output: "
#: The gate's bound on each check, handed to `sd-check --timeout`. Its own
#: 900-second default is for an interactive run; the gate's `make check` also
#: builds a virtualenv (sd:1918) and shares the machine's test slots, and on a
#: busy machine it ran past 900 s and failed as a timeout.
CHECK_SECONDS = sd_lib.GATE_CHECK_SECONDS
#: How much longer the child may take than `sd-check` needs to report its own timeout.
REPORT_GRACE_SECONDS = 60
#: The tail of `sd-check`'s own stderr the receipt keeps, as `sd-check` tails each check's.
STDERR_TAIL_CHARS = 4000
LOCAL_BLOCK = "CLAUDE.local.md"
#: Variables the child must not inherit from the caller: Python package selectors, forced colour,
#: and the operator's Rust build folder, which `sd_gate_cache.cargo_target` replaces with the gate's own (sd:2493).
DROPPED_ENVIRONMENT = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX", "__PYVENV_LAUNCHER__",
                       "FORCE_COLOR", "CLICOLOR_FORCE", "PY_COLORS", "CARGO_TARGET_DIR")
#: Session variables, by name or prefix: dropped so two sessions' passes at one head bind equal (sd:1912, D1; fnm's per-shell folder, sd:2602).
SESSION_ENVIRONMENT = ("CLAUDECODE", "TERM_SESSION_ID", "PWD", "OLDPWD", "SHLVL", "_", "FNM_MULTISHELL_PATH")
SESSION_PREFIXES = ("CLAUDE_", "HERDR_", "ITERM_")
#: Set in the child: the gate captures output, and the caller's terminal colour must not change a result (sd:2076).
NO_COLOUR_ENVIRONMENT = {"NO_COLOR": "1", "PYTHON_COLORS": "0"}
#: Set to "1" in the child: the run is the gate, so the check provisions rather than borrows.
GATE_VARIABLE = "SD_LOCAL_GATE"


class GateError(RuntimeError):
    """`git` could not set up or read the gate's worktree; the check did not run."""


def gate_git(root: pathlib.Path, *args: str) -> str:
    """`git <args>` in `root`, stripped; `GateError` on any failure, since a gate must not guess."""
    try:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise GateError(f"git could not finish: {error}") from None
    if result.returncode:
        raise GateError((result.stderr or result.stdout or "git failed").strip()[:2000])
    return result.stdout.strip()


def untracked_local_block(root: pathlib.Path) -> pathlib.Path | None:
    """The checkout's untracked `CLAUDE.local.md`, the one file the worktree gets copied in."""
    local = root / LOCAL_BLOCK
    if local.is_file() and sd_lib.git_output(["ls-files", "--error-unmatch", LOCAL_BLOCK], root) is None:
        return local
    return None


def gate_inputs(root: pathlib.Path, head: str, tree: str | None = None, own: bool = False) -> str:
    """A 12-hex digest of what a gate run depends on beyond the commit's own tree; `tree` replaces `head` under a tree key.
    `own`, the pack gating itself, leaves out the checkout's `bin/` (sd:2613); else every pack `bin/` file, or `pack_scope`'s closure (sd:2722)."""
    digest = hashlib.sha256((f"head {head}" if tree is None else f"tree {tree}").encode() + b"\n")
    local = untracked_local_block(root)
    digest.update(b"local " + (local.read_bytes() if local else b"absent") + b"\n" + b"pack tree\n" * own)
    for path in [] if own else sd_gate_receipts.pack_files(BIN, sd_gate_receipts.pack_scope(root, head)):
        digest.update(f"pack {path.name}\n".encode() + path.read_bytes())
    return digest.hexdigest()[:12]


def gate_environment(root: pathlib.Path, environ: dict[str, str] | None = None) -> dict[str, str]:
    """The caller's environment without package selectors, forced colour, the operator's `CARGO_TARGET_DIR`,
    session variables, `PATH` entries in `root`, no folder (fnm's per-shell link, sd:2772) or venv `bin`s; each resolved.

    Plus `SD_LOCAL_GATE=1`, `NO_COLOR=1` and `PYTHON_COLORS=0`, whatever the caller had them set to.
    """
    source = os.environ if environ is None else environ
    env = {key: value for key, value in source.items()
           if key not in DROPPED_ENVIRONMENT + SESSION_ENVIRONMENT and not key.startswith(SESSION_PREFIXES)}
    top = root.resolve()
    resolved = [pathlib.Path(entry).resolve() for entry in env.get("PATH", "").split(os.pathsep) if entry and os.path.isabs(entry)]
    kept = [str(path) for path in resolved if path.is_dir() and not path.is_relative_to(top)
            and not (path.parent / "pyvenv.cfg").is_file()]
    env["PATH"] = os.pathsep.join(kept)
    env.update({GATE_VARIABLE: "1", **NO_COLOUR_ENVIRONMENT})
    return env


#: How a caller runs the `sd-check` child: `(argv, env, cwd, timeout)` to `(exit code or None, stdout, stderr)`.
Run = Callable[[list[str], dict[str, str], pathlib.Path, int], tuple[int | None, str, str]]


def run_child(argv: list[str], env: dict[str, str], cwd: pathlib.Path, timeout: int) -> tuple[int | None, str, str]:
    try:
        result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False, env=env)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"sd-check could not finish: {error}", ""
    return result.returncode, result.stdout, result.stderr


def base_ref(branch: str | None) -> str | None:
    """The ref a pull request's base branch is compared at: the remote-tracking one, as `sd-ship` fetches it."""
    return f"refs/remotes/origin/{branch}" if branch else None


def check_in_worktree(root: pathlib.Path, head: str, *, timeout: int = CHECK_SECONDS, base: str | None = None,
                      database: pathlib.Path | None = None, run: Run | None = None,
                      environ: Mapping[str, str] | None = None, reuse: bool = True,
                      record: bool = True, slot_timeout: int = 0, offload: str | None = None) -> dict[str, Any]:
    """`sd-check --json` in a clean detached worktree of `head`; the worktree is removed after.

    Returns `{"head", "status", "exit_code", "summary", "report", "stderr"}`,
    where `head` is the commit the worktree held after the run, read back
    rather than assumed. The worktree is gone once this returns, so the
    receipt keeps what `sd-check` said (sd:1872); only the status description
    posted to GitHub is cut short.

    `base` is a ref for `sd-check --base`; `environ` is what the gate's
    environment is made from, the process's own by default. With a `database`, a matching
    receipt answers instead of a run (the result then carries `reused`), and a
    passing run leaves one when its binding held from before the run to after;
    otherwise the result's `receipt_skipped` names what moved (sd:2612).
    `reuse=False` never reads one and `record=False` never writes one (the merge gate).
    `offload` and a satellite's offload receipt (sd:2704): `sd_gate_receipts.from_receipts`.
    """
    with tempfile.TemporaryDirectory(prefix=sd_gate_cache.worktree_prefix(root)) as parent:  # sd:2739
        tree = pathlib.Path(parent) / "tree"
        gate_git(root, "worktree", "add", "--detach", str(tree), head)
        try:
            if local := untracked_local_block(root):
                shutil.copyfile(local, tree / LOCAL_BLOCK)
            env, mode = sd_gate_receipts.offload_run(database, root, gate_environment(root, None if environ is None else dict(environ)), record=record, offload=offload)  # sd:2782
            content, fork = sd_gate_receipts.tree_key(tree, base)
            own = sd_gate_receipts.gates_itself(root, tree, BIN)
            gated = sd_gate_receipts.Worktree(root, tree, head, base, env, content, fork, own,
                                              gate_inputs(root, head, content, own), mode)
            identity = (sd_gate_receipts.gate_binding(tree, head, gated.inputs, base, env, fork, mode)
                        if database is not None and offload != "require" else None)
            before = sd_gate_receipts.start_view(gated, identity)  # sd:2704
            answer, miss = sd_gate_receipts.from_receipts(database, gated, identity, reuse=reuse, record=record, offload=offload)
            if answer is not None:
                return {"head": gate_git(tree, "rev-parse", "HEAD"), **answer}
            warning = sd_gate_receipts.pack_warning(database, root, head, own) if record and database else None
            argv = [sys.executable, str((tree / "bin" if own else BIN) / "sd-check"), "--json", "--timeout", str(timeout),
                    *(["--base", base] if base else []), *(["--slot-timeout", str(slot_timeout)] * (slot_timeout > 0))]
            with sd_gate_cache.cargo_environment(root, tree, env) as child:
                code, output, errors = (run or run_child)(argv, child, tree, timeout + slot_timeout + REPORT_GRACE_SECONDS)
            checked = gate_git(tree, "rev-parse", "HEAD")
            reading = check_reading(code, output, errors)
            if record and database and identity and reading["status"] == "success" and checked == head:
                sd_gate_receipts.record_gate_pass(database, gated, identity, reading, before)
            reading.update({"pack_warning": warning} if warning else {})
        finally:
            # The administrative entry goes with the directory; the temporary
            # directory's own cleanup removes whatever the removal left.
            sd_lib.git_output(["worktree", "remove", "--force", str(tree)], root)
    return {"head": checked, **reading, **({"reuse_miss": miss} if miss else {})}  # sd:2602; never in the receipt


def named_checks(report: dict[str, Any]) -> str:
    """The checks a summary names: any precheck (sd:2604) and each that ran, or, in a docs-only run, the scope and the docs row."""
    rows = [entry for entry in [report.get("precheck"), *(report.get("checks") or [])] if isinstance(entry, dict)]
    scope = report.get("scope")
    if not (isinstance(scope, dict) and scope.get("mode") == "docs-only"):
        return ", ".join(summary_row(row) for row in rows if row.get("status") != "absent")
    # The three names read `skipped` in a docs-only run; the scope is what a reader needs.
    if report.get("status") == "pass":
        return "docs-only"
    return "docs-only: " + ", ".join(summary_row(row) for row in rows if row.get("name") == "docs")


def summary_row(row: dict[str, Any]) -> str:
    """One check as a summary names it; a failed one adds the steps sd-check says failed (sd:2608)."""
    steps = row.get("failed_steps") if row.get("status") == "fail" else None
    return f"{row.get('name')} {row.get('status')}" + (f": {'; '.join(map(str, steps))}" if isinstance(steps, list) and steps else "")


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
    named = named_checks(report or {})
    said = {"report": report, "stderr": errors[-STDERR_TAIL_CHARS:]}
    if code == 0 and overall == "pass":
        return {"status": "success", "exit_code": code, "summary": f"sd-check pass ({named})", **said}
    if code is None:
        return {"status": "failure", "exit_code": code, "summary": output[:DESCRIPTION_LIMIT], **said}
    words = f"sd-check {overall or 'error'}" + (f" ({named})" if named else f" (exit {code})")
    words = words if len(words) <= DESCRIPTION_LIMIT else words[:DESCRIPTION_LIMIT - 5].rstrip() + " ...)"  # the report keeps every step
    kept = [row["output_path"] for row in (report or {}).get("checks") or [] if isinstance(row, dict) and row.get("output_path")]
    words += f"{WHOLE_OUTPUT}{kept[0]}" if kept else ""  # where the lane log's reader finds the whole output, uncut
    return {"status": "failure", "exit_code": code, "summary": words, **said}
