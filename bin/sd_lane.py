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
           these three take `--expected-revision`, the `revision` `list`
           prints, and refuse a queue that changed since (sd:2717);
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
           (sd:2821);
  watch    print each gate end a lane or builder log records, once;
  request  on a satellite: ask the hub's lane to merge an item the satellite
           gated and prepared, through a row in the workflow database (sd:2704).

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
lane waits on another's lock. The next landing retries.

A satellite gates on its own machine and asks the hub to merge (sd:2704).
`lane request` writes `lane-request:v1:<slug>:<item>` over the wire. Before
each claim the runner takes in this repository's requests (`intake`). It
first looks for an entry that names the request's revision: one is there when
the row's `queued` write failed, and a finished one gives the row its outcome.
The runner claims a satellite entry only while the request's newest revision
is the `queued` write naming it, so a failed write or a newer request keeps it.
It then refuses a request the repository did not opt into, one whose branch
or head is malformed, and one whose `ship:` row is not `ready_to_send` at its
head; it supersedes the item's pending entry, leaves a request whose item is
running for the next intake, and adds a `gate: satellite` entry, the queue
before the row. A `queued` row whose entry finished gets the outcome a failed
write left out. A satellite entry runs no prepare and no catch-up: the
runner fetches the branch and the base, hands the entry back when the branch
moved or the head lacks the base, and merges with `--satellite-gate`, which
accepts the satellite's receipt under the trust rule in `sd_local_gate`
instead of a gate on the hub. A request without `--manual` stops there as
`prepared`, as a hub entry queued without it does. Its outcome goes back to
the request row, and a hand-back or failure notes the item, with the trust
rule's next action for its code. `lane run --satellite-only` claims satellite
entries only, starts no speculative gate, and exits when none is pending; a
scheduled job on the hub runs it until every job runs `--hosted`. Each hub run
publishes the hub's pack digest to `sd-lane-pack:v1:<slug>` at its start and
after a fast-forward of the pack checkout.

Only a repository's lane host drains its queue (sd:3003): the machine
`repo.lane_host` names, or the hub when it is NULL. Elsewhere `run`,
`enqueue`, `move`, `hold` and `release` refuse with `lane_elsewhere`, and a
host that cannot be read refuses with `lane_unknown`. The runner reads the
host again before each claim, so a move stops it at the next item. The same
scheduled job runs on every machine: `lane run --hosted` runs each lane this
machine hosts, one after another, and skips one whose runner is busy.
"""

from __future__ import annotations

import contextlib
import dataclasses
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Iterator

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
#: The verbs that fill or reorder a queue only its lane host drains; off the host they refuse (sd:2795, sd:3003).
#: `list` and `cancel` still answer there, so an old host's pending entries can be read and cancelled after a move.
HOST_VERBS = ("enqueue", "move", "hold", "release")
#: `(argv, log) -> sd-ship's JSON answer`; the log receives the step's whole output.
Ship = Callable[[list[str], pathlib.Path], dict[str, Any]]
#: `(root, head, base) -> the gate's result`: the next entry's gate on a predicted landing (sd:2586).
Gate = Callable[[pathlib.Path, str, str], dict[str, Any]]
#: `(item, body, main checkout) -> what happened`: the landing's item note (sd:2568).
Note = Callable[[int, str, pathlib.Path], str]
#: An entry's `gate` when a satellite gated it and asked for the merge (sd:2704).
SATELLITE = "satellite"
#: The request row a satellite writes, one per repository and item; `<slug>:<item>` follows.
REQUEST_PREFIX = "lane-request:v1:"
REQUEST_WRITER = "sd-lane-request"
#: What a refused request's row says to do, by refusal code.
REFUSAL_ACTIONS = {
    "satellite_gate_off": "Opt the repository in on the hub with sd-db.sh repo satellite-gate <path> accept, "
                          "or ship the item from the hub with sd-ship lane enqueue.",
    "invalid_request": "Request again from the item's worktree with sd-ship lane request.",
    "satellite_not_prepared": "On the satellite: sd-ship prepare at the pushed head, then sd-ship lane request again.",
}
COMMIT_ID = re.compile(r"[0-9a-f]{40}")
#: `sd_db.ship.HELD`: the merge met another live ship operation's repository lock, which passes (sd:2861).
LOCK_HELD = "another ship operation owns this repository"
#: How many runs a satellite entry waits out a held lock before it fails; the scheduled run comes every 5 minutes.
LOCK_RETRIES = 12


@dataclasses.dataclass(frozen=True)
class Hub:
    """The lane's rows in the workflow database: the hub's connection, `sd_db.ship`, the lane's slug and main checkout."""

    connection: Any
    store: Any
    slug: str
    main: pathlib.Path


