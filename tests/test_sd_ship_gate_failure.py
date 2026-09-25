"""sd:1475. A gate that fails before any reviewer is asked spends no pass.

Under parallel load `make check` outran sd-check's fixed 900-second limit,
sd-review reported `gate_failed` without asking a provider, and sd-ship kept
the reserved pass anyway: sd:1309 lost two of its five automatic passes that
way, and each loss also demanded `--retry-review` for a review nobody ran.
"""

from __future__ import annotations

import contextlib
import copy
import importlib
import io
import unittest
import unittest.mock

from tests import test_sd_review as review_tests
from tests import test_sd_ship_provider as provider_tests
from tests.test_sd_review import FakeRunner, sd_review

ship = provider_tests.ship
# After the fixture import, which puts `bin/` on the path.
sd_ship_review = importlib.import_module("sd_ship_review")
HEAD = provider_tests.HEAD

GATE_FAILED = {"status": "gate_failed", "check": {"status": "fail", "exit_code": 1, "detail": "timed out after 900s"},
               "completed_reviews": 0, "reviewed_by": [], "outcomes": [], "findings": []}


class GateFailureSpendsNoPass(unittest.TestCase):
    # Borrowed, not inherited: a subclass would run every selection test twice.
    context = provider_tests.ProviderSelection.context

    def test_a_gate_failure_before_any_reviewer_leaves_no_pass(self):
        review, process = self.context(report_changes=GATE_FAILED)
        with self.assertRaisesRegex(ship.Refusal, "no review pass was spent") as caught:
            review.review(HEAD)
        self.assertIn("timed out after 900s", str(caught.exception))
        self.assertEqual(review.state["passes"], [])
        self.assertIsNone(review.state.get("reviewed_head"))
        self.assertEqual(review.state["review_preflight_error"]["kind"], "gate_failed")
        self.assertEqual(process.call_count, 2)

    def test_the_next_prepare_reviews_without_a_retry_flag(self):
        failed, _process = self.context(report_changes=GATE_FAILED)
        with self.assertRaises(ship.Refusal):
            failed.review(HEAD)
        review, _process = self.context(state=failed.state)
        review.review(HEAD)
        self.assertEqual(len(review.state["passes"]), 1)
        self.assertEqual(review.state["passes"][0]["report"]["status"], "clean")
        self.assertIsNone(review.state["review_preflight_error"])

    def test_a_gate_failure_on_a_fix_verification_keeps_the_earlier_pass_only(self):
        reviewed, _process = self.context()
        reviewed.review(HEAD)
        original = copy.deepcopy(reviewed.state["passes"])
        fixed = "c" * 40
        failed, _process = self.context(state=reviewed.state, head=fixed, report_changes=GATE_FAILED)
        with unittest.mock.patch("sd_ship_review.git", return_value=""), self.assertRaises(ship.Refusal):
            failed.review(fixed)
        self.assertEqual(failed.state["passes"], original)

    def test_a_run_that_asked_a_reviewer_still_spends_its_pass(self):
        asked = {**GATE_FAILED, "outcomes": [{"backend": "automatic", "status": "failed"}]}
        review, _process = self.context(report_changes=asked)
        with self.assertRaises(ship.Refusal) as caught:
            review.review(HEAD)
        self.assertNotIn("no review pass was spent", str(caught.exception))
        self.assertEqual(len(review.state["passes"]), 1)


class TheRealGateFailureIsRecognised(review_tests.ReviewFixture):
    """The predicate read against what sd-review emits, not a hand-built report."""

    # Imported as a module, so the loader does not collect its classes here.
    prepare = review_tests.PipelineTests.prepare
    run_review = review_tests.PipelineTests.run_review

    def test_sd_review_s_gate_failure_is_the_shape_sd_ship_releases(self):
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner({"sd-check": sd_review.Completed(1, "{}", "timed out after 900s")})
        result = self.run_review(root, runner)
        self.assertEqual(result["status"], "gate_failed")
        self.assertTrue(sd_ship_review.unreviewed_gate_failure(result, sd_review.EXIT_GATE))


class ReviewTimeoutReachesTheGate(unittest.TestCase):
    def test_sd_review_hands_its_phase_budget_to_sd_check(self):
        """The phase budget sd-review plans for the gate is the limit sd-check uses."""
        runner = FakeRunner({})
        sd_review.run_check(provider_tests.fixture.ROOT, runner, {}, 2400)
        argv = runner.calls[0]["argv"]
        self.assertEqual(argv[argv.index("--timeout") + 1], "2400")

    def test_prepare_forwards_review_timeout_to_both_sd_review_stages(self):
        review, process = provider_tests.ProviderSelection.context(self)
        review.args.review_timeout = 3000
        review.review(HEAD)
        for call in process.call_args_list:
            argv = call.args[1]
            self.assertEqual(argv[argv.index("--timeout") + 1], "3000")

    def test_prepare_without_review_timeout_forwards_none(self):
        review, process = provider_tests.ProviderSelection.context(self)
        review.review(HEAD)
        self.assertTrue(all("--timeout" not in call.args[1] for call in process.call_args_list))

    def test_the_parser_takes_a_positive_review_timeout_on_every_dispatch_surface(self):
        for args in (["prepare", "--item", "42"], ["prepare", "--no-item", "--review-id", "record"],
                     ["review", "--no-item", "--review-id", "record"]):
            with self.subTest(args=args):
                self.assertIsNone(ship.parser().parse_args(args).review_timeout)
                self.assertEqual(ship.parser().parse_args([*args, "--review-timeout", "3000"]).review_timeout, 3000)
                with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                    ship.parser().parse_args([*args, "--review-timeout", "0"])


if __name__ == "__main__":
    unittest.main()
