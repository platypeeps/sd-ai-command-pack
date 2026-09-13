"""The line-count ceilings, enforced instead of remembered.

The design fixes a ceiling for each part of the replacement world -- the
temporary `migrate-*` tools at 1,500, and `dashboard/` at 4,600 with 2,300 of
it carrying code (R11-D24, with the total re-derived at R11-D29, at R11-D30
and at R11-D38) -- and says in as many words that "caps are
CI tests; a cap is never raised in the PR that busts it". That rule survives
every re-derivation: 4,000 and 4,300 were each set in their own decision
record by a change that fit under the ceiling it replaced, not in a pull
request that did not fit. 4,350 was set the same way at R11-D29, by a change
touching this file and one design record and nothing under `dashboard/`,
while the directory stood at 4,190 against the 4,300 it replaced.

**`bin/` no longer has one.** R11-D48 retired it on 2026-09-11; the record is
the comment above `MIGRATE_CAP` below, where the derivation chain used to be.
Its values stay in `CEILING_HISTORY` as a closed record, because that history
is the evidence the retirement was decided on and deleting it would delete the
argument along with the number.

**Downward-only now attaches to the code cap, not to the dashboard total.**
R11-D17 said 4,000 could only fall; R11-D24 raised it anyway, and said so in
its own record rather than in the change that crossed it. The reason is the
thing this file measures: 46% of `dashboard/` is comments, docstrings and
blanks, which is house style, and one ceiling over both halves means a branch
and a paragraph bid for the same line -- the paragraph loses, because the
branch is what the change is for. So the total may be re-derived with an
itemisation, and `DASHBOARD_CODE_CAP` was the one that could only move
downward -- until R11-D41 gave it a way to say yes that does not cost working
code.

**R11-D41, 2026-09-06: the code cap is payable in kind, and the ceilings
record their own history.** Two changes, from one reading of what these
constants have actually done. `CEILING_HISTORY` below holds every value each
one has held, read from this file's own git log. R11-D41 read nine moves and
found **not one downward move and not one refusal**, with `bin/` going 8,000 to
15,750 in seven days and four of those raises inside three days. That is the
shape the paragraph below warns about -- 95,000 lines one defensible commit at a
time -- arriving inside the mechanism built to prevent it, because each raise is
priced in isolation and nothing ever looks at them together. R11-D48 is what
that finding eventually produced: the ceiling it was written about is the one
that has been retired, and the other two kept.

**No count of those moves is written in this file.** The nine above is dated
and attributed because it is what one decision read on one day; every live
figure is `ceiling_moves()` below, which counts recorded values and upward and
downward transitions across every ceiling in `CEILING_HISTORY`, retired ones
included, and `test_the_recorded_history_is_raises_only` prints all three when
it fails. The reason is the defect this paragraph kept producing: the header
said nine, the table said something else, the git log said a third thing and a
review said a fourth, and each was defensible because each counted a different
set -- which is precisely what made a stale number indistinguishable from a
differently-scoped one. A reader who wants the number runs the test.

*The code cap is payable in kind.* R11-D24's downward-only clause is
superseded. `DASHBOARD_CODE_CAP` may rise when the same change removes or
factors at least as many code lines from `dashboard/` as it adds, so net code
does not grow. R11-D24's intent survives whole -- prose still cannot buy code,
because prose is not what the payment is made in. What goes is the endgame,
which was delete something that works or do not build the thing, and which is
documented once already: R11-D24 exists *because* 6b-7 was spent deleting
rationale to fit a write path. `DASHBOARD_CODE_SLACK` is the mechanical half.
The gap between the cap and what `dashboard/` measures may not widen, so a
raise nobody paid for surfaces as a number rather than as a paragraph a
reviewer has to weigh. Editing both constants together is still possible and
is still a claim of unpaid capacity; the rule binds at the same strength as "a
cap is never raised in the PR that busts it", which is to say by review, but
now against a figure instead of against a belief.

*Considered and not done: making the totals report rather than gate.* The
per-raise derivation is expensive -- R11-D38 cost an agent twenty-two minutes
and serialised four units of work behind it -- and across every raise R11-D41
could see, it had never once returned "no". But a ceiling that only reports is
exactly what the retired stack had, and the paragraph below says what that
produced. The gate stays for `dashboard/`. What is new is that the trend is
data, so "should this still be rising" has somewhere to be asked other than
inside the next raise -- and for `bin/` the answer to that question was
eventually no, which is R11-D48.

Until now they were prose. The retired stack this repository is replacing
reached 95,000 lines one defensible commit at a time, and no single one of
those commits looked like the problem, which is
exactly why the bound has to be mechanical: a number in a design document is
checked by whoever remembers to check it.

Landing the test while every cap passes is deliberate. A cap introduced in the
change that breaks it is a negotiation; a cap introduced with headroom is a
guard, and the next pull request that would cross the line meets a red check
instead of a reviewer's memory.

**Enumerated from `git ls-files`, never from a list here.** Two reasons, both
learned rather than assumed. A hand-written list of files cannot see the
thirteenth one somebody adds next month -- the same trap the Makefile's lint
paths still carry. And walking the directory instead would count whatever is
lying in it: `find bin -type f` once reported this repository at 8,862 lines,
over its own cap, because it swept up `__pycache__/*.pyc`. The index holds
tracked source and nothing else, so it answers the question actually being
asked.
"""

