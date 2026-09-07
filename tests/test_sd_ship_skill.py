"""`sd-ship` is a skill, so criteria 2, 3 and 32 are claims about its text.

There is no `bin/sd-ship`. The eight steps are prose an agent follows, which
is why criterion 2 says "asserted against the skill text, not inferred": the
only place "the command does not do X" can be checked is the file that tells
the agent what to do. Two consequences shape every assertion here.

**Absence carries the weight.** A test that greps for a sentence passes
forever and catches nothing -- it breaks on a rewrite that preserves the
meaning and survives a rewrite that destroys it. So the checks aim at the
forbidden thing: a `--delete-branch` on a merge, a `sleep` or a loop in the
settle step, `sd-spec` inside the sequence, a placeholder `Work:` line, a
review cap restated in the skill. Where presence must be asserted it anchors
on a flag or a command token (`--watch`, `--match-head-commit`,
`delete_branch_on_merge`) rather than on the sentence around it, or on a
value derived from `WORKFLOW.md` rather than typed here.

**Commands are parsed, not matched.** The backticked spans are extracted and
the ones that begin with `git` or `gh` are read as command lines. A deletion
flag added to the merge fails here; the paragraph that names
`--delete-branch` in order to forbid it does not, because it is not a
command.

Criterion 32's merge test goes one step further than reading. It takes the
merge command the file prescribes, fills in the head the lane reviewed, and
runs it against a model of GitHub's documented merge semantics -- `sha=`
given and the head moved since it was given is a refusal and no merge. The
control beside it strips `--match-head-commit` from the same command and
watches the same model merge the moved head, which is what makes the first
test mean anything: the flag is what refuses, not the model. Nothing here
reaches the network or invokes `gh`.

The reviewer-order comparison at the end overlaps `tests/test_sd_registry.py`
on purpose. That file keeps the two readers honest for the registry's own
reasons; criterion 32 names the same comparison as one of its four tests, and
both must pass.
"""

from __future__ import annotations

import pathlib
import re
import shlex
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_registry  # noqa: E402

SKILL = REPO_ROOT / "skills/sd-ship/SKILL.md"
WORKFLOW = REPO_ROOT / "WORKFLOW.md"
RULE = REPO_ROOT / ".claude/rules/sd-planning-adversarial-review.md"

SKILL_TEXT = SKILL.read_text(encoding="utf-8")

#: A `Work:` line standing in for an item that does not exist. The criterion
#: forbids the form, so the test names the form rather than a sentence about
#: it.
PLACEHOLDER_WORK = re.compile(
    r"Work:\s*\(?(?:none|n/?a|tbd|todo|pending|unknown|null|-|—)"
    r"(?=[\s`).,]|$)",
    re.IGNORECASE,
)

#: Anything that removes a branch, on either side. `--delete\b` covers
#: `--delete-branch` as well; both spellings are listed because a merge and a
#: push carry different ones and a reader should see both named.
DELETION = re.compile(
    r"--delete-branch|--delete\b|\bbranch\s+-[dD]\b|\bpush\s+\S+\s+:"
    r"|:refs/heads|-X\s*DELETE|--method\s+DELETE"
)

#: A settle step that re-asks. `--watch` is one wait; these are a loop.
POLLING = re.compile(r"\bsleep\b|\bwhile\b|\buntil\b|\bdone\b|\bwatch\s+-n\b")

#: Words that would turn criterion 3's warning into a gate. The criterion is
#: explicit that `sd-ship` warns *and ships*, and a warning that holds the
#: commit is a different command from the specified one.
REFUSAL = ("refus", "block", "abort", "halt", "reject", "does not commit")


def section(text: str, heading: str) -> str:
    """One `## ` section of a markdown page, its heading excluded."""

    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = start
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    return "\n".join(lines[start:end])


def sequence_section() -> str:
    return section(SKILL_TEXT, "## The sequence")


def autonomous_section() -> str:
    return section(SKILL_TEXT, "## The autonomous lane (R10-D1)")


