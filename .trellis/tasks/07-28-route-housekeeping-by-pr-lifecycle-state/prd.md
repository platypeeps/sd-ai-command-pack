# Route housekeeping by pull request lifecycle state

## Goal

Make one housekeeping invocation classify the starting branch's pull-request
lifecycle and perform only the applicable merge or cleanup work, so an
already-merged exact-head branch reaches a clean result without an irrelevant
merge-eligibility failure or a second recovery run.

## Background

- The canonical housekeeping template currently invokes
  `maybe_merge_ready_open_pr "$START_BRANCH"` before
  `cleanup_current_branch_if_merged "$START_BRANCH"` at
  `templates/scripts/sd-ai-command-pack-housekeeping.sh:1227-1228`.
- Recent-session analysis found an already-merged PR that first retained
  `finish_work_missing`, then cleaned successfully only on a second run.
- Merge eligibility protects an open PR. An already-merged PR instead needs
  exact-head merge proof before local and remote branch cleanup.
- Full evidence is recorded in
  `../07-28-analyze-recurring-trellis-workflow-instability/research/recent-trellis-workflow-instability.md`.

## Requirements

- R1: Resolve one bounded PR identity and lifecycle state for the starting
  feature branch before choosing merge or cleanup work. Supported states are
  `OPEN`, `MERGED`, `CLOSED`, and unavailable or ambiguous.
- R2: For `OPEN`, retain the existing exact-head finish-work, CI, review-thread,
  merge-state, and eligibility gates. Merge only when eligible, then refresh
  GitHub state before cleanup.
- R3: For `MERGED`, skip merge eligibility and run cleanup directly against the
  exact PR head and merge evidence. Do not emit or retain
  `finish_work_missing` merely because no completion receipt is needed to
  merge an already-merged PR.
- R4: For `CLOSED`, report one stable `pull_request_not_merged` anomaly and do
  not evaluate eligibility, merge, or delete a branch.
- R5: For unavailable, malformed, or ambiguous PR identity, report one bounded
  indeterminate-state anomaly and fail closed without merge or deletion.
- R6: Preserve housekeeping as the sole merge and general branch-cleanup
  mutation owner. Preserve exact-head checks, default-branch synchronization,
  protected-main behavior, and non-destructive failure semantics.
- R7: An already-merged cleanup result must represent inapplicable eligibility
  explicitly as `eligibility: null` and may report `outcome.status: clean` only
  when delegated final status is clean and all required cleanup evidence is
  present.
- R8: Change `templates/**` first, keep root installed mirrors byte-identical,
  and update public result documentation and compatibility fixtures together.

## Dependencies and coordination

- Parent program: `07-22-streamline-sd-skill-workflows`.
- Coordinate any result-shape change with
  `07-28-decide-housekeeping-result-schema-compatibility`; do not silently
  change schema-version-1 semantics or restore caller-trusted attestations.
- Feed the new scenarios into
  `07-22-validate-sd-workflow-program-integration` before that program closes.
- This task does not depend on planning-only finalization behavior: an already
  merged PR is a distinct lifecycle state.

## Acceptance Criteria

- [ ] An already-merged exact-head PR skips eligibility, cleans local and
      remote feature branches in one invocation, and returns a clean result
      with `eligibility: null` when final delegated status is clean.
- [ ] An open eligible PR still passes exact-head eligibility, merges, refreshes
      PR evidence, and cleans safely.
- [ ] An open blocked PR is neither merged nor deleted and retains the existing
      actionable eligibility reason.
- [ ] Closed-unmerged, missing, ambiguous, malformed, and provider-failure
      fixtures each fail closed with one stable lifecycle anomaly.
- [ ] A mismatched or advanced PR head prevents deletion even when another PR
      identity reports merged.
- [ ] Result-schema compatibility tests, housekeeping tests, shell checks,
      template/root parity, `make sync`, and `make check` pass.

## Out of Scope

- Changing finish-work receipt production or planning-only finalization.
- Defining the cross-command `environment_blocked` contract.
- Weakening merge eligibility, auto-merging closed PRs, or deleting branches
  without exact-head merged evidence.
- Modifying or publishing upstream Trellis.
