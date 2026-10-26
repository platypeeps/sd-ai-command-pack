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
dispatcher (`build_run`, step 2) reads the load and the interactive builders,
which are not in the database, and passes them in.
"""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import time
import uuid
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

from . import paths, reads
from .database import transaction
from .errors import SdDbError
from .runner import RUNNABLE_KINDS, queue_state, restoration_pending
from .writes import (
    add_note,
    create_assignment,
    create_item,
    set_item_fields,
    set_setting,
    transition,
)
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
# The note on an item a blocked run parked (pack sd:6132).
PARKED = "Parked: build run {run} ended blocked; Retry on the Builds panel unparks it"
#: The steps a run walks, each written before it starts.
STEPS = ("claimed", "worktree", "building", "reviewing", "fixing", "enqueuing", "enqueued", "checking", "cleaning")
#: A note that sends the operator's finding to a bundle's next builder: Send to builder (pack sd:6020).
FINDING = "Send to builder: "
#: The model a bundle runs on (Q60): Sonnet only when every member's `fields.work_kind` is `mechanical`.
OPUS, SONNET = "opus", "sonnet"
#: The fields a supervisor may write on its own open run.
RUN_FIELDS = frozenset({"step", "heartbeat_at", "supervisor_pid", "supervisor_pgid", "supervisor_start", "session_id",
                        "log_path", "builder_pgid", "builder_start", "review_round", "final", "detail", "model"})
#: Every run column a reap decides on. Its compare-and-set, and the settle after it, match them all against the
#: row the reap read, so a writer between the read and the write (a beat, a registration, `enqueued`, a cancel)
#: makes the reap do nothing that tick.
REAP_READS = ("step", "outcome", "heartbeat_at", "supervisor_pid", "supervisor_start", "supervisor_pgid",
              "builder_pgid", "builder_start", "cancel_requested", "released_at")
_SAME = " AND ".join(f"{name} IS ?" for name in REAP_READS)
#: Where a fresh row resumes a step lost (design, "Run ownership by step"); any other step resumes itself.
#: A fix resumes at its review, which reads the head the fix left.
RESUME = {"claimed": "worktree", "fixing": "reviewing"}
#: The outcomes that count as a loss at a step; a second one at the same step blocks the bundle.
LOSSES = ("interrupted", "timed_out", "error_max_turns")
#: The steps from `enqueued` on: the lease is released, the members are `done`, and step 7 releases the run.
#: Only `enqueued` has no supervisor, so only it is left out of the reap.
LANE_STEPS = ("enqueued", "checking", "cleaning")
#: The steps a cancel may stop: from `enqueuing` on, the lane may hold the branch (design, "Liveness").
CANCELLABLE = ("claimed", "worktree", "building", "reviewing", "fixing")
ACTIVE = ("queued", "running", "ending")
#: Auto-pickup's end, a UTC timestamp, or none for off (design, "Auto-pickup").
AUTO_PICKUP = "build.auto_pickup_until"


class BuildRefused(SdDbError):
    """A press or a claim refused, with nothing written."""


def _repo_refusal(row) -> str | None:
    """Why the item's repository takes no build, or None: the one repository rule `queue` and `claim` read.

    `row` carries the item's `id` and `repo`, and the repository's `repo_path`,
    `managed`, `remote` and `lane_host` (`_REPO`'s columns).
    """
    item = row["id"]
    if row["repo_path"] is None:
        return f"item {item} needs a registered repository"
    if not row["managed"]:
        return f"item {item}'s repository {row['repo']} is not managed"
    if not row["remote"]:
        return f"item {item}'s repository {row['repo']} has no remote"
    if row["lane_host"] is not None:
        return f"item {item}'s lane runs on {row['lane_host']}; builds run on the hub only"
    return None


_REPO = ("SELECT item.*, repo.path AS repo_path, repo.remote, repo.managed, repo.lane_host "
         "FROM item LEFT JOIN repo ON repo.path = item.repo WHERE item.id = ?")


def _item(connection, item: int) -> dict:
    """The item a build may take, or the refusal that names why not."""
    row = connection.execute(_REPO, (item,)).fetchone()
    if row is None:
        raise BuildRefused(f"no item {item}")
    if row["kind"] not in RUNNABLE_KINDS:
        raise BuildRefused(f"item {item} is a {row['kind']} item; a build takes only "
                           f"{', '.join(RUNNABLE_KINDS[:-1])} and {RUNNABLE_KINDS[-1]} items")
    if row["status"] != "ready":
        raise BuildRefused(f"item {item} is {row['status']}; a build takes a ready item")
    refused = _repo_refusal(row)
    if refused:
        raise BuildRefused(refused)
    active = connection.execute(
        f"SELECT id, status FROM assignment WHERE item = ? AND status IN {ACTIVE} LIMIT 1", (item,)).fetchone()
    if active:
        raise BuildRefused(f"item {item} has {active['status']} assignment {active['id']}")
    held = _held(connection, item)
    if held:
        raise BuildRefused(held)
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


def over_load(load: float, cap: float) -> str:
    """Why no builder starts under this five-minute load, or "" (pack sd:6111).

    A cap of 0 or less is the gate's load rule off, as the lane's `load_stop`
    reads it; Start next on the dashboard reads the cap the same way.
    """
    return f"the five-minute load is {load:g}, above the cap of {cap:g}" if 0 < cap < load else ""


def room(connection, *, load: float | None, load_cap: float | None, interactive: list[dict] | None) -> dict:
    """Builders that may start now: `machine`, `used` and `held` by repository, and `why` there is none.

    `load` and `load_cap` are the five-minute load and its cap from `sd gate
    status --json`, a cap of 0 or less meaning none; `interactive` is one
    `{repo, session_id}` per interactive builder, `repo` its key or None
    when its cwd names none. Either unread
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
    if not why and isinstance(load, (int, float)) and isinstance(load_cap, (int, float)):
        why = over_load(load, load_cap)
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
def _holding(item: str) -> str:
    """The unreleased build runs that hold `item` (an SQL expression), as its lead's or a member's: one query.

    A held run (`blocked` or `abandoned`) keeps its lease while a process
    may live in its worktree; the item's status may move, but no build of it
    starts until a reap releases that run.
    """
    return (f"SELECT runner_run.id, runner_run.outcome FROM assignment holder JOIN runner_run "
            f"ON runner_run.assignment = COALESCE(holder.parent, holder.id) WHERE holder.item = {item} "
            f"AND holder.scope = '{SCOPE}' AND runner_run.released_at IS NULL")


def _held(connection, item: int) -> str | None:
    """Why no build of `item` may start while a run holds it, or None."""
    run = connection.execute(_holding("?") + " LIMIT 1", (item,)).fetchone()
    if run is None:
        return None
    return (f"item {item} is held by build run {run['id']} ({run['outcome'] or 'open'}), which releases once "
            f"its process groups read gone")


_RECHECK = (f"EXISTS (SELECT 1 FROM item WHERE item.id = assignment.item AND item.status = 'ready' "
            f"AND item.kind IN ({', '.join(repr(kind) for kind in RUNNABLE_KINDS)})) "
            f"AND NOT EXISTS (SELECT 1 FROM assignment other WHERE other.item = assignment.item "
            f"AND other.id != assignment.id AND other.status IN {ACTIVE}) "
            f"AND NOT EXISTS ({_holding('assignment.item')})")


def claim(connection, *, owner: str, load: float | None, load_cap: float | None, interactive: list[dict] | None,
          root: Path | None = None) -> dict | None:
    """Claim one bundle under one `BEGIN IMMEDIATE`; None when nothing may start now.

    The repository with room whose best queued build ranks first (priority,
    then queue time) gives up to `BUNDLE_MAX` of its queued builds. A member
    whose item moved after the press fails the re-check: the claim's writes
    roll back, that member ends `blocked` with the reason, and nothing else
    changes, so the next claim takes the rest.

    A queued build whose repository `queue` would now refuse (unmanaged, no
    remote, a satellite lane host: `_repo_refusal`) ends `blocked` with that
    reason before the bundle is picked, its item left as it is, and the same
    claim goes on to the next repository (pack sd:6103).
    """
    with transaction(connection):
        if restoration_pending(connection):
            raise BuildRefused("database restore reimport is incomplete; builds are held")
        available = room(connection, load=load, load_cap=load_cap, interactive=interactive)
        if available["why"]:
            return None
        queued = connection.execute(
            "SELECT assignment.id, assignment.item, assignment.parent, assignment.run_count, item.repo "
            "FROM assignment JOIN item ON item.id = assignment.item "
            "WHERE assignment.status = 'queued' AND assignment.scope = ? AND item.repo IS NOT NULL "
            "ORDER BY item.priority IS NULL, item.priority, assignment.queued_at, assignment.id", (SCOPE,)).fetchall()
        queued = [row for row in queued if not _refused_repo(connection, row)]
        repo = next((row["repo"] for row in queued if room_for(available, row["repo"]) > 0), None)
        if repo is None:
            return None
        bundle = _bundle([row for row in queued if row["repo"] == repo])
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
                _refuse(connection, row, _held(connection, row["item"])
                        or f"item {row['item']} moved to {row['status']} after the press")
            return None
        return run(connection, ident)


def _bundle(rows: list) -> list:
    """The queued rows of one repository a claim takes, best first.

    A bundle that ran before claims alone, its old lead first, so its run
    gets the lead's branch and worktree back (pack sd:6020); fresh rows
    bundle with fresh rows only, up to `BUNDLE_MAX`.
    """
    best = rows[0]
    group = best["parent"] or (best["id"] if best["run_count"] else None)
    if group is None:
        return [row for row in rows if row["parent"] is None and not row["run_count"]][:BUNDLE_MAX]
    return sorted((row for row in rows if group in (row["id"], row["parent"])), key=lambda row: row["id"] != group)


def _refuse(connection, row, reason: str) -> None:
    """End one queued build `blocked` with why the claim did not take it; its item stays as it is."""
    reason += "; not built"
    connection.execute("UPDATE assignment SET status = 'blocked', ended = ?, result = ? "
                       "WHERE id = ? AND status = 'queued'", (clock(), reason, row["id"]))
    add_note(connection, row["item"], "comment", f"Build assignment {row['id']} blocked: {reason}")


def _refused_repo(connection, row) -> bool:
    """End a queued build whose repository turned ineligible after the press (`_repo_refusal`); True if it did."""
    refused = _repo_refusal(connection.execute(_REPO, (row["item"],)).fetchone())
    if refused:
        _refuse(connection, row, f"{refused} after the press")
    return refused is not None


def _open_run(connection, lead: int, *, repo: str, owner: str, step: str, model: str, work: Path, stamp: str,
              session_id: str | None = None, review_round: int | None = None) -> str:
    """The lead's next run and its lease, numbered after every run the lead has, and each member's count moved to it."""
    number = connection.execute("SELECT MAX(COALESCE((SELECT MAX(run) FROM runner_run WHERE assignment = ?), 0), "
                                "run_count) + 1 FROM assignment WHERE id = ?", (lead, lead)).fetchone()[0]
    connection.execute("UPDATE assignment SET run_count = ? WHERE (id = ? OR parent = ?) AND scope = ?",
                       (number, lead, lead, SCOPE))
    ident = uuid.uuid4().hex
    connection.execute(
        "INSERT INTO runner_run (id, assignment, run, repo, branch, owner, work_path, retained_path, start_step, "
        "step, model, session_id, review_round, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ident, lead, number, repo, branch(lead), owner, str(work), str(work), step, step, model, session_id,
         review_round, stamp, stamp))
    if step not in LANE_STEPS:
        connection.execute("INSERT INTO runner_lease (run, repo, branch, exclusive, acquired_at) VALUES (?, ?, ?, 0, ?)",
                           (ident, repo, branch(lead), stamp))
    return ident


