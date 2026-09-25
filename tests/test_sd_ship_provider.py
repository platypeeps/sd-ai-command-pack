"""Scoped reviewer selection never changes automatic policy or grants a pass."""

from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sd_db import connect, initialise, read_registry, record_cost, seed

from tests import test_sd_ship as fixture
from tests import test_sd_ship_no_item_publication as publication

ship = fixture.ship
CAP = fixture.CAP
HEAD, BASE = "a" * 40, "b" * 40


class ProviderSelection(unittest.TestCase):
    def context(self, provider=None, *, state=None, head=HEAD, plan_changes=None, report_changes=None):
        chosen = provider or "automatic"
        plan = {"status": "explained", "requested_reviews": 1, "providers": [chosen], "fallback_candidates": [],
                "readiness": {"status": "ready", "blockers": [], "warnings": [], "runtime_approval": "not_observable"},
                "timing": {"phase_seconds": 60, "setup_seconds": 3600, "execution_seconds": 3720,
                           "candidates": [{"name": chosen, "recipient": chosen + "@local"}]}}
        report = {**copy.deepcopy(plan), "status": "clean", "subject": {"head": head, "base": BASE},
                  "scope": "branch", "authorship_base": BASE, "authored_with": [], "check": {"status": "pass"},
                  "completed_reviews": 1, "reviewed_by": [chosen], "findings": [],
                  "outcomes": [{"backend": chosen, "status": "clean"}]}
        plan.update(plan_changes or {})
        report.update(report_changes or {})

        def process(_root, argv, **_kwargs):
            if "--explain" in argv:
                return subprocess.CompletedProcess(argv, 0, json.dumps(plan), "")
            current = copy.deepcopy(report)
            for flag, key in (("--verify-report", "verification_report_digest"), ("--resume-report", "resume_report_digest")):
                if flag in argv:
                    current[key] = ship.digest(json.loads(pathlib.Path(argv[argv.index(flag) + 1]).read_text()))
            if "--base" in argv:
                current["subject"]["base"] = argv[argv.index("--base") + 1]
            return subprocess.CompletedProcess(argv, 1 if current["status"] != "clean" else 0, json.dumps(current), "")

        process_mock = Mock(side_effect=process)
        runtime = ship.ReviewRuntime(binding=lambda _root: "binding", process=process_mock, current_head=lambda _root: head,
                                     clock=lambda: "now", timing_plan=ship.timing_plan, bin_dir=fixture.ROOT / "bin",
                                     setup_seconds=3600, diagnostic_bytes=4096)
        args = SimpleNamespace(provider=provider, retry_review=False, reuse_check=False, additional_review_for=None,
                               request_reason=None, review_history_digest=None, path=[], message_file=None, author=None)
        store = SimpleNamespace(save=Mock(return_value=2))
        review = ship.SharedReview(pathlib.Path("."), None, pathlib.Path("unused"), args, store=store,
                                   repository="fixture/repo", branch="topic", head=head, key="key", revision=1,
                                   state=copy.deepcopy(state) if state is not None else {"passes": []},
                                   identity=ship.ItemIdentity(42), history=ship.ItemHistory(), runtime=runtime)
        return review, process_mock

    def test_parser_accepts_provider_only_on_dispatch_surfaces(self):
        for args in (["prepare", "--item", "42"], ["prepare", "--no-item", "--review-id", "record"],
                     ["review", "--no-item", "--review-id", "record"]):
            with self.subTest(args=args):
                self.assertIsNone(ship.parser().parse_args(args).provider)
                self.assertEqual(ship.parser().parse_args([*args, "--provider", "minimax"]).provider, "minimax")

    def test_explicit_selection_reaches_both_stages_and_is_recorded(self):
        review, process = self.context("minimax")
        review.review(HEAD)
        self.assertEqual(process.call_count, 2)
        for call in process.call_args_list:
            argv = call.args[1]
            self.assertEqual(argv[argv.index("--provider") + 1], "minimax")
        self.assertIn("--explain", process.call_args_list[0].args[1])
        self.assertIn("--expected-timing", process.call_args_list[1].args[1])
        self.assertEqual(review.state["passes"][0]["requested_provider"], "minimax")
        self.assertEqual(review.result("reviewed")["review_selection"],
                         {"requested_provider": "minimax", "reviewed_by": ["minimax"]})

    def test_omission_does_not_forward_or_inherit_a_named_provider(self):
        review, process = self.context()
        review.review(HEAD)
        self.assertTrue(all("--provider" not in call.args[1] for call in process.call_args_list))
        self.assertIsNone(review.state["passes"][0]["requested_provider"])

    def test_mismatched_or_fallback_plan_refuses_before_reservation(self):
        cases = ({"providers": ["other"]}, {"fallback_candidates": ["other"]}, {"providers": []},
                 {"requested_reviews": 2},
                 {"timing": {"phase_seconds": 60, "setup_seconds": 3600, "execution_seconds": 3720,
                             "candidates": [{"name": "other", "recipient": "other@local"}]}})
        for change in cases:
            with self.subTest(change=change):
                review, process = self.context("minimax", plan_changes=change)
                with self.assertRaises(ship.Refusal):
                    review.review(HEAD)
                self.assertEqual(process.call_count, 1)
                self.assertEqual(review.state["passes"], [])

    def test_conflicting_reuse_refuses_without_replacing_clean_or_blocking_evidence(self):
        reviewed, _process = self.context("minimax")
        reviewed.review(HEAD)
        for blocking in (False, True):
            state = copy.deepcopy(reviewed.state)
            if blocking:
                state["passes"][0]["report"]["status"] = "blocking"
                state["passes"][0]["exit_code"] = 1
                state["reviewed_head"] = None
            review, process = self.context("baseten", state=state)
            with self.subTest(blocking=blocking), self.assertRaisesRegex(ship.Refusal, "requested reviewer"):
                review.review(HEAD)
            process.assert_not_called()
            self.assertEqual(review.state, state)
            review.store.save.assert_not_called()

    def test_same_or_omitted_selection_reuses_receipt_and_reports_actual_reviewer(self):
        reviewed, _process = self.context("minimax")
        reviewed.review(HEAD)
        for choice in ("minimax", None):
            review, process = self.context(choice, state=reviewed.state)
            review.review(HEAD)
            process.assert_not_called()
            self.assertEqual(review.state, reviewed.state)
            self.assertEqual(review.result("reviewed")["review_selection"]["reviewed_by"], ["minimax"])

    def test_legacy_automatic_receipts_remain_usable_without_rewriting_history(self):
        reviewed, _process = self.context()
        reviewed.review(HEAD)
        reviewed.state["passes"][0].pop("requested_provider", None)
        for choice in (None, "automatic"):
            review, process = self.context(choice, state=reviewed.state)
            review.review(HEAD)
            process.assert_not_called()
            self.assertEqual(review.state, reviewed.state)

    def test_report_mismatch_retains_raw_evidence_but_never_clears_review(self):
        review, _process = self.context("minimax", report_changes={"reviewed_by": ["other"]})
        with self.assertRaisesRegex(ship.Refusal, "requested reviewer"):
            review.review(HEAD)
        self.assertEqual(len(review.state["passes"]), 1)
        self.assertEqual(review.state["passes"][0]["requested_provider"], "minimax")
        self.assertEqual(review.state["passes"][0]["report"]["reviewed_by"], ["other"])
        self.assertIsNone(review.state["reviewed_head"])
        with self.assertRaises(ship.Refusal):
            review.check_review(HEAD)

    def test_metadata_only_record_operations_refuse_ignored_selection(self):
        for flags in (["--create-record", "--assert-new-work"], ["--rebind-branch", "old"],
                      ["--close-record", "complete"], ["--reopen-record"],
                      ["--import-history", "prior.json", "--assert-history-complete"]):
            args = ship.parser().parse_args(["review", "--no-item", "--review-id", "record", "--provider", "minimax", *flags])
            with self.subTest(flags=flags), self.assertRaisesRegex(ship.Refusal, "provider.*record"):
                ship.validate_identity(args)

    def test_fix_verification_retains_history_and_uses_only_the_current_selector(self):
        reviewed, _process = self.context("minimax")
        reviewed.review(HEAD)
        original = copy.deepcopy(reviewed.state["passes"])
        fixed_head = "c" * 40
        for choice in ("minimax", "baseten", None):
            with self.subTest(choice=choice), patch("sd_ship_review.is_ancestor", return_value=True):
                review, process = self.context(choice, state=reviewed.state, head=fixed_head)
                review.review(fixed_head)
                self.assertEqual(review.state["passes"][:-1], original)
                self.assertEqual(review.state["passes"][-1]["requested_provider"], choice)
                argv = process.call_args_list[-1].args[1]
                self.assertIn("--verify-report", argv)
                self.assertEqual(argv[argv.index("--base") + 1], HEAD)
                self.assertEqual("--provider" in argv, choice is not None)
                self.assertEqual(review.state["passes"][-1]["report"]["reviewed_by"], [choice or "automatic"])

    def test_failed_retry_and_additional_request_preserve_selectors_and_budget(self):
        incomplete = {"status": "unavailable", "completed_reviews": 0, "reviewed_by": []}
        first, _process = self.context("minimax", report_changes=incomplete)
        with self.assertRaises(ship.Refusal):
            first.review(HEAD)
        # Retries spend the automatic allowance the table's cap grants, and
        # each one keeps the selector it was dispatched with.
        selectors, spent = ["minimax"], first
        for index in range(CAP - 1):
            choice = "baseten" if index % 2 == 0 else "minimax"
            spent, _process = self.context(choice, state=spent.state, report_changes=incomplete)
            spent.args.retry_review = True
            with patch("sd_ship_review.is_ancestor", return_value=True), self.assertRaises(ship.Refusal):
                spent.review(HEAD)
            selectors.append(choice)
        prefix = copy.deepcopy(spent.state["passes"])
        self.assertEqual(len(prefix), CAP)
        self.assertEqual(prefix[:1], first.state["passes"])
        self.assertEqual([entry["requested_provider"] for entry in prefix], selectors)
        refused, process = self.context("minimax", state=spent.state)
        refused.args.retry_review = True
        with self.assertRaisesRegex(ship.Refusal, "spent"):
            refused.review(HEAD)
        process.assert_not_called()
        self.assertEqual(refused.state["passes"], prefix)
        allowed, process = self.context("minimax", state=spent.state)
        allowed.args.additional_review_for, allowed.args.request_reason = HEAD, "Synthetic explicit additional request"
        with patch("sd_ship_review.is_ancestor", return_value=True):
            allowed.review(HEAD)
        self.assertEqual(allowed.state["passes"][:-1], prefix)
        self.assertEqual(allowed.state["passes"][-1]["additional_review_request"]["prior_history_digest"], ship.digest(prefix))
        self.assertIn("--resume-report", process.call_args_list[-1].args[1])

    def test_changed_tools_or_head_prevent_explicit_receipt_reuse(self):
        reviewed, _process = self.context("minimax")
        reviewed.review(HEAD)
        for head, binding in ((HEAD, "changed"), ("c" * 40, "binding")):
            review, process = self.context("minimax", state=reviewed.state)
            review.runtime = SimpleNamespace(binding=lambda _root, value=binding: value)
            with self.subTest(head=head, binding=binding), self.assertRaises(ship.Refusal):
                review.check_review(head)
            process.assert_not_called()

    def test_interrupted_explicit_dispatch_keeps_its_selection_for_retry_evidence(self):
        review, process = self.context("minimax")
        original_process = process.side_effect

        def interrupted(root, argv, **kwargs):
            if "--explain" in argv:
                return original_process(root, argv, **kwargs)
            raise ship.ReviewTimeout({"kind": "watchdog_expired", "allowed_seconds": 60})

        process.side_effect = interrupted
        with self.assertRaisesRegex(ship.Refusal, "reserved pass retained"):
            review.review(HEAD)
        original = copy.deepcopy(review.state["passes"])
        self.assertEqual(original[0]["requested_provider"], "minimax")
        self.assertEqual(original[0]["execution_error"]["stage"], "execution")
        retry, _process = self.context("baseten", state=review.state)
        retry.args.retry_review = True
        with patch("sd_ship_review.is_ancestor", return_value=True):
            retry.review(HEAD)
        self.assertEqual(retry.state["passes"][:-1], original)
        self.assertEqual(retry.state["passes"][-1]["requested_provider"], "baseten")


