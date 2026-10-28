"""The dispatcher's tick and the supervisor of one headless builder run (pack sd:6094).

Design: system `docs/work/2026-10-24-build-dispatcher/design.md`, step 2.

`dispatch` is one tick of the `build-dispatch` job: it writes the job's
heartbeat, reaps lost runs (`build.reap`), moves each `enqueued` run whose
lane entry merged to `cleaning` or ends it `lane_failed`, claims bundles
under the caps (`build.claim`), and spawns one supervisor for each open run
that has none. A spawn leaves the job's process group (`start_new_session`),
so neither the job's timeout nor launchd's exit cleanup reaches it.

`Supervisor` walks one run's steps from its `step` column, each written
before it starts: `worktree`, `building`, `reviewing` and `fixing`,
`enqueuing`, then `enqueued`, where it exits and the lane holds the run; a
fresh supervisor does `cleaning` after the merge. Every child runs in its own
process group, recorded in `builder_pgid` and `builder_start` before the
child runs: the child waits on a pipe and execs only once that write landed,
so a supervisor lost between the spawn and the write leaves nothing running.
A write that changes no row stops the supervisor before its next child.

The builder is judged by its last stream line, never its exit code (probe
#28947). Nothing before `enqueuing` pushes: `sd-ship lane enqueue` publishes
the head, behind the enqueuing compare-and-set that a requested cancel fails.

The same tick reaps and claims draft runs (`sd_db.draft`, pack sd:6361), one
at a time, and `DraftSupervisor` walks one: a read-only `claude -p` in the
repository's checkout, its reply parsed and written by `draft.write`.
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import build, draft, paths, sessions
from .build import Probe
from .ship import this_host
from .writes import add_note, now, record_cost, record_state

#: A child past this many seconds is ended: TERM to its group, `GRACE_SECONDS`, KILL.
TIMEOUT_SECONDS = build.BUDGET_MINUTES * 60
GRACE_SECONDS = 20
BEAT_SECONDS = 30
#: Reviews with blockers before the bundle blocks (lead, note #29482).
REVIEW_ROUNDS = 3
MAX_TURNS = 300
TITLE_MAX = 63
#: A read (`git status`, `lane list`) that takes longer is unread.
READ_SECONDS = 120
#: The `heartbeat` state row the tick writes first.
HEARTBEAT = "build-dispatch"
#: The lane entry states that end an `enqueued` run without a merge: the lane's `BLOCKED` ends, which
#: `lane retry` queues again (`prepared` is a merge the lane refused), and a cancel.
LANE_ENDED = ("failed", "skipped", "prepared", "cancelled")

#: The waits, in seconds, before a supervisor statement a locked database refused is sent again (pack sd:6588).
#: With each try's own `busy_timeout` they total about a minute, well under `build.STALE_SECONDS`.
LOCK_WAITS = (1, 2, 4, 8, 16)

#: The child waits for one byte on its pipe, written once its group is recorded, then execs the command.
GATE = ("import os, sys\n"
        "fd = int(sys.argv[1])\n"
        "go = os.read(fd, 1)\n"
        "os.close(fd)\n"
        "if go != b'1':\n"
        "    sys.exit(125)\n"
        "os.execvp(sys.argv[2], sys.argv[2:])\n")

BRIEF = """You are a headless builder run by the build dispatcher (pack sd:6094).

Build these items, one commit per item, in the worktree {worktree} on branch {branch}:
{items}
{findings}
Rules:
- Work only in {worktree}. Read each item with `sd task show N` and the repository's CLAUDE.md first.
- The dispatcher owns every item's status: never run `sd task status`, never push, never open a pull request.
- Write a test that fails before each fix, then make it pass; skip no test.
- End the commit that delivers a whole item with a `Closes: sd:N` trailer: an item no trailer names
  stays open and is not delivered. Add no attribution lines.
- Keep every commit line, and every body line, at 72 characters or less outside a code fence:
  `sd-ship lane enqueue` refuses a longer one.
- Write the pull-request title, a Conventional Commit of {title_max} characters or less, alone to {title}.
- Write the pull-request body, with `## Summary` and `## Test plan`, to {body}; quote each fail-first line.
  The body is public, so it names no local path (the worktree, a home directory): use repo-relative paths.
- Leave the worktree clean, with your commits on the branch.
- An item that needs the operator: record it with `sd task note N '<question>' --kind question` and skip it.

Your final message is your report: the commits, the tests run with their result lines, and anything not done.
"""

FIX = """The review of branch {branch} found these blockers. Fix each one fail-first as a new commit in
{worktree}, then update the body at {body}. Never push. Your final message is your report.

{blockers}
"""

DRAFT = """You are the headless lead, run by the build dispatcher (pack sd:6361). Draft the spec for one
captured item. You hold the read tools only: read the repository in the current directory, its CLAUDE.md
and AGENTS.md, and the code the item touches. You write nothing; the dispatcher writes your reply.

The item is sd:{item}, in {repo}:
Title: {title}
{body}

