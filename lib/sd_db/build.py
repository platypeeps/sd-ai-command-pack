"""The Build queue and its claim, on the retired runner's tables (pack sd:6093).

Design: system `docs/work/2026-10-24-build-dispatcher/design.md`, step 1.

A Build press queues one `assignment` per item: role `author`, lane
`parallel`, scope `build`. A claim takes up to `BUNDLE_MAX` queued builds of
one repository as a bundle: one `runner_run` (the attempt) and one
`runner_lease` on branch `build/sd-<lead>`, every member `running` with its
`parent` the lead, and every item `in_progress`. While an assignment is
queued or running, `workflow.change_status` refuses the item's status writes
(criterion 7.19); a cancel is the way out.

Every write a supervisor makes is a compare-and-set on its own run, open and
unreleased (`write`, `enqueued`), so a late old supervisor writes nothing.
`reap` ends a run that fails `alive` in three steps, each safe to stop after:
the compare-and-set of its outcome, the kill of its builder's process group,
and one transaction that releases it and retries, blocks or cancels. A tick
that dies between them leaves an ended, unreleased run, and the next `reap`
starts at the kill.

Nothing here runs a process but the kill and the liveness probe; the
dispatcher (step 2) reads the load and the interactive builders, which are not
in the database, and passes them in.
"""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import paths, reads
from .database import transaction
from .errors import SdDbError
from .runner import RUNNABLE_KINDS, queue_state, restoration_pending
from .writes import add_note, create_assignment, transition
from .writes import now as clock

#: The assignment scope a Build press writes.
SCOPE = "build"
#: Code-writing builders per machine and per repository: the operator's standing rule.
MACHINE_CAP = 6
REPO_CAP = 3
#: Items per bundle, so a bundle fits one 60-minute run (lead, note #29482).
BUNDLE_MAX = 3
BUDGET_MINUTES = 60
#: A supervisor beats every 30 s; one silent this long, or unspawned this long after its claim, is lost.
STALE_SECONDS = 180
#: Lost runs one bundle may retry before it blocks.
RETRIES = 1
#: The steps a run walks, each written before it starts.
STEPS = ("claimed", "worktree", "building", "reviewing", "fixing", "enqueuing", "enqueued", "checking", "cleaning")
#: The model a bundle runs on (Q60): Sonnet only when every member's `fields.work_kind` is `mechanical`.
OPUS, SONNET = "opus", "sonnet"
#: The fields a supervisor may write on its own open run.
RUN_FIELDS = frozenset({"step", "heartbeat_at", "supervisor_pid", "supervisor_pgid", "supervisor_start", "session_id",
                        "log_path", "builder_pgid", "builder_start", "final", "detail", "model"})
#: The steps the lane holds the run at: no supervisor runs, reap leaves it, step 7 releases it.
LANE_STEPS = ("enqueued", "checking", "cleaning")
ACTIVE = ("queued", "running", "ending")


class BuildRefused(SdDbError):
    """A press or a claim refused, with nothing written."""


def _item(connection, item: int) -> dict:
    """The item a build may take, or the refusal that names why not."""
    row = connection.execute(
        "SELECT item.*, repo.path AS repo_path, repo.remote, repo.managed, repo.lane_host "
        "FROM item LEFT JOIN repo ON repo.path = item.repo WHERE item.id = ?", (item,)).fetchone()
    if row is None:
        raise BuildRefused(f"no item {item}")
    if row["kind"] not in RUNNABLE_KINDS:
        raise BuildRefused(f"item {item} is a {row['kind']} item; a build takes only "
                           f"{', '.join(RUNNABLE_KINDS[:-1])} and {RUNNABLE_KINDS[-1]} items")
    if row["status"] != "ready":
        raise BuildRefused(f"item {item} is {row['status']}; a build takes a ready item")
    if row["repo_path"] is None:
        raise BuildRefused(f"item {item} needs a registered repository")
    if not row["managed"]:
        raise BuildRefused(f"item {item}'s repository {row['repo']} is not managed")
    if not row["remote"]:
        raise BuildRefused(f"item {item}'s repository {row['repo']} has no remote")
    if row["lane_host"] is not None:
        raise BuildRefused(f"item {item}'s lane runs on {row['lane_host']}; builds run on the hub only")
    active = connection.execute(
        f"SELECT id, status FROM assignment WHERE item = ? AND status IN {ACTIVE} LIMIT 1", (item,)).fetchone()
    if active:
        raise BuildRefused(f"item {item} has {active['status']} assignment {active['id']}")
    return dict(row)


