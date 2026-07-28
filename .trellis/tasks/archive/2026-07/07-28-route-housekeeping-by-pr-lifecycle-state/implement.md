# Housekeeping PR-lifecycle routing implementation plan

## Implementation

1. Inventory the existing PR lookup, merge, cleanup, anomaly, and result
   composition functions in the canonical housekeeping and result templates.
2. Introduce the smallest internal PR-state dispatcher that reuses existing
   provider parsing and exact-head proof helpers.
3. Route `OPEN`, `MERGED`, `CLOSED`, and indeterminate states according to
   `design.md`; remove the unconditional merge-then-cleanup call sequence.
4. Pass the initially resolved identity into cleanup-only work. After an actual
   merge, refresh provider state before cleanup.
5. Make cleanup-only result composition emit `eligibility: null` and reconcile
   schema compatibility with
   `07-28-decide-housekeeping-result-schema-compatibility`.
6. Update the canonical docs and skill guidance only where observable behavior
   changes, then synchronize generated and root mirrors.
7. Add the new scenarios to the workflow-program integration task's eventual
   matrix.

## Validation

- Add focused coverage in `tests/test_housekeeping.py` and
  `tests/test_housekeeping_result.py` for every acceptance case.
- Preserve `tests/test_pr_eligibility.py` behavior for open PRs.
- Run focused tests for housekeeping, result composition, and PR eligibility.
- Run shell syntax/static checks used by the repository.
- Run `make sync`, generated parity checks, and `make check`.
- Validate the task artifacts before `task.py start` and do not start until the
  user reviews this plan.

## Risk and rollback

- Highest risk: deleting a branch using stale or mismatched PR evidence.
  Prevent it with an exact-head mismatch fixture and provider reread after
  merge.
- Compatibility risk: changing a schema-version-1 result field. Resolve it
  explicitly rather than silently altering the payload.
- Rollback restores the prior dispatcher only; receipt and eligibility formats
  remain authoritative and no migration state is written.
