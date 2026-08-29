# Design: Trellis task metadata integrity preflight

## Boundary

Extend the existing task-oriented section of
`scripts/sd-ai-command-pack-review-preflight.mjs` and its template twin. Reuse
the preflight's diff discovery, bounded file reads, plain-object validation,
path normalization, and diagnostic helpers. Do not add a second executable.

## Validation flow

1. Resolve the comparison diff through the existing preflight mechanism.
2. Select added or modified task records under active and archived task roots.
3. Reject symlinked or non-regular task records before reading content.
4. Parse each record as a bounded JSON object.
5. Validate identity, lifecycle, and branch-target fields.
6. Resolve parent/child directory references against the checkout and compare
   reciprocal relationships when applicable.
7. Emit one bounded diagnostic per defect and a summary PASS line otherwise.

Changed-record scoping prevents old archived exceptions from blocking an
unrelated PR while still making any touched record meet the current contract.

## Compatibility

- Support active `.trellis/tasks/MM-DD-name/task.json` and archived
  `.trellis/tasks/archive/YYYY-MM/MM-DD-name/task.json` layouts.
- Permit feature bases for stacked changes; only equality with the work branch
  is inherently contradictory.
- Preserve current task-scaffold and completed-active-root checks. Shared
  helpers may be factored only when behavior remains test-covered.

## Diagnostics

Messages name the task path, field, observed invalid relationship, and the
safe correction. Parser or filesystem uncertainty is a failure because a
changed task record cannot be vouched when it is unreadable.

## Verification strategy

Use fixture repositories in `tests/test_review_preflight.py` to cover each
field matrix, archived layouts, parent/child reciprocity, symlinks, malformed
JSON, unchanged historical records, and multi-defect aggregation. Retain
template/root parity and full-check integration coverage.