def _members(connection, lead: int, status: str = "running") -> list[dict]:
    return [dict(row) for row in connection.execute(
        "SELECT id, item FROM assignment WHERE (id = ? OR parent = ?) AND status = ? AND scope = ? "
        "ORDER BY id = ? DESC, id", (lead, lead, status, SCOPE, lead))]


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


def ended_runs(connection, since: str, *, limit: int = 50) -> list[dict]:
    """The build runs released at or after `since`, newest first (Queue's Builds panel, pack sd:6095)."""
    return [dict(row) for row in connection.execute(
        "SELECT runner_run.* FROM runner_run JOIN assignment ON assignment.id = runner_run.assignment "
        "WHERE assignment.scope = ? AND runner_run.released_at IS NOT NULL AND runner_run.released_at >= ? "
        "ORDER BY runner_run.released_at DESC, runner_run.run DESC, runner_run.rowid DESC LIMIT ?",
        (SCOPE, since, limit))]


def pull_url(connection, repo: str, branch: str | None, items: list[int]) -> str:
    """The pull request `sd-ship` opened for `branch`, from its ship receipt, or "" (pack sd:6020, Open PR).

    The lane names an entry by the first member the branch delivers, so each member's receipt is read in turn. Nothing
    asks GitHub: a branch never shipped, a repository with no GitHub remote or an unreadable receipt has none to show.
    """
    from . import ship
    from .workflow import WorkflowError

    probe = paths.keys(repo)  # a run row written before migration 014 holds the absolute form
    row = connection.execute(
        f"SELECT remote FROM repo WHERE path IN ({paths.placeholders(probe)})", probe).fetchone()
    if not branch or row is None or not row["remote"]:
        return ""
    try:
        repository = ship._github_repository(row["remote"])
        for item in items:
            receipt = ship.read(connection, ship.receipt_key(repository, branch, item))[1]
            url = (receipt.get("pull_request") or {}).get("url")
            if isinstance(url, str) and url.startswith("https://github.com/"):
                return url
    except WorkflowError:
        return ""
    return ""


