---
title: the pack has no answer to "write the test first", and one skill contradicts it
status: in_progress
branch: feat/sd-tdd-test-first
created: 2026-09-05
---

# PRD — the pack has no answer to write the test first

## Problem

The pack has 81 skills. None of them says how to write a test.

This is not a judgement about coverage; it is a grep. Measured on `main` at
`53da3689`, before this item: across every file under `skills/` — not only
`SKILL.md`, and including `_shared/references/` —
`grep -rlni 'test-driven\|test.first\|red.green\|failing test first'` returns
nothing. Stated as a measurement with its commit rather than in the present
tense, because after this item lands the same grep matches `sd-tdd`, and a
present-tense claim would then read as false.

The pack has a debugging discipline (`sd-debug`), a review-receiving
discipline (`sd-receive-review`), an interrogation discipline (`sd-grill`), a
shipping discipline (`sd-ship`), and a runner that executes whatever test
entrypoint a repository already has (`sd-check`). Between "this feature does not
exist" and "the suite is green" there is nothing written down.

The observable failure is the one every acceptance criterion in this repository
is designed to catch and none of them can: **a test written after the code
passes on its first run, which proves only that it agrees with what was
written.** It may test the implementation rather than the behaviour, it may miss
the case the author forgot, and nobody can tell, because it was never seen to
fail. `sd-debug` requires rerunning the reproduction after a fix, which proves
the symptom is gone; it does not require proving the new test would have caught
the bug.

**A second gap sits underneath the first, and this item does not close it.**
`sd-typed-holes` tells a Rust author to land a compiling skeleton whose bodies
are `todo!()` **as its own commit**, before any behaviour exists. Test-first
says no production code without a failing test. Read together, a Rust author
has two skills giving what look like opposite instructions, and the pack says
nothing about which governs.

The item tried three times to settle it and failed review three times. The
boundary is not where it first appears: `sd-typed-holes` step 2 also lands
derives, conversion impls and trivial accessors *implemented rather than held
open*, so the skeleton is not behaviour-free and every rule drawn at the commit
exempted real bodies. That finding is now recorded in `sd-typed-holes`' own
`## Lineage`, along with the fact that its upstream is a two-layer practice
whose second layer — golden tests written from the spec so they fail on arrival
— this pack never carried over. What reads as a skill opposing test-first is a
skill missing the half that supplied it. Naming the question accurately is what
this item delivers; answering it is not.

**Scope note.** This item adds the discipline and nothing adjacent to it. It
does not add a conduct harness, and cannot: the same gap C-11 named on the
`sd-grill` item applies here and is widened again, which is stated in
`### What these criteria do not cover` rather than papered over. It also does
not settle three adjacent questions. Requirement 8 covers two of them in
`sd-tdd` — how a test bootstraps against code that does not exist yet, and
whether evidence for a late test can be recovered by reverting. The third, the
`sd-typed-holes` boundary described above, belongs to requirement 9 and is
recorded in that skill's own `## Lineage`. All three were answered wrongly at
least twice; each is now recorded as open where a reader will meet it. The scope
this PRD describes is the second one, cut after three review rounds produced
twenty-three findings of which fourteen belonged to three additions that are
no longer here.

## Requirements

1. A new `sd-tdd` skill states the test-first discipline as a gate: no
   production code without a test that was **seen to fail against a tree
   lacking the behaviour**, and a test that has only ever been seen to pass is
   not evidence. The gate is stated on the observed failure rather than on
   authorship order, because which file was typed first is not recoverable from
   the tree an hour later and a watched failure is — the same reasoning that
   made `sd-grill` split its question forms on who authored the candidates
   rather than on what answer was expected. Writing the test first is the only
   route the skill offers to that evidence.
2. `sd-tdd` names what "seen to fail" requires — that the failure is the
   expected one, distinguishing a test that fails because the behaviour is
   missing from one that fails because of a typo, a stale import, or a
   collapsed fixture — and requires the message be quoted with a statement of
   why it is the behaviour being absent.
3. `sd-tdd` never instructs an agent to delete a user's work on its own
   authority. Where the upstream source says code written before its test must
   be deleted and rewritten, this skill proposes that, names what would be
   lost, and **waits for consent**, because an agent that deletes uncommitted
   work because a skill told it to is a worse failure than a test written in
   the wrong order.
