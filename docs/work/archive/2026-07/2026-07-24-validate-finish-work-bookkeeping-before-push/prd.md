---
title: Validate finish-work bookkeeping before push
status: done
created: 2026-07-24
branch: codex/validate-finish-work-bookkeeping-before-push
---
# Validate finish-work bookkeeping before push

## Goal

Prevent invalid task/archive/journal bookkeeping from reaching GitHub by
validating the tasks before archive and the complete finalization bundle before
its single push.

## Confirmed Evidence

- A recent direct-main bookkeeping push ran full CI and failed because
  `.trellis/tasks/archive/2026-07/07-23-mark-future-triggered-tasks-parked/task.json`
  had a blank description despite a sibling PRD.
- The repository test that found the defect scans archived tasks, while the
  runtime changed-task preflight does not currently require a non-empty task
  description.
- The installed Trellis finish-work skill archives tasks and then records the
  journal. The pack wrapper improves journal recording but does not run one
  authoritative post-finalization bookkeeping validation before later callers
  push, nor can it validate a planning finalization that intentionally has no
  archive move.

## Dependencies And Boundaries

- Parent: `07-22-streamline-sd-skill-workflows`.
- `07-24-add-bookkeeping-only-ci-fast-lane` consumes the same validator for its
  cheap exact-head CI lane and must not implement a second metadata policy.
- `07-24-implement-read-only-sd-check` may invoke the validator read-only but
  does not own archive or journal mutation.
- `07-24-support-planning-only-pr-finalization` depends on this task publishing
  an explicit planning-finalization validation mode. That task owns mode
  selection, typed finalization evidence, and merge-flow composition.
- Implement entirely in the command pack. Do not modify or publish upstream
  Trellis without separate explicit approval.

## Requirements

- R1: Add one versioned, read-only bookkeeping validator with concise human
  output and a typed JSON result. Reuse existing task metadata, topology,
  context-placeholder, journal, and whitespace rules rather than creating
  parallel interpretations.
- R2: Before archive, validate every exact task selected for completion:
  bounded regular task JSON and PRD files, non-empty `id`, `name`, title, and
  description, directory/identity agreement, legal lifecycle fields,
  timestamps, base/feature branch semantics, parent/child reciprocity, and
  context files without generated placeholders.
- R3: After journal recording, validate the complete mode-specific
  finalization delta. `completion` requires supported active/archive layout,
  completion metadata, and archive move identity. `planning` requires changed
  tasks to remain valid active planning tasks with no archive, completion, or
  session-pointer mutation. Both require journal/index agreement, real
  summary/change/test content, known work commits, placeholders, and whitespace.
- R4: The pre-archive failure stops before Trellis mutation. A post-finalization
  failure stops before push, reports exact recovery steps, and preserves the
  local commits for inspection; it never amends, resets, drops, or publishes
  automatically.
- R5: `sd-finish-work`, the review/ship finalization tail, housekeeping, local
  pre-publication, and bookkeeping-only CI consume the same validator and
  stable reason codes.
- R6: Preserve the current commit ordering and at most one final push per
  finalization attempt. Do not combine archive and journal commits merely to
  optimize CI.
- R7: Bound paths and messages, reject symlinked/non-regular/oversized or
  invalid-UTF-8 artifacts, and never expose absolute repository paths in
  durable or JSON output.
- R8: Keep exact-head review, CI, unresolved-thread, eligibility, and
  housekeeping gates unchanged. Local validation prevents bad pushes; it does
  not authorize a cheaper CI mode by itself.

## Acceptance Criteria

- [ ] A PRD-backed active task with a blank description fails before archive
  and produces no task or journal commit.
- [ ] A valid archive-plus-journal completion bundle and a valid
  planning-task-plus-journal bundle both pass locally and the identical
  fixtures pass the bookkeeping CI lane under distinct typed modes.
- [ ] Invalid lifecycle metadata, topology, archive layout, context
  placeholders, journal/index state, commit references, or whitespace stop
  before push with stable field/path diagnostics.
- [ ] Post-finalization failure preserves recoverable local commits without
  pushing or mutating unrelated paths.
- [ ] Finish-work performs one post-bundle validation and later callers reuse
  its exact result instead of rerunning divergent checks.
- [ ] Focused validator, finish-work, housekeeping, preflight, and CI fixtures,
  generated parity, `make sync`, and `make check` pass.

## Out Of Scope

- Changing upstream Trellis task/archive behavior.
- Selecting completion versus planning finalization or authorizing merge.
- Migrating untouched historical archives repository-wide.
- Treating local bookkeeping validation as review or merge authority.