def queue(connection, items: list[int], *, who: str, expected_revisions: dict | None = None) -> list[dict]:
    """The Build press: one queued build assignment per item, or the whole selection refused."""
    if not items or len(set(items)) != len(items) or any(type(item) is not int for item in items):
        raise BuildRefused("select one or more distinct items")
    if not isinstance(who, str) or not who.strip():
        raise BuildRefused("a press names who pressed it")
    with transaction(connection):
        if restoration_pending(connection):
            raise BuildRefused("database restore reimport is incomplete; builds are held")
        if expected_revisions is not None:
            from .workflow import item_state
            if {str(key) for key in expected_revisions} != {str(item) for item in items}:
                raise BuildRefused("the press needs one expected revision per selected item")
            for item in items:
                expected = expected_revisions.get(item, expected_revisions.get(str(item)))
                if item_state(connection, item)["revision"] != expected:
                    raise BuildRefused(f"item {item} changed; refresh the selection")
        for item in items:
            _item(connection, item)
        created = []
        for item in items:
            ident = create_assignment(connection, item=item, role="author", status="queued", lane="parallel",
                                      budget_minutes=BUDGET_MINUTES)
            connection.execute("UPDATE assignment SET scope = ?, queued_at = ?, started = NULL WHERE id = ?",
                               (SCOPE, clock(), ident))
            add_note(connection, item, "comment", f"Build assignment {ident} queued by {who}")
            created.append(ident)
        return [queue_state(connection, ident) for ident in created]


def eligible(connection, *, now: str | None = None) -> list[dict]:
    """The ready items a build may take, highest priority first: auto-pickup's selection.

    `reads.backlog_items` gives the unparked rows in priority order; a
    scheduled occurrence and every row `queue` would refuse are left out.
    """
    found = []
    for row in reads.backlog_items(connection, status="ready", now=now):
        if row["scheduled"]:
            continue
        try:
            _item(connection, row["id"])
        except BuildRefused:
            continue
        found.append({"id": row["id"], "title": row["title"], "repo": row["repo"], "priority": row["priority"]})
    return found


def _key(repo: str | None) -> str | None:
    return paths.key(repo) if isinstance(repo, str) and repo.startswith("/") else repo


def room(connection, *, load: float | None, load_cap: float | None, interactive: list[dict] | None) -> dict:
    """Builders that may start now: `machine`, `used` and `held` by repository, and `why` there is none.

    `load` and `load_cap` are the five-minute load and its cap from `sd gate
    status --json`; `interactive` is one `{repo, session_id}` per interactive
    builder, `repo` its key or None when its cwd names none. Either unread
    (None) is no room, never room. A headless run's own session is not counted
    twice. A repository holding an exclusive or quarantined lease of any other
    kind has no room (`held`).
    """
    why = ""
    if not (isinstance(load, (int, float)) and isinstance(load_cap, (int, float))
            and math.isfinite(load) and math.isfinite(load_cap)):
        why = "the load was not read"
    elif interactive is None:
        why = "the interactive builders were not counted"
    leases = connection.execute(
        "SELECT lease.repo, lease.exclusive, run.quarantine, run.session_id, assignment.scope "
        "FROM runner_lease lease JOIN runner_run run ON run.id = lease.run "
        "LEFT JOIN assignment ON assignment.id = run.assignment WHERE lease.released_at IS NULL").fetchall()
    builds = [row for row in leases if row["scope"] == SCOPE]
    headless = {row["session_id"] for row in builds if row["session_id"]}
    used: dict[str, int] = {}
    for row in builds:
        used[row["repo"]] = used.get(row["repo"], 0) + 1
    others = [entry for entry in interactive or [] if not (entry.get("session_id") and entry["session_id"] in headless)]
    for entry in others:
        repo = _key(entry.get("repo"))
        if repo:
            used[repo] = used.get(repo, 0) + 1
    held = sorted({row["repo"] for row in leases if row["scope"] != SCOPE and (row["exclusive"] or row["quarantine"])})
    machine = MACHINE_CAP - len(builds) - len(others)
    if not why and isinstance(load, (int, float)) and isinstance(load_cap, (int, float)) and load > load_cap:
        why = f"the five-minute load is {load:g}, above the cap of {load_cap:g}"
    if not why and machine <= 0:
        why = f"{MACHINE_CAP - machine} builders run already; the cap is {MACHINE_CAP}"
    return {"machine": 0 if why else machine, "used": used, "held": held, "why": why}


