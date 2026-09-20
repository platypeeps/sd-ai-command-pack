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

#: The *Development / Code, before merge* cap, read from the module that owns
#: it rather than spelled here, so a later change to the row moves this too.
CAP = importlib.import_module("sd_ship_history").AUTOMATIC_CODE_REVIEW_PASSES


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
        passes = [{"head": chr(ord("a") + index) * 40, "report": report} for index in range(CAP)]
        state = {"passes": passes}
        history = ItemHistory()
        self.assertEqual(history.spent(state), CAP)
        self.assertEqual(history.history_digest(state), digest(passes))
        self.assertFalse(history.requires_continuation(state))
        self.assertEqual(history.request_fields(state), {})
        self.assertEqual(history.aggregate(state), review_history(passes))
        prefix = history.history_digest(state)
        extra = chr(ord("a") + CAP) * 40
        request = {"head": extra, "reason": "explicit continuation", "allowed_passes": 1,
                   "prior_history_digest": prefix}
        passes.append({"head": extra, "additional_review_request": request})
        history.validate_requests(state)
        self.assertEqual(history.aggregate(state, before_last=True), review_history(passes[:CAP]))
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
        # A request is required only past the automatic cap, so the prefix it
        # binds is the whole automatic run. The digest is literal: a changed
        # derivation, or a changed cap, cannot validate this stored request.
        automatic = [{"head": chr(ord("a") + index) * 40, "report": report} for index in range(CAP)]
        extra = chr(ord("a") + CAP) * 40
        request = {"head": extra, "reason": "explicit continuation", "allowed_passes": 1,
                   "prior_history_digest": "47f27a1e3d5b70f7be7e1e1dab50f876d6295e9c746812469d6cb0542968d91d"}
        state = {"passes": [*automatic, {"head": extra, "additional_review_request": request}]}
        ItemHistory().validate_requests(state)
        self.assertEqual(ItemHistory().aggregate(state, before_last=True),
                         ItemHistory().aggregate({"passes": automatic}))
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


