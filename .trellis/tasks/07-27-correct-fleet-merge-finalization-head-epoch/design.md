# Design: Correct fleet merge finalization head epochs

## Decision

Extend the controller's existing `pr-head-advanced` transition to the `merge`
stage. The issued merge action remains bound to the last reviewed publication
head. When `sd-finish-work` creates the required archive/journal successor, the
merge owner records that issued action as a bounded retry against the old head
and existing PR number. The controller then issues `pr-publication` for the new
head, establishing a new exact-head epoch before review, CI eligibility, and
merge run again.

## Transition

```text
merge(old published head)
  -> sd-finish-work produces valid successor receipt and advances PR head
  -> record retryable-failure/pr-head-advanced against old head + same PR
  -> pr-publication(new head)
  -> review(new head)
  -> merge-eligibility(new head)
  -> merge(new head, retained finish-work receipt)
  -> post-merge-verification
```

The merge action is not replayed. The second merge action has a new attempt and
action identity. A second head advance at attempt two terminates as
`retry-exhausted` under the controller's existing bound.

## Evidence Boundaries

- The old merge receipt must name the current controller head and PR number;
  it never names the unpublished successor.
- Only a passed publication receipt establishes the successor head.
- Review, eligibility, merge, and post-merge receipts remain equal to their
  publication epoch.
- The valid finish-work receipt is retained across republication and consumed
  by housekeeping only after its exact head has passed the new review and
  eligibility gates.
- Terminal corrective-release recovery remains available for the distinct
  case where finish-work cannot produce valid task evidence.

## Contract-Surface Sweep

Included:

- Controller receipt semantics, lane advancement, validation, bounded retry,
  persisted state, CLI error text, and resume behavior.
- Fleet skill merge ownership and recovery wording.
- Fleet operator guide and backend controller specification.
- Template/root generated parity, release version, changelog, and candidate
  validation evidence.

Excluded:

- `pr-publication`, which establishes rather than consumes a head epoch.
- `post-merge-verification`, because the PR is already merged and no
  republication is meaningful.
- Housekeeping or Trellis receipt schema changes; the existing exact-head
  completion receipt is valid and sufficient.
- The terminal missing-task-evidence recovery transition, whose preconditions
  and append-only planning-bundle behavior stay unchanged.

## Rollout and Rollback

Ship one patch release after focused and full-fleet candidate validation. Keep
the original campaign blocked until the patch is current, then use its explicit
corrective recovery transition to return PR #180 to publication without
discarding any prior receipt. Rollback is to leave the campaign and PR paused;
do not rewrite controller or consumer history.
