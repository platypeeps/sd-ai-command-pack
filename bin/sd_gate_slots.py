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

A queue stands in front of the slots (sd:2262). On 2026-10-01 about 14 gates
waited on hand-written copies of one load rule; when load fell, several read the
same quiet moment and started together, in no order. Now every waiter takes a
ticket, and only the head of the queue is admitted, under one `queue.lock`, and
only when the load rule holds. So the first to wait is the first to start, and
no two waiters share one free slot or one load reading. A ticket is `flock`ed
by its waiter, so a dead waiter's ticket is free and the next poll removes it.

`run` waits, runs one command, and frees the slot when it ends; `status` shows
who holds and who waits. `sd gate run` and `sd gate status` are the same verbs
with the machine settings read.

One pool for every caller (sd:2522). On 2026-10-03 the pack's own `make test`
counted 2 slots from its Makefile while `sd-check` counted the machine's 4, the
stdlib `run` ignored `sd.gate_slots`, and a gate that waited said how many
slots were busy but not who held them. Now every entry point takes its count
from `configured` with `sd.gate_slots` read (`count` prints it for the shell),
and a waiting gate names each holder, its directory and since when.

Stdlib only: the harness runs this file from a bare fixture copy.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import fcntl
import json
import os
import pathlib
import re
import shlex
import signal
import subprocess
import sys
import time
from typing import Callable, Iterator, Mapping, NamedTuple, Sequence, TextIO

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
#: Exit codes of the `run` command, beside the command's own: as `timeout(1)`.
RUN_TIMED_OUT = 124
RUN_NOT_STARTED = 125
RUN_NOT_FOUND = 127

#: The load rule (sd:2262). The defaults are the hand rule of 2026-10-01: load1
#: below 40 on 16 cores, held for 45 s, and 45 s between two starts.
LOAD_VARIABLE = "SD_GATE_LOAD_MAX"
SETTLE_VARIABLE = "SD_GATE_SETTLE_SECONDS"
LOAD_PER_CORE = 2.5
DEFAULT_SETTLE_SECONDS = 45.0
#: A gap between two load samples longer than this, or than the settle time,
#: restarts the low-load record: nobody watched the load in between.
STALE_SAMPLE_SECONDS = 15.0
QUEUE_LOCK = "queue.lock"
QUEUE_STATE = "queue.state"
QUEUE_DIR = "queue"
NUMBER = re.compile(r"[0-9]+(\.[0-9]+)?")


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


class LoadRule(NamedTuple):
    """Admit only while load1 is below `limit`; `settle` seconds of low load and between starts. 0 is off."""
    limit: float
    settle: float
    source: str


def default_load_max(cores: int | None = None) -> float:
    """2.5 per core: 40 on a 16-core machine."""
    return LOAD_PER_CORE * (cores if cores is not None else (os.cpu_count() or CORES_PER_SLOT))


def parse_number(text: str, source: str) -> float:
    if not NUMBER.fullmatch(text):
        raise ValueError(f"{source} must be a non-negative number (got '{text}')")
    return float(text)


def load_rule(environ: Mapping[str, str], limit_setting: str | None = None, settle_setting: str | None = None,
              *, cores: int | None = None) -> LoadRule:
    """The load rule: each value from its variable, then the machine setting, then the default.

    The settings are `sd.gate_load_max` and `sd.gate_settle_seconds`, read by
    the caller so this file needs nothing but stdlib.
    """
    def setting_value(variable: str, setting: str | None, name: str, default: float) -> tuple[float, str | None]:
        if variable in environ:
            return parse_number(environ[variable], variable), variable
        if setting is not None:
            return parse_number(setting, name), name
        return default, None
    limit, limit_source = setting_value(LOAD_VARIABLE, limit_setting, "sd.gate_load_max", default_load_max(cores))
    settle, settle_source = setting_value(SETTLE_VARIABLE, settle_setting, "sd.gate_settle_seconds", DEFAULT_SETTLE_SECONDS)
    sources = [source for source in (limit_source, settle_source) if source]
    return LoadRule(limit, settle, ", ".join(sources) or "default")


#: The machine settings the stdlib entry points read, with the check each value passes.
MACHINE_SETTINGS: tuple[tuple[str, Callable[[str, str], object]], ...] = (
    ("gate_slots", parse_count), ("gate_load_max", parse_number), ("gate_settle_seconds", parse_number))


