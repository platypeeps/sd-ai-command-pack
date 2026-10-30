"""The Build queue, its claim and its reap on the runner tables (pack sd:6093).

The design's failure table names most of these tests: system
`docs/work/2026-10-24-build-dispatcher/design.md`.
"""
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any
from unittest import mock

from sd_db import build, operations, recovery, runner, workflow
from sd_db.database import connect
from sd_db.errors import BackupError
from sd_db.migrate import initialise
from sd_db.workflow import item_state
from sd_db.writes import (
    create_assignment,
    create_item,
    read_settings,
    record_state,
    set_setting,
    transition,
    upsert_repo,
)

#: `sd_db.backup` the module: the package exports the function under that name.
backup = import_module("sd_db.backup")
A, B = "/fixture/a", "/fixture/b"
START = "Sat Oct 24 09:00:00 2026"
IDLE: dict[str, Any] = {"load": 1.0, "load_cap": 40.0, "interactive": []}


def later(stamp: str, seconds: int) -> str:
    return (datetime.fromisoformat(stamp) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


class Probe:
    """Every pid answers `alive` and `started`, every group `group`; `pids` maps a pid to its own (alive, started)."""

    def __init__(self, alive=True, started="Sat Oct 24 09:00:00 2026", group=False, pids=None):
        self.answer, self.start, self.members, self.pids = alive, started, group, pids or {}

    def alive(self, pid):
        return self.pids.get(pid, (self.answer, self.start))[0]

    def started(self, pid):
        return self.pids.get(pid, (self.answer, self.start))[1]

    def group(self, pgid):
        return self.members


class Kill:
    """Records each group kill; `gone` is what each answers, or a map of group to answer (True when unnamed)."""

    def __init__(self, connection, gone=True):
        self.connection, self.gone, self.calls = connection, gone, []

    def __call__(self, pgid):
        open_runs = self.connection.execute("SELECT COUNT(*) FROM runner_run WHERE released_at IS NULL").fetchone()[0]
        self.calls.append((pgid, open_runs))
        return self.gone.get(pgid, True) if isinstance(self.gone, dict) else self.gone


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root / "sd.db"
        initialise(self.database)
        self.db = connect(self.database)
        self.addCleanup(self.db.close)
        for repo in (A, B):
            upsert_repo(self.db, repo, remote=f"/fixture/remote{repo[-2:]}", managed=1)

    def item(self, repo=A, status="ready", kind="task", priority=None, fields=None):
        return create_item(self.db, kind=kind, title="Build me", repo=repo, status=status, priority=priority,
                           fields=fields)

    def claim(self, db=None, **inputs):
        return build.claim(db or self.db, owner="fixture", root=self.root / "worktrees", **{**IDLE, **inputs})

    def count(self, sql, *args):
        return self.db.execute(sql, args).fetchone()[0]

    def statuses(self, items):
        return [item_state(self.db, item)["item"]["status"] for item in items]


class Queue(Case):
    def test_queue_refuses_whole_selection(self):
        """Failure table, Press: one refusal refuses every item, and nothing is written."""
        ready, planning = self.item(), self.item(status="planning")
        busy = self.item()
        build.queue(self.db, [busy], who="operator")
        upsert_repo(self.db, "/fixture/off", remote="/fixture/r-off", managed=0)
        upsert_repo(self.db, "/fixture/none", managed=1)
        upsert_repo(self.db, "/fixture/sat", remote="/fixture/r-sat", managed=1)
        satellite = self.item(repo="/fixture/sat")
        self.db.execute("UPDATE repo SET lane_host = 'work' WHERE path = '/fixture/sat'")
        stale = self.item()
        revision = item_state(self.db, stale)["revision"]
        self.db.execute("UPDATE item SET title = 'moved' WHERE id = ?", (stale,))
        cases = {
            "is planning; a build takes a ready item": ([ready, planning], None),
            "has queued assignment": ([ready, busy], None),
            "is not managed": ([ready, self.item(repo="/fixture/off")], None),
            "has no remote": ([ready, self.item(repo="/fixture/none")], None),
            "builds run on the hub only": ([ready, satellite], None),
            "is a followup item": ([ready, self.item(kind="followup")], None),
            "needs a registered repository": ([ready, self.item(repo=None)], None),
            "changed; refresh the selection": ([stale], {stale: revision}),
        }
        before = self.count("SELECT COUNT(*) FROM assignment")
        for reason, (items, revisions) in cases.items():
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(build.BuildRefused, reason):
                    build.queue(self.db, items, who="operator", expected_revisions=revisions)
        self.assertEqual(self.count("SELECT COUNT(*) FROM assignment"), before)
        self.assertEqual(self.statuses([ready]), ["ready"])

    def test_a_press_queues_one_build_per_item_and_locks_its_status(self):
        items = [self.item(), self.item()]
        queued = build.queue(self.db, items, who="operator",
                             expected_revisions={item: item_state(self.db, item)["revision"] for item in items})
        self.assertEqual([(row["item"], row["status"], row["role"], row["lane"], row["scope"], row["budget_minutes"])
                          for row in queued],
                         [(item, "queued", "author", "parallel", "build", 60) for item in items])
        with self.assertRaisesRegex(workflow.TransitionRefused, f"cancel queued assignment {queued[0]['id']} first"):
            workflow.change_status(self.db, items[0], "blocked", who="operator")

    def test_a_restore_reimport_holds_the_press_and_the_claim(self):
        item = self.item()
        build.queue(self.db, [item], who="operator")
        record_state(self.db, "restore", body={})
        with self.assertRaisesRegex(build.BuildRefused, "restore reimport"):
            build.queue(self.db, [self.item()], who="operator")
        with self.assertRaisesRegex(build.BuildRefused, "restore reimport"):
            self.claim()
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 0)

    def test_eligible_is_the_ready_items_a_press_takes_by_priority(self):
        low, high = self.item(priority=3), self.item(priority=1)
        self.item(status="planning")
        self.item(kind="followup")
        held = self.item()
        build.queue(self.db, [held], who="operator")
        self.assertEqual([row["id"] for row in build.eligible(self.db)], [high, low])


