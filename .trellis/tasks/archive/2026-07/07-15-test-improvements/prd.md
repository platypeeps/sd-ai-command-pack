# Test concision + review-local fixture speedup

## Goal

Two clean test improvements from the optimization review's deferred tail:
parametrize repeated assertion blocks for concision + better failure reporting,
and class-scope the heavy `make_repo` fixture in `test_review_local` to trim the
slowest shard (the current CI wall-clock floor). Tests-only, 100% installer
coverage held.

## Requirements

- R1 (assertion parametrization): Convert copy-pasted assertion blocks to
  data-driven `subTest` loops, primarily in `tests/test_generated_parity.py`
  (the ~14 near-identical `for adapter in [...]: assertTrue(is_file);
  assertIn(phrase)` blocks and the long hand-written `assertTrue(...is_file())`
  runs) and any equally repetitive block in `tests/test_install_core.py`. Every
  existing assertion must still run (same targets, same expected values) — this
  is a re-expression, not a reduction of what's checked. `subTest` gives
  per-case failure reporting.
- R2 (class-scoped review-local fixture): `test_review_local` calls `make_repo()`
  27x (once per test). Build the canonical repo once per class (setUpClass
  template dir) and give each test a `shutil.copytree` copy, mirroring the
  housekeeping fixture already in `install_test_support.py`. Perfect per-test
  isolation (these tests run the review-local.sh script and write outputs) --
  verify determinism across reruns. If `make_repo` is too light for class-scoping
  to help (it may be -- assess and MEASURE), leave it per-test and say so.

## Constraints (HARD)

- 100% line+branch installer coverage held; every behavior assertion preserved
  (`make test` is the oracle -- run after each change).
- Tests-only: no change to `install.py`/`installer/`, scripts, docs, or shipped
  payload -> NO version bump.
- `make lint` (ruff + mypy) stays green -- do NOT introduce star imports or
  `# noqa` that disables real checks.
- Measure `time make test` before/after and report honestly; if a change is
  neutral or risky, drop it.

## Explicitly dropped (assessed, not worth it)

- The per-module `_support` import-shim collapse: the only line-saving form is
  `from install_test_support import *`, which reintroduces the F405
  "possibly-undefined name" lint gap the maintainer deliberately avoided with
  explicit rebindings (an explicit `from ... import (...)` list is the same
  length, so there is no clean LOC win). Left as-is.

## Acceptance Criteria

- [ ] Repeated assertion blocks parametrized with `subTest`; every prior
      assertion still executes; `make test` green at 100% installer coverage.
- [ ] `make_repo` class-scoping applied if it measurably helps `test_review_local`
      (with per-test isolation verified), or left per-test with a measured reason.
- [ ] `make lint` green (no star imports / no lint-weakening noqa); measured
      runtime delta reported.

## Non-goals

- The review-local.sh fractional-timeout change (shipped-script change -> belongs
  in the micro-refactors batch, and its value is ~1.4s on one test).
- The import-shim collapse (dropped above).
