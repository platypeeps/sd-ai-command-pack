"""`sd-ship lane`: a serial ship queue per repository that outlives the session that filled it (sd:2524).

An integrator session used to chain `sd-ship prepare` and `merge` by hand, in
shell scripts kept in its scratchpad. The chain died with the session, and a
second chain started beside it raced it. This keeps the chain in the hub
database and runs it under one runner lock per repository:

  enqueue  publish the head, then add a worktree, its item, branch and head,
           a title and the body text to the repository's queue;
  list     print the queue, each body as its size;
  cancel   mark a pending entry cancelled, or release a stuck running one;
           `--expected-claim <holder token>:<step>` releases only the
           running claim the caller read (sd:3330);
  retry    queue the item's last failed, skipped or prepared entry again, at
           its head with its texts; `--manual` grants the merge (sd:3254);
           `--expected-head` refuses, in the write's transaction, a last
           entry at another head (sd:3268); a cancelled one needs it, and
           refuses a moved branch, a newer entry or a merged head (sd:3389);
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
           runner lock it first reclaims a running entry whose holder here
           is gone, and lists it as `reclaimed` (sd:2821, below). An entry
           whose prepare or merge met a hub fault goes
           back to pending, at most `HUB_RETRIES` times, and the run stops
           (sd:3239, below);
  watch    print each gate end a lane or builder log records, once.

The verbs are the queue's only writers, each in one hub database
transaction, so a terminal and a dashboard reorder it the same way. A change
takes effect at the next item boundary, never mid-merge; a running entry
refuses every edit.

The queue is in the hub database (sd:3282): each entry is the latest `state`
row, kind `checkpoint`, of its key `lane:v1:<owner/repo>:<id>`, and older
rows are its history. A write is one `BEGIN IMMEDIATE` transaction, local on
the hub and over the tailnet session on a satellite; with the hub down every
verb refuses `hub_unavailable`. A checkout whose origin names no GitHub
repository has no lane. The lane folder, `<lane root>/<repository>/lane/`,
keeps this machine's logs and runner lock, and under `review/` each review
`sd-ship prepare` finished but the hub has not yet recorded (sd:3340). The lane root is `SD_LANE_ROOT`,
else `sd.lane_root`, else `$XDG_STATE_HOME/sd/lanes`. A `queue/queue.json` an
earlier version left there is imported once (`import_file_queue`).

Another host runs an entry only from a commit on `origin`, so enqueue,
retry and the import of a pending entry publish its head first, by
`<head>:refs/heads/<branch>`, never the tip, never with force and never to
the default branch `origin` advertises (`publish_head`). A failed read,
fetch or push is an unknown answer, not a "no": nothing is queued.

A claim reads the lane host and takes the first pending entry in one
transaction, and refuses while another entry of the repository runs. The
lane host runs any entry, whichever host enqueued it (sd:3283): its own
worktree when it was enqueued here, any worktree here at its head, else a
lane worktree from the fetched `origin/<branch>`, which the runner removes
once the entry ends (`checkout_for`). A
running entry carries a `holder` (host, pid, a token per claim), its `step`
and `lease_until`. Every runner write checks the token, so a reclaimed or
released claim writes nothing more; a hub fault is tried again for
`WRITE_RETRY_SECONDS`, then the run stops, and a hub that refuses this
build stops it at once (sd:3359). A holder on this machine is dead
when the runner lock is free and its pid is gone; one on another machine
once its lease passed, which the lane host checks at claim. In prepare its
entry goes back to pending, failing at the `RECLAIMS`th time; in merge it
fails, since a merge may have landed. `lane cancel` on a running entry
releases it by the same rule, unless its holder here is alive.

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
keeps its texts as every row does (sd:3254), so `retry` needs no body file.
The runner writes them to private temporary files for prepare. A cancelled
entry keeps them too, and `retry` queues it again only at the head the caller
read (sd:3389): the system Queue page re-queues a cancel, and enqueues nothing.

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
It never removes a builder's worktree: no lock excludes its builder, and a
write through a handle opened before removal is lost. The entry's `remove`
holds the command that removes the worktree and its branch once the builder
stops, and the note names the host that holds it.
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
`repo.lane_host` names, or the hub when it is NULL. Elsewhere `run` refuses
with `lane_elsewhere`, and a host that cannot be read refuses with
`lane_unknown`; every other verb edits the shared queue from any host
(sd:3283). Each claim reads the host in its own transaction, and so does
the before-merge write: after a move the entry in flight goes back to
pending at its place, with `moved_off`, and the run stops; a merge that
answers `lane_elsewhere` counts as the same move. Such a put-back moves
`expected_head` only to a catch-up merge prepare pushed
(`pushed_catch_up`). The same scheduled job runs on every machine: `lane
run --hosted` runs each lane this machine hosts, one after another, and
skips one whose runner is busy; for every other checkout here it imports
the file queue and reclaims. The lane host gates and merges on its own
machine; the entry's commits reach it through `origin`.

A hub fault is retried (sd:3239). A hub upgrade broke a satellite's sessions
mid-prepare, and the entries failed for good. When `sd-ship` names the
blocker `hub_unavailable` (`sd_ship_workflow.HUB_FAULTS`), the runner puts the
entry back as pending with its `hub_retries` count and stops: the next entry
would meet the same hub. The next run starts after the satellite's
self-install, in a new process. A catch-up merge prepare made is accepted
as the entry's head; any other move still skips the entry.
The retry's prepare reuses a review that cleared before the fault, as at any
head the ship receipt records reviewed; a review whose report the fault kept
from the receipt is incomplete, and spends the one `--retry-review`.
"""

from __future__ import annotations

import calendar
import contextlib
import dataclasses
import fcntl
import functools
import hashlib
import json
import os
import pathlib
import re
import secrets
import signal
import sqlite3
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
#: After this long a run starts no new entry (sd:3287). The lane-run cron job's
#: JOB_TIMEOUT is 120 minutes, and one entry takes 30 to 45, so an entry started
#: just inside the budget still finishes before the job limit TERMs the runner.
RUN_BUDGET_SECONDS = 55 * 60
#: How long a stopped run waits for its cancelled speculative gate, once after
#: SIGTERM and once after SIGKILL (sd:3361).
CANCEL_SECONDS = 10
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
#: The codes of an entry that stops `prepared` for want of merge authority (sd:3132).
RUNNER_MERGE_MANUAL = "runner_merge_manual"
RUNNER_MERGE_UNKNOWN = "runner_merge_unknown"
#: The runs that put an entry back after a hub fault before the next fault fails it (sd:3239).
HUB_RETRIES = 2
#: The ends short of a merge: `retry` queues such an entry again, with its texts (sd:3254), and a cancelled
#: one at the head the caller read (sd:3389).
BLOCKED = ("failed", "skipped", "prepared")


class LaneError(RuntimeError):
    """A lane command that cannot do what it was asked; nothing was changed. `code` is a stable refusal name, or None."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class Stop(LaneError):
    """A runner write that cannot land: its claim was voided, or the hub stayed down past `WRITE_RETRY_SECONDS`."""


class BuildRefused(LaneError):
    """A `hub_unavailable` refusal no retry in this process can pass (`sd_ship_workflow.BUILD_FAULTS`, sd:3359)."""


#: The refusal code of a cancel, move, hold or release whose `--expected-revision` no longer matches (sd:2717).
STALE_REVISION = "stale_revision"
#: The refusal code of a retry whose `--expected-head` is not the head of the item's last entry (sd:3268).
STALE_HEAD = "stale_head"
#: The refusal code of a cancel whose `--expected-claim` no longer holds the item's running entry (sd:3330).
STALE_CLAIM = "stale_claim"
#: The refusals of a cancelled entry's retry (sd:3389): its item has a newer entry, or merged at its head.
SUPERSEDED, ALREADY_MERGED = "superseded", "already_merged"
#: The refusal code of a lane verb whose hub database did not answer; a write may have landed (sd:3282).
HUB_UNAVAILABLE = "hub_unavailable"
#: The code of a runner write whose claim token no longer holds its entry: a reclaim or a release voided it.
CLAIM_LOST = "claim_lost"
#: A publish whose read, fetch or push failed: `origin` may have moved, so the answer is unknown, not "no".
PUBLISH_UNKNOWN = "publish_unknown"
#: The definite publish answers: the head's commit is in neither place, or the remote branch and the head diverged.
HEAD_GONE, BRANCH_DIVERGED = "head_gone", "branch_diverged"
#: The definite publish answer for no branch or `origin`'s default branch: only a pull request lands there.
DEFAULT_BRANCH = "default_branch"
#: The skips of an entry with no checkout here (sd:3283): `origin/<branch>` is past the queued head and its
#: catch-up merge, or a local branch of that name is at another commit; `HEAD_GONE` when `origin` has no branch.
HEAD_MOVED, BRANCH_BUSY = "head_moved", "branch_busy"
#: The code of a lane verb off its lane host, and of an `sd-ship merge` that met a lane move (sd:3003).
LANE_ELSEWHERE = "lane_elsewhere"
#: Each entry is the latest `state` row, kind `checkpoint`, of its key `lane:v1:<owner/repo>:<id>` (sd:3282).
KEY_PREFIX = "lane:v1:"
#: A runner write that meets a hub fault is tried every `WRITE_PAUSE` seconds for this long, then the run stops.
WRITE_RETRY_SECONDS = 600
WRITE_PAUSE = 30
#: The reclaim of a dead holder in prepare that fails its entry instead of putting it back, so a crash loop stops.
RECLAIMS = 3
#: A merge lease is `MERGE_SECONDS` and this long for the landing.
LANDING_SECONDS = 1800
#: The bound on one `git` step of a publish: a fetch or a push crosses the network.
PUBLISH_SECONDS = 300
#: The longest chain of catch-up merges an entry's head may carry: one per prepare that pushed a catch-up
#: and was then reclaimed or put back after a hub fault, so every reclaim and hub retry fits (sd:3283).
CATCH_UPS = RECLAIMS + HUB_RETRIES + 1


@dataclasses.dataclass(frozen=True)
class Queue:
    """One repository's queue in the hub database, and this machine's lane folder for its logs and its runner lock."""

    repository: str
    lane: pathlib.Path
    environ: dict[str, str]

    @property
    def lock_file(self) -> pathlib.Path:
        return self.lane / "queue" / "runner.lock"


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
    """Where an earlier version kept the queue file; `import_file_queue` reads it once, and `lane list` names it."""
    return lane_dir(root, environ) / "queue" / "queue.json"


def require_sd_db() -> None:
    """Make `sd_db` importable through `sd_lib.import_sd_db`, or refuse: the queue lives in its database."""
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise LaneError(f"the lane queue lives in the workflow database: {imported.problem}", code=HUB_UNAVAILABLE)


def hub_database(environ: dict[str, str]) -> Any:
    """The workflow database: the file on the hub, the hub's over the tailnet on a satellite."""
    require_sd_db()
    from sd_db.database import default_path  # noqa: PLC0415
    return default_path(environ.get("HOME"))