Use the existing context: the item, the repository and its rules. Ask only what would change the work and
the repository cannot answer. State the problem as an outsider would recognise it, and keep requirements
apart from assumptions. Each acceptance criterion names a check and its result ("`make test` passes with 0
failures"), never an intention. When the shape needs a design page before code, say so in the approach.

Your final message is the reply, in exactly this form and nothing else:

## Spec

Problem: <what is wrong today>
Approach: <the shape of the change, and the alternative you rejected with the reason>
Acceptance criteria:
- <a check and its result>
Risks: <what could make this wrong>

## Questions

<At most {questions}, only those whose answer changes the work. Each is its text, then two or more lines
that start "Option:", the recommended one first, ending " (Recommended)". Leave the section out when there
is none.>
"""

RESUME = """Your run was interrupted. Continue the brief in {worktree}: finish the items, commit, write the
title to {title} and the body to {body}, and leave the worktree clean. Your final message is your report.
"""


class Unread(Exception):
    """A read gave no answer: an unknown result, never a negative one."""


class Lost(Exception):
    """The run ended or moved under this supervisor; it writes nothing more."""


class Cancelled(Exception):
    """A cancel was asked; the active group is gone."""


class TimedOut(Exception):
    """A child ran past its timeout; its group is gone."""


class Survivor(Exception):
    """A process group still had a process after SIGKILL."""


@dataclass
class Tools:
    """The commands a supervisor runs, each an argv prefix: the seams a test fills with fakes."""
    claude: list[str]
    review: list[str]
    ship: list[str]
    lint: list[str]
    git: list[str] = field(default_factory=lambda: ["git"])


def judge(lines: list[str], *, session: str | None = None) -> dict:
    """The builder's verdict from the stream-json lines one child wrote: the last line, never the exit code.

    `state` is `pass`, `denied` (with `tools`), `max_turns`, `failed` or
    `unknown`. A pass needs a `result` line of subtype `success`, `is_error`
    false and an empty `permission_denials` list, in the session the run
    recorded (`session`), else the one its `init` line named: a line of
    another session is no evidence for this run.
    """
    text = [line for line in lines if line.strip()]
    init = None
    for line in text:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("type") == "system" and record.get("subtype") == "init":
            init = record.get("session_id")
            break
    if not text:
        return {"state": "unknown", "why": "the builder wrote no stream line"}
    try:
        final = json.loads(text[-1])
    except ValueError:
        return {"state": "unknown", "why": "the last stream line is not JSON"}
    if not isinstance(final, dict) or final.get("type") != "result":
        return {"state": "unknown", "why": "the last stream line is not a result"}
    want, named = session or init, final.get("session_id")
    if not named or (want and named != want):
        return {"state": "unknown", "why": f"the result names session {named or 'none'}, not {want or 'none'}",
                "final": final}
    result = {"final": final, "session_id": named}
    denials = final.get("permission_denials")
    if not isinstance(denials, list):
        return {**result, "state": "unknown", "why": "the result has no permission_denials list"}
    if denials:
        tools = sorted({str(row.get("tool_name") if isinstance(row, dict) else row) for row in denials})
        return {**result, "state": "denied", "tools": tools, "why": f"permission denied: {', '.join(tools)}"}
    if final.get("subtype") == "error_max_turns":
        return {**result, "state": "max_turns", "why": "the builder hit its turn limit"}
    if final.get("subtype") != "success" or final.get("is_error") is not False:
        return {**result, "state": "failed", "why": f"the result is {final.get('subtype')}, is_error "
                                                    f"{final.get('is_error')}"}
    return {**result, "state": "pass", "why": ""}


def _read(argv: list[str], *, env: dict | None = None) -> str:
    """A short read-only command's stdout; `Unread` when it fails or gives no answer in `READ_SECONDS`."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=READ_SECONDS, check=False,
                              stdin=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.SubprocessError) as error:
        raise Unread(f"{argv[0]} gave no answer: {error}") from None
    if done.returncode != 0:
        raise Unread(f"{' '.join(argv[:4])} failed: exit {done.returncode}: {done.stderr.strip()[:200]}")
    return done.stdout


def lane_entry(ship: list[str], cwd: Path | str, items: Collection[int], *, env: dict | None = None) -> dict | None:
    """The newest lane entry of any of `items` by enqueue order, from `sd-ship lane list`; None when there is none.

    Any member: the entry's item is the first member the branch delivers.
    """
    try:
        answer = json.loads(_read([*ship, "-C", str(cwd), "lane", "list"], env=env))
    except ValueError:
        raise Unread("sd-ship lane list answered no JSON") from None
    entries = answer.get("entries") if isinstance(answer, dict) and answer.get("ok") else None
    if not isinstance(entries, list):
        raise Unread("sd-ship lane list gave no entries")
    mine = [row for row in entries if isinstance(row, dict) and row.get("item") in items]
    return max(mine, key=lambda row: row.get("enqueue_seq") or 0) if mine else None


def _lead_item(connection, ident: str) -> tuple[int, list[int]]:
    members = build.run(connection, ident)["members"]
    return members[0]["item"], [member["item"] for member in members[1:]]