def room_for(available: dict, repo: str) -> int:
    """`room`'s answer for one repository: at most `REPO_CAP` builders there, and none while it is held."""
    if available["why"] or repo in available["held"]:
        return 0
    return max(0, min(available["machine"], REPO_CAP - available["used"].get(repo, 0)))


def _model(connection, items: list[int]) -> str:
    for item in items:
        row = connection.execute("SELECT fields FROM item WHERE id = ?", (item,)).fetchone()
        try:
            fields = json.loads(row["fields"] or "{}") if row else {}
        except ValueError:
            fields = {}
        if not isinstance(fields, dict) or fields.get("work_kind") != "mechanical":
            return OPUS
    return SONNET


def branch(lead: int) -> str:
    return f"build/sd-{lead}"


def worktree(repo: str, lead: int, *, root: Path | None = None) -> Path:
    return (root or Path.home() / "worktrees") / f"{Path(repo).name}-build-{lead}"


class _Moved(Exception):
    """A member's item moved after the press; the claim's writes roll back."""


#: The claim's re-check of each member, in the UPDATE's WHERE (design, claim step 4).
_RECHECK = (f"EXISTS (SELECT 1 FROM item WHERE item.id = assignment.item AND item.status = 'ready' "
            f"AND item.kind IN ({', '.join(repr(kind) for kind in RUNNABLE_KINDS)})) "
            f"AND NOT EXISTS (SELECT 1 FROM assignment other WHERE other.item = assignment.item "
            f"AND other.id != assignment.id AND other.status IN {ACTIVE})")


def claim(connection, *, owner: str, load: float | None, load_cap: float | None, interactive: list[dict] | None,
          root: Path | None = None) -> dict | None:
    """Claim one bundle under one `BEGIN IMMEDIATE`; None when nothing may start now.

    The repository with room whose best queued build ranks first (priority,
    then queue time) gives up to `BUNDLE_MAX` of its queued builds. A member
    whose item moved after the press fails the re-check: the claim's writes
    roll back, that member ends `blocked` with the reason, and nothing else
    changes, so the next claim takes the rest.
    """
    with transaction(connection):
        if restoration_pending(connection):
            raise BuildRefused("database restore reimport is incomplete; builds are held")
        available = room(connection, load=load, load_cap=load_cap, interactive=interactive)
        if available["why"]:
            return None
        queued = connection.execute(
            "SELECT assignment.id, assignment.item, item.repo FROM assignment JOIN item ON item.id = assignment.item "
            "WHERE assignment.status = 'queued' AND assignment.scope = ? AND item.repo IS NOT NULL "
            "ORDER BY item.priority IS NULL, item.priority, assignment.queued_at, assignment.id", (SCOPE,)).fetchall()
        repo = next((row["repo"] for row in queued if room_for(available, row["repo"]) > 0), None)
        if repo is None:
            return None
        bundle = [row for row in queued if row["repo"] == repo][:BUNDLE_MAX]
        lead = bundle[0]["id"]
        ids = [row["id"] for row in bundle]
        marks = ", ".join("?" for _ in ids)
        try:
            with transaction(connection):
                stamp = clock()
                taken = connection.execute(
                    f"UPDATE assignment SET status = 'running', started = ?, ended = NULL, "
                    f"parent = CASE WHEN id = ? THEN NULL ELSE ? END "
                    f"WHERE id IN ({marks}) AND status = 'queued' AND scope = ? AND {_RECHECK}",
                    (stamp, lead, lead, *ids, SCOPE)).rowcount
                if taken != len(ids):
                    raise _Moved
                ident = _open_run(connection, lead, repo=repo, owner=owner, step="claimed",
                                  model=_model(connection, [row["item"] for row in bundle]),
                                  work=worktree(repo, lead, root=root), stamp=stamp)
                for row in bundle:
                    transition(connection, row["item"], "in_progress", who="build",
                               reason=f"build run {ident} claimed assignment {row['id']}")
        except _Moved:
            moved = connection.execute(
                f"SELECT assignment.id, assignment.item, item.status FROM assignment JOIN item ON item.id = assignment.item "
                f"WHERE assignment.id IN ({marks}) AND NOT ({_RECHECK})", ids).fetchall()
            for row in moved:
                reason = f"item {row['item']} moved to {row['status']} after the press; not built"
                connection.execute("UPDATE assignment SET status = 'blocked', ended = ?, result = ? "
                                   "WHERE id = ? AND status = 'queued'", (clock(), reason, row["id"]))
                add_note(connection, row["item"], "comment", f"Build assignment {row['id']} blocked: {reason}")
            return None
        return run(connection, ident)


