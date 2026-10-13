#!/usr/bin/env python3
"""Provision the local gate's own virtualenv (sd:1918, sd:3280).

`sd-ship merge` runs `sd-check` for a `repo.ci = local` repository in a fresh
detached worktree and exports `SD_LOCAL_GATE=1` (`bin/sd_local_gate.py`). In
that mode the Makefile never borrows the main checkout's `.venv`: a borrowed
environment is the operator's state, and its requirements are whatever
`make setup` last installed, not the commit under test's. So `make check`
calls this first, and it builds `.venv` in the worktree:

* `requirements-dev.txt` and `requirements-security.txt` under
  `--require-hashes`;
* no `sd_db`: the suite and `bin/` read the worktree's own `lib/`, so a
  caller that still reads an installed copy fails here first;
* nothing for opencode: the live confinement check is the opt-in
  `tests/opencode_escape_probe.py`, run by hand, so the gate does not depend
  on which opencode the machine holds (sd:3486).

A `.venv` that is a link, or a real one this script did not build, is refused
and left alone: gate mode rebuilds its environment, and the operator's
environment is not a thing it may rebuild.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VENV = ROOT / ".venv"
#: Written into the environment once it is complete; a rerun may rebuild only a tree carrying it.
MARKER = "sd-gate-environment"
REQUIREMENTS = ("requirements-dev.txt", "requirements-security.txt")


class GateError(Exception):
    """A sentence for stderr; the gate fails rather than run on a guess."""


def head() -> str:
    probe = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return probe.stdout.strip() if probe.returncode == 0 else "an unknown commit"


def clear_venv() -> None:
    if VENV.is_symlink():
        raise GateError(f"{VENV} is a link; the gate provisions its own environment and will not build through it")
    if VENV.exists():
        if not (VENV / MARKER).is_file():
            raise GateError(f"{VENV} exists and is not a gate environment; gate mode will not rebuild it. "
                            "Run the gate in a fresh worktree")
        shutil.rmtree(VENV)


def run(argv: list[str]) -> None:
    done = subprocess.run(argv, cwd=ROOT, check=False)
    if done.returncode != 0:
        raise GateError(f"{' '.join(argv[:4])} ... exited {done.returncode}")


def main(argv: list[str]) -> int:
    python = argv[1] if len(argv) > 1 else sys.executable
    try:
        ref = head()
        clear_venv()
        run([python, "-m", "venv", str(VENV)])
        interpreter = str(VENV / "bin" / "python")
        requirements = [part for name in REQUIREMENTS for part in ("-r", name)]
        run([interpreter, "-m", "pip", "install", "--quiet", "--require-hashes", *requirements])
        (VENV / MARKER).write_text(f"requirements at {ref}\n", encoding="utf-8")
    except GateError as error:
        print(f"error: SD_LOCAL_GATE=1: {error}", file=sys.stderr)
        return 1
    print(f"gate environment: {VENV.name} (no borrowing) at {ref}; sd_db is lib/, not installed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
