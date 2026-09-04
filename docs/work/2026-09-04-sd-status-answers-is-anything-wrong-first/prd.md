---
title: sd-status answers "is anything wrong" before it answers anything else
status: planning
created: 2026-09-04
branch:
---

# PRD — sd-status answers "is anything wrong" first

## Problem

`bin/sd-status` prints eight sections in a fixed source order, but the sections
themselves are not fixed: `open pull requests` prints a body only when there are
some, `legacy residue` prints `none found` but the residue rows do not, and the
work-item list elides after twenty. A reader cannot learn the shape once and
then scan for the deviation, because the shape changes with the content.

Worse, nothing in the report answers the first question anyone actually has.
Everything it prints is a fact; none of it is a judgement. The report on `main`
at `8cf99431` prints `planning     the-plan-interview-is-one-sentence` in a list
of three planning items — and that item's branch `skill/sd-grill` was squash-
merged into `main` sixty-four minutes earlier as `#740`. The work is done, the
document says `planning`, and `sd-status` prints the contradiction without
noticing it, one indistinguishable row among 493.

The same run buries every other open thread. Two review concerns under
`## Review` in that item's `prd.md` are disposed `parked` and carry triggers
nobody is watching. Nine acceptance criteria on it are unchecked. Four branches
on `origin` are unmerged with no open pull request. None of that appears
anywhere in the report, and there is no handle to refer to any of it by: to ask
for one, you have to describe it in prose and hope the next session resolves the
description to the same thing.

## Requirements

1. **A fixed output skeleton.** Every section prints on every run, in the same
   order, whether or not it has content; an empty section prints a sentence
   saying it is empty rather than vanishing. The order is stated in
   `skills/sd-status/SKILL.md` and the reader learns it once.
2. **An abnormality banner, first.** Before any other section, one block
   answering "is anything wrong" without reading the rest. Its findings are
   derived on every run from git, the filesystem and the already-collected
   GitHub state; nothing is read from or written to a maintained list of known
   problems. The checks that exist are a single enumerated table in the source,
   so "which checks are there" is answered by reading one constant.
2b. **A check that could not run says so.** Each class reports one of three
   states — `clear`, `n finding(s)`, or `unchecked: <reason>` — and an
   `unchecked` class is never counted as clear. A banner that answers "is
   anything wrong" must distinguish *nothing is wrong* from *I could not look*,
   or it asserts health it never established.
3. **The abnormality classes cover the contradictions this repository actually
   produces**, each derived rather than declared: a non-`done` item whose branch
   is already in the default branch (including through a squash merge, which is
   how this repository merges); `status: in_progress` with no `branch:`; a
   `branch:` that resolves to no ref; an item whose `prd.md` will not yield a
   status; an item idle in `planning` past the 45-day R10-D1 threshold; a
   planning item with no date to age it by; an open pull request with a failing
   check; an open pull request missing a required context; a dirty tree on a
   branch that has an open pull request; an open protection gap; and a review
   concern-ledger row whose disposition this reader does not recognise. That
   last class replaces "a concern disposed `unresolved`", which was measured and
   found to have no members: `unresolved` is used zero times as a disposition
   anywhere under `docs/work/`. The corpus carries five disposition
   vocabularies across at least eight ledger headings, so the real risk is a row
   nothing can classify, and that row is itself the finding.
4. **Pending items, ranked, capped at 10.** The ranking rule is stated in the
   output and in the skill, so a reader can predict the order before running it.
   The line says how many items the cap suppressed, and the suppressed ones are
   reachable through `--actions` and `--json` rather than lost.
5. **One next step.** A single concrete suggestion derived from the top-ranked
   pending item — not a menu, not a list of three.
6. **Unaddressed recommendations, followups, flags and issues are found and
   reported**, from sources this repository actually has, with what was
   deliberately excluded stated in the output rather than left implicit.
