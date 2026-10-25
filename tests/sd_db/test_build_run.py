"""The dispatcher's tick and the supervisor of a headless builder run (pack sd:6094).

The design's failure table names most of these tests: system
`docs/work/2026-10-24-build-dispatcher/design.md`, step 2. The supervisor
runs real git in a fixture repository with a bare origin; `claude`,
`sd-review`, `sd-ship` and `sd-docs-lint` are fakes that read their next
answer from a plan file and log each call.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from sd_db import build, build_run, operations
from sd_db.database import connect
from sd_db.migrate import initialise
from sd_db.workflow import item_state
from sd_db.writes import create_item, upsert_repo

from . import support

#: One fake for every tool: its role is its file name, its answers come from `<plans>/<role>.json`.
FAKE = textwrap.dedent('''
    import json, os, subprocess, sys, time
    from pathlib import Path
    role, plans = Path(sys.argv[0]).stem, Path(os.environ["FAKE_PLANS"])
    with open(plans / "calls.jsonl", "a") as log:
        log.write(json.dumps({"role": role, "argv": sys.argv[1:], "cwd": os.getcwd()}) + "\\n")
    plan = plans / f"{role}.json"
    queue = json.loads(plan.read_text()) if plan.exists() else []
    mode = queue.pop(0) if queue else "default"
    plan.write_text(json.dumps(queue))
    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    def line(record):
        print(json.dumps(record), flush=True)
    if role == "claude":
        session = "session-fixture"
        if "--resume" in sys.argv:
            session = sys.argv[sys.argv.index("--resume") + 1]
        line({"type": "system", "subtype": "init", "session_id": session})
        if mode == "hang":
            time.sleep(120)
        if mode == "slow":
            time.sleep(3)
        if mode == "silent":
            sys.exit(0)
        Path("work.txt").write_text(Path("work.txt").read_text() + mode + "\\n" if Path("work.txt").exists()
                                    else mode + "\\n")
        git("add", "work.txt")
        git("-c", "commit.gpgsign=false", "commit", "-qm", f"fix: {mode}")
        final = {"type": "result", "subtype": "success", "is_error": False, "permission_denials": [],
                 "session_id": session, "result": f"built ({mode})", "total_cost_usd": 0.42,
                 "usage": {"input_tokens": 10, "output_tokens": 20}}
        if mode == "deny":
            final["permission_denials"] = [{"tool_name": "Bash", "tool_input": {"command": "git push"}}]
        if mode == "max_turns":
            final.update(subtype="error_max_turns", is_error=True)
        if mode == "other":
            final["session_id"] = "session-of-another-run"
        line(final)
        sys.exit(3 if mode in ("deny", "exit3") else 0)
    if role == "sd-review":
        work = sys.argv[sys.argv.index("-C") + 1]
        if mode == "cancel":
            import sqlite3
            db = sqlite3.connect(os.environ["FAKE_DB"])
            db.execute("UPDATE runner_run SET cancel_requested = 'cancelled by fixture' WHERE released_at IS NULL")
            db.commit()
            mode = "clean"
        if mode == "garbage":
            print("not json")
            sys.exit(4)
        findings = [{"path": "work.txt", "line": 1, "title": "a blocker", "disposition": "blocking"}]
        print(json.dumps({"status": "blocking" if mode == "blocking" else "clean",
                          "subject": {"head": git("-C", work, "rev-parse", "HEAD")},
                          "findings": findings if mode == "blocking" else []}))
    if role == "sd-ship":
        lane = plans / "lane.json"
        entries = json.loads(lane.read_text()) if lane.exists() else []
        if "list" in sys.argv:
            print(json.dumps({"ok": mode != "unread", "entries": entries}))
            sys.exit(3 if mode == "unread" else 0)
        argv = sys.argv
        items = [int(argv[n + 1]) for n, arg in enumerate(argv) if arg == "--item"]
        entry = {"id": f"e{len(entries) + 1}", "item": items[0], "status": "pending", "enqueue_seq": len(entries) + 1,
                 "expected_head": argv[argv.index("--expected-head") + 1]}
        lane.write_text(json.dumps(entries + [entry]))
        print(json.dumps({"ok": True, **entry}))
    if role == "sd-docs-lint":
        sys.exit(1 if mode == "refuse" else 0)
''')


def group_gone(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


class Case(unittest.TestCase):
    bundle: dict
    items: list[int]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.database = self.root / "sd.db"
        initialise(self.database)
        self.db = connect(self.database)
        self.addCleanup(self.db.close)
        self.repo = support.repository(self.root / "fixture", bare=self.root / "origin.git")
        upsert_repo(self.db, str(self.repo), remote="https://github.com/fixture/repo.git", managed=1)
        self.plans = self.root / "plans"
        self.plans.mkdir()
        tools = self.root / "tools"
        tools.mkdir()
        for role in ("claude", "sd-review", "sd-ship", "sd-docs-lint"):
            (tools / f"{role}.py").write_text(FAKE, encoding="utf-8")
        self.tools = build_run.Tools(**{name: [sys.executable, str(tools / f"{role}.py")] for name, role in
                                        (("claude", "claude"), ("review", "sd-review"), ("ship", "sd-ship"),
                                         ("lint", "sd-docs-lint"))})
        self.env = {**os.environ, "FAKE_PLANS": str(self.plans), "FAKE_DB": str(self.database)}
        self.logs = self.root / "bulk"

    def plan(self, **roles):
        for role, modes in roles.items():
            (self.plans / f"{role.replace('_', '-')}.json").write_text(json.dumps(modes), encoding="utf-8")

    def calls(self, role=None):
        path = self.plans / "calls.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [row for row in rows if role is None or row["role"] == role]

    def press(self, count=1):
        self.items = [create_item(self.db, kind="task", title=f"Build me {n}", repo=str(self.repo), status="ready")
                      for n in range(count)]
        build.queue(self.db, self.items, who="operator")
        bundle = build.claim(self.db, owner="fixture", load=1.0, load_cap=40.0, interactive=[],
                             root=self.root / "worktrees")
        assert bundle is not None
        self.bundle = bundle
        return bundle

    def supervisor(self, ident=None, **options):
        options = {"beat_seconds": 0.2, "timeout": 30, "grace": 0.5, **options}
        return build_run.Supervisor(self.db, ident or self.bundle["id"], tools=self.tools, log_root=self.logs,
                                    environ=self.env, **options)

    def write_pr(self, title="feat(fixture): build the fixture"):
        logs = build_run.log_dir(self.logs, self.bundle["repo"])
        logs.mkdir(parents=True, exist_ok=True)
        (logs / f"sd-{self.bundle['assignment']}.title").write_text(title + "\n", encoding="utf-8")
        (logs / f"sd-{self.bundle['assignment']}.body.md").write_text("## Summary\n\nx\n\n## Test plan\n\ny\n")

    def wait_for_builder(self, connection):
        """Until the builder (not the worktree's git) runs: the claude call is logged and its group recorded."""
        for _ in range(200):
            row = build.run(connection, self.bundle["id"])
            if row["step"] == "building" and self.calls("claude") and row["builder_pgid"]:
                return
            time.sleep(0.05)
        raise AssertionError("the builder never started")

    def statuses(self):
        return [item_state(self.db, item)["item"]["status"] for item in self.items]

    def latest(self):
        return dict(self.db.execute("SELECT * FROM runner_run ORDER BY run DESC LIMIT 1").fetchone())

    def remote_branches(self):
        return support.git(self.root / "origin.git", "for-each-ref", "--format=%(refname:short)", "refs/heads")


class Judge(unittest.TestCase):
    def lines(self, **final):
        record = {"type": "result", "subtype": "success", "is_error": False, "permission_denials": [],
                  "session_id": "s1", **final}
        return [json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}), json.dumps(record)]

    def test_judge_reads_the_last_line(self):
        self.assertEqual(build_run.judge(self.lines())["state"], "pass")
        self.assertEqual(build_run.judge(self.lines(subtype="error_max_turns", is_error=True))["state"], "max_turns")
        self.assertEqual(build_run.judge(self.lines(is_error=True))["state"], "failed")
        denied = build_run.judge(self.lines(permission_denials=[{"tool_name": "Bash"}]))
        self.assertEqual((denied["state"], denied["tools"]), ("denied", ["Bash"]))
        for lines in ([], self.lines()[:1], ["not json"], self.lines() + ["{\"type\": \"assistant\"}"]):
            with self.subTest(lines=lines):
                self.assertEqual(build_run.judge(lines)["state"], "unknown", "no final result is not a pass")
        missing = self.lines()
        missing[-1] = json.dumps({k: v for k, v in json.loads(missing[-1]).items() if k != "permission_denials"})
        self.assertEqual(build_run.judge(missing)["state"], "unknown")

    def test_judge_refuses_another_sessions_line(self):
        """A judge pass is tied to the run's own session: a result of another session is unknown."""
        self.assertEqual(build_run.judge(self.lines(session_id="s2"))["state"], "unknown")
        self.assertEqual(build_run.judge(self.lines(), session="s9")["state"], "unknown")
        self.assertEqual(build_run.judge(self.lines(), session="s1")["state"], "pass")


