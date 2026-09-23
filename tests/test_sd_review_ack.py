"""The read/acknowledge gate, proved against the round that produced it.

`tests/fixtures/sd-543-review-round.json` is not an invented fixture. It is the
twelve pull requests item sd:543 names -- 851, 852, 856 through 865 -- captured
from the GitHub API with their reviews and their inline comments as they stand.
Those twelve merged on green CI while thirteen inline comments went unread, and
the argument of this file is that a gate which cannot refuse *that* round is
not a gate.

So every count below is measured from the capture rather than asserted from
memory, and the two cases that matter most are named individually:

  #859 and #861 carry **no inline comment at all** and four and three body
  findings respectively. A reader that counts inline comments calls both clean.

  371495dc is the commit three review threads on #860 cited as the fix. It is a
  real object in this repository and it is not an ancestor of the default
  branch, which is why three real defects shipped under three threads that all
  read as answered. `fix-not-landed` is the verdict that had to exist.
"""

from __future__ import annotations

import ast
import fcntl
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import unittest.mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sd-543-review-round.json"
UNANSWERED = REPO_ROOT / "tests" / "fixtures" / "sd-631-unanswered-round.json"
COUNT_ONLY = REPO_ROOT / "tests" / "fixtures" / "sd-655-count-only-round.json"
CAPTURES = sorted((REPO_ROOT / "tests" / "fixtures").glob("*-round.json"))

sys.path.insert(0, str(BIN))
import sd_lib  # noqa: E402

ack = sd_lib.sibling("sd_review_ack_under_test", "sd-review-ack")

#: The pull requests in the capture, and what each carried. Derived once, here,
#: from the capture itself rather than written down: a hand-kept table is the
#: thing this whole item is about.
ROUND = json.loads(FIXTURE.read_text(encoding="utf-8"))["pull_requests"]

GIT_IDENTITY = (
    "-c", "user.email=review-ack@example.invalid",
    "-c", "user.name=Review Ack Fixture",
    "-c", "commit.gpgsign=false",
)


def run(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BIN / "sd-review-ack"), "--from", str(FIXTURE), *args],
        cwd=str(root), capture_output=True, text=True, check=False,
    )


def payload(root: pathlib.Path, *args: str) -> tuple[dict, int]:
    done = run(root, "--json", *args)
    return json.loads(done.stdout or "{}"), done.returncode


class Repo:
    """A scratch repository with one commit on `main` and one off it.

    The commit off `main` is the shape of 371495dc: real, reachable by hash,
    and never an ancestor of the branch anything lands on.
    """

    def __init__(self, stack: tempfile.TemporaryDirectory) -> None:
        self.root = pathlib.Path(stack.name) / "repo"
        self.root.mkdir()
        self._git("init", "--initial-branch=main")
        (self.root / "README.md").write_text("landed\n")
        self._git("add", "README.md")
        self._git("commit", "-m", "landed")
        self.landed = self._git("rev-parse", "HEAD")
        self._git("checkout", "-b", "stranded")
        (self.root / "README.md").write_text("stranded\n")
        self._git("commit", "-am", "stranded")
        self.stranded = self._git("rev-parse", "HEAD")
        self._git("checkout", "main")

    def _git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", *GIT_IDENTITY, *args], cwd=str(self.root),
            capture_output=True, text=True, check=True,
        )
        return done.stdout.strip()


class RoundFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = tempfile.TemporaryDirectory()
        self.addCleanup(self.stack.cleanup)
        self.repo = Repo(self.stack)
        # `main` exists and `origin/main` does not, so every run names the ref
        # explicitly rather than depending on a remote the fixture has no need of.
        self.ref = ("--landed-in", "main")


class TheHistoricalRound(RoundFixture):
    """The gate, run against the round that went unread."""

    def test_the_gate_refuses_the_round_that_merged_clean(self):
        """Twelve merges, green CI, and this exits 1 with every finding named."""
        result, code = payload(self.repo.root, "--check", *self.ref)
        self.assertEqual(code, 1, "a gate that passes this round is not a gate")
        self.assertEqual(len(result["findings"]), 41)
        self.assertEqual(len(result["unsatisfied"]), 41)
        self.assertTrue(all(row["verdict"] == "unread" for row in result["findings"]))

    def test_both_places_a_reviewer_states_a_finding_are_read(self):
        """Nine inline, thirty-two in a review body. The body is most of the round.

        Thirteen inline comments is what the item counted, and nine of them were
        findings rather than replies. The other thirty-two findings were never
        counted by anything, in three shapes: a `Suppressed comments` section, a
        bulleted `Outstanding review findings:` list, and cells of the
        file-summary table. Counting inline comments reads 9 of 41.
        """
        result, _ = payload(self.repo.root, *self.ref)
        sources = [row["source"] for row in result["findings"]]
        self.assertEqual(sources.count("inline"), 9)
        self.assertEqual(sources.count("body"), 32)

    def test_the_pull_requests_a_comment_count_calls_clean(self):
        """#859 and #861 have zero inline comments and seven findings between them.

        This is the case the item is about. `gh pr view --json comments` returns
        an empty list for both, so anything counting comments reports no
        findings, and the reviewer's real findings sit in prose nobody opened.
        """
        for number, expected in ((859, 4), (861, 4)):
            with self.subTest(pr=number):
                self.assertEqual(ROUND[str(number)]["comments"], [])
                result, _ = payload(self.repo.root, "--pr", str(number), *self.ref)
                self.assertEqual(len(result["findings"]), expected)
                self.assertTrue(all(row["source"] == "body" for row in result["findings"]))
                # Located, not merely counted. Losing a parser would keep the
                # total right -- `_reconciled` replaces what it drops -- while
                # turning every row into an unreadable `?`, which is a worse
                # report that a count-only assertion cannot tell apart.
                self.assertNotIn("?", {row["path"] for row in result["findings"]})

    def test_every_pull_request_that_carried_a_finding_is_named(self):
        """No pull request with a finding falls out of the report."""
        result, _ = payload(self.repo.root, *self.ref)
        found = {row["pr"] for row in result["findings"]}
        self.assertEqual(found, {852, 856, 857, 858, 859, 860, 861, 863, 865})

    def test_the_dot_prefixed_path_survives_the_body_parser(self):
        """`.github/scripts/run-tests.sh:175` is a body finding and it parses.

        It is the watchdog defect from this item's own correction note, which is
        on main to this day. A locator pattern anchored to a leading letter
        drops exactly this row, silently -- and the assertion has to name the
        *body* source, because #860 also carries inline comments on the same
        file. Asserting on the path alone passes with the parser broken, which
        is how this test read before a mutation run caught it.
        """
        result, _ = payload(self.repo.root, "--pr", "860", *self.ref)
        located = {(row["source"], row["path"], row["line"]) for row in result["findings"]}
        self.assertIn(("body", ".github/scripts/run-tests.sh", 175), located)
        self.assertNotIn("?", {row["path"] for row in result["findings"]})

    def test_a_finding_stated_only_in_the_file_summary_table_is_read(self):
        """#856's critical finding sits in a table cell, where a reader skims.

        This shape was found because #880, reviewed months later, reported clean
        through an earlier version of this file while carrying three real
        findings in exactly this place. The item's own body names #856's garbled
        docstring as a real finding nobody filed; it is here, twice, because the
        reviewer stated it inline *and* in the table.
        """
        result, _ = payload(self.repo.root, "--pr", "856", *self.ref)
        body = [row for row in result["findings"] if row["source"] == "body"]
        self.assertEqual(len(body), 4)
        self.assertIn(
            ("bin/sd_work.py", "Critical: update the command inventory guard for this scoped exception"),
            {(row["path"], row["text"]) for row in body},
        )

    def test_a_body_that_states_findings_in_no_known_shape_is_not_clean(self):
        """#858 states two voted findings in prose and nowhere this parser reads.

        The guard that keeps this file honest about its own blind spots. #858
        has no inline comment, no suppressed section, no outstanding list and no
        vote-marked table row -- and it is not clean, because its own summary
        sentence says it is not. Reporting zero here is the defect, not the
        absence of a parser.
        """
        self.assertEqual(ROUND["858"]["comments"], [])
        result, code = payload(self.repo.root, "--pr", "858", "--check", *self.ref)
        self.assertEqual(code, 1)
        self.assertEqual(len(result["findings"]), 2)
        self.assertEqual({row["path"] for row in result["findings"]}, {"?"})

    def test_a_reply_is_an_answer_and_not_a_finding(self):
        """#860 carries six inline rows: three findings and three replies to them.

        Counting rows reports twelve inline findings across the round where
        there are nine. A gate that inflates its own alarm is a gate that gets
        turned off, so the replies are separated rather than counted.
        """
        result, _ = payload(self.repo.root, "--pr", "860", *self.ref)
        inline = [row for row in result["findings"] if row["source"] == "inline"]
        self.assertEqual(len(ROUND["860"]["comments"]), 6)
        self.assertEqual(len(inline), 3)
        self.assertEqual(sum(row["replies"] for row in inline), 3)

    def test_an_answered_thread_whose_fix_never_landed_still_reads_unread(self):
        """The state that shipped three defects, now printable.

        Every one of #860's three inline findings has a reply, each reply is
        truthful, and each names 371495dc -- which is not an ancestor of main.
        The threads read as resolved. Nothing had ever compared the two.
        """
        result, _ = payload(self.repo.root, "--pr", "860", *self.ref)
        answered = [row for row in result["findings"] if row.get("replies")]
        self.assertEqual(len(answered), 3)
        self.assertTrue(all(row["verdict"] == "unread" for row in answered))


