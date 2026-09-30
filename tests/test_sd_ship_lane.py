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
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sd_db import create_item
from sd_db import ship as receipts
from sd_db.testing.remote import _git

from tests import test_sd_ship as fixture

ship = fixture.ship
ROOT = fixture.ROOT


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
