# Implementation plan: shared PR eligibility gate

## 1. Inventory Existing Gates

- Map every readiness, checks, thread, head, and merge decision in
  housekeeping, update-deps, review, ship, and tests.
- Freeze current reason/error behavior that must remain observable.

## 2. Define And Implement The Evaluator

- Add the versioned JSON schema and strict identity validation.
- Extract check collection, complete thread pagination, finish-work evidence,
  and head re-read into a read-only helper.
- Emit stable reason codes and retryability without mutation side effects.

## 3. Rewire Callers

- Make housekeeping consume the evaluator and retain final mutation-boundary
  identity checks.
- Remove update-deps' duplicate gate description/logic and route eligible
  candidates through housekeeping.
- Expose blocked/indeterminate evidence to ship/review reports without granting
  override authority.

## 4. Add Unified Review Evidence

- After `07-22-integrate-routed-review-backends` freezes its receipt, add strict
  consumption of exact-head router review, including router-issued `none`.
- Reject older heads, command-pack-local exemption claims, unknown major
  versions, and partial evidence.

## 5. Validate

- Run focused gate, housekeeping, update-deps, pagination, and exact-head tests.
- Run generated parity, `make sync`, `make check`, and install audit.
- Search live source to prove one merge mutation owner and one eligibility
  evaluator.

## Stop Points

- Stop if extraction would remove housekeeping's final mutation-boundary
  recheck.
- Stop if the unified review receipt is still provisional; land the generic
  evaluator without guessing the pending schema.