class ThePrStateCountUsesTheSameReader(unittest.TestCase):
    """`sd-pr-state`'s `review findings:` line counts what this module finds.

    It used to count `Suppressed comments (N)` and nothing else, which is one
    of the three shapes. #880 stated three real findings in cells of its
    file-summary table and that line printed nothing, on the surface the
    integrator actually reads before merging.
    """

    #: #880's review body, reduced to the table that carried its findings.
    BODY = (
        "Three unresolved moderate findings affect duplicate fields.\n\n"
        "| File | Summary |\n|---|---|\n"
        "| `bin/sd-status` | Uses row-aware contribution rendering. |\n"
        "| `bin/sd_work.py` | Uses row-aware rendering. Moderate finding (2 votes): "
        "field orders still differ between surfaces. Moderate finding (1 vote): "
        "dictionary results can print `revision` twice. |\n"
        "| `bin/sd_lib.py` | Adds `display_fields`. Moderate finding (3 votes): "
        "duplicate fields in `order` are rendered twice. |\n"
    )

    def test_findings_stated_only_in_a_table_reach_the_count(self):
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        counted = pr_state.review_findings(
            [{"body": self.BODY, "author": {"login": "copilot-pull-request-reviewer"}}]
        )
        self.assertEqual(counted["in_body"], 3)
        self.assertEqual(counted["reviewers"], ["copilot-pull-request-reviewer"])

    def test_review_bodies_are_actually_asked_for(self):
        """The count is only as good as the field that carries it.

        `review_findings` reads `reviews[].body`. If `reviews` ever left
        `PR_FIELDS`, `gh pr list` would stop returning it, every body would be
        empty and every pull request would report clean -- the item's defect,
        reintroduced by a one-word edit in a tuple nothing else guards.
        """
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        self.assertIn("reviews", pr_state.PR_FIELDS)

    def test_every_captured_review_carries_the_body_the_parser_reads(self):
        """The fixture is only evidence if it holds what the live call returns."""
        for number, record in ROUND.items():
            for review in record["reviews"]:
                with self.subTest(pr=number):
                    self.assertIn("body", review)
                    self.assertIsInstance(review["body"], str)

    def test_both_halves_reach_ids_and_an_unreadable_half_says_so(self):
        """`ids` is body plus inline, and the reason the inline half failed.

        `in_body` stays the count this file has always printed. `ids` is what
        `sd-status` walks: dropping the inline half there would restore the
        original defect in the one place that now reports it, with a pull
        request reading clear while its inline comments sat unread. And when
        the inline call fails, `unreadable` carries why -- a partial count
        presented as a total is this item's defect exactly, so the sentence has
        to survive the trip rather than being swallowed into a smaller number.
        """
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        pull = {"reviews": [{"body": self.BODY, "author": {"login": "bot"}}], "number": 880}
        original = pr_state.inline_findings
        try:
            pr_state.inline_findings = lambda *a: ([], {}, "gh api exited 1")
            blind = pr_state._findings(pull, REPO_ROOT, "acme/widget")
            pr_state.inline_findings = lambda *a: (["inline-id"], {"inline-id": ["abc"]}, "")
            whole = pr_state._findings(pull, REPO_ROOT, "acme/widget")
        finally:
            pr_state.inline_findings = original
        self.assertEqual(blind["unreadable"], "gh api exited 1")
        self.assertEqual(whole["unreadable"], "")
        self.assertEqual(whole["in_body"], 3)
        self.assertEqual(len(whole["ids"]), 4)
        self.assertIn("inline-id", whole["ids"])
        self.assertEqual(whole["stated"]["inline-id"], ["abc"],
                         "the commits a finding was stated against survive the union")

    def test_a_re_review_does_not_double_what_it_restates(self):
        """Two surfaces, one fact. A restated finding is one finding.

        A reviewer that runs again after a push restates what still stands,
        and #860 carries four reviews for exactly that reason. `findings`
        deduplicates by id across every review it is given, in one pass; a
        caller that instead loops and calls it once per review gets that
        deduplication per review and none across them, so this surface and
        `sd-review-ack` report different totals for the same pull request.

        The body here is #859's real review body from the capture. The only
        construction is that it appears twice, which is what a second pass on
        an unchanged finding produces. Measured before the fix: 8 against 4.
        """
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        once = ROUND["859"]["reviews"][0]
        again = [once, dict(once)]
        truth = ack.findings(859, again, [])
        stated = pr_state.review_findings(again, 859)
        self.assertEqual(len(ack.findings(859, [once], [])), 4)
        self.assertEqual(len(truth), 4)
        self.assertEqual(stated["in_body"], len(truth))
        self.assertEqual(stated["ids"], [row["id"] for row in truth])
        self.assertEqual(stated["reviewers"], ["copilot-pull-request-reviewer[bot]"])

    def test_no_pull_request_in_the_round_is_counted_twice_over(self):
        """The same question across all twelve, enumerated rather than sampled."""
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        for number, record in ROUND.items():
            with self.subTest(pr=number):
                reviews, comments = record["reviews"], record["comments"]
                body = pr_state.review_findings(reviews, int(number))["ids"]
                inline = [row["id"] for row in ack.findings(int(number), [], comments)]
                union = list(dict.fromkeys(body + inline))
                self.assertEqual(len(set(union)), len(union))
                self.assertEqual(len(union), len(ack.findings(int(number), reviews, comments)))

    def test_the_grouped_markers_are_named_for_the_report(self):
        """`sd-status` hedges its count from this list, not from a second parser.

        The row says "at least N" only because the ids that cover an unknown
        number travel with the count. A report that decided that for itself
        would be the two-surfaces-one-fact drift again, one field along.
        """
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        body = ("| File | Summary |\n|---|---|\n"
                "| `a.py` | Moderate findings (3 votes each): one and another. |\n"
                "| `b.py` | Moderate finding (2 votes): a single one. |\n")
        reviews = [{"body": body, "author": {"login": "bot"}}]
        stated = pr_state.review_findings(reviews, 1)
        rows = ack.findings(1, reviews, [])
        self.assertEqual(len(stated["ids"]), 2)
        self.assertEqual(len(stated["indeterminate"]), 1)
        self.assertEqual(stated["indeterminate"],
                         [row["id"] for row in rows if row["indeterminate"]])

    def test_a_comment_response_that_is_not_a_list_is_refused(self):
        """`gh` exits 0 and returns an error object. That is not zero findings.

        The third time this shape has come up in this item, after `gh` missing
        and after a capture that is not JSON. An error object or a null
        iterates as nothing, the row prints clean, and the gate passes hardest
        on the day GitHub is having trouble.
        """
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        original = pr_state.gh_json
        try:
            for payload in ({"message": "API rate limit exceeded"}, None, "nope"):
                with self.subTest(payload=type(payload).__name__):
                    pr_state.gh_json = lambda *a, _p=payload: (_p, "")
                    ids, read_at, reason = pr_state.inline_findings(REPO_ROOT, "acme/widget", 7)
                    self.assertEqual((ids, read_at), ([], {}))
                    self.assertIn("not a list of comments", reason)
                    self.assertIn(type(payload).__name__, reason)
        finally:
            pr_state.gh_json = original

    def test_a_real_comment_list_is_read_through_the_shared_reader(self):
        """The success half, so the refusal above is not the only path covered."""
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        comments = ROUND["860"]["comments"]
        original = pr_state.gh_json
        try:
            pr_state.gh_json = lambda *a: (comments, "")
            ids, read_at, reason = pr_state.inline_findings(REPO_ROOT, "acme/widget", 860)
        finally:
            pr_state.gh_json = original
        self.assertEqual(reason, "")
        self.assertEqual(sorted(read_at), sorted(ids), "every inline id carries the commits it was stated at")
        # Six inline rows on #860: three findings and three replies. The reader
        # decides which is which, and this asserts it was asked.
        self.assertEqual(len(comments), 6)
        self.assertEqual(ids, [row["id"] for row in ack.findings(860, [], comments)])
        self.assertEqual(len(ids), 3)

    def test_a_body_with_nothing_in_it_still_counts_nothing(self):
        """The clean case stays clean: the line prints only on a non-zero count."""
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        counted = pr_state.review_findings([{"body": "Looks good to me.", "author": {"login": "bot"}}])
        self.assertEqual(counted["in_body"], 0)
        self.assertEqual(counted["reviewers"], [])


class BothOrdersOfATableCell(unittest.TestCase):
    """The reviewer writes a finding two ways round, and both are real.

    The suffix row below is copied from the review of the pull request that
    added this file. An earlier version of the parser knew only the prefix
    order and gave that review the right count with mangled text -- "pagination
    handling: ; fail-" -- which reads like a finding somebody looked at. A
    wrong finding that looks read is worse than one that does not parse.
    """

    PREFIX = (
        "| `bin/sd_work.py` | Uses row-aware rendering. Moderate finding (2 votes): "
        "field orders still differ between surfaces. Moderate finding (1 vote): "
        "dictionary results can print `revision` twice. |\n"
    )
    SUFFIX = (
        "| `bin/sd-review-ack` | Implements finding parsing, acknowledgement storage, "
        "and gate verdicts. Findings: pagination handling (moderate, 3 votes); "
        "fail-closed behavior on API errors (critical, 3 votes); unknown dispositions "
        "(critical, 1 vote). |\n"
    )

    def test_the_severity_leads_and_the_text_follows_a_colon(self):
        rows = ack._table(880, self.PREFIX, "bot")
        self.assertEqual(
            [(row["path"], row["text"]) for row in rows],
            [("bin/sd_work.py", "Moderate finding: field orders still differ between surfaces"),
             ("bin/sd_work.py", "Moderate finding: dictionary results can print `revision` twice")],
        )

    def test_the_text_leads_and_the_severity_sits_in_the_marker(self):
        rows = ack._table(883, self.SUFFIX, "bot")
        self.assertEqual(
            [(row["path"], row["text"]) for row in rows],
            [("bin/sd-review-ack", "moderate: pagination handling"),
             ("bin/sd-review-ack", "critical: fail-closed behavior on API errors"),
             ("bin/sd-review-ack", "critical: unknown dispositions")],
        )

    def test_the_summary_prose_is_not_mistaken_for_the_first_finding(self):
        """`Implements finding parsing...` is what changed, not what is wrong."""
        first = ack._table(883, self.SUFFIX, "bot")[0]
        self.assertNotIn("Implements", first["text"])
        self.assertNotIn("acknowledgement storage", first["text"])
        # The label goes too, and not only the prose before it. Cutting at the
        # last sentence would leave `Findings: pagination handling`, which is
        # the reviewer's heading pretending to be part of the finding.
        self.assertNotIn("Findings", first["text"])
        self.assertEqual(first["text"], "moderate: pagination handling")

    def test_a_marker_that_says_each_covers_a_number_it_does_not_state(self):
        """#885's own review: two markers, four findings, and no split stated.

        `Moderate findings (3 votes each)` is the reviewer saying "more than
        one" in its own words. Where they split is not stated, and splitting on
        "and" or on a semicolon would be this parser guessing. So the row keeps
        its whole text and is marked indeterminate, and every count built on it
        says "at least". Counting it flat as one is the worse of the two
        errors: an undercount on a gate reads as progress.
        """
        rows = ack.findings(885, [{"body": (
            "| File | Summary |\n|---|---|\n"
            "| `bin/sd-pr-state` | Collects ids. Moderate findings (3 votes each): "
            "deduplicate repeated IDs and reject non-list comment responses. "
            "Nit findings (1 vote each): add coverage and update the contract. |\n"
        ), "author": {"login": "bot"}}], [])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["indeterminate"] for row in rows))
        self.assertIn("deduplicate repeated IDs", rows[0]["text"])
        self.assertIn("reject non-list", rows[0]["text"])
        self.assertEqual(ack.at_least(rows, len(rows)), "at least 2")

    def test_a_singular_marker_is_counted_flat(self):
        """The control. Hedging every count would make the hedge meaningless."""
        rows = ack.findings(880, [{"body": (
            "| File | Summary |\n|---|---|\n"
            "| `bin/sd_work.py` | Uses row-aware rendering. Moderate finding (2 votes): "
            "field orders still differ between surfaces. Moderate finding (1 vote): "
            "dictionary results can print `revision` twice. |\n"
            "| `bin/sd_lib.py` | Adds `display_fields`. Moderate finding (3 votes): "
            "duplicate fields in `order` are rendered twice. |\n"
        ), "author": {"login": "bot"}}], [])
        self.assertEqual(len(rows), 3)
        self.assertFalse(any(row["indeterminate"] for row in rows))
        self.assertEqual(ack.at_least(rows, len(rows)), "3")

    def test_the_marker_is_the_only_evidence_of_plurality_that_is_used(self):
        """`N and M votes` is the reviewer's other way of saying more than one.

        And a plural `Findings:` label is *not* used as evidence: the reviewer
        writes that label in front of a single finding too, so reading it as
        plural would hedge counts that are exact.
        """
        self.assertTrue(ack.PLURAL_MARKER.search("(2 and 1 votes)"))
        self.assertTrue(ack.PLURAL_MARKER.search("(1 vote each)"))
        self.assertIsNone(ack.PLURAL_MARKER.search("(3 votes)"))
        rows = ack.findings(1, [{"body": (
            "| File | Summary |\n|---|---|\n"
            "| `a.py` | Findings: the order differs (2 votes). |\n"
        ), "author": {"login": "bot"}}], [])
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["indeterminate"])

    def test_an_acknowledgement_survives_a_row_becoming_indeterminate(self):
        """The flag is not in the id, so an answer already on record still counts."""
        body = ("| File | Summary |\n|---|---|\n"
                "| `a.py` | Moderate findings (3 votes each): one thing and another. |\n")
        row = ack.findings(1, [{"body": body, "author": {"login": "bot"}}], [])[0]
        self.assertTrue(row["indeterminate"])
        flat = ack.finding_id(1, row["source"], row["path"], row["line"], row["text"])
        self.assertEqual(row["id"], flat)

    def test_a_label_with_no_sentence_before_it_is_still_stripped(self):
        """The period fallback cannot help when the cell opens with the label."""
        rows = ack._table(883, "| `a.py` | Findings: only this one (moderate, 1 vote). |\n", "bot")
        self.assertEqual([row["text"] for row in rows], ["moderate: only this one"])


