# Bound review-learnings unsafe-path diagnostics

## Goal

Convert unsafe planning changed-path inputs from an uncaught ValueError into a bounded phase-specific diagnostic with focused regression coverage.

## Background

- In `platypeeps/people-profiles` PR #3, the required command
  `sd-ai-command-pack-review-learnings.py --github-pr 3 --dry-run` terminated
  with `ValueError: planning changed path is unsafe` and a Python traceback.
- `_normalize_planning_changed_paths()` intentionally rejects non-string,
  traversal, control-character, oversized, and over-count inputs, but the
  command's live planning-signal path does not catch that expected validation
  failure.
- `templates/scripts/sd-ai-command-pack-review-learnings.py` is the shipped
  source of truth; the root script is its byte-verified mirror.

## Requirements

- Treat unsafe planning changed-path validation as an expected CLI failure,
  not an unhandled exception.
- Emit a stable, phase-specific diagnostic that explains the invalid planning
  evidence without echoing unsafe raw path text, control characters, secrets,
  or host-specific absolute paths.
- Preserve the existing exit-code contract for invalid command evidence and
  return a schema-valid bounded failure report in `--json` mode.
- Preserve successful planning-signal behavior for valid changed paths and all
  existing GitHub-scan, dry-run, and update modes.
- Update the template first and keep the root script byte-identical.
- Add focused CLI-level regression coverage for unsafe traversal/control input
  and assert the diagnostic, exit code, JSON contract, and absence of a
  traceback.

## Acceptance Criteria

- [x] Human mode reports the unsafe planning evidence with a stable
  `sd-review-learnings` phase tag, exits with the documented failure code, and
  prints no traceback. Guarded the main scan path's `build_review_learning_signal`
  call with `except ValueError -> _print_early_failure(phase="planning")` +
  `return 2`; `test_review_learnings_main_reports_unsafe_planning_path_without_traceback`
  asserts the `[sd-review-learnings:planning]` tag, exit 2, and no traceback.
- [x] JSON mode returns one bounded schema-valid failure document and the same
  failure exit code. `test_review_learnings_main_bounds_unsafe_planning_path_in_json`
  parses stdout as one doc, asserts `schemaVersion == REPORT_SCHEMA_VERSION`,
  `write.reason`, and exit 2.
- [x] Regression tests cover representative unsafe inputs without reproducing
  their raw unsafe values in output. Traversal (`b/../../etc/passwd`, human) and
  control-character (`b/e\x01vil`, JSON) inputs; both assert the raw value is
  absent from output.
- [x] Existing valid planning-signal tests continue to pass. Full module: 61
  tests OK.
- [x] Template/root byte parity and `make check` pass. Template edited first,
  root byte-mirrored (diff -q clean).

## Out of Scope

- Changing the accepted changed-path grammar or safety bounds.
- Changing review-signal clustering, GitHub collection, or managed-document
  write behavior beyond routing this validation failure safely.
- Reworking unrelated review-learnings performance or reviewer-generalization
  tasks.

## Notes

- Source evidence: `platypeeps/people-profiles` PR #3 review-learnings pass,
  observed 2026-07-27 UTC.
- This is a lightweight PRD-only bug-hardening task.
