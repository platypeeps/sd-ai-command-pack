# sd-github-review Operator Contract Handoff

## Status

**MOVED.** Operator UX is now planned in `sd-ai-command-pack` under
`07-25-add-routed-review-operator-ux`. The source repository retains router
contract ownership; this repository owns portable operator presentation.
Implementation remains gated on stable contracts and normal task selection.

## Source Ownership

`sd-github-review` remains authoritative for:

- `.github/sd-review.yml` and compiled-manifest schemas;
- deterministic source/catalog compilation and canonical digests;
- installer pending/active promotion and drift contracts;
- runtime plan, receipt, status, and recovery-workflow contracts; and
- source-location and bounded validation diagnostics.

The private control plane remains authoritative for candidate catalogs,
provider/model/credential/policy bindings, balances, reservations,
reconciliation, and deferred records.

## Pack-Owned Experience

The pack provides:

- `sd-review config init|validate|render|explain|diff|migrate`; and
- `sd-review budget status|pending|explain|retry`.

Presets are scaffolding only: `init` materializes a complete explicit source.
There are no runtime imports, inheritance, hidden profiles, or contextual
defaults. Candidate and slot labels remain disabled unless the source opts in.
Read operations are the default; writes and recovery are explicit bounded
actions.

## Contract Gates

- Human-source, exact-catalog, and compiled-manifest contracts have stable
  versions discoverable through the canonical setup descriptor.
- Validation, deterministic render/digest, semantic diff, and one-time
  migration have conformance fixtures consumed by the pack.
- Status and pending responses are bounded, redact secrets/source content,
  expose freshness and unknowns, and cover cheap/deep plus parallel plans.
- Recovery proves explicit authorization, exact-head revalidation,
  idempotence, and receipt/attempt linkage.
- Pack source/generated parity, install/update/uninstall, help, docs, tests,
  changelog, manifest, and release gates remain mandatory.
