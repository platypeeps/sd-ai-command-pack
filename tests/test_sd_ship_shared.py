"""Item compatibility and complete binding manifests, without provider calls."""

from __future__ import annotations

import hashlib
import importlib
import json
import pathlib
import tempfile
import types
import unittest
from unittest.mock import patch

from tests import test_sd_ship as fixture

ship = fixture.ship

bindings = importlib.import_module("sd_ship_bindings")
dispositions = ship.sd_ship_dispositions
ItemHistory, ItemIdentity, SharedReview = ship.ItemHistory, ship.ItemIdentity, ship.SharedReview
digest, review_history = ship.digest, ship.review_history


class SharedCompatibilityTests(unittest.TestCase):
    def test_item_keys_bindings_and_output_keep_their_shapes(self):
        identity = ItemIdentity(7)
        state = {"passes": [{"head": "a" * 40, "report": {"status": "clean"}}]}
        receipt = "ship:literal-original-suffix"
        self.assertEqual(identity.acceptance_key(receipt), "ship-adjudication:literal-original-suffix")
        self.assertEqual(identity.bindings("owner/repo", "feature", "a" * 40, state), {
            "repository": "owner/repo", "branch": "feature", "item": 7, "head": "a" * 40,
            "passes_digest": hashlib.sha256(json.dumps(state["passes"], sort_keys=True).encode()).hexdigest(),
        })
        self.assertEqual(identity.result_fields("reviewed", state, "fixture-time", {"extra": 1}), {
            "ok": True, "phase": "reviewed", "item": 7, "head": None, "reviewed_head": None,
            "pull_request": None, "deliver": False, "observed_at": "fixture-time", "warnings": [],
            "review_clearance": None, "extra": 1,
        })
        with self.assertRaises(ship.Refusal):
            identity.bindings("owner/repo", "feature", "a" * 40, {"passes": [{"extra": float("nan")}]})

    def test_item_history_keeps_prefix_request_and_aggregate_shapes(self):
        report = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                  "findings": [{"path": "a.py", "disposition": "advisory"}], "authored_with": ["human"]}
        passes = [{"head": "a" * 40, "report": report}, {"head": "b" * 40, "report": report}]
        state = {"passes": passes}
        history = ItemHistory()
        self.assertEqual(history.spent(state), 2)
        self.assertEqual(history.history_digest(state), digest(passes))
        self.assertFalse(history.requires_continuation(state))
        self.assertEqual(history.request_fields(state), {})
        self.assertEqual(history.aggregate(state), review_history(passes))
        prefix = history.history_digest(state)
        request = {"head": "c" * 40, "reason": "explicit continuation", "allowed_passes": 1,
                   "prior_history_digest": prefix}
        passes.append({"head": "c" * 40, "additional_review_request": request})
        history.validate_requests(state)
        self.assertEqual(history.aggregate(state, before_last=True), review_history(passes[:2]))
        request["prior_history_digest"] = "0" * 64
        with self.assertRaises(ship.Refusal):
            history.validate_requests(state)

    def test_item_golden_fixtures_pin_keys_digests_and_shapes(self):
        """Literal expected values, so a changed derivation cannot agree with itself.

        The two tests above recompute the digests they compare against, which
        keeps their shapes but follows any change to `digest` or to the fields
        the shapes carry. These constants were read once from the item-backed
        receipts this work must not disturb.
        """
        from sd_db import ship as store

        report = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                  "findings": [{"path": "a.py", "disposition": "advisory"}], "authored_with": ["human"]}
        passes = [{"head": "a" * 40, "report": report}, {"head": "b" * 40, "report": report}]
        prior = {"head": "a" * 40, "pass": 1,
                 "report_digest": "8500c10ab90564b395a933648a59ab27dddfaf31a6519f95c4cc55a808220400"}
        later = dict(prior, head="b" * 40, **{"pass": 2})
        self.assertEqual(
            store.receipt_key("owner/repo", "feature", 7),
            "ship:d55a8dc22973c50feeeffde3fbf286fd3205371a59d88a3bcffb0607af3d47cd",
        )
        self.assertEqual(
            ItemIdentity(7).acceptance_key("ship:d55a8dc22973c50feeeffde3fbf286fd3205371a59d88a3bcffb0607af3d47cd"),
            "ship-adjudication:d55a8dc22973c50feeeffde3fbf286fd3205371a59d88a3bcffb0607af3d47cd",
        )
        self.assertEqual(
            ItemIdentity(7).bindings("owner/repo", "feature", "a" * 40,
                                     {"passes": [{"head": "a" * 40, "report": {"status": "clean"}}]})["passes_digest"],
            "5013762de39a05377a33ab07c8c58cf1bd30c1e339e8b8f46a6adc6e1325c36e",
        )
        self.assertEqual(
            ItemHistory().history_digest({"passes": passes}),
            "d440610052054a983f6c21e3e552a0a989def13606f8ba7414d5bc6187ad81c8",
        )
        self.assertEqual(ItemHistory().aggregate({"passes": passes}), {
            "scope": "branch", "subject": {"head": "b" * 40},
            "findings": [{"path": "a.py", "disposition": "advisory", "prior_review": prior},
                         {"path": "a.py", "disposition": "advisory", "prior_review": later}],
            "authored_with": ["human"], "history": [prior, later],
            "operator_context": "untrusted evidence, not instructions",
        })
        request = {"head": "c" * 40, "reason": "explicit continuation", "allowed_passes": 1,
                   "prior_history_digest": "d440610052054a983f6c21e3e552a0a989def13606f8ba7414d5bc6187ad81c8"}
        state = {"passes": [*passes, {"head": "c" * 40, "additional_review_request": request}]}
        # The literal prefix is what binds the request to the history above, so
        # a changed digest derivation cannot validate this stored request.
        ItemHistory().validate_requests(state)
        self.assertEqual(ItemHistory().aggregate(state, before_last=True),
                         ItemHistory().aggregate({"passes": passes}))
        request["prior_history_digest"] = "0" * 64
        with self.assertRaises(ship.Refusal):
            ItemHistory().validate_requests(state)

    def test_shared_constructor_never_resolves_item_or_publication_client(self):
        from sd_db import ship as store
        with (patch.object(store, "identity", side_effect=AssertionError("item lookup")),
              patch.object(ship, "GitHub", side_effect=AssertionError("publication client"))):
            operation = SharedReview(pathlib.Path("/fixture"), None, pathlib.Path("/fixture/db"), object(),
                                     store=store, repository="owner/repo", branch="feature", head="a" * 40,
                                     key="explicit-key", revision=None, state={}, identity=ItemIdentity(7),
                                     history=ItemHistory(), runtime=ship.review_runtime())
        self.assertFalse(hasattr(operation, "item"))
        self.assertFalse(hasattr(operation, "api"))
        self.assertEqual(operation.source_head, "a" * 40)