4. `sd-tdd` closes in one of a named closed set of **exactly three** states,
   decided by counting rather than by judgement so that exactly one always
   fits. Each production change is sorted **proven** — valid red for it was
   observed against a tree that did not yet contain it — or **unproven**; all
   proven is `disciplined`, some but not all is `partial`, none is
   `abandoned`. The classifier is when valid red was *observed* relative to the
   change, not when the test was authored, since authorship admits a test
   written and never run. `proven` requires **both** halves of the cycle to
   have been observed — the red against a tree lacking the change, and the
   change then passing with the suite green — because a bound that fires
   between them leaves real untested production code in the tree, and a
   classifier keyed on the red step alone would close that session
   `disciplined`. **A session with no production changes closes
   `disciplined`**, and the skill says so in those words: with no changes both
   outer predicates are vacuously true, so a requirement that merely demanded a
   tie-break without naming its result would leave the same ambiguity it exists
   to remove.
5. `sd-tdd` bounds what running a suite may reach — no production credentials,
   live endpoints, shared state, or fixtures that send mail or move money —
   since preferring real code over mocks is a statement about the code under
   test, not a licence to reach production.
6. `sd-tdd` names the sibling surfaces a reader would otherwise confuse it with,
   and each of `sd-debug`, `sd-check`, `sd-review` and `sd-typed-holes` is named.
7. `sd-tdd` records its lineage — the upstream source, its licence, and the
   revision — and says what it took and what it deliberately did not.
8. `sd-tdd` states what it does **not** settle, rather than settling it wrongly.
   Two adjacent questions — bootstrapping a test for code that does not exist
   yet, and recovering evidence for a test written late — were each answered
   twice and failed review both times. The skill names them, says what was
   tried and why it failed. Where an open question would otherwise require
   writing production code before valid red, the skill does **not** authorise
   the reader to resolve it alone: an open section cannot issue an instruction
   that contradicts a gate the skill still enforces, so it says to stop and ask
   the user, and the outcome is reported.
9. `sd-typed-holes` carries a `## Lineage` section recording its own
   provenance: the upstream it was re-authored from, that upstream's licence
   status, the revision, and the two hops by which it reached this pack. It
   also names the unsettled boundary with `sd-tdd` rather than asserting one.

## Acceptance criteria

**Preconditions, because otherwise these commands read two different trees.**
The path and budget checks below inspect `origin/main...HEAD` while every
`grep`, `ls` and unittest inspects the worktree. Run the whole set only on the
pushed branch with `git status --porcelain` printing **nothing**; otherwise a
deficient commit can pass the branch checks while an uncommitted repair passes
the content checks.

- [ ] the worktree is clean and pushed: `git status --porcelain` prints nothing
      and `git rev-parse HEAD origin/<branch>` prints the same sha twice
- [ ] `sd-tdd` exists and the frontmatter contract holds:
      `python3 -m unittest tests.test_skill_frontmatter` prints `OK`
- [ ] `ls skills/*/SKILL.md | wc -l` prints `82`. Counted as skill *files*,
      because `ls -d skills/*/` also counts `skills/_shared/`, which is
      companion references and not a skill
- [ ] the new skill is an *addition*, proven by path identity rather than by a
      count — deleting one folded skill and adding two also yields 82. Run
      exactly this; the first prints the one name and nothing else, the second
      prints nothing:
      ```
      git diff --no-renames --name-status origin/main...HEAD -- skills/ \
        | awk '$1=="A"{print $2}'
      git diff --no-renames --name-status origin/main...HEAD -- skills/ tests/ \
        | awk '$1=="D"'
      ```
      Expected addition, exactly: `skills/sd-tdd/SKILL.md`.
      `--no-renames` is load-bearing: without it git reports a sufficiently
      similar delete/add pair as `R`, which neither `A` nor `D` matches
- [ ] **exactly two skill files change**, which the addition check alone does
      not show. The scope cut means `sd-debug` must be untouched; run exactly
      this and it prints two paths, `skills/sd-tdd/SKILL.md` and
      `skills/sd-typed-holes/SKILL.md`, and nothing else:
      ```
      git diff --name-only origin/main...HEAD -- skills/
      ```
- [ ] `sd-tdd` carries the pack's section skeleton, anchored to whole lines so
      that prose *mentioning* a heading cannot satisfy it; run exactly this and
      all seven lines print `1`. A second match — a real heading plus one
      inside a fenced example — prints `2` and fails:
      ```
      for h in 'When to use' 'Arguments' 'The gate' 'Workflow' \
               'Red flags' 'Safety rules' 'Final report'; do
        grep -cE -- "^## ${h}$" skills/sd-tdd/SKILL.md
      done
      ```