class ProviderPublication(unittest.TestCase):
    setUp = fixture.ShipCase.setUp
    args = fixture.ShipCase.args
    operation = fixture.ShipCase.operation
    prepare = fixture.ShipCase.prepare

    def test_item_prepare_selects_only_the_named_fixture_and_preserves_registry(self):
        registry = self.database.with_name("providers.yaml")
        before = registry.read_bytes()
        self.prepare("--provider", "reviewer2")
        state = self.operation().state
        self.assertEqual(state["passes"][0]["requested_provider"], "reviewer2")
        self.assertEqual(state["passes"][0]["report"]["reviewed_by"], ["reviewer2"])
        self.assertEqual(state["passes"][0]["report"]["fallback_candidates"], [])
        self.assertEqual(registry.read_bytes(), before)

    def test_unranked_explicit_reviewer_recovers_mixed_authorship_without_automatic_fallback(self):
        import sd_registry
        registry = self.database.with_name("providers.yaml")
        provider = self.programs / "review-fixture"
        registry.write_text(registry.read_text().replace("roles:\n", f"  requested: {{ start: '{provider}', vendor: independent, "
                                                        "bill: fixture, roles: [reviewer], reader: claude-json }\nroles:\n"))
        selected = sd_registry.read_file(registry).providers["requested"]
        local = self.root / "CLAUDE.local.md"
        local.write_text(local.read_text().replace("reviewers: ", f"reviewers: {sd_registry.recipient(selected)}, "))
        for author in ("reviewer/secondvendor", "reviewer2/thirdvendor"):
            fixture._git(self.root, "commit", "--allow-empty", "-m", f"fixture authorship\n\nAuthored-with: {author}")
        head = fixture._git(self.root, "rev-parse", "HEAD")
        automatic = self.operation()
        with self.assertRaises(ship.Refusal):
            automatic.review(head)
        self.assertFalse(automatic.state.get("passes"))
        before = registry.read_bytes(), list(self.connection.execute("SELECT * FROM provider"))
        self.prepare("--provider", "requested")
        report = self.operation().state["passes"][0]["report"]
        self.assertEqual(report["reviewed_by"], ["requested"])
        self.assertEqual(report["fallback_candidates"], [])
        self.assertTrue(report["chain"])
        self.assertTrue(all(not row["eligible"] for row in report["chain"]))
        self.assertNotIn("requested", [row["provider"] for row in report["chain"]])
        self.assertEqual((registry.read_bytes(), list(self.connection.execute("SELECT * FROM provider"))), before)

    def test_failed_named_reviewer_does_not_run_an_automatic_alternate(self):
        (self.programs / "review-fixture").write_text("#!/usr/bin/env python3\nprint('not a review')\n")
        with self.assertRaises(ship.Refusal):
            self.prepare("--provider", "reviewer2")
        report = self.operation().state["passes"][0]["report"]
        self.assertEqual([row["backend"] for row in report["outcomes"]], ["reviewer2"])
        self.assertEqual(report["fallback_candidates"], [])
        self.assertFalse(self.remote.pull_requests)