def machine_settings(environ: Mapping[str, str], *, stream: TextIO | None = None) -> dict[str, str | None]:
    """`sd.gate_slots`, `sd.gate_load_max` and `sd.gate_settle_seconds` from the machine config, as text.

    For the stdlib-only entry points (`wait` and `count`, which `run-tests.sh`
    runs, and `run`/`status` here), so they read what `sd-check` and `sd gate`
    read. The path is `sd_lib.machine_config_path`'s. A file that cannot be
    read or holds a bad value gives no settings, so the defaults, with a
    warning: load control never fails a gate.
    """
    home = environ.get("XDG_CONFIG_HOME") or str(pathlib.Path(environ.get("HOME") or pathlib.Path.home()) / ".config")
    path = pathlib.Path(home) / "sd-ai-command-pack" / "config.json"
    values: dict[str, str | None] = {key: None for key, _ in MACHINE_SETTINGS}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        mine = loaded.get("config", {}).get("sd", {}) if isinstance(loaded, dict) else {}
        for key, check in MACHINE_SETTINGS:
            value = mine.get(key) if isinstance(mine, dict) else None
            if value is not None:
                text = value if isinstance(value, str) else repr(value)
                check(text, f"sd.{key}")
                values[key] = text
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError) as error:
        if stream is not None:
            stream.write(f"warning: cannot read the gate settings in {path} ({error}); using the defaults\n")
        values = dict.fromkeys(values)
    return values


def machine_rule(environ: Mapping[str, str], *, stream: TextIO | None = None,
                 cores: int | None = None) -> LoadRule:
    """`load_rule` with `sd.gate_load_max` and `sd.gate_settle_seconds` read by `machine_settings`."""
    values = machine_settings(environ, stream=stream)
    return load_rule(environ, values["gate_load_max"], values["gate_settle_seconds"], cores=cores)


