"""Typed additions preserve existing shipping result and refusal contracts."""

from __future__ import annotations

import importlib
import json
import pathlib
import re
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests import test_sd_ship as fixture

ship = fixture.ship
ItemHistory, ItemIdentity = ship.ItemHistory, ship.ItemIdentity
ReviewRuntime, SharedReview = ship.ReviewRuntime, ship.SharedReview
validate_review_readiness = importlib.import_module("sd_ship_review").validate_review_readiness
workflow = importlib.import_module("sd_ship_workflow")
bindings = importlib.import_module("sd_ship_bindings")
failure, success = workflow.failure, workflow.success


def explained(readiness=None):
    report = {"status": "explained", "requested_reviews": 1,
              "timing": {"phase_seconds": 60, "setup_seconds": 3600, "execution_seconds": 3720,
                         "candidates": [{"name": "fixture", "recipient": "fixture@local"}]}}
    if readiness is not None:
        report["readiness"] = readiness
    return subprocess.CompletedProcess([], 0, json.dumps(report), "")


class WorkflowState(unittest.TestCase):
    def test_failure_classification_is_explicit_not_error_prose(self):
        cases = [("network_down", "retryable_failure", False), ("consent_missing", "operator_decision", True),
                 ("protection_required", "policy_block", False)]
        for code, state, approval in cases:
            error = ship.Refusal("same error text", code=code, state=state, approval_required=approval,
                                 next_action="A supported next action.")
            result = failure("merge", error)
            self.assertEqual({key: result[key] for key in ("ok", "manualRequired", "error")},
                             {"ok": False, "manualRequired": True, "error": "same error text"})
            workflow = result["workflow"]
            self.assertEqual(workflow["schema_version"], 1)
            self.assertEqual(workflow["state"], state)
            self.assertEqual(workflow["blocker"]["code"], code)
            self.assertEqual(workflow["blocker"]["retryable"], state == "retryable_failure")
            self.assertEqual(workflow["blocker"]["approval_required"], approval)
            self.assertTrue(workflow["next_action"])

    def test_runtime_error_and_unclassified_policy_error_remain_failures(self):
        self.assertEqual(failure("prepare", OSError("unavailable"))["workflow"]["state"], "retryable_failure")
        self.assertEqual(failure("merge", ValueError("bad policy"))["workflow"]["state"], "policy_block")

    def test_success_adds_state_without_changing_phase_or_identity(self):
        runtime = SimpleNamespace(clock=lambda: "now")
        review = SharedReview(pathlib.Path("."), None, pathlib.Path("unused"), None, store=None,
                              repository="fixture/repo", branch="topic", head="head", key="key", revision=1,
                              state={"head": "head"}, identity=ItemIdentity(42), history=ItemHistory(), runtime=runtime)
        result = review.result("merged", merge_commit="merged-head")
        self.assertTrue(result["ok"])
        self.assertEqual(result["phase"], "merged")
        self.assertEqual(result["item"], 42)
        self.assertEqual(result["merge_commit"], "merged-head")
        self.assertEqual(result["workflow"], success("merged"))
        self.assertIsNone(result["workflow"]["blocker"])

    def test_observed_merge_does_not_claim_durable_reconciliation(self):
        result = success("merged", observed_only=True)
        self.assertIn("reconcile", result["next_action"])
        self.assertIn("merge", success("ready_to_send", observed_only=True)["next_action"])

    def test_merged_action_requires_closeout_without_granting_deletion_authority(self):
        result = success("merged")
        self.assertEqual(result["state"], "success")
        self.assertIsNone(result["blocker"])
        self.assertEqual(result["next_action"],
                         "Triage review findings and complete approved post-merge closeout. "
                         "Confirm exact deletion targets and obtain explicit approval before deleting anything.")

    def test_check_reuse_requires_an_explicit_flag_in_both_review_entrypoints(self):
        for command in ("prepare", "review"):
            base = [command, "--no-item", "--review-id", "fixture"]
            self.assertFalse(ship.parser().parse_args(base).reuse_check)
            self.assertTrue(ship.parser().parse_args([*base, "--reuse-check"]).reuse_check)