7. **Every actionable item carries a stable id** that is short enough to type
   and derivable from the data alone, so that "do `w7a3c`" in a later session
   still means the same item. No id ledger is written anywhere: `sd-status`
   stays read-only.
8. **The ids are pickable through the harness `AskUserQuestion` component**,
   whose hard limits are four options per question and four questions. The
   resolution of "10 items, 4 slots" is written into
   `skills/sd-status/SKILL.md` so the calling agent renders one thing and not
   whatever it invents.
9. `sd-status` still writes nothing — no cache, no index row, no state file —
   and still exits 0 whether or not it found abnormalities. Exit 2 stays
   reserved for an invocation fault.

## Acceptance criteria

- [ ] `make check` ends with `0 FAILED` and reports `40 OK` — unchanged from
      `8cf99431`, because this adds tests to `tests/test_sd_status.py` and no
      new test module
- [ ] `python3 -m unittest tests.test_sd_status -v` prints `OK` with 0 failures
      and 0 errors
- [ ] `python3 -m unittest tests.test_loc_caps` prints `OK`; `bin/` measured by
      `line_count(tracked("bin"))` stays at or under 14,000, and
      `git diff --stat origin/main...HEAD -- dashboard/` prints nothing, so no
      dashboard ceiling moves — evaluated on the pushed branch, since before the
      commits exist the diff is empty whatever the tree holds
- [ ] `./bin/sd-status | head -1` prints `sd-status: <this repo path>` and
      `./bin/sd-status | grep -c '^abnormalities$'` prints `1`
- [ ] running `./bin/sd-status` in this checkout names
      `the-plan-interview-is-one-sentence` under `abnormalities` with class
      `branch-already-merged`: `./bin/sd-status --json | python3 -c "import
      json,sys; d=json.load(sys.stdin); print(sum(1 for a in d['abnormalities']
      ['findings'] if a['check']=='branch-already-merged'))"` prints `1`
- [ ] the section skeleton is fixed: this command prints the twelve section
      headings in order, and prints them identically for a repository with no
      work items —
      `./bin/sd-status | grep -nE '^[a-z][a-z ()/,-]*$'`
- [ ] `./bin/sd-status | sed -n '/^pending/,/^$/p' | grep -cE '^  [a-z][0-9a-f]{4}'`
      prints a number `<= 10`, and the `pending` heading line states the total
      and how many were suppressed
- [ ] every id is a pure function of the data: running `./bin/sd-status --json`
      twice and diffing the `id` fields prints nothing —
      `diff <(./bin/sd-status --json | python3 -c "import json,sys;
      print('\n'.join(a['id'] for a in json.load(sys.stdin)['actions']))") <(...
      the same command again ...)` prints nothing
- [ ] `sd-status` writes nothing: `tests/test_sd_status.py` already asserts a
      read-only tree digest around a full run, and that test still passes —
      `python3 -m unittest tests.test_sd_status.ReadOnlyTests` prints `OK`
- [ ] `grep -c 'AskUserQuestion' skills/sd-status/SKILL.md` prints at least `1`
      and the section naming it states the 4-options/4-questions limit and the
      resolution
- [ ] `./bin/sd-status --actions | head -1` names the total number of actionable
      items, and `./bin/sd-status --actions | grep -cE '^[a-z][0-9a-f]{4} '`
      equals that total
- [ ] `./bin/sd-status; echo $?` prints `0` in this checkout, which has
      abnormalities — a finding is a report, not a failure
- [ ] two findings on one object get two ids: the test named in `implement.md`
      step 7 builds a pull request that is both `pr-check-failing` and
      `dirty-tree-with-open-pr` and asserts the two inventory rows have
      different `id` values. This is C-11's regression check, and under the
      rejected letter-keyed formula it fails
- [ ] a check that could not run prints `unchecked` and is not counted clear:
      with `PATH` stripped of `gh`, `./bin/sd-status --json | python3 -c "import
      json,sys; b=json.load(sys.stdin)['abnormalities'];
      print(b['unchecked_classes'] > 0 and 'clear' not in b['summary'])"` prints
      `True`
