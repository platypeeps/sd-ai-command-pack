# PARKED: Add routed review operator UX

> Status: BLOCKED (external) — do not `task.py start`. Requires: stable sd-github-review setup/compiler/status/pending/explanation/recovery, adjudication, and retention/status/purge contract majors + conformance fixtures. Marked 2026-07-25; see Dependencies.

## Goal

Extend the unified `sd-review` command with portable configuration, budget,
finding-adjudication, and data-retention operations over versioned contracts published by
`sd-github-review`. Keep the command pack responsible for operator
presentation and safe orchestration, while the router remains the schema,
compiler, selection, receipt, and adjudication-validation authority and the
private control plane retains ledger/event-store authority.

## Requirements

- R1: Preserve the approved public vocabulary. Add nested `sd-review config`,
  `sd-review budget`, and `sd-review data` operations; do not add another top-
  level public skill or command.
- R2: Deliver configuration operations through child task
  `07-25-add-sd-review-configuration-operations`: `init`, `validate`,
  `render`, `explain`, `diff`, and `migrate`.
- R3: Deliver budget operations through child task
  `07-25-add-sd-review-budget-operations`: `status`, `pending`, `explain`,
  and explicitly authorized `retry`.
- R4: Deliver finding operations through child task
  `07-25-add-sd-review-finding-adjudication-operations`: `list`,
  `adjudicate`, and `status`.
- R5: Consume only published, versioned setup-discovery, compiler,
  configuration, status, pending, explanation, and recovery contracts. Reject
  missing or incompatible required capabilities with actionable guidance.
- R5b: Render the router's stable assurance/gate Check identities and branch-
  protection readiness. Report when the gate is not required or assurance is
  incorrectly required; never mutate repository rules without explicit
  authorization.
- R5a: Preserve the router's explicit `standalone`/`managed` mode and
  capability vocabulary. Configuration operations remain available in both
  modes; budget, pending/recovery, finding, and private-data operations report
  `unsupported_in_standalone` or `control_plane_not_configured` without
  fabricating zero, empty, or successful authoritative state.
- R6: Do not duplicate router schemas, compiler defaults, model selection,
  budget accounting, recovery policy, or receipt authority in the command
  pack.
- R7: Keep observation and explanation read-only. Configuration writes,
  finding adjudications, and review recovery must be explicit, bounded,
  conflict-aware, and attributable
  to the operator's request.
- R8: Never receive provider credentials, source content from private control
  plane state, or raw ledger access. Render safe aliases, digests, freshness,
  unknown states, and bounded diagnostics only.
- R9: Implement executable orchestration in authoritative source templates and
  keep generated adapters, root script mirrors, manifest, installed guide,
  help, tests, changelog, and release ledger synchronized.
- R10: Preserve independent `reviewOutcome`, `assuranceOutcome`, and
  `gateOutcome` vocabulary across direct `sd-review`, `sd-ship`, and
  `sd-work-backlog` composition. A passing gate with deferred assurance remains
  reported as deferred, not as a completed or passing review.
- R11: Treat these operations as consumers of the stable router contract.
  Implementation must not begin against provisional fixtures or invent
  compatibility behavior for superseded source formats.
- R12: Deliver data operations through child task
  `07-25-add-sd-review-data-operations`: read-only `status` and explicitly
  confirmed `purge` over the router-owned `standard-v1` retention contract.
  Consume only stable versioned retention/status/purge contracts and never
  duplicate retention authority in the command pack.

## Acceptance Criteria

- [ ] All four child tasks are completed and archived with focused contract,
      behavior, and lifecycle tests passing.
- [ ] Every supported adapter exposes the operations through `sd-review`; no
      `sd-review-budget` or other new top-level public command is installed.
- [ ] Capability discovery covers ready, absent, incompatible, malformed, and
      unavailable integrations without provider dispatch or ledger mutation.
- [ ] Setup output distinguishes the stable assurance and gate Checks, requires
      only the gate for branch protection, and provides actionable diagnostics
      without unrequested repository-rule mutation.
- [ ] Standalone fixtures keep configuration UX available, report managed-only
      families as unsupported, and never turn managed outage into standalone.
- [ ] Tests prove the pack delegates compilation, status, and recovery to the
      published router interfaces rather than carrying a second authority
      implementation.
- [ ] Read-only operations leave repository, GitHub, provider, and ledger state
      unchanged; write and retry operations require explicit intent.
- [ ] Data status shows retention policy/digest, counts and next deletion by
      class, holds, coverage gaps, purge progress, backup purge deadline, and
      GitHub-native artifacts excluded from private purge.
- [ ] Data purge is repository-scoped, explicitly confirmed, idempotent, and
      actor/reason attributable; it delegates to the published router contract
      and never claims to delete GitHub-native artifacts.
- [ ] Output redacts secrets and private state while preserving safe aliases,
      source locations, canonical digests, freshness, and actionable unknowns.
- [ ] Template/generated parity, manifest/provenance, help/catalog,
      install/update/check/uninstall, release-ledger, focused tests,
      `make check`, and fleet candidate validation pass.

## Dependencies

- Parent program `07-22-integrate-routed-review-backends` establishes the
  unified `sd-review` surface and router capability boundary.
- `platypeeps/sd-github-review` task
  `07-25-compile-and-execute-budget-aware-review-plans` and its configuration,
  status, pending, explanation, and recovery children must publish stable
  versioned contracts and conformance fixtures.
- `platypeeps/sd-github-review` task
  `07-25-establish-trusted-finding-adjudication` must publish stable finding,
  trust, workflow, status, and receipt contracts.
- `platypeeps/sd-github-review` task
  `07-25-define-review-data-retention-policy` must publish stable
  `standard-v1`, status, purge, deletion, backup, hold, and coverage contracts.

## Out of Scope

- Implementing router schemas, compilation, selection, ledger accounting, or
  recovery policy in this repository.
- Storing provider credentials or private balance/reservation state.
- Defining retention durations, mutating legal holds, deleting GitHub-native
  artifacts, or bypassing private-control-plane purge authorization.
- Backward-compatible interpretation of superseded configuration formats.
- Starting implementation, committing, publishing, or opening a pull request
  as part of this planning move.
