# Retry-exhausted lane recovery design

## Overview

Add one more explicit recovery transition to the fleet controller, built as a
near-copy of the existing `recover_pack_blocker` rather than a new mechanism.
That function already establishes the shape this needs: strict preconditions,
idempotency keyed on the source action, an append-only record in
`state["recoveries"]`, a lane reset, and `validate_state` before return. The new
transition differs in exactly two ways — it accepts a terminal `retry-exhausted`
lane instead of a merge-stage pack blocker, and it returns the lane to the stage
that exhausted rather than to a fixed `pr-publication`.

Reusing the existing shape matters more than the small amount of duplication it
costs. A second, differently-shaped recovery path is how a state machine grows
inconsistent invariants.

## Why not widen an existing transition

- `retry_consumer` is documented and implemented as the `ownership-skip`
  reopener and restarts the lane at `checkout-validation`. Widening it would
  both overload one flag with two different policies and restart a lane whose
  own completed work has legitimately dirtied the checkout, which
  `checkout-validation` would then reject.
- `recover_pack_blocker` is bound to a corrective release and to merge-stage
  pack blockers. A retry exhaustion is neither, and forcing a corrective release
  for an operator-side fix inverts the cost.
- `resolve_reconciliation` exists to settle `ambiguous` receipts. A
  `retryable-failure` receipt is not ambiguous — it is a decisive record of a
  real failure — and relabeling it would destroy the distinction the results
  vocabulary exists to keep.

## Transition contract

Name: `resume --recover-exhausted-consumer <name> --exhausted-action <id>`,
with `--release` required and validated against the campaign release.

`resume` already counts exactly three mutually exclusive selectors at
`:1780` — `--retry-consumer`, `--recover-consumer`, `--resolve-action` — and
raises `resume accepts only one recovery mode` when more than one is given.
The new selector joins that same tuple, making it four. `--exhausted-action` is
rejected when `--recover-exhausted-consumer` is absent, matching how
`--corrective-release` is already rejected outside `--recover-consumer`.

Preconditions, each with its own distinct error message:

1. Campaign release matches `--release`.
2. Consumer exists in the campaign.
3. Lane `status` is `terminal` and `result` is `retry-exhausted`.
4. The lane's last receipt has `result: "retryable-failure"`, an `actionId`
   equal to `--exhausted-action`, a `stage` equal to the lane's stage, a
   `reasonCode` equal to the lane's recorded blocker, and an `attempt` equal to
   the lane's `attempt`.
5. The recovery cap for this consumer and stage is not yet reached.

Campaign identity is not a precondition of this transition. `CampaignStore.load`
(`:257-262`) already refuses a mismatched `repositoryDigest` or `campaignId`
before any transition runs, and duplicating that check here would create a
second, weaker gate for the same invariant.

Precondition 4's `attempt` comparison closes a real gap. `validate_lane`
(`:509`) and `validate_receipt` (`:544`) each bound their own `attempt` to
`>= 1` but never relate the two, so a state where the supplied action matches
the right stage and reason code but not the lane's recorded exhausted attempt is
valid to the validator and must be refused here instead.

The lane's `issuedAction` is deliberately *not* a precondition. `validate_lane`
(`:539-543`) already rejects any non-`issued` lane that carries an
`issuedAction`, so a terminal lane with an issued action cannot be loaded at
all. Asserting it inside the transition would be dead code and must not be
counted as a covered refusal path.

Any other terminal result falls through condition 3 and is refused. The full
`TERMINAL_RESULTS` set (`:77-89`) is `at-target`, `merged`, `pr-open`,
`retry-exhausted`, `product-failure`, `review-finding`, `ownership-skip`,
`permanent-incompatibility`, `operator-decision`. Every member except
`retry-exhausted` is refused and keeps its existing handling.

Idempotency follows `recover_pack_blocker` exactly: look up an existing
recovery record with the same `consumer` and `fromActionId`; if found, return it
with `changed: False` and mutate nothing. Re-running the same command is safe.

## Attempt numbering and the recovery bound

This is the load-bearing decision, because the retry gate at `:1097` is
`lane["attempt"] < 2` and `_next_stage_attempt` returns `max(attempts) + 1` for
the stage — which is `3` for a stage that has already burned attempts 1 and 2.

Two options were considered:

- **Fresh budget.** Make the retry gate recovery-aware so attempts are counted
  since the last recovery, giving two more attempts per recovery. Requires
  changing `:1097`, which is the single most safety-relevant line in the retry
  path.
- **One attempt per recovery (chosen).** Set `to_attempt =
  _next_stage_attempt(lane, lane["stage"])` and leave `:1097` untouched. The
  recovered lane gets exactly one attempt; a further `retryable-failure`
  immediately re-terminates as `retry-exhausted`.

