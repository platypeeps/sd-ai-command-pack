# Implementation plan: Fleet rollout 0.55.2

## Execution Checklist

- [ ] Start the Trellis task on the dedicated source rollout branch.
- [ ] Plan the full-fleet controller campaign and initialize timing evidence.
- [ ] Execute and record the issued immutable-release preflight.
- [ ] Repeatedly execute only controller-issued consumer actions, creating one
      dedicated Trellis task per eligible consumer during checkout validation.
- [ ] Publish, classify, review, and settle each exact PR head.
- [ ] Run exact-head eligibility and serialized managed housekeeping merges.
- [ ] Verify every merged default branch, installed version, audit, branch
      deletion, and pruned refs.
- [ ] Run controller validation/status and complete the timing report.
- [ ] Finish the source rollout task through the normal source lifecycle.

## Validation Commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py validate \
  --repo <absolute-source-root> \
  --campaign fleet-v0-55-2-20260727T135308Z --json

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py status \
  --repo <absolute-source-root> \
  --campaign fleet-v0-55-2-20260727T135308Z --json

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-timing.py \
  --repo <absolute-source-root> report \
  --run-id fleet-v0-55-2-20260727T135308Z --complete
```

## Risk and Recovery Points

- Persist a receipt before requesting another controller action.
- Pause and load controller recovery guidance for ambiguous mutations,
  exhausted retries, invalid state, or a pack-owned blocker.
- Preserve the unrelated pre-existing stash in the source checkout.
