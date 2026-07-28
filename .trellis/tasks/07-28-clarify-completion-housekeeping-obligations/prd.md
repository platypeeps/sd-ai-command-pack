# Clarify completion versus housekeeping obligations

## Goal

Define an explicit lifecycle contract that separates work a task must complete
before Trellis archives it from merge, branch cleanup, superseded-PR closure,
and other follow-through owned by `sd-housekeeping` after archive.

The contract must let a task record remain truthful at every boundary without
weakening the existing finish-work receipt, exact-head review, or housekeeping
merge gates.

## Confirmed Evidence

- In `platypeeps/rwbp-coordinator` PR #187, the completed task was archived
  before merge while its PRD still presented merge/housekeeping steps as
  unchecked acceptance criteria. Copilot discussion `discussion_r3661730449`
  correctly identified the apparent contradiction between `status=completed`
  and the unchecked criteria.
- The consumer fix had to restate the completed exact-head implementation and
  move merge, cleanup, and superseded-PR closure into a post-archive
  housekeeping handoff.
- This repository's earlier `07-06-close-fleet-refresh-loop` reconciliation
  found multiple archived tasks with unchecked post-merge acceptance criteria,
  so the ambiguity is recurrent rather than unique to PR #187.
- `sd-finish-work` owns validation, archive, journal recording, and the typed
  finalization receipt. `sd-housekeeping` remains the sole merge and cleanup
  mutation owner.

## Requirements

- R1: Define which outcomes belong in task acceptance criteria and therefore
  must be complete before `task.py archive` can truthfully mark the task
  completed.
- R2: Define one explicit, consistently named place for downstream obligations
  that can only occur after archive, such as merge, branch deletion, default-
  branch synchronization, superseded-PR closure, and post-merge fleet checks.
- R3: Update canonical `sd-finish-work`, `sd-housekeeping`, `sd-review-pr`, and
  `sd-ship` guidance so they use the same ownership boundary and do not instruct
  authors to leave required pre-archive acceptance criteria unchecked.
- R4: Preserve the existing sequence: validated implementation and task record,
  archive/journal successor, exact-head review and CI settlement, then guarded
  housekeeping mutations. Do not move merge authority into finish-work.
- R5: Keep `templates/**` authoritative and synchronize root dogfood copies,
  generated adapters, documentation, and contract tests through the normal
  pack workflow.
- R6: Include concrete authoring examples for a normal implementation task, a
  planning-only finalization, and a task with post-archive fleet or cleanup
  follow-through.
- R7: Do not require historical archived tasks to be rewritten. The contract
  applies prospectively, while known contradictions may be reconciled in their
  owning repositories.

## Acceptance Criteria

- [ ] Canonical lifecycle guidance states that every acceptance criterion
  required for task completion is satisfied before archive.
- [ ] Post-archive merge and cleanup obligations have one explicit handoff
  representation that cannot be mistaken for incomplete task acceptance
  criteria.
- [ ] `sd-finish-work`, `sd-housekeeping`, `sd-review-pr`, and `sd-ship` agree on
  the archive/review/merge ownership boundary and retain all current exact-head,
  unresolved-thread, CI, and no-touch gates.
- [ ] Examples cover completion, planning finalization, and downstream fleet or
  cleanup follow-through without introducing a second merge authority.
- [ ] Skill contract tests reject stale guidance that makes post-archive
  housekeeping mutations pre-archive completion criteria.
- [ ] Templates, root copies, generated adapters, documentation, manifest
  provenance, `make sync`, and `make check` are green.

## Notes

- Origin: consumer review finding on `platypeeps/rwbp-coordinator` PR #187,
  discussion `discussion_r3661730449`, observed 2026-07-27.
- This task defines the contract. `07-28-enforce-pre-archive-acceptance-readiness`
  implements automated enforcement after this representation is settled.
- Implement entirely in this command pack. Do not modify or publish upstream
  Trellis without separate explicit approval.
