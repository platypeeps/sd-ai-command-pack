#!/usr/bin/env python3
"""Machine-wide gate slots: at most N repository gates run at once (sd:1541, sd:1996).

On 2026-09-25 several gates started together, the load average reached 157,
and tests with a fixed bound failed. On 2026-09-28 nine `sd-ship` gates across
repositories reached 141 on 16 cores, and a vitest default of 5 s failed tests
that assert nothing about time. Every local gate now waits for a slot first.

A slot is a kernel `flock` on `<dir>/slot.N.lock`. The kernel drops it when the
last descriptor on that open file closes, so a holder that dies frees its slot,
and no waiter ever judges a holder dead or deletes anything. The pid written
into a lock file is a hint for a reader, never evidence (#1195 review).

One implementation, two callers. `sd-check` takes a slot around the checks it
runs; `.github/scripts/run-tests.sh` opens the lock files itself and runs the
`wait` command below on those descriptors, so the lock outlives this process
and stays with the shell. A holder sets `SD_GATE_SLOTS=0` for everything it
starts, so a gate inside a gate never waits on the slot its parent holds.

Stdlib only: the harness runs this file from a bare fixture copy.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import pathlib
import subprocess
import sys
import time
from typing import Callable, Mapping, Sequence, TextIO

#: How many gates may run at once; `0` means no cap. A holder exports `0`.
SLOTS_VARIABLE = "SD_GATE_SLOTS"
DIRECTORY_VARIABLE = "SD_GATE_SLOTS_DIR"
POLL_VARIABLE = "SD_GATE_SLOT_POLL"
DEFAULT_POLL_SECONDS = 5.0
#: How often a queued gate says it is still queued, so it does not look hung.
REPORT_EVERY_SECONDS = 60.0
#: Cores per default slot. A repository gate runs a test worker on nearly every
#: core, so a quarter of the cores in gates keeps the load near four per core.
CORES_PER_SLOT = 4
#: Exit codes of the `wait` command.
LAUNCHER_EXITED = 3
TIMED_OUT = 4


class LauncherExited(Exception):
    """The process that started the waiter exited: an orphan must not take a slot."""


def directory(environ: Mapping[str, str]) -> pathlib.Path:
    """Where the slot lock files live, shared by every gate on this machine."""
    named = environ.get(DIRECTORY_VARIABLE)
    if named:
        return pathlib.Path(named)
    state = environ.get("XDG_STATE_HOME") or str(pathlib.Path(environ.get("HOME", "~")).expanduser() / ".local" / "state")
    return pathlib.Path(state) / "sd" / "gate-slots"


def default_slots(cores: int | None = None) -> int:
    """A quarter of the cores, and at least one: 4 on a 16-core machine."""
    count = cores if cores is not None else (os.cpu_count() or CORES_PER_SLOT)
    return max(1, count // CORES_PER_SLOT)


def parse_count(text: str, source: str) -> int:
    """A non-negative slot count, or a `ValueError` naming where it came from."""
    if not text.isascii() or not text.isdigit():
        raise ValueError(f"{source} must be a non-negative integer (got '{text}')")
    return int(text)


def configured(environ: Mapping[str, str], setting: str | None) -> tuple[int, str]:
    """The cap and who set it: the variable, then CI, then `sd.gate_slots`, then the default.

    CI never waits: a runner is one job's machine. `setting` is the machine's
    `sd.gate_slots`, read by the caller so this file needs nothing but stdlib.
    """
    if SLOTS_VARIABLE in environ:
        return parse_count(environ[SLOTS_VARIABLE], SLOTS_VARIABLE), SLOTS_VARIABLE
    if environ.get("CI") or environ.get("GITHUB_ACTIONS"):
        return 0, "CI"
    if setting is not None:
        return parse_count(setting, "sd.gate_slots"), "sd.gate_slots"
    return default_slots(), "default"


def poll_seconds(environ: Mapping[str, str]) -> float:
    try:
        seconds = float(environ.get(POLL_VARIABLE, DEFAULT_POLL_SECONDS))
    except ValueError:
        return DEFAULT_POLL_SECONDS
    return seconds if seconds > 0 else DEFAULT_POLL_SECONDS


def try_lock(fd: int) -> bool:
    """True when this call took the lock on `fd`'s open file without waiting."""
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def parent_of(pid: int) -> int | None:
    """`pid`'s parent as `ps` reads it, or None when `ps` cannot say."""
    if pid == os.getpid():
        return os.getppid()
    try:
        shown = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True,
                               timeout=10, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return int(shown) if shown.isdigit() else None


def launcher_watch(pid: int, ppid: int) -> Callable[[], bool]:
    """True once `pid` was reparented away from `ppid`. A run detached at start has no launcher.

    An unreadable `ps` is not an exit, as in the harness's own watchdog.
    """
    def exited() -> bool:
        if ppid == 1:
            return False
        current = parent_of(pid)
        return current is not None and current != ppid
    return exited