def steps() -> dict[int, str]:
    """The numbered steps of the sequence, each with its continuation lines.

    A step owns the indented lines under it and stops at the next number or
    at the first unindented paragraph. That boundary is the point: the
    paragraph excluding `sd-spec` from the sequence sits after step 8 and
    must not be read as part of it, or criterion 2's `sd-spec` check would
    pass on a file that ran `sd-spec` in step 8.
    """

    found: dict[int, str] = {}
    current: int | None = None
    for line in sequence_section().splitlines():
        started = re.match(r"^(\d+)\.\s", line)
        if started:
            current = int(started.group(1))
            found[current] = line
            continue
        if current is None:
            continue
        if not line.strip() or line.startswith((" ", "\t")):
            found[current] += "\n" + line
            continue
        current = None
    return found


def spans(text: str) -> list[str]:
    """Every backticked span, newlines and indentation collapsed."""

    return [
        " ".join(match.group(1).split())
        for match in re.finditer(r"`([^`]+)`", text, re.DOTALL)
    ]


def commands(text: str) -> list[str]:
    """The backticked spans that are command lines rather than names."""

    return [span for span in spans(text) if span.startswith(("git ", "gh "))]


def sentences(text: str) -> list[str]:
    """The text's sentences, wrapping collapsed.

    Coarse on purpose. What it buys is the difference between a file that
    states a property somewhere and a file that states it about the thing at
    hand: three tokens scattered over a step say much less than the same
    three in one sentence.
    """

    return re.split(r"(?<=\.)\s+", " ".join(text.split()))


def bullet_containing(text: str, needle: str) -> str:
    """The one `- ` bullet holding `needle`, with its wrapped lines.

    Narrower than the enclosing block on purpose. `WORKFLOW.md`'s Defaults
    list is one unbroken block, and reading the whole of it for the words
    before "repository" would collect "a repository you own" from three
    bullets away.
    """

    lines = text.splitlines()
    hit = next(i for i, line in enumerate(lines) if needle in line)
    start = hit
    while start >= 0 and not lines[start].startswith("- "):
        start -= 1
    if start < 0:
        raise AssertionError(f"{needle!r} is in no bullet")
    end = hit + 1
    while end < len(lines) and lines[end].startswith(" ") and lines[end].strip():
        end += 1
    return "\n".join(lines[start:end])


def repositories_named(block: str) -> set[str]:
    """The repositories a `Needed-by:` rule applies to, read off the rule."""

    words = {
        match.group(1).lower()
        for match in re.finditer(r"\b([A-Za-z]+)\s+repository\b", block)
    }
    words -= {"the", "a", "an", "that", "this", "shared", "upstream"}
    if "pack" in block:
        words.add("pack")
    return words


def needed_by_values(block: str) -> set[str]:
    """The accepted trailer values, derived from whichever page is read.

    Every `<...>` collapses to one token so the item form compares equal
    across two pages that word the placeholder differently.
    """

    values: set[str] = set()
    for span in spans(block):
        match = re.match(r"Needed-by:\s*(.+)", span)
        if not match:
            continue
        for part in match.group(1).split("|"):
            values.add(re.sub(r"<[^>]+>", "<item>", part.strip()))
    return values


def code_row_cap() -> str:
    """The *code, before merge* cap, from the table that owns it."""

    for line in RULE.read_text(encoding="utf-8").splitlines():
        if line.startswith("| Development |") and "Code, before merge" in line:
            return line.rsplit("|", 2)[1].strip()
    raise AssertionError("the review table has no code-before-merge row")


def merge_argv(command: str, head: str) -> list[str]:
    """The prescribed merge, as argv, with `head` as the sha it names.

    The sha is substituted by position after `--match-head-commit` rather
    than by matching the placeholder's wording, so rewording
    `<the reviewed sha>` does not quietly stop the substitution and leave the
    test asserting against a literal nobody passes.
    """

    filled = re.sub(r"<[^>]+>", "X", command).replace("#N", "#1")
    argv = shlex.split(filled)
    if "--match-head-commit" in argv:
        argv[argv.index("--match-head-commit") + 1] = head
    return argv


def without_the_flag(argv: list[str]) -> list[str]:
    index = argv.index("--match-head-commit")
    return argv[:index] + argv[index + 2:]


