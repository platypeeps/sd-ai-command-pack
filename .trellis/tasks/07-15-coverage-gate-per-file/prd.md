# Per-file coverage floors + fleet-preflight CLI tests

## Problem

Audit findings A-008 and A-015 (both P2, testing), 2026-07-15 @ f6f3932:

- A-008: the 76% scripts coverage floor applies to the pooled TOTAL only
  (`.github/workflows/tests.yml:73`); per-file reality: fleet-preflight.py
  62%, review-learnings.py 69% while TOTAL=79% passes. A single script can
  regress toward 0% with CI green.
- A-015: `scripts/sd-ai-command-pack-fleet-preflight.py:190-282` (the
  entire CLI surface: `main`, arg parsing, JSON/text rendering,
  `--fail-on-refresh-needed` exit codes) has zero coverage; tests call
  helpers only.

## Goal

The coverage floor means what it says per script, and the fleet-preflight
CLI surface that automation keys on is exercised.

## Requirements

- Enforce a per-file floor for each `scripts/sd-ai-command-pack-*.py`
  (loop `coverage report --include=<file> --fail-under=N`); choose N per
  file at-or-below current reality, ratcheting the weakest (62%) upward
  with the new tests rather than lowering the bar.
- Add fleet-preflight `main()`/subprocess tests: temp fleet manifest,
  `--json` and text output, unknown-consumer SystemExit,
  `--fail-on-refresh-needed` exit code.
- Keep total runtime impact small (reuse existing runner sharding).

## Acceptance Criteria

- [ ] CI fails if any single shipped script drops below its floor.
- [ ] fleet-preflight CLI paths covered; its per-file number rises above
      the old 62%.
- [ ] Documented floor policy (aggregate + per-file) in the workflow or
      CONTRIBUTING.
