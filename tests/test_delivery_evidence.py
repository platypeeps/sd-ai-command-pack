"""Delivery evidence: the trailer block git reads, and who may record one.

Three guards, one mechanic. `git interpret-trailers --parse` reads a message's
*last* paragraph and nothing else, so a single blank line demotes a trailer to
prose and every reader downstream sees exactly what it would see if the author
had never written it. That is sd:5, which landed on main with its `Delivers:`
line one paragraph too high and had to be re-recorded by an empty commit.

Each guard is called directly rather than through the command that owns it,
and each has a control asserting the shape that must still pass. A test that
only asserts a refusal cannot tell a guard that fires correctly from one that
fires always, and `_delivery_reason` in particular refuses for six distinct
reasons -- a fixture that tripped an earlier one would "pass" while proving
nothing about the trailer check it was written for.
"""

from __future__ import annotations

import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

import sd_lib  # noqa: E402
import sd_work  # noqa: E402

#: The message that cost sd:5 its delivery, reduced to the line that did it.
DEMOTED = (
    "chore(work): record the delivery\n"
    "\n"
    "Body paragraph.\n"
    "\n"
    "Delivers: sd:7\n"
    "\n"
    "Co-Authored-By: Someone <nobody@example.invalid>\n"
)

#: The same message with the same two trailers, contiguous. Every assertion
#: about `DEMOTED` is paired with one about this, because the difference
#: between them is one blank line and that is the entire subject.
CONTIGUOUS = (
    "chore(work): record the delivery\n"
    "\n"
    "Body paragraph.\n"
    "\n"
    "Delivers: sd:7\n"
    "Co-Authored-By: Someone <nobody@example.invalid>\n"
)


#: What GitHub appends to a squash whose message already ends in a trailer
#: block: its co-author line, contiguously. Measured over `origin/main` at
#: a593db65: every one of the 187 squashes whose body did *not* end in a
#: trailer block got the line as a new paragraph, and both of the 2 whose
#: body did (dependabot's `Signed-off-by:`) got it joined to the block.
GITHUB_COAUTHOR = "Co-authored-by: Someone <nobody@example.invalid>\n"

#: The attribution paragraph every assistant-written pull-request body ends
#: with, spelled as the template spells it.
ATTRIBUTION = (
    "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"
    "https://claude.ai/code/session_01EXAMPLE\n"
)

#: A squashed pull request composed per `.github/PULL_REQUEST_TEMPLATE.md`
#: since sd:640: attribution paragraph, then the trailer block, then what
#: GitHub appends. The trailers stay the last paragraph.
SQUASHED_TEMPLATE = (
    "fix(thing): the change (#99)\n"
    "\n"
    "## Summary\n"
    "\n"
    "- The change.\n"
    "\n"
    + ATTRIBUTION
    + "\n"
    "Item: sd:7\n"
    "Delivers: sd:7\n"
    "Refs: sd:8\n"
    + GITHUB_COAUTHOR
)

#: The same pull request in the order the template had before sd:640, which
#: is the shape of 9c789ad3 (#887): trailers, then attribution, then GitHub's
#: line as a paragraph of its own. Four of the seven `Delivers:` merges on
#: main had this shape, and `--delivered-by` refused every one.
SQUASHED_ATTRIBUTION_LAST = (
    "fix(thing): the change (#99)\n"
    "\n"
    "## Summary\n"
    "\n"
    "- The change.\n"
    "\n"
    "Item: sd:7\n"
    "Delivers: sd:7\n"
    "Refs: sd:8\n"
    "\n"
    + ATTRIBUTION
    + "\n"
    + GITHUB_COAUTHOR
)

TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"


def git_trailers(message: str) -> set[str]:
    """The trailer names `git interpret-trailers --parse` reads out of `message`."""
    parsed = subprocess.run(
        ["git", "interpret-trailers", "--parse"], input=message,
        capture_output=True, text=True, check=True, timeout=30)
    return {line.partition(":")[0] for line in parsed.stdout.splitlines() if line}


