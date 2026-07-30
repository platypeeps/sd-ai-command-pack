# Planning adversarial review — concern ledger

Contract: `.claude/sd-ai-command-pack/planning-adversarial-review.md`.

Trigger: `prd.md` materially rewritten from the Trellis scaffold (pre-edit hash
`cbef917c71de3e70`); `design.md` and `implement.md` created (both previously
absent).

Round 1 lanes: host review (this session) and Codex (`codex exec --cd <repo-root>
--sandbox read-only --ephemeral`, background task `brz5n1fxh`, exit 0).

Every Codex citation below was re-verified against source before acceptance; no
concern was adopted on the reviewer's assertion alone.

## C-1 — Recovery record cannot pass `validate_state`

- Severity: high. Blocks implementation.
- Lanes: host and Codex, independently.
- Evidence: `validate_recovery` (`fleet-controller.py:559`) calls
  `_strict_fields` with one exact key set including `correctiveRelease`,
  `fromHead`, `fromPrNumber`; `_strict_fields` (`:331-338`) raises on both
  missing and unknown keys; `:586-587` requires `fromStage == "merge"`;
  `validate_state` (`:709`) applies it to every row. The eight-field
  `local-checks` record originally proposed fails on all three counts, breaking
  the "validate before and after" acceptance criterion.
- Disposition: **addressed** in `design.md` ("Recovery record") and
  `implement.md` step 1. Tagged union on a `kind` discriminator with two exact
  key sets; `_normalize_state` (`:341-345`) backfills `kind: "pack-blocker"` on
  pre-existing rows using the precedent it already sets for `recoveries: []`.
  The original design sentence claiming `recoveries` was already heterogeneous
  was wrong and has been removed.
- Follow-on: this remediation's "no `SCHEMA_VERSION` bump" claim was itself
  overturned. Round 2 raised `C-N-1`, showing the same-version record change is
  irreversible, and the operator resolved it by bumping to `2` with a load-time
  migration. See `C-N-1` below for the final compatibility position.

## C-2 — Recovery cap under-specified

- Severity: high. Blocks implementation.
- Lanes: host and Codex, independently.
- Evidence: pack-blocker recoveries share `state["recoveries"]` and carry
  `consumer` plus `fromStage: "merge"` (`:1287`). `merge` is a real lane stage
  and therefore a real exhaustion site, so a `(consumer, stage)` count without a
  kind discriminator lets a prior pack-blocker recovery consume an exhaustion
  budget it is unrelated to. The constant, boundary, and ordering against the
  idempotency lookup were all unstated.
