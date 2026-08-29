# Fleet refresh 0.15.6 implementation plan

## Execution Order

1. Run source preflight and record all before versions and exact commands.
2. Process rwbp-coordinator as the first fast canary.
3. Process loadsmith as the second fast canary.
4. Process hoa-manager as the third fast canary.
5. Process rwbp-website.
6. Process mezmo_benchmark.
7. Process anomaly-metric-creator last.
8. Rerun source preflight and verify every available consumer is at target.
9. Record the aggregate outcome in the Trellis journal and archive this task.

## Per-Consumer Checklist

1. Verify clean status, default branch, remote synchronization, and no existing
   refresh PR for 0.15.6.
2. Fast-forward the default branch and create
   `codex/refresh-sd-ai-command-pack-0-15-6`.
3. Run the preflight-printed installer and expected-platform audit commands.
4. Run the consumer-documented full-check gate.
5. Inspect the diff and ensure it contains only installer-owned changes.
6. Commit, push, and create the consumer PR with a literal body file.
7. Watch CI and review state; address only consumer integration findings.
8. Run the consumer housekeeping gate to merge and clean.
9. Verify 0.15.6 provenance, expected-platform audit, clean default branch, and
   absence of the refresh branch.

## Validation Commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-preflight.py

python3 scripts/sd-ai-command-pack-install-audit.py \
  --repo <consumer> \
  --expected-platform claude \
  --expected-platform gemini \
  --expected-platform github \
  --expected-platform opencode
```

Each consumer additionally runs its documented full-check command before PR
creation. After all merges, rerun preflight and require six `at-target` rows.

All nine execution steps are complete. Every manifest consumer advanced from
0.15.5 to 0.15.6 through its sequential refresh PR, passed pre-PR and
post-merge audit, and ended clean on its default branch. Final fleet preflight
reports six `at-target` rows and no stale consumer.

## Review Gates

- No dirty consumer is mutated.
- No consumer is processed concurrently with another.
- No PR opens before install, audit, and consumer validation pass.
- No merge occurs outside the consumer housekeeping gate.
- No consumer product code is included in a refresh diff.
- Post-merge provenance and audit must agree on 0.15.6.

## Rollback Points

- Before PR creation: stop on the local refresh branch and report the failure.
- After PR creation: leave the PR open and report its blocker; never force-push
  or bypass checks.
- After merge: preserve completed consumers; stop the remaining rollout only
  for a confirmed released-pack defect requiring a patch release.