def this_host() -> str:
    require_sd_db()
    from sd_db.ship import (
        this_host as host,  # noqa: PLC0415 -- the one host name the lane host rows use
    )
    return host()


def runnable(row: dict[str, Any]) -> bool:
    """A pending entry, not held: the lane host runs it from whichever host enqueued it (sd:3283)."""
    return row.get("status") == "pending" and not row.get("held")


def lease_passed(row: dict[str, Any]) -> bool:
    """Whether a running entry's `lease_until` is past; a lease that is missing or unreadable has not passed."""
    try:
        return calendar.timegm(time.strptime(str(row["lease_until"]), "%Y-%m-%dT%H:%M:%SZ")) < time.time()
    except (KeyError, ValueError, OverflowError):
        return False


def repository_of(root: pathlib.Path) -> str | None:
    """`owner/name`, lower-cased, of the GitHub repository `root`'s origin names, or None."""
    require_sd_db()
    from sd_db.protection import github_slug  # noqa: PLC0415
    found = github_slug(lane_git(sd_lib.main_worktree_root(root), "config", "--get", "remote.origin.url") or "")
    return "/".join(found).lower() if found else None


def queue_for(root: pathlib.Path, environ: dict[str, str]) -> Queue:
    """The queue of the repository `root` is a checkout of; one whose origin names no GitHub repository has none."""
    repository = repository_of(root)
    if repository is None:
        raise LaneError(f"{root} has no lane: its origin names no GitHub repository, so prepare could not open "
                        "its pull request either")
    return Queue(repository, lane_dir(root, environ), environ)


def on_hub(queue: Queue, work: Callable[[Any], Any]) -> Any:
    """`work(connection)` in one hub database transaction, `BEGIN IMMEDIATE`; it replaces the queue file's lock.

    Local on the hub, over the tailnet session on a satellite. The read, the
    check and the write sit in one transaction, so a revision or head check
    keeps its meaning. A fault of the database or its session refuses with
    `HUB_UNAVAILABLE`: an unknown answer, since a write may have landed.
    """
    require_sd_db()
    from sd_db.database import connect, transaction  # noqa: PLC0415
    from sd_db.errors import SdDbError  # noqa: PLC0415
    try:
        connection = connect(hub_database(queue.environ), write=True)
        try:
            with transaction(connection):
                return work(connection)
        finally:
            connection.close()
    except (SdDbError, sqlite3.Error, OSError, EOFError) as error:
        refusal = BuildRefused if sd_ship_workflow.is_hub_fault(error, sd_ship_workflow.BUILD_FAULTS) else LaneError
        raise refusal(f"The hub database did not answer: {type(error).__name__}: {error}. A write may have "
                      "landed; `sd-ship lane list` shows the queue once the hub answers.",
                      code=HUB_UNAVAILABLE) from None


def stored(connection: Any, repository: str) -> list[dict[str, Any]]:
    """The latest row of each of `repository`'s entry keys, in queue order; older rows are each entry's history."""
    prefix = f"{KEY_PREFIX}{repository}:"
    rows = connection.execute(
        "SELECT body FROM state WHERE id IN (SELECT MAX(id) FROM state WHERE kind = 'checkpoint' "
        "AND substr(key, 1, ?) = ? GROUP BY key)", (len(prefix), prefix)).fetchall()
    return sorted((json.loads(row["body"]) for row in rows), key=lambda row: (row.get("position") or 0, row["id"]))


def store(connection: Any, repository: str, entry: dict[str, Any]) -> None:
    require_sd_db()
    from sd_db.writes import now  # noqa: PLC0415
    connection.execute("INSERT INTO state(kind, key, timestamp, body) VALUES ('checkpoint', ?, ?, ?)",
                       (f"{KEY_PREFIX}{repository}:{entry['id']}", now(), json.dumps(entry, sort_keys=True)))


def update(queue: Queue, change: Callable[[list[dict[str, Any]]], Any],
           check: Callable[[Any], None] | None = None) -> Any:
    """One read-modify-write: `change` edits the entries, each entry it changed or added gets a new row.

    `check(connection)` runs first in the same transaction, and refuses by raising.
    """
    def work(connection: Any) -> Any:
        if check is not None:
            check(connection)
        entries = stored(connection, queue.repository)
        before = {row["id"]: json.dumps(row, sort_keys=True) for row in entries}
        answer = change(entries)
        for row in entries:
            if before.get(row["id"]) != json.dumps(row, sort_keys=True):
                store(connection, queue.repository, row)
        return answer
    return on_hub(queue, work)


def read_queue(queue: Queue) -> list[dict[str, Any]]:
    return on_hub(queue, lambda connection: stored(connection, queue.repository))


def runner_write(queue: Queue, change: Callable[[list[dict[str, Any]]], Any],
                 check: Callable[[Any], None] | None = None) -> Any:
    """`update` for the runner: a hub fault is tried again every `WRITE_PAUSE` seconds, up to `WRITE_RETRY_SECONDS`.

    Then it raises `Stop`, and the run stops; a write that landed unseen is
    found by the next try or the next run, under the claim's token. A hub
    that refuses this process's build (`BuildRefused`) stops it at once
    (sd:3359): no retry in this process can pass, and the `repo-sync.sh
    follow` that clears it waits for the runner lock the retry would hold.
    """
    deadline = time.monotonic() + WRITE_RETRY_SECONDS
    while True:
        try:
            return update(queue, change, check)
        except Stop:
            raise
        except BuildRefused as error:
            raise Stop(f"{error} This process keeps the build it loaded, so the runner stops now and frees its "
                       "lock; the next run settles the entry.", code=HUB_UNAVAILABLE) from None
        except LaneError as error:
            if error.code != HUB_UNAVAILABLE:
                raise
            if time.monotonic() >= deadline:
                raise Stop(f"{error} The runner stops; the next run settles the entry.", code=HUB_UNAVAILABLE) from None
        time.sleep(WRITE_PAUSE)