from __future__ import annotations

import io
import pathlib
import shutil
import subprocess
import tempfile
import tokenize
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Each cap names the design decision it enforces, so a failure points at the
# record rather than at a bare number.
#
# **R11-D48, 2026-09-11: the `bin/` ceiling is retired.** `BIN_CAP`, the
# derivation chain that stood here, and `test_bin_stays_under_its_ceiling` are
# deleted. `bin/` has no line-count ceiling and no successor mechanism; the
# operator's decision was to remove it rather than to move it again.
#
# The evidence is `CEILING_HISTORY["BIN_CAP"]` below, which is why that entry
# is kept after the constant it described is gone. Twenty-one recorded values,
# 8,000 on 2026-08-30 to 20,803 on 2026-09-10: **eleven days, every move
# upward, not one downward move and not one refusal.** R11-D41 read the first
# nine of those and kept the gate, on the reasoning that a ceiling which only
# reports is what the retired stack had. Twelve more raises later the gate has
# still never returned "no", and what it has returned instead is measurable:
# each raise is a serialised preparatory pull request, and R11-D38 alone cost
# an agent twenty-two minutes and blocked four units of work behind it.
#
# A control that has never once refused is not bounding anything; it is
# charging a toll for the paperwork of agreeing. R11-D24's clause -- never
# raise a cap in the pull request that crossed it -- is what made that toll
# compulsory, and it is the clause being answered here: the way to stop paying
# it is to stop having the cap, not to keep the cap and waive the clause.
#
# What is **not** retired, so this is not read wider than it is:
#
#   * `MIGRATE_CAP` below, on the temporary `migrate-*` tools.
#   * `DASHBOARD_CAP`, `DASHBOARD_CODE_CAP` and `DASHBOARD_CODE_SLACK`. The
#     dashboard ceilings have a code/prose split and a payable-in-kind rule
#     that `bin/` never had, and they are a different argument.
#   * The review lane's own ceiling in `tests/test_sd_review_boundary.py`,
#     which is a separate number with a separate record.
#
# Nothing under `bin/` is touched by this change, so it lands as its own
# preparatory commit in the shape R11-D24 asks for, against a tree that the
# retired cap still passes.
MIGRATE_CAP = 1_500        # temporary tools, deleted at steps 7 and 11
# R11-D29, re-derived 2026-09-03 with the itemisation R11-D24's clause asks
# for: 4,190 measured on `main`, 158 measured on the branch that carries the
# dashboard ack-and-mutation-count item, 2 unclaimed. Both figures came off
# `line_count(tracked("dashboard"))` below rather than out of an estimate.
#
# It is a plain number, and one round of review was spent finding out why it
# has to be. The clause forbids raising a cap in the pull request that needs
# it, which leaves a window where capacity exists that no landed change has
# claimed; the attempt to close that window made this constant conditional on
# a work item's `implement.md` being present, so that an abandoned item took
# its reservation with it. That is worse. `sd-plan` sweeps merged items to
# `docs/work/archive/YYYY-MM/`, so the routine archive commit would have moved
# the file, dropped the ceiling back to 4,300 under a directory holding 4,348
# lines in total, and turned a bookkeeping commit into a red build. A ceiling that
# depends on where a document currently lives is not a ceiling.
#
# So the window stays open and is named instead: 2 lines, on `main`, until the
# reserved branch lands -- 14 when this was first written, narrowed by the
# branch's own remediation. That is the price of the clause, and it is smaller
# than the cost of the mechanism that tried to remove it.
#
# R11-D30, re-derived 2026-09-04 for the host-parsing item, which cannot start
# without it: 4,348 measured on `main`, +18 measured for the fix, 9 unclaimed.
# The 18 is not an estimate. The host-parsing item's `implement.md` pins the
# exact replacement body for `host_name`, and the figure is
# `line_count(tracked("dashboard"))` over a tree carrying that text rather than
# a description of it -- 17 lines becoming 35, of which 2 are code and 16 are the
# paragraph explaining why a security boundary now refuses input it used to
# repair. `DASHBOARD_CODE_CAP` is untouched: +2 against 31 lines of headroom,
# and it is downward-only under R11-D24 besides.
#
# The 9 unclaimed lines are the honest part. 4,375 was picked as a round number
# and 9 is what the subtraction left, not a margin computed from anything. It
# is kept because the predecessor item moved its own cap in four separate
# shipped changes -- each round of review added rationale, and rationale is
# what this cap is mostly made of. If this item's review rounds cost more than
# 9 lines, that busts a ceiling visibly rather than quietly, which is the
# behaviour this constant exists to produce.
#
# R11-D38, re-derived 2026-09-06 for PR 7's `sd-ship --deliver` slice, on the
# same three lines as the then-live `BIN_CAP` and with the same evidence
# behind them (that ceiling is retired at R11-D48; this derivation is not):
# 4,366 measured + 98 reserved + 119 reserved + 12 reserved + 5 unclaimed =
# 4,600. Nine lines of headroom did not hold a new control on the item screen.
#
# The 98 is four spans at four built analogues: the `/api/deliver` branch of
# `do_POST` at the `/api/ack` branch it copies (`dashboard/server.py:548-564`,
# 17, plus its line in the path tuple at `:530`), the row write behind it at
# `store.set_watermark` (`dashboard/store.py:198-218`, 21), the control itself
# at `dismissCell` with the comment head house style requires of a control
# whose failure mode has to be explained (`dashboard/app.js:594-624`, 31), and
# the hand-merge reconciliation display at `whereCell`
# (`dashboard/app.js:549-566`, 18) with `work.split_status`
# (`dashboard/work.py:86-95`, 10), which is where the two new states -- a row
# `in_progress` with the squash commit on a note, and `done` but unmarked --
# have to be spelled.
#
# The 119 is the second unrepaired seam PR 7 crosses, and it is a different
# one from `bin/`'s. `deliver` is the first control to carry an item's
# identity to a write that is not an ack, which is exactly the boundary
# R11-D25 drew when it ruled that an ack "is not a parameterised action" -- an
# id written to a store and compared against on render, never reaching an
# argv. Nothing has crossed from that side to a write that names a work item.
#
# The 12 is post-report discovery at the same 11.3% of the body.
#
# **`DASHBOARD_CODE_CAP` does not fit and is not being moved.** Measured with
# `code_line_count` over the same four analogue spans, PR 7's dashboard body
# carries 55 lines of code against 29 lines of headroom -- 7 + 1 for the
# server branch, 8 for the store write, 22 for the control, 14 + 3 for the
# display -- and that is before either discovery line spends anything. The
# code half may only move downward (R11-D24, and the paragraph above), so this
# is recorded as a finding about PR 7's dashboard scope rather than resolved
# with a number. Prose is not what busts it and prose cannot buy it back.
DASHBOARD_CAP = 4_600


