"""The write path: every mutation is a named command, and the list is closed.

**`RUN_ALLOWLIST` is the whole security model of writing.** The server does not
take a command from the page, build one from a parameter, or interpolate
anything a caller sends into one. A POST names an **id**; it resolves to an
argv written down here; an id that resolves to nothing is a 404. There is no
path from request text to a shell -- `bounded_run` takes a list and never a
string, and nothing here joins one.

**The list is the backbone's own, and nothing else.** Until sd:719 step 3 a
registered plugin could declare actions beside its tile (R11-D21), namespaced by
its prefix and run in its own root. That went with the plugin loader: the
dashboard now offers `RUN_ALLOWLIST` and reads no manifest. `sd plugin list
--json` still reports a plugin's declared actions; this page no longer runs
them.

**What is NOT here, deliberately: no GET has a side effect.** The dashboard
this replaces started a rebuild on `GET /api/state?refresh=1` behind the Host
check alone while its POST twin required the token
(`local-project-dashboard/dashboard.py:1714` against `:1788` in
`platypeeps/system`, as that file stood at its last commit before
platypeeps/system#190 deleted it at 6b-9 -- a citation into that repository's
history, not into any working tree; nothing on disk answers to the path any
more). `tests/test_dashboard_actions.py` pins that this does not inherit the
habit, which outlives the file it was learned from.
"""

from __future__ import annotations

import os
import select
import signal
import subprocess
import time
from pathlib import Path

# Long enough for a collect that talks to GitHub and Jira, short enough that a
# wedged command is a failed button rather than a held thread.
ACTION_SECONDS = 300.0
ACTION_BYTES = 64 * 1024

# Resolved from this file, not looked up on `PATH`: the server may be a
# LaunchAgent whose `PATH` is launchd's, and a button that works in a terminal
# and 502s under the agent is the failure this constant exists to make
# impossible. Found by pressing it.
SD_DASHBOARD = Path(__file__).resolve().parent.parent / "bin" / "sd-dashboard"

# The backbone's own. One entry, and it is the one the Issues and PRs tabs
# already ask for by printing how stale they are.
RUN_ALLOWLIST: dict[str, dict] = {
    "index": {
        "label": "collect issues and pull requests",
        "argv": [str(SD_DASHBOARD), "index"],
        "cwd": None,
    },
}


# --- the bounded call ----------------------------------------------------
# Moved here from `dashboard/plugins.py` at sd:719 step 3, when the plugin loader
# was deleted and this module became the only caller. The comments below say
# "tile" because a plugin tile was the first child this bounded; an action is
# the same kind of child under the same two bounds.

READ_CHUNK = 65536
# How much of a failing tile's stderr rides back in the refusal. The tail
# rather than the head: a Python traceback puts the error on its last line, and
# a plugin author reading a row wants the thing that went wrong rather than the
# first frame of the stack that led there. Bounded because stderr is written by
# the plugin too, and an unbounded one would put a plugin in charge of how long
# a row is.
STDERR_TAIL = 512

# What one refusal will read off stderr on its way out, at most. Raised in
# review as a hang: a tile writing stderr in a loop keeps the pipe readable, so
# an unbounded drain would spin there and never reach the kill. Measured, that
# does not happen -- `yes`, `cat /dev/zero`, and three concurrent writers each
# ran the pipe empty in three reads, because a zero-timeout `select` sees the
# gap the instant the reader wins and no writer refills within that quantum.
# The bound stays anyway, on the narrower claim it can actually carry: one
# refusal reads what one pipe buffer can hold, which is everything a tile can
# have written with nobody reading, and it is a fixed amount of work rather
# than an argument about scheduling.
DRAIN_BYTES = 65536


class Bounded(Exception):
    """A subprocess did not deliver a usable answer inside its bounds.

    Raised for every way `bounded_run` can decline: the deadline passing, the
    byte ceiling being crossed, the command failing to start, the process
    outliving its own output, and a non-zero exit. The message says which.
    """


