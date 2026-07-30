# Add a fleet-controller recovery transition for retry-exhausted lanes

## Goal

Give the fleet controller a safe, evidence-gated way to continue a consumer lane
whose per-stage retry budget was exhausted, once the operator has fixed the
cause and can prove it. Today that state is a dead end: the lane is terminal,
every `resume` transition rejects it, and because canary cohorts are sequential,
one exhausted lane stalls the entire campaign.

## Observed failure

Campaign `v0-56-1-20260729T173059Z`, release `0.56.1`, 2026-07-29. The
`rwbp-coordinator` canary lane failed `local-checks` twice. Both failures were
defects in the consumer refresh task's own artifacts — personal absolute paths
in `prd.md`, then generated `_example` scaffold rows in `check.jsonl` and
`implement.jsonl`, then task-context rows outside the allowed spec/research
roots. Neither failure involved the pack payload or consumer product code.

The install itself was clean and stayed clean: provenance `0.56.1`, install
audit `178 targets checked`, vouched hashes matching, and 29 changed paths all
installer-managed or that task's own artifacts.

After the artifacts were corrected, the consumer's documented full gate passed
end to end — `Full check complete`, exit 0, `56 passed (27.8s)`, review preflight
with zero failures. The cause was fixed and provably fixed. The controller still
had no way to continue: `next` returned `[]`, campaign status `blocked`, and the
seven remaining lanes sat `waiting` at `checkout-validation`.

## Current behavior

- `scripts/sd-ai-command-pack-fleet-controller.py:1097` allows a retry only
  while `lane["attempt"] < 2`, so a stage gets two automatic attempts.
- `:1087` sets the counter on `passed` via `_next_stage_attempt`, which is
  `max(attempts recorded for that stage, default=0) + 1` (`:1213-1219`). It is
  not a reset to `1`: it yields `1` only on first entry to a stage, and carries
  forward for a stage re-entered later — as the `pr-head-advanced` path at
  `:1099-1101` does when it sends a lane back to `pr-publication`. The budget is
  therefore per stage rather than per lane, and is consumed cumulatively across
  every entry into that stage. This behavior is correct and does not change.
- `:1104-1107` makes the lane terminal with result `retry-exhausted` and records
  the reason code as the lane blocker.
- No `resume` transition accepts that lane state:
  - `retry_consumer` (`:1199`) requires a terminal `ownership-skip`.
  - `recover_pack_blocker` requires a terminal `review-finding` with
    `packBlocker: true` at `merge`.
  - `resolve_reconciliation` (`:1344`) requires an existing `ambiguous` receipt;
    a `retryable-failure` receipt does not qualify.

`.agents/skills/sd-fleet-refresh/references/controller-recovery.md:34-35` states
the intended policy — "After attempt exhaustion, create or reuse a scoped task
and leave the lane parked" — but the campaign has no way to resume afterward,
so parking is permanent in practice.

## Requirements

- Add one explicit, operator-initiated recovery transition that returns a
  terminal `retry-exhausted` lane to a runnable state. It must be a deliberate
  act, never automatic, and never triggered by `next`.
- Gate the transition on evidence, not intent. At minimum require the exact
  campaign, consumer, release, and the action ID of the exhausted attempt, and
  reject any mismatch.
- Resume the lane at the stage that exhausted, not from the top. Restarting at
  `checkout-validation` would demand a clean checkout that the lane's own
  completed work has legitimately made dirty.
- Preserve the full receipt history. The transition never deletes, rewrites, or
  downgrades the failure receipts that recorded the exhaustion, and does not
  write to `lane["receipts"]` at all. The recovery is recorded as its own
  append-only row in `state["recoveries"]`, which is where the existing
  pack-blocker recovery already records itself.
- Keep the existing per-stage budget of two *automatic* attempts unchanged. This
  task adds operator-authorized attempts on top of that budget, granted one at a
  time by an explicit command; it does not loosen the automatic budget and does
  not change the `:1097` gate.
- Do not let recovery mask a real failure class. Refuse the transition for
  lanes terminal on `product-failure`, `review-finding`,
  `permanent-incompatibility`, or `ownership-skip`, each of which already has
  its own documented handling.