- [ ] the ledger scanner classifies this repository's real corpus: `./bin/sd-status
      --json | python3 -c "import json,sys; a=json.load(sys.stdin)['actions'];
      print(sum(1 for r in a if r['check']=='open-concern'))"` prints a non-zero
      count, and the row for `C-19` in
      `docs/work/archive/2026-08/2026-08-26-codex-local-review-adapter/prd.md`
      — disposed `ACCEPTED and parked` — is among them. That row is the one an
      archive-excluding or `## Review`-heading-matching scanner silently drops
- [ ] `./bin/sd-status --json | python3 -c "import json,sys;
      print(json.load(sys.stdin)['threads']['unreadable_rows'])"` prints a list,
      and every `C-` row in `docs/work` that the scanner could not classify
      appears in it — nothing is dropped silently. On today's corpus that list
      has 16 entries against 245 concerns; the criterion is that the list is
      printed and complete, not that it is empty
- [ ] the ledger classifier reproduces the prototype's measured split on this
      corpus: 245 distinct concerns, 206 closed, 23 open, 16 unclassifiable, and
      `C-19` in `archive/2026-08/2026-08-26-codex-local-review-adapter` is among
      the open ones. Any of the four rules in `implement.md` step 3 being dropped
      changes one of these four numbers, which is what makes them a check rather
      than a description

### What these criteria do not cover

The claim that a reader can "immediately see whether there is anything to look
for" is about a person's eyes and cannot be checked here. What is checked is the
mechanical part of it: the skeleton is fixed, the banner is first, and the
banner is non-empty exactly when a derived check fires. Whether the resulting
page reads well is the user's judgement on the first real run.

The `AskUserQuestion` rendering is a property of the calling agent, not of
`bin/sd-status`. No test in this repository can assert that an agent rendered
four options with `multiSelect`. The criterion above checks that the skill
*states* the contract, which is the achievable half; the other half is the
user's.

## References

- `bin/sd-status`, `bin/sd_lib.py`, `bin/sd_sweep.py` (the 45-day R10-D1
  threshold and the `item_date` derivation this reuses), `bin/sd-pr-state`
  (`collect`, `failing_checks`).
- `.claude/sd-ai-command-pack/planning-adversarial-review.md` — the four
  dispositions `addressed`, `rebutted`, `parked`, `unresolved` that the concern
  scanner reads.
- `tests/test_loc_caps.py` — `bin/` measured 12,416 on `8cf99431` against a
  14,000 ceiling.

## Review

Planning adversarial review, 2026-09-04. Trigger: `prd.md`, `design.md` and
`implement.md` all new — none existed at baseline. Lanes: the host lane
(completed, two rounds) and this repository's native `bin/sd-review --scope
planning` lane. The ledger below is merged across both.

| ID | Lane | Round | Severity | Blocking | Disposition |
|---|---|---|---|---|---|
| C-1 | host | 1 | high | yes | addressed |
| C-2 | host | 1 | high | yes | addressed |
| C-3 | host | 1 | medium | yes | addressed |
| C-4 | host | 1 | medium | no | rebutted |
| C-5 | host | 1 | medium | yes | addressed |
| C-6 | host | 1 | low | no | parked |
| C-7 | host | 2 | medium | yes | addressed |
| C-8 | host | 2 | low | no | rebutted |
| C-9 | host | 2 | medium | yes | addressed |
| C-10 | host | 2 | low | no | rebutted |
| C-11 | codex | 1 | high | yes | addressed |
| C-12 | codex | 2 | medium | yes | addressed |
| C-13 | codex | 2 | medium | yes | addressed |
| C-14 | coordinator | 2 | high | yes | addressed |
| C-15 | coordinator | 2 | high | yes | addressed |
| C-16 | coordinator | 2 | medium | no | rebutted |
| C-17 | coordinator | 2 | medium | yes | addressed |
| C-18 | codex | 3 | high | yes | addressed |
| C-19 | codex | 3 | high | yes | addressed |
| C-20 | inventory | 3 | high | yes | rebutted |
| C-21 | inventory | 3 | high | yes | addressed |
| C-22 | inventory | 3 | medium | yes | addressed |

**C-1 — the merged-branch check would have found nothing.** The first draft
tested `git merge-base --is-ancestor <branch> <default>`, and this repository
squash-merges: `origin/skill/sd-grill` is *not* an ancestor of `origin/main`
even though `#740` landed all of it sixty-four minutes ago. The check would have
shipped green against a repository where the abnormality it was written for is
sitting in plain sight — the exact failure the PRD's problem statement names.
Addressed in `design.md`: the test is now "every path the branch touched is
identical in the default branch", derived from two `git diff --name-only` calls,
with the ancestor test kept as the cheap first pass. Verified by hand on
`8cf99431`: `git diff --name-only origin/main origin/skill/sd-grill` prints
nothing, so the intersection with the branch's own changed paths is empty.

