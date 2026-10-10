"""`sd-ship lane`: a serial ship queue per repository that outlives the session that filled it (sd:2524).

An integrator session used to chain `sd-ship prepare` and `merge` by hand, in
shell scripts kept in its scratchpad. The chain died with the session, and a
second chain started beside it raced it. This keeps the chain in a file and
runs it under one lock per repository:

  enqueue  add a worktree, its item, the head it must still be at, a title
           and a body file to the repository's queue;
  list     print the queue;
  cancel   mark a pending entry cancelled;
  retry    queue the item's last failed, skipped or prepared entry again, at
           its head with its kept body; `--manual` grants the merge (sd:3254);
           `--expected-head` refuses, under the queue's lock, a last entry
           at another head (sd:3268);
  move     put a pending entry up, down, on top or at a position (sd:2584);
  hold     keep a pending entry in place but skip it; `release` ends that;
           these four take `--expected-revision`, the `revision` `list`
           prints, and refuse a queue that changed since (sd:2717, sd:3137);
  run      take the queue's first pending entry that is not held, read again
           before each item: head check, `prepare --catch-up` (once more
           with `--retry-review` after an incomplete review, sd:3037),
           then `merge`; a failed entry is marked and the runner goes on.
           While one entry ships, the next one's gate runs on its predicted
           landing (sd:2586, below). After a merge it deletes the remote
           branch, notes the item with the worktree's removal command and
           fast-forwards the main checkout (sd:2568, below). Under the
           runner lock it first marks failed a running entry whose runner
           pid is gone, with `reclaimed_by`, and lists it as `reclaimed`
           (sd:2821). An entry whose prepare or merge met a hub fault goes
           back to pending, at most `HUB_RETRIES` times, and the run stops
           (sd:3239, below);
  watch    print each gate end a lane or builder log records, once.

The verbs are the queue's only writers, each under the queue file's lock, so
a terminal and a dashboard reorder it the same way. A change takes effect at
the next item boundary, never mid-merge; a running entry refuses every edit.

The queue is `<lane root>/<repository>/lane/queue/queue.json`. The lane root
is `SD_LANE_ROOT`, else `sd.lane_root`, else `$XDG_STATE_HOME/sd/lanes`.

What the hand-run chains taught, kept here:

  - The runner holds the repository's lane lock from before the catch-up
    merge to after the merge. A merge of the base done before the lock went
    stale when another chain landed first, and prepare refused it as behind.
  - The runner never waits for a lock. A runner that finds the lane lock held
    exits at once, and `sd-ship` refuses a locked repository rather than
    queueing behind it, so no process holds one lock while it waits on another
    (a 28-minute stall on 2026-10-03).
  - Every prepare and merge keeps its whole output in a log beside the queue,
    so a failure can be read without running the step again.

The merge needs authority (sd:3132): `repo.runner_merge` `auto` for the
repository, or `--manual` on the entry, the operator's explicit grant on a
`manual` repository. The runner then merges with `--manual`. Otherwise, or
when the setting cannot be read, it stops at a prepared head, marks the entry
`prepared` and says why in its `code` and `reason` (`merge_refusal`).

An entry that stops short of a merge (`failed`, `skipped` or `prepared`)
keeps its body copy until the item's next entry ends (sd:3254), so `retry`
needs no body file. That next entry takes a copy of its own, and its end
drops every earlier entry's copy; a merged or cancelled entry drops its own.

The next entry's gate runs early (sd:2586). Its prepare used to start only
after the entry ahead merged, then catch up and gate for 10 to 20 minutes.
When the runner claims an entry that may merge, it predicts the landing: the
entry's catch-up merge of the fetched base branch, as a commit on that base.
It merges the next entry onto that commit as prepare's catch-up would, in a
scratch worktree, and runs `sd gate check`'s gate there in the background. The real landing is another commit with the
same tree, so the next entry's catch-up makes the gated tree, and its prepare
reuses the receipt. That needs the repository's tree key
(`sd_gate_receipts`), which names the merge base by its tree; without it, or
on a conflict, nothing is gated. After a merge the runner waits for that gate
before the next prepare. A wrong prediction costs only the machine time: the
receipt names a tree that prepare never gates, and prepare runs its own check.
The next entry records what happened as its `speculation`.

After a merge the runner lands the entry (sd:2568). It deletes the remote
branch with `--force-with-lease` while the worktree's tip is the merged head.
It never removes the worktree: no lock excludes its builder, and a write
through a handle opened before removal is lost. The entry's `remove` holds
the command that removes the worktree and its branch once the builder stops.
It notes the item with the merge commit, what the cleanup did, a `git
branch` recover command and that command. A worktree `sd-ship merge` has
already removed (sd:3006) is noted as such, from the lane's own checkout
(sd:3096). Then it fast-forwards the main
checkout. When that checkout holds the running `sd-ship`, as the pack's does
for every lane, it tries each other lane's runner lock once and skips if one
is held: a lane mid-prepare must not have its tools change under it, and no
lane waits on another's lock. The next landing retries. It holds the lane
root folder's lock meanwhile, and a runner that starts then runs nothing
(sd:3273): a lane with no runner lock yet has none to try.

Only a repository's lane host drains its queue (sd:3003): the machine
`repo.lane_host` names, or the hub when it is NULL. Elsewhere `run`,
`enqueue`, `move`, `hold` and `release` refuse with `lane_elsewhere`, and a
host that cannot be read refuses with `lane_unknown`. The runner reads the
host again before each claim, so a move stops it at the next item. The same
scheduled job runs on every machine: `lane run --hosted` runs each lane this
machine hosts, one after another, and skips one whose runner is busy. A
satellite that hosts a lane gates and merges on its own machine, so no item
passes from one machine to another.

A hub fault is retried (sd:3239). A hub upgrade broke a satellite's sessions
mid-prepare, and the entries failed for good. When `sd-ship` names the
blocker `hub_unavailable` (`sd_ship_workflow.HUB_FAULTS`), the runner puts the
entry back as pending with its `hub_retries` count and stops: the next entry
would meet the same hub. The next run starts after the satellite's
self-install, in a new process. When prepare's catch-up merge moved HEAD,
the entry's `expected_head` moves to it; any other move still skips the entry.
The retry's prepare reuses a review that cleared before the fault, as at any
head the ship receipt records reviewed; a review whose report the fault kept
from the receipt is incomplete, and spends the one `--retry-review`.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Iterator

import sd_lib
import sd_ship_workflow

BIN = pathlib.Path(__file__).resolve().parent
ROOT_VARIABLE = "SD_LANE_ROOT"
#: Each also covers its gate's slot wait, which has its own bound (sd:2611).
PREPARE_SECONDS = 3 * 3600 + sd_lib.GATE_SLOT_SECONDS
MERGE_SECONDS = 3 * 3600 + sd_lib.GATE_SLOT_SECONDS
MERGE_WAIT_SECONDS = 2100
#: The lines a gate writes when it ends: the pack's test runner, `make`'s own
#: failure, and the system repository's check script.
GATE_END = re.compile(r"run-tests: end head=|check\.sh: every suite passed|make: \*\*\*")
WATCH_MINUTES = 3
#: Prepare's delivery choices; an entry carries one and forwards it unchanged.
CLAIMS = ("deliver", "associate-only")
#: The relative places `move` takes besides a 1-based position among pending entries.
PLACES = ("up", "down", "top")
#: The verbs that fill or reorder a queue only its lane host drains; off the host they refuse (sd:2795, sd:3003).
#: `list` and `cancel` still answer there, so an old host's pending entries can be read and cancelled after a move.
HOST_VERBS = ("enqueue", "move", "hold", "release", "retry")
#: `(argv, log) -> sd-ship's JSON answer`; the log receives the step's whole output.
Ship = Callable[[list[str], pathlib.Path], dict[str, Any]]
#: `(root, head, base) -> the gate's result`: the next entry's gate on a predicted landing (sd:2586).
Gate = Callable[[pathlib.Path, str, str], dict[str, Any]]
#: `(item, body, main checkout) -> what happened`: the landing's item note (sd:2568).
Note = Callable[[int, str, pathlib.Path], str]
#: The codes of an entry that stops `prepared` for want of merge authority (sd:3132).
RUNNER_MERGE_MANUAL = "runner_merge_manual"
RUNNER_MERGE_UNKNOWN = "runner_merge_unknown"
#: The runs that put an entry back after a hub fault before the next fault fails it (sd:3239).
HUB_RETRIES = 2
#: The ends short of a merge: such an entry keeps its body copy, and `retry` queues it again (sd:3254).
BLOCKED = ("failed", "skipped", "prepared")


class LaneError(RuntimeError):
    """A lane command that cannot do what it was asked; nothing was changed. `code` is a stable refusal name, or None."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


