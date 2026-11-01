"""The dispatcher's tick and the supervisor of a headless builder run (pack sd:6094).

The design's failure table names most of these tests: system
`docs/work/2026-10-24-build-dispatcher/design.md`, step 2. The supervisor
runs real git in a fixture repository with a bare origin; `claude`,
`sd-review`, `sd-ship` and `sd-docs-lint` are fakes that read their next
answer from a plan file and log each call. Each fake but `claude` first
parses its argv with the real tool's own parser, so a call the tool would
refuse fails here too.
"""
import importlib
import json
import os
import signal
import sqlite3
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

from sd_db import (
    build,
    build_run,
    database,
    draft,
    operations,
    runner,
    sessions,
    writes,
)
from sd_db.database import connect
from sd_db.migrate import initialise
from sd_db.ship import this_host
from sd_db.workflow import item_state
from sd_db.writes import add_note, create_item, upsert_repo

from . import support
from .test_build import Probe as GoneProbe

BIN = Path(__file__).resolve().parents[2] / "bin"
with mock.patch("sys.path", [str(BIN), *sys.path]):
    #: The adapter, for its `cited`: the lane's own reader of what a branch delivers.
    ADAPTER = importlib.import_module("sd_operations")
    LANE = importlib.import_module("sd_lane")  # loaded now: `cited` imports it, and the lane's body reader, by name
    importlib.import_module("sd_ship_body")

