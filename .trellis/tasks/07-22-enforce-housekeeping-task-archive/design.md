# Fleet rollout design for the housekeeping finish-work gate

## Boundary

The pack source checkout owns release identity and orchestration. Each consumer
checkout is an independent mutation boundary. Release `0.30.2` carries the
implementation under test plus the source-owned CodeQL cleanup annotation
found by the first canary. After that corrective release is tagged, this task
installs its immutable payload and does not change consumer product code.

The safety claim is a three-link proof:

1. the tagged source housekeeping self-test proves missing or stale
   `--finish-work-head` evidence cannot reach `gh pr merge`;
2. preflight proves the tag, current source payload, and candidate ledger are
   identical and valid; and
3. each consumer install audit and provenance record proves its installed
   housekeeping executable is that payload.

The rollout therefore does not run a speculative merge probe against a live
consumer PR. Normal finish-work, CI, review-thread, head-identity, and
housekeeping behavior provides the end-to-end operational validation.

## Orchestration And State

Use the existing `sd-fleet-refresh` controller and `docs/FLEET_ROLLOUT.md`.
Initialize one timing run before preflight and reuse it after interruption.
The fleet preflight, wave planner, timing record, PR state, and final audit are
the canonical per-consumer ledger.

Although the rollout has eight independently verifiable consumer outcomes,
do not create eight Trellis child tasks up front. The fleet controller already
owns bounded, resumable per-consumer state and mandatory outcome reporting;
parallel task trees would duplicate that authority. Create a follow-up or
corrective task only when a verified finding leaves real work after its
consumer outcome.

Process the three canaries sequentially, then continue conservatively one
consumer at a time in manifest order, with AMC last. Before each start or
merge decision, use the wave planner and never exceed its concurrency or merge
candidate decision.

## Per-Consumer State Machine

1. `pending`: preflight reports the consumer stale.
2. `owned`: checkout exists, tree is clean, and no active stream would be
   disturbed by branch preparation.
3. `installed`: the preflight-selected command installed `0.30.2`.
4. `validated`: expected-platform audit and consumer full-check passed.
5. `published`: the installer-only commit is pushed and represented by one PR.
6. `reviewed`: the exact head completed integration-only or remote review and
   all findings were dispositioned.
7. `settled`: required CI is green and no review thread remains unresolved.
8. `finished`: `sd-finish-work` completed, any bookkeeping commit is pushed,
   and the exact final head is green.
9. `merged`: housekeeping accepted that exact finish-work head and merged.
10. `verified`: provenance and audit report `0.30.2`, the default branch is
    clean, and refresh branches are absent according to policy.

Terminal alternatives are `at-target`, `PR-open`, `skipped`, `failed`, or
`blocked`, each with bounded evidence and timing state.

## Failure And Finding Policy

Corrective finding ledger:

| ID | Contract family | Evidence | Severity | Disposition | Fix | Regression |
| --- | --- | --- | --- | --- | --- | --- |
| CF-1 | Generated Python payload quality | `rwbp-coordinator` PR #170 CodeQL thread on `_atomic_write_body` | Pack blocker | Fix in source before more consumer mutation | Add the explanatory best-effort cleanup comment to the template and mirror; release as `0.30.2` | Existing PR-body atomic-write tests plus source full check and full-fleet candidate validation |

The bounded adjacent-surface sweep found the same empty cleanup pattern only
in source-only fleet timing code; it is not part of the installed payload and
was not the consumer finding. Other installed `except OSError` sites either
return or raise explicit diagnostics. No runtime, schema, CLI, persistence, or
normalization contract changes, so the correction is intentionally comment
only.

- Release identity or telemetry failure: stop before new mutation.
- Dirty, missing, or ownership-ambiguous checkout: skip without mutation.
- Consumer-only local-gate failure: leave the local refresh branch for
  inspection, record the reason, and continue only when it is not a pack
  compatibility signal.
- Red CI, unresolved feedback, head drift, or non-clean merge state: do not
  merge; leave the PR open and report it.
- Pack correctness, security, install/audit, compatibility, or a reproduced
  post-merge task gap on `0.30.2`: pause the fleet and enter one source-owned
  corrective campaign.
- Deferred low-risk findings: reply, resolve when allowed, and record one
  follow-up per canonical owner before continuing.

## Compatibility And Rollback

This rollout changes only vendored pack payload and its receipts/provenance.
Already merged consumers remain on `0.30.2` if a later consumer is skipped.
Before PR creation, a failure remains isolated on the unmerged refresh branch;
after PR creation, it remains an open PR. Never reset, force-push, or bypass a
consumer gate. A confirmed released-pack defect requires a corrective release,
then a fresh preflight and resume of this same rollout task.

## Source Task Completion

Publish and tag the bounded `0.30.2` source correction before resuming the
fleet from a fresh preflight. After every selected consumer has a terminal
outcome, update the PRD with the fleet table and evidence, complete the timing
report, and publish any remaining source task bookkeeping through
`sd-create-pr`, then use normal review, finish-work, and housekeeping.
