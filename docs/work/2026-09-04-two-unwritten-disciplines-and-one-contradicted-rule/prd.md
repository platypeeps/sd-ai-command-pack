---
title: two disciplines the pack never wrote down, and one rule its newest skill contradicts
status: planning
created: 2026-09-04
branch: feat/debug-receive-and-question-form
---

# PRD — two unwritten disciplines and one contradicted rule

## Problem

A review of `github.com/obra/superpowers` named four things worth taking. One
shipped as `sd-grill`. Three did not, and the one that shipped arrived with a
defect its own first use demonstrated.

**The pack produces findings and has nothing that receives them.** `sd-review`
reviews a diff and disposes of findings locally. `sd-red-team` generates
adversarial ones. The planning contract in `.claude/sd-ai-command-pack/`
requires exactly one disposition per concern from a fixed set. Nothing states
the discipline for an author on the other end of any of it: how to tell a
finding that is right from one that is merely authoritative. `sd-feedback` is
the nearest surface and explicitly disclaims the job — its own text says do not
use it "to reply to reviewers, resolve threads, edit the reviewed artifact".
The observable failure is agreement-by-default: a reviewer's finding accepted
because a reviewer wrote it, with no evidence either way recorded.

**The pack verifies and cannot debug.** `sd-check` runs this repository's
entrypoints. `sd-review` reviews a diff. `sd-postmortem` analyses an incident
after it is over, blamelessly and for an organisation. Between a failing test
and a merged fix there is no written discipline at all, so the default holds:
edit the first plausible cause, rerun, and call a green result a fix. That
default is why a fix nobody can explain ships as often as one somebody can.

**`sd-grill` says nothing about a question form it then used exclusively.** Its
step 3 forbids supplying the expected answer inside the question and is silent
on supplying *candidates*, which leaves a reader free to decide that picking one
of three assistant-written options is stating rather than adopting. Its first
real session asked every question that way, so by its own step 7 every
load-bearing answer was contaminated — and the session still presented a
`completed` closing statement for approval, with nothing in the skill requiring
that fact to appear before the requirements being approved. The contamination
was disclosed only because the author noticed, which is not a rule.

The tempting framing is that this was inherited: `sd-socratic-review` bans
answer choices containing the expected answer, the upstream `brainstorming`
skill prefers multiple choice, and `sd-grill` draws on both. That framing is
wrong and this item does not use it. `sd-socratic-review`'s rule is narrower
than a ban and carries its own exception for a learner who asks for help, and
`sd-grill` never adopted question-form policy from `brainstorming` at all — it
took the classification, the ratchet and the gate. The sources differ in
emphasis; the ambiguity was `sd-grill`'s own.

## Requirements

1. `sd-grill` states when the assistant may author the candidate answers to a
   question and when it may not, in terms a reader can apply to one specific
   question without opening either parent skill.
2. An answer selected from an assistant-authored option set is recorded
   contaminated on the same terms as any other assistant-supplied answer. How
   certain the user was about the choice does not change where the words came
   from.
3. A `completed` session whose load-bearing answers were all obtained that way
   states it before the requirements it asks the user to approve, not in a
   footnote after them.
4. `sd-grill` records where its sources differ on question form, that the
   ambiguity was its own rather than inherited from either, and which way this
   skill settled it — so the next reader inherits the ruling instead of
   rediscovering the gap, and inherits it stated accurately.
5. A new `sd-debug` skill holds one debugging discipline: a reproduction before
   any edit, one variable per experiment, every hypothesis carrying a
   prediction that could fail, and a fix whose mechanism is stated rather than
   inferred from a green run.
6. `sd-debug` closes in one of a named closed set of states, and a session that
   never reproduced the failure cannot report a fix.
7. A new `sd-receive-review` skill gives each incoming finding exactly one
   disposition from the four the pack's planning contract already uses, and
   never marks one addressed without naming the change that addressed it.
