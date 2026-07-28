# Stabilized-release fleet rollout design

## Overview

Run one resumable source-owned campaign after the remediation program has
passed final integration and shipped as a verified successor release. The
controller is the durable state machine; each consumer remains an isolated
transaction whose mutation is owned by that consumer's checkout and Trellis
task.

The successor-release gate avoids two fleet mutations: deploying the known
partial 0.55.5 behavior and then replacing it again after stabilization.

## Cohorts and scope

At execution time, select every manifest consumer below the successor release
and use the order and concurrency declared in `docs/fleet/consumers.json`:

1. Sequential canaries: `rwbp-coordinator`, `loadsmith`, `hoa-manager`.
2. Bounded post-canary cohort: `rwbp-website`, `mezmo_benchmark`,
   `se-ai-command-pack`, and `sd-github-review`, with manifest concurrency.
3. `anomaly-metric-creator`: solo final cohort, but only after its unrelated
   active work is clean.

It must not infer a need to reinstall a consumer that preflight proves is
already at the exact target.

## Release gate

The rollout controller may be planned only after
`07-28-stabilize-self-hosted-delivery-lifecycle` and all of its work packages
are archived through the single merge, its cumulative self-hosting matrix
passes, and release preparation produces a current full-fleet candidate ledger
for the successor payload. The broader program-integration backlog is not part
of this release gate. Upstream Trellis tasks remain
separately owned and do not block the pack release. Prefer a pack-local
compatibility boundary or a local-only Trellis checkout fix. Escalate an
upstream dependency only when final integration produces a reproducible safety
failure and proves that neither local option can satisfy the release
invariants.

## Consumer transaction

For every controller-issued lane:

1. Prove a clean synchronized default branch and unambiguous Trellis ownership.
2. Create or resume the dedicated consumer refresh task and branch.
3. Run the exact installer and expected-platform audit from source preflight.
4. Run declared `candidatePrepare`, inspect the diff for managed integration
   changes, and run the consumer's full check.
5. Publish or reuse one PR, run the configured review cycle, remediate only
   integration findings, and rebind every gate to the exact successor head.
6. Merge through installed housekeeping when the controller issues the merge
   action; merge does not require an extra rollout approval.
7. Verify the clean default branch, target provenance, install audit, and
   branch cleanup before recording the terminal receipt.

## Failure handling

- Dirty, missing, or ambiguously owned checkout: record a blocker without
  mutation.
- Consumer-owned validation or review finding: keep the consumer PR open and
  report it; do not edit unrelated product behavior under this task.
- Pack-owned integration blocker: stop new starts and unsettled merges, create
  a corrective pack task/release, and resume with the controller's
  corrective-release protocol.
- Interrupted action: reconcile issued action evidence through controller
  `resume`; never replay side effects from remembered conversation state.
- Advanced PR head: use the documented bounded republication retry and restart
  exact-head evidence for the new epoch.

## Evidence and handoff

The campaign state is private operational state, while the task records a
compact durable table containing consumer, before version, controller result,
branch/PR, exact head, checks, review disposition, merge, final version, and
blocker. The final source fleet status is the closure check.

## Boundaries

- No force installation, force push, forced merge, destructive cleanup, or
  mutation of dirty consumer work.
- No consumer product changes or upstream Trellis changes.
- No bypass of release identity, candidate evidence, review, CI, exact-head,
  finish-work, housekeeping, or post-merge audit gates.
