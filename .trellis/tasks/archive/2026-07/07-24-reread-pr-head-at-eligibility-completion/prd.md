# Re-read PR head at eligibility completion

## Goal

Make local-branch pull-request eligibility fail closed when the PR head changes
or becomes unreadable after evidence collection.

## Confirmed Evidence

- The quality contract requires every eligibility result to re-read the PR head
  after collecting evidence and return retryable `indeterminate` when it
  changes.
- `evaluate_local_branch.finish()` currently re-reads only
  `refs/heads/<branch>` before returning. The initial PR head is collected, but
  it is not queried again by PR number at completion.
- PR #232 merged with a non-outdated unresolved Copilot thread identifying this
  exact gap. Housekeeping's later `--match-head-commit` remains a mutation
  backstop, but it does not make an earlier stale `eligible` receipt correct.

## Dependencies And Boundaries

- Parent: `07-22-streamline-sd-skill-workflows`.
- Preserve the completed shared eligibility evaluator and housekeeping as the
  only merge mutation owner. This is a focused correctness fix, not a new
  eligibility implementation.
- `07-24-support-planning-only-pr-finalization` depends on this final PR-head
  proof. Land this task first, or reconcile it in the same reviewed cutover,
  before that task changes the finalization evidence carried by eligibility.
- The user approved implementing this task on PR #244 as the smallest
  bootstrap implementation. Update that PR's planning-only description and
  rerun its review gates before merge; do not leave the published scope stale.
- Land before the final routed-review/program integration matrix relies on the
  evaluator's exact-head receipt.

## Requirements

- R1: Retain the discovered PR number and initial full `headRefOid` in
  local-branch evaluation, then query that exact PR number for `headRefOid`
  again inside the common completion path after checks and review-thread
  evidence have been collected.
- R2: Compare strict full commit OIDs. A changed final PR head returns
  retryable `indeterminate` with `head_changed`; a missing, unauthorized,
  malformed, non-string, non-OID, timed-out, or failed final read returns
  retryable `indeterminate` with a stable unavailable reason.
- R3: Continue to re-read the local branch head and preserve existing
  local/remote/PR equality, finish-work, checks, thread, and merge-state gates.
  No result may remain `eligible` after either local or PR final-head evidence
  changes or becomes unavailable.
- R4: Bind the output evidence to both initial and final PR head observations
  through the existing versioned result contract. Preserve
  `pullRequest.headOid` as the initial observation and add the nullable,
  additive `pullRequest.finalHeadOid` field for the final observation in both
  modes; retain the current `head` fields for schema-major-1 compatibility.
- R5: Keep the evaluator read-only and bounded. It must not fetch, push, merge,
  resolve threads, update labels, or retry indefinitely.
- R6: Update template source first and synchronize the root mirror; preserve
  housekeeping's exact receipt validation and `--match-head-commit` backstop.

## Acceptance Criteria

- [x] Local and PR heads stable throughout evaluation can return eligible when
  every other gate passes.
- [x] A PR head that advances while the local branch remains stable returns
  retryable `indeterminate:head_changed` and never eligible.
- [x] The final lookup uses the retained PR number rather than the branch name,
  and the receipt records both initial and final PR OIDs.
- [x] Final PR lookup failure, timeout, malformed JSON, missing field, invalid
  type, and invalid OID each fail closed without a traceback or mutation.
- [x] Local-head change behavior and dependency-PR double-read behavior retain
  their existing contracts.
- [x] Mutation-spy tests prove no Git/GitHub write was introduced, and
  housekeeping still checks the mutation-boundary head.
- [x] Focused eligibility and housekeeping tests, template/root parity,
  `make sync`, and `make check` pass.
- [x] PR #244 accurately describes the mixed planning/implementation scope and
  is re-reviewed at the final implementation head.

## Out Of Scope

- Changing review-provider routing or bookkeeping-successor policy.
- Weakening unresolved-thread, successful-check, finish-work, or merge-state
  requirements.
- Treating `--match-head-commit` as a substitute for a correct eligibility
  receipt.
