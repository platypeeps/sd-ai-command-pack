---
title: the interview that decides every downstream artifact is one sentence long
status: planning
created: 2026-09-04
branch: skill/sd-grill
---

# PRD — the plan interview is one sentence

## Problem

`sd-plan`'s first step is the whole interrogation: "Ask until the PRD's headings
can be filled honestly." One sentence, and everything downstream inherits
whatever it produced. The rest of that skill is specific to the point of naming
exit codes, so the imbalance is not house style — it is the step nobody wrote.

Nothing else in the pack fills it. `sd-socratic-review` has the machinery — one
question per turn, response classes, misconception repair, an evidence ledger
that reports what it did not cover — but its subject is the user's understanding
of a *topic* and its output is a learning report, not a statement of intent.
`sd-red-team` is adversarial but non-interactive and takes a settled artifact.
`sd-premortem` needs a plan already accepted. `sd-decide` needs the options
already known. A user who wants their half-formed idea interrogated has no
surface to reach for, and the interrogation currently happens ad hoc or not at
all.

The failure that makes this worth a skill rather than a paragraph: an assistant
conducting an unstructured interview fills silences. It proposes the requirement
the user never stated, the user says "yes, that", and the PRD now records the
assistant's idea as the user's intent with nothing marking which is which. That
is not caught downstream — every later gate reads the PRD as authored.

## Requirements

1. A skill interrogates the user's own proposal one question per turn. It has
   three terminations and all three write nothing: **completed**, ending in a
   closing statement the user approves; **handed off**, when the subject turns
   out to belong to a sibling skill; and **stopped**, when the user halts it or
   an agreed bound is reached first. Only a completed session produces a closing
   statement. The other two report what was and was not covered, and neither
   presents its partial ledger as a statement of intent.
2. It is a skill and not one of the eleven commands: it carries no
   `disable-model-invocation`, so the model may reach for it and the user may
   ask for it in conversation.
3. Each answer is classified from a fixed closed set, and a success criterion
   naming an intention rather than a check and its result is classified as
   defective and repaired rather than accepted.
4. Content the assistant supplied and the user then adopted is reported
   separately from what the user stated independently.
5. The skill writes no file, creates no branch, and invokes no sibling that
   would; whichever of its three closing states it reaches is where its work
   ends.
6. The skill classifies how much interrogation a proposal warrants, and the
   classification governs the depth of the interrogation only. It never governs
   whether the user's approval is required before implementation: that gate is
   identical at every classification, and the skill says so in as many words.
7. `sd-plan`'s interview step names the skill, so the relationship is not
   asserted in one direction only.
8. Material adapted from outside the pack records where it came from, under
   which licence, at which revision.

## Acceptance criteria

- [ ] `make check` reports 40 `OK` and 0 `FAILED` — unchanged from `6b1ea46e`
- [ ] `grep -c disable-model-invocation skills/sd-grill/SKILL.md` prints `0`
- [ ] `grep -c '^# sd-grill$' skills/sd-grill/SKILL.md` prints `1`, satisfying
      the title contract in `tests/test_skill_frontmatter.py`
- [ ] `grep -c 'sd-grill. is that interrogation written down' skills/sd-plan/SKILL.md`
      prints `1` — a bare name count would pass on a sentence saying never to
      use it, so the criterion pins the sentence that establishes the
      relationship, not the occurrence of the word
- [ ] on the pushed branch, `git diff --stat origin/main...HEAD -- bin/ dashboard/`
      prints nothing, so no line-count ceiling in `tests/test_loc_caps.py` moves
      — evaluated after the commits exist, since before them it passes whatever
      the branch contains
- [ ] `grep -c 'obra/superpowers' skills/sd-grill/SKILL.md` prints `1` and that
      line names both the licence and the revision — the `## Lineage` section
      exists to be re-audited, and a section heading with nothing under it
      cannot be
- [ ] the seven answer classes the skill declares are each still *declared* —
      this exact command prints seven lines, each ending `1`:

      ```
      for c in grounded asserted deferred contradiction unfalsifiable \
               scope-drift not-asked; do
        echo "$c $(grep -cF -- "**$c**" skills/sd-grill/SKILL.md)"
      done
      ```

      The bold token appears only in the class list, so deleting a class from
      that list fails the check even though the bare word survives elsewhere in
      the prose — which a plain `grep -c grounded` would not catch
