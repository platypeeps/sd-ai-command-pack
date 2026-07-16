# sd-fleet-refresh: consumer fleet rollout loop

## Problem
Fleet rollout is the pack's most recurring multi-repo chore and is only
half-automated: fleet-preflight exists but the loop (branch, install,
full-check, PR, watch, merge — per consumer) is manual. 0.10.5 + 0.11.0
+ 0.12.0 are pending rollout now.

## Goal
`/sd:fleet-refresh` executes the documented FLEET_ROLLOUT.md procedure
across stale consumers, strictly sequentially, with per-consumer gated
merges and a fleet status report.

## Requirements
Contract per parent design § sd-fleet-refresh: preflight first
(at-target skip), `consumer=` filter, `dry-run`, `no-merge`, dirty-tree
skip + report, consumer full-check before PR, housekeeping-gate merges,
FLEET_ROLLOUT.md as procedure authority, mandatory per-consumer status
table.

## Acceptance Criteria
- [ ] Skill + adapters + manifest wiring installed and tested.
- [ ] Format tests pin preflight-first, dirty-skip, sequential rule, and
      the status-table report shape.
- [ ] Guide + README document it, cross-linking FLEET_ROLLOUT.md.
