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
   `toStage == fromStage`. Add `kind` to the record `recover_pack_blocker`
   constructs at `:1287-1299` — `:1300` is the only append site in the file.

   Set `SCHEMA_VERSION = 2` (`:30`) and add a v1 migration arm to
   `_normalize_state` (`:341`) that backfills `recoveries: []` when absent,
   backfills `kind: "pack-blocker"` on every recovery row lacking it, and sets
   `schemaVersion = 2`. This is the operator decision on `C-N-1`; the bump is
   intended, not a stop condition. Two specifics:

   - The existing backfill branch is gated on
     `state.get("schemaVersion") == SCHEMA_VERSION`, which no longer matches a v1
     state once the constant is `2`. The v1 arm must do the `recoveries` backfill
     itself; do not assume the existing branch runs after it.
   - The function shallow-copies with `dict(state)`. Copy the `recoveries` list
     and each row before adding `kind`, or the caller's nested objects are
     mutated in place.

   Leave `:835` alone — it already writes `SCHEMA_VERSION`, so new campaigns
   pick up `2` with no edit. Do not add a write-back migration path; migration is
   load-time and persists through the existing atomic write at `:286`.

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

   Validate `--release` against `state["release"]`, following
   `resolve_reconciliation` (`:1326-1327`) and the receipt path (`:1133-1134`).
   Do **not** copy `recover_pack_blocker`'s release handling: it compares against
   `actual_release`, the current pack manifest version (`:1236`), because a
   corrective release is definitionally a *different* version. This transition has
   no corrective release, and a manifest comparison here would make any campaign
   unrecoverable the moment the installed pack moved past that campaign's target
   — including the paused `v0-56-1-20260729T173059Z`, whose recovery is the reason
   the task exists. Add a test pinning this: recovery succeeds with
   `--release <campaign release>` while the pack manifest reports a later version.
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
- Migration tests:
  - a `schemaVersion: 1` state with no `recoveries` key loads, migrates, and
    validates, and reports `schemaVersion: 2`;
  - a `schemaVersion: 1` state whose recovery rows lack `kind` migrates with
    every row tagged `pack-blocker`;
  - `_normalize_state` does not mutate the input mapping or its nested recovery
    rows;
  - a read-only command (`validate`, `status`) against a v1 state file leaves the
    file byte-for-byte unchanged on disk while reporting the migrated view;
  - the first mutating command against a v1 state persists `schemaVersion: 2`;
  - a `schemaVersion: 3` state is refused at `:615` with
    `campaign schemaVersion must be 2`;
  - a v2 state read by the pre-change validator is refused on the version check
    — asserted as the documented one-way rollback boundary, not as a supported
    path.
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
9. Return to `07-28-roll-out-stabilized-pack-release-to-fleet` and **abandon**
   campaign `v0-56-1-20260729T173059Z` deliberately, then plan a fresh campaign on
   the corrective release. Operator decision, 2026-07-29.

   Rationale: the campaign targets `0.56.1`, `manifest.json` is already at
   `0.56.2`, and this task publishes `0.56.3`. Recovering it would roll a
   two-versions-stale pack to eight consumers and would commit its state file to
   schema `2` one-way for no benefit. The transition's value is the permanent fix
   for a defect that recurs on every future campaign, not the rescue of this one.

   `rwbp-coordinator` re-enters the fresh campaign as an ordinary lane from its
   existing branch `chore/sd-ai-command-pack-0.56.1`, reporting `at-target` only
   if its work has merged by then. Do not clean, reset, or force that checkout;
   its uncommitted managed work is legitimate.

   Recording, not acting: abandonment is a state transition under the rollout
   task's own protocol, so perform it there rather than by editing controller
   state by hand.

   Note for the record: this weakens one of the three arguments made for the
   schema bump in `C-N-1` — "the paused campaign stays recoverable" — since it is
   now being abandoned. The bump's primary justification is unaffected: a rollback
   fails on a version check naming the cause instead of an unknown-field error
   pointing at a recovery row.

## Stop conditions

- The v1 migration arm cannot make an existing campaign load and validate at
  version `2` — stop. The bump is only acceptable because migration is
  automatic; a bump that requires operators to hand-edit state files is a
  different, larger change.
- Migration turns out to need a write-back pass or a lock upgrade to be correct,
  rather than working purely load-time before `validate_state` — stop, because
  that puts a migration inside the locking protocol.
- Implementing the transition requires changing the retry gate at `:1097` after
  all — stop, because the design explicitly chose not to touch it.
- Any test requires weakening an existing refusal to pass.

The earlier stop condition on the `SCHEMA_VERSION` bump is retired. The bump is
now the chosen path, decided by the operator on `C-N-1` and recorded in
`design.md` "Rollback" and `research/planning-adversarial-review.md`.