#: The refusal code of a cancel, move, hold or release whose `--expected-revision` no longer matches (sd:2717).
STALE_REVISION = "stale_revision"
#: The refusal code of a retry whose `--expected-head` is not the head of the item's last entry (sd:3268).
STALE_HEAD = "stale_head"


def lane_root(environ: dict[str, str]) -> pathlib.Path:
    """Where every repository's lane folder lives: the variable, the setting, or the state default."""
    value = environ.get(ROOT_VARIABLE) or sd_lib.core_setting("lane_root", environ)
    if value:
        return pathlib.Path(os.path.expanduser(value))
    state = environ.get("XDG_STATE_HOME") or os.path.join(environ.get("HOME") or os.path.expanduser("~"), ".local/state")
    return pathlib.Path(state) / "sd" / "lanes"


def lane_dir(root: pathlib.Path, environ: dict[str, str]) -> pathlib.Path:
    """This repository's lane folder, named after its main checkout, so every worktree shares it."""
    return lane_root(environ) / sd_lib.main_worktree_root(root).resolve().name / "lane"


def queue_path(root: pathlib.Path, environ: dict[str, str]) -> pathlib.Path:
    return lane_dir(root, environ) / "queue" / "queue.json"


@contextlib.contextmanager
def queue_lock(path: pathlib.Path) -> Iterator[None]:
    """A short exclusive hold on the queue file for one read-modify-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def read_queue(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries")
    except FileNotFoundError:
        return []
    except (OSError, ValueError, AttributeError) as error:
        raise LaneError(f"cannot read the lane queue {path}: {error}") from None
    if not isinstance(entries, list):
        raise LaneError(f"the lane queue {path} holds no entry list")
    return entries


def write_queue(path: pathlib.Path, entries: list[dict[str, Any]]) -> None:
    """Replace the queue in one rename, so a reader never sees half a file."""
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        json.dump({"entries": entries}, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(handle.name, path)


def update(path: pathlib.Path, change: Callable[[list[dict[str, Any]]], Any]) -> Any:
    with queue_lock(path):
        entries = read_queue(path)
        answer = change(entries)
        write_queue(path, entries)
        return answer


def lane_git(worktree: pathlib.Path, *args: str) -> str | None:
    return sd_lib.git_output(list(args), worktree)


def stamp_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def keep_body(body_file: pathlib.Path, lane: pathlib.Path, item: int) -> pathlib.Path:
    """A private copy of the pull request body under the lane's own folder (sd:3170).

    The runner passes the body to prepare later, and a body under /tmp did not
    outlive a reboot. The copy is the entry's own, so two entries never share one.
    """
    bodies = lane / "bodies"
    bodies.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f"{item}-", suffix=".md", dir=bodies)
    with os.fdopen(handle, "wb") as copy:  # mkstemp makes it 0600
        copy.write(body_file.read_bytes())
    return pathlib.Path(name)


def drop_body(row: dict[str, Any], lane: pathlib.Path) -> None:
    """Remove an ended entry's body copy; a body an earlier version queued by its own path stays (sd:3170)."""
    body = pathlib.Path(str(row.get("body_file") or ""))
    if body.parent == lane / "bodies":
        body.unlink(missing_ok=True)


def enqueue_entry(worktree: pathlib.Path, item: int, title: str, body_file: pathlib.Path, environ: dict[str, str], *,
                  expected_head: str | None = None, manual: bool = False, claim: str | None = None,
                  acceptance_file: pathlib.Path | None = None,
                  guard: Callable[[list[dict[str, Any]]], None] | None = None) -> dict[str, Any]:
    """Add one entry; the head defaults to the worktree's, and must name a commit there.

    `claim` is prepare's delivery choice, `deliver` or `associate-only`, and
    is refused when absent as prepare refuses it; it and `acceptance_file`
    reach prepare unchanged. `guard` reads the queue under its lock first,
    and refuses by raising.
    """
    worktree = worktree.resolve()
    sd_lib.refuse_unmanaged(worktree, LaneError)  # its prepare would refuse; do not queue it
    if claim not in CLAIMS:
        raise LaneError("name the delivery claim prepare needs: --deliver for the item's last pull request, "
                        "or --associate-only for an earlier one")
    if acceptance_file is not None and not acceptance_file.is_file():
        raise LaneError(f"the acceptance file {acceptance_file} does not exist")
    head = lane_git(worktree, "rev-parse", "--verify", "--quiet", f"{expected_head or 'HEAD'}^{{commit}}")
    if not head:
        raise LaneError(f"{expected_head or 'HEAD'} names no commit in {worktree}")
    if not body_file.is_file():
        raise LaneError(f"the body file {body_file} does not exist")
    path = queue_path(worktree, environ)
    body = keep_body(body_file, path.parent.parent, item)
    entry = {"worktree": str(worktree), "item": item, "expected_head": head, "title": title,
             "body_file": str(body), "authority": "manual" if manual else None, "claim": claim,
             "acceptance_file": str(acceptance_file.resolve()) if acceptance_file else None,
             "status": "pending", "enqueued_at": stamp_now()}

    def add_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
        if guard is not None:
            guard(entries)
        if any(row.get("item") == item and row.get("status") in ("pending", "running") for row in entries):
            raise LaneError(f"sd:{item} is already queued in this lane")
        entries.append(entry)
        return entry
    try:
        return update(path, add_entry)
    except BaseException:
        body.unlink(missing_ok=True)
        raise


def pending_entry(entries: list[dict[str, Any]], item: int) -> dict[str, Any]:
    for row in entries:
        if row.get("item") == item and row.get("status") == "pending":
            return row
    if any(row.get("item") == item and row.get("status") == "running" for row in entries):
        raise LaneError(f"sd:{item} is running; the queue changes only between items")
    raise LaneError(f"sd:{item} has no pending entry in this lane")


