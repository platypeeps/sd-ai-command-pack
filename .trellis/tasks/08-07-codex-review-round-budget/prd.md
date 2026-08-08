# Raise the planning adversarial-review round budget to five and ask before continuing

## Goal

Give the planning adversarial-review loop a budget of five automatic rounds
instead of three, and make budget exhaustion a request for permission to
continue rather than a mandatory stop.

## Problem

`.claude/sd-ai-command-pack/planning-adversarial-review.md:110-119` caps
convergence:

```text
When addressed concerns change a planning artifact, rerun the host review and,
only if it was available in the initial round, one fresh Codex review against
the updated artifact set. Reconcile each remediation round through the same
ledger. Run at most two remediation rounds (three automatic rounds total); do
not start a fourth automatic round.

If a substantive concern persists after the permitted remediation rounds, or
the two lanes remain in material conflict, stop before implementation approval
or `task.py start` and ask the user for judgment.
```

Two separate problems live in that text.

**The budget is too small for the work it gates.** Three rounds is one initial
review plus two remediations. A planning batch that touches `prd.md`,
`design.md`, and `implement.md` together routinely raises concerns in more than
two waves, because fixing a `design.md` contract surfaces the next
`implement.md` inconsistency only after the design is settled. The repository
already has a recorded instance of the cap binding before convergence, in
`.trellis/workspace/sdelmas/journal-6.md:1411`:

```text
Planning-adversarial-review COMPLETE (3 passes, contract cap) ... HONESTY
CAVEAT: Option A (M-1 fix) landed after the final review pass -> host-verified
only, NOT Codex-approved (pass budget spent); used 3 remediation rounds vs
nominal 2.
```

That session shipped a change the Codex lane never saw, and had to record the
gap as a caveat, because the budget ran out mid-convergence. The cap did not
prevent an unbounded loop; it produced an unreviewed change plus an honest
apology.

**Exhaustion is a dead end, not a decision point.** The current instruction is
`stop ... and ask the user for judgment`. Judgment about what to do instead —
not permission to keep converging. A user who can see that round 3 closed four
of five concerns has no sanctioned way to say "run one more". The only exits
are abandoning the remaining concern or overriding the contract.

## Requirements

1. The automatic budget is **five rounds total** — one initial review plus four
   remediation rounds. The count is of automatic rounds, matching how the
   current text counts them, so the change is `two remediation rounds (three
   automatic rounds total)` becoming `four remediation rounds (five automatic
   rounds total)`.
2. On exhausting the budget with concerns still open, the agent asks the user
   for **permission to continue**, as a structured decision with a
   recommendation. Granting it authorizes a further bounded run of rounds;
   declining ends convergence at the current ledger state.
3. Permission is per-request and does not become standing authority for the
   task, the session, or later planning batches. Each exhaustion asks again.
4. The existing stop-and-ask escalation for **material lane conflict** is
   unchanged. A host/Codex disagreement is a judgment call, not a budget
   problem, and must not be silently converted into "run more rounds".
5. Every unresolved blocking concern still blocks implementation approval and
   `task.py start`, at any round count. Raising the budget must not weaken that
   gate.
6. `.claude/sd-ai-command-pack/planning-adversarial-review.md` and
   `templates/.claude/sd-ai-command-pack/planning-adversarial-review.md` are
   byte-identical twins today and must stay so.
7. The completion report in section 5 gains the rounds actually run and whether
   a continuation was requested, granted, or declined — otherwise a five-round
   convergence is indistinguishable from a two-round one in the record.

## Open decision

**What the number five counts.** This PRD reads "loop count to 5" as five
automatic rounds total, because that is the unit the existing sentence counts
and the unit a reader of the report sees. The alternative reading is five
*remediation* rounds, giving six total. Recommendation: five total, as written
above. If the intent was five remediations, only the arithmetic in requirement
1 changes.

## Acceptance criteria

- Both twin copies state a five-round automatic budget and remain
  byte-identical.
- The exhaustion path asks for permission to continue, with the structured
  question named and its recommendation stated.
- The material-conflict escalation still stops for judgment and is visibly
  distinct from budget exhaustion.
- Granting continuation is scoped to one request; the text says so.
- The completion report lists rounds run and the continuation disposition.
- No change weakens the unresolved-blocker gate on implementation approval or
  `task.py start`.

## Out of scope

- The remote review `roundLimit`, already 5 and separately configured at
  `scripts/sd-ai-command-pack-review.py:273` and `:313`.
- The `sd-review-local` fix loop and its own repeat rules.
- Any change to when the adversarial-review contract triggers, which
  `.claude/rules/sd-planning-adversarial-review.md` owns.
- Making the budget configurable. The contract is prose; a number in prose is
  the change requested.
