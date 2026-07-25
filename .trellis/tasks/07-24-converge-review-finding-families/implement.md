# Implementation plan: review-family convergence gate

## 1. Define fixtures and contracts

- Add good/base/failure fixtures for family normalization, same-family
  recurrence, unrelated families, changed exact heads, malformed findings, and
  unknown categories.
- Add controller scenarios for second-family stop, completed sibling audit,
  one batched fix commit, post-audit recurrence, and explicit round extension.

## 2. Add family state to unified review

- Consume the typed family vocabulary from
  `feed-review-learnings-into-review-planning`.
- Extend the versioned review state/receipt with bounded finding-family and
  sibling-audit records.
- Implement deterministic transitions and stable reason codes without prompt
  parsing or shell-string execution.

## 3. Implement the sibling-audit boundary

- Generate the applicable family matrix from changed paths, task artifacts,
  and normalized findings.
- Route it through the configured local adversarial reviewer and retain a
  visible unavailable/failed result when that reviewer cannot run.
- Aggregate all current findings, dispositions, and sibling results before
  allowing a fix batch.

## 4. Integrate remediation and reporting

- Enforce one scoped fix commit and one `sd-check` result before redispatch.
- Use the portable structured question only for a repeated post-audit family
  that needs explicit round extension.
- Add round, family, sibling, cost, and limitation fields to human/JSON output.

## 5. Validate

- Run focused review-controller, learning, remediation, exact-head, and report
  tests.
- Run generated parity, install audit, `make sync`, and `make check`.
- Dogfood on a seeded state-controller fixture and verify a same-family cluster
  converges in one audit/fix batch.

## Delivered Implementation

- Extended the internal exact-scope local-review stage with a strict,
  exact-head schema-version-1 family-evidence boundary rather than adding a
  public command or a parallel review controller.
- Added the versioned family vocabulary, original-label preservation,
  deterministic family audit matrices, second-round sibling-audit gating,
  clean/check/batch evidence validation, and post-audit structured-extension
  gating.
- Kept remote dispatch outside the stage. The future unified controller stores
  the bounded evidence and consumes the stage's family gate, remote eligibility,
  telemetry, and exact-head receipt.
- Added subprocess fixtures for same and unrelated families, successful and
  failed audits, one-commit enforcement, wrong-head rejection, and explicit
  post-audit extension.
