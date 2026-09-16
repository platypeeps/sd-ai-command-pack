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
- [ ] 3. The pack wiring: `review` in `bin/sd-review` reaches the ledger
      through `sd_handoff_rows.library()` and `connect(sd_db, write=True)`,
      reserves the bound through `ledger.reserve` after the preflight,
      `--explain`, `--dry-run` and failed-check exits and immediately before
      each real `run_provider`, and passes the bills at their cap as
      `capped_bills: Mapping[str, str]`, bill name to exposure line, to
      `reviewer_chain` and to `pick`; a `reserve` refusal for a bound that
      would pass the cap is the same outcome. The bound is the serialized
      `request_prompt` byte length over three plus `max_tokens`, at
      `price.in` and `price.out` per million tokens (`design.md`, the
      bound and the assumption). Tests: the cost-row test, the
      concurrent-pair test and the `--provider` refusal naming the month's
      total, all in `tests/test_sd_registry.py` or beside it, and one
      integration test through `review` with an at-cap bill in the database
      and no `capped_bills` handed in, asserting both the fallthrough and
      the `--provider` refusal. The bound uses `price.in` and `price.out`
      per million tokens (`design.md`, the bound).
      `WORKFLOW.md`'s "recorded ceiling, not an enforced one" paragraph changes
      in the same pull request.
- [ ] 4. OWNER ONLY, the fixture half done: one live
      `GET https://www.minimax.io/v1/token_plan/remains` with the operator's
      key, recorded as `tests/fixtures/minimax/token_plan_remains.json` in
      #1001 (`f39f120a`).
      Then the reader: two `meter` rows per answer, the zero-window skip in
      fallthrough and the refusal by name on a direct pick, asserted with each
      window at zero in turn. No lane calls the endpoint. The call site: at
      `review` start, for each bill row carrying `meter:` (`Bill.meter`, keyed
      through the provider's bill, not a provider field), the newest `meter`
      row per window is read from the database; a window at zero puts the
      bill into `capped_bills` beside the ledger's over-cap bills; no row, or
      a newest row older than the five-hour window, does the same, naming
      the missing or stale reading. The destination is pinned to
      `www.minimax.io` and `/v1/token_plan/remains` (`design.md`, the meter). The rows are refreshed by the same `review` call
      through the recorded-fixture reader in tests and the live `GET` in
      production, and a `GET` that fails leaves the last rows standing and
      says so in the run's output; if that leaves no row or a stale one, the
      bill is capped by the rule above. Two focused tests: a `GET` that fails
      (recorded as a connection error in the fixture) leaves the previous
      two rows as the newest and the run's output names the failure; and,
      in slice 3, a reservation whose pid is dead is swept by
      `release_orphans` at the next `review` start, asserted by writing the
      row with a pid that does not exist and reading `exposure` before and
      after.
- [ ] 3a. Beside slice 3: a `url` entry on a capped bill without `price.in`,
      `price.out` or `max_tokens`, or with a value that is not a finite
      non-negative number (a string, NaN, a negative), is refused at registry
      read and on the database-merged read naming the entry, the key and the
      value, with one test per case in `tests/test_sd_registry.py`; and a
      pinned-meter test: a `meter:` naming any other host or path is refused
      naming both, and the reader sends no request.

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
