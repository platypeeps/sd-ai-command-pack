"""Accepted findings still pass through the canonical publication and merge guards."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sd_db import create_assignment
from sd_db.workflow import WorkflowError

from tests import test_sd_ship_dispositions as disposition_fixture

ship = disposition_fixture.ship


class DispositionGuardTests(unittest.TestCase):
    setUp = disposition_fixture.DispositionTests.setUp
    args = disposition_fixture.DispositionTests.args
    operation = disposition_fixture.DispositionTests.operation
    prepare = disposition_fixture.DispositionTests.prepare
    merge = disposition_fixture.DispositionTests.merge
    cli = disposition_fixture.DispositionTests.cli
    blocked = disposition_fixture.DispositionTests.blocked
    command = disposition_fixture.DispositionTests.command
    filled = disposition_fixture.DispositionTests.filled

    def accept_review(self):
        self.blocked()
        self.filled()
        validated = self.command("--dispositions-file", str(self.proposal_file))
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
        digest = json.loads(validated.stdout)["acceptance_digest"]
        accepted = self.command("--dispositions-file", str(self.proposal_file), "--accept-dispositions", digest)
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

    def prepare_accepted(self):
        self.accept_review()
        with patch.object(ship, "review_process", side_effect=AssertionError("unexpected review dispatch")):
            self.assertEqual(self.prepare()["phase"], "ready_to_send")

    def change_policy(self):
        local = self.root / "CLAUDE.local.md"
        local.write_text(local.read_text().replace("mode: full", "mode: guest"))

    def unchanged_reviews_and_no_merge(self):
        self.assertEqual(self.operation().state["passes"], self.raw)
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def assert_pre_push_revalidation(self, mutate, message):
        self.accept_review()
        original = ship.Ship.check_review
        checks = []

        def after_first_check(operation, head, **kwargs):
            checks.append(head)
            result = original(operation, head, **kwargs)
            if len(checks) == 1:
                mutate()
            return result

        with (patch.object(ship.Ship, "check_review", new=after_first_check),
              patch.object(ship, "review_process", side_effect=AssertionError("unexpected review dispatch")),
              patch.object(ship, "git", wraps=ship.git) as git_calls):
            with self.assertRaisesRegex(ship.Refusal, message):
                self.prepare()
        self.assertEqual(len(checks), 2)
        self.assertFalse(any(call.args[1:2] == ("push",) for call in git_calls.call_args_list))
        self.assertFalse(self.remote.pull_requests)
        self.unchanged_reviews_and_no_merge()

    def test_evidence_change_after_review_clearance_refuses_before_push(self):
        self.assert_pre_push_revalidation(
            lambda: self.evidence.write_text("changed after the first gate"),
            "disposition evidence changed",
        )

    def test_policy_change_after_review_clearance_refuses_before_push(self):
        self.assert_pre_push_revalidation(self.change_policy, "review tools or repository policy changed")

    def test_stale_evidence_refuses_at_first_merge_gate_before_authority_lookup(self):
        self.prepare_accepted()
        self.evidence.write_text("changed after publication")
        operation = self.operation("merge", "--manual", "--expected-head", self.head)
        with patch.object(operation.api, "owned", side_effect=AssertionError("authority lookup after stale evidence")):
            with self.assertRaisesRegex(ship.Refusal, "disposition evidence changed"):
                operation.merge()
        self.assertEqual(self.operation().state["phase"], "ready_to_send")
        self.unchanged_reviews_and_no_merge()

    def assert_final_merge_revalidation(self, mutate, message):
        self.prepare_accepted()
        operation = self.operation("merge", "--manual", "--expected-head", self.head)
        ready = operation.api.ready
        check_review = ship.Ship.check_review
        checks = []

        def after_ci(*args, **kwargs):
            ready(*args, **kwargs)
            mutate()

        def observed_check(current, head, **kwargs):
            checks.append(head)
            return check_review(current, head, **kwargs)

        with (patch.object(operation.api, "ready", side_effect=after_ci),
              patch.object(ship.Ship, "check_review", new=observed_check)):
            with self.assertRaisesRegex(ship.Refusal, message):
                operation.merge()
        self.assertEqual(len(checks), 2)
        self.assertEqual(self.operation().state["phase"], "ci_passed")
        self.unchanged_reviews_and_no_merge()

    def test_evidence_change_during_ci_refuses_at_final_merge_gate(self):
        self.assert_final_merge_revalidation(
            lambda: self.evidence.write_text("changed during remote readiness checks"),
            "disposition evidence changed",
        )

    def test_policy_change_during_ci_refuses_at_final_merge_gate(self):
        self.assert_final_merge_revalidation(self.change_policy, "review tools or repository policy changed")

    def test_accepted_dispositions_preserve_exact_head_and_app_ci_requirements(self):
        self.prepare_accepted()
        pull = self.remote.pull(1)
        valid = dict(pull.checks[0])
        for changes, message in (
            ({"conclusion": "failure"}, "required CI is not passing"),
            ({"status": "queued"}, "required CI is not passing"),
            ({"head_sha": "0" * 40}, "required CI is not passing"),
            ({"app": {"id": 8}}, "required CI has no current result"),
        ):
            with self.subTest(changes=changes):
                pull.checks = [{**valid, **changes}]
                with self.assertRaisesRegex(ship.Refusal, message):
                    self.merge()
        pull.checks = []
        with self.assertRaisesRegex(ship.Refusal, "required CI has no current result"):
            self.merge()
        self.unchanged_reviews_and_no_merge()

    def test_accepted_dispositions_preserve_manual_ownership_protection_and_runner_guards(self):
        self.prepare_accepted()
        operation = self.operation("merge", "--expected-head", self.head)
        with self.assertRaisesRegex(ship.Refusal, "separate owned --run assignment or explicit --manual"):
            operation.merge()
        self.double.admin = False
        with self.assertRaisesRegex(ship.Refusal, "administer"):
            self.merge()
        self.double.admin = True
        self.remote.protection["enforce_admins"]["enabled"] = False
        with self.assertRaisesRegex(ship.Refusal, "administrators"):
            self.merge()
        self.remote.protection["enforce_admins"]["enabled"] = True
        create_assignment(self.connection, item=self.item, role="author", status="running")
        with self.assertRaisesRegex(WorkflowError, "manual merge authority"):
            self.merge()
        self.unchanged_reviews_and_no_merge()


if __name__ == "__main__":
    unittest.main()