# The half that cannot be paid for with prose. R11-D24 split the dashboard
# ceiling in two because a single total let a docstring and a branch compete
# for the same line, and 6b-7 was spent deleting rationale to fit a write path
# -- which is the cap working against the comment convention it was explicitly
# widened to hold. This one bounds what the other cannot: code.
DASHBOARD_CODE_CAP = 2_328 # R11-D41's first exercise; see the note below

# The gap between that cap and what `dashboard/` measures, recorded when
# R11-D41 wrote the rule: 2,300 against 2,271. It is what makes "payable in
# kind" checkable rather than remembered. Raising the cap by twenty-six lines
# and deleting twenty-six elsewhere leaves this untouched and passes; raising
# the cap alone widens it and fails. It may fall freely -- code added under an
# unmoved ceiling is the ordinary case and needs no permission.
DASHBOARD_CODE_SLACK = 29

# **2026-09-07, the first raise R11-D41 permitted, and what it actually cost.**
# The Work tab's `deliver` control -- the operator's claim after a hand merge
# that carried no `Delivers:` trailer -- measured 67 code lines: 27 for the
# writer in `work.py`, 6 for the label that resolves a row back to its
# checkout, 20 for the endpoint, 14 for the button. Against that, two
# factorings returned 18: `post()`, which was the same five lines of headers
# and token in each of two writers, and `payloadFor()`, which was the same
# seven lines of fetch-and-catch in each of five views. Net +49 against 21 of
# headroom, so the ceiling moved 28.
#
# **Ten of those 28 lines are unpaid, and that is the point of saying so here.**
# R11-D41 permits editing both constants at once precisely because "a visible
# claim of unpaid capacity" is better than a hidden one. `dashboard/` was
# searched for the remaining ten first: the duplication that looks reclaimable
# -- `window_start` in both trackers, their `OVERLAP` and `FIRST_RUN_WINDOW`
# constants -- is documented in `jira.py` as deliberately unshared, so taking
# it would be reversing a recorded decision to buy ten lines. Slack falls from
# 21 to 0, which is the honest consequence: the next code line under
# `dashboard/` fails this cap and asks the question again.
#
# **This raise sits in the change that needs it, against the paragraph at the
# top of this file.** That paragraph -- "a cap is never raised in the PR that
# busts it" -- reported how `BIN_CAP` and `DASHBOARD_CAP` were each moved, and
# those two had no slack test. `DASHBOARD_CODE_SLACK` makes a standalone
# raise of *this* cap impossible: a raise with no code beside it widens the
# distance and fails on the spot. The two rules cannot both be met, and
# R11-D41 is the later one and was written for this cap by name, so it wins
# here. Recorded rather than resolved quietly, because the older paragraph
# still governs `DASHBOARD_CAP` and should not be read as retired. It no
# longer governs `BIN_CAP`, which R11-D48 removed outright rather than
# exempting -- see that record above.