def queue_revision(entries: list[dict[str, Any]]) -> str:
    """The pending order and holds, which is everything a reorder reads; `lane list` prints it (sd:2717).

    The same digest the system dashboard's Queue page computed for itself, so
    a revision it already holds still compares equal.
    """
    pending = [[row.get("item"), bool(row.get("held"))] for row in entries if row.get("status") == "pending"]
    return hashlib.sha256(json.dumps(pending).encode()).hexdigest()[:16]


def check_revision(entries: list[dict[str, Any]], expected: str | None) -> None:
    """Refuse a reorder made against a queue that changed since the caller read it; None checks nothing."""
    if expected is not None and queue_revision(entries) != expected:
        raise LaneError(f"the queue changed since revision {expected}; it is at {queue_revision(entries)}; "
                        "read it again with `sd-ship lane list`", code=STALE_REVISION)


def cancel(root: pathlib.Path, item: int, environ: dict[str, str], *,
           expected_revision: str | None = None) -> dict[str, Any]:
    path = queue_path(root, environ)

    def mark(entries: list[dict[str, Any]]) -> dict[str, Any]:
        check_revision(entries, expected_revision)
        row = pending_entry(entries, item)
        row.update(status="cancelled", finished_at=stamp_now())
        return row
    row = update(path, mark)
    drop_body(row, path.parent.parent)  # after the write, so a failed write leaves the body with its entry
    return row


def retry(root: pathlib.Path, item: int, environ: dict[str, str], *, manual: bool = False,
          expected_head: str | None = None) -> dict[str, Any]:
    """Queue `item`'s last entry again when it stopped short of a merge (sd:3254).

    A new entry, as `enqueue` makes it, from the old one's worktree, title,
    claim, acceptance file and kept body copy, at its head or prepare's
    catch-up of it (`caught_up`). `manual` grants the merge as `enqueue
    --manual` does; an entry that had that grant keeps it. The old entry
    stays as history, and its copy goes when the new entry ends.

    `expected_head`, a full commit id, is the head the caller showed: under
    the queue's lock, a last entry at another head is refused with
    `STALE_HEAD` (sd:3268). None checks nothing.
    """
    def at_expected_head(entries: list[dict[str, Any]]) -> None:
        latest = [row for row in entries if row.get("item") == item][-1:]
        head = latest[0].get("expected_head") if latest else None
        if expected_head is not None and head != expected_head:
            raise LaneError(f"sd:{item}'s last entry is at {head}, not the expected head {expected_head}; "
                            "read it again with `sd-ship lane list`", code=STALE_HEAD)
    rows = [row for row in read_queue(queue_path(root, environ)) if row.get("item") == item]
    if not rows:
        raise LaneError(f"sd:{item} has no entry in this lane")
    last = rows[-1]
    at_expected_head(rows)
    if last.get("status") in ("pending", "running"):
        raise LaneError(f"sd:{item} is already queued in this lane")
    if last.get("status") not in BLOCKED:
        raise LaneError(f"sd:{item}'s last entry is {last.get('status')}; retry takes a failed, skipped or "
                        "prepared one")
    body = pathlib.Path(str(last.get("body_file") or ""))
    if not body.is_file():
        raise LaneError(f"sd:{item}'s last entry kept no body copy ({body}); enqueue it again with --body-file")
    worktree = pathlib.Path(last["worktree"])
    acceptance = last.get("acceptance_file")
    entry = enqueue_entry(worktree, item, last["title"], body, environ,
                          expected_head=caught_up(worktree, last["expected_head"]),
                          manual=manual or last.get("authority") == "manual", claim=last.get("claim"),
                          acceptance_file=pathlib.Path(acceptance) if acceptance else None, guard=at_expected_head)
    return {**entry, "retried": {"status": last["status"], "finished_at": last.get("finished_at")}}


def position(where: str) -> str:
    """`up`, `down`, `top`, or a 1-based position among the pending entries."""
    if where in PLACES or (where.isdigit() and int(where) >= 1):
        return where
    raise ValueError(f"name up, down, top or a position from 1, not {where!r}")


def move(root: pathlib.Path, item: int, where: str, environ: dict[str, str], *,
         expected_revision: str | None = None) -> dict[str, Any]:
    """Reorder the pending entries; finished entries keep their place as history."""
    where = position(where)

    def reorder(entries: list[dict[str, Any]]) -> dict[str, Any]:
        check_revision(entries, expected_revision)
        row = pending_entry(entries, item)
        slots = [index for index, entry in enumerate(entries) if entry.get("status") == "pending"]
        rows = [entries[index] for index in slots]
        now = rows.index(row)
        target = {"top": 0, "up": now - 1, "down": now + 1}[where] if where in PLACES else int(where) - 1
        rows.insert(max(0, min(target, len(rows) - 1)), rows.pop(now))
        for index, entry in zip(slots, rows, strict=True):
            entries[index] = entry
        return {"item": item, "position": rows.index(row) + 1, "pending": [entry.get("item") for entry in rows]}
    return update(queue_path(root, environ), reorder)


def set_hold(root: pathlib.Path, item: int, environ: dict[str, str], *, held: bool,
             expected_revision: str | None = None) -> dict[str, Any]:
    """Hold a pending entry in place, so the runner and its speculation skip it, or release it."""
    def toggle_hold(entries: list[dict[str, Any]]) -> dict[str, Any]:
        check_revision(entries, expected_revision)
        row = pending_entry(entries, item)
        if bool(row.get("held")) == held:
            raise LaneError(f"sd:{item} is {'already' if held else 'not'} held")
        row.update(held=held, held_at=stamp_now() if held else None)
        return row
    return update(queue_path(root, environ), toggle_hold)


def ship_process(argv: list[str], log: pathlib.Path, timeout: int) -> dict[str, Any]:
    """Run `sd-ship` with `--json`; its whole output goes to `log`, its answer comes back."""
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        done = subprocess.run([sys.executable, str(BIN / "sd-ship"), *argv], capture_output=True, text=True,
                              timeout=timeout, check=False)
        out, err = done.stdout, done.stderr
    except subprocess.TimeoutExpired as error:
        def decoded_output(value: str | bytes | None) -> str:
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        out, err = decoded_output(error.stdout), f"timed out after {timeout} s\n{decoded_output(error.stderr)}"
    log.write_text(f"$ sd-ship {' '.join(argv)}\n{out}\n--- stderr ---\n{err}", encoding="utf-8")
    try:
        answer = json.loads(out)
    except ValueError:
        return {"ok": False, "error": (err or out)[-1500:]}
    return answer if isinstance(answer, dict) else {"ok": False, "error": out[-1500:]}


def default_ship(argv: list[str], log: pathlib.Path) -> dict[str, Any]:
    return ship_process(argv, log, MERGE_SECONDS if "merge" in argv[2:4] else PREPARE_SECONDS)