def wait_for_slot(fds: Sequence[int], where: pathlib.Path, *, poll: float, stream: TextIO,
                  stop: Callable[[], bool] = lambda: False, deadline: float | None = None,
                  clock: Callable[[], float] = time.monotonic) -> int | None:
    """Lock one of `fds` and return its index; None once `deadline` passes.

    `stop` is asked before every attempt, so a waiter whose launcher died
    takes nothing even when a slot frees during its sleep. While queued it
    says so on `stream` at once and every `REPORT_EVERY_SECONDS` after.
    """
    started = clock()
    reported: float | None = None
    while True:
        for index, fd in enumerate(fds):
            if stop():
                raise LauncherExited()
            if try_lock(fd):
                waited = clock() - started
                if reported is not None:
                    stream.write(f"gate slot taken after {waited:.0f}s under {where}\n")
                    stream.flush()
                return index
        now = clock()
        if reported is None:
            stream.write(f"waiting for a gate slot: {len(fds)} of {len(fds)} in use under {where}\n")
            stream.flush()
            reported = now
        elif now - reported >= REPORT_EVERY_SECONDS:
            stream.write(f"still waiting for a gate slot after {now - started:.0f}s under {where}\n")
            stream.flush()
            reported = now
        if deadline is not None and now >= deadline:
            return None
        time.sleep(poll if deadline is None else max(0.0, min(poll, deadline - now)))


class Slot:
    """A slot held by this process until `release`; `waited` is the seconds spent queued."""

    def __init__(self, handle: TextIO | None, path: pathlib.Path | None, waited: float) -> None:
        self.handle, self.path, self.waited = handle, path, waited

    def release(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None


def acquire(slots: int, environ: Mapping[str, str], *, stream: TextIO, timeout: float | None = None) -> Slot | None:
    """Take one of `slots` slots for this process, or None when `timeout` passed first.

    `slots` of 0 takes nothing. A directory that cannot be made runs uncapped
    with a warning, as the harness always has: a cap is load control, and no
    gate fails for the want of one. The lock files are not inherited by the
    checks this process starts, so a check that outlives it frees nothing late.
    """
    if slots <= 0:
        return Slot(None, None, 0.0)
    where = directory(environ)
    try:
        where.mkdir(parents=True, exist_ok=True)
        handles = [open(where / f"slot.{index}.lock", "a") for index in range(1, slots + 1)]
    except OSError as error:
        stream.write(f"warning: cannot use {where} ({error}); running without the gate cap\n")
        return Slot(None, None, 0.0)
    started = time.monotonic()
    try:
        taken = wait_for_slot([handle.fileno() for handle in handles], where, poll=poll_seconds(environ),
                              stream=stream, stop=launcher_watch(os.getpid(), os.getppid()),
                              deadline=None if timeout is None else started + timeout)
    except BaseException:
        for handle in handles:
            handle.close()
        raise
    for index, handle in enumerate(handles):
        if index != taken:
            handle.close()
    if taken is None:
        return None
    held = handles[taken]
    try:
        held.truncate(0)
        held.write(f"{os.getpid()}\n")
        held.flush()
    except OSError:
        pass
    return Slot(held, where / f"slot.{taken + 1}.lock", time.monotonic() - started)


def slot_command(argv: list[str] | None = None) -> int:
    """`directory` prints where the slots live; `wait --pid P --ppid Q --dir D FD...`
    locks one inherited descriptor and prints its index.

    The shell that opened the descriptors keeps the lock after this exits.
    Exit 3 when P's launcher exited, or when this process's own parent did.
    """
    parser = argparse.ArgumentParser(prog="sd_gate_slots.py")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("directory", help="print the slot directory")
    wait = commands.add_parser("wait", help="lock one of the inherited slot descriptors")
    wait.add_argument("--pid", type=int, required=True, help="the gate's pid")
    wait.add_argument("--ppid", type=int, required=True, help="the gate's parent when it started")
    wait.add_argument("--dir", required=True, help="the slot directory, for the waiting message")
    wait.add_argument("fds", type=int, nargs="+")
    args = parser.parse_args(argv)
    if args.command == "directory":
        print(directory(os.environ))
        return 0
    gate_gone = launcher_watch(args.pid, args.ppid)
    shell = os.getppid()
    try:
        taken = wait_for_slot(args.fds, pathlib.Path(args.dir), poll=poll_seconds(os.environ), stream=sys.stderr,
                              stop=lambda: os.getppid() != shell or gate_gone())
    except LauncherExited:
        return LAUNCHER_EXITED
    if taken is None:
        return TIMED_OUT
    print(taken)
    return 0


if __name__ == "__main__":
    raise SystemExit(slot_command())
