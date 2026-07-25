# Batch review-learnings GitHub fetches (tactical)

## Goal

`sd-review-learnings` stops making one gh GraphQL subprocess per PR (~30-45 serial spawns
per documented `--github-days 2 --update` run at current merge cadence) by batching PR
numbers into aliased GraphQL queries (15-25 per request).

## Origin

SE-pack repo audit 2026-07-25 (se-ai-command-pack ledger A-028, P2/M). Defect lives in
this repo's source; the SE-side task was retired in favor of this one.

## IMPORTANT — check before starting

`07-25-generalize-review-learnings-across-reviewers` replaces the Copilot-specific
collection path with normalized receipts/projections and will likely DELETE the code this
task optimizes. This task is the tactical fix for current pain only:

- If the generalization is expected to land soon, SKIP this task (mark superseded).
- If it stays blocked on sd-github-review contracts and learnings runs hurt now, do this
  minimal batching without restructuring types (keep the diff small to discard later).

## Requirements

- `scripts/sd-ai-command-pack-review-learnings.py` (~:1174-1193): batch via GraphQL field
  aliases or a single search query; preserve parsed output, timeouts, per-batch errors.

## Acceptance Criteria

- [ ] A run over N PRs makes at most ceil(N/batch) gh calls; identical learnings output on
      a fixture window.
- [ ] Changelog + version; note in the generalization task that the collection code moved.
