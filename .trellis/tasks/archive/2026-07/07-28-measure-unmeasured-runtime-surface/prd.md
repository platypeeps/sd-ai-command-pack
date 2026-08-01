# Measure coverage for the unmeasured shipped runtime surface

## Goal

Bring the roughly 12,600 unmeasured lines of shipped runtime — Node, shell, and `.github/scripts` — under coverage measurement, so a source-text assertion is distinguishable from a behavioral test.

## Requirements

- Add `.github/scripts/*.py` to the include list in `.coveragerc:6` (a one-line change) and land that first.
- Adopt a JS coverage tool (c8 or equivalent) for `scripts/sd-ai-command-pack-review-preflight.mjs` (4,547 lines, today checked only by `node --check` at tests.yml:350).
- Adopt a shell coverage tool for the `.sh` surface, including `scripts/sd-ai-command-pack-full-check.sh`.
- Publish measured coverage before gating on it; do not add failing floors in the same change.
- Replace at least the source-text assertion at `tests/test_full_check.py:1576` with a behavioral test once the shell lane is measured.

## Acceptance Criteria

- [x] `.github/scripts/bookkeeping_ci_scope.py` (477 lines) reports a coverage number.
- [ ] review-preflight.mjs reports a coverage number in CI.
- [ ] The shell lane reports a coverage number in CI.
- [ ] Floors are added only in a follow-up change, at or below measured values.
- [ ] `make check` passes.

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
