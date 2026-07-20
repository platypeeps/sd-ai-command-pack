# Recover paused work-loop checkpoints

## Goal

Allow paused checkpoint ledgers to reconcile complete verified lifecycle advances without false red context health or manual state repair.

## Background

- Downstream work-loop run `3248D9B5-9487-4DAC-9F0E-05CAB495ABB7` paused
  iteration 4 while PR #15 awaited a substantive remote review. The ledger
  recorded phase `checkpoint`, feature branch `codex/se-fact-check`, and HEAD
  `c353febc894219e4f2d61fd815518c6dd14068c0`.
- Review later succeeded, the feature advanced to
  `24e65c93a54cbeae2fac1c5a219d9d9834dc9587`, PR #15 merged, its Trellis task
  was archived, and housekeeping returned a clean `main` at merge commit
  `a50816f420c54e3e06110fac03692d92530ba31e`.
- Direct evidence recovery failed with `cannot update evidence during checkpoint
  phase`. `reconcile --observed-phase followups --verified-live-advance` also
  failed because `checkpoint` sorts after `followups`, so the helper classified
  the verified live state as a contradiction and marked context health red.
- Archived task `07-19-work-loop-same-phase-evidence-updates` documented a
  manual `checkpoint -> shipping` recovery. The autonomous resume contract does
  not persist or safely restore the checkpoint's owning lifecycle phase, so
  that workaround cannot be applied reliably from arbitrary human checkpoint
  targets.

## Requirements

- Treat checkpoint state as a control/recovery overlay rather than an ordered
  lifecycle advance. A paused ledger must retain the lifecycle phase that owns
  its next safe transition.
- Persist an explicit resume phase for newly created ready and paused
  checkpoints without replacing the human-readable checkpoint target.
- Let `reconcile --verified-live-advance` recover from a checkpoint when the
  caller supplies complete, locally verifiable current-state evidence and an
  observed phase that is a legal forward recovery from the stored resume phase.
- Validate the complete candidate state before atomically changing the phase,
  current evidence, checkpoint state, or context health.
- Preserve fail-closed red behavior for partial evidence, unverified advances,
  phase regression, changed task/base identity, conflicting PR identity,
  unverifiable commits, or an invalid feature-to-base branch transition.
- Keep schema-version-1 ledgers readable. Use an existing phase-valued target
  as the compatibility fallback; when an older checkpoint has only a human
  target, require an explicit resume phase rather than inferring from branch or
  PR names.
- Update `sd-work-backlog` resume instructions to perform checkpoint recovery
  through the supported helper contract and to re-run exact reconciliation
  before selecting more work.
- Change the canonical template first, keep the root installed mirror byte
  synchronized, and update relevant command documentation, status contracts,
  release metadata, and provenance.

## Acceptance Criteria

- [ ] A shipping-owned paused checkpoint can reconcile a complete verified
      post-merge state into `followups`, recording the default branch, merge
      HEAD, PR identity, and final shipped feature SHA atomically.
- [ ] Successful recovery clears the obsolete checkpoint, preserves stable
      task/base identity, records an amber verified-advance event, and becomes
      green after an exact reconciliation.
- [ ] The same recovery without `--verified-live-advance`, with partial
      evidence, with an illegal observed phase, or with conflicting identity or
      Git evidence remains red and does not partially update current state.
- [ ] Newly written checkpoints retain both a human target and their owning
      resume phase.
- [ ] Existing schema-version-1 checkpoints with a phase-valued target remain
      recoverable; older human-target-only checkpoints fail with a bounded
      diagnostic that names the explicit recovery argument.
- [ ] CLI regression coverage exercises pause, lock release, resume, verified
      post-pause reconciliation, exact reconciliation, result recording, and
      the return to inventory.
- [ ] Focused work-loop tests, template/root parity, release/provenance gates,
      `make check`, and the canonical full-check pass.

## Out of Scope

- Inferring GitHub merge state from the network inside the standard-library
  ledger helper.
- Weakening branch, commit ancestry, PR identity, lock, or atomic-write guards.
- Manually editing user-local ledgers as the supported recovery path.
- Automatically reopening terminal stopped runs.
- Changes to the upstream Trellis runtime.