class ASuppressedHeadingIsAnAssertion(RoundFixture):
    """The reviewer's own count is checked, not trusted."""

    def test_a_heading_promising_more_than_it_lists_still_yields_findings(self):
        rows = ack._suppressed(1, "### Suppressed comments (3)\n\n**a.py:1**\n* only one\n", "bot")
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(1 for row in rows if row["path"] == "?"), 2)

    def test_an_unparsed_finding_is_unread_rather_than_absent(self):
        rows = ack._suppressed(1, "### Suppressed comments (2)\n\n(a format nobody planned for)\n", "bot")
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row["id"] for row in rows}), 2)


class AFixIsSatisfiedByLanding(RoundFixture):
    """`Fixed in <sha>` is a claim, and this is the check nobody ran."""

    def _first(self, number: int) -> str:
        result, _ = payload(self.repo.root, "--pr", str(number), *self.ref)
        return result["findings"][0]["id"]

    def test_a_commit_that_never_reached_the_branch_is_not_a_fix(self):
        """The #860 shape: a real commit, a truthful reply, a shipped defect."""
        found = self._first(860)
        result, code = payload(
            self.repo.root, "--pr", "860", "--check",
            "--ack", found, "--fixed", self.repo.stranded, *self.ref,
        )
        row = next(r for r in result["findings"] if r["id"] == found)
        self.assertEqual(row["verdict"], "fix-not-landed")
        self.assertEqual(code, 1)

    def test_a_commit_nobody_has_cannot_be_acknowledged_at_all(self):
        """Refused when it is recorded, rather than recorded and disbelieved."""
        done = run(self.repo.root, "--pr", "860", "--ack", self._first(860),
                   "--fixed", "0" * 40, *self.ref)
        self.assertEqual(done.returncode, 2)
        self.assertIn("names no commit in this repository", done.stderr)

    def test_a_record_naming_a_vanished_commit_reads_as_fix_missing(self):
        """The verdict still exists, for a store written before a commit was lost."""
        found = self._first(860)
        ack.write_store(self.repo.root, {found: {
            "pr": 860, "disposition": "fixed", "commit": "0" * 40, "reason": "",
            "path": "x", "line": 1, "at": "2026-09-12T00:00:00+00:00",
        }})
        result, code = payload(self.repo.root, "--pr", "860", "--check", *self.ref)
        row = next(r for r in result["findings"] if r["id"] == found)
        self.assertEqual(row["verdict"], "fix-missing")
        self.assertEqual(code, 1)

    def test_a_branch_name_is_recorded_as_the_commit_it_meant_today(self):
        """`--fixed main` must not record a name whose meaning moves."""
        found = self._first(860)
        payload(self.repo.root, "--pr", "860", "--ack", found, "--fixed", "main", *self.ref)
        record = ack.read_store(self.repo.root)[0][found]
        self.assertEqual(record["commit"], self.repo.landed)
        self.assertEqual(record["cited"], "main")

    def test_a_commit_on_the_branch_satisfies_the_finding(self):
        found = self._first(860)
        result, _ = payload(
            self.repo.root, "--pr", "860",
            "--ack", found, "--fixed", self.repo.landed, *self.ref,
        )
        row = next(r for r in result["findings"] if r["id"] == found)
        self.assertEqual(row["verdict"], "landed")

    def test_findings_answered_only_by_fixes_that_never_landed_stay_red(self):
        """What counts as answered, asserted as a set rather than per verdict.

        Every finding on #860 acknowledged, every acknowledgement truthful,
        every cited commit still off the branch. Widening `SATISFIED` by one
        entry turns this tool back into the thing it replaced, and no other
        test here can see that edit: each of them names one verdict and checks
        the verdict, not whether the gate treats it as an answer.
        """
        result, _ = payload(self.repo.root, "--pr", "860", *self.ref)
        for row in result["findings"]:
            payload(self.repo.root, "--pr", "860", "--ack", row["id"],
                    "--fixed", self.repo.stranded, *self.ref)
        after, code = payload(self.repo.root, "--pr", "860", "--check", *self.ref)
        self.assertEqual(len(after["unsatisfied"]), len(result["findings"]))
        self.assertEqual(code, 1)

    def test_a_dismissal_without_a_reason_is_refused(self):
        done = run(self.repo.root, "--pr", "860", "--ack", self._first(860), "--dismiss", "   ")
        self.assertEqual(done.returncode, 2)
        self.assertIn("reason", done.stderr)


