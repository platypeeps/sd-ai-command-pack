# Use cd -- in the repo-root guards

## Goal

Close the loadsmith #48 Copilot comments (3522664869/79/81): the 0.5.14
root guards call `cd "$REPO_ROOT"` without the `--` option terminator the
same scripts already use when resolving `SCRIPT_DIR`/`REPO_ROOT`, so a
dash-prefixed root would parse as a `cd` option.

## Requirements

- R1: All three guard sites use `cd -- "$REPO_ROOT"`, matching the
  scripts' own resolution convention.
- R2: Twins in sync; shellcheck warning gate clean; ship as 0.5.15 and
  fold into the open fleet refresh PRs, resolving the three threads.

## Acceptance Criteria

- [x] Three guard sites carry the terminator; shellcheck clean; twins
      identical.
- [x] Fleet PRs updated to 0.5.15 with loadsmith's threads resolved
      (post-merge step).

## Reconciliation Note - 2026-07-09

Reconciled by `07-06-close-fleet-refresh-loop`: loadsmith PR #48 comments
3522664869, 3522664879, and 3522664881 are resolved or obsolete on the merged
PR, and the current loadsmith install audits clean at pack `0.7.0`.
