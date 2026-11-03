"""Teammate runs: a lead's in-session builder on the build run's rows (pack sd:7221).

The failure table in `docs/work/2026-11-02-builder-heartbeat/design.md` names
these tests. The merge guard's and the backup's are in `test_ship.py` and
`test_build.py`, the CLI's in `tests/test_sd_operations.py`, and the
readers' in the dashboard's `test_build_panel.py` and `test_now_screen.py`.
"""
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

from sd_db import (
    build,
    progress,
    reads,
    reporting,
    runner,
    skills_catalog,
    teammate,
    today,
    workflow,
)
from sd_db.database import connect
from sd_db.migrate import initialise
from sd_db.writes import create_assignment, create_item, record_state, upsert_repo
from sd_db.writes import now as clock

from .test_build import later

build_run = import_module("sd_db.build_run")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bin"))
sd_lane = import_module("sd_lane")
A, B = "/fixture/a", "/fixture/b"
REMOTE = "git@github.com:Fixture/Repo.git"


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
            upsert_repo(self.db, repo, remote=REMOTE if repo == A else "/fixture/remote-b", managed=1)

    def item(self, repo=A, status="in_progress"):
        return create_item(self.db, kind="task", title="Teammate builds me", repo=repo, status=status)

    def start(self, items, budget=90):
        return teammate.start(self.db, items, worktree="/w/pack-1", branch="feat/x", budget_minutes=budget,
                              owner="lead")

    def run_row(self, ident):
        return dict(self.db.execute("SELECT * FROM runner_run WHERE id = ?", (ident,)).fetchone())

    def assignments(self, ident):
        lead = self.run_row(ident)["assignment"]
        return [tuple(row) for row in self.db.execute(
            "SELECT item, status, scope, budget_minutes, parent IS NULL FROM assignment WHERE id = ? OR parent = ? "
            "ORDER BY id", (lead, lead))]