8. `sd-receive-review` requires the reviewer's strongest reading of a finding to
   be stated before that finding is rebutted, and states that a reviewer's
   authority is not evidence.
9. Each new skill names the sibling surfaces a reader would otherwise confuse it
   with, so the seam is readable from the skill rather than from this item.
10. Neither new skill takes an outward action from inside itself: `sd-debug`
    never commits, branches, or opens a pull request, and leaves no experimental
    edit standing that it has not run against the reproduction;
    `sd-receive-review` never posts a reply, resolves a thread, or merges.
11. `sd-feedback` names `sd-receive-review` as the owner of the job it already
    disclaims, so the seam is readable from the side a reader arrives on first.

## Acceptance criteria

- [ ] `ls skills/*/SKILL.md | wc -l` prints `81` — two new skills on top of the
      79 that exist, none lost. Counted as skill *files*, not directories:
      `ls -d skills/*/ | wc -l` prints `80` today and would print `82`, but one
      of those directories is `skills/_shared/`, which holds companion
      references and is not a skill
- [ ] `python3 -m unittest tests.test_skill_frontmatter` prints `OK` with 0
      failures, so both new skills satisfy the name, title, description and
      marker contract
- [ ] `make check` prints 0 `FAILED` and its `OK` count is `40`, unchanged —
      folded skills add no test module, and none of the 40 is lost
- [ ] requirements 1 through 4 are pinned to a distinctive phrase **inside the
      section that owns them**, and exactly once. A phrase can be added
      anywhere; these fail unless it lands where the rule has effect. The text
      is flattened first because these are claims about what the file says, not
      about where its line breaks fall — a criterion that a reflow can break was
      testing the formatting. Run exactly this; every line prints `1`:
      ```
      G=skills/sd-grill/SKILL.md
      flat() { tr '\n' ' ' | tr -s ' '; }
      W=$(awk '/^## Workflow/,/^## The gate/' "$G" | flat)
      L=$(awk '/^## Lineage/,0' "$G" | flat)
      printf '%s' "$W" | grep -oiF -- 'the assistant supplies the candidates' | wc -l
      printf '%s' "$W" | grep -oiF -- 'contaminated by construction' | wc -l
      printf '%s' "$W" | grep -oiF -- 'before the requirements it asks the user to approve' | wc -l
      printf '%s' "$L" | grep -oiF -- 'the sources pull in different directions' | wc -l
      printf '%s' "$L" | grep -oiF -- "the defect was this skill's own ambiguity" | wc -l
      ```
- [ ] `sd-debug` declares its closing states and its first gate; run exactly
      this and every line prints at least `1`:
      ```
      flat() { tr '\n' ' ' | tr -s ' '; }
      D=$(flat < skills/sd-debug/SKILL.md)
      for s in '**fixed**' '**diagnosed**' '**stalled**' \
               'No edit before a reproduction'; do
        printf '%s' "$D" | grep -oiF -- "$s" | wc -l
      done
      ```
- [ ] `sd-receive-review` declares all four dispositions; run exactly this and
      every line prints at least `1`:
      ```
      flat() { tr '\n' ' ' | tr -s ' '; }
      R=$(flat < skills/sd-receive-review/SKILL.md)
      for s in '**addressed**' '**rebutted**' '**parked**' '**unresolved**'; do
        printf '%s' "$R" | grep -oiF -- "$s" | wc -l
      done
      ```
- [ ] both new skills carry the pack's section skeleton, so neither ships as
      prose with a frontmatter block. Anchored to a whole line so that prose
      *mentioning* a heading cannot satisfy it; run exactly this and all twelve
      lines print `1`:
      ```
      for f in skills/sd-debug/SKILL.md skills/sd-receive-review/SKILL.md; do
        for h in 'When to use' 'Arguments' 'Workflow' \
                 'Red flags' 'Safety rules' 'Final report'; do
          grep -cE -- "^## ${h}\$" "$f"
        done
      done
      ```