def watch(connection, *, lane: Callable[[dict, list[int]], dict | None], probe=Probe) -> list[dict]:
    """Step 7's start: each open `enqueued` run whose lane entry merged moves to `cleaning`; one whose entry
    failed, was skipped or was cancelled ends `lane_failed`. An unread lane changes nothing this tick.

    A merged run moves only once `verdict` reads its last supervisor and child gone, so the fresh supervisor
    never shares the worktree.
    """
    moved = []
    for row in build.open_runs(connection):
        if row["step"] != "enqueued" or row["outcome"] is not None:
            continue
        delivered = [member["item"] for member in build.run(connection, row["id"])["members"]
                     if member["status"] == "done"]
        try:
            entry = lane(row, delivered)
        except Unread:
            continue
        status = entry.get("status") if entry else None
        if status == "merged" and build.verdict(row, probe=probe)[0] == build.GONE:
            if build.merged(connection, row):
                moved.append({"run": row["id"], "step": "cleaning"})
        elif entry is not None and status in LANE_ENDED:
            reason = f"lane entry {entry.get('id')} {status}: {entry.get('reason') or entry.get('code') or 'no reason'}"
            if build.lane_failed(connection, row, reason):
                moved.append({"run": row["id"], "outcome": "lane_failed"})
    return moved


def dispatch(connection, *, owner: str, load: float | None, load_cap: float | None, interactive: list[dict] | None,
             spawn: Callable[[str], Any], lane: Callable[[dict, list[int]], dict | None], why: str = "",
             root: Path | None = None, probe=Probe, kill=build.kill_group) -> dict:
    """One tick: heartbeat, reap, watch the lane, claim, spawn; what each did.

    `load`, `load_cap` and `interactive` are read before the claim, outside
    the database; any unread (None) means no claim this tick, as does `why`,
    a reason the caller found (such as an unwritable log folder).
    """
    record_state(connection, "heartbeat", key=HEARTBEAT, body={"pid": os.getpid(), "owner": owner})
    reaped = build.reap(connection, probe=probe, kill=kill) + draft.reap(connection, probe=probe, kill=kill)
    moved = watch(connection, lane=lane, probe=probe)
    claimed: list[str] = []
    while not why and len(claimed) < build.MACHINE_CAP:
        try:
            taken = build.claim(connection, owner=owner, load=load, load_cap=load_cap, interactive=interactive,
                                root=root)
        except build.BuildRefused as refusal:
            why = str(refusal)
            break
        if taken is None:
            break
        claimed.append(taken["id"])
    drafted: list[str] = []
    if not why:
        # After the builds: a draft takes what machine room they leave, and no repository slot.
        available = build.room(connection, load=load, load_cap=load_cap, interactive=interactive)
        taken = draft.claim(connection, owner=owner, available=available)
        drafted += [taken["id"]] if taken else []
    spawned = []
    for row in [*build.open_runs(connection), *draft.open_runs(connection)]:
        if row["outcome"] is None and row["supervisor_pid"] is None and row["step"] != "enqueued":
            spawn(row["id"])
            spawned.append(row["id"])
    return {"reaped": reaped, "moved": moved, "claimed": claimed, "drafted": drafted, "spawned": spawned, "why": why}


def spawn(argv: list[str], *, log: Path) -> int:
    """Start a supervisor in a new session, out of the tick's process group; its pid."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as sink:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=sink, stderr=subprocess.STDOUT,
                                   start_new_session=True, close_fds=True)
    return process.pid


def log_dir(log_root: Path, repo: str) -> Path:
    """`<bulk root>/<repository>/build/`, the design's log folder."""
    return log_root / paths.expand(repo).name / "build"


def _environ(environ: dict | None) -> dict:
    env = dict(os.environ if environ is None else environ)
    # The token reaches the child's environment only: no row or log holds it.
    if env.get("CUSTOM_CLAUDE_CODE_OAUTH_TOKEN"):
        env["CLAUDE_CODE_OAUTH_TOKEN"] = env["CUSTOM_CLAUDE_CODE_OAUTH_TOKEN"]
    return env


class Patient:
    """A supervisor's connection: a statement a locked database refused outside a transaction is sent again.

    A statement refused outside a transaction (a `BEGIN`, a read, one
    autocommit write) wrote nothing, so a retry cannot write twice; one
    inside a transaction fails as it did. Each try waits its `busy_timeout`.
    """

    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name: str):
        return getattr(self.connection, name)

    def execute(self, sql: str, parameters=()):
        for wait in (*LOCK_WAITS, None):
            try:
                return self.connection.execute(sql, parameters)
            except sqlite3.OperationalError as error:
                if wait is None or self.connection.in_transaction or not (
                        "locked" in str(error) or "busy" in str(error)):
                    raise
            time.sleep(wait)


