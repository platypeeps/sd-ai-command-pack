# Design: fleet PR head republication

## Boundary

The source-only fleet controller remains the sole state owner. No consumer file, Git ref, PR, or private state file is changed by the new transition itself. The caller still performs and verifies the remediation commit, then records the old-head review action and later executes the issued publication action.

## Transition

Introduce the stable reason code `pr-head-advanced`.

For a lane at `review` or `merge-eligibility`:

1. The issued action remains bound to publication epoch N.
2. The caller fixes and pushes the PR, but records the issued action as `retryable-failure`, `reasonCode=pr-head-advanced`, using epoch N's published full head and PR number.
3. The controller appends that immutable receipt.
4. If this is attempt one, the lane moves to `pr-publication` with the next collision-free attempt number.
5. The next publication action reuses the PR and records the newly classified full head, establishing epoch N+1.
6. Normal exact-head validation resumes for review, eligibility, merge, and post-merge receipts.

Generic retryable failures retain the existing same-stage retry behavior. If the head-advance result occurs on attempt two, the lane becomes `retry-exhausted`; it does not create a third review cycle.

## Validation Rules

- The special reason is meaningful only with `result=retryable-failure`.
- The stage must be `review` or `merge-eligibility`.
- The old-head receipt must satisfy the existing PR-head equality guard and include the established PR number.
- The transition never accepts the successor head early; only the new publication receipt can establish it.
- State validation remains epoch-based: historical PR-head receipts match the most recent preceding publication receipt.

## Compatibility

No schema fields change. Existing campaign state loads unchanged. The transition adds behavior for a previously terminal gap but does not reinterpret existing receipts.

## Operational Recovery

The active v0.54.0 campaign can use the current source controller after this task merges. It records PR #299's original review action against `7ad0fa...` as the retryable old-head result, issues publication attempt two, then records `4417acc...` as the new epoch.

## Rollback

Before merge, revert the code/spec/docs commit. After a retry receipt has been recorded, do not delete or edit it; complete the issued publication action or use normal reconciliation if the side effect is ambiguous.