@contextlib.contextmanager
def queue_lock(path: pathlib.Path) -> Iterator[None]:
    """The queue file's lock, which an earlier `sd-ship` takes to append to that file; the import takes it too."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


@contextlib.contextmanager
def runner_lock(queue: Queue) -> Iterator[bool]:
    """This machine's runner lock for the repository, never waited for: True when held, False when busy."""
    queue.lock_file.parent.mkdir(parents=True, exist_ok=True)
    with open(queue.lock_file, "a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def lane_git(worktree: pathlib.Path, *args: str) -> str | None:
    return sd_lib.git_output(list(args), worktree)


def stamp_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stamp_at(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def entry_id() -> str:
    """`<UTC stamp>-<8 hex>`, made once at enqueue: the last part of the entry's key."""
    return f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{secrets.token_hex(4)}"


def shown(row: Any) -> Any:
    """An entry as a verb prints it: the body and acceptance texts as their sizes."""
    if not isinstance(row, dict):
        return row
    texts = {f"{key}_bytes": len(row[key].encode()) for key in ("body", "acceptance") if isinstance(row.get(key), str)}
    return {**{key: value for key, value in row.items() if key not in ("body", "acceptance")}, **texts}


def publish_git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=PUBLISH_SECONDS,
                              check=False, env=sd_lib.without_fsmonitor(os.environ))
    except (OSError, subprocess.SubprocessError):
        return None


def publish_head(root: pathlib.Path, branch: str, head: str) -> str | None:
    """Put `head` on `origin/<branch>`; None once it is there, else `DEFAULT_BRANCH`, `HEAD_GONE` or `BRANCH_DIVERGED` (sd:3282).

    Another host runs an entry only from a commit on `origin`. The one push is
    `<head>:refs/heads/<branch>`, never the branch tip and never with force,
    so a branch the builder moved after enqueue still publishes the head the
    entry names. A tip that is `head` or contains it pushes nothing. The two
    answers are definite: the same push can never succeed. A failed read,
    fetch or push raises `PUBLISH_UNKNOWN`: `origin` may have moved.
    No branch, or `origin`'s default branch, answers `DEFAULT_BRANCH`: a push
    there lands commits no pull request reviewed. The default branch is the
    `HEAD` symref `origin` advertises in the same read as the tip, never a
    local `origin/HEAD` or a guess; no symref is `PUBLISH_UNKNOWN`.
    """
    if not branch:
        return DEFAULT_BRANCH
    ref = f"refs/heads/{branch}"

    def answer(*args: str, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
        done = publish_git(root, *args)
        if done is None or done.returncode not in ok:
            said = (done.stderr or done.stdout).strip()[-400:] if done is not None else "no answer"
            raise LaneError(f"Cannot tell whether {head} is on origin/{branch}: git {args[0]} failed ({said}). "
                            "Nothing was queued; retry when origin answers.", code=PUBLISH_UNKNOWN)
        return done

    def has(commit: str) -> bool:
        return answer("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}", ok=(0, 1)).returncode == 0

    def descends(newer: str, older: str) -> bool:
        return answer("merge-base", "--is-ancestor", older, newer, ok=(0, 1)).returncode == 0
    listed = [line.split("\t") for line in answer("ls-remote", "--symref", "origin", "HEAD", ref).stdout.splitlines()]
    default = next((name.removeprefix("ref: refs/heads/") for name, *rest in listed
                    if rest == ["HEAD"] and name.startswith("ref: refs/heads/")), None)
    if default is None:
        raise LaneError(f"Cannot tell whether {branch} is origin's default branch: origin advertised no HEAD branch. "
                        "Nothing was queued or pushed; retry when origin answers.", code=PUBLISH_UNKNOWN)
    if branch == default:
        return DEFAULT_BRANCH
    tip = next((name for name, *rest in listed if rest == [ref]), None)
    if tip == head:
        return None
    if tip and not has(tip):
        answer("fetch", "-q", "--no-tags", "origin", ref)
    if not has(head):
        return HEAD_GONE
    if tip and descends(tip, head):
        return None
    if tip and not descends(head, tip):
        return BRANCH_DIVERGED
    answer("push", "-q", "origin", f"{head}:{ref}")
    return None


def require_published(root: pathlib.Path, branch: str, head: str, gone: str) -> None:
    """`publish_head`, refusing a definite answer: `gone` says what to do when the head's commit is nowhere."""
    found = publish_head(root, branch, head)
    if found == DEFAULT_BRANCH:
        raise LaneError(f"{branch or 'a detached HEAD'} is not a feature branch: the lane publishes and prepares a "
                        "branch other than origin's default; nothing was queued or pushed.", code=DEFAULT_BRANCH)
    if found == HEAD_GONE:
        raise LaneError(gone, code=HEAD_GONE)
    if found == BRANCH_DIVERGED:
        raise LaneError(f"origin/{branch} and {head} each lack the other's commits; nothing was queued. "
                        "Push the branch yourself, or enqueue a head that contains origin's.", code=BRANCH_DIVERGED)


def add_entry(queue: Queue, entry: dict[str, Any],
              guard: Callable[[list[dict[str, Any]]], None] | None = None,
              check: Callable[[Any], None] | None = None) -> dict[str, Any]:
    """Append `entry` at the largest position plus one; `guard` and `check` refuse first, in the same transaction.

    `guard` reads the entries, `check(connection)` the hub database (`update`).
    """
    def append_last(entries: list[dict[str, Any]]) -> dict[str, Any]:
        if guard is not None:
            guard(entries)
        if any(row.get("item") == entry["item"] and row.get("status") in ("pending", "running") for row in entries):
            raise LaneError(f"sd:{entry['item']} is already queued in this lane")
        entry["position"] = max((int(row.get("position") or 0) for row in entries), default=0) + 1
        entries.append(entry)
        return entry
    return update(queue, append_last, check)


def enqueue_entry(worktree: pathlib.Path, item: int, title: str, body_file: pathlib.Path, environ: dict[str, str], *,
                  expected_head: str | None = None, manual: bool = False, claim: str | None = None,
                  acceptance_file: pathlib.Path | None = None) -> dict[str, Any]:
    """Add one entry; the head defaults to the worktree's, and must name a commit there.

    `claim` is prepare's delivery choice, `deliver` or `associate-only`, and
    is refused when absent as prepare refuses it; it reaches prepare
    unchanged. The entry holds the body and acceptance texts, not their
    paths. The head is published first (`publish_head`); any answer but published
    refuses, and nothing is queued.
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
    branch = lane_git(worktree, "branch", "--show-current")
    if not branch:
        raise LaneError(f"{worktree} has no branch checked out; the lane publishes and prepares a branch")
    queue = queue_for(worktree, environ)
    # Read first: a hub that does not answer, or an item already queued, refuses before anything is pushed.
    if any(row.get("item") == item and row.get("status") in ("pending", "running") for row in read_queue(queue)):
        raise LaneError(f"sd:{item} is already queued in this lane")
    entry = {"id": entry_id(), "repository": queue.repository, "item": item, "branch": branch, "expected_head": head,
             "title": title, "body": body_file.read_text(encoding="utf-8"),
             "acceptance": acceptance_file.read_text(encoding="utf-8") if acceptance_file else None,
             "authority": "manual" if manual else None, "claim": claim, "enqueued_on": this_host(),
             "worktree": str(worktree), "status": "pending", "enqueued_at": stamp_now()}
    require_published(worktree, branch, head, f"{head} names no commit in {worktree}")
    return add_entry(queue, entry)


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


def reclaim(row: dict[str, Any], *, released: bool = False) -> dict[str, Any]:
    """Settle a running entry whose holder is dead, or that the operator released; what was done.

    At `step: prepare` it goes back to pending at its place, with `reclaims`
    plus one; prepare saves under revision checks and runs again safely. The
    `RECLAIMS`th reclaim fails it instead. At `step: merge` it fails: a merge
    may have landed. The holder goes, so its token holds nothing any more.
    """
    holder = row.pop("holder", None) or {}
    pid, step = holder.get("pid"), row.pop("step", None)
    reclaims = int(row.get("reclaims") or 0) + 1
    who = f"the operator released it from {holder.get('host')} pid {pid}" if released else f"runner pid {pid} died"
    for key in ("lease_until", "started_at"):
        row.pop(key, None)
    row.update(last_holder=holder, reclaims=reclaims, **({"released": True} if released else {}))
    if step == "prepare" and reclaims < RECLAIMS:
        row.update(status="pending")
    elif step == "prepare":
        row.update(status="failed", step="runner", finished_at=stamp_now(), reclaimed_by=os.getpid(),
                   reason=f"{who} in prepare, reclaim {reclaims} of {RECLAIMS}; the lane stops retrying it, so "
                          "read its prepare logs before enqueueing it again")
    else:
        row.update(status="failed", step="runner", finished_at=stamp_now(), reclaimed_by=os.getpid(),
                   reason=f"{who} with the entry running; a merge may have landed, so read its logs and pull "
                          "request before enqueueing it again")
    return {"item": row.get("item"), "runner_pid": pid, "step": step, "status": row["status"]}


def check_claim(running: dict[str, Any] | None, item: int, expected: str | None) -> None:
    """Refuse a release of a claim other than `<holder token>:<step>`, the one the caller read; None checks nothing.

    The revision covers the pending entries only, and a token is made per
    claim, so this one catches a step that moved on, a claim that ended, and
    an entry that went back to pending and was claimed again (sd:3330).
    """
    if expected is None:
        return
    token = ((running or {}).get("holder") or {}).get("token")
    now = f"{token}:{(running or {}).get('step')}" if token else None
    if now != expected:
        raise LaneError(f"sd:{item} is not running under claim {expected}; "
                        f"{f'it is at {now}' if now else 'no claim holds it'}; read it again with `sd-ship lane list`",
                        code=STALE_CLAIM)


def cancel(root: pathlib.Path, item: int, environ: dict[str, str], *,
           expected_revision: str | None = None, expected_claim: str | None = None) -> dict[str, Any]:
    """Cancel a pending entry, or release a running one (D3 of sd:3174) by the reclaim rule (`reclaim`).

    A release refuses while the holder is on this machine and its pid is
    alive. A holder on another machine counts as stuck on the operator's word.
    `expected_claim` binds the cancel to the running claim the caller read
    (`check_claim`), in the write's transaction.
    """
    if expected_claim is not None and not all(expected_claim.partition(":")[::2]):
        raise LaneError(f"name the claim as <holder token>:<step>, as `sd-ship lane list` prints them, "
                        f"not {expected_claim!r}")

    def mark(entries: list[dict[str, Any]]) -> dict[str, Any]:
        check_revision(entries, expected_revision)
        running = next((row for row in entries if row.get("item") == item and row.get("status") == "running"), None)
        check_claim(running, item, expected_claim)
        if running is not None:
            holder = running.get("holder") or {}
            if holder.get("host") == this_host() and runner_alive(holder.get("pid")):
                raise LaneError(f"sd:{item} is running under pid {holder.get('pid')} on this machine; "
                                "it is not stuck, so it is not released", code="holder_alive")
            reclaim(running, released=True)
            return running
        row = pending_entry(entries, item)
        row.update(status="cancelled", finished_at=stamp_now())
        return row
    return update(queue_for(root, environ), mark)


def enqueue_order(connection: Any, repository: str) -> dict[str, int]:
    """Each entry id's first row id: the order the hub took the entries in, which no clock and no `move` changes."""
    prefix = f"{KEY_PREFIX}{repository}:"
    return {row["key"][len(prefix):]: row["first"] for row in connection.execute(
        "SELECT key, MIN(id) AS first FROM state WHERE kind = 'checkpoint' AND substr(key, 1, ?) = ? GROUP BY key",
        (len(prefix), prefix)).fetchall()}


def newest_entry(connection: Any, repository: str, item: int) -> dict[str, Any] | None:
    """`item`'s newest entry by `enqueue_order`, or None (sd:3412).

    Not the last by position: after a hold and `move top`, a newer entry
    sits above older finished ones.
    """
    order = enqueue_order(connection, repository)
    return max((row for row in stored(connection, repository) if row.get("item") == item),
               key=lambda row: order.get(row["id"], 0), default=None)


def check_successor(connection: Any, repository: str, entry: dict[str, Any]) -> None:
    """Refuse `SUPERSEDED` when `entry`'s item has a newer entry, whatever its end (sd:3389).

    Newer is by `enqueue_order`, not position: `move` can put a later entry
    above it. The operator's next step for the item was that entry.
    """
    item, newest = entry.get("item"), newest_entry(connection, repository, entry.get("item"))
    if newest is not None and newest["id"] != entry["id"]:
        raise LaneError(f"sd:{item} has a newer entry, {newest.get('status')} at {newest.get('expected_head')}, "
                        f"than the {entry.get('status')} one; read it again with `sd-ship lane list`", code=SUPERSEDED)


def check_unmerged(root: pathlib.Path, queue: Queue, cancelled: dict[str, Any]) -> None:
    """Refuse `ALREADY_MERGED` when the ship receipt of the entry's branch and item merged its head (sd:3389).

    Every merge goes through `sd-ship`, in the lane or by hand, and leaves that
    receipt in the hub database; a squash leaves the head off the base, so the
    base's history cannot tell. A receipt `merged` or `merge_dispatch` at a
    head that contains the cancelled one refuses; a later head on the branch
    is a follow-up and passes. An unreadable receipt, or a git read that fails,
    is unknown and refuses.
    """
    require_sd_db()
    from sd_db import ship  # noqa: PLC0415
    from sd_db.workflow import WorkflowError  # noqa: PLC0415
    item, branch, head = cancelled.get("item"), str(cancelled["branch"]), str(cancelled["expected_head"])

    def branch_receipt(connection: Any) -> dict[str, Any]:
        try:
            return ship.read(connection, ship.receipt_key(queue.repository, branch, int(str(item))))[1]
        except WorkflowError as error:
            raise LaneError(f"sd:{item}'s ship receipt for {branch} cannot be read ({error}), so whether {head} "
                            "merged is unknown; nothing was queued") from None
    found = on_hub(queue, branch_receipt)
    if found.get("phase") not in ("merged", "merge_dispatch"):
        return
    merged = str(found.get("head") or "")
    if not merged or merged == head or read_git(root, "merge-base", "--is-ancestor", head, merged,
                                                 ok=(0, 1)).returncode == 0:
        raise LaneError(f"sd:{item}'s ship receipt for {branch} is {found.get('phase')} at "
                        f"{found.get('merge_commit') or merged or 'an unrecorded head'}, which holds the cancelled "
                        f"head {head}; nothing was queued", code=ALREADY_MERGED)


def branch_unmoved(root: pathlib.Path, cancelled: dict[str, Any]) -> None:
    """Refuse `HEAD_MOVED` when a cancelled entry's branch moved past its head (sd:3389).

    A moved branch is scope the caller did not see: enqueue it from its
    worktree. `origin/<branch>` must be the head, prepare's catch-up of it, or
    gone (the publish puts the head back); this host's worktree, while on the
    branch, the head or its catch-up. A read that fails raises `PUBLISH_UNKNOWN`.
    """
    item, branch, head = cancelled.get("item"), str(cancelled["branch"]), str(cancelled["expected_head"])
    tip = (read_git(root, "ls-remote", "origin", f"refs/heads/{branch}").stdout.split() or [""])[0]
    if tip and read_git(root, "rev-parse", "--verify", "--quiet", f"{tip}^{{commit}}", ok=(0, 1)).returncode != 0:
        read_git(root, "fetch", "-q", "--no-tags", "origin", f"refs/heads/{branch}")
    if tip and tip != head:
        if not catch_up_of(root, tip, head):
            raise LaneError(f"origin/{branch} is at {tip}, not sd:{item}'s cancelled head {head} or its catch-up; "
                            "nothing was queued. Enqueue the new head from its worktree.", code=HEAD_MOVED)
    worktree = pathlib.Path(str(cancelled.get("worktree")))
    if (cancelled.get("enqueued_on") == this_host() and worktree.is_dir()
            and read_git(worktree, "branch", "--show-current").stdout.strip() == branch
            and not at_head(worktree, head)):
        raise LaneError(f"{worktree} moved on {branch} from sd:{item}'s cancelled head {head}; nothing was "
                        "queued. Enqueue the new head from that worktree.", code=HEAD_MOVED)


def retry(root: pathlib.Path, item: int, environ: dict[str, str], *, manual: bool = False,
          expected_head: str | None = None) -> dict[str, Any]:
    """Queue `item`'s last entry again when it stopped short of a merge (sd:3254).

    A new entry with the old one's branch, title, claim, texts and worktree
    hint, at its head, or at prepare's catch-up of it (`caught_up`) when the
    worktree is on this host. The head is published now (`publish_head`); a
    refusal queues nothing and the old entry stays blocked. `manual` grants
    the merge as `enqueue --manual` does; an entry that had that grant keeps
    it. The old entry stays as history.

    The last entry is the item's newest by `enqueue_order`, not by position
    (sd:3412). `expected_head`, a full commit id, is the head the caller
    showed: a last entry at another head is refused with `STALE_HEAD`
    (sd:3268). None checks nothing. In the write's transaction the read
    is made again: another head refuses `STALE_HEAD`, a newer entry
    `SUPERSEDED` (`check_successor`).

    A cancelled last entry (sd:3389) needs `expected_head`, and is refused
    before the publish by `branch_unmoved` and `check_unmerged`. The new
    entry joins the queue last, as any enqueue does. A branch that moves
    after `branch_unmoved` read it leaves the entry pending; the runner's
    head check (`checkout_for`) then skips it `HEAD_MOVED`.
    """
    def newest_at_expected_head(connection: Any) -> dict[str, Any]:
        latest = newest_entry(connection, queue.repository, item)
        if latest is None:
            raise LaneError(f"sd:{item} has no entry in this lane")
        if expected_head is not None and latest.get("expected_head") != expected_head:
            raise LaneError(f"sd:{item}'s last entry is at {latest.get('expected_head')}, not the expected head "
                            f"{expected_head}; read it again with `sd-ship lane list`", code=STALE_HEAD)
        return latest

    def still_newest(connection: Any) -> None:
        newest_at_expected_head(connection)
        check_successor(connection, queue.repository, last)
    queue = queue_for(root, environ)
    last = on_hub(queue, newest_at_expected_head)
    if last.get("status") in ("pending", "running"):
        raise LaneError(f"sd:{item} is already queued in this lane")
    cancelled = last.get("status") == "cancelled"
    if not cancelled and last.get("status") not in BLOCKED:
        raise LaneError(f"sd:{item}'s last entry is {last.get('status')}; retry takes a failed, skipped, "
                        "prepared or cancelled one")
    if cancelled and expected_head is None:
        raise LaneError(f"sd:{item}'s last entry is cancelled; retry it only at the head you read, with "
                        "--expected-head <full commit id> as `sd-ship lane list` prints it")
    if not last.get("branch"):
        raise LaneError(f"sd:{item}'s last entry names no branch; queue it with `sd-ship lane enqueue`")
    if not isinstance(last.get("body"), str):
        raise LaneError(f"sd:{item}'s last entry kept no body; enqueue it again with --body-file")
    if cancelled:
        branch_unmoved(root, last)
        check_unmerged(root, queue, last)
    worktree, head = pathlib.Path(str(last.get("worktree"))), last["expected_head"]
    if last.get("enqueued_on") == this_host() and worktree.is_dir():
        head = caught_up(worktree, head)
    require_published(root, last["branch"], head,
              f"sd:{item}'s head {head} is not on `origin` or in this checkout; run the retry on "
              f"{last.get('enqueued_on')}, or enqueue again from a worktree that has it")
    keep = ("repository", "item", "branch", "title", "body", "acceptance", "claim", "enqueued_on", "worktree")
    entry = {**{key: last.get(key) for key in keep}, "id": entry_id(), "expected_head": head,
             "authority": "manual" if manual or last.get("authority") == "manual" else None,
             "status": "pending", "enqueued_at": stamp_now()}
    added = add_entry(queue, entry, check=still_newest)
    return {**added, "retried": {"status": last["status"], "finished_at": last.get("finished_at")}}


def position(where: str) -> str:
    """`up`, `down`, `top`, or a 1-based position among the pending entries."""
    if where in PLACES or (where.isdigit() and int(where) >= 1):
        return where
    raise ValueError(f"name up, down, top or a position from 1, not {where!r}")


def move(root: pathlib.Path, item: int, where: str, environ: dict[str, str], *,
         expected_revision: str | None = None) -> dict[str, Any]:
    """Reorder the pending entries among their own positions; finished entries keep theirs as history."""
    where = position(where)

    def reorder(entries: list[dict[str, Any]]) -> dict[str, Any]:
        check_revision(entries, expected_revision)
        row = pending_entry(entries, item)
        rows = [entry for entry in entries if entry.get("status") == "pending"]
        slots = [entry.get("position") for entry in rows]
        now = rows.index(row)
        target = {"top": 0, "up": now - 1, "down": now + 1}[where] if where in PLACES else int(where) - 1
        rows.insert(max(0, min(target, len(rows) - 1)), rows.pop(now))
        for entry, slot in zip(rows, slots, strict=True):
            entry["position"] = slot
        return {"item": item, "position": rows.index(row) + 1, "pending": [entry.get("item") for entry in rows]}
    return update(queue_for(root, environ), reorder)


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
    return update(queue_for(root, environ), toggle_hold)


def import_id(host: str, path: pathlib.Path, row: dict[str, Any]) -> str:
    """The fixed id of an imported file entry, so a second pass skips what the first one wrote."""
    seed = json.dumps([host, str(path), row.get("item"), row.get("enqueued_at")])
    return f"import-{hashlib.sha256(seed.encode()).hexdigest()[:16]}"


def file_text(name: Any) -> str | None:
    try:
        return pathlib.Path(str(name)).read_text(encoding="utf-8") if name else None
    except (OSError, ValueError):
        return None


def imported_row(queue: Queue, path: pathlib.Path, old: dict[str, Any], host: str) -> dict[str, Any]:
    """A file entry as a row, by the rules in "Migration" of the sd:3174 design; no publish yet."""
    row = {key: value for key, value in old.items() if key not in ("body_file", "acceptance_file", "runner_pid")}
    worktree = pathlib.Path(str(old.get("worktree") or ""))
    branch = old.get("branch") or (lane_git(worktree, "branch", "--show-current") if worktree.is_dir() else None)
    row.update(id=import_id(host, path, old), repository=queue.repository, branch=branch or None,
               body=file_text(old.get("body_file")), acceptance=file_text(old.get("acceptance_file")),
               enqueued_on=host, imported_from=str(path), imported_body_file=old.get("body_file"))
    if any(key in old for key in ("prepare_log", "merge_log")):
        row["log_host"] = host
    status, now = old.get("status"), stamp_now()
    if status == "running":  # no runner holds the lock, so the one that claimed it died
        row.update(status="failed", step="runner", finished_at=now, reclaimed_by=os.getpid(),
                   reason=f"runner pid {old.get('runner_pid')} died with the entry running; a merge may have landed, "
                          "so read its logs and pull request before enqueueing it again")
    elif status == "pending" and not row["branch"]:
        row.update(status="failed", code="no_branch", finished_at=now,
                   reason="no branch and no worktree to read one from; queue it with `sd-ship lane enqueue`")
    elif status == "pending" and (row["body"] is None or (old.get("acceptance_file") and row["acceptance"] is None)):
        row.update(status="failed", code="no_body", finished_at=now,
                   reason="its body or acceptance file is gone; enqueue it again with --body-file")
    return row


def import_file_queue(root: pathlib.Path, queue: Queue, *, runner_locked: bool = False) -> dict[str, Any]:
    """Move this host's queue file, from an earlier version, into the hub database once (sd:3282).

    Under the runner lock, never waited for, and the file's own lock, which an
    older `sd-ship` takes to append. Pending entries are published first; an
    unknown answer stops the import and keeps the file. Then one transaction
    writes a row per entry, in file order, under a fixed id that a rerun
    skips. Then the file is renamed, its bytes kept, and the body copies the
    committed rows name are deleted; any other body stays, since an older
    enqueue may have copied it before its queue write. What happened, or {}.
    """
    path = queue_path(root, queue.environ)
    report: dict[str, Any] = {}
    if path.exists():
        with contextlib.nullcontext(True) if runner_locked else runner_lock(queue) as held:
            report = import_locked(root, queue, path) if held else {"skipped": "a runner holds the lock; the next pass imports"}
    bodies = queue.lane / "bodies"
    if bodies.is_dir() and any(bodies.iterdir()):
        drop_imported_bodies(queue)
    return report


def import_locked(root: pathlib.Path, queue: Queue, path: pathlib.Path) -> dict[str, Any]:
    host = this_host()
    with queue_lock(path):
        try:
            old = json.loads(path.read_text(encoding="utf-8")).get("entries")
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, AttributeError) as error:
            return {"stopped": f"cannot read {path}: {error}"}
        if not isinstance(old, list):
            return {"stopped": f"{path} holds no entry list"}
        present = {row["id"]: row for row in read_queue(queue)}
        active = {row.get("item") for row in present.values() if row.get("status") in ("pending", "running")}
        rows = [imported_row(queue, path, entry, host) for entry in old if isinstance(entry, dict)]
        for row in rows:
            if row["status"] != "pending" or row["id"] in present or row.get("item") in active:
                continue
            try:
                found = publish_head(root, str(row["branch"]), str(row.get("expected_head")))
            except LaneError as error:
                return {"stopped": f"sd:{row.get('item')}: {error}", "file": str(path)}
            if found is not None:
                fix = ("enqueue it again from a feature branch" if found == DEFAULT_BRANCH
                       else "`sd-ship lane retry` publishes it once the branch is fixed")
                row.update(status="skipped", code=found, finished_at=stamp_now(),
                           reason=f"{found}: {row.get('expected_head')} could not be published to "
                                  f"origin/{row['branch']}; {fix}")

        def write(entries: list[dict[str, Any]]) -> list[Any]:
            ids = {entry["id"] for entry in entries}
            queued = {entry.get("item") for entry in entries if entry.get("status") in ("pending", "running")}
            top = max((int(entry.get("position") or 0) for entry in entries), default=0)
            written = []
            for row in rows:
                if row["id"] in ids:
                    continue
                if row["status"] == "pending" and row.get("item") in queued:
                    row.update(status="cancelled", code="duplicate_on_import", finished_at=stamp_now(),
                               reason=f"sd:{row.get('item')} is already queued in the shared queue")
                queued |= {row.get("item")} if row["status"] in ("pending", "running") else set()
                top += 1
                entries.append({**row, "position": top})
                written.append(row.get("item"))
            return written
        written = update(queue, write)
        kept = path.with_name(f"queue.json.imported-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
        for count in range(2, 1000):  # a second file in the same second must not replace the first one's bytes
            if not kept.exists():
                break
            kept = kept.with_name(f"{kept.name.split('~')[0]}~{count}")
        path.rename(kept)
    drop_imported_bodies(queue)
    return {"imported": written, "file": str(path)}


def drop_imported_bodies(queue: Queue) -> None:
    """Delete each body copy an imported row names, under this lane's `bodies/` only; other files there stay."""
    bodies = queue.lane / "bodies"
    for row in read_queue(queue):
        named = pathlib.Path(str(row.get("imported_body_file") or ""))
        if named.parent == bodies:
            named.unlink(missing_ok=True)


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


def blocker_code(answer: dict[str, Any]) -> str | None:
    """The code of the blocker `sd-ship` answered with, or None."""
    return ((answer.get("workflow") or {}).get("blocker") or {}).get("code")


def answered_hub_fault(answer: dict[str, Any]) -> bool:
    """Whether `sd-ship` answered with a hub fault, which the next run retries (sd:3239)."""
    return blocker_code(answer) == sd_ship_workflow.HUB_UNAVAILABLE


def process(entry: dict[str, Any], queue: Queue, ship: Ship, advance: Callable[[], None]) -> dict[str, Any]:
    """One entry, start to end; the fields to record on it.

    The body and acceptance texts go to private temporary files for prepare.
    `advance` is the before-merge write (`step: merge`); it raises `Stop`
    when the claim is lost or the hub stays down, and no merge starts.
    """
    worktree, item, logs = pathlib.Path(entry["worktree"]), entry["item"], queue.lane / "logs"
    if not at_head(worktree, entry["expected_head"]):
        return {"status": "skipped", "code": HEAD_MOVED, "reason": "the worktree's HEAD moved from the queued head"}
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    prepare_log = logs / f"prepare-{item}-{stamp}.log"
    with tempfile.TemporaryDirectory(prefix="sd-lane-texts-") as private:  # 0700, removed with the step
        body = pathlib.Path(private) / "body.md"
        body.write_text(str(entry.get("body") or ""), encoding="utf-8")
        claim = [f"--{entry['claim']}"]
        if isinstance(entry.get("acceptance"), str):
            (pathlib.Path(private) / "acceptance.md").write_text(entry["acceptance"], encoding="utf-8")
            claim += ["--acceptance-file", str(pathlib.Path(private) / "acceptance.md")]
        argv = ["-C", str(worktree), "prepare", "--item", str(item), *claim, "--catch-up",
                "--title", entry["title"], "--body-file", str(body), "--json"]
        prepared = ship(argv, prepare_log)
        # sd:3037. An incomplete review gets the one retry an operator would give it, and no second.
        if blocker_code(prepared) == "review_incomplete":
            prepare_log = logs / f"prepare-{item}-{stamp}-retry.log"
            prepared = ship([*argv, "--retry-review"], prepare_log)
    fields: dict[str, Any] = {"prepare_log": str(prepare_log), "log_host": this_host(), "head": prepared.get("head")}
    if not (prepared.get("ok") and prepared.get("phase") == "ready_to_send"):
        return {**fields, "status": "failed", "step": "prepare", "phase": prepared.get("phase"),
                "reason": str(prepared.get("error") or prepared.get("code") or "prepare did not reach ready_to_send")[:600],
                **({"hub_fault": True} if answered_hub_fault(prepared) else {})}
    refused = merge_refusal(entry)
    if refused is not None:
        return {**fields, "status": "prepared", **refused}
    advance()
    merge_log = logs / f"merge-{item}-{stamp}.log"
    merged = ship(["-C", str(worktree), "merge", "--item", str(item), "--expected-head", str(prepared.get("head")),
                   "--manual", "--watch", "--wait-seconds", str(MERGE_WAIT_SECONDS), "--json"], merge_log)
    fields["merge_log"] = str(merge_log)
    if blocker_code(merged) == LANE_ELSEWHERE:
        return {**fields, "moved": str(merged.get("error") or "the lane moved")[:600]}  # a move, not a failure
    if not (merged.get("ok") and merged.get("phase") == "merged"):
        return {**fields, "status": "failed", "step": "merge", "phase": merged.get("phase"),
                "reason": str(merged.get("error") or merged.get("code") or "merge did not confirm")[:600],
                **({"hub_fault": True} if answered_hub_fault(merged) else {})}
    return {**fields, "status": "merged", "merge_commit": merged.get("merge_commit")}


class SpeculativeGate(threading.Thread):
    """A speculative gate's thread, which a stopped run cancels (sd:3361).

    The gate's `sd-check` runs as a process group's leader; `started` records
    that group while it runs. `cancel_gate` ends the group and waits a bounded time,
    so a stopped run frees its runner lock instead of waiting on the check. A
    group that starts after the cancel is ended at once.
    """

    def __init__(self, target: Callable[[], None], name: str) -> None:
        super().__init__(target=target, name=name)
        self.cancelled = False
        self.group: int | None = None
        self.guard = threading.Lock()

    def started(self, group: int | None) -> None:
        with self.guard:
            self.group = group
            if self.cancelled and group is not None:
                end_group(group, signal.SIGTERM)

    def cancel_gate(self) -> bool:
        """End the gate's group, SIGTERM then SIGKILL, each followed by `CANCEL_SECONDS`; whether the gate ended."""
        for number in (signal.SIGTERM, signal.SIGKILL):
            with self.guard:
                self.cancelled = True
                if self.group is not None:
                    end_group(self.group, number)
            self.join(CANCEL_SECONDS)
            if not self.is_alive():
                return True
        return False


def end_group(group: int, number: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):  # already gone
        os.killpg(group, number)


def gate_run() -> Any:
    """`sd_gate_run.run_child` that tells the speculative gate running it about its group (sd:3361)."""
    import sd_gate_run  # noqa: PLC0415 -- the gate loads only for a speculation
    current = threading.current_thread()
    hook = current.started if isinstance(current, SpeculativeGate) else None
    return functools.partial(sd_gate_run.run_child, started=hook)


def default_gate(root: pathlib.Path, head: str, base: str) -> dict[str, Any]:
    """`sd gate check`'s run at `head` against `base`, which leaves the receipt prepare reads."""
    import sd_gate_run  # noqa: PLC0415 -- the gate loads only for a speculation
    library = sd_lib.import_sd_db().module
    if library is None:
        raise LaneError("no sd_db library, so a pass would leave no receipt")
    return sd_gate_run.check_in_worktree(root, head, base=base, database=library.default_path(os.environ.get("HOME")),
                                         run=gate_run(), slot_timeout=sd_lib.GATE_SLOT_SECONDS)


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


def speculate(entry: dict[str, Any], queue: Queue, gate: Gate, busy: bool = False) -> SpeculativeGate | None:
    """Start the next entry's gate on `entry`'s predicted landing, or None.

    An entry the runner may not merge (`merge_refusal`) stops prepared and
    never lands, so nothing follows it to predict. `busy` says an earlier
    speculative gate still runs; one at a time. Either entry with no
    worktree of its own on this host gets no gate (sd:3283). What happened
    goes on the next entry as `speculation`, and the gate's whole result to
    a log beside the others.
    """
    host = this_host()
    following = next((row for row in read_queue(queue) if runnable(row)), None)
    if following is None or merge_refusal(entry) is not None:
        return None

    def record_speculation(fields: dict[str, Any]) -> None:
        def on_follower(entries: list[dict[str, Any]]) -> None:
            for row in entries:
                if row["id"] == following["id"]:
                    row["speculation"] = {"after": entry["item"], **fields}
        with contextlib.suppress(LaneError, OSError):  # a note that cannot be written stops nothing
            update(queue, on_follower)
    def own_tree_here(row: dict[str, Any]) -> bool:
        return row.get("enqueued_on") == host and pathlib.Path(str(row.get("worktree") or "")).is_dir()
    try:
        plan = ({"skipped": "an earlier speculative gate still runs"} if busy else
                {"skipped": f"no worktree on this host for sd:{entry['item']} or sd:{following['item']}; "
                            "a lane worktree is made only when its entry runs"}
                if not (own_tree_here(entry) and own_tree_here(following)) else predict(entry, following))
    except Exception as error:  # a speculation that cannot be set up gates nothing; the lane goes on
        plan = {"skipped": f"{type(error).__name__}: {error}"[:600]}
    if "skipped" in plan:
        record_speculation({"status": "skipped", "reason": plan["skipped"]})
        return None
    log = queue.lane / "logs" / f"speculate-{following['item']}-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}.log"
    record_speculation({"status": "running", **plan, "log": str(log), "log_host": this_host()})

    def run_gate() -> None:
        try:
            result = gate(pathlib.Path(following["worktree"]), plan["head"], plan["base"])
            fields = {"status": result.get("status"), "summary": str(result.get("summary"))[:300],
                      "receipt": "recorded" if result.get("receipt_revision") is not None else
                      result.get("receipt_skipped") or result.get("receipt_error") or "none"}
        except Exception as error:
            result = fields = {"status": "error", "reason": f"{type(error).__name__}: {error}"[:600]}
        if thread.cancelled:
            fields = {"status": "cancelled", "reason": "the run stopped, so it ended this gate (sd:3361)"}
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        record_speculation({**plan, "log": str(log), "log_host": this_host(), **fields})
    thread = SpeculativeGate(run_gate, f"sd-lane-speculate-{following['item']}")
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
    if entry.get("lane_worktree"):
        done.append(f"the lane worktree {worktree} is removed with its entry")
        return "Cleanup: " + ", ".join(done), None
    remove = f"git -C {main} worktree remove {worktree} && git -C {main} update-ref -d refs/heads/{branch} {tip}"
    done.append(f"worktree {worktree} and branch {branch} kept on {this_host()} for removal once the builder stops")
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
    kept, where = entry.get("builder_worktree"), f" on {entry.get('builder_host')}"
    if entry.get("lane_worktree") and kept:  # the builder's own worktree, on the host that enqueued it (sd:3283)
        cleanup, remove = f"{cleanup}; the builder worktree {kept} stays{where}", f"git -C {kept} worktree remove {kept}"
    fields = {"cleanup": cleanup, "remove": remove}
    body = f"Landed: merged at {merged[:12]} (head {str(head)[:12]}). {cleanup}."
    if branch and tip:
        body += f" Recover: git branch {branch} {tip}."
    if remove:
        body += f" Remove{where if entry.get('lane_worktree') else ''}: {remove}"  # last and bare, so it copies whole
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


def lane_host_reason(root: pathlib.Path, environ: dict[str, str] | None = None) -> str | None:
    """Why this machine does not run `root`'s lane, or None on its lane host (sd:3003).

    `sd_lib.lane_elsewhere` reads `repo.lane_host` on a connection opened for
    this read. Without `sd_db` there is no database and no other host. A
    checkout whose origin names no GitHub repository matches no row, so only
    the hub hosts it. A database that does not open refuses `hub_unavailable`
    (sd:3282); rows that disagree, or a read fault, refuse `lane_unknown`:
    uncertain ownership never reads as the hub's.
    """
    if sd_lib.import_sd_db().module is None:
        return None
    import sd_gate_receipts  # noqa: PLC0415
    from sd_db.database import connect  # noqa: PLC0415
    from sd_db.protection import github_slug  # noqa: PLC0415

    try:
        database = hub_database(environ if environ is not None else dict(os.environ))
        found = github_slug(lane_git(sd_lib.main_worktree_root(root), "config", "--get", "remote.origin.url"))
        if found is None:
            served = sd_gate_receipts.served_hub(database)
            return None if served is None else f"The lane for {root.name} runs on the hub {served}, not on this machine."
    except Exception as error:  # noqa: BLE001 -- every fault is "cannot tell", which refuses
        raise LaneError(f"Cannot read the lane host for {root}: {error}. Nothing was changed; "
                        "retry when the database answers.", code="lane_unknown") from None
    try:
        connection = connect(database, write=False)
    except Exception as error:  # noqa: BLE001 -- the hub is down: every lane verb refuses the same way
        raise LaneError(f"The hub database did not answer: {type(error).__name__}: {error}. Nothing was changed; "
                        "retry when the hub answers.", code=HUB_UNAVAILABLE) from None
    try:
        return sd_lib.lane_elsewhere(connection, database, "/".join(found))
    except Exception as error:  # noqa: BLE001 -- `LaneUnknown`, or a read fault it did not wrap
        raise LaneError(str(error), code=getattr(error, "code", None) or "lane_unknown") from None
    finally:
        connection.close()


def refuse_elsewhere(root: pathlib.Path, environ: dict[str, str] | None = None) -> None:
    """Refuse `lane run` off `root`'s lane host, before it reads or writes the queue (sd:3003).

    Only `run` is host-bound: the other verbs edit the shared queue from any host (sd:3283).
    """
    elsewhere = lane_host_reason(root, environ)
    if elsewhere is not None:
        raise LaneError(elsewhere, code=LANE_ELSEWHERE)


def host_check(queue: Queue) -> Callable[[Any], None]:
    """A `check` for `update` that refuses unless this machine runs the lane, read in the write's transaction."""
    def on_lane_host(connection: Any) -> None:
        try:
            elsewhere = sd_lib.lane_elsewhere(connection, hub_database(queue.environ), queue.repository)
        except Exception as error:  # noqa: BLE001 -- `LaneUnknown`, or a read fault it did not wrap
            raise LaneError(str(error), code=getattr(error, "code", None) or "lane_unknown") from None
        if elsewhere is not None:
            raise LaneError(elsewhere, code=LANE_ELSEWHERE)
    return on_lane_host


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
    """Settle each `running` entry whose holder on this machine died (sd:2821, sd:3282), by `reclaim`.

    Called with this machine's runner lock held, so no runner here is live;
    the holder's pid must also be gone, which a reused pid only makes wait.
    A pid that cannot be read keeps the entry `running`. A holder on another
    machine is left to its lease.
    """
    host = this_host()
    return [reclaim(row) for row in entries if row.get("status") == "running"
            and (row.get("holder") or {}).get("host") == host and not runner_alive(row["holder"].get("pid"))]


def held(entries: list[dict[str, Any]], entry: dict[str, Any], token: str) -> dict[str, Any]:
    """The running row `entry` names, while its holder is still `token`; else the claim is lost."""
    for row in entries:
        if row["id"] == entry["id"] and row.get("status") == "running" and (row.get("holder") or {}).get("token") == token:
            return row
    raise Stop(f"sd:{entry['item']}'s claim was reclaimed or released; this runner writes nothing more for it "
               "and stops", code=CLAIM_LOST)


def claim_entry(queue: Queue, token: str, reclaimed: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Take the first pending entry not held, by position, under a new holder; None when none.

    One transaction reads the lane host and claims, so a move is before the
    claim or after it. It refuses while another entry of the repository
    runs. A holder on another host is dead once its `lease_until` passed: it
    is reclaimed (`reclaim`) and listed in `reclaimed` (sd:3283). A retried
    claim that finds its own token running landed before.
    """
    found: list[dict[str, Any]] = []

    def claim_first(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
        host = this_host()
        found.clear()
        for row in entries:
            if row.get("status") != "running":
                continue
            holder = row.get("holder") or {}
            if holder.get("token") == token:
                return dict(row)
            if holder.get("host") != host and lease_passed(row):
                found.append(reclaim(row))
                continue
            raise LaneError(f"sd:{row.get('item')} is running under {holder.get('host')} pid {holder.get('pid')}; "
                            "one entry of a repository runs at a time", code="lane_busy")
        for row in entries:
            if runnable(row):
                row.update(status="running", started_at=stamp_now(), step="prepare",
                           holder={"host": host, "pid": os.getpid(), "token": token},
                           lease_until=stamp_at(time.time() + 2 * PREPARE_SECONDS))
                return dict(row)
        return None
    claimed = runner_write(queue, claim_first, check=host_check(queue))
    if reclaimed is not None:  # only once the claim's transaction landed
        reclaimed.extend(found)
    return claimed


class Moved(Stop):
    """The lane moved to another host before the merge; the entry is pending again at its place (sd:3283)."""


def advance(queue: Queue, entry: dict[str, Any], token: str) -> None:
    """The before-merge write: `step: merge` and the merge lease, while `token` holds the entry on the lane host.

    The host is read in the write's transaction. Off it the entry goes back
    to pending at its place with `moved_off`, and `Moved` stops the run; a
    host that cannot be read stops it too, and reclaim settles the entry.
    """
    expected = pushed_catch_up(pathlib.Path(entry["worktree"]), str(entry.get("branch") or ""), entry["expected_head"])
    elsewhere: list[str] = []

    def read_host(connection: Any) -> None:
        try:
            found = sd_lib.lane_elsewhere(connection, hub_database(queue.environ), queue.repository)
        except Exception as error:  # noqa: BLE001 -- `LaneUnknown`, or a read fault it did not wrap
            raise Stop(f"Cannot read the lane host before the merge: {error}. No merge started; the next run "
                       "settles the entry.", code="lane_unknown") from None
        elsewhere[:] = [found] if found else []

    def to_merge(entries: list[dict[str, Any]]) -> None:
        row = held(entries, entry, token)
        if elsewhere:
            back_to_pending(row, expected, moved_off={"host": this_host(), "at": stamp_now()})
        else:
            row.update(step="merge", lease_until=stamp_at(time.time() + MERGE_SECONDS + LANDING_SECONDS))
    runner_write(queue, to_merge, check=read_host)
    if elsewhere:
        raise Moved(f"{elsewhere[0]} sd:{entry['item']} is pending again at its place, for that host.",
                    code=LANE_ELSEWHERE)


def finish_entry(queue: Queue, entry: dict[str, Any], token: str, outcome: dict[str, Any]) -> None:
    """Record a run entry's outcome while `token` holds it; a retry that finds its own outcome is done."""
    def mark_finished(entries: list[dict[str, Any]]) -> None:
        row = next((row for row in entries if row["id"] == entry["id"]), {})
        if (row.get("holder") or {}).get("token") == token and row.get("status") != "running":
            if row.get("status") == outcome.get("status"):
                return  # an earlier try landed unseen
        held(entries, entry, token).update(outcome, finished_at=stamp_now())
        row.pop("lease_until", None)
    runner_write(queue, mark_finished)


def read_git(tree: pathlib.Path, *args: str, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    """`git <args>` in `tree` for a runner decision; a failure raises `PUBLISH_UNKNOWN`, never a "no"."""
    done = publish_git(tree, *args)
    if done is None or done.returncode not in ok:
        said = (done.stderr or done.stdout).strip()[-300:] if done is not None else "no answer"
        raise LaneError(f"git {args[0]} failed in {tree} ({said}); the entry is not skipped.", code=PUBLISH_UNKNOWN)
    return done


def catch_up_of(tree: pathlib.Path, commit: str, expected: str) -> bool:
    """Whether `commit` is prepare's catch-up of `expected`, or a chain of them (sd:3283).

    Prepare's catch-up is `git merge --no-ff origin/<default branch>`, and a
    conflict aborts it, so each link must be just that: a merge whose second
    parent is on `origin`'s default branch and whose tree is the clean merge
    of its parents. A merge of anything else, or one with edits of its own, is
    scope no review saw, so the entry skips `HEAD_MOVED`. Each prepare that
    pushed a catch-up and was then put back or reclaimed adds a link, so the
    chain is at most `CATCH_UPS` long. A read that fails raises `PUBLISH_UNKNOWN`.
    """
    default: list[str] = []
    for _ in range(CATCH_UPS if commit != expected else 0):
        parents = read_git(tree, "rev-list", "--parents", "-n", "1", commit).stdout.split()[1:]
        if len(parents) != 2 or not clean_merge(tree, commit, *parents) or not landed(tree, parents[1], default):
            return False
        if parents[0] == expected:
            return True
        commit = parents[0]
    return False


def clean_merge(tree: pathlib.Path, commit: str, first: str, second: str) -> bool:
    """Whether `commit`'s tree is what git's merge of `first` and `second` makes, with no conflict and no edit."""
    merged = read_git(tree, "merge-tree", "--write-tree", first, second, ok=(0, 1))
    return merged.returncode == 0 and merged.stdout.split()[:1] == [read_git(tree, "rev-parse", f"{commit}^{{tree}}").stdout.strip()]


def landed(tree: pathlib.Path, commit: str, default: list[str]) -> bool:
    """Whether `commit` is on `origin`'s default branch; `default` keeps its tip, read once per check."""
    if not default:
        listed = [line.split("\t") for line in read_git(tree, "ls-remote", "--symref", "origin", "HEAD").stdout.splitlines()]
        name = next((ref.removeprefix("ref: refs/heads/") for ref, *rest in listed
                     if rest == ["HEAD"] and ref.startswith("ref: refs/heads/")), None)
        tip = next((ref for ref, *rest in listed if rest == ["HEAD"] and not ref.startswith("ref: ")), None)
        if not name or not tip:
            raise LaneError(f"origin advertised no default branch to {tree}; the entry is not skipped.",
                            code=PUBLISH_UNKNOWN)
        if read_git(tree, "rev-parse", "--verify", "--quiet", f"{tip}^{{commit}}", ok=(0, 1)).returncode != 0:
            read_git(tree, "fetch", "-q", "--no-tags", "origin", f"+refs/heads/{name}:refs/remotes/origin/{name}")
        default.append(tip)
    return read_git(tree, "merge-base", "--is-ancestor", commit, default[0], ok=(0, 1)).returncode == 0


def caught_up(worktree: pathlib.Path, expected: str) -> str:
    """`expected`, or the worktree's HEAD when that is prepare's catch-up of it.

    A retried entry starts there (sd:3239, sd:3254); any other move of HEAD
    still skips the entry. A read that fails raises `PUBLISH_UNKNOWN`.
    """
    head = read_git(worktree, "rev-parse", "HEAD").stdout.strip()
    return head if catch_up_of(worktree, head, expected) else expected


def at_head(tree: pathlib.Path, expected: str) -> bool:
    """Whether `tree`'s HEAD is `expected` or its catch-up merge, the heads the runner prepares."""
    head = read_git(tree, "rev-parse", "HEAD").stdout.strip()
    return head == expected or catch_up_of(tree, head, expected)


def pushed_catch_up(tree: pathlib.Path, branch: str, expected: str) -> str:
    """`origin/<branch>` when it is the catch-up merge of `expected` that prepare pushed, else `expected` (sd:3283).

    A put-back reads `origin` only for this, so `expected_head` always names a
    published commit. A catch-up only in the worktree, or a read that fails,
    keeps `expected`; this host's worktree rule (`checkout_for`) accepts that
    catch-up.
    """
    listed = publish_git(tree, "ls-remote", "origin", f"refs/heads/{branch}") if branch else None
    tip = (listed.stdout.split() or [""])[0] if listed is not None and listed.returncode == 0 else ""
    try:
        return tip if tip and catch_up_of(tree, tip, expected) else expected
    except LaneError:  # unknown keeps the published head
        return expected


def back_to_pending(row: dict[str, Any], expected: str, **fields: Any) -> None:
    """A running row back to pending at its place, its holder gone; `fields` say why."""
    for key in ("started_at", "holder", "step", "lease_until"):
        row.pop(key, None)
    row.update(status="pending", expected_head=expected, **fields)


def put_back(queue: Queue, entry: dict[str, Any], token: str, expected: str, **fields: Any) -> None:
    """`back_to_pending` while `token` still holds the entry: a move, a hub fault, or an `origin` that did not answer."""
    runner_write(queue, lambda entries: back_to_pending(held(entries, entry, token), expected, **fields))


def worktrees(main: pathlib.Path) -> list[tuple[pathlib.Path, str]]:
    """Each worktree of the repository on this disk, with the branch it has checked out, or ''."""
    found: list[tuple[pathlib.Path, str]] = []
    for line in read_git(main, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            found.append((pathlib.Path(line.removeprefix("worktree ")), ""))
        elif line.startswith("branch refs/heads/") and found:
            found[-1] = (found[-1][0], line.removeprefix("branch refs/heads/"))
    return found


def drop_lane_worktree(main: pathlib.Path, tree: pathlib.Path, branch: str | None) -> None:
    """Remove a worktree the lane made under its folder, and `branch` with it; no builder writes there."""
    publish_git(main, "worktree", "remove", "--force", str(tree))
    publish_git(main, "worktree", "prune")
    if branch:
        publish_git(main, "branch", "-D", branch)


def skip(code: str, reason: str) -> dict[str, Any]:
    return {"status": "skipped", "code": code, "reason": reason}


def checkout_for(root: pathlib.Path, queue: Queue, entry: dict[str, Any]) -> dict[str, Any]:
    """Where this host runs `entry` (sd:3283): `{"tree"}`, with `made` for a lane worktree, or a skip's fields.

    In order: the entry's own worktree, when it was enqueued here; any
    worktree here with its branch at the head; else a lane worktree at
    `<lane folder>/worktrees/<item>` from the fetched `origin/<branch>`
    (`lane_tree`). The head is `expected_head` or its catch-up merges (`catch_up_of`). A
    `gate: satellite` entry of the retired hand-off is skipped (sd:3003).
    """
    expected, branch = str(entry.get("expected_head")), str(entry.get("branch") or "")
    if entry.get("gate") == "satellite":
        return skip("retired_hand_off", "a satellite hand-off entry an older version queued; enqueue it again")
    if not branch:  # nothing to fetch, now or on a later run
        return {"status": "failed", "code": "no_branch", "reason": "the entry names no branch; queue it with "
                                                                    "`sd-ship lane enqueue`"}
    own = pathlib.Path(str(entry.get("worktree") or ""))
    if entry.get("enqueued_on") == this_host() and own.is_dir() and at_head(own, expected):
        return {"tree": own}
    main, lane = sd_lib.main_worktree_root(root), queue.lane / "worktrees" / str(entry["item"])
    listed = worktrees(main)
    for path, name in listed:
        if branch and name == branch and path.is_dir() and at_head(path, expected):
            mine = path.resolve() == lane.resolve()  # a killed run's lane worktree at the head: reused, then removed
            return {"tree": path, **({"made": True, "branch_made": name} if mine else {})}
    return lane_tree(main, lane, branch, expected, listed)


def fetched_tip(main: pathlib.Path, branch: str) -> str:
    """`origin/<branch>`'s tip, fetched into `refs/remotes/origin/<branch>`, or '' when `origin` has no such branch.

    A failed read or fetch raises `PUBLISH_UNKNOWN`: the branch may be there.
    """
    ref = f"refs/heads/{branch}"
    read = publish_git(main, "ls-remote", "origin", ref) if branch else None
    if read is None or read.returncode != 0:
        raise LaneError(f"Cannot read origin/{branch}: git ls-remote failed; the entry is not skipped.",
                        code=PUBLISH_UNKNOWN)
    tip = (read.stdout.split() or [""])[0]
    fetched = publish_git(main, "fetch", "-q", "--no-tags", "origin", f"+{ref}:refs/remotes/origin/{branch}") if tip else None
    if tip and (fetched is None or fetched.returncode != 0):
        raise LaneError(f"Cannot fetch origin/{branch}; the entry is not skipped.", code=PUBLISH_UNKNOWN)
    return tip


def lane_tree(main: pathlib.Path, lane: pathlib.Path, branch: str, expected: str,
              listed: list[tuple[pathlib.Path, str]]) -> dict[str, Any]:
    """A lane worktree at `lane` from the fetched `origin/<branch>`, or a skip; raises `PUBLISH_UNKNOWN`.

    A lane worktree a killed run left at another head is the lane's own, so
    it goes with its branch. No `origin/<branch>` is `HEAD_GONE`; a tip past
    the head and its catch-up is `HEAD_MOVED`; a local branch at another
    commit, or one checked out elsewhere, is `BRANCH_BUSY`. A failed read or
    fetch of `origin` is unknown, not a skip.
    """
    for path, name in listed:
        if path.resolve() == lane.resolve():
            drop_lane_worktree(main, path, name or None)
    listed = [(path, name) for path, name in listed if path.resolve() != lane.resolve()]
    if lane.exists():  # the lane's own folder, which git no longer lists: a killed run's, kept aside, never deleted
        lane.rename(lane.with_name(f"{lane.name}.stale-{entry_id()}"))
    ref, tip = f"refs/heads/{branch}", fetched_tip(main, branch)
    if not tip:
        return skip(HEAD_GONE, f"origin/{branch} is gone; `sd-ship lane retry` publishes {expected} again from "
                               "a checkout that has it")
    if tip != expected and not catch_up_of(main, tip, expected):
        return skip(HEAD_MOVED, f"origin/{branch} is at {tip}, neither the queued head {expected} nor its catch-up")
    local = read_git(main, "rev-parse", "--verify", "--quiet", ref, ok=(0, 1)).stdout.strip()
    if local and (local != tip or any(name == branch for _, name in listed)):
        return skip(BRANCH_BUSY, f"the local branch {branch} is at {local}, or checked out at another head; "
                                 "remove it, or retry from a worktree at the head")
    lane.parent.mkdir(parents=True, exist_ok=True)
    made = publish_git(main, "worktree", "add", "-q", *([str(lane), branch] if local else
                       ["--track", "-b", branch, str(lane), f"refs/remotes/origin/{branch}"]))
    if made is None or made.returncode != 0:
        raise LaneError(f"Cannot make the lane worktree {lane}: {(made.stderr if made else 'no answer')[-300:]}")
    return {"tree": lane, "made": True, "branch_made": None if local else branch}


def requeue(queue: Queue, entry: dict[str, Any], token: str, outcome: dict[str, Any]) -> bool:
    """Put a running entry back as pending after a hub fault, or False once its retries are spent (sd:3239).

    It keeps its place, and `hub_fault` says what failed where; a later
    outcome writes its own fields beside it. Its `expected_head` moves only
    to a catch-up merge prepare pushed (`pushed_catch_up`, sd:3283).
    """
    retries = int(entry.get("hub_retries") or 0)
    if not outcome.pop("hub_fault", False) or retries >= HUB_RETRIES:
        return False
    expected = pushed_catch_up(pathlib.Path(entry["worktree"]), str(entry.get("branch") or ""), entry["expected_head"])
    fault: dict[str, Any] = {key: outcome[key] for key in ("step", "reason", "prepare_log", "merge_log", "log_host")
                             if key in outcome}
    put_back(queue, entry, token, expected, hub_retries=retries + 1, hub_fault={**fault, "at": stamp_now()})
    return True


def settle_checkout(root: pathlib.Path, queue: Queue) -> dict[str, Any]:
    """Under the runner lock already held: import the file queue, then reclaim dead holders; what happened."""
    imported = import_file_queue(root, queue, runner_locked=True)
    reclaimed = runner_write(queue, reclaim_dead)
    return {**({"import": imported} if imported else {}), **({"reclaimed": reclaimed} if reclaimed else {})}


def clock() -> float:
    """The run budget's clock; a suite replaces it."""
    return time.monotonic()


def run_lane(root: pathlib.Path, environ: dict[str, str], ship: Ship = default_ship,
             gate: Gate = default_gate, note: Note | None = None, deadline: float | None = None) -> dict[str, Any]:
    """Drain this repository's queue in order under its runner lock; never wait for the lock.

    It first imports the file queue and reclaims dead holders here
    (`settle_checkout`). One speculative gate runs at a time (`speculate`);
    after a merge the runner lands the entry (`land`), then waits for that
    gate, so the next prepare finds its receipt. `note` defaults to
    `default_note`, read at the call, so a suite can replace it. Off the lane
    host it refuses before any of that (sd:3003). Each claim reads the host
    in its own transaction (`claim_entry`): after a move it claims nothing and
    says why in `stopped`. After a hub fault it puts the entry back and stops
    the same way (`requeue`, sd:3239). A runner write it cannot land stops
    the run (`Stop`), and the next run settles the entry. With its lock held
    it tries the lane root once: `other_lanes_idle` holds that root while
    the serving tree or the tools checkout moves, and then the runner runs
    nothing (sd:3273). Once `clock` passes `deadline`, by default
    `RUN_BUDGET_SECONDS` from now, it claims no next entry and says so in
    `stopped`; an entry it started still finishes (sd:3287). A stopped run
    cancels its speculative gate (`SpeculativeGate.cancel_gate`) rather than wait
    on it, and says how that went in `speculative_gate` (sd:3361).
    """
    refuse_elsewhere(root, environ)
    queue = queue_for(root, environ)
    own_lock = queue.lock_file
    with runner_lock(queue) as locked:
        if not locked:
            return {"ran": [], "busy": f"another runner holds {own_lock}"}
        try:
            with lane_root_lock(lane_root(environ), fcntl.LOCK_SH | fcntl.LOCK_NB):
                pass
        except BlockingIOError:
            return {"ran": [], "busy": "the tools this lane runs are moving; the next run retries"}
        ran: list[dict[str, Any]] = []
        answer: dict[str, Any] = {"ran": ran, **settle_checkout(root, queue)}
        ahead: SpeculativeGate | None = None
        deadline = clock() + RUN_BUDGET_SECONDS if deadline is None else deadline
        while True:
            if clock() >= deadline:
                answer["stopped"] = "the run spent its budget; the next run takes the pending entries"
                break
            token, reclaimed = secrets.token_hex(16), list[dict[str, Any]]()
            try:
                entry = claim_entry(queue, token, reclaimed)
            except LaneError as error:  # moved, unknown, busy, or a hub that stayed down
                answer["stopped"], entry = str(error), None
            if reclaimed:
                answer["reclaimed"] = [*answer.get("reclaimed", []), *reclaimed]
            if entry is None:
                break
            if ahead is not None and ahead.is_alive():
                speculate(entry, queue, gate, busy=True)  # notes the skip: one speculative gate at a time
            else:
                ahead = speculate(entry, queue, gate)
            row, stopped = run_entry(root, queue, entry, token, environ, ship, note or default_note)
            if row is not None:
                ran.append(row)
            if stopped is not None:
                answer["stopped"] = stopped
                break
            if ahead is not None and row is not None and row.get("status") == "merged":
                ahead.join(PREPARE_SECONDS)  # the next prepare reads its receipt
        return finish_speculation(ahead, answer)


def finish_speculation(ahead: SpeculativeGate | None, answer: dict[str, Any]) -> dict[str, Any]:
    """`answer` once the speculative gate is done: waited for, or cancelled when the run stopped (sd:3361).

    A stopped run waits on no check, so it frees its runner lock now.
    """
    if ahead is not None and "stopped" in answer:
        answer["speculative_gate"] = ("cancelled" if ahead.cancel_gate() else
                                      f"still ending {2 * CANCEL_SECONDS}s after SIGKILL; the lock is freed anyway")
    elif ahead is not None:
        ahead.join()
    return answer


def run_entry(root: pathlib.Path, queue: Queue, entry: dict[str, Any], token: str, environ: dict[str, str],
              ship: Ship, note: Note) -> tuple[dict[str, Any] | None, str | None]:
    """Find a checkout here (`checkout_for`), then prepare, merge and record one claimed entry.

    Its row for `ran`, and why the run stops, or None. An `origin` that did
    not answer puts the entry back at its place and stops the run. A lane
    worktree the runner made goes once the entry ends, whatever its outcome.
    """
    try:
        found = checkout_for(root, queue, entry)
    except LaneError as error:
        if error.code == PUBLISH_UNKNOWN:
            return unknown_checkout(queue, entry, token, error)
        found = {"status": "failed", "step": "worktree", "reason": str(error)[:600]}
    tree = found.pop("tree", None)
    try:
        return run_checkout(root, queue, entry, token, environ, ship, note, tree, found)
    finally:
        if tree is not None and found.get("made"):
            drop_lane_worktree(sd_lib.main_worktree_root(root), tree, found.get("branch_made"))


def unknown_checkout(queue: Queue, entry: dict[str, Any], token: str,
                     error: LaneError) -> tuple[dict[str, Any] | None, str]:
    """Put `entry` back at its place after a git read with no answer, and stop the run: unknown is not a skip."""
    try:
        put_back(queue, entry, token, entry["expected_head"], checkout_fault={"reason": str(error)[:600],
                                                                              "at": stamp_now()})
    except Stop as stop:
        return None, str(stop)
    return {"item": entry["item"], "status": "pending"}, f"sd:{entry['item']}: {error} It is pending again."


def run_checkout(root: pathlib.Path, queue: Queue, entry: dict[str, Any], token: str, environ: dict[str, str],
                 ship: Ship, note: Note, tree: pathlib.Path | None,
                 found: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """`run_entry` in `tree`, or the skip `found` holds when there is none."""
    outcome = found
    try:
        if tree is not None:
            built = {"lane_worktree": True, "builder_worktree": entry.get("worktree"),
                     "builder_host": entry.get("enqueued_on")}
            local = {**entry, "worktree": str(tree), **(built if found.get("made") else {})}
            outcome = process(local, queue, ship, functools.partial(advance, queue, local, token))
            if outcome.get("moved"):
                put_back(queue, entry, token, pushed_catch_up(tree, str(entry.get("branch") or ""),
                                                              entry["expected_head"]),
                         moved_off={"host": this_host(), "at": stamp_now(), "step": "merge"})
                return ({"item": entry["item"], **outcome, "status": "pending"},
                        f"{outcome['moved']} sd:{entry['item']} is pending again at its place, for that host.")
            if requeue(queue, local, token, outcome):
                return ({"item": entry["item"], **outcome, "status": "pending"},
                        f"sd:{entry['item']} met a hub fault in {outcome.get('step')}; "
                        "it is pending again, and the next run retries it")
            outcome.update(settle(local, outcome, environ, note, queue.lock_file, root))
    except Stop as error:
        return None, str(error)
    except LaneError as error:
        if error.code == PUBLISH_UNKNOWN:  # the head check had no answer; prepare has not started
            return unknown_checkout(queue, entry, token, error)
        outcome = {"status": "failed", "reason": f"{type(error).__name__}: {error}"[:600]}
    except Exception as error:  # a broken entry is marked; the next one still runs
        outcome = {"status": "failed", "reason": f"{type(error).__name__}: {error}"[:600]}
    try:
        finish_entry(queue, entry, token, outcome)
    except Stop as error:
        return {"item": entry["item"], **outcome, "recorded": False}, str(error)
    return {"item": entry["item"], **outcome}, None


def run_hosted(environ: dict[str, str], ship: Ship = default_ship, gate: Gate = default_gate,
               note: Note | None = None) -> dict[str, Any]:
    """`lane run --hosted`: `run_lane` for each repository this machine hosts, one after another (sd:3003).

    The same job runs on every machine. Its lanes are the managed `repo` rows,
    in path order, whose checkout is on this disk and whose lane host is this
    machine. Ownership this machine cannot
    read skips that lane with the reason. A held runner lock skips it too
    (`run_lane` answers `busy`), and a refusal in one lane leaves the next to run.
    Every other checkout here, hosted or not, has its file queue imported and
    its dead holders reclaimed under its runner lock (sd:3282). The lanes share
    one run budget, `RUN_BUDGET_SECONDS` from the start (sd:3287).
    """
    deadline = clock() + RUN_BUDGET_SECONDS
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise LaneError(f"lane run --hosted reads the repo table: {imported.problem}")
    from sd_db.database import connect  # noqa: PLC0415
    from sd_db.protection import github_slug  # noqa: PLC0415
    from sd_db.repos import registered  # noqa: PLC0415

    database = hub_database(environ)
    try:
        connection = connect(database, write=False)
        rows = sd_lib.managed_rows(registered(connection))
    except Exception as error:  # noqa: BLE001 -- no list of lanes is no lane to run
        raise LaneError(f"Cannot read the repositories this machine hosts: {error}. Nothing ran; "
                        "the next run retries.", code="lane_unknown") from None
    lanes: list[dict[str, Any]] = []
    hosted: list[tuple[str, pathlib.Path]] = []
    others: list[tuple[str, pathlib.Path]] = []
    try:
        for row in rows:
            found, checkout = github_slug(row["remote"]), sd_lib.repo_disk(row["path"])
            if found is None or not (checkout / ".git").exists():
                continue
            try:
                (hosted if sd_lib.hosts_lane(connection, database, "/".join(found)) else others).append(
                    (row["path"], checkout))
            except Exception as error:  # noqa: BLE001 -- `LaneUnknown` skips this lane; it never runs as the hub's
                lanes.append({"path": row["path"], "skipped": str(error), "code": getattr(error, "code", "lane_unknown")})
                others.append((row["path"], checkout))
    finally:
        connection.close()  # a lane runs for hours; each reads its host again on its own connection
    for path, checkout in others:
        try:
            queue = queue_for(checkout, environ)
            with runner_lock(queue) as locked:
                settled = settle_checkout(checkout, queue) if locked else {}
        except (LaneError, sd_lib.ConfigError, OSError) as error:
            settled = refusal(error)
        if settled:
            lanes.append({"path": path, "settled": settled})
    for path, checkout in hosted:
        try:
            lanes.append({"path": path, **run_lane(checkout, environ, ship, gate, note, deadline)})
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
    retrier = verbs.add_parser("retry", help="queue the item's newest entry again, by enqueue order whatever a move "
                                             "did (sd:3412), when it failed, skipped or stopped prepared, at its "
                                             "head with its body text (sd:3254); a cancelled one needs "
                                             "--expected-head (sd:3389)")
    retrier.add_argument("item", type=int)
    retrier.add_argument("--manual", action="store_true",
                         help="authorize the runner to merge when repo.runner_merge is manual, as enqueue --manual")
    retrier.add_argument("--expected-head", help=f"refuse with {STALE_HEAD} unless the item's newest entry is at "
                                                 "this full commit id, checked in the write's transaction (sd:3268), "
                                                 f"and {SUPERSEDED} after a newer entry; a cancelled entry needs it, "
                                                 f"and refuses {HEAD_MOVED} when its branch moved and "
                                                 f"{ALREADY_MERGED} at a merged head (sd:3389)")
    canceller = verbs.add_parser("cancel", help="mark a pending entry cancelled, or release a stuck running one")
    canceller.add_argument("item", type=int)
    canceller.add_argument("--expected-claim", metavar="TOKEN:STEP",
                           help=f"release only the running claim `lane list` printed, its holder.token and step; "
                                f"else refuse with {STALE_CLAIM}, checked in the write's transaction (sd:3330)")
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
                                                        "this revision, checked in the write's transaction")
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
        imported = {} if args.lane_command == "run" else import_file_queue(root, queue_for(root, environ))
        if args.lane_command == "enqueue":
            result: Any = enqueue_entry(root, args.item, args.title, args.body_file, environ,
                                        expected_head=args.expected_head, manual=args.manual, claim=args.claim,
                                        acceptance_file=args.acceptance_file)
        elif args.lane_command == "list":
            entries = read_queue(queue_for(root, environ))
            result = {"queue": str(queue_path(root, environ)), "revision": queue_revision(entries),
                      "entries": [shown(row) for row in entries], **({"import": imported} if imported else {})}
        elif args.lane_command == "retry":
            result = retry(root, args.item, environ, manual=args.manual, expected_head=args.expected_head)
        elif args.lane_command == "cancel":
            result = cancel(root, args.item, environ, expected_revision=args.expected_revision,
                            expected_claim=args.expected_claim)
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
    return succeed(shown(result))


def refusal(error: Exception) -> dict[str, Any]:
    """A lane command's refusal: its text, and its code when it has one."""
    code = {"code": error.code} if isinstance(error, LaneError) and error.code else {}
    return {"error": str(error), **code}


def succeed(result: Any) -> int:
    print(json.dumps({"ok": True, **(result if isinstance(result, dict) else {"result": result})}, indent=2,
                     sort_keys=True))
    return 0