- Disposition: **addressed** in `design.md` ("Attempt numbering and the recovery
  bound") and `implement.md` step 3. `MAX_EXHAUSTION_RECOVERIES = 2`; count only
  `kind == "retry-exhausted"` rows matching consumer and stage; refuse at
  `>= 2`; idempotency lookup runs before the cap so a replay still succeeds when
  the cap is full.

## C-3 — CLI exclusivity matrix omits reconciliation

- Severity: high. Blocks implementation.
- Lane: Codex.
- Evidence: verified at `:1780`. `resume` counts exactly three selectors —
  `retry_consumer`, `recover_consumer`, `resolve_action` — and raises
  `resume accepts only one recovery mode`. `implement.md` named only the first
  two.
- Disposition: **addressed** in `design.md` ("Transition contract") and
  `implement.md` step 4. All four selectors join the same count;
  `--exhausted-action` is rejected when its mode flag is absent.

## C-4 — PRD misdescribed the attempt counter as a reset

- Severity: medium. Blocks implementation (contract accuracy and test coverage).
- Lane: Codex.
- Evidence: verified at `:1213-1219`. `_next_stage_attempt` returns
  `max(attempts for that stage, default=0) + 1`, which is `1` only on first
  entry to a stage. A stage re-entered through the `pr-head-advanced` path
  (`:1099-1101`) carries its prior attempts forward. "Resets the counter per
  stage" was imprecise. The mechanism the design chose is nonetheless correct:
  attempt 3 after 1 and 2, and `3 < 2` is false so the next retryable failure
  re-exhausts immediately.
- Disposition: **addressed** in `prd.md` ("Current behavior" and the budget
  requirement), which now distinguishes the two automatic attempts from
  operator-authorized ones, and in `implement.md`'s new attempt-numbering tests
  (attempt 3, immediate re-exhaustion, attempt 4 on second recovery, cap refusal
  on the third).

## C-5 — Evidence contract does not bind receipt to the exhausted attempt

- Severity: medium. Blocks implementation.
- Lane: Codex.
- Evidence: verified at `:509` and `:544`. `validate_lane` and
  `validate_receipt` each bound their own `attempt` to `>= 1` and never relate
  them, so a state where the supplied action matches stage and reason code but
  not the lane's recorded exhausted attempt is valid to the validator.
- Disposition: **addressed**. `design.md` precondition 4 now requires
  `last_receipt["attempt"] == lane["attempt"]`; `implement.md` step 2 and the
  refusal test list carry it.

## C-6 — Refusal matrix incomplete, and one precondition unreachable

- Severity: medium. Blocks acceptance closure.
- Lane: Codex.
- Evidence: verified. `TERMINAL_RESULTS` (`:77-89`) has nine members;
  `design.md` enumerated seven and omitted `operator-decision`.
  `CampaignStore.load` (`:257-262`) already refuses mismatched
  `repositoryDigest` / `campaignId`, so a new campaign-identity check would be a
  second weaker gate. Conversely `validate_lane` (`:539-543`) rejects any
  non-`issued` lane carrying an `issuedAction`, so the proposed "lane has no
  issuedAction" precondition is unreachable through the CLI and cannot be
  counted as covered refusal coverage.
- Disposition: **addressed**. `design.md` enumerates the full terminal set,
  states that campaign identity is handled by `load`, and explicitly drops the
  `issuedAction` precondition as dead code. `prd.md` acceptance criteria and
  `implement.md`'s test list follow.

## C-7 — Repository controller spec not updated

- Severity: high. Blocks implementation.
- Lane: Codex.
- Evidence: verified. `.trellis/spec/backend/manifest-and-filesystem.md:1406`
  reads "Retryable failure -> one new attempt; exhaustion parks with a stable
  reason." Shipping the transition without changing that line leaves the
  executable contract contradicting the code.
- Disposition: **addressed** as a new `prd.md` requirement, a new acceptance
  criterion, `design.md` ("Documentation"), and `implement.md` step 7.
  One correction to the reviewer's framing: the adjacent `:1344` sentence
  calling `--recover-consumer` "the sole transition from a terminal merge-stage
  pack blocker" stays true as written, because it is scoped to merge-stage pack
  blockers. Only `:1406` changes.

# Round 2

Codex round 2 (background task `bpvo2pxwu`, exit 0) verified C-1 through C-6 as
RESOLVED against source and returned C-7 as STILL-OPEN plus two new demonstrated
defects. Host round 2 raised C-9 independently. All citations below were
re-verified before acceptance.

Per contract section 4, no third automatic round runs. C-7 repeated after
remediation and C-N-1 was a genuine fork, so the review stopped and escalated
C-N-1 to the operator instead of deciding it.

# Resolution, 2026-07-29

The operator resolved `C-N-1` by choosing the `SCHEMA_VERSION` bump with
migration. Implementing that decision surfaced two further host findings, `C-11`
and `C-12`, both recorded below and both addressed.

A second operator decision the same day set `implement.md` step 9 to **abandon**
campaign `v0-56-1-20260729T173059Z` and replan on the corrective release, rather
than recover it. Evidence: the campaign targets `0.56.1`, `manifest.json` is at
`0.56.2`, and this task publishes `0.56.3`, so recovery would roll a
two-versions-stale pack to eight consumers. This weakens one of the three
arguments recorded for `C-N-1`'s bump — that the paused campaign stays
recoverable — and the `C-N-1` entry says so rather than leaving the stale
rationale standing. The bump's primary justification, a legible rollback failure,
is unaffected.

No `C-*` concern remains unresolved, so section 3's bar for implementation
approval is met. Two caveats stand:

- The `C-7` (round 2), `C-N-2`, `C-9`, `C-10`, `C-11`, and `C-12` remediations
  have not been through any review lane. Section 4 forbids a third automatic
  round, so they rest on host verification against source only.
- Implementation approval is not `task.py start`. That still needs an explicit
  per-task go-ahead from the operator.

## C-N-1 — Same-version record change is not reversible (round 2, Codex)

- Severity: high. Blocked implementation until the operator decision below;
  **addressed**.
- Evidence: verified. `SCHEMA_VERSION = 1` (`:30`). `_normalize_state`
  (`:257-259`, `:341-345`) runs before validation and therefore only gives
  forward compatibility — a new controller reading old rows. Nothing makes the
  old validator accept a row carrying `kind`, because `_strict_fields`
  (`:331-338`) rejects unknown keys. After a rollback, every `load()` of a
  campaign that used the transition fails, not merely the recovery path. The
  design's original rollback claim that the record "simply becomes inert" was
  false.
- Disposition: **addressed by operator decision, 2026-07-29.** Escalated under
  contract section 4 with three options. The operator chose **bump
  `SCHEMA_VERSION` to 2 and migrate**, on the grounds that a rollback then fails
  on `campaign schemaVersion must be 1` — a version check naming the real cause —
  instead of on an unknown-field error pointing at a recovery row, and that the
  paused `v0-56-1-20260729T173059Z` stays recoverable rather than being discarded.
  The rejected alternatives were keeping version 1 with a documented one-way
  constraint, and bumping without migration and abandoning the paused campaign.

  **Correction to this rationale.** The second ground no longer holds: a later
  decision the same day abandons that campaign anyway, because it targets `0.56.1`
  while `manifest.json` is at `0.56.2` and this task publishes `0.56.3`. The
  decision itself stands on the first ground alone — a rollback that fails on a
  version check rather than an unknown-field error. Noted here so the stale
  argument is not cited later as if it still applied.

  Recorded in `design.md` ("Recovery record", "Compatibility", "Rollback"),
  `prd.md` (one requirement, two acceptance criteria), and `implement.md`
  (step 1, migration test list, rewritten stop conditions). Migration is
  load-time in `_normalize_state` before `validate_state` (`:258-259`), so no
  operator action is needed and no write-back pass enters the locking protocol.
  Migrating a campaign is one-way and `design.md` "Rollback" says so explicitly
  instead of promising a clean revert.

  The earlier stop condition in `implement.md` — "the `kind` discriminator turns
  out to require a `SCHEMA_VERSION` bump after all" — is retired, because the bump
  is now the chosen path rather than a surprise. It is replaced by two conditions
  that fire if the *migration* cannot be made to work purely load-time.

  A separate top-level state key was considered and rejected: an old validator
  rejects an unknown top-level key identically, so it carries the same rollback
  cost while splitting one invariant across two lists.

## C-N-2 — Resume dispatch has three sites, plan covered one (round 2, Codex)

- Severity: high. Blocks implementation.
- Evidence: verified at `:1720-1731`. A pre-lock guard returns a read-only
  `resume_report` when all three existing selectors are `None`. Without the new
  selector in that condition, `resume --recover-exhausted-consumer X` prints a
  report, returns `0`, and performs no transition — a silent no-op. The
  catch-all at `:1792-1820` routes anything unmatched into
  `resolve_reconciliation`, so the new mode also needs its own branch ahead of
  it.
- Disposition: **addressed** in `implement.md` step 4, which now enumerates all
  three dispatch sites and names the silent-no-op failure mode, plus a
  regression test asserting the new selector transitions rather than reporting.

## C-7 (round 2) — Spec recovery-row contract also contradicts the new row

- Severity: high. Was `addressed`, reopened by round 2, now **addressed** again.
- Evidence: verified at `.trellis/spec/backend/manifest-and-filesystem.md:1380-1383`:
  "Each recovery row binds the consumer, blocking head and PR, corrective
  release, source action, and destination publication attempt." That is a
  universal claim over recovery rows, and the `retry-exhausted` arm carries none
  of head, PR, or corrective release. Round-1 remediation caught only `:1406`.
- Disposition: **addressed** in `implement.md` step 7, which now names both spec
  sites and requires the row contract to become kind-aware.
- Caveat: this second remediation, and C-N-2's, have **not** been through a
  review lane. Section 4 forbids a third automatic round.

## C-10 — `prd.md` and `design.md` disagreed on where the recovery is recorded

- Severity: medium. Blocks implementation (contradictory requirement).
- Lane: host, round 2. Neither review lane caught it.
- Evidence: `prd.md` required the transition to "append a distinct recovery
  receipt" and made that an acceptance criterion, while `design.md` states the
  transition writes only to `state["recoveries"]` and lane scalars and "never
  touches `lane["receipts"]`". Both cannot hold. `design.md` is right: appending
  to `lane["receipts"]` would require a new `RESULTS` member, which is itself a
  schema widening and would break the byte-for-byte receipt-preservation goal
  the same requirement asks for.
- Disposition: **addressed** in `prd.md`, whose requirement and acceptance
  criterion now match `design.md` — no write to `lane["receipts"]`, recovery
  recorded as a row in `state["recoveries"]`.

## C-9 — Kind-blind idempotency lookup becomes a `KeyError` (round 2, host)

- Severity: medium. Blocks implementation.
- Lane: host, round 2. Raised by the C-1 remediation itself, so it could not
  exist in round 1.
- Evidence: `recover_pack_blocker`'s idempotency lookup at `:1247-1254` filters
  only on `(consumer, fromActionId)`, then dereferences
  `existing["correctiveRelease"]` at `:1256`. Once a second recovery kind shares
  `state["recoveries"]`, a match against a `retry-exhausted` row — which has no
  `correctiveRelease` — raises an unhandled `KeyError` rather than a typed
  `FleetControllerError`. Reachability is narrow, because `fromActionId` is
  taken from `lane["receipts"][-1]` and the two kinds record different actions,
  but the failure mode is an uncaught exception in a recovery path.
- Disposition: **addressed** in `implement.md` step 1 (both lookups filter on
  `kind`) with a regression test added to the record-compatibility list.

## C-11 — Migration would be skipped by the existing backfill gate (host)

- Severity: medium. Found while implementing the `C-N-1` decision, so it could
  not exist in either review round.
- Lane: host.
- Evidence: verified at `:342`. The existing `recoveries: []` backfill is gated on
  `state.get("schemaVersion") == SCHEMA_VERSION`. Once the constant is `2`, that
  gate stops matching a `schemaVersion: 1` state, so a v1 state would receive
  neither the `recoveries` backfill nor the `kind` tagging unless the new v1 arm
  performs both itself. Separately, `_normalize_state` shallow-copies with
  `dict(state)` (`:343`), so tagging rows in place would mutate the caller's
  nested objects.
- Disposition: **addressed** in `design.md` ("Recovery record") and
  `implement.md` step 1, both of which now require the v1 arm to carry the
  `recoveries` backfill and to copy the list and rows before tagging, plus a
  no-input-mutation test in the migration list.

## C-12 — Mirroring `recover_pack_blocker` would compare release to the manifest (host)

- Severity: high. Would make the paused campaign unrecoverable.
- Lane: host.
- Evidence: verified. `implement.md` step 2 directs the new function to mirror
  `recover_pack_blocker`'s structure, and that function validates its release
  against `actual_release`, the current pack manifest version (`:1236`), because a
  corrective release is definitionally a different version. This transition has no
  corrective release. Copying that comparison would refuse recovery of any
  campaign whose target is not the installed pack version — exactly the state of
  `v0-56-1-20260729T173059Z`, which targets `0.56.1` while the manifest has moved
  to `0.56.2`. The correct precedents are `resolve_reconciliation` (`:1326-1327`)
  and the receipt path (`:1133-1134`), which both compare against
  `state["release"]`.
- Disposition: **addressed** in `implement.md` step 2, which now names the trap
  and requires a test where recovery succeeds at the campaign release while the
  manifest reports a later version. `design.md`'s transition contract already said
  "validated against the campaign release" and needed no change.

## C-8 — Does the campaign actually leave `blocked`? (host, verified claim)

- Severity: n/a. Raised by the host lane as an unverified design assertion.
- Evidence: traced end to end. `_lane_observations` (`:904`) maps
  `retry-exhausted` with `packBlocker: false` to `failed`; the wave planner
  (`fleet-wave-plan.py:186-195`) returns `stopStarting: True` for a canary in
  `TERMINAL_STATES` outside the success set; `_refresh_campaign_status`
  (`:1408`) turns that into `blocked`. After the reset the lane is `waiting` at
  a mid-lane stage, falls through to `in-flight`, is not terminal, and the
  campaign returns to `active`. `next` eligibility (`:945`) reads only `status`
  and `result`, never `attempt`, so attempt 3 does not block issuance.
- Disposition: **rebutted** — the design's claim holds. Recorded because it was
  an assumption when written and is now evidence.
