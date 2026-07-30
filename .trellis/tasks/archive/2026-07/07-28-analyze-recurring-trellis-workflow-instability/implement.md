# Remediation implementation plan

## Package A: already-merged housekeeping routing

Owner: `07-28-route-housekeeping-by-pr-lifecycle-state`, a focused child of
`07-22-streamline-sd-skill-workflows`.

1. Follow the child task's converged PRD, design, and implementation plan.
2. Add a feature-branch PR lifecycle dispatcher to the canonical housekeeping
   template and synchronize the root mirror.
3. Route `OPEN`, `MERGED`, `CLOSED`, and unavailable/ambiguous states as
   specified in `design.md`.
4. Reuse the initial PR identity for cleanup-only work; reread after an actual
   merge before deletion.
5. Update the housekeeping result composer/docs so cleanup-only results carry
   `eligibility: null` without being treated as incomplete.
6. Add fixtures for:
   - already-merged PR returns clean in one run;
   - open eligible PR still merges and cleans;
   - open blocked PR remains untouched;
   - closed-unmerged PR produces one anomaly;
   - unavailable/ambiguous PR identity fails closed;
   - head mismatch prevents deletion.
7. Run focused housekeeping/result/eligibility tests, shell checks, template
   parity, `make sync`, and `make check`.

## Package B: environment-blocked contract

Owner: `07-28-standardize-environment-blocked-recovery-evidence`, a separate
child of `07-22-streamline-sd-skill-workflows`.

1. Follow the child task's converged PRD, design, and implementation plan.
2. Inventory current typed result schemas and every known environment-bound
   mutation call before selecting the schema location/version.
3. Define the shared bounded blocker fragment and compatibility behavior.
4. Add one reusable composer per implementation language; do not parse
   arbitrary stderr or execute recovery automatically.
5. Integrate incrementally at recorder, finish-work, housekeeping, work-loop,
   KB, and cache boundaries while retaining each command's current exit code.
6. Update skills so they report the checkpoint, distinguish repository defects
   from environmental blocks, and request only the smallest exact retry.
7. Add fixtures for clean failure, partial recoverable mutation, retry
   idempotency, unsafe/malformed diagnostics, symlink boundaries, and missing
   authority.
8. Prove no environment-blocked path reaches merge, branch deletion, archive,
   force operations, or broad cleanup.
9. Run focused command suites, result-schema compatibility tests, template
   parity, install audit, `make sync`, and `make check`.

## Operational sequence

1. Start `07-28-stabilize-self-hosted-delivery-lifecycle` and use its one
   branch/PR/merge plan for every pack-owned remediation. Commit this planning
   surface as the first branch commit; do not publish a planning-only PR.
2. Execute the eleven work packages in the umbrella design order, with focused
   commits, tests, local reviews, and `progress.md` checkpoints but no
   intermediate finalization or merge.
3. Run the bounded cumulative self-hosting matrix and release preparation,
   then archive the umbrella and all completed work packages through one
   validated completion bundle and one housekeeping merge.
4. Publish a successor release newer than 0.55.5, then execute
   `07-28-roll-out-stabilized-pack-release-to-fleet` once.

Independently, reconcile upstream Trellis bookkeeping locally and route the two
accepted upstream gaps through `07-28-harden-add-session-retry-convergence` and
`07-28-restore-install-safe-opencode-mem-reader`. This lane does not block step
4 unless final integration proves it is absolutely required; publication
remains separately approval-gated.

## Pre-start review gate

- Confirmed 2026-07-28: existing task artifacts remain separate acceptance
  contracts but their implementation is delivered through one umbrella PR.
- Confirmed: environment-blocked support is a typed diagnostic/retry contract,
  not automatic privilege escalation.
- Confirmed: upstream Trellis reconciliation remains outside the pack tasks.
- The umbrella and every work package remain in planning; obtain explicit
  implementation approval before `task.py start`.
- The fleet rollout child also remains in planning and is explicitly blocked
  on the pack remediation, final integration, and successor release.
  `handoff.md` is the canonical entry surface for a new session.