# Every value each ceiling has held, oldest first: read from this file's own
# history with `git log -- tests/test_loc_caps.py` on 2026-09-06, and appended
# by every raise since. Data, not prose: the docstring above records each raise
# where it happened, and no reader of that many separate paragraphs can see the
# shape they make together.
# `bin/` nearly doubled in a week. Nothing here has ever fallen, and nothing
# here has ever refused. That is the finding R11-D41 was written from, and it
# is only visible in one place because this list exists.
#
# The dates are the day the value landed on `main`, not the day its record was
# written. A new value goes on the end in the same change that moves the
# constant, which the test below enforces -- a history that may be left behind
# is a history nobody can cite.
CEILING_HISTORY: dict[str, tuple[tuple[str, int], ...]] = {
    # Closed. R11-D48 retired this ceiling on 2026-09-11 and the constant is
    # gone, so nothing below checks this entry against a live value. It stays
    # because these twenty-one rows -- every one a raise, none a refusal --
    # are the evidence the retirement was argued from, and a decision whose
    # evidence has been deleted cannot be reviewed later.
    "BIN_CAP": (
        ("2026-08-30", 8_000),
        ("2026-08-31", 14_000),
        ("2026-09-06", 14_700),
        ("2026-09-06", 15_050),
        ("2026-09-06", 15_400),
        ("2026-09-06", 15_750),
        ("2026-09-07", 16_750),
        ("2026-09-07", 17_000),
        ("2026-09-07", 17_050),
        ("2026-09-07", 17_250),
        ("2026-09-07", 18_000),
        ("2026-09-07", 18_550),
        ("2026-09-08", 19_500),
        ("2026-09-08", 20_050),
        ("2026-09-09", 20_231),
        ("2026-09-09", 20_246),
        ("2026-09-09", 20_475),
        ("2026-09-09", 20_731),
        ("2026-09-09", 20_733),
        ("2026-09-10", 20_745),
        ("2026-09-10", 20_803),
    ),
    "DASHBOARD_CAP": (
        ("2026-08-30", 2_500),
        ("2026-08-31", 4_000),
        ("2026-09-01", 4_300),
        ("2026-09-04", 4_350),
        ("2026-09-04", 4_375),
        ("2026-09-06", 4_600),
    ),
    "DASHBOARD_CODE_CAP": (
        ("2026-09-01", 2_300),
        ("2026-09-07", 2_328),
    ),
}


def ceiling_moves() -> tuple[int, int, int]:
    """What `CEILING_HISTORY` records, counted rather than remembered.

    Returns `(values, upward, downward)`: recorded values summed across every
    ceiling in the history, retired ones included, and the transitions between
    consecutive values of the same ceiling by direction. A first value is not a
    move, so `upward + downward` is `values` minus one per ceiling.

    This exists because the count had four answers at once -- the header said
    one number, the table another, the file's git log a third and a review a
    fourth -- and every one was defensible, because none of them said what it
    counted. Saying what it counts is this docstring's job; producing the
    number is the code's. Nothing else in this file restates it, on the same
    reasoning `bin/sd-status` uses for `CLASSES`: one table, and every reader
    of it iterates rather than repeats.
    """

    values = upward = downward = 0
    for history in CEILING_HISTORY.values():
        values += len(history)
        # `strict=False` deliberately: the offset slice is one shorter, which
        # is what makes each pair a transition rather than a value.
        for (_, before), (_, after) in zip(history, history[1:], strict=False):
            if after > before:
                upward += 1
            elif after < before:
                downward += 1
    return values, upward, downward


