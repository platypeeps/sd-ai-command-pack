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
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sd-543-review-round.json"

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
            ("bin/sd_work.py", "Critical: update the command inventory guard for this scoped exception."),
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

    def test_a_body_with_nothing_in_it_still_counts_nothing(self):
        """The clean case stays clean: the line prints only on a non-zero count."""
        pr_state = sd_lib.sibling("sd_pr_state_under_test", "sd-pr-state")
        counted = pr_state.review_findings([{"body": "Looks good to me.", "author": {"login": "bot"}}])
        self.assertEqual(counted["in_body"], 0)
        self.assertEqual(counted["reviewers"], [])


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

    def test_a_commit_nobody_has_is_not_a_fix_either(self):
        found = self._first(860)
        result, code = payload(
            self.repo.root, "--pr", "860", "--check",
            "--ack", found, "--fixed", "0" * 40, *self.ref,
        )
        row = next(r for r in result["findings"] if r["id"] == found)
        self.assertEqual(row["verdict"], "fix-missing")
        self.assertEqual(code, 1)

    def test_a_commit_on_the_branch_satisfies_the_finding(self):
        found = self._first(860)
        result, _ = payload(
            self.repo.root, "--pr", "860",
            "--ack", found, "--fixed", self.repo.landed, *self.ref,
        )
        row = next(r for r in result["findings"] if r["id"] == found)
        self.assertEqual(row["verdict"], "landed")

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
        """A corrupt store makes the gate refuse, never pass."""
        ack.store_path(self.repo.root).write_text("{not json")
        _, code = payload(self.repo.root, "--check", *self.ref)
        self.assertEqual(code, 1)

    def test_an_id_that_names_no_finding_is_a_usage_error(self):
        done = run(self.repo.root, "--pr", "863", "--ack", "deadbeefcafe", "--dismiss", "read")
        self.assertEqual(done.returncode, 2)
        self.assertIn("no finding here has the id", done.stderr)


if __name__ == "__main__":
    unittest.main()
