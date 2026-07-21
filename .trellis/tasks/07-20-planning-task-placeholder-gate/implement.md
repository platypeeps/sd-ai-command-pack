# Reject Placeholder Context in New Planning Tasks Implementation Plan

## Execution Order

1. Rewrite the context-seed inspection set to include only diff-changed
   `implement.jsonl` and `check.jsonl` artifacts, independent of task status.
2. Make result text lifecycle-neutral and preserve aggregate failure behavior.
3. Update focused tests for planning-task rejection, multi-file reporting,
   empty and grounded acceptance, and unchanged historical exclusion.
4. Copy the canonical template script to its root mirror and verify byte
   equality.

## Validation Plan

1. Run the focused review-preflight test covering task context seeds.
2. Run `python3 -m unittest tests.test_review_preflight`.
3. Run `cmp -s templates/scripts/sd-ai-command-pack-review-preflight.mjs scripts/sd-ai-command-pack-review-preflight.mjs`.
4. Run `make check`.

## Documentation And Spec Updates

Update the frontend adapter guideline only if implementation reveals a durable
contract not already captured by the template-authority and deterministic
preflight rules. Include the normal release metadata update during shipping.

## Review Notes

- Confirm a planning task fails before `task.py start` when its changed context
  still contains a top-level `_example` row.
- Confirm changing only `task.json` does not scan untouched context files.
- Confirm both affected context paths appear in one failed run.

## Rollback Points

The change is isolated to one preflight function, its messages, and tests. A
rollback restores the prior lifecycle-gated selection and synchronized mirror.

## Follow-Ups

None planned; broader JSONL schema validation is outside this task.
