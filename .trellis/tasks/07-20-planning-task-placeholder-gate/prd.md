# Reject placeholder context in new planning tasks

## Goal

Extend deterministic review preflight so newly added planning-task check and implement context files cannot retain generated _example scaffold rows.

## Requirements

- Inspect newly added or changed Trellis task `check.jsonl` and
  `implement.jsonl` files for generated `_example` scaffold rows regardless of
  whether the task is planning, in progress, completed, or archived.
- Fail review preflight with the exact task path and a direct instruction to
  replace the scaffold with grounded context or leave the file empty.
- Scope the new enforcement to files introduced or changed by the review diff;
  do not make unrelated historical planning tasks block a PR.
- Keep empty context files and valid `{\"file\": ..., \"reason\": ...}` rows
  accepted.
- Add focused regression coverage and keep the canonical template script and
  source-checkout mirror synchronized.

## Acceptance Criteria

- [x] A new planning task containing an `_example` row fails review preflight.
- [x] The failure identifies every affected context file in one pass.
- [x] An empty planning-task context file passes.
- [x] Grounded context rows continue to pass.
- [x] Unchanged historical planning tasks remain outside the new diff-scoped
      failure boundary.

## Notes

- Review-derived follow-up from PR #184.
- This is a focused preflight/test update; implementation begins in work-loop
  iteration 8.
