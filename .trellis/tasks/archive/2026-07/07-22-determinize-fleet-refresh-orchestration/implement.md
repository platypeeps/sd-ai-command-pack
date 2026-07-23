# Implementation plan: fleet refresh controller

## 1. Capture Current State Machine

- Map every current timing, wave, lane, retry, ownership, PR, review, merge,
  and reporting transition to a normalized table.
- Reuse existing helper contracts where they are already deterministic.

## 2. Add Versioned State And Controller

- Define state, event, result, reason-code, and idempotency schemas.
- Implement `plan`, `next`, `record`, `status`, `resume`, and `validate` with
  atomic persistence and JSON output.
- Reject invalid transitions and cross-release/cross-consumer state.

## 3. Integrate Owning Actions

- Adapt install, candidate check, PR, review, housekeeping, and post-merge
  results into normalized controller receipts.
- Add explicit reconciliation for ambiguous side effects.

## 4. Reduce The Skill

- Replace prose-owned timing and lane algorithms with controller invocation and
  result interpretation.
- Move rare operator recovery guidance to a conditionally loaded reference.
- Use the portable question contract only for genuine policy decisions.

## 5. Validate

- Run transition, interruption, idempotency, wave, timeout, no-touch,
  reconciliation, report, and existing fleet tests.
- Run `make sync`, `make check`, install audit, and a disposable dry campaign.

## Stop Points

- Stop if an action cannot provide an idempotency or reconciliation identity.
- Stop if controller persistence would be written into a consumer checkout
  without an explicit ignored/owned location.