class TheControl(RoundFixture):
    """Acknowledging clears what was acknowledged, and nothing else."""

    def test_clearing_one_pull_request_leaves_the_rest_red(self):
        """#865 carries six findings. Clear all six; thirty-five must remain."""
        result, _ = payload(self.repo.root, "--pr", "865", *self.ref)
        ids = [row["id"] for row in result["findings"]]
        self.assertEqual(len(ids), 6)
        for found in ids:
            payload(self.repo.root, "--pr", "865", "--ack", found,
                    "--dismiss", "read, and stale against the merged head", *self.ref)

        cleared, code = payload(self.repo.root, "--pr", "865", "--check", *self.ref)
        self.assertEqual(cleared["unsatisfied"], [])
        self.assertEqual(code, 0, "acknowledging every finding must let the gate pass")

        whole, code = payload(self.repo.root, "--check", *self.ref)
        self.assertEqual(len(whole["findings"]), 41)
        self.assertEqual(len(whole["unsatisfied"]), 35)
        self.assertEqual(code, 1)
        self.assertNotIn(865, {row["pr"] for row in whole["unsatisfied"]})

    def test_a_captured_round_with_an_explicit_null_is_read_as_empty(self):
        """`"reviews": null` is not the same absence as a missing key.

        `.get("reviews", ())` hands back None for a key present with a JSON
        null, where `or ()` hands back the empty tuple; both call sites use the
        latter. This test does **not** discriminate the two, and saying so is
        the point: `findings` guards its own arguments with `or []`, so the
        run survives either way today. What the test pins is the behaviour --
        a null round reads as empty and the gate exits 0 -- which stays true if
        that internal guard is ever removed, and which is the case a fixture
        can really produce.
        """
        odd = pathlib.Path(self.stack.name) / "null.json"
        odd.write_text(json.dumps({"pull_requests": {"7": {"reviews": None, "comments": None}}}))
        done = subprocess.run(
            [sys.executable, str(BIN / "sd-review-ack"), "--from", str(odd), "--check", *self.ref],
            cwd=str(self.repo.root), capture_output=True, text=True, check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("no review findings", done.stdout)

    def test_a_round_that_could_not_be_read_fails_the_gate(self):
        """`gh` missing is not evidence that a pull request is clean.

        The gate passing when it cannot read is the gate passing hardest on the
        day GitHub is having trouble. Without `--check` this is a report and
        still exits 0; with it, the run refuses.
        """
        # `git` stays reachable and `gh` does not: the tool must still know
        # which repository it is in, and must not be able to read GitHub.
        bare = pathlib.Path(self.stack.name) / "no-gh"
        bare.mkdir(exist_ok=True)
        (bare / "git").symlink_to(shutil.which("git") or "/usr/bin/git")
        empty = dict(os.environ, PATH=str(bare))
        base = [sys.executable, str(BIN / "sd-review-ack"), *self.ref]
        report = subprocess.run(base, cwd=str(self.repo.root), capture_output=True,
                                text=True, check=False, env=empty)
        gated = subprocess.run([*base, "--check"], cwd=str(self.repo.root),
                               capture_output=True, text=True, check=False, env=empty)
        self.assertEqual(report.returncode, 0)
        self.assertEqual(gated.returncode, 1)
        self.assertIn("unavailable:", report.stdout)
        self.assertIn("nothing was read, so nothing is acknowledged", report.stdout)

    def test_an_endpoint_that_answers_with_something_other_than_a_list_stops_the_round(self):
        """The live half of the same refusal, for both endpoints it reads.

        `payload or []` used to stand here and turned an error object into a
        clean pull request: a rate-limit body is a dict, iterates as nothing,
        and the pull request prints with no findings on it. `pr list` above
        already refused a non-list; these two did not.

        Driven through a real `gh` on `PATH` rather than a patched module,
        because `sd_lib.sibling` loads a fresh module object on every call --
        an in-process patch here would leave the code under test reading the
        real GitHub and the test passing for the wrong reason.
        """
        for bad in ("reviews", "comments"):
            with self.subTest(endpoint=bad):
                rounds, reason = self._round_with_fake_gh(bad)
                self.assertEqual(rounds, {})
                self.assertIn(f"not a list of {bad}", reason)
                self.assertIn("dict", reason)

    def test_a_live_round_that_reads_two_real_lists_is_not_refused(self):
        """The control for the refusal above: valid lists still produce a round."""
        rounds, reason = self._round_with_fake_gh(None)
        self.assertEqual(reason, "")
        self.assertEqual(sorted(rounds), [7])
        self.assertEqual(rounds[7], {"reviews": [], "comments": []})

    #: A `gh` that authenticates, lists one pull request, and answers every
    #: API path with an empty list -- except the one named, which answers with
    #: the rate-limit object GitHub really returns.
    FAKE_GH = """#!/bin/sh
case "$*" in
  *'auth status'*) exit 0 ;;
  *'pr list'*) echo '[{"number":7}]' ;;
%s  *) echo '[]' ;;
esac
"""

    def _round_with_fake_gh(self, broken: str | None) -> tuple[dict, str]:
        """`live_round` against a `gh` that answers one endpoint with an object."""
        if "origin" not in self.repo._git("remote"):
            self.repo._git("remote", "add", "origin", "https://github.com/acme/widget.git")
        bin_dir = pathlib.Path(self.stack.name) / f"fake-{broken or 'ok'}"
        bin_dir.mkdir()
        (bin_dir / "git").symlink_to(shutil.which("git") or "/usr/bin/git")
        arm = f"""  *{broken}*) echo '{{"message":"API rate limit exceeded"}}' ;;\n""" if broken else ""
        fake = bin_dir / "gh"
        fake.write_text(self.FAKE_GH % arm, encoding="utf-8")
        fake.chmod(0o755)
        return self._live_round_under(bin_dir)

    def _live_round_under(self, bin_dir: pathlib.Path) -> tuple[dict, str]:
        """`live_round` in a subprocess, so `PATH` is the only thing that changed."""
        script = (
            "import json,pathlib,sys;"
            f"sys.path.insert(0, {str(BIN)!r});"
            "import sd_lib;"
            "m = sd_lib.sibling('a', 'sd-review-ack');"
            f"r, why, _ = m.live_round(pathlib.Path({str(self.repo.root)!r}), None, 10);"
            "print(json.dumps({'rounds': {str(k): v for k, v in r.items()}, 'why': why}))"
        )
        done = subprocess.run(
            [sys.executable, "-c", script], cwd=str(self.repo.root), text=True,
            capture_output=True, check=False,
            env=dict(os.environ, PATH=str(bin_dir), PYTHONDONTWRITEBYTECODE="1"),
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        return {int(k): v for k, v in payload["rounds"].items()}, payload["why"]

    def test_a_named_pull_request_the_capture_lacks_is_an_error(self):
        """Not "no findings": the file never held it, so the question is wrong."""
        done = run(self.repo.root, "--pr", "9999", "--check", *self.ref)
        self.assertEqual(done.returncode, 2)
        self.assertIn("holds no pull request 9999", done.stderr)

    def test_an_empty_round_passes_the_gate(self):
        """The gate is not green-by-default and not red-by-default either."""
        empty = pathlib.Path(self.stack.name) / "empty.json"
        empty.write_text(json.dumps({"pull_requests": {"1": {"reviews": [], "comments": []}}}))
        done = subprocess.run(
            [sys.executable, str(BIN / "sd-review-ack"), "--from", str(empty), "--check", *self.ref],
            cwd=str(self.repo.root), capture_output=True, text=True, check=False,
        )
        self.assertEqual(done.returncode, 0)
        self.assertIn("no review findings", done.stdout)


class TheRecord(RoundFixture):
    """Where an acknowledgement lives, and what a broken one is worth."""

    def test_the_record_is_outside_the_tree(self):
        """An acknowledgement in the tree would change the head it acknowledges."""
        result, _ = payload(self.repo.root, "--pr", "863", *self.ref)
        found = result["findings"][0]["id"]
        payload(self.repo.root, "--pr", "863", "--ack", found, "--dismiss", "read", *self.ref)
        path = ack.store_path(self.repo.root)
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent.name, ".git")
        self.assertEqual(
            subprocess.run(["git", "status", "--porcelain"], cwd=str(self.repo.root),
                           capture_output=True, text=True, check=True).stdout,
            "",
            "acknowledging must leave the working tree clean",
        )

    def test_an_unreadable_record_reads_as_nothing_acknowledged(self):
        """A corrupt store makes the gate refuse, never pass -- and says so."""
        ack.store_path(self.repo.root).write_text("{not json")
        result, code = payload(self.repo.root, "--check", *self.ref)
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", result["store_error"])
        self.assertIn("record unreadable", run(self.repo.root, *self.ref).stdout)

    def test_a_disposition_this_version_does_not_define_is_not_an_acknowledgement(self):
        """A store written by a later version is not honoured by guessing."""
        result, _ = payload(self.repo.root, "--pr", "863", *self.ref)
        found = result["findings"][0]["id"]
        ack.write_store(self.repo.root, {found: {
            "pr": 863, "disposition": "wontfix", "commit": None, "reason": "because",
            "path": "x", "line": 1, "at": "2026-09-12T00:00:00+00:00",
        }})
        result, code = payload(self.repo.root, "--pr", "863", "--check", *self.ref)
        self.assertEqual(result["findings"][0]["verdict"], "unknown-disposition")
        self.assertEqual(code, 1)

    def test_a_disposition_the_caller_invents_is_refused_at_the_write(self):
        """The read side above refuses one it finds; this refuses one offered.

        Unreachable from the command line, where argparse offers `--fixed` and
        `--dismiss` and nothing else, and reachable from every library caller --
        `sd-status` among them. A guard no test can reach is a guard that gets
        deleted as dead code, and this one is what keeps an invented
        disposition out of the record rather than merely unhonoured in it.
        """
        result, _ = payload(self.repo.root, "--pr", "863", *self.ref)
        found = [row for row in ack.findings(
            863, ROUND["863"]["reviews"], ROUND["863"]["comments"],
        ) if row["id"] == result["findings"][0]["id"]][0]
        with self.assertRaises(ack.UsageError) as raised:
            ack.acknowledge(self.repo.root, found, "wontfix", "because")
        self.assertIn("fixed or dismissed", str(raised.exception))
        self.assertEqual(ack.read_store(self.repo.root)[0], {})

    def test_a_capture_that_is_not_json_is_refused_rather_than_read_as_empty(self):
        """`--from` pointed at a broken file must not report a clean round.

        The live path refuses when `gh` cannot be reached; this is the same
        claim for the replay path, and it is the one a CI job would hit -- a
        truncated artefact download reads as valid-and-empty unless something
        says otherwise.
        """
        broken = pathlib.Path(self.stack.name) / "torn.json"
        broken.write_text('{"pull_requests": {"7": {"reviews"', encoding="utf-8")
        done = run(self.repo.root, "--from", str(broken), "--check")
        self.assertEqual(done.returncode, 2)
        self.assertIn("is not valid JSON", done.stderr)

    def test_the_store_is_replaced_in_one_step(self):
        """A torn write would read as empty and discard real acknowledgements."""
        path = ack.store_path(self.repo.root)
        ack.write_store(self.repo.root, {"a": {"pr": 1}})
        leftovers = [p.name for p in path.parent.glob(f".{ack.STORE_NAME}.*")]
        self.assertEqual(leftovers, [])
        self.assertEqual(json.loads(path.read_text())["acknowledgements"], {"a": {"pr": 1}})

    def test_an_id_that_names_no_finding_is_a_usage_error(self):
        done = run(self.repo.root, "--pr", "863", "--ack", "deadbeefcafe", "--dismiss", "read")
        self.assertEqual(done.returncode, 2)
        self.assertIn("no finding here has the id", done.stderr)

    def test_an_unreadable_record_refuses_an_acknowledgement_and_keeps_its_bytes(self):
        """review-914 B1: `--ack` on a torn store replaced it, dismissals and all.

        A store cut short still holds acknowledgements somebody wrote. Reading
        it as empty is the safe direction for the gate; writing that emptiness
        back is the unsafe one, which `record_answers` already refuses.
        """
        result, _ = payload(self.repo.root, "--pr", "863", *self.ref)
        found = result["findings"][0]["id"]
        path = ack.store_path(self.repo.root)
        ack.write_store(self.repo.root, {name: {
            "pr": 1, "disposition": "dismissed", "commit": None, "reason": f"real reason {name}",
            "path": "x", "line": 1, "at": "2026-09-12T00:00:00+00:00",
        } for name in ("aaaa00000001", "aaaa00000002")})
        path.write_bytes(path.read_bytes()[:-4])
        torn = path.read_bytes()
        done = run(self.repo.root, "--pr", "863", "--ack", found, "--dismiss", "new", *self.ref)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("repair or move it first", done.stderr)
        self.assertEqual(path.read_bytes(), torn)

    def test_an_unreadable_record_does_not_ask_for_an_acknowledgement(self):
        """The listing points at the repair, not at the write that `--ack` refuses."""
        ack.store_path(self.repo.root).write_text("{not json")
        out = run(self.repo.root, "--pr", "863", *self.ref).stdout
        self.assertIn("record unreadable", out)
        self.assertIn("repair or move the record first", out)
        self.assertNotIn("acknowledge each", out)
        control = tempfile.TemporaryDirectory()
        self.addCleanup(control.cleanup)
        self.assertIn("acknowledge each", run(Repo(control).root, "--pr", "863", *self.ref).stdout)


class Branch:
    """A repository holding the two commits an automatic record has to tell apart.

    One commit answers a finding and reaches `main`. One commit answers a
    different finding and never leaves its own branch -- the 371495dc shape
    again, in the automatic path this time rather than the typed one.
    """

    FILES = ("bin/thing.py", "bin/other.py", "docs/untouched.md")

    def __init__(self, stack: tempfile.TemporaryDirectory) -> None:
        self.root = pathlib.Path(stack.name) / "branch"
        self.root.mkdir()
        self._git("init", "-q", "--initial-branch=main", ".")
        for name in self.FILES:
            self._write(name, "as the reviewer read it\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "the state the reviewer read")
        self.reviewed = self._git("rev-parse", "HEAD")
        self._git("checkout", "-q", "-b", "stranded")
        self._write("bin/other.py", "answered, and never pushed anywhere that lands\n")
        self._git("commit", "-qam", "answer the other thing")
        self.stranded = self._git("rev-parse", "HEAD")
        self._git("checkout", "-q", "main")
        self._write("bin/thing.py", "answered\n")
        self._git("commit", "-qam", "answer the thing")
        self.landed = self._git("rev-parse", "HEAD")

    def _write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _git(self, *args: str) -> str:
        done = subprocess.run(["git", *GIT_IDENTITY, *args], cwd=str(self.root),
                              capture_output=True, text=True, check=True)
        return done.stdout.strip()


class APushIsEvidenceOrItIsNothing(unittest.TestCase):
    """What an automatic `fixed` record may be written from.

    `sd-status` grew a row for a pull request carrying a review finding nobody
    has answered, and nothing on the way to a merge wrote an acknowledgement,
    so the store stayed empty and the row fired on every reviewed pull request
    forever. The fix is a record written by the merge path -- and a record the
    merge path writes for *every* finding is worse than the noise it replaces,
    because it reads exactly like a finding somebody answered.

    So the automatic record is bound to the one thing a push can prove: a
    commit that did not exist when the reviewer read the file, that changes the
    file the finding names, reachable from the head being pushed. Every test
    here is a way that binding could come loose.
    """

    #: The file-summary table the reviewer actually writes, one finding per
    #: file. Three files; the push touches one of them.
    REVIEW = (
        "| File | Summary |\n"
        "|---|---|\n"
        "| `bin/thing.py` | Moderate finding (2 votes): the thing is wrong. |\n"
        "| `bin/other.py` | Moderate finding (1 vote): the other thing is wrong. |\n"
        "| `docs/untouched.md` | Moderate finding (1 vote): nobody went near this. |\n"
    )

    def setUp(self) -> None:
        self.stack = tempfile.TemporaryDirectory()
        self.addCleanup(self.stack.cleanup)
        self.branch = Branch(self.stack)

    def rows(self, commit: str | None = None) -> list[dict]:
        return ack.findings(7, [{
            "author": "bot",
            "commit_id": self.branch.reviewed if commit is None else commit,
            "body": self.REVIEW,
        }], [])

    def verdicts(self) -> dict[str, str]:
        """Every finding's path and what the record now says about it."""
        store, _ = ack.read_store(self.branch.root)
        return {row["path"]: ack.id_verdict(self.branch.root, row["id"], store, "main")
                for row in self.rows()}

    def test_a_commit_that_changed_the_file_answers_the_finding(self) -> None:
        """The whole point: the push carried a fix, so the finding is answered."""
        written, _ = ack.record_answers(self.branch.root, self.rows(), "main")
        self.assertEqual([row["path"] for row in written], ["bin/thing.py"])
        self.assertEqual(written[0]["disposition"], "fixed")
        self.assertEqual(written[0]["commit"], self.branch.landed)
        self.assertEqual(self.verdicts()["bin/thing.py"], "landed")

    def test_a_finding_on_a_file_the_push_never_touched_is_not_answered(self) -> None:
        """The failure mode this record is one loose predicate away from.

        A record written for every finding on the pull request satisfies the
        gate and says nothing, which is the state the gate was built to end.
        Two of these three files are untouched by anything reachable from
        `main` after the review, and both must still read `unread`.
        """
        ack.record_answers(self.branch.root, self.rows(), "main")
        self.assertEqual(self.verdicts()["docs/untouched.md"], "unread")
        self.assertEqual(self.verdicts()["bin/other.py"], "unread")
        self.assertEqual(len(ack.read_store(self.branch.root)[0]), 1)

    def test_pushing_is_not_landing(self) -> None:
        """An answered finding whose answer never reached `main` stays open.

        The record is written from the push, and what it is worth is still
        decided by `fix_verdict` against the branch the work lands on. Nothing
        here is allowed to shortcut that.
        """
        written, _ = ack.record_answers(self.branch.root, self.rows(), "stranded")
        self.assertEqual([row["path"] for row in written], ["bin/other.py"])
        self.assertEqual(self.verdicts()["bin/other.py"], "fix-not-landed")
        self.assertEqual(
            ack.unacknowledged(self.branch.root, [row["id"] for row in self.rows()], "main"),
            [row["id"] for row in self.rows()],
            "a push that has not landed answers nothing the gate counts",
        )

    def test_a_dismissal_is_never_overwritten_by_a_later_push(self) -> None:
        """The one record a machine must not touch is the one a person wrote."""
        found = [row for row in self.rows() if row["path"] == "bin/thing.py"][0]
        ack.acknowledge(self.branch.root, found, "dismissed", "the reviewer misread the diff")
        self.assertEqual(ack.record_answers(self.branch.root, self.rows(), "main"), ([], ""))
        record = ack.read_store(self.branch.root)[0][found["id"]]
        self.assertEqual(record["disposition"], "dismissed")
        self.assertEqual(record["reason"], "the reviewer misread the diff")

    def test_a_second_push_does_not_move_a_record_somebody_has_read(self) -> None:
        ack.record_answers(self.branch.root, self.rows(), "main")
        before = dict(ack.read_store(self.branch.root)[0])
        self.assertEqual(ack.record_answers(self.branch.root, self.rows(), "main"), ([], ""))
        self.assertEqual(ack.read_store(self.branch.root)[0], before)

    def test_a_review_that_names_no_commit_answers_nothing(self) -> None:
        """A payload with no `commit_id` cannot date a finding, so nothing is dated.

        The captured rounds in `tests/fixtures/` are pruned to author and body,
        and an older API shape carries no commit either. Absence of evidence
        must not read as evidence of an answer.
        """
        self.assertEqual(ack.record_answers(self.branch.root, self.rows(""), "main"), ([], ""))
        self.assertEqual(ack.read_store(self.branch.root)[0], {})

    def test_a_finding_this_reader_could_not_place_is_never_answered(self) -> None:
        """`?` is the path of a finding the parser failed on; it stays unread.

        Deciding that an unparsed finding has been answered because some file
        changed is the parser's blind spot laundered into a clean gate.
        """
        rows = ack.findings(7, [{
            "author": "bot", "commit_id": self.branch.reviewed,
            "body": "## Suppressed comments (2)\n\n**bin/thing.py:1**\nreal\n",
        }], [])
        shortfall = [row for row in rows if row["path"] == "?"]
        self.assertEqual(len(shortfall), 1)
        written, _ = ack.record_answers(self.branch.root, rows, "main")
        self.assertEqual([row["path"] for row in written], ["bin/thing.py"])

    def test_a_finding_restated_against_a_later_commit_is_not_answered(self) -> None:
        """A reviewer repeating itself is a reviewer saying the finding stands.

        The same words in a second review read against a newer head. Dating
        that finding to the first read would let the very commit the reviewer
        looked at and still objected to count as its answer.
        """
        body = ("| File | Summary |\n|---|---|\n"
                "| `bin/thing.py` | Moderate finding (2 votes): the thing is wrong. |\n")
        rows = ack.findings(7, [
            {"author": "bot", "commit_id": self.branch.reviewed, "body": body},
            {"author": "bot", "commit_id": self.branch.landed, "body": body},
        ], [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reviewed"], "")
        self.assertEqual(ack.record_answers(self.branch.root, rows, "main"), ([], ""))

    def test_a_corrupt_record_is_not_replaced_by_an_automatic_one(self) -> None:
        """A store nothing can read is not a store with nothing in it."""
        ack.store_path(self.branch.root).write_text("{not json", encoding="utf-8")
        written, broken = ack.record_answers(self.branch.root, self.rows(), "main")
        self.assertEqual(written, [])
        self.assertIn("is not valid JSON", broken,
                      "an empty result with no sentence is indistinguishable from nothing to record")
        self.assertEqual(ack.store_path(self.branch.root).read_text(), "{not json")


class ThePathIsTheReviewersText(unittest.TestCase):
    """A finding's path is passed to git as a name, never as a pattern.

    `git rev-list -- <path>` reads its path as a pathspec, and a pathspec is a
    glob. A reviewer that writes `bin/*.py` would have its finding answered by
    any commit that touched any file under `bin/`, and a file whose real name
    carries `[` would never be matched at all. Both directions are here,
    because either alone is passed by an implementation that quotes wrongly.
    """

    def setUp(self) -> None:
        self.stack = tempfile.TemporaryDirectory()
        self.addCleanup(self.stack.cleanup)
        self.branch = Branch(self.stack)

    def rows(self, path: str) -> list[dict]:
        return ack.findings(7, [{
            "author": "bot", "commit_id": self.branch.reviewed,
            "body": f"| File | Summary |\n|---|---|\n| `{path}` | Moderate finding (2 votes): wrong. |\n",
        }], [])

    def test_a_glob_in_the_path_answers_nothing_it_would_have_matched(self) -> None:
        """`bin/*.py` names no file; `bin/thing.py` changing is not its answer."""
        self.assertEqual(ack.answering_commit(self.branch.root, self.rows("bin/*.py")[0], "main"), "")
        self.assertEqual(ack.record_answers(self.branch.root, self.rows("bin/*.py"), "main"), ([], ""))

    def test_a_bracket_in_a_finding_path_is_a_bracket(self) -> None:
        """`bin/[a].py` as a pattern matches `bin/a.py`; as a name it matches itself only."""
        self.branch._write("bin/a.py", "the file the pattern would match\n")
        self.branch._git("add", "-A")
        self.branch._git("commit", "-qm", "touch bin/a.py")
        self.assertEqual(ack.answering_commit(self.branch.root, self.rows("bin/[a].py")[0], "main"), "")
        self.branch._write("bin/[a].py", "answered\n")
        self.branch._git("add", "-A")
        self.branch._git("commit", "-qm", "answer the bracketed thing")
        answered = self.branch._git("rev-parse", "HEAD")
        self.assertEqual(ack.answering_commit(self.branch.root, self.rows("bin/[a].py")[0], "main"), answered)


class Squash(Branch):
    """`Branch`, plus the shape every merge in this repository leaves behind.

    `topic` carries the commit that answers the finding and one more; `main`
    carries their squash and nothing from `topic`'s own history. A second
    branch, `elsewhere`, carries a merge-shaped commit that is on no landing
    ref at all -- the control for a pull request GitHub calls merged whose
    merge commit this repository cannot find on `main`.
    """

    def __init__(self, stack: tempfile.TemporaryDirectory) -> None:
        super().__init__(stack)
        self._git("checkout", "-q", "-b", "topic", self.reviewed)
        self._write("bin/other.py", "answered on the topic branch\n")
        self._git("commit", "-qam", "answer the other thing, on the branch")
        self.answer = self._git("rev-parse", "HEAD")
        self._write("docs/untouched.md", "a second commit on the branch\n")
        self._git("commit", "-qam", "more on the branch")
        self.head = self._git("rev-parse", "HEAD")
        self._git("checkout", "-q", "main")
        self._git("merge", "-q", "--squash", "topic")
        self._git("commit", "-qm", "the other thing, squashed (#7)")
        self.squash = self._git("rev-parse", "HEAD")
        self._git("checkout", "-q", "-b", "elsewhere", self.reviewed)
        self._write("bin/other.py", "a landing that is not on main\n")
        self._git("commit", "-qam", "squashed somewhere else")
        self.elsewhere = self._git("rev-parse", "HEAD")
        self._git("checkout", "-q", "main")


class ASquashIsALanding(unittest.TestCase):
    """The commit a record names is never on `main` here; its squash is.

    Found on the first two pull requests the automatic record was run
    against: #889 and #890 merged by squash, and every one of their fifteen
    records read `fix-not-landed` afterwards, forever, because `main` never
    contains a branch commit. The model stays "the commit claiming to answer
    is in the history that landed"; the history that landed is read through
    the pull request, and each of the three facts it rests on is checked.
    """

    REVIEW = ("| File | Summary |\n|---|---|\n"
              "| `bin/other.py` | Moderate finding (1 vote): the other thing is wrong. |\n")

    def setUp(self) -> None:
        self.stack = tempfile.TemporaryDirectory()
        self.addCleanup(self.stack.cleanup)
        self.repo = Squash(self.stack)
        self.rows = ack.findings(7, [{"author": "bot", "commit_id": self.repo.reviewed,
                                      "body": self.REVIEW}], [])
        written, _ = ack.record_answers(self.repo.root, self.rows, "topic")
        self.assertEqual([row["commit"] for row in written], [self.repo.answer])

    def merged(self, head: str | None = None, merge: str | None = None, **extra) -> dict:
        pull = {"merged": True, "merge_commit_sha": merge or self.repo.squash,
                "head": {"sha": head or self.repo.head}}
        pull.update(extra)
        return pull

    def state(self, pull: dict | None) -> str:
        payload = {"reviews": [{"author": "bot", "commit_id": self.repo.reviewed, "body": self.REVIEW}],
                   "comments": []}
        if pull is not None:
            payload["pull"] = pull
        return ack.review_state(self.repo.root, {7: payload}, "main")["findings"][0]["verdict"]

    def test_ancestry_alone_never_sees_a_squash_land(self) -> None:
        """The defect, kept as the baseline the rest of this class moves from."""
        self.assertEqual(self.state(None), "fix-not-landed")

    def test_a_merged_pull_request_whose_head_carried_the_commit_landed(self) -> None:
        """The fix: merged, the commit is in the merged head, the squash is on main."""
        self.assertEqual(self.state(self.merged()), "landed")

    def test_the_captured_shape_replays_offline(self) -> None:
        """`--from` with the merge facts in the file is enough; no second trip."""
        capture = pathlib.Path(self.stack.name) / "squash.json"
        capture.write_text(json.dumps({"pull_requests": {"7": {
            "reviews": [{"author": "bot", "commit_id": self.repo.reviewed, "body": self.REVIEW}],
            "comments": [], "pull": self.merged(),
        }}}), encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(BIN / "sd-review-ack"), "--from", str(capture), "--check",
             "--landed-in", "main", "--json"],
            cwd=str(self.repo.root), capture_output=True, text=True, check=False,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout)["findings"][0]["verdict"], "landed")

    def test_a_merge_commit_that_is_not_on_the_landing_ref_is_not_a_landing(self) -> None:
        """GitHub says merged; `main` does not have the commit it merged as."""
        self.assertEqual(self.state(self.merged(merge=self.repo.elsewhere)), "fix-not-landed")

    def test_a_commit_the_merged_head_never_carried_is_not_a_landing(self) -> None:
        """The pull request merged, but the cited commit is from some other branch."""
        self.assertEqual(self.state(self.merged(head=self.repo.elsewhere)), "fix-not-landed")

    def test_an_unmerged_pull_request_carries_no_landing(self) -> None:
        """`merge_commit_sha` is set on open pull requests too; `merged` decides."""
        self.assertEqual(self.state(self.merged(merged=False)), "fix-not-landed")
        self.assertEqual(self.state({"merge_commit_sha": self.repo.squash,
                                     "head": {"sha": self.repo.head}}), "fix-not-landed")
        self.assertEqual(ack.landing_evidence({"pull": "merged"}), {})

    def test_a_live_round_reads_the_pull_request_beside_its_reviews(self) -> None:
        """`live_round` is where the merge facts come from, so it has to ask for them."""
        calls: list[list[str]] = []

        class PrState:
            @staticmethod
            def probe(root):
                return {"available": True, "slug": "acme/widget", "reason": ""}

            @staticmethod
            def gh_json(args, root):
                calls.append(args)
                return ({"merged": True} if args[1].endswith("/pulls/7") else []), ""

        with unittest.mock.patch.object(ack.sd_lib, "sibling", return_value=PrState):
            rounds, error, _ = ack.live_round(self.repo.root, 7, 5)
        self.assertEqual(error, "")
        self.assertEqual(rounds[7]["pull"], {"merged": True})
        self.assertIn(["api", "repos/acme/widget/pulls/7"], calls)


class ARestatedFindingIsNotAnswered(unittest.TestCase):
    """A record the reviewer has read and overruled stops satisfying the gate.

    The real order of events: the push answers the finding and `sd-ship`
    records `fixed <commit>` at once; the reviewer then reads that commit and
    states the finding again. The record is on file and is never moved, so
    without this the restatement read as answered -- by the very commit the
    reviewer looked at and objected to.
    """

    BODY = ("| File | Summary |\n|---|---|\n"
            "| `bin/thing.py` | Moderate finding (2 votes): the thing is wrong. |\n")

    def setUp(self) -> None:
        self.stack = tempfile.TemporaryDirectory()
        self.addCleanup(self.stack.cleanup)
        self.branch = Branch(self.stack)
        # The first review, and the push that answered it, recorded as it happened.
        written, _ = ack.record_answers(self.branch.root, self.review(self.branch.reviewed), "main")
        self.assertEqual([row["commit"] for row in written], [self.branch.landed])
        # A later head that contains the fix, for the reviewer to read.
        self.branch._write("notes.txt", "later\n")
        self.branch._git("add", "-A")
        self.branch._git("commit", "-qm", "later, on top of the fix")
        self.later = self.branch._git("rev-parse", "HEAD")

    def review(self, *commits: str) -> list[dict]:
        return ack.findings(7, [{"author": "bot", "commit_id": commit, "body": self.BODY}
                                for commit in commits], [])

    def state(self, rows: list[dict]) -> dict:
        return ack.review_state(self.branch.root, {7: {"reviews": [
            {"author": "bot", "commit_id": commit, "body": self.BODY} for commit in rows
        ], "comments": []}}, "main")

    def test_restated_against_a_head_that_contains_the_fix_is_fix_restated(self) -> None:
        result = self.state([self.branch.reviewed, self.later])
        self.assertEqual(result["findings"][0]["verdict"], "fix-restated")
        self.assertEqual(len(result["unsatisfied"]), 1, "the gate stays red")
        rows = self.review(self.branch.reviewed, self.later)
        self.assertEqual(
            ack.unacknowledged(self.branch.root, [rows[0]["id"]], "main",
                               {rows[0]["id"]: rows[0]["stated_at"]}),
            [rows[0]["id"]],
            "the id-only gate `sd-status` uses reaches the same verdict from the map",
        )

    def test_the_record_is_left_on_file_for_a_person_to_move(self) -> None:
        before = dict(ack.read_store(self.branch.root)[0])
        self.state([self.branch.reviewed, self.later])
        self.assertEqual(ack.read_store(self.branch.root)[0], before)

    def test_restated_against_a_head_without_the_fix_keeps_the_record(self) -> None:
        """The other direction: the reviewer repeated itself before the fix existed."""
        result = self.state([self.branch.reviewed, self.branch.stranded])
        self.assertEqual(result["findings"][0]["verdict"], "landed")
        self.assertEqual(result["unsatisfied"], [])

    def test_stated_once_and_answered_after_stays_landed(self) -> None:
        result = self.state([self.branch.reviewed])
        self.assertEqual(result["findings"][0]["verdict"], "landed")

    def test_without_the_map_the_id_gate_cannot_see_the_restatement(self) -> None:
        """Documented, not hidden: a caller without `stated` gets ancestry alone."""
        rows = self.review(self.branch.reviewed, self.later)
        self.assertEqual(ack.unacknowledged(self.branch.root, [rows[0]["id"]], "main"), [])


class TheRoundNobodyHasAnswered(unittest.TestCase):
    """#889 as captured, which is what an unanswered pull request looks like.

    `tests/fixtures/sd-631-unanswered-round.json` is pull request 889 read from
    the API on 2026-09-13: one automated review, ten findings across a
    file-summary table, a `Suppressed comments` section and one inline comment,
    and not one of them answered. It is the control for the automatic record --
    a machine that acknowledges this round acknowledges everything.
    """

    ROUND = json.loads(UNANSWERED.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.stack = tempfile.TemporaryDirectory()
        self.addCleanup(self.stack.cleanup)
        self.branch = Branch(self.stack)

    def payload(self) -> dict:
        return self.ROUND["pull_requests"]["889"]

    def test_the_review_was_read_against_the_head_that_is_still_the_head(self) -> None:
        """The measured fact behind "unanswered": no commit came after the review."""
        reviews = self.payload()["reviews"]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["commit_id"], self.ROUND["head"])
        self.assertEqual(
            len(ack.findings(889, reviews, self.payload()["comments"])), 10,
            "the capture carries ten findings and the reader must see all ten",
        )

    def test_a_push_that_touches_none_of_the_named_files_answers_nothing(self) -> None:
        """The real ten findings, replayed against a real push that is not a fix.

        The capture's commit ids name commits no test repository can have, so
        the review is re-dated onto this fixture's first commit and every
        finding keeps its real path and its real text. `main` then carries a
        commit made after that review -- which is the whole of what "somebody
        pushed" proves -- and it touches none of the ten files.
        """
        reviews = [dict(row, commit_id=self.branch.reviewed)
                   for row in self.payload()["reviews"]]
        comments = [dict(row, original_commit_id=self.branch.reviewed, commit_id=None)
                    for row in self.payload()["comments"]]
        rows = ack.findings(889, reviews, comments)
        self.assertEqual(len(rows), 10)
        self.assertEqual(ack.record_answers(self.branch.root, rows, "main"), ([], ""))
        self.assertEqual(
            ack.unacknowledged(self.branch.root, [row["id"] for row in rows], "main"),
            [row["id"] for row in rows],
            "ten findings stated and none answered is ten findings standing",
        )


class AMarkerWithNoNoun(unittest.TestCase):
    """#893's round, where the reviewer stopped writing the word `votes`.

    `tests/fixtures/sd-655-count-only-round.json` is pull request 893 read from
    the API on 2026-09-13, both of its reviews, bodies and all. The first one
    states five findings in a three-column file-summary table and spells every
    marker as a bare count -- `**Critical (1):**`, `**Moderate (2):**` -- and a
    reader that required `votes?` called that pull request clean while it
    carried five. Hand-counted against the review on GitHub, in the order the
    table states them:

      `bin/sd-ship`       Critical (1)  the pre-squash SHA is the one recorded
      `bin/sd-ship`       Moderate (2)  helper loading outside the guarded block
      `bin/sd-review-ack` Critical (2)  a plain pathspec is a glob
      `bin/sd-review-ack` Critical (1)  an older acknowledgement satisfies a restatement
      `bin/sd-review-ack` Moderate (1)  a corrupt store is indistinguishable from empty

    Five, and item sd:655 recorded six. The sixth is not in a marker: the
    round's *second* review names four more defects in its summary sentence
    only, with no table and no marker anywhere in the body, and this reader
    counts markers on purpose. What it cannot count it must not pretend to, so
    the number pinned below is the five the reviewer marked.
    """

    ROUND = json.loads(COUNT_ONLY.read_text(encoding="utf-8"))

    def rows(self) -> list[dict]:
        payload = self.ROUND["pull_requests"]["893"]
        return ack.findings(893, payload["reviews"], payload["comments"])

    def test_the_round_that_read_clean_reads_as_five_findings(self) -> None:
        """The defect, measured: a bare count is a marker or the round is silent."""
        self.assertEqual(len(self.rows()), 5)

    def test_the_captured_round_is_refused_by_the_gate(self) -> None:
        """End to end, through the CLI, on the real body."""
        stack = tempfile.TemporaryDirectory()
        self.addCleanup(stack.cleanup)
        repo = Repo(stack)
        done = subprocess.run(
            [sys.executable, str(BIN / "sd-review-ack"), "--from", str(COUNT_ONLY),
             "--check", "--landed-in", "main", "--json"],
            cwd=str(repo.root), capture_output=True, text=True, check=False,
        )
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(len(result["findings"]), 5)
        self.assertEqual(len(result["unsatisfied"]), 5)

    def test_the_severity_survives_a_table_with_three_columns(self) -> None:
        """`File | Summary | Findings`, so a cell separator precedes the label.

        The count and the text were both right before this and the severity of
        the first finding in each row read `| **Critical`, which is a garbled
        finding that still looks like a finding somebody read -- the failure
        `_cell` was written for, in a column layout it had not seen.
        """
        self.assertEqual(
            [(row["path"], row["text"]) for row in self.rows()],
            [("bin/sd-ship",
              "Critical: Records the pre-squash SHA, preventing normal squash merges "
              "from reaching `landed`"),
             ("bin/sd-ship",
              "Moderate: Helper loading outside the guarded block can abort `prepare` "
              "instead of producing an advisory warning"),
             ("bin/sd-review-ack", "Critical: Normal pathspecs can match unrelated files"),
             ("bin/sd-review-ack",
              "Critical: Older acknowledgements can satisfy findings restated on newer commits"),
             ("bin/sd-review-ack",
              "Moderate: Corrupt stores are indistinguishable from empty results and "
              "produce no warning")],
        )

    def test_a_bare_count_is_flat_unless_the_reviewer_says_otherwise(self) -> None:
        """The control for the hedge: five exact counts stay exact."""
        rows = self.rows()
        self.assertFalse(any(row["indeterminate"] for row in rows))
        self.assertEqual(ack.at_least(rows, len(rows)), "5")

    def test_the_second_review_states_nothing_this_reader_will_invent(self) -> None:
        """A body with no table and no marker yields nothing, not a guess.

        The honest half of the count above. The reviewer's summary sentence
        lists four defects in prose; a reader that mined prose for findings
        would be writing them, and `_reconciled` is what makes the gap loud
        when the reviewer next moves them into a shape.
        """
        second = self.ROUND["pull_requests"]["893"]["reviews"][1]
        self.assertNotIn("|", second["body"])
        self.assertEqual(ack.findings(893, [second], []), [])

    def test_the_suppressed_headings_own_count_is_not_a_finding_marker(self) -> None:
        """Why the bare-count marker needs the colon after it.

        `### Suppressed comments (4)` is a bare count in parentheses in every
        body that has that section, and it is the reviewer's own heading rather
        than a severity label. A marker that matched it would count the section
        twice -- once as the heading's own assertion, which `_suppressed`
        already checks, and once as a marker `_reconciled` cannot place, which
        is a phantom finding nothing states and nobody can acknowledge.

        Enumerated from `tests/fixtures/` rather than asserted from the one
        example: every captured round on disk, every review body in it, every
        heading against every marker.
        """
        self.assertIsNone(ack.VOTE_MARKER.search("### Suppressed comments (4)"))
        headings = 0
        for capture in CAPTURES:
            payload = json.loads(capture.read_text(encoding="utf-8"))
            for number, record in payload["pull_requests"].items():
                for review in record.get("reviews") or []:
                    body = review.get("body") or ""
                    marks = [mark.span() for mark in ack.VOTE_MARKER.finditer(body)]
                    for heading in ack.SUPPRESSED_HEADING.finditer(body):
                        headings += 1
                        overlap = [body[start:stop] for start, stop in marks
                                   if start < heading.end() and heading.start() < stop]
                        self.assertEqual(
                            overlap, [],
                            f"{capture.name} #{number}: {heading.group(0)!r} read as a marker",
                        )
        self.assertGreater(headings, 0, "no capture carries the heading this guards")


class TwoCountsInOneMarker(unittest.TestCase):
    """`**Nits (2 votes, 1 vote):**`, from #889's captured review.

    One cell, one run of prose, two counts. It read as exactly one finding,
    which is an undercount, and an undercount on a gate reads as progress. The
    comma is the reviewer saying "more than one" the same way `each` and
    `N and M votes` already did, so it is read the same way: the row keeps its
    whole text and is marked indeterminate, and every count built on it says
    "at least". Splitting the prose would be this reader guessing which half of
    a sentence is which finding, and two rows out of one run would need the id
    to carry an index -- the id is over the content so that an acknowledgement
    survives the reviewer re-rendering the same words.
    """

    ROUND = json.loads(UNANSWERED.read_text(encoding="utf-8"))

    def rows(self) -> list[dict]:
        payload = self.ROUND["pull_requests"]["889"]
        return ack.findings(889, payload["reviews"], payload["comments"])

    def test_the_captured_marker_is_read_as_more_than_one_finding(self) -> None:
        grouped = [row for row in self.rows() if row["indeterminate"]]
        self.assertEqual(len(grouped), 1)
        self.assertTrue(grouped[0]["text"].startswith("Nits:"))
        self.assertIn("2 votes, 1 vote", self.ROUND["pull_requests"]["889"]["reviews"][0]["body"])

    def test_the_round_that_carried_it_stops_claiming_an_exact_count(self) -> None:
        rows = self.rows()
        self.assertEqual(len(rows), 10)
        self.assertEqual(ack.at_least(rows, len(rows)), "at least 10")

    def test_the_comma_is_the_evidence_and_not_the_plural_noun(self) -> None:
        """`Nits` is not read as plural; the reviewer writes it over one finding too."""
        self.assertTrue(ack.PLURAL_MARKER.search("(2 votes, 1 vote)"))
        self.assertTrue(ack.PLURAL_MARKER.search("(2, 1)"))
        self.assertIsNone(ack.PLURAL_MARKER.search("(3 votes)"))
        self.assertIsNone(ack.PLURAL_MARKER.search("(1)"))
        rows = ack._table(1, "| `a.py` | Nits (2 votes): one thing. |\n", "bot")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["indeterminate"])


#: A second *process* writing one row into the store of the repository named by
#: `argv[1]`, under the id in `argv[2]`. A thread would share this process's
#: `flock`-holding descriptor in ways a real lane never does.
CHILD_WRITER = (
    "import pathlib, sys;"
    "sys.path.insert(0, sys.argv[3]);"
    "sys.dont_write_bytecode = True;"
    "import sd_lib;"
    "writer = sd_lib.sibling('child_writer', 'sd-review-ack');"
    "writer.acknowledge(pathlib.Path(sys.argv[1]),"
    " {'id': sys.argv[2], 'pr': 7, 'path': 'bin/thing.py', 'line': None},"
    " 'dismissed', 'the child wrote this')"
)


class TwoWritersAtOnce(unittest.TestCase):
    """The store is one file for the whole repository, and two lanes share it.

    `store_path` resolves the *common* git dir on purpose, so every linked
    worktree of this repository writes the same file -- which is what makes a
    lost update the ordinary case here rather than a rare one. Both writers did
    read-modify-write with nothing serialising the three steps: two lanes that
    got there in the same second each read the same rows, and the second
    `os.replace` dropped the first lane's record.

    `write_store` was already atomic against a crash and that was never the
    defect; the defect is the window around it. So the tests below interleave
    two writers for real -- one across a process boundary, one across the
    read-modify-write window itself -- rather than asserting that `flock` was
    called, which would pass on a lock held over nothing.
    """

    def setUp(self) -> None:
        self.stack = tempfile.TemporaryDirectory()
        self.addCleanup(self.stack.cleanup)
        self.branch = Branch(self.stack)
        self.open: set[int] = set()

    def rows(self) -> list[dict]:
        """The three findings of the automatic path, on this repository."""
        return ack.findings(7, [{
            "author": "bot",
            "commit_id": self.branch.reviewed,
            "body": APushIsEvidenceOrItIsNothing.REVIEW,
        }], [])

    def held(self) -> int:
        """This test process, holding the sidecar the way a live writer does."""
        path = ack.lock_path(self.branch.root)
        handle = os.open(str(path), os.O_CREAT | os.O_WRONLY, 0o644)
        self.open.add(handle)
        self.addCleanup(lambda: os.close(handle) if handle in self.open else None)
        fcntl.flock(handle, fcntl.LOCK_EX)
        return handle

    def release(self, handle: int) -> None:
        os.close(handle)
        self.open.discard(handle)

    def test_a_second_process_waits_rather_than_overwriting(self) -> None:
        """The cross-process half, which is the one two worktrees produce.

        The lock is held here and a real second interpreter is asked to write.
        It must not have written when the lock is still held -- that wait is the
        whole fix -- and it must write once the lock goes. Without the lock the
        child returns immediately, which is what this reddens on.
        """
        handle = self.held()
        child = subprocess.Popen(
            [sys.executable, "-c", CHILD_WRITER, str(self.branch.root), "childrow", str(BIN)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(child.kill)
        with self.assertRaises(subprocess.TimeoutExpired):
            child.wait(timeout=2)
        self.assertEqual(ack.read_store(self.branch.root)[0], {},
                         "a writer wrote while another writer held the lock")
        self.release(handle)
        self.assertEqual(child.wait(timeout=30), 0, child.communicate()[1])
        self.assertIn("childrow", ack.read_store(self.branch.root)[0])

    def test_a_push_and_a_hand_acknowledgement_keep_both_rows(self) -> None:
        """The interleaving itself: both writers, both rows, one file.

        `record_answers` is the push's writer and `acknowledge` is the
        operator's, and the window is between the read and the replace. So the
        push is held open *inside* that window -- after the read that decides,
        before the write -- and the hand acknowledgement is let go at exactly
        that moment. Serialised, the second writer cannot start until the first
        has finished and both rows survive. Unserialised, the second writer
        reads the store the first has not written yet and the first then
        replaces the file without its row: one row, and `assertEqual` below
        says which one went.

        The pause is a timeout rather than an event the other writer sets,
        because under a correct lock the other writer never gets far enough to
        set anything -- a handshake would deadlock the fixed code and pass only
        the broken one.

        What the two writers *can* agree on is the moment before either tries
        the lock, so they rendezvous on a barrier there. An `Event` the push set
        and did not wait on would leave the hand writer's scheduling inside the
        measured window: if the kernel did not run it within the pause, the
        broken code would append after the push had written, both rows would
        survive, and the test would pass having proved nothing. After the
        barrier both threads are running and the next thing each does is the
        lock, so the pause covers the race and not the scheduler.
        """
        real = ack.read_store
        reached = threading.Barrier(2)
        counted = {"push": 0}

        def read_store(root: pathlib.Path) -> tuple[dict[str, dict], str]:
            rows = real(root)
            if threading.current_thread().name == "push":
                counted["push"] += 1
                # The second read is the one under the lock, the one whose rows
                # are replaced. Pausing on the first would prove nothing: it
                # happens before the lock is taken, so the fixed and the broken
                # code both re-read afterwards and both look clean.
                if counted["push"] == 2:
                    reached.wait(10)
                    threading.Event().wait(1.5)
            return rows

        outcome: dict = {}

        def push() -> None:
            with unittest.mock.patch.object(ack, "read_store", read_store):
                outcome["push"] = ack.record_answers(self.branch.root, self.rows(), "main")[0]

        def hand() -> None:
            reached.wait(10)  # the same barrier: neither runs on before both arrive
            outcome["hand"] = ack.acknowledge(
                self.branch.root,
                {"id": "byhand", "pr": 7, "path": "docs/untouched.md", "line": None},
                "dismissed", "the reviewer misread the diff",
            )

        writers = [threading.Thread(target=push, name="push"),
                   threading.Thread(target=hand, name="hand")]
        for writer in writers:
            writer.start()
        for writer in writers:
            writer.join(60)
        self.assertEqual([row["path"] for row in outcome["push"]], ["bin/thing.py"])
        store = ack.read_store(self.branch.root)[0]
        automatic = [found for found, row in store.items() if row["disposition"] == "fixed"]
        self.assertEqual(len(automatic), 1, f"the push's row is gone: {store}")
        self.assertIn("byhand", store, f"the hand-written row is gone: {store}")
        self.assertEqual(len(store), 2)

    def test_a_read_takes_no_lock_and_leaves_no_file(self) -> None:
        """Read-only means read-only, down to not creating the sidecar.

        The same rule `sys.dont_write_bytecode` is set for at the top of the
        file. `--check` and the row `sd-status` builds from this store both run
        on repositories nobody is acknowledging anything in, and a gate that
        writes a file in `.git/` to report is a gate that cannot be run on a
        tree somebody else owns.
        """
        self.assertEqual(ack.read_store(self.branch.root), ({}, ""))
        self.assertEqual(ack.unacknowledged(self.branch.root, ["nothing"], "main"), ["nothing"])
        done = subprocess.run(
            [sys.executable, str(BIN / "sd-review-ack"), "--from", str(FIXTURE),
             "--check", "--landed-in", "main"],
            cwd=str(self.branch.root), capture_output=True, text=True, check=False,
        )
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertFalse(ack.lock_path(self.branch.root).exists(),
                         "reading the store created a lock file")
        ack.acknowledge(self.branch.root, self.rows()[0], "dismissed", "not a defect")
        self.assertTrue(ack.lock_path(self.branch.root).exists(),
                        "a writer that creates no lock file is locking nothing")

    def test_a_lock_that_cannot_be_taken_still_records(self) -> None:
        """A sidecar that cannot exist degrades to the write, not to silence.

        A read-only `.git`, a filesystem without `flock`: the row is still the
        operator's acknowledgement, and refusing to record it would be a worse
        failure than the race this lock closes.
        """
        nowhere = pathlib.Path(os.devnull) / "no" / ack.LOCK_NAME
        with unittest.mock.patch.object(ack, "lock_path", return_value=nowhere):
            with ack.locked(self.branch.root) as taken:
                self.assertFalse(taken)
            row = ack.acknowledge(self.branch.root, self.rows()[0], "dismissed", "not a defect")
        self.assertEqual(row["reason"], "not a defect")
        self.assertEqual(len(ack.read_store(self.branch.root)[0]), 1)

    def test_every_writer_of_the_store_holds_the_lock(self) -> None:
        """Enumerated from the tree, because two is only today's answer.

        The audit found two writers and a third added later would make this fix
        partial and say nothing. So the set is derived rather than listed: every
        `write_store` call in the file has to sit inside a `with locked(...)`,
        and no other file in `bin/` may reach the store at all.
        """
        source = (BIN / "sd-review-ack").read_text(encoding="utf-8")
        tree = ast.parse(source)
        windows = [(node.lineno, node.end_lineno or node.lineno)
                   for node in ast.walk(tree) if isinstance(node, ast.With)
                   and any(isinstance(item.context_expr, ast.Call)
                           and getattr(item.context_expr.func, "id", "") == "locked"
                           for item in node.items)]
        calls = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and getattr(node.func, "id", "") == "write_store"]
        self.assertTrue(calls, "no writer found, so this test measures nothing")
        self.assertEqual(
            [line for line in calls
             if not any(start <= line <= stop for start, stop in windows)],
            [], "a write_store call outside every `with locked(...)` block",
        )
        elsewhere = []
        for path in sorted(BIN.iterdir()):
            if not path.is_file() or path.name == "sd-review-ack":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "write_store" in text or ack.STORE_NAME in text:
                elsewhere.append(path.name)
        self.assertEqual(elsewhere, [], "another module reaches the store directly")


class TheUnlocatedSentinelIsNotALabel(unittest.TestCase):
    """sd:1395: the value that means "no file" may not also be the file shown.

    `"?"` is the `path` of a finding a review heading counted and the body
    reader could not recover. It is read as a control value in
    `answering_commit` -- a finding this reader could not place is one it may
    not decide has been answered -- and it is printed as though it were a
    path everywhere a finding is rendered or grouped. sd:1223 is titled
    `11 live code-review findings remain in ?/` because of the second job.

    The defect is the pairing, not either half: anyone improving the display
    edits the two producers, leaves the guard comparing against the character,
    and the guard stops recognising its own findings. So the literal is
    written once, and every other site reads it by name.
    """

    SOURCE = (REPO_ROOT / "bin" / "sd-review-ack").read_text(encoding="utf-8")

    def test_the_sentinel_is_spelled_once_in_the_whole_file(self):
        """One constant, and every producer and guard reads it by name.

        Counted from the parsed source rather than from a list of the sites
        known today: a fourth producer added next year is inside this check
        without anybody remembering to add it.
        """
        tree = ast.parse(self.SOURCE)
        literals = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value == ack.UNLOCATED
        ]
        self.assertEqual(
            [node.lineno for node in literals], [self._constant_line(tree)],
            "the unlocated sentinel is written by hand somewhere other than its "
            "own definition; a display change there cannot reach the guard",
        )

    def _constant_line(self, tree: ast.Module) -> int:
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "UNLOCATED"
                for target in node.targets
            ):
                return node.value.lineno
        self.fail("bin/sd-review-ack defines no UNLOCATED constant")

    def test_both_producers_make_a_row_the_guard_recognises(self):
        """The shortfall row and the reconciliation row are the two producers."""
        shortfall = ack._shortfall(1, "2", 0, "bot")
        reconciled = ack._reconciled(1, "(moderate, 2 votes) a thing", "bot", [])
        self.assertTrue(ack.is_unlocated(shortfall["path"]))
        self.assertEqual(len(reconciled), 1)
        self.assertTrue(ack.is_unlocated(reconciled[0]["path"]))

    def test_an_empty_path_is_not_an_unlocated_finding(self):
        """Two states, kept apart: no path recorded, and a finding with no file."""
        self.assertFalse(ack.is_unlocated(""))
        self.assertFalse(ack.is_unlocated(None))

    def test_the_guard_refuses_an_unlocated_finding_without_asking_git(self):
        """`answering_commit` reads the sentinel by name, not by character."""
        calls: list[list[str]] = []

        def spy(args, root):
            calls.append(args)
            return ""

        row = dict(ack._shortfall(1, "2", 0, "bot"), reviewed="c0ffee")
        with unittest.mock.patch.object(ack.sd_lib, "git_output", spy):
            self.assertEqual(ack.answering_commit(REPO_ROOT, row, "main"), "")
            self.assertEqual(calls, [], "an unplaced finding asked git a question")
            ack.answering_commit(REPO_ROOT, dict(row, path="bin/thing.py"), "main")
        self.assertEqual(len(calls), 1, "a placed finding must still be asked about")

    def test_a_rendered_unlocated_finding_does_not_read_as_a_file(self):
        """The display half, which is the half sd:1223's title got wrong."""
        row = dict(
            ack._shortfall(1, "2", 0, "bot"), verdict="unread", replies=0, reviewed="",
        )
        stream = io.StringIO()
        ack.render_findings(
            {"findings": [row], "unsatisfied": [row], "pull_requests": [1],
             "landing_ref": "origin/main", "store_error": ""},
            stream,
        )
        self.assertIn(ack.UNLOCATED_LABEL, stream.getvalue())
        self.assertNotIn(f" {ack.UNLOCATED} ", stream.getvalue())