- [ ] `skills/sd-grill/SKILL.md` has a `## Safety rules` section whose first
      rule states the skill is read-only and writes no file, creates no branch,
      and invokes nothing that would

- [ ] `grep -cF 'This holds at every classification' skills/sd-grill/SKILL.md`
      prints `1`, and the sentence sits under `## The gate` — requirement 6's
      claim is that the skill states the gate is classification-independent, so
      the criterion checks the statement rather than the intent behind it

### What these criteria do not cover

Requirements 1 and 4 are properties of how the skill behaves across turns of a
live conversation: one question per turn, and a contaminated answer that keeps
its origin when the same content comes back later. No check in this repository
can run them. The pack's CI asserts the *structure* of a skill file and never
its conduct, which is true of every skill here — demanding otherwise would mean
no skill in the pack could ship.

So they were verified by reading, in the two review lanes recorded under
`## Review`, and by nothing else. Naming that is the point: a requirement with
no criterion is one whose verification is a person, and the difference between
a gap and a hidden gap is whether the document says which person.

## References

- `github.com/obra/superpowers`, MIT, revision `b36e0829c6d0140e93cfef2ca599b1b07d4a7797` —
  its `brainstorming` skill is the source of the three-way effort
  classification, the one-way ratchet, and the gate that does not scale with
  simplicity.
- `skills/sd-socratic-review/SKILL.md` — the turn machinery this adapts.
- `skills/sd-plan/SKILL.md` — the step being filled, and the owner of
  `docs/work/`.

## Review

Planning adversarial review, 2026-09-04. Trigger: `prd.md` new, `design.md` and
`implement.md` absent at baseline and deliberately still absent. Two lanes ran —
the host lane and this repository's native Codex lane — over three rounds, the
maximum the contract permits. The
ledger below is merged and deduplicated across both.

| ID | Lane | Round | Severity | Blocking | Disposition |
|---|---|---|---|---|---|
| C-1 | host + codex | 1 | high | yes | addressed |
| C-2 | codex | 1 | high | yes | addressed |
| C-3 | codex | 1 | medium | yes | addressed |
| C-4 | codex | 1 | medium | yes | addressed |
| C-5 | codex | 1 | medium | yes | addressed |
| C-6 | host | 1 | low | no | rebutted |
| C-7 | host | 1 | low | no | parked |
| C-8 | host | 1 | low | no | addressed |
| C-9 | codex | 2 | medium | yes | addressed |
| C-10 | codex | 2 | medium | yes | addressed |
| C-11 | codex | 2 | high | yes | **unresolved — referred to the user** |
| C-12 | codex | 3 | medium | yes | addressed |
| C-13 | codex | 3 | medium | yes | addressed |

**C-1 — several requirements carried no acceptance criteria, and the document
cited a `## Review` section it did not have.** Addressed: criteria added for
requirements 3, 5, 6 and 8, each naming a command and its expected result; this
section created. The separate question of whether reader-verification suffices
for the two remaining requirements is C-11, held apart so that each concern
carries exactly one disposition.

**C-2 — the contamination rule could launder assistant-supplied intent.**
Step 7 said contamination lapsed "until the user restates it independently"
while the final report said *every* contaminated answer stays marked; the two
could not both hold, and the gap between them was the laundering path. This is
the failure the whole item exists to prevent, found by the second lane and not
the first. Addressed in `skills/sd-grill/SKILL.md`: contamination is never
cleared, and a later independent answer is recorded beside it rather than
replacing it.

**C-3 — requirement 6 was not independently testable, and the skill contradicted
itself on the probe path.** The red-flags table said "Two questions" where the
probe path said "two or three". Addressed: requirement 6 rewritten to the claim
that is actually checkable — the gate is identical at every classification and
the skill says so — with a criterion pinning that sentence; the table now reads
"Two or three questions".

**C-4 — two acceptance criteria passed while their requirements were unmet.**
The seven-class check matched the same words in surrounding prose, so deleting a
class from the declaration left the check green; the `sd-plan` check counted an
occurrence, which a sentence saying never to use the skill would also satisfy.
Both were criteria added by the host lane's own first remediation round, and
both were caught by the second lane. Addressed: the class check pins the bold
declaration token through `grep -cF`, verified `1` for all seven; the `sd-plan`
check pins the sentence. The criterion's claim that requirement 3 enumerates the
seven classes was also wrong and is corrected — it requires a closed set without
naming its members.

