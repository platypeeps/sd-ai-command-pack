# Cross-repository implementation plan

## 1. Freeze The Cross-Repository Boundary

- Agree on the router v1 request field for a bounded exact-head local-review
  summary. Keep the richer local receipt and all raw local artifacts owned by
  `sd-ai-command-pack`.
- Agree on a side-effect-free setup descriptor and the distinction between
  optional absence, declared-invalid/unavailable setup, and post-dispatch
  failure or ambiguity.
- Add shared positive and negative fixtures for clean, fully dispositioned,
  unavailable, failed, stale, and malformed local summaries.

## 2. Publish The Router Contract

- Complete `platypeeps/sd-github-review` task
  `07-22-publish-routed-review-receipt-contract` first.
- Require a stable v1 request/receipt schema, canonical fixtures, exact-head
  identity, setup descriptor, bounded local-summary validation, dispatch-phase
  idempotency, observation metadata, and durable transport.
- Pilot Copilot plus at least one external backend before declaring the
  protocol consumable.

## 3. Replace The Command-Pack Surface

- Add the agreed clean public surface: `sd-check` for deterministic
  verification and `sd-review` for every local, codebase, and PR review scope.
- Implement one pack-owned local provider/receipt engine used only by the new
  `sd-review` lifecycle.
- Preserve standalone dirty-worktree review, add exact-scope reuse and
  invalidation, distinguish findings from unavailable/failed providers, and
  keep raw output local.
- Preserve non-prompting local-only PR review for optional router absence while
  failing early for explicit/required remote review and failing closed for
  broken or ambiguous router state.
- Remove the old skills, adapters, scripts, manifest entries, configuration
  keys, documentation, and help catalog entries. Add their pack-owned paths to
  provenance-aware retired-target cleanup without adding aliases or readers.
- Update `sd-create-pr`, `sd-ship`, `sd-work-backlog`, help, docs, tests, and
  fleet gates to reference only the new commands.

## 4. Consume The Router Contract In The Command Pack

- Complete child task `07-22-integrate-routed-review-backends` only after the
  router v1 fixtures are available.
- Preserve templates as source of truth. Make the router the only remote
  request owner; do not retain direct-review compatibility code.
- Send only the bounded local outcome summary and prove one lifecycle across
  local, Copilot, and external finding channels without duplicate local runs or
  dual remote dispatch.

## 5. Integration Review

- Run both repositories' contract tests against the same fixture corpus.
- Exercise automatic selection and every explicit override on a disposable
  pilot PR.
- Verify exact-head invalidation after a review-fix push, zero unresolved
  threads before merge, and backend/cost/latency reporting.
- Verify a finish-work-only successor receives a distinct router decision and
  exact-head receipt, including policy-allowed `none`, while mixed changes,
  explicit remote intent, and required floors take the normal review route.
- Verify the router remains noninteractive and no probe/routing/finalization
  path executes PR checkout code.
- Verify worktree/scope/configuration invalidation, standalone local review,
  local-receipt reuse, provider unavailability, and the repository minimum
  remote-review floor.
- Verify router-free optional and required consumers, declared-invalid and
  unreadable capability state, explicit remote intent, `remote=none`, and
  ambiguous post-dispatch reconciliation without any fallback request.
- Verify every old command/skill target is absent after a clean install and is
  provenance-safely retired after refresh, with no discoverable alias or legacy
  configuration path.
- Record measured latency, request count, actionable findings, false positives,
  and operator friction; do not claim cost/quality optimization without this
  evidence.

## 6. Close The Decision

- Confirm neither child required shared mutable source or atomic releases.
- If the protocol held, retain separate repositories and archive this decision
  task after both child outcomes are linked.
- If an invalidation condition occurred, return to planning with the concrete
  failure before proposing consolidation.

## Stop Points

- Do not start either implementation task until both planning artifact sets are
  reviewed.
- Do not enable routed review by default until the pilot passes.
- Do not publish the command-pack cutover until the router contract and fleet
  migration are ready; the new pack version contains no legacy path.
