# Support same-phase work-loop evidence updates

## Goal

Let the autonomous work-loop ledger record expected HEAD and PR evidence changes within an active lifecycle phase without false red contradictions.

## Requirements

- Add a supported controller operation for recording verified mutable evidence
  while the logical phase remains unchanged. At minimum, shipping must be able
  to record the commit created by Stage 1 and the resulting PR number/URL.
- Define which `current` fields are stable identity (`task`, expected branch)
  and which may legitimately advance (`head`, `prNumber`, `prUrl`,
  `lastShippedSha`, and final branch/head at a verified merge boundary).
- Keep phase transitions and evidence updates distinct enough that an update
  cannot skip lifecycle phases or replay a side effect.
- Make `reconcile --verified-live-advance` useful for verified evidence
  advances within one phase, not only for a later observed phase.
- Preserve fail-closed red contradictions for a different task, unexplained
  branch, regressed HEAD, conflicting PR, or unverified lifecycle advance.
- Update `sd-work-backlog` orchestration instructions to use the supported
  operation after commits, PR publication, pushed review fixes, finish-work
  commits, and merge evidence instead of checkpoint detours.
- Clear or supersede stale ready checkpoints after a successful recovery so
  status reports do not keep directing an active loop to an obsolete phase.
- Keep user-local state atomic, bounded, private where supported, and backward
  compatible with existing schema-version-1 ledgers.

## Acceptance Criteria

- [x] A `shipping` ledger can record a newly committed HEAD and newly created PR
      without an illegal same-phase transition or red context health.
- [x] A pushed review-fix or finish-work commit can advance the recorded HEAD
      without a checkpoint workaround.
- [x] A verified merged PR can record final default-branch/merge-commit evidence
      before follow-up processing.
- [x] Same-phase updates reject a changed task, an unrelated branch, a
      conflicting PR number, a non-descendant HEAD where Git evidence is
      available, and unknown current-state fields.
- [x] `reconcile --verified-live-advance` distinguishes a legitimate evidence
      advance from a contradiction and retains red behavior for unverified
      mismatches.
- [x] Successful recovery clears obsolete checkpoint state and produces a
      green, internally consistent status snapshot.
- [x] Focused tests cover create/push/review-fix/finish-work/merge advances,
      invalid updates, old ledgers, atomic failure, and resume behavior.
- [x] Shared skills, command docs, generated mirrors, and canonical checks pass.

## Notes

- Reproduced twice in work-loop run
  `212A7A6B-EE55-45B2-921F-4C5E2483CA9F`:
  - after PR #170 merged, reconciling the clean default-branch state against
    the remembered feature-branch HEAD produced a false contradiction;
  - during PR #171 Stage 1, commit `bd09d60` and PR publication were normal
    shipping progress, but `shipping -> shipping` was illegal and reconcile
    marked the expected HEAD change red even with `--verified-live-advance`.
- The safe manual recovery was `shipping -> checkpoint`, then
  `checkpoint -> shipping` with updated evidence, followed by exact reconcile
  to restore green health. That proves recoverability but is too brittle for
  every autonomous iteration.
- This changes the core state-machine contract and requires `design.md` plus
  `implement.md` before implementation.
