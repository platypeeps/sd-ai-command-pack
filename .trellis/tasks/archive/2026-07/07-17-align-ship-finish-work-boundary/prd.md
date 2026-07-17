# Align finish-work ownership in sd-ship lifecycle

## Goal

Ensure sd-ship runs finish-work exactly once at the composite merge boundary without breaking standalone sd-review-pr behavior.

## Requirements

- Standalone `sd-review-pr` must continue to run Trellis finish-work after a
  clean review loop.
- `sd-ship until=review` must retain the standalone review behavior and finish
  the current Trellis work before stopping.
- `sd-ship until=merge` must defer finish-work during Stage 2 so the active
  task remains available through the watch and merge tail.
- In the merge-through path, Stage 3 must watch without invoking housekeeping;
  Stage 4 must invoke housekeeping exactly once and remain the sole merge
  authority.
- A blocked or timed-out Stage 3 must leave the active task unarchived for a
  later resume.
- The change must not weaken local checks, remote-review convergence, CI
  waiting, unresolved-thread checks, merge guards, or standalone
  `sd-watch-pr` behavior.
- The lifecycle contract must be reflected in shipped shared skills,
  installed mirrors, consumer documentation, project specs, focused tests,
  and release metadata.

## Acceptance Criteria

- [x] The review skill defines an explicit composite deferral mode that is
  accepted only from `sd-ship` when the chain continues to merge.
- [x] Standalone `sd-review-pr` and `sd-ship until=review` still run
  finish-work after a clean review loop.
- [x] `sd-ship until=merge` invokes Stage 2 with finish-work deferred, invokes
  Stage 3 with its existing `no-merge` mode, and invokes housekeeping once in
  Stage 4.
- [x] Blocked Stage 3 guidance preserves the active task for a later resume.
- [x] Focused lifecycle-contract and generated-parity tests pass.
- [x] Canonical repository checks and the fleet candidate validation pass.

## Notes

- This is a prompt-orchestration ownership fix; no Trellis-owned file may be
  modified.