- [ ] the remaining clauses of requirements 5, 7, 8 and 10 are each pinned to
      the file that must carry them — these are claims about what the skills
      say, and a grep is decisive for them. Run exactly this; every line prints
      at least `1`:
      ```
      flat() { tr '\n' ' ' | tr -s ' '; }
      D=$(flat < skills/sd-debug/SKILL.md)
      R=$(flat < skills/sd-receive-review/SKILL.md)
      for s in 'one variable' 'a prediction that could fail' \
               'State the mechanism before claiming a fix' \
               'never commits, branches, or opens a pull request'; do
        printf '%s' "$D" | grep -oiF -- "$s" | wc -l
      done
      for s in 'naming the change that addressed it' 'strongest reading' \
               'authority is not evidence' \
               'posts no reply, resolves no thread, merges nothing'; do
        printf '%s' "$R" | grep -oiF -- "$s" | wc -l
      done
      ```
- [ ] the seams of requirement 9 are named in the skills themselves:
      `grep -cF -- 'sd-postmortem' skills/sd-debug/SKILL.md` prints at least
      `1`, and `grep -cF -- 'sd-feedback' skills/sd-receive-review/SKILL.md`
      prints at least `1`
- [ ] the reciprocal pointer of requirement 11 exists:
      `grep -cF -- 'sd-receive-review' skills/sd-feedback/SKILL.md` prints at
      least `1`
- [ ] `git diff --stat origin/main...HEAD -- bin/ dashboard/ tests/test_loc_caps.py`
      prints nothing on the pushed branch. The ceilings live in
      `tests/test_loc_caps.py`, *outside* the `bin/` and `dashboard/` pathspec,
      so a pathspec covering only those two would pass while a ceiling was
      quietly raised — the file that defines the limit has to be in the diff
      that proves the limit held. `bin/` measured 12,416 lines against the
      14,000 ceiling on `main`; this item spends none of that 1,584
- [ ] the two new skills are *additions*, proven by path identity rather than by
      a count — deleting one folded skill and adding three also yields 81. Run
      exactly this; the first prints the two names and nothing else, the second
      prints nothing:
      ```
      git diff --no-renames --name-status origin/main...HEAD -- skills/ \
        | awk '$1=="A"{print $2}'
      git diff --no-renames --name-status origin/main...HEAD -- skills/ tests/ \
        | awk '$1=="D"'
      ```
      `--no-renames` is load-bearing: without it git reports a sufficiently
      similar delete/add pair as `R`, which neither `A` nor `D` matches, so an
      existing skill could be renamed away while both commands still printed
      their expected output.
      Expected additions, exactly: `skills/sd-debug/SKILL.md` and
      `skills/sd-receive-review/SKILL.md`
- [ ] `python3 -m unittest tests.test_skill_companions tests.test_doc_citations`
      prints `OK`, so each cited shared reference ships with the skill citing it
      and no citation in this item's prose trips the adjacency rule

### What these criteria do not cover

The greps above are decisive for *presence*: a required rule is in the file, in
the section that owns it, and the section headings are real headings rather than
prose mentioning them. They are **not** decisive for the *relationships* several
requirements assert, and this item does not claim they are:

- requirement 6's "a session that never reproduced cannot report a fix" is a
  dependency between two states, not a token;
- requirement 7's "exactly one disposition per finding" is a cardinality
  constraint that no substring proves;
- requirement 8's "strongest reading *before* the rebuttal" is an ordering;
- requirement 10's "no experimental edit left standing that has not been run
  against the reproduction" is a postcondition.

Each of those is present in the file and reader-verified, and a substring check
can be satisfied by text that negates the rule as easily as by text that states
it. Where the phrase was cheap to harden it was hardened — the mechanism check
pins the whole imperative clause rather than three words that a `Never` in front
would also match — but hardening a substring is not the same as testing a
relationship, and calling it one would be the defect this pack keeps finding.