class Claim(Case):
    def test_a_bundle_is_one_run_one_lease_and_its_items_in_progress(self):
        items = [self.item(), self.item()]
        queued = build.queue(self.db, items, who="operator")
        run = self.claim()
        lead = queued[0]["id"]
        self.assertEqual((run["assignment"], run["branch"], run["step"], run["run"], run["model"]),
                         (lead, f"build/sd-{lead}", "claimed", 1, "opus"))
        self.assertEqual(run["work_path"], str(self.root / "worktrees" / f"a-build-{lead}"))
        self.assertEqual([(m["id"], m["status"]) for m in run["members"]],
                         [(row["id"], "running") for row in queued])
        self.assertEqual(self.db.execute("SELECT parent FROM assignment WHERE id = ?", (queued[1]["id"],)).fetchone()[0], lead)
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL AND branch = ?",
                                    f"build/sd-{lead}"), 1)
        self.assertEqual(self.statuses(items), ["in_progress", "in_progress"])
        self.assertIsNone(self.claim(), "nothing is left queued")

    def test_a_claim_records_the_build_branch_on_every_member_row(self):
        """pack sd:6756: an empty `item.branch` failed sd-docs-lint on a design-only build."""
        items = [self.item(), self.item()]
        self.db.execute("UPDATE item SET branch = 'docs/old' WHERE id = ?", (items[1],))
        lead = build.queue(self.db, items, who="operator")[0]["id"]
        self.claim()
        self.assertEqual([item_state(self.db, item)["item"]["branch"] for item in items],
                         [f"build/sd-{lead}"] * 2)

    def test_a_bundle_of_mechanical_items_runs_sonnet(self):
        build.queue(self.db, [self.item(fields={"work_kind": "mechanical"})], who="operator")
        self.assertEqual(self.claim()["model"], "sonnet")

    def test_a_bundle_takes_at_most_three_and_the_best_repository_first(self):
        build.queue(self.db, [self.item(repo=B, priority=2)], who="operator")
        build.queue(self.db, [self.item(priority=1) for _ in range(4)], who="operator")
        first = self.claim()
        self.assertEqual((first["repo"], len(first["members"])), (A, 3))
        second = self.claim()
        self.assertEqual((second["repo"], len(second["members"])), (A, 1), "the fourth of A still ranks first")
        third = self.claim()
        self.assertEqual((third["repo"], len(third["members"])), (B, 1))

    def test_claim_race_respects_repo_cap(self):
        """Failure table, Claim: `BEGIN IMMEDIATE` serializes claims; the later ones see the earlier leases."""
        items = [self.item() for _ in range(15)]
        build.queue(self.db, items, who="operator")
        barrier, results, errors = threading.Barrier(6), [], []

        def race():
            connection = connect(self.database)
            try:
                barrier.wait()
                results.append(self.claim(connection))
            except Exception as error:  # noqa: BLE001 - the test reports any failure
                errors.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=race) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        runs = [run for run in results if run is not None]
        self.assertEqual(len(runs), build.REPO_CAP)
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), build.REPO_CAP)
        members = [member["item"] for run in runs for member in run["members"]]
        self.assertEqual(len(members), len(set(members)))
        self.assertEqual(self.count("SELECT COUNT(*) FROM assignment WHERE status = 'running'"), 9)

    def test_claim_rolls_back_moved_item(self):
        """Failure table, Claim: an item moved after the press fails the re-check; nothing else changes."""
        items = [self.item(), self.item()]
        queued = build.queue(self.db, items, who="operator")
        transition(self.db, items[1], "in_progress", who="hand")
        self.assertIsNone(self.claim())
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 0)
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease"), 0)
        rows = self.db.execute("SELECT status, result FROM assignment ORDER BY id").fetchall()
        self.assertEqual(rows[0]["status"], "queued")
        self.assertEqual(rows[1]["status"], "blocked")
        self.assertIn(f"item {items[1]} moved to in_progress after the press", rows[1]["result"])
        self.assertEqual(self.statuses(items), ["ready", "in_progress"])
        run = self.claim()
        self.assertEqual([m["id"] for m in run["members"]], [queued[0]["id"]])

    def ineligible_after_press(self, change: str, reason: str):
        """A repository that turns ineligible between press and claim: its builds end blocked, the next repo runs.

        `change` is the SQL that turns repository A ineligible; `reason` the
        refusal `queue` gives for it. The claim re-checks the repository in
        its transaction (pack sd:6103), so A's queued builds end `blocked`
        with that reason, their items stay `ready` for a later press, and the
        same claim goes on to B.
        """
        items = [self.item(priority=1), self.item(priority=1)]
        queued = build.queue(self.db, items, who="operator")
        other = build.queue(self.db, [self.item(repo=B, priority=2)], who="operator")
        self.db.execute(change, (A,))
        run = self.claim()
        self.assertIsNotNone(run, "the ineligible repository does not stall the claim")
        self.assertEqual((run["repo"], [m["id"] for m in run["members"]]), (B, [other[0]["id"]]))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run WHERE repo = ?", A), 0)
        rows = self.db.execute("SELECT status, result FROM assignment WHERE id IN (?, ?) ORDER BY id",
                               tuple(row["id"] for row in queued)).fetchall()
        self.assertEqual([row["status"] for row in rows], ["blocked", "blocked"])
        for row in rows:
            self.assertRegex(row["result"], reason)
        self.assertEqual(self.statuses(items), ["ready", "ready"])
        self.assertIsNone(self.claim(), "nothing of A is left queued")

    def test_a_requeued_bundle_claims_alone_under_its_lead_and_gets_its_worktree_back(self):
        """Pack sd:6020: Send to builder queues a bundle again; its claim keeps the lead, so branch and worktree match."""
        items = [self.item(), self.item()]
        queued = build.queue(self.db, items, who="operator")
        lead = queued[0]["id"]
        first = self.claim()
        build.end(self.db, first["id"], "cancelled", "the operator cancelled it")
        newer = self.item()
        build.queue(self.db, [newer], who="operator")  # queued before the requeue, so it ranks first
        for row in reversed(queued):
            state = runner.queue_state(self.db, row["id"])
            runner.requeue(self.db, row["id"], expected_revision=state["revision"], who="operator")
        runs = [self.claim(), self.claim()]
        self.assertEqual([len(run["members"]) if run else 0 for run in runs].count(0), 0, "two bundles, not one")
        claims = {run["assignment"]: run for run in runs}
        again = claims.pop(lead)
        self.assertEqual((again["branch"], again["work_path"], again["run"]), (first["branch"], first["work_path"], 2))
        self.assertEqual(sorted(member["item"] for member in again["members"]), sorted(items))
        self.assertEqual([member["item"] for member in claims.popitem()[1]["members"]], [newer])

    def test_claim_skips_a_repository_unmanaged_after_the_press(self):
        self.ineligible_after_press("UPDATE repo SET managed = 0 WHERE path = ?", "is not managed")

    def test_claim_skips_a_repository_without_a_remote_after_the_press(self):
        self.ineligible_after_press("UPDATE repo SET remote = NULL WHERE path = ?", "has no remote")

    def test_claim_skips_a_repository_moved_to_a_satellite_lane_after_the_press(self):
        self.ineligible_after_press("UPDATE repo SET lane_host = 'work' WHERE path = ?", "builds run on the hub only")

    def test_claim_respects_exclusive_lease(self):
        """Guard: an exclusive lease of any other kind in the repository leaves it no room."""
        self.db.execute("INSERT INTO assignment (item, role, status, scope) VALUES (?, 'author', 'blocked', 'item')",
                        (self.item(status="planning"),))
        old = self.db.execute("SELECT MAX(id) FROM assignment").fetchone()[0]
        self.db.execute("INSERT INTO runner_run (id, assignment, run, repo, branch, owner, work_path, retained_path, "
                        "created_at, updated_at) VALUES ('old', ?, 1, ?, 'work/x', 'runner', '/w', '/r', '', '')", (old, A))
        self.db.execute("INSERT INTO runner_lease (run, repo, branch, exclusive, acquired_at) VALUES ('old', ?, 'work/x', 1, '')", (A,))
        build.queue(self.db, [self.item()], who="operator")
        self.assertIsNone(self.claim())
        build.queue(self.db, [self.item(repo=B)], who="operator")
        self.assertEqual(self.claim()["repo"], B)

    def test_an_unread_load_or_builder_count_is_no_room(self):
        build.queue(self.db, [self.item()], who="operator")
        for inputs in ({"load": None}, {"load_cap": float("nan")}, {"interactive": None}, {"load": 41.0}):
            with self.subTest(inputs=inputs):
                self.assertIsNone(self.claim(**inputs))
                self.assertTrue(build.room(self.db, **{**IDLE, **inputs})["why"])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 0)

    def test_the_gates_off_limit_is_no_load_cap(self):
        """Review round 1: the gate reports `load_max` 0 when its load rule is off, its default; that is no cap."""
        with mock.patch("sys.path", [str(Path(__file__).resolve().parents[2] / "bin"), *sys.path]):
            gate = import_module("sd_gate_slots")
        off = gate.load_rule({}).limit
        build.queue(self.db, [self.item()], who="operator")
        self.assertEqual(build.room(self.db, **{**IDLE, "load": 2.5, "load_cap": off})["why"], "")
        self.assertIsNotNone(self.claim(load=2.5, load_cap=off))

    def test_interactive_builders_count_against_their_repository_and_the_machine(self):
        build.queue(self.db, [self.item()], who="operator")
        busy = [{"repo": A, "session_id": f"s{n}"} for n in range(3)]
        self.assertIsNone(self.claim(interactive=busy))
        elsewhere = [{"repo": None, "session_id": f"s{n}"} for n in range(6)]
        self.assertIsNone(self.claim(interactive=elsewhere))
        self.assertIn("6 builders run already", build.room(self.db, **{**IDLE, "interactive": elsewhere})["why"])
        run = self.claim(interactive=busy[:2])
        build.write(self.db, run["id"], session_id="headless")
        available = build.room(self.db, **{**IDLE, "interactive": [{"repo": A, "session_id": "headless"}]})
        self.assertEqual(build.room_for(available, A), 2, "a headless run's own session counts once")


