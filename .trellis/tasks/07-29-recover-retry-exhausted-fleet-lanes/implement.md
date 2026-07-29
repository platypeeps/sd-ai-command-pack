# Retry-exhausted lane recovery implementation plan

## Pre-start gate

- The paused campaign `v0-56-1-20260729T173059Z` stays paused. Do not mutate any
  consumer checkout while this task is in progress.
- `rwbp-coordinator` keeps its refresh branch and uncommitted managed work
  exactly as it is. Do not clean, reset, stash, commit, or push it.

## Execution

The design's compatibility question is closed — see `design.md`, "Recovery
record". `validate_recovery` does constrain the key set, so the tagged-union
decision is made and step 1 implements it rather than re-deciding it.

1. Convert `validate_recovery` (`:559`) into a `kind` dispatch with two exact
   key sets, per `design.md`. The `pack-blocker` arm keeps every existing rule
   including `fromStage == "merge"` and `toStage == "pr-publication"`; the
   `retry-exhausted` arm requires `fromStage in LANE_STAGES` and
   `toStage == fromStage`. Extend `_normalize_state` (`:341`) to backfill
   `kind: "pack-blocker"` on any recovery row lacking it, alongside the existing
   `recoveries: []` backfill. Add `kind` to the record `recover_pack_blocker`
   constructs at `:1287-1299` — `:1300` is the only append site in the file.
   Do not bump `SCHEMA_VERSION`.

   Also make both idempotency lookups kind-aware. `recover_pack_blocker`'s
   lookup at `:1247-1254` filters only on `(consumer, fromActionId)` and then
   dereferences `existing["correctiveRelease"]` at `:1256`. Once a second kind
   shares the list, a match on a `retry-exhausted` row raises an unhandled
   `KeyError` instead of a typed `FleetControllerError`. Add
   `item["kind"] == "pack-blocker"` there and the matching filter in the new
   function. This is narrow to reach but the failure mode is an uncaught
   exception, and the tagged union is what creates it.
2. Add `recover_retry_exhausted(state, *, consumer, exhausted_action_id,
   release)` next to `recover_pack_blocker`, mirroring its structure:
   preconditions, idempotent lookup on `(consumer, fromActionId)`, recovery
   record, lane reset, `_refresh_campaign_status`, `validate_state`. Include the
   `last_receipt["attempt"] == lane["attempt"]` precondition with its own
   message. Do not add an `issuedAction` precondition — `validate_lane`
   (`:539-543`) already makes that state unloadable.
3. Implement the recovery cap as its own precondition with its own message:
   `MAX_EXHAUSTION_RECOVERIES = 2`, counting only records with
   `kind == "retry-exhausted"` matching `consumer` and the lane's stage,
   refusing at `>= 2`. Place the cap check **after** the idempotent lookup so a
   replay still returns its record when the cap is full.
4. Wire the `resume` subparser: `--recover-exhausted-consumer` plus
   `--exhausted-action`. There are **three** dispatch sites, not one, and
   missing any of them is a silent failure:

   - `:1720-1724` — the pre-lock guard that returns a read-only
     `resume_report` when all three existing selectors are `None`. The new
     selector must join that condition. Miss this and
     `resume --recover-exhausted-consumer X` falls into the read-only branch,
     prints a report, returns `0`, and performs no transition at all.
   - `:1780-1790` — the mode count. Add the new selector so all four of
     `--retry-consumer`, `--recover-consumer`, `--resolve-action`, and
     `--recover-exhausted-consumer` are mutually exclusive under the existing
     `resume accepts only one recovery mode` error.
   - `:1792-1820` — add an explicit branch for the new mode **before** the
     catch-all that currently routes to reconciliation, or the new mode falls
     through into `resolve_reconciliation`.

   Reject `--exhausted-action` when `--recover-exhausted-consumer` is absent,
   require it when the mode is selected, and reject `--corrective-release` on
   this path — all three matching how `--corrective-release` is already
   rejected at `:1725-1728` and `:1795`/`:1814`.
5. Render the recovery in the `resume` report the same way the pack-blocker
   recovery is rendered, so `--json` consumers see a consistent shape. Note that
   `status` and the resume report already copy `state["recoveries"]` wholesale
   into their payloads (`:1513`, `:1563`), so `kind` becomes visible on every
   recovery row in `--json` output, including backfilled pack-blocker rows.