class ReadinessReservation(unittest.TestCase):
    def context(self, response):
        process = Mock(return_value=response)
        runtime = ReviewRuntime(binding=lambda _root: "binding", process=process, current_head=lambda _root: "head",
                                clock=lambda: "now", timing_plan=ship.timing_plan, bin_dir=pathlib.Path("bin"),
                                setup_seconds=3600, diagnostic_bytes=4096)
        store = SimpleNamespace(save=Mock(return_value=2))
        review = SharedReview(pathlib.Path("."), None, pathlib.Path("unused"), None, store=store,
                              repository="fixture/repo", branch="topic", head="head", key="key", revision=1,
                              state={"passes": []}, identity=ItemIdentity(42), history=ItemHistory(), runtime=runtime)
        return review, process, store

    def test_missing_malformed_and_blocked_readiness_never_reserve_a_pass(self):
        blocked = {"status": "blocked", "blockers": [{"code": "consent_missing", "boundary": "policy",
                   "provider": "claude", "next_action": "Approve the named recipient."}],
                   "warnings": [], "runtime_approval": "not_observable"}
        for readiness in (None, {}, {"status": "ready", "blockers": [{}]}, blocked,
                          {"status": "blocked", "blockers": []}):
            with self.subTest(readiness=readiness):
                review, process, store = self.context(explained(readiness))
                with self.assertRaisesRegex(ship.Refusal, "no provider pass was reserved"):
                    review.execute_review(["review"], "head", [{"head": "head"}])
                self.assertEqual(process.call_count, 1)
                self.assertEqual(review.state["passes"], [])
                self.assertEqual(store.save.call_args.args[-1]["passes"], [])
                self.assertIsNone(review.state.get("reviewed_head"))

    def test_ready_with_unobservable_runtime_permission_is_not_false_authorization(self):
        ready = {"status": "ready", "blockers": [], "runtime_approval": "not_observable", "warnings": []}
        validate_review_readiness(explained(ready))
        review, process, _store = self.context(explained(ready))
        review.execute_review(["review"], "head", [{"head": "head"}])
        self.assertEqual(process.call_count, 2)
        self.assertEqual(len(review.state["passes"]), 1)

    def test_claimed_runtime_approval_is_not_accepted_as_pack_authority(self):
        ready = {"status": "ready", "blockers": [], "warnings": [], "runtime_approval": "granted"}
        with self.assertRaisesRegex(ship.Refusal, "no valid readiness plan"):
            validate_review_readiness(explained(ready))


class PolicyReferenceBinding(unittest.TestCase):
    def test_reference_additions_changes_and_removals_change_acceptance_binding(self):
        for skill in ("sd-check", "sd-review", "sd-ship"):
            with self.subTest(skill=skill):
                self.assert_reference_inventory_bound(skill)

    def assert_reference_inventory_bound(self, skill):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            library = root / "library.py"
            library.write_text("fixture library")
            folder = root / "skills" / skill / "references"
            folder.mkdir(parents=True)
            with (patch.object(bindings, "BIN", root / "bin"),
                  patch.object(bindings, "tool_files", side_effect=lambda: {}),
                  patch.object(bindings, "ADJUDICATOR_POLICY_FILES", ())):
                before = bindings.adjudicator_binding(str(library))
                reference = folder / "acceptance.md"
                reference.write_text("fixture acceptance rule")
                added = bindings.adjudicator_binding(str(library))
                self.assertNotEqual(added, before)
                reference.write_text("changed acceptance rule")
                self.assertNotEqual(bindings.adjudicator_binding(str(library)), added)
                reference.unlink()
                self.assertEqual(bindings.adjudicator_binding(str(library)), before)

    def test_required_policy_files_bind_content_and_refuse_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            library = root / "library.py"
            library.write_text("fixture library")
            for name in bindings.ADJUDICATOR_POLICY_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture policy")
            with (patch.object(bindings, "BIN", root / "bin"),
                  patch.object(bindings, "tool_files", side_effect=lambda: {})):
                before = bindings.adjudicator_binding(str(library))
                for name in bindings.ADJUDICATOR_POLICY_FILES:
                    with self.subTest(policy=name):
                        path = root / name
                        path.write_text("changed policy")
                        self.assertNotEqual(bindings.adjudicator_binding(str(library)), before)
                        path.unlink()
                        with self.assertRaisesRegex(ship.Refusal, "required review binding file cannot be read"):
                            bindings.adjudicator_binding(str(library))
                        path.write_text("fixture policy")
                        self.assertEqual(bindings.adjudicator_binding(str(library)), before)

    def test_the_protection_reader_is_in_the_review_manifest(self):
        """`sd_protection.py` is what the merge gate reads a ruleset through.
        A change to its bypass or pagination handling must invalidate a
        clearance the way a change to `sd_ship_remote.py` does."""
        self.assertIn("sd_protection.py", bindings.REVIEW_TOOL_FILES)

    def test_every_module_sd_ship_imports_is_in_the_review_manifest(self):
        """The manifest is a hand-maintained tuple, so a module the gate grows
        a dependency on is a silent gap until somebody adds a line. This walks
        `sd-ship`'s `sd_*` imports transitively over `bin/` and names any the
        tuple lacks: the enumeration the tuple itself cannot be."""
        pattern = re.compile(r"^\s*(?:import|from)\s+(sd_[a-z_]+)", re.MULTILINE)
        seen, todo = set(), ["sd-ship"]
        while todo:
            name = todo.pop()
            if name in seen or not (bindings.BIN / name).is_file():
                continue
            seen.add(name)
            todo.extend(f"{module}.py" for module in pattern.findall((bindings.BIN / name).read_text()))
        self.assertEqual(sorted(seen - set(bindings.REVIEW_TOOL_FILES)), [],
                         "modules sd-ship imports that REVIEW_TOOL_FILES does not bind")

    def test_cross_skill_receipt_policy_and_review_helpers_remain_required(self):
        self.assertTrue({"skills/sd-check/SKILL.md", "skills/sd-review/SKILL.md", "skills/sd-ship/SKILL.md",
                         "skills/sd-check/references/check-receipts.md"}.issubset(bindings.ADJUDICATOR_POLICY_FILES))
        self.assertTrue({"sd_check_receipts.py", "sd_review_material.py", "sd_review_readiness.py"}
                        .issubset(bindings.REVIEW_TOOL_FILES))


if __name__ == "__main__":
    unittest.main()
