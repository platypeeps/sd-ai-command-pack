"""`sd-ship lane`: a serial ship queue per repository that outlives the session that filled it (sd:2524).

An integrator session used to chain `sd-ship prepare` and `merge` by hand, in
shell scripts kept in its scratchpad. The chain died with the session, and a
second chain started beside it raced it. This keeps the chain in a file and
runs it under one lock per repository:

  enqueue  add a worktree, its item, the head it must still be at, a title
           and a body file to the repository's queue;
  list     print the queue;
  cancel   mark a pending entry cancelled;
  move     put a pending entry up, down, on top or at a position (sd:2584);
  hold     keep a pending entry in place but skip it; `release` ends that;
  run      take the queue's first pending entry that is not held, read again
           before each item: head check, `prepare --catch-up`,
           then `merge`; a failed entry is marked and the runner goes on.
           While one entry ships, the next one's gate runs on its predicted
           landing (sd:2586, below). After a merge it deletes the remote
           branch, notes the item with the worktree's removal command and
           fast-forwards the main checkout (sd:2568, below);
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

The merge needs authority: an entry merges only when it was enqueued with
`--manual`, which the runner passes on. Without it the runner stops at a
prepared head and marks the entry `prepared`.

The next entry's gate runs early (sd:2586). Its prepare used to start only
after the entry ahead merged, then catch up and gate for 10 to 20 minutes.
When the runner claims an entry that may merge, it predicts the landing: the
entry's catch-up merge of the fetched base branch, as a commit on that base.
It merges the next entry onto that commit as prepare's catch-up would,
CHANGELOG resolver included, in a scratch worktree, and runs `sd gate check`'s
gate there in the background. The real landing is another commit with the
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
branch` recover command and that command. Then it fast-forwards the main
checkout. When that checkout holds the running `sd-ship`, as the pack's does
for every lane, it tries each other lane's runner lock once and skips if one
is held: a lane mid-prepare must not have its tools change under it, and no
lane waits on another's lock. The next landing retries.
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
import threading
import time
from typing import Any, Callable, Iterator

import sd_changelog_merge
import sd_lib

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
#: `(argv, log) -> sd-ship's JSON answer`; the log receives the step's whole output.
Ship = Callable[[list[str], pathlib.Path], dict[str, Any]]
#: `(root, head, base) -> the gate's result`: the next entry's gate on a predicted landing (sd:2586).
Gate = Callable[[pathlib.Path, str, str], dict[str, Any]]
#: `(item, body, main checkout) -> what happened`: the landing's item note (sd:2568).
Note = Callable[[int, str, pathlib.Path], str]


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
                  expected_head: str | None = None, manual: bool = False, claim: str | None = None,
                  acceptance_file: pathlib.Path | None = None) -> dict[str, Any]:
    """Add one entry; the head defaults to the worktree's, and must name a commit there.

    `claim` is prepare's delivery choice, `deliver` or `associate-only`, and
    is refused when absent as prepare refuses it; it and `acceptance_file`
    reach prepare unchanged.
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
    entry = {"worktree": str(worktree), "item": item, "expected_head": head, "title": title,
             "body_file": str(body_file.resolve()), "authority": "manual" if manual else None, "claim": claim,
             "acceptance_file": str(acceptance_file.resolve()) if acceptance_file else None,
             "status": "pending", "enqueued_at": stamp_now()}

    def add_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
        if any(row.get("item") == item and row.get("status") in ("pending", "running") for row in entries):
            raise LaneError(f"sd:{item} is already queued in this lane")
        entries.append(entry)
        return entry
    return update(queue_path(worktree, environ), add_entry)


def pending_entry(entries: list[dict[str, Any]], item: int) -> dict[str, Any]:
    for row in entries:
        if row.get("item") == item and row.get("status") == "pending":
            return row
    if any(row.get("item") == item and row.get("status") == "running" for row in entries):
        raise LaneError(f"sd:{item} is running; the queue changes only between items")
    raise LaneError(f"sd:{item} has no pending entry in this lane")


