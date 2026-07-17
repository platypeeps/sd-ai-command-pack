# Add archived task JSONL placeholder preflight

## Goal

Prevent generated `_example` rows from being committed with newly completed or
archived Trellis tasks without making existing historical scaffolds or active
planning tasks fail the review preflight.

## Requirements

- Extend the generic JavaScript review preflight and its shipped template twin.
- Inspect changed Trellis task context in `.trellis/tasks/**`.
- Treat `implement.jsonl` and `check.jsonl` as completion artifacts when their
  task is archived or its `task.json` status is `completed`.
- Parse each non-empty JSONL line and fail when a parsed object owns an
  `_example` key. Report the file and line with an actionable cleanup message.
- Inspect sibling context files when a changed `task.json` completes a task,
  even if those context files are otherwise unchanged.
- Skip active planning/in-progress task scaffolds, untouched legacy archives,
  symlinked files, and paths outside the repository.
- Keep the review preflight usable without project dependencies and preserve
  Node 16.9 compatibility.
- Keep the default remote review cycle limit at five; this task does not alter
  review-round policy.

## Acceptance Criteria

- [x] A newly archived task containing an `_example` row fails preflight with
  its exact file and line.
- [x] An active task newly marked `completed` is checked through its sibling
  `implement.jsonl` and `check.jsonl` files.
- [x] Planning task scaffolds and untouched archived history do not fail.
- [x] Real JSONL context entries pass, and symlinked context files are skipped.
- [x] Source/template parity and focused regression tests pass.
- [x] Distributed documentation and the review-preflight runtime contract
  describe the new check.
- [x] Release metadata and candidate fleet evidence are updated for the shipped
  payload change.

## Notes

- Historical archives currently contain generated seed rows. They are
  deliberately grandfathered unless their task completion artifacts change.
- Generic malformed-JSONL schema enforcement is outside this task's scope.
- Changing Trellis's upstream task scaffolding is outside this repository's
  ownership and is not required for this preventive guard.
