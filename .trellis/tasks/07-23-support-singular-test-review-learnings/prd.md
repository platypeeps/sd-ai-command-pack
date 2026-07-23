# Support singular test directories in review learnings

## Goal

Preserve review-learning classification for repositories that use either test/ or tests/, with source-template and regression-test coverage.

## Requirements

- Classify paths below either top-level `test/` or `tests/` as the same test
  path family.
- Use the same dual-directory rule for the review-learning signal fallback.
- Keep the canonical template and generated root script synchronized.
- Ship the correction as a patch release so consumers can refresh without
  provenance drift.

## Acceptance Criteria

- [x] Both directory conventions map to the `tests` path family.
- [x] Both directory conventions map otherwise-unclassified comments to the
  reviewer/test-harness signal.
- [x] A focused regression test covers the singular and plural paths.
- [x] Generated parity, candidate fleet validation, and the full pack gate pass.

## Notes

- Triggered by consumer PR #8 after the 0.32.0 refresh overwrote an earlier
  consumer-only correction.
- Validation: 34 focused tests passed; all eight fleet candidates passed;
  `make check` passed with installer coverage at 100% and shipped-helper
  coverage above every configured floor.
