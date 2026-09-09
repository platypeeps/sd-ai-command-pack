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
#
# R11-D43, 2026-09-07, funds **criterion 29 alone** -- PR 8b, the second of the
# four slices -- and leaves 27 and 28 unfunded, as R11-D15's clause requires.
# The base is **16,399**, measured on `main` at `6b36e3ec` rather than
# estimated: criterion 26 is merged, so for the first time a slice is priced
# off the tree it actually builds on.
#
# **Criterion 26 came in at 650 against 976, and the body was right to 2%.**
# 15,749 before 8a, 16,399 after, both counted from git. The body reserved 663
# and delivered 650: `bin/sd-skill-use` 243 against 240, `bin/sd_codex.py` plus
# its verb 368 against 368, the installer +39 against +55. That is the first
# time this method has predicted a delivered total closely, and it is what
# R11-D42's own correction asked for -- price the header, then the aggregate
# holds.
#
# **What did not get spent is the seam charge.** 238 was reserved for two
# first crossings at R11-D38's flat 119, and both cost nothing beyond their
# spans. Writing `skill_use` rows cost six lines, because
# `sd_db.writes.record_skill_use` already carried the `timestamp` parameter a
# nightly needs. Reading a Codex transcript cost the 46 already priced against
# `bin/sd_ledger.py:143-188`, because a JSONL parse with a damaged-line policy
# was built. A flat 119 for "nothing here has done this" charges for novelty;
# what actually costs is an *unrepaired* boundary, and both of these had a
# repaired one on the other side.
#
# Criterion 29 is **573**: a 422-line body, 119 of seam, 32 of post-report.
# The spans below sum to 422; 7.6% of that is 32.
#
# The body is five spans, each at a built analogue with its header counted:
#
#   * `bin/sd_handoff_rows.py`, new, **120**. The item resolver and the row
#     reader both hooks need; a suffixless file cannot be imported, so
#     `bin/sd-handoff-restore` and `bin/sd-note` cannot share code any other
#     way. 49 for the header at `bin/sd_restore.py:1-49`, the built
#     small-library-touching-module header; 21 for the deferred `sd_db` frame
#     at `:54-74`; 10 for resolving the item at `dashboard/work.py:253-262`
#     inside `deliver`, which is `sd_lib.external_id` and
#     `sd_db.writes.item_by_external`; 10 for the open-rows read, which is
#     the eight-line `unresolved_state` at `sd_db/writes.py:409-416` -- the
#     built select-a-kind-and-filter-unresolved shape -- plus its call; 19 for
#     rendering rows to lines at `bin/sd_sweep.py:144-162` `render`; and 11 of
#     glue, five boundaries at 2.10.
#   * `bin/sd-handoff-prompt`, new, **162**. `PreCompact` and `SessionEnd` in
#     one file, for `bin/sd-skill-use`'s reason: the events differ in what they
#     read off the payload and in nothing else. 68 for the header at
#     `bin/sd-skill-use:1-68`, counted whole because this hook carries the same
#     obligation over two events plus an opt-out plus the never-claim rule;
#     25 for the payload read and event dispatch, the body of
#     `skill_and_mode` at `:149-173`; 12 for asking whether a packet is already
#     fresh, which is a call into the built `load_age_seconds` and `expired`;
#     16 for building the prompt and emitting it, twice the eight-line `emit`
#     at `bin/sd-handoff-restore:408-415`; 30 for `run` and `main` at
#     `bin/sd-skill-use:189-243` less the library half; 11 of glue.
#   * `bin/sd-note`, new, **106**. The followup writer, and the first caller
#     `sd_db.add_note` has ever had in this pack. Priced against
#     `bin/sd-trackers` whole, 147 lines of parse-resolve-print: 48 for its
#     header at `:1-48`, 7 for `build_parser` at `:118-124`, 17 for `main` at
#     `:127-143`, 20 for the write and its refusal, 6 for the confirming line,
#     8 of glue, four boundaries at 2.10. Less than `sd-trackers` because the
#     resolving half lives in
#     `sd_handoff_rows.py` and is paid once.
#   * `bin/sd-handoff-restore`, **+32**. Rows beside the packet, read before
#     the `if not path.is_file(): return 0` at `:448` that the criterion's test
#     hits first. 11 for a rows-first block shaped like `run`'s own prologue at
#     `:435-445`, 8 for the emit and the reshaped early return, 11 for one more
#     section in `context_for` at `:373-405`, 2 of glue.
#   * `bin/sd_install.py`, **+2**. Two rows in `HOOK_SPECS`. This is what 8a
#     bought: the table went plural there, so two more events are two tuples
#     and an updated expectation in a test that answers to no cap.
#
# **Glue is 2.10 lines per boundary for a module this size, not 2.9.** R11-D42
# took 2.9 from one file. Measured over **every** tracked `bin/` module with
# fewer than fifteen top-level definitions -- fourteen of them, `sd_ledger`
# 1.33 through `sd_research_checklinks` 3.00 -- the mean is 2.10. The eleven
# with fifteen or more average 3.70, from `sd-handoff` 2.85 to `sd-status`
# 5.21, which is the opposite of what a per-boundary rate would predict and is
# why the split is by definition count rather than by an average over all of
# `bin/`. Two modules are excluded, both for the same measured reason and
# neither on assumption: `bin/sd-dashboard` at 10.14 carries a 57-line embedded
# `plist` template at `:48-100`, and `bin/sd_research_review.py` at 12.17 a
# 59-line `CHECKLIST` string at `:210-268`. A data blob between definitions is
# not glue between them; the check is that the gap is one literal, not that the
# number is large.
#
# Headers over those same fourteen run **21** (`sd_research_checklinks.py`,
# two definitions) to **86** (`sd_codex.py`, twelve), mean 52.4, against the
# 49-72 R11-D42 recorded. Across all of `bin/` the top is 156
# (`sd-skill-adopt`): a header states the module's policy, and its size tracks
# how much policy there is rather than how much code follows. So no header
# below is taken from the mean. Each is taken from a named built file whose
# obligations match the one being priced.
#
# The 119 is **one** seam and it is not the `note` rows. Reading notes is
# priced above as a caller, because `add_note` and `resolve_note` are built and
# the vocabulary is a SQL `CHECK` -- the same reasoning R11-D42 used to drop
# its GitHub seam. What is genuinely uncrossed is the `PreCompact` and
# `SessionEnd` payload contract: nothing here has ever registered either
# event, nothing has read either payload, and the failure mode of getting it
# wrong is a packet silently lost rather than an error anybody sees.
#
# The 32 is post-report discovery at **7.6%**, the mean of three observations
# and no longer two: R11-D38's 14.4% and 8.3%, and PR 8a's 0%. 8a's review
# round found ten stale line citations, seven of its own making and three
# older than the branch, and every one of them was corrected in place for no
# net `bin/` line at all. One round landing entirely in documentation is thin
# evidence for a rate, which is why it is averaged rather than adopted.
#
# 16,399 plus 573 is 16,972; the 28 unclaimed is what a round 17,000 left.
#
# R11-D44, 2026-09-07, funds **criterion 27 alone** -- PR 8c, the third of the
# four R11-D42 split PR 8 into. The base is 16,723, measured on `main` by
# `git ls-files bin` after PR 8b merged at `05adec9e`, and equal to what the
# branch carried. Criterion 28 stays unfunded, to be preceded by its own
# re-derivation against a measured tree, as this one was.
#
# **Body variance becomes its own line, at 12%.** Criterion 29 delivered 324
# against 573, which looks like room to spare and is not. The three spans
# actually built came to 324 against the 258 priced for them -- 26% over -- and
# the total held only because `bin/sd-handoff-prompt` and its 119 of seam were
# cut on evidence and returned 281. PR 8a's body was right to -2%; PR 8b's
# overran by 26%. Two observations, opposite signs, mean **+12%**. R11-D43
# carried no such line because one observation at -2% looked like precision. It
# was luck: a cut, not an estimate, is what kept 8b inside its cap.
#
# **The seam is 40, not the flat 119, because every boundary around the push
# has a repaired counterpart.** R11-D42 charged `git push` as a first crossing.
# Measured rather than assumed:
#
#   - The subprocess policy is built. `sd_lib.git_output` at `bin/sd_lib.py:143`
#     takes arbitrary `git` argv behind a fixed-argv call, a timeout, no shell
#     and a failure-is-None contract, with **30 call sites** across seven files.
#   - The *network* git policy is built. `git fetch` runs through that same
#     helper at `bin/sd_lib.py:1343` and `:1349`, and its failure is already an
#     operator-readable `Answer(UNKNOWN, "git fetch <remote> <ref>")`.
#   - The *mutating* git policy is built. `git commit` runs at
#     `bin/sd_lib.py:1227` with a `TrailerError` carrying git's own stderr.
#     R11-D42's "no `git push` exists anywhere in `bin/`" was true and
#     incomplete: write-side git is not new, only its remote half is.
#   - The harness is built. `tests/test_sd_pr_state.py:41` and `:147` put a
#     fake `gh` on `PATH` with fixed answers, which is the recording fixture a
#     first write needs, and tests answer to no cap.
#
# What is genuinely uncrossed is narrower than a push and is not the push.
# **No `gh` call in `bin/` has ever sent a non-GET method or a request body.**
# `sd_lib.gh_api` at `:269` runs `["gh", "api", endpoint]` with no method and no
# body; `gh_json` at `bin/sd-pr-state:117` passes arbitrary args but every one
# of its callers reads. Opening a pull request is the pack's first write to
# GitHub from `bin/`, and it needs a refusal vocabulary a read does not have: a
# rejected push, a pull request that already exists, a `gh` installed but
# unauthorised. The last is already written at `bin/sd-pr-state:166`. One
# boundary, half-repaired, failing loudly: **40**.
#
# **Two functions become one shared opener and two thin ends, and the reason is
# whose file it is.** R11-D42 priced promotion and demotion as a directioned
# pair on the `install_hook` / `remove_hook` precedent at
# `bin/sd_install.py:536` and `:608` -- 72 and 76 lines, 143 with the boundary.
# Reading them, what makes that pair expensive is not that it has two
# directions. It is that `~/.claude/settings.json` is **somebody else's file**:
# its docstring's own reasons are idempotence against a second `--user` run,
# interleaving against another installer, and refusing rather than overwriting
# a file that will not parse. `skills/paths.json` is this repository's own
# tracked file with a validating reader already built at
# `bin/sd_install.py:265`. None of the three policies transfer. The precedent
# was cited for its shape; its cost lives somewhere the shape does not reach.
# What differs between the directions is the move and the edit; the branch, the
# commit, the push and the pull request are identical, and pricing them twice
# prices a copy.
#
# **The 204 of body** is built in `bin/sd_skill.py` and not a new module,
# because `sd skill promote` and `sd skill demote` join `try`, `list` and the
# nightly under one verb group and reuse five things already there:
# `SkillRefusal`, `checkout()`, `available()`, `CONTRIB_DIR`, `SKILLS_DIR`. A
# new module would re-declare them and pay a header for the privilege.
#
#   `paths_edit`            34   one function, both directions. Loads the whole
#                                document, not `read_paths`'s `data["paths"]`,
#                                or the `$comment` block is destroyed
#   `branch_and_open`       66   the shared half: branch, staged `git mv`,
#                                commit, push, open, print the URL. Six steps
#                                each saying which one failed, plus a
#                                dirty-tree refusal so the commit sweeps in no
#                                unrelated work
#   `promote`               36   `contrib/<name>` exists, `skills/<name>` does
#                                not, a `--path` is named or the call refuses
#   `demote`                34   a path names it; paths.json's own comment says
#                                a skill may be on two, so removing from all or
#                                refusing is a real branch
#   `bin/sd`                22   two subparsers under the existing `skill` group
#   docstring and banner    12   `sd_skill.py`'s docstring is about trials today
#
# **Glue is 8.** `bin/sd_skill.py` goes from six top-level definitions to ten,
# still under fifteen, so R11-D43's 2.10 applies to four new boundaries.
# `bin/sd` gains subparser lines and no definition, so it draws nothing at 3.70.
#
# **Post-report discovery is 5.7%**, the mean of four observations: R11-D38's
# 14.4% and 8.3%, PR 8a's 0% and PR 8b's 0%. 8b's review round, like 8a's,
# landed entirely in documentation -- the `packet_section` defect was found
# while building and is counted in delivery, not after it. Two consecutive
# zeroes pull the rate down; they are averaged rather than adopted, for the
# reason R11-D43 gave. 5.7% of the 204 body is 12.
#
# 204 plus 8 plus 40 plus 24 plus 12 is **288**. 16,723 plus 288 is 17,011,
# which busts a round 17,000 by eleven. Rounding to the next fifty leaves 39
# unclaimed against R11-D43's 28, and the extra slack is bought by the
# body-variance line being new and two observations deep.
#
# R11-D45, 2026-09-07, funds **criterion 28 alone** -- PR 8d, the last of the
# four R11-D42 split PR 8 into. The base is 16,895, measured on `main` by
# `git ls-files bin` after PR 8c merged at `17d80480`.
#
# **The body-variance line changes statistic, and the reason is that the loss
# is not symmetric.** R11-D44 introduced it as the mean of two observations and
# gave it no theory of what it was for. Three now: PR 8a's -2%, PR 8b's +26%,
# PR 8c's -19% (172 delivered against 204 of body plus 8 of glue). Their mean
# is +1.7%, which is very nearly nothing, and a reserve sized to it would be
# too small half the time. An underrun costs unspent budget and nothing else.
# An overrun busts the cap, and the clause above forbids raising it in the pull
# request that busts it, so an overrun costs a re-derivation and a second pull
# request. A reserve is protection against the bad tail, not an estimate of the
# middle, so it is sized at the largest overrun yet observed: **26%**, PR 8b's.
#
# 8c's -19% is worth naming, because it is not noise. R11-D44 put validation in
# the two ends and the shared work in the middle, and left the directory move
# and the clean-checkout check in the ends, where each would have been written
# twice. Making the direction a parameter pulled both into the middle and the
# ends collapsed from 36 and 34 to 9 and 8. The correction was found by writing
# the code, which is where that class of error is always found.
#
# **The seam is 0, as R11-D42 had it, and PR 8c is why it stays 0.** Every
# boundary this criterion touches now has a built crossing on the other side:
# `gh api --method POST` at `bin/sd_skill.py:278` for filing an issue, the
# `gh_json` transport it goes through at `bin/sd-pr-state:117`, the suffixless
# import at `bin/sd_skill.py:160`, and `sd_db.sync_shadow` -- `sync` at
# `shadow_sync.py:391` in the installed library -- which is complete and whose
# own docstring settles the split: the module is the collector, the verb lives
# in the pack.
#
# **The 244 of body is two new modules and two edits, priced against named
# built files rather than against a range.**
#
#   `bin/sd_suggest.py`                                          128
#     header                    45   `bin/sd_skill.py:1-46`. The obligations
#                                    match: a policy about when a verb may
#                                    reach a remote, and why one gate is
#                                    explicit. `bin/sd-note:1-42` is the other
#                                    candidate at 42 and states less
#     deferred sd_db frame      18   `bin/sd_handoff_rows.py` `library` at 13
#                                    plus `connect` at 5, measured; the same
#                                    frame in `bin/sd_restore.py` is 19
#     the row, in every mode    30   `bin/sd-note` `cmd_write` at 26, which is
#                                    already "resolve the item, write the row,
#                                    print the id" exactly. Plus 4 for reading
#                                    the mode: "every mode" is
#                                    `bin/sd_lib.py:33` `MODES`, three of them,
#                                    and the row carries which
#     `publish`                 35   4 to refuse without `--to`, 16 for the
#                                    dedup read the skill already requires at
#                                    `skills/sd-suggest/SKILL.md:36` ("not 'I
#                                    searched my memory' -- the list API call,
#                                    actually made"), 12 for the POST measured
#                                    against `bin/sd_skill.py:277-284`, 3 to
#                                    print what was filed
#
#   `bin/sd_shadow.py`                                            84
#     header                    32   Smaller than either analogue on purpose:
#                                    `shadow_sync.py`'s own docstring states
#                                    the collector/verb split, so this one
#                                    cites it instead of restating it
#     deferred sd_db frame      18   the same 18, and not shared -- two modules
#                                    carrying their own is the measured
#                                    precedent, `sd_restore` and
#                                    `sd_handoff_rows` each having one
#     the wrapper               34   open, call `sd_db.sync_shadow`, render
#                                    `Synced`'s six fields into operator
#                                    English, close. `bin/sd_restore.py`
#                                    `resume` is 36 and `reimport` 47 for
#                                    comparable render-a-result work
#
#   `bin/sd`                                                      28
#     Two new groups and three verbs. PR 8c delivered 17 for two verbs under a
#     group that already existed; a group costs the difference
#
#   `_sibling` moves to `sd_lib`                                   4
#     The third copy. `bin/sd-status:97` and `bin/sd_skill.py:160` are the two,
#     and PR 8c's own log says two is a coincidence and three is a policy.
#     +18 in `sd_lib.py`, -18 in `sd_skill.py`, and an import line at each of
#     three call sites
#
# **Glue is 12.** `sd_suggest.py` has four definitions and `sd_shadow.py`
# three, both far under fifteen, so R11-D43's 2.10 applies to their three and
# two boundaries. `sd_lib.py` gains one definition at 3.70 and `sd_skill.py`
# loses one at 2.10.
#
# **Post-report discovery is 4.5%**, the mean of five: R11-D38's 14.4% and
# 8.3%, and 0% from each of PR 8a, 8b and 8c. Three consecutive zeroes is the
# point at which averaging a dead rate starts to look like ignoring evidence,
# so it is worth saying what the zeroes are: every review round since 8a has
# found real defects -- ten stale citations, a six-path row drop, a too-broad
# dashboard assertion, two harness defects -- and every one of them was fixed
# in documentation or in tests, neither of which answers to this cap. The rate
# is not measuring whether review finds things. It measures whether what review
# finds costs `bin/` lines, and lately it has not.
#
# 244 plus 12 plus 0 plus 63 plus 11 is **330**. 16,895 plus 330 is 17,225;
# the cap is **17,250** and the 25 unclaimed is what rounding left. This is the
# last of the four, so the next re-derivation in this item is a new item's.
# R11-D46, 2026-09-07, funds the **sd-status-answers-is-anything-wrong-first**
# item whole. The base is **17,189**: `line_count` over the files
# `tracked("bin")` enumerates, `migrate-*` excluded as always -- which is to
# say the same two functions `test_bin_stays_under_its_ceiling` calls, run on
# `main` at `6f9b96ad`. The enumerating command is named separately from the
# counting one on purpose, because every predecessor record here named only
# the first: `git ls-files bin` and `git ls-tree -r --name-only main bin` list
# paths and cannot produce a total, so a reader following those sentences
# literally gets a file list and no number. Found in review. For a historical
# commit the same measure is `git ls-tree -r --name-only <sha> bin`, then
# `git show <sha>:<path> | wc -l` summed, since the files are not in the tree.
# This is the first re-derivation in this file that is not PR 8's, which
# R11-D45's last sentence anticipated.
#
# **PR 8d came in at 228 against 256, and the four-slice split is now closed.**
# 16,895 before it, 17,123 after, both by that same measure at `17d80480` and
# `fe0712ae`. The 66 lines between
# 17,123 and the 17,189 base are the sweep item's branch resolution, which
# answered to no reservation and fitted in R11-D45's 25 unclaimed plus what 8d
# left -- which is the ordinary case a ceiling is supposed to permit.
#
# **The body-variance line keeps R11-D45's statistic and its number.** Four
# observations now: 8a -2%, 8b +26%, 8c -19%, 8d -11%. Their mean is -1.5% and
# three of the four are underruns, which is exactly why the mean is the wrong
# statistic here: an underrun costs unspent budget, an overrun costs a
# re-derivation and a second pull request. Sized to the largest overrun yet
# observed, still 8b's: **26%**.
#
# **The item's own `implement.md` budgeted 600 against a measurement that is now
# ten times stale** -- 12,416 lines and a 14,000 ceiling, read on `8cf99431` on
# 2026-09-04, when 1,584 lines of headroom made the figure a formality. Today
# `bin/` stands 61 lines under its ceiling, so the number has to be derived
# rather than claimed. That is the whole of why this record exists, and the
# item's budget section is corrected in the same change.
#
# **The 524 of body is nineteen spans at named built files.** The item lands in
# `bin/sd-status` alone, which is why every analogue below is drawn from that
# file where one exists there:
#
#   `Class` and `CLASSES`, 21 rows        79   `RESIDUE` at `bin/sd-status:946`
#                                              is 40 for six rows of four
#                                              fields at ~6 lines each. This
#                                              table is 21 rows of six written
#                                              three to a row, plus 8 for the
#                                              NamedTuple and the same comment
#                                              head. `ACKNOWLEDGED_FACTS` at
#                                              `:442` is the other candidate at
#                                              4.25 lines a row, and is rejected:
#                                              its rows carry a prose sentence
#                                              each and these carry a rank
#   `EXCLUDED` and its printed line       14   `BACKENDS` at `:903`, 10 for a
#                                              flat tuple, plus 4 for the
#                                              sentence `design.md:310` requires
#                                              so the section never implies it
#                                              swept what it skipped
#   `action_id()`                         14   No smaller analogue exists in the
#                                              file: `_always_listed` at `:1097`
#                                              is 4 and states no policy. C-11
#                                              makes the key a check-and-subject
#                                              pair, and the stability rule that
#                                              verification 5 diffs has to be
#                                              written down beside it
#   `actionable_inventory()`              21   `residue_section` at `:986`,
#                                              which is already "run the
#                                              producers, tag each row, return
#                                              the list"
#   the work-item producer                33   `backends_section` at `:913`.
#                                              Four checks, one pass over the
#                                              items
#   the `open-step` producer              33   the same
#   the `source-marker` producer          21   `residue_section`; one `git grep`
#                                              and a row per hit
#   the `undisclosed-tool` producer       21   `residue_section`; a glob, a
#                                              `test -e`, a row per miss
#   four adapters over built sources      24   `protection-gap`,
#                                              `issue-needs-you`/`issue-open`,
#                                              `unmerged-branch` and the three
#                                              `pr-*` checks already have
#                                              producers -- `_protection_gaps`,
#                                              `issues_section`,
#                                              `carrier_branches` and
#                                              `bin/sd-pr-state`. Each costs a
#                                              six-line row shaper, not a
#                                              producer. This is where the
#                                              21-check table stops being
#                                              alarming
#   `branch_landed()`                     41   `sd_lib.delivered` at
#                                              `bin/sd_lib.py:1342`, the built
#                                              three-state git answer with the
#                                              same never-a-bare-boolean
#                                              contract. Three tiers rather than
#                                              two, and one fewer network call
#   the ledger scanner, `DISPOSITIONS`    96   `load_acknowledgements` at
#                                              `:484` is 87 for one file parsed
#                                              against a vocabulary, emitting a
#                                              row per line it cannot read --
#                                              which is `unreadable-concern-row`
#                                              exactly. Plus 9 for the four
#                                              rules the prototype earned
#   `accepted-gap-standing` rows          12   `_apply_acknowledgements` at
#                                              `:571` reads that same file, so
#                                              this is a second loop over
#                                              `accepted_gaps[]` and not a
#                                              second reader
#   `_render_banner`                      22   `pack_banner` at `:129`, the
#                                              built summary line
#   `_render_pending`                     26   `_render_work` at `:1101`, a
#                                              capped sorted list that states
#                                              its own suppressed count
#   `_render_next`                        15   `_render_issues` at `:1214`
#   `_render_threads`                     16   `_render_handoff` at `:1165`
#   eight empty-state sentences           16   2 each, at the `if not X:` pairs
#                                              already in the renderers
#   `--actions`, `collect`, the bump      20   `build_parser` at `:1240` is 24
#                                              for the whole parser, so one flag
#                                              is 4; `collect` at `:1063` gains
#                                              three keys and their calls at 16
#
# **Glue is 89, and it is `bin/sd-status`'s own rate rather than its class's.**
# Seventeen new top-level definitions. R11-D43 measured 3.70 for the eleven
# modules with fifteen or more definitions, and measured `bin/sd-status` itself
# at **5.21**, the highest of them. The file has 42 definitions and every line
# of this item lands in it, so the file's own figure is the one that applies;
# using the class mean would price this change against ten modules it does not
# touch. 17 x 5.21 = 89.
#
# **The seam is 0, and the reason is that the discovery has already been made.**
# Two boundaries look new and neither is. Nothing in `bin/` shells out to
# `git grep` -- checked, `grep -rn '"grep"' bin/` returns nothing -- and nothing
# passes `--no-renames`. But both go through `sd_lib.git_output`, the fixed-argv
# transport with 30 call sites, so the *transport* is repaired; what a seam
# charge actually buys is the discovery behind an unrepaired boundary, which is
# R11-D44's correction and R11-D45's reason for its own 0. Here that discovery
# is already written down: the item's `implement.md` step 3 records a prototype
# run with four rules it earned the hard way -- including that keying on
# `split("/")[2]` collapses 487 archived items into one bucket -- and its
# expected counts on today's corpus, 245 concerns, 206 closed, 23 open, 16
# unclassifiable. Step 2 records the tier-1/tier-2 split verified against this
# checkout's five squash-merged branches. A crossing whose findings are in the
# plan is paid for in the body, not in a contingency.
#
# **Post-report discovery is 5.5%, and the run of zeroes is over.** Six
# observations: R11-D38's 14.4% and 8.3%, 0% from each of PR 8a, 8b and 8c, and
# **10.6%** from the sweep item -- two review rounds costing a net +7 lines in
# `bin/` (`e2d12b09` +9/-4, `83e2e2dd` +6/-4) against a 66-line delivered body.
# R11-D45 said three consecutive zeroes were measuring whether review's findings
# cost `bin/` lines rather than whether review finds things; the sweep item is
# the case where they did, because what its reviewer found was a docstring
# making a false claim about cost, and a docstring in `bin/` charges this cap.
# Mean of six is 5.5%; 5.5% of the 524 body is 29.
#
# 524 plus 89 plus 0 plus 159 plus 29 is **801**. 17,189 plus 801 is 17,990 and
# the cap is **18,000**; the 10 unclaimed is what rounding to the next fifty
# left, and it is smaller than any predecessor's because 801 is a 4.7% raise and
# a wider margin on top of a reserve this size would be asking twice.
#
# The item is funded **whole** rather than sliced. R11-D42 split PR 8 because
# 2,592 in one step was 16.5% for scope a month out; this is a third of that
# against a body specified span by span in a design that already ran a prototype.
# Step 1 of its checklist is still landable alone, which is a property of the
# work and not of the funding.
#
# **R11-D47, 2026-09-07, funds steps 2 through 7 of the same item, and is the
# first record in this file derived from a measurement of its own predecessor
# rather than from analogues alone.** The base is **17,800**: `line_count` over
# the files `tracked("bin")` enumerates with `migrate-*` filtered out -- the two
# functions `test_bin_stays_under_its_ceiling` calls -- run on `main` at
# `5c23df19`. R11-D46 funded the item whole at 18,000; step 1 spent 584 of the
# 801 it reserved, and the 200 left do not hold the rest.
#
# **The ceiling moves; the steps do not.** The operator's ruling of 2026-09-07,
# in their words: *"whatever does not reduce existing functionality. We gotta
# get out of the proposal to remove functionality to maintain a cap. I will
# never agree to that. If functionality requires more code, then it requires
# more code."* Nothing below trims scope to fit a number. The cap exists to make
# growth deliberate and measured, which is why this record derives a raise
# rather than waving one through -- and why it is not raised in the pull request
# that needs it.
#
# **Step 1 measured span by span against what R11-D46 priced.** Each span was
# located by walking the module's AST on `main` at `5c23df19` and taking the
# top-level definition's own line extent, so these are delivered spans and not a
# re-reading of the diff:
#
#   `Class`, `CLASSES`, `BY_CHECK`      priced  79   actual  56   0.71x
#   `EXCLUDED`                          priced  14   actual  16   1.14x
#   `action_id()`                       priced  14   actual  19   1.36x
#   `actionable_inventory()`            priced  21   actual  45   2.14x
#   `_work_rows()`                      priced  33   actual  57   1.73x
#   `_step_rows()`                      priced  33   actual  48   1.45x
#   `_marker_rows()`                    priced  21   actual  29   1.38x
#   `_tool_rows()`                      priced  21   actual  27   1.29x
#   four adapters                       priced  24   actual 121   5.04x
#                                       ----------   ----------
#                                              260          495   1.90x
#
# The item's own `implement.md` records step 1 at 586. The measure above, taken
# at `d3166845~1` and `d3166845` by the same two functions the test calls, is
# **584**. Two lines, and the smaller number is the measured one.
#
# **Where the other 89 went, and it is not all glue.** 584 minus the 495 above
# leaves 89. Seven of it is seven one-line module constants nobody enumerated --
# `IDLE_DAYS`, `_BOX_RE`, `_DISCLOSED_RE`, `_HEADING_RE`, `_ITEM_DATE_RE`,
# `_MARKER_PATHS`, `_MARKER_PATTERN` -- and four unpriced helpers cost a further
# 77: `_row` 18, `_widen_collisions` 17, `_age_days` 18, `_branch_names` 24.
# Those 77 sit inside the 495 as delivered lines but against a price of zero.
# Measured spans are therefore 502 and true glue -- blank lines, comment heads,
# the import -- is **82**.
#
# **Three findings, and only one is "the estimate was low".**
#
# - **The glue rate came in under, and the definition count came in over.**
#   R11-D46 charged 5.21 a definition, this file's own figure, over an assumed
#   13. Step 1 added **25** top-level definitions and 82 lines of glue, which is
#   **3.28** each. Forecasting a definition count is the fragile half, so glue
#   is charged below as a fraction of measured span instead: 82/502 = **16.3%**.
# - **A span priced at a built same-file analogue lands near it.** The four
#   producers ran 1.29, 1.38, 1.45 and 1.73 against `residue_section` and
#   `backends_section`, mean **1.46**; `CLASSES` came in *under* at 0.71 against
#   `RESIDUE`.
# - **A span priced by its shape missed by five.** The four adapters were "a
#   six-line row shaper" and cost 30 each. R11-D46 flagged that span itself as
#   "the first span in the series priced by its shape rather than at a named
#   built analogue". It was, and it is the one that missed. The cause is
#   nameable and not adapter-specific: an inventory row carries `title`,
#   `detail` and `suggest` prose plus a docstring, and six lines cannot hold
#   them.
#
# **So the remaining 264 is priced by how each span was priced, not by one
# blended multiplier.** Eight of the nine sit at a built analogue in this same
# file and take **1.5x**, the producers' measured mean rounded up. The ninth is
# shape-priced and takes **2.0x**:
#
#   `branch_landed()`                    41   1.5x    62   `sd_lib.delivered`
#   the ledger scanner, `DISPOSITIONS`   96   1.5x   144   `load_acknowledgements`
#   `accepted-gap-standing` rows         12   1.5x    18   `_apply_acknowledgements`
#   `_render_banner`                     22   1.5x    33   `pack_banner`
#   `_render_pending`                    26   1.5x    39   `_render_work`
#   `_render_next`                       15   1.5x    22   `_render_issues`
#   `_render_threads`                    16   1.5x    24   `_render_handoff`
#   eight empty-state sentences          16   2.0x    32   shape, "2 each"
#   `--actions`, `collect`, the bump     20   1.5x    30   `build_parser`
#                                       ---          ---
#                                       264          404
#
# **Plus 84 for spans nobody will enumerate.** Step 1's four helpers and seven
# constants cost 84 against a price of zero, which is **32%** of its priced 260.
# This is the honest half of the derivation: a span list is a forecast of what
# the work will turn out to need, and the single measurement available says such
# a list undercounts by about a third. 32% of the priced 264 is 84 -- taken on
# the priced figure rather than on the 404, because the 1.5x already absorbed
# part of the same effect and charging both to the adjusted number would ask
# twice. Body is **488**.
#
# Glue at 16.3% of 488 is **80**. Body plus glue is **568**.
#
# **The seam is 0, for the reason R11-D46 gave and R11-D44 fixed.** Steps 2 and
# 3 cross into `git grep` and branch resolution. Both go through
# `sd_lib.git_output`, the fixed-argv transport with 30 call sites, so the
# transport is built; and the discovery is written down -- step 3's prototype
# run with its four earned rules and its expected counts, step 2's tier split
# verified against this checkout's five squash-merged branches. A seam charge
# buys discovery that has not happened. This one has.
#
# **Variance stays at 26%**, this file's largest observed overrun, still 8b's.
# It is deliberately not raised to step 1's 1.90x: that overrun is priced into
# the multipliers above rather than left for a contingency to absorb, and
# charging it in both places would ask twice. 26% of 568 is **148**.
#
# **Post-report discovery is 4.76%, and a seventh observation lowered it.**
# R11-D46 recorded six: 14.4%, 8.3%, 0%, 0%, 0% and 10.6%. Step 1's review is
# the seventh. It raised two findings -- a wall-clock-dependent test, confirmed
# and fixed, and a Windows path separator, rejected because the line it names is
# untouched context, the same pattern stands at 12 sites, and this pack targets
# no Windows. The fix landed in `#787` touching `tests/test_sd_status.py` alone,
# so it cost `bin/` **0**. Mean of seven is 4.76%; 4.76% of the 488 body is
# **23**.
#
# 488 plus 80 plus 0 plus 148 plus 23 is **739**. 17,800 plus 739 is 18,539 and
# the cap is **18,550**; the 11 unclaimed is what rounding to the next fifty
# left. The raise is 550 on 18,000, or 3.1%.
#
# One sanity line, because a derivation this long can be right at every step and
# wrong in total: 739 is a little above the 584 step 1 actually cost, for a
# remaining half whose priced spans total 264 against step 1's 260. The halves
# are the same size, the first is measured, and the second is funded slightly
# above it. That is the shape the number should have.
# Approved additional controls: docs/workflow-control-capacity.md. Keep this
# capacity decision separate from the implementation when publishing.
BIN_CAP = 20_231
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
# busts it" -- reports how `BIN_CAP` and `DASHBOARD_CAP` were each moved, and
# those two have no slack test. `DASHBOARD_CODE_SLACK` makes a standalone
# raise of *this* cap impossible: a raise with no code beside it widens the
# distance and fails on the spot. The two rules cannot both be met, and
# R11-D41 is the later one and was written for this cap by name, so it wins
# here. Recorded rather than resolved quietly, because the older paragraph
# still governs the other two ceilings and should not be read as retired.


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
        ("2026-09-07", 17_000),
        ("2026-09-07", 17_050),
        ("2026-09-07", 17_250),
        ("2026-09-07", 18_000),
        ("2026-09-07", 18_550),
        ("2026-09-08", 19_500),
        ("2026-09-08", 20_050),
        ("2026-09-09", 20_231),
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
