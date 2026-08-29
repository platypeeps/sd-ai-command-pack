---
title: Converge repeated review finding families
status: done
created: 2026-07-24
branch: codex/converge-review-finding-families
---
# Converge repeated review finding families

## Goal

Make repeated review rounds converge by recognizing finding families, requiring
a root-cause and sibling audit when a family repeats, batching related fixes,
and preventing unbounded provider redispatch.

## Confirmed Evidence

- A read-only three-day scan inspected 38 pull requests and 114 Copilot
  comments. Boundary validation alone produced 30 comments across 30 distinct
  normalized signatures; the recurrence is thematic rather than duplicate
  text.
- PR #237 required 22 remote-review rounds and 23 pull-request CI executions.
  Findings repeatedly covered persisted-state validation, attempts, receipts,
  replay and idempotency, exact heads, filesystem permissions, locks, symlinks,
  TOCTOU, and controlled diagnostics.
- The completed boundary-contract advisory and the PR checklist both existed
  before PR #237. Advisory prose did not force a whole-family audit or stop the
  one-finding-per-round loop.

## Dependencies And Boundaries

- Parent: `07-24-implement-unified-routed-sd-review`.
- Depends on `07-24-feed-review-learnings-into-review-planning` publishing the
  bounded finding-family vocabulary and evidence shape.
- The parent review controller owns provider dispatch, exact-head receipts,
  remediation, and round state. This child owns only family-level convergence
  policy and evidence.
- `07-22-validate-sd-workflow-program-integration` must exercise the combined
  controller behavior before program closure.

## Requirements

- R1: Normalize actionable findings into a versioned bounded family vocabulary
  derived from review-learnings categories, including boundary validation,
  generated surfaces, contract/documentation drift, task metadata, reviewer or
  test-harness quality, and an explicit other category. Preserve the original
  provider finding and disposition separately; classification never rewrites
  reviewer evidence.
- R2: Record, per review attempt and exact head, the provider, round, finding
  identity, normalized family, disposition, related fix commit, and whether a
  sibling audit has been completed. Persist only bounded coordination metadata
  in the parent review receipt/state contract.
- R3: When the same actionable family appears on two review rounds in one PR
  lifecycle, stop automatic remote redispatch before incurring another round.
  Generate a bounded root-cause and sibling-audit checklist covering every
  matching state field, transition, operation, generated surface, and failure
  branch implicated by the family.
- R4: Run the configured local adversarial review against the complete family
  checklist and current intended diff. A missing or failed local reviewer is a
  visible limitation and cannot be presented as a completed sibling audit.
- R5: Collect every current actionable review comment plus locally found
  siblings, disposition them together, apply only approved in-scope fixes, run
  `sd-check`, and publish at most one focused fix commit before the next remote
  request.
- R6: Resume automatic remote routing only after the sibling audit and local
  validation are recorded. If the next round repeats the same family, require
  the parent command's existing structured decision for an explicit round
  extension; default to stop with actionable evidence.
- R7: Report rounds avoided, repeated families, sibling findings, batch size,
  provider cost class, and the exact head without claiming that review quality
  is equivalent across providers.
- R8: Never suppress, dismiss, resolve, or downgrade a finding solely because
  it belongs to a repeated family. Preserve exact-head invalidation, unresolved
  thread gates, CI, and housekeeping authority.

## Acceptance Criteria

- [ ] Two same-family findings across review rounds stop redispatch and produce
  one deterministic sibling-audit requirement; unrelated families do not
  trigger the threshold.
- [ ] A state-machine fixture audits schema types, transitions, replay,
  attempts, receipts, head binding, lock/path safety, and error translation in
  one batch instead of rediscovering them round by round.
- [ ] Current remote comments and local sibling findings produce one scoped fix
  batch and at most one pushed review-fix commit before redispatch.
- [ ] Missing, failed, malformed, or unavailable local review cannot mark the
  sibling audit complete or grant positive confidence.
- [ ] A repeated post-audit family requires explicit round extension and
  retains all exact-head, thread, CI, and merge gates.
- [ ] Human and JSON reports expose family counts, audit state, round/cost
  telemetry, limitations, and the exact reviewed head.
- [ ] Focused state-machine tests, generated parity, install audit,
  `make sync`, and `make check` pass.

## Out Of Scope

- Treating token matching as proof of test or branch coverage.
- Automatically accepting reviewer findings or broadening fix scope.
- Replacing provider-specific review output with a lowest-common-denominator
  summary.
- Increasing the default review-round budget.
