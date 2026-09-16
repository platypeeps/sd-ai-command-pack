# Implement — spend cap and meter

Four slices, in this order. Slice 1 is not this repository's.

## Step checklist

- [x] 1. System reservation ledger: `local-sd-db/sd_db/ledger.py` with
      `reserve`, `claim`, `settle`, `lose`, `release_orphans` and `exposure`.
      Delivered by sd:234 slice 8a, `platypeeps/system` #406 at `4b240d28`;
      this item opened no pull request for it. At `a5347185` the module was
      absent; measured 2026-09-16 in the system checkout, the six names are
      top-level functions of the module.
- [x] 2. The pin: `.github/workflows/tests.yml` moves the `platypeeps/system`
      `ref:` (the "Check out the system checkout, for sd_db" step) to the
      commit that carries `ledger.py`. Done by sd:719's #999 (`c6879551`),
      which pinned `4b240d284c1ce9d2168ff7688113def45e0a8a2e`; measured
      2026-09-16, `grep -n 'ref:' .github/workflows/tests.yml` names that
      sha. No pin pull request from this item.
- [ ] 3. The pack wiring, two sites. `review` in `bin/sd-review` reaches
      the ledger through `sd_handoff_rows.library()` and
      `connect(sd_db, write=True)`, calls `release_orphans` once before the
      chain is built, and passes the bills at their cap as
      `capped_bills: Mapping[str, str]`, bill name to exposure line, to
      `reviewer_chain` and to `pick`. `run_provider`, for a `url` entry,
      once `request_prompt` is built and immediately before `client(...)`:
      `reserve` with the bound, `claim` in the next statement, and in a
      `finally` after the call `settle` with the usage or `lose` without
      usable usage (`design.md`, the lifecycle); a `reserve` refusal is a
      `REFUSED` outcome carrying the exposure line, which fallthrough passes
      over and a direct pick reports. A preflight goes through the same
      path and is reserved the same; `--explain`, `--dry-run` and a failed
      check never reach it. The bound is the UTF-8 byte length of
      `request_prompt`, the string handed to `client`, over three, times
      `price.in`, plus `max_tokens` times `price.out`, per million tokens
      (`design.md`, the bound and the assumption). Tests: the cost-row
      test, the concurrent-pair test and the `--provider` refusal naming
      the month's total, all in `tests/test_sd_registry.py` or beside it;
      one integration test through `review` with an at-cap bill in the
      database and no `capped_bills` handed in, asserting both the
      fallthrough and the `--provider` refusal; four boundary tests,
      `library()` refusing and `connect` refusing, each for an uncapped
      bill (dispatched) and a capped one (refused naming the fault); a
      preflight test asserting a ledger row exists after the probe; and a
      lifecycle test with a fake client asserting `sending` before the
      call, `run` after a response with usage and `bound` after a timeout.
      `WORKFLOW.md`'s "recorded ceiling, not an enforced one" paragraph
      changes in the same pull request.
- [ ] 4. OWNER ONLY, the fixture half done: one live
      `GET https://www.minimax.io/v1/token_plan/remains` with the operator's
      key, recorded as `tests/fixtures/minimax/token_plan_remains.json` in
      #1001 (`f39f120a`).
      Then the reader: the one `general` entry selected from `model_remains`
      (none or two, capped naming the count), its two fields validated
      (missing, non-numeric, NaN, infinity, outside 0 to 100: capped naming
      the field and the value, no row written), two `meter` rows per good
      answer, the zero-window skip in fallthrough and the refusal by name on
      a direct pick, asserted with each window at zero in turn. No lane
      calls the endpoint. The call site, at `review` start, for each bill
      row carrying `meter:` (`Bill.meter`, keyed through the provider's
      bill, not a provider field), in this order: the `GET` to the pinned
      `https://www.minimax.io/v1/token_plan/remains` with the key named by
      the bill's `meter_env:`; a good answer persisted as the two rows; then
      the newest `meter` row per window read back from the database. A
      window at zero puts the bill into `capped_bills` beside the ledger's
      over-cap bills; no row, or a newest row older than the five-hour
      window, does the same, naming the missing or stale reading. The
      `GET` is the recorded-fixture reader in tests and the live call in
      production; a `GET` that fails writes nothing, says so in the run's
      output, and the read-back sees the prior rows, capped by the rule
      above when they are absent or stale. Tests: one edited fixture per
      validation case above; a `GET` that fails (recorded as a connection
      error in the fixture) leaves the previous two rows as the newest and
      the run's output names the failure; a fresh answer written before
      classification, asserted by seeding a zero row, answering 100 from
      the fixture and reading an uncapped bill; and, in slice 3, a
      reservation whose pid is dead is swept by `release_orphans` at the
      next `review` start, asserted by writing the row with a pid that does
      not exist and reading `exposure` before and after.
- [ ] 3a. Beside slice 3: a `url` entry on a capped bill without `price.in`,
      `price.out` or `max_tokens`, or with a value that is not a finite
      non-negative number (a string, NaN, a negative), is refused at registry
      read and on the database-merged read naming the entry, the key and the
      value, with one test per case in `tests/test_sd_registry.py`; a
      pinned-meter test: a `meter:` naming any other scheme, host, port or
      path is refused naming the value and the pinned four, and the reader
      sends no request, with the same-host `http://` value as one of the
      cases; and a `meter_env` test: a bill with `meter:` and no
      `meter_env:` is refused at registry read naming the bill.

## Verification

- Slice 1: `grep -n '^def ' local-sd-db/sd_db/ledger.py` in the system
  checkout at `4b240d28` or later lists the six names among its top-level
  functions; at `a5347185` the file is absent.
- Slice 2: `grep -n 'ref:' .github/workflows/tests.yml` names a system
  commit at or after `4b240d28`; measured 2026-09-16, it names
  `4b240d284c1ce9d2168ff7688113def45e0a8a2e`.
- Slice 3, before the work: `grep -c capped_bills bin/sd-review` is 0 at
  `2eafa78b`; after, it is at least 2, `grep -c 'ledger\.' bin/sd-review`
  is at least 4 (`reserve`, `claim`, `settle`, `lose`), and the named tests
  fail on the unwired code and pass on the wired one.
- Slice 4, before the work: `git grep -l token_plan -- bin tests` lists no
  file; after, it lists the reader and its test.
- Every slice: `make check` rc 0 with 0 `FAILED`/`ERROR`, and `bin/sd-docs-lint`
  ends `sd-docs-lint: clean`.
- Not verifiable here: the live meter call (slice 4, owner only) and the
  concurrent race against a real database, which the test simulates with two
  threads and one connection each.
