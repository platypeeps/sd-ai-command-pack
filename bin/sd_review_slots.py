"""Machine-wide review slots: at most N reviews run their reviewers at once (sd:2523).

On the 2026-10-02 overnight run, lanes in several repositories each ran
`sd-ship prepare` at once, and each started a Codex review with no shared
limit, so load and the account's quota spiked together. A review now holds a
slot from its first reviewer to its last; the gate after it has its own pool.

A slot is a kernel `flock` on `<dir>/slot.N.lock`, the shape of `sd_gate_slots`
in its own directory: a holder that dies frees its slot, and no waiter judges a
holder dead. `slot.N.info` names the holder for the waiting line.

The cap is `SD_REVIEW_SLOTS`, then `sd.review_slots`, then 2; `0` is no cap.
Flat, not a share of the cores as the gate's is: a reviewer spends one model
account's quota and mostly waits on the network, and neither scales with cores.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from typing import Any, Callable, Mapping, TextIO

import sd_lib
import sd_review_readiness
from sd_gate_slots import parse_count, try_lock, utc_stamp, write_info

SLOTS_VARIABLE = "SD_REVIEW_SLOTS"
DIRECTORY_VARIABLE = "SD_REVIEW_SLOTS_DIR"
DEFAULT_SLOTS = 2
POLL_SECONDS = 5.0
clock = time.monotonic


def review_slot_directory(environ: Mapping[str, str]) -> pathlib.Path:
    """Where the slot lock files live, shared by every review on this machine."""
    if environ.get(DIRECTORY_VARIABLE):
        return pathlib.Path(environ[DIRECTORY_VARIABLE])
    state = environ.get("XDG_STATE_HOME") or str(pathlib.Path(environ.get("HOME", "~")).expanduser() / ".local" / "state")
    return pathlib.Path(state) / "sd" / "review-slots"


def review_slot_cap(environ: Mapping[str, str], setting: str | None) -> tuple[int, str]:
    """The cap and who set it: the variable, then `sd.review_slots`, then the default."""
    if SLOTS_VARIABLE in environ:
        return parse_count(environ[SLOTS_VARIABLE], SLOTS_VARIABLE), SLOTS_VARIABLE
    if setting is not None:
        return parse_count(setting, "sd.review_slots"), "sd.review_slots"
    return DEFAULT_SLOTS, "default"


def holder(where: pathlib.Path, number: int) -> str:
    """`slot N: <label> pid P since T`, from the info file: a hint, never evidence."""
    try:
        info = json.loads((where / f"slot.{number}.info").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = None
    info = info if isinstance(info, dict) else {}
    since = info.get("since")
    return (f"slot {number}: {info.get('label') or '(no label)'} pid {info.get('pid')}"
            + (f" since {utc_stamp(since)}" if isinstance(since, (int, float)) else ""))


class Slot:
    """A slot held until `give_back`; `report` is what the review result records."""

    def __init__(self, handle: TextIO | None, report: dict) -> None:
        self.handle, self.report = handle, report

    def give_back(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def __del__(self) -> None:
        # A backstop: `sd-review` gives the slot back in a `finally`. A holder
        # that forgets to frees it when the last reference goes.
        self.give_back()


def take_review_slot(environ: Mapping[str, str], setting: Callable[[], str | None], *, stream: TextIO, label: str,
            deadline: float | None = None, poll: float = POLL_SECONDS) -> Slot | None:
    """Wait for a slot and hold it; None once `deadline`, a `clock` reading, passes first.

    `setting` reads `sd.review_slots`. One that cannot be read, a bad cap, or
    a directory that cannot be used gives the default or no cap with a
    warning: the cap is load control, and no review fails for the want of one.
    """
    try:
        slots, source = review_slot_cap(environ, None if SLOTS_VARIABLE in environ else setting())
    except Exception as error:  # noqa: BLE001 -- sd_lib.ConfigError or ValueError; either only warns
        stream.write(f"warning: {error}; using {DEFAULT_SLOTS} review slots\n")
        slots, source = DEFAULT_SLOTS, "default"
    report = {"slots": slots, "source": source, "waited_seconds": 0}
    where = review_slot_directory(environ)
    try:
        if slots > 0:
            where.mkdir(parents=True, exist_ok=True)
        handles = [open(where / f"slot.{number}.lock", "a") for number in range(1, slots + 1)]
    except OSError as error:
        stream.write(f"warning: cannot use {where} ({error}); reviewing without the review cap\n")
        handles = []
    if not handles:
        return Slot(None, report)
    started, waiting = clock(), False
    while (taken := next((index for index, handle in enumerate(handles) if try_lock(handle.fileno())), None)) is None:
        if not waiting:
            stream.write(f"waiting for a review slot: {slots} of {slots} in use under {where} "
                         f"({'; '.join(holder(where, number) for number in range(1, slots + 1))})\n")
            stream.flush()
            waiting = True
        if deadline is not None and clock() >= deadline:
            for handle in handles:
                handle.close()
            return None
        time.sleep(poll if deadline is None else max(0.0, min(poll, deadline - clock())))
    for index, handle in enumerate(handles):
        if index != taken:
            handle.close()
    write_info(where / f"slot.{taken + 1}.lock", os.getpid(), label, os.getcwd())
    report.update(slot=taken + 1, waited_seconds=round(clock() - started))
    return Slot(handles[taken], report)


def hold_review_slot(result: dict[str, Any], environ: Mapping[str, str], root: pathlib.Path,
                     bound_seconds: float) -> Slot | None:
    """`sd-review`'s slot step: hold a slot for its reviewers, or refuse the review in `result`.

    The reviewers run before the gate (sd:2605), so the wait cannot spend the
    gate's bound: the gate after it still needs all of it. `sd-review` passes
    its setup bound, counted from the process start that `sd_lib.STARTED`
    records, so setup and the wait share that one term of sd-ship's watchdog
    plan. Kept here, outside the review lane, so `sd-review` spends five
    lines on it (sd:2523): take the slot, refuse, and give it back in a
    `try`/`finally` before the gate. None means the review refused.
    """
    slot = take_review_slot(environ, lambda: sd_lib.core_setting("review_slots", dict(environ)), stream=sys.stderr,
                            label=f"sd-review {root}", deadline=sd_lib.STARTED + bound_seconds)
    if slot is None:
        result["readiness"]["status"] = "blocked"
        result["readiness"]["blockers"].append(sd_review_readiness.blocker(
            "review_slot_busy", "capacity", "No review slot came free within the setup bound; prepare again."))
        result["status"] = "refused"
        return None
    result["review_slot"] = slot.report
    return slot