class Writes(Case):
    def setUp(self):
        super().setUp()
        self.items = [self.item(), self.item()]
        build.queue(self.db, self.items, who="operator")
        self.bundle = self.claim()

    def test_late_run_writes_nothing(self):
        """Failure table, Enqueued: a late old supervisor's compare-and-set names its own ended run; no row changes."""
        self.db.execute("UPDATE runner_run SET outcome = 'interrupted' WHERE id = ?", (self.bundle["id"],))
        before = {table: self.db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                  for table in ("runner_run", "runner_lease", "assignment", "item")}
        self.assertFalse(build.write(self.db, self.bundle["id"], step="building", heartbeat_at="x"))
        self.assertFalse(build.beat(self.db, self.bundle["id"]))
        self.assertFalse(build.enqueued(self.db, self.bundle["id"]))
        after = {table: self.db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in before}
        self.assertEqual([[tuple(row) for row in rows] for rows in after.values()],
                         [[tuple(row) for row in rows] for rows in before.values()])

    def test_enqueued_releases_the_lease_and_ends_the_members_done(self):
        self.assertTrue(build.write(self.db, self.bundle["id"], step="enqueuing"))
        self.assertTrue(build.enqueued(self.db, self.bundle["id"]))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 0)
        self.assertEqual([m["status"] for m in build.run(self.db, self.bundle["id"])["members"]], ["done", "done"])
        self.assertEqual(self.statuses(self.items), ["in_progress", "in_progress"])
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((row["step"], row["outcome"], row["released_at"]), ("enqueued", None, None),
                         "the run stays open for steps 7 and 8")
        self.assertFalse(build.enqueued(self.db, self.bundle["id"]), "enqueued once")

    def test_reap_skips_enqueued_run(self):
        """Failure table, Enqueued: no supervisor while the run waits on the lane; reap leaves it open."""
        build.write(self.db, self.bundle["id"], step="enqueuing", supervisor_pid=4242, supervisor_start=START)
        build.enqueued(self.db, self.bundle["id"])
        kill = Kill(self.db)
        self.assertEqual(build.reap(self.db, now=later(self.bundle["created_at"], 3600), probe=Probe(alive=False),
                                    kill=kill), [])
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((row["outcome"], row["released_at"], kill.calls), (None, None, []))

    def test_an_abandoned_enqueued_run_releases_once_gone(self):
        """Failure table, Restore: an enqueued run abandoned by a restore is held, then released once it reads gone."""
        build.write(self.db, self.bundle["id"], step="enqueuing")
        build.enqueued(self.db, self.bundle["id"])
        recovery.prepare_restore(self.db)
        build.reap(self.db, probe=Probe(alive=False))
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((row["step"], row["outcome"], row["released_at"] is not None), ("enqueued", "abandoned", True))
        self.assertIsNone(build._held(self.db, self.items[0]), "no held run left")

    def test_reap_judges_a_checking_run(self):
        """Failure table, Checking: a fresh supervisor lost after the merge; gone, so settled and retried at that step."""
        build.write(self.db, self.bundle["id"], step="enqueuing")
        build.enqueued(self.db, self.bundle["id"])
        build.write(self.db, self.bundle["id"], step="checking", supervisor_pid=4242, supervisor_pgid=4242,
                    supervisor_start=START)
        settled = build.reap(self.db, now=later(self.bundle["created_at"], 3600), probe=Probe(alive=False))
        self.assertEqual([(row["run"], row["outcome"], row["blocked"]) for row in settled],
                         [(self.bundle["id"], "interrupted", None)])
        retry = build.run(self.db, settled[0]["retry"])
        self.assertEqual((retry["step"], retry["run"], retry["released_at"]), ("checking", 2, None))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 0,
                         "a lane step takes no builder slot")
        self.assertEqual(self.statuses(self.items), ["in_progress", "in_progress"])

    def test_enqueued_refuses_a_requested_cancel(self):
        """Failure table, Cancel: a cancel committed before `enqueued` wins; the run never reaches the lane."""
        build.write(self.db, self.bundle["id"], step="reviewing")
        state = operations.assignment_state(self.db, self.bundle["assignment"])
        operations.cancel_assignment(self.db, self.bundle["assignment"], expected_revision=state["revision"],
                                     who="operator")
        self.assertFalse(build.enqueuing(self.db, self.bundle["id"]), "the enqueuing compare-and-set loses")
        build.write(self.db, self.bundle["id"], step="enqueuing")
        self.assertFalse(build.enqueued(self.db, self.bundle["id"]))
        self.assertEqual(build.run(self.db, self.bundle["id"])["step"], "enqueuing")
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 1)

    def test_enqueuing_first_refuses_cancel(self):
        """Failure table, Cancel: after the enqueuing compare-and-set a cancel is refused, naming the lane entry."""
        build.write(self.db, self.bundle["id"], step="reviewing")
        self.assertTrue(build.enqueuing(self.db, self.bundle["id"]))
        state = operations.assignment_state(self.db, self.bundle["assignment"])
        self.assertIn("sd-ship lane cancel", state["capabilities"]["cancel"]["reason"])
        with self.assertRaisesRegex(workflow.WorkflowError, "cancel its lane entry"):
            operations.cancel_assignment(self.db, self.bundle["assignment"], expected_revision=state["revision"],
                                         who="operator")
        self.assertIsNone(build.run(self.db, self.bundle["id"])["cancel_requested"])

    def test_cancel_write_checks_the_step(self):
        """A cancel read before the enqueuing compare-and-set and written after it changes nothing (one winner)."""
        build.write(self.db, self.bundle["id"], step="reviewing")
        state = operations.assignment_state(self.db, self.bundle["assignment"])
        real = operations.assignment_state

        def raced(connection, assignment):
            build.enqueuing(self.db, self.bundle["id"])
            return state

        with mock.patch.object(operations, "assignment_state", raced):
            with self.assertRaisesRegex(workflow.WorkflowError, "moved past the steps a cancel may stop"):
                operations.cancel_assignment(self.db, self.bundle["assignment"], expected_revision=state["revision"],
                                             who="operator")
        self.assertIsNone(build.run(self.db, self.bundle["id"])["cancel_requested"])
        self.assertEqual(real(self.db, self.bundle["assignment"])["build_run"], self.bundle["id"])

    def test_a_write_outside_the_run_fields_is_refused(self):
        for fields in ({"outcome": "done"}, {"released_at": "x"}, {"step": "nowhere"}):
            with self.subTest(fields=fields), self.assertRaises(build.BuildRefused):
                build.write(self.db, self.bundle["id"], **fields)


