# Design — two unwritten disciplines and one contradicted rule

## Approach

### The question-form rule

The obvious fix is to ban assistant-authored option sets outright, matching
`sd-socratic-review`. Rejected. That skill bans them for a reason that does not
transfer: it is testing whether a learner knows something, and an option list
hands over the answer being tested. `sd-grill` is not testing the user's
knowledge — it is extracting intent the user already holds. Options there are
sometimes the only way to make a question answerable at all, and the harness's
own question tool is built from them. A ban would be widely ignored, which is
worse than no rule.

The other obvious fix is to permit options freely and rely on step 7's existing
contamination rule. Also rejected: step 7 covers an answer "the assistant
supplied and the user then adopted", and a reader can argue that a user who
picks one of three options *chose* rather than *adopted*. That reading is what
let a fully contaminated session close `completed` without saying so. The
ambiguity is the defect; leaving it and hoping is not a fix.

So the rule splits the form by **who authored the candidate set**, which is
observable, rather than by whether the answer was expected, which is not:

- **open** — the user's answer supplies its own content.
- **closed, externally determined** — the candidates come from something that
  exists and was read: the files in a directory, the states a schema allows,
  the options a tool exposes. The assistant transcribed them. Not contaminated;
  the ledger records what was read.
- **closed, assistant-authored** — the assistant wrote the candidates.
  Contaminated by construction, always, regardless of how decisively the user
  chose.

Open is asked first. An assistant-authored closed question is permitted only
after an open one was asked and did not land, or when the user asked to be
given options. And because a whole session can legitimately run that way, the
consequence is moved to where it can be seen: the closing statement leads with
it, before the requirements it is asking the user to approve. The alternative —
listing contaminated answers under a heading near the end — is what the first
session did, and it is a disclosure the reader meets after already having read
the requirements as though they were the user's.

### `sd-debug`

Shaped as an evidence ledger with a gate in front of it, matching `sd-grill`
and `sd-socratic-review` rather than inventing a third house style.

The gate is the whole discipline: **no edit before a reproduction**. Everything
else follows from it. A hypothesis is admissible only if it predicts something
not yet observed, so that the experiment can fail; a prediction that merely
restates the symptom tests nothing. Experiments change one variable, because
two changes and a green run leave you unable to say which mattered.

The closing states are chosen so that the most common false report is
unsayable. `**fixed**` requires the reproduction to have been rerun and to no
longer reproduce, *and* the mechanism to be stated in one sentence. A session
that got a green run without a mechanism closes `**diagnosed**` at best — and
one that never reproduced the failure cannot reach either, which is the point:
"it stopped happening" is not a fix, and the skill should have no word for it.
`**stalled**` reports what was eliminated, which is the salvageable value of a
failed debugging session and is normally thrown away.

Read-only was considered and rejected. Debugging means running things and
sometimes editing to test a hypothesis; a read-only debugging skill would be
advice about debugging rather than a discipline for doing it. The bound is
narrower and enforceable instead: no commit, no branch, no pull request, and no
experimental edit left standing that has not been run against the reproduction.

### `sd-receive-review`

The dispositions are not new. The pack's planning adversarial review contract
already fixes exactly four — `addressed`, `rebutted`, `parked`, `unresolved` —
with exactly one per concern. Reusing them was preferred over coining a
review-response vocabulary, because a second four-word set for the same idea is
how two ledgers come to mean slightly different things by the same words.

The load-bearing rule is the steelman: a finding may not be rebutted until its
strongest reading has been stated. Without it `rebutted` becomes the disposition
for findings that were inconvenient, and a four-way ledger with an escape hatch
is a one-way ledger. Its mirror is stated too — reviewer authority is not
evidence — because the failure this skill exists for is agreement-by-default,
and a skill that only guarded against dismissal would make that failure worse.

`unresolved` deliberately has no remediation path inside the skill. It escalates
and stops. This matches the planning contract, where two lanes in material
conflict stop for the user's judgment rather than being self-approved, and it
is the only disposition the author cannot grant themselves.

The skill produces dispositions and takes no outward action — no reply posted,
no thread resolved, no merge. That is the same posture `sd-review` already
holds ("dispose of the findings locally, never posting them") and the same seam
`sd-feedback` already declares from its side.

## Decisions

- **D1 — the question-form split is by who authored the candidate set, not by
  whether the answer was expected.** Decided by the assistant, 2026-09-04, from
  the observation that "expected answer" is unobservable at the moment a
  question is written while authorship is not. Reversed by a case where an
  assistant-authored set demonstrably does not contaminate, which would mean the
  split is drawn in the wrong place.
- **D2 — a fully contaminated session may still close `completed`.** Same date
  and source. The alternative is forcing such sessions to close `stopped`, which
  would make the honest disclosure cost the user their statement of intent and
  so create pressure to not disclose. Reversed if disclosure-first turns out to
  be ignored in practice, at which point the harder rule is the remaining
  option.
- **D3 — reuse the planning contract's four dispositions rather than coin new
  ones.** Same date and source. Reversed if a review response needs a state the
  four cannot express; the candidate is a distinct "duplicate of another
  finding", currently handled as `parked` with a pointer.
- **D4 — `sd-debug` is not read-only.** Same date and source. Reversed only by
  evidence that the bound is unenforceable in practice, in which case the
  fallback is diagnosis-only with the fix handed to a separate request.
- **D5 — the behavioural halves of requirements 5 through 8, and requirement
  10's postcondition, ship verified by reading.** Forced, not
  chosen: the conduct harness that would test them was abandoned on 2026-09-04
  when `claude plugin eval` proved to implement it already and to be gated
  behind early access on this account. Reversed the day that gate lifts.

## Risks

**Three deliverables in one item.** A blocking concern on any one of them
stalls the other two. Accepted because they share one origin, one review lane
and one pull request, and because the `sd-grill` fix is small enough that
splitting it would cost more review than it saves. Named so that if a lane does
block on one, splitting is the first thing considered rather than the last.

**Two new skills, both verified by reading only.** This item takes the pack from
one skill whose behavioural requirements are reader-verified to three. C-11 on
the `sd-grill` item was parked on the argument that a declared gap is acceptable
while nothing can close it; that argument does not improve by being applied
three times. Accepted and recorded rather than mitigated, because the thing that
would close it exists and is switched off.

**The steelman rule is unenforceable by reading.** Nothing in a transcript
distinguishes a real steelman from a sentence shaped like one, and the skill
cannot tell the difference either. Accepted: the rule's value is that a rebuttal
must be preceded by a statement the reviewer would recognise, which at least
makes a bad rebuttal visible to the reviewer reading it.

**`sd-debug` overlaps the Rust skills.** `sd-rust-async` covers debugging
spawned tasks and select loops, and a reader could reasonably reach for either.
Mitigated by naming the seam from `sd-debug` only, and not by narrowing it — a
language-agnostic debugging discipline that excused itself from Rust would be a
strange thing to have written. The reciprocal pointer from `sd-rust-async` is
deliberately not added: it is a skill about writing async Rust that mentions
debugging in passing, and every skill that mentions debugging is not a place
this item is willing to edit. `sd-feedback` is the one exception, because it
disclaims this exact job in its own "Do not use" list and named no owner for
it — that pointer is added.
