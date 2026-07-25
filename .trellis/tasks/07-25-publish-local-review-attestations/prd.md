# Publish local review attestations

## Goal

Publish bounded exact-head local sd-review evidence to sd-github-review without invoking a GitHub-side reviewer.

## Background

`sd-review` already owns exact PR scope, deterministic checks, local provider
execution, normalized local receipts, finding disposition, and exact-head
re-entry. `sd-github-review` will own the v2 local-attestation, trust, receipt,
and stable Check contracts. This task connects those boundaries; it does not
create a second review command or redefine router policy.

## Requirements

- Extend the unified `sd-review` PR lifecycle; do not add or restore a public
  `sd-review-local` command and do not require a separate user command merely
  to publish evidence.
- Discover whether the exact repository/head is configured for a v2
  local-attested route before publishing. A direct-handler, managed, `none`,
  absent, invalid, or incompatible setup must not be reinterpreted as local-
  attested.
- Publish only after deterministic checks pass and the selected local provider
  plan reaches a terminal normalized result for the exact clean PR head.
- Build the bounded contract from the canonical local receipt: repository, PR,
  head, lane, attempt, invocation/receipt/content/configuration digests,
  tool/profile/version, terminal outcome, finding/disposition counts,
  timestamps, and evidence digest.
- Exclude source, paths, patches, prompts, raw findings, transcripts, secrets,
  configuration values, and local artifact paths.
- Submit through the repository's authenticated trusted workflow so
  `sd-github-review` derives actor/workflow authority and owns trust,
  authorization, idempotency, outcomes, and Check projection.
- Preserve the same attempt and evidence fingerprint across safe retries.
  Wrong-head, rejected, conflicting, or ambiguous publication fails closed and
  never dispatches a remote reviewer as fallback.
- Report the resulting local-attested receipt, stable assurance/gate state, and
  the `repository_attested` limitation. Never call it independent or claim
  GitHub verified the model execution.
- Optional provider/model/token/latency/cost metadata is bounded and marked
  `self_reported_local`; absence does not synthesize zero usage.

## Acceptance Criteria

- [ ] Exact-head clean, findings, failed, and cancelled local receipts produce
      canonical bounded publication requests with matching terminal outcomes.
- [ ] No GitHub-side reviewer, Copilot request, PR-Agent adapter, review, or
      comment is dispatched by the local-attested path.
- [ ] Dirty, stale, wrong-head, malformed, absent-provider, and incomplete
      local evidence cannot publish positive assurance.
- [ ] Matching retry is idempotent; conflicting or ambiguous publication stops
      without a fallback reviewer.
- [ ] Direct-handler, managed, `none`, absent, invalid, and incompatible setup
      cases retain their existing behavior and cannot consume the attestation
      publisher accidentally.
- [ ] Generated skills/templates/docs and coordinator tests expose one unified
      `sd-review` lifecycle with no duplicate public command.
- [ ] Final reports distinguish local review execution, repository-attested
      GitHub assurance, and independent remote review.

## Dependencies

- `platypeeps/sd-github-review:07-25-define-local-review-attestation-contracts`.
- `platypeeps/sd-github-review:07-25-ingest-local-review-attestations`.
- The shipped unified `sd-review` exact-scope local receipt lifecycle.

## Out of Scope

- Choosing trust policy, mapping outcomes to branch-protection Checks, or
  creating a second local review workflow.
- Uploading raw local review artifacts or claiming cryptographic proof of model
  execution.