def open_question(connection, items: list[int], since: str) -> dict | None:
    """The first `question` note on `items` since `since` that no `Ruling on note #<n>:` decision answers."""
    if not items:
        return None
    marks = ", ".join("?" for _ in items)
    row = connection.execute(
        f"SELECT asked.id, asked.item FROM note asked WHERE asked.kind = 'question' AND asked.item IN ({marks}) "
        f"AND asked.timestamp >= ? AND NOT EXISTS (SELECT 1 FROM note ruling WHERE ruling.item = asked.item "
        f"AND ruling.kind = 'decision' AND ruling.body LIKE 'Ruling on note #' || asked.id || ':%') "
        f"ORDER BY asked.id LIMIT 1", (*items, since)).fetchone()
    return dict(row) if row else None


def finished_seconds(connection, *, limit: int = 20) -> list[float]:
    """Claim to release, in seconds, of the last `limit` build runs that ended `done`, newest first.

    The past runs Today's builder ETA reads (sd:6003). A retried bundle's runs count each on its own.
    """
    rows = connection.execute(
        "SELECT runner_run.created_at, runner_run.released_at FROM runner_run "
        "JOIN assignment ON assignment.id = runner_run.assignment WHERE assignment.scope = ? "
        "AND runner_run.outcome = 'done' AND runner_run.released_at IS NOT NULL "
        "ORDER BY runner_run.released_at DESC, runner_run.id DESC LIMIT ?", (SCOPE, limit)).fetchall()
    return [seconds for row in rows if (seconds := _age(row["created_at"], row["released_at"])) >= 0]


