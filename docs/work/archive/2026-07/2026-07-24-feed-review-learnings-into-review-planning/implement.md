# Implementation plan: current review-learning planning signal

## 1. Extend typed scanner output

- Add JSON fixtures for bounded clusters, representative signatures,
  truncation, freshness, and unavailable GitHub evidence.
- Render Markdown and human output from the same normalized cluster objects.

## 2. Add review-attempt collection

- Run one bounded scan at review-attempt start and record a typed receipt.
- Add optional private cache validation using repository identity, schema,
  watermark, lifetime, permissions, and atomic replacement.
- Preserve read-only scan behavior and explicit-only tracked update mode.

## 3. Select and consume relevant learning

- Map intended changed paths to normalized path families.
- Pass only applicable bounded clusters to local review and the convergence
  child; record evidence source, age, truncation, and limitations.
- Never send historical comment bodies to remote providers or grant confidence
  from history alone.

## 4. Validate

- Test one-scan-per-attempt reuse, stale/corrupt cache, unavailable/rate-limited
  GitHub, path-family selection, and zero tracked writes.
- Run focused learning/review tests, generated parity, install audit,
  `make sync`, and `make check`.