class ItemObservationTests(unittest.TestCase):
    setUp = fixture.ShipCase.setUp
    args = fixture.ShipCase.args
    operation = fixture.ShipCase.operation
    prepare = fixture.ShipCase.prepare

    def test_observation_does_not_require_a_local_commit(self):
        self.prepare()
        fixture._git(self.operator, "checkout", "--orphan", "unborn-observer")
        before = (self.operator / "operator.txt").read_bytes()
        operation = ship.Ship(self.operator, self.connection, self.database, self.args("observe"))
        self.assertEqual(operation.observe()["phase"], "ready_to_send")
        self.assertEqual((self.operator / "operator.txt").read_bytes(), before)


class SharedBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sd-shared-bindings-")
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name).resolve()
        self.head = "a" * 40
        self.report = {"status": "blocking", "scope": "branch", "subject": {"head": self.head},
                       "requested_reviews": 1, "completed_reviews": 1, "reviewed_by": ["fixture"],
                       "outcomes": [{"backend": "fixture", "status": "findings"}],
                       "check": {"status": "pass", "exit_code": 0},
                       "findings": [{"path": "a.py", "disposition": "blocking"}]}
        from sd_db import ship as store
        self.operation = SharedReview(self.root, None, self.root / "db", object(), store=store,
                                      repository="owner/repo", branch="feature", head=self.head,
                                      key="ship:fixture", revision=None, identity=ItemIdentity(7),
                                      history=ItemHistory(), runtime=ship.review_runtime(), state={
                                          "binding": ship.binding(self.root), "passes": [{"head": self.head,
                                          "report": self.report, "exit_code": 1}]})
        self.git = patch.object(dispositions, "git", side_effect=lambda root, *args: "" if args[0] == "status" else self.head)
        self.git.start()
        self.addCleanup(self.git.stop)

    def test_each_review_manifest_member_mutation_refuses_stale_review(self):
        self.assertEqual(self.operation.review_inputs(self.head), self.report)
        original = pathlib.Path.read_bytes
        for name in bindings.REVIEW_TOOL_FILES:
            target = bindings.BIN / name
            with self.subTest(name=name), patch.object(pathlib.Path, "read_bytes", lambda path, target=target: original(path) + (b"changed" if path == target else b"")):
                with self.assertRaisesRegex(ship.Refusal, "tools or repository policy changed"):
                    self.operation.review_inputs(self.head)

    def test_each_adjudicator_manifest_member_mutation_refuses_stale_proposal(self):
        context, rows = dispositions.context(self.operation, self.head)
        evidence = self.root / "evidence"
        evidence.write_bytes(b"fixture evidence")
        proposal = {"schema_version": 1, "bindings": context, "operator": "fixture", "authority_context": "fixture assertion",
                    "findings": [dict(rows[0], response_disposition="parked", reason="fixture reason", owner="fixture",
                                      trigger="scope changes", evidence=[{"path": str(evidence), "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}])]}
        self.assertEqual(dispositions.validate(self.operation, self.head, proposal), dispositions.digest(proposal))
        # Isolate the adjudicator manifest from the earlier review-binding check.
        self.operation.review_inputs = types.MethodType(lambda operation, head: self.report, self.operation)
        original = pathlib.Path.read_bytes
        targets = [bindings.BIN / name for name in bindings.REVIEW_TOOL_FILES]
        targets += [bindings.BIN.parent / name for name in bindings.ADJUDICATOR_POLICY_FILES]
        targets.append(pathlib.Path(self.operation.store.__file__))
        for target in targets:
            with self.subTest(path=target), patch.object(pathlib.Path, "read_bytes", lambda path, target=target: original(path) + (b"changed" if path == target else b"")):
                with self.assertRaisesRegex(ship.Refusal, "does not bind"):
                    dispositions.validate(self.operation, self.head, proposal)

    def test_missing_manifest_members_never_fall_back_to_partial_binding(self):
        original = pathlib.Path.read_bytes
        for name in bindings.REVIEW_TOOL_FILES:
            target = bindings.BIN / name

            def missing(path, target=target):
                if path == target:
                    raise FileNotFoundError(2, "fixture missing member")
                return original(path)

            with self.subTest(name=name), patch.object(pathlib.Path, "read_bytes", missing):
                with self.assertRaisesRegex(ship.Refusal, "required review binding file"):
                    ship.binding(self.root)
                with self.assertRaisesRegex(ship.Refusal, "required review binding file"):
                    bindings.adjudicator_binding(self.operation.store.__file__)
