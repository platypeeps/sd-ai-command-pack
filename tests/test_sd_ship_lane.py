"""The merge lane: a hold on the repository's ship lock (sd:2035), and a merge
from a checkout that has another branch open (sd:2037).

On 2026-09-28 a lane held for one item by convention while other sessions'
prepares took the ship lock twice, and the lane could not merge that item from
its own checkout because merge read the checkout's branch. Real bare Git, real
CLI children and the shared GitHub double, as in `test_sd_ship`.
"""

from __future__ import annotations

import contextlib
import json
import shlex
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sd_db import create_item
from sd_db import ship as receipts
from sd_db.testing.remote import _git

from tests import test_sd_lane_requests as requests_suite
from tests import test_sd_ship as fixture

ship = fixture.ship
ROOT = fixture.ROOT
sd_lane = requests_suite.sd_lane
lane_git = requests_suite.git


class LaneCase(unittest.TestCase):
    # Borrowed, not inherited: a subclass would run every `ShipCase` test again.
    setUp = fixture.ShipCase.setUp
    args = fixture.ShipCase.args
    operation = fixture.ShipCase.operation
    hold_ship_lock = fixture.ShipCase.hold_ship_lock

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

    def test_a_hold_that_lands_while_a_prepare_waits_for_the_lock_refuses_it_under_the_lock(self):
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
                patch.object(ship.Ship, "prepare", side_effect=AssertionError("ran under a hold for another item")):
            with self.assertRaisesRegex(ship.Refusal, f"held for sd:{self.item}"):
                self.dispatch("prepare", item=other)

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
    the ship: row without the ship lock; merge still meets the lock's HubOnly."""

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

        # `create=True`: the pinned sd_db predates `served_by`.
        for patcher in (patch.object(receipts, "repository_lock", lock_on_a_satellite),
                        patch("sd_db.database.served_by", served_by, create=True)):
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

    def test_merge_still_refuses_at_the_lock(self):
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        with self.assertRaisesRegex(ship.Refusal, "runs on the sd hub only"):
            self.dispatch("merge", "--manual", "--expected-head", self.head())
        self.assertEqual(self.entered, ["fixture/repo"])
        self.assertEqual(self.puts(), [])

    def test_a_merged_records_prepare_reconciles_on_the_hub_only(self):
        self.assertEqual(self.dispatch("prepare")["phase"], "ready_to_send")
        key = receipts.receipt_key("fixture/repo", "topic", self.item)
        revision, row = receipts.read(self.connection, key)
        receipts.save(self.connection, key, revision, {**row, "phase": "merged"})
        with self.assertRaisesRegex(ship.Refusal, "runs on the sd hub only"):
            self.dispatch("prepare")
        self.assertEqual(self.entered, ["fixture/repo"])


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


