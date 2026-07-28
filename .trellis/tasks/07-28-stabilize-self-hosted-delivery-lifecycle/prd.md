# Stabilize the self-hosted delivery lifecycle in one merge

## Goal

Deliver every pack-owned remediation from the recurring Trellis instability
review on one branch and through one pull request and merge. Preserve focused
work-package commits, tests, and local reviews, but do not exercise the known
partial finalization workflow through intermediate planning or implementation
merges.

## Background

The affected repository is self-hosting: the same finish-work, housekeeping,
recorder, work-loop, and recovery surfaces being repaired would otherwise be
used to deliver each repair independently. Repeated intermediate merges would
re-enter the failure modes under investigation and produce avoidable recovery
work.

The current implementation supports the safer bootstrap shape:

- `sd-finish-work` accepts multiple exact task directories in one pre-archive
  gate.
- Completion-bundle validation detects and validates multiple archive moves.
- Changing multiple Trellis task directories is a soft review-scope warning,
  not a validation failure, when they form one reviewable outcome.

## Requirements

- R1: Use one branch, one PR, one finalization sequence, and one merge for the
  complete command-pack stabilization. Do not create or merge a separate
  planning-only PR first.
- R2: Treat the following existing tasks as independently verifiable work
  packages whose full PRDs and acceptance criteria remain authoritative:
  - `07-24-support-planning-only-pr-finalization`
  - `07-28-clarify-completion-housekeeping-obligations`
  - `07-28-enforce-pre-archive-acceptance-readiness`
  - `07-28-decide-housekeeping-result-schema-compatibility`
  - `07-28-validate-finish-work-receipt-path`
  - `07-28-route-housekeeping-by-pr-lifecycle-state`
  - `07-25-fix-work-loop-lock-race`
  - `07-25-backlog-selector-blocked-markers`
  - `07-24-track-clean-recovery-artifacts`
  - `07-25-user-scope-toolchain-caches`
  - `07-28-standardize-environment-blocked-recovery-evidence`
- R3: Assign every included work-package task to the same feature branch and
  move it to `in_progress` before its implementation begins. Keep this umbrella
  task as the session's active task and do not reparent the existing tasks from
  their current programs.
- R4: Commit the current planning and handoff artifacts as the first bounded
  commit on the stabilization branch. Continue implementation on that branch;
  do not publish or merge those artifacts through a separate planning PR.
- R5: Implement each work package as one or more focused commits with its own
  targeted tests and local routed review. Update `progress.md` after each
  package so another session can resume without finalizing or reconstructing
  state from conversation history.
- R6: Do not invoke intermediate `sd-finish-work`, archive, housekeeping,
  release, or fleet-refresh operations. Branch pushes for durable backup are
  allowed, but no additional PR or merge may represent a partial package.
- R7: Run a cumulative self-hosting stability matrix covering completion,
  planning finalization, journal-only recovery, post-archive review successor,
  already-merged cleanup, acceptance readiness, receipt compatibility and path
  validation, interrupted recording, stale-lock recovery, blocked selection,
  recovery-artifact ownership, user-cache ownership, and typed
  `environment_blocked` retry.
- R8: Use the repaired branch-local implementation for the one final
  lifecycle. Run the canonical multi-task pre-archive gate, archive this
  umbrella and all eleven completed work-package tasks, record one bounded
  campaign journal entry, produce one exact-head completion receipt, and merge
  only through normal review, CI, and housekeeping gates.
- R9: Leave `07-28-analyze-recurring-trellis-workflow-instability`,
  `07-28-roll-out-stabilized-pack-release-to-fleet`, and the broader
  `07-22-validate-sd-workflow-program-integration` task active. The umbrella's
  matrix is the release-safety gate; the broader program task consumes this
  evidence later and does not expand this bootstrap PR.
- R10: Keep upstream Trellis changes and consumer fleet mutation out of this
  PR. Prefer pack-local compatibility; an upstream dependency is permitted
  only if the cumulative matrix proves no safe local implementation exists.
- R11: Change `templates/**` first, synchronize root/generated mirrors, update
  version and changelog metadata, and produce a current release-candidate
  ledger before the final PR review.

## Acceptance Criteria

- [ ] Exactly one stabilization PR contains the planning baseline, all eleven
      work packages, cumulative integration evidence, release metadata, and
      final task bookkeeping; no intermediate planning or implementation PR is
      opened or merged.
- [ ] Every work-package PRD acceptance criterion is satisfied with focused
      tests and a recorded local-review disposition.
- [ ] `progress.md` provides a commit-bound resumable checkpoint after every
      work package without requiring intermediate task finalization.
- [ ] The cumulative self-hosting matrix passes every R7 scenario against the
      final branch implementation.
- [ ] Canonical pre-archive validation accepts the umbrella plus all eleven
      exact work-package task directories in one read-only gate.
- [ ] The completion bundle validates every intended archive move, the single
      journal tail, and the exact final head without accepting unrelated task
      or workspace changes.
- [ ] Final local review, remote review, required CI, unresolved-thread checks,
      merge state, and exact-head evidence are clean before one housekeeping
      merge.
- [ ] Template/root parity, focused suites, shell/static checks, install audit,
      `make sync`, `make check`, and release-candidate validation pass.
- [ ] No upstream Trellis repository or fleet consumer is mutated by this PR.
- [ ] After merge, the successor release can be published without another
      command-pack code change; fleet rollout remains a separate task.

## Out of Scope

- Combining the successor release's consumer rollout into this PR.
- Completing unrelated routed-review, agent-artifact, audit, or broader SD
  program tasks.
- Publishing an upstream Trellis change.
- One giant implementation commit; atomic merge does not remove internal
  commit, test, review, or rollback boundaries.

## Notes

- Parent investigation: `07-28-analyze-recurring-trellis-workflow-instability`.
- Approved delivery decision: one atomic stabilization merge with focused
  internal work packages.