def default_runner_merge(root: pathlib.Path) -> str:
    """`repo.runner_merge` of the repository `root` is a checkout of, `auto` or `manual` (sd:3132).

    Resolved as `sd-ship`'s `row_merges` resolves it: `registered_for`, then
    the row's remote must name the GitHub repository the origin names. Raises
    `LaneError` with the reason when it cannot tell: no `sd_db`, a database
    that does not answer, no row, a row for another repository, or another
    value. A doubt never reads as `auto`.
    """
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise LaneError(str(imported.problem), code=RUNNER_MERGE_UNKNOWN)
    from sd_db.database import connect, default_path  # noqa: PLC0415
    from sd_db.protection import github_slug  # noqa: PLC0415
    from sd_db.repos import registered_for  # noqa: PLC0415

    origin = lane_git(root, "config", "--get", "remote.origin.url")
    try:
        connection = connect(default_path(), write=False)
    except Exception as error:  # noqa: BLE001 -- every fault is "cannot tell", which merges nothing
        raise LaneError(f"the database did not answer: {error}", code=RUNNER_MERGE_UNKNOWN) from None
    try:
        row = sd_lib.repo_row(connection, registered_for(connection, str(root.resolve()), origin))
        value = row["runner_merge"] if row is not None and "runner_merge" in row.keys() else None
        own = github_slug(origin) if origin else None
        if row is None or own is None or github_slug(row["remote"] or "") != own:
            why = f"no repo row has the remote {origin}"
        elif value not in ("auto", "manual"):
            why = f"the repo row says {value!r}, neither auto nor manual"
        else:
            return str(value)
    except Exception as error:  # noqa: BLE001 -- as above
        why = f"{type(error).__name__}: {error}"
    finally:
        connection.close()
    raise LaneError(why, code=RUNNER_MERGE_UNKNOWN)


def merge_refusal(entry: dict[str, Any]) -> dict[str, str] | None:
    """Why the runner may not merge `entry`, as a code and a reason; None when it may (sd:3132).

    The one authority check: `--manual` on the entry, or `repo.runner_merge`
    `auto` for its repository. `default_runner_merge` is read at the call, so
    a suite can replace it.
    """
    if entry.get("authority") == "manual":
        return None
    try:
        setting = default_runner_merge(pathlib.Path(entry["worktree"]))
    except Exception as error:  # noqa: BLE001 -- an unread setting authorises nothing
        return {"code": RUNNER_MERGE_UNKNOWN,
                "reason": f"repo.runner_merge cannot be read ({error}), and the entry has no --manual; merge by hand"}
    if setting == "auto":
        return None
    return {"code": RUNNER_MERGE_MANUAL, "reason": "repo.runner_merge is manual and the entry has no --manual; "
                                                   "merge by hand"}


def answered_hub_fault(answer: dict[str, Any]) -> bool:
    """Whether `sd-ship` answered with a hub fault, which the next run retries (sd:3239)."""
    return ((answer.get("workflow") or {}).get("blocker") or {}).get("code") == sd_ship_workflow.HUB_UNAVAILABLE


def process(entry: dict[str, Any], logs: pathlib.Path, ship: Ship) -> dict[str, Any]:
    """One entry, start to end; the fields to record on it."""
    worktree, item = pathlib.Path(entry["worktree"]), entry["item"]
    if lane_git(worktree, "rev-parse", "HEAD") != entry["expected_head"]:
        return {"status": "skipped", "reason": "the worktree's HEAD moved from the queued head"}
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    prepare_log = logs / f"prepare-{item}-{stamp}.log"
    claim = [f"--{entry['claim']}"] + (["--acceptance-file", entry["acceptance_file"]] if entry.get("acceptance_file") else [])
    argv = ["-C", str(worktree), "prepare", "--item", str(item), *claim, "--catch-up",
            "--title", entry["title"], "--body-file", entry["body_file"], "--json"]
    prepared = ship(argv, prepare_log)
    # sd:3037. An incomplete review gets the one retry an operator would give it, and no second.
    if ((prepared.get("workflow") or {}).get("blocker") or {}).get("code") == "review_incomplete":
        prepare_log = logs / f"prepare-{item}-{stamp}-retry.log"
        prepared = ship([*argv, "--retry-review"], prepare_log)
    fields: dict[str, Any] = {"prepare_log": str(prepare_log), "head": prepared.get("head")}
    if not (prepared.get("ok") and prepared.get("phase") == "ready_to_send"):
        return {**fields, "status": "failed", "step": "prepare", "phase": prepared.get("phase"),
                "reason": str(prepared.get("error") or prepared.get("code") or "prepare did not reach ready_to_send")[:600],
                **({"hub_fault": True} if answered_hub_fault(prepared) else {})}
    refused = merge_refusal(entry)
    if refused is not None:
        return {**fields, "status": "prepared", **refused}
    merge_log = logs / f"merge-{item}-{stamp}.log"
    merged = ship(["-C", str(worktree), "merge", "--item", str(item), "--expected-head", str(prepared.get("head")),
                   "--manual", "--watch", "--wait-seconds", str(MERGE_WAIT_SECONDS), "--json"], merge_log)
    fields["merge_log"] = str(merge_log)
    if not (merged.get("ok") and merged.get("phase") == "merged"):
        return {**fields, "status": "failed", "step": "merge", "phase": merged.get("phase"),
                "reason": str(merged.get("error") or merged.get("code") or "merge did not confirm")[:600],
                **({"hub_fault": True} if answered_hub_fault(merged) else {})}
    return {**fields, "status": "merged", "merge_commit": merged.get("merge_commit")}


def default_gate(root: pathlib.Path, head: str, base: str) -> dict[str, Any]:
    """`sd gate check`'s run at `head` against `base`, which leaves the receipt prepare reads."""
    import sd_gate_run  # noqa: PLC0415 -- the gate loads only for a speculation
    library = sd_lib.import_sd_db().module
    if library is None:
        raise LaneError("no sd_db library, so a pass would leave no receipt")
    return sd_gate_run.check_in_worktree(root, head, base=base, database=library.default_path(os.environ.get("HOME")),
                                         slot_timeout=sd_lib.GATE_SLOT_SECONDS)


def scratch_git(tree: pathlib.Path, *args: str) -> str | None:
    """`git` for a speculation: stripped stdout, or None on any failure.

    No hook runs, since what a hook does is not what prepare's merge makes.
    It runs through the gate's `gate_git`, whose bound a worktree of the whole
    tree, or a fetch, needs on a loaded machine; `sd_lib`'s 15 s is too short.
    """
    import sd_gate_run  # noqa: PLC0415 -- the gate loads only for a speculation
    try:
        return sd_gate_run.gate_git(tree, "-c", "core.hooksPath=/dev/null", *args)
    except sd_gate_run.GateError:
        return None


def catch_up_in(tree: pathlib.Path, ref: str, message: str) -> bool:
    """Merge `ref` into the scratch worktree's HEAD as `sd-ship prepare --catch-up` does; False on a conflict."""
    if scratch_git(tree, "merge", "--no-ff", "--no-edit", "--no-verify", "-m", message, ref) is not None:
        return True
    scratch_git(tree, "merge", "--abort")
    return False


