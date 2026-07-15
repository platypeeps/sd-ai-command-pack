# Test speedups: in-process installs + class-scoped git fixtures

## Goal

Shave more time off the (already-parallel, ~20s) suite by cutting per-test
process/git overhead, without losing behavior coverage or the enforced 100%
line+branch installer coverage. Conservative and bounded — value here is modest,
so correctness and coverage take strict priority over maximal conversion.

## Requirements

- R1 (class-scoped git fixtures, primary): Build the expensive git-repo
  fixtures once per test class and give each test a cheap copy. The clearest win
  is `make_housekeeping_repo` (~15 git subprocesses, ~211ms × 22 tests in
  test_housekeeping); also assess `make_repo` / `make_pack_source_fixture`.
  Build the canonical repo in `setUpClass` into a template dir; per test
  `shutil.copytree` it and rewrite the `origin` remote URL as needed. Mutation
  isolation must be perfect — no test may see another's writes.
- R2 (in-process installs, bounded): Convert `self.run_install(...)` subprocess
  calls to `install.main([...])` under `contextlib.redirect_stdout` ONLY where
  the test just installs then inspects the filesystem/exit code. KEEP the
  subprocess form wherever the test depends on real-process semantics: `argv`
  handling, `os.environ`/PATH isolation, exit-code-as-process-status, combined
  stderr, or the symlink-exec path. Do not chase the count — convert the safe
  majority, leave the rest.

## Constraints (HARD)

- 100% line+branch coverage on install.py + installer/* MUST hold. Run
  `make test` after every batch of conversions; if a conversion drops a branch
  to uncovered (e.g. the subprocess entry path stops being exercised), keep
  enough subprocess coverage to hold the gate — do NOT add `pragma: no cover`
  or weaken `--fail-under`.
- No behavior assertion may be lost or weakened. Every existing `assertIn`/
  status/exit-code check stays. The suite is the oracle.
- Only touch `tests/`. No change to install.py/installer/, scripts, docs.
- Net effect must be neutral-or-faster: measure wall-clock before/after
  (`make test`), report the delta honestly. If a change doesn't help or adds
  risk, drop it.

## Acceptance Criteria

- [ ] Class-scoped fixtures in place for the heavy repos; per-test isolation
      verified (full suite green, no cross-test contamination).
- [ ] Safe happy-path installs converted to `install.main()`; risky ones kept
      as subprocess with a one-line reason where non-obvious.
- [ ] `make test` green, installer coverage 100% line+branch, scripts ≥76%;
      `make lint` green; measured runtime reported (expect same-or-faster).

## Non-goals

- The star-import test-shim collapse and assertion-parametrization (separate
  concision items, deferred).
- Converting subprocess calls whose whole point is process/CLI-boundary testing.
- Adding a parallel-test dependency (already handled by the module-sharded
  runner).
