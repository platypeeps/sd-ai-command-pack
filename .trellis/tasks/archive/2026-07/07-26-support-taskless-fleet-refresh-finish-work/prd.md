# Support taskless fleet refresh finish-work

## Goal

Correct the fleet refresh and finish-work lifecycle so consumer refreshes without an active Trellis task can produce a valid exact-head housekeeping receipt without weakening bookkeeping validation.

## Requirements

- Define one canonical Trellis lifecycle for fleet consumer refreshes that start without an active task and carry installer-managed implementation changes.
- Preserve the generic planning validator's fail-closed rule for arbitrary non-task commits; any exception must be bound to deterministic fleet release identity, installed-target scope, exact base/head evidence, and a clean single-parent history.
- Prevent future lanes from reaching PR publication without the bookkeeping evidence that their deferred finish-work tail will require.
- Provide an append-only recovery for an already-published fleet PR whose local journal commit failed final-bundle validation; do not require amend, reset, dropped commits, force-push, or fabricated historical task evidence.
- Keep fleet controller receipts, timing state, `sd-review-pr` deferral, `sd-finish-work`, and `sd-housekeeping` exact-head validation consistent across the recovery.
- Update canonical templates first and keep root installed mirrors synchronized.
- Add regression coverage for task-backed refreshes, supported taskless refresh recovery, arbitrary non-task commit rejection, stale/mismatched release evidence, and interrupted resume behavior.

## Corrective Finding Ledger

| ID | Contract family | Evidence | Severity | Disposition | Fix | Regression |
|---|---|---|---|---|---|---|
| `fleet-0-54-0-taskless-finish-work` | correctness | `rwbp-coordinator` PR #177 final-bundle planning receipt at `44f74ab1dbc19bb719fa46fc8d824340645f4c45` returned `planning_recovery_commit_scope_invalid` for the installer commit | blocker | pause corrective release | Define and implement the canonical taskless fleet finalization and append-only recovery contract | Exercise exact-head finish-work and housekeeping receipts for taskless fleet refreshes without weakening ordinary planning validation |

## Acceptance Criteria

- [ ] A fresh taskless consumer lane cannot publish a PR that its required finish-work tail is structurally unable to validate.
- [ ] A supported fleet refresh can complete finish-work and produce a schema-version-1 exact-head receipt accepted by housekeeping.
- [ ] The existing `rwbp-coordinator` PR #177 state has a documented append-only recovery that preserves commit history and does not push invalid bookkeeping evidence.
- [ ] Untrusted or ordinary non-task implementation commits still fail with stable reason codes.
- [ ] Controller recovery never replays an already-issued side effect and resumes only from authoritative receipts.
- [ ] Template/mirror parity checks, focused fleet/validator tests, install audit, and `make check` pass.

## Notes

- Origin campaign: `fleet-0-54-0-20260726T143936Z`, consumer `rwbp-coordinator`, PR #177.
- The invalid private finish-work receipt was generated before push or merge; the local journal commit must remain unpushed and unmodified for recovery inspection.
- This task owns the released-pack blocker. Deferred style findings from the same PR remain in their separate P3 follow-up tasks.
