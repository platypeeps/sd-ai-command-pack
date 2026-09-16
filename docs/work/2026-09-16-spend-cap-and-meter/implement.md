# Implement — spend cap and meter

Four slices, in this order. Slice 1 is not this repository's.

## Step checklist

- [ ] 1. System reservation ledger: `local-sd-db/sd_db/ledger.py` with
      `reserve`, `claim`, `settle`, `lose`, `release_orphans` and `exposure`.
      Delivered by sd:234 slice 8a, in `platypeeps/system`; this item's
      requirement 1 is satisfied when that slice merges and does not open a
      pull request of its own for it. At `a5347185` the module is absent.
- [ ] 2. The pin: `.github/workflows/tests.yml` moves the `platypeeps/system`
      `ref:` (the "Check out the system checkout, for sd_db" step) to the
      commit that carries `ledger.py`. `.github/workflows/**` is sensitive
      under `.github/sd-review.json`, so this is its own owner-reviewed pull
      request, as sd:361 step 5 was.
- [ ] 3. The pack wiring: `review` in `bin/sd-review` reserves the bound
      through `ledger.reserve` before dispatch and passes the bills at their
      cap as `capped_bills` to `reviewer_chain` and to `pick`; the bound is
      the byte length over four plus `max_tokens` at the entry's price
      (`design.md`, the assumption). Tests: the cost-row test, the
      concurrent-pair test and the `--provider` refusal naming the month's
      total, all in `tests/test_sd_registry.py` or beside it, and one
      integration test through `review` with an at-cap bill in the database
      and no `capped_bills` handed in, asserting both the fallthrough and
      the `--provider` refusal. The bound uses `price.in` and `price.out`
      per million tokens (`design.md`, the bound).
      `WORKFLOW.md`'s "recorded ceiling, not an enforced one" paragraph changes
      in the same pull request.
- [ ] 4. OWNER ONLY: one live `GET https://www.minimax.io/v1/token_plan/remains`
      with the operator's key, recorded as a fixture under `tests/fixtures/`.
      Then the reader: two `meter` rows per answer, the zero-window skip in
      fallthrough and the refusal by name on a direct pick, asserted with each
      window at zero in turn. No lane calls the endpoint. The call site: at
      `review` start, for each bill whose entry carries `meter:`, the newest
      `meter` row per window is read from the database; a window at zero puts
      the bill into `capped_bills` beside the ledger's over-cap bills; no row
      means not capped. The rows are refreshed by the same `review` call
      through the recorded-fixture reader in tests and the live `GET` in
      production, and a `GET` that fails leaves the last rows standing and
      says so in the run's output.

## Verification

- Slice 3, before the work: `grep -c capped_bills bin/sd-review` is 0 at
  `2eafa78b`; after, it is at least 2, and the three named tests fail on the
  unwired code and pass on the wired one.
- Slice 4, before the work: `git grep -l token_plan -- bin tests` lists no
  file; after, it lists the reader and its test.
- Every slice: `make check` rc 0 with 0 `FAILED`/`ERROR`, and `bin/sd-docs-lint`
  ends `sd-docs-lint: clean`.
- Not verifiable here: the live meter call (slice 4, owner only) and the
  concurrent race against a real database, which the test simulates with two
  threads and one connection each.