class AFindingKeepsItsNameWhenGitHubMovesIt(unittest.TestCase):
    """sd:1388: the id is keyed on the coordinate the reviewer read, not the live one.

    GitHub re-anchors an inline comment as the branch grows: `line` moves by
    the hunk delta of every later push and becomes null once the comment goes
    outdated. `original_line` does not move. `_reviewed_at` already prefers
    `original_commit_id` for exactly this reason, in a docstring four lines
    from the id, while the id itself keyed on the field that moves.

    What that cost: a finding acknowledged as `carried` under id A is read
    back under id B after an unrelated push, the store row under A is
    orphaned, and `record_answers` writes `fixed` under B -- so the carried
    finding's satisfaction can no longer be lost when the item holding it is
    cancelled, and a human `dismissed <reason>` is silently replaced by an
    automatic verdict under a new name.
    """

    COMMENT = {
        "path": "bin/x.py", "body": "the finding, stated once", "author": "bot",
        "id": 4242, "in_reply_to_id": None, "original_commit_id": "c0ffee",
        "original_line": 47,
    }

    def _row(self, **extra) -> dict:
        return ack.findings(1200, [], [dict(self.COMMENT, **extra)])[0]

    def test_a_later_push_that_moves_the_line_does_not_rename_the_finding(self):
        """The decisive case: one comment, read twice, across a line-moving edit."""
        self.assertEqual(self._row(line=47)["id"], self._row(line=53)["id"])

    def test_a_comment_gone_outdated_keeps_the_name_it_had(self):
        """GitHub drops `line` to null once the hunk is gone; the finding stays itself."""
        self.assertEqual(self._row(line=47)["id"], self._row(line=None)["id"])

    def test_the_finding_is_placed_at_the_state_it_is_dated_to(self):
        """One coordinate, not two: `original_commit_id` and `original_line` are a pair.

        Showing the moved line beside the commit the reviewer read would name
        a line that does not carry the finding in that commit.
        """
        row = self._row(line=53)
        self.assertEqual((row["reviewed"], row["line"]), ("c0ffee", 47))

    def test_a_payload_with_no_original_line_still_reads_the_line_it_has(self):
        """The captured rounds and the older API shape carry only `line`.

        Falling back to it keeps every id in `tests/fixtures/*-round.json`
        exactly as it was, so this change renames no finding already on
        record except one GitHub had already moved.
        """
        row = ack.findings(1200, [], [{"path": "bin/x.py", "body": "t", "author": "bot",
                                       "line": 9, "in_reply_to_id": None}])[0]
        self.assertEqual(row["line"], 9)
        self.assertEqual(row["id"], ack.finding_id(1200, "inline", "bin/x.py", 9, "t"))

    def test_an_acknowledgement_survives_the_push_that_moves_the_comment(self):
        """The failure the item describes, end to end, without a repository.

        The store is keyed by finding id. If the id moves, the row recorded
        against the finding is not found when the finding is read again.
        """
        before, after = self._row(line=47), self._row(line=53)
        store = {before["id"]: {"disposition": "carried", "item": 771}}
        self.assertIn(after["id"], store)


