"""The Build press on Tasks and the Builds panel on Queue (pack sd:6095).

Design: system `docs/work/2026-10-24-build-dispatcher/design.md`, step 4 and its Dashboard section.

`plan` is what the Build dialog shows before anything is written: each repository's bundles of up to
`build.BUNDLE_MAX` items with the model and the room now, and every selected item a press would refuse, with
why. `press` is the Build press: `build.queue` with the revisions the dialog read, the whole selection or none. A
refusal is a 409 and writes nothing. After the queue lands it kickstarts the `build-dispatch` job, so a claim
takes seconds, not a slot; a kickstart that fails only says so, and the next tick claims the rows.

`panel` is Queue's Builds panel: one row per open build run, and the build runs released in the last 24 hours with
their outcome. `retry` is Retry on a blocked or cancelled run: each such member's item goes back to `ready` and
its assignment is queued again (`runner.requeue`), in one transaction. With a `finding` it is Send to builder (pack
sd:6020): the finding is a `build.FINDING` note on each item first, and the claim keeps the bundle under its lead, so
the next builder resumes the same worktree and its brief names the finding. Cancel on a running build is the route that
exists, `/api/assignments/<lead>/cancel` (`operations.cancel_assignment`), bound to the revision this panel read.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from sd_db import build, operations, reads, runner, workflow
from sd_db import repos as sd_repos
from sd_db.config import label_prefix
from sd_db.database import transaction
from sd_db.errors import SdDbError
from sd_db.writes import add_note, transition

__all__ = ["JOB", "QUIET_SECONDS", "RECENT_HOURS", "kickstart", "panel", "plan", "press", "retry"]

#: The local-cron-jobs job that runs `sd assignments dispatch` (system, build-dispatch.job).
JOB = "build-dispatch"
#: A builder whose log has not grown this long is stalled: shown, never acted on (design, Dashboard).
QUIET_SECONDS = 15 * 60
#: How far back the panel lists ended runs.
RECENT_HOURS = 24
KICKSTART_SECONDS = 5
#: The bundle statuses Retry and Send to builder take: each keeps its worktree.
AGAIN = ("blocked", "cancelled")
#: The longest finding Send to builder takes, as a note line the brief quotes.
FINDING_MAX = 4000
#: The steps a builder writes its log in; a quiet log elsewhere (a review, the lane) is not a stall.
LOGGING = ("building", "fixing")


def items_of(values) -> list[int]:
    """The selected item ids, distinct positive integers, or ValueError."""
    if (not isinstance(values, list) or not values or len(values) > 50
            or any(type(item) is not int or not 1 <= item <= 9223372036854775807 for item in values)
            or len(set(values)) != len(values)):
        raise ValueError("Select one to 50 distinct items to build.")
    return values


def _at(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds(since: str | None, now: str) -> int | None:
    start, end = _at(since), _at(now)
    return int((end - start).total_seconds()) if start and end else None


def interactive(connection, *, now: str, sessions=None) -> list[dict] | None:
    """One `{repo, session_id}` per interactive builder, as `sd assignments dispatch` counts them; None when unread.

    `sessions` is `claude_sessions.document`, the seam a test fills. A cwd in a linked worktree counts against its
    main checkout (`sd_lib.main_worktree_root`, pack sd:6112).
    """
    from . import claude_sessions, pack_module

    try:
        document = (sessions or claude_sessions.document)(connection, now=now)
        if document["builders"]["running"] is None:
            return None
        root = pack_module("sd_lib").main_worktree_root
        repos = [row["path"] for row in sd_repos.registered(connection)]
        found = []
        for session in document["sessions"] or []:
            count = sum(1 for agent in session.get("agents") or [] if agent["builder"] and agent["state"] != "idle")
            count += 1 if session.get("builder") and session.get("status") != "idle" else 0
            cwd = str(root(Path(session["cwd"]).resolve())) if session.get("cwd") else ""
            key = build.paths.key(cwd) if cwd else ""
            repo = next((path for path in repos if key and (key == path or key.startswith(path.rstrip("/") + "/"))), None)
            found += [{"repo": repo, "session_id": session.get("id")}] * count
        return found
    except Exception:  # noqa: BLE001 -- any failure is "not counted", which shows no room
        return None


def _room(connection, *, now: str, sessions=None, gate=None) -> dict:
    from .start_next import UNREAD, _load

    try:
        load, load_cap = _load(gate)
    except UNREAD:
        load = load_cap = None
    return build.room(connection, load=load, load_cap=load_cap, interactive=interactive(connection, now=now,
                                                                                        sessions=sessions))


def plan(connection, items: list[int], *, now: str, sessions=None, gate=None) -> dict:
    """What a Build press on `items` would queue: `bundles` by repository, `refused` with each reason, the `room` now.

    A refused item refuses the whole press, as `build.queue` does; the dialog shows why and offers no Build.
    `room` is informative: a press queues whatever the room, and the claim waits for room.
    """
    taken, refused = [], []
    for item in items:
        try:
            taken.append(build._item(connection, item))  # the press's own check, so the dialog never disagrees with it
        except build.BuildRefused as refusal:
            refused.append({"id": item, "why": str(refusal)})
    revisions = reads.revisions(connection, [row["id"] for row in taken]) if taken else {}
    room = _room(connection, now=now, sessions=sessions, gate=gate)
    groups: dict[str, list[dict]] = {}
    for row in taken:
        groups.setdefault(row["repo"], []).append(row)
    bundles = []
    for repo, rows in groups.items():
        for start in range(0, len(rows), build.BUNDLE_MAX):
            chunk = rows[start:start + build.BUNDLE_MAX]
            bundles.append({"repo": repo, "name": Path(repo).name, "room": build.room_for(room, repo),
                            "model": build._model(connection, [row["id"] for row in chunk]),
                            "branch": "build/sd-<lead assignment>",
                            "items": [{"id": row["id"], "title": row["title"], "revision": revisions[row["id"]]}
                                      for row in chunk]})
    return {"read": now, "bundles": bundles, "refused": refused,
            "room": {"machine": room["machine"], "why": room["why"], "cap": build.MACHINE_CAP,
                     "repo_cap": build.REPO_CAP},
            "budget_minutes": build.BUDGET_MINUTES}


def kickstart(*, runner=subprocess.run) -> dict:
    """Start the dispatcher's tick now: `{ok, why}`. A failure only waits for the next two-minute slot."""
    service = f"gui/{os.getuid()}/{label_prefix()}.cron.{JOB}"
    try:
        done = runner(["/bin/launchctl", "kickstart", service], capture_output=True, text=True,
                      timeout=KICKSTART_SECONDS, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as failure:
        return {"ok": False, "service": service, "why": f"launchctl kickstart did not run: {failure}"}
    if done.returncode != 0:
        why = (done.stderr or done.stdout or "").strip().splitlines()
        return {"ok": False, "service": service,
                "why": f"launchctl kickstart exit {done.returncode}" + (f": {why[-1]}" if why else "")}
    return {"ok": True, "service": service, "why": ""}


def press(payload: dict, *, start=None):
    """POST /api/tasks/build: `{items, revisions}`; the write `action_route` runs, or ValueError for a bad body."""
    if set(payload) != {"items", "revisions"} or not isinstance(payload["revisions"], dict):
        raise ValueError("Provide the items to build and the revision the dialog read for each.")
    items = items_of(payload["items"])
    revisions = payload["revisions"]
    if any(not isinstance(value, str) for value in revisions.values()):
        raise ValueError("Each revision is the text the dialog read.")

    def write(connection):
        try:
            queued = build.queue(connection, items, who="dashboard", expected_revisions=revisions)
        except build.BuildRefused as refusal:
            # A refused press wrote nothing (`build.queue`'s one transaction): a 409, so the page reads again.
            return 409, {"error": f"Nothing queued: {refusal}.", "reload": True}
        return {"queued": [{"id": row["id"], "item": row["item"], "status": row["status"]} for row in queued],
                "kickstart": (start or kickstart)()}

    return write


def _waiting(connection, run: dict, items: list[int]) -> str:
    """Why a run waits on the operator: it is held (`blocked`, `abandoned`), or an open question note asks."""
    if run["outcome"] in ("blocked", "abandoned"):
        return run["detail"] or f"the run ended {run['outcome']}"
    asked = build.open_question(connection, items, run["created_at"])
    return f"question note #{asked['id']} on sd:{asked['item']}" if asked else ""


def _log_quiet(path: str | None, now: str) -> int | None:
    """Seconds since the run's log last grew, or None when it has none or it is not read."""
    if not path:
        return None
    try:
        changed = os.stat(path).st_mtime
    except OSError:
        return None
    clock = _at(now)
    return max(0, int(clock.timestamp() - changed)) if clock else None


def _members(connection, run: dict) -> list[dict]:
    rows = build.run(connection, run["id"])["members"]
    titles = reads.items_by_ids(connection, [row["item"] for row in rows])
    return [{"item": row["item"], "assignment": row["id"], "status": row["status"],
             "title": titles[row["item"]]["title"] if row["item"] in titles else ""} for row in rows]


def _open_row(connection, run: dict, now: str) -> dict:
    members = _members(connection, run)
    step = run["step"] or "claimed"
    beat = _seconds(run["heartbeat_at"] or run["created_at"], now)
    quiet = _log_quiet(run["log_path"], now)
    waiting = _waiting(connection, run, [member["item"] for member in members])
    lost = step != "enqueued" and run["outcome"] is None and (beat is None or beat >= build.STALE_SECONDS)
    state = ("waiting" if waiting else "lost" if lost
             else "stalled" if step in LOGGING and quiet is not None and quiet >= QUIET_SECONDS else "working")
    cancel = {"assignment": run["assignment"], "allowed": False, "reason": "", "revision": ""}
    try:
        current = operations.assignment_state(connection, run["assignment"])
        cancel.update(revision=current["revision"], allowed=current["capabilities"]["cancel"]["allowed"],
                      reason=current["capabilities"]["cancel"]["reason"])
    except (SdDbError, sqlite3.Error) as failure:
        cancel["reason"] = f"the assignment was not read: {failure}"
    if cancel["allowed"] and run["cancel_requested"]:
        cancel.update(allowed=False, reason=f"{run['cancel_requested']}; the supervisor stops at its next beat")
    elif cancel["allowed"] and step not in build.CANCELLABLE:
        cancel.update(allowed=False, reason=f"the run is at {step}; cancel its lane entry with "
                                            f"sd-ship lane cancel {members[0]['item'] if members else '<item>'}")
    return {"run": run["id"], "attempt": run["run"], "repo": run["repo"], "name": Path(run["repo"]).name,
            "items": members, "model": run["model"] or "", "step": step, "state": state, "why": waiting,
            "outcome": run["outcome"], "started": run["created_at"], "elapsed": _seconds(run["created_at"], now),
            "beat": beat, "quiet": quiet, "usd": round(build.run_spent(connection, run["id"]), 2),
            "log": run["log_path"] or "", "branch": run["branch"] or "", "worktree": run["work_path"] or "",
            "pull": build.pull_url(connection, run["repo"], run["branch"], [member["item"] for member in members]),
            "cancel": cancel}


def _retry_state(connection, run: dict) -> dict:
    """Retry on an ended run: only the lead's latest run, released, whose bundle ended blocked or cancelled.

    A bundle blocks on a `blocked` outcome and on a second loss at one step, whose run keeps the loss as its
    outcome (`build.LOSSES`); the lead assignment's `blocked` status covers both.
    A cancelled bundle keeps its worktree too, so Send to builder may resume it (pack sd:6020).
    """
    current = runner.queue_state(connection, run["assignment"])
    latest = current["run"]
    reason = ""
    if latest["id"] != run["id"]:
        reason = f"run {latest['id']} is newer"
    elif latest["released_at"] is None:
        reason = "the run still holds its lease"
    elif current["status"] not in AGAIN:
        reason = f"the bundle ended {current['status']}; Retry takes a blocked or cancelled one"
    return {"assignment": run["assignment"], "revision": current["revision"], "allowed": not reason, "reason": reason,
            "bundle": current["status"]}


def panel(connection, *, now: str) -> dict:
    """Queue's Builds panel: `runs`, each open build run; `recent`, the runs released in the last `RECENT_HOURS`.

    A read that failed is `error`, so the page says the builds were not read, never that none run.
    """
    try:
        rows = [_open_row(connection, run, now) for run in build.open_runs(connection)]
        since = (_at(now) - timedelta(hours=RECENT_HOURS)).isoformat().replace("+00:00", "Z")
        recent = []
        for row in build.ended_runs(connection, since):
            members = _members(connection, row)
            recent.append({"run": row["id"], "repo": row["repo"], "name": Path(row["repo"]).name, "items": members,
                           "pull": build.pull_url(connection, row["repo"], row["branch"], [m["item"] for m in members]),
                           "outcome": row["outcome"], "detail": row["detail"] or "",
                           "ended": row["released_at"], "step": row["step"] or "claimed", "model": row["model"] or "",
                           "usd": round(build.run_spent(connection, row["id"]), 2), "log": row["log_path"] or "",
                           "worktree": row["work_path"] or "", "retry": _retry_state(connection, row)})
    except (SdDbError, sqlite3.Error, ValueError, TypeError, KeyError) as failure:
        return {"runs": [], "recent": [], "error": str(failure) or "the build runs could not be read", "read": now}
    return {"runs": rows, "recent": recent, "error": "", "read": now, "quiet_seconds": QUIET_SECONDS,
            "stale_seconds": build.STALE_SECONDS, "hours": RECENT_HOURS}


def retry(connection, assignment: int, *, expected_revision: str, who: str, finding: str = "") -> dict:
    """Retry a blocked or cancelled build: each such member's item to `ready`, a `finding` note on it when one is
    sent (Send to builder), then its assignment queued again, in one transaction.

    The lead's revision is the one the panel read; a moved run is `StaleItem` (a 409). Each item must pass the
    press's own check once it is ready, so a retried bundle is one the next claim can take.
    """
    with transaction(connection):
        current = runner.queue_state(connection, assignment)
        if current["scope"] != build.SCOPE:
            raise workflow.WorkflowError(f"assignment {assignment} is not a build")
        if current["revision"] != expected_revision:
            raise workflow.StaleItem(f"build assignment {assignment} changed; read the Builds panel again")
        run = current["run"]
        state = _retry_state(connection, run) if run else {"allowed": False, "reason": "it never ran"}
        if not state["allowed"]:
            raise workflow.WorkflowError(f"Retry refused: {state['reason']}")
        members = build._members(connection, assignment, current["status"])
        if not members:
            raise workflow.WorkflowError(f"Retry refused: build run {run['id']} has no {current['status']} member")
        items = reads.items_by_ids(connection, [member["item"] for member in members])
        queued = []
        for member in members:
            item = items.get(member["item"])
            if item is not None and item["status"] == "blocked":
                transition(connection, member["item"], "ready", who=who, reason=f"Retry of build run {run['id']}")
            build.unpark(connection, member["item"])
            try:
                build._item(connection, member["item"])
            except build.BuildRefused as refusal:
                raise workflow.WorkflowError(f"Retry refused: {refusal}") from None
            if finding:
                add_note(connection, member["item"], "comment", build.FINDING + finding)
            fresh = runner.queue_state(connection, member["id"])["revision"]
            queued.append(runner.requeue(connection, member["id"], expected_revision=fresh, who=who))
            add_note(connection, member["item"], "comment",
                     f"Build assignment {member['id']} queued again by {who}: "
                     f"{'Send to builder' if finding else 'Retry'} of build run {run['id']}")
        return {"run": run["id"], "queued": [{"id": row["id"], "item": row["item"], "status": row["status"]}
                                             for row in queued]}
