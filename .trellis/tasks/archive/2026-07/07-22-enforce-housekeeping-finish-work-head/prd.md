# Enforce finish-work head before housekeeping merge

## Goal

Port the consumer-proven exact-head lifecycle handoff into the sd-ai-command-pack source templates, generated adapters, shipped script, documentation, and regression suite.

## Requirements

- A ready open pull request must not reach the housekeeping merge operation
  unless the caller supplies the exact commit for which `sd-finish-work`
  completed.
- Missing, malformed, or stale finish-work head evidence must fail closed with
  an actionable message and leave the pull request open.
- Already-merged and default-branch cleanup must remain available without the
  finish-work head because no delivery merge remains to protect.
- The shared skill, `sd-ship`, every generated platform adapter, operator
  documentation, and the shipped script must describe one identical handoff.
- Source templates are authoritative; root dogfood copies must be regenerated
  and byte-identical after sync.
- Regression coverage must include missing, stale, malformed, and matching-head
  scenarios without weakening any existing check, review-thread, or head gate.
- The compatible payload fix must receive the required patch release metadata
  and candidate-validation refresh.

## Acceptance Criteria

- [x] `--finish-work-head <oid>` accepts a full commit OID and rejects malformed
  values with usage status `2`.
- [x] A ready PR without the option or with a stale head is not merged.
- [x] A matching head proceeds through all existing merge predicates.
- [x] Cleanup-only behavior remains unchanged.
- [x] Templates, generated adapters, root mirrors, docs, manifest version, and
  changelog are synchronized.
- [x] Focused housekeeping tests and the complete `make check` gate pass.

## Validation

- `python -m unittest tests.test_housekeeping`: 27 tests passed.
- Fleet candidate validation: all eight configured consumers passed; the
  `0.30.1` ledger was refreshed.
- `make check`: tests, coverage, lint, type checking, security audit, install
  audit, KB freshness, source drift, and local full-check all passed.

## Notes

- This ports the behavior proven in `sd-github-review` commit `291a9f2` into
  its durable source owner. Consumer rollout is separate from this PR.