What none of it reaches at all is **conduct**: whether an agent holding
`sd-debug` actually reproduces before editing, or whether one holding
`sd-receive-review` actually rebuts a wrong finding instead of agreeing with it.
A rule can be present, greppable, correctly worded, and ignored.

This repository has no conduct harness. The successor item that would have
built one was abandoned on 2026-09-04, after `claude plugin eval` turned out to
implement it already and to be gated behind early access on this account. So
the behavioural halves of requirements 5 through 8, and the postcondition in
requirement 10, ship unverified in exactly the way `sd-grill`'s requirements 1
and 4 did, and C-11 on that item stays parked with two more skills standing
behind it rather than one.

## Review

Two lanes ran: the host's own, and the repository's native Codex lane
(`codex exec --sandbox read-only --ephemeral`). Both were available and both
completed. Round 1 of each ran against the three planning artifacts; a
remediation round followed and a second Codex round is recorded below.

| ID | Lane | Severity | Blocks | Disposition |
|---|---|---|---|---|
| C-1 | codex | high | yes | addressed |
| C-2 | codex | high | yes | addressed |
| C-3 | codex | high | yes | addressed |
| C-4 | codex | high | yes | addressed |
| C-5 | codex + host | high | yes | addressed |
| C-6 | codex | medium | yes | addressed |
| C-7 | codex | medium | yes | addressed |
| C-8 | codex | medium | yes | addressed |
| C-9 | codex | low | no | addressed |
| C-10 | host | medium | yes | addressed |
| C-11 | host | high | yes | addressed |
| C-12 | host | high | yes | addressed |
| C-13 | host | low | no | addressed |
| C-14 | host | low | no | rebutted |
| C-15 | host | medium | yes | addressed |

**C-1 — the new `sd-grill` rule contradicted both sentences it was layered onto.**
Step 3 still forbade supplying the expected answer without qualification while
the new form rule permitted assistant-authored candidates, so an option set was
both permitted and forbidden; step 7 classified every assistant-supplied adopted
answer as contaminated while the new rule called a transcribed set ordinary, so
a transcribed selection was both. Addressed in `skills/sd-grill/SKILL.md`: step
3 now forbids steering toward the expected answer and defers the question of
whether candidates may be offered at all to the form rule, which is named as
governing; step 7 gained an explicit narrow exception for transcribed
candidates, with the boundary stated — if the assistant chose which subset of a
real set to show, it authored the set.

**C-2 — the content greps were spoofable and unanchored where they need not
have been.** `grep -cF '## Workflow'` matched prose mentioning the heading, not
only a heading, and `state the mechanism` was satisfied by text negating the
rule. Addressed: the skeleton check is now `grep -cE "^## <heading>$"`, anchored
to a whole line, and the mechanism check pins the full imperative clause
`State the mechanism before claiming a fix`.

**C-3 — the item claimed the greps were decisive for every file-content
requirement, and they are not.** Requirement 6 asserts a dependency between two
states, 7 a cardinality constraint, 8 an ordering, and 10 a postcondition; no
substring proves any of them, and a check can be satisfied by text that negates
the rule. Addressed by narrowing the claim rather than by inventing a check:
the "What these criteria do not cover" section now names all four relationships
explicitly, says a hardened substring is still not a relationship test, and
separates that from the conduct gap. The alternative — asserting decisiveness
the checks do not have — is the exact defect this repository keeps finding.

**C-4 — the budget criterion could not prove the ceiling did not move.** It
diffed `bin/` and `dashboard/`, but the ceilings are defined in
`tests/test_loc_caps.py`, outside that pathspec, so raising a ceiling produced
no diff and passed. Addressed: the pathspec now includes
`tests/test_loc_caps.py`, and the criterion says why the file defining the limit
has to be in the diff that proves the limit held.