def run_spent(connection, ident: str) -> float:
    """What one build run spent so far: its `run` and `bound` cost rows, which carry the run as their pass."""
    return float(connection.execute(
        "SELECT COALESCE(SUM(usd), 0.0) FROM cost WHERE pass = ? AND source IN ('run', 'bound')", (ident,)).fetchone()[0])


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


def enqueuing(connection, ident: str) -> bool:
    """The `enqueuing` step: one compare-and-set from `reviewing`, or from `enqueuing` on a resumed run, that a
    requested cancel fails. With the cancel's own step check it makes one winner: cancel or enqueue, never both."""
    with transaction(connection):
        return connection.execute(
            "UPDATE runner_run SET step = 'enqueuing', heartbeat_at = ?, updated_at = ? WHERE id = ? "
            "AND step IN ('reviewing', 'enqueuing') AND outcome IS NULL AND released_at IS NULL "
            "AND cancel_requested IS NULL", (clock(), clock(), ident)).rowcount == 1


def enqueued(connection, ident: str, delivered: Collection[int] | None = None) -> bool:
    """The `enqueued` step: the lease released and the members `done`, the items left `in_progress` for the lane.

    `delivered` is the items the lane entry delivers; a member outside it
    (the builder skipped it) ends `blocked` with its item and a note, so the
    merge leaves it open. None delivers every member. The run stays open,
    `released_at` and `outcome` null, until step 7 ends it; `reap` skips it
    meanwhile. One compare-and-set on the run, open and not yet at a lane
    step; False, with no row changed, for a late supervisor whose run was
    reaped or retried, or one already enqueued.
    """
    marks = ", ".join("?" for _ in LANE_STEPS)
    with transaction(connection):
        stamp = clock()
        # A cancel asked first wins: the run never reaches `enqueued`, which
        # the reap skips, and the reap ends it cancelled.
        if connection.execute(
                f"UPDATE runner_run SET step = 'enqueued', updated_at = ? WHERE id = ? AND released_at IS NULL "
                f"AND outcome IS NULL AND cancel_requested IS NULL AND (step IS NULL OR step NOT IN ({marks}))",
                (stamp, ident, *LANE_STEPS)).rowcount != 1:
            return False
        lead = connection.execute("SELECT assignment FROM runner_run WHERE id = ?", (ident,)).fetchone()["assignment"]
        connection.execute("UPDATE runner_lease SET released_at = ? WHERE run = ? AND released_at IS NULL", (stamp, ident))
        members = _members(connection, lead)
        skipped = [member for member in members if delivered is not None and member["item"] not in delivered]
        for member in members:
            if member not in skipped:
                connection.execute("UPDATE assignment SET status = 'done', ended = ?, result = ? WHERE id = ?",
                                   (stamp, f"build run {ident} enqueued in the lane", member["id"]))
        for member in skipped:
            _block(connection, [member], f"build run {ident} enqueued no commit with a `Closes: sd:{member['item']}` "
                                         "trailer, so the merge leaves this item open", stamp)
        return True