- Bound repeated use so a lane cannot be recovered indefinitely into an
  unbounded retry loop.
- Carry the recovery-record shape change as an explicit schema version bump with
  an automatic load-time migration, so an existing campaign keeps working without
  operator intervention and a controller rollback fails on a version check that
  names the real cause. Migrating a campaign is one-way and must be documented as
  such; no downgrade path is in scope.
- Update the shipped skill and its recovery reference to document the new
  transition and to correct the "leave the lane parked" text, which currently
  describes a permanent stop.
- Update the repository's own controller contract,
  `.trellis/spec/backend/manifest-and-filesystem.md:1406`, which states that
  exhaustion parks the lane. Leaving it unchanged would ship code that
  contradicts the executable spec in the same repository.
- Treat `templates/**` as the source of truth; `.agents/**` and `.claude/**` are
  generated mirrors and must be regenerated, not hand-edited.

## Out of scope

- Changing the per-stage retry budget or making retries automatic.
- Reworking cohort sequencing so a terminal lane does not stall its cohort.
  That is a separate design question; record it as a follow-up rather than
  widening this task.
- The task-scaffold defect that caused the original failures — that generated
  `_example` rows in `check.jsonl` / `implement.jsonl` immediately fail the
  pack's own review preflight in any installed repository. Owned separately.

## Acceptance Criteria

- [x] A terminal `retry-exhausted` lane can be returned to a runnable state
      through one explicit `resume` transition, and `next` then issues an action
      for that lane at the stage that exhausted.
- [x] The transition is refused, with a distinct message, when the consumer,
      release, or exhausted action ID does not match recorded state, or when the
      supplied action's attempt is not the lane's recorded exhausted attempt.
      Campaign identity is covered by the pre-existing `CampaignStore.load`
      refusal and is asserted against that message rather than a new one.
- [x] The transition is refused for every terminal result other than
      `retry-exhausted`: `at-target`, `merged`, `pr-open`, `product-failure`,
      `review-finding`, `ownership-skip`, `permanent-incompatibility`, and
      `operator-decision`.
- [x] Repeated recovery of the same lane is bounded at two per consumer and
      stage, the bound counts only retry-exhaustion recoveries, and an idempotent
      replay still succeeds once the bound is full.
- [x] A recovered lane resumes at attempt 3 for that stage, and one further
      `retryable-failure` re-terminates it immediately as `retry-exhausted`.
- [x] Every pre-existing receipt survives the transition byte-for-byte,
      `lane["receipts"]` is not written at all, and the recovery is recorded as
      its own row in `state["recoveries"]`.
- [x] `controller validate` reports `valid` before and after the transition.
- [x] A campaign state file written at the previous schema version loads,
      migrates, and validates with no operator action, and a read-only command
      against it leaves the file unchanged on disk.
- [x] A state file at the new schema version is refused by the previous
      controller on the schema version check, and the one-way nature of migration
      is documented rather than implied.
- [x] Focused tests cover the accepted path, each refusal path, and the receipt
      preservation guarantee.
- [x] `sd-fleet-refresh` SKILL.md and `references/controller-recovery.md` are
      updated in `templates/**` and the generated mirrors regenerated, with the
      inaccurate permanent-park wording corrected.
- [x] `.trellis/spec/backend/manifest-and-filesystem.md` describes the new
      transition and no longer states that exhaustion parks the lane
      permanently.
- [x] The full self-hosting check passes on the change.

## Completion

This is the corrective pack task for the paused rollout. After it merges and a
corrective release is published, campaign `v0-56-1-20260729T173059Z` is resolved
per the rollout task's own protocol — either recovered on the released
transition or consciously abandoned and replanned on the corrective version.

## Notes

- Blocked rollout: `07-28-roll-out-stabilized-pack-release-to-fleet`.
- Failure class belongs to `07-28-analyze-recurring-trellis-workflow-instability`.
- Consumer state at pause: `rwbp-coordinator` on branch
  `chore/sd-ai-command-pack-0.56.1`, base commit
  `519acb0d6e697294128d23c835eef7893d384341`, 29 uncommitted managed paths, no
  commit, no push, no PR. Nothing was cleaned or reset.