def cancel(root: pathlib.Path, item: int, environ: dict[str, str]) -> dict[str, Any]:
    def mark(entries: list[dict[str, Any]]) -> dict[str, Any]:
        row = pending_entry(entries, item)
        row.update(status="cancelled", finished_at=stamp_now())
        return row
    return update(queue_path(root, environ), mark)


def position(where: str) -> str:
    """`up`, `down`, `top`, or a 1-based position among the pending entries."""
    if where in PLACES or (where.isdigit() and int(where) >= 1):
        return where
    raise ValueError(f"name up, down, top or a position from 1, not {where!r}")


def move(root: pathlib.Path, item: int, where: str, environ: dict[str, str]) -> dict[str, Any]:
    """Reorder the pending entries; finished entries keep their place as history."""
    where = position(where)

    def reorder(entries: list[dict[str, Any]]) -> dict[str, Any]:
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


def set_hold(root: pathlib.Path, item: int, environ: dict[str, str], *, held: bool) -> dict[str, Any]:
    """Hold a pending entry in place, so the runner and its speculation skip it, or release it."""
    def toggle_hold(entries: list[dict[str, Any]]) -> dict[str, Any]:
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


def process(entry: dict[str, Any], logs: pathlib.Path, ship: Ship) -> dict[str, Any]:
    """One entry, start to end; the fields to record on it."""
    worktree, item = pathlib.Path(entry["worktree"]), entry["item"]
    if lane_git(worktree, "rev-parse", "HEAD") != entry["expected_head"]:
        return {"status": "skipped", "reason": "the worktree's HEAD moved from the queued head"}
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    prepare_log = logs / f"prepare-{item}-{stamp}.log"
    claim = [f"--{entry['claim']}"] + (["--acceptance-file", entry["acceptance_file"]] if entry.get("acceptance_file") else [])
    prepared = ship(["-C", str(worktree), "prepare", "--item", str(item), *claim, "--catch-up",
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
    if sd_changelog_merge.resolve_keep_both(tree) and scratch_git(tree, "commit", "--quiet", "--no-verify", "-m", message) is not None:
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

    An entry queued without `--manual` stops prepared and never lands, so
    nothing follows it to predict. `busy` says an earlier speculative gate
    still runs; one at a time. What happened goes on the next entry as
    `speculation`, and the gate's whole result to a log beside the others.
    """
    following = next((row for row in read_queue(path) if row.get("status") == "pending" and not row.get("held")), None)
    if entry.get("authority") != "manual" or following is None:
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
def other_lanes_idle(lanes: pathlib.Path, own: pathlib.Path) -> Iterator[str | None]:
    """Hold every other lane's runner lock for one step, trying each once; yields the busy lane, or None."""
    with contextlib.ExitStack() as held:
        for lock in sorted(lanes.glob("*/lane/queue/runner.lock")):
            if lock.resolve() == own.resolve():
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
         own_lock: pathlib.Path) -> dict[str, Any]:
    """After a merge: delete the remote branch, note the item with the removal and recover commands, fast-forward."""
    worktree = pathlib.Path(entry["worktree"])
    main = sd_lib.main_worktree_root(worktree).resolve()
    head, merged = outcome.get("head"), str(outcome.get("merge_commit") or "")
    branch = lane_git(worktree, "branch", "--show-current") or ""
    tip = lane_git(worktree, "rev-parse", "HEAD")
    cleanup, remove = clean_up(entry, head, main, branch, tip)
    fields: dict[str, Any] = {"cleanup": cleanup, "remove": remove}
    body = f"Landed: merged at {merged[:12]} (head {str(head)[:12]}). {cleanup}."
    if branch and tip:
        body += f" Recover: git branch {branch} {tip}."
    if remove:
        body += f" Remove: {remove}"  # last and bare, so it copies whole
    try:
        fields["note"] = note(entry["item"], body, main)
    except Exception as error:  # the merge stands; the record says the note did not land
        fields["note"] = f"failed: {type(error).__name__}: {error}"[:400]
    fields["fast_forward"] = fast_forward(main, environ, own_lock)
    return fields


def run_lane(root: pathlib.Path, environ: dict[str, str], ship: Ship = default_ship,
             gate: Gate = default_gate, note: Note | None = None) -> dict[str, Any]:
    """Drain this repository's queue in order under its lane lock; never wait for the lock.

    One speculative gate runs at a time (`speculate`); after a merge the
    runner lands the entry (`land`), then waits for that gate, so the next
    prepare finds its receipt. `note` defaults to `default_note`, read at the
    call, so a suite can replace it.
    """
    path = queue_path(root, environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    own_lock = path.parent / "runner.lock"
    with open(own_lock, "a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"ran": [], "busy": f"another runner holds {own_lock}"}
        ran: list[dict[str, Any]] = []
        ahead: threading.Thread | None = None
        while True:
            def claim_next(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
                for row in entries:
                    if row.get("status") == "pending" and not row.get("held"):
                        row.update(status="running", started_at=stamp_now(), runner_pid=os.getpid())
                        return dict(row)
                return None
            entry = update(path, claim_next)
            if entry is None:
                if ahead is not None:
                    ahead.join()
                return {"ran": ran}
            if ahead is not None and ahead.is_alive():
                speculate(entry, path, gate, busy=True)  # notes the skip: one speculative gate at a time
            else:
                ahead = speculate(entry, path, gate)
            try:
                outcome = process(entry, path.parent.parent / "logs", ship)
            except Exception as error:  # a broken entry is marked; the next one still runs
                outcome = {"status": "failed", "reason": f"{type(error).__name__}: {error}"[:600]}
            if outcome.get("status") == "merged":
                try:
                    outcome.update(land(entry, outcome, environ, note or default_note, own_lock))
                except Exception as error:  # the merge stands; the entry says what did not follow it
                    outcome["cleanup"] = f"failed: {type(error).__name__}: {error}"[:600]

            def finish(entries: list[dict[str, Any]], entry=entry, outcome=outcome) -> None:
                for row in entries:
                    if row.get("item") == entry["item"] and row.get("status") == "running":
                        row.update(outcome, finished_at=stamp_now())
            update(path, finish)
            ran.append({"item": entry["item"], **outcome})
            if ahead is not None and outcome.get("status") == "merged":
                ahead.join(PREPARE_SECONDS)  # the next prepare reads its receipt


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
    choice = adder.add_mutually_exclusive_group()
    for claim, text in zip(CLAIMS, ("the item's last pull request, as prepare --deliver",
                                    "an earlier pull request of the item, as prepare --associate-only"), strict=True):
        choice.add_argument(f"--{claim}", dest="claim", action="store_const", const=claim, help=text)
    adder.add_argument("--acceptance-file", type=pathlib.Path, help="forwarded to prepare unchanged")
    verbs.add_parser("list", help="print this repository's queue")
    canceller = verbs.add_parser("cancel", help="mark a pending entry cancelled")
    canceller.add_argument("item", type=int)
    mover = verbs.add_parser("move", help="move a pending entry; the runner reads the new order at the next item")
    mover.add_argument("item", type=int)
    mover.add_argument("where", type=position, help="up, down, top, or a position from 1 among the pending entries")
    for name, text in (("hold", "skip a pending entry, keeping its place, until it is released"),
                       ("release", "let a held entry run again")):
        verbs.add_parser(name, help=text).add_argument("item", type=int)
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
                                        expected_head=args.expected_head, manual=args.manual, claim=args.claim,
                                        acceptance_file=args.acceptance_file)
        elif args.lane_command == "list":
            path = queue_path(root, environ)
            result = {"queue": str(path), "entries": read_queue(path)}
        elif args.lane_command == "cancel":
            result = cancel(root, args.item, environ)
        elif args.lane_command == "move":
            result = move(root, args.item, args.where, environ)
        elif args.lane_command in ("hold", "release"):
            result = set_hold(root, args.item, environ, held=args.lane_command == "hold")
        else:
            result = run_lane(root, environ)
    except (LaneError, sd_lib.ConfigError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, **(result if isinstance(result, dict) else {"result": result})}, indent=2,
                     sort_keys=True))
    return 0
