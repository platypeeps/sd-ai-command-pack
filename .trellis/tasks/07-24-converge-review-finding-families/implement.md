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
