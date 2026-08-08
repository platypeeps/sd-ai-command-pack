# sd-work-backlog --workers N: parallel backlog workers

## Problem

Owner-requested feature (2026-08-08): run multiple work-backlog subagents at
the same time, with the count user-specified, in a safe and conflict-avoiding
way. Today sd-work-backlog is single-worker; nothing prevents two concurrent
sessions from claiming the same task, colliding on session numbers, or
fighting over the default branch.

## Requirements

1. `sd-work-backlog --workers N`: N concurrent workers, N user-specified.
2. Each worker runs in an isolated git worktree with its own task claim;
   claiming is conflict-safe (atomic claim marker; a claimed task is invisible
   to other workers).
3. Workers never share a checkout branch; merges to the default branch are
   serialized through the existing housekeeping gate.
4. Failure of one worker does not strand the others; the ledger records
   per-worker state.

## Prerequisites (sequence before or design around)

- 08-07-work-loop-start-discards-stopped-ledger (ledger correctness)
- 08-07-provenance-concurrent-session-collision (session numbering under
  concurrency)
- 08-08-developer-identity-not-in-worktrees (identity in worktrees)
- 08-06-upstream-add-session-numbering (collision-proof numbering)
- 08-07-status-worktree-invisibility (worktree inventory for status/cleanup)

## Acceptance criteria

- [ ] Two workers on a seeded backlog never claim the same task (stress test
      with induced races).
- [ ] `--workers 1` behavior identical to today's single-worker loop.
- [ ] Worker crash leaves a recoverable claim that housekeeping reports.
- [ ] Documentation covers count selection and resource expectations.

## Evidence

Owner directive 2026-08-08; prerequisite defects all filed and prioritized in
this consolidation.