class FakeGitHub:
    """GitHub's merge semantics, and no rule of its own.

    `PUT /repos/{owner}/{repo}/pulls/{n}/merge` takes an optional `sha=`;
    where it is given and the pull request's head is no longer that sha the
    answer is 405 and nothing merges. `gh pr merge --match-head-commit` is
    that parameter. The model knows nothing about reviews -- it cannot tell a
    reviewed head from any other -- which is what leaves the refusal
    attributable to the flag the skill prescribes.
    """

    def __init__(self, head: str) -> None:
        self.head = head
        self.merged: str | None = None

    def run(self, argv: list[str]) -> tuple[int, str]:
        named = None
        if "--match-head-commit" in argv:
            named = argv[argv.index("--match-head-commit") + 1]
        if named is not None and named != self.head:
            return 1, (
                f"failed to merge: the head is {self.head}, "
                f"not the {named} the call named"
            )
        self.merged = self.head
        return 0, "merged"


REVIEWED = "a" * 40
MOVED = "b" * 40


class TheSequenceParses(unittest.TestCase):
    """The controls. Every check below reads one of these three things, and
    a parser returning nothing would make all of them pass over any file."""

    def test_the_sequence_has_eight_numbered_steps(self) -> None:
        self.assertEqual(sorted(steps()), list(range(1, 9)))

    def test_every_step_has_a_body(self) -> None:
        for number, body in steps().items():
            self.assertGreater(len(body), 60, f"step {number} is a stub")

    def test_the_command_scan_reaches_the_real_commands(self) -> None:
        found = commands(sequence_section())
        self.assertIn("git fetch -p", found)
        self.assertTrue(
            any(span.startswith("gh pr merge") for span in found),
            "the merge command was not found in the sequence",
        )


class AChangeWithNoWorkItem(unittest.TestCase):
    """Criterion 2, all four clauses, against the file's own text."""

    def test_no_step_runs_sd_spec(self) -> None:
        offenders = [n for n, body in steps().items() if "sd-spec" in body]
        self.assertEqual(offenders, [], f"sd-spec is inside steps {offenders}")

    def test_the_file_still_says_where_sd_spec_runs(self) -> None:
        """The other half: the token vanishing from the page entirely would
        satisfy the check above while telling the reader nothing."""

        outside = sequence_section()
        for body in steps().values():
            outside = outside.replace(body, "")
        self.assertIn("sd-spec", outside)

    def test_no_placeholder_work_line_anywhere_in_the_file(self) -> None:
        self.assertEqual(PLACEHOLDER_WORK.findall(SKILL_TEXT), [])

    def test_the_placeholder_pattern_recognises_one(self) -> None:
        """A dead pattern would clear the check above on any file."""

        for form in ("Work: none", "Work: n/a", "Work: TBD", "Work: -"):
            self.assertTrue(PLACEHOLDER_WORK.search(form), form)
        self.assertIsNone(PLACEHOLDER_WORK.search("a `Work:` line resolving"))

    def test_the_work_line_is_stated_as_conditional_on_the_item(self) -> None:
        holding = [body for body in steps().values() if "Work:" in body]
        self.assertTrue(holding, "no step mentions the Work: line")
        for body in holding:
            self.assertTrue(
                any(mark in body for mark in ("absent", "omitted", "only when")),
                "the Work: line is described unconditionally",
            )

    def test_no_step_carries_a_branch_deletion_command(self) -> None:
        for number, body in steps().items():
            for command in commands(body):
                self.assertIsNone(
                    DELETION.search(command),
                    f"step {number} deletes a branch: {command}",
                )

    def test_the_deletion_pattern_recognises_the_forms(self) -> None:
        for form in (
            "gh pr merge --squash --delete-branch",
            "git push origin --delete topic",
            "git push origin :topic",
            "git branch -D topic",
        ):
            self.assertTrue(DELETION.search(form), form)
        for kept in ("git fetch -p", "git worktree list", "gh pr checks 1 --watch"):
            self.assertIsNone(DELETION.search(kept), kept)

    def test_the_last_step_leaves_the_remote_branch_to_the_repository(self) -> None:
        """Anchored on the setting's name, which is what does the removing."""

        self.assertIn("delete_branch_on_merge", steps()[8])

    def test_the_settle_step_issues_no_polling_loop(self) -> None:
        """Every backticked span, not only the command-shaped ones.

        A polling loop starts with `while`, so the command filter used
        elsewhere in this file walks straight past the shape this check
        exists to catch. It did, until a mutation put a loop in step 5 and
        only the wait-once test noticed.
        """

        for span in spans(steps()[5]):
            self.assertIsNone(POLLING.search(span), f"a loop in step 5: {span}")

    def test_the_settle_step_waits_once_with_watch(self) -> None:
        waits = [c for c in commands(steps()[5]) if c.startswith("gh pr checks")]
        self.assertEqual(len(waits), 1, f"step 5 issues {len(waits)} waits")
        self.assertIn("--watch", waits[0])

    def test_the_polling_pattern_recognises_a_loop(self) -> None:
        for form in (
            "while true; do gh pr checks 1; sleep 10; done",
            "sleep 30",
            "watch -n 5 gh pr checks 1",
        ):
            self.assertTrue(POLLING.search(form), form)
        self.assertIsNone(POLLING.search("gh pr checks 1 --watch"))