def register(connection, ident: str, *, pid: int, pgid: int, start: str | None) -> bool:
    """A supervisor takes its run: one compare-and-set on an open run no supervisor holds; False for a second one."""
    with transaction(connection):
        return connection.execute(
            "UPDATE runner_run SET supervisor_pid = ?, supervisor_pgid = ?, supervisor_start = ?, heartbeat_at = ?, "
            "updated_at = ? WHERE id = ? AND supervisor_pid IS NULL AND released_at IS NULL AND outcome IS NULL",
            (pid, pgid, start, clock(), clock(), ident)).rowcount == 1


def end(connection, ident: str, outcome: str, detail: str, *, question: str | None = None) -> dict | None:
    """The supervisor ends its own run, its groups confirmed gone; `_settle`'s answer, or None once the run moved.

    One compare-and-set from an open outcome, then `_settle` in the same
    transaction: `cancelled` ends the bundle and moves its items to ready,
    a `LOSSES` outcome retries once at the `RESUME` step, `blocked` blocks
    the bundle with `detail` (held until a reap reads the supervisor gone),
    and `done` releases it. `question` adds a question note on each item.
    """
    if outcome not in ("cancelled", "blocked", "done", *LOSSES):
        raise BuildRefused(f"no supervisor outcome {outcome!r}")
    with transaction(connection):
        if connection.execute("UPDATE runner_run SET outcome = ?, detail = ?, updated_at = ? WHERE id = ? "
                              "AND outcome IS NULL AND released_at IS NULL",
                              (outcome, detail, clock(), ident)).rowcount != 1:
            return None
        row = dict(connection.execute("SELECT * FROM runner_run WHERE id = ?", (ident,)).fetchone())
        if question:
            for member in _members(connection, row["assignment"], "done" if row["step"] in LANE_STEPS else "running"):
                add_note(connection, member["item"], "question", question)
        if outcome == "done":
            stamp = clock()
            connection.execute("UPDATE runner_run SET released_at = ?, updated_at = ? WHERE id = ?",
                               (stamp, stamp, ident))
            connection.execute("UPDATE runner_lease SET released_at = ? WHERE run = ? AND released_at IS NULL",
                               (stamp, ident))
            return {"run": ident, "outcome": "done", "retry": None, "blocked": None}
        return _settle(connection, row, block=detail if outcome == "blocked" else None)


def merged(connection, read: dict) -> bool:
    """The tick moves an `enqueued` run whose lane entry merged to `cleaning`, with a fresh beat and no supervisor.

    The compare-and-set matches the row read, at `enqueued` and open; the
    process columns of the supervisor that enqueued it are cleared, so the
    tick spawns a fresh one and the reap judges it as any step.
    """
    with transaction(connection):
        stamp = clock()
        return connection.execute(
            f"UPDATE runner_run SET step = 'cleaning', heartbeat_at = ?, supervisor_pid = NULL, "
            f"supervisor_pgid = NULL, supervisor_start = NULL, builder_pgid = NULL, builder_start = NULL, "
            f"updated_at = ? WHERE id = ? AND step = 'enqueued' AND {_SAME}",
            (stamp, stamp, read["id"], *(read[name] for name in REAP_READS))).rowcount == 1


def lane_failed(connection, read: dict, reason: str) -> bool:
    """The tick ends an `enqueued` run whose lane entry failed or was skipped: `lane_failed`, released, in one write.

    The worktree stays for Retry; the lane's own note names the step.
    """
    with transaction(connection):
        stamp = clock()
        if connection.execute(
                f"UPDATE runner_run SET outcome = 'lane_failed', detail = ?, released_at = ?, updated_at = ? "
                f"WHERE id = ? AND step = 'enqueued' AND {_SAME}",
                (reason, stamp, stamp, read["id"], *(read[name] for name in REAP_READS))).rowcount != 1:
            return False
        connection.execute("UPDATE runner_lease SET released_at = ? WHERE run = ? AND released_at IS NULL",
                           (stamp, read["id"]))
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
#: Outcomes of a run that ended unretried while a process may live: it keeps its lease until `_release`.
HELD = ("blocked", "abandoned")
#: Unsure reaps in a row before a run ends blocked.
DOUBTS = 3


