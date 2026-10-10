#!/usr/bin/env python3
"""Provision the local gate's own virtualenv with the worktree's `sd_db` (sd:1918, sd:3278).

`sd-ship merge` runs `sd-check` for a `repo.ci = local` repository in a fresh
detached worktree and exports `SD_LOCAL_GATE=1` (`bin/sd_local_gate.py`). In
that mode the Makefile never borrows the main checkout's `.venv`: a borrowed
environment is the operator's state, and its `sd_db` is whatever `make setup`
last installed, not the commit under test. So `make check` calls this first,
and it builds `.venv` in the worktree:

* `requirements-dev.txt` and `requirements-security.txt` under
  `--require-hashes`;
* `sd_db` from the worktree's own `lib/`, the commit under test;
* nothing for opencode, which it cannot install on this platform: the live
  confinement test needs it, a skip fails the suite anyway, and this says so
  first, by name, instead of a whole suite later.

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
LIBRARY = ROOT / "lib"
VENV = ROOT / ".venv"
#: Written into the environment once it is complete; a rerun may rebuild only a tree carrying it.
MARKER = "sd-gate-environment"
REQUIREMENTS = ("requirements-dev.txt", "requirements-security.txt")


class GateError(Exception):
    """A sentence for stderr; the gate fails rather than run on a guess."""


def require_opencode() -> str:
    found = shutil.which("opencode")
    if not found:
        raise GateError("opencode is not on PATH. The gate runs tests/test_sd_review_opencode.py live and never "
                        "skips it. Install the pinned build (.github/scripts/install-opencode.sh; linux-x64) "
                        "or put opencode on PATH, then retry")
    return found


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
        opencode = require_opencode()
        if not (LIBRARY / "pyproject.toml").is_file():
            raise GateError(f"no sd_db library at {LIBRARY}")
        ref = head()
        clear_venv()
        run([python, "-m", "venv", str(VENV)])
        interpreter = str(VENV / "bin" / "python")
        requirements = [part for name in REQUIREMENTS for part in ("-r", name)]
        run([interpreter, "-m", "pip", "install", "--quiet", "--require-hashes", *requirements])
        run([interpreter, "-m", "pip", "install", "--quiet", str(LIBRARY)])
        (VENV / MARKER).write_text(f"sd_db lib/ at {ref}\n", encoding="utf-8")
    except GateError as error:
        print(f"error: SD_LOCAL_GATE=1: {error}", file=sys.stderr)
        return 1
    print(f"gate environment: {VENV.name} (no borrowing), sd_db from lib/ at {ref}, opencode {opencode}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