class TheNeededByTrailer(unittest.TestCase):
    """Criterion 3: the warning path, the pass path, and one definition.

    The accepted forms and the three repositories are read out of
    `WORKFLOW.md` rather than typed here. A second, drifting definition in
    the skill is the defect this repository keeps finding, and a test holding
    its own copy of the answer cannot see it.
    """

    def setUp(self) -> None:
        self.policy = bullet_containing(
            WORKFLOW.read_text(encoding="utf-8"), "Needed-by:"
        )
        self.passage = next(
            body for body in steps().values() if "Needed-by:" in body
        )

    def test_the_policy_bullet_yields_something_to_compare(self) -> None:
        self.assertGreaterEqual(len(needed_by_values(self.policy)), 3)
        self.assertEqual(len(repositories_named(self.policy)), 3)

    def test_the_skill_accepts_the_forms_the_policy_defines(self) -> None:
        self.assertEqual(
            needed_by_values(self.passage), needed_by_values(self.policy)
        )

    def test_the_skill_names_the_repositories_the_policy_names(self) -> None:
        for repository in repositories_named(self.policy):
            self.assertIn(repository, self.passage)

    def test_a_missing_trailer_warns(self) -> None:
        self.assertTrue(re.search(r"\bwarn", self.passage), "nothing warns")

    def test_the_warning_does_not_hold_the_ship(self) -> None:
        lowered = self.passage.lower()
        for word in REFUSAL:
            self.assertNotIn(word, lowered, f"the warning became a gate: {word}")
        self.assertTrue(
            any(mark in lowered for mark in ("continues", "ships", "with the commit")),
            "the passage never says the run goes on",
        )

    def test_the_carried_trailer_passes_quietly(self) -> None:
        lowered = self.passage.lower()
        self.assertTrue(
            any(
                mark in lowered
                for mark in ("nothing said", "no warning", "says nothing", "silent")
            ),
            "the pass path is not stated",
        )