- [ ] requirements 1 through 5 and 8 are each pinned to a phrase in the file.
      Flattened because these phrases wrap across lines and `grep` is
      line-based; fixed-string and case-insensitive because a case mismatch is
      not a content defect. Run exactly this; every line prints at least `1`:
      ```
      flat() { tr '\n' ' ' | tr -s ' '; }
      T=$(flat < skills/sd-tdd/SKILL.md)
      for s in 'seen to fail' 'passes on its first run' \
               'the failure is the expected one' \
               'never deletes' 'waits for consent' \
               'exactly three' 'proven' 'unproven' \
               'closes `disciplined`' \
               'production credentials' \
               'does not settle'; do
        printf '%s' "$T" | grep -oiF -- "$s" | wc -l
      done
      ```
- [ ] requirement 8's section exists as a heading, not only as prose:
      `grep -cE -- '^## What this skill does not settle$' skills/sd-tdd/SKILL.md`
      prints `1`
- [ ] the seams of requirement 6 are named in the skill itself; run exactly
      this and all four lines print at least `1`:
      ```
      for s in sd-debug sd-check sd-review sd-typed-holes; do
        grep -cF -- "$s" skills/sd-tdd/SKILL.md
      done
      ```
- [ ] requirement 7's lineage is present and actually cites licence and
      revision. Flattened, because no single line-based grep can check three
      tokens that wrap; the heading prints `1` and all three needles print at
      least `1`:
      ```
      grep -cE -- '^## Lineage$' skills/sd-tdd/SKILL.md
      flat() { tr '\n' ' ' | tr -s ' '; }
      L=$(flat < skills/sd-tdd/SKILL.md)
      for s in 'obra/superpowers' 'MIT' 'b36e082'; do
        printf '%s' "$L" | grep -oF -- "$s" | wc -l
      done
      ```
- [ ] requirement 9's lineage exists and names its own upstream, that
      upstream's licence status, and the revision:
      `grep -cE -- '^## Lineage$' skills/sd-typed-holes/SKILL.md` prints `1`,
      and run exactly this, all three printing at least `1`:
      ```
      flat() { tr '\n' ' ' | tr -s ' '; }
      H=$(flat < skills/sd-typed-holes/SKILL.md)
      for s in 'Shearerbeard/claude-skills' 'c79fe3a' 'no licence file'; do
        printf '%s' "$H" | grep -oiF -- "$s" | wc -l
      done
      ```
- [ ] `python3 -m unittest tests.test_skill_companions tests.test_doc_citations`
      prints `OK`, so each cited shared reference ships with the skill citing it
      and no citation in this item's prose trips the adjacency rule
- [ ] `make check` ends with `0` `FAILED` and `40` `OK`
- [ ] `git diff --stat origin/main...HEAD -- bin/ dashboard/ tests/test_loc_caps.py`
      prints nothing on the pushed branch. The ceilings live in
      `tests/test_loc_caps.py`, *outside* the `bin/` and `dashboard/` pathspec,
      so a pathspec covering only those two would pass while a ceiling was
      quietly raised

### What these criteria do not cover

Every criterion above is a claim about what a file *says*. None is a claim
about what an agent holding the skill *does*, and several requirements have a
behavioural half that no grep reaches:

- requirement 1's "seen to fail against a tree lacking the behaviour" is a
  claim about what a past run did and what the tree looked like when it did it;
- requirement 2's "the failure is the expected one" is a judgement about a
  message — and one this item twice failed to reduce to a rule;
- requirement 3's consent rule is a thing that must happen before an action,
  not a sentence in a file;
- requirement 4's counting rule is a classification made during a session, and
  a grep cannot tell a correct sort from an incorrect one;
- requirement 8's honesty is the hardest of all: a section admitting two open
  questions is worth nothing if the agent reads past it.

Each is present in the file and reader-verified. A substring check can be
satisfied by text that negates a rule as easily as by text that states it — a
file saying "deletion needs no consent" passes every phrase count above. So
does a file whose seven headings all sit inside a fenced example and none of
which is real.

These are not oversights to be patched with more needles. Every one is the same
limit — grep sees tokens, not claims — and adding needles moves the boundary
without removing it. They are listed so a reader knows the criteria are a
floor, and that the review lanes, not the greps, are what checked the content.

