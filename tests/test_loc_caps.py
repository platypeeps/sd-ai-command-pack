"""The three line-count ceilings, enforced instead of remembered.

The design fixes a ceiling for each part of the replacement world -- `bin/` at
15,750 lines (R11-D15 set 14,000, re-derived from built code after 8,000 was
busted with six of the eleven commands still unwritten -- `sd-plan`, `sd-ship`,
`sd-spec`, `sd-deps`, `sd-suggest`, `sd-map`; re-derived again at R11-D31 for
the registry reader, at R11-D32 for what PR 6 had left, at R11-D34 for its
last two units and at R11-D38 for PR 7), the temporary `migrate-*` tools at
1,500 outside it, `dashboard/` at 4,600 with 2,300 of it carrying code
(R11-D24, with the total re-derived at R11-D29, at R11-D30 and at R11-D38)
-- and says in as many words that "caps are
CI tests; a cap is never raised in the PR that busts it". That rule survives
every re-derivation: 14,000, 4,000 and 4,300 were each set in their own
decision record by a change that fit under the ceiling it replaced, not in a
pull request that did not fit. 4,350 was set the same way at R11-D29, by a
change touching this file and one design record and nothing under `dashboard/`,
while the directory stood at 4,190 against the 4,300 it replaced. 14,700 was
set the same way at R11-D31, by a change touching this file and one item's
planning pages and nothing under `bin/`, while the directory stood at 13,307
against the 14,000 it replaced. 15,050 was set the same way at R11-D32,
15,400 at R11-D34 and 15,750 at R11-D38, each by a change touching this file
and the same item's planning pages and nothing under `bin/`, while the
directory stood at 14,536, then at 14,895, then at 15,260 against the ceiling
each replaced.

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
one has held, read from this file's own git log: nine upward moves across the
three of them, **not one downward move and not one refusal**, `bin/` going
8,000 to 15,750 in seven days and four of those raises inside three days. That
is the shape the paragraph below warns about -- 95,000 lines one defensible
commit at a time -- arriving inside the mechanism built to prevent it, because
each raise is priced in isolation and nothing ever looks at nine of them
together.

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
and serialised four units of work behind it -- and in nine raises it has never
once returned "no". But a ceiling that only reports is exactly what the
retired stack had, and the paragraph below says what that produced. The gate
stays. What is new is that the trend is data, so "should this still be rising"
has somewhere to be asked other than inside the next raise.

`bin/`'s ceiling keeps the original clause and is no longer untouched: it stood
unmoved from R11-D15 to 2026-09-06, then moved four times in that one day --
for the registry reader, for what PR 6 had left, for two units whose
specified bodies were priced right and overran anyway, and for PR 7's retire
step and the reader that has to precede it. It has no code half of
its own, because `bin/` has no equivalent of `dashboard/app.js` -- one file
large enough that a paragraph and a branch measurably compete -- and inventing
one the day the total first bound would be a mechanism chosen to pass a number.

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
# `bin/` has been re-derived four times, each in its own change, each pricing
# unwritten units off built analogues measured span by span -- because this
# item's `implement.md` pins no body for any of them, and built code is the
# only input that is not an opinion. R11-D31 took it to 14,700 for PR 6's
# registry reader (13,307 + 559 - 158 measured, 888 reserved, 104 unclaimed),
# R11-D32 to 15,050 for the rest of PR 6 (14,536 + 452 + 62), R11-D34 to
# 15,400 for its last two units (14,895 + 236 + 106 + 119 + 20 + 24), and
# R11-D38 to 15,750 for PR 7.
#
# PR 6 is closed, so R11-D38 is the first of them that can check the others
# against outcomes instead of against each other:
#
#                                reserved  body  in-flight  post-report  total
#   `sd attribute`, write side        168   168          0            -    168
#   the installer's consent prompt     64   ~65        135            -    199
#   the `url` client and its reader   114   216*       102           31    247
#   criterion 11's mode predicate     106   109          3            9    118
#   `sd-ship`, criteria 2, 3, 32        -     0          0            0      0
#
#   * body and in-flight are one commit for the `url` client (50387d01): 114
#     priced, 216 landed. Every other row separates them.
#
# The analogue method holds a fourth time -- 106 priced against 109 built,
# every specified body so far inside 5%. Two of R11-D34's three findings do
# not, and one of its own figures does not either.
#
# **A seam pays out once.** R11-D34 read overruns of 0, 135 and 122 and
# concluded that discovery is a property of the seam crossed rather than of
# the size of what crosses it, so the contingency is flat per crossing. The
# magnitude survives; the trigger does not. Criterion 11 crossed the seam
# R11-D34 named -- `mode` out of the `CLAUDE.local.md` block -- and found 3
# lines rather than 119, because the consent prompt had crossed it first: the
# 135 that overran the consent prompt *was* the marker fix, as R11-D34's own
# sentence says ("until the marker fix landed"). Discovery belongs to the
# first crossing of a seam and does not renew. So the flat line is reserved
# once per seam no landed unit has crossed, and not at all for a re-crossing.
# Under that rule the estimator is unchanged at (135 + 102) / 2 = 119: the two
# first crossings are still the only two first crossings, and 3 is not a third
# observation of the same thing.
#
# **Post-report discovery scales; in-flight discovery does not.** That is the
# opposite of R11-D34's finding for the other line, and it follows from what
# each one measures. In-flight discovery is whatever was already sitting
# behind the seam, and it is that size whatever crosses it. Post-report
# discovery is a second reader working over a body, and a longer body holds
# more to find. The two observations are 31 lines on a 216-line body and 9 on
# a 109-line one: as absolutes they differ 3.4x, as fractions of the body
# 14.4% and 8.3%, differing 1.7x. The ratio is the steadier statistic on this
# line, so this line is a percentage where the other one is ruled out as one.
#
# **A measured actual is still not a settled number, and R11-D34's own figure
# is the proof.** It recorded the `url` client at "236, measured" and the
# client landed at 247: a second review round (4aaef4c6) put 11 more lines
# into `bin/sd_install.py` after the total had been measured, reported, and
# used to derive a ceiling. Two rounds, not one. The 20 R11-D34 called
# post-report was only the first of them.
#
# R11-D38, re-derived 2026-09-06: 15,260 measured + 299 reserved + 119
# reserved + 34 reserved + 38 unclaimed = 15,750.
#
# The 15,260 is `line_count` over the 26 tracked files this test enumerates,
# on `main` at f5b30c00, `migrate-*` excluded as always.
#
# The 299 is PR 7's body in `bin/` and nowhere else, seven spans priced at
# seven built analogues: the file-or-row resolver at `sd_registry.library`
# and `sd_registry.read` (37), the row-to-dataclass adapter at
# `sd_registry._adapt` (38), `sd_lib.delivered` at the built trailer scan
# `attribution` with `_in_range` (50), `bin/sd-status`'s row read and stale
# line at `residue_section` with `_render_work` (38), `bin/sd-docs-lint`
# rules 1 and 2 (44), rule 7 for criterion 33 at `check_citations` with
# `resolve_citation` (73), and the `sd_db` step's tag pin at `resolve_pin`
# (19). What is *not* in it matters as much: the retire step is B's command
# in another repository, `skills/sd-ship/` carries `--deliver` and there is
# no `bin/sd-ship` at all, `tests/` is outside every cap here, and
# `dashboard/`'s `deliver` screen answers to `DASHBOARD_CAP`, re-derived
# below in the same change and on the same three lines.
#
# The 119 is in-flight discovery for the one seam PR 7 crosses that no landed
# unit has: `sd_db`'s item rows, read from the pack. The library boundary
# itself is repaired -- `sd_registry.library` and `sd_install.open_library`
# already cross it -- but nothing in `bin/` has read an item row.
#
# The 34 is post-report discovery at the mean of the two measured ratios,
# 11.3% of the 299-line body. Two observations, and the entry says so.
#
# The review lane is not in the way this time. `test_sd_review_boundary` caps
# `bin/sd-review` plus its non-`SHARED_CORE` imports at 1700 and that lane is
# 1699 today, with no headroom at all -- but PR 7's four `bin/` files are
# `sd_lib` (shared core), `sd-status`, `sd-docs-lint` and `sd_install.py`,
# none of which the lane contains. R11-D34's reservation could not be spent
# where its work belonged; this one can.
#
# The 38 unclaimed is what a round 15,750 left, and funds nothing. Over 452
# for PR 7 busts a ceiling visibly, which is what this constant is for. PR 8
# stays unfunded under R11-D15's clause. The item's `prd.md` carries the rest.
#
# R11-D42, 2026-09-07, funds **criterion 26 alone** and leaves the rest of PR 8
# unfunded exactly as R11-D15's clause requires. PR 8 is not one pull request
# any more: priced whole it came to 2,592 lines, a 16.5% raise in one step for
# scope a month out, and this ceiling exists to make that visible rather than
# to wave it through. It lands in four slices, one per criterion, each preceded
# by its own re-derivation. Splitting costs nothing -- 2,593 across four against
# 2,592 in one -- because the seams do not double.
#
# The base is **15,749**, not the 15,743 this branch measures. The six-line
# difference is `sd_lib.external_id`, committed on PR 7's branch and merging
# first, and already inside R11-D38's reservation. Pricing off 15,743 would
# fund criterion 26 six lines short of the tree it will actually build on.
#
# Criterion 26 is **976**: a 663-line body, 238 of seam, 75 of post-report.
# The body is three spans at built analogues -- `bin/sd_codex.py` at 368,
# `bin/sd-skill-use` at 240, and the installer going from one hook event to
# five at +55 net. The +55 is shared: the two hooks criterion 29 needs ride on
# it free, which is why 26 lands before 29.
#
# The 238 is two seams at R11-D38's flat 119, both genuinely uncrossed:
# writing `skill_use` rows, which nothing in `bin/` has done, and parsing a
# Codex transcript, a format nothing here has read. R11-D38's own item-rows
# seam is spent -- `d9aca2e0` crossed it -- so it is not reserved again. No
# seam is reserved for calling GitHub: `sd_lib.gh_api` and
# `bin/sd-pr-state`'s `gh_json` repair that transport twice over.
#
# **PR 7 is the first delivered total, and it overran.** R11-D38 reserved 452
# and PR 7 spent 489 in `bin/` -- 8.2% over, 15,260 to 15,749, which is the
# 1 line of headroom this branch measures. Per span it was far worse than
# that: `sd_lib.py` took 378 against 125 reserved, three times over, while
# `bin/sd-status` came in at -5 against 38. The misses cancelled. So
# R11-D38's claim that the analogue method holds "inside 5%" does not survive
# its own first total -- the method is unreliable per span and roughly right
# in aggregate, which is the reverse of what it concluded from four units, and
# it is the aggregate that a ceiling actually gates.
#
# What that costs here is the per-file header. A new module in `bin/` is 49 to
# 72 lines before its first function -- measured, `sd_restore.py` 49,
# `sd_sweep.py` 54, `sd-handoff-restore` 71, `sd-handoff` 72 -- plus 2.9 lines
# of glue per function boundary, which is `sd-handoff-restore`'s 46 remainder
# over 16 defs. Criterion 26 adds two new files, so 125 of its 663 is header
# that no function-level analogue would have shown.
#
# The 25 unclaimed is what a round 16,750 left.
BIN_CAP = 16_750           # R11-D42: criterion 26 only; 27, 28 and 29 unfunded
MIGRATE_CAP = 1_500        # temporary tools, outside the bin/ cap, deleted at steps 7 and 11
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
# same three lines as `BIN_CAP` above and with the same evidence behind them:
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
DASHBOARD_CODE_CAP = 2_300 # R11-D24, amended by R11-D41: payable in kind

# The gap between that cap and what `dashboard/` measures, recorded when
# R11-D41 wrote the rule: 2,300 against 2,271. It is what makes "payable in
# kind" checkable rather than remembered. Raising the cap by twenty-six lines
# and deleting twenty-six elsewhere leaves this untouched and passes; raising
# the cap alone widens it and fails. It may fall freely -- code added under an
# unmoved ceiling is the ordinary case and needs no permission.
DASHBOARD_CODE_SLACK = 29


# Every value each ceiling has held, oldest first, read from this file's own
# history with `git log -- tests/test_loc_caps.py` on 2026-09-06. Data, not
# prose: the docstring above records each raise where it happened, and no
# reader of nine separate paragraphs can see the shape the nine make together.
# `bin/` nearly doubled in a week. Nothing here has ever fallen, and nothing
# here has ever refused. That is the finding R11-D41 was written from, and it
# is only visible in one place because this list exists.
#
# The dates are the day the value landed on `main`, not the day its record was
# written. A new value goes on the end in the same change that moves the
# constant, which the test below enforces -- a history that may be left behind
# is a history nobody can cite.
CEILING_HISTORY: dict[str, tuple[tuple[str, int], ...]] = {
    "BIN_CAP": (
        ("2026-08-30", 8_000),
        ("2026-08-31", 14_000),
        ("2026-09-06", 14_700),
        ("2026-09-06", 15_050),
        ("2026-09-06", 15_400),
        ("2026-09-06", 15_750),
        ("2026-09-07", 16_750),
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
    ),
}


def tracked(*pathspecs: str) -> list[pathlib.Path]:
    """Tracked files matching `pathspecs`, as the index reports them."""

    output = subprocess.run(
        ["git", "ls-files", "-z", "--", *pathspecs],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / name for name in output.split("\0") if name]


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

    def test_bin_stays_under_its_ceiling(self) -> None:
        """`bin/` minus the temporary migration tools, which have their own cap."""

        paths = [p for p in tracked("bin") if not p.name.startswith("migrate-")]
        # The enumeration is asserted non-empty before the cap. A pathspec that
        # stopped matching -- a rename, a move, a typo -- would count zero lines
        # and report a clean pass, which is the one way a cap test can fail at
        # its job while looking like it worked. Non-empty is the whole check: a
        # directory pathspec matches everything under it or nothing, so there is
        # no partial-match case for a file-count floor to catch, and a floor
        # would instead fail on a legitimate consolidation.
        self.assertTrue(paths, "bin/ enumeration matched no tracked files")
        self.assert_cap("bin/", paths, BIN_CAP)

    def test_the_migration_tools_stay_under_their_own_ceiling(self) -> None:
        """`migrate-*` is outside the `bin/` cap because it is deleted, not kept.

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
            ("BIN_CAP", BIN_CAP),
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


if __name__ == "__main__":
    unittest.main()