**C-5 — `implement.md` had drifted from the PRD's verification suite.** It
asserted the superseded directory count and described "the three `grep -cF`
loops" after the PRD had moved to flattened occurrence-counting groups plus
separate seam, pointer and path-identity commands, so following it would have
skipped most content checks. Found independently by both lanes — the host lane
caught the count during the cross-artifact sweep, the Codex lane caught the
count and the stale loop description together. Addressed: the Verification
section now enumerates every command block the PRD actually contains.

**C-6 — cardinality does not preserve identity.** Deleting one folded skill and
adding three also yields 81, and replacing a test module preserves 40 `OK`
lines, so the counts could pass over a silent deletion. Addressed: a path
identity criterion was added, asserting from `git diff --name-status` that the
additions are exactly the two named files and that nothing under `skills/` or
`tests/` was deleted.

**C-7 — the claimed contradiction between the skill's two parents was
overstated.** `sd-socratic-review` does not categorically ban answer choices —
it avoids choices that contain the expected answer, and carries an exception for
a learner who asks for help — and `sd-grill` never adopted question-form policy
from `brainstorming` at all; its Lineage says it took the classification, the
ratchet and the gate. The real defect was `sd-grill`'s own silence about
candidate answers. Addressed in three places: the Problem statement now names
and rejects the inherited-conflict framing, requirement 4 asks Lineage to record
that the ambiguity was the skill's own, and the Lineage paragraph was rewritten
to say what the sources actually say. The References bullet asserting
`brainstorming` as one of two reconciled parents was corrected in the same pass,
having been left stale by the first two edits.

**C-8 — material routing seams were missing from both new skills.** `sd-retro`
accepts completed software-delivery debugging streams, so `sd-debug` needed the
active-investigation versus finished-stream seam; `sd-review` already disposes
of findings locally and `sd-ship` owns the live pull-request lifecycle, so
naming only `sd-feedback` left the two nearest neighbours unaddressed. Addressed
in both skills, each stating the seam rather than only the name.

**C-9 — requirement attribution in the References section was wrong.** The
`sd-feedback` bullet credited requirement 9 with making the seam readable from
both sides; requirement 9 supplies the new skill's routing and requirement 11
the reciprocal pointer. Addressed: the bullet now cites both.

**C-10 — the skill-count criterion counted a directory that is not a skill.**
`ls -d skills/*/ | wc -l` includes `skills/_shared/`, which holds companion
references. Addressed: the criterion counts `skills/*/SKILL.md` and asserts 81,
and states why the file count is the right measure.

**C-11 — four requirements had no acceptance criterion.** Requirement 5's
one-variable, falsifying-prediction and stated-mechanism clauses, requirement
7's naming rule, requirement 8 entirely, and requirement 10 were all filed under
"reader-verified" when each is a claim about what a file says. Addressed: a
criterion covering all four was added. This is the same defect as C-1 on the
`sd-grill` item, found again one item later.

**C-12 — three pinned phrases could not match, and one had a case mismatch.**
The criteria used line-based `grep -cF` while three of the phrases wrapped
across lines in the skill text, and `state the mechanism` did not match
`State the mechanism`. Run as written against a correct file they returned `0`.
Addressed by fixing the check rather than the prose: the text is flattened with
`tr` before matching, the match is case-insensitive, and occurrences are counted
with `grep -oiF | wc -l`. A criterion a reflow can break was testing the
formatting, not the content.

**C-13 — the item added two more undeclared uses of `bounds=`.** Four skills now
use it — `sd-socratic-review`, `sd-grill`, and both new ones — and it was absent
from `skills/_shared/references/argument-vocabulary.md`, whose stated purpose is
that a name learned on one skill transfers to the next. Addressed by reserving
it in that reference with its concept and its boundary against `scope=`, rather
than by adding two more violations to an existing two.

**C-14 — `repro=` in `sd-debug` is a skill-owned argument outside the shared
vocabulary, the same class as the parked C-7 on the `sd-grill` item.**
Rebutted, on the reference's own text: "Skill-owned argument names outside this
list keep their own per-skill meaning; this reference governs the shared
vocabulary, not every private argument." One user is not a shared concept.
`bounds=` was promoted under C-13 because four skills use it for one concept;
`repro=` has one user and stays skill-owned. The distinction is the number of
users, and it is recorded here so the next author has the rule rather than the
precedent.