class Reap(Case):
    def setUp(self):
        super().setUp()
        self.items = [self.item(), self.item()]
        build.queue(self.db, self.items, who="operator")
        self.bundle = self.claim()

    def stale(self):
        return later(self.bundle["created_at"], build.STALE_SECONDS + 1)

    def test_reap_unstarted_run(self):
        """Failure table, Spawn: no beat for 180 s after the claim: reaped, a fresh row at `worktree`."""
        self.assertEqual(build.reap(self.db, now=later(self.bundle["created_at"], 60)), [])
        settled = build.reap(self.db, now=self.stale())
        self.assertEqual([(row["run"], row["outcome"]) for row in settled], [(self.bundle["id"], "interrupted")])
        retry = build.run(self.db, settled[0]["retry"])
        self.assertEqual((retry["step"], retry["run"], retry["branch"], retry["work_path"], retry["released_at"]),
                         ("worktree", 2, self.bundle["branch"], self.bundle["work_path"], None))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 1)
        self.assertEqual([m["status"] for m in retry["members"]], ["running", "running"])

    def test_a_second_loss_blocks_the_items_with_an_action_note(self):
        build.write(self.db, self.bundle["id"], step="building", log_path="/logs/one.jsonl")
        retry = build.reap(self.db, now=self.stale())[0]["retry"]
        row = build.run(self.db, retry)
        settled = build.reap(self.db, now=later(row["created_at"], build.STALE_SECONDS + 1))
        self.assertEqual(settled[0]["retry"], None)
        self.assertEqual([m["status"] for m in build.run(self.db, retry)["members"]], ["blocked", "blocked"])
        self.assertEqual(self.statuses(self.items), ["blocked", "blocked"])
        note = self.db.execute("SELECT body FROM note WHERE item = ? AND kind = 'followup'", (self.items[0],)).fetchone()
        self.assertIn("lost at step building", note["body"])
        self.assertIn(row["work_path"], note["body"])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 0)

    def lose(self, **fields):
        """Lose the current run at a stale beat; the fresh row the reap opened."""
        if fields:
            build.write(self.db, self.bundle["id"], **fields)
        settled = build.reap(self.db, now=later(self.bundle["created_at"], build.STALE_SECONDS + 1), probe=Probe())
        self.bundle = build.run(self.db, settled[0]["retry"]) if settled[0]["retry"] else self.bundle
        return settled[0]

    def test_resume_fixing_reviews_again(self):
        """Failure table, Recovery: a loss at fixing resumes at reviewing, round and session kept, in one fresh row."""
        old = self.bundle["id"]
        self.lose(step="fixing", review_round=2, session_id="session-1")
        self.assertEqual((self.bundle["step"], self.bundle["review_round"], self.bundle["session_id"],
                          self.bundle["outcome"], self.bundle["work_path"], self.bundle["branch"]),
                         ("reviewing", 2, "session-1", None, build.run(self.db, old)["work_path"],
                          build.run(self.db, old)["branch"]))
        self.assertEqual(build.run(self.db, old)["outcome"], "interrupted")
        self.assertFalse(build.write(self.db, old, step="building"), "a late old supervisor writes nothing")

    def test_second_loss_same_step(self):
        """Failure table, Recovery: losses at two steps each retry; a second loss at one step blocks."""
        self.assertIsNotNone(self.lose(step="building")["retry"])
        self.assertIsNotNone(self.lose(step="reviewing")["retry"], "a first loss at reviewing")
        self.assertIsNone(self.lose(step="reviewing")["retry"])
        self.assertEqual(self.statuses(self.items), ["blocked", "blocked"])

    def at_lane_step(self, step):
        build.write(self.db, self.bundle["id"], step="enqueuing")
        build.enqueued(self.db, self.bundle["id"])
        build.write(self.db, self.bundle["id"], step=step)

    def test_a_second_loss_at_checking_turns_off_and_files(self):
        """pack sd:6094 (c): health unknown after a second loss, so auto-pickup off, an item filed, then cleaning."""
        set_setting(self.db, "build.auto_pickup_until", "2026-10-25T13:00:00+00:00")
        self.at_lane_step("checking")
        items = self.count("SELECT COUNT(*) FROM item")
        self.assertIsNotNone(self.lose()["retry"], "a first loss at checking retries")
        settled = self.lose()
        self.assertEqual(read_settings(self.db, ["build.auto_pickup_until"]), {"build.auto_pickup_until": None})
        filed = self.db.execute("SELECT * FROM item WHERE id > ? ORDER BY id", (max(self.items),)).fetchall()
        self.assertEqual((self.count("SELECT COUNT(*) FROM item"), len(filed)), (items + 1, 1))
        self.assertIn("health unknown", filed[0]["title"])
        retry = build.run(self.db, settled["retry"])
        self.assertEqual((retry["step"], retry["outcome"], retry["released_at"]), ("cleaning", None, None))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 0)
        self.assertEqual(self.statuses(self.items), ["in_progress", "in_progress"], "the lane owns the items")

    def test_a_second_loss_at_cleaning_ends_done(self):
        """pack sd:6094 (c): a second loss at cleaning ends the run done; the worktree stays, with a note."""
        self.at_lane_step("cleaning")
        self.assertIsNotNone(self.lose()["retry"])
        settled = self.lose()
        row = build.run(self.db, settled["run"])
        self.assertEqual((settled["retry"], row["outcome"], row["released_at"] is not None), (None, "done", True))
        self.assertEqual(self.statuses(self.items), ["in_progress", "in_progress"])
        note = self.db.execute("SELECT body FROM note WHERE item = ? ORDER BY id DESC", (self.items[0],)).fetchone()
        self.assertIn(f"worktree {row['work_path']} kept", note["body"])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run WHERE released_at IS NULL"), 0)

    def test_a_live_supervisor_is_left_alone(self):
        build.write(self.db, self.bundle["id"], supervisor_pid=4242, supervisor_pgid=4242,
                    supervisor_start="Sat Oct 24 09:00:00 2026", heartbeat_at=self.bundle["created_at"])
        soon = later(self.bundle["created_at"], 60)
        self.assertEqual(build.reap(self.db, now=soon, probe=Probe()), [])
        self.assertEqual(build.reap(self.db, now=soon, probe=Probe(alive=None)), [], "an unknown probe is no verdict")
        self.assertEqual(len(build.reap(self.db, now=soon, probe=Probe(started="Sat Oct 24 08:00:00 2026"))), 1,
                         "a reused pid is not the supervisor")

    def test_a_lost_compare_and_set_leaves_a_run_that_beat(self):
        build.write(self.db, self.bundle["id"], heartbeat_at=self.bundle["created_at"])

        class Beating(Probe):
            def alive(probe, pid):
                build.write(self.db, self.bundle["id"], heartbeat_at=later(self.bundle["created_at"], 30))
                return False

        build.write(self.db, self.bundle["id"], supervisor_pid=4242)
        self.assertEqual(build.reap(self.db, now=later(self.bundle["created_at"], 60), probe=Beating()), [])
        self.assertIsNone(build.run(self.db, self.bundle["id"])["outcome"])

    def test_reap_resumes_kill(self):
        """Failure table, Reap ours: a tick killed between the compare-and-set and the kill; the next kills, then retries."""
        self.ended(builder_pgid=777, builder_start=START)
        kill = Kill(self.db)
        settled = build.reap(self.db, probe=Probe(group=True), kill=kill)
        self.assertEqual(kill.calls, [(777, 1)], "the kill came before the retry's new run")
        self.assertIsNotNone(settled[0]["retry"])

    def test_a_group_alive_after_the_kill_ends_blocked(self):
        """Failure table, Reap ours: the group still has a process after SIGKILL: blocked, lease released, no retry."""
        self.ended(builder_pgid=777, builder_start=START)
        settled = build.reap(self.db, probe=Probe(group=True), kill=Kill(self.db, gone=False))
        self.assertEqual([(row["retry"], "777" in row["blocked"]) for row in settled], [(None, True)])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 1)
        self.assertEqual(self.statuses(self.items), ["blocked", "blocked"])

    def test_a_survivor_keeps_its_lease(self):
        """Failure table, Blocked: a group outlives SIGKILL; the run stays unreleased with its lease, a slot short."""
        free = build.room(self.db, **IDLE)["machine"]
        self.ended(builder_pgid=777, builder_start=START)
        build.reap(self.db, probe=Probe(group=True), kill=Kill(self.db, gone=False))
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((row["outcome"], row["released_at"]), ("blocked", None))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 1)
        self.assertEqual(build.room(self.db, **IDLE)["machine"], free, "the survivor still holds its slot")

    def test_third_unsure_keeps_the_lease(self):
        """Failure table, Blocked: the third unsure reap blocks the run but keeps it unreleased with its lease."""
        self.ended(builder_pgid=777, builder_start=START)
        for _ in range(build.DOUBTS):
            build.reap(self.db, probe=Probe(started=None, group=True), kill=Kill(self.db))
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((row["outcome"], row["released_at"]), ("blocked", None))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 1)
        self.assertEqual(self.statuses(self.items), ["blocked", "blocked"])

    def test_blocked_run_releases_once_groups_are_gone(self):
        """Failure table, Blocked: later ticks re-probe; alive or unsure changes nothing, ESRCH releases; never a retry."""
        self.ended(builder_pgid=777, builder_start=START, supervisor_pid=4242, supervisor_pgid=4242,
                   supervisor_start=START)
        build.reap(self.db, probe=Probe(group=True), kill=Kill(self.db, gone=False))
        notes = self.count("SELECT COUNT(*) FROM note WHERE kind = 'followup'")
        for probe in (Probe(group=True), Probe(alive=None, group=None)):
            kill = Kill(self.db)
            self.assertEqual(build.reap(self.db, probe=probe, kill=kill), [])
            self.assertEqual(kill.calls, [], "never killed again")
            self.assertIsNone(build.run(self.db, self.bundle["id"])["released_at"])
        kill = Kill(self.db)
        build.reap(self.db, probe=Probe(alive=False, group=False), kill=kill)
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((row["outcome"], row["released_at"] is not None, kill.calls), ("blocked", True, []))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 0)
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 1, "no retry")
        self.assertEqual(self.count("SELECT COUNT(*) FROM note WHERE kind = 'followup'"), notes, "no new followup")

    def held(self):
        """The bundle's run held (a survivor of SIGKILL), and both items moved back to ready by the operator."""
        self.ended(builder_pgid=777, builder_start=START)
        build.reap(self.db, probe=Probe(group=True), kill=Kill(self.db, gone=False))
        for item in self.items:
            workflow.change_status(self.db, item, "ready", who="operator")
        self.assertEqual(self.statuses(self.items), ["ready", "ready"])

    def test_queue_refuses_an_item_a_held_run_holds(self):
        """Failure table, Held: no press of the lead's or a member's item while its held run keeps the lease."""
        self.held()
        for item in self.items:
            with self.subTest(item=item):
                with self.assertRaisesRegex(build.BuildRefused,
                                            f"held by build run {self.bundle['id']} .*releases once"):
                    build.queue(self.db, [item], who="operator")

    def test_claim_skips_an_item_a_held_run_holds(self):
        """Failure table, Held: a queued build of a held item is not claimed; it ends blocked naming the run."""
        self.held()
        queued = []
        for item in self.items:
            ident = create_assignment(self.db, item=item, role="author", status="queued", lane="parallel")
            self.db.execute("UPDATE assignment SET scope = 'build', queued_at = ? WHERE id = ?",
                            (self.bundle["created_at"], ident))
            queued.append(ident)
        self.assertIsNone(self.claim())
        rows = self.db.execute(f"SELECT status, result FROM assignment WHERE id IN ({queued[0]}, {queued[1]})")
        for row in rows:
            self.assertEqual(row["status"], "blocked")
            self.assertIn(f"held by build run {self.bundle['id']}", row["result"])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 1, "no second builder")

    def ended(self, **fields):
        """The run as a reap that stopped after its compare-and-set left it."""
        build.write(self.db, self.bundle["id"], **fields)
        self.db.execute("UPDATE runner_run SET outcome = 'interrupted' WHERE id = ?", (self.bundle["id"],))

    def unsure(self, probe, **fields):
        """Failure table, Reap unsure: nothing killed, the run and its lease kept, nothing retried."""
        self.ended(builder_pgid=777, **fields)
        kill = Kill(self.db)
        self.assertEqual(build.reap(self.db, probe=probe, kill=kill), [])
        self.assertEqual(kill.calls, [])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run WHERE released_at IS NULL"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 1)
        self.assertEqual(self.statuses(self.items), ["in_progress", "in_progress"])

    def supervised(self):
        """A stale run whose supervisor (pid 4242, group 4242) and builder (group 777) both still answer."""
        build.write(self.db, self.bundle["id"], supervisor_pid=4242, supervisor_pgid=4242, supervisor_start=START,
                    builder_pgid=777, builder_start=START)
        return later(self.bundle["created_at"], build.STALE_SECONDS + 1)

    def test_ours_with_live_supervisor_kills_both_before_retry(self):
        """Failure table, Reap ours: a paused supervisor and its builder are killed, both ESRCH, then the retry."""
        kill = Kill(self.db)
        settled = build.reap(self.db, now=self.supervised(), probe=Probe(group=True), kill=kill)
        self.assertEqual(kill.calls, [(4242, 1), (777, 1)], "both groups die before the retry's new run")
        self.assertEqual([row["blocked"] for row in settled], [None])
        self.assertIsNotNone(settled[0]["retry"])

    def test_ours_supervisor_survives_kill_ends_blocked(self):
        """Failure table, Reap ours: the supervisor's group outlives SIGKILL: blocked, no retry."""
        kill = Kill(self.db, gone={4242: False})
        settled = build.reap(self.db, now=self.supervised(), probe=Probe(group=True), kill=kill)
        self.assertEqual([(row["retry"], "4242" in row["blocked"]) for row in settled], [(None, True)])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 1)
        self.assertEqual(self.statuses(self.items), ["blocked", "blocked"])

    def test_ours_supervisor_unproven_is_unsure(self):
        """Failure table, Reap unsure: a live supervisor whose start is unread, or EPERM, or no group: no kill."""
        for name, probe, fields in (("start unread", Probe(started=None), {}),
                                    ("EPERM", Probe(alive=None), {}),
                                    ("no group recorded", Probe(), {"supervisor_pgid": None})):
            with self.subTest(name):
                self.supervised()
                build.write(self.db, self.bundle["id"], builder_pgid=None, **fields)
                self.db.execute("UPDATE runner_run SET outcome = 'interrupted', doubts = NULL WHERE id = ?",
                                (self.bundle["id"],))
                kill = Kill(self.db)
                self.assertEqual(build.reap(self.db, probe=probe, kill=kill), [])
                self.assertEqual(kill.calls, [])
                self.db.execute("UPDATE runner_run SET outcome = NULL WHERE id = ?", (self.bundle["id"],))

    def test_a_live_builder_whose_start_is_unread_is_unsure(self):
        """The round-2 repro: before, this settled and retried into the live builder's worktree."""
        self.unsure(Probe(started=None, group=True), builder_start=START)

    def test_a_reused_builder_pid_with_group_members_is_unsure(self):
        self.unsure(Probe(started="Sat Oct 24 08:00:00 2026", group=True), builder_start=START)

    def test_a_dead_leader_with_a_live_child_is_unsure(self):
        self.unsure(Probe(alive=False, group=True), builder_start=START)

    def test_a_group_the_probe_cannot_read_is_unsure(self):
        self.unsure(Probe(alive=None, group=None), builder_start=START)

    def test_a_builder_without_a_recorded_start_is_unsure(self):
        self.unsure(Probe(group=True))

    def test_a_supervisor_the_probe_cannot_read_is_unsure(self):
        self.unsure(Probe(pids={4242: (None, None), 777: (False, None)}), supervisor_pid=4242,
                    supervisor_start=START, builder_start=START)

    def test_three_unsure_reaps_end_the_run_blocked_naming_the_group(self):
        """Failure table, Reap unsure: the third unsure reap in a row ends it blocked with an action note, no retry."""
        self.ended(builder_pgid=777, builder_start=START)
        kill, probe = Kill(self.db), Probe(started=None, group=True)
        self.assertEqual(build.reap(self.db, probe=probe, kill=kill), [])
        self.assertEqual(build.reap(self.db, probe=probe, kill=kill), [])
        settled = build.reap(self.db, probe=probe, kill=kill)
        self.assertEqual(kill.calls, [])
        self.assertEqual([row["retry"] for row in settled], [None])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 1)
        self.assertEqual(self.statuses(self.items), ["blocked", "blocked"])
        note = self.db.execute("SELECT body FROM note WHERE item = ? AND kind = 'followup'", (self.items[0],)).fetchone()
        self.assertIn("builder group 777", note["body"])

    def test_an_empty_group_and_a_gone_supervisor_are_gone(self):
        """Failure table, Reap gone: no process in the group, the supervisor gone or its pid reused: settled, retried."""
        for name, pids in {"gone": {4242: (False, None)}, "reused": {4242: (True, "Sat Oct 24 08:00:00 2026")}}.items():
            with self.subTest(name):
                self.ended(builder_pgid=777, builder_start=START, supervisor_pid=4242, supervisor_pgid=4242,
                           supervisor_start=START)
                kill = Kill(self.db)
                settled = build.reap(self.db, probe=Probe(alive=False, pids=pids), kill=kill)
                self.assertEqual(kill.calls, [])
                self.assertEqual([row["blocked"] for row in settled], [None])
                self.bundle = build.run(self.db, settled[0]["retry"]) if settled[0]["retry"] else self.bundle
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 3,
                         "a loss at claimed resumes at worktree; one there is a first loss too")

    def test_a_restore_abandons_every_open_build_run_unretried(self):
        """Failure table, Restore: runs end abandoned, unretried, leases kept; a reap releases each once it reads gone."""
        self.ended(builder_pgid=777, builder_start=START)
        build.queue(self.db, [self.item(repo=B)], who="operator")
        other = self.claim()
        recovery.prepare_restore(self.db)
        rows = {row["id"]: (row["outcome"], row["released_at"]) for row in build.open_runs(self.db)}
        self.assertEqual(rows, {self.bundle["id"]: ("abandoned", None), other["id"]: ("abandoned", None)})
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 2)
        self.assertEqual(self.count("SELECT COUNT(*) FROM assignment WHERE status = 'blocked'"), 3)
        kill = Kill(self.db)
        self.assertEqual(build.reap(self.db, now=self.stale(), probe=Probe(group=True), kill=kill), [])
        self.assertEqual(kill.calls, [], "an abandoned run is never signalled")
        self.assertEqual([row["id"] for row in build.open_runs(self.db)], [self.bundle["id"]],
                         "the run with no process is released; the one whose builder answers keeps its lease")
        build.reap(self.db, now=self.stale(), probe=Probe(alive=False), kill=kill)
        self.assertEqual((build.open_runs(self.db), kill.calls), ([], []))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 2, "no retry")

    def test_dead_supervisor_with_live_group_is_not_gone(self):
        """Failure table, Reap unsure: the supervisor pid is dead but its group (a git child) lives: no settle."""
        self.ended(supervisor_pid=4242, supervisor_pgid=4242, supervisor_start=START)
        kill = Kill(self.db)
        self.assertEqual(build.verdict(build.run(self.db, self.bundle["id"]), probe=Probe(alive=False, group=True)),
                         (build.UNSURE, []))
        self.assertEqual(build.reap(self.db, probe=Probe(alive=False, group=True), kill=kill), [])
        self.assertEqual((kill.calls, self.count("SELECT COUNT(*) FROM runner_run")), ([], 1))

    def test_a_supervisor_with_no_recorded_group_is_unsure(self):
        """Failure table, Reap unsure: a dead supervisor pid with no group recorded may have left children."""
        self.ended(supervisor_pid=4242, supervisor_start=START)
        self.assertEqual(build.reap(self.db, probe=Probe(alive=False), kill=Kill(self.db)), [])
        self.assertIsNone(build.run(self.db, self.bundle["id"])["released_at"])

    def test_a_cancel_waits_for_the_supervisor_group(self):
        """Failure table, Cancel: a cancelled run whose dead supervisor's group lives is not settled; items stay."""
        build.write(self.db, self.bundle["id"], supervisor_pid=4242, supervisor_pgid=4242, supervisor_start=START)
        state = operations.assignment_state(self.db, self.bundle["assignment"])
        operations.cancel_assignment(self.db, self.bundle["assignment"], expected_revision=state["revision"],
                                     who="operator")
        self.assertEqual(build.reap(self.db, now=self.stale(), probe=Probe(alive=False, group=True)), [])
        self.assertEqual(self.statuses(self.items), ["in_progress", "in_progress"])
        settled = build.reap(self.db, now=self.stale(), probe=Probe(alive=False))
        self.assertEqual([(row["outcome"], row["retry"]) for row in settled], [("cancelled", None)])

    def test_a_held_run_waits_for_the_supervisor_group(self):
        """Failure table, Blocked: `_release` asks `verdict`, so a live supervisor group keeps the lease."""
        self.ended(supervisor_pid=4242, supervisor_pgid=4242, supervisor_start=START, builder_pgid=777,
                   builder_start=START)
        build.reap(self.db, probe=Probe(group=True), kill=Kill(self.db, gone=False))
        build.reap(self.db, probe=Probe(alive=False, group=True), kill=Kill(self.db))
        self.assertIsNone(build.run(self.db, self.bundle["id"])["released_at"])

    def test_promotion_keeps_build_leases(self):
        """Failure table, Promote: the runner's leases are released; a build run's stays until a reap reads it gone."""
        self.assertEqual(backup._release_leases(self.db), [])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 1)

    def test_a_reimport_pending_holds_the_reap(self):
        """Failure table, Restore: a run the restore did not see is left alone until the reimport ends."""
        record_state(self.db, "restore", body={})
        kill = Kill(self.db)
        self.assertEqual(build.reap(self.db, now=self.stale(), probe=Probe(), kill=kill), [])
        self.assertIsNone(build.run(self.db, self.bundle["id"])["outcome"])

    def test_a_bundle_with_no_running_member_is_released_not_retried(self):
        """Failure table, Retry: members blocked by hand under an open run: released, no retry, no duplicate run."""
        self.db.execute("UPDATE assignment SET status = 'blocked' WHERE scope = 'build'")
        settled = build.reap(self.db, now=self.stale(), probe=Probe())
        self.assertEqual([(row["outcome"], row["retry"]) for row in settled], [("interrupted", None)])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run WHERE released_at IS NULL"), 0)

    def test_a_retry_numbers_after_the_leads_last_run(self):
        """Failure table, Retry: a run count behind the lead's runs still gives the retry a fresh number."""
        self.db.execute("UPDATE assignment SET run_count = 0 WHERE scope = 'build'")
        retry = build.run(self.db, build.reap(self.db, now=self.stale(), probe=Probe())[0]["retry"])
        self.assertEqual(retry["run"], 2)
        self.assertEqual(self.count("SELECT COUNT(*) FROM assignment WHERE scope = 'build' AND run_count = 2"), 2)

    def test_cancel_dead_supervisor(self):
        """Failure table, Cancel: the supervisor is dead at cancel; the reap ends the bundle cancelled, not retried."""
        lead = self.bundle["assignment"]
        member = self.bundle["members"][1]["id"]
        state = operations.assignment_state(self.db, member)
        self.assertTrue(state["capabilities"]["cancel"]["allowed"])
        operations.cancel_assignment(self.db, member, expected_revision=state["revision"], who="operator")
        self.assertEqual(self.count("SELECT COUNT(*) FROM assignment WHERE status = 'running'"), 2,
                         "the cancel is asked, not done")
        settled = build.reap(self.db, now=self.stale())
        self.assertEqual([(row["outcome"], row["retry"]) for row in settled], [("cancelled", None)])
        self.assertEqual([m["status"] for m in build.run(self.db, self.bundle["id"])["members"]], ["cancelled", "cancelled"])
        self.assertEqual(self.statuses(self.items), ["ready", "ready"])
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run WHERE assignment = ?", lead), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_lease WHERE released_at IS NULL"), 0)

    def test_a_running_build_names_its_cancel_in_the_status_refusal(self):
        with self.assertRaisesRegex(workflow.TransitionRefused,
                                    f"cancel running build assignment {self.bundle['assignment']} first"):
            workflow.change_status(self.db, self.items[0], "blocked", who="operator")