#: One fake for every tool: its role is its file name, its answers come from `<plans>/<role>.json`.
FAKE = textwrap.dedent('''
    import json, os, re, subprocess, sys, time
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
    def real(name):
        """The real tool's module and `sys.argv` as its own parser reads it; a parse error exits 2 as it does."""
        import argparse, importlib.machinery, importlib.util
        bin_dir = os.environ["FAKE_BIN"]
        sys.path.insert(0, bin_dir)
        loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), os.path.join(bin_dir, name))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        class Parsed(Exception):
            pass
        original = argparse.ArgumentParser.parse_args
        def parse(self, args=None, namespace=None):
            raise Parsed(original(self, args, namespace))
        argparse.ArgumentParser.parse_args = parse
        try:
            module.main(sys.argv[1:])
        except Parsed as parsed:
            return module, parsed.args[0]
        finally:
            argparse.ArgumentParser.parse_args = original
        sys.exit(f"{name} never parsed its arguments")
    def line(record):
        print(json.dumps(record), flush=True)
    if role == "claude":
        session = "session-fixture"
        if "--resume" in sys.argv:
            session = sys.argv[sys.argv.index("--resume") + 1]
        line({"type": "system", "subtype": "init", "session_id": session})
        if mode == "hang":
            time.sleep(120)
        if mode.startswith("draft"):
            # A draft run's reply (pack sd:6361): no file, no commit; `draft-bad` has no `## Spec`.
            reply = ("## Spec\\n\\nProblem: x\\n\\n## Questions\\n\\nWhich?\\nOption: A (Recommended)\\nOption: B\\n"
                     if mode != "draft-bad" else "Here is the spec you asked for.")
            final = {"type": "result", "subtype": "success", "is_error": False, "permission_denials": [],
                     "session_id": session, "result": reply, "total_cost_usd": 0.31,
                     "usage": {"input_tokens": 5, "output_tokens": 7}}
            if mode == "draft-deny":
                final["permission_denials"] = [{"tool_name": "Write", "tool_input": {"file_path": "x"}}]
            line(final)
            sys.exit(0)
        if mode == "slow":
            time.sleep(3)
        if mode == "silent":
            sys.exit(0)
        Path("work.txt").write_text(Path("work.txt").read_text() + mode + "\\n" if Path("work.txt").exists()
                                    else mode + "\\n")
        git("add", "work.txt")
        # One `Closes: sd:N` trailer per item the brief lists, as the brief asks; `skip` leaves out the last
        # one, as a builder that skips an item for the operator does, and `none` delivers nothing.
        prompt = sys.argv[sys.argv.index("-p") + 1]
        items = re.findall(r"^- sd:(\\d+)", prompt, re.M)
        items = [] if mode == "none" else items[:-1] if mode == "skip" else items
        trailers = "".join(f"\\nCloses: sd:{item}" for item in items)
        git("-c", "commit.gpgsign=false", "commit", "-qm", f"fix: {mode}" + (f"\\n{trailers}" if items else ""))
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
        review, args = real("sd-review")
        assert (args.scope, args.json) == ("branch", True), args
        if mode == "cancel":
            import sqlite3
            db = sqlite3.connect(os.environ["FAKE_DB"])
            db.execute("UPDATE runner_run SET cancel_requested = 'cancelled by fixture' WHERE released_at IS NULL")
            db.commit()
            mode = "clean"
        if mode == "garbage":
            print("not json")
            sys.exit(4)
        raw = {"path": "work.txt", "line": 1, "severity": "high", "summary": "a blocker", "family": "correctness"}
        findings = review.dispose([review._finding(raw)], "high")  # the record shape `--json` prints
        if mode == "gate_failed":
            print(json.dumps({"status": "gate_failed", "cleared_status": "clean", "findings": [],
                              "subject": {"head": git("-C", work, "rev-parse", "HEAD")},
                              "check": {"status": "fail", "checks": [
                                  {"command": ["make", "check"], "exit_code": 2, "failed_steps": ["make target audit"],
                                   "failure": "audit: a long line"}]}}))
            sys.exit(0)
        print(json.dumps({"status": "blocking" if mode == "blocking" else "clean",
                          "subject": {"head": git("-C", work, "rev-parse", "HEAD")},
                          "findings": findings if mode == "blocking" else []}))
    if role == "sd-ship":
        lane = plans / "lane.json"
        entries = json.loads(lane.read_text()) if lane.exists() else []
        _, args = real("sd-ship")
        assert args.command == "lane", args
        if "list" in sys.argv:
            print(json.dumps({"ok": mode != "unread", "entries": entries}))
            sys.exit(3 if mode == "unread" else 0)
        import sd_lane
        if args.claim not in sd_lane.CLAIMS:  # enqueue_entry's first refusal, which the parser leaves to it
            print(json.dumps({"ok": False, "error": "name the delivery claim prepare needs"}))
            sys.exit(3)
        import sd_ship_body, sd_ship_remote
        try:  # the lane's own title and line checks (`check_lines`, `check_item`), with no commits read
            body = args.body_file.read_text()
            sd_ship_body.refuse_long_lines(args.title, body, [])
            sd_ship_body.refuse_unconventional_title(args.title)
            sd_ship_body.normalize(body, args.items[0])
        except sd_ship_remote.Refusal as error:
            print(json.dumps({"ok": False, "error": f"{error}; nothing was queued"}))
            sys.exit(3)
        argv = sys.argv
        items = [int(argv[n + 1]) for n, arg in enumerate(argv) if arg == "--item"]
        entry = {"id": f"e{len(entries) + 1}", "item": items[0], "status": "pending", "enqueue_seq": len(entries) + 1,
                 "expected_head": argv[argv.index("--expected-head") + 1]}
        lane.write_text(json.dumps(entries + [entry]))
        print(json.dumps({"ok": True, **entry}))
    if role == "sd-docs-lint":
        _, args = real("sd-docs-lint")
        assert args.pr_body is not None and args.pr_body.is_file(), args
        if mode == "refuse":  # the real tool's failure lines, on stderr, its stdout only notes
            print("PR privacy: 1 pattern(s) from /x/privacy-patterns, no match")
            print("FAIL pull request body: line 3 matches a privacy pattern in /x/privacy-patterns",
                  file=sys.stderr)
            print("sd-docs-lint: 1 failure(s)", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
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
        self.env = {**os.environ, "FAKE_PLANS": str(self.plans), "FAKE_DB": str(self.database),
                    "FAKE_BIN": str(BIN)}
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
        options = {"cited": ADAPTER.cited, **options}
        return build_run.Supervisor(self.db, ident or self.bundle["id"], tools=self.tools, log_root=self.logs,
                                    environ=self.env, **options)

    def write_pr(self, title="feat(fixture): build the fixture", body="## Summary\n\nx\n\n## Test plan\n\ny\n"):
        logs = build_run.log_dir(self.logs, self.bundle["repo"])
        logs.mkdir(parents=True, exist_ok=True)
        (logs / f"sd-{self.bundle['assignment']}.title").write_text(title + "\n", encoding="utf-8")
        (logs / f"sd-{self.bundle['assignment']}.body.md").write_text(body)

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

    def test_judge_skips_a_trailing_lifecycle_line(self):
        """Claude Code writes a command_lifecycle line after the result (build 168 read as unknown)."""
        tail = json.dumps({"type": "command_lifecycle", "state": "completed", "session_id": "s1"})
        self.assertEqual(build_run.judge(self.lines() + [tail])["state"], "pass")
        self.assertEqual(build_run.judge(self.lines(is_error=True) + [tail, tail])["state"], "failed")
        self.assertEqual(build_run.judge(self.lines()[:1] + [tail])["state"], "unknown")

    def test_judge_refuses_another_sessions_line(self):
        """A judge pass is tied to the run's own session: a result of another session is unknown."""
        self.assertEqual(build_run.judge(self.lines(session_id="s2"))["state"], "unknown")
        self.assertEqual(build_run.judge(self.lines(), session="s9")["state"], "unknown")
        self.assertEqual(build_run.judge(self.lines(), session="s1")["state"], "pass")


class Supervise(Case):
    def test_the_fakes_refuse_what_the_real_tools_refuse(self):
        """Review round 1: the fake took an enqueue the real `sd-ship` refuses; now each parses as its tool does."""
        body = self.root / "body.md"
        body.write_text("## Summary\n", encoding="utf-8")
        enqueue = ["-C", str(self.repo), "lane", "enqueue", "--item", "1", "--title", "fix: x", "--body-file",
                   str(body), "--expected-head", "HEAD"]
        for argv, code in ((enqueue, 3), ([*enqueue, "--deliver"], 0), (["-C", str(self.repo), "lane", "lsit"], 2)):
            with self.subTest(argv=argv):
                done = subprocess.run([*self.tools.ship, *argv], capture_output=True, text=True, env=self.env,
                                      check=False)
                self.assertEqual(done.returncode, code, done.stdout + done.stderr)
        done = subprocess.run([*self.tools.review, "-C", str(self.repo), "--scope", "brnach", "--json"],
                              capture_output=True, text=True, env=self.env, check=False)
        self.assertEqual(done.returncode, 2, done.stderr)

    def test_the_builder_env_carries_the_run_and_items_for_otel(self):
        """pack sd:6943: Claude Code's OTel joins the run's trace; a value already there stays first."""
        self.press(2)
        self.env["OTEL_RESOURCE_ATTRIBUTES"] = "host.name=fixture"
        env = self.supervisor().env
        self.assertEqual(env["OTEL_RESOURCE_ATTRIBUTES"], f"host.name=fixture,sd.build_run={self.bundle['id']},"
                         f"sd.items={self.items[0]};{self.items[1]}")
        self.assertNotIn("CLAUDE_CODE_ENABLE_TELEMETRY", {key for key in env if key not in os.environ})

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

    def test_a_skipped_member_is_not_delivered(self):
        """Review round 2: only the members a branch commit's `Closes:` trailer cites are enqueued and done."""
        self.press(2)
        self.write_pr()
        self.plan(claude=["skip"], sd_review=["clean"])
        self.assertEqual(self.supervisor().run()["step"], "enqueued")
        enqueue = next(call["argv"] for call in self.calls("sd-ship") if "enqueue" in call["argv"])
        self.assertEqual([enqueue[n + 1] for n, arg in enumerate(enqueue) if arg == "--item"], [str(self.items[0])])
        self.assertEqual(self.statuses(), ["in_progress", "blocked"])
        self.assertEqual([m["status"] for m in build.run(self.db, self.bundle["id"])["members"]], ["done", "blocked"])
        note = self.db.execute("SELECT body FROM note WHERE item = ? AND body LIKE '%Closes: sd:%'", (self.items[1],))
        self.assertIsNotNone(note.fetchone(), "the skipped item says why it stays open")

    def test_a_member_with_an_open_question_is_not_enqueued(self):
        """sd:6571: an earlier run's commit cites the member, but this run's builder skipped it with a question."""
        self.press()
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"])
        add_note(self.db, self.items[0], "question", "Which option?\nOption: Yes (Recommended)\nOption: No")
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "blocked")
        self.assertIn("open question", ended["blocked"])
        self.assertEqual([call for call in self.calls("sd-ship") if "enqueue" in call["argv"]], [])

    def test_only_the_member_with_an_open_question_stays_out(self):
        self.press(2)
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"])
        add_note(self.db, self.items[1], "question", "Which option?\nOption: Yes (Recommended)\nOption: No")
        self.assertEqual(self.supervisor().run()["step"], "enqueued")
        enqueue = next(call["argv"] for call in self.calls("sd-ship") if "enqueue" in call["argv"])
        self.assertEqual([enqueue[n + 1] for n, arg in enumerate(enqueue) if arg == "--item"], [str(self.items[0])])
        self.assertEqual(self.statuses(), ["in_progress", "blocked"])
        # The lane adds each open item a branch commit's trailer cites to the closing set, unless a `Refs:`
        # line keeps it open: the questioned member's old trailer must not close it.
        work = Path(build.run(self.db, self.bundle["id"])["work_path"])
        head = enqueue[enqueue.index("--expected-head") + 1]
        body = Path(enqueue[enqueue.index("--body-file") + 1]).read_text(encoding="utf-8")
        self.db.execute("UPDATE item SET status = 'in_progress' WHERE id = ?", (self.items[1],))
        cited, _ = LANE.cited_closes(self.db, self.items[0], body, LANE.branch_commits(work, "main", head), ())
        self.assertEqual([row["item"] for row in cited], [])

    def test_the_lane_entry_is_found_by_any_delivered_member(self):
        """The entry's item is the first member delivered, so the lookups (resume, watch) read every member."""
        (self.plans / "lane.json").write_text(json.dumps([{"id": "e1", "item": 7, "status": "merged",
                                                           "enqueue_seq": 1}]))
        found = build_run.lane_entry(self.tools.ship, self.repo, [5, 7], env=self.env)
        self.assertEqual(found and found["id"], "e1")
        self.assertIsNone(build_run.lane_entry(self.tools.ship, self.repo, [5], env=self.env))

    def test_an_unread_delivery_writes_nothing(self):
        """`cited` None (the commits were not read) is unknown: no enqueue, no outcome; the reap retries."""
        self.press()
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"])
        self.assertIsNone(ADAPTER.cited(self.repo, "origin/no-such-branch", "HEAD", ""))
        ended = self.supervisor(cited=lambda *_: None).run()
        self.assertEqual((ended["outcome"], self.latest()["outcome"]), (None, None))
        self.assertEqual([call for call in self.calls("sd-ship") if "enqueue" in call["argv"]], [])

    def test_a_branch_that_delivers_nothing_blocks(self):
        self.press()
        self.write_pr()
        self.plan(claude=["none"], sd_review=["clean"])
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "blocked")
        self.assertIn("delivers no item", ended["blocked"])
        self.assertEqual([call for call in self.calls("sd-ship") if "enqueue" in call["argv"]], [])

    def test_a_group_of_zombies_reads_gone(self):
        """sd:6406: under load a git grandchild's zombie waits for launchd to reap it, and macOS answers
        EPERM to `killpg` on a group that holds only zombies; that group runs nothing, so it is gone."""
        self.press()
        leader = subprocess.Popen([sys.executable, "-c", "import os\nif os.fork() == 0: os._exit(0)\nos._exit(0)"],
                                  start_new_session=True)
        self.addCleanup(leader.wait)
        # Every member, not only the leader: under gate load the forked child still ran when the leader was
        # already a zombie, so the group read alive (2026-10-30 04:07 MDT).
        def states():
            rows = subprocess.run(["ps", "-A", "-o", "pgid=,stat="], capture_output=True, text=True).stdout.split("\n")
            return [row.split()[1] for row in rows if row.split() and row.split()[0] == str(leader.pid)]

        deadline = time.monotonic() + 30
        while not states() or any(state[:1] != "Z" for state in states()):
            self.assertLess(time.monotonic(), deadline, f"the group never became zombies: {states()}")
            time.sleep(0.05)
        self.assertIs(build.Probe.group(leader.pid), False)
        self.assertTrue(self.supervisor().end_group(leader.pid))

    def questions(self):
        return [row["body"] for row in self.db.execute("SELECT body FROM note WHERE item = ? AND kind = 'question'",
                                                       (self.items[0],))]

    def test_judge_last_line_not_exit(self):
        """Failure table, Judge: exit 0 (here 3) with a permission denial blocks with a question; the exit code is no verdict."""
        self.press()
        self.plan(claude=["deny"])
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "blocked")
        self.assertEqual(self.statuses(), ["blocked"])
        self.assertEqual(len(self.questions()), 1)
        self.assertIn("denied Bash", self.questions()[0])
        self.assertEqual(self.calls("sd-review"), [], "no review after a denial")
        # pack sd:6708: a first denial looks transient, so the pick is a requeue.
        _, options = writes.parse(self.questions()[0])
        self.assertEqual(writes.recommended(self.questions()[0], options),
                         options.index("Requeue as is (Recommended)"))

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
        self.assertIn("- work.txt:1 a blocker", fixes[0][fixes[0].index("-p") + 1], "the fix names each blocker")
        self.assertEqual(self.statuses(), ["blocked"])

    def test_a_fix_then_a_clean_review_enqueues(self):
        self.press()
        self.write_pr()
        self.plan(claude=["pass", "fix1"], sd_review=["blocking", "clean"])
        self.assertEqual(self.supervisor().run()["step"], "enqueued")
        self.assertEqual(self.latest()["review_round"], 1)

    def test_a_failed_gate_goes_back_to_the_builder(self):
        """A review that cleared over a failed gate is a blocker to fix, not an unknown answer (runs 155-203)."""
        self.press()
        self.write_pr()
        self.plan(claude=["pass", "fix1"], sd_review=["gate_failed", "clean"])
        self.assertEqual(self.supervisor().run()["step"], "enqueued")
        self.assertEqual(len(self.calls("sd-review")), 2)
        fix = [call["argv"] for call in self.calls("claude")][1]
        self.assertIn("make target audit", fix[fix.index("-p") + 1], "the fix names the failed gate step")

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

    def test_a_locked_database_once_keeps_the_run_at_its_step(self):
        """pack sd:6588: the supervisor's group write meets one `database is locked`, retries, and the child runs."""
        self.press()
        build.write(self.db, self.bundle["id"], step="reviewing")

        class Locked:
            """The fixture connection whose next `BEGIN IMMEDIATE` fails once, as a held write lock does."""
            def __init__(self, connection):
                self.connection, self.armed = connection, False

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, parameters=()):
                if self.armed and sql == "BEGIN IMMEDIATE":
                    self.armed = False
                    raise sqlite3.OperationalError("database is locked")
                return self.connection.execute(sql, parameters)

        locked = Locked(self.db)
        supervisor = build_run.Supervisor(locked, self.bundle["id"], tools=self.tools, log_root=self.logs,
                                          environ=self.env, cited=ADAPTER.cited, beat_seconds=0.2, timeout=30,
                                          grace=0.5)
        supervisor.logs.mkdir(parents=True, exist_ok=True)
        locked.armed = True
        with mock.patch.object(database, "LOCK_WAITS", (0.01,)):
            code = supervisor.child([*self.tools.claude, "-p", "x"], cwd=self.root, name="locked")
        self.assertFalse(locked.armed, "the lock was met")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.calls("claude")), 1)
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((row["step"], row["outcome"]), ("reviewing", None))

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

    def test_a_body_the_lane_refuses_blocks_with_its_reason(self):
        """Review round 1: the lane's own line check refuses a long body line; the run blocks naming it."""
        self.press()
        self.write_pr(body="## Summary\n\n" + "x" * 80 + "\n")
        self.plan(claude=["pass"], sd_review=["clean"])
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "blocked")
        self.assertIn("limit 72", ended["blocked"])
        self.assertIn("72 characters or less outside a code fence", build_run.BRIEF)

    def test_a_body_the_lint_refuses_blocks_naming_the_line(self):
        """Pack sd:6402: the lint's failures go to stderr; the block names them, and the brief warns."""
        self.press()
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"], sd_docs_lint=["refuse"])
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "blocked")
        self.assertIn("line 3 matches a privacy pattern", ended["blocked"])
        self.assertIn(".lint.err.out", ended["blocked"])
        self.assertEqual([call for call in self.calls("sd-ship") if "enqueue" in call["argv"]], [])
        self.assertIn("names no local path", build_run.BRIEF)

    def test_the_brief_keeps_closes_lines_out_of_the_body(self):
        """Pack sd:6626: run 137 copied its commit's Closes: trailer into the body; enqueue refuses it."""
        self.assertIn("The body carries no `Closes:` line", build_run.BRIEF)

    def test_the_brief_forbids_a_kill_by_pattern(self):
        """Pack sd:6815: build 268's `pkill -f "sd-check --json"` ended the vault job's queued gate."""
        self.assertIn("never `pkill` or `killall`", build_run.BRIEF)

    def test_a_requeued_bundle_briefs_the_findings_sent_to_its_branch(self):
        """Pack sd:6020: Send to builder writes a finding note and queues the bundle again; the fresh builder's brief
        names the finding and the branch it resumes, and leaves out a note from before the bundle's first run."""
        self.press()
        item = self.items[0]
        add_note(self.db, item, "comment", "Send to builder: an older finding for another branch")
        self.db.execute("UPDATE note SET timestamp = '2000-01-01T00:00:00+00:00' WHERE body LIKE '%older finding%'")
        build.end(self.db, self.bundle["id"], "cancelled", "the operator cancelled it")
        add_note(self.db, item, "comment", "Send to builder: the Retry label reads wrong on phones")
        lead = self.bundle["assignment"]
        runner.requeue(self.db, lead, expected_revision=runner.queue_state(self.db, lead)["revision"], who="operator")
        again = build.claim(self.db, owner="fixture", load=1.0, load_cap=40.0, interactive=[],
                            root=self.root / "worktrees")
        assert again is not None
        prompt = build_run.BRIEF.format(**self.supervisor(again["id"]).brief())
        self.assertIn(f"- sd:{item}: the Retry label reads wrong on phones", prompt)
        self.assertIn(f"already holds the commits of an earlier run on {self.bundle['branch']}", prompt)
        self.assertNotIn("older finding", prompt)
        first = build_run.BRIEF.format(**self.supervisor(self.bundle["id"]).brief())
        self.assertNotIn("Send to builder", first)

    def test_enqueue_resume_no_duplicate(self):
        """Failure table, Enqueuing (pack sd:6094 (a)): a run lost after the lane wrote its entry resumes at
        enqueuing, reads `lane list` first, finds the entry at its head and records `enqueued`; no second entry."""
        self.press()
        self.write_pr()
        work = Path(self.bundle["work_path"])
        support.git(self.repo, "worktree", "add", "-q", "-b", self.bundle["branch"], str(work), "origin/main")
        (work / "work.txt").write_text("done\n")
        support.git(work, "add", "work.txt")
        support.git(work, "-c", "commit.gpgsign=false", "commit", "-qm", f"fix: done\n\nCloses: sd:{self.items[0]}")
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

    def hold(self, session: str) -> None:
        work = Path(self.bundle["work_path"])
        sessions.beat(self.db, session, machine=this_host(), cwd=None, found=sessions.worktrees([str(work)]))

    def test_a_held_build_worktree_is_kept(self):
        """pack sd:6024: a session other than the run's builder holds the worktree, so cleaning keeps it."""
        self.press()
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"])
        self.supervisor().run()
        self.hold("session-other")
        self.merge_to_cleaning()
        ended = self.supervisor().run()
        self.assertEqual(ended["outcome"], "done")
        self.assertTrue(Path(self.bundle["work_path"]).is_dir())
        note = self.db.execute("SELECT body FROM note WHERE item = ? ORDER BY id DESC", (self.items[0],)).fetchone()
        self.assertIn("a live session holds it: session-", note["body"])

    def test_the_builders_own_session_does_not_keep_its_worktree(self):
        self.press()
        self.write_pr()
        self.plan(claude=["pass"], sd_review=["clean"])
        self.supervisor().run()
        self.hold("session-fixture")
        self.merge_to_cleaning()
        self.assertEqual(self.supervisor().run()["outcome"], "done")
        self.assertFalse(Path(self.bundle["work_path"]).exists())

    def merge_to_cleaning(self):
        entries = json.loads((self.plans / "lane.json").read_text())
        (self.plans / "lane.json").write_text(json.dumps([{**row, "status": "merged"} for row in entries]))
        lane = lambda row, items: build_run.lane_entry(self.tools.ship, self.repo, items)  # noqa: E731
        exited = build.Probe()
        exited.alive = lambda pid: False if pid == os.getpid() else build.Probe.alive(pid)  # type: ignore[method-assign]
        exited.group = lambda pgid: False if pgid == os.getpgrp() else build.Probe.group(pgid)  # type: ignore[method-assign]
        with mock.patch.dict(os.environ, {"FAKE_PLANS": str(self.plans), "FAKE_BIN": str(BIN)}):
            moved = build_run.watch(self.db, lane=lane, probe=exited)
        self.assertEqual(moved, [{"run": self.bundle["id"], "step": "cleaning"}])


class Tick(Case):
    def setUp(self):
        super().setUp()
        self.spawned: list[str] = []
        self.entries: dict[int, Any] = {}

    def lane(self, row, items):
        answer = next((self.entries[item] for item in items if item in self.entries), None)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def tick(self, **inputs):
        return build_run.dispatch(self.db, owner="fixture", spawn=self.spawned.append, lane=self.lane,
                                  root=self.root / "worktrees",
                                  **{"load": 1.0, "load_cap": 40.0, "interactive": [], **inputs})

    def enqueued(self, count=1, skip_lead=False):
        self.items = [create_item(self.db, kind="task", title="Built", repo=str(self.repo), status="ready")
                      for _ in range(count)]
        build.queue(self.db, self.items, who="operator")
        self.tick()
        run = next(row for row in build.open_runs(self.db) if row["step"] != "enqueued")  # this item's, not an older
        build.write(self.db, run["id"], step="enqueuing")
        self.assertTrue(build.enqueued(self.db, run["id"], self.items[1:] if skip_lead else None))
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
        self.assertEqual(self.statuses(), ["in_progress"], "only a catch-up conflict goes back to a builder")

    CONFLICT = ("merging origin/main into build/sd-1 conflicts; the branch is unchanged; "
                "sd-ship lane retry --item 1 queues it again")

    def test_a_catch_up_conflict_goes_back_to_its_builder(self):
        """pack sd:6940: a conflict with main alone queues the bundle again under its lead, with a finding."""
        run = self.enqueued()
        self.entries[self.items[0]] = {"id": "e1", "status": "failed", "reason": self.CONFLICT}
        result = self.tick()
        self.assertEqual(build.run(self.db, run["id"])["outcome"], "lane_failed")
        self.assertEqual(self.statuses(), ["in_progress"], "the same tick claims it again")
        again = build.run(self.db, result["claimed"][0])
        self.assertEqual((again["assignment"], again["branch"]), (run["assignment"], run["branch"]))
        notes = [row["body"] for row in self.db.execute("SELECT body FROM note WHERE item = ?", self.items)]
        self.assertTrue(any(body.startswith(build.REBUILD) for body in notes), notes)

    def test_a_conflict_waits_until_its_supervisor_is_gone(self):
        """Review: a requeue while the old supervisor still ran let a new builder share its worktree."""
        run = self.enqueued()
        build.register(self.db, run["id"], pid=os.getpid(), pgid=os.getpgrp(),
                       start=build.Probe.started(os.getpid()))
        self.entries[self.items[0]] = {"id": "e1", "status": "failed", "reason": self.CONFLICT}
        self.assertEqual(self.tick()["claimed"], [], "a live supervisor holds the worktree")
        self.assertIsNone(build.run(self.db, run["id"])["outcome"])
        gone = build.Probe()
        gone.alive = lambda pid: False  # type: ignore[method-assign]
        gone.group = lambda pgid: False  # type: ignore[method-assign]
        self.assertNotEqual(self.tick(probe=gone)["claimed"], [], "once gone, the bundle goes back to a builder")
        self.assertEqual(build.run(self.db, run["id"])["outcome"], "lane_failed")

    def test_a_conflict_without_its_lead_is_left_to_the_operator(self):
        """Review: a rebuild that lost its lead would claim under a child's branch, so none is queued."""
        for case in ("moved", "skipped"):
            with self.subTest(case=case):
                run = self.enqueued(2, skip_lead=case == "skipped")  # a skipped lead ends blocked
                lead, child = self.items
                if case == "moved":
                    writes.transition(self.db, lead, "planning", who="operator", reason="moved on")
                self.entries = {child: {"id": "e1", "status": "failed", "reason": self.CONFLICT}}
                self.assertEqual(self.tick()["claimed"], [])
                self.assertEqual(build.run(self.db, run["id"])["outcome"], "lane_failed")
                self.assertEqual(item_state(self.db, child)["item"]["status"], "in_progress")
                self.assertEqual(self.db.execute("SELECT status FROM assignment WHERE item = ?",
                                                 (child,)).fetchone()[0], "done")

    def test_conflict_rebuilds_stop_at_their_cap(self):
        """pack sd:6940: past `CONFLICT_REBUILDS` the bundle stays lane_failed for the operator."""
        run = self.enqueued()
        for _ in range(build.CONFLICT_REBUILDS):
            self.entries[self.items[0]] = {"id": "e1", "status": "failed", "reason": self.CONFLICT}
            claimed = self.tick()["claimed"][0]
            build.write(self.db, claimed, step="enqueuing")
            self.assertTrue(build.enqueued(self.db, claimed))
        self.tick()
        self.assertEqual(self.tick()["claimed"], [])
        self.assertEqual(self.statuses(), ["in_progress"])
        self.assertEqual(self.db.execute("SELECT status FROM assignment WHERE id = ?",
                                         (run["assignment"],)).fetchone()[0], "done")

    def test_every_lane_end_short_of_a_merge_ends_the_run(self):
        """Review round 1: the lane's own list of ends short of a merge, and a cancel, each end the run."""
        for status in (*LANE.BLOCKED, "cancelled"):
            with self.subTest(status=status):
                run = self.enqueued()
                self.entries[self.items[0]] = {"id": "e1", "status": status, "reason": "stopped"}
                self.tick()
                self.assertEqual(build.run(self.db, run["id"])["outcome"], "lane_failed")

    def test_an_unread_lane_changes_nothing(self):
        run = self.enqueued()
        self.entries[self.items[0]] = build_run.Unread("hub unavailable")
        self.tick()
        row = build.run(self.db, run["id"])
        self.assertEqual((row["step"], row["outcome"], row["released_at"]), ("enqueued", None, None))


class Drafts(Case):
    """The draft supervisor and the tick's draft claim (pack sd:6361), with the fake `claude`."""

    def queue(self):
        self.items = [create_item(self.db, kind="task", title="Draft me", body={"text": "The capture's one line."},
                                  repo=str(self.repo), status="planning")]
        self.assignment = draft.queue_if_eligible(self.db, self.items[0], who="dashboard")
        assert self.assignment is not None

    def claimed(self):
        self.queue()
        run = draft.claim(self.db, owner="fixture", available=build.room(self.db, load=1.0, load_cap=40.0,
                                                                         interactive=[]))
        assert run is not None
        return run

    def drafter(self, ident, **options):
        options = {"beat_seconds": 0.2, "timeout": 30, "grace": 0.5, **options}
        return build_run.DraftSupervisor(self.db, ident, tools=self.tools, log_root=self.logs, environ=self.env,
                                         **options)

    def notes(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM note WHERE item = ? ORDER BY id", self.items)]

    def assignment_status(self):
        return self.db.execute("SELECT status FROM assignment WHERE id = ?", (self.assignment,)).fetchone()[0]

    def test_a_draft_run_writes_its_spec_and_questions(self):
        run = self.claimed()
        self.plan(claude=["draft"])
        ended = self.drafter(run["id"]).run()
        self.assertEqual(ended, {"run": run["id"], "outcome": "done", "questions": 1})
        notes = [note for note in self.notes() if note["session"] == f"draft:{run['id']}"]
        self.assertEqual([note["kind"] for note in notes], ["comment", "question"])
        self.assertTrue(notes[0]["body"].startswith("Draft spec:"))
        self.assertEqual(notes[1]["body"], "Which?\nOption: A (Recommended)\nOption: B")
        self.assertEqual((self.assignment_status(), self.statuses()), ("done", ["planning"]))
        row = build.run(self.db, run["id"])
        self.assertEqual((row["outcome"], row["step"], row["session_id"]), ("done", "drafting", "session-fixture"))
        cost = self.db.execute("SELECT * FROM cost WHERE pass = ?", (run["id"],)).fetchone()
        self.assertEqual((cost["usd"], cost["assignment"]), (0.31, self.assignment))
        prompt = self.calls("claude")[0]["argv"][1]
        self.assertIn(f"sd:{self.items[0]}", prompt)
        self.assertIn("The capture's one line.", prompt)

    def test_a_draft_run_denies_write_tools(self):
        """Failure table, Drafting: the run holds the read tools only, and a denial writes nothing."""
        run = self.claimed()
        self.plan(claude=["draft-deny"])
        before = self.notes()
        ended = self.drafter(run["id"]).run()
        call = self.calls("claude")[0]
        argv = call["argv"]
        self.assertEqual(argv[argv.index("--tools"):argv.index("--tools") + 4], ["--tools", "Read", "Grep", "Glob"])
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertNotIn("auto", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual((argv[argv.index("--max-turns") + 1], argv[argv.index("--model") + 1]), ("60", "opus"))
        self.assertEqual(Path(call["cwd"]).resolve(), self.repo.resolve(), "it reads the repository's checkout")
        self.assertEqual(ended["outcome"], "blocked")
        self.assertIn("permission denied: Write", build.run(self.db, run["id"])["detail"])
        self.assertEqual((self.notes(), self.assignment_status(), self.statuses()), (before, "blocked", ["planning"]))

    def test_an_unparsed_reply_writes_no_note(self):
        """Failure table, Write: a reply with no `## Spec` is no draft; the run ends blocked with its log."""
        run = self.claimed()
        self.plan(claude=["draft-bad"])
        before = self.notes()
        ended = self.drafter(run["id"]).run()
        self.assertEqual(ended["outcome"], "blocked")
        row = build.run(self.db, run["id"])
        self.assertIn(str(build_run.log_dir(self.logs, run["repo"]) / f"{run['id']}.jsonl"), row["detail"])
        self.assertEqual((self.notes(), self.assignment_status(), self.statuses()), (before, "blocked", ["planning"]))
        self.assertIsNone(row["released_at"], "held until the reap reads the supervisor gone")
        self.assertEqual(draft.reap(self.db, probe=GoneProbe(alive=False, group=False)), [])
        self.assertIsNotNone(build.run(self.db, run["id"])["released_at"])

    def test_a_hung_draft_is_killed_and_retried_once(self):
        """Failure table, Drafting: the bound kills the group; a fresh run retries once, then a followup blocks it."""
        run = self.claimed()
        self.plan(claude=["hang", "hang"])
        ended = self.drafter(run["id"], timeout=1.5).run()
        self.assertEqual(ended["outcome"], "timed_out")
        self.assertTrue(group_gone(build.run(self.db, run["id"])["builder_pgid"]))
        retry = build.run(self.db, ended["retry"])
        self.assertEqual((retry["step"], retry["run"], retry["session_id"]), ("claimed", 2, None))
        again = self.drafter(retry["id"], timeout=1.5).run()
        self.assertEqual((again["outcome"], again["retry"]), ("timed_out", None))
        self.assertEqual((self.assignment_status(), self.statuses()), ("blocked", ["planning"]))
        followups = [note["body"] for note in self.notes() if note["kind"] == "followup"]
        self.assertEqual(len(followups), 1)
        self.assertIn("Draft blocked:", followups[0])
        self.assertEqual(draft.open_runs(self.db), [])

    def test_a_tick_claims_and_spawns_one_draft(self):
        self.queue()
        spawned: list[str] = []
        tick: dict[str, Any] = {"owner": "fixture", "spawn": spawned.append, "lane": lambda *_: None, "root": self.root / "worktrees",
                "load": 1.0, "load_cap": 40.0, "interactive": []}
        result = build_run.dispatch(self.db, **tick)
        self.assertEqual((result["claimed"], len(result["drafted"]), spawned), ([], 1, result["drafted"]))
        self.assertEqual(build_run.dispatch(self.db, **tick)["drafted"], [], "one draft at a time")
        self.assertEqual(build_run.dispatch(self.db, **{**tick, "load": None})["drafted"], [])

    def test_supervise_routes_a_draft_run_to_the_draft_supervisor(self):
        run = self.claimed()
        seen = []

        class Fake:
            def __init__(self, connection, ident, **options):
                seen.append((type(self).__name__, ident, sorted(options)))

            def run(self):
                return {"run": seen[-1][1]}

        args = mock.Mock(run=run["id"])
        with mock.patch("sys.path", [str(BIN), *sys.path]), \
                mock.patch.object(ADAPTER, "log_root", return_value=self.logs), \
                mock.patch.object(ADAPTER.sd_handoff_rows, "connect", return_value=connect(self.database)), \
                mock.patch.object(build_run, "DraftSupervisor", Fake), \
                mock.patch("builtins.print"):
            ADAPTER.supervise_build(args)
        self.assertEqual(seen, [("Fake", run["id"], ["log_root", "tools"])])


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
