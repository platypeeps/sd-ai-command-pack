# Reject malformed task context JSONL

## Goal

Fail closed when changed Trellis task context manifests contain malformed non-empty JSONL rows, with deterministic diagnostics and regression coverage.

## Requirements

- Treat every malformed non-empty row in a changed `implement.jsonl` or
  `check.jsonl` as a deterministic validation failure.
- Report the file and one-based line number without echoing malformed content.
- Preserve empty-line handling and existing seed/reference diagnostics.
- Ship the fix from the canonical template as a patch release.

## Acceptance Criteria

- [x] The parser emits a distinct malformed-row issue.
- [x] Review preflight fails closed with a bounded file-and-line diagnostic.
- [x] Unit and repository-level regression tests cover malformed JSONL.
- [x] Generated parity, fleet candidate validation, and full pack checks pass.

## Notes

- Triggered by Copilot review round 2 on consumer PR #8.
- Validation: focused review-preflight tests, template/root parity, the fleet
  candidate ledger across eight consumers, and `make check` all passed on
  2026-07-23.
