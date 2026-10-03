"""`sd-ship lane`: a serial ship queue per repository that outlives the session that filled it (sd:2524).

An integrator session used to chain `sd-ship prepare` and `merge` by hand, in
shell scripts kept in its scratchpad. The chain died with the session, and a
second chain started beside it raced it. This keeps the chain in a file and
runs it under one lock per repository:

  enqueue  add a worktree, its item, the head it must still be at, a title
           and a body file to the repository's queue;
  list     print the queue;
  cancel   mark a pending entry cancelled;
  run      pop pending entries in order: head check, `prepare --catch-up`,
           then `merge`; a failed entry is marked and the runner goes on;
  watch    print each gate end a lane or builder log records, once.

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

The merge needs authority: an entry merges only when it was enqueued with
`--manual`, which the runner passes on. Without it the runner stops at a
prepared head and marks the entry `prepared`.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterator

import sd_lib

BIN = pathlib.Path(__file__).resolve().parent
ROOT_VARIABLE = "SD_LANE_ROOT"
PREPARE_SECONDS = 3 * 3600
MERGE_SECONDS = 3 * 3600
MERGE_WAIT_SECONDS = 2100
#: The lines a gate writes when it ends: the pack's test runner, `make`'s own
#: failure, and the system repository's check script.
GATE_END = re.compile(r"run-tests: end head=|check\.sh: every suite passed|make: \*\*\*")
WATCH_MINUTES = 3
#: `(argv, log) -> sd-ship's JSON answer`; the log receives the step's whole output.
Ship = Callable[[list[str], pathlib.Path], dict[str, Any]]


class LaneError(RuntimeError):
    """A lane command that cannot do what it was asked; nothing was changed."""


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


def enqueue_entry(worktree: pathlib.Path, item: int, title: str, body_file: pathlib.Path, environ: dict[str, str], *,
            expected_head: str | None = None, manual: bool = False) -> dict[str, Any]:
    """Add one entry; the head defaults to the worktree's, and must name a commit there."""
    worktree = worktree.resolve()
    head = lane_git(worktree, "rev-parse", "--verify", "--quiet", f"{expected_head or 'HEAD'}^{{commit}}")
    if not head:
        raise LaneError(f"{expected_head or 'HEAD'} names no commit in {worktree}")
    if not body_file.is_file():
        raise LaneError(f"the body file {body_file} does not exist")
    entry = {"worktree": str(worktree), "item": item, "expected_head": head, "title": title,
             "body_file": str(body_file.resolve()), "authority": "manual" if manual else None,
             "status": "pending", "enqueued_at": stamp_now()}

    def add_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
        if any(row.get("item") == item and row.get("status") in ("pending", "running") for row in entries):
            raise LaneError(f"sd:{item} is already queued in this lane")
        entries.append(entry)
        return entry
    return update(queue_path(worktree, environ), add_entry)


def cancel(root: pathlib.Path, item: int, environ: dict[str, str]) -> dict[str, Any]:
    def mark(entries: list[dict[str, Any]]) -> dict[str, Any]:
        for row in entries:
            if row.get("item") == item and row.get("status") == "pending":
                row.update(status="cancelled", finished_at=stamp_now())
                return row
        raise LaneError(f"sd:{item} has no pending entry in this lane")
    return update(queue_path(root, environ), mark)


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