class HistoryChainTests(unittest.TestCase):
    """The chain a raised cap makes longer, checked at every link.

    Both cases below were reported against the cap raise and are the reason
    the coverage rule reads each stored entry rather than its position.
    """

    @staticmethod
    def _complete(base: str, head: str, previous: dict | None = None) -> dict:
        report = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                  "authorship_base": base, "subject": {"base": base, "head": head}}
        if previous is not None:
            report["verification_report_digest"] = digest(previous.get("report") or {})
        return report

    def _chain(self, length: int) -> tuple[dict, dict]:
        """`length` stored passes; the last one's report is the one read now."""
        base = "0" * 40
        passes: list[dict] = []
        for index in range(length):
            head = f"{index + 1:040x}"
            previous = passes[-1] if passes else None
            passes.append({"head": head, "report": self._complete(
                base if previous is None else previous["head"], head, previous)})
        return {"passes": passes}, passes[-1]["report"]

    def test_a_stale_digest_in_the_middle_of_the_chain_is_refused(self):
        state, report = self._chain(4)
        ItemHistory()._validate_coverage(state, report)
        # The mutation is two links back, where a check on the last link
        # alone cannot reach it.
        state["passes"][0]["report"]["status"] = "mutated after the fact"
        with self.assertRaisesRegex(ship.Refusal, "does not continue"):
            ItemHistory()._validate_coverage(state, report)

    def test_an_explicit_request_below_the_cap_still_takes_the_full_branch_rule(self):
        base = "0" * 40
        incomplete = {"status": "clean", "requested_reviews": 2, "completed_reviews": 1,
                      "authorship_base": base, "subject": {"base": base, "head": "a" * 40}}
        passes = [{"head": "a" * 40, "report": incomplete}, {"head": "b" * 40, "report": incomplete}]
        requested = {"head": "c" * 40, "reason": "operator asked", "allowed_passes": 1,
                     "prior_history_digest": digest(passes)}
        full = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                "authorship_base": base, "subject": {"base": base, "head": "c" * 40},
                "resume_report_digest": digest(review_history(passes))}
        state = {"passes": [*passes, {"head": "c" * 40, "report": full, "additional_review_request": requested}]}
        # Two incomplete passes then an explicitly requested full-branch
        # review: valid under the cap that was in force when it was written,
        # and the entry says so whatever the cap is now.
        self.assertIsNone(ItemHistory()._validate_coverage(state, full))
        # Which rule it took, asserted rather than assumed: only the
        # full-branch rule reads `resume_report_digest`, so breaking that one
        # field must refuse. The chain rule would have refused on the two
        # incomplete predecessors instead, with a different sentence.
        broken = dict(full, resume_report_digest=digest({"not": "the prior history"}))
        state["passes"][-1]["report"] = broken
        with self.assertRaisesRegex(ship.Refusal, "full-branch coverage does not match"):
            ItemHistory()._validate_coverage(state, broken)

    def test_an_automatic_verification_after_a_full_review_needs_no_earlier_completion(self):
        base = "0" * 40
        incomplete = {"status": "clean", "requested_reviews": 2, "completed_reviews": 1,
                      "authorship_base": base, "subject": {"base": base, "head": "a" * 40}}
        passes = [{"head": "a" * 40, "report": incomplete}, {"head": "b" * 40, "report": incomplete}]
        full = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                "authorship_base": base, "subject": {"base": base, "head": "c" * 40},
                "resume_report_digest": digest(review_history(passes))}
        checkpoint = {"head": "c" * 40, "report": full,
                      "additional_review_request": {"head": "c" * 40, "reason": "operator asked",
                                                    "allowed_passes": 1, "prior_history_digest": digest(passes)}}
        verification = self._complete("c" * 40, "d" * 40, checkpoint)
        state = {"passes": [*passes, checkpoint, {"head": "d" * 40, "report": verification}]}
        # The full review covered the whole branch, so the two incomplete
        # passes it superseded cannot hold the verification after it.
        self.assertIsNone(ItemHistory()._validate_coverage(state, verification))
        broken = dict(verification, verification_report_digest=digest({"not": full}))
        state["passes"][-1]["report"] = broken
        with self.assertRaisesRegex(ship.Refusal, "does not continue"):
            ItemHistory()._validate_coverage(state, broken)

    def test_a_stale_resume_link_on_an_intermediate_retry_is_refused(self):
        base = "0" * 40
        incomplete = {"status": "clean", "requested_reviews": 2, "completed_reviews": 1,
                      "authorship_base": base, "subject": {"base": base, "head": "a" * 40}}
        first = {"head": "a" * 40, "report": incomplete}
        # `first` completed 1 of the 2 reviews it requested, so it verified
        # nothing and the retry resumes the aggregate before it, not that
        # pass's own report.
        resumed = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                   "authorship_base": base, "subject": {"base": base, "head": "b" * 40},
                   "resume_report_digest": digest(review_history([first]))}
        retry = {"head": "b" * 40, "report": resumed, "retry": True}
        verification = self._complete("b" * 40, "c" * 40, retry)
        state = {"passes": [first, retry, {"head": "c" * 40, "report": verification}]}
        self.assertIsNone(ItemHistory()._validate_coverage(state, verification))
        # Mutating the report the retry resumed leaves the retry's own
        # resume link stale, two entries back from the report read now.
        state["passes"][0]["report"] = dict(incomplete, status="mutated after the fact")
        with self.assertRaisesRegex(ship.Refusal, "retain the incomplete review evidence"):
            ItemHistory()._validate_coverage(state, verification)

    def test_a_retry_that_produced_no_report_is_resumed_by_the_next_one(self):
        base = "0" * 40
        incomplete = {"status": "clean", "requested_reviews": 2, "completed_reviews": 1,
                      "authorship_base": base, "subject": {"base": base, "head": "a" * 40}}
        first = {"head": "a" * 40, "report": incomplete}
        # The attempt between them timed out: it reserved a pass and stored no
        # report at all, which is not a stale link, only an absent one.
        timed_out = {"head": "b" * 40, "retry": True,
                     "execution_error": {"kind": "watchdog_expired", "stage": "execution",
                                         "captured_report": {"scope": "branch", "findings": [],
                                                             "authored_with": [],
                                                             "subject": {"head": "b" * 40}}}}
        resumed = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                   "authorship_base": base, "subject": {"base": base, "head": "c" * 40},
                   "resume_report_digest": digest(review_history([first, timed_out]))}
        state = {"passes": [first, timed_out, {"head": "c" * 40, "report": resumed, "retry": True}]}
        self.assertIsNone(ItemHistory()._validate_coverage(state, resumed))
        broken = dict(resumed, resume_report_digest=digest({"not": "the prior history"}))
        state["passes"][-1]["report"] = broken
        with self.assertRaisesRegex(ship.Refusal, "retain the incomplete review evidence"):
            ItemHistory()._validate_coverage(state, broken)

    def test_an_automatic_verification_that_produced_no_report_is_resumed_not_refused(self):
        """A reservation is not a verification, whatever the next pass calls itself.

        Reported against the cap raise: the reportless exemption reached only
        entries marked `retry`, so a verification that timed out was read as a
        stale link and refused the recovery that follows it. The chain is only
        long enough to hold one once the cap allows five.
        """
        base = "0" * 40
        complete = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                    "authorship_base": base, "subject": {"base": base, "head": "a" * 40}}
        first = {"head": "a" * 40, "report": complete}
        # No `retry` key: this reserved an automatic verification and timed out.
        timed_out = {"head": "b" * 40,
                     "execution_error": {"kind": "watchdog_expired", "stage": "execution",
                                         "captured_report": {"scope": "branch", "findings": [],
                                                             "authored_with": [],
                                                             "subject": {"head": "b" * 40}}}}
        resumed = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                   "authorship_base": base, "subject": {"base": base, "head": "c" * 40},
                   "resume_report_digest": digest(review_history([first, timed_out]))}
        state = {"passes": [first, timed_out, {"head": "c" * 40, "report": resumed, "retry": True}]}
        self.assertIsNone(ItemHistory()._validate_coverage(state, resumed))
        # An attempt that died without parseable evidence is the same
        # reservation: a watchdog leaves a captured report, an unreadable
        # receipt leaves nothing, and neither verified anything.
        state["passes"][1] = {"head": "b" * 40,
                              "execution_error": {"kind": "unreadable_receipt", "stage": "execution"}}
        bare = dict(resumed, resume_report_digest=digest(
            review_history([first, state["passes"][1]])))
        state["passes"][-1]["report"] = bare
        self.assertIsNone(ItemHistory()._validate_coverage(state, bare))
        # The exemption reaches the reservation, not what follows it: a plain
        # verification cannot continue from a pass that produced no report.
        state["passes"][-1] = {"head": "c" * 40, "report": dict(
            bare, subject={"base": "b" * 40, "head": "c" * 40})}
        with self.assertRaisesRegex(ship.Refusal, "never completed the requested local review depth"):
            ItemHistory()._validate_coverage(state, state["passes"][-1]["report"])

    def test_a_retry_after_a_reportless_one_still_carries_the_earlier_blockers(self):
        """An absent report is not a licence to forget what came before it.

        Reported at high severity against the reportless exemption: the
        aggregate a retry must resume was taken only when the attempt left
        parseable timeout evidence, so an attempt that died leaving nothing
        let an earlier pass's blocking findings out of the evidence the next
        retry carries -- the case that most needs them kept.
        """
        base = "0" * 40
        blocking = {"status": "blocking", "requested_reviews": 1, "completed_reviews": 1,
                    "authorship_base": base, "subject": {"base": base, "head": "a" * 40},
                    "findings": [{"path": "bin/x.py", "summary": "a real blocker"}],
                    "authored_with": ["codex"]}
        first = {"head": "a" * 40, "report": blocking}
        reportless = {"head": "b" * 40, "retry": True,
                      "execution_error": {"kind": "unreadable_receipt", "stage": "execution"}}
        carried = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                   "authorship_base": base, "subject": {"base": base, "head": "c" * 40},
                   "resume_report_digest": digest(review_history([first, reportless]))}
        state = {"passes": [first, reportless, {"head": "c" * 40, "report": carried, "retry": True}]}
        self.assertIsNone(ItemHistory()._validate_coverage(state, carried))
        # Dropping the earlier evidence is what the rule refuses, and the
        # blocker is what would have been dropped.
        dropped = dict(carried, resume_report_digest=None)
        state["passes"][-1]["report"] = dropped
        with self.assertRaisesRegex(ship.Refusal, "retain the incomplete review evidence"):
            ItemHistory()._validate_coverage(state, dropped)

    def test_a_failed_verification_that_wrote_a_report_forgets_nothing(self):
        """A report is not evidence that anybody reviewed anything.

        Reported at high severity against the reportless exemption above: a
        verification that completed no review still emits a report, and its
        findings list is empty. Read as the latest word it supersedes the
        completed blocking review before it, and the retry that follows is
        handed zero blockers -- the same continuity hole as an absent report,
        wearing the shape of evidence.
        """
        base = "0" * 40
        blocking = {"status": "blocking", "requested_reviews": 1, "completed_reviews": 1,
                    "authorship_base": base, "subject": {"base": base, "head": "a" * 40},
                    "findings": [{"path": "bin/x.py", "summary": "a real blocker"}],
                    "authored_with": ["codex"]}
        first = {"head": "a" * 40, "report": blocking}
        # Nobody completed: 1 requested, 0 done, and so nothing found.
        failed = {"status": "clean", "requested_reviews": 1, "completed_reviews": 0,
                  "authorship_base": "a" * 40, "subject": {"base": "a" * 40, "head": "b" * 40},
                  "findings": [], "authored_with": [],
                  "verification_report_digest": digest(blocking)}
        second = {"head": "b" * 40, "report": failed}
        carried = {"status": "clean", "requested_reviews": 1, "completed_reviews": 1,
                   "authorship_base": base, "subject": {"base": base, "head": "c" * 40},
                   "resume_report_digest": digest(review_history([first, second]))}
        state = {"passes": [first, second, {"head": "c" * 40, "report": carried, "retry": True}]}
        self.assertIsNone(ItemHistory()._validate_coverage(state, carried))
        # The aggregate the dispatcher hands out is the aggregate the
        # validator asks for, and the blocker is in it.
        handed = ItemHistory().prior({"passes": [first, second]})
        self.assertEqual([row["summary"] for row in handed["findings"]], ["a real blocker"])
        # Carrying the failed verification's own report instead is what the
        # rule refuses, and it is exactly what drops the blocker.
        dropped = dict(carried, resume_report_digest=digest(failed))
        state["passes"][-1]["report"] = dropped
        with self.assertRaisesRegex(ship.Refusal, "retain the incomplete review evidence"):
            ItemHistory()._validate_coverage(state, dropped)