The second is chosen. It changes no existing gate, it is self-bounding, and it
matches the intent: recovery is for a cause the operator has already fixed and
verified, so one attempt is the honest amount of credit. An operator who has not
actually fixed the cause gets one attempt, not four.

Because each new exhaustion produces a new `actionId`, the idempotency key alone
would permit an unbounded recover-fail-recover cycle. So the cap in precondition
5 is explicit and separate, and is defined exactly:

- Constant: `MAX_EXHAUSTION_RECOVERIES = 2` — enough for one genuine mistake
  plus one genuine fix, short of a loop.
- Counted set: records in `state["recoveries"]` where
  `kind == "retry-exhausted"`, `consumer` matches, and `fromStage` matches the
  lane's current stage. Pack-blocker records are excluded by `kind`. Without
  that exclusion the two kinds collide at `merge`, which is a real lane stage
  and therefore a real exhaustion site, and a prior pack-blocker recovery would
  silently consume an exhaustion budget it has nothing to do with.
- Boundary: refuse when the count is already `>= 2`, so the transition succeeds
  twice and the third distinct exhaustion is refused.
- Ordering: the idempotency lookup runs **before** the cap check. Re-running an
  already-recorded recovery must keep returning that record with
  `changed: False` even once the cap is full; a replay is not a third use.

## Recovery record

The original plan assumed `state["recoveries"]` accepted heterogeneous rows.
It does not. `validate_recovery` (`:559-589`) applies `_strict_fields` with one
exact key set — `consumer, correctiveRelease, fromActionId, fromAttempt,
fromBlocker, fromHead, fromPrNumber, fromStage, recordedAt, toAttempt, toStage`
— where `_strict_fields` (`:331-338`) raises on both a missing and an unknown
key, and `:586-587` hard-requires `fromStage == "merge"`. `validate_state`
(`:709`) runs that validator over every row. A record without
`correctiveRelease`/`fromHead`/`fromPrNumber`, or with
`fromStage: "local-checks"`, is rejected outright, which would break the
"`validate` reports `valid` before and after" acceptance criterion.

**Decision: tagged union on a `kind` discriminator, with `SCHEMA_VERSION` bumped
to `2` and a load-time migration.** The version bump is an operator decision on
`C-N-1`, recorded in `research/planning-adversarial-review.md`.

`validate_recovery` becomes a dispatch on `kind`:

```
kind: "pack-blocker"
  consumer, correctiveRelease, fromActionId, fromAttempt, fromBlocker,
  fromHead, fromPrNumber, fromStage, kind, recordedAt, toAttempt, toStage
  fromStage == "merge", toStage == "pr-publication"   (unchanged rules)

kind: "retry-exhausted"
  consumer, fromActionId, fromAttempt, fromBlocker, fromStage, kind,
  recordedAt, toAttempt, toStage
  fromStage in LANE_STAGES, toStage == fromStage
```

Each arm keeps its own exact key set, so neither kind can borrow the other's
fields. The retry-exhausted arm carries no `correctiveRelease`, `fromHead`, or
`fromPrNumber` because no corrective release, PR, or head is involved.

Records persisted before this change have no `kind`, and `_strict_fields` would
reject them as missing it. `_normalize_state` (`:341-345`) is where the fix goes,
because it already runs before validation (`:258-259`) and already establishes
the precedent of backfilling `recoveries: []`. It gains a v1 migration arm:

```
schemaVersion == 1:
  backfill recoveries: []            when absent
  backfill kind: "pack-blocker"      on every recovery row lacking it
  set schemaVersion = 2
```

Backfilling `kind: "pack-blocker"` is correct by construction, since pack-blocker
recovery is the only kind that could have written a row before now.

Two mechanics matter here and are easy to get wrong:

- The **existing** backfill at `:342` is gated on
  `state.get("schemaVersion") == SCHEMA_VERSION`. Once `SCHEMA_VERSION` is `2`
  that gate stops matching a v1 state, so the v1 arm must carry the `recoveries`
  backfill itself rather than relying on the existing branch to run afterwards.
- `_normalize_state` currently shallow-copies with `dict(state)`. Adding `kind`
  to rows means copying the `recoveries` list and each row it touches, or the
  function mutates the caller's nested objects in place.

Migration is load-time and in-memory. A read-only command (`status`, `validate`)
normalizes a v1 campaign to v2 and reports on it without writing; the migrated
`schemaVersion: 2` persists only when a mutating command reaches the atomic
write at `:286`. That is the behavior that keeps the paused
`v0-56-1-20260729T173059Z` inspectable before anyone commits to migrating it.

The `(consumer, fromActionId)` global uniqueness rule at `:717` is unchanged and
applies across both kinds. Action IDs derive from campaign, release, consumer,
stage, and attempt, so the two kinds cannot collide on one.

The record is appended; nothing is removed.

## Lane reset

