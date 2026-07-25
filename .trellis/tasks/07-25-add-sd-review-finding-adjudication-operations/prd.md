# PARKED: Add sd-review Finding Adjudication Operations

> Status: BLOCKED (external) — do not `task.py start`. Requires: stable sd-github-review finding/trust/workflow/receipt contracts (07-25-establish-trusted-finding-adjudication). Marked 2026-07-25; see Dependencies.

## Goal

Add `sd-review findings list|adjudicate|status` as the portable operator UX
for trusted finding adjudication without making the command pack the finding
identity, authorization, storage, or correctness authority.

## Requirements

- `list` shows current exact-head findings, operational disposition, trust
  coverage, adjudication status, safe evidence references, and exclusions.
- `adjudicate` lets an operator review individual findings or a bounded batch,
  preview the proposed event, and explicitly attest correctness, relationship,
  resolution, rationale code, and safe evidence references.
- `status` reports adjudication coverage, unresolved/disputed evidence,
  freshness, truncation, and trusted-workflow receipt correlation.
- Invoke only setup-discovered versioned `sd-github-review` operations. Do not
  derive stable finding identities, actor permissions, CODEOWNER policy, or
  trust upgrades in the pack.
- Automation may propose dispositions and record operational evidence, but it
  must not confer `maintainer_attested` or `independent` trust.
- Preserve explicit authorization for every mutation. Noninteractive execution
  requires an unambiguous user request and still fails when the trusted
  workflow requires human confirmation.
- Keep missing adjudication non-blocking for merge in v1; report reduced
  learning/effectiveness coverage instead of inventing a label.
- In standalone mode, report trusted adjudication and effectiveness evidence as
  unsupported because no authoritative event store exists. Do not infer
  correctness from GitHub thread state or offer a local substitute store.
- Never render raw provider transcripts, credentials, private store state,
  unrestricted source/diff content, or hidden actor-policy inputs.

## Acceptance Criteria

- [ ] Every supported adapter exposes the three operations beneath
      `sd-review findings`; no new top-level adjudication command is added.
- [ ] List/status are side-effect free and report ready, absent, incompatible,
      unavailable, stale, disputed, truncated, and insufficient-evidence states.
- [ ] Standalone fixtures report unsupported trusted adjudication without
      mutation or fabricated coverage; managed outage never changes mode.
- [ ] Adjudicate previews the exact event and mutation, preserves structured
      user choice, and invokes only the trusted setup-discovered workflow.
- [ ] Tests prove bots, finding publishers, insufficient permissions, stale
      findings, high-risk approval gaps, and conflicting events cannot be
      upgraded by command-pack behavior.
- [ ] Replay returns the existing event; ambiguous mutation stops for
      reconciliation without retrying a second append.
- [ ] Template/generated parity, help, docs, manifest/provenance,
      install/update/check/uninstall, release ledger, `make check`, and fleet
      validation pass.

## Dependencies

- Parent `07-25-add-routed-review-operator-ux`.
- `platypeeps/sd-github-review` task
  `07-25-establish-trusted-finding-adjudication`.

## Out of Scope

- Adjudication schema, trust policy, private event storage, learning promotion,
  effectiveness scoring, or automatic reviewer changes.