This repository has no conduct harness. The successor item that would have
built one was abandoned on 2026-09-04, after `claude plugin eval` turned out to
implement it and to be gated behind early access on this account. So the
behavioural halves above ship unverified in the same way `sd-grill`'s and
`sd-debug`'s did, and **C-11 on the `sd-grill` item stays parked with a fourth
skill standing behind it**.

## References

- `github.com/obra/superpowers`, MIT, revision
  `b36e0829c6d0140e93cfef2ca599b1b07d4a7797` — its `test-driven-development`
  skill is the source of requirements 1 and 2 and of the rationalization
  table's form. Requirement 3 is where this pack **departs** from it: upstream
  says code written before its test must be deleted, with "delete means delete"
  and no consent step, which is an instruction an agent can execute against
  uncommitted work.
- `github.com/Shearerbeard/claude-skills`, `plugins/rust/skills/typed-holes`,
  revision `c79fe3a` — what `sd-typed-holes` was re-authored from, recovered
  for requirement 9. **No licence file**: `LICENSE`, `LICENSE.md`,
  `LICENSE.txt` and `COPYING` are all absent, so its terms are unstated rather
  than permissive. Upstream is a *two-layer* practice whose layer 2 — golden
  tests written from the spec "so they fail on arrival" — this pack did not
  carry over.
