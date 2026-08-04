# Measure coverage for the unmeasured shipped runtime surface

## Goal

Bring the roughly 12,600 unmeasured lines of shipped runtime — Node, shell, and `.github/scripts` — under coverage measurement, so a source-text assertion is distinguishable from a behavioral test.

## Requirements

- Add `.github/scripts/*.py` to the include list in `.coveragerc:6` (a one-line change) and land that first.
- Adopt a JS coverage tool (c8 or equivalent) for `scripts/sd-ai-command-pack-review-preflight.mjs` (4,547 lines, today checked only by `node --check` at tests.yml:350).
- Adopt a shell coverage tool for the `.sh` surface, including `scripts/sd-ai-command-pack-full-check.sh`.
- Publish measured coverage before gating on it; do not add failing floors in the same change.
- Replace at least the source-text assertion at `tests/test_full_check.py:1576` with a behavioral test once the shell lane is measured. **Done (2026-08-04):** `test_full_check_script_runs_pack_source_drift_gates` no longer greps the script text — it runs `run_pack_source_drift_gates` on a clean pack fixture (asserts the gate's summary output) and asserts the `PACK_DRIFT=0` toggle short-circuits it. Failure paths stay covered behaviorally in `tests/test_pack_drift.py`.

## Acceptance Criteria

- [x] `.github/scripts/bookkeeping_ci_scope.py` (477 lines) reports a coverage number.
- [x] review-preflight.mjs reports a coverage number in CI.
- [x] The shell lane reports a coverage number in CI.
- [x] Floors are added only in a follow-up change, at or below measured values. (No floor added in this task — all three lanes publish a measured number and hard-fail only on a zero-line/plumbing break; floor-setting is deferred, per R4.)
- [x] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-050 (P1 · L · Verified · testing).
- Ratio today: ~12,600 unmeasured lines versus 16,064 measured statements.
- The ~262-line Python program run via `python3 -` at full-check.sh:610 is structurally unmeasurable and may need extracting to a file first.
- Subprocess coverage plumbing already exists (`tests/coverage_sitecustomize/sitecustomize.py:22`), so the omission is configuration, not capability.
- Cross-ref A-033 (fixed): that entry closed by *documenting* shell and `.github/scripts` as coverage-exempt. This task re-opens that decision and adds surfaces the exemption never covered.
- **Verified 2026-07-28:** `.coveragerc:6` is the `[run] include` list and `.coveragerc:34` is a separate `[report] include` narrowed to `install.py` + `installer/*` with `fail_under = 100`. Adding `.github/scripts/*.py` to `[run]` therefore measures without touching the strict gate, so R1 is genuinely zero-risk and lands alone.
- **Nuance the finding omits:** `.github/scripts/*.py` is not entirely unchecked — `tests.yml:346` already runs mypy over `bookkeeping_ci_scope.py` and `check-command-surface-drift.py`. They are type-checked but not coverage-measured.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.
- **Lane 1 measured baseline (2026-07-31, PR #292):** `bookkeeping_ci_scope.py` 77% — 233 statements, 51 missed, 94 branches, 21 partial — via `coverage run -m unittest tests.test_bookkeeping_ci_scope` + `combine` + `report --include=".github/scripts/*"`. No floor set (R4). `[report]` strict gate confirmed unchanged.
- **Lane 2 measured baseline (2026-07-31/08-01, PR #301):** `review-preflight.mjs` 52.3% — 2,478/4,738 lines — via `c8 --clean=false --include="scripts/sd-ai-command-pack-review-preflight.mjs"` wrapping every bookkeeping-mode invocation in tests.yml, reported by CI run 30675259927 job "CI scope" step "Report review preflight JavaScript coverage". No floor set (R4); the step hard-fails only on a 0/0 zero-lines measurement, not on a low percentage. Lane 3 (shell) remains open — task stays `in_progress`.
- **Lane 3 wiring (2026-08-04, branch `feat/measure-shell-coverage-lane3`):** shell chosen tool = **kcov** (Linux/ptrace); inline-Python scope decision = **exclude + defer** (`full-check.sh` heredoc runs on `python3` stdin, so bash never executes it and kcov cannot attribute it — extraction is a separate task). Implementation: `.github/scripts/kcov-bash-shim.sh` stands in for the tests' bash via a new `SD_AI_COMMAND_PACK_TEST_BASH` override in `tests/install_test_support.py`; a dedicated `shell-coverage` CI job runs the whole suite under the shim, merges kcov runs, and publishes the `scripts/sd-ai-command-pack-*.sh` line count via `report-shell-coverage.sh` + `summarize_shell_coverage.py` (hard-fails on a zero measurement, no floor — R4). A-033 exemption reversed in CONTRIBUTING.md + README.md (shell now measured; GitHub workflow YAML stays exempt). **Verified locally:** shim exit-code passthrough, summarizer count + zero-guard (exit 2), suite green with override unset and set to plain bash (121 shell-touching tests), ruff/mypy/shellcheck/yaml clean, deterministic pack-source-drift gate clean (install audit 210, twins 205, env-var docs). **Not locally verifiable (kcov is Linux-only, no macOS support):** the actual non-zero shell coverage number — proven only by the first green `shell-coverage` CI run. The Lane 3 acceptance box stays unchecked until that CI run records the baseline here.
- **Lane 3 measured baseline (2026-08-04, PR #320, CI run 30947982168):** shipped shell **29.7% — 349/1174 lines** — kcov v43 (built from pinned source `a39874f9`, Ubuntu 24.04) wrapping every `bash SCRIPT` the suite spawns via `kcov-bash-shim.sh`, merged and reported by the `shell-coverage` job's "Report shipped shell coverage" step. No floor set (R4); the step hard-fails only on a 0/0 zero-lines measurement. **Root-cause note for future maintainers:** kcov's shell-source collector engages only when the coverage *target is the script* — the shim invokes `kcov OUT SCRIPT args`, not `kcov OUT bash SCRIPT` (the latter targets the stripped bash binary, finds no DWARF, and silently records `total_lines=0`). Scope is the plain `bash SCRIPT [args]` invocation form (full-check.sh, review-local.sh, review-scope.sh, review-full-check.sh); `bash -c` source-form and `bash -n` syntax-check invocations are not kcov-attributable and fall through to the real bash. The shim grants no exec bit (kcov reads 0644 scripts via the shebang; a chmod would dirty the tracked tree and break review-local.sh + surface-closure). All non-shell jobs and the 1510-test suite under the shim are green.
