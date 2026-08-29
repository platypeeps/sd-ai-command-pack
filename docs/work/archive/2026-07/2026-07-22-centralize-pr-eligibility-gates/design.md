# Design: shared exact-head eligibility evaluator

## Boundary

The evaluator is a pure readiness adapter over local identity plus GitHub
evidence. It emits a receipt; housekeeping remains the mutation controller.

`caller -> resolve PR/head -> collect checks -> paginate threads -> validate
finish-work/review evidence -> re-read head -> eligibility receipt`

## Result Contract

The versioned result contains:

- invocation, repository, PR, base, and full head identity;
- start/end observed head OIDs;
- required check conclusions and source URLs/IDs;
- review-thread page count, total count, unresolved count, and completeness;
- finish-work evidence identity;
- optional/required exact-head router review identity, including a router-issued
  current-head `none` decision;
- `eligible|blocked|indeterminate`, stable reason codes, and retryability;
- evaluator version and timestamps.

The schema contains evidence, not shell commands. Unknown fields are tolerated
within the major version; unknown majors fail closed.

## Caller Responsibilities

- Housekeeping revalidates the receipt identity at its mutation boundary and
  is the only caller permitted to merge.
- Update-deps decides whether a dependency PR belongs in its safe/grouped/unsafe
  classes, then invokes the shared readiness path. It never translates a
  partial receipt into eligibility.
- Review/ship may use blocked reasons for reporting but cannot override them.

## Head Changes

The evaluator reads the current head before and after collecting evidence. If
the values differ, it returns `indeterminate:head_changed` and discards the
eligibility decision. Callers may retry within their bounded policy.

Finish-work commits are ordinary new heads and rerun evidence. When routed
review is required, the evaluator accepts only a router receipt bound to the
exact new head. The router may classify a verified bookkeeping-only successor
as `none` within policy, but the evaluator does not create or infer that
classification and never treats the prior receipt as current-head evidence.

## Failure Model

- Deterministic negative evidence is `blocked`.
- Missing permissions, partial pagination, rate limits, malformed data, and
  contradictory identity are `indeterminate`.
- No error path returns `eligible` with warnings.

## Rollback

Keep the previous housekeeping implementation available only in version
history. Rollback reinstalls the prior pack version; do not retain two live
eligibility paths.