def predict(entry: dict[str, Any], following: dict[str, Any]) -> dict[str, Any]:
    """`{"head", "base"}` for `following`'s gate once `entry` lands, or `{"skipped": why}`.

    `base` stands in for `entry`'s squash merge: its catch-up merge's tree, as
    a commit on the fetched base branch. `head` is `following`'s catch-up
    merge onto `base`, so its tree is the one `following`'s prepare will gate.
    """
    import sd_gate_receipts  # noqa: PLC0415 -- the declaration reader loads only for a speculation
    root = pathlib.Path(following["worktree"])
    for row, whose in ((entry, f"sd:{entry['item']}'s"), (following, "its")):
        if lane_git(pathlib.Path(row["worktree"]), "rev-parse", "HEAD") != row["expected_head"]:
            return {"skipped": f"{whose} worktree's HEAD moved from the queued head"}
    remote = lane_git(root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD") or ""
    branch = remote.removeprefix("refs/remotes/origin/")
    if not branch or branch == remote:
        return {"skipped": "origin/HEAD names no base branch"}
    if scratch_git(root, "fetch", "--quiet", "--no-tags", "origin", f"refs/heads/{branch}:{remote}") is None:
        return {"skipped": f"origin/{branch} could not be fetched"}
    fork, message = lane_git(root, "rev-parse", "--verify", "--quiet", remote), f"Merge origin/{branch}"
    with tempfile.TemporaryDirectory(prefix="sd-lane-speculate-") as parent:
        tree = pathlib.Path(parent) / "tree"
        if not fork or scratch_git(root, "worktree", "add", "--quiet", "--detach", str(tree), entry["expected_head"]) is None:
            return {"skipped": "the scratch worktree could not be made"}
        try:
            if not catch_up_in(tree, fork, message):
                return {"skipped": f"sd:{entry['item']} conflicts with origin/{branch}"}
            landed = scratch_git(tree, "commit-tree", "HEAD^{tree}", "-p", fork, "-m",
                                 f"sd-ship lane: sd:{entry['item']} as predicted to land")
            if not landed or scratch_git(tree, "checkout", "--quiet", "--detach", following["expected_head"]) is None:
                return {"skipped": "the predicted landing could not be built"}
            if not catch_up_in(tree, landed, message):
                return {"skipped": f"it conflicts with sd:{entry['item']}'s predicted landing"}
            if not sd_gate_receipts.keyed_by_tree(tree):
                return {"skipped": f"no tree key in {sd_gate_receipts.REUSE_DECLARATION}, so prepare could not reuse a pass"}
            head = scratch_git(tree, "rev-parse", "HEAD")
        finally:
            scratch_git(root, "worktree", "remove", "--force", str(tree))
    return {"head": head, "base": landed} if head else {"skipped": "the merged head could not be read"}


def speculate(entry: dict[str, Any], path: pathlib.Path, gate: Gate, busy: bool = False) -> threading.Thread | None:
    """Start the next pending entry's gate on `entry`'s predicted landing; None when no gate started.

    An entry the runner may not merge (`merge_refusal`) stops prepared and
    never lands, so nothing follows it to predict. `busy` says an earlier
    speculative gate still runs; one at a time. What happened goes on the
    next entry as `speculation`, and the gate's whole result to a log beside
    the others.
    """
    following = next((row for row in read_queue(path) if row.get("status") == "pending" and not row.get("held")), None)
    if following is None or merge_refusal(entry) is not None:
        return None

    def record_speculation(fields: dict[str, Any]) -> None:
        def on_follower(entries: list[dict[str, Any]]) -> None:
            for row in entries:
                if row.get("item") == following["item"] and row.get("enqueued_at") == following.get("enqueued_at"):
                    row["speculation"] = {"after": entry["item"], **fields}
        with contextlib.suppress(LaneError, OSError):  # a note that cannot be written stops nothing
            update(path, on_follower)
    try:
        plan = {"skipped": "an earlier speculative gate still runs"} if busy else predict(entry, following)
    except Exception as error:  # a speculation that cannot be set up gates nothing; the lane goes on
        plan = {"skipped": f"{type(error).__name__}: {error}"[:600]}
    if "skipped" in plan:
        record_speculation({"status": "skipped", "reason": plan["skipped"]})
        return None
    log = path.parent.parent / "logs" / f"speculate-{following['item']}-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}.log"
    record_speculation({"status": "running", **plan, "log": str(log)})

    def run_gate() -> None:
        try:
            result = gate(pathlib.Path(following["worktree"]), plan["head"], plan["base"])
            fields = {"status": result.get("status"), "summary": str(result.get("summary"))[:300],
                      "receipt": "recorded" if result.get("receipt_revision") is not None else
                      result.get("receipt_skipped") or result.get("receipt_error") or "none"}
        except Exception as error:
            result = fields = {"status": "error", "reason": f"{type(error).__name__}: {error}"[:600]}
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        record_speculation({**plan, "log": str(log), **fields})
    thread = threading.Thread(target=run_gate, name=f"sd-lane-speculate-{following['item']}")
    thread.start()
    return thread


def default_note(item: int, body: str, main: pathlib.Path) -> str:
    """`sd task note`, run from the main checkout as a person would."""
    done = subprocess.run([sys.executable, str(BIN / "sd"), "task", "note", str(item), "--body", body], cwd=main,
                          capture_output=True, text=True, timeout=120, check=False)
    return "written" if done.returncode == 0 else f"failed: {(done.stderr or done.stdout).strip()[-300:]}"


def clean_up(entry: dict[str, Any], head: str | None, main: pathlib.Path, branch: str,
             tip: str | None) -> tuple[str, str | None]:
    """Delete the merged remote branch; what happened, and the command that removes the worktree and its branch.

    The runner never removes a worktree itself: no lock excludes its builder,
    and a write through a file handle opened before removal reaches an unlinked
    file and is lost. Whoever stops the builder runs the command;
    `git worktree remove` refuses uncommitted or untracked files on its own,
    and `update-ref -d` refuses a branch that moved past the merged head.
    """
    worktree = pathlib.Path(entry["worktree"]).resolve()
    if worktree == main:
        return f"Cleanup skipped: {worktree} is the main checkout", None
    if not branch:
        return "Cleanup skipped: the worktree has no branch checked out", None
    if not tip or tip != head:
        return f"Cleanup skipped: the worktree's tip {tip} is not the merged head {head}", None
    listed = lane_git(main, "ls-remote", "origin", f"refs/heads/{branch}")
    remote = listed.split()[0] if listed else None
    done = []
    if remote == tip:
        deleted = lane_git(main, "push", "-q", f"--force-with-lease=refs/heads/{branch}:{tip}", "origin", "--delete", branch)
        done.append(f"removed origin/{branch}" if deleted is not None else f"origin/{branch} kept: the delete failed")
    elif remote:
        done.append(f"origin/{branch} kept: it is at {remote}, not the merged head")
    remove = f"git -C {main} worktree remove {worktree} && git -C {main} update-ref -d refs/heads/{branch} {tip}"
    done.append(f"worktree {worktree} and branch {branch} kept for removal once the builder stops")
    return "Cleanup: " + ", ".join(done), remove


@contextlib.contextmanager
def lane_root_lock(lanes: pathlib.Path, mode: int) -> Iterator[None]:
    """`flock` the lane root folder itself, made first, so no lane can start outside the lock (sd:3273)."""
    lanes.mkdir(parents=True, exist_ok=True)
    handle = os.open(lanes, os.O_RDONLY)
    try:
        fcntl.flock(handle, mode)
        yield
    finally:
        os.close(handle)


@contextlib.contextmanager
def other_lanes_idle(lanes: pathlib.Path, own: pathlib.Path | None = None) -> Iterator[str | None]:
    """Hold every other lane's runner lock for one step, trying each once; yields the busy lane, or None.

    `own` is the caller's lock, or None for a caller that is no lane: the
    installer's move of the serving tree (sd:3273). The scan finds only the
    runner locks that exist, so it holds the lane root too: a runner checks
    that root once it holds its own lock (`run_lane`), so a lane that starts
    after the scan runs nothing. A runner holds the root only for that check
    and waits on nothing meanwhile, so the wait here is at most that check.
    """
    with contextlib.ExitStack() as held:
        held.enter_context(lane_root_lock(lanes, fcntl.LOCK_EX))
        for lock in sorted(lanes.glob("*/lane/queue/runner.lock")):
            if own is not None and lock.resolve() == own.resolve():
                continue
            handle = held.enter_context(open(lock, "a", encoding="utf-8"))
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield lock.parent.parent.parent.name
                return
        yield None


def fast_forward(main: pathlib.Path, environ: dict[str, str], own_lock: pathlib.Path) -> str:
    """Bring the main checkout to its merged base, never waiting on another lane."""
    branch = lane_git(main, "branch", "--show-current")
    default = (lane_git(main, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") or "").removeprefix("origin/")
    if not branch or branch != (default or branch) or (not default and branch not in ("main", "master")):
        return f"fast-forward skipped: the main checkout is on {branch or 'a detached HEAD'}, not the default branch"
    lane_git(main, "fetch", "-q", "origin")
    # Every lane runs the tools from wherever `sd-ship` resolves; moving that
    # checkout under another lane's running prepare changes its code mid-step.
    guarded = BIN.is_relative_to(main)
    with other_lanes_idle(lane_root(environ), own_lock) if guarded else contextlib.nullcontext() as busy:
        if busy:
            return f"fast-forward skipped: the {busy} lane is running from this checkout; the next landing retries"
        moved = lane_git(main, "merge", "-q", "--ff-only", f"origin/{branch}")
    return (f"fast-forwarded {main} to {lane_git(main, 'rev-parse', '--short', 'HEAD')}" if moved is not None
            else f"fast-forward skipped: git merge --ff-only origin/{branch} failed")


def land(entry: dict[str, Any], outcome: dict[str, Any], environ: dict[str, str], note: Note,
         own_lock: pathlib.Path, root: pathlib.Path) -> dict[str, Any]:
    """After a merge: delete the remote branch, note the item with the removal and recover commands, fast-forward.

    `root` is the repository the lane runs for. `sd-ship merge` removes a clean
    worktree itself (sd:3006), and git cannot name the main checkout from a
    directory that is gone, so the lane's own root answers (sd:3096).
    """
    worktree = pathlib.Path(entry["worktree"])
    gone = not worktree.is_dir()
    main = sd_lib.main_worktree_root(root if gone else worktree).resolve()
    head, merged = outcome.get("head"), str(outcome.get("merge_commit") or "")
    if gone:  # the merge removed the worktree with its branches; nothing is left to clean
        branch, tip = "", None
        cleanup, remove = f"Cleanup: worktree {worktree} was already removed by the merge", None
        fields: dict[str, Any] = {"cleanup": cleanup, "remove": remove}
        body = f"Landed: merged at {merged[:12]} (head {str(head)[:12]}). {cleanup}."
        return land_note(fields, body, entry, environ, note, own_lock, main)
    branch, tip = lane_git(worktree, "branch", "--show-current") or "", lane_git(worktree, "rev-parse", "HEAD")
    cleanup, remove = clean_up(entry, head, main, branch, tip)
    fields = {"cleanup": cleanup, "remove": remove}
    body = f"Landed: merged at {merged[:12]} (head {str(head)[:12]}). {cleanup}."
    if branch and tip:
        body += f" Recover: git branch {branch} {tip}."
    if remove:
        body += f" Remove: {remove}"  # last and bare, so it copies whole
    return land_note(fields, body, entry, environ, note, own_lock, main)


def land_note(fields: dict[str, Any], body: str, entry: dict[str, Any], environ: dict[str, str], note: Note,
              own_lock: pathlib.Path, main: pathlib.Path) -> dict[str, Any]:
    """Note the item from the main checkout, then fast-forward it; both land on `fields`."""
    try:
        fields["note"] = note(entry["item"], body, main)
    except Exception as error:  # the merge stands; the record says the note did not land
        fields["note"] = f"failed: {type(error).__name__}: {error}"[:400]
    fields["fast_forward"] = fast_forward(main, environ, own_lock)
    return fields


def settle(entry: dict[str, Any], outcome: dict[str, Any], environ: dict[str, str], note: Note,
           own_lock: pathlib.Path, root: pathlib.Path) -> dict[str, Any]:
    """What follows an entry's outcome: the landing of a merge."""
    fields: dict[str, Any] = {}
    if outcome.get("status") == "merged":
        try:
            fields.update(land(entry, outcome, environ, note, own_lock, root))
        except Exception as error:  # the merge stands; the entry says what did not follow it
            fields["cleanup"] = f"failed: {type(error).__name__}: {error}"[:600]
    return fields


def lane_host_reason(root: pathlib.Path) -> str | None:
    """Why this machine does not run `root`'s lane, or None on its lane host (sd:3003).

    `sd_lib.lane_elsewhere` reads `repo.lane_host` on a connection opened for
    this read. Without `sd_db` there is no database and no other host. A
    checkout whose origin names no GitHub repository matches no row, so only
    the hub hosts it. A database that does not answer, or rows that disagree,
    raise `lane_unknown`: uncertain ownership never reads as the hub's.
    """
    if sd_lib.import_sd_db().module is None:
        return None
    import sd_gate_receipts  # noqa: PLC0415
    from sd_db.database import connect, default_path  # noqa: PLC0415
    from sd_db.protection import github_slug  # noqa: PLC0415

    try:
        database = default_path()
        found = github_slug(lane_git(sd_lib.main_worktree_root(root), "config", "--get", "remote.origin.url"))
        if found is None:
            served = sd_gate_receipts.served_hub(database)
            return None if served is None else f"The lane for {root.name} runs on the hub {served}, not on this machine."
        connection = connect(database, write=False)
    except Exception as error:  # noqa: BLE001 -- every fault is "cannot tell", which refuses
        raise LaneError(f"Cannot read the lane host for {root}: {error}. Nothing was changed; "
                        "retry when the database answers.", code="lane_unknown") from None
    try:
        return sd_lib.lane_elsewhere(connection, database, "/".join(found))
    except Exception as error:  # noqa: BLE001 -- `LaneUnknown`, or a read fault it did not wrap
        raise LaneError(str(error), code=getattr(error, "code", None) or "lane_unknown") from None
    finally:
        connection.close()


def refuse_elsewhere(root: pathlib.Path) -> None:
    """Refuse a host verb off `root`'s lane host, before it reads or writes the queue (sd:3003)."""
    elsewhere = lane_host_reason(root)
    if elsewhere is not None:
        raise LaneError(elsewhere, code="lane_elsewhere")


def lane_moved(root: pathlib.Path) -> str | None:
    """`lane_host_reason` for a runner between items: a refusal is a reason to stop, never to claim."""
    try:
        return lane_host_reason(root)
    except LaneError as error:
        return str(error)


def runner_alive(pid: Any) -> bool:
    """Whether `pid` may still run; True unless the kernel says no such process, so a doubt keeps the entry."""
    if type(pid) is not int or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:  # EPERM: a process holds the pid
        return True
    return True


def reclaim_dead(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark failed each `running` entry whose runner died (sd:2821); called with the runner lock held.

    Every runner holds that lock while an entry runs, so holding it proves no
    runner is live; the entry's pid must also be gone, which a reused pid only
    makes wait. A pid that cannot be read keeps the entry `running`.
    """
    reclaimed = []
    for row in entries:
        pid = row.get("runner_pid")
        if row.get("status") == "running" and not runner_alive(pid):
            row.update(status="failed", step="runner", finished_at=stamp_now(), reclaimed_by=os.getpid(),
                       reason=f"runner pid {pid} died with the entry running; a merge may have landed, so read "
                              "its logs and pull request before enqueueing it again")
            reclaimed.append({"item": row.get("item"), "runner_pid": pid})
    return reclaimed


def finish_entry(path: pathlib.Path, entry: dict[str, Any], outcome: dict[str, Any]) -> None:
    """Record a run entry's outcome, then drop the item's earlier body copies, and its own unless it is blocked.

    sd:3170 dropped every ended entry's copy; sd:3254 keeps a blocked one's for `retry`.
    """
    def mark_finished(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        earlier = []
        for row in entries:
            if row.get("item") != entry["item"]:
                continue
            if row.get("status") == "running":
                row.update(outcome, finished_at=stamp_now())
            elif row.get("status") != "pending":
                earlier.append(dict(row))
        return earlier
    lane = path.parent.parent
    for row in update(path, mark_finished):  # after the write, as in `cancel`
        drop_body(row, lane)
    if outcome.get("status") not in BLOCKED:
        drop_body(entry, lane)


def caught_up(worktree: pathlib.Path, expected: str) -> str:
    """`expected`, or the worktree's HEAD when that is prepare's catch-up of it: a merge whose first parent it is.

    A retried entry starts there (sd:3239, sd:3254); any other move of HEAD still skips the entry.
    """
    head = lane_git(worktree, "rev-parse", "HEAD")
    if (head and head != expected and lane_git(worktree, "rev-parse", "HEAD^1") == expected
            and lane_git(worktree, "rev-parse", "--verify", "--quiet", "HEAD^2")):
        return head
    return expected


def requeue(path: pathlib.Path, entry: dict[str, Any], outcome: dict[str, Any]) -> bool:
    """Put a running entry back as pending after a hub fault, or False once its retries are spent (sd:3239).

    It keeps its place and its body copy, and `hub_fault` says what failed
    where; a later outcome writes its own fields beside it. Its `expected_head` moves to the
    worktree's HEAD only when that is prepare's catch-up: a merge whose first
    parent is the queued head.
    """
    retries = int(entry.get("hub_retries") or 0)
    if not outcome.pop("hub_fault", False) or retries >= HUB_RETRIES:
        return False
    expected = caught_up(pathlib.Path(entry["worktree"]), entry["expected_head"])
    fault: dict[str, Any] = {key: outcome[key] for key in ("step", "reason", "prepare_log", "merge_log") if key in outcome}

    def put_back(entries: list[dict[str, Any]]) -> None:
        for row in entries:
            if row.get("item") == entry["item"] and row.get("status") == "running":
                for key in ("started_at", "runner_pid"):
                    row.pop(key, None)
                row.update(status="pending", expected_head=expected, hub_retries=retries + 1,
                           hub_fault={**fault, "at": stamp_now()})
    update(path, put_back)
    return True


def run_lane(root: pathlib.Path, environ: dict[str, str], ship: Ship = default_ship,
             gate: Gate = default_gate, note: Note | None = None) -> dict[str, Any]:
    """Drain this repository's queue in order under its lane lock; never wait for the lock.

    One speculative gate runs at a time (`speculate`); after a merge the
    runner lands the entry (`land`), then waits for that gate, so the next
    prepare finds its receipt. `note` defaults to `default_note`, read at the
    call, so a suite can replace it. Off the lane host it refuses before any of
    that (sd:3003). It reads the host again before each claim, under the
    runner lock: after a move it finishes the running entry, claims no next
    one, and says why in `stopped`. After a hub fault it puts the entry back
    and stops the same way (`requeue`, sd:3239). With its lock held it tries
    the lane root once: `other_lanes_idle` holds that root while the serving
    tree or the tools checkout moves, and then the runner runs nothing (sd:3273).
    """
    refuse_elsewhere(root)
    path = queue_path(root, environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    own_lock = path.parent / "runner.lock"
    with open(own_lock, "a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"ran": [], "busy": f"another runner holds {own_lock}"}
        try:
            with lane_root_lock(lane_root(environ), fcntl.LOCK_SH | fcntl.LOCK_NB):
                pass
        except BlockingIOError:
            return {"ran": [], "busy": "the tools this lane runs are moving; the next run retries"}
        reclaimed = update(path, reclaim_dead)
        ran: list[dict[str, Any]] = []
        answer: dict[str, Any] = {"ran": ran, **({"reclaimed": reclaimed} if reclaimed else {})}
        ahead: threading.Thread | None = None
        while True:
            stopped = lane_moved(root)  # sd:3003: a move stops the lane at an item boundary, never mid-merge

            def claim_next(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
                for row in entries:
                    if row.get("status") == "pending" and not row.get("held"):
                        row.update(status="running", started_at=stamp_now(), runner_pid=os.getpid())
                        return dict(row)
                return None
            entry = None if stopped else update(path, claim_next)
            if entry is None:
                if stopped:
                    answer["stopped"] = stopped
                if ahead is not None:
                    ahead.join()
                return answer
            if ahead is not None and ahead.is_alive():
                speculate(entry, path, gate, busy=True)  # notes the skip: one speculative gate at a time
            else:
                ahead = speculate(entry, path, gate)
            try:
                outcome = process(entry, path.parent.parent / "logs", ship)
            except Exception as error:  # a broken entry is marked; the next one still runs
                outcome = {"status": "failed", "reason": f"{type(error).__name__}: {error}"[:600]}
            if requeue(path, entry, outcome):
                ran.append({"item": entry["item"], **outcome, "status": "pending"})
                answer["stopped"] = (f"sd:{entry['item']} met a hub fault in {outcome.get('step')}; "
                                     "it is pending again, and the next run retries it")
                if ahead is not None:
                    ahead.join()
                return answer
            outcome.update(settle(entry, outcome, environ, note or default_note, own_lock, root))
            finish_entry(path, entry, outcome)
            ran.append({"item": entry["item"], **outcome})
            if ahead is not None and outcome.get("status") == "merged":
                ahead.join(PREPARE_SECONDS)  # the next prepare reads its receipt


def run_hosted(environ: dict[str, str], ship: Ship = default_ship, gate: Gate = default_gate,
               note: Note | None = None) -> dict[str, Any]:
    """`lane run --hosted`: `run_lane` for each repository this machine hosts, one after another (sd:3003).

    The same job runs on every machine. Its lanes are the managed `repo` rows,
    in path order, whose checkout is on this disk and whose lane host is this
    machine. Ownership this machine cannot
    read skips that lane with the reason. A held runner lock skips it too
    (`run_lane` answers `busy`), and a refusal in one lane leaves the next to run.
    """
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise LaneError(f"lane run --hosted reads the repo table: {imported.problem}")
    from sd_db.database import connect, default_path  # noqa: PLC0415
    from sd_db.protection import github_slug  # noqa: PLC0415
    from sd_db.repos import registered  # noqa: PLC0415

    database = default_path()
    try:
        connection = connect(database, write=False)
        rows = sd_lib.managed_rows(registered(connection))
    except Exception as error:  # noqa: BLE001 -- no list of lanes is no lane to run
        raise LaneError(f"Cannot read the repositories this machine hosts: {error}. Nothing ran; "
                        "the next run retries.", code="lane_unknown") from None
    lanes: list[dict[str, Any]] = []
    hosted: list[tuple[str, pathlib.Path]] = []
    try:
        for row in rows:
            found, checkout = github_slug(row["remote"]), sd_lib.repo_disk(row["path"])
            if found is None or not (checkout / ".git").exists():
                continue
            try:
                if sd_lib.hosts_lane(connection, database, "/".join(found)):
                    hosted.append((row["path"], checkout))
            except Exception as error:  # noqa: BLE001 -- `LaneUnknown` skips this lane; it never runs as the hub's
                lanes.append({"path": row["path"], "skipped": str(error), "code": getattr(error, "code", "lane_unknown")})
    finally:
        connection.close()  # a lane runs for hours; each reads its host again on its own connection
    for path, checkout in hosted:
        try:
            lanes.append({"path": path, **run_lane(checkout, environ, ship, gate, note)})
        except (LaneError, sd_lib.ConfigError, OSError) as error:
            lanes.append({"path": path, **refusal(error)})
    return {"lanes": lanes}


def gate_ends(root: pathlib.Path, seen: set[str], minutes: int = WATCH_MINUTES) -> list[str]:
    """Each new gate end in a `*.log` under `root` changed in the last `minutes`, once per log state."""
    found, cutoff = [], time.time() - minutes * 60
    for log in sorted(root.rglob("*.log")):
        try:
            stat = log.stat()
            if stat.st_mtime < cutoff:
                continue
            lines = [line for line in log.read_text(encoding="utf-8", errors="replace").splitlines() if GATE_END.search(line)]
        except OSError:
            continue
        key = f"{log}|{stat.st_ino}:{stat.st_size}|{lines[-1] if lines else ''}"
        if lines and key not in seen:
            seen.add(key)
            found.append(f"GATE-END {log.parent.name}/{log.name}: {lines[-1][:140]}")
    return found


def watch(root: pathlib.Path, *, once: bool, write: Callable[[str], Any] = print) -> int:
    seen: set[str] = set()
    while True:
        for line in gate_ends(root, seen):
            write(line)
        if once:
            return 0
        time.sleep(60)


def add_lane_verbs(commands: Any) -> None:
    lane = commands.add_parser("lane", help="a serial ship queue per repository, run under one lock (sd:2524)")
    verbs = lane.add_subparsers(dest="lane_command", required=True)
    adder = verbs.add_parser("enqueue", help="queue this worktree's item for prepare and merge")
    adder.add_argument("--item", type=int, required=True)
    adder.add_argument("--title", required=True)
    adder.add_argument("--body-file", type=pathlib.Path, required=True)
    adder.add_argument("--expected-head", help="the head the worktree must still be at (default: HEAD now)")
    adder.add_argument("--manual", action="store_true",
                       help="authorize the runner to merge when repo.runner_merge is manual; auto needs no flag")
    choice = adder.add_mutually_exclusive_group()
    for claim, text in zip(CLAIMS, ("the item's last pull request, as prepare --deliver",
                                    "an earlier pull request of the item, as prepare --associate-only"), strict=True):
        choice.add_argument(f"--{claim}", dest="claim", action="store_const", const=claim, help=text)
    adder.add_argument("--acceptance-file", type=pathlib.Path, help="forwarded to prepare unchanged")
    verbs.add_parser("list", help="print this repository's queue")
    retrier = verbs.add_parser("retry", help="queue the item's last failed, skipped or prepared entry again, "
                                             "at its head with its kept body (sd:3254)")
    retrier.add_argument("item", type=int)
    retrier.add_argument("--manual", action="store_true",
                         help="authorize the runner to merge when repo.runner_merge is manual, as enqueue --manual")
    retrier.add_argument("--expected-head", help=f"refuse with {STALE_HEAD} unless the item's last entry is at this "
                                                 "full commit id, checked under the queue's lock (sd:3268)")
    canceller = verbs.add_parser("cancel", help="mark a pending entry cancelled")
    canceller.add_argument("item", type=int)
    mover = verbs.add_parser("move", help="move a pending entry; the runner reads the new order at the next item")
    mover.add_argument("item", type=int)
    mover.add_argument("where", type=position, help="up, down, top, or a position from 1 among the pending entries")
    editors = [canceller, mover]
    for name, text in (("hold", "skip a pending entry, keeping its place, until it is released"),
                       ("release", "let a held entry run again")):
        editors.append(verbs.add_parser(name, help=text))
        editors[-1].add_argument("item", type=int)
    for editor in editors:
        editor.add_argument("--expected-revision", help=f"refuse with {STALE_REVISION} unless `lane list` still prints "
                                                        "this revision, checked under the queue's lock")
    runner = verbs.add_parser("run", help="drain the queue in order; exits at once if another runner holds the lane")
    runner.add_argument("--hosted", action="store_true",
                        help="run the lane of each repository this machine hosts, one after another (sd:3003)")
    watcher = verbs.add_parser("watch", help="print each gate end a log under the lane root records, once")
    watcher.add_argument("--once", action="store_true", help="scan once and exit")


def lane_main(args: Any) -> int:
    """The `sd-ship lane` verbs; prints JSON and exits 0, or 3 with the refusal."""
    environ = dict(os.environ)
    try:
        if args.lane_command == "watch":
            return watch(lane_root(environ), once=args.once)
        if args.lane_command == "run" and args.hosted:  # from any folder: it reads the repo table, not the cwd
            return succeed(run_hosted(environ))
        root = sd_lib.repo_root(None)  # a git that gave no answer says why, as a ConfigError (sd:2986)
        if root is None:
            raise LaneError("cwd is not inside a Git repository")
        if args.lane_command in HOST_VERBS:  # no `lane run` drains this machine's queue (sd:2795, sd:3003)
            refuse_elsewhere(root)
        if args.lane_command == "enqueue":
            result: Any = enqueue_entry(root, args.item, args.title, args.body_file, environ,
                                        expected_head=args.expected_head, manual=args.manual, claim=args.claim,
                                        acceptance_file=args.acceptance_file)
        elif args.lane_command == "list":
            path = queue_path(root, environ)
            entries = read_queue(path)
            result = {"queue": str(path), "revision": queue_revision(entries), "entries": entries}
        elif args.lane_command == "retry":
            result = retry(root, args.item, environ, manual=args.manual, expected_head=args.expected_head)
        elif args.lane_command == "cancel":
            result = cancel(root, args.item, environ, expected_revision=args.expected_revision)
        elif args.lane_command == "move":
            result = move(root, args.item, args.where, environ, expected_revision=args.expected_revision)
        elif args.lane_command in ("hold", "release"):
            result = set_hold(root, args.item, environ, held=args.lane_command == "hold",
                              expected_revision=args.expected_revision)
        else:
            result = run_lane(root, environ)
    except (LaneError, sd_lib.ConfigError, OSError) as error:
        print(json.dumps({"ok": False, **refusal(error)}, indent=2, sort_keys=True))
        return 3
    return succeed(result)


def refusal(error: Exception) -> dict[str, Any]:
    """A lane command's refusal: its text, and its code when it has one."""
    code = {"code": error.code} if isinstance(error, LaneError) and error.code else {}
    return {"error": str(error), **code}


def succeed(result: Any) -> int:
    print(json.dumps({"ok": True, **(result if isinstance(result, dict) else {"result": result})}, indent=2,
                     sort_keys=True))
    return 0