class SatelliteEntry(requests_suite.Requests):
    """sd:2704 step 7. A satellite entry runs no prepare and no catch-up: fetch, head and base checks,
    then one `merge --satellite-gate`; `sd-ship` is the lane suite's recorder."""

    def setUp(self):
        super().setUp()
        self.prepared()
        self.ask()
        requests_suite.sd_lane.intake(self.hub, self.path)

    def run_lane(self, ship=None, **options):
        return sd_lane.run_lane(self.repo, self.environ, ship or self.ship, self.gate, **{"hub": self.hub, **options})

    def advance(self, branch: str) -> str:
        """Another machine pushes to `branch` on origin."""
        other = self.tmp / f"other-{branch}"
        if not other.exists():
            subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True)
        lane_git(other, "fetch", "-q", "origin")
        lane_git(other, "checkout", "-q", "-B", branch, f"origin/{branch}")
        lane_git(other, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
        lane_git(other, "push", "-q", "origin", branch)
        return lane_git(other, "rev-parse", "HEAD")

    def remote_branches(self):
        return lane_git(self.origin, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()

    def test_a_satellite_entry_merges_with_its_receipt_and_no_prepare_or_catch_up(self):
        self.run_lane()
        [merge] = self.calls
        self.assertEqual(merge, sd_lane.satellite_merge_argv(self.entries()[0]))
        self.assertNotIn("prepare", merge)
        self.assertNotIn("--catch-up", merge)
        for flag, value in (("--branch", "topic"), ("--expected-head", self.head), ("-C", str(self.repo))):
            self.assertEqual(merge[merge.index(flag) + 1], value)
        self.assertIn("--satellite-gate", merge)
        entry, row = self.entries()[0], self.row()
        self.assertEqual((entry["status"], entry["request_row"]), ("merged", "written"))
        self.assertEqual((row["status"], row["merge_commit"]), ("merged", "merged-7"))

    def test_a_moved_base_hands_back_with_no_merge_call(self):
        from sd_local_gate import HAND_BACK  # noqa: PLC0415

        self.advance("main")
        self.run_lane()
        self.assertEqual(self.calls, [])
        entry, row = self.entries()[0], self.row()
        self.assertEqual((entry["status"], entry["code"]), ("handed_back", "base_moved"))
        self.assertEqual((row["status"], row["code"], row["next_action"]),
                         ("handed_back", "base_moved", HAND_BACK.format(base="main")))
        [(item, body, _)] = self.notes
        self.assertEqual(item, 7)
        self.assertIn("handed_back (base_moved)", body)
        self.assertIn("sd-ship lane request again", body)

    def test_a_moved_branch_hands_back_with_no_merge_call(self):
        self.advance("topic")
        self.run_lane()
        self.assertEqual(self.calls, [])
        self.assertEqual((self.entries()[0]["code"], self.row()["status"]), ("head_moved", "handed_back"))

    def test_a_satellite_refusal_from_merge_hands_back_and_another_fails(self):
        for code, status in (("satellite_pack_mismatch", "handed_back"), ("base_moved", "handed_back"),
                             ("checks_failed", "failed")):
            with self.subTest(code=code):
                self.answers[(7, "merge")] = {"ok": False, "error": f"refused: {code}", "workflow": {
                    "blocker": {"code": code}, "next_action": "the merge's own next step"}}
                if self.entries()[-1]["status"] != "pending":
                    self.ask()
                    requests_suite.sd_lane.intake(self.hub, self.path)
                self.run_lane()
                entry, row = self.entries()[-1], self.row()
                self.assertEqual((entry["status"], entry["code"], row["status"]), (status, code, status))
                self.assertIn(f"Lane: {status} ({code})", self.notes[-1][1])
                if code == "satellite_pack_mismatch":  # the trust rule's own next action, not the generic hand-back
                    self.assertTrue(row["next_action"].startswith("Bring the satellite's pack checkout"), row["next_action"])

    def test_no_speculative_gate_starts_for_a_satellite_follower(self):
        hub_tree = self.worktree("hubitem")
        sd_lane.enqueue_entry(hub_tree, 3, "hub item", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.move(self.repo, 3, "top", self.environ)
        self.run_lane()
        self.assertEqual(self.gates, [])
        satellite = next(entry for entry in self.entries() if entry["item"] == 7)
        self.assertEqual(satellite["status"], "merged")
        self.assertNotIn("speculation", satellite)

    def test_the_remote_branch_is_deleted_at_the_merged_head_only(self):
        self.run_lane()
        self.assertEqual(self.remote_branches(), ["main"])
        self.assertIn("removed origin/topic", self.entries()[0]["cleanup"])
        self.assertIsNone(self.entries()[0]["remove"])

    def test_a_remote_branch_pushed_past_the_merged_head_is_kept(self):
        ship = self.ship

        def push_during_merge(argv, log):
            self.advance("topic")
            return ship(argv, log)
        self.run_lane(push_during_merge)
        self.assertEqual(self.remote_branches(), ["main", "topic"])
        self.assertIn("origin/topic kept: it is at", self.entries()[0]["cleanup"])

    def test_a_request_without_manual_stops_before_the_merge(self):
        self.ask(authority=None)
        requests_suite.sd_lane.intake(self.hub, self.path)
        self.run_lane()
        self.assertEqual(self.calls, [])
        entry = self.entries()[-1]
        self.assertEqual((entry["status"], self.row()["status"]), ("prepared", "prepared"))
        self.assertIn("--satellite-gate", entry["next_action"])

    def test_the_hand_merge_command_is_quoted_for_a_shell(self):
        """Prepare review at 9cbbbec5: a path with a space or a branch with `;` broke the copied command."""
        entry = {"worktree": "/hub/my pack", "item": 7, "branch": "topic;echo", "expected_head": self.head}
        command = sd_lane.hand_merge(entry).removeprefix("On the hub: ")
        self.assertEqual(shlex.split(command), ["sd-ship", "-C", "/hub/my pack", "merge", "--item", "7", "--branch",
                                                "topic;echo", "--expected-head", self.head, "--manual",
                                                "--satellite-gate"])

    def test_a_request_replaced_while_intake_decides_does_not_run_on_the_old_authority(self):
        """Review round 5: the satellite asked again without --manual; the queued entry kept `manual` and merged."""
        self.ask()
        raced: list[int] = []

        def satellite_asks_again(connection, key, previous, value):
            if value.get("status") == "queued" and not raced:
                raced.append(self.ask(authority=None))
            return receipts.save(connection, key, previous, value)
        store = requests_suite.types.SimpleNamespace(read=receipts.read, receipt_key=receipts.receipt_key,
                                                     save=satellite_asks_again)
        self.run_lane(hub=sd_lane.Hub(self.connection, store, requests_suite.SLUG, self.repo))
        self.assertEqual((self.calls, self.entries()[-1]["status"], self.row()["status"]), ([], "pending", "requested"))
        self.run_lane()  # the newer request decides: no --manual, so no merge
        self.assertEqual(self.entries()[-2]["superseded_by"]["revision"], raced[0])
        self.assertEqual((self.calls, self.entries()[-1]["status"]), ([], "prepared"))

    def test_a_replaced_request_whose_row_cannot_be_read_again_is_not_claimed(self):
        """Prepare review at 63bc828e: the conflict's recovery read failed, so the manual entry stayed claimable."""
        self.ask()
        raced: list[int] = []

        def satellite_asks_again(connection, key, previous, value):
            if value.get("status") == "queued" and not raced:
                raced.append(self.ask(authority=None))
            return receipts.save(connection, key, previous, value)

        def stopped_after_the_race(connection, key):
            if raced:
                raise RuntimeError("the database stopped here")
            return receipts.read(connection, key)
        store = requests_suite.types.SimpleNamespace(read=stopped_after_the_race, receipt_key=receipts.receipt_key,
                                                     save=satellite_asks_again)
        self.run_lane(hub=sd_lane.Hub(self.connection, store, requests_suite.SLUG, self.repo))
        self.assertEqual((self.calls, self.entries()[-1]["authority"], self.entries()[-1]["status"]),
                         ([], "manual", "pending"))
        self.run_lane()
        self.assertEqual((self.calls, self.entries()[-1]["status"]), ([], "prepared"))

    def test_no_entry_is_claimed_unless_its_request_row_names_it(self):
        """Prepare review at 63bc828e: every failure point in intake leaves the replaced manual entry unclaimed."""
        update = sd_lane.update

        def queue_write_fails(path, change):
            if change.__name__ == "queue_request":
                raise OSError("the queue file stopped here")
            return update(path, change)

        def read_fails(connection, key):
            raise RuntimeError("the database stopped here")
        unread = requests_suite.types.SimpleNamespace(read=read_fails, receipt_key=receipts.receipt_key,
                                                      save=receipts.save)
        faults = {"queue write": (self.hub, patch.object(sd_lane, "update", queue_write_fails)),
                  "queued write": (self.failing_hub("queued"), contextlib.nullcontext()),
                  "row read": (sd_lane.Hub(self.connection, unread, requests_suite.SLUG, self.repo),
                               contextlib.nullcontext())}
        for fault, (hub, broken) in faults.items():
            with self.subTest(fault):
                self.ask()
                requests_suite.sd_lane.intake(self.hub, self.path)  # a manual entry the row names
                self.ask(authority=None)
                with broken:
                    self.run_lane(hub=hub)
                self.assertEqual(self.calls, [])
                self.assertFalse([entry for entry in self.entries() if entry["status"] in ("running", "merged")])
                self.run_lane()
                self.assertEqual((self.calls, self.entries()[-1]["authority"], self.entries()[-1]["status"]),
                                 ([], None, "prepared"))

    def failing_hub(self, *statuses):
        """The hub's rows, but a row write with one of `statuses` fails as a stopped database would."""
        def save(connection, key, previous, value):
            if value.get("status") in statuses:
                raise RuntimeError("the database stopped here")
            return receipts.save(connection, key, previous, value)
        store = requests_suite.types.SimpleNamespace(read=receipts.read, receipt_key=receipts.receipt_key, save=save)
        return sd_lane.Hub(self.connection, store, requests_suite.SLUG, self.repo)

    def test_an_entry_whose_queued_write_failed_runs_after_the_next_intake_writes_it(self):
        """Review round 1: the row stayed `requested` while its entry merged; now the entry waits for the row."""
        self.ask()
        self.run_lane(hub=self.failing_hub("queued"))
        self.assertEqual((self.calls, self.entries()[-1]["status"], self.row()["status"]), ([], "pending", "requested"))
        self.run_lane()
        self.assertEqual((self.entries()[-1]["status"], self.entries()[-1]["request_row"]), ("merged", "written"))
        self.assertEqual((self.row()["status"], self.row()["merge_commit"]), ("merged", "merged-7"))

    def test_a_failed_outcome_write_is_written_at_the_next_intake(self):
        """Review round 2: the row was `queued` and its outcome write failed, so it read `queued` for good."""
        queued = sd_lane.request_key(requests_suite.SLUG, 7)
        before = receipts.read(self.connection, queued)[0]
        self.assertEqual(requests_suite.sd_lane.intake(self.hub, self.path), [])  # a pending entry: nothing to write
        self.run_lane(hub=self.failing_hub("merged"))
        self.assertEqual((receipts.read(self.connection, queued)[0], self.row()["status"]), (before, "queued"))
        [answer] = requests_suite.sd_lane.intake(self.hub, self.path)
        self.assertEqual((answer["status"], answer["request_row"]), ("merged", "written"))
        self.assertEqual((self.row()["status"], self.row()["merge_commit"]), ("merged", "merged-7"))

    def test_a_finished_entry_writes_its_outcome_though_its_ship_row_moved_on(self):
        """Review round 1: with the outcome write failed, the next intake must not refuse a merged item as unprepared."""
        self.run_lane(hub=self.failing_hub("merged"))
        self.prepared(phase="merged")
        requests_suite.sd_lane.intake(self.hub, self.path)
        self.assertEqual((self.row()["status"], self.row()["merge_commit"]), ("merged", "merged-7"))


if __name__ == "__main__":
    unittest.main()
