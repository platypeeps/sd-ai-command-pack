# Reject Placeholder Context in New Planning Tasks Design

## Overview

Make the existing Trellis context-seed preflight depend on the review diff,
not task lifecycle status. Any changed `implement.jsonl` or `check.jsonl` file
is inspected for top-level `_example` scaffold rows, including while its task
is still planning.

## Proposal

- Build the inspection set only from changed context artifact paths returned
  by `currentChangedPaths()`.
- Do not infer additional context files from a changed `task.json`; this keeps
  unchanged historical files outside the failure boundary.
- Reuse `parseTrellisTaskArtifactPath`, `isRegularFile`, and
  `findTrellisTaskContextSeedRows` so archive handling, symlink safety, and
  top-level-row detection retain their current behavior.
- Report every seed row found across every changed context file before the
  preflight exits.
- Use lifecycle-neutral pass and failure text that tells the operator to
  replace the scaffold with grounded context or leave the file empty.

## Boundaries And Non-Goals

- Do not validate arbitrary JSONL schema beyond the existing top-level
  `_example` marker check.
- Do not scan untouched task context or make historical scaffold rows block an
  unrelated review.
- Do not require non-empty context files.
- Do not change Trellis task lifecycle behavior.

## Affected Files

- `templates/scripts/sd-ai-command-pack-review-preflight.mjs` is canonical.
- `scripts/sd-ai-command-pack-review-preflight.mjs` is its byte-identical
  source-checkout mirror.
- `tests/test_review_preflight.py` covers planning, empty, grounded, archived,
  and untouched cases.

## Data And Command Contracts

The accepted context shapes remain an empty file or JSONL rows such as
`{"file":"<path>","reason":"<why>"}`. A changed file containing a
top-level `_example` key fails with its repo-relative path and line number.
Malformed non-seed rows retain the current behavior and are outside this
task's contract.

## Risks And Edge Cases

- A task status-only change must not pull unchanged context files into scope.
- Renamed or newly archived context files remain diff-visible and are checked.
- Symlinked context files remain excluded by `isRegularFile`.
- Multiple affected files must accumulate failures in one preflight run.

## Validation

- Run the focused planning-context regression tests in
  `tests/test_review_preflight.py`.
- Run the complete review-preflight test module.
- Verify canonical and mirror scripts are byte-identical.
- Run `make check` before publication.
