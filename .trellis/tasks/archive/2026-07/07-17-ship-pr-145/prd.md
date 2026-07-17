# Ship PR 145 lifecycle ownership fix

## Goal

Carry PR 145 through deferred review, no-merge watch, Stage 4 finish-work, merge, and post-merge cleanup.

## Requirements

- Reuse open PR #145 on `codex/align-ship-finish-work-boundary`; do not create
  a duplicate pull request.
- Run Stage 2 review with the composite-only `defer-finish-work` mode so this
  task remains active through review and watch.
- Run Stage 3 with `no-merge`; Stage 4 housekeeping is the sole finish-work,
  merge, and cleanup authority.
- Preserve every delegated check, review-thread, CI, head-parity, and merge
  gate without weakening or bypassing it.
- Leave the repository on a clean, current default branch with the feature
  branch removed locally and remotely after the verified merge.

## Acceptance Criteria

- [ ] PR #145 has a clean deterministic review result, green CI, and no
  unresolved review threads on its final pre-finish-work head.
- [ ] Stage 2 explicitly defers finish-work and Stage 3 settles green without
  invoking housekeeping.
- [ ] Stage 4 archives this task, records the session, pushes and validates any
  finish-work commits, and merges PR #145 through the housekeeping gate.
- [ ] Post-merge cleanup leaves `main` clean and equal to `origin/main`, with
  the feature branch absent locally and remotely.

## Notes

- This is operational shipping follow-through for an already-implemented and
  reviewed change; a PRD-only task is sufficient.
