"""The merge lane: a hold on the repository's ship lock (sd:2035), and a merge
from a checkout that has another branch open (sd:2037).

On 2026-09-28 a lane held for one item by convention while other sessions'
prepares took the ship lock twice, and the lane could not merge that item from
its own checkout because merge read the checkout's branch. Real bare Git, real
CLI children and the shared GitHub double, as in `test_sd_ship`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sd_db import create_item
from sd_db import ship as receipts
from sd_db.testing.remote import _git

from tests import test_sd_lane as lane_suite
from tests import test_sd_ship as fixture
from tests.clean_env import clean_environment

ship = fixture.ship
ROOT = fixture.ROOT
sd_lane = lane_suite.sd_lane
lane_git = lane_suite.git


class LaneCase(unittest.TestCase):
    # Borrowed, not inherited: a subclass would run every `ShipCase` test again.
    setUp = fixture.ShipCase.setUp
    args = fixture.ShipCase.args
    operation = fixture.ShipCase.operation
    hold_ship_lock = fixture.ShipCase.hold_ship_lock
    amend_after_a_blocking_review = fixture.ShipCase.amend_after_a_blocking_review
    prepare = fixture.ShipCase.prepare

    def run_cli(self, *argv, cwd=None):
        completed = subprocess.run([sys.executable, str(ROOT / "bin/sd-ship"), *argv, "--json"],
                                   cwd=cwd or self.root, env=self.environment, text=True,
                                   capture_output=True, timeout=fixture.CLI_TIMEOUT)
        return completed.returncode, json.loads(completed.stdout)

    def dispatch(self, command, *extra, item=None, root=None):
        argv = [command, "--item", str(item or self.item), "--json", *extra]
        if command == "prepare":
            argv += ["--associate-only", "--title", "change"]
        return ship.dispatch(root or self.root, self.connection, self.database, ship.parser().parse_args(argv),
                             receipts, False)

    def head(self, root=None):
        return _git(root or self.root, "rev-parse", "HEAD")

    def puts(self):
        return [call for call in self.remote.calls if call.method == "PUT"]

    def other_item(self, branch=None):
        return create_item(self.connection, kind="work", title="another item", status="in_progress",
                           repo=str(self.operator), branch=branch)

    def hold_path(self):
        import sd_ship_hold
        return sd_ship_hold.hold_file(self.database, "fixture/repo")


class HeldLane(LaneCase):
    """sd:2035. A hold is the lock's reservation for one item, not a convention."""

    def test_a_hold_refuses_another_items_prepare_and_the_held_item_prepares_and_merges(self):
        code, held = self.run_cli("hold", "--item", str(self.item), "--holder", "pack lane")
        self.assertEqual(code, 0, held)
        self.assertEqual((held["hold"]["item"], held["hold"]["holder"]), (self.item, "pack lane"))
        other = self.other_item()
        with self.assertRaises(ship.Refusal) as refused:
            self.dispatch("prepare", item=other)
        self.assertEqual(refused.exception.workflow["blocker"]["code"], "lane_held")
        self.assertIn(f"held for sd:{self.item} by pack lane", str(refused.exception))
        self.assertEqual(self.remote.pull_requests, {})
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        merged = self.dispatch("merge", "--manual", "--expected-head", self.head())
        self.assertEqual(merged["phase"], "merged")
        # The merge that the hold was for ends it; nothing waits out the expiry.
        self.assertFalse(self.hold_path().exists())

    def test_a_hold_that_lands_while_a_merge_waits_for_the_lock_refuses_it_under_the_lock(self):
        """The check before the lock is an early answer; the one under it is the answer."""
        import sd_ship_hold
        other = self.other_item()
        lock = receipts.repository_lock

        @contextlib.contextmanager
        def hold_lands_first(database, repository, **options):
            sd_ship_hold.take(database, repository, self.item, window=60, holder="pack lane", command="test")
            with lock(database, repository, **options):
                yield

        with patch.object(receipts, "repository_lock", hold_lands_first), \
                patch.object(ship.Ship, "merge", side_effect=AssertionError("ran under a hold for another item")):
            with self.assertRaisesRegex(ship.Refusal, f"held for sd:{self.item}"):
                self.dispatch("merge", "--manual", "--expected-head", self.head(), item=other)

    def test_a_hold_refuses_another_items_merge_before_any_merge_call(self):
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        other = self.other_item()
        code, held = self.run_cli("hold", "--item", str(other))
        self.assertEqual(code, 0, held)
        with self.assertRaisesRegex(ship.Refusal, f"held for sd:{other}"):
            self.dispatch("merge", "--manual", "--expected-head", self.head())
        self.assertEqual(self.puts(), [])

    def test_the_cli_refusal_names_the_holder_and_exits_3(self):
        self.assertEqual(self.run_cli("hold", "--item", str(self.item), "--holder", "pack lane")[0], 0)
        other = self.other_item()
        code, refused = self.run_cli("prepare", "--item", str(other), "--associate-only", "--title", "change")
        self.assertEqual(code, 3)
        self.assertEqual(refused["workflow"]["blocker"]["code"], "lane_held")
        self.assertIn(f"sd:{self.item} by pack lane until ", refused["error"])

    def test_a_second_hold_refuses_and_the_same_item_renews(self):
        self.assertEqual(self.run_cli("hold", "--item", str(self.item), "--for", "60")[0], 0)
        first = json.loads(self.hold_path().read_text())
        other = self.other_item()
        code, refused = self.run_cli("hold", "--item", str(other))
        self.assertEqual(code, 3)
        self.assertEqual(refused["workflow"]["blocker"]["code"], "lane_held")
        code, renewed = self.run_cli("hold", "--item", str(self.item), "--for", "600")
        self.assertEqual(code, 0, renewed)
        self.assertGreater(renewed["hold"]["expires_at"], first["expires_at"])

    def test_an_expired_hold_holds_nothing(self):
        self.assertEqual(self.run_cli("hold", "--item", str(self.item))[0], 0)
        record = json.loads(self.hold_path().read_text())
        record["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.hold_path().write_text(json.dumps(record))
        other = self.other_item()
        code, held = self.run_cli("hold", "--item", str(other))
        self.assertEqual(code, 0, held)
        self.assertEqual(held["hold"]["item"], other)

    def test_release_is_the_holders_alone(self):
        self.assertEqual(self.run_cli("hold", "--item", str(self.item))[0], 0)
        other = self.other_item()
        code, refused = self.run_cli("release", "--item", str(other))
        self.assertEqual(code, 3)
        self.assertTrue(self.hold_path().exists())
        code, released = self.run_cli("release", "--item", str(self.item))
        self.assertEqual(code, 0, released)
        self.assertEqual(released["released"]["item"], self.item)
        self.assertFalse(self.hold_path().exists())
        self.assertEqual(self.dispatch("prepare", item=other)["phase"], "ready_to_send")

    def test_a_hold_takes_the_ship_lock(self):
        self.hold_ship_lock("fixture/repo")
        code, refused = self.run_cli("hold", "--item", str(self.item))
        self.assertEqual(code, 3)
        self.assertIn("another ship operation owns this repository", refused["error"])
        self.assertFalse(self.hold_path().exists())

    def test_the_hold_window_is_bounded(self):
        self.assertEqual(ship.parser().parse_args(["hold", "--item", "1", "--for", "86400"]).hold_seconds, 86400)
        for value in ("0", "-5", "86401", "soon"):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                ship.parser().parse_args(["hold", "--item", "1", "--for", value])


class SatellitePrepare(LaneCase):
    """sd:2679. Over a remote connection prepare binds the pull request and writes
    the ship: row without the ship lock; merge refuses before it reads a row (sd:3003)."""

    HUB = "hub.example.test:8769"

    def setUp(self):
        LaneCase.setUp(self)
        self.entered = []

        @contextlib.contextmanager
        def lock_on_a_satellite(database, repository, **options):
            # What `repository_lock` does over the wire.
            self.entered.append(repository)
            raise ship.Refusal(f"the sd-ship repository lock runs on the sd hub only; this machine reaches "
                               f"the database on {self.HUB}. Run it on the hub")
            yield

        def served_by(target, home=None):
            return self.HUB if str(target) == str(self.database) else None

        for patcher in (patch.object(receipts, "repository_lock", lock_on_a_satellite),
                        patch("sd_db.database.served_by", served_by), patch.object(receipts, "served_by", served_by)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_prepare_binds_the_pull_request_and_writes_the_ship_row_without_the_lock(self):
        prepared = self.dispatch("prepare")
        self.assertEqual(prepared["phase"], "ready_to_send")
        self.assertEqual(self.entered, [])
        number = prepared["pull_request"]["number"]
        self.assertIn(number, self.remote.pull_requests)
        key = receipts.receipt_key("fixture/repo", "topic", self.item)
        self.assertTrue(key.startswith("ship:"))
        row = receipts.read(self.connection, key)[1]
        self.assertEqual((row["phase"], row["pull_request"]["number"]), ("ready_to_send", number))
        self.assertEqual((row["invoker"]["lock_holder"], row["invoker"]["served_by"]), (None, self.HUB))

    def test_a_hold_for_another_item_refuses_the_lock_free_prepare(self):
        """sd:1938. The hold is read off the lane host too, before anything is reviewed or pushed."""
        import sd_ship_hold
        sd_ship_hold.take(self.database, "fixture/repo", self.other_item(), window=60, holder="pack lane", command="test")
        with patch.object(ship.Ship, "review", side_effect=AssertionError("reviewed under a hold for another item")), \
                self.assertRaises(ship.Refusal) as refused:
            self.dispatch("prepare")
        self.assertEqual(refused.exception.workflow["blocker"]["code"], "lane_held")
        self.assertEqual((self.entered, self.remote.pull_requests), ([], {}))

    def test_merge_refuses_before_it_reads_a_row(self):
        """sd:2795 (sd:2782 L3): merge used to read the ship: and hold rows, then meet HubOnly at the lock."""
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        with patch.object(ship, "Ship", side_effect=AssertionError("read the ship: row")), \
                patch.object(ship.sd_ship_hold, "refuse_other", side_effect=AssertionError("read the hold")), \
                self.assertRaisesRegex(ship.Refusal, "The lane for fixture/repo runs on the hub, not on this machine") as refused:
            self.dispatch("merge", "--manual", "--expected-head", self.head())
        self.assertEqual(refused.exception.workflow["blocker"]["code"], "lane_elsewhere")
        self.assertEqual(self.entered, [])
        self.assertEqual(self.puts(), [])

    def test_a_merged_records_prepare_reconciles_on_the_hub_only(self):
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        key = receipts.receipt_key("fixture/repo", "topic", self.item)
        revision, row = receipts.read(self.connection, key)
        receipts.save(self.connection, key, revision, {**row, "phase": "merged"})
        with self.assertRaisesRegex(ship.Refusal, "runs on the sd hub only"):
            self.dispatch("prepare")
        self.assertEqual(self.entered, ["fixture/repo"])


class LockFreePrepare(LaneCase):
    """sd:1938. Prepare takes no ship lock; a reserved pass names its process, and a second prepare reads it.

    Failure table: two prepares before review, one loses at the revision check; a second prepare during a
    live review refuses naming the pid; a dead or reused pid lets the retry run; another host's pid counts as live.
    """

    def receipt(self):
        return receipts.read(self.connection, receipts.receipt_key("fixture/repo", "topic", self.item))[1]

    def during_review(self, step, planning=False):
        """Patch the reviewer so `step` runs once while the provider pass runs, its pass reserved; `step`'s answers.

        With `planning`, `step` runs during `--explain` instead, before anything is reserved.
        """
        real, answers = ship.review_process, []

        def process(root, argv, **kwargs):
            if ("--explain" in argv) == planning and not answers:
                answers.append(None)
                try:
                    answers[0] = step()
                except ship.Refusal as refusal:
                    answers[0] = refusal
            return real(root, argv, **kwargs)

        return patch.object(ship, "review_process", process), answers

    def dead_pid(self):
        child = subprocess.Popen(["true"], env=clean_environment())
        child.wait()
        return child.pid

    def test_a_second_prepare_during_a_live_review_refuses_naming_its_pid(self):
        patcher, answers = self.during_review(lambda: self.operation("prepare", "--retry-review").prepare())
        with patcher:
            first = self.operation("prepare").prepare()
        (second,) = answers
        self.assertIsInstance(second, ship.Refusal)
        self.assertEqual(second.workflow["blocker"]["code"], "review_running")
        self.assertIn(f"pid {os.getpid()} on {socket.gethostname()} is still reviewing", str(second))
        self.assertEqual(first["phase"], "ready_to_send")
        self.assertEqual(len(self.receipt()["passes"]), 1)

    def test_a_dead_reviewers_pass_takes_the_one_retry(self):
        class Killed(Exception):
            pass

        def killed():
            raise Killed

        patcher, _ = self.during_review(killed)
        with patcher, self.assertRaises(Killed):
            self.operation("prepare").prepare()
        key = receipts.receipt_key("fixture/repo", "topic", self.item)
        revision, row = receipts.read(self.connection, key)
        self.assertEqual((row["phase"], row["passes"][-1]["process"]["pid"]), ("reviewing", os.getpid()))
        row["passes"][-1]["process"]["pid"] = self.dead_pid()
        receipts.save(self.connection, key, revision, row)
        with self.assertRaises(ship.Refusal) as refused:
            self.operation("prepare").prepare()
        self.assertEqual(refused.exception.workflow["blocker"]["code"], "review_incomplete")
        self.assertEqual(self.operation("prepare", "--retry-review").prepare()["phase"], "ready_to_send")
        self.assertEqual([entry["retry"] for entry in self.receipt()["passes"]], [False, True])

    def test_a_reused_pid_reads_dead_and_another_hosts_reads_live(self):
        child = subprocess.Popen(["sleep", "60"], env=clean_environment())
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        now = datetime.now(timezone.utc)
        reviewing, here = {"phase": "reviewing"}, socket.gethostname()

        def reserved(pid, started=now, host=here, deadline=now + timedelta(hours=1), **entry):
            process = {"pid": pid, "host": host, "execution_seconds": 3600, "deadline": deadline.isoformat()}
            return [{"head": "0" * 40, "started_at": started.isoformat(), "process": process, **entry}]

        live = fixture.sd_ship_review.live_reviewer
        self.assertEqual(live(reviewing, reserved(child.pid))["pid"], child.pid)
        self.assertIsNone(live(reviewing, reserved(child.pid, started=now - timedelta(hours=1))), "a reused pid")
        self.assertIsNone(live(reviewing, reserved(self.dead_pid())))
        self.assertEqual(live(reviewing, reserved(self.dead_pid(), host="satellite.example.test"))["host"],
                         "satellite.example.test")
        self.assertIsNone(live({"phase": "reviewed"}, reserved(child.pid)))
        self.assertIsNone(live(reviewing, reserved(child.pid, report={})))
        self.assertIsNone(live(reviewing, reserved(child.pid, execution_error={"kind": "watchdog_expired"})))
        self.assertIsNone(live(reviewing, [{"head": "0" * 40, "started_at": now.isoformat()}]), "a pass before sd:1938")
        past = now - timedelta(seconds=1)
        self.assertIsNone(live(reviewing, reserved(child.pid, host="satellite.example.test", deadline=past)))
        self.assertIsNone(live(reviewing, reserved(child.pid, deadline=past)), "the deadline backs up a live pid")
        without = reserved(child.pid, host="satellite.example.test")
        del without[0]["process"]["deadline"]
        self.assertIsNone(live(reviewing, without), "a reservation with no deadline holds nothing")

    def remote_reservation(self, head, deadline):
        """Leave the record mid-review, its pass reserved until `deadline` by a process on another machine."""
        key = receipts.receipt_key("fixture/repo", "topic", self.item)
        revision, row = receipts.read(self.connection, key)
        process = {"pid": 1, "host": "satellite.example.test", "execution_seconds": 3600, "deadline": deadline.isoformat()}
        row["passes"].append({"head": head, "started_at": datetime.now(timezone.utc).isoformat(), "base": None,
                              "retry": False, "requested_provider": None, "process": process})
        receipts.save(self.connection, key, revision, {**row, "phase": "reviewing", "reviewed_head": None})

    def remote_reservation_expires(self):
        """Move the reserved pass's deadline into the past."""
        key = receipts.receipt_key("fixture/repo", "topic", self.item)
        revision, row = receipts.read(self.connection, key)
        row["passes"][-1]["process"]["deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        receipts.save(self.connection, key, revision, row)

    def test_a_remote_reservation_refuses_within_its_bound_and_expires_past_it(self):
        """sd:1938 review: a satellite that died mid-review blocks the item until its pass's bound, no longer."""
        self.assertEqual(self.operation("prepare").prepare()["phase"], "ready_to_send")
        _git(self.root, "commit", "-q", "--allow-empty", "-m", "fix\n\nAuthored-with: human")
        self.remote_reservation(self.head(), datetime.now(timezone.utc) + timedelta(hours=1))
        with self.assertRaises(ship.Refusal) as refused:
            self.operation("prepare", "--retry-review").prepare()
        self.assertEqual(refused.exception.workflow["blocker"]["code"], "review_running")
        self.assertIn("pid 1 on satellite.example.test", str(refused.exception))
        self.remote_reservation_expires()
        self.assertEqual(self.operation("prepare", "--retry-review").prepare()["phase"], "ready_to_send")

    def test_a_reservation_holds_through_its_execution_bound_however_long_planning_took(self):
        """sd:1938 round 2: planning ran 790 s, and 100 s of the execution watchdog remain; the pass still reads live.

        The pass's `started_at` is taken before planning, the watchdog's clock starts at the reservation's
        save. A bound counted from `started_at` expired while the reviewer ran. A clock moved by `offset`
        stands in for the time; the second prepare runs on another machine, so only the bound can answer.
        """
        offset, real, bound = [-790.0], ship.review_process, []

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) + timedelta(seconds=offset[0])

        def second():
            with patch("socket.gethostname", return_value="lane.example.test"):
                return self.operation("prepare", "--retry-review").prepare()

        def process(root, argv, **kwargs):
            if "--explain" in argv:
                planned = real(root, argv, **kwargs)
                bound.append(json.loads(planned.stdout)["timing"]["execution_seconds"])
                offset[0] = 0.0  # planning is over: the reservation is saved now
                return planned
            if len(bound) == 1:
                offset[0] = bound[0] - 100.0
                try:
                    bound.append(second())
                except ship.Refusal as refusal:
                    bound.append(refusal)
            return real(root, argv, **kwargs)

        with patch.object(ship, "review_process", process), patch.object(fixture.sd_ship_review, "datetime", Clock), \
                patch.object(ship, "moment", lambda: Clock.now(timezone.utc).isoformat()):
            first = self.operation("prepare").prepare()
        refusal = bound[1]
        self.assertIsInstance(refusal, ship.Refusal)
        self.assertEqual(refusal.workflow["blocker"]["code"], "review_running")
        self.assertEqual(first["phase"], "ready_to_send")
        self.assertEqual(len(self.receipt()["passes"]), 1)

    def test_a_second_prepare_during_planning_wins_and_the_first_loses_at_its_reservation(self):
        """Planning reserves nothing, so the revision check settles it: one pass, no lost receipt."""
        patcher, answers = self.during_review(lambda: self.operation("prepare").prepare(), planning=True)
        with patcher, self.assertRaisesRegex(Exception, "changed concurrently"):
            self.operation("prepare").prepare()
        self.assertEqual(answers[0]["phase"], "ready_to_send")
        self.assertEqual(len(self.receipt()["passes"]), 1)

    def test_restart_review_sets_aside_a_pass_that_still_reads_live(self):
        """sd:1938 review: `--restart-review REASON` is the operator's word, so the live-review guard yields to it."""
        reviewed, amended, payload, program = self.amend_after_a_blocking_review()
        self.remote_reservation(reviewed, datetime.now(timezone.utc) + timedelta(hours=1))
        with self.assertRaises(ship.Refusal) as refused:
            self.operation("prepare").prepare()
        self.assertEqual(refused.exception.workflow["blocker"]["code"], "review_running")
        payload["structured_output"]["findings"] = []
        program.write_text("#!/usr/bin/env python3\nimport json\nprint(" + repr(json.dumps(payload)) + ")\n")
        prepared = self.operation("prepare", "--restart-review", "satellite died mid-review").prepare()
        self.assertEqual(prepared["reviewed_head"], amended)
        self.assertEqual([entry["head"] for entry in self.receipt()["passes"]], [amended])

    def test_a_prepare_in_review_holds_no_lock_so_another_items_lane_step_runs(self):
        """The point of sd:1938: a hand prepare's review no longer refuses the lane for its whole run.

        The lane's step here is `hold` for another item, which takes the same ship lock a lane merge takes.
        The hold lands mid-prepare, so this item's merge then refuses the held lane.
        """
        other = self.other_item()
        patcher, answers = self.during_review(lambda: (receipts.held_locks(self.database),
                                                       self.run_cli("hold", "--item", str(other), "--holder", "pack lane")))
        with patcher:
            prepared = self.dispatch("prepare")
        ((locks, (code, held)),) = answers
        self.assertEqual((locks, code), ([], 0), held)
        self.assertEqual(held["hold"]["item"], other)
        self.assertEqual((prepared["phase"], prepared["invoker"]["lock_holder"]), ("ready_to_send", None))
        with self.assertRaisesRegex(ship.Refusal, f"held for sd:{other}"):
            self.dispatch("merge", "--manual", "--expected-head", self.head())
        self.assertEqual(self.puts(), [])

    def test_a_merged_records_prepare_still_reconciles_under_the_lock(self):
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        key = receipts.receipt_key("fixture/repo", "topic", self.item)
        revision, row = receipts.read(self.connection, key)
        receipts.save(self.connection, key, revision, {**row, "phase": "merged"})
        entered, lock = [], receipts.repository_lock

        @contextlib.contextmanager
        def recording(database, repository, **options):
            entered.append(repository)
            with lock(database, repository, **options):
                yield

        with patch.object(receipts, "repository_lock", recording), \
                patch.object(ship.Ship, "reconcile", return_value={"ok": True, "phase": "merged"}):
            self.dispatch("prepare")
        self.assertEqual(entered, ["fixture/repo"])

    def test_two_prepares_before_review_one_loses_at_the_revision_check(self):
        first, second = self.operation("prepare"), self.operation("prepare")
        self.assertEqual(second.prepare()["phase"], "ready_to_send")
        with self.assertRaisesRegex(Exception, "changed concurrently"):
            first.prepare()
        self.assertEqual(len(self.receipt()["passes"]), 1)


class LaneHost(LaneCase):
    """sd:3003, acceptance 8 to 10: `dispatch` asks `hosts_lane`, not whether a hub serves the database."""

    HUB = "hub.example.test:8769"

    def lane_host(self, host):
        self.connection.execute("UPDATE repo SET lane_host = ?", (host,))
        self.connection.commit()

    def on_a_satellite(self, host=None):
        """`served_by` names a hub wherever `sd_db` reads it; `host` is this machine's name."""
        def served_by(target, home=None):
            return self.HUB if str(target) == str(self.database) else None
        stack = contextlib.ExitStack()
        stack.enter_context(patch("sd_db.database.served_by", served_by))
        stack.enter_context(patch.object(receipts, "served_by", served_by))
        if host is not None:
            stack.enter_context(patch.object(receipts, "this_host", lambda: host))
        return stack

    def rows(self):
        return self.connection.execute("SELECT id, key, body FROM state ORDER BY id").fetchall()

    def test_off_the_host_merge_and_a_no_item_verb_refuse_before_any_row_changes(self):
        """Acceptance 8, on the hub with the lane on build-2 and on a satellite with it on the hub."""
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        before = self.rows()
        no_item = ["review", "--no-item", "--create-record", "--assert-new-work", "--json"]
        for machine, host, context in (("the hub", "build-2", contextlib.nullcontext), ("a satellite", None, self.on_a_satellite)):
            self.lane_host(host)
            for argv in (["merge", "--item", str(self.item), "--manual", "--expected-head", self.head(), "--json"], no_item):
                with self.subTest(machine=machine, verb=argv[0]), context(), \
                        patch.object(ship, "Ship", side_effect=AssertionError("read the ship: row")), \
                        self.assertRaises(ship.Refusal) as refused:
                    ship.dispatch(self.root, self.connection, self.database, ship.parser().parse_args(argv), receipts, False)
                self.assertEqual(refused.exception.workflow["blocker"]["code"], "lane_elsewhere")
                self.assertIn(f"runs on {host or 'the hub'}, not on this machine", str(refused.exception))
        self.assertEqual((self.rows(), self.puts()), (before, []))

    def test_on_a_satellite_that_hosts_the_lane_merge_merges(self):
        """Acceptance 9: the satellite host takes its own ship lock, under its state folder, and merges."""
        state = self.directory / "state"
        self.lane_host("build-2")
        with self.on_a_satellite(host="build-2"), patch.dict("os.environ", {"XDG_STATE_HOME": str(state)}):
            prepared = self.dispatch("prepare")
            self.assertEqual(prepared["phase"], "ready_to_send")
            self.assertIsNone(prepared["invoker"]["lock_holder"])  # no prepare holds the lock (sd:1938)
            merged = self.dispatch("merge", "--manual", "--expected-head", self.head())
        self.assertEqual(merged["phase"], "merged")
        self.assertEqual(len(list((state / "sd" / receipts.LOCK_DIRECTORY).glob("*.lock"))), 1)
        self.assertFalse((self.database.parent / receipts.LOCK_DIRECTORY).exists())

    def test_on_the_hub_a_lane_hosted_elsewhere_prepares_without_the_lock(self):
        """Acceptance 10: the hub prepares lock-free, and its save is checked against the row's revision."""
        self.lane_host("build-2")
        with patch.object(receipts, "repository_lock", side_effect=AssertionError("took the ship lock")):
            prepared = self.dispatch("prepare")
        self.assertEqual(prepared["phase"], "ready_to_send")
        key = receipts.receipt_key("fixture/repo", "topic", self.item)
        revision, row = receipts.read(self.connection, key)
        self.assertEqual((row["phase"], row["invoker"]["lock_holder"], row["invoker"].get("served_by")),
                         ("ready_to_send", None, None))
        with self.assertRaisesRegex(Exception, "changed concurrently"):
            receipts.save(self.connection, key, revision - 1, {**row, "phase": "stale"})
        self.assertEqual(receipts.read(self.connection, key)[0], revision)

    def test_clones_that_disagree_refuse_lane_unknown_and_prepare_takes_no_side(self):
        """Unknown ownership refuses; it never falls back to the hub or to a lock-free prepare."""
        clone = self.directory / "clone-2"
        fixture.upsert_repo(self.connection, str(clone), remote=self.remote_url, managed=1)
        self.connection.execute("UPDATE repo SET lane_host = 'build-2' WHERE path = ?", (str(clone),))
        self.connection.commit()
        for command in ("prepare", "merge"):
            with self.subTest(command=command), patch.object(ship, "Ship", side_effect=AssertionError("read a row")), \
                    self.assertRaises(ship.Refusal) as refused:
                self.dispatch(command, *(["--manual", "--expected-head", self.head()] if command == "merge" else []))
            self.assertEqual(refused.exception.workflow["blocker"]["code"], "lane_unknown")
            self.assertIn("name different lane hosts", str(refused.exception))
        self.assertEqual(self.remote.pull_requests, {})

    def test_a_move_after_dispatch_reads_the_host_is_refused_at_the_lock(self):
        """The lock reads the host again; dispatch's answer is an early refusal, not the authority."""
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        self.lane_host("build-2")
        with patch.object(ship.sd_lib, "lane_elsewhere", lambda connection, database, repository: None), \
                self.assertRaisesRegex(receipts.LaneElsewhere, "runs on build-2"):
            self.dispatch("merge", "--manual", "--expected-head", self.head())
        self.assertEqual(self.puts(), [])

    def test_an_sd_db_without_hosts_lane_hosts_every_lane_on_the_hub_only(self):
        for served, hosted in ((None, True), (self.HUB, False)):
            with self.subTest(served=served), patch.dict(receipts.__dict__), \
                    patch("sd_db.database.served_by", lambda target, home=None, served=served: served):
                del receipts.__dict__["hosts_lane"]
                self.assertIs(ship.sd_lib.hosts_lane(self.connection, self.database, "fixture/repo"), hosted)

    def test_a_fresh_process_refuses_off_the_host(self):
        """A fresh `sd-ship` has not imported `sd_db.ship`; that must not read as a library without `hosts_lane`."""
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        self.lane_host("build-2")
        for argv, code in ((["lane", "run"], lambda answer: answer["code"]),
                           (["merge", "--item", str(self.item), "--manual", "--expected-head", self.head(), "--json"],
                            lambda answer: answer["workflow"]["blocker"]["code"])):
            with self.subTest(verb=argv[0]):
                completed = subprocess.run([sys.executable, str(ROOT / "bin/sd-ship"), *argv], cwd=self.root,
                                           env=self.environment, text=True, capture_output=True,
                                           timeout=fixture.CLI_TIMEOUT)
                answer = json.loads(completed.stdout)
                self.assertEqual((completed.returncode, code(answer)), (3, "lane_elsewhere"), completed.stderr)
                self.assertIn("runs on build-2, not on this machine", answer["error"])
        self.assertEqual(self.puts(), [])


class RetiredHandOff(unittest.TestCase):
    """sd:3003, acceptance 14: with a lane host per repository, no verb hands an item from a satellite to the hub."""

    def test_the_hand_off_verbs_are_unknown_arguments(self):
        for argv in (["lane", "request", "--item", "7"], ["lane", "run", "--satellite-only"],
                     ["merge", "--item", "7", "--expected-head", "a" * 40, "--satellite-gate"]):
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()) as said, self.assertRaises(SystemExit) as raised:
                    ship.parser().parse_args(argv)
                self.assertEqual(raised.exception.code, 2)
                self.assertRegex(said.getvalue(), "invalid choice: 'request'|unrecognized arguments: --sat")


class MergeFromTheLane(LaneCase):
    """sd:2037. Merge resolves the item's branch from its receipt, not from the checkout."""

    def setUp(self):
        LaneCase.setUp(self)
        # The lane's own checkout of the same repository, on the default
        # branch; the item's branch stays open in the author's checkout.
        self.lane = self.directory / "lane"
        _git(self.root, "worktree", "add", "-q", str(self.lane), "main")

    def test_merge_from_a_checkout_on_another_branch_uses_the_receipt(self):
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        head, lane_head = self.head(), self.head(self.lane)
        merged = self.dispatch("merge", "--manual", "--expected-head", head, root=self.lane)
        self.assertEqual(merged["phase"], "merged")
        self.assertEqual([call.body["sha"] for call in self.puts()], [head])
        # Neither checkout moved: the lane fetched the branch, it switched nothing.
        self.assertEqual(_git(self.lane, "branch", "--show-current"), "main")
        self.assertEqual(self.head(self.lane), lane_head)
        self.assertEqual((_git(self.root, "branch", "--show-current"), self.head()), ("topic", head))

    def test_the_expected_head_is_enforced_from_the_lane(self):
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        with self.assertRaisesRegex(ship.Refusal, "--expected-head must name the current exact reviewed commit"):
            self.dispatch("merge", "--manual", "--expected-head", self.head(self.lane), root=self.lane)
        self.assertEqual(self.puts(), [])

    def test_the_branch_tip_on_origin_is_the_head_checked(self):
        """The author's checkout is not read: a push past the reviewed head refuses the merge."""
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        head = self.head()
        self.remote.commit_on("topic", "raced\n\nAuthored-with: human", files={"raced.py": "changed\n"})
        with self.assertRaisesRegex(ship.Refusal, "--expected-head must name the current exact reviewed commit"):
            self.dispatch("merge", "--manual", "--expected-head", head, root=self.lane)
        self.assertEqual(self.puts(), [])

    def test_branch_names_the_receipt_when_the_item_has_none(self):
        self.connection.execute("UPDATE item SET branch = NULL WHERE id = ?", (self.item,))
        self.connection.commit()
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        # A second receipt for the item makes the receipt lookup ambiguous.
        key = receipts.receipt_key("fixture/repo", "later", self.item)
        receipts.save(self.connection, key, 0, {"repository": "fixture/repo", "branch": "later", "item": self.item})
        with self.assertRaisesRegex(ship.Refusal, "--branch") as refused:
            self.dispatch("merge", "--manual", "--expected-head", self.head(), root=self.lane)
        self.assertEqual(refused.exception.workflow["blocker"]["code"], "prepare_required")
        merged = self.dispatch("merge", "--manual", "--expected-head", self.head(), "--branch", "topic", root=self.lane)
        self.assertEqual(merged["phase"], "merged")

    def test_the_cli_merges_from_the_lane_with_c(self):
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        code, merged = self.run_cli("-C", str(self.lane), "merge", "--item", str(self.item), "--manual",
                                    "--expected-head", self.head(), cwd=self.directory)
        self.assertEqual(code, 0, merged)
        self.assertEqual(merged["phase"], "merged")


if __name__ == "__main__":
    unittest.main()