**C-15 — the remediation introduced two cross-artifact drifts of its own.**
Correcting C-3 named requirement 10 as unreachable by grep while two other
passages still scoped the conduct gap to "requirements 5 through 8", and
correcting C-7 left the References bullet asserting the two-parents framing that
correction had just removed. Both found by the round-2 cross-artifact sweep and
addressed. Recorded rather than folded silently into C-3 and C-7, because the
contract's warning that a remediation round finds defects its own fixes
introduced is the thing this entry is evidence for.

**C-16 — a transcribed option set could launder assistant authorship.** The
step-7 exception cleared any set "transcribed from something that exists". An
assistant that wrote an option list into an artifact one turn, then transcribed
the *complete* list the next, satisfied the exception while the words stayed the
assistant's; the subset clause only caught partial reads. Addressed: the
exception now requires a set that exists **independently of the assistant**, and
names the laundering path explicitly — a set the assistant itself wrote earlier
carries its contamination through the artifact rather than being cleared by it.
The test given is whether the set would exist had the assistant never written
anything.

**C-17 — "the user asked for options" and "never first" could not both hold.**
Step 3 permitted an assistant-authored closed question when the user asked to be
given options, then said such a question is never the form a question takes
first, leaving a request for options before question one with two valid
readings. Found independently by the Codex lane and by the pull request's
automated reviewer, which is the strongest evidence in this ledger that it was a
real ambiguity rather than a lane's preference. Addressed: the rule now bans it
as the *assistant's own* opening move and states the two places it is permitted,
noting that when the user asked, the user's request is the move that preceded
it — so it may be the assistant's first question.

**C-18 — `sd-debug` defined the mechanism of the bug, not of the fix.**
Requirement 5 wants a fix whose mechanism is stated, but step 10 asked only for
"a causal chain from cause to symptom", which explains why the bug happened and
says nothing about why the edit stops it. The pinned phrase grep passed over
exactly this gap. Addressed: the mechanism is now two links — cause to symptom,
*and* where in that chain the edit cuts — with the skill saying plainly that the
second is the one that gets skipped, and `fixed` requiring both.

**C-19 — a bound-triggered stop had two incompatible closing states.** The
safety rule sent every bound-triggered stop to `stalled` while the workflow
defined `stalled` as no reproduction or no surviving hypothesis, so a bound that
landed after the cause was established forced a report that discarded it. Raised
by the automated reviewer on the pull request and, from the other direction, by
the Codex lane's reading of the `sd-retro` seam. Addressed: a bound now closes
the session at whatever was actually established and never above it —
`diagnosed` with a cause, `stalled` without, never `fixed`, because `fixed`
needs the reproduction rerun the bound stopped short of.

**C-20 — the `sd-retro` seam excluded the sessions most worth retrospecting.**
"When to use" said this skill stops when the cause is found, which hands
`sd-retro` only the successful sessions and leaves a `stalled` one with no
onward path. Addressed: the seam is now stated on session closure — this skill
hands over when the investigation closes in **any** of its three states,
`stalled` included.

**C-21 — the `sd-review` seam put two different meanings on one field name.**
`bin/sd-review` already writes `disposition` with the values
`blocking|advisory`, a severity gate on the merge; `sd-receive-review` requires
exactly one of four dispositions, a response to the claim. The seam named no
normalization, so consuming that output would either overwrite the merge gate or
leave two fields called the same thing. Addressed: the seam paragraph now states
that the two are different fields, that the lane's value is carried through
unchanged under its own name, and that collapsing them loses the merge gate.

