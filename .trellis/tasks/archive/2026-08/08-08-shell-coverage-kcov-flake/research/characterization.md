# Characterization attempt (implement.md steps 1-2, 2026-08-09)

## Reproduction (step 1)

Method: repeated single-test invocation of
`tests.test_bookkeeping_validator.BookkeepingValidatorTests.test_completion_successor_finds_recent_anchor_in_long_history`
via `.venv/bin/python -m unittest`, on the developer machine (macOS,
Darwin 25.6.0, Apple Silicon, 16 cores) — the environment where the test
has never been observed to fail. Baseline single run: 2.5 s wall.

- Serial phase: 10 iterations → **10 pass, 0 fail**.
- Mandatory concurrent-load phase: 16 `yes > /dev/null` spinners (one
  per core, full CPU saturation) running throughout → 15 iterations →
  **15 pass, 0 fail**.

Total 25 iterations, zero hits. **Conclusion: not reproduced.** This is
the expected negative result: both occurrences happened on
`ubuntu-latest` runners inside the full-suite kcov lane (272–316 s suite
wall time), and neither the runner kernel, the memory envelope, nor the
kcov-instrumented sibling processes are reproducible on this machine.
CPU saturation alone did not surface the failure, which weakly
disfavors pure CPU contention and leaves memory/fd pressure and
runner-specific I/O behavior as the open candidates.

## `fatal: could not parse HEAD` analysis (step 1, occurrence 2)

`git commit` exits 128 with this message when HEAD resolution fails at
commit time. In a repository where 100+ commits had just succeeded and
every fixture git call runs `-c gc.auto=0` (no background repack, no
pack-refs racing — `tests/install_test_support.py:223-231`), the
plausible transient causes are:

- a failed/short read of `.git/HEAD` or the loose ref it names under
  system pressure (ENOMEM/EMFILE-class failure inside git's ref
  resolution), or
- HEAD naming a ref whose loose file could not be opened at that
  moment.

Today's assertion output cannot distinguish these — it shows only git's
one-line fatal. That is precisely the gap `prd.md` requirement 7 closes
(post-failure capture of HEAD bytes, loose-ref existence, packed-refs
membership, lock files). No further speculation recorded; the next
occurrence carries the discriminating evidence.

## Message-string couplings (step 2)

Grep of `tests/` for the literals being enriched (`Git could not …`,
`could not inspect`, `could not enumerate`, `finalization delta`,
`whitespace validation could not`, `inspect parents for`) and for the
four affected reason codes:

- **No test asserts any of the message literals** owned by the
  bookkeeping validator. The `could not inspect` matches in
  `test_review_full_check.py:219,236`, `test_housekeeping_result.py:333`
  and `test_housekeeping.py:1185` belong to other scripts' messages.
- Reason-code-only assertions (unchanged by this task):
  `test_bookkeeping_validator.py:1146,1187,1228,1497`;
  `test_pr_eligibility.py:365`.

Coupling list: **empty** — no existing assertions need message updates;
the only permitted existing-test edit remains the additive subject-probe
upgrade (implement.md step 6).

## Spec touch check (implement.md step 8)

`grep` of `.trellis/spec/` (including
`.trellis/spec/tooling/bookkeeping-validator.md`) for every enriched
message literal (`could not inspect`, `could not enumerate`,
`finalization delta`, `whitespace validation could not`, `inspect
parents for`, `Git could not`) returned no matches. **No spec change
needed.**
