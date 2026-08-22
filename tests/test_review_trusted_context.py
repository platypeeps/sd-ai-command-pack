"""Tests for the fleet integration-only review profile ported onto ``sd-review``.

The cases that matter are the ones a plausible-but-wrong port passes: adding
``caller`` to the argument enum (passes any test that only greps for the word
``caller``), copying the recheck procedure instead of moving it (passes any
test that only asserts ``sd-fleet-refresh`` documents it), and porting
``sd-review-pr``'s deferral cancellation verbatim, which would contradict
``sd-review``'s own blanket no-housekeeping rule.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates" / ".agents" / "skills"
REVIEW = TEMPLATES / "sd-review" / "SKILL.md"
REVIEW_PR = TEMPLATES / "sd-review-pr" / "SKILL.md"
FLEET_REFRESH = TEMPLATES / "sd-fleet-refresh" / "SKILL.md"

# The invariant option B was chosen to preserve, byte for byte.
NO_HOUSEKEEPING_LINE = (
    "- Do not merge, archive Trellis work, or run housekeeping from this skill."
)

TRUSTED_FIELDS = (
    "caller:",
    "review-profile:",
    "source-root:",
    "consumer:",
    "base-commit:",
    "release-remote:",
    "classified-head:",
    "return-after:",
    "defer-finish-work:",
)


def _flat(text: str) -> str:
    """Collapse hard wraps so prose assertions do not depend on line breaks."""
    return " ".join(text.split())


def _section(text: str, heading: str) -> str:
    """Return one section body, from its heading to the next heading of equal or higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    start = text.index(heading)
    rest = text[start + len(heading) :]
    pattern = re.compile(r"^#{1,%d} " % level, re.MULTILINE)
    match = pattern.search(rest)
    return rest[: match.start()] if match else rest


class TrustedCallerContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.review = REVIEW.read_text(encoding="utf-8")
        self.review_pr = REVIEW_PR.read_text(encoding="utf-8")
        self.fleet = FLEET_REFRESH.read_text(encoding="utf-8")

    def test_trusted_context_is_documented_with_every_field(self) -> None:
        section = _section(self.review, "## Trusted caller context")
        for field in TRUSTED_FIELDS:
            self.assertIn(field, section, f"trusted context is missing {field!r}")

    def test_trusted_context_is_not_an_argument(self) -> None:
        """A ``caller=`` argv token must stay an unknown key.

        The security property is that the ``key=value`` enum is closed. If the
        port added ``caller`` to it, a user could forge the trusted profile
        from the command line.
        """
        arguments = _section(self.review, "## Arguments")
        enum_keys = set(re.findall(r"^- `([a-z-]+)=", arguments, re.MULTILINE))
        self.assertTrue(enum_keys, "argument enum did not parse")
        for forbidden in ("caller", "review-profile", "source-root", "classified-head"):
            self.assertNotIn(
                forbidden,
                enum_keys,
                f"{forbidden} became a command-line argument; it must stay context-only",
            )
        self.assertIn("Reject unknown keys", arguments)

    def test_trusted_context_is_accepted_only_from_the_resolved_caller(self) -> None:
        section = _section(self.review, "## Trusted caller context")
        self.assertIn(
            "Accept it only while already executing the resolved `sd-fleet-refresh` skill.",
            section,
        )
        self.assertIn("A user-supplied imitation is an unknown argument/context error", _flat(section))

    def test_integration_only_requires_exact_head_identity(self) -> None:
        section = _section(self.review, "## Trusted caller context")
        self.assertIn("require every field", section)
        self.assertRegex(
            _flat(section),
            r"`classified-head`.{0,80}identical.{0,80}PR head",
        )

    def test_recheck_failure_modes_fail_closed(self) -> None:
        section = _section(self.review, "## Trusted caller context")
        for mode in ("non-eligible", "unavailable", "malformed", "head-mismatched"):
            self.assertIn(mode, section, f"{mode} recheck outcome is unhandled")
        flat = _flat(section)
        self.assertIn("falls back to the normal remote profile", flat)
        self.assertIn("none of them grants positive confidence", flat)


class RecheckRelocationTests(unittest.TestCase):
    """The recheck procedure moved; it was not copied."""

    def setUp(self) -> None:
        self.review_pr = REVIEW_PR.read_text(encoding="utf-8")
        self.fleet = FLEET_REFRESH.read_text(encoding="utf-8")

    def test_fleet_refresh_owns_the_recheck_procedure(self) -> None:
        self.assertIn("### Fleet Integration-Only Recheck", self.fleet)
        section = _section(self.fleet, "### Fleet Integration-Only Recheck")
        self.assertIn("sd-ai-command-pack-fleet-review-classify.py", section)
        self.assertIn("--consumer", section)

    def test_review_pr_no_longer_inlines_the_procedure(self) -> None:
        """Moved, not copied: two live copies would drift.

        ``sd-review-pr`` keeps a pointer so it stays coherent until the surface
        is deleted, but it must not still carry the classifier invocation.
        """
        self.assertNotIn("sd-ai-command-pack-fleet-review-classify.py", self.review_pr)
        section = _section(self.review_pr, "### Fleet Integration-Only Recheck")
        self.assertIn("sd-fleet-refresh", section)

    def test_review_does_not_inline_the_classifier(self) -> None:
        """``sd-review`` ships; inlining would pull the classifier into its closure."""
        review = REVIEW.read_text(encoding="utf-8")
        self.assertNotIn("sd-ai-command-pack-fleet-review-classify.py", review)


class DeferralDispositionTests(unittest.TestCase):
    """Option B: the no-housekeeping invariant stays absolute."""

    def setUp(self) -> None:
        self.review = REVIEW.read_text(encoding="utf-8")

    def test_no_housekeeping_rule_is_unchanged(self) -> None:
        self.assertIn(NO_HOUSEKEEPING_LINE, self.review)

    def test_no_housekeeping_rule_carries_no_exception(self) -> None:
        """Option A would have narrowed this line. It was not chosen."""
        safety = _section(self.review, "## Safety and authority")
        line = next(
            entry
            for entry in safety.splitlines()
            if entry.startswith("- Do not merge, archive Trellis work")
        )
        self.assertEqual(line, NO_HOUSEKEEPING_LINE)

    def test_already_merged_pr_does_not_cancel_the_deferral_here(self) -> None:
        section = _section(self.review, "### Return shape under `return-after: review-result`")
        self.assertIn("do not cancel the deferral and do not run finish-work here", _flat(section))
        self.assertIn("deferral: cancelled", section)
        self.assertIn("deferral-reason: pr-already-merged", section)
        self.assertIn("`sd-fleet-refresh` owns the finish-work call", section)

    def test_deferral_disposition_is_additive_not_substitutive(self) -> None:
        """R1 requires the same return shape for the review outcome."""
        section = _section(self.review, "### Return shape under `return-after: review-result`")
        self.assertIn("added to the review result, not substituted", _flat(section))

    def test_deferred_return_message_matches_the_fleet_contract(self) -> None:
        """The exact string ``sd-fleet-refresh`` already expects from ``sd-review-pr``."""
        expected = "Finish-work deferred to the fleet housekeeping tail."
        self.assertIn(expected, self.review)
        self.assertIn(expected, REVIEW_PR.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