def _terminate(proc: subprocess.Popen) -> None:
    """Kill the child's whole process group, not just the command it named.

    A command that backgrounds work would otherwise outlive its own timeout and
    go on holding the pipe, so the deadline would bound this module and nothing
    else.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def bounded_run(argv: list[str], cwd: Path | None, *, seconds: float, limit: int) -> bytes:
    """`argv`'s stdout, refusing past `seconds` or `limit` bytes.

    Both bounds are applied to the stream as it arrives. Reading everything and
    measuring afterwards would make the limit advisory: the process has already
    handed us the bytes by the time the number is known.

    Stderr is read alongside stdout and its tail is carried into the refusal.
    It used to go to `DEVNULL`, which made every failing tile report as bare
    `exited 1` -- this module refuses to let a plugin go quiet and was
    discarding the plugin's own account of why it had. It is read rather than
    left in a pipe because a pipe nobody drains fills, and a tile blocked
    writing its traceback would hit the deadline and be reported as a timeout
    instead: the fix for a lost message would have been a wrong one.
    """
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except (OSError, ValueError) as error:
        # The cwd belongs in the message: "no such file or directory" for a
        # tile that exists says nothing until you know which directory it was
        # looked for in. Found in review.
        where = f" in {cwd}" if cwd is not None else ""
        raise Bounded(f"cannot run {argv[0]}{where}: {error}") from None

    chunks: list[bytes] = []
    size = 0
    stop = time.monotonic() + seconds
    assert proc.stdout is not None
    assert proc.stderr is not None
    said = b""

    def refuse(reason: str) -> Bounded:
        """The refusal, with whatever the tile managed to say about it."""
        drain()
        tail = said.decode("utf-8", "replace").strip()
        return Bounded(f"{reason}: {tail}" if tail else reason)

    def drain() -> None:
        """Whatever is already in the stderr pipe, without waiting for more.

        Called on the way to every refusal because the interesting case is a
        tile that writes its traceback and exits: both pipes close at once, and
        the loop can break on stdout without stderr's last read.

        Never blocks: a zero timeout means no read waits on the tile. Bounded
        by DRAIN_BYTES besides, so one refusal costs a fixed amount of reading
        no matter what the tile is doing -- see that constant for what was and
        was not shown about the loop this bound was proposed to stop.
        """
        nonlocal said
        budget = DRAIN_BYTES
        while err in watch and budget > 0:
            if not select.select([err], [], [], 0)[0]:
                return
            piece = os.read(err, min(READ_CHUNK, budget))
            if not piece:
                watch.remove(err)
                return
            budget -= len(piece)
            said = (said + piece)[-STDERR_TAIL:]

    fd = proc.stdout.fileno()
    err = proc.stderr.fileno()
    watch = [fd, err]
    try:
        while True:
            left = stop - time.monotonic()
            # Two different failures share this deadline and are not the same
            # thing to whoever reads the row: a tile that never spoke, and one
            # that wrote and then stopped. Reporting the second as "no stdout"
            # sends the operator looking for a tile that never started.
            #
            # Both name stdout rather than output, because since R11-D18 the
            # refusal carries the tile's stderr tail: "no output within 5s:
            # Traceback ..." contradicts itself, and the tile that talked only
            # on stderr is exactly the case this message is read in. Found in
            # review.
            stalled = (
                f"no stdout within {seconds:g}s"
                if not size
                else f"stopped writing stdout within {seconds:g}s, after {size} bytes"
            )
            if left <= 0:
                raise refuse(stalled)
            ready = select.select(watch, [], [], left)[0]
            if not ready:
                raise refuse(stalled)
            if err in ready:
                # Kept as a tail, so a tile that writes megabytes of warnings
                # costs a constant amount of memory rather than its own choice
                # of one.
                piece = os.read(err, READ_CHUNK)
                if piece:
                    said = (said + piece)[-STDERR_TAIL:]
                else:
                    # Closed. Left in `watch` it would be ready forever and
                    # spin this loop against the deadline.
                    watch.remove(err)
                continue
            # One byte past the ceiling is enough to know the tile crossed
            # it. Asking for a fixed 64KB and measuring afterwards would let a
            # caller with a small limit still be handed -- and made to
            # allocate -- a full chunk before the limit was consulted, which
            # is the opposite of enforcing it while reading.
            chunk = os.read(fd, min(READ_CHUNK, limit - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise refuse(f"wrote more than {limit} bytes")
            chunks.append(chunk)
        # Closing stdout is not exiting, and the exit status is part of what
        # the budget covers: a tile that prints its JSON and then fails has
        # failed. Killing it on the way past would record -SIGKILL, and a
        # loader that reads its own kill as a clean exit accepts the output of
        # every tile that dies after writing.
        #
        # The wait drains, for the reason the loop above reads stderr at all.
        # Stdout closing does not close stderr, and a tile that prints its JSON,
        # closes stdout, then writes past the pipe capacity on stderr blocks in
        # that write until someone reads -- so a plain `wait` here would hang on
        # it until the deadline and report `did not exit` for a tile that had
        # already said everything it was asked for. That is the deadlock this
        # function was changed to remove, moved past the break. Found in review.
        while True:
            left = stop - time.monotonic()
            if left <= 0:
                raise refuse(f"did not exit within {seconds:g}s")
            if err in watch:
                # Capped at 50ms so a tile that exits while holding stderr open
                # -- a grandchild inheriting it -- is noticed by the `wait`
                # below rather than waited on until the deadline.
                if select.select([err], [], [], min(left, 0.05))[0]:
                    piece = os.read(err, READ_CHUNK)
                    if piece:
                        said = (said + piece)[-STDERR_TAIL:]
                        continue
                    watch.remove(err)
            try:
                # Once stderr is closed there is nothing left to drain and this
                # blocks for the rest of the budget; while it is open the poll
                # is free and the select above is what does the waiting.
                proc.wait(timeout=left if err not in watch else 0.0)
                break
            except subprocess.TimeoutExpired:
                continue
        if proc.returncode != 0:
            raise refuse(f"exited {proc.returncode}")
    finally:
        # Only on the way out of a refusal. A tile that exited on its own has
        # nothing left to kill, and `poll()` is what tells the two apart.
        if proc.poll() is None:
            _terminate(proc)
        proc.stdout.close()
        proc.stderr.close()
    return b"".join(chunks)


def catalog() -> list[dict]:
    """What the page may offer: id and label only, never the argv.

    The command is not sent to the browser. Nothing there needs it, and a page
    that has never seen an argv cannot be talked into echoing a different one
    back.

    Declaration order, not sorted: R11-D23 chose a list over an object keyed
    by id to keep it. Found in review, against this repository's own record.
    """
    return [{"id": name, "label": spec["label"]}
            for name, spec in RUN_ALLOWLIST.items()]


def run(action_id: object) -> tuple[dict, int]:
    """Run one allow-listed action. `(body, status)`.

    Resolved, never constructed: an unknown id is a 404, not an attempt.
    """
    if not isinstance(action_id, str) or not action_id:
        return {"ok": False, "error": "no action named"}, 400
    spec = RUN_ALLOWLIST.get(action_id)
    if spec is None:
        return {"ok": False, "error": f"no such action: {action_id}"}, 404
    try:
        out = bounded_run(
            spec["argv"],
            cwd=Path(spec["cwd"]) if spec["cwd"] else None,
            seconds=ACTION_SECONDS,
            limit=ACTION_BYTES,
        )
    except Bounded as error:
        # The operator pressed a button and something did not happen. Saying
        # which is the difference between a dashboard and a light switch with
        # no bulb behind it.
        return {"ok": False, "error": str(error), "id": action_id}, 502
    text = out.decode("utf-8", "replace").strip()
    return {"ok": True, "id": action_id, "output": text[-2000:]}, 200