class Park(Case):
    """pack sd:6132 (operator ruling #32107): a build run that ends blocked parks its items once its lease is
    released, as the nightly prune parks an idle item (sd:6008); a run that ends done or retried parks nothing."""

    def setUp(self):
        super().setUp()
        self.items = [self.item(), self.item()]
        build.queue(self.db, self.items, who="operator")
        self.bundle = self.claim()

    def parked(self):
        return [item_state(self.db, item)["item"]["parked_at"] is not None for item in self.items]

    def lose(self, row):
        return build.reap(self.db, now=later(row["created_at"], build.STALE_SECONDS + 1))[0]

    def test_a_second_loss_parks_the_blocked_items_and_a_retry_parks_none(self):
        build.write(self.db, self.bundle["id"], step="building")
        retry = self.lose(self.bundle)["retry"]
        self.assertEqual(self.parked(), [False, False], "a retried run parks nothing")
        self.assertIsNone(self.lose(build.run(self.db, retry))["retry"])
        self.assertEqual((self.statuses(self.items), self.parked()), (["blocked", "blocked"], [True, True]))
        note = self.db.execute("SELECT body FROM note WHERE item = ? AND kind = 'comment' ORDER BY id DESC",
                               (self.items[0],)).fetchone()
        self.assertEqual(note["body"], build.PARKED.format(run=retry))

    def test_a_held_blocked_run_parks_its_items_only_when_its_lease_is_released(self):
        """A supervisor that ends blocked holds the lease until its groups read gone; the park waits for that, and an
        item the operator moved on in the meantime stays unparked."""
        build.write(self.db, self.bundle["id"], supervisor_pid=4242, supervisor_pgid=4242, supervisor_start=START,
                    builder_pgid=777, builder_start=START)
        build.end(self.db, self.bundle["id"], "blocked", "a permission denial")
        self.assertEqual((self.statuses(self.items), self.parked()), (["blocked", "blocked"], [False, False]))
        workflow.change_status(self.db, self.items[1], "ready", who="operator")
        build.reap(self.db, probe=Probe(alive=False, group=False), kill=Kill(self.db))
        self.assertIsNotNone(build.run(self.db, self.bundle["id"])["released_at"])
        self.assertEqual(self.parked(), [True, False])

    def test_a_run_that_ends_done_parks_nothing(self):
        build.end(self.db, self.bundle["id"], "done", "the lane merged it")
        self.assertEqual(self.parked(), [False, False])

    def test_a_park_never_unparks_or_restamps_an_item(self):
        """An item parked already keeps its first stamp and gets no second note."""
        build.write(self.db, self.bundle["id"], step="building")
        retry = self.lose(self.bundle)["retry"]
        workflow.edit_item(self.db, self.items[0], {"parked_at": "2026-10-01T00:00:00+00:00"}, who="operator")
        self.lose(build.run(self.db, retry))
        self.assertEqual(item_state(self.db, self.items[0])["item"]["parked_at"], "2026-10-01T00:00:00+00:00")
        self.assertEqual(self.count("SELECT COUNT(*) FROM note WHERE item = ? AND body LIKE 'Parked: build run%'",
                                    self.items[0]), 0)