class Supervise(Case):
    def test_a_press_runs_to_the_lane(self):
        """Two items, one run, one branch, one lane entry; the members end done and the items stay in progress."""
        self.press(2)
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"])
        ended = self.supervisor().run()
        self.assertEqual(ended, {"run": self.bundle["id"], "outcome": None, "step": "enqueued"})
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((row["step"], row["session_id"], row["outcome"]), ("enqueued", "session-fixture", None))
        self.assertEqual([m["status"] for m in row["members"]], ["done", "done"])
        self.assertEqual(self.statuses(), ["in_progress", "in_progress"])
        enqueue = [call["argv"] for call in self.calls("sd-ship") if "enqueue" in call["argv"]]
        self.assertEqual(len(enqueue), 1)
        self.assertEqual([enqueue[0][n + 1] for n, arg in enumerate(enqueue[0]) if arg == "--item"],
                         [str(item) for item in self.items])
        self.assertEqual(json.loads(row["final"])["result"], "built (pass)")
        cost = self.db.execute("SELECT * FROM cost WHERE assignment = ?", (row["assignment"],)).fetchone()
        self.assertEqual((cost["source"], cost["usd"], cost["tokens_in"], cost["tokens_out"]), ("run", 0.42, 10, 20))
        note = self.db.execute("SELECT body FROM note WHERE item = ? AND body LIKE '%report%'", (self.items[0],))
        self.assertIn("built (pass)", note.fetchone()["body"])
        self.assertEqual(self.remote_branches(), "main", "the fake lane pushed nothing; the supervisor neither")
        self.assertIsNone(self.latest()["cancel_requested"])

    def test_judge_last_line_not_exit(self):
        """Failure table, Judge: exit 0 (here 3) with a permission denial blocks with a question; the exit code is no verdict."""
        self.press()
        self.plan(claude=["deny"])
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "blocked")
        self.assertEqual(self.statuses(), ["blocked"])
        question = self.db.execute("SELECT body FROM note WHERE item = ? AND kind = 'question'",
                                   (self.items[0],)).fetchone()
        self.assertIn("denied Bash", question["body"])
        self.assertEqual(self.calls("sd-review"), [], "no review after a denial")

    def test_a_success_line_passes_whatever_the_exit_code(self):
        self.press()
        self.write_pr()
        self.plan(claude=["exit3"], sd_review=["clean"])
        self.assertEqual(self.supervisor().run()["step"], "enqueued")

    def test_a_line_of_another_session_blocks(self):
        self.press()
        self.plan(claude=["other"])
        self.assertEqual(self.supervisor().run()["outcome"], "blocked")
        self.assertIn("session-of-another-run", self.latest()["detail"])

    def test_max_turns_retries_once(self):
        """Failure table, Judge: `error_max_turns` is a loss at building: a fresh row there, the session kept."""
        self.press()
        self.plan(claude=["max_turns"])
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "error_max_turns")
        retry = build.run(self.db, ended["retry"])
        self.assertEqual((retry["step"], retry["session_id"], retry["run"]), ("building", "session-fixture", 2))
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"])
        self.assertEqual(self.supervisor(retry["id"]).run()["step"], "enqueued")
        resumed = [call["argv"] for call in self.calls("claude")][-1]
        self.assertEqual(resumed[resumed.index("--resume") + 1], "session-fixture")

    def test_a_pass_needs_a_clean_worktree_ahead(self):
        self.press()
        self.plan(claude=["pass"])
        supervisor = self.supervisor()
        real = supervisor.unfinished

        def dirty():
            (Path(self.bundle["work_path"]) / "stray.txt").write_text("x")
            return real()

        supervisor.unfinished = dirty
        self.assertEqual(supervisor.run()["outcome"], "blocked")
        self.assertIn("dirty", self.latest()["detail"])

    def test_timeout_kills_group(self):
        """Failure table, Building: a hung builder's group is ended at the timeout; a fresh row retries once."""
        self.press()
        self.plan(claude=["hang"])
        ended = self.supervisor(timeout=1.5).run()
        old = build.run(self.db, self.bundle["id"])
        self.assertEqual(ended["outcome"], "timed_out")
        self.assertTrue(group_gone(old["builder_pgid"]))
        self.assertEqual(build.run(self.db, ended["retry"])["step"], "building")

    def test_review_rounds_bound(self):
        """Failure table, Reviewing: blockers after 3 rounds block the items with the blockers; each fix resumes."""
        self.press()
        self.plan(claude=["pass", "fix1", "fix2"], sd_review=["blocking", "blocking", "blocking"])
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "blocked")
        self.assertIn("3 review rounds left blockers: work.txt:1 a blocker", self.latest()["detail"])
        self.assertEqual(len(self.calls("sd-review")), 3)
        fixes = [call["argv"] for call in self.calls("claude")][1:]
        self.assertEqual([argv[argv.index("--resume") + 1] for argv in fixes], ["session-fixture"] * 2)
        self.assertEqual(self.statuses(), ["blocked"])

    def test_a_fix_then_a_clean_review_enqueues(self):
        self.press()
        self.write_pr()
        self.plan(claude=["pass", "fix1"], sd_review=["blocking", "clean"])
        self.assertEqual(self.supervisor().run()["step"], "enqueued")
        self.assertEqual(self.latest()["review_round"], 1)

    def test_an_unknown_review_is_retried_once(self):
        self.press()
        self.plan(claude=["pass"], sd_review=["garbage", "garbage"])
        self.assertEqual(self.supervisor().run()["outcome"], "blocked")
        self.assertEqual(len(self.calls("sd-review")), 2)
        self.assertIn("the review gave no answer twice", self.latest()["detail"])

    def test_cancel_before_enqueuing_wins(self):
        """Failure table, Enqueuing CAS: a cancel asked during reviewing wins; no `sd-ship`, nothing pushed."""
        self.press()
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["cancel"])
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "cancelled")
        self.assertEqual(self.statuses(), ["ready"])
        self.assertEqual([m["status"] for m in build.run(self.db, self.bundle["id"])["members"]], ["cancelled"])
        self.assertEqual(self.calls("sd-ship"), [])
        self.assertEqual(self.remote_branches(), "main")
        self.assertTrue(Path(self.bundle["work_path"]).is_dir(), "the worktree is kept")

    def test_cancel_kills_the_active_group(self):
        """Failure table, Cancel: a cancel during building kills the builder's group at the next beat."""
        self.press()
        self.plan(claude=["hang"])

        def cancel():
            other = connect(self.database)
            try:
                self.wait_for_builder(other)
                state = operations.assignment_state(other, self.bundle["assignment"])
                operations.cancel_assignment(other, self.bundle["assignment"], expected_revision=state["revision"],
                                             who="operator")
            finally:
                other.close()

        thread = threading.Thread(target=cancel)
        thread.start()
        started = time.monotonic()
        ended = self.supervisor().run()
        thread.join()
        self.assertLess(time.monotonic() - started, 20, "the hang was cut short")
        self.assertEqual(ended["outcome"], "cancelled", self.latest()["detail"])
        self.assertTrue(group_gone(build.run(self.db, self.bundle["id"])["builder_pgid"]))
        self.assertEqual(self.statuses(), ["ready"])
        self.assertEqual(self.calls("sd-review"), [])

    def test_a_lost_run_stops_before_the_next_step(self):
        """Failure table, Any step: a run the reap ended mid-step; the beat changes no row, so the group is killed
        and nothing after it runs."""
        self.press()
        self.plan(claude=["slow"])

        def reaped():
            other = connect(self.database)
            try:
                self.wait_for_builder(other)
                other.execute("UPDATE runner_run SET outcome = 'interrupted' WHERE id = ?", (self.bundle["id"],))
                other.commit()
            finally:
                other.close()

        thread = threading.Thread(target=reaped)
        thread.start()
        ended = self.supervisor().run()
        thread.join()
        self.assertIsNone(ended["outcome"], ended)
        self.assertTrue(group_gone(build.run(self.db, self.bundle["id"])["builder_pgid"]), ended)
        self.assertEqual(self.calls("sd-review"), [])

    def test_a_child_runs_only_after_its_group_is_recorded(self):
        """Failure table, Child: a write that fails closes the gate; the child exits unrun."""
        self.press()
        build.write(self.db, self.bundle["id"], step="building")
        supervisor = self.supervisor()
        supervisor.logs.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(build, "write", return_value=False):
            with self.assertRaises(build_run.Lost):
                supervisor.child([*self.tools.claude, "-p", "x"], cwd=self.root, name="gated")
        self.assertEqual(self.calls("claude"), [], "the fake never started")

    def test_a_second_supervisor_registers_nothing(self):
        self.press()
        self.assertTrue(build.register(self.db, self.bundle["id"], pid=4242, pgid=4242, start="x"))
        ended = self.supervisor().run()
        self.assertIn("another supervisor", ended["why"])
        self.assertEqual(build.run(self.db, self.bundle["id"])["supervisor_pid"], 4242)
        self.assertEqual(self.calls(), [])

    def test_a_long_title_blocks_before_the_lane(self):
        self.press()
        self.write_pr("feat(fixture): " + "x" * 60)
        self.plan(claude=["pass"], sd_review=["clean"])
        self.assertEqual(self.supervisor().run()["outcome"], "blocked")
        self.assertEqual([call for call in self.calls("sd-ship") if "enqueue" in call["argv"]], [])

    def test_enqueue_resume_no_duplicate(self):
        """Failure table, Enqueuing (pack sd:6094 (a)): a run lost after the lane wrote its entry resumes at
        enqueuing, reads `lane list` first, finds the entry at its head and records `enqueued`; no second entry."""
        self.press()
        self.write_pr()
        work = Path(self.bundle["work_path"])
        support.git(self.repo, "worktree", "add", "-q", "-b", self.bundle["branch"], str(work), "origin/main")
        (work / "work.txt").write_text("done\n")
        support.git(work, "add", "work.txt")
        support.git(work, "-c", "commit.gpgsign=false", "commit", "-qm", "fix: done")
        head = support.git(work, "rev-parse", "HEAD")
        (self.plans / "lane.json").write_text(json.dumps([{"id": "e1", "item": self.items[0], "status": "pending",
                                                           "enqueue_seq": 1, "expected_head": head}]))
        build.write(self.db, self.bundle["id"], step="enqueuing")
        self.assertEqual(self.supervisor().run()["step"], "enqueued")
        self.assertEqual([call["argv"][-2:] for call in self.calls("sd-ship")], [["lane", "list"]])
        self.assertEqual(len(json.loads((self.plans / "lane.json").read_text())), 1)

    def test_an_unread_lane_at_enqueuing_writes_nothing(self):
        """An unknown `lane list` is no answer: the supervisor stops unwritten, and the reap retries it."""
        self.press()
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"], sd_ship=["unread"])
        ended = self.supervisor().run()
        self.assertEqual((ended["outcome"], self.latest()["step"]), (None, "enqueuing"))
        self.assertEqual([call for call in self.calls("sd-ship") if "enqueue" in call["argv"]], [])

    def test_clean_keeps_dirty_worktree(self):
        """Failure table, Cleaning: a dirty worktree stays, with a note; the run ends done and releases."""
        self.press()
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"])
        self.supervisor().run()
        work = Path(self.bundle["work_path"])
        (work / "stray.txt").write_text("x")
        self.merge_to_cleaning()
        ended = self.supervisor().run()
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((ended["outcome"], row["outcome"], row["released_at"] is not None), ("done", "done", True))
        self.assertTrue(work.is_dir())
        note = self.db.execute("SELECT body FROM note WHERE item = ? ORDER BY id DESC", (self.items[0],)).fetchone()
        self.assertIn("kept worktree", note["body"])

    def test_cleaning_removes_a_clean_worktree(self):
        self.press()
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"])
        self.supervisor().run()
        self.merge_to_cleaning()
        self.assertEqual(self.supervisor().run()["outcome"], "done")
        self.assertFalse(Path(self.bundle["work_path"]).exists())
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM runner_run WHERE released_at IS NULL").fetchone()[0], 0)

    def merge_to_cleaning(self):
        entries = json.loads((self.plans / "lane.json").read_text())
        (self.plans / "lane.json").write_text(json.dumps([{**row, "status": "merged"} for row in entries]))
        lane = lambda row, item: build_run.lane_entry(self.tools.ship, self.repo, item)  # noqa: E731
        exited = build.Probe()
        exited.alive = lambda pid: False if pid == os.getpid() else build.Probe.alive(pid)  # type: ignore[method-assign]
        exited.group = lambda pgid: False if pgid == os.getpgrp() else build.Probe.group(pgid)  # type: ignore[method-assign]
        with mock.patch.dict(os.environ, {"FAKE_PLANS": str(self.plans)}):
            moved = build_run.watch(self.db, lane=lane, probe=exited)
        self.assertEqual(moved, [{"run": self.bundle["id"], "step": "cleaning"}])


