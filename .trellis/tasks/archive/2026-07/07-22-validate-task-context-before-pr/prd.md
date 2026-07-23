# Validate task context before PR publication

## Goal

Run deterministic Trellis task metadata and context validation inside sd-create-pr before its first commit so generated _example rows and non-spec task context paths cannot be published before the later review gate.

## Requirements

- Run the existing deterministic review preflight in `sd-create-pr` after
  update-spec and path classification but before staging, committing, or
  pushing the intended branch.
- Stop publication when the preflight helper is missing or fails; preserve its
  complete diagnostic output instead of falling through to Git side effects.
- Extend the diff-scoped task-context check so changed `implement.jsonl` and
  `check.jsonl` rows may reference only `.trellis/spec/**` or
  `.trellis/tasks/**/research/**` paths.
- Continue rejecting top-level generated `_example` rows while leaving empty
  manifests and untouched historical task context outside the failure boundary.
- Keep source templates, source-checkout mirrors, public documentation,
  release metadata, and focused regression coverage synchronized.

## Acceptance Criteria

- [x] `sd-create-pr` runs the deterministic review preflight before its first
      `git add` and before any push.
- [x] A changed task context manifest containing an `_example` row fails with
      the exact manifest path and line.
- [x] A changed task context manifest containing a code, test, or other
      non-spec/non-research path fails with the exact manifest path and line.
- [x] Empty manifests and grounded spec/research entries pass.
- [x] Focused tests, generated parity, fleet candidate validation, and
      `make check` pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