def _side(pid: int | None, start: str | None, pgid: int | None, *, probe=Probe) -> str:
    """One process of a run, and its group, as gone, ours or unsure: the one probe `verdict` takes twice.

    - Gone: nothing recorded (no process was spawned), or ESRCH on the group
      with the pid dead or now started at another time.
    - Ours: the pid answers with the start the run recorded, and its group
      is recorded, so a kill can reach every child.
    - Unsure: anything else, such as a pid with no group recorded, a group
      with members while its leader is dead or reused, EPERM, an unread
      start or an unknown probe.
    """
    if pid is None and pgid is None:
        return GONE
    if pid is not None and same_process(pid, start, probe=probe):
        return OURS if pgid is not None else UNSURE
    if pgid is None or probe.group(pgid) is not False:
        return UNSURE
    if pid is None:
        return GONE
    answer = probe.alive(pid)
    if answer is False:
        return GONE
    started = probe.started(pid) if answer is True else None
    return GONE if started is not None and started != start else UNSURE


def verdict(row: dict, *, probe=Probe) -> tuple[str, list[int]]:
    """What a reap may do to an ended run's processes, and the groups to kill: every gone, release or retry asks it.

    The supervisor (`supervisor_pid`, `supervisor_pgid`) and the builder
    (`builder_pgid` and its leader) are each a `_side`; the run is `UNSURE`
    when either is, else `OURS` when either is, else `GONE`. So nothing is
    released or retried until ESRCH answers on both groups, and a paused
    supervisor, or a child of a dead one, cannot run beside a replacement.
    """
    sides = [(_side(row["supervisor_pid"], row["supervisor_start"], row["supervisor_pgid"], probe=probe),
              row["supervisor_pgid"]),
             (_side(row["builder_pgid"], row["builder_start"], row["builder_pgid"], probe=probe), row["builder_pgid"])]
    states = [state for state, _ in sides]
    state = UNSURE if UNSURE in states else OURS if OURS in states else GONE
    return state, [group for side, group in sides if side == OURS] if state == OURS else []


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
       was asked) where every `REAP_READS` column is the value read; a lost
       race means a writer moved the run (a beat, a registration, `enqueued`,
       a cancel), and the run is left alone this tick.
    2. Take the `verdict`. `OURS`: kill the supervisor's group, then the
       builder's; a group that still has a process after the SIGKILL ends
       the run `blocked`, not retried, unreleased with its lease until
       `_release` finds every group gone. `UNSURE`:
       the run stays ended and unreleased, its lease held, nothing killed;
       the `DOUBTS`th unsure reap in a row ends it blocked, not retried.
    3. `_settle` it in one transaction.

    A held run (`HELD`) goes to `_release` at any step, `enqueued` too. An
    open run at `enqueued` is left alone: it waits on the lane, and no
    supervisor runs until the merge; `checking` and `cleaning` run under a
    fresh supervisor and take the verdict like any step. Nothing is reaped while a restore
    reimport is pending: `abandon` ended
    every run the restore found, and a run it did not find is not this
    store's to judge.
    """
    now = now or clock()
    settled: list[dict] = []
    if restoration_pending(connection):
        return settled
    for row in open_runs(connection):
        if row["outcome"] in HELD:
            _release(connection, row, probe=probe)
            continue
        if row["step"] == "enqueued" and row["outcome"] is None:
            continue
        if row["outcome"] is None:
            if alive(row, now=now, probe=probe):
                continue
            outcome = "cancelled" if row["cancel_requested"] else "interrupted"
            detail = (row["cancel_requested"] if outcome == "cancelled"
                      else f"supervisor lost at step {row['step']}: no live beat for {STALE_SECONDS} s")
            with transaction(connection):
                if connection.execute(
                        f"UPDATE runner_run SET outcome = ?, detail = ?, updated_at = ? WHERE id = ? AND {_SAME}",
                        (outcome, detail, clock(), row["id"], *(row[name] for name in REAP_READS))).rowcount != 1:
                    continue
            row = {**row, "outcome": outcome, "detail": detail}
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
        result = _settle(connection, row, block=block)
        if result is not None:
            settled.append(result)
    return settled


def _release(connection, read: dict, *, probe=Probe) -> bool:
    """Release a held run (`blocked` or `abandoned`), and its lease, once `verdict` reads it gone; True if released.

    The probe alone decides: no kill, no retry, no note. Unsure or alive
    leaves the run as it is for the next tick. The write matches the row
    read, as the reap's compare-and-set does.
    """
    if verdict(read, probe=probe)[0] != GONE:
        return False
    with transaction(connection):
        stamp = clock()
        if connection.execute(f"UPDATE runner_run SET released_at = ?, updated_at = ? WHERE id = ? AND {_SAME}",
                              (stamp, stamp, read["id"], *(read[name] for name in REAP_READS))).rowcount != 1:
            return False
        connection.execute("UPDATE runner_lease SET released_at = ? WHERE run = ? AND released_at IS NULL",
                           (stamp, read["id"]))
        if read["outcome"] == "blocked":
            _park(connection, read["id"], read["assignment"], stamp)
        return True


def _doubt(connection, ident: str) -> int:
    """Count one unsure reap on an ended, unreleased run; the count so far (0 when the run moved on)."""
    with transaction(connection):
        connection.execute("UPDATE runner_run SET doubts = COALESCE(doubts, 0) + 1, updated_at = ? "
                           "WHERE id = ? AND released_at IS NULL", (clock(), ident))
        row = connection.execute("SELECT doubts FROM runner_run WHERE id = ? AND released_at IS NULL",
                                 (ident,)).fetchone()
        return 0 if row is None else row["doubts"]


def _settle(connection, read: dict, *, block: str | None = None) -> dict | None:
    """Release an ended run and its lease, then retry it, block it, or end it cancelled, in one transaction.

    A retry is a fresh row: `run` + 1, the same worktree and branch, the
    `RESUME` step, the old `review_round` and `session_id`, no outcome; the
    old row's outcome stays set, so a late old supervisor writes nothing. A
    second loss at the same step blocks the bundle. A run with
    `cancel_requested` ends cancelled whatever its outcome: no fresh row.

    `read` is the row the reap decided on; nothing happens unless every
    `REAP_READS` column still holds its value (a cancel since then moves it).

    `block` names processes the reap could not end or could not judge: the
    bundle ends blocked, never retried, whatever the outcome.
    """
    ident = read["id"]
    with transaction(connection):
        row = connection.execute(f"SELECT * FROM runner_run WHERE id = ? AND outcome IS NOT NULL AND {_SAME}",
                                 (ident, *(read[name] for name in REAP_READS))).fetchone()
        if row is None:
            return None
        stamp = clock()
        lead = row["assignment"]
        members = _members(connection, lead, "done" if row["step"] in LANE_STEPS else "running")
        if block is not None:
            # A process may live: the run stays unreleased and keeps its
            # lease, so it still counts in `room`, until `_release` finds
            # every group gone.
            reason = (f"build run {ident} ended at step {row['step']}: {block}; check the group, then requeue or "
                      f"cancel; log {row['log_path'] or 'none'}, worktree {row['work_path']}")
            connection.execute("UPDATE runner_run SET outcome = 'blocked', detail = ?, updated_at = ? WHERE id = ?",
                               (reason, stamp, ident))
            _block(connection, members, reason, stamp)
            return {"run": ident, "outcome": "blocked", "retry": None, "blocked": block}
        connection.execute("UPDATE runner_run SET released_at = ?, updated_at = ? WHERE id = ?", (stamp, stamp, ident))
        connection.execute("UPDATE runner_lease SET released_at = ? WHERE run = ? AND released_at IS NULL", (stamp, ident))
        retry = None
        if row["outcome"] == "cancelled" or row["cancel_requested"]:
            for member in members:
                connection.execute("UPDATE assignment SET status = 'cancelled', ended = ?, result = ? WHERE id = ?",
                                   (stamp, row["detail"], member["id"]))
                _move(connection, member["item"], "ready", f"build run {ident} {row['detail']}; worktree {row['work_path']} kept")
        elif row["outcome"] in LOSSES:
            marks = ", ".join("?" for _ in LOSSES)
            losses = connection.execute(f"SELECT COUNT(*) FROM runner_run WHERE assignment = ? AND step IS ? "
                                        f"AND outcome IN ({marks})", (lead, row["step"], *LOSSES)).fetchone()[0]
            if not members:
                # Nothing of the bundle runs any more (a hand edit, an old
                # restore): released, and nothing to retry.
                pass
            elif losses <= RETRIES:
                step = row["step"] or "claimed"
                retry = _open_run(connection, lead, repo=row["repo"], owner=row["owner"], step=RESUME.get(step, step),
                                  model=row["model"] or OPUS, work=Path(row["work_path"]), stamp=stamp,
                                  session_id=row["session_id"], review_round=row["review_round"])
                for member in members:
                    add_note(connection, member["item"], "comment",
                             f"Build run {ident} lost at step {row['step']}; retried as run {retry}")
            elif row["step"] == "checking":
                retry = _health_unknown(connection, row, members, stamp)
            elif row["step"] == "cleaning":
                # Merged, and the lane owns the items: nothing is blocked, the worktree just stays.
                connection.execute("UPDATE runner_run SET outcome = 'done', updated_at = ? WHERE id = ?",
                                   (stamp, ident))
                for member in members:
                    add_note(connection, member["item"], "comment",
                             f"Build run {ident} lost at cleaning a second time; worktree {row['work_path']} kept: "
                             f"remove it by hand once it is clean")
                return {"run": ident, "outcome": "done", "retry": None, "blocked": None}
            else:
                reason = (f"build run {ident} lost at step {row['step']} a second time; "
                          f"log {row['log_path'] or 'none'}, worktree {row['work_path']}")
                _block(connection, members, reason, stamp)
                _park(connection, ident, lead, stamp)
        return {"run": ident, "outcome": row["outcome"], "retry": retry, "blocked": block}


def _health_unknown(connection, row, members: list[dict], stamp: str) -> str:
    """A second loss at `checking`: the merge's health is unknown, so auto-pickup goes off first, an item is filed,
    and a fresh row goes on to `cleaning` (design, "Run ownership by step"); the fresh row's id."""
    set_setting(connection, AUTO_PICKUP, None)
    filed = create_item(connection, kind="task", title=f"Build run {row['id']}: health unknown after its merge",
                        repo=row["repo"])
    add_note(connection, filed, "comment",
             f"Build run {row['id']} was lost at checking a second time, so the health check after its merge has no "
             f"answer. Auto-pickup ({AUTO_PICKUP}) is off. Run `repo-sync.sh refresh` and `dashboard.sh health`, "
             f"then turn it on again. Log {row['log_path'] or 'none'}.")
    retry = _open_run(connection, row["assignment"], repo=row["repo"], owner=row["owner"], step="cleaning",
                      model=row["model"] or OPUS, work=Path(row["work_path"]), stamp=stamp,
                      session_id=row["session_id"], review_round=row["review_round"])
    for member in members:
        add_note(connection, member["item"], "comment",
                 f"Build run {row['id']} lost at checking a second time; auto-pickup is off, item {filed} filed, "
                 f"run {retry} cleans up")
    return retry