class TrailerBlockTests(unittest.TestCase):
    """`sd_lib.trailer_block` and `sd_lib.demoted_trailers`, on their own."""

    def test_a_squash_in_the_template_order_keeps_its_trailers(self) -> None:
        """sd:640. Attribution above, trailers last, GitHub's line joined on.

        Asserted against git as well as against the two readers, because git
        is the reader whose answer decides whether the delivery exists.
        """
        self.assertEqual((), sd_lib.demoted_trailers(SQUASHED_TEMPLATE))
        block = sd_lib.trailer_block(SQUASHED_TEMPLATE).splitlines()
        self.assertIn("Delivers: sd:7", block)
        self.assertIn("Refs: sd:8", block)
        self.assertEqual({"Item", "Delivers", "Refs", "Co-authored-by"},
                         git_trailers(SQUASHED_TEMPLATE))

    def test_a_squash_with_the_attribution_last_loses_its_trailers(self) -> None:
        """The control, and the defect: the same body in the old order."""
        self.assertEqual(("Item: sd:7", "Delivers: sd:7"),
                         sd_lib.demoted_trailers(SQUASHED_ATTRIBUTION_LAST))
        self.assertNotIn("Delivers: sd:7",
                         sd_lib.trailer_block(SQUASHED_ATTRIBUTION_LAST).splitlines())
        self.assertEqual({"Co-authored-by"}, git_trailers(SQUASHED_ATTRIBUTION_LAST))

    def test_the_pull_request_template_ends_in_the_trailer_block(self) -> None:
        """The template is the shape every hand-written body starts from, so
        it is pinned here: its last paragraph is trailers and nothing else,
        `Delivers:` is among them, and the attribution line sits above it."""
        template = TEMPLATE.read_text(encoding="utf-8")
        block = sd_lib.trailer_block(template).splitlines()
        self.assertTrue(block)
        for line in block:
            self.assertRegex(line, r"^[A-Za-z-]+: \S")
        self.assertIn("Delivers:", {line.partition(" ")[0] for line in block})
        self.assertLess(template.index("Generated with"), template.index(block[0]))
        self.assertEqual((), sd_lib.demoted_trailers(template))

    def test_a_blank_line_before_the_last_block_demotes_the_trailer(self) -> None:
        self.assertEqual(("Delivers: sd:7",), sd_lib.demoted_trailers(DEMOTED))

    def test_a_contiguous_block_demotes_nothing(self) -> None:
        """The control. Same trailers, same message, one blank line fewer."""
        self.assertEqual((), sd_lib.demoted_trailers(CONTIGUOUS))

    def test_the_block_is_the_last_paragraph_and_git_agrees(self) -> None:
        """Not asserted against a second implementation of the same slice.

        `git interpret-trailers --parse` is the reader whose answer decides
        whether a delivery exists, so the property under test is agreement
        with it and not agreement with a rule restated here.
        """
        for message, expected in ((DEMOTED, {"Co-Authored-By"}),
                                  (CONTIGUOUS, {"Delivers", "Co-Authored-By"})):
            with self.subTest(message=message.splitlines()[0]):
                parsed = subprocess.run(
                    ["git", "interpret-trailers", "--parse"], input=message,
                    capture_output=True, text=True, check=True, timeout=30)
                self.assertEqual(
                    expected,
                    {line.partition(":")[0] for line in parsed.stdout.splitlines() if line},
                )
                self.assertEqual(
                    {line.partition(":")[0] for line in parsed.stdout.splitlines() if line},
                    {line.partition(":")[0]
                     for line in sd_lib.trailer_block(message).splitlines() if line},
                )

    def test_a_quoted_trailer_in_prose_is_not_a_demoted_one(self) -> None:
        """The column-zero anchor, which is what keeps this usable here.

        This repository's commit messages discuss `Delivers:` constantly. An
        unanchored match would make every one of them a finding, and a check
        that fires on its own documentation is a check nobody leaves on.
        """
        message = (
            "docs: explain the trailer\n"
            "\n"
            "The squash should carry `Delivers: sd:7`, and an indented\n"
            "  Delivers: sd:7\n"
            "is prose about one.\n"
            "\n"
            "Item: sd:7\n"
        )
        self.assertEqual((), sd_lib.demoted_trailers(message))

    def test_a_message_that_is_only_a_trailer_block_demotes_nothing(self) -> None:
        self.assertEqual((), sd_lib.demoted_trailers("Delivers: sd:7\n"))


