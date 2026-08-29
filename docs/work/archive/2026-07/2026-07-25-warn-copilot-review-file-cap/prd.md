---
title: Warn on Copilot review file cap
status: done
created: 2026-07-25
branch: codex/warn-copilot-review-file-cap
---
# Warn on Copilot review file cap

## Goal

Prevent a locally green review cycle from discovering only after publication
that GitHub Copilot cannot review the pull request because its changed-file
limit has been exceeded.

## Background

GitHub Copilot returned an exact-head review event for
`platypeeps/sd-github-review#22` stating that it could not review 400 changed
files because the maximum is 300. The existing deterministic preflight warns
about changed lines, authored-source lines, and task-directory breadth, but it
does not compare the changed-file count with this hard provider boundary.

## Requirements

- Count every file in the same local diff already selected by the preflight's
  `currentReviewDiffStats()` boundary; do not call GitHub or require a PR.
- Add `copilotReviewFileLimit` to the bounded review-preflight configuration,
  defaulting to `300` and accepting only positive integers.
- Emit a warning when the changed-file count is greater than the configured
  limit. The warning must state the count, the limit, the Copilot consequence,
  and the recommended split action.
- Emit a passing result when a non-empty diff is at or below the limit.
- Preserve the existing line-size, authored-source, large-file, and Trellis
  task-directory advisories.
- Update the template source first, synchronize its root mirror, document the
  configuration key, and carry the compatible shipped-payload release ledger.
- Cover the exact 300-file boundary, a 301-file overflow, and a lower configured
  limit with deterministic tests.

## Out of Scope

- Blocking publication or automatically splitting a pull request.
- Requesting or re-requesting a GitHub reviewer.
- Discovering provider limits dynamically from GitHub.
- Changing review routing or the separate GitHub compare-response truncation
  contract.

## Acceptance Criteria

- [ ] A 300-file diff passes the Copilot file-count check at the default limit.
- [ ] A 301-file diff warns before remote review and recommends splitting.
- [ ] A positive integer `copilotReviewFileLimit` override changes the boundary.
- [ ] Invalid non-positive or non-integer overrides fail configuration
  validation rather than silently weakening the advisory.
- [ ] Template/root parity, focused tests, `make check`, release payload gates,
  and candidate validation pass.

## Compatibility

This is an additive advisory and configuration key. Existing configurations
retain their current behavior with the new default applied automatically.