class Supervisor:
    """One run's supervisor: `run()` walks its steps and returns how it ended."""

    def __init__(self, connection, ident: str, *, tools: Tools, log_root: Path,
                 cited: Callable[[Path, str, str, str], Collection[int] | None], environ: dict | None = None,
                 beat_seconds: float = BEAT_SECONDS, timeout: float = TIMEOUT_SECONDS, grace: float = GRACE_SECONDS,
                 probe=Probe):
        """`cited(worktree, base, head, body)` is the items the lane reads the branch as delivering, None when unread:
        the lane's own reader, which lives beside it in `bin/`."""
        self.db: Any = Patient(connection)  # duck-types the connection the writes are annotated with
        self.ident, self.tools, self.probe, self.cited = ident, tools, probe, cited
        self.beat_seconds, self.timeout, self.grace = beat_seconds, timeout, grace
        self.row = build.run(self.db, ident)
        self.logs = log_dir(log_root, self.row["repo"])
        self.work = Path(self.row["work_path"])
        self.repo = paths.expand(self.row["repo"])
        self.lead, self.others = _lead_item(self.db, ident)
        lead_id = self.row["assignment"]
        self.title = self.logs / f"sd-{lead_id}.title"
        self.body = self.logs / f"sd-{lead_id}.body.md"
        self.log = self.logs / f"{ident}.jsonl"
        self.reviewed: str | None = None
        self.blockers: list[dict] = []
        self.last_beat = 0.0
        self.env = _environ(environ)

    # ----------------------------------------------------------- the walk

    def run(self) -> dict:
        pid = os.getpid()
        if not build.register(self.db, self.ident, pid=pid, pgid=os.getpgrp(), start=self.probe.started(pid)):
            return {"run": self.ident, "outcome": None, "why": "another supervisor holds the run, or it ended"}
        self.logs.mkdir(parents=True, exist_ok=True)
        self.last_beat = time.monotonic()
        try:
            return self.walk()
        except Lost:
            return {"run": self.ident, "outcome": None, "why": "the run ended or moved under this supervisor"}
        except Cancelled:
            return self.finish("cancelled", self.fresh()["cancel_requested"] or "cancelled")
        except TimedOut:
            return self.finish("timed_out", f"a child ran past {self.timeout:g} s; its group was ended")
        except Survivor as survivor:
            return self.finish("blocked", str(survivor))
        except Unread as unread:
            # An unknown result: no write, so the reap finds the run lost and retries it once.
            return {"run": self.ident, "outcome": None, "why": str(unread)}

    def walk(self) -> dict:
        step = self.row["step"]
        steps = {"claimed": self.worktree, "worktree": self.worktree, "building": self.building,
                 "reviewing": self.reviewing, "fixing": self.reviewing, "enqueuing": self.enqueuing,
                 "cleaning": self.cleaning}
        while step in steps:
            ended = steps[step]()
            if isinstance(ended, dict):
                return ended
            step = ended
        if step == "enqueued":
            return {"run": self.ident, "outcome": None, "step": "enqueued"}
        return self.finish("blocked", f"no supervisor step for {step}")

    def finish(self, outcome: str, detail: str, *, question: str | None = None) -> dict:
        ended = build.end(self.db, self.ident, outcome, detail, question=question)
        return ended or {"run": self.ident, "outcome": None, "why": "the run ended or moved before its last write"}

    def fresh(self) -> dict:
        return build.run(self.db, self.ident)

    def enter(self, step: str, **fields) -> None:
        if self.fresh()["cancel_requested"] and step in build.CANCELLABLE:
            raise Cancelled
        if not build.write(self.db, self.ident, step=step, heartbeat_at=now(), **fields):
            raise Lost
        self.last_beat = time.monotonic()

    # -------------------------------------------------------------- steps

    def worktree(self) -> str | dict:
        self.enter("worktree")
        branch = self.row["branch"]
        if self.work.is_dir():
            current = _read([*self.tools.git, "-C", str(self.work), "branch", "--show-current"], env=self.env).strip()
            if current != branch:
                return self.finish("blocked", f"worktree {self.work} is on {current or 'no branch'}, not {branch}")
            return "building"
        if self.child([*self.tools.git, "-C", str(self.repo), "fetch", "-q", "origin"], cwd=self.repo,
                      name="worktree") != 0:
            return self.finish("blocked", f"git fetch in {self.repo} failed; see {self.out('worktree')}")
        try:
            _read([*self.tools.git, "-C", str(self.repo), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], env=self.env)
            argv = ["worktree", "add", str(self.work), branch]
        except Unread:
            argv = ["worktree", "add", "-b", branch, str(self.work), self.base()]
        if self.child([*self.tools.git, "-C", str(self.repo), *argv], cwd=self.repo, name="worktree") != 0:
            return self.finish("blocked", f"git worktree add {self.work} failed; see {self.out('worktree')}")
        return "building"

    def building(self) -> str | dict:
        self.enter("building", log_path=str(self.log))
        session = self.fresh()["session_id"]
        prompt = (RESUME if session else BRIEF).format(**self.brief())
        return self.claude(prompt, session=session, then="reviewing")

    def reviewing(self) -> str | dict:
        self.enter("reviewing")
        head = self.head()
        answer: dict | None = None
        for _attempt in range(2):
            out = self.out("review")
            out.write_bytes(b"")
            self.child([*self.tools.review, "-C", str(self.work), "--scope", "branch", "--json"], cwd=self.work,
                       name="review")
            answer = self.review_answer(out, head)
            if answer is not None:
                break
        if answer is None:
            return self.finish("blocked", f"the review gave no answer twice at {head[:12]}; see {self.out('review')}")
        if answer["status"] in ("clean", "advisory"):
            self.reviewed = head
            return "enqueuing"
        rounds = (self.fresh()["review_round"] or 0) + 1
        if not build.write(self.db, self.ident, review_round=rounds):
            raise Lost
        self.blockers = answer["blockers"]
        if rounds >= REVIEW_ROUNDS:
            return self.finish("blocked", f"{rounds} review rounds left blockers: {self.summary(self.blockers)}")
        return self.fix()

    def fix(self) -> str | dict:
        self.enter("fixing")
        session = self.fresh()["session_id"]
        if not session:
            return self.finish("blocked", "no builder session recorded to resume for the fix")
        prompt = FIX.format(blockers=self.summary(self.blockers, limit=None), **self.brief())
        return self.claude(prompt, session=session, then="reviewing")

    def enqueuing(self) -> str | dict:
        if not build.enqueuing(self.db, self.ident):
            if self.fresh()["cancel_requested"]:
                raise Cancelled
            raise Lost
        self.last_beat = time.monotonic()
        head = self.head()
        if self.reviewed is not None and head != self.reviewed:
            if not build.write(self.db, self.ident, step="reviewing"):
                raise Lost
            return "reviewing"
        try:
            body = self.body.read_text(encoding="utf-8")
        except OSError:
            body = ""
        cited = self.cited(self.work, self.base(), head, body)
        if cited is None:
            raise Unread(f"the commits {head[:12]} adds were not read")
        # Delivery as the lane reads it: a member no `Closes:` trailer cites was skipped, and stays open.
        delivered = [item for item in [self.lead, *self.others] if item in cited]
        # A retry's branch keeps the lost run's trailers: a member this run's builder skipped with a question
        # waits on it (pack sd:6571).
        asked = [item for item in delivered if build.open_question(self.db, [item], self.row["created_at"])]
        delivered = [item for item in delivered if item not in asked]
        if not delivered and asked:
            return self.finish("blocked", f"every cited item has an open question since the run started: "
                                          f"{', '.join(f'sd:{item}' for item in asked)}")
        if asked:
            # The lane closes every open item a branch trailer cites; a `Refs:` line keeps these open.
            refs = f"Refs: {' '.join(f'sd:{item}' for item in asked)}"
            if refs not in body.splitlines():
                body = body.rstrip("\n") + f"\n\n{refs}\n"
                self.body.write_text(body, encoding="utf-8")
        if not delivered:
            return self.finish("blocked", "the branch delivers no item: no commit has a `Closes: sd:N` trailer "
                                          "for one of the run's items")
        entry = lane_entry(self.tools.ship, self.work, delivered, env=self.env)
        if entry and entry.get("status") != "cancelled" and entry.get("expected_head") == head:
            return self.lane_done(entry, delivered)
        try:
            title = self.title.read_text(encoding="utf-8").strip()
        except OSError:
            title = ""
        if not title or len(title) > TITLE_MAX or "\n" in title:
            return self.finish("blocked", f"the title at {self.title} is missing or over {TITLE_MAX} characters")
        errors = self.out("lint.err")
        errors.write_bytes(b"")
        if self.child([*self.tools.lint, "--pr-body", str(self.body)], cwd=self.work, name="lint") != 0:
            # The lint prints its failures on stderr; its stdout holds only notes (pack sd:6402).
            try:
                failures = [line[5:] for line in errors.read_text(encoding="utf-8").splitlines()
                            if line.startswith("FAIL ")]
            except OSError:
                failures = []
            return self.finish("blocked", f"sd-docs-lint refused the body at {self.body}: "
                                          f"{'; '.join(failures[:3]) or 'no FAIL line'}; see {errors}")
        out = self.out("enqueue")
        out.write_bytes(b"")
        items = [arg for item in delivered for arg in ("--item", str(item))]
        # The run is each delivered item's whole delivery, so it is the last pull request: `--deliver`.
        self.child([*self.tools.ship, "-C", str(self.work), "lane", "enqueue", *items, "--deliver", "--title", title,
                    "--body-file", str(self.body), "--expected-head", head], cwd=self.work, name="enqueue")
        try:
            answer = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            answer = None
        if not isinstance(answer, dict) or answer.get("ok") is not True:
            reason = answer.get("error") if isinstance(answer, dict) else "no JSON answer"
            return self.finish("blocked", f"sd-ship lane enqueue refused: {reason}; see {out}")
        return self.lane_done(answer, delivered)

    def lane_done(self, entry: dict, delivered: list[int]) -> str | dict:
        if build.enqueued(self.db, self.ident, delivered):
            add_note(self.db, delivered[0], "comment",
                     f"Build run {self.ident} enqueued {self.row['branch']} in the lane"
                     f"{' as entry ' + str(entry.get('id')) if entry.get('id') else ''}")
            return "enqueued"
        if self.fresh()["cancel_requested"]:
            return self.finish("blocked", f"a cancel was asked after the lane entry was written; cancel it with "
                                          f"`sd-ship lane cancel {delivered[0]}`")
        raise Lost

    def cleaning(self) -> dict:
        self.enter("cleaning")
        if not self.work.is_dir():
            return self.finish("done", f"worktree {self.work} was already removed")
        try:
            dirty = _read([*self.tools.git, "-C", str(self.work), "status", "--porcelain"], env=self.env).strip()
        except Unread as unread:
            dirty = f"unread: {unread}"
        if dirty:
            add_note(self.db, self.lead, "comment",
                     f"Build run {self.ident} kept worktree {self.work}: it is not clean ({dirty.splitlines()[0]})")
            return self.finish("done", f"worktree {self.work} kept: not clean")
        # A session other than this run's builder works in it (pack sd:6024): it stays.
        own = self.fresh()["session_id"]
        held = sessions.describe(sessions.holders(self.db, str(self.work), machine=this_host(),
                                                  exclude=(own,) if own else ()))
        if held:
            add_note(self.db, self.lead, "comment", f"Build run {self.ident} kept worktree {self.work}: {held}")
            return self.finish("done", f"worktree {self.work} kept: {held}")
        if self.child([*self.tools.git, "-C", str(self.repo), "worktree", "remove", str(self.work)], cwd=self.repo,
                      name="cleaning") != 0:
            add_note(self.db, self.lead, "comment",
                     f"Build run {self.ident} kept worktree {self.work}: git worktree remove failed")
            return self.finish("done", f"worktree {self.work} kept: removal failed")
        return self.finish("done", f"worktree {self.work} removed")

    # ------------------------------------------------------------ helpers

    def brief(self) -> dict:
        items = [self.lead, *self.others]
        titles = {row["id"]: row["title"] for row in self.db.execute(
            f"SELECT id, title FROM item WHERE id IN ({', '.join('?' for _ in items)})", items)}
        return {"worktree": self.work, "branch": self.row["branch"], "title": self.title, "body": self.body,
                "title_max": TITLE_MAX, "items": "\n".join(f"- sd:{item} {titles.get(item, '')}" for item in items),
                "findings": self.findings(items)}

    def findings(self, items: list[int]) -> str:
        """The Send to builder notes on `items` since the lead's first run, up to this run (pack sd:6020); "" for none.

        A bundle queued again keeps its lead, so this run resumes the branch an earlier run left.
        """
        first = self.db.execute("SELECT MIN(created_at) FROM runner_run WHERE assignment = ?",
                                (self.row["assignment"],)).fetchone()[0]
        notes = self.db.execute(
            f"SELECT item, body FROM note WHERE item IN ({', '.join('?' for _ in items)}) AND body LIKE ? "
            f"AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp, id",
            (*items, build.FINDING + "%", first, self.row["created_at"])).fetchall()
        if not notes:
            return ""
        sent = "\n".join(f"- sd:{note['item']}: {note['body'][len(build.FINDING):].strip()}" for note in notes)
        return (f"\nThe worktree already holds the commits of an earlier run on {self.row['branch']}: build on them.\n"
                f"The operator sent these findings to the branch, oldest first. Fix each one the branch does not\n"
                f"fix yet, fail-first, as a new commit:\n{sent}\n")

    def claude(self, prompt: str, *, session: str | None, then: str) -> str | dict:
        argv = [*self.tools.claude, "-p", prompt, "--output-format", "stream-json", "--verbose",
                "--permission-mode", "auto", "--max-turns", str(MAX_TURNS), "--model", self.row["model"] or build.OPUS]
        if session:
            argv += ["--resume", session]
        offset = self.log.stat().st_size if self.log.exists() else 0
        self.child(argv, cwd=self.work, name="claude", out=self.log, session=session is None)
        with open(self.log, "rb") as handle:
            handle.seek(offset)
            lines = handle.read().decode("utf-8", "replace").splitlines()
        verdict = judge(lines, session=session or self.fresh()["session_id"])
        final = verdict.get("final")
        if final is not None:
            fields: dict[str, Any] = {"final": json.dumps(final, sort_keys=True)[:65536]}
            if verdict.get("session_id") and not session:
                fields["session_id"] = verdict["session_id"]
            if not build.write(self.db, self.ident, **fields):
                raise Lost
            self.cost(final)
        if verdict["state"] == "pass":
            if isinstance(final, dict) and isinstance(final.get("result"), str) and final["result"].strip():
                add_note(self.db, self.lead, "comment", f"Build run {self.ident} report:\n{final['result'][:8000]}")
            problem = self.unfinished()
            return self.finish("blocked", problem) if problem else then
        if verdict["state"] == "denied":
            return self.finish("blocked", verdict["why"],
                               question=f"Build run {self.ident}: the builder was denied {', '.join(verdict['tools'])}. "
                                        f"Allow it, or change the brief, then requeue.")
        if verdict["state"] == "max_turns":
            return self.finish("error_max_turns", verdict["why"])
        return self.finish("blocked", f"{verdict['why']}; log {self.log}")

    def cost(self, final: dict) -> None:
        usage = final.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        usd = final.get("total_cost_usd")
        record_cost(self.db, source="run", role="author", repo=self.row["repo"], assignment=self.row["assignment"],
                    pass_=self.ident, owner_pid=os.getpid(),
                    tokens_in=usage.get("input_tokens") if isinstance(usage.get("input_tokens"), int) else None,
                    tokens_out=usage.get("output_tokens") if isinstance(usage.get("output_tokens"), int) else None,
                    usd=float(usd) if isinstance(usd, (int, float)) else None)

    def unfinished(self) -> str:
        """Why a passing builder's worktree is not done: dirty, or no commit ahead of the base; empty when done."""
        try:
            if _read([*self.tools.git, "-C", str(self.work), "status", "--porcelain"], env=self.env).strip():
                return f"the builder left worktree {self.work} dirty"
            ahead = _read([*self.tools.git, "-C", str(self.work), "rev-list", "--count", f"{self.base()}..HEAD"], env=self.env)
        except Unread as unread:
            return f"the worktree was not read: {unread}"
        return "" if ahead.strip().isdigit() and int(ahead) > 0 else f"the builder left no commit on {self.row['branch']}"

    def base(self) -> str:
        try:
            ref = _read([*self.tools.git, "-C", str(self.repo), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], env=self.env)
        except Unread:
            return "origin/main"
        return ref.strip() or "origin/main"

    def head(self) -> str:
        return _read([*self.tools.git, "-C", str(self.work), "rev-parse", "HEAD"], env=self.env).strip()

    def review_answer(self, out: Path, head: str) -> dict | None:
        """The review's `status` and blockers, for this head; None for an unknown answer."""
        try:
            answer = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(answer, dict):
            return None
        subject = answer.get("subject")
        if isinstance(subject, dict) and subject.get("head") and subject["head"] != head:
            return None
        status = answer.get("status")
        findings = answer.get("findings")
        findings = findings if isinstance(findings, list) else []
        if status in ("clean", "advisory"):
            return {"status": status, "blockers": []}
        if status == "blocking":
            return {"status": status, "blockers": [row for row in findings
                                                   if isinstance(row, dict) and row.get("disposition") == "blocking"]}
        return None

    @staticmethod
    def summary(blockers: list[dict], limit: int | None = 3) -> str:
        # `summary` is the text of an `sd-review --json` finding record.
        lines = [f"{row.get('path', '?')}:{row.get('line', '?')} {row.get('summary') or ''}".strip() for row in blockers]
        return "; ".join(lines[:limit]) if limit else "\n".join(f"- {line}" for line in lines)

    def out(self, name: str) -> Path:
        return self.logs / f"{self.ident}.{name}.out"

    # -------------------------------------------------------------- children

    def child(self, argv: list[str], *, cwd: Path, name: str, out: Path | None = None, session: bool = False) -> int:
        """Run one child in its own process group, recorded before it runs; its exit code.

        The child waits on a pipe until `builder_pgid` and `builder_start`
        are written, then execs `argv`; a failed write closes the pipe and
        the child exits unrun. While it runs, the supervisor beats, stops at
        a requested cancel or a lost run, and ends it past `timeout`. Its
        group must read gone after it exits, or the run is a `Survivor`.
        """
        target = out or self.out(name)
        read, gate = os.pipe()
        try:
            with open(target, "ab") as sink, open(self.out(name + ".err"), "ab") as errors:
                process = subprocess.Popen([sys.executable, "-c", GATE, str(read), *argv], cwd=cwd,
                                           stdin=subprocess.DEVNULL, stdout=sink, stderr=errors, env=self.env,
                                           pass_fds=(read,), start_new_session=True)
        except OSError:
            os.close(gate)
            raise
        finally:
            os.close(read)
        try:
            recorded = build.write(self.db, self.ident, builder_pgid=process.pid,
                                   builder_start=self.probe.started(process.pid))
            if recorded:
                os.write(gate, b"1")
        finally:
            os.close(gate)
        if not recorded:
            process.wait()
            raise Lost
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                code = process.wait(timeout=min(1.0, self.beat_seconds))
                break
            except subprocess.TimeoutExpired:
                pass
            try:
                if session:
                    self.watch_session()
                self.beat(process)
            except Lost:
                # No write lands any more: the group goes before the supervisor does.
                self.end_group(process.pid, process)
                raise
            if time.monotonic() >= deadline:
                if not self.end_group(process.pid, process):
                    raise Survivor(f"process group {process.pid} ({name}) still had a process after SIGKILL")
                raise TimedOut
        if not self.end_group(process.pid, process):
            raise Survivor(f"process group {process.pid} ({name}) still had a process after SIGKILL")
        return code

    def beat(self, process: subprocess.Popen) -> None:
        """Beat when one is due; stop the child's group at a lost run or a requested cancel."""
        if time.monotonic() - self.last_beat < self.beat_seconds:
            return
        self.last_beat = time.monotonic()
        if not build.beat(self.db, self.ident):
            raise Lost
        row = self.fresh()
        if row["cancel_requested"] and row["step"] in build.CANCELLABLE:
            if not self.end_group(process.pid, process):
                raise Survivor(f"process group {process.pid} still had a process after SIGKILL at a cancel")
            raise Cancelled

    def watch_session(self) -> None:
        """Write the builder's session id as soon as its `init` line names it, so the room counts it once."""
        if self.fresh()["session_id"] or not self.log.exists():
            return
        with open(self.log, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and record.get("type") == "system" and record.get("subtype") == "init":
                    if record.get("session_id") and not build.write(self.db, self.ident,
                                                                    session_id=record["session_id"]):
                        raise Lost
                    return

    def end_group(self, pgid: int, process: subprocess.Popen | None = None) -> bool:
        """TERM the group, `grace` seconds, then SIGKILL; True once ESRCH answers.

        The leader is reaped as it dies (`process.poll`): a zombie leader is
        still a member of its group, and would read as a survivor.
        """
        def gone() -> bool:
            if process is not None:
                process.poll()
            return self.probe.group(pgid) is False

        if gone():
            return True
        for sent, wait in ((signal.SIGTERM, self.grace), (signal.SIGKILL, 5.0)):
            try:
                os.killpg(pgid, sent)
            except ProcessLookupError:
                return True
            except OSError:
                pass  # EPERM may be a group of zombies only (sd:6406): `gone` decides
            stop = time.monotonic() + wait
            while time.monotonic() < stop:
                if gone():
                    return True
                time.sleep(0.05)
        return gone()


class DraftSupervisor(Supervisor):
    """One draft run's supervisor (pack sd:6361): `drafting`, then `draft.write` or `draft.end`.

    It shares the build supervisor's child, beat and group handling: the
    child's group is recorded before it runs, a lost run ends it, and the
    `timeout` (`draft.BUDGET_MINUTES`) ends a hung one, which the reap
    retries once. The child holds `draft.TOOLS` only, in `dontAsk` mode and
    with no MCP server, so its one way to the database is its reply.
    """

    def __init__(self, connection, ident: str, *, tools: Tools, log_root: Path, environ: dict | None = None,
                 beat_seconds: float = BEAT_SECONDS, timeout: float = draft.BUDGET_MINUTES * 60,
                 grace: float = GRACE_SECONDS, probe=Probe):
        self.db, self.ident, self.tools, self.probe = Patient(connection), ident, tools, probe
        self.beat_seconds, self.timeout, self.grace = beat_seconds, timeout, grace
        self.row = build.run(self.db, ident)
        self.logs = log_dir(log_root, self.row["repo"])
        self.repo = self.work = paths.expand(self.row["repo"])
        self.log = self.logs / f"{ident}.jsonl"
        self.item = self.db.execute("SELECT item FROM assignment WHERE id = ?",
                                       (self.row["assignment"],)).fetchone()["item"]
        self.last_beat = 0.0
        self.env = _environ(environ)

    def run(self) -> dict:
        pid = os.getpid()
        if not build.register(self.db, self.ident, pid=pid, pgid=os.getpgrp(), start=self.probe.started(pid)):
            return {"run": self.ident, "outcome": None, "why": "another supervisor holds the run, or it ended"}
        self.logs.mkdir(parents=True, exist_ok=True)
        self.last_beat = time.monotonic()
        try:
            return self.drafting()
        except (Lost, Cancelled):
            return {"run": self.ident, "outcome": None, "why": "the run ended or moved under this supervisor"}
        except TimedOut:
            return self.finish("timed_out", f"the draft ran past {self.timeout:g} s; its group was ended")
        except Survivor as survivor:
            return self.finish("blocked", str(survivor))

    def finish(self, outcome: str, detail: str, *, question: str | None = None) -> dict:
        ended = draft.end(self.db, self.ident, outcome, detail)
        return ended or {"run": self.ident, "outcome": None, "why": "the run ended or moved before its last write"}

    def argv(self) -> list[str]:
        title, body = draft.item_text(self.db, self.item)
        prompt = DRAFT.format(item=self.item, repo=self.row["repo"], title=title, body=body.strip() or "(no body)",
                              questions=draft.QUESTIONS_MAX)
        return [*self.tools.claude, "-p", prompt, "--output-format", "stream-json", "--verbose",
                "--tools", *draft.TOOLS, "--permission-mode", "dontAsk", "--strict-mcp-config",
                "--max-turns", str(draft.MAX_TURNS), "--model", self.row["model"] or build.OPUS]

    def drafting(self) -> dict:
        if not build.write(self.db, self.ident, step="drafting", heartbeat_at=now(),
                           log_path=str(self.log)):
            raise Lost
        self.last_beat = time.monotonic()
        offset = self.log.stat().st_size if self.log.exists() else 0
        self.child(self.argv(), cwd=self.repo, name="claude", out=self.log, session=True)
        with open(self.log, "rb") as handle:
            handle.seek(offset)
            lines = handle.read().decode("utf-8", "replace").splitlines()
        verdict = judge(lines, session=self.fresh()["session_id"])
        final = verdict.get("final")
        if final is not None:
            fields: dict[str, Any] = {"final": json.dumps(final, sort_keys=True)[:65536]}
            if verdict.get("session_id"):
                fields["session_id"] = verdict["session_id"]
            if not build.write(self.db, self.ident, **fields):
                raise Lost
            self.cost(final)
        if verdict["state"] != "pass":
            # A turn limit is no loss here: a fresh run has no session to resume, so it blocks as any other end.
            return self.finish("blocked", f"{verdict['why']}; nothing was written; log {self.log}")
        parsed = draft.parse(final.get("result") if isinstance(final, dict) else None)
        if parsed is None:
            return self.finish("blocked", f"the reply has no `## Spec`, or a question short of two Option: "
                                          f"lines; nothing was written; log {self.log}")
        if not draft.write(self.db, self.ident, *parsed):
            raise Lost
        return {"run": self.ident, "outcome": "done", "questions": len(parsed[1])}