class LaneError(RuntimeError):
    """A lane command that cannot do what it was asked; nothing was changed. `code` is a stable refusal name, or None."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


#: The refusal code of a move, hold or release whose `--expected-revision` no longer matches (sd:2717).
STALE_REVISION = "stale_revision"


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


def request_key(slug: str, item: int) -> str:
    return f"{REQUEST_PREFIX}{slug}:{item}"


def request(root: pathlib.Path, item: int, *, manual: bool, database: pathlib.Path | None = None) -> dict[str, Any]:
    """`lane request` on a satellite: write the item's request row for the hub's lane (sd:2704).

    Refused on the hub, where `lane enqueue` queues the item; for a lane the
    hub does not host, since only the hub's run takes requests in (sd:3003);
    and for an item whose `ship:` row is not `ready_to_send` at the branch's
    pushed head, which intake would refuse.
    """
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise LaneError(str(imported.problem))
    import sd_gate_receipts  # noqa: PLC0415
    from sd_db import ship as store  # noqa: PLC0415
    from sd_db.database import connect, default_path  # noqa: PLC0415
    from sd_db.errors import SdDbError  # noqa: PLC0415 -- a revision conflict is one
    from sd_ship_remote import Refusal, slug  # noqa: PLC0415

    database = database or default_path()
    hub = sd_gate_receipts.served_hub(database)
    if not hub:
        raise LaneError("this machine is the sd hub: a request asks the hub to merge what a satellite gated; "
                        "queue a hub item with sd-ship lane enqueue", code="hub_request")
    try:
        own = slug(lane_git(root, "config", "--get", "remote.origin.url") or "")
    except Refusal as error:
        raise LaneError(str(error)) from None
    branch = lane_git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        raise LaneError(f"{root} has no branch checked out; request from the item's worktree")
    listed = lane_git(root, "ls-remote", "origin", f"refs/heads/{branch}")
    pushed = listed.split()[0] if listed else None
    try:
        connection = connect(database)
    except SdDbError as error:
        raise LaneError(f"the hub {hub} did not answer, so no request was written; rerun once it does: {error}") from None
    try:
        refuse_unhosted(connection, database, own)
        _, shipped = store.read(connection, store.receipt_key(own, branch, item))
        if shipped.get("phase") != "ready_to_send" or not pushed or shipped.get("head") != pushed:
            raise LaneError(f"sd:{item} is not ready_to_send at the pushed head of {branch} ({str(pushed)[:12]}); "
                            f"{REFUSAL_ACTIONS['satellite_not_prepared']}", code="satellite_not_prepared")
        key = request_key(own, item)
        revision, _ = store.read(connection, key)
        value = {"writer": REQUEST_WRITER, "repository": own, "item": item, "branch": branch, "head": pushed,
                 "base": shipped.get("base"), "authority": "manual" if manual else None,
                 "satellite": sd_gate_receipts.satellite_identity(), "requested_at": stamp_now(), "status": "requested"}
        written = store.save(connection, key, revision, value)
    except SdDbError as error:
        raise LaneError(f"the request was not written to the hub {hub}; rerun sd-ship lane request: {error}") from None
    finally:
        connection.close()
    return {"request": key, "revision": written, **value}


def refuse_unhosted(connection: Any, database: pathlib.Path, own: str) -> None:
    """Refuse a request no run would take in: only the hub's run reads request rows (`default_hub`)."""
    try:
        elsewhere = sd_lib.lane_elsewhere(connection, database, own)
        host, _ = sd_lib.lane_host(connection, own)
    except Exception as error:  # noqa: BLE001 -- `LaneUnknown`, or a read fault it did not wrap
        raise LaneError(str(error), code=getattr(error, "code", None) or "lane_unknown") from None
    if elsewhere is None:
        raise LaneError(f"The lane for {own} runs on this machine, not on the hub, so no run would take a "
                        "request in. Queue the item here with sd-ship lane enqueue.", code="lane_elsewhere")
    if host is not None:
        raise LaneError(f"{elsewhere}\nNo run there takes a request in: queue the item on {host} with "
                        "sd-ship lane enqueue.", code="lane_elsewhere")