**C-2 — a sequence id fails requirement 7 and the draft used one.** `A1..A10`
renumbers the moment an item resolves, which is precisely the failure the
requirement forbids, and the draft had written `A1` into two examples. Addressed:
the id is a class letter plus four hex digits of `sha1(class + "\0" + natural
key)`, and `design.md` names the natural key for each of the eight classes and
argues why each key is stable. The collision behaviour is specified rather than
left to chance, and its residual instability is stated in `design.md` under
`## Risks` instead of being claimed away.

**C-3 — "abnormalities" and "pending" overlapped with no rule.** A merged-but-
open item is both an abnormality and the top pending item, and the draft let it
appear twice with two ids. Addressed: there is exactly one inventory. An
abnormality is an inventory row whose class is marked abnormal, and the banner
renders those rows; the `pending` section ranks the whole inventory. One row,
one id, two renderings — so `w7a3c` in the banner and `w7a3c` in `pending` are
the same thing and the reader is never asked to reconcile two lists.

**C-4 — reading every `prd.md` on every run is too slow at 493 items.**
Rebutted with a measurement rather than an argument: `sd-status` already calls
`sd_lib.work_items(root)`, which opens and parses all 493 `prd.md` files today,
and the full report returns in well under a second. The concern scanner reads
only the non-archived, non-parked items — six files in this repository — so it
adds six reads to 493. The measurement is `time ./bin/sd-status >/dev/null` on
the branch, recorded in `implement.md`'s verification step.

**C-5 — an unchecked `- [ ]` on a `done` item is not actionable, and the draft
counted it.** 490 archived items carry checked and unchecked boxes as historical
record; sweeping them in would have produced an inventory of thousands, capped
at 10, in which nothing real was ever visible. Addressed: the checkbox scanner
reads only items that are neither archived nor parked nor `done`, and
`design.md` records the exclusion beside the others so the output can state it.

**C-6 — `--actions` is a fourth flag on a command the design describes as
having three.** Parked, not blocking. The alternative is that the ids for items
11..N exist only in `--json`, which makes the human-facing half of requirement 7
depend on a JSON reader. The flag is additive and read-only. Trigger: a decision
that `sd-*` commands have a flag budget. Owner: the user.

**C-7 — the acceptance criteria were four intentions wearing check syntax.**
Round 1 shipped "the skeleton is fixed" and "ids are stable" with no command
behind either. Addressed: every criterion above now names a command and the
output it must produce, including the two-run `diff` that is the only way to
check id stability mechanically, and the two claims that genuinely cannot be
checked here are moved under `### What these criteria do not cover` with the
reason.

**C-8 — the 45-day idle check duplicates `bin/sd_sweep.py`.** Rebutted:
`design.md` imports `sd_sweep.item_date` and `sd_sweep.DEFAULT_DAYS` rather than
restating either. What is not shared is `scan()`, because it walks the tree a
second time and `sd-status` already holds the `WorkItem` list; the threshold and
the date derivation — the two things that could drift into disagreement — have
exactly one definition each.

