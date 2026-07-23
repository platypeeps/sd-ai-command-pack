# Validate planning task topology semantics

## Goal

Add diff-scoped semantic review-preflight checks for durable planning tasks
that inherit an unrelated feature base and for active parent PRDs that omit
children declared by task metadata, while preserving intentional stacked-branch
workflows.

## Background

Review of PR #227 found two defects that passed the existing structural task
metadata checks:

- a newly created deferred planning task inherited the feature branch on which
  it was created even though its parent did not establish that stack; and
- an active parent task's `children` metadata included a task that its PRD no
  longer represented.

The current preflight correctly permits feature bases because stacked work is a
supported workflow. It also validates reciprocal parent/child metadata, but it
does not interpret the relationship between a deferred child's base and its
parent or compare an active parent's declared children with its PRD. The new
checks must add those semantics without imposing `main` as a universal base or
turning free-form Markdown into a general task-reference parser.

## Requirements

### Changed-scope boundary

- Add one coherent task-topology semantic check to the existing deterministic
  review preflight.
- Inspect added or modified active-task `task.json` files for planning-base
  inheritance. Ignore deleted old paths during moves and do not migrate
  untouched historical records.
- Inspect an active task's child representation when either its `task.json` or
  sibling `prd.md` is added or modified. A deleted changed `prd.md` remains in
  scope when the corresponding active task declares children.
- Keep archived task PRDs and unchanged active task prose outside this new
  check. Existing metadata, context, and completed-task checks remain
  authoritative for their current scopes.

### Deferred planning-base semantics

- Treat an active record as a deferred planning child only when it has
  `status: planning`, `branch: null`, and a non-empty `parent` identifier.
- Load the referenced parent through the existing safe active/archive task
  lookup. The child's `base_branch` is semantically valid when it equals either
  the parent's `base_branch` or the parent's non-empty active `branch`.
- Reject any other base with a diagnostic that names the child record, its
  observed base, and the parent-derived allowed targets.
- Preserve intentional stacks: a deferred child may target its parent's active
  feature branch. Do not require any task base to equal `main`, the remote
  default branch, or the current review base.
- Do not infer intent for standalone planning tasks or tasks that already own
  a work branch. Those cases remain governed by the existing structural branch
  invariants.
- Avoid duplicate diagnostics when the parent is already missing, malformed,
  ambiguous, or unsafe; the existing reciprocal-link validation remains the
  failure source for unverifiable linked records.

### Parent PRD child representation

- For each in-scope active task with a non-empty valid `children` array,
  safely read its sibling `prd.md` as a bounded regular file without following
  symlinks.
- Require every declared child identifier to appear as an exact delimited token
  in the PRD. Accept representation in a child-task table, dependency section,
  Markdown link, or other prose; do not require a particular heading or
  presentation format.
- Reject missing, unsafe, non-regular, oversized, or unreadable PRDs and report
  all missing child identifiers in deterministic order with bounded output.
- Treat the metadata `children` array as the enumerable source for this check.
  Do not infer additional children from arbitrary PRD references or reject
  extra historical task IDs mentioned in prose.

### Delivery

- Keep `templates/scripts/sd-ai-command-pack-review-preflight.mjs` authoritative
  and synchronize its installed root mirror.
- Extend focused executable and helper-level coverage in
  `tests/test_review_preflight.py` for the new rules and their compatibility
  boundaries.
- Update the durable review-preflight contract in
  `.trellis/spec/backend/quality-guidelines.md`.
- Because this adds a new consumer-visible rejection rule, publish it as the
  next minor release under the repository's version policy, with synchronized
  changelog and exact-payload fleet candidate evidence.

## Out of Scope

- Changing Trellis `task.py create` defaults or opening an upstream Trellis PR.
- Requiring all repositories or tasks to use `main` as their base branch.
- Rejecting intentional standalone stacks that cannot be inferred from current
  metadata.
- Parsing a dedicated PRD child-map grammar or proving that every task ID in
  free-form prose belongs in `children`.
- Rewriting unchanged active or archived task history.

## Acceptance Criteria

- [x] A changed deferred planning child whose base matches neither its parent's
      base nor active branch fails with a path-specific corrective diagnostic.
- [x] A deferred child based on its parent's durable base passes.
- [x] A deferred child based on its parent's active feature branch passes as an
      intentional stack.
- [x] Standalone planning tasks, tasks with assigned work branches, and
      unchanged historical records do not gain a new semantic blocker.
- [x] An in-scope active parent fails when any declared child is absent from its
      PRD, including when only the PRD changed.
- [x] Exact-token matching prevents a longer child ID from satisfying a shorter
      declared ID while accepting tables, dependencies, links, and prose.
- [x] Missing or unsafe in-scope parent PRDs fail closed; archived and unchanged
      PRDs remain grandfathered.
- [x] Existing metadata reciprocity, context-scaffold, completed-task, and
      stacked-base tests retain their behavior.
- [x] Template/root parity, focused tests, candidate validation, and
      `make check` pass for the release payload.

## Notes

- This is a standalone preventive preflight task rather than a new child of the
  skill-streamlining program.
- Exact child-ID presence is intentionally a one-way consistency check. A
  structured bidirectional PRD map would require a separate schema decision.
