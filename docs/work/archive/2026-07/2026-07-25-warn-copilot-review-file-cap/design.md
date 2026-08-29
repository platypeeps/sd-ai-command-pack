# Warn on Copilot review file cap Design

## Boundary

`templates/scripts/sd-ai-command-pack-review-preflight.mjs` remains the shipped
source of truth. `checkDiffSize()` already owns the deterministic review-size
advisories and receives the complete file list from `currentReviewDiffStats()`,
so the file-count check belongs there beside the existing changed-line check.

## Contract

- `copilotReviewFileLimit` is a positive integer with default `300`.
- `diff.files.length > limit` emits `WARN`; equality emits `PASS`.
- The output names both values and says that Copilot will not review the diff
  above the limit.
- Configuration validation reports an error for invalid explicit values and
  retains the default only so the rest of the preflight can continue collecting
  deterministic findings before returning failure.

## Data Flow

```text
local git diff -> currentReviewDiffStats -> diff.files.length
  + validated review-preflight config -> PASS or WARN
```

No provider call, PR lookup, or changed-path filtering is introduced. Counting
the already-selected diff keeps working-tree and branch-diff behavior aligned
with every other preflight size advisory.

## Compatibility and Rollback

The change is advisory: it does not block review, alter routing, or mutate the
repository. Rollback consists of removing the config key, output branch, tests,
and documentation while restoring the prior patch version.
