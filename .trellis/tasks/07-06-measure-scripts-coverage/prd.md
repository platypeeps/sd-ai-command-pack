# Measure coverage for shipped scripts Python helpers

## Goal

Coverage is measured for `install.py` only (`.coveragerc:6`
`include = install.py`), while the pack ships ~3,770 lines of Python
helpers: `sd-ai-command-pack-install-audit.py` (497),
`-pr-body-scope.py` (586), `-record-session.py` (367),
`-review-learnings.py` (890), `-update-spec-kb.py` (1,430). All have
behavioral subprocess tests (every script name appears 18-88 times in
test_install.py), but nothing quantifies which branches are exercised
— a regression in an unexercised error path would ship silently.
Notably, the verified wildcard-glob bug in pr-body-scope
(07-06-fix-pr-body-scope-wildcard-globs) lived exactly in such an
unmeasured path. The `.coveragerc` comment acknowledges the trade-off,
but "focused tests exist" is not "coverage is known".

## Requirements

- R1: Add a second coverage report scoped to `scripts/*.py`.
  Subprocess coverage is already wired via
  `tests/coverage_sitecustomize/sitecustomize.py`; tests run the
  template copies from temp dirs, so add `[paths]` aliasing to
  attribute temp-dir copies back to `scripts/` sources.
- R2: Start non-gating: publish the per-file numbers in CI output,
  then set a realistic `fail_under` (suggested initial: 85) as a
  separate ratchet once the baseline is known.
- R3: Keep the install.py 100% gate unchanged and independent.
- R4: Document the two-report layout in README's Verify section.

## Acceptance Criteria

- [ ] CI prints per-file coverage for all five shipped Python helpers.
- [ ] A threshold (even provisional) is enforced for scripts coverage,
  or an explicit follow-up ratchet plan is recorded in the PRD.
- [ ] Full battery green on both matrix legs.

## Notes

- Origin: 2026-07-06 deep review (Testing finding 2 MEDIUM).