def requests(hub: Hub) -> list[tuple[str, int, dict[str, Any]]]:
    """This lane's request rows whose newest revision is `requested` or `queued`, oldest first."""
    prefix = f"{REQUEST_PREFIX}{hub.slug}:"
    keys = hub.connection.execute("SELECT DISTINCT key FROM state WHERE kind = 'checkpoint' AND substr(key, 1, ?) = ?",
                                  (len(prefix), prefix)).fetchall()
    found = []
    for (key,) in keys:
        try:
            revision, row = hub.store.read(hub.connection, key)
        except Exception:  # an unreadable row is not a request; nothing here can repair it
            continue
        if row.get("status") in ("requested", "queued"):
            found.append((key, revision, row))
    return sorted(found, key=lambda request: request[1])


def git_name(main: pathlib.Path, name: Any) -> bool:
    """A branch name `git` accepts as given and no option can hide in."""
    return (isinstance(name, str) and bool(name) and not name.startswith("-")
            and lane_git(main, "check-ref-format", "--branch", name) == name)


def malformed(hub: Hub, key: str, row: dict[str, Any]) -> str | None:
    """Why a request cannot be taken in as written, or None. Its branch and base reach `git` argv on the hub."""
    import sd_gate_receipts  # noqa: PLC0415

    item, head = row.get("item"), row.get("head")
    if row.get("writer") != REQUEST_WRITER or not sd_gate_receipts.names_node(row.get("satellite")):
        return f"the request is not a {REQUEST_WRITER} row from a satellite named by host, tailnet login and address"
    if type(item) is not int or key != request_key(hub.slug, item) or row.get("repository") != hub.slug:
        return "the request's item or repository does not match its key"
    if not git_name(hub.main, row.get("branch")) or not git_name(hub.main, row.get("base")):
        return "the request's branch or base is not a branch name"
    if not (isinstance(head, str) and COMMIT_ID.fullmatch(head)):
        return "the request's head is not a full commit id"
    if row.get("authority") not in (None, "manual"):
        return "the request's authority is neither manual nor none"
    return None


