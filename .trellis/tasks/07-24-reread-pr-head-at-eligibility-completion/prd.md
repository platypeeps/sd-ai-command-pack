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
  through the existing versioned result contract, updating schema/spec
  documentation only as required by its compatibility rules.
- R5: Keep the evaluator read-only and bounded. It must not fetch, push, merge,
  resolve threads, update labels, or retry indefinitely.
- R6: Update template source first and synchronize the root mirror; preserve
  housekeeping's exact receipt validation and `--match-head-commit` backstop.

## Acceptance Criteria

- [ ] Local and PR heads stable throughout evaluation can return eligible when
  every other gate passes.
- [ ] A PR head that advances while the local branch remains stable returns
  retryable `indeterminate:head_changed` and never eligible.
- [ ] Final PR lookup failure, timeout, malformed JSON, missing field, invalid
  type, and invalid OID each fail closed without a traceback or mutation.
- [ ] Local-head change behavior and dependency-PR double-read behavior retain
  their existing contracts.
- [ ] Mutation-spy tests prove no Git/GitHub write was introduced, and
  housekeeping still checks the mutation-boundary head.
- [ ] Focused eligibility and housekeeping tests, template/root parity,
  `make sync`, and `make check` pass.

## Out Of Scope

- Changing review-provider routing or bookkeeping-successor policy.
- Weakening unresolved-thread, successful-check, finish-work, or merge-state
  requirements.
- Treating `--match-head-commit` as a substitute for a correct eligibility
  receipt.
