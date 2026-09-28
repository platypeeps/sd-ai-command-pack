#!/usr/bin/env python3
"""Provision the local gate's own virtualenv, pinned as CI pins it (sd:1918).

`sd-ship merge` runs `sd-check` for a `repo.ci = local` repository in a fresh
detached worktree and exports `SD_LOCAL_GATE=1` (`bin/sd_local_gate.py`). In
that mode the Makefile never borrows the main checkout's `.venv`: a borrowed
environment is the operator's state, and its `sd_db` is whatever `make setup`
last installed from the system checkout's HEAD, not the pin CI runs. So
`make check` calls this first, and it builds `.venv` in the worktree:

* `requirements-dev.txt` and `requirements-security.txt` under
  `--require-hashes`, as the `lint` and `unittest` jobs install them;
* `sd_db` from the system checkout at the ref `tests.yml` pins, read from the
  workflow rather than restated, so the gate and CI cannot drift apart;
* nothing for opencode, which it cannot install on this platform: the live
  confinement test needs it, a skip fails the suite anyway, and this says so
  first, by name, instead of a whole suite later.

A `.venv` that is a link, or a real one this script did not build, is refused
and left alone: gate mode rebuilds its environment, and the operator's
environment is not a thing it may rebuild.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
VENV = ROOT / ".venv"
#: Written into the environment once it is complete; a rerun may rebuild only a tree carrying it.
MARKER = "sd-gate-environment"
#: The checkout of `platypeeps/system` a job names, and the `ref:` under it (as tests/test_system_pin.py reads it).
PIN = re.compile(r"repository: platypeeps/system\n(?:[ \t]+(?:#.*|\w+: .*)\n)*?[ \t]+ref: (\S+)")
#: The canary job checks out system `main` on purpose; it is not a pin.
CANARY_REF = "main"
REQUIREMENTS = ("requirements-dev.txt", "requirements-security.txt")


class GateError(Exception):
    """A sentence for stderr; the gate fails rather than run on a guess."""


def pinned_ref(text: str) -> str:
    """The one system ref `tests.yml` pins `sd_db` to."""
    found = [ref for ref in PIN.findall(text) if ref != CANARY_REF]
    if len(found) != 1:
        raise GateError(f"expected one pinned platypeeps/system ref in {WORKFLOW.name}, found {found}")
    return found[0]


def system_checkout(environ: dict[str, str]) -> pathlib.Path:
    """Where the `sd_db` source lives, as `bin/sd_install.py` resolves it."""
    return pathlib.Path(os.path.expanduser(environ.get("SD_SYSTEM_CHECKOUT") or "~/repos/system"))


def require_opencode() -> str:
    found = shutil.which("opencode")
    if not found:
        raise GateError("opencode is not on PATH. The gate runs tests/test_sd_review_opencode.py live and never "
                        "skips it. Install the pinned build (.github/scripts/install-opencode.sh; linux-x64) "
                        "or put opencode on PATH, then retry")
    return found


def require_commit(checkout: pathlib.Path, ref: str) -> None:
    probe = subprocess.run(["git", "-C", str(checkout), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                           capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        raise GateError(f"{checkout} has no {ref}; run 'git -C {checkout} fetch --tags origin' "
                        "(or set SD_SYSTEM_CHECKOUT) and retry")


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
        ref = pinned_ref(WORKFLOW.read_text(encoding="utf-8"))
        checkout = system_checkout(dict(os.environ))
        require_commit(checkout, ref)
        clear_venv()
        run([python, "-m", "venv", str(VENV)])
        interpreter = str(VENV / "bin" / "python")
        requirements = [part for name in REQUIREMENTS for part in ("-r", name)]
        run([interpreter, "-m", "pip", "install", "--quiet", "--require-hashes", *requirements])
        run([interpreter, "-m", "pip", "install", "--quiet", f"git+file://{checkout}@{ref}#subdirectory=local-sd-db"])
        (VENV / MARKER).write_text(f"sd_db {ref}\n", encoding="utf-8")
    except GateError as error:
        print(f"error: SD_LOCAL_GATE=1: {error}", file=sys.stderr)
        return 1
    print(f"gate environment: {VENV.name} (no borrowing), sd_db at {ref}, opencode {opencode}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