**C-5 — requirement 1 could not hold for every termination.** The skill honours
stop and bound, so a session can end before a closing statement exists, which
the requirement forbade. Addressed: requirement 1 now names both terminations
and forbids a stopped session from presenting its partial ledger as intent.

**C-6 — `scope=probe|bounded|structural` reuses a reserved shared argument
name.** Rebutted: `skills/_shared/references/argument-vocabulary.md` reserves
`scope=` for the extent of work a skill covers, and the classification governs
exactly that — how far the interrogation goes.

**C-7 — `pressure=standard|hard` is a skill-owned name outside the shared
vocabulary.** Parked, not blocking: the vocabulary permits skill-owned names,
and promoting this one is warranted only when a second skill wants an intensity
dial. Trigger: that second skill. Owner: the user.

**C-8 — the line-count-ceiling criterion passed vacuously.** Before the branch
had commits, `git diff origin/main...HEAD` printed nothing whatever the tree
contained. Addressed: the criterion now says it is evaluated on the pushed
branch, and why.

**C-9 — the seven-class criterion was not runnable as written.** It carried a
literal `<class>` placeholder and omitted the filename, so executed exactly as
printed it returned `0`, not `1`. The host lane had verified the criterion by
running a *different* command from the one it wrote down — which is the failure
this repository keeps finding in other clothes. Addressed: the criterion is now
the runnable loop, and running it exactly as printed produces seven lines each
ending `1`.

**C-10 — the fix for C-5 left the two artifacts disagreeing.** `prd.md`
requirement 1 was rewritten to name a stopped termination while
`skills/sd-grill/SKILL.md` still presented a closing statement unconditionally
and still required a hardened statement in every report. A remediation that
corrects one artifact and leaves its pair asserting the old thing is exactly the
shape the contract's cross-artifact sweep exists for. Addressed: workflow step 9
now closes in one of two named ways, the final report gained a `Closing state`
bullet and made the hardened statement conditional, and `## The gate` says a
stopped session reaches no approval.

**C-12 — the C-10 fix left three unconditional statements standing.** The skill
gained a stopped branch, but its `description`, its `## The gate` paragraph, and
PRD requirement 5 all still said the work ends at a closing statement. Addressed:
the description now names both outcomes, the gate paragraph scopes its sentence
to a **completed** interrogation, and requirement 5 refers to whichever closing
state is reached.

**C-13 — declaring "exactly two" closing states left a third path unclassified.**
Step 8 already required stopping early when a sibling skill owns the subject, and
that termination fit neither `completed` nor `stopped`. Addressed: the closure is
now three named states, `handed off` is defined in step 9 and forbidden from
presenting its partial ledger as intent, and PRD requirement 1 names all three.

**C-11 — the two lanes disagree on whether requirements 1 and 4 may ship
verified by reading alone. Unresolved, and referred to the user.** The Codex
lane holds that `sd-plan`'s contract requires every requirement to name a check
and its result, so reader-verification does not satisfy it and the item is
blocked. The host lane holds that no skill in this pack has conduct-level CI —
`tests/test_skill_frontmatter.py` asserts frontmatter and title and nothing
about behaviour — so the same objection would block every skill the pack has
ever shipped, and the achievable standard is that the gap be declared rather
than hidden. Both readings are defensible and neither is a fact a further round
can settle. Per section 4 of the planning contract, three automatic rounds have
run and two lanes remain in material conflict, so this stops here for the user's
judgment instead of being self-approved.

**Lane status.** Host: completed, three rounds. Codex: completed, three rounds.
C-12 and C-13 were found by the Codex lane in round 3 and remediated by the host
lane afterwards; the contract forbids a fourth automatic round, so those two
fixes carry host verification only and no second opinion. That is a real
limit of this ledger, not a formality.
The Codex lane declined to run full `make check` because its runner writes
`.coverage*` and `unittest-output.log`, which its read-only instruction forbade;
it ran a focused 26-test subset instead, and the host lane ran the full gate at
every round.

**Implementation is blocked on C-11.** Every other concern is addressed,
rebutted, or parked, and no parked concern blocks. C-11 needs a decision from
the user, not another round.

## Log

- 2026-09-04 created. No `design.md`: the approach was settled before the item
  existed — a standalone skill rather than a `--grill` flag on `sd-plan`, chosen
  by the user, and a design restating that is a design nobody needed. No
  `implement.md`: one landable step, one pull request.
