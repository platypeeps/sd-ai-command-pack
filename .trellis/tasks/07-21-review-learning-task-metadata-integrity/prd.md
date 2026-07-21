# Enforce Trellis task metadata integrity in review preflight

## Goal

Add changed-task validation for identity, lifecycle, and branch-target invariants repeatedly caught during review.

## Background

Recent review signals repeatedly found task bookkeeping defects after the
implementation itself was complete:

- PRs #189 and #197 recorded a feature branch as `base_branch`.
- PR #169 described completed work while task metadata remained
  `in_progress`.
- PRs #167 and #154 exposed inconsistent task identifiers, references, or
  version-bearing names.
- PRs #149 and #184 found generated context scaffolds; that case is already
  covered by the current preflight and must remain covered without duplicate
  logic.

The current preflight rejects completed active-root tasks and changed context
scaffolds, but it does not validate the broader changed-task metadata contract.

## Requirements

- Extend the canonical review preflight and template twin with one coherent
  changed-task metadata check rather than scattered special cases.
- Inspect newly added or changed `.trellis/tasks/**/task.json` records. Avoid a
  repository-wide historical migration gate.
- Validate identity invariants:
  - `id` and `name` are non-empty strings and equal;
  - the dated task-directory suffix matches `name` for active and archived
    layouts;
  - parent/child links reference existing task directories and are reciprocal
    when both records are in the checkout.
- Validate lifecycle invariants:
  - `status` is one of `planning`, `in_progress`, `review`, or `completed`;
  - `planning`, `in_progress`, and `review` records have `completedAt: null`;
  - `completed` records have a non-empty completion timestamp and remain under
    the archive tree;
  - the existing completed-active-root guard remains authoritative.
- Validate branch-target invariants:
  - `base_branch` is a non-empty string;
  - when `branch` is present, it is a non-empty string distinct from
    `base_branch`;
  - stacked work remains supported; do not require `base_branch` to equal
    `main`.
- Fail closed with path- and field-specific diagnostics for malformed JSON,
  unsafe symlink traversal, or unverifiable changed records.
- Add regression coverage for valid active, archived, child, and stacked-task
  records plus every rejected invariant.
- Keep root/template preflight copies byte-equivalent and update relevant
  adapter guidance if the author-time contract changes.

## Out of Scope

- Rewriting historical archived metadata that is not changed by the branch.
- Parsing free-form prose to validate every backticked task reference.
- Enforcing a single repository branch name or forbidding stacked PRs.
- Replacing Trellis's own `task.py` lifecycle operations.

## Acceptance Criteria

- [ ] A changed task with mismatched `id`/`name` or directory suffix fails with
      an actionable field-specific message.
- [ ] Invalid completion-state combinations fail without changing task files.
- [ ] A changed task whose `branch` equals `base_branch` fails, while a valid
      stacked base branch passes.
- [ ] Missing or one-sided parent/child links are detected without rejecting
      valid standalone tasks.
- [ ] Unchanged historical records do not become new blockers.
- [ ] Existing scaffold and completed-root checks retain their behavior and
      tests.
- [ ] Canonical tests, template parity, install audit, and full-check pass.

## Notes

- Evidence source: `docs/review-learnings.md`, refreshed 2026-07-21.