class TheVerdictSaysWhatItRead(unittest.TestCase):
    """sd:1392: a clean verdict over the first 30 open pull requests.

    `--check` listed open pull requests at `DEFAULT_LIMIT`, `gh` truncated
    silently, and the report printed the number that came back -- so the size
    of the sample was presented as the scope of the verdict. Thirty-four open
    pull requests with unacknowledged findings on the four oldest exited 0 and
    said `30 pull request(s)`, with nothing saying four were never read.

    Bounded, and that is why the remedy is a refusal rather than an alarm:
    `sd-ship`'s merge gate goes per pull request through `review_state` and
    never through this path, so nothing downstream reads a capped verdict.
    Only the standalone report does, and it is the one that has to say so.
    """

    def _pr_state(self, open_pulls: int) -> tuple[type, list[list[str]]]:
        calls: list[list[str]] = []

        class PrState:
            @staticmethod
            def probe(root):
                return {"available": True, "slug": "acme/widget", "reason": ""}

            @staticmethod
            def gh_json(args, root):
                calls.append(args)
                if args[0] != "pr":
                    return ([] if args[1].endswith(("/reviews", "/comments")) else {}), ""
                asked = int(args[args.index("--limit") + 1])
                return [{"number": n} for n in range(1, min(open_pulls, asked) + 1)], ""

        return PrState, calls

    def _round(self, open_pulls: int, limit: int) -> tuple[dict, str, int, list[list[str]]]:
        state, calls = self._pr_state(open_pulls)
        with unittest.mock.patch.object(ack.sd_lib, "sibling", return_value=state):
            rounds, error, capped = ack.live_round(REPO_ROOT, None, limit)
        return rounds, error, capped, calls

    def test_a_read_that_stopped_at_its_limit_says_where_it_stopped(self):
        rounds, error, capped, _ = self._round(34, 30)
        self.assertEqual(error, "")
        self.assertEqual(len(rounds), 30, "the limit is still the limit")
        self.assertEqual(capped, 30)

    def test_a_read_that_reached_the_end_is_not_reported_as_capped(self):
        """Exactly `limit` open pull requests is a complete read, not a truncated one.

        `len(payload) >= limit` would refuse here forever on a repository that
        happens to sit on the number, which is a gate crying wolf at a read
        that missed nothing. One extra row asked for answers it exactly.
        """
        rounds, _, capped, calls = self._round(30, 30)
        self.assertEqual((len(rounds), capped), (30, 0))
        listing = calls[0]
        self.assertEqual(listing[listing.index("--limit") + 1], "31",
                         "the cap is detected by asking for one more, in the same call")

    def test_check_refuses_while_the_read_is_capped(self):
        """Absence of evidence, the same direction `reason` already fails in.

        A capped read cannot know whether a finding stands on a pull request it
        never opened, and a gate that rules clean on that is the one that
        passes hardest on the busiest repository.
        """
        args = ack.ack_parser().parse_args(["--check"])
        with unittest.mock.patch.object(ack, "live_round", return_value=({}, "", 30)):
            result, code = ack.review_report(args, REPO_ROOT)
        self.assertEqual(code, 1)
        self.assertEqual(result["capped"], 30)

    def test_a_capped_read_without_check_still_reports(self):
        """Reporting is not gating: the cap is said, and the exit stays 0."""
        args = ack.ack_parser().parse_args([])
        with unittest.mock.patch.object(ack, "live_round", return_value=({}, "", 30)):
            _, code = ack.review_report(args, REPO_ROOT)
        self.assertEqual(code, 0)

    def test_a_captured_round_is_never_capped(self):
        """A replayed file is the whole file; only a live listing can stop short."""
        args = ack.ack_parser().parse_args(["--from", str(FIXTURE)])
        self.assertEqual(ack._chosen_round(args, REPO_ROOT)[2], 0)

    def test_the_header_does_not_print_the_sample_as_the_scope(self):
        self.assertEqual("3 pull request(s)",
                         ack.read_scope({"pull_requests": [1, 2, 3], "capped": 0}))
        self.assertIn("not how many are open",
                      ack.read_scope({"pull_requests": [1, 2, 3], "capped": 3}))

    def test_the_report_names_the_cap_even_with_nothing_to_report(self):
        """The clean-looking run is the one that needed telling."""
        stream = io.StringIO()
        ack.render_findings(
            {"findings": [], "unsatisfied": [], "pull_requests": [1, 2, 3],
             "landing_ref": "origin/main", "store_error": "", "capped": 3},
            stream,
        )
        self.assertIn("--limit", stream.getvalue())
        self.assertIn("read stopped at 3", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