- `skills/sd-typed-holes/SKILL.md` — reached this pack in `56ba92eb`
  (2026-08-31, #640) from `se-ai-command-pack`, where it was written as
  `se-typed-holes` in `9de85c3` (2026-08-27).
- `docs/work/2026-09-04-two-unwritten-disciplines-and-one-contradicted-rule/prd.md`
  — the immediately prior adoption from the same upstream, and the source of
  the acceptance-criteria shapes reused above: flattened fixed-string greps,
  `--no-renames` path identity, and the budget pathspec that includes the file
  defining the ceiling.

## Review

Host lane, then the native Codex lane (`--cd <root> --sandbox read-only
--ephemeral`). Round 1 returned eight blocking concerns and two non-blocking.
All ten are dispositioned below; each carries exactly one disposition.

**C-1 — acceptance mixed committed and worktree state. `addressed`.**
The path and budget checks read `origin/main...HEAD` while every content check
read the worktree, so a deficient commit could pass the first while an
uncommitted repair passed the second. The lane demonstrated it live: content
greps passed against uncommitted `sd-tdd` while the addition command printed
nothing. Two preconditions now head the criteria — clean `git status
--porcelain` and `HEAD` equal to the pushed branch.

**C-2 — predicates could pass while the requirement was false. `addressed`.**
Three requirements (2, 5, and the later 11) had no pinned phrase at all;
needles added, plus `exactly three` to pin requirement 6's closed set against a
silent fourth state. `## The gate` added to the heading loop. The lineage
criterion asked for a single grep "on a line that also names the licence and
the revision", which no line-based grep can do and which the file did not
satisfy — the revision had wrapped; it is flattened now and checks
`obra/superpowers`, `MIT` and `b36e082` separately.

One sub-example was wrong: the lane said six headings inside a fenced block
"still produce six `1`s". A fenced duplicate alongside a real heading prints
`2`, and the criterion demands `1`, so that case fails rather than passes. The
reachable version — all seven headings *only* inside a fence — is real, and is
now conceded in `### What these criteria do not cover` along with the negation
and reciprocal-agreement gaps, which more needles cannot close.

**C-3 — D1 replaced test-first with verified sensitivity, then called the
evidence identical. `addressed`.** The strongest finding of the round, and the
claim was simply false. Reverting proves the test is *sensitive* to the
behaviour; it does not undo the implementation having chosen which cases were
considered. Upstream names the mechanism — "you verify the cases you
remembered, not the ones you'd have discovered". Both routes stay open, per
D1's original reason, and they now close differently: test-before-code closes
`disciplined`, a recovered late test closes `partial` with the recovered
behaviours named. The gate, D1, D6, requirements 1 and 6, the closing states
and one red-flag row all moved together.

**C-4 — new modules and symbols deadlocked before valid red. `addressed`.**
A test importing a module that does not exist fails with an import error, which
requirement 2 rejects; creating the module is production code requirement 1
forbids. Only Rust had an exception. New requirement 10 and a "bootstrap
carve-out" paragraph in the gate: the smallest surface that turns an import
error into an assertion failure is not the behaviour, stated for every
language rather than one.

**C-5 — the typed-holes seam exempted actual behaviour. `addressed`.**
The seam was drawn at the *commit*, and that commit lands derives, `From`/`Into`
impls, and trivial accessors implemented rather than held open. A getter
returning the wrong same-typed field compiles, passes clippy, and was exempt.
`sd-typed-holes`' own safety rules already conceded that derives and runtime
semantics need tests. The seam now divides contents, not commits, in D4 and in
both skill files.

**C-6 — revert/restore had uncontained destructive authority. `addressed`.**
The skill ordered reverts while forbidding commits and branches, so it held no
recovery mechanism, and then claimed this happened "without deleting anything".
New requirement 11 and a safety rule: committed or explicitly saved before any
revert, refuse where unrelated dirty edits prevent isolation, restoration
verified rather than intended. D3's "only construction" claim was also false —
an ordinary red-green cycle on the bug produces the same evidence with no
revert — and is corrected.

**C-7 — the initial-pass branch had no truthful closing state. `addressed`.**
The workflow told an agent to stop when the first test passes and left it
nowhere to record the result: `partial` needs mixed compliance, `abandoned`
says the discipline was not followed, `disciplined` needs a failure that cannot
exist. Resolved without a fourth state, since no production code is written for
such a behaviour: a **Behaviours already present** report line that needs no
quoted failure and counts neither way.

**C-8 — running "real code" and the suite had no outward-effect boundary.
`addressed`.** The safety rules bounded git and said nothing about production
credentials, live endpoints, shared databases, or fixtures that send mail or
move money. A rule now bounds what a suite may reach, and marks "prefer real
code over mocks" as a statement about the code under test rather than a licence
to reach production.

**C-9 — wrong upstream provenance for the "tired" row. `addressed`.**
Verified: absent from `test-driven-development/SKILL.md`, present at
`verification-before-completion/SKILL.md:70`. The design's point about
admonitory rows survives; the attribution is corrected in place.

**C-10 — the design misstated its own footprint. `addressed`.**
"Four surfaces" enumerated three files, and the "one-line" reciprocal edits
were seven added lines in `sd-debug` and fifty-four in `sd-typed-holes`, the
latter carrying a `## Lineage` section as well as the seam. Corrected to three
files with those counts named. This entry first said "seven added lines each",
repeating in the ledger the arithmetic error it was recording.

### Round 2

Run against the clean pushed snapshot `41cda029`, so these findings are about
the tree as shipped, not a tree moving underneath the lane. Five blocking, one
non-blocking. The important result is not the count: **three round-1
dispositions were disproved and one was incomplete.** Every one of them failed
the same way — the round-1 fix corrected the sentence describing a rule and
left the procedure that executes it untouched. C-4, C-5 and C-6 were recorded
`addressed` above; those three words were wrong when written, and are left
standing with this section as their correction rather than edited out.

**C-11 — the C-3 two-route change did not reach every consumer. `addressed`.**
Step 9 and requirement 3 were updated to offer both routes; four other places
still assumed the four-step one. The Final report demanded "the four steps of
step 9" for every bug fix, so a valid pre-fix cycle had no truthful line. The
`### What these criteria do not cover` bullet still called requirement 3 a
four-step procedure. `sd-debug`'s handoff fired *after* the fix and mandated
revert/restore, contradicting the PRD's claim that the handoff supplies the
pre-fix route. And a red-flag row said an unproven regression test "guards
nothing" — an overclaim the workflow itself avoids, since not-known-to-guard is
the weaker true statement. All four corrected; `sd-debug` now hands over before
applying the fix, with the after-the-fix handoff still owed but priced at a
revert and a `partial`.

**C-12 — the three closing states were not mutually exclusive. `addressed`.**
New defect, introduced by the C-3 remediation. A session whose single
production change was never seen to fail matched `partial` ("changes with no
failing-test evidence") *and* `abandoned` ("the discipline was not followed"),
which breaks D6's "exactly one chosen". A single recovered-late change matched
`partial` only by ignoring its own opening words, "the evidence is mixed". The
states are now decided by sorting changes into `first`/`recovered`/`none` and
counting, which is exhaustive and disjoint by construction rather than by
careful reading.

**C-13 — C-5 was fixed in prose and not in procedure. Round-1 `addressed` was
wrong; now `addressed`.** The seam text correctly placed derives, conversion
impls and implemented accessors under test-first. `sd-typed-holes` step 4 then
gated the skeleton on check, clippy and format — none of which read behaviour —
and proposed the commit. The getter returning the wrong same-typed field, the
exact case the seam was written for, still shipped without `sd-tdd` ever being
invoked. Step 4 now requires every real body in the skeleton to be listed and
routed through `sd-tdd` before the commit is proposed, and the final report
carries that evidence or states its absence.

**C-14 — C-6's recovery mechanism was itself lossy. Round-1 `addressed` was
wrong; now `addressed`.** The safety rule offered `git diff > <patch>` as the
save before a destructive revert. Plain `git diff` omits staged changes and
mangles binaries, so a staged or binary fix would have produced an empty or
unusable backup at precisely the moment one was needed. Now
`git stash --include-untracked` or `git diff HEAD --binary`, with the reason
stated so the command is not quietly simplified back.

**C-15 — C-4's carve-out was unreachable in its own terms. Round-1 `addressed`
was wrong; now `addressed`.** The bootstrap carve-out permitted "the signature
that raises" and then required that surface to turn an import error into an
*assertion failure*. A Python stub raising `NotImplementedError` reports an
error, which step 4 rejected, sending the agent to write a placeholder return
value — executable behaviour, the very thing the gate forbids. The lane
demonstrated it: `FAILED (errors=1)`. Step 4 now draws the line at whose
absence the message reports rather than at error-versus-failure. A defect in
the test or its scaffolding is invalid red; a declared hole announcing itself —
`NotImplementedError`, or `todo!()` in Rust — is the behaviour being absent and
is valid red. This also aligns the rule with the `sd-typed-holes` lineage,
where a diverging panic is exactly how a hole speaks.

**C-16 — two stale numbers. `addressed`.** The heading criterion said "all six
lines" above a seven-item loop. And the C-10 ledger entry said the seam edits
were "seven added lines each" when they are seven and fifty-four — recording
the arithmetic error inside the entry correcting it.

**Round-1 entries the lane verified as holding:** C-1, C-2, C-7, C-8, C-9. It
also confirmed the C-2 rebuttal: real headings plus fenced duplicates produce
seven `2`s, and headings existing only inside a fence produce seven `1`s,
which is what the revised ledger says.

### Round 3, and the scope cut

Run against `90d884ad`. Six blocking findings, and the decisive result was not
any one of them: **every C-11..C-16 disposition was still false or incomplete**,
the same outcome round 2 reported for round 1. The lane invoked the planning
contract's stop at the third round.

The findings were checked and are correct. Three are worth recording by name
because they are the ones that settled the scope question:

- **C-22** refuted the valid-red rule in both directions. "Whose absence the
  message reports" was supposed to separate a declared hole from broken
  scaffolding. A bare `NotImplementedError` carries no message naming any
  behaviour, while a collapsed factory's
  `AttributeError: 'LegacyCart' object has no attribute 'calculate_total'`
  names the wanted behaviour perfectly and is invalid red. The rule sorted both
  cases backwards. Worse, the fix left the gate demanding the scaffolding turn
  an import error "into an assertion failure" while step 4, twenty-seven lines
  later, forbade manufacturing one — the C-1 defect class, introduced by the
  remediation for a finding about reachability.
- **C-21** showed the recovery procedure could not execute. After writing the
  test, the tree holds both the test and the fix; the
  `git stash --include-untracked` the safety rule prescribed removes both,
  leaving no fix to revert and no test to run.
- **C-20** found a no-evidence exit written into the gate that was added to
  close a no-evidence hole: the report bullet ended "or a statement that a body
  shipped without it".

**The scope was cut rather than remediated a fourth time.** Across three rounds
the item produced twenty-three findings, and fourteen belong to three
additions: the late-recovery revert path (C-3, C-6, C-11, C-12, C-14, C-18,
C-21), the `sd-typed-holes` seam (C-5, C-13, C-19, C-20), and the bootstrap
carve-out (C-4, C-15, C-22). The core discipline drew almost none. All three
are removed. `sd-debug` is reverted to `origin/main` untouched;
`sd-typed-holes` keeps only the `## Lineage` this item recovered, with the
boundary named as an open question inside it. `sd-tdd` states the two
unsettled questions in a section of its own rather than answering them a third
time.

Dispositions for the round-3 findings under the cut scope, one each:

- **C-17** (`sd-debug` had no operative pre-fix handoff) — `parked`. The
  handoff is gone; `sd-debug` is byte-identical to `origin/main`.
- **C-18** (the classifier keyed on authorship, and the empty session) —
  `addressed`. Changes are now sorted by when valid red was *observed* relative
  to the change, which is what requirement 4 says and what D4 explains. The
  empty session is now tie-broken by name in all three artifacts. Round 4
  caught that this sentence was false when first written: the skill and D4 both
  said `disciplined`, but requirement 4 only demanded that a winner be named
  without naming one, so two of three artifacts settled it and the ledger
  claimed three.
- **C-19, C-20** (the typed-holes fill pass and skeleton gate) — `parked`. Both
  concern a seam that no longer exists.
- **C-21** (the stash could not execute) — `parked`. The procedure it describes
  is removed.
- **C-22** (valid red unresolvable, and the gate contradicted step 4) —
  `addressed` in the only honest way available: the skill no longer claims a
  rule. Step 4 asks for the message to be quoted with a statement of why it is
  the behaviour being absent, and `## What this skill does not settle` records
  that two attempts at a syntactic rule failed and how.
- **C-23** (footprint numbers stale a third time: 7/54 claimed, 15/72 actual) —
  `addressed` by deletion. The counts are gone from both documents. A number
  that changes on every commit and had been wrong in all three of its states
  does not belong in prose; the diff is the source of truth for it.

### Round 4, the confirmation pass

Run against `46533b37`, scoped to reject findings against the three removed
features. It raised none, which is the result the cut was for. Four blocking
and two non-blocking, all local; the lane also confirmed the step 9 classifier
is exhaustive and mutually exclusive over every non-empty set, that `sd-debug`
is byte-identical to `origin/main`, and that the `sd-typed-holes` diff is
exactly one appended `## Lineage`.

**C-24 — the bound rule contradicted the closing-state classifier.
`addressed`.** The safety rule said a bound closes `partial`, "never
`disciplined`", while step 9 says all-proven closes `disciplined`. One
completed cycle followed by an expired bound counts 1 proven / 0 unproven:
step 9 said `disciplined`, the safety rule said `partial` with no unproven
change to name. The rule now defers to step 9's count and puts the unreached
behaviours under **Deferred** rather than `unproven` — nothing was written for
them, so there is no production change to be unproven. What a bound must never
do is licence reporting an unproven change as proven, which is what the rule
was reaching for.

**C-25 — the open question issued an instruction the gate forbids.
`addressed`.** `## What this skill does not settle` said to "write the least
scaffolding that lets the test speak", which is a positive instruction to
create production code before valid red — exactly what the gate prohibits, in
the section admitting the question is unresolved. The section now states the
tension and stops: when it comes up, stop and ask the user, the same move the
first safety rule makes for a proposed rewrite. An open question cannot issue
an instruction that contradicts a rule the skill still enforces.

**C-26 — requirement 4 demanded a tie-break without naming its result.
`addressed`.** The skill and D4 both said the empty session closes
`disciplined`; requirement 4 said only that it "must be tie-broken by name".
It now names `disciplined`. This also falsifies a sentence in the C-18
disposition above, which claimed all three artifacts named a winner when two
did — corrected in place, with the error left visible rather than removed.

**C-27 — the branch violates the two-file diff boundary. `rebutted`.** The
criterion is `git diff --name-only origin/main...HEAD -- skills/`, with the
pathspec, and it prints exactly the two skill files. The lane ran the command
without `-- skills/`, got the item's own `prd.md` and `design.md` as well, and
reported the criterion as violated. Its own acceptance table records the
correct invocation passing under "changed skills", so the finding contradicts
the run directly above it. A work item that did not modify its own PRD would be
the defect.

**C-28 — the scope note named the wrong requirements. `addressed`.** It
attributed the `sd-typed-holes` boundary and bootstrapping to requirement 8.
Requirement 8 covers bootstrapping and late recovery; the boundary is
requirement 9. Rewritten to name all three open questions and where each is
recorded.

**C-29 — two `## Lineage` cross-references pointed the wrong way.
`addressed`.** Lineage was appended after the operational sections, so "the
safety rules below" and "Four rules below" referred to rules above them.

### Round 5

Run against `b56334c0`. Two blocking, no non-blocking — and the first of them
is the one the previous round's fix was predicted to cause. Every cross-rule
consistency edit in this item has introduced a new defect elsewhere; this made
it five for five, which is why the round was run rather than shipping on the
round-4 remediation.

**C-30 — a bound could close an incomplete cycle as `disciplined`.
`addressed`.** The C-24 fix defined `proven` as "valid red was observed against
a tree that did not yet contain the change", keying on the red step alone.
Concrete case: valid red observed, production code written, a *time* bound
fires before the rerun. Step 9 counted the change proven and closed
`disciplined`, while real untested code sat in the tree — it could not be
`Deferred`, having been reached and implemented, and the Cycles bullet demanded
pass-and-suite evidence that did not exist. `proven` now requires **both**
halves of the cycle: the red, and the change then seen to pass with the suite
green. An interrupted change falls to `unproven`, the session closes `partial`,
and the report names which half is missing — the report bullet now distinguishes
"never seen to fail" from "seen to fail and then left before it was seen to
pass", the second being the more dangerous state because nothing has run
against that code since. `Deferred` is unchanged and does not overlap: it is
behaviours nothing was written for.

**C-31 — the C-25 remediation was not propagated. `addressed`.** The skill was
changed to say "stop and ask" for the bootstrap question, while requirement 8
and D7 still said it "tells the reader to use judgement". Two artifacts
authorised autonomous resolution of a question the third routed to the user.
Both corrected, and D7 now records the constraint the round-4 fix taught: an
open question may not issue a positive instruction that contradicts a rule the
skill still enforces.

**What the lane confirmed.** It ran the closing classifier over its state space
— `combinations=36 exactly_one_failures=0` — and confirmed `Deferred` and
`Behaviours already present` do not collide, C-26 names `disciplined` for the
empty session, C-28's attribution is right, C-29's references now say "above",
requirements 1-7 and 9 agree with D1-D7 and both skill files, `sd-typed-holes`
differs only by one appended `## Lineage`, and the two-file criterion run with
its pathspec prints exactly the two expected paths.

### What the lane could not run

`make check` and the companion/citation unittests failed inside the read-only
sandbox — `Operation not permitted` creating coverage, log and temp files —
so those results are the host's, not the lane's. Every other acceptance
command ran there verbatim.

## Log

- 2026-09-05 created. Scope set by the user after a review of all 14 upstream
  skills against all 81 pack skills found test-driven development to be the one
  genuine hole.
- 2026-09-05 codex round 1 returned eight blocking concerns and two
  non-blocking; all ten dispositioned in `## Review`. The round added
  requirements 10, 11 and 12 and changed the closing-state contract, so a
  recovered late test now closes `partial`. `sd-typed-holes` gained a
  `## Lineage`, recovering provenance that changed D4 rather than annotating
  it.
- 2026-09-05 codex round 2 against `41cda029`: five blocking, one non-blocking,
  recorded as C-11..C-16. Three round-1 dispositions were disproved and one
  incomplete, all failing the same way — the sentence describing a rule was
  corrected and the procedure executing it was not. The round added a counting
  rule for the closing states, a valid-red definition that makes the bootstrap
  carve-out reachable, a lossless save command, and a step in
  `sd-typed-holes` that routes the skeleton's real bodies through `sd-tdd`.
- 2026-09-05 codex round 3 against `90d884ad`: six blocking, and every round-2
  disposition still false or incomplete. Scope cut on the user's decision
  rather than remediated a fourth time. The late-recovery path, the
  `sd-typed-holes` seam and the bootstrap carve-out are removed; `sd-debug`
  reverted to `origin/main`; `sd-typed-holes` keeps only its recovered
  `## Lineage`. Requirements fall from twelve to nine and the skill gains a
  section naming what it does not settle.
- 2026-09-05 codex round 4 against `46533b37`, the confirmation pass on the cut
  scope: four blocking and two non-blocking, none against a removed feature,
  all local. Five addressed and one rebutted (the two-file criterion was run
  without its pathspec). The lane confirmed the closing-state classifier is
  exhaustive and mutually exclusive, `sd-debug` byte-identical to `origin/main`,
  and the `sd-typed-holes` diff exactly one appended `## Lineage`.
- 2026-09-05 codex round 5 against `b56334c0`: two blocking, none non-blocking.
  C-30 was the defect the round-4 fix was predicted to introduce — `proven`
  keyed on the red step alone, so a time bound firing mid-cycle closed
  `disciplined` over untested code. `proven` now requires both halves of the
  cycle. C-31 was unpropagated wording from the C-25 fix. The lane verified the
  classifier over 36 combinations with zero exclusivity failures.
