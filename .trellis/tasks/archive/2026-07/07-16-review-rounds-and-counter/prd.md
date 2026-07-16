# Restore 5 review rounds + report cycle counter

## Problem

0.9.0 cut the default remote review round limit from five to two; the
maintainer wants five back. Separately, neither the sd-review-pr final
report nor the housekeeping merge report states how many review cycles a
PR actually consumed, so cycle cost is invisible in the reports.

## Requirements

- R1. SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT default: 2 -> 5
  everywhere it is stated (skill binding, neutral command + generated
  adapters, guide prose + config row, README row, test pins).
- R2. sd-review-pr final report gains a mandatory row: remote review
  rounds used of the configured limit (0 of N when no remote review ran).
- R3. sd-housekeeping report gains a mandatory final-state row
  `PR review rounds:` — the merged PR's submitted reviewer review count
  via gh, or `n/a` on verification-only runs; skill template, guidance,
  Final Report list, installed-guide block, and format-test pins updated.
- R4. Shipped payload: bump 0.14.0 (behavior default change) + CHANGELOG.

## Acceptance Criteria

- [ ] Grep shows no remaining "default two"/`:-2}`/`2` round-limit sites.
- [ ] Format tests pin the two new report rows; make test + full-check
  green; adapters regenerated via make generate (no hand edits).
