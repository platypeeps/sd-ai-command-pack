# Parallelize the test suite by module

## Goal

Cut test-suite wall-clock (and every CI unittest lane) by sharding the
`unittest` run across worker processes, without losing the enforced 100%
line+branch installer coverage. Deliver it through a single runner script that
both the Makefile and CI call, so the two cannot drift.

## Problem

The suite runs fully serial: one `coverage run --parallel-mode -m unittest
discover -s tests`. Measured baseline ~84s wall-clock, of which the top five
files are ~65% (test_review_local, test_install_audit, test_housekeeping,
test_install_core, test_full_check) — dominated by real subprocess installers,
git-repo builds, and bash/jq/node calls. The suite is embarrassingly parallel
across modules: no test writes into the source tree, every fixture uses its own
`TemporaryDirectory`, and coverage's `--parallel-mode` already writes one data
file per process for `coverage combine` — so only the runner is serial.

The CI workflow and the Makefile each maintain their own copy of the test
command (plus the absolute coverage env), guarded by a parity test
(`test_generated_parity.test_coverage_dependency_is_declared_and_used_by_ci`).
Any parallel form must stay consistent across both and keep that test honest.

## Requirements

- R1: A shared runner (`.github/scripts/run-tests.sh`) shards the suite by
  module across workers, one `coverage run --parallel-mode -m unittest
  tests.<module>` per shard, and exits non-zero if any shard's tests fail.
- R2: Coverage is fully preserved: `coverage combine` + the existing
  `--fail-under=100` (installer) and `--fail-under=76` (scripts) gates pass
  unchanged. Installer subprocess coverage still works (the runner exports the
  absolute `COVERAGE_PROCESS_START`/`COVERAGE_FILE`/`PYTHONPATH` rig).
- R3: The skipped-test gate still works — the runner writes `unittest-output.log`
  for the existing `skipped=[1-9]` grep.
- R4: Both `make test` and the CI unittest lane call the runner (no duplicated
  command), and the parity test is updated to pin the runner + its rig contract
  instead of the old inline command.
- R5: Portable and clean: bash 3.2-safe (macOS), shellcheck `-S warning` clean,
  no repo pollution (shard logs in a temp dir), and the empty
  `tests/test_install.py` facade (exits 5, "no tests") is excluded.

## Acceptance Criteria

- [ ] `make test` and `bash .github/scripts/run-tests.sh` + combine + reports
      both pass with installer coverage at 100% (line+branch).
- [ ] Measured wall-clock materially reduced (~84s → ~20s locally at 8 workers;
      ~3× expected on 4-vCPU CI runners).
- [ ] `make lint` (ruff/mypy/shellcheck) and `make full-check` pass; generated
      Obsidian KB refreshed.
- [ ] Parity test green against the runner-based workflow/README/Makefile.

## Non-goals

- The larger in-process `install.main()` conversion and class-scoped git
  fixtures (bigger refactors; tracked separately) — this task is the runner-level
  parallelization win only.
- Adding a parallel test dependency (pytest-xdist etc.): the runner uses xargs +
  coverage's existing parallel mode, no new deps.