class Tick(Case):
    def setUp(self):
        super().setUp()
        self.spawned: list[str] = []
        self.entries: dict[int, Any] = {}

    def lane(self, row, item):
        answer = self.entries.get(item)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def tick(self, **inputs):
        return build_run.dispatch(self.db, owner="fixture", spawn=self.spawned.append, lane=self.lane,
                                  root=self.root / "worktrees",
                                  **{"load": 1.0, "load_cap": 40.0, "interactive": [], **inputs})

    def enqueued(self):
        self.items = [create_item(self.db, kind="task", title="Built", repo=str(self.repo), status="ready")]
        build.queue(self.db, self.items, who="operator")
        self.tick()
        run = build.open_runs(self.db)[0]
        build.write(self.db, run["id"], step="enqueuing")
        self.assertTrue(build.enqueued(self.db, run["id"]))
        self.spawned.clear()
        return run

    def test_a_tick_claims_spawns_and_beats(self):
        items = [create_item(self.db, kind="task", title="Built", repo=str(self.repo), status="ready")
                 for _ in range(2)]
        build.queue(self.db, items, who="operator")
        result = self.tick()
        self.assertEqual((len(result["claimed"]), result["spawned"]), (1, result["claimed"]))
        beat = self.db.execute("SELECT * FROM state WHERE kind = 'heartbeat' AND key = ?",
                               (build_run.HEARTBEAT,)).fetchone()
        self.assertIsNotNone(beat)
        build.register(self.db, result["claimed"][0], pid=os.getpid(), pgid=os.getpgrp(),
                       start=build.Probe.started(os.getpid()))
        again = self.tick()
        self.assertEqual((again["claimed"], again["spawned"]), ([], []), "a registered run is not spawned again")

    def test_an_unread_input_claims_nothing(self):
        build.queue(self.db, [create_item(self.db, kind="task", title="Built", repo=str(self.repo),
                                          status="ready")], who="operator")
        for inputs in ({"load": None}, {"interactive": None}, {"why": "the log folder is not writable"}):
            with self.subTest(inputs=inputs):
                self.assertEqual(self.tick(**inputs)["claimed"], [])
        self.assertEqual(self.spawned, [])

    def test_a_merged_entry_moves_the_run_to_cleaning(self):
        """Failure table, Lane watch: on `merged` the run goes to cleaning with a fresh beat and gets a supervisor."""
        run = self.enqueued()
        self.entries[self.items[0]] = {"id": "e1", "status": "merged"}
        result = self.tick()
        row = build.run(self.db, run["id"])
        self.assertEqual((row["step"], row["supervisor_pid"], row["outcome"]), ("cleaning", None, None))
        self.assertEqual((result["moved"], self.spawned), ([{"run": run["id"], "step": "cleaning"}], [run["id"]]))

    def test_clean_only_after_merge(self):
        """Failure table, Cleaning removal: a pending or running entry leaves the run at enqueued, unspawned."""
        run = self.enqueued()
        for status in ("pending", "running"):
            self.entries[self.items[0]] = {"id": "e1", "status": status}
            self.tick()
            self.assertEqual(build.run(self.db, run["id"])["step"], "enqueued")
        self.assertEqual(self.spawned, [])

    def test_a_failed_entry_ends_the_run_lane_failed(self):
        run = self.enqueued()
        self.entries[self.items[0]] = {"id": "e1", "status": "failed", "reason": "gate red"}
        self.tick()
        row = build.run(self.db, run["id"])
        self.assertEqual((row["outcome"], row["released_at"] is not None), ("lane_failed", True))
        self.assertIn("gate red", row["detail"])
        self.assertEqual(self.spawned, [])

    def test_an_unread_lane_changes_nothing(self):
        run = self.enqueued()
        self.entries[self.items[0]] = build_run.Unread("hub unavailable")
        self.tick()
        row = build.run(self.db, run["id"])
        self.assertEqual((row["step"], row["outcome"], row["released_at"]), ("enqueued", None, None))


class Spawn(unittest.TestCase):
    def test_a_supervisor_survives_the_job_group(self):
        """Risk, launchd: a spawn leaves the job's process group, so killing that group spares it."""
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "supervisor.log"
            job = subprocess.Popen(
                [sys.executable, "-c", textwrap.dedent(f'''
                    import sys, time
                    sys.path[:0] = {sys.path!r}
                    from pathlib import Path
                    from sd_db import build_run
                    print(build_run.spawn([sys.executable, "-c", "import time; time.sleep(30)"],
                                          log=Path({str(log)!r})), flush=True)
                    time.sleep(30)
                ''')], stdout=subprocess.PIPE, text=True, start_new_session=True)
            assert job.stdout is not None
            try:
                pid = int(job.stdout.readline())
            finally:
                os.killpg(job.pid, signal.SIGKILL)
                job.wait()
                job.stdout.close()
            try:
                time.sleep(0.2)
                os.kill(pid, 0)
                self.assertNotEqual(os.getpgid(pid), job.pid)
            finally:
                os.killpg(pid, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
