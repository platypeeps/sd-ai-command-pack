# Design — simplify review and shipping composition

## Scope boundary

The composition half only. Removal scheduling and the transitional catalog status
belong to `07-28-retire-transitional-review-surfaces`; deletion belongs to
`07-24-remove-retired-review-surfaces`. Housekeeping and the shared exact-head
eligibility evaluator stay untouched as the only merge mutation owners.

## R7 is where the difficulty lives

`sd-ship` Stage 2 (`.agents/skills/sd-ship/SKILL.md:129-136`) currently gets
**three** things from `sd-review-pr`:

1. the bounded review loop (check, remote review, fixes, replies);
2. *"the one read-only, PR-scoped post-cycle review-learning pass; no other ship
   stage repeats it"*;
3. finish-work, conditionally — `until=review` invokes it **without**
   `defer-finish-work` so its Step 8 finishes the Trellis work; `until=merge`
   invokes it **with** `defer-finish-work` and defers to the Stage 4 handoff.

`sd-review` supplies only the first. `SKILL.md:73` states plainly:

> Do not merge, archive Trellis work, or run housekeeping from this skill.

and `grep -n "review-learning" .agents/skills/sd-review/SKILL.md` returns
**nothing** — the successor has no review-learning pass at all.

### The two `until=` values are not equally hard

- **`until=merge` is nearly mechanical.** Stage 4 already "runs finish-work"
  (`SKILL.md:145`) and reuses its schema-version-1 receipt bound to the exact
  final head. Deferral is already the behavior; the successor simply never had
  the thing being deferred.
- **`until=review` has no home for finish-work.** Its whole contract is *finish
  the Trellis work, then stop before merge*. Under the successor, no stage does
  that.

Options for `until=review`:

- **A — `sd-ship` runs finish-work itself as an explicit step after Stage 2.**
  Keeps the user-visible contract identical, puts the authority in the composer
  where R2 already says the lifecycle is explicit. Recommended.
- **B — `until=review` stops without finishing work.** Smallest diff, but changes
  observable behavior for every current caller and quietly moves work onto the
  operator.
- **C — give `sd-review` a finish-work mode.** Rejected: directly contradicts
  `SKILL.md:73` and re-creates the overlapping authority R6 exists to remove.

### The review-learning pass needs an owner, named explicitly

It is not optional plumbing — Stage 2 asserts it happens exactly once per cycle.
Either `sd-ship` invokes `sd-review-learnings` as its own step, or the pass is
dropped and that is written down as a decision. Silently losing a
once-per-cycle pass during a repoint is the failure mode to avoid.

## R3 and R4 land on Stage 3 together

Stage 3 (`SKILL.md:138-142`) invokes `sd-watch-pr` with `no-merge`, and the skill
says `no-merge` *"suppresses the standalone watch command's automatic
housekeeping handoff so Stage 4 owns that side effect exactly once."*

So:

- R3 (remove public `sd-watch-pr`) deletes the surface Stage 3 calls.
- R4 (no `no-merge` inversion; mutation must not be the default) deletes the
  mechanism Stage 3 relies on to stay safe.

Both are correct and they must land as one change: the internal read-only
coordinator replaces the surface **and** makes report-only the default, so the
suppression flag becomes unnecessary rather than merely removed. Doing R4 before
R3 would leave a public watch command whose default is now safe but whose callers
still pass a flag that no longer exists; doing R3 before R4 leaves the inversion
live in the internal coordinator.

## Contract shape

After this task the composition reads:

```
Stage 1  sd-create-pr        publish or reuse exactly one PR      (R1)
Stage 2  sd-review scope=pr  bounded review loop                  (R7)
Stage 2b sd-ship             finish-work / review-learning        (R7 gap)
Stage 3  internal coordinator  read-only bounded polling          (R3, R4)
Stage 4  sd-housekeeping     finish-work, receipt, merge, cleanup (unchanged)
```

**Stage 2b's owner is `sd-ship` — decided 2026-07-28, option A.** An earlier
draft left it `TBD`. Both halves land on the composer for the same reason: R2
makes the lifecycle explicit in `sd-ship`, and `sd-review/SKILL.md:73` forbids
finish-work inside the successor (option C), while option B silently drops work
onto the operator for every current `until=review` caller.

So Stage 2b is two explicit `sd-ship` steps, run once after Stage 2 and only
under `until=review` — `until=merge` reaches Stage 4, which already runs
finish-work (`SKILL.md:145`) and must not run it twice:

1. finish-work, bound to the same head Stage 2 reviewed;
2. `sd-review-learnings`, invoked by name.

Stage 2b does **not** collapse into Stage 2 (that is option C) and does not
collapse into Stage 4 (which `until=review` never reaches). Under `until=merge`
Stage 2b is skipped entirely — that skip is the double-run guard, and it is the
thing to test.

## R8 — the guide

`docs/SD_AI_COMMAND_PACK.md:194` opens the "Recommended review loop", which then
interleaves successor and transitional steps (`:212`, `:230`, `:247`, `:256`)
across 18 steps with no decision point. Presenting the successor loop only is
simpler and is compatible with the predecessor still shipping — the transitional
commands remain callable, they just stop being recommended. Prefer that over
adding a branch the reader has to evaluate.

## Compatibility

`until=pr`, `until=review`, `until=merge` are the observable contract. Option A
preserves all three verbatim; option B changes `until=review`. Whichever is
chosen, the change is user-visible and belongs in the CHANGELOG.

## Rollout and rollback

R7 and R8 are the interim and can land before retirement. R1-R6 are the end
state. Each stage repoint is independently revertable while the predecessor still
ships — which is exactly the window this task should use, because after
`07-24-remove-retired-review-surfaces` lands there is no predecessor to revert
to.

## Risk

The failure mode is a repoint that looks complete because the review loop still
works, while finish-work and the review-learning pass have quietly gone missing —
both are post-loop side effects that no review-loop test would catch. Test for
their presence, not for the loop's success.
