# Release 0.30.2 CodeQL cleanup annotation

## Goal

Publish the source-owned comment-only correction surfaced by rwbp-coordinator PR #170, validate the full fleet candidate, and tag 0.30.2 before resuming rollout.

## Requirements

- Keep the runtime behavior unchanged: temporary-file cleanup remains
  best-effort after atomic replacement or concurrent removal.
- Update the template source of truth and installed mirror together.
- Bump the release to `0.30.2`, regenerate versioned surfaces, synchronize the
  dogfood install, and record an all-pass full-fleet candidate ledger.
- Merge and tag the corrective release before any further consumer mutation.

## Acceptance Criteria

- [x] The CodeQL-reported empty `except OSError` contains a clear intentional
  cleanup comment in both template and mirror.
- [x] Focused PR-body tests pass.
- [x] Every configured fleet candidate passes install, audit, preparation, and
  declared checks against the exact `0.30.2` payload.
- [x] `make check` passes, including release, twin, provenance, coverage, lint,
  type, workflow, and candidate-ledger gates.
- [x] The source pull request is reviewed, thread-clean, green, and ready for
  the housekeeping merge gate. The parent rollout verifies the merge and
  `v0.30.2` tag before any consumer mutation resumes.

## Notes

- Parent rollout: `07-22-enforce-housekeeping-task-archive`.
- Trigger: unresolved CodeQL thread on `rwbp-coordinator` PR #170.