`attempt = to_attempt`, `blocker = None`, `result = None`, `status = "waiting"`,
stage unchanged. Then `state["updatedAt"]`, `_refresh_campaign_status`, and
`validate_state` — the same closing sequence as `recover_pack_blocker`.

That closing sequence is what returns the campaign from `blocked` to `active`,
and the path was traced rather than assumed. `_lane_observations` (`:904`) maps
`retry-exhausted` with `packBlocker: false` to observed state `failed`; the wave
planner (`fleet-wave-plan.py:186-195`) sees a canary in `TERMINAL_STATES` that
is not a success state and returns `stopStarting: True` with reason
`canary health is incomplete at <name>`; `_refresh_campaign_status` (`:1408`)
turns that into `status: "blocked"`. After the reset the lane is `waiting` at a
mid-lane stage, so `:904` no longer matches, the stage is neither
`checkout-validation` nor `merge`, and the mapping falls through to `in-flight`
— not terminal, so no failed canary, so `stopStarting` is false and the campaign
is `active` again.

`next` is unaffected by the raised attempt number: eligibility at `:945` filters
only on `status != "waiting"` or `result is not None`, and never reads
`attempt`.

## Receipt preservation

The transition writes only to `state["recoveries"]` and to the lane's own
scalar fields. It never touches `lane["receipts"]`. The pre-existing
`retryable-failure` receipts remain byte-for-byte, which is what keeps the
campaign's audit trail honest about the fact that the stage did fail twice.

## Compatibility

- Additive: two new flags and a new function. No existing signature, result
  value, or stage list changes.
- `validate_recovery` gains a `kind` dispatch and the pack-blocker arm gains one
  required key. Forward compatibility holds: the pack-blocker arm keeps every
  rule it has today, and the `_normalize_state` v1 arm supplies `kind` for rows
  written before the change, so a new controller reads every existing campaign.
- `SCHEMA_VERSION` moves from `1` to `2`. New campaigns are written at `2`
  (`:835`). Existing v1 campaigns migrate on load and are rewritten at `2` by
  the first mutating command.
- Backward compatibility does **not** hold, by decision — see "Rollback" below.
- Campaigns created before this change recover normally, since the transition
  reads only fields that already exist on the lane.

## Documentation

Two surfaces need updating, not one.

**Shipped skill.** `templates/**` is the source of truth. Update the
`sd-fleet-refresh` skill and `references/controller-recovery.md`, then
regenerate the `.agents/**` and `.claude/**` mirrors. The reference's current
line 34-35 — "After attempt exhaustion, create or reuse a scoped task and leave
the lane parked" — describes a permanent stop and must be corrected to describe
parking followed by this transition.

**Repository spec.** `.trellis/spec/backend/manifest-and-filesystem.md` is the
executable controller contract and currently contradicts this change at `:1406`:
"Retryable failure -> one new attempt; exhaustion parks with a stable reason."
That line must gain the recovery transition. The neighbouring `:1344` sentence —
`--recover-consumer` is "the sole transition from a terminal merge-stage pack
blocker" — stays true exactly as written, because it is scoped to merge-stage
pack blockers, which this transition does not touch. Shipping the code without
the `:1406` change would leave the repository internally contradictory.

## Rollback

An earlier draft claimed a rolled-back controller would find the new record
"simply inert". That was false. `_normalize_state` gives *one-way* compatibility
only: a new controller reads old rows because normalization runs before
validation (`:258-259`), but nothing makes an old validator accept a row carrying
`kind`. `_strict_fields` (`:331-338`) rejects unknown keys, so a rollback breaks
**every** `load()` of a campaign that used this transition, not just the recovery
path.

**Migrating a campaign to schema 2 is therefore one-way. Rolling the controller
back does not roll a migrated campaign back.** The bump makes that fact legible
rather than avoidable.

Rollback of the code is a plain revert. Its effect depends on campaign state:

- A campaign never loaded by the new controller is untouched and still at
  version `1`. The reverted controller reads it normally.
- A campaign migrated and then written by the new controller is at version `2`.
  The reverted controller refuses it at `:615` with
  `campaign schemaVersion must be 1` — a precise, actionable error naming the
  real cause. This is the reason the bump was chosen over keeping version `1`,
  where the same revert would instead produce an unknown-field error from
  `_strict_fields` that points at a recovery row rather than at the version skew.
- There is no downgrade path. A campaign that must survive a controller rollback
  has to be recreated on the reverted version, or the rollback deferred.

The paused `v0-56-1-20260729T173059Z` is readable but not yet migrated, because
migration only persists on a mutating command. Recovering it on the corrective
release is the act that commits it to version `2`. That is a deliberate,
operator-visible step, not a side effect of inspecting it.

A third shape — a separate top-level state key instead of a tagged union — was
rejected. An old validator rejects an unknown top-level key identically, so its
rollback cost is the same while it also splits one invariant across two lists.
