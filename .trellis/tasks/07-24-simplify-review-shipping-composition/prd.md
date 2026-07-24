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

## Acceptance Criteria

- [ ] `sd-create-pr` fixtures prove publication stops after the PR exists and no
  provider, polling, finish-work, or merge call occurs.
- [ ] `sd-ship` fixtures prove the complete ordered lifecycle, including
  completion/planning finalization, successor-head re-entry, preserved planned
  task state, and a single housekeeping merge owner.
- [ ] No public catalog, registry, adapter, or help output exposes `sd-watch-pr`.
- [ ] Internal waiting tests prove bounded polling, complete thread pagination,
  timeout reporting, and zero mutation.
- [ ] There is no private create/review/watch composition mode or compatibility
  argument that preserves the prior overlap.
- [ ] Focused publishing/shipping tests, generated parity, install audit,
  `make sync`, and `make check` pass.

## Out Of Scope

- Weakening exact-head review, thread, CI, finish-work, or housekeeping gates.
- Preserving `sd-watch-pr` as an alias or default-merge wrapper.

## Notes

- The command names must communicate their authority: create publishes, review
  reviews, ship ships, and housekeeping merges/cleans.
