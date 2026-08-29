# Stabilized-release fleet rollout implementation plan

## Pre-start gate

- Keep this task in planning until the single-merge stabilization task and all
  eleven work packages are archived, its cumulative matrix passes, and the
  successor release is published.
- Confirm a successor release newer than 0.55.5 contains the required fixes
  and that its candidate-validation ledger and current manifest describe the
  exact installable payload.
- Run live fleet status and select every manifest consumer below that verified
  successor release.
- Keep `anomaly-metric-creator` no-touch while it is dirty or has unrelated
  active work.
- Do not wait for upstream Trellis adoption or publication. If final
  integration exposes a Trellis-owned failure, first prove whether the pack or
  local Trellis checkout can compensate safely; stop only when neither can.

## Execution

1. After the release gate passes, start this task and invoke `sd-fleet-refresh`
   from the clean source checkout.
2. Run release preflight and create one controller campaign for the stale
   consumers using the manifest's normal merge-enabled policy.
3. Advance the sequential canaries through install, audit, preparation,
   validation, PR publication, review, merge, cleanup, and post-merge audit.
4. After all canaries have terminal success evidence, advance the bounded
   post-canary cohort within manifest concurrency.
5. On a pack-owned blocker, stop the campaign, record the exact evidence, and
   route the correction through a separate pack task and release before resume.
6. Recheck `anomaly-metric-creator` after its unrelated work clears; refresh it
   only when it remains below the successor release and the controller issues
   its final-cohort lane.
7. Run final fleet status and reconcile every selected consumer into the task's
   rollout results table.
8. Finish and publish this task through the normal exact-head lifecycle only
   when all terminal results and remaining blockers are explicit.

## Validation

- Source fleet preflight and controller validation before and after campaign.
- Expected-platform install audit before each PR and after each merge.
- Consumer-declared preparation and full-check gate.
- Exact-head GitHub checks, configured review backends, and unresolved-thread
  query before merge.
- Post-merge provenance, clean working tree, synchronized default branch, and
  branch deletion evidence.

## Stop conditions

- Release identity or candidate evidence is stale or invalid.
- A consumer is dirty, missing, ambiguously owned, or has an unrelated active
  task.
- Product-code or repo-policy changes appear necessary.
- Review, CI, exact-head, or housekeeping evidence is incomplete.
- A pack-owned defect requires a corrective release.
