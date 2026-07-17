# Ship PR 144

## Goal

Carry PR #144 through the standard SD publish, review, watch, merge, and housekeeping chain without bypassing stage gates.

## Requirements

- Use the default `sd-ship` stop-point, `until=merge`.
- Reuse PR #144 and the current feature branch; do not create a duplicate pull
  request or force-push.
- Run the standard stages in order: `sd-create-pr`, `sd-review-pr`,
  `sd-watch-pr`, then `sd-housekeeping`.
- Preserve every delegated stage's local checks, remote-review loop, CI wait,
  unresolved-thread guard, and failure/blocked stop behavior.
- Let `sd-housekeeping` remain the only merge authority and perform the
  post-merge branch/ref cleanup.
- Record and publish the Trellis task and session state produced by the stage
  workflows.

## Acceptance Criteria

- [ ] Stage 1 reuses PR #144 and publishes any task/spec bookkeeping.
- [ ] Stage 2 completes with deterministic checks green and no unresolved
  actionable review feedback.
- [ ] Stage 3 observes required CI and reviewer state settled green.
- [ ] Stage 4 merges only through the housekeeping gate.
- [ ] Final checkout is on the default branch, clean, synchronized with its
  remote, and free of stale feature-branch refs.

## Notes

- This is a lightweight operational task; no new product or architecture
  design is required.