class ProviderEligibility(unittest.TestCase):
    setUp = fixture.ShipCase.setUp
    args = fixture.ShipCase.args
    operation = fixture.ShipCase.operation

    def assert_not_dispatched(self, name):
        registry = self.database.with_name("providers.yaml")
        before = registry.read_bytes(), list(self.connection.execute("SELECT * FROM provider"))
        review = self.operation("prepare", "--provider", name)
        original_process = ship.review_process

        def explain_only(root, argv, **kwargs):
            self.assertIn("--explain", argv, "an ineligible selection must not reach execution")
            return original_process(root, argv, **kwargs)

        with patch.object(ship, "review_process", side_effect=explain_only) as process:
            with self.assertRaises(ship.Refusal):
                review.review(fixture._git(self.root, "rev-parse", "HEAD"))
        self.assertEqual(process.call_count, 1)
        self.assertIn("--explain", process.call_args.args[1])
        self.assertFalse(review.state.get("passes"))
        self.assertEqual((registry.read_bytes(), list(self.connection.execute("SELECT * FROM provider"))), before)

    def test_unknown_and_non_reviewer_names_never_reserve(self):
        for name in ("missing", "author"):
            with self.subTest(name=name):
                self.assert_not_dispatched(name)

    def test_disabled_and_unsupported_reader_choices_never_reserve(self):
        registry = self.database.with_name("providers.yaml")
        original = registry.read_text()
        for change in ("enabled: false, reason: disabled, reader: claude-json", "reader: unsupported-json"):
            registry.write_text(original.replace("vendor: thirdvendor, bill: fixture, roles: [reviewer], reader: claude-json",
                                                  "vendor: thirdvendor, bill: fixture, roles: [reviewer], " + change))
            with self.subTest(change=change):
                self.assert_not_dispatched("reviewer2")

    def test_author_vendor_is_still_excluded(self):
        fixture._git(self.root, "commit", "--allow-empty", "-m", "fixture authorship\n\nAuthored-with: reviewer2/thirdvendor")
        self.assert_not_dispatched("reviewer2")

    def test_absent_consent_and_missing_executable_never_reserve(self):
        local = self.root / "CLAUDE.local.md"
        original = local.read_text()
        local.write_text("<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\nreviewers: none\n<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n")
        self.assert_not_dispatched("reviewer2")
        local.write_text(original)
        (self.programs / "review-fixture").unlink()
        self.assert_not_dispatched("reviewer2")

    def test_at_cap_named_provider_does_not_fall_back_or_change_provider_rows(self):
        registry = self.database.with_name("providers.yaml")
        registry.write_text("""bills:
  paid: { cost: company, cap_usd_month: 1 }
providers:
  paid: { url: 'https://paid.example.test/v1', model: fixture, vendor: paidvendor, bill: paid,
          roles: [reviewer], max_tokens: 100000, price: { in: 1.0, out: 2.0 }, env: [] }
roles:
  author: []
  reviewer: []
""")
        (self.root / "CLAUDE.local.md").write_text("<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\n"
                                               "reviewers: paid@paid.example.test\n<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n")
        seed(self.connection, read_registry(registry))
        record_cost(self.connection, source="run", provider="paid", bill="paid", usd=1.0)
        self.assert_not_dispatched("paid")