class Race(Case):
    """Race table: a writer runs between the reap's read and its compare-and-set; the reap must do nothing then."""

    def setUp(self):
        super().setUp()
        self.items = [self.item(), self.item()]
        build.queue(self.db, self.items, who="operator")
        self.bundle = self.claim()
        self.stale = later(self.bundle["created_at"], build.STALE_SECONDS + 1)

    def reap_after(self, writer, probe=None):
        """One reap whose `open_runs` read is followed by `writer`, as a supervisor or an operator landing then."""
        read = build.open_runs

        def snapshot(connection):
            rows = read(connection)
            writer()
            return rows

        kill = Kill(self.db)
        with mock.patch.object(build, "open_runs", snapshot):
            settled = build.reap(self.db, now=self.stale, probe=probe or Probe(alive=False), kill=kill)
        return settled, kill

    def test_enqueued_between_read_and_reap_wins(self):
        build.write(self.db, self.bundle["id"], step="enqueuing")
        settled, kill = self.reap_after(lambda: build.enqueued(self.db, self.bundle["id"]))
        row = build.run(self.db, self.bundle["id"])
        self.assertEqual((settled, kill.calls, row["step"], row["outcome"], row["released_at"]),
                         ([], [], "enqueued", None, None))
        self.assertEqual(self.count("SELECT COUNT(*) FROM runner_run"), 1, "no retry")

    def test_cancel_between_read_and_reap_wins(self):
        def cancel():
            state = operations.assignment_state(self.db, self.bundle["assignment"])
            operations.cancel_assignment(self.db, self.bundle["assignment"], expected_revision=state["revision"],
                                         who="operator")

        settled, _ = self.reap_after(cancel)
        self.assertEqual(settled, [])
        settled = build.reap(self.db, now=self.stale, probe=Probe(alive=False))
        self.assertEqual([(row["outcome"], row["retry"]) for row in settled], [("cancelled", None)])
        self.assertEqual(self.statuses(self.items), ["ready", "ready"])

    def test_cancel_after_the_compare_and_set_still_wins(self):
        """The cancel lands on the ended, unreleased run: its settle ends it cancelled, no fresh row."""
        self.db.execute("UPDATE runner_run SET outcome = 'interrupted' WHERE id = ?", (self.bundle["id"],))
        state = operations.assignment_state(self.db, self.bundle["assignment"])
        operations.cancel_assignment(self.db, self.bundle["assignment"], expected_revision=state["revision"],
                                     who="operator")
        settled = build.reap(self.db, now=self.stale, probe=Probe(alive=False))
        self.assertEqual([row["retry"] for row in settled], [None])
        self.assertEqual(self.statuses(self.items), ["ready", "ready"])

    def test_supervisor_registration_between_read_and_reap_wins(self):
        settled, kill = self.reap_after(lambda: build.write(
            self.db, self.bundle["id"], supervisor_pid=4242, supervisor_pgid=4242, supervisor_start=START))
        self.assertEqual((settled, kill.calls, build.run(self.db, self.bundle["id"])["outcome"]), ([], [], None))

    def test_builder_registration_between_read_and_reap_wins(self):
        settled, kill = self.reap_after(lambda: build.write(
            self.db, self.bundle["id"], builder_pgid=777, builder_start=START))
        self.assertEqual((settled, kill.calls, build.run(self.db, self.bundle["id"])["outcome"]), ([], [], None))

    def test_a_step_between_read_and_reap_wins(self):
        settled, _ = self.reap_after(lambda: build.write(self.db, self.bundle["id"], step="building"))
        self.assertEqual((settled, build.run(self.db, self.bundle["id"])["outcome"]), ([], None))

    def test_a_beat_between_read_and_reap_wins(self):
        settled, _ = self.reap_after(lambda: build.beat(self.db, self.bundle["id"]))
        self.assertEqual((settled, build.run(self.db, self.bundle["id"])["outcome"]), ([], None))


