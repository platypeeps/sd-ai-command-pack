# PARKED: Add sd-review Configuration Operations

> Status: BLOCKED (external) — do not `task.py start`. Requires: stable sd-github-review configuration/compiler contracts (07-25-compile-and-execute-budget-aware-review-plans). Marked 2026-07-25; see Dependencies.

## Goal

Add `sd-review config init|validate|render|explain|diff|migrate` as a portable
operator layer over repository-owned configuration and compiler contracts.

## Requirements

- R1: `init` scaffolds a complete explicit consumer configuration at
  `<consumer-repository>/.github/sd-review.yml` from a pinned versioned preset.
  It creates no runtime imports, inheritance, hidden profiles, or contextual
  defaults. Managed presets materialize explicit
  `budgetExhaustion.<lane>.merge=block|allow`; fresh presets visibly use
  `block` unless the operator supplies a reviewed choice.
  The requested `standalone` or `managed` mode is explicit; a standalone preset
  materializes fixed lane profiles and requires no catalog/control plane.
- R2: `validate` invokes router-owned compiler validation and preserves
  bounded source locations and diagnostic codes.
- R3: `render` displays the canonical expanded manifest plus source, catalog,
  and output digests without credentials or private catalog data.
  Catalog digest is present only in managed mode. Render preserves each lane's
  explicit budget-exhaustion merge policy.
- R4: `explain` reports slots and chains, candidate eligibility, applicable
  policies, and the expected no-dispatch selection result.
  In standalone it instead reports fixed lane profiles, `not_managed`, and the
  managed capabilities that are unavailable.
- R5: `diff` reports semantic source or catalog-update effects, including
  candidate availability, safe credential/policy aliases, completion behavior,
  budget-exhaustion merge behavior, stable assurance/gate Check readiness, and
  override exposure.
- R6: `migrate` invokes the router-owned one-time v1-to-v2 migration and
  retains no compatibility interpretation layer.
  Fixed v1 routes migrate to explicit standalone v2; managed enablement remains
  a separate reviewed mode change and semantic diff. Supported legacy
  exhaustion values are translated once by the router migration and are never
  accepted as active v2 configuration.
- R7: The pack performs capability discovery and response validation but does
  not duplicate schemas, normalization, defaults, compilation, catalog access,
  or digest algorithms.
- R8: `validate`, `render`, `explain`, and `diff` are read-only. `init`
  and `migrate` require explicit intent, support preview, detect conflicts,
  and avoid overwriting user changes without confirmation.
- R9: Implement source/generated surfaces, help, docs, manifest, changelog,
  install lifecycle, and tests through current pack conventions.

## Acceptance Criteria

- [ ] Every operation is reachable through `sd-review config` on every
      supported adapter and no separate public command is added.
- [ ] Golden fixtures prove the pack forwards versioned inputs and preserves
      router validation codes, locations, canonical output, and digests without
      local reinterpretation.
- [ ] `init` produces a complete explicit source whose labels are opt-in and
      whose preset/version identity is visible and reproducible.
- [ ] Managed init/render/diff fixtures expose explicit per-lane block/allow
      policy with no hidden default; missing or legacy active values fail.
- [ ] Validation/explain output diagnoses a missing required gate or incorrectly
      required assurance Check without silently changing branch protection.
- [ ] Preview, conflict, existing-file, partial-write, malformed response,
      incompatible-major, and unavailable-capability cases fail safely.
- [ ] Mode-change preview lists every gained/lost capability; standalone
      init/validate/render/explain/diff/migrate require no control-plane endpoint
      or credential, and managed failure never changes mode.
- [ ] Render, explain, and diff expose safe aliases and actionable changes but
      no secret, private catalog value, raw source, or hidden default.
- [ ] Migration is idempotent after success, preserves a recoverable source
      backup or equivalent transactional guarantee, and leaves no live v1 path.
- [ ] Focused controller tests, generated parity, help/catalog, manifest,
      install/update/check/uninstall, release ledger, `make check`, and fleet
      candidate validation pass.

## Dependencies

- Parent `07-25-add-routed-review-operator-ux`.
- Stable setup-discovery, source-v2, exact-catalog, compiled-manifest,
  validation, render, diff, and migration contracts from
  `platypeeps/sd-github-review` task
  `07-25-compile-and-execute-budget-aware-review-plans`.

## Out of Scope

- Provider/model selection, ledger reporting, recovery, or dispatch.
- A second configuration parser/compiler or long-lived v1 compatibility.
