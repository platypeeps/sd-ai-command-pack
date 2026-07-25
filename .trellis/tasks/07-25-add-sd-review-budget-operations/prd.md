# PARKED: Add sd-review Budget Operations

> Status: BLOCKED (external) — do not `task.py start`. Requires: stable sd-github-review status/pending/explanation/recovery contracts (07-25-compile-and-execute-budget-aware-review-plans). Marked 2026-07-25; see Dependencies.

## Goal

Add `sd-review budget status|pending|explain|retry` over bounded router status
and recovery contracts without making the command pack a ledger or recovery
policy authority.

## Requirements

- R1: `status` summarizes overall, repository, cheap/deep lane, named-chain,
  candidate, provider/model, and shared-pool state with observation freshness
  and explicit unknowns.
- R2: `pending` lists deferred reviews, repository/PR/head identity,
  exact-head freshness, reason, next eligibility observation, and bounded
  recovery eligibility plus separate assurance and merge-gate outcomes.
- R3: `explain` reports why each configured slot would select, skip, fail, or
  defer candidates against an identified compiled digest without dispatching
  providers or reserving budget.
- R4: `retry` invokes only the declared trusted recovery workflow after
  explicit authorization. It returns the new attempt and receipt correlation
  and preserves exact-head/idempotence semantics.
- R5: Reads are side-effect free. The pack does not query private ledger
  storage, infer balances, mutate reservations, refill pools, select an
  alternate provider, or bypass router recovery policy.
- R6: Distinguish available, low, exhausted, refilled, stale, unknown,
  deferred, eligible, recovered, superseded, failed, and completed states. A
  passing `sd-review / gate` with `assuranceOutcome=deferred` remains deferred
  and is never reported as a completed or passing review.
- R7: Responses are bounded and safe: no credentials, provider secrets, source
  content, prompts, raw findings, or private control-plane payloads.
- R8: Implement source/generated surfaces, help, docs, manifest, changelog,
  install lifecycle, and tests through current pack conventions.
- R9: In standalone mode, report `not_managed` plus the unavailable budget,
  pending, explanation, and recovery capabilities. Do not show numeric zero,
  an empty authoritative queue, or a successful retry. A managed outage remains
  `unavailable` and never suggests automatic standalone fallback.

## Acceptance Criteria

- [ ] Every operation is reachable through `sd-review budget` on every
      supported adapter; no `sd-review-budget` top-level command is installed.
- [ ] Status fixtures cover global, repository, lane, chain, candidate,
      provider/model, shared-pool, freshness, partial-data, and unknown views
      without double-counting shared budget.
- [ ] Pending output distinguishes current, stale-head, recovered, superseded,
      failed, and completed records and gives an actionable next step without
      claiming a review occurred.
- [ ] Status/pending output preserves independent review, assurance, and gate
      outcomes and identifies the exact explicit merge policy/reason that
      allowed or blocked a budget-deferred gate.
- [ ] Explain is side-effect free and binds its reasoning to the compiled
      configuration/catalog digest it evaluated.
- [ ] Retry tests prove explicit authorization, trusted-workflow identity,
      current-head revalidation, logical attempt/fingerprint reuse, conflicting
      retry rejection, and receipt linkage.
- [ ] Missing, incompatible, malformed, unavailable, stale, and ambiguous
      contract states fail closed without direct provider or ledger access.
- [ ] Standalone fixtures return deterministic actionable unsupported output
      without invoking providers, workflows, or ledger operations.
- [ ] Focused controller tests, generated parity, help/catalog, manifest,
      install/update/check/uninstall, release ledger, `make check`, and fleet
      candidate validation pass.

## Dependencies

- Parent `07-25-add-routed-review-operator-ux`.
- Stable status, pending, explanation, recovery, receipt, and setup-discovery
  contracts from `platypeeps/sd-github-review` task
  `07-25-compile-and-execute-budget-aware-review-plans`.

## Out of Scope

- Ledger storage, budget policy, provider selection, refill, reservation, or
  reconciliation logic.
- Automatic retry, direct provider dispatch, or treating a passing deferred
  gate as review completion.
