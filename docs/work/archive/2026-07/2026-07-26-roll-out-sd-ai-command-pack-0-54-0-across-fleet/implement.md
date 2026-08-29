# Fleet rollout 0.54.0 implementation plan

## Campaign identity

- Controller campaign: `fleet-0-54-0-20260726T143936Z`
- Timing run: `timing-0-54-0-20260726T143936Z`
- Release authority: `origin`
- Selected consumers: complete schema-version-4 manifest
- Merge mode: enabled
- Review mode: classifier-selected integration-only with remote fallback

## Preparation and activation

- [x] Review the converged PRD and design, then activate this task through the
      Trellis Phase 1.4 gate on a dedicated source task branch.
- [x] Generate one safe campaign ID and timing run ID from `0.54.0` plus UTC
      start time; record both in this task before executing controller actions.
- [x] Fetch tags from `origin` and prove local `v0.54.0` matches the advertised
      immutable tag.

## Campaign initialization

- [x] Run controller `plan` for the absolute source root, release `0.54.0`, all
      eight consumers, and merge-enabled mode; retain its schema/status.
- [x] Initialize timing with every manifest consumer and rollout priority.
- [x] Call controller `next`, execute only its preflight action through
      `sd-ai-command-pack-fleet-preflight.py`, bracket timing, and record the
      exact normalized receipt.

## Controller action loop

- [x] Repeatedly call controller `next`; validate and execute every returned
      action once, then record one receipt before requesting more work.
- [x] For checkout validation, reject dirty/missing/divergent/live-owned
      checkouts without stash, reset, clean, clone, or overwrite.
- [x] Run preflight-issued install/audit commands, manifest preparation/check
      commands, and each consumer's documented full local gate.
- [x] Commit only managed rollout output; classify exact base/head, push, and
      create or reuse one PR. Start reviewer and CI timing together.
- [x] Invoke `sd-review-pr` with the controller-bound fleet context and selected
      integration-only or remote profile. Inspect all existing feedback.
- [x] Classify every verified finding; stop for pack blockers or capture
      deferred owners and follow-up tasks before continuing.
- [x] Settle exact-head checks through `sd-watch-pr`, record merge eligibility,
      and allow only the controller's serialized merge action to invoke
      consumer housekeeping.
- [x] Verify post-merge version, install audit, clean default branch, deleted
      refresh branch, and pruned refs before recording the terminal result.
- [x] Respect canary order, post-canary concurrency two, AMC-last ordering, and
      the controller's manifest-ordered merge serialization.

## Final validation and reporting

- [x] Run controller `validate` and `status` after all selected consumers are
      terminal.
- [x] Finish every timing consumer result and run `report --complete`.
- [x] Update this task with the campaign ID, immutable release/preflight
      evidence, consumer result table, scheduling/retry/finding/timing summary,
      and every remaining follow-up.
- [x] Run `trellis-check`, required source bookkeeping validation, and
      `trellis-update-spec`; commit only task/session artifacts in the source
      repository, then finish work through the normal source lifecycle.

## Corrective release resolution

- Corrective task `07-26-support-taskless-fleet-refresh-finish-work` shipped in
  release `0.54.1` through PR #257 and recovered PR #177.
- Corrective task `07-26-support-fleet-pr-head-republication` shipped through
  PR #258 and recovered the later PR #299 head-advance lifecycle gap.
- Controller status is `complete`; validation is `valid`; all eight lanes are
  terminal.

## Validation commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py validate \
  --repo . \
  --campaign <campaign-id> --json

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py status \
  --repo . \
  --campaign <campaign-id> --json

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-timing.py \
  --repo . \
  report --run-id <run-id> --complete
```

## Rollback points

- Before a consumer action: stop without mutation and retain the issued action.
- After a possibly issued side effect: use controller `resume`; never replay.
- On a pack blocker: hold unsettled merges and prepare a corrective release.
- On ownership skip or consumer-local blocker: retain exact lane evidence and
  continue only when the controller issues another eligible action.