**C-9 — the cross-artifact sweep found the line budget asserted in one place
and contradicted in another.** `design.md` claimed "about 380 lines" while
`implement.md`'s step 5 budgeted 300 and the PRD cited neither. Every occurrence
of each figure was enumerated with `grep -rn` across the item directory rather
than by rereading the files in order. Addressed: the budget appears once, in
`implement.md`, as a ceiling checked by `tests/test_loc_caps.py`; `design.md`
now points at that check instead of restating a number, and the PRD's criterion
names the test rather than a line count.

**C-10 — the review lane's first run reported `check: fail (exit 1)`, which
could have been read as a red gate on these artifacts.** Rebutted with the
cause: this worktree has no `.venv`, so `make check` had no interpreter, and the
Makefile's `VENV ?= .venv` makes that a per-checkout fact rather than a repo
fact. Re-run as `VENV=<main checkout>/.venv ./bin/sd-review --scope planning`
the gate printed `check: pass (exit 0)`, and the same `make check` invocation
printed 40 `OK` and 0 `FAILED`. The failure was the environment, not the work.

**C-11 — the id key omitted the check, so two findings on one object always
collided.** Found by the Codex lane, not the host lane, and it is the defect
that would have made requirement 7 useless in practice. The draft hashed
`class letter + "\0" + natural key`, but a pull request can be
`pr-check-failing` and `dirty-tree-with-open-pr` at the same time, and a work
item can be `branch-already-merged` and `idle-planning` at the same time; every
such pair hashed to one id. The lane evaluated the published formula rather than
describing it and got `pa02e3ced` for both members of the pull-request pair, so
the eight-digit widening the design offered as the collision remedy was no
remedy at all — the inputs were identical, not merely close. Addressed in
`design.md`: identity is `(check, natural key)`, the letter is a display prefix
only, and the design now states that two findings on one object are two rows
with two suggestions on purpose. A test for exactly that case is step 7's first
named case in `implement.md`.

**C-12 — the merge detector loses rename source paths.** `git diff --name-only`
reports a rename as its destination only, with rename detection on by default
(confirmed by the lane against `c85fcf0c`). A branch renaming `A` to `B`, where
the default branch holds both `A` and an identical `B`, puts `B` in `touched`
and `A` in `divergent`; they do not intersect and the detector says the work
landed although `A`'s removal never did. Addressed: `--no-renames` on both
diffs, with the reasoning in `design.md`, and the case is a named test.

**C-13 — checkbox and marker text are not unique keys within a file.** Two
implementation steps can each carry `- [ ] Run make check`; the lane evaluated
the published formula and got `s839e`, then `s839ed045`, for both occurrences.
Identical inputs, so widening resolves nothing — the same structural defect as
C-11 in a second place. Addressed: the `s` key gains the nearest preceding
heading and an ordinal over identical `(heading, text)` pairs; the `t` key gains
an ordinal. `design.md` states plainly that the ordinal is the weakest component
here and why the alternatives are worse.

**C-14 — every git-only merge test is a false negative in this repository, and
the design shipped one as its only tier.** The path-equality detector was
measured against all five surviving `origin` branches rather than argued about:
ancestry finds 0 of 5, path-equality finds 3 of 5, and the two misses are the
predicted case where `main` has since edited the same paths. A 40% false-negative
rate under a banner that asserts health is not acceptable. Addressed: the check
is now two-tier — path equality offline, `mergedAt` from a matched pull request
when GitHub is reachable — with the measurement table, and `git branch --merged`,
`--is-ancestor` and `git cherry` each recorded as a rejected alternative with the
evidence, because the next person will reach for them first.

