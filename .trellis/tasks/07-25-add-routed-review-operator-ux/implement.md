# Routed Review Operator UX Implementation Plan

## Preconditions

- Do not start until the owning `sd-github-review` configuration,
  setup-discovery, status, pending, explanation, and recovery contracts have
  stable majors and conformance fixtures.
- Require stable finding identity, trust policy, adjudication workflow, and
  evidence-query contracts before implementing finding operations.
- Require stable `standard-v1`, retention status, purge, deletion-receipt,
  backup-expiry, legal-hold visibility, and coverage contracts before data
  operations.
- Confirm the unified `sd-review` implementation and current generated-surface
  conventions before editing shipped payload.
- Use `task.py start` only when implementation is explicitly selected from the
  backlog; this planning move does not start the work.

## Delivery Sequence

1. Pin compatible setup and operation contracts, including assurance/gate
   outcomes, branch-protection readiness, safe example responses, and failure
   fixtures.
2. Add one shared capability-discovery, invocation, validation, and output
   envelope to authoritative `sd-review` controller/template sources.
3. Implement `07-25-add-sd-review-configuration-operations`.
4. Implement `07-25-add-sd-review-budget-operations`.
5. Implement `07-25-add-sd-review-finding-adjudication-operations`.
6. Implement `07-25-add-sd-review-data-operations`.
7. Update the canonical skill, command-source guidance, generated adapters,
   installed guide, help/catalog, and composing workflows without creating a
   new top-level public command.
8. Synchronize source/root script mirrors and generated surfaces; update
   manifest, changelog/version, provenance, and release evidence as required.
9. Run focused controller/contract tests, generated parity, install lifecycle,
   full pack checks, and fleet candidate validation.

## Stop Conditions

- Stop if the router requires the pack to receive credentials, query private
  ledger storage, or reproduce compiler/recovery/retention policy.
- Stop if response contracts cannot distinguish stale, unknown, deferred,
  superseded, recovered, and completed states.
- Stop if an adapter cannot preserve explicit mutation authorization or a
  shipped surface cannot be generated from authoritative sources.
- Stop if purge cannot distinguish live deletion, backup expiry, and excluded
  GitHub-native artifacts or cannot require exact repository confirmation.