def process(entry: dict[str, Any], logs: pathlib.Path, ship: Ship) -> dict[str, Any]:
    """One entry, start to end; the fields to record on it."""
    worktree, item = pathlib.Path(entry["worktree"]), entry["item"]
    if lane_git(worktree, "rev-parse", "HEAD") != entry["expected_head"]:
        return {"status": "skipped", "reason": "the worktree's HEAD moved from the queued head"}
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    prepare_log = logs / f"prepare-{item}-{stamp}.log"
    prepared = ship(["-C", str(worktree), "prepare", "--item", str(item), "--deliver", "--catch-up",
                     "--title", entry["title"], "--body-file", entry["body_file"], "--json"], prepare_log)
    fields: dict[str, Any] = {"prepare_log": str(prepare_log), "head": prepared.get("head")}
    if not (prepared.get("ok") and prepared.get("phase") == "ready_to_send"):
        return {**fields, "status": "failed", "step": "prepare", "phase": prepared.get("phase"),
                "reason": str(prepared.get("error") or prepared.get("code") or "prepare did not reach ready_to_send")[:600]}
    if entry.get("authority") != "manual":
        return {**fields, "status": "prepared", "reason": "queued without --manual; merge by hand"}
    merge_log = logs / f"merge-{item}-{stamp}.log"
    merged = ship(["-C", str(worktree), "merge", "--item", str(item), "--expected-head", str(prepared.get("head")),
                   "--manual", "--watch", "--wait-seconds", str(MERGE_WAIT_SECONDS), "--json"], merge_log)
    fields["merge_log"] = str(merge_log)
    if not (merged.get("ok") and merged.get("phase") == "merged"):
        return {**fields, "status": "failed", "step": "merge", "phase": merged.get("phase"),
                "reason": str(merged.get("error") or merged.get("code") or "merge did not confirm")[:600]}
    return {**fields, "status": "merged", "merge_commit": merged.get("merge_commit")}


def run_lane(root: pathlib.Path, environ: dict[str, str], ship: Ship = default_ship) -> dict[str, Any]:
    """Drain this repository's queue in order under its lane lock; never wait for the lock."""
    path = queue_path(root, environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.parent / "runner.lock", "a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"ran": [], "busy": f"another runner holds {path.parent / 'runner.lock'}"}
        ran: list[dict[str, Any]] = []
        while True:
            def claim_next(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
                for row in entries:
                    if row.get("status") == "pending":
                        row.update(status="running", started_at=stamp_now(), runner_pid=os.getpid())
                        return dict(row)
                return None
            entry = update(path, claim_next)
            if entry is None:
                return {"ran": ran}
            try:
                outcome = process(entry, path.parent.parent / "logs", ship)
            except Exception as error:  # a broken entry is marked; the next one still runs
                outcome = {"status": "failed", "reason": f"{type(error).__name__}: {error}"[:600]}

            def finish(entries: list[dict[str, Any]], entry=entry, outcome=outcome) -> None:
                for row in entries:
                    if row.get("item") == entry["item"] and row.get("status") == "running":
                        row.update(outcome, finished_at=stamp_now())
            update(path, finish)
            ran.append({"item": entry["item"], **outcome})


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
    adder.add_argument("--manual", action="store_true", help="authorize the runner to merge with sd-ship merge --manual")
    verbs.add_parser("list", help="print this repository's queue")
    canceller = verbs.add_parser("cancel", help="mark a pending entry cancelled")
    canceller.add_argument("item", type=int)
    verbs.add_parser("run", help="drain the queue in order; exits at once if another runner holds the lane")
    watcher = verbs.add_parser("watch", help="print each gate end a log under the lane root records, once")
    watcher.add_argument("--once", action="store_true", help="scan once and exit")


def lane_main(args: Any) -> int:
    """The `sd-ship lane` verbs; prints JSON and exits 0, or 3 with the refusal."""
    environ = dict(os.environ)
    root = sd_lib.repo_root(None)
    try:
        if args.lane_command == "watch":
            return watch(lane_root(environ), once=args.once)
        if root is None:
            raise LaneError("cwd is not inside a Git repository")
        if args.lane_command == "enqueue":
            result: Any = enqueue_entry(root, args.item, args.title, args.body_file, environ,
                                  expected_head=args.expected_head, manual=args.manual)
        elif args.lane_command == "list":
            path = queue_path(root, environ)
            result = {"queue": str(path), "entries": read_queue(path)}
        elif args.lane_command == "cancel":
            result = cancel(root, args.item, environ)
        else:
            result = run_lane(root, environ)
    except (LaneError, sd_lib.ConfigError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, **(result if isinstance(result, dict) else {"result": result})}, indent=2,
                     sort_keys=True))
    return 0