class DeliveryReasonTests(unittest.TestCase):
    """`sd_work._delivery_reason`: what a task's closure may name as evidence.

    A real repository, because every refusal here is a fact about git that a
    stubbed `git_output` would let the test invent. The repository has no
    remote, which is the `_verified_tip` branch that requires `main`.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name).resolve()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "file.txt").write_text("one\n", encoding="utf-8")
        self.git("add", "file.txt")
        self.git("commit", "-q", "-m", CONTIGUOUS)
        self.delivered = self.git("rev-parse", "HEAD")
        self.row = {"id": 7, "repo": str(self.root)}

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", "-C", str(self.root), *args],
                                capture_output=True, text=True, check=True, timeout=30)
        return result.stdout.strip()

    def test_a_contiguous_delivers_trailer_on_main_is_recorded(self) -> None:
        """The control, and the only passing shape this function has."""
        self.assertEqual(
            f"delivered at {self.delivered} on refs/heads/main",
            sd_work._delivery_reason(self.row, self.delivered),
        )

    def test_a_demoted_delivers_trailer_is_named_as_demoted(self) -> None:
        """Not "no trailer". The author wrote one; git will not read it back.

        Told apart on purpose: "carries no `Delivers:`" sends a caller to write
        a line that is already there, which is how sd:5 needed a second commit
        to say what the first one said.
        """
        (self.root / "file.txt").write_text("two\n", encoding="utf-8")
        self.git("commit", "-q", "-a", "-m", DEMOTED)
        commit = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(sd_work.WorkRefusal, "outside the trailer block"):
            sd_work._delivery_reason(self.row, commit)

    def test_a_commit_with_no_delivers_trailer_is_refused(self) -> None:
        (self.root / "file.txt").write_text("three\n", encoding="utf-8")
        self.git("commit", "-q", "-a", "-m", "chore: no trailer at all\n")
        commit = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(sd_work.WorkRefusal, "carries no `Delivers: sd:7`"):
            sd_work._delivery_reason(self.row, commit)

    def test_two_delivers_trailers_on_one_commit_are_read_one_per_line(self) -> None:
        """e6c2cb20 (#869) carries `Delivers: sd:580` and `Delivers: sd:572`.

        `git log --format=%(trailers:key=Delivers,valueonly)` prints those as
        `sd:580sd:572` when the caller drops the newlines, and a reader that
        joined the values would hold one id naming nothing (sd:640, note
        #1225). Every reader in `bin/` takes the block a line at a time; this
        pins that for the one a task's closure goes through, and for the one
        `sd work deliver` and `sd-status` share.
        """
        (self.root / "file.txt").write_text("five\n", encoding="utf-8")
        message = (
            "fix(gates): two gates in one squash\n"
            "\n"
            "Delivers: sd:7\n"
            "Delivers: sd:9\n"
            "Co-Authored-By: Someone <nobody@example.invalid>\n"
        )
        self.git("commit", "-q", "-a", "-m", message)
        commit = self.git("rev-parse", "HEAD")
        for item in (7, 9):
            with self.subTest(item=item):
                self.assertEqual(
                    f"delivered at {commit} on refs/heads/main",
                    sd_work._delivery_reason({"id": item, "repo": str(self.root)}, commit),
                )
                self.assertTrue(sd_lib._closes(message, f"sd:{item}"))
        self.assertFalse(sd_lib._closes(message, "sd:7sd:9"))
        with self.assertRaisesRegex(sd_work.WorkRefusal, "carries no `Delivers: sd:8`"):
            sd_work._delivery_reason({"id": 8, "repo": str(self.root)}, commit)

    def test_a_delivers_trailer_for_another_item_is_refused(self) -> None:
        """The row's own id, never any `Delivers:` line the commit happens to
        carry -- a batched squash names several and closes exactly one."""
        with self.assertRaisesRegex(sd_work.WorkRefusal, "carries no `Delivers: sd:8`"):
            sd_work._delivery_reason({"id": 8, "repo": str(self.root)}, self.delivered)

    def test_a_commit_off_the_default_branch_is_not_reachable(self) -> None:
        self.git("checkout", "-q", "-b", "side")
        (self.root / "file.txt").write_text("four\n", encoding="utf-8")
        self.git("commit", "-q", "-a", "-m", CONTIGUOUS)
        commit = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        with self.assertRaisesRegex(sd_work.WorkRefusal, "not reachable from refs/heads/main"):
            sd_work._delivery_reason(self.row, commit)

    def test_an_abbreviated_commit_is_refused(self) -> None:
        with self.assertRaisesRegex(sd_work.WorkRefusal, "full lowercase commit ID"):
            sd_work._delivery_reason(self.row, self.delivered[:12])

    def test_a_task_belonging_to_no_checkout_has_nothing_to_verify(self) -> None:
        with self.assertRaisesRegex(sd_work.WorkRefusal, "belongs to no checkout"):
            sd_work._delivery_reason({"id": 7, "repo": None}, self.delivered)


class TaskDeliveryCLITests(unittest.TestCase):
    """The whole of sd:591, through the real `sd` binary on a scratch database.

    `sd work deliver` refuses a `kind=task` row, so before this the only way
    to close one was `sd task status done`, which recorded who and when and
    nothing about what shipped it. Four items closed on 2026-09-12 lost their
    SHA that way. The evidence now goes on the transition, in the sentence
    `sd_db.progress` writes for a work item, so one query over the status
    history answers "what delivered this" for either kind.
    """

    def host(self):
        """One `TaskCLI` fixture: a scratch HOME and its own sd database."""
        from tests.test_sd_work import TaskCLI

        class Case(TaskCLI):
            def runTest(self) -> None:  # pragma: no cover - fixture host only
                pass

        case = Case()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def repository(self, case):
        """A registered checkout the scratch database will accept a task in."""
        import sd_db
        import sd_db.repos

        root = (case.home / "checkout").resolve()
        root.mkdir()
        for command in (("init", "-q", "-b", "main"), ("config", "user.name", "Fixture"),
                        ("config", "user.email", "fixture@example.invalid")):
            subprocess.run(["git", "-C", str(root), *command], check=True, timeout=30)
        with sd_db.connect(sd_db.default_path(case.home), write=True) as connection:
            sd_db.repos.upsert_repo(connection, str(root), status_source="row")
        return root

    def commit(self, root: pathlib.Path, message: str, content: str) -> str:
        (root / "file.txt").write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "file.txt"], check=True, timeout=30)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", message],
                       check=True, timeout=30)
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True,
                              timeout=30).stdout.strip()

    def statuses(self, case, item: int) -> list[str]:
        """The item's status-change history, which is where the evidence lands."""
        import sd_db

        with sd_db.connect(sd_db.default_path(case.home), write=False) as connection:
            return [row["body"] for row in connection.execute(
                "SELECT body FROM note WHERE item = ? AND kind = 'status_change' ORDER BY id",
                (item,))]

    def test_a_task_closes_carrying_the_commit_that_delivered_it(self) -> None:
        case = self.host()
        root = self.repository(case)
        state = json.loads(case.call("task", "add", "Fix the thing", "--json",
                                     cwd=root).stdout)
        item = state["item"]["id"]
        sha = self.commit(root, f"fix: the thing\n\nDelivers: sd:{item}\n", "one\n")

        done = json.loads(case.call("task", "status", item, "done",
                                    "--delivered-by", sha, "--json", cwd=root).stdout)
        self.assertEqual("done", done["item"]["status"])
        self.assertIn(f"delivered at {sha} on refs/heads/main", self.statuses(case, item)[-1])

    def test_a_plain_close_records_no_commit_which_is_the_gap(self) -> None:
        """The control, and the state the flag exists to leave behind.

        Closing without `--delivered-by` still works and still records nothing
        about delivery. Asserted so a later change that started inventing
        evidence for an unverified close would fail here rather than pass
        quietly as an improvement.
        """
        case = self.host()
        root = self.repository(case)
        state = json.loads(case.call("task", "add", "Fix the thing", "--json",
                                     cwd=root).stdout)
        item = state["item"]["id"]
        case.call("task", "status", item, "done", cwd=root)
        self.assertNotIn("delivered at", self.statuses(case, item)[-1])

    def test_an_unverifiable_commit_leaves_the_task_open(self) -> None:
        """Refused before the status moves, not after: a task closed and then
        found to have no evidence is the hole, not a smaller version of it."""
        case = self.host()
        root = self.repository(case)
        state = json.loads(case.call("task", "add", "Fix the thing", "--json",
                                     cwd=root).stdout)
        item = state["item"]["id"]
        sha = self.commit(root, "fix: the thing, with no trailer\n", "one\n")

        refused = case.call("task", "status", item, "done", "--delivered-by", sha,
                            code=1, cwd=root)
        self.assertIn("carries no `Delivers:", refused.stderr)
        readback = json.loads(case.call("store", "item", item, "--json", cwd=root).stdout)
        self.assertEqual("planning", readback["item"]["status"])

    def test_work_deliver_on_a_task_names_the_flag_that_records_it(self) -> None:
        """The refusal sd:591 was filed against, with the remedy in it.

        The library's own sentence -- "this operation is for work items" --
        leaves a caller holding a real merged SHA with nowhere to put it, and
        the workaround it produced was a hand-written note.
        """
        case = self.host()
        root = self.repository(case)
        state = json.loads(case.call("task", "add", "Fix the thing", "--json",
                                     cwd=root).stdout)
        item = state["item"]["id"]
        sha = self.commit(root, f"fix: the thing\n\nDelivers: sd:{item}\n", "one\n")

        refused = case.call("work", "deliver", item, sha, code=1, cwd=root)
        self.assertIn(f"--delivered-by {sha}", refused.stderr)
        self.assertIn("ordinary task", refused.stderr)


class ShipMergeGuardTests(unittest.TestCase):
    """`sd-ship merge` refuses to dispatch a squash that demotes its own trailer.

    The one moment the pack composes a message that git will parse later, so
    this reaches the real composition through the real merge path rather than
    asserting about a string. `tests.test_sd_ship` owns the fixture; it is
    hosted here rather than subclassed so this module collects its own tests
    and not that file's forty.
    """

    def host(self):
        """One `ShipCase` fixture, set up and torn down with this test."""
        from tests.test_sd_ship import ShipCase

        class Case(ShipCase):
            def runTest(self) -> None:  # pragma: no cover - fixture host only
                pass

        case = Case()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def merge_operation(self, case):
        from tests.test_sd_ship import _git

        case.prepare()
        return case.operation("merge", "--manual", "--expected-head",
                              _git(case.root, "rev-parse", "HEAD"))

    def test_a_well_formed_squash_message_still_merges(self) -> None:
        """The control. Without it, a guard that refused every merge passes."""
        self.assertEqual("merged", self.merge_operation(self.host()).merge()["phase"])

    def test_a_body_ending_in_a_trailer_line_is_refused_before_dispatch(self) -> None:
        from tests.test_sd_ship import ship

        case = self.host()
        operation = self.merge_operation(case)
        # `merge` appends `Item:` after a blank line, so a body whose own last
        # line reads as a trailer lands one paragraph above the block and git
        # never reads it back. Nothing about the line looks wrong in the PR.
        operation.state["body"] = (
            operation.state["body"].rstrip() + f"\n\nDelivers: sd:{case.item}")
        with self.assertRaisesRegex(ship.Refusal, "outside the trailer block"):
            operation.merge()
        self.assertFalse([call for call in case.remote.calls if call.method == "PUT"],
                         "the squash must not be dispatched")


class ReviewFindingsTests(unittest.TestCase):
    """`sd-pr-state` counts findings a review states outside its comments.

    Read directly rather than through `collect`, which would need a `gh`. The
    property is about one string, and a fixture that reached GitHub to assert
    it would be asserting about the fixture.
    """

    #: The shape `copilot-pull-request-reviewer` actually wrote on #861, cut to
    #: the heading that matters. That pull request showed zero inline comments,
    #: so every count a reader had access to said the review was clean.
    BODY = (
        "### Needs a closer look\n"
        "\n"
        "Three moderate review findings remain unresolved.\n"
        "\n"
        "<details>\n"
        "<summary>Review details</summary>\n"
        "\n"
        "### Suppressed comments (3)\n"
        "\n"
        "**tests/test_dashboard_plugins.py:186**\n"
        "* `os.kill(pid, 0)` also succeeds for a zombie.\n"
        "</details>\n"
    )

    def state(self):
        """`bin/sd-pr-state`, imported the way `tests/test_sd_status.py` does."""
        import importlib.machinery
        import importlib.util

        path = ROOT / "bin" / "sd-pr-state"
        loader = importlib.machinery.SourceFileLoader("sd_pr_state_delivery", str(path))
        spec = importlib.util.spec_from_file_location(loader.name, str(path), loader=loader)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[loader.name] = module
        loader.exec_module(module)
        return module

    def test_findings_stated_only_in_a_review_body_are_counted(self) -> None:
        found = self.state().review_findings(
            [{"author": {"login": "copilot-pull-request-reviewer"}, "body": self.BODY}])
        self.assertEqual(3, found["in_body"])
        self.assertEqual(["copilot-pull-request-reviewer"], found["reviewers"])

    def test_a_review_that_states_no_suppressed_findings_counts_zero(self) -> None:
        """The control. An ordinary review must not become a standing finding."""
        found = self.state().review_findings(
            [{"author": {"login": "someone"}, "body": "Looks good, one nit inline."}])
        self.assertEqual(0, found["in_body"])
        self.assertEqual(1, found["reviews"])

    def test_absent_or_malformed_reviews_are_not_an_error(self) -> None:
        state = self.state()
        for reviews in (None, [], "reviews", [None, 7]):
            with self.subTest(reviews=reviews):
                self.assertEqual(0, state.review_findings(reviews)["in_body"])

    def test_the_line_is_printed_only_when_there_is_something_to_print(self) -> None:
        """`sd-status` prints `render_pulls` too, so a zero must stay silent."""
        state = self.state()
        record = {
            "number": 861, "title": "t", "draft": False, "mergeable": "MERGEABLE",
            "merge_state": "CLEAN", "review_decision": "NONE", "head": "topic",
            "base": "main", "checks": {}, "checks_total": 0, "failing": [],
            "behind_by": 0,
            "review_findings": {"reviews": 1, "in_body": 3, "reviewers": ["copilot"]},
        }
        result = {"available": True, "reason": "", "pull_requests": [record]}
        loud = io.StringIO()
        state.render_pulls(result, loud)
        self.assertIn("3 stated by copilot in a review body", loud.getvalue())

        record["review_findings"] = {"reviews": 1, "in_body": 0, "reviewers": []}
        quiet = io.StringIO()
        state.render_pulls(result, quiet)
        self.assertNotIn("review findings", quiet.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