def take_in(hub: Hub, path: pathlib.Path, key: str, revision: int, row: dict[str, Any]) -> dict[str, Any]:
    """One request through intake's six steps (design.md, "Intake"); what happened."""
    def answer(status: str, **fields: Any) -> dict[str, Any]:
        hub.store.save(hub.connection, key, revision, {**row, "status": status, "decided_at": stamp_now(), **fields})
        return {"request": key, "revision": revision, "status": status, **fields}

    def refuse(code: str, reason: str) -> dict[str, Any]:
        return answer("refused", code=code, reason=reason, next_action=REFUSAL_ACTIONS[code])
    taken = {"key": key, "revision": revision}
    # Step 4 first: an entry naming this revision means its `queued` write failed. It may have run since,
    # and its merge moved the ship: row on, so the checks below would misjudge it (review round 1).
    found = next((entry for entry in read_queue(path) if entry.get("request") == taken), None)
    if found is not None and found.get("status") in ("pending", "running"):
        return answer("queued", entry={"enqueued_at": found.get("enqueued_at"), "revision": revision})
    if found is not None:
        return answer(str(found["status"]), **outcome_fields(found))
    if sd_lib.repo_ci(hub.connection, hub.main) != "local" or sd_lib.repo_satellite_gate(hub.connection, hub.main) != "accept":
        return refuse("satellite_gate_off", "the repository does not take satellite gates: "
                                            "repo.ci must be local and repo.satellite_gate accept")
    why = malformed(hub, key, row)
    if why:
        return refuse("invalid_request", why)
    item, branch, head = row["item"], row["branch"], row["head"]
    _, shipped = hub.store.read(hub.connection, hub.store.receipt_key(hub.slug, branch, item))
    if shipped.get("phase") != "ready_to_send" or shipped.get("head") != head:
        return refuse("satellite_not_prepared", f"the ship: row for {branch} is {shipped.get('phase') or 'absent'} "
                                                f"at {str(shipped.get('head'))[:12]}, not ready_to_send at {head[:12]}")
    if shipped.get("base") != row["base"]:  # the merge would check the ship: row's base, not the one intake pre-checked
        return refuse("invalid_request", f"the request's base {row['base']} is not the ship: row's {shipped.get('base')}")

    def queue_request(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
        if any(entry.get("item") == item and entry.get("status") == "running" for entry in entries):
            return None
        for entry in entries:
            if entry.get("item") == item and entry.get("status") == "pending":
                entry.update(status="cancelled", finished_at=stamp_now(), superseded_by=taken)
        entry = {"worktree": str(hub.main), "item": item, "gate": SATELLITE, "branch": branch, "base": row["base"],
                 "expected_head": head, "title": shipped.get("title"), "authority": row.get("authority"),
                 "request": taken, "status": "pending", "enqueued_at": stamp_now()}
        entries.append(entry)
        return entry
    entry = update(path, queue_request)
    if entry is None:
        return {"request": key, "revision": revision, "status": "requested",
                "reason": f"sd:{item} is running; the next intake takes the request in"}
    # A failed write leaves the entry unclaimable (`claimable`): the next intake writes `queued` (step 4),
    # or a newer request supersedes it (step 5).
    return answer("queued", entry={"enqueued_at": entry["enqueued_at"], "revision": revision})


def intake(hub: Hub, path: pathlib.Path) -> list[dict[str, Any]]:
    """Take this lane's requests in, oldest first; a request that cannot be decided now waits for the next intake.

    A `queued` row whose entry finished gets the outcome a failed `write_outcome` left unwritten (review round 2).
    """
    done: list[dict[str, Any]] = []
    try:
        found, entries = requests(hub), read_queue(path)
    except Exception as error:  # the database would not answer; hub entries still run, and the next intake reads again
        return [{"status": "unread", "error": f"{type(error).__name__}: {error}"[:300]}]
    for key, revision, row in found:
        try:
            if row["status"] == "requested":
                done.append(take_in(hub, path, key, revision, row))
                continue
            taken = {"key": key, "revision": entry_revision(row)}
            finished = next((entry for entry in entries if entry.get("request") == taken
                             and entry.get("status") not in ("pending", "running")), None)
            if finished is not None:
                done.append({"request": key, "status": finished["status"],
                             "request_row": write_outcome(hub, finished, finished)})
        except Exception as error:  # e.g. the row changed under intake: its newest revision is read again next time
            done.append({"request": key, "revision": revision, "status": row.get("status"),
                         "error": f"{type(error).__name__}: {error}"[:300]})
    return done


def outcome_fields(outcome: dict[str, Any]) -> dict[str, Any]:
    """What a request row keeps of its entry's outcome."""
    return {name: outcome.get(name) for name in ("code", "reason", "next_action", "merge_commit")}


def entry_revision(row: dict[str, Any]) -> Any:
    """The request revision a row's `entry` names; None when the entry is not an object, so a bad write
    from a satellite acknowledges nothing and stops no runner (sd:2792)."""
    entry = row.get("entry")
    return entry.get("revision") if isinstance(entry, dict) else None


def acknowledges(row: dict[str, Any], taken: dict[str, Any]) -> bool:
    """The request row says `queued` for the entry that took in revision `taken`."""
    revision = entry_revision(row)
    return row.get("status") == "queued" and revision is not None and revision == taken.get("revision")


def claimable(hub: Hub | None, entry: dict[str, Any]) -> bool:
    """Whether the runner may claim `entry`. A satellite entry needs its request's newest revision to be the
    `queued` write naming it: a failed write, a newer request or a row that cannot be read keeps it pending
    until an intake settles it, so it never runs on a superseded authority (review rounds 5 and 6)."""
    if entry.get("gate") != SATELLITE:
        return True
    taken = entry.get("request") or {}
    try:
        _, row = hub.store.read(hub.connection, taken["key"]) if hub is not None else (None, {})
    except Exception:  # an unread row authorises nothing
        return False
    return acknowledges(row, taken)


def write_outcome(hub: Hub, entry: dict[str, Any], outcome: dict[str, Any]) -> str:
    """Write a satellite entry's outcome to its request row, unless a newer request replaced the one it took in."""
    taken = entry.get("request") or {}
    try:
        revision, row = hub.store.read(hub.connection, taken.get("key"))
        if not acknowledges(row, taken):
            return "skipped: the request row moved on from this entry"
        hub.store.save(hub.connection, taken["key"], revision, {
            **row, "status": outcome.get("status"), **outcome_fields(outcome), "decided_at": stamp_now()})
    except Exception as error:  # the outcome stands on the entry; the row says what it last knew
        return f"failed: {type(error).__name__}: {error}"[:300]
    return "written"


def publish_pack(hub: Hub) -> str:
    """Publish the pack digest this hub's merges compare, for a satellite's warning before its gate."""
    import sd_gate_receipts  # noqa: PLC0415

    key = sd_gate_receipts.PACK_PREFIX + hub.slug
    try:
        # A pack gating itself binds its tree, not this bin/, so it publishes what its receipts hold (sd:2613).
        digest = sd_gate_receipts.pack_bin(sd_gate_receipts.gates_itself(hub.main, hub.main, BIN))
        revision, _ = hub.store.read(hub.connection, key)
        hub.store.save(hub.connection, key, revision, {"writer": "sd-lane", "pack_bin": digest,
                                                       "published_at": stamp_now(),
                                                       "pack_rev": lane_git(BIN.parent, "rev-parse", "HEAD")})
    except Exception as error:  # a satellite only loses its early warning; the merge still compares
        return f"failed: {type(error).__name__}: {error}"[:300]
    return "published"


@contextlib.contextmanager
def default_hub(root: pathlib.Path) -> Iterator[Hub | None]:
    """The run's view of the workflow database; None without `sd_db`, a database, or a GitHub origin, and off the hub."""
    if sd_lib.import_sd_db().module is None:
        yield None
        return
    import sd_gate_receipts  # noqa: PLC0415
    from sd_db import ship as store  # noqa: PLC0415
    from sd_db.database import connect, default_path  # noqa: PLC0415
    from sd_ship_remote import slug  # noqa: PLC0415

    main = sd_lib.main_worktree_root(root).resolve()
    try:
        own = slug(lane_git(main, "config", "--get", "remote.origin.url") or "")
        if sd_gate_receipts.served_hub(default_path()) is not None:  # a satellite host reads no request (sd:3003)
            raise LaneError("a satellite")
        connection = connect(default_path())
    except Exception:  # no GitHub origin, no database, or not the hub: no request can be read; entries still run
        yield None
        return
    try:
        yield Hub(connection, store, own, main)
    finally:
        connection.close()


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


def satellite_merge_argv(entry: dict[str, Any]) -> list[str]:
    """The one `sd-ship merge` a satellite entry runs: the satellite's receipt in place of a gate (sd:2704 step 4)."""
    return ["-C", entry["worktree"], "merge", "--item", str(entry["item"]), "--branch", entry["branch"],
            "--expected-head", entry["expected_head"], "--manual", "--satellite-gate",
            "--watch", "--wait-seconds", str(MERGE_WAIT_SECONDS), "--json"]


def handed_back(entry: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    """The satellite acts next: its branch moved, the base moved, or the hub would not take its receipt."""
    from sd_local_gate import HAND_BACK, SATELLITE_REFUSALS  # noqa: PLC0415

    return {"status": "handed_back", "code": code, "reason": reason[:600],
            "next_action": SATELLITE_REFUSALS.get(code, HAND_BACK).format(base=entry["base"])}


def hand_merge(entry: dict[str, Any]) -> str:
    """The hub's merge of a satellite entry for a person to run, quoted: the path and branch reach a shell."""
    return "On the hub: " + shlex.join(["sd-ship", "-C", entry["worktree"], "merge", "--item", str(entry["item"]),
                                        "--branch", entry["branch"], "--expected-head", entry["expected_head"],
                                        "--manual", "--satellite-gate"])


def process_satellite(entry: dict[str, Any], logs: pathlib.Path, ship: Ship) -> dict[str, Any]:
    """A satellite entry: fetch, the head and base checks of design.md "Freshness", then merge; no prepare."""
    main, branch, base, head = pathlib.Path(entry["worktree"]), entry["branch"], entry["base"], entry["expected_head"]
    remote, onto = f"refs/remotes/origin/{branch}", f"refs/remotes/origin/{base}"
    if scratch_git(main, "fetch", "--quiet", "--no-tags", "origin", f"+refs/heads/{branch}:{remote}",
                   f"+refs/heads/{base}:{onto}") is None:
        return {"status": "failed", "step": "fetch", "reason": f"origin/{branch} or origin/{base} could not be fetched"}
    tip = lane_git(main, "rev-parse", "--verify", "--quiet", remote)
    if tip != head:
        return {"head": head, **handed_back(entry, "head_moved", f"origin/{branch} is at {tip}, not the requested head")}
    if lane_git(main, "merge-base", "--is-ancestor", onto, head) is None:
        return {"head": head, **handed_back(entry, "base_moved", f"{head[:12]} does not contain origin/{base}")}
    if entry.get("authority") != "manual":
        return {"head": head, "status": "prepared", "reason": "requested without --manual; merge by hand",
                "next_action": hand_merge(entry)}
    log = logs / f"merge-{entry['item']}-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}.log"
    merged = ship(satellite_merge_argv(entry), log)
    fields = {"head": head, "merge_log": str(log)}
    if merged.get("ok") and merged.get("phase") == "merged":
        return {**fields, "status": "merged", "merge_commit": merged.get("merge_commit")}
    workflow = merged.get("workflow") or {}
    code = str((workflow.get("blocker") or {}).get("code") or merged.get("code") or "")
    reason = str(merged.get("error") or code or "merge did not confirm")
    if code in ("head_moved", "base_moved") or code.startswith("satellite_"):
        return {**fields, **handed_back(entry, code, reason)}
    if LOCK_HELD in reason:  # the next run retries; the request row stays `queued`
        retries = int(entry.get("lock_retries") or 0)
        if retries < LOCK_RETRIES:
            return {**fields, "status": "pending", "lock_retries": retries + 1, "reason": reason[:600]}
        reason = f"{reason}; still held after {retries} runs"
    return {**fields, "status": "failed", "step": "merge", "phase": merged.get("phase"), "code": code or None,
            "reason": reason[:600], "next_action": workflow.get("next_action")}


def process(entry: dict[str, Any], logs: pathlib.Path, ship: Ship) -> dict[str, Any]:
    """One entry, start to end; the fields to record on it."""
    if entry.get("gate") == SATELLITE:
        return process_satellite(entry, logs, ship)
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
        if row.get("gate") != SATELLITE and lane_git(pathlib.Path(row["worktree"]), "rev-parse", "HEAD") != row["expected_head"]:
            return {"skipped": f"{whose} worktree's HEAD moved from the queued head"}
    remote = lane_git(root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD") or ""
    branch = remote.removeprefix("refs/remotes/origin/")
    if not branch or branch == remote:
        return {"skipped": "origin/HEAD names no base branch"}
    # A satellite entry ahead has no worktree here: its head comes from its branch on origin.
    ahead = [f"+refs/heads/{entry['branch']}:refs/remotes/origin/{entry['branch']}"] if entry.get("gate") == SATELLITE else []
    if scratch_git(root, "fetch", "--quiet", "--no-tags", "origin", f"refs/heads/{branch}:{remote}", *ahead) is None:
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
    if entry.get("authority") != "manual" or following is None or following.get("gate") == SATELLITE:
        return None  # a satellite entry gated on the satellite, and its merge runs no gate here

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
    satellite = entry.get("gate") == SATELLITE  # merged from the main checkout; the satellite removes its own worktree
    if worktree == main and not satellite:
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
    if satellite:
        return "Cleanup: " + (", ".join(done) or f"origin/{branch} was already gone"), None
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
         own_lock: pathlib.Path, root: pathlib.Path) -> dict[str, Any]:
    """After a merge: delete the remote branch, note the item with the removal and recover commands, fast-forward.

    `root` is the repository the lane runs for. `sd-ship merge` removes a clean
    worktree itself (sd:3006), and git cannot name the main checkout from a
    directory that is gone, so the lane's own root answers (sd:3096).
    """
    worktree = pathlib.Path(entry["worktree"])
    gone = not worktree.is_dir() and entry.get("gate") != SATELLITE
    main = sd_lib.main_worktree_root(root if gone else worktree).resolve()
    head, merged = outcome.get("head"), str(outcome.get("merge_commit") or "")
    if gone:  # the merge removed the worktree with its branches; nothing is left to clean
        branch, tip = "", None
        cleanup, remove = f"Cleanup: worktree {worktree} was already removed by the merge", None
        fields: dict[str, Any] = {"cleanup": cleanup, "remove": remove}
        body = f"Landed: merged at {merged[:12]} (head {str(head)[:12]}). {cleanup}."
        return land_note(fields, body, entry, environ, note, own_lock, main)
    if entry.get("gate") == SATELLITE:  # the branch is open on the satellite; its tip here is the merged head
        branch, tip = entry["branch"], head
    else:
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


def note_hand_back(entry: dict[str, Any], outcome: dict[str, Any], note: Note) -> str:
    """Note a satellite entry's hand-back or failure on its item, with who acts next."""
    code = f" ({outcome['code']})" if outcome.get("code") else ""
    body = f"Lane: {outcome.get('status')}{code}: {outcome.get('reason')}."
    if outcome.get("next_action"):
        body += f" Next: {outcome['next_action']}"
    try:
        return note(entry["item"], body, pathlib.Path(entry["worktree"]))
    except Exception as error:  # the outcome stands on the entry and the row
        return f"failed: {type(error).__name__}: {error}"[:400]


def settle(entry: dict[str, Any], outcome: dict[str, Any], environ: dict[str, str], note: Note,
           own_lock: pathlib.Path, hub: Hub | None, root: pathlib.Path) -> dict[str, Any]:
    """What follows an entry's outcome: the landing of a merge, and a satellite entry's row and note."""
    fields: dict[str, Any] = {}
    if outcome.get("status") == "pending":  # put back (sd:2861): nothing to settle, and the row still acknowledges it
        return fields
    if outcome.get("status") == "merged":
        try:
            fields.update(land(entry, outcome, environ, note, own_lock, root))
        except Exception as error:  # the merge stands; the entry says what did not follow it
            fields["cleanup"] = f"failed: {type(error).__name__}: {error}"[:600]
        if hub is not None and BIN.is_relative_to(hub.main) and str(fields.get("fast_forward")).startswith("fast-forwarded"):
            fields["pack"] = publish_pack(hub)  # the hub's tools just changed
    if entry.get("gate") == SATELLITE:
        if hub is not None:
            fields["request_row"] = write_outcome(hub, entry, {**outcome, **fields})
        if outcome.get("status") in ("handed_back", "failed"):
            fields["note"] = note_hand_back(entry, outcome, note)
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


def run_lane(root: pathlib.Path, environ: dict[str, str], ship: Ship = default_ship,
             gate: Gate = default_gate, note: Note | None = None, *, satellite_only: bool = False,
             hub: Hub | None = None) -> dict[str, Any]:
    """Drain this repository's queue in order under its lane lock; never wait for the lock.

    One speculative gate runs at a time (`speculate`); after a merge the
    runner lands the entry (`land`), then waits for that gate, so the next
    prepare finds its receipt. `note` defaults to `default_note`, read at the
    call, so a suite can replace it; `hub` defaults to `default_hub`'s, the
    same way. Before each claim the runner takes in satellite requests
    (`intake`). `satellite_only` claims only satellite entries and starts no
    speculative gate (ruling Q4). A satellite entry is claimed only while its
    request row acknowledges it (`claimable`). Off the lane host it refuses before any of
    that (sd:3003). It reads the host again before each claim, under the
    runner lock: after a move it finishes the running entry, claims no next
    one, and says why in `stopped`.
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
        reclaimed = update(path, reclaim_dead)
        with contextlib.nullcontext(hub) if hub is not None else default_hub(root) as hub:
            ran: list[dict[str, Any]] = []
            answer: dict[str, Any] = {"ran": ran, **({"reclaimed": reclaimed} if reclaimed else {})}
            if hub is not None:
                answer.update(pack=publish_pack(hub), intake=[])
            ahead: threading.Thread | None = None
            deferred: set[tuple[Any, Any]] = set()  # entries put back this run; the next run retries them
            while True:
                stopped = lane_moved(root)  # sd:3003: a move stops the lane at an item boundary, never mid-merge
                if hub is not None and stopped is None:
                    answer["intake"] += intake(hub, path)

                def claim_next(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
                    for row in entries:
                        if (row.get("status") == "pending" and not row.get("held")
                                and (row.get("item"), row.get("enqueued_at")) not in deferred
                                and (not satellite_only or row.get("gate") == SATELLITE) and claimable(hub, row)):
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
                # A satellite-only run gates nothing: a satellite follower is never
                # gated early, and a hub entry is not this run's to prepare.
                if not satellite_only:
                    if ahead is not None and ahead.is_alive():
                        speculate(entry, path, gate, busy=True)  # notes the skip: one speculative gate at a time
                    else:
                        ahead = speculate(entry, path, gate)
                try:
                    outcome = process(entry, path.parent.parent / "logs", ship)
                except Exception as error:  # a broken entry is marked; the next one still runs
                    outcome = {"status": "failed", "reason": f"{type(error).__name__}: {error}"[:600]}
                outcome.update(settle(entry, outcome, environ, note or default_note, own_lock, hub, root))

                def finish(entries: list[dict[str, Any]], entry=entry, outcome=outcome) -> None:
                    for row in entries:
                        if row.get("item") == entry["item"] and row.get("status") == "running":
                            row.update(outcome, finished_at=stamp_now())
                update(path, finish)
                ran.append({"item": entry["item"], **outcome})
                if outcome.get("status") == "pending":
                    deferred.add((entry["item"], entry.get("enqueued_at")))
                if ahead is not None and outcome.get("status") == "merged":
                    ahead.join(PREPARE_SECONDS)  # the next prepare reads its receipt


def run_hosted(environ: dict[str, str], ship: Ship = default_ship, gate: Gate = default_gate,
               note: Note | None = None) -> dict[str, Any]:
    """`lane run --hosted`: `run_lane` for each repository this machine hosts, one after another (sd:3003).

    The same job runs on every machine. Its lanes are the managed `repo` rows,
    in path order, whose checkout is on this disk and whose lane host is this
    machine. A hosted lane runs with no queue file: a satellite's `lane request`
    is a row only intake reads (review round 1). Ownership this machine cannot
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
    editors = [mover]
    for name, text in (("hold", "skip a pending entry, keeping its place, until it is released"),
                       ("release", "let a held entry run again")):
        editors.append(verbs.add_parser(name, help=text))
        editors[-1].add_argument("item", type=int)
    for editor in editors:
        editor.add_argument("--expected-revision", help=f"refuse with {STALE_REVISION} unless `lane list` still prints "
                                                        "this revision, checked under the queue's lock")
    runner = verbs.add_parser("run", help="drain the queue in order; exits at once if another runner holds the lane")
    which = runner.add_mutually_exclusive_group()
    which.add_argument("--hosted", action="store_true",
                       help="run the lane of each repository this machine hosts, one after another (sd:3003)")
    which.add_argument("--satellite-only", action="store_true",
                       help="claim satellite entries only, start no speculative gate, exit when none is pending; "
                            "it goes once the scheduled jobs run --hosted")
    asker = verbs.add_parser("request", help="on a satellite: ask the hub's lane to merge this worktree's prepared item")
    asker.add_argument("--item", type=int, required=True)
    asker.add_argument("--manual", action="store_true", help="authorize the hub's runner to merge, as enqueue --manual")
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
        elif args.lane_command == "cancel":
            result = cancel(root, args.item, environ)
        elif args.lane_command == "move":
            result = move(root, args.item, args.where, environ, expected_revision=args.expected_revision)
        elif args.lane_command in ("hold", "release"):
            result = set_hold(root, args.item, environ, held=args.lane_command == "hold",
                              expected_revision=args.expected_revision)
        elif args.lane_command == "request":
            result = request(root, args.item, manual=args.manual)
        else:
            result = run_lane(root, environ, satellite_only=args.satellite_only)
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
