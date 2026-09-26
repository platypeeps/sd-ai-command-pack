"""sd:1475. A gate that fails before any reviewer is asked spends no pass.

Under parallel load `make check` outran sd-check's fixed 900-second limit,
sd-review reported `gate_failed` without asking a provider, and sd-ship kept
the reserved pass anyway: sd:1309 lost two of its five automatic passes that
way, and each loss also demanded `--retry-review` for a review nobody ran.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import importlib
import io
import sys
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
        with unittest.mock.patch("sd_ship_review.is_ancestor", return_value=True), self.assertRaises(ship.Refusal):
            failed.review(fixed)
        self.assertEqual(failed.state["passes"], original)

    def test_a_released_re_review_restores_the_binding_it_superseded(self):
        """Local review finding on sd:1475: dispatch saves the new binding before the gate runs.

        Popping the pass alone left the new binding stored, so the next prepare
        no longer saw the policy change and refused with "this head was already
        reviewed" instead of re-reviewing under the new policy.
        """
        reviewed, _process = self.context()
        reviewed.review(HEAD)
        original = copy.deepcopy(reviewed.state)
        failed, _process = self.context(state=reviewed.state, report_changes=GATE_FAILED)
        failed.runtime = dataclasses.replace(failed.runtime, binding=lambda _root: "moved")
        with unittest.mock.patch("sd_ship_review.is_ancestor", return_value=True), \
                self.assertRaisesRegex(ship.Refusal, "no review pass was spent"):
            failed.review(HEAD)
        for key in ("passes", "binding", "head", "reviewed_head", "review_clearance"):
            self.assertEqual(failed.state.get(key), original.get(key), key)
        again, process = self.context(state=failed.state)
        again.runtime = dataclasses.replace(again.runtime, binding=lambda _root: "moved")
        with unittest.mock.patch("sd_ship_review.is_ancestor", return_value=True):
            again.review(HEAD)
        self.assertEqual(process.call_count, 2)
        self.assertEqual(len(again.state["passes"]), 2)
        self.assertIn("review_binding_change", again.state["passes"][1])

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

    def test_a_failing_unittest_gate_keeps_its_output_in_the_receipt(self):
        """sd:1484. `check.detail` is sd-check's own stderr, empty when a test
        fails; the failure is in `checks[].stdout/stderr`. The release kept
        only `detail`, so the receipt said the gate failed and not why, and
        learning why meant running the gate again."""
        root = self.make_repo()
        (root / "test_gate.py").write_text(
            "import unittest\n\n\nclass Gate(unittest.TestCase):\n"
            "    def test_sd1484_marker(self):\n        self.assertEqual(1, 2)\n", encoding="utf-8")
        self.local_block(root, f"check: {sys.executable} -m unittest test_gate")
        check = sd_review.run_check(root, sd_review.subprocess_runner, self.environment(), 60)
        self.assertEqual(check["status"], "fail")
        review, _process = GateFailureSpendsNoPass.context(self, report_changes={**GATE_FAILED, "check": check})
        with self.assertRaisesRegex(ship.Refusal, "no review pass was spent") as caught:
            review.review(HEAD)
        receipt = review.state["review_preflight_error"]
        kept = receipt["checks"]
        self.assertEqual([(c["name"], c["status"], c["exit_code"]) for c in kept], [("check", "fail", 1), ("test", "absent", None), ("lint", "absent", None)])
        self.assertIn("FAIL: test_sd1484_marker", kept[0]["stderr"])
        self.assertIn("AssertionError: 1 != 2", str(caught.exception))

    def test_the_kept_output_is_bounded(self):
        noisy = {"name": "test", "status": "fail", "exit_code": 1, "reason": "",
                 "stdout": "o" * 10000 + "END-OUT", "stderr": "e" * 10000 + "END-ERR", "command": ["make", "test"]}
        report = {**GATE_FAILED, "check": {**GATE_FAILED["check"], "checks": [noisy] * 5}}
        review, _process = GateFailureSpendsNoPass.context(self, report_changes=report)
        with self.assertRaises(ship.Refusal):
            review.review(HEAD)
        kept = review.state["review_preflight_error"]["checks"]
        self.assertEqual(len(kept), len(sd_ship_review.sd_lib.CHECK_NAMES))
        for record in kept:
            self.assertEqual(len(record["stdout"]), 4096)
            self.assertTrue(record["stdout"].endswith("END-OUT"))
            self.assertTrue(record["stderr"].endswith("END-ERR"))

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
