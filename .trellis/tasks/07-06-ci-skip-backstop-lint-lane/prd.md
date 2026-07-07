# Add CI skip backstop and lint lane

## Goal

Three CI gaps from the 2026-07-06 deep review:

1. **Silent-skip exposure**: the suite has 60 environmental skip
   guards (`bash` 48, `node` 8, `jq` 1, root 3). Today zero tests skip
   locally or on ubuntu-latest, but `unittest discover` exits 0 on
   skips — if a runner image ever dropped node or changed shell
   assumptions, up to ~57 tests would vanish silently and CI would
   stay green.
2. **No Python/JS lint lane**: ruff has been run locally (a
   `.ruff_cache/` for ruff 0.15.20 exists) but is unconfigured,
   unpinned, and absent from CI, so its signal is invisible and
   unreproducible. The 1,186-line `review-preflight.mjs` gets only a
   `node --check` syntax test.
3. **Linux-only matrix**: developers are on Darwin; the one confirmed
   shell crash from this review (bash 3.2 empty-array, task
   07-06-fix-bash32-empty-array-crash) is macOS-specific behavior that
   ubuntu CI can never catch.

## Requirements

- R1: Fail CI on any skipped test — parse the unittest summary for
  `skipped=` in the workflow, or add an env flag (e.g.
  `SD_PACK_TESTS_REQUIRE_TOOLS=1` set in tests.yml) that converts
  `skipTest` into `fail` in CI while keeping local skips friendly.
- R2: Add ruff to CI: pin `ruff==<version>` in requirements-dev.txt,
  add `[tool.ruff]` config (consider consolidating `.coveragerc` into
  a new `pyproject.toml` at the same time), run `ruff check` over
  install.py, scripts/, templates/scripts/, tests/ in the security or
  unittest job. Fix or explicitly ignore the initial findings.
- R3: Add a `macos-latest` leg to the unittest matrix (at minimum for
  one Python version) so BSD-tool and bash-3.2 behavior is exercised.
- R4: Keep `.githooks`/local flows working; document the lint command
  in the Verify/CONTRIBUTING docs (coordinates with
  07-06-contributor-experience-baseline).

## Acceptance Criteria

- [ ] A deliberately-injected skip (temporary test) fails CI;
  reverted after verification.
- [ ] `ruff check` runs green and pinned in CI.
- [ ] macOS leg green in CI.
- [ ] Full battery green.

## Notes

- Origin: 2026-07-06 deep review (Testing findings 3/5/6; tooling
  findings 3/4). actionlint remains explicitly deferred per
  07-03-pack-shell-lint unless a concrete workflow defect appears.
