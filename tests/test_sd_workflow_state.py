"""Typed additions preserve existing shipping result and refusal contracts."""

from __future__ import annotations

import hashlib
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
reviewer_process = importlib.import_module("sd_ship_review").reviewer_process
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
                         "Triage review findings and complete post-merge closeout. "
                         "Remove this PR's safe branches, stashes, refs and stale worktrees "
                         "after recording their object IDs.")

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
        # `review` reserves each pass with its process (sd:1938); execution adds the deadline.
        review.execute_review(["review"], "head", [{"head": "head", "process": reviewer_process()}])
        self.assertEqual(process.call_count, 2)
        self.assertEqual(len(review.state["passes"]), 1)
        self.assertEqual(review.state["passes"][0]["process"]["execution_seconds"], 3720)

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

    def test_the_review_binding_binds_the_external_reviews_value_not_the_home_path(self):
        """A satellite under another login has another HOME, so another config
        path; the hub then refused every offload merge as `review_binding_moved`
        (sd:2793). The binding holds across HOMEs and moves with the value; a
        receipt that bound the path reads as moved, naming the entry."""
        with tempfile.TemporaryDirectory() as directory:
            scratch = pathlib.Path(directory)
            root = scratch / "repo"
            subprocess.run(["git", "init", "-q", str(root)], check=True)

            def manifest(home: str, value: str) -> dict:
                config = scratch / home / ".config" / bindings.sd_lib.CONFIG_RELATIVE_PATH
                config.parent.mkdir(parents=True, exist_ok=True)
                config.write_text(json.dumps({"config": {"sd": {"external_reviews": value}}}))
                with patch.dict("os.environ", {"HOME": str(scratch / home), "XDG_CONFIG_HOME": ""}):
                    return bindings.binding_manifest(root)

            hub = manifest("hub", "configured")
            self.assertEqual(bindings.manifest_digest(manifest("satellite", "configured")), bindings.manifest_digest(hub))
            self.assertNotEqual(bindings.manifest_digest(manifest("satellite", "deny")), bindings.manifest_digest(hub))
            old = json.loads(json.dumps(hub))
            old["policy"]["external_review_policy"] = bindings.digest({"path": str(scratch / "hub"), "value": "configured"})
            self.assertEqual(bindings.binding_change(old, hub), [("external_review_policy", "policy")])

    def test_the_local_policy_digest_reads_the_parsed_block(self):
        """sd:2854. A hub and a satellite keep their own untracked copy: layout, comments and
        lines outside the markers move nothing, a key moves it, and no file reads as an empty block."""
        start, end = bindings.sd_lib.LOCAL_BLOCK_START, bindings.sd_lib.LOCAL_BLOCK_END
        with tempfile.TemporaryDirectory() as directory:
            local = pathlib.Path(directory) / "CLAUDE.local.md"
            empty = bindings.sd_lib.local_policy_digest(None)
            self.assertEqual(bindings.sd_lib.local_policy_digest(local), empty)
            for text in ("a note, no block\n", f"{start}\n{end}\n", f"reviewers: outside\n{start}\n# a comment\n\n{end}\n"):
                with self.subTest(text=text):
                    local.write_text(text)
                    self.assertEqual(bindings.sd_lib.local_policy_digest(local), empty)
            local.write_text(f"{start}\nmode: full\ncheck: make check\n{end}\n")
            full = bindings.sd_lib.local_policy_digest(local)
            self.assertNotEqual(full, empty)
            local.write_text(f"# the satellite's copy\n{start}\n  check:   make check  # same\n\nmode: 'full'\n{end}\nnotes\n")
            self.assertEqual(bindings.sd_lib.local_policy_digest(local), full)
            local.write_text(f"{start}\nmode: minimal\ncheck: make check\n{end}\n")
            self.assertNotEqual(bindings.sd_lib.local_policy_digest(local), full)

    def test_a_receipt_bound_to_the_raw_local_file_moves_once_and_says_why(self):
        """sd:2854 changed what the `CLAUDE.local.md` entry hashes, so the normalizer names it."""
        self.assertIn("local-block-1", bindings.NORMALIZER)
        stored = {"schema": 2, "normalizer": bindings.NORMALIZER.replace("+local-block-1", "")}
        current = {"schema": 2, "normalizer": bindings.NORMALIZER, "verdict": {}, "policy": {}, "gate": {}, "check": {}}
        [(reason, kind)] = bindings.binding_change(stored, current)
        self.assertIn("local-block-1", reason)

    def test_the_protection_reader_is_in_the_review_manifest(self):
        """`sd_protection.py` is what the merge gate reads a ruleset through.
        A change to its bypass or pagination handling must invalidate a
        clearance the way a change to `sd_ship_remote.py` does."""
        self.assertIn("sd_protection.py", bindings.REVIEW_TOOL_FILES)

    def test_every_module_a_review_tool_imports_is_classified(self):
        """The classes are hand-maintained tuples, so a module a review tool
        grows a dependency on is a silent gap until somebody adds a line. This
        walks the `sd_*` imports of `sd-ship`, `sd-review` and `sd-check`
        transitively over `bin/` and names any module that is in no class and
        not exempt: the enumeration the tuples cannot be. It walked `sd-ship`
        alone until sd:1834, which left `sd_jev.py` and `sd_opencode.py`,
        both on the review path, unbound."""
        pattern = re.compile(r"^\s*(?:import|from)\s+(sd_[a-z_]+)", re.MULTILINE)
        seen, todo = set(), ["sd-ship", "sd-review", "sd-check"]
        while todo:
            name = todo.pop()
            if name in seen or name in bindings.IMPORT_EXEMPT or not (bindings.BIN / name).is_file():
                continue
            seen.add(name)
            todo.extend(f"{module}.py" for module in pattern.findall((bindings.BIN / name).read_text()))
        self.assertEqual(sorted(seen - set(bindings.REVIEW_TOOL_FILES)), [],
                         "modules a review tool imports that no binding class holds")

    def test_each_bound_file_has_exactly_one_class(self):
        classes = bindings.VERDICT_FILES + bindings.GATE_FILES + bindings.CHECK_FILES
        self.assertEqual(len(classes), len(set(classes)))
        self.assertFalse(set(classes) & set(bindings.IMPORT_EXEMPT))
        self.assertTrue({"sd_jev.py", "sd_opencode.py", "sd_review_request.py"}.issubset(bindings.VERDICT_FILES))

    def test_no_verdict_file_reads_its_docstrings(self):
        """The normalizer drops docstrings, which is only sound while no
        verdict code reads one: a prompt built from `__doc__` would change
        without moving the binding."""
        for name in bindings.VERDICT_FILES:
            with self.subTest(name=name):
                self.assertIsNone(re.search(r"__doc__|getdoc|getsource", (bindings.BIN / name).read_text()))

    def test_the_normalized_hash_ignores_comments_and_docstrings_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "module.py"

            def hashed(source):
                path.write_text(source)
                return bindings.normalized_hash(path)

            base = hashed('"""Module."""\ndef f():\n    """Doc."""\n    return "prompt"\n')
            self.assertTrue(base.startswith("ast:"))
            self.assertEqual(hashed('"""Other."""\n# note\ndef f():\n    """Other doc."""\n\n    return  "prompt"\n'), base)
            self.assertNotEqual(hashed('"""Module."""\ndef f():\n    """Doc."""\n    return "other prompt"\n'), base)
            self.assertNotEqual(hashed('"""Module."""\ndef f():\n    """Doc."""\n    log("x")\n    return "prompt"\n'), base)
            broken = hashed("def f(:\n")
            self.assertEqual(broken, "raw:" + hashlib.sha256(b"def f(:\n").hexdigest())
            self.assertNotEqual(hashed("def f(::\n"), broken)

    def test_the_normalized_hash_parses_each_content_once_and_new_bytes_again(self):
        """sd:1615: the parse is memoized by the bytes' digest, not by path or mtime."""
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "module.py"
            parse = Mock(wraps=bindings.normalized_source)
            with patch.object(bindings, "normalized_source", parse):
                path.write_text("def f():\n    return 'one'\n")
                first = bindings.normalized_hash(path)
                self.assertEqual(bindings.normalized_hash(path), first)
                self.assertEqual(parse.call_count, 1)
                # Same size, same path: only the content can tell them apart.
                path.write_text("def f():\n    return 'two'\n")
                self.assertNotEqual(bindings.normalized_hash(path), first)
                self.assertEqual(parse.call_count, 2)

    def test_cross_skill_receipt_policy_and_review_helpers_remain_required(self):
        self.assertTrue({"skills/sd-check/SKILL.md", "skills/sd-review/SKILL.md", "skills/sd-ship/SKILL.md",
                         "skills/sd-check/references/check-receipts.md"}.issubset(bindings.ADJUDICATOR_POLICY_FILES))
        self.assertTrue({"sd_check_receipts.py", "sd_review_material.py", "sd_review_readiness.py"}
                        .issubset(bindings.REVIEW_TOOL_FILES))


if __name__ == "__main__":
    unittest.main()