def _open_run(connection, lead: int, *, repo: str, owner: str, step: str, model: str, work: Path, stamp: str,
              session_id: str | None = None) -> str:
    """The lead's next run and its lease, numbered after every run the lead has, and each member's count moved to it."""
    number = connection.execute("SELECT MAX(COALESCE((SELECT MAX(run) FROM runner_run WHERE assignment = ?), 0), "
                                "run_count) + 1 FROM assignment WHERE id = ?", (lead, lead)).fetchone()[0]
    connection.execute("UPDATE assignment SET run_count = ? WHERE (id = ? OR parent = ?) AND status = 'running' "
                       "AND scope = ?", (number, lead, lead, SCOPE))
    ident = uuid.uuid4().hex
    connection.execute(
        "INSERT INTO runner_run (id, assignment, run, repo, branch, owner, work_path, retained_path, start_step, "
        "step, model, session_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, ?, ?)",
        (ident, lead, number, repo, branch(lead), owner, str(work), str(work), step, model, session_id, stamp, stamp))
    connection.execute("INSERT INTO runner_lease (run, repo, branch, exclusive, acquired_at) VALUES (?, ?, ?, 0, ?)",
                       (ident, repo, branch(lead), stamp))
    return ident


def _members(connection, lead: int) -> list[dict]:
    return [dict(row) for row in connection.execute(
        "SELECT id, item FROM assignment WHERE (id = ? OR parent = ?) AND status = 'running' AND scope = ? "
        "ORDER BY id = ? DESC, id", (lead, lead, SCOPE, lead))]


def run(connection, ident: str) -> dict:
    """One run with its bundle: the lead first, then the members."""
    row = connection.execute("SELECT * FROM runner_run WHERE id = ?", (ident,)).fetchone()
    if row is None:
        raise BuildRefused(f"no build run {ident}")
    result = dict(row)
    result["members"] = [dict(member) for member in connection.execute(
        "SELECT id, item, status FROM assignment WHERE (id = ? OR parent = ?) AND scope = ? ORDER BY id = ? DESC, id",
        (row["assignment"], row["assignment"], SCOPE, row["assignment"]))]
    return result


def open_runs(connection) -> list[dict]:
    """Every unreleased build run, oldest first."""
    return [dict(row) for row in connection.execute(
        "SELECT runner_run.* FROM runner_run JOIN assignment ON assignment.id = runner_run.assignment "
        "WHERE runner_run.released_at IS NULL AND assignment.scope = ? ORDER BY runner_run.created_at, runner_run.id",
        (SCOPE,))]


def write(connection, ident: str, **fields) -> bool:
    """One supervisor write on its own run; False, with nothing written, once the run ended or was released."""
    if not fields or set(fields) - RUN_FIELDS:
        raise BuildRefused(f"unsupported build run write: {sorted(set(fields) - RUN_FIELDS)}")
    if "step" in fields and fields["step"] not in STEPS:
        raise BuildRefused(f"no build step {fields['step']!r}")
    columns = ", ".join(f"{name} = ?" for name in fields)
    with transaction(connection):
        return connection.execute(
            f"UPDATE runner_run SET {columns}, updated_at = ? "
            f"WHERE id = ? AND released_at IS NULL AND outcome IS NULL",
            (*fields.values(), clock(), ident)).rowcount == 1


