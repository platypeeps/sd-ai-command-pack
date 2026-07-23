# Design: skill workflow remediation program

## Architecture

The parent is a coordination and integration artifact. Implementation remains
distributed across bounded children, with shared contracts flowing in one
direction:

1. Platform capability, checkout trust, and structured-interaction policy are
   generated from canonical metadata.
2. Deterministic check and PR eligibility coordinators produce typed evidence.
3. Review, backlog, fleet, audit, and maintenance skills consume typed evidence
   rather than reproducing transport or state logic in prose.
4. Command-registry validation prevents removed surfaces from leaking back into
   adapters, docs, specs, or manifests.

## Dependency Waves

### Wave 1: independent foundations

- `07-22-centralize-pr-eligibility-gates`
- `07-22-enforce-untrusted-checkout-preflight`
- `07-22-add-portable-structured-questions`
- `07-22-add-command-surface-drift-lint`
- `07-22-structure-skill-runtime-contracts`

These can be implemented independently. If they touch common generator or
manifest code, each task must rebase/reconcile against already-landed sibling
contracts instead of restoring earlier generated output.

### Wave 2: workflow-specific simplification

- `07-22-integrate-routed-review-backends` consumes the PR-gate,
  structured-question, and command-registry contracts and remains blocked on
  the external router v1 task already recorded in its artifacts.
- `07-22-determinize-fleet-refresh-orchestration` may consume the structured
  interaction contract but does not depend on the review cutover.
- `07-22-streamline-backlog-design-workflows` consumes the structured
  interaction contract and must coordinate its final live-command references
  with the review cutover.
- `07-22-harden-review-learnings-boundaries` consumes the structured
  interaction contract for explicit external writes.
- `07-22-optimize-audit-charter-routing` consumes the interaction contract only
  for follow-up-task selection, never for deterministic applicability.

### Wave 3: integration

The parent runs the cross-child scenario matrix after all selected children
land. Integration review resolves common registry, generated-adapter, manifest,
and documentation conflicts once, at the end.

## Shared Invariants

- Evidence is bound to the current repository, scope, and full head identity.
- Read-only commands do not refresh generated state or mutate Git/GitHub.
- Housekeeping is the only merge mutation owner.
- A skill may request user judgment but must not use a question to transfer an
  unbounded state machine to the user.
- Host-specific tools are generated capability adaptations, not canonical
  runtime assumptions.
- All failure, unavailable, stale, absent, and indeterminate outcomes remain
  distinct and fail closed where readiness cannot be proven.

## Integration Matrix

The final review covers at least:

- finish-work creates a new head after review;
- remote routing is absent, invalid, unavailable, failed, or ambiguous;
- local providers are missing, paid/networked, or produce reusable evidence;
- checkout content originates from an untrusted fork;
- structured questions are available, unavailable, or noninteractive;
- unresolved review threads span multiple GraphQL pages;
- dependency PRs are safe, grouped, or unsafe;
- fleet refresh stops, resumes, retries, and encounters no-touch ownership;
- audit fingerprints omit an optional charter while exhaustive mode retains it;
- retired identifiers appear in a live spec and are rejected;
- review-learnings receives a relative, absolute, or symlink-escaping target.

## Rollback

Each child defines its own rollback. The program rollback is version-based:
reinstall the last known-good pack release rather than retaining dormant legacy
surfaces in the new release. Parent closure records which child version or PR
introduced each contract.
