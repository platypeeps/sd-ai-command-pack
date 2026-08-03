# Implement: review_preflight in-process install conversion

## Preconditions

- `run_install_inproc` exists in `tests/install_test_support.py` (verified).
- review_preflight has 54 `run_install` call sites (~56 runtime invocations),
  0 `extra_env=`, 0 in-proc (verified).

## Steps

1. Record baseline under the FULL CI environment (verified empirically: the 3
   coverage vars alone are NOT enough — without `SD_AI_COMMAND_PACK_PYTHON` the
   preflight's python helper falls back to a python that, under
   `COVERAGE_PROCESS_START`+`coverage_sitecustomize`, pollutes the fixture's
   changed-path set and flips `test_review_preflight_advises_scope_section_for_generated_files`
   to a spurious failure; run-tests.sh sets all of these — C-1):
   ```
   rm -f .coverage .coverage.*
   COVERAGE_PROCESS_START="$PWD/.coveragerc" \
   COVERAGE_FILE="$PWD/.coverage" \
   PYTHONPATH="$PWD/tests/coverage_sitecustomize" \
   SD_AI_COMMAND_PACK_PYTHON="$PWD/.venv/bin/python" \
   GIT_CONFIG_COUNT=3 \
   GIT_CONFIG_KEY_0=maintenance.auto GIT_CONFIG_VALUE_0=false \
   GIT_CONFIG_KEY_1=gc.auto GIT_CONFIG_VALUE_1=0 \
   GIT_CONFIG_KEY_2=receive.autogc GIT_CONFIG_VALUE_2=false \
   .venv/bin/python -m coverage run --parallel-mode -m unittest \
     tests.test_review_preflight
   ```
   Expect `Ran 66 tests ... OK`. Time it (repeat 2x, take median); note
   wall-clock and test count. Clean up `.coverage.*` after.

2. Enumerate every `self.run_install(` site in `test_review_preflight.py`
   (`grep -n`). For each, read the surrounding test and confirm CONVERT per
   design's rule (all 54 expected to convert; `:713-715` symlink test is CONVERT
   per C-4). Any true exception stays subprocess with a one-line reason.

3. Convert eligible sites: `self.run_install(root)` -> `self.run_install_inproc(root)`
   (and the `result = self.run_install(...)` form likewise). Preserve arguments
   and the exact assertion. Expected result: 0 `run_install`, 54
   `run_install_inproc` (`grep -c`).

4. Prove no global-state leak (C-2/C5): add a throwaway probe (or a temporary
   assert) that snapshots `Path.cwd()`, `dict(os.environ)`, and `list(sys.argv)`
   immediately before and after one `run_install_inproc(root)` and asserts each
   is unchanged. Run it; if any diverges, keep that pattern subprocess or contain
   the leak. Remove the probe before commit (it need not ship).

5. Run the module alone:
   `.venv/bin/python -m unittest tests.test_review_preflight` — expect same test
   count, 0 failures, 0 new skips (AC2). Also time it under the step-1 CI
   coverage environment and record before/after (AC4).

6. Run the full suite through the CI path to catch cross-test state bleed and
   coverage regressions:
   `rm -f .coverage .coverage.*; PYTHON_BIN=.venv/bin/python bash
   .github/scripts/run-tests.sh` (expect rc 0), then
   `.venv/bin/python -m coverage combine` and
   `.venv/bin/python -m coverage report --include="install.py,installer/*"
   --fail-under=100` (expect 100%, AC3).

7. If the installer gate drops below 100% (not expected — entry lines are owned
   by `test_install_core.py:2358`, `:2690`, and `:2204-2219`), run
   `.venv/bin/python -m coverage report --include="install.py,installer/*"
   --show-missing` to name the uncovered line, then STOP and re-scope: add a
   focused installer-entry test that owns it. Do NOT un-convert review_preflight
   fixture calls to recover coverage (violates scope/AC1).

8. `make check` — expect exit 0 (AC5).

## Validation commands (summary)

- V1 module: `.venv/bin/python -m unittest tests.test_review_preflight` -> OK, same count.
- V2 timing: coverage-run wall-clock before vs after under CI coverage env, recorded (AC4).
- V3 isolation probe: cwd/os.environ/sys.argv unchanged across an in-proc install (C5).
- V4 full sharded run: `run-tests.sh` rc 0 (no cross-test bleed).
- V5 coverage gate: installer/`install.py` 100% after combine (AC3).
- V6 `make check` exit 0 (AC5).

## Rollback points

- After step 3, before commit: `git checkout tests/test_review_preflight.py`.
- Post-commit: revert the single commit; test-only, no production/CI impact.

## Commit

Single commit, `tests/test_review_preflight.py` only:
`perf(test): use in-process installer twin in review_preflight`, body noting the
before/after module timing and any calls kept subprocess for coverage/semantics.
Not shipped payload (tests/ absent from manifest/templates): no version bump,
CHANGELOG, or regen.