class Start(Case):
    def test_a_start_writes_one_run_and_one_assignment_per_item_lead_first(self):
        first, second = self.item(), self.item()
        run = self.start([first, second])
        self.assertEqual([member["item"] for member in run["members"]], [first, second])
        self.assertEqual(self.assignments(run["id"]), [(first, "in_session", "teammate", 90, 1),
                                                        (second, "in_session", "teammate", 90, 0)])
        row = self.run_row(run["id"])
        self.assertEqual((row["repo"], row["branch"], row["work_path"], row["step"], row["outcome"], row["released_at"]),
                         (A, "feat/x", "/w/pack-1", "building", None, None))
        self.assertEqual(run["due"], later(row["created_at"], 90 * 60))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM runner_lease").fetchone()[0], 0)

    def test_a_start_refuses_and_writes_nothing(self):
        held, done, other = self.item(), self.item(status="done"), self.item(repo=B)
        self.start([held])
        record = self.item()
        cases = {"held": ([held], "held by teammate run"), "done": ([done], "is done"),
                 "two repos": ([record, other], "share one repository"), "none": ([], "distinct items"),
                 "twice": ([record, record], "distinct items"), "no item": ([99999], "no item 99999")}
        before = self.db.execute("SELECT COUNT(*) FROM assignment").fetchone()[0]
        for case, (items, why) in cases.items():
            with self.subTest(case=case), self.assertRaisesRegex(teammate.TeammateRefused, why):
                self.start(items)
        with self.assertRaisesRegex(teammate.TeammateRefused, "positive number"):
            self.start([record], budget=0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM assignment").fetchone()[0], before)

    def test_a_start_refuses_an_item_a_build_holds(self):
        item = self.item(status="ready")
        build.queue(self.db, [item], who="operator")
        with self.assertRaisesRegex(teammate.TeammateRefused, "queued build assignment"):
            self.start([item])

    def test_a_restore_reimport_holds_a_start_and_the_reap(self):
        item = self.item()
        run = self.start([item])
        record_state(self.db, "restore", key="fixture", body={})
        with self.assertRaisesRegex(teammate.TeammateRefused, "restore"):
            self.start([self.item()])
        self.assertEqual(teammate.reap(self.db, now=later(run["created_at"], 10 * 3600)), [])

    def test_the_session_still_moves_its_items(self):
        """A running assignment refuses every status write (criterion 7.19); a teammate's does not."""
        item = self.item(status="ready")
        self.start([item])
        workflow.change_status(self.db, item, "in_progress", who="builder")
        self.assertEqual(workflow.item_state(self.db, item)["item"]["status"], "in_progress")


class Ownership(Case):
    """An open teammate run owns its items against every pickup; the session's own writes still pass.

    The design's failure table, "Ownership readers", names each reader and
    whether it reads `in_session`; these tests pin each decision.
    """

    def held(self, status="ready", **fields):
        item = self.item(status=status)
        if fields:
            self.db.execute("UPDATE item SET " + ", ".join(f"{key} = ?" for key in fields) + " WHERE id = ?",
                            (*fields.values(), item))
        return item, self.start([item])

    def test_auto_pickup_and_the_build_press_skip_a_teammates_item(self):
        item, _ = self.held()
        free = self.item(status="ready")
        self.assertEqual([row["id"] for row in build.eligible(self.db)], [free])
        with self.assertRaisesRegex(build.BuildRefused, f"item {item} has in_session assignment"):
            build.queue(self.db, [item], who="operator")

    def test_a_queued_build_of_a_teammates_item_is_not_claimed(self):
        item, _ = self.held()
        queued = create_assignment(self.db, item=item, role="author", status="queued", lane="parallel")
        self.db.execute("UPDATE assignment SET scope = 'build', queued_at = ? WHERE id = ?", (clock(), queued))
        self.assertIsNone(build.claim(self.db, owner="fixture", root=self.root / "worktrees", load=1.0,
                                      load_cap=40.0, interactive=[]))
        row = self.db.execute("SELECT status, result FROM assignment WHERE id = ?", (queued,)).fetchone()
        self.assertEqual(row["status"], "blocked")
        self.assertIn("a teammate builds it", row["result"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM runner_run").fetchone()[0], 1, "no second builder")

    def test_the_runner_queue_and_its_delivery_skip_a_teammates_item(self):
        item, _ = self.held(branch="feat/x")
        with self.assertRaisesRegex(runner.RunnerRefused, f"item {item} already has queued work"):
            runner.enqueue(self.db, [item], who="operator")
        sent, _ = self.held(status="ready_to_send", branch="feat/x")
        self.assertNotIn(sent, [row["id"] for row in runner.delivery_candidates(self.db)])

    def test_unscheduled_and_the_report_clean_skip_a_teammates_item(self):
        item, _ = self.held()
        self.assertNotIn(item, [row["id"] for row in today.unscheduled(self.db)])
        report = create_item(self.db, kind="report", title="A clean report", repo=A, status="planning",
                             fields={"attention": 0})
        self.db.execute("UPDATE item SET created_at = '2026-01-01T00:00:00Z' WHERE id = ?", (report,))
        self.start([report])
        found = reporting.clean_reports(self.db, before=reporting.cutoff("2026-02-01"))
        self.assertEqual([row["id"] for row in found["selected"]], [])
        self.assertEqual(found["declined"], [{"id": report, "why": "work on it is queued, running or ending"}])

    def test_a_skill_review_a_teammate_holds_takes_no_proposals(self):
        review = create_item(self.db, kind="task", title="Review a skill", repo=A, status="ready",
                             source="skill-request", fields={"skill_review": {"action": "review", "review_result": "x"}})
        self.start([self.item(status="ready"), review])  # a member: the lead's item has the run's row
        revision = workflow.item_state(self.db, review)["revision"]
        with self.assertRaisesRegex(workflow.WorkflowError, "wait for the reviewer"):
            skills_catalog.apply_proposals(self.db, review, [1], expected_revision=revision, who="operator")

    def test_the_lane_keeps_a_teammates_worktree(self):
        item, _ = self.held()
        self.db.execute("UPDATE item SET status = 'done' WHERE id = ?", (item,))
        self.assertIn(f"of item {item} is active", sd_lane.builder_busy(self.db, self.root / "w", item))

    def test_the_sessions_own_status_cancel_and_edit_writes_pass(self):
        """Criterion 7.19 guards the runner's rows; a teammate's are the session's, so it reads `ACTIVE_ASSIGNMENTS`."""
        item, _ = self.held()
        self.assertIn("in_progress", workflow.allowed_statuses(self.db, item))
        self.assertEqual(progress.task_guard(self.db, workflow.item_state(self.db, item)["item"]), "")
        workflow._refuse_active_assignment(self.db, item)
        self.assertNotIn(teammate.STATUS, workflow.ACTIVE_ASSIGNMENTS)
        self.assertEqual([row["item"] for row in reads.assignment_ledger(self.db, live=True)], [],
                         "the Management page lists the lane's order; the Queue view lists teammate runs")


class Beat(Case):
    def test_a_beat_by_any_item_refreshes_the_run(self):
        first, second = self.item(), self.item()
        run = self.start([first, second])
        self.db.execute("UPDATE runner_run SET heartbeat_at = '2026-11-02T00:00:00+00:00' WHERE id = ?", (run["id"],))
        self.assertEqual(teammate.beat(self.db, second), run["id"])
        self.assertGreater(self.run_row(run["id"])["heartbeat_at"], "2026-11-02T00:00:00+00:00")

    def test_a_beat_with_no_open_run_refuses(self):
        item = self.item()
        with self.assertRaisesRegex(teammate.TeammateRefused, f"no open teammate run holds item {item}"):
            teammate.beat(self.db, item)
        run = self.start([item])
        teammate.end(self.db, item)
        with self.assertRaisesRegex(teammate.TeammateRefused, "no open teammate run"):
            teammate.beat(self.db, item)
        self.assertEqual(self.run_row(run["id"])["outcome"], "done")


class End(Case):
    def test_an_end_releases_the_run_and_leaves_the_items_as_they_are(self):
        first, second = self.item(), self.item(status="blocked")
        run = self.start([first, second])
        self.assertEqual(teammate.end(self.db, first, reason="reported"), run["id"])
        row = self.run_row(run["id"])
        self.assertEqual((row["outcome"], row["detail"]), ("done", "reported"))
        self.assertIsNotNone(row["released_at"])
        self.assertEqual([status for _, status, *_ in self.assignments(run["id"])], ["done", "done"])
        self.assertEqual([workflow.item_state(self.db, item)["item"]["status"] for item in (first, second)],
                         ["in_progress", "blocked"])
        self.assertEqual(teammate.open_runs(self.db), [])
        self.start([first])  # ended, the items take a new run


class Reap(Case):
    def test_a_quiet_run_inside_its_budget_lives_past_the_build_stale_limit(self):
        """The build reap ends a run after `build.STALE_SECONDS`; a builder beats only at checkpoints."""
        run = self.start([self.item()])
        self.assertEqual(teammate.reap(self.db, now=later(run["created_at"], build.STALE_SECONDS * 6)), [])
        self.assertIsNone(self.run_row(run["id"])["outcome"])

    def test_a_run_silent_past_its_budget_and_grace_ends_interrupted(self):
        item = self.item()
        run = self.start([item])
        edge = (90 + teammate.GRACE_MINUTES) * 60
        self.assertEqual(teammate.reap(self.db, now=later(run["created_at"], edge - 1)), [])
        ended = teammate.reap(self.db, now=later(run["created_at"], edge))
        self.assertEqual(ended, [{"run": run["id"], "outcome": "interrupted", "retry": None, "blocked": None}])
        row = self.run_row(run["id"])
        self.assertIn("no beat for 120 min", row["detail"])
        self.assertIsNotNone(row["released_at"])
        self.assertEqual(self.assignments(run["id"])[0][1], "cancelled")
        self.assertEqual(workflow.item_state(self.db, item)["item"]["status"], "in_progress")

    def test_a_beat_restarts_the_silence(self):
        run = self.start([self.item()])
        beat = later(run["created_at"], 100 * 60)
        self.db.execute("UPDATE runner_run SET heartbeat_at = ? WHERE id = ?", (beat, run["id"]))
        self.assertEqual(teammate.reap(self.db, now=later(run["created_at"], 150 * 60)), [])
        self.assertEqual(len(teammate.reap(self.db, now=later(beat, 120 * 60))), 1)

    def test_a_beat_between_the_read_and_the_end_keeps_the_run(self):
        """The end is a compare-and-set on the beat the reap read."""
        run = self.start([self.item()])
        reads = teammate.open_runs

        def read_then_beat(connection):
            found = reads(connection)
            connection.execute("UPDATE runner_run SET heartbeat_at = '2099-01-01T00:00:00+00:00' WHERE id = ?",
                               (run["id"],))
            return found
        teammate.open_runs = read_then_beat
        self.addCleanup(setattr, teammate, "open_runs", reads)
        self.assertEqual(teammate.reap(self.db, now=later(run["created_at"], 10 * 3600)), [])
        self.assertIsNone(self.run_row(run["id"])["outcome"])

    def test_a_run_whose_items_all_landed_ends_done(self):
        first, second = self.item(), self.item()
        run = self.start([first, second])
        self.db.execute("UPDATE item SET status = 'done' WHERE id = ?", (first,))
        self.assertEqual(teammate.reap(self.db, now=later(run["created_at"], 60)), [])
        self.db.execute("UPDATE item SET status = 'done' WHERE id = ?", (second,))
        self.assertEqual(teammate.reap(self.db, now=later(run["created_at"], 60))[0]["outcome"], "done")
        self.assertEqual([status for _, status, *_ in self.assignments(run["id"])], ["done", "done"])

    def test_the_dispatch_tick_reaps_teammate_runs(self):
        run = self.start([self.item()])
        self.db.execute("UPDATE runner_run SET heartbeat_at = '2000-01-01T00:00:00+00:00', "
                        "created_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (run["id"],))
        result = build_run.dispatch(self.db, owner="fixture", load=None, load_cap=None, interactive=None,
                                    spawn=lambda ident: None, lane=lambda row, items: None, why="fixture")
        self.assertIn(run["id"], [entry["run"] for entry in result["reaped"]])
        self.assertEqual(result["spawned"], [])


if __name__ == "__main__":
    unittest.main()