6. Update `templates/**` for the `sd-fleet-refresh` SKILL and
   `references/controller-recovery.md`, correcting the permanent-park wording,
   then regenerate the `.agents/**` and `.claude/**` mirrors through the normal
   generation path rather than editing them.
7. Update `.trellis/spec/backend/manifest-and-filesystem.md` in **two** places.
   `:1406` states that exhaustion parks the lane and must describe the recovery
   transition. `:1380-1383` states that *each* recovery row "binds the consumer,
   blocking head and PR, corrective release, source action, and destination
   publication attempt" — a universal claim over recovery rows that the
   `retry-exhausted` arm contradicts by design, since it carries no head, PR, or
   corrective release. That sentence must become kind-aware. Leave the `:1344`
   pack-blocker "sole transition" sentence alone; it is scoped to merge-stage
   pack blockers and stays accurate.

## Validation

- Focused controller tests, each asserting the specific error message:
  - accepted path returns the lane to `waiting` at the exhausted stage and
    flips campaign status away from `blocked`;
  - refusal on release mismatch, unknown consumer, non-terminal lane, action ID
    mismatch, receipt/lane stage or reason disagreement, receipt attempt not
    equal to the lane attempt, and cap reached;
  - refusal for every terminal result other than `retry-exhausted` — all eight
    of `at-target`, `merged`, `pr-open`, `product-failure`, `review-finding`,
    `ownership-skip`, `permanent-incompatibility`, `operator-decision`;
  - campaign-identity refusal asserted against the existing
    `CampaignStore.load` message, not a new transition-specific one;
  - idempotent re-run returns the existing record and reports no change,
    including when the cap is already full;
  - `lane["receipts"]` is unchanged across the transition;
  - `next` issues an action for the recovered lane at the exhausted stage;
  - `resume --recover-exhausted-consumer` with no other selector performs the
    transition rather than returning the read-only report, and `resume` with no
    selector at all still returns the read-only report.
- Attempt-numbering tests, which the earlier plan omitted:
  - the recovered lane carries `attempt == 3` for a stage that burned 1 and 2;
  - one further `retryable-failure` re-terminates immediately as
    `retry-exhausted` rather than granting a fourth attempt;
  - a second recovery of the same stage yields `attempt == 4`;
  - the third distinct exhaustion is refused by the cap.
- Record-compatibility tests:
  - a state file whose recovery rows predate `kind` loads, normalizes, and
    validates;
  - a `retry-exhausted` row carrying `correctiveRelease`, `fromHead`, or
    `fromPrNumber` is rejected as an unknown field;
  - a `pack-blocker` row still requires `fromStage == "merge"`;
  - `recover_pack_blocker` run against a state that already holds a
    `retry-exhausted` row raises its typed error, never a `KeyError`.
- `controller validate` reports `valid` before and after.
- Full self-hosting check on the change.
- Generated-mirror drift check, to prove the mirrors were regenerated and not
  hand-edited.

## Rollout

7. Merge through the normal exact-head lifecycle.
8. Publish the corrective release and update the fleet manifest to that version.
9. Return to `07-28-roll-out-stabilized-pack-release-to-fleet` and resolve
   campaign `v0-56-1-20260729T173059Z` under that task's protocol: the campaign
   targets `0.56.1`, so recovering it on a controller shipped in a later version
   requires reading the released controller's own rules first. If the released
   transition cannot act on a `0.56.1` campaign, consciously abandon that
   campaign and replan on the corrective version, where `rwbp-coordinator` will
   report `at-target` only if its work has by then been merged — otherwise it
   re-enters as an ordinary lane from its existing branch.

## Stop conditions

- The `kind` discriminator turns out to require a `SCHEMA_VERSION` bump after
  all — stop and re-plan, because a bump changes campaign compatibility for
  every existing campaign. The design's `_normalize_state` backfill is what
  avoids the bump; if that backfill cannot be made to work, the condition fires.
- Implementing the transition requires changing the retry gate at `:1097` after
  all — stop, because the design explicitly chose not to touch it.
- Any test requires weakening an existing refusal to pass.