class Backup(Case):
    """Guard: the backup's journal check covers the runner's runs; a build run keeps no journal."""

    def snapshot(self) -> Path:
        """The store's copy in a backup directory, as `_snapshot` leaves it: WAL pages included."""
        directory = self.root / "backup"
        directory.mkdir()
        copy = sqlite3.connect(directory / self.database.name)
        self.db.backup(copy)
        copy.close()
        return directory

    def test_a_build_run_needs_no_journal(self):
        build.queue(self.db, [self.item()], who="operator")
        self.claim()
        directory = self.snapshot()
        self.assertFalse(backup._copy_runner_journal(self.database, directory, {"runner_run": 1}))
        backup._check_runner_records(self.db, directory)

    def test_a_runner_run_still_needs_its_journal(self):
        self.db.execute("INSERT INTO assignment (item, role, status, scope) VALUES (?, 'author', 'blocked', 'item')",
                        (self.item(status="planning"),))
        old = self.db.execute("SELECT MAX(id) FROM assignment").fetchone()[0]
        self.db.execute("INSERT INTO runner_run (id, assignment, run, repo, branch, owner, work_path, retained_path, "
                        "created_at, updated_at, released_at) VALUES ('old', ?, 1, ?, 'w', 'runner', '/w', '/r', '', '', 'x')",
                        (old, A))
        directory = self.snapshot()
        with self.assertRaisesRegex(BackupError, "durable journal is missing"):
            backup._copy_runner_journal(self.database, directory, {"runner_run": 1})


if __name__ == "__main__":
    unittest.main()
