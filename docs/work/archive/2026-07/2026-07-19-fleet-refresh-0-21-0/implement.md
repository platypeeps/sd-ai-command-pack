# Fleet refresh 0.21.4 implementation plan

## Execution Order

1. Run source preflight and record all before versions and exact commands.
2. Process rwbp-coordinator as the first fast canary.
3. Process loadsmith as the second fast canary.
4. Process hoa-manager as the third fast canary.
5. Process rwbp-website.
6. Process mezmo_benchmark.
7. Process se-ai-command-pack.
8. Process anomaly-metric-creator last.
9. Rerun source preflight and verify every available consumer is at target.
10. Record aggregate results, finish the Trellis session, and archive the task.

## Per-Consumer Checklist

1. Verify clean status, default branch, remote synchronization, and no existing
   refresh PR for 0.21.4.
2. Fast-forward the default branch and create
   `codex/refresh-sd-ai-command-pack-0-21-4`.
3. Run the preflight-printed installer and expected-platform audit commands.
4. Run the consumer-documented full-check gate.
5. Inspect the diff and require only installer-owned changes.
6. Commit, push, and create the consumer PR using a literal body file.
7. Watch CI and review state; address only consumer integration findings.
8. Run the consumer housekeeping gate to merge and clean.
9. Verify 0.21.4 provenance, expected-platform audit, clean default branch, and
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
creation. After all merges, rerun preflight and require seven `at-target` rows.

## Review Gates

- No dirty consumer is mutated.
- No consumer is processed concurrently with another.
- No PR opens before install, audit, and consumer validation pass.
- No merge occurs outside the consumer housekeeping gate.
- No consumer product code is included in a refresh diff.
- Post-merge provenance and audit must agree on 0.21.4.

## Rollback Points

- Before PR creation: stop on the local refresh branch and report the failure.
- After PR creation: leave the PR open and report its blocker; never force-push
  or bypass checks.
- After merge: preserve completed consumers; stop the remaining rollout only
  for a confirmed released-pack defect requiring a patch release.