**C-15 — the banner had two states and needed three.** Tier 2 needs the
network, and a check that could not run was going to print as clear. Addressed:
requirement 2b, and a per-class `clear` / `n finding(s)` / `unchecked: reason`
state where unchecked is never counted as clear. This is the same rule the
`protection` section already lives by — "never present the absence of gaps you
did not read as safety" — applied to every class rather than one.

**C-16 — the REST `merged` boolean reportedly reads `false` while `merged_at`
carries a timestamp; do not branch on it.** Rebutted on measurement, and
recorded as unreproduced rather than repeated:
`gh api repos/<slug>/pulls/740` returns `"merged": true` beside
`"merged_at": "2026-09-04T22:11:09Z"`. The advice is followed anyway for a
different and verified reason — `gh pr list --json merged` errors with
`Unknown JSON field`, so `mergedAt` is the only field available at the call site
tier 2 uses.

**C-17 — an existing planning item already owns branch resolution, and silently
implementing half of it would strand it.**
`docs/work/2026-09-04-the-sweep-trusts-a-branch-field-it-never-resolves`
(`status: planning`, unowned) exists because `sd_sweep` excludes any item with a
`branch:` field without ever resolving it. Addressed by an explicit scope call
in `design.md`: this item does not touch `bin/sd_sweep.py`, so that item stays
landable and keeps its own fix. What is adopted from it, with attribution, is
its criterion 5 (local *and* remote refs count) and its criterion 4 ("git cannot
answer" is distinct from "the branch is absent"), and what is supplied back to
it is an answer to its open question 2: a `branch:` resolving to nothing is a
third state that is reported, not swept. Its evidence that CI cannot host such a
check — `.github/workflows/tests.yml` sets no `fetch-depth`, so the checkout is
depth 1 with no other branches — is recorded in `design.md` rather than
re-derived later.

**C-18 — the ledger anchor matched no table rows at all.** The regex allowed no
whitespace after the optional `|`, and every markdown ledger in this repository
writes `| C-7 | host | 1 | low | no | parked |` with a space after the pipe. The
lane ran the published anchor against the adjacent interview PRD and got
`ledger table rows=13; proposed anchor matches=0` — so the scanner built to stop
concerns being silently dropped would itself have silently dropped an entire
ledger format, including the `unreadable-row` safeguard that was supposed to
make that impossible. Addressed: `\s*` after the pipe. Re-measured on that same
file, exactly as the lane did: 15 matches before, 28 after, the difference being
its 13 table rows.

**C-19 — `headRefName` alone does not establish that *this* branch landed.**
Tier 2 matched any merged pull request with the branch's name, which answers a
different question. A branch reused or extended after an earlier merge matches
the old PR's `mergedAt` while carrying unlanded commits, and tier 2 would have
overruled a correct tier-1 "not landed" with a stale fact — producing a
top-ranked false `branch-already-merged` and a suggestion to close work that is
not finished. A PR merged into a different base qualified too. Addressed: tier 2
now requires `mergedAt` non-null **and** `baseRefName == default` **and**
`headRefOid == branch tip`, and abstains to `unknown` otherwise. Both cases are
named regression tests in `implement.md` step 2.

**C-20 — "do not automate the concern ledger; four of seven candidate sources
are unreliable."** The read-only inventory lane recommended dropping the parser
entirely and reporting limits instead. **Rebutted on measurement**, and it is
the one rebuttal here that could reasonably have gone the other way, so the
evidence is recorded in full in `design.md`. The parser was prototyped against
all 494 items rather than argued about: 245 distinct concerns, 206 closed, 23
open, 16 unclassifiable. Every failure mode the lane named is real and each has
a specific counter — dedupe by `(full item path, C-id)` for the "same `C-n` in
three places" problem, a continuation window for wrapped dispositions (18
unclassifiable → 1 across active items), and shape precedence (table > bold >
prose) for cross-references. The lane's must-surface case passes:
`C-19 parked [prose] archive/2026-08/2026-08-26-codex-local-review-adapter`.
What the lane was protecting against — parse one format, miss three, print a
clean banner — is designed out rather than promised against, because an
unclassifiable row is itself a finding. The residual 6.5% is accepted and
itemised, including a **sixth** disposition vocabulary (`**Confirmed,
corrected.**`) that no enumeration so far had named.