def tracked(*pathspecs: str, root: pathlib.Path = REPO_ROOT) -> list[pathlib.Path]:
    """Tracked files matching `pathspecs`, as the index reports them.

    `--deduplicate` because the index holds an unmerged path once per merge
    stage, and plain `ls-files` prints it once per stage. The consumers here
    are `line_count` and `code_line_count`, which iterate and **sum**, so a
    conflicted file charges its lines to a cap three times.

    That is a worse failure than the one the same missing flag caused in
    `tests/test_code_health.py`, which shares this call's argv and which is
    where the defect was found. There the tripling surfaces as a countable
    contradiction -- two functions sharing one key -- and the message says so.
    Here it surfaces as a larger number against a ceiling, in a file whose
    ceilings are famously argued over one raise at a time, with nothing to
    distinguish the inflation from real growth. The reader's next move is to
    derive a raise for a cap that was never crossed.

    `root` is the test seam, kept off every caller's signature deliberately:
    the suite injects a throwaway repository to build an index this repository
    will not hold on demand.
    """

    output = subprocess.run(
        ["git", "ls-files", "-z", "--deduplicate", "--", *pathspecs],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [root / name for name in output.split("\0") if name]


# Everything that is not a line of code: a comment, a docstring, a blank. The
# string tokens are the load-bearing exclusion -- roughly half of every Python
# file here is docstring, which is house style and the reason a code-only
# measure had to exist at all.
NOT_CODE = frozenset({
    tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE,
    tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER,
})


def code_line_count(paths: list[pathlib.Path]) -> int:
    """Lines carrying code, with comments, docstrings and blanks left out.

    Python is tokenised rather than pattern-matched, because the alternative
    is a regex that cannot tell `# a comment` from `url = "http://x/#frag"`
    and would drift in whichever direction its author was hoping for.

    JavaScript has no tokeniser in the standard library, so it is measured by
    the crude rule -- a non-blank line that does not open with `//`. That is
    **conservative on purpose**: it counts a `/* */` block as code, so the
    error can only tighten this cap, never loosen it. `dashboard/app.js` holds
    no block comment today and the measure is checked, not assumed.

    Every other suffix carries no code and is not counted. The rule is stated
    by extension rather than as "not Python", because a `README.md` measured
    by the JavaScript rule is every line of prose counted as code, failing
    this cap for a reason that has nothing to do with what it protects. Such a
    file still charges the total cap, which is where a large one belongs; and
    should `dashboard/` ever hold a third language, this returns too low until
    somebody adds it, so the omission surfaces as headroom that does not
    behave, not as a silent pass. Found in review.
    """

    total = 0
    for path in paths:
        # The suffix decides before the file is opened. Reading first would
        # make "every other suffix counts nothing" fail on the one case it
        # most obviously covers -- an icon or a font under `dashboard/`, which
        # is not text and would raise rather than be ignored. Found in review.
        if path.suffix not in {".py", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".js":
            total += sum(
                1 for line in text.splitlines()
                if line.strip() and not line.strip().startswith("//")
            )
            continue
        seen = set()
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type not in NOT_CODE and token.string.strip():
                seen.add(token.start[0])
        total += len(seen)
    return total


def line_count(paths: list[pathlib.Path]) -> int:
    total = 0
    for path in paths:
        # A tracked path can be absent from the working tree during a partial
        # checkout. Counting it as zero would understate the total and let a
        # cap pass for the wrong reason, so it is an error, not a skip.
        with path.open(encoding="utf-8") as handle:
            total += sum(1 for _ in handle)
    return total


class LineCountCaps(unittest.TestCase):
    def assert_cap(self, label: str, paths: list[pathlib.Path], cap: int) -> int:
        total = line_count(paths)
        self.assertLessEqual(
            total,
            cap,
            f"{label} is {total} lines against a cap of {cap}. The cap is a design "
            f"decision, not a lint setting: raise it in its own change with its own "
            f"record, never in the pull request that crossed it. Files counted: "
            f"{', '.join(sorted(str(p.relative_to(REPO_ROOT)) for p in paths))}",
        )
        return total

    def test_the_migration_tools_stay_under_their_own_ceiling(self) -> None:
        """`migrate-*` has a ceiling of its own because it is deleted, not kept.

        An empty result is correct rather than suspicious here: steps 7 and 11
        delete these tools, and a cap on nothing is satisfied. It is asserted
        rather than skipped so the transition is visible in the test output.
        """

        paths = [p for p in tracked("bin") if p.name.startswith("migrate-")]
        if not paths:
            self.assertEqual(paths, [], "no migrate-* tools remain; the cap has no subject")
            return
        self.assert_cap("bin/migrate-*", paths, MIGRATE_CAP)

    def test_the_dashboard_stays_under_its_ceiling(self) -> None:
        """`dashboard/` only.

        `bin/sd-dashboard` is the CLI in front of it and counts against `bin/`,
        where the design's own itemisation puts the dashboard glue. Counting it
        in both places would make the two caps overlap and neither one mean
        what it says.
        """

        paths = tracked("dashboard")
        self.assertTrue(paths, "dashboard/ enumeration matched no tracked files")
        self.assert_cap("dashboard/", paths, DASHBOARD_CAP)

    def test_the_dashboard_code_stays_under_its_own_ceiling(self) -> None:
        """The half a docstring cannot buy back (R11-D24).

        The total above may be paid for in prose; this one may not. It is the
        cap that binds when code grows, so that fitting a change never means
        deleting the reasoning for a different one -- which is what 6b-7 spent
        its last hour doing under a single combined ceiling.
        """

        paths = tracked("dashboard")
        self.assertTrue(paths, "dashboard/ enumeration matched no tracked files")
        total = code_line_count(paths)
        self.assertLessEqual(
            total,
            DASHBOARD_CODE_CAP,
            f"dashboard/ carries {total} lines of code against a cap of "
            f"{DASHBOARD_CODE_CAP}. Prose is not what busted this one, so prose "
            f"is not what fixes it: the cap is a design decision (R11-D24), "
            f"raised only in its own record and never in the pull request that "
            f"crossed it.",
        )

    def test_the_code_ceiling_is_paid_for_in_kind(self) -> None:
        """R11-D41: the cap may rise, but not by more than it is paid for.

        The test above bounds the code. This one bounds the *permission* --
        the distance between the ceiling and the tree. Adding code narrows
        that distance and is the ordinary case; raising the ceiling widens it
        and is the case that has to be paid for, by removing or factoring at
        least as many code lines as the raise claims. R11-D24 said this half
        could only fall, which left one answer when it bound: delete something
        that works, or do not build the thing. This is the way to say yes.

        A change may still edit both constants at once. That is a visible
        claim of unpaid capacity rather than a hidden one, which is the whole
        of what this test buys and is the same strength as the clause at the
        top of this file.
        """

        paths = tracked("dashboard")
        self.assertTrue(paths, "dashboard/ enumeration matched no tracked files")
        slack = DASHBOARD_CODE_CAP - code_line_count(paths)
        self.assertLessEqual(
            slack,
            DASHBOARD_CODE_SLACK,
            f"DASHBOARD_CODE_CAP now stands {slack} lines above what "
            f"dashboard/ measures, against {DASHBOARD_CODE_SLACK} when "
            f"R11-D41 recorded the rule. A raise is payable in kind: remove "
            f"or factor as many code lines as it claims, or lower "
            f"DASHBOARD_CODE_SLACK in its own record and say what bought it.",
        )

    def test_each_ceiling_is_the_last_value_its_history_records(self) -> None:
        """A history that may be left behind is a history nobody can cite.

        `CEILING_HISTORY` exists so the trend is checkable in one place, and a
        list that drifts from the constants it describes is worse than no list
        -- it is the "number in a design document" this file was written to
        replace, wearing the clothes of the thing that replaced it. So the
        next raise updates both or fails here.
        """

        for name, value in (
            ("DASHBOARD_CAP", DASHBOARD_CAP),
            ("DASHBOARD_CODE_CAP", DASHBOARD_CODE_CAP),
        ):
            with self.subTest(ceiling=name):
                history = CEILING_HISTORY[name]
                self.assertEqual(
                    history[-1][1],
                    value,
                    f"{name} is {value} and CEILING_HISTORY ends at "
                    f"{history[-1][1]}, set {history[-1][0]}. A change that "
                    f"moves a ceiling appends to its history in the same "
                    f"commit; R11-D41 is why the list is there at all.",
                )

    def test_the_recorded_history_is_raises_only(self) -> None:
        """R11-D41's finding, asserted instead of recited.

        The finding was that nothing ever looked at the raises together. This
        is the looking, and it fails the day a ceiling finally comes down --
        at which point the paragraph in R11-D41 that reasons from "not one
        downward move" needs rewriting, which is what a failure here is for.

        The message carries the live figures so the number lives in output
        rather than in prose that goes stale between readings.
        """

        values, upward, downward = ceiling_moves()
        self.assertEqual(
            downward,
            0,
            f"CEILING_HISTORY now records a downward move: {values} recorded "
            f"values, {upward} up, {downward} down across "
            f"{len(CEILING_HISTORY)} ceilings. R11-D41 reasons from there "
            f"being none; update that paragraph rather than this assertion.",
        )
        self.assertEqual(
            upward,
            values - len(CEILING_HISTORY),
            f"a ceiling repeats a value: {values} recorded values across "
            f"{len(CEILING_HISTORY)} ceilings leaves "
            f"{values - len(CEILING_HISTORY)} moves, but only {upward} of "
            f"them changed the number. A row that moves nothing is a raise "
            f"nobody made.",
        )

    def test_the_code_measure_does_not_count_prose_as_code(self) -> None:
        """The measure is the cap, so a measure that drifts is a cap that lies.

        Checked against a file whose answer is known by construction rather
        than against `dashboard/`, whose answer changes with every commit.
        """

        scratch = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        module = scratch / "sample.py"
        module.write_text(
            '"""A docstring.\n\nSpanning several lines, none of them code.\n"""\n'
            "\n"
            "# A comment.\n"
            "VALUE = 1  # code, despite the comment\n"
            'TEXT = """\nstill an assignment, and only its first line is code\n"""\n',
            encoding="utf-8",
        )
        self.assertEqual(code_line_count([module]), 2)

        script = scratch / "sample.js"
        script.write_text(
            "// a comment\n\nconst x = 1; // trailing\n  // indented comment\n",
            encoding="utf-8",
        )
        self.assertEqual(code_line_count([script]), 1)

        # Prose in a file the measure has no rule for is not code, and is not
        # counted by the rule for a language it is not written in.
        prose = scratch / "notes.md"
        prose.write_text("# Heading\n\nA paragraph about the design.\n", encoding="utf-8")
        self.assertEqual(code_line_count([prose]), 0)

    def test_no_javascript_under_the_cap_hides_prose_in_a_block_comment(self) -> None:
        """The JS measure cannot see `/* */`, so it is checked that none opens a line.

        Without this the conservative direction is only an assumption: a file
        that started using block comments would have them counted as code,
        and the first person to notice would be whoever the cap failed on.

        A line *opening* one is the whole check, and deliberately not every
        `/*` in the file: `const glob = "src/*.js"` holds the substring and no
        comment. A block opened mid-line after real code leaves that line
        counted as code, which it is, and its continuation lines counted as
        code, which is the conservative direction this measure already
        accepts. Narrowed in review, with the gap stated rather than implied.
        """

        for path in tracked("dashboard"):
            if path.suffix != ".js":
                continue
            # A line that *opens* with `/*`, not the substring anywhere: a
            # regex or a string may hold `/*` mid-line without a byte of it
            # being a comment, and failing on that would be a false positive
            # about comment style. Found in review.
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertFalse(
                    line.strip().startswith("/*"), f"{path}:{number} opens a block comment")


#: What `_unmerged_index_repo` leaves in the working tree once the conflict is
#: resolved: four lines, of which two carry code. Small enough that the
#: expected sums below are read rather than computed, which is the point --
#: a case that derived its own expectation from the same helper it is testing
#: would agree with the defect as readily as with the fix.
RESOLVED = '"""Resolved."""\n\nx = 1\ny = 2\n'
RESOLVED_LINES = 4
RESOLVED_CODE_LINES = 2


def _unmerged_index_repo(root: pathlib.Path) -> pathlib.Path:
    """A repository whose index holds `dashboard/panel.py` unmerged.

    The conflict is a real merge, not a hand-written index: the three stages
    have to come from git's own machinery or the fixture merely restates the
    belief under test.

    The working tree is then **resolved and left unstaged**, which is the
    state this defect is actually met in. A person fixes the conflict in their
    editor and runs the suite before `git add`; the file on disk is valid
    Python again, so nothing warns them, while the index still carries three
    stages. Leaving the conflict markers in place instead would make
    `code_line_count` raise on a tokenise error -- a different failure, and a
    louder one than the silent inflation this guards.
    """

    def git(*argv: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            # Identity and signing are passed per invocation rather than read
            # from the machine, so the fixture does not fail on a host with no
            # `user.email` or one that signs every commit.
            ["git", "-c", "user.email=caps@example.invalid",
             "-c", "user.name=loc caps", "-c", "commit.gpgsign=false", *argv],
            cwd=root, capture_output=True, text=True, check=check)

    panel = root / "dashboard" / "panel.py"
    panel.parent.mkdir(parents=True)
    git("init", "-q", "-b", "main", ".")
    panel.write_text('"""Base."""\n\nx = 0\n')
    git("add", "dashboard/panel.py")
    git("commit", "-qm", "base")
    git("checkout", "-q", "-b", "other")
    panel.write_text('"""Other."""\n\nx = 2\n')
    git("commit", "-qam", "other")
    git("checkout", "-q", "main")
    panel.write_text('"""Mine."""\n\nx = 1\n')
    git("commit", "-qam", "mine")
    git("merge", "other", check=False)
    panel.write_text(RESOLVED)
    return panel


class AnUnmergedIndex(unittest.TestCase):
    """What the caps measure while a merge is still being resolved."""

    def setUp(self) -> None:
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.root = pathlib.Path(home.name)
        self.panel = _unmerged_index_repo(self.root)

    def assert_the_index_is_unmerged(self) -> None:
        """The premise every case below rests on, asserted rather than assumed.

        Without this the cases would pass against any ordinary repository,
        which is exactly how the defect survived: nothing about a clean
        checkout tells the two behaviours apart.
        """

        stages = subprocess.run(
            ["git", "ls-files", "-u", "--", "dashboard/panel.py"],
            cwd=self.root, capture_output=True, text=True, check=True).stdout
        self.assertEqual(
            [line.split("\t")[0].split()[-1] for line in stages.splitlines()],
            ["1", "2", "3"],
            "the fixture did not leave an unmerged index, so nothing below "
            "proves anything")
        raw = subprocess.run(
            ["git", "ls-files", "-z", "--", "dashboard/panel.py"],
            cwd=self.root, capture_output=True, text=True, check=True).stdout
        self.assertEqual(
            [name for name in raw.split("\0") if name],
            ["dashboard/panel.py"] * 3,
            "this git no longer repeats an unmerged path; if that is now the "
            "default, say so here rather than deleting these cases")

    def test_a_conflicted_file_charges_the_total_cap_once(self) -> None:
        """The measure, not the path list.

        Deduplicating the paths is the mechanism; the thing that breaks is the
        sum. Asserting only that `tracked` returns one path would leave the
        case passing for a reason next to the one that matters, and would not
        fail if somebody later reintroduced the tripling further down the
        pipe.
        """

        self.assert_the_index_is_unmerged()
        self.assertEqual(self.panel.read_text(), RESOLVED,
                         "the working tree is resolved; only the index is not")
        self.assertEqual(
            line_count(tracked("dashboard", root=self.root)), RESOLVED_LINES,
            "a file being merged charged its lines to the total cap once per "
            "merge stage")

    def test_a_conflicted_file_charges_the_code_cap_once(self) -> None:
        """`code_line_count` sums over the same list and inflates the same way.

        Both consumers are named because they are separate loops over
        `tracked`, and a fix applied to one of them would leave the other
        wrong -- which is the shape of the defect being fixed here in the
        first place.
        """

        self.assert_the_index_is_unmerged()
        self.assertEqual(
            code_line_count(tracked("dashboard", root=self.root)),
            RESOLVED_CODE_LINES,
            "a file being merged charged its code lines to the code cap once "
            "per merge stage")

    def test_the_seam_reads_the_repository_it_is_pointed_at(self) -> None:
        """`root` must move the enumeration, not merely be accepted.

        A seam that is ignored would let the cases above read this repository,
        find no conflict, and agree with whatever `tracked` does.
        """

        self.assertEqual(tracked("dashboard", root=self.root), [self.panel])
        self.assertNotIn(self.panel, tracked("dashboard"))


class DeletedArchitectureResidue(unittest.TestCase):
    """sd:601. A generated file nothing reads can only ever be wrong.

    `generated/registry-snapshot.json` listed 20 skills. Fourteen existed in
    neither `skills/` nor `contrib/`, and it omitted 76 that did -- last
    written 2026-08-17, before the rename that made it wrong, and read by no
    code in the tree. The pack was pointing outward at drift in a consumer's
    CLAUDE.md while shipping the same drift itself.

    It is not refreshed, because a refreshed list is stale again on the next
    rename; that is how it reached fourteen. sd:10's own prd.md calls it
    residue from a deleted architecture, and acceptance criterion 17 requires
    it absent, so this asserts the criterion rather than restating a judgement.

    The criterion's other two paths, `tests/test_selector_contract_drift.py`
    and `plugins/sd`, are sd:10's to remove and are still present. They are
    deliberately NOT recited here: a list naming paths this file does not
    enforce is the same unread recitation sd:601 is about.
    """

    def test_the_registry_snapshot_does_not_come_back(self) -> None:
        path = "generated/registry-snapshot.json"
        self.assertEqual([], tracked(path), f"{path} is tracked again")
        self.assertFalse((REPO_ROOT / path).exists(), f"{path} is on disk again")

    def test_nothing_in_the_tree_reads_the_registry_snapshot(self) -> None:
        """Enumerated from the index, not from a list of directories."""
        readers = [
            path for path in tracked("bin", "tests", "dashboard", "skills",
                                     ".github", "Makefile")
            if path.is_file() and path.name != pathlib.Path(__file__).name
            and "registry-snapshot" in path.read_text(
                encoding="utf-8", errors="replace")
        ]
        self.assertEqual([], readers)


if __name__ == "__main__":
    unittest.main()