**C-22 — `depth=brief` and the final-report contract disagreed about the
steelman.** `brief` was defined as reporting the ledger "without the steelman
text" while the workflow forbids `rebutted` without one and the final report
requires it for every rebutted finding, with no precedence rule. Addressed:
`brief` now shortens the report and not the work — the steelman is constructed
for every finding and printed for every `rebutted` one, and what `brief` drops
is the steelman text for findings disposed some other way.

**C-23 — the path-identity criterion was blind to renames.** It filtered `A` and
`D` only, and git reports a sufficiently similar delete/add pair as `R`, so an
existing skill or test could be renamed away while both commands printed exactly
what the criterion expected and the count still read 81. Addressed with
`--no-renames` on both commands and a sentence saying why it is load-bearing.
This is the second defect in this one criterion — C-6 added it because
cardinality does not preserve identity, and C-23 is the discovery that the
identity check had its own blind spot.

**C-24 — `implement.md` never converged with the round-1 remediations.** Every
one of the five: it still called the source relationship a "parents'
disagreement" after C-7 removed that framing, omitted `sd-retro`, `sd-review`
and `sd-ship` from the seam list after C-8 added them, omitted the
shared-vocabulary edit entirely after C-13 made it a deliverable, used the
pre-C-4 budget pathspec, and still scoped the conduct gap to requirements 5
through 8 after C-3 and C-15 widened it to include 10. C-5 and C-15 both claim
`addressed` for parts of this and both were wrong about it — the PRD and
`design.md` were swept, `implement.md` was not. Addressed by rewriting the
affected passages, and recorded as its own entry rather than folded into C-5,
because "the sweep missed an artifact" is a different failure from "an artifact
drifted".

**C-25 — the `bounds=` reservation had no owned implementation step.**
`references/argument-vocabulary.md` is fanned into every citing skill by
`bin/sd_install.py`, so reserving a name there rewrites the companion shipped
with 56 skills across two directory layouts, and `implement.md` listed no step
that owned the change or audited its consumers. `tests.test_skill_companions`
proves the copy happened, not that the new definition fits what the citers mean.
Addressed: `implement.md` gains Step 4 naming the source edit, the fan-out, and
the consumer audit. The audit's result is unchanged — all four literal `bounds=`
uses match the reserved definition — but it is now a step that was run rather
than a fact asserted.

### Conclusion

Twenty-four concerns addressed, one rebutted with evidence, none parked, none
unresolved. No blocking concern remains open.

Ten of those twenty-four came from the second Codex round and the pull request's
automated reviewer, after the first conclusion in this section declared the item
unblocked. That conclusion was wrong when written: it was recorded before the
round it claimed to have cleared had returned. Two of the ten — the
options-first contradiction and the bound-triggered closing state — were found
by both lanes independently.

The item ships with one gap declared rather than closed, and it is the same gap
as before: nothing here tests conduct. That is C-11 on the `sd-grill` item, and
this item widens it from one skill to three. It is not resolved by anything
above and is not claimed to be.

## References

- `docs/work/2026-09-04-the-plan-interview-is-one-sentence/prd.md` — the
  `sd-grill` item whose first real use produced the defect requirements 1
  through 4 fix, and whose C-11 this item widens rather than closes.
- `github.com/obra/superpowers`, MIT, revision
  `b36e0829c6d0140e93cfef2ca599b1b07d4a7797` — `systematic-debugging` is the
  source of requirements 5 and 6, and `receiving-code-review` of 7 and 8.
  `brainstorming` is cited by requirement 4 only to be set aside: `sd-grill`
  took its classification, ratchet and gate, never its question-form policy,
  and saying otherwise was the error C-7 corrected.
- `skills/sd-feedback/SKILL.md` — the surface that disclaims the
  `sd-receive-review` job in its own "Do not use" list. Requirement 9 makes the
  seam readable from the new skill's side and requirement 11 supplies the
  reciprocal pointer; it takes both, not requirement 9 alone.

## Log

- 2026-09-04 created. Scope set by the user after the abandoned harness item:
  resolve the open `sd-grill` defect, then design and implement `sd-debug` and
  `sd-receive-review`.
