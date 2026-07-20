# Fleet Refresh 0.23.3 Implementation Plan

## Preparation

1. Verify `manifest.json`, tag `v0.23.3`, and the full-fleet candidate ledger.
2. Run source fleet preflight and preserve the reported before versions, exact
   install/audit commands, local paths, and priority order.
3. Activate this task only after the PRD and design agree with the live report.

## Per-Consumer Loop

For rwbp-coordinator, loadsmith, hoa-manager, rwbp-website, mezmo_benchmark,
se-ai-command-pack, then anomaly-metric-creator:

1. Confirm the checkout exists, is clean, and can fast-forward its default
   branch; otherwise record a skip without mutation.
2. Create `codex/sd-pack-0-23-3-refresh` from the synchronized default branch;
   the already-open coordinator canary may retain its original branch name.
3. Run the preflight-provided install and expected-platform audit commands.
4. Run the consumer's documented full-check or equivalent validation gate.
5. Review the diff for installer ownership, receipts, provenance, secrets, and
   repository integration only; commit, push, and open a scoped refresh PR.
6. Wait for required checks and review state, address rollout-owned findings,
   and merge only through the consumer housekeeping gate.
7. Confirm the consumer returns clean to its synchronized default branch with
   installed version `0.23.3` and a passing post-merge audit.

## Finalization

1. Rerun source preflight and require every available consumer to be
   `at-target`, or record exact stale/PR-open/skipped outcomes.
2. Check every PR and local/remote rollout branch state, then update the PRD
   acceptance evidence.
3. Archive this source task and record one source journal session with the
   consumer PRs, review outcomes, and any follow-up tasks.

## Rollback Points

- Before installation: delete no state; a clean skipped checkout is unchanged.
- Before PR creation: leave a failing refresh branch intact for inspection and
  do not advance if the released pack is defective.
- After PR creation: preserve the PR and branch when the gate cannot merge;
  report the blocker rather than rewriting history.
