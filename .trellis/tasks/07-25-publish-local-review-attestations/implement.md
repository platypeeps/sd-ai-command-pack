# Local Review Attestation Publisher Implementation Plan

1. Consume the published sd-github-review local-attestation fixtures and setup
   capability without duplicating schema or policy logic.
2. Add explicit local-attested capability selection to the unified review
   coordinator after exact-head local completion.
3. Project the canonical local receipt into the bounded publication envelope
   and persist its request identity/fingerprint before dispatch.
4. Invoke, resume, reconcile, and report the trusted ingestion workflow without
   reviewer fallback.
5. Update the canonical skill, generated templates/adapters, documentation, and
   installer manifests without adding a public command.
6. Validate all terminal outcomes, setup states, wrong/changed heads, replay,
   ambiguity, privacy bounds, zero remote dispatch, generated-surface parity,
   focused tests, and the full repository gate.