def _block(connection, members: list[dict], reason: str, stamp: str) -> None:
    for member in members:
        connection.execute("UPDATE assignment SET status = 'blocked', ended = ?, result = ? WHERE id = ?",
                           (stamp, reason, member["id"]))
        _move(connection, member["item"], "blocked", reason)
        add_note(connection, member["item"], "followup",
                 f"Build blocked: {reason}. Look at the log and the worktree, then requeue or cancel.")


def _park(connection, ident: str, lead: int, stamp: str) -> None:
    """Park each item of a blocked run, once the run and its lease are released, as the nightly prune parks an idle
    one (pack sd:6132, sd:6008): an item the operator moved on, or one parked already, stays as it is."""
    for member in _members(connection, lead, "blocked"):
        row = connection.execute("SELECT status, parked_at FROM item WHERE id = ?", (member["item"],)).fetchone()
        if row is not None and row["status"] == "blocked" and row["parked_at"] is None:
            set_item_fields(connection, member["item"], parked_at=stamp)
            add_note(connection, member["item"], "comment", PARKED.format(run=ident))


def abandon(connection, reason: str) -> list[str]:
    """End every unreleased build run `abandoned`, never retried; the ids.

    A restore and a promotion call it in the transaction that blocks the
    assignments: the rows came from a store, or a machine, that is no longer
    this one, so nothing may signal or retry them from here. Each keeps its
    lease, as a `blocked` run does, until a reap's `_release` finds its
    groups gone: a supervisor of the old store may still run here.
    """
    with transaction(connection):
        stamp = clock()
        runs = [row["id"] for row in open_runs(connection) if row["outcome"] not in HELD]
        for ident in runs:
            connection.execute("UPDATE runner_run SET outcome = 'abandoned', detail = COALESCE(detail, ?), "
                               "updated_at = ? WHERE id = ?", (reason, stamp, ident))
        return runs


def _move(connection, item: int, target: str, reason: str) -> None:
    row = connection.execute("SELECT status FROM item WHERE id = ?", (item,)).fetchone()
    if row is not None and row["status"] != target and row["status"] != "done":
        transition(connection, item, target, who="build", reason=reason)
