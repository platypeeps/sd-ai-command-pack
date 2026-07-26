# Design: Journal-Only Planning Recovery

## Summary

Extend the existing `planning` final-bundle validator with a fail-closed
recovery subtype. Normal planning bundles continue to prove task changes in the
captured base-to-head range. When that exact range is journal-only, the
validator derives the earlier planning scope from the new session's referenced
work commits and proves each commit independently.

No third CLI mode is added. The result remains schema version 1 and
`mode: planning`; evidence records `planningSubtype: journal-only-recovery`.

## Validation Flow

1. Resolve and verify the captured base and checked-out final head as today.
2. Enumerate the exact base-to-head delta and reject unsupported paths.
3. Validate the new journal/index bundle and return a bounded summary of newly
   completed sessions plus their resolved commit IDs.
4. If active task artifacts changed in the exact range, run the existing
   planning validator unchanged.
5. If no task artifacts changed, require one new completed session and validate
   its resolved commits as journal-only recovery evidence:
   - every resolved ID is unique and at or before the captured base;
   - every commit has exactly one parent;
   - every parent-to-commit path belongs to an active Trellis task;
   - deletion, archive, layout, lifecycle, and baseline-state validation
     applies without retroactively rerunning current publication-quality
     content checks over already-published planning artifacts; and
   - the aggregate proves at least one task directory.
6. Emit the normal planning success code only when both journal validation and
   recovered task validation are clean.

## Data Contract

The existing JSON schema remains compatible. Successful journal-only recovery
adds bounded evidence:

```json
{
  "mode": "planning",
  "reasonCodes": ["planning_bundle_valid"],
  "evidence": {
    "planningSubtype": "journal-only-recovery",
    "taskDirectories": [".trellis/tasks/07-25-example"]
  }
}
```

Normal planning and completion results omit `planningSubtype`.

## Safety Boundaries

- A caller cannot select the subtype; repository and journal evidence select
  it.
- The validator never executes referenced commits or checkout-owned helpers.
- Parent-to-commit inspection uses Git object data and existing bounded readers.
- Merge commits are rejected rather than choosing a parent.
- A referenced commit with any non-task path is invalid even if it also changes
  a valid task.
- Recovery validates current and baseline task lifecycle records but does not
  excuse future publication from the normal planning bundle's full metadata,
  topology, context, PRD, and whitespace checks.
- The captured base and head remain immutable. Recovery never widens the final
  bundle range or rewrites the preserved journal commit.

## Compatibility

Keep `completion|planning` CLI parsing, schema version 1, and established valid
reason codes. Only evidence and new invalid reason codes expand. The
`sd-finish-work` skill documents automatic recovery and still requires the
exact retained result before its single push.

## Rollback

Revert the validator, skill, spec, and tests together. The preserved journal
commit remains local and inspectable; do not fall back to pushing after an
invalid gate.