def beat(connection, ident: str) -> bool:
    return write(connection, ident, heartbeat_at=clock())


def enqueued(connection, ident: str) -> bool:
    """The `enqueued` step: the lease released and the members `done`, the items left `in_progress` for the lane.

    The run stays open, `released_at` and `outcome` null, until step 7 ends
    it; `reap` skips it meanwhile. One compare-and-set on the run, open and
    not yet at a lane step; False, with no row changed, for a late
    supervisor whose run was reaped or retried, or one already enqueued.
    """
    marks = ", ".join("?" for _ in LANE_STEPS)
    with transaction(connection):
        stamp = clock()
        if connection.execute(
                f"UPDATE runner_run SET step = 'enqueued', updated_at = ? WHERE id = ? AND released_at IS NULL "
                f"AND outcome IS NULL AND (step IS NULL OR step NOT IN ({marks}))",
                (stamp, ident, *LANE_STEPS)).rowcount != 1:
            return False
        lead = connection.execute("SELECT assignment FROM runner_run WHERE id = ?", (ident,)).fetchone()["assignment"]
        connection.execute("UPDATE runner_lease SET released_at = ? WHERE run = ? AND released_at IS NULL", (stamp, ident))
        for member in _members(connection, lead):
            connection.execute("UPDATE assignment SET status = 'done', ended = ?, result = ? WHERE id = ?",
                               (stamp, f"build run {ident} enqueued in the lane", member["id"]))
        return True


class Probe:
    """The liveness probe: `alive` and `group` are True, False (ESRCH) or None (EPERM, unknown); `started` is `ps -o lstart=`."""

    @staticmethod
    def alive(pid: int) -> bool | None:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return None
        return True

    @staticmethod
    def group(pgid: int) -> bool | None:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return None
        return True

    @staticmethod
    def started(pid: int) -> str | None:
        try:
            done = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                                  timeout=10, check=False, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode != 0:
            return None
        return " ".join(done.stdout.split()) or None


def _age(stamp: str, now: str) -> float:
    return (datetime.fromisoformat(now) - datetime.fromisoformat(stamp)).total_seconds()


def alive(row: dict, *, now: str, probe=Probe) -> bool:
    """Whether a run's supervisor lives: a beat (or, before the first, the claim) under `STALE_SECONDS` old,
    and its pid answering with the process start it recorded.

    A probe that cannot answer is no verdict: the run counts as alive until
    its beat goes stale, which needs no probe.
    """
    if _age(row["heartbeat_at"] or row["created_at"], now) >= STALE_SECONDS:
        return False
    pid = row["supervisor_pid"]
    if pid is None:
        return True
    answer = probe.alive(pid)
    if answer is not True:
        return answer is None
    started = probe.started(pid)
    return started is None or started == row["supervisor_start"]


def same_process(pid: int | None, start: str | None, *, probe=Probe) -> bool:
    """Whether `pid` is the process a run recorded: alive, and started at `start`.

    Anything less is not proof: no pid or start recorded, a pid gone, a start
    that differs (the pid was reused) or one the probe cannot read. Nothing is
    signalled without it.
    """
    if pid is None or not start or probe.alive(pid) is not True:
        return False
    return probe.started(pid) == start


GONE, OURS, UNSURE = "gone", "ours", "unsure"
#: Unsure reaps in a row before a run ends blocked.
DOUBTS = 3


def verdict(row: dict, *, probe=Probe) -> tuple[str, list[int]]:
    """What a reap may do to an ended run's processes, and the groups to kill: the one decision every reap path takes.

    The supervisor and the builder each read as gone, ours or unsure; the
    run is `UNSURE` when either is, else `OURS` when either is, else `GONE`.
    No retry starts until both are gone, so a paused supervisor cannot
    resume beside its replacement.

    - Supervisor: gone with no pid, ESRCH, or a pid now started at another
      time; ours when pid and start match and it recorded its group
      (`supervisor_pgid`); anything else (start unread, EPERM, no group) is
      unsure.
    - Builder: gone with no group or ESRCH on the group; ours when the
      leader's pid and start match; anything else (a reused leader pid or a
      dead one while the group has members, EPERM, an unknown probe) is
      unsure.
    """
    states, groups = [], []
    pid = row["supervisor_pid"]
    answer = None if pid is None else probe.alive(pid)
    started = probe.started(pid) if answer is True else None
    if pid is None or answer is False or (started is not None and started != row["supervisor_start"]):
        states.append(GONE)
    elif started is not None and row["supervisor_start"] and row["supervisor_pgid"] is not None:
        states.append(OURS)
        groups.append(row["supervisor_pgid"])
    else:
        states.append(UNSURE)
    pgid = row["builder_pgid"]
    if same_process(pgid, row["builder_start"], probe=probe):
        states.append(OURS)
        groups.append(pgid)
    elif pgid is None or probe.group(pgid) is False:
        states.append(GONE)
    else:
        states.append(UNSURE)
    state = UNSURE if UNSURE in states else OURS if OURS in states else GONE
    return state, groups if state == OURS else []