class TheReviewedHead(unittest.TestCase):
    """Criterion 32: only a reviewed head, or a verified fix of it, ships."""

    def merge_command(self) -> str:
        found = [c for c in commands(steps()[6]) if c.startswith("gh pr merge")]
        self.assertEqual(len(found), 1, f"step 6 prescribes {len(found)} merges")
        return found[0]

    def test_a_fix_gets_one_further_pass_over_its_own_diff(self) -> None:
        body = steps()[2]
        self.assertIn("diff", body)
        self.assertIn("since", body)
        self.assertIn("passed", body)

    def test_the_skill_reads_that_cap_from_the_table_and_states_none(self) -> None:
        """The rule file owns the caps; a skill restating one is how the two
        drift. So the cap's own text, taken from the table, must not appear
        here, and step 2 must point at the file it comes from."""

        cap = code_row_cap()
        self.assertTrue(cap, "the code-before-merge row has no cap")
        self.assertNotIn(cap, SKILL_TEXT)
        self.assertIn(".claude/rules/sd-planning-adversarial-review.md", steps()[2])

    def test_the_push_refuses_a_head_the_lane_has_not_passed(self) -> None:
        """One sentence carries all three, rather than the step between them.

        Step 3 also says that `--match-head-commit` refuses the same head at
        GitHub, and that sentence holds a refusal and a sha of its own. Read
        token by token across the whole step it stands in for the local
        refusal and lets it be deleted unnoticed, which is what the first
        version of this test did.
        """

        carried = [
            line
            for line in sentences(steps()[3])
            if "refus" in line and "sha" in line and "passed" in line
        ]
        self.assertTrue(
            carried,
            "no sentence in step 3 refuses a head the lane has not passed "
            "and names its sha",
        )

    def test_the_never_list_forbids_pushing_an_unseen_head(self) -> None:
        never = section(SKILL_TEXT, "## Never").lower()
        self.assertIn("never push a head the local lane has not seen", never)

    def test_a_moved_head_is_refused_by_the_merge_the_skill_prescribes(self) -> None:
        """The reviewed head is named in the call; the head moved after the
        review; the model refuses and merges nothing."""

        argv = merge_argv(self.merge_command(), REVIEWED)
        self.assertIn(REVIEWED, argv, "the merge call never names the reviewed head")
        github = FakeGitHub(head=MOVED)
        code, message = github.run(argv)
        self.assertNotEqual(code, 0, "the moved head merged")
        self.assertIsNone(github.merged)
        self.assertIn(REVIEWED, message)

    def test_the_same_merge_is_accepted_when_the_head_did_not_move(self) -> None:
        argv = merge_argv(self.merge_command(), REVIEWED)
        github = FakeGitHub(head=REVIEWED)
        code, _ = github.run(argv)
        self.assertEqual(code, 0)
        self.assertEqual(github.merged, REVIEWED)

    def test_the_flag_is_what_refuses_and_not_the_model(self) -> None:
        """The control. Strip `--match-head-commit` from the same command and
        the same model merges the moved head, so the refusal above belongs to
        the flag rather than to a fixture written to refuse."""

        argv = without_the_flag(merge_argv(self.merge_command(), REVIEWED))
        github = FakeGitHub(head=MOVED)
        code, _ = github.run(argv)
        self.assertEqual(code, 0)
        self.assertEqual(github.merged, MOVED)


class TheLoopStopsAtPullRequestReady(unittest.TestCase):
    """Criterion 32's last clause, on the lane that could break it.

    The autonomous lane is the only part of `sd-ship` that runs without a
    person watching, so it is the only part that could merge one. Its bound
    is asserted as an absence -- no merge and no ready-for-review command
    anywhere in the section -- because that survives a rewrite of the
    paragraph around it.
    """

    def test_the_lane_issues_no_merge_and_no_ready_command(self) -> None:
        for command in commands(autonomous_section()):
            self.assertNotIn("pr merge", command, command)
            self.assertNotIn("pr ready", command, command)

    def test_the_bound_holds_where_nothing_else_would_stop_it(self) -> None:
        lane = autonomous_section()
        self.assertIn("draft", lane)
        self.assertIn("never merges", lane)
        self.assertIn("branch protection", lane)


class TheTwoRegistryReadersAgree(unittest.TestCase):
    """Criterion 32's other clause: one reviewer order, read two ways.

    `sd_db` is installed in this tree, so the branch that applies is the
    comparison. Where it is not installed the first test says so and fails
    rather than skipping -- a skip would leave the pair pinned on one reader.
    """

    def test_the_library_is_installed_so_there_are_two_readers(self) -> None:
        self.assertIsNotNone(
            sd_registry.library(),
            "sd_db is not in this virtualenv; run `make setup`",
        )

    def test_both_readers_give_the_same_reviewer_order(self) -> None:
        shipped = sd_registry.shipped_path(REPO_ROOT)
        by_file = sd_registry.read(shipped, prefer_library=False)
        by_library = sd_registry.read(shipped, prefer_library=True)
        order = [provider.name for provider in by_file.order("reviewer")]
        self.assertNotEqual(order, [], "the registry named no reviewer")
        self.assertEqual(
            order, [provider.name for provider in by_library.order("reviewer")]
        )


if __name__ == "__main__":
    unittest.main()
