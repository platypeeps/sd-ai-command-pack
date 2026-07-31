# Simplify review and shipping composition

## Goal

Create one predictable shipping composition: `sd-create-pr` publishes,
`sd-review` reviews, `sd-ship` explicitly composes the end-to-end lifecycle, and
housekeeping remains the sole merge mutation owner.

## Confirmed Evidence

- Review finding `1.5.2.1` confirms that standalone `sd-watch-pr` defaults from
  watching into a merge-capable housekeeping handoff unless `no-merge` is passed.
- Existing program findings F09 and F10 record review behavior inside
  `sd-create-pr`, a private composition mode, duplicate polling, and the
  merge-capable public watch surface.
- Parent R29 approves a publish-only create command, explicit ship composition,
  and read-only internal waiting.

## Dependencies And Boundaries

- Parent: `07-22-integrate-routed-review-backends`.
- Depends on `07-24-implement-read-only-sd-check` and
  `07-24-implement-unified-routed-sd-review` publishing their stable contracts.
- Depends on `07-24-support-planning-only-pr-finalization` publishing one typed
  completion/planning finalization contract so `sd-ship` does not recreate
  task-state heuristics or a planning bypass.
- Housekeeping and the shared exact-head eligibility evaluator remain unchanged
  as the only merge mutation/gate owners.

## Requirements

- R1: Make `sd-create-pr` publish or reuse exactly one current-branch PR. It owns
  file-scope resolution, scoped commit/push, title/body, and PR identity only; it
  performs no AI review, remote routing, review polling, finish-work, merge, or
  private nested composition.
- R2: Make `sd-ship` the explicit end-to-end workflow: publish/reuse, review,
  run the deterministically selected completion or planning finalization,
  re-enter check/review for any new exact head, then delegate the eligible merge
  and cleanup to housekeeping.
- R3: Remove public `sd-watch-pr`. Keep any required waiting as a deterministic
  read-only internal coordinator used by `sd-review`/`sd-ship`, with bounded
  polling and no direct or implicit merge transition.
- R4: A standalone wait request is report-only unless the user invokes the
  explicit ship/housekeeping lifecycle that grants merge authority. Do not retain
  a `no-merge` inversion where mutation is the default.
- R5: Update `sd-work-backlog`, help/catalog, examples, docs, adapters, and tests
  to call only the orthogonal create/review/ship/housekeeping surface.
- R6: Remove hidden caller flags and private modes that reproduce the old
  overlapping composition. Internal typed context may narrow an explicit parent
  workflow but cannot become a second public interface.

Added 2026-07-28 — the interim, before retirement lands:

- R7: Repoint `sd-ship` Stage 2 at `sd-review scope=pr` as soon as the successor
  contract is stable, without waiting for the predecessor to be deleted.
  `.agents/skills/sd-ship/SKILL.md:129` currently calls `sd-review-pr`, so the
  main delivery path runs the predecessor and none of `sd-review`'s guarantees
  apply — even though `.agents/skills/sd-review/SKILL.md:14` declares the
  successor self-contained.

  This is **not** a one-line reference edit. `SKILL.md:133-136` branches Stage 2
  on `defer-finish-work`: `until=review` lets the predecessor's Step 8 finish the
  Trellis work, while `until=merge` defers it to Stage 3. `sd-review` has no
  equivalent argument and `.agents/skills/sd-review/SKILL.md:73` forbids it from
  archiving Trellis work at all. So the repoint owes a design for where
  finish-work, review-learning, and the Stage 3 transition land under each
  `until=` value before the reference changes.

  Ownership: **this task owns the repoint** (decided 2026-07-28).
  `07-28-retire-transitional-review-surfaces` has dropped its duplicate claim and
  now depends on R7 landing. Gated on R2's ordering, not on
  `07-24-remove-retired-review-surfaces`.
- R8: While both lifecycles ship, the shipped guidance must name one current
  path. `docs/SD_AI_COMMAND_PACK.md:194` interleaves successor and transitional
  steps across 18 steps with no decision point, so a reader cannot tell which
  lifecycle they are in. Either present the successor loop only, or add an
  explicit decision point that routes to one lifecycle.

## Acceptance Criteria

- [x] `sd-create-pr` fixtures prove publication stops after the PR exists and no
  provider, polling, finish-work, or merge call occurs.
- [x] `sd-ship` fixtures prove the complete ordered lifecycle, including
  completion/planning finalization, successor-head re-entry, preserved planned
  task state, and a single housekeeping merge owner.
- [x] No public catalog, registry, adapter, or help output exposes `sd-watch-pr`.
- [x] Internal waiting tests prove bounded polling, complete thread pagination,
  timeout reporting, and zero mutation.
- [x] There is no private create/review/watch composition mode or compatibility
  argument that preserves the prior overlap.
- [x] Focused publishing/shipping tests, generated parity, install audit,
  `make sync`, and `make check` pass.
- [x] No shipped skill, adapter, or doc routes the primary delivery path through
  `sd-review-pr` while `sd-review` is the declared successor.
- [x] The recommended review loop in the shipped guide describes exactly one
  lifecycle, or routes through an explicit decision point.

## Out Of Scope

- Weakening exact-head review, thread, CI, finish-work, or housekeeping gates.
- Preserving `sd-watch-pr` as an alias or default-merge wrapper.

## Notes

- The command names must communicate their authority: create publishes, review
  reviews, ship ships, and housekeeping merges/cleans.
- 2026-07-28 audit source: `.trellis/audit/report-2026-07-28.md` — finding A-045
  (P2 · L · Plausible · architecture). This task was tracked-stale against it:
  R1-R6 describe the correct end state but every one of them is contingent on
  retirement landing, so nothing here changed the interim behavior A-045
  measures. R7/R8 are that interim.
- Removal-version scheduling and the transitional catalog status for the same
  finding are owned by `07-28-retire-transitional-review-surfaces`. Coordinate
  with it rather than duplicating; this task owns only the composition half.
- **R7 gap measured 2026-07-28.** `grep -n "review-learning"
  .agents/skills/sd-review/SKILL.md` returns nothing — the successor has no
  review-learning pass, yet `sd-ship/SKILL.md:131-132` states Stage 2 owns "the
  one read-only, PR-scoped post-cycle review-learning pass; no other ship stage
  repeats it". The repoint must name a new owner for it or drop it by decision.
- **The two `until=` values differ in difficulty.** `until=merge` is nearly
  mechanical because Stage 4 already runs finish-work (`sd-ship/SKILL.md:145`).
  `until=review` has no home for finish-work under the successor at all.
  `design.md` carries the three options.
- **R3 and R4 both land on Stage 3 and must land together.**
  `sd-ship/SKILL.md:138-142` calls `sd-watch-pr` with `no-merge` specifically to
  suppress its automatic housekeeping handoff. R3 deletes that surface and R4
  deletes the inversion it relies on; either order alone leaves a broken
  intermediate state.
- Planning complete 2026-07-28: `design.md` and `implement.md` added.
