# Implementation plan: backlog and design workflow simplification

## 1. Classify Backlog Paths

- Map normal and rare sections to helper reason codes and current tests.
- Confirm every recovery invariant remains owned after extraction.

## 2. Add Conditional Recovery References

- Create bounded references for terminal reconciliation, stopped/red recovery,
  ledger migration, and exceptional ownership cases.
- Make the core skill load only the reference selected by typed helper output.

## 3. Add Typed Design Selection

- Normalize selector and stop-boundary parsing in `sd-work-backlog`.
- Cover design completion, design-to-merge continuation, no eligible task, and
  resumed run behavior.

## 4. Retire `sd-work-designs`

- Remove source and generated targets, help/catalog/docs/config references, and
  completion metadata.
- Register installed paths for provenance-aware retirement with no alias.
- Coordinate live review-command references with the routed-review cutover.

## 5. Validate

- Run focused backlog state/recovery/selector/retirement tests.
- Compare normal-run loaded context before and after without weakening content.
- Run `make sync`, `make check`, install audit, and applicable fleet validation.

## Stop Points

- Stop if a recovery path lacks a deterministic helper reason code; add the
  typed state first rather than guessing from prose.
- Stop before removing the old surface until all generated target paths are in
  the retirement inventory.
