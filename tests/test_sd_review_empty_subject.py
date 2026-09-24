"""sd:1405. A run that was handed nothing to read must not look like a review.

`finish_review` derives its status from `reviewed`, which counts providers that
*answered*. Nothing in that expression, and nothing upstream of the dispatch
loop, asks whether the subject had any paths in it. So a review of an empty
subject spends a real provider call, records `completed_reviews: 1`, and
reports `clean` -- or `advisory`, when the reader invents a finding about the
nothing it was shown -- at exit 0, in a receipt no consumer can tell apart from
a review that read a five-hundred-line diff and found it sound.

Measured on `6ae7e416` before any fix:

    empty subject, reader finds nothing : status 'clean'    exit 0  1/1  paths 0
    empty subject, reader emits finding : status 'advisory' exit 0  1/1  paths 0
    real diff,     reader finds nothing : status 'clean'    exit 0  1/1  paths 2

The provider outage this row was filed for is *not* this defect and is already
handled: every reader timing out, or returning a schema-invalid answer, gives
`status 'unavailable'` at exit 5, because `incomplete` catches it.
"""

from __future__ import annotations

import json
import subprocess

from tests.test_sd_review import FakeRunner, sd_review
from tests.test_sd_review_fallbacks import ReviewRunFixture

ANSWERS = {"sd-check": sd_review.Completed(0, "{}", "")}
FOUND_NOTHING = sd_review.Completed(0, json.dumps({"findings": []}), "")
INVENTED_A_FINDING = sd_review.Completed(0, json.dumps({"findings": [
    {"path": "src.py", "line": 1, "severity": "low",
     "summary": "invented", "family": "correctness"}]}), "")


class TheEmptySubjectIsNotAReview(ReviewRunFixture):
    def named_repo(self, name):
        """`prepare` always builds `repo`; a test needing a control needs two."""
        root = self.make_repo(name)
        (root / "src.py").write_text("the_review_subject = 123\n")
        (root / ".github").mkdir()
        (root / ".github/sd-review.json").write_text(json.dumps({"default_tier": "cheap"}))
        return root

    def commit_everything(self, root):
        """Leave the worktree clean, so the `worktree` scope has no paths."""
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-m", "everything\n\nAuthored-with: human"],
                       check=True, capture_output=True)

    def review_of_nothing(self, answer, name="repo"):
        root = self.named_repo(name)
        self.commit_everything(root)
        runner = FakeRunner(ANSWERS, default=answer)
        result = self.run_review(root, runner)
        self.assertEqual(len(result["subject"]["paths"]), 0, "the premise: the subject is empty")
        return result, runner

    def exit_code(self, result):
        return sd_review.STATUS_EXIT.get(str(result["status"]), sd_review.EXIT_OK)

    def test_a_review_of_nothing_does_not_report_what_a_review_reports(self):
        """The distinction, asserted where it is missing: an empty subject and a
        read-everything-found-nothing run must not arrive at the same word."""
        empty, _ = self.review_of_nothing(FOUND_NOTHING)
        real = self.run_review(self.named_repo("control"), FakeRunner(ANSWERS, default=FOUND_NOTHING))
        self.assertEqual(real["status"], "clean", "the control has to be a real clean review")
        self.assertNotEqual(
            empty["status"], real["status"],
            "a run handed 0 paths reports the same status as one that read a diff")

    def test_a_review_of_nothing_does_not_exit_like_a_review(self):
        """A consumer that shells out and tests `$? == 0` -- the merge gate is
        one -- cannot see the difference the status word does not draw."""
        empty, _ = self.review_of_nothing(FOUND_NOTHING)
        self.assertNotEqual(self.exit_code(empty), sd_review.EXIT_OK,
                            "an empty subject exits 0, indistinguishable from a completed review")

    def test_nothing_to_read_spends_no_provider_call(self):
        """The bill is the sharpest statement of it: a reader was paid to read
        an empty diff, and the ledger records a completed review for it."""
        empty, runner = self.review_of_nothing(FOUND_NOTHING)
        provider_calls = [call for call in runner.calls
                          if "sd-check" not in " ".join(map(str, call.get("argv", ())))]
        self.assertEqual(provider_calls, [], "a provider was invoked on an empty subject")
        self.assertEqual(empty["completed_reviews"], 0)
        self.assertEqual(empty["reviewed_by"], [])

    def test_an_invented_finding_about_nothing_is_not_advisory(self):
        """The row's own wording, reproduced: `advisory` at exit 0 having read
        no code. The finding is about a diff the reader was never shown."""
        empty, _ = self.review_of_nothing(INVENTED_A_FINDING)
        self.assertNotEqual(empty["status"], "advisory",
                            "a reader's invention about an empty subject is reported as advice")

    def test_the_outage_this_row_was_filed_for_is_already_caught(self):
        """Guards the refutation. If a later change makes a total reader outage
        exit 0, this fails and says so rather than leaving the row's premise
        looking true for the wrong reason."""
        root = self.prepare(tier="cheap")
        (root / "src.py").write_text("changed = 1\n")
        timed_out = sd_review.Completed(124, "", "timed out negotiating with code-mode host")
        result = self.run_review(root, FakeRunner(ANSWERS, default=timed_out))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(self.exit_code(result), sd_review.EXIT_GATE)
        self.assertEqual(result["completed_reviews"], 0)