def kill_group(pgid: int) -> bool:
    """SIGKILL a builder's process group; True once no member lives (ESRCH), False while one may."""
    if not isinstance(pgid, int) or pgid <= 1 or pgid == os.getpgrp():
        return False
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    for _ in range(20):
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        time.sleep(0.1)
    return False


def reap(connection, *, now: str | None = None, probe=Probe, kill=kill_group) -> list[dict]:
    """End every open build run that fails `alive`; the runs settled, each `{run, outcome, retry}`.

    1. Compare-and-set `outcome` (`interrupted`, or `cancelled` when a cancel
       was asked) where `heartbeat_at` is the value read; a lost race means the
       supervisor beat, and the run is left alone.
    2. Take the `verdict`. `OURS`: kill the supervisor's group, then the
       builder's; a group that still has a process after the SIGKILL ends
       the run blocked, not retried. `UNSURE`:
       the run stays ended and unreleased, its lease held, nothing killed;
       the `DOUBTS`th unsure reap in a row ends it blocked, not retried.
    3. `_settle` it in one transaction.

    A run at a `LANE_STEPS` step is left alone: the lane holds it, and no
    supervisor is expected until step 7. Nothing is reaped while a restore
    reimport is pending: `abandon` ended
    every run the restore found, and a run it did not find is not this
    store's to judge.
    """
    now = now or clock()
    settled: list[dict] = []
    if restoration_pending(connection):
        return settled
    for row in open_runs(connection):
        if row["step"] in LANE_STEPS:
            continue
        if row["outcome"] is None:
            if alive(row, now=now, probe=probe):
                continue
            outcome = "cancelled" if row["cancel_requested"] else "interrupted"
            detail = (row["cancel_requested"] if outcome == "cancelled"
                      else f"supervisor lost at step {row['step']}: no live beat for {STALE_SECONDS} s")
            with transaction(connection):
                if connection.execute(
                        "UPDATE runner_run SET outcome = ?, detail = ?, updated_at = ? WHERE id = ? "
                        "AND outcome IS NULL AND released_at IS NULL AND heartbeat_at IS ?",
                        (outcome, detail, clock(), row["id"], row["heartbeat_at"])).rowcount != 1:
                    continue
        (state, groups), block = verdict(row, probe=probe), None
        if state == UNSURE:
            doubts = _doubt(connection, row["id"])
            if doubts < DOUBTS:
                continue
            block = (f"{doubts} reaps in a row could not tell whether builder group {row['builder_pgid']} "
                     f"or supervisor {row['supervisor_pid']} still runs; nothing was killed")
        elif state == OURS:
            survivors = [group for group in groups if not kill(group)]
            if survivors:
                block = f"process group {', '.join(map(str, survivors))} still had a process after SIGKILL"
        result = _settle(connection, row["id"], block=block)
        if result is not None:
            settled.append(result)
    return settled


def _doubt(connection, ident: str) -> int:
    """Count one unsure reap on an ended, unreleased run; the count so far (0 when the run moved on)."""
    with transaction(connection):
        connection.execute("UPDATE runner_run SET doubts = COALESCE(doubts, 0) + 1, updated_at = ? "
                           "WHERE id = ? AND released_at IS NULL", (clock(), ident))
        row = connection.execute("SELECT doubts FROM runner_run WHERE id = ? AND released_at IS NULL",
                                 (ident,)).fetchone()
        return 0 if row is None else row["doubts"]


