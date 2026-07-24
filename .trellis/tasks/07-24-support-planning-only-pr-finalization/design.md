# Design: planning-only PR finalization

## Design Summary

Extend the SD finalization boundary, not upstream Trellis. A deterministic
helper classifies and validates the exact PR range, the SD finish-work wrapper
performs either completion or planning bookkeeping, and the shared eligibility
evaluator independently verifies the resulting typed evidence before
housekeeping may merge.

The user continues to invoke the same finish/review/ship/housekeeping surface.
There is no public planning-mode selector and no second merge path.

## State Model

| Mode | Preconditions | Task mutation | Session mutation | Result |
| --- | --- | --- | --- | --- |
| `completion` | Started task is complete and pre-archive validation passes | Archive selected completed tasks | Record one journal entry; clear pointers only through archive semantics | Typed completion receipt |
| `planning` | Exact PR range is proven planning-only and any active task is a preserved planning task in that closure | None | Record one journal entry; preserve active pointer | Typed planning receipt |
| blocked/indeterminate/failed | Scope, identity, lifecycle, or validation is not proven | None after the owning stop boundary | No duplicate or partial publication | Typed failure result |

Planning is a positive proof, not the inverse of completion. Unrecognized state
never defaults to planning.

## Components

### Canonical finalization evaluator

Add a versioned helper in the canonical template script surface. It accepts
bounded JSON containing repository/PR identity, full base and candidate head
OIDs, active-task identity when present, and the requested operation stage. It
derives the mode and emits one typed result.

The helper reuses the validator from
`07-24-validate-finish-work-bookkeeping-before-push` for artifact and journal
rules. Its additional responsibility is exact-range classification:

1. resolve and validate full base/head commit identities;
2. require linear ancestry and inspect every intervening tree entry without
   rename inference;
3. allow only regular non-executable planning-task and final-journal files;
4. reject archive paths, task deletions, lifecycle changes away from planning,
   unsupported modes, and any non-Trellis path;
5. validate changed tasks plus their affected parent/child closure; and
6. bind the result to the current repository, PR, base, and head.

The helper does not execute checkout-owned code, call providers, write task
state, record the journal, push, review, or merge.

### SD finish-work orchestration

The canonical `sd-finish-work` wrapper asks the helper for a pre-finalization
decision after its normal clean-tree and ownership checks.

- `completion` delegates to Trellis archive behavior, then records the journal.
- `planning` skips the Trellis finish-work archive step and records the journal
  through `sd-ai-command-pack-record-session.py` while preserving the active
  pointer and every task lifecycle field.
- any other result stops before a mode-specific mutation.

After journal creation, run final-bundle validation over the entire local
successor range and emit the final receipt. The wrapper remains responsible for
at most one push after all finalization commits exist.

### Typed receipt

The receipt shape is versioned and bounded. A representative planning result is:

```json
{
  "schemaVersion": 1,
  "status": "valid",
  "mode": "planning",
  "repository": "platypeeps/sd-ai-command-pack",
  "pullRequest": 244,
  "baseOid": "<40-char oid>",
  "headOid": "<40-char oid>",
  "changedTaskIds": ["add-bookkeeping-only-ci-fast-lane"],
  "activeTask": {
    "id": "add-bookkeeping-only-ci-fast-lane",
    "status": "planning",
    "preserved": true
  },
  "journalCommit": "<40-char oid>",
  "reasonCodes": ["planning_finalization_valid"]
}
```

The exact schema may include bounded validation details, but must not carry
absolute paths, arbitrary command output, or a caller-selected success mode.

### Eligibility and housekeeping

Replace the bare finish-work head request with the typed finalization contract.
The eligibility evaluator recomputes the exact-range classification or verifies
the receipt against the same helper and current Git/GitHub identities. A valid
receipt is one input to eligibility, never its whole decision.

Checks, review threads, merge state, local/remote/PR equality, and the final PR
head read remain independent gates. Housekeeping receives one eligible receipt,
performs its existing mutation-boundary head check, merges, verifies GitHub's
merged identity, and cleans only the proven branch. Status reports the
finalization mode and preserves a planning active task as expected state.

## Data Flow

1. User invokes the existing finish/review/ship/housekeeping workflow.
2. The finalization evaluator classifies the committed PR range.
3. SD finish-work performs completion or planning bookkeeping.
4. The canonical validator checks the whole final bundle.
5. One successor push publishes the final head.
6. Required CI and review settle on that exact head.
7. Eligibility independently verifies finalization plus all existing gates.
8. Housekeeping merges and cleans; the planning task remains active on `main`.

## Idempotency And Recovery

Use repository state, journal commit identity, and existing session content as
the retry key. A rerun must distinguish:

- no finalization started;
- valid local journal commit not yet pushed;
- pushed head awaiting checks/review;
- valid exact-head receipt awaiting housekeeping; and
- already merged/cleaned state.

Do not create a second journal entry or receipt for the same work/base/head
tuple. Malformed or partial local state remains inspectable and blocks before
push; the helper never resets, amends, deletes, or rewrites it.

## Compatibility And Cutover

- Update every canonical template, generated adapter, root mirror, helper,
  test, help/catalog entry, and manifest/provenance record in one cutover.
- Remove `--finish-work-head`, `finishWorkRequired`, `finishWorkHead`, and their
  compatibility readers after all internal callers use the typed evidence.
- Coordinate with the pending final-head reread task to avoid two competing
  eligibility schemas or sequential rewrites of the same boundary.
- No upstream Trellis change is needed; completion still delegates to Trellis,
  while planning finalization is owned by the SD wrapper.

## Rollback

Rollback is release-level: reinstall the last known-good pack and leave the PR
open. Do not fall back to a caller assertion, manually archive a planning task,
clear its pointer, or merge outside housekeeping. Local journal commits remain
recoverable and unpushed when validation fails.

## Trade-offs

- Independent recomputation adds a small local validation cost, but prevents a
  mode flag from becoming an unsafe merge bypass.
- Automatic internal selection keeps the command surface clean, but therefore
  requires stronger deterministic classification and explicit typed reporting.
- Replacing the bare attestation is a larger cutover than adding a planning
  flag; it removes ambiguous trust rather than preserving two evidence models.