def utc_stamp(seconds: float) -> str:
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ticket:
    """One waiter's place: its sequence number and the locked ticket file."""

    def __init__(self, seq: int, path: pathlib.Path, fd: int | None) -> None:
        self.seq, self.path, self.fd = seq, path, fd

    def drop(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class Queue:
    """The machine-wide waiting order in front of the slots under `where`.

    Every read and change happens under `queue.lock`, so admission is one step.
    A ticket is created and locked under it, and only a process that can take
    a ticket's own lock removes it: its waiter is dead, and the kernel says so.
    """

    def __init__(self, where: pathlib.Path) -> None:
        self.where = where
        self.tickets = where / QUEUE_DIR

    @contextlib.contextmanager
    def admission_lock(self) -> Iterator[None]:
        fd = os.open(self.where / QUEUE_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def state(self) -> dict:
        try:
            loaded = json.loads((self.where / QUEUE_STATE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def write_state(self, state: dict) -> None:
        target = self.where / QUEUE_STATE
        partial = target.with_name(f"{QUEUE_STATE}.{os.getpid()}")
        partial.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        os.replace(partial, target)

    def enter(self, label: str, cwd: str, *, wall: Callable[[], float] = time.time) -> Ticket:
        """Take the next place in the queue, held by this process until `leave` or death."""
        self.tickets.mkdir(parents=True, exist_ok=True)
        with self.admission_lock():
            state = self.state()
            stored = state.get("next")
            seq = stored if isinstance(stored, int) and stored > 0 else 1 + max(
                (int(path.stem) for path in self.tickets.glob("*.ticket") if path.stem.isdigit()), default=0)
            state["next"] = seq + 1
            self.write_state(state)
            path = self.tickets / f"{seq:012d}.ticket"
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.write(fd, json.dumps({"seq": seq, "pid": os.getpid(), "label": label, "cwd": cwd,
                                     "since": wall()}).encode())
        return Ticket(seq, path, fd)

    def leave(self, ticket: Ticket) -> None:
        if ticket.fd is None:
            return
        with self.admission_lock():
            ticket.path.unlink(missing_ok=True)
            ticket.drop()

    def waiters(self, *, prune: bool) -> list[dict]:
        """The live tickets in order. Call under `admission_lock`; `prune` removes the dead ones."""
        live: list[dict] = []
        try:
            paths = sorted(self.tickets.glob("*.ticket"))
        except OSError:
            return live
        for path in paths:
            try:
                fd = os.open(path, os.O_RDWR)
            except OSError:
                continue
            try:
                if try_lock(fd):
                    if prune:
                        path.unlink(missing_ok=True)
                    continue
                try:
                    entry = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    entry = {}
                entry["seq"] = int(path.stem) if path.stem.isdigit() else 0
                live.append(entry)
            finally:
                os.close(fd)
        return live

    def admit(self, ticket: Ticket, fds: Sequence[int], rule: LoadRule, *,
              loadavg: Callable[[], Sequence[float]] = os.getloadavg,
              wall: Callable[[], float] = time.time) -> tuple[int | None, str]:
        """Lock one of `fds` for `ticket` when it heads the queue and the load rule holds.

        Returns the slot's index, or None and the reason it waits. An admitted
        ticket leaves the queue in the same step.
        """
        with self.admission_lock():
            state = self.state()
            now = wall()
            try:
                live = self.waiters(prune=True)
                order = [entry["seq"] for entry in live]
                if ticket.seq not in order:
                    order.append(ticket.seq)
                if order[0] != ticket.seq:
                    return None, f"place {order.index(ticket.seq) + 1} of {len(order)} in the queue"
                # Only the head samples, under its own rule: callers may run
                # different rules, and one waiter's sample must not count for another's.
                load1, load5 = (float(value) for value in tuple(loadavg())[:2])
                record_sample(state, rule, load1, now)
                held = load_hold(state, rule, load1, load5, now)
                if held:
                    return None, held
                for index, fd in enumerate(fds):
                    if try_lock(fd):
                        state["last_admitted"] = now
                        ticket.path.unlink(missing_ok=True)
                        ticket.drop()
                        return index, ""
                return None, f"{len(fds)} of {len(fds)} in use"
            finally:
                self.write_state(state)


def record_sample(state: dict, rule: LoadRule, load1: float, now: float) -> None:
    """Keep `low_since`: when load1 last went below the limit, in an unbroken run of samples.

    The record names the rule it was kept under; a sample under another rule
    starts it again, so no rule inherits low load another rule judged.
    """
    sampled = state.get("sampled_at")
    measured = [rule.limit, rule.settle]
    if rule.limit > 0 and load1 >= rule.limit:
        state["low_since"] = None
    elif (state.get("low_since") is None or state.get("sampled_rule") != measured
          or not isinstance(sampled, (int, float))
          or not 0 <= now - sampled <= max(rule.settle, STALE_SAMPLE_SECONDS)):
        state["low_since"] = now
    state["sampled_at"] = now
    state["sampled_rule"] = measured


def load_hold(state: dict, rule: LoadRule, load1: float, load5: float, now: float) -> str:
    """Why the head may not start now, or "" when it may."""
    if rule.limit > 0:
        if load1 >= rule.limit:
            return f"load {load1:.1f} is at or above {rule.limit:g}"
        low = now - float(state.get("low_since") or now)
        if load5 >= rule.limit and low < rule.settle:
            return (f"load {load1:.1f} has been below {rule.limit:g} for {low:.0f}s of {rule.settle:g}s "
                    f"(load5 {load5:.1f})")
    last = state.get("last_admitted")
    if rule.settle > 0 and isinstance(last, (int, float)) and 0 <= now - last < rule.settle:
        return f"the last gate started {now - last:.0f}s ago; starts are {rule.settle:g}s apart"
    return ""


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
                  clock: Callable[[], float] = time.monotonic, rule: LoadRule | None = None,
                  loadavg: Callable[[], Sequence[float]] = os.getloadavg, wall: Callable[[], float] = time.time,
                  label: str = "") -> int | None:
    """Queue, then lock one of `fds` and return its index; None once `deadline` passes.

    `stop` is asked before every attempt, so a waiter whose launcher died
    takes nothing even when a slot frees during its sleep. While queued it
    says why on `stream` at once and every `REPORT_EVERY_SECONDS` after. With
    no `rule` the load is not read. Each report names who holds the slots
    (sd:2522). A queue that cannot be written falls back to taking any free
    slot, as before sd:2262.
    """
    rule = rule if rule is not None else LoadRule(0.0, 0.0, "none")
    queue = Queue(where)
    try:
        ticket: Ticket | None = queue.enter(label or f"pid {os.getpid()}", os.getcwd(), wall=wall)
    except OSError as error:
        stream.write(f"warning: cannot queue under {where} ({error}); taking any free slot\n")
        ticket = None
    started = clock()
    reported: float | None = None
    try:
        while True:
            if stop():
                raise LauncherExited()
            if ticket is None:
                taken = next((index for index, fd in enumerate(fds) if try_lock(fd)), None)
                reason = f"{len(fds)} of {len(fds)} in use"
            else:
                taken, reason = queue.admit(ticket, fds, rule, loadavg=loadavg, wall=wall)
            if taken is not None:
                if reported is not None:
                    stream.write(f"gate slot taken after {clock() - started:.0f}s under {where}\n")
                    stream.flush()
                return taken
            now = clock()
            if reported is None:
                stream.write(f"waiting for a gate slot: {reason} under {where}{held_by(queue)}\n")
                stream.flush()
                reported = now
            elif now - reported >= REPORT_EVERY_SECONDS:
                stream.write(f"still waiting for a gate slot after {now - started:.0f}s: {reason}{held_by(queue)}\n")
                stream.flush()
                reported = now
            if deadline is not None and now >= deadline:
                return None
            time.sleep(poll if deadline is None else max(0.0, min(poll, deadline - now)))
    finally:
        if ticket is not None:
            queue.leave(ticket)


class Slot:
    """A slot held by this process until `release`; `waited` is the seconds spent queued."""

    def __init__(self, handle: TextIO | None, path: pathlib.Path | None, waited: float) -> None:
        self.handle, self.path, self.waited = handle, path, waited

    def release(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None


def write_info(lock: pathlib.Path, pid: int, label: str, cwd: str) -> None:
    """`slot.N.info` beside the lock: who holds it, for `status`. Only a hint, as the pid is."""
    info = lock.with_suffix(".info")
    try:
        partial = info.with_name(f"{info.name}.{os.getpid()}")
        partial.write_text(json.dumps({"pid": pid, "label": label, "cwd": cwd, "since": time.time()}),
                           encoding="utf-8")
        os.replace(partial, info)
    except OSError:
        pass


def acquire(slots: int, environ: Mapping[str, str], *, stream: TextIO, timeout: float | None = None,
            rule: LoadRule | None = None, label: str = "") -> Slot | None:
    """Take one of `slots` slots for this process, or None when `timeout` passed first.

    `slots` of 0 takes nothing. A directory that cannot be made runs uncapped
    with a warning, as the harness always has: a cap is load control, and no
    gate fails for the want of one. The lock files are not inherited by the
    checks this process starts, so a check that outlives it frees nothing late.
    With no `rule`, the load rule comes from the variables and the defaults.
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
                              deadline=None if timeout is None else started + timeout,
                              rule=rule if rule is not None else load_rule(environ), label=label)
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
    lock = where / f"slot.{taken + 1}.lock"
    try:
        held.truncate(0)
        held.write(f"{os.getpid()}\n")
        held.flush()
    except OSError:
        pass
    write_info(lock, os.getpid(), label or f"pid {os.getpid()}", os.getcwd())
    return Slot(held, lock, time.monotonic() - started)


def run_gated(command: Sequence[str], environ: Mapping[str, str], *, slots: int, rule: LoadRule, stream: TextIO,
        label: str = "", timeout: float | None = None) -> int:
    """Wait for a slot, run `command` with `SD_GATE_SLOTS=0`, free the slot, and return its exit code.

    The command runs in its own process group. SIGINT, SIGTERM and SIGHUP go
    to that whole group, and this process waits for the command to end. The
    slot lock is not passed to the command: when this process dies, even by
    SIGKILL, the kernel frees the slot (sd:1195), and a daemon the command
    started never holds one.
    """
    if not command:
        stream.write("error: name a command to run after --\n")
        return RUN_NOT_STARTED
    try:
        slot = acquire(slots, environ, stream=stream, timeout=timeout, rule=rule, label=label or shlex.join(command))
    except LauncherExited:
        stream.write("error: the process that started this gate exited while it waited for a slot\n")
        return RUN_NOT_STARTED
    except KeyboardInterrupt:
        return 128 + signal.SIGINT
    if slot is None:
        stream.write(f"error: no gate slot came free within {timeout:g}s\n")
        return RUN_TIMED_OUT
    forwarded = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {}
    try:
        try:
            child = subprocess.Popen(list(command), env={**environ, SLOTS_VARIABLE: "0"}, process_group=0)
        except OSError as error:
            stream.write(f"error: cannot run {command[0]}: {error}\n")
            return RUN_NOT_FOUND

        def forward(signum: int, _frame: object) -> None:
            try:
                os.killpg(child.pid, signum)
            except (ProcessLookupError, PermissionError):
                # A group that already exited: macOS answers EPERM, not only ESRCH (sd:2402).
                pass

        for signum in forwarded:
            previous[signum] = signal.signal(signum, forward)
        code = child.wait()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        slot.release()
    return 128 - code if code < 0 else code


def read_holders(where: pathlib.Path) -> list[dict]:
    """Who holds each slot under `where`; call under `queue.lock`, so no admission races the probe.

    A slot is held exactly when this process cannot lock it. Its label shows
    only when `slot.N.info` names the pid the lock file names, so a holder
    that wrote no info never shows an earlier holder's label.
    """
    holders = []
    numbers = {int(match.group(1)) for path in where.glob("slot.*.lock")
               if (match := re.fullmatch(r"slot\.([0-9]+)\.lock", path.name))}
    for number in sorted(numbers):
        lock = where / f"slot.{number}.lock"
        try:
            fd = os.open(lock, os.O_RDWR)
        except OSError:
            continue
        try:
            if try_lock(fd):
                fcntl.flock(fd, fcntl.LOCK_UN)
                continue
            text = lock.read_text(encoding="utf-8", errors="replace").split()
            pid = int(text[0]) if text and text[0].isdigit() else None
            try:
                info = json.loads(lock.with_suffix(".info").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                info = {}
            if not isinstance(info, dict) or info.get("pid") != pid:
                info = {}
            recorded = info.get("since")
            since = float(recorded) if isinstance(recorded, (int, float)) else lock.stat().st_mtime
            holders.append({"slot": number, "pid": pid, "label": info.get("label", ""),
                            "cwd": info.get("cwd", ""), "since": utc_stamp(since)})
        finally:
            os.close(fd)
    return holders


def held_by(queue: Queue) -> str:
    """The holders as one clause for a waiting line, or "" when none can be read (sd:2522)."""
    try:
        with queue.admission_lock():
            holders = read_holders(queue.where)
    except OSError:
        return ""
    return "".join(f"; slot {entry['slot']} held by {entry['label'] or 'an unlabelled gate'} "
                   f"(pid {entry['pid'] or '?'}) since {entry['since']}"
                   + (f" in {entry['cwd']}" if entry["cwd"] else "") for entry in holders)


def snapshot(where: pathlib.Path, slots: int, rule: LoadRule, *,
             loadavg: Callable[[], Sequence[float]] = os.getloadavg, wall: Callable[[], float] = time.time) -> dict:
    """Who holds a slot (`read_holders`), who waits and in which place, and the load rule; read under `queue.lock`."""
    queue = Queue(where)
    holders, waiters, state = [], [], {}
    if where.is_dir():
        with queue.admission_lock():
            state = queue.state()
            holders = read_holders(where)
            for place, entry in enumerate(queue.waiters(prune=False), start=1):
                queued = entry.get("since")
                waiters.append({"place": place, "pid": entry.get("pid"), "label": entry.get("label", ""),
                                "cwd": entry.get("cwd", ""),
                                "since": utc_stamp(float(queued)) if isinstance(queued, (int, float)) else ""})
    try:
        load = [round(float(value), 2) for value in tuple(loadavg())[:3]]
    except OSError:
        load = []
    last = state.get("last_admitted")
    return {"directory": str(where), "slots": slots, "holders": holders, "waiters": waiters, "load": load,
            "load_max": rule.limit, "settle_seconds": rule.settle, "rule_source": rule.source,
            "last_admitted": utc_stamp(last) if isinstance(last, (int, float)) else None, "now": utc_stamp(wall())}


def render_queue(report: dict) -> str:
    load = "/".join(f"{value:.1f}" for value in report["load"]) or "unknown"
    limit = f"{report['load_max']:g}" if report["load_max"] > 0 else "off"
    lines = [f"gate slots under {report['directory']}: {len(report['holders'])} of {report['slots'] or 'no cap'} in use; "
             f"load {load}, limit {limit}, settle {report['settle_seconds']:g}s",
             f"last start: {report['last_admitted'] or 'none recorded'}"]
    lines.append("holding:" if report["holders"] else "holding: none")
    for entry in report["holders"]:
        lines.append(f"  slot {entry['slot']}  pid {entry['pid']}  since {entry['since']}  "
                     f"{entry['label'] or '(no label)'}  {entry['cwd']}".rstrip())
    lines.append("waiting:" if report["waiters"] else "waiting: none")
    for entry in report["waiters"]:
        lines.append(f"  {entry['place']}. pid {entry['pid']}  since {entry['since']}  "
                     f"{entry['label'] or '(no label)'}  {entry['cwd']}".rstrip())
    return "\n".join(lines)


def add_gate_verbs(verbs: argparse._SubParsersAction) -> None:
    """`run` and `status`, shared by this file and `sd gate`."""
    runner = verbs.add_parser("run", help="wait in the machine-wide gate queue, run a command, free the slot")
    runner.add_argument("--label", default="", help="what `status` shows for this gate (default: the command)")
    runner.add_argument("--timeout", type=float, metavar="SECONDS",
                        help=f"give up waiting after this long, exit {RUN_TIMED_OUT}")
    runner.add_argument("command", nargs=argparse.REMAINDER, help="-- then the command and its arguments")
    shower = verbs.add_parser("status", help="who holds a gate slot, who waits, and since when")
    shower.add_argument("--json", action="store_true", help="one machine-readable object")


def gate_verb(args: argparse.Namespace, environ: Mapping[str, str], slots: int, rule: LoadRule) -> int:
    if args.command_name == "status":
        report = snapshot(directory(environ), slots, rule)
        print(json.dumps(report, indent=2) if args.json else render_queue(report))
        return 0
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    return run_gated(command, environ, slots=slots, rule=rule, stream=sys.stderr, label=args.label, timeout=args.timeout)


def slot_command(argv: list[str] | None = None) -> int:
    """`directory` prints where the slots live; `count` prints how many there are;
    `wait --pid P --ppid Q --dir D FD...` queues, locks one inherited descriptor
    and prints its index; `run` and `status` are `sd gate run` and `sd gate
    status`. All of them read the machine settings through `machine_settings`,
    so the count is `sd-check`'s: `SD_GATE_SLOTS`, CI, `sd.gate_slots`, the default.

    The shell that opened the descriptors keeps the lock after `wait` exits.
    Exit 3 when P's launcher exited, or when this process's own parent did.
    """
    parser = argparse.ArgumentParser(prog="sd_gate_slots.py")
    commands = parser.add_subparsers(dest="command_name", required=True)
    commands.add_parser("directory", help="print the slot directory")
    commands.add_parser("count", help="print how many slots this machine has (0: no cap)")
    wait = commands.add_parser("wait", help="queue, then lock one of the inherited slot descriptors")
    wait.add_argument("--pid", type=int, required=True, help="the gate's pid")
    wait.add_argument("--ppid", type=int, required=True, help="the gate's parent when it started")
    wait.add_argument("--dir", required=True, help="the slot directory, for the waiting message")
    wait.add_argument("fds", type=int, nargs="+")
    add_gate_verbs(commands)
    args = parser.parse_args(argv)
    if args.command_name == "directory":
        print(directory(os.environ))
        return 0
    try:
        settings = machine_settings(os.environ, stream=sys.stderr)
        rule = load_rule(os.environ, settings["gate_load_max"], settings["gate_settle_seconds"])
        if args.command_name in ("count", "run", "status"):
            slots, _ = configured(os.environ, settings["gate_slots"])
            if args.command_name == "count":
                print(slots)
                return 0
            return gate_verb(args, os.environ, slots, rule)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return RUN_NOT_STARTED if args.command_name == "run" else 2
    gate_gone = launcher_watch(args.pid, args.ppid)
    shell = os.getppid()
    where = pathlib.Path(args.dir)
    try:
        taken = wait_for_slot(args.fds, where, poll=poll_seconds(os.environ), stream=sys.stderr,
                              stop=lambda: os.getppid() != shell or gate_gone(), rule=rule,
                              label=f"run-tests.sh pid {args.pid}")
    except LauncherExited:
        return LAUNCHER_EXITED
    if taken is None:
        return TIMED_OUT
    write_info(where / f"slot.{taken + 1}.lock", args.pid, "run-tests.sh", os.getcwd())
    print(taken)
    return 0


if __name__ == "__main__":
    raise SystemExit(slot_command())
