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

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sd-543-review-round.json"
UNANSWERED = REPO_ROOT / "tests" / "fixtures" / "sd-631-unanswered-round.json"

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
            pr_state.inline_findings = lambda *a: ([], "gh api exited 1")
            blind = pr_state._findings(pull, REPO_ROOT, "acme/widget")
            pr_state.inline_findings = lambda *a: (["inline-id"], "")
            whole = pr_state._findings(pull, REPO_ROOT, "acme/widget")
        finally:
            pr_state.inline_findings = original
        self.assertEqual(blind["unreadable"], "gh api exited 1")
        self.assertEqual(whole["unreadable"], "")
        self.assertEqual(whole["in_body"], 3)
        self.assertEqual(len(whole["ids"]), 4)
        self.assertIn("inline-id", whole["ids"])

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
                    ids, reason = pr_state.inline_findings(REPO_ROOT, "acme/widget", 7)
                    self.assertEqual(ids, [])
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
            ids, reason = pr_state.inline_findings(REPO_ROOT, "acme/widget", 860)
        finally:
            pr_state.gh_json = original
        self.assertEqual(reason, "")
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
            f"r, why = m.live_round(pathlib.Path({str(self.repo.root)!r}), None, 10);"
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
        written = ack.record_answers(self.branch.root, self.rows(), "main")
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
        written = ack.record_answers(self.branch.root, self.rows(), "stranded")
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
        self.assertEqual(ack.record_answers(self.branch.root, self.rows(), "main"), [])
        record = ack.read_store(self.branch.root)[0][found["id"]]
        self.assertEqual(record["disposition"], "dismissed")
        self.assertEqual(record["reason"], "the reviewer misread the diff")

    def test_a_second_push_does_not_move_a_record_somebody_has_read(self) -> None:
        ack.record_answers(self.branch.root, self.rows(), "main")
        before = dict(ack.read_store(self.branch.root)[0])
        self.assertEqual(ack.record_answers(self.branch.root, self.rows(), "main"), [])
        self.assertEqual(ack.read_store(self.branch.root)[0], before)

    def test_a_review_that_names_no_commit_answers_nothing(self) -> None:
        """A payload with no `commit_id` cannot date a finding, so nothing is dated.

        The captured rounds in `tests/fixtures/` are pruned to author and body,
        and an older API shape carries no commit either. Absence of evidence
        must not read as evidence of an answer.
        """
        self.assertEqual(ack.record_answers(self.branch.root, self.rows(""), "main"), [])
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
        written = ack.record_answers(self.branch.root, rows, "main")
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
        self.assertEqual(ack.record_answers(self.branch.root, rows, "main"), [])

    def test_a_corrupt_record_is_not_replaced_by_an_automatic_one(self) -> None:
        """A store nothing can read is not a store with nothing in it."""
        ack.store_path(self.branch.root).write_text("{not json", encoding="utf-8")
        self.assertEqual(ack.record_answers(self.branch.root, self.rows(), "main"), [])
        self.assertEqual(ack.store_path(self.branch.root).read_text(), "{not json")


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
        self.assertEqual(ack.record_answers(self.branch.root, rows, "main"), [])
        self.assertEqual(
            ack.unacknowledged(self.branch.root, [row["id"] for row in rows], "main"),
            [row["id"] for row in rows],
            "ten findings stated and none answered is ten findings standing",
        )


if __name__ == "__main__":
    unittest.main()