class ProviderItemless(unittest.TestCase):
    invoke = publication.NoItemPublication.invoke

    def setUp(self):
        fixture.ShipCase.setUp(self)
        self.database = self.database.with_name("no-items.db")
        initialise(self.database)
        self.connection = connect(self.database)
        self.addCleanup(self.connection.close)
        self.review_id = self.invoke("review", "--create-record", "--assert-new-work")["review_id"]

    def assert_selected_dispatch(self, command):
        args = ship.parser().parse_args([command, "--no-item", "--review-id", self.review_id,
                                         "--provider", "reviewer2", "--database", str(self.database)])
        with patch.object(ship, "review_process", wraps=ship.review_process) as process:
            result = ship.dispatch(self.root, self.connection, self.database, args, fixture.receipts, False)
        self.assertEqual(process.call_count, 2)
        self.assertEqual(result["review_selection"], {"requested_provider": "reviewer2", "reviewed_by": ["reviewer2"]})
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM item").fetchone()[0], 0)

    def test_no_item_prepare_forwards_the_explicit_choice(self):
        self.assert_selected_dispatch("prepare")

    def test_no_item_review_forwards_the_explicit_choice(self):
        self.assert_selected_dispatch("review")


class ProviderAdjudicated(unittest.TestCase):
    setUp = publication.NoItemPublication.setUp
    invoke = publication.NoItemPublication.invoke
    accepted_blocker = publication.NoItemPublication.accepted_blocker

    def test_conflicting_selection_cannot_replace_durably_accepted_review(self):
        self.accepted_blocker()
        before = list(self.connection.iterdump())
        args = ship.parser().parse_args(["prepare", "--no-item", "--review-id", self.review_id, "--provider", "other"])
        review = publication.no_item.open_review(self.root, self.connection, self.database, args,
                                                 fixture.receipts, ship.review_runtime())
        with patch.object(ship, "review_process", side_effect=AssertionError("no dispatch")):
            with self.assertRaisesRegex(ship.Refusal, "requested reviewer"):
                review.review(self.head)
        self.assertEqual(list(self.connection.iterdump()), before)
        self.assertFalse(self.remote.pull_requests)


if __name__ == "__main__":
    unittest.main()