**C-21 — `.github/sd-status.json`'s `accepted_gaps[]` was being read only to
subtract findings.** The best machine-readable source in the repository — schema
-backed, each entry carrying an `until` written as an observable condition — was
feeding `load_acknowledgements` and going no further, so an accepted gap left
`protection.gaps` and reached no other section. An accepted gap is a standing
commitment with a written expiry that nothing re-reads. Addressed: the
`accepted-gap-standing` class puts each entry in the inventory with its `since`
and `until`, at rank 45 and explicitly **not** abnormal — accepting it was a
decision, and re-flagging a decision as a defect is how a banner becomes noise.

**C-22 — the checkbox filter asserts a repository convention instead of
observing one.** Scoping `- [ ]` to live items takes 1,747 boxes to 24, but the
step from "on a `done` item" to "is history" is a convention this tool would be
assuming. Addressed by stating it in the output rather than by changing it: the
`open threads` line prints both numbers and the assumption in words, so a reader
who disagrees can see the figure they would rather have. Two further findings
from the same lane are folded in without their own ids because they change no
decision: source markers are truly zero when scanned over `git ls-files` (a
plain `grep -rE` returns 4 by reaching into untracked worktrees), and open
GitHub issues and PRs are 0 and 0 — printed, because a tool that looked only at
GitHub would report an empty world and be wrong about everything.

**Lane status.** Host: completed, three rounds. `bin/sd-review --scope planning`
(Codex): completed, three rounds — one blocking finding in round 1 (C-11), two
in round 2 (C-12, C-13), two in round 3 (C-18, C-19), all addressed. The lane routes this subject to
`tier skip` for provider selection but runs the repository's own gate and the
Codex provider anyway; the findings are its verbatim output, dispositioned
locally and posted nowhere. A third independent read arrived mid-flight from the
coordinating session's read-only inventory agent and produced C-14 through C-17;
its factual claims were re-measured here before being acted on, and one (C-16)
did not reproduce.

**Round budget, and the limit it leaves.** Section 4 permits three automatic
rounds and forbids a fourth. All three have run. C-18 and C-19 were found in
round 3 and remediated afterwards, so **those two fixes carry host verification
only and no second opinion** — the same shape the interview item recorded, and a
real limit of this ledger rather than a formality. The mechanical halves of both
were re-measured rather than reasoned about: the anchor fix against the actual
corpus (15 → 28 matches), and the `merged`/`merged_at` question against the live
API. What has not been independently reviewed is whether the C-19 remediation is
*sufficient* — whether `headRefOid` plus `baseRefName` closes every way a
name-matched pull request can lie.

**Promotion is unblocked, with that caveat attached.** No concern is
`unresolved`. The one `parked` concern, C-6, is non-blocking and carries a
trigger and an owner. Every blocking concern raised in three rounds is
addressed. Implementation has not started.

## Log

- 2026-09-04 created, with `design.md` and `implement.md`: the id scheme and the
  squash-merge derivation are both choices with rejected alternatives, and the
  work lands in one file with a line ceiling, which is a step list.
- 2026-09-04 adversarial review, three rounds, two lanes. C-1, C-2, C-3, C-5,
  C-7, C-9, C-11 through C-15, C-17, C-18 and C-19 changed these artifacts;
  C-4, C-8, C-10 and C-16 were rebutted with evidence; C-6 parked. The native
  `bin/sd-review --scope planning` lane ran in all three rounds and produced
  five blocking findings, every one of them a defect the host lane had missed.
- 2026-09-04 planning complete; implementation not started. `bin/sd-status`,
  `skills/sd-status/SKILL.md` and `tests/test_sd_status.py` are untouched.
