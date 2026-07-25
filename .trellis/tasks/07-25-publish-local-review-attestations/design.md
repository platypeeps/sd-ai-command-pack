# Local Review Attestation Publisher Design

## Boundary

The unified `sd-review` coordinator is the sole local producer. It reuses its
canonical exact-head local receipt, projects only the allow-listed v2 envelope,
and invokes the repository's trusted ingestion workflow. It never writes the
assurance/gate Checks directly and never interprets router-owned trust policy.

```text
sd-review exact-head local receipt
  -> bounded v2 envelope
  -> trusted GitHub workflow dispatch
  -> sd-github-review authorization/receipt/Checks
  -> typed publication result returned to sd-review
```

Capability discovery selects this branch only for an explicit compatible
local-attested route. Publication identity and fingerprint persist with the
local attempt so resume is idempotent. Ambiguous dispatch enters
reconciliation-required state; no remote fallback is allowed.

The final report states both facts separately: local tools performed the review
and an authorized repository actor attested its bounded result on GitHub. It
does not infer independence or third-party verification.

## Rollback

Disable publication only through an explicit reviewed route/configuration
change. Existing local receipts and GitHub attempt evidence remain immutable;
rollback never converts them to `none` or remote review receipts.