def _settle(connection, ident: str, *, block: str | None = None) -> dict | None:
    """Release an ended run and its lease, then retry it once, block it, or end it cancelled.

    `block` names processes the reap could not end or could not judge: the
    bundle ends blocked, never retried, whatever the outcome.
    """
    with transaction(connection):
        row = connection.execute("SELECT * FROM runner_run WHERE id = ? AND released_at IS NULL "
                                 "AND outcome IS NOT NULL", (ident,)).fetchone()
        if row is None:
            return None
        stamp = clock()
        connection.execute("UPDATE runner_run SET released_at = ?, updated_at = ? WHERE id = ?", (stamp, stamp, ident))
        connection.execute("UPDATE runner_lease SET released_at = ? WHERE run = ? AND released_at IS NULL", (stamp, ident))
        lead, members = row["assignment"], _members(connection, row["assignment"])
        retry = None
        if block is not None:
            reason = (f"build run {ident} ended at step {row['step']}: {block}; check the group, then requeue or "
                      f"cancel; log {row['log_path'] or 'none'}, worktree {row['work_path']}")
            connection.execute("UPDATE runner_run SET detail = ? WHERE id = ?", (reason, ident))
            _block(connection, members, reason, stamp)
        elif row["outcome"] == "cancelled":
            for member in members:
                connection.execute("UPDATE assignment SET status = 'cancelled', ended = ?, result = ? WHERE id = ?",
                                   (stamp, row["detail"], member["id"]))
                _move(connection, member["item"], "ready", f"build run {ident} {row['detail']}; worktree {row['work_path']} kept")
        elif row["outcome"] == "interrupted":
            losses = connection.execute("SELECT COUNT(*) FROM runner_run WHERE assignment = ? AND outcome = 'interrupted'",
                                        (lead,)).fetchone()[0]
            if not members:
                # Nothing of the bundle runs any more (a hand edit, an old
                # restore): released, and nothing to retry.
                pass
            elif losses <= RETRIES:
                retry = _open_run(connection, lead, repo=row["repo"], owner=row["owner"], step=row["step"] or "claimed",
                                  model=row["model"] or OPUS, work=Path(row["work_path"]), stamp=stamp,
                                  session_id=row["session_id"])
                for member in members:
                    add_note(connection, member["item"], "comment",
                             f"Build run {ident} lost at step {row['step']}; retried as run {retry}")
            else:
                reason = (f"build run {ident} lost at step {row['step']} after {losses - 1} retry; "
                          f"log {row['log_path'] or 'none'}, worktree {row['work_path']}")
                _block(connection, members, reason, stamp)
        return {"run": ident, "outcome": row["outcome"], "retry": retry, "blocked": block}


def _block(connection, members: list[dict], reason: str, stamp: str) -> None:
    for member in members:
        connection.execute("UPDATE assignment SET status = 'blocked', ended = ?, result = ? WHERE id = ?",
                           (stamp, reason, member["id"]))
        _move(connection, member["item"], "blocked", reason)
        add_note(connection, member["item"], "followup",
                 f"Build blocked: {reason}. Look at the log and the worktree, then requeue or cancel.")


def abandon(connection, reason: str) -> list[str]:
    """End every unreleased build run `abandoned`: released, its lease too, never retried; the ids.

    A restore and a promotion call it in the transaction that blocks the
    assignments or releases the leases: the processes those rows name ran on
    a store, or a machine, that is no longer this one, so nothing may signal
    them or retry them from here.
    """
    with transaction(connection):
        stamp = clock()
        runs = [row["id"] for row in open_runs(connection)]
        for ident in runs:
            connection.execute("UPDATE runner_run SET outcome = 'abandoned', detail = COALESCE(detail, ?), "
                               "released_at = ?, updated_at = ? WHERE id = ?", (reason, stamp, stamp, ident))
            connection.execute("UPDATE runner_lease SET released_at = ? WHERE run = ? AND released_at IS NULL",
                               (stamp, ident))
        return runs


def _move(connection, item: int, target: str, reason: str) -> None:
    row = connection.execute("SELECT status FROM item WHERE id = ?", (item,)).fetchone()
    if row is not None and row["status"] != target and row["status"] != "done":
        transition(connection, item, target, who="build", reason=reason)
