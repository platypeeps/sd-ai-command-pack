---
title: Routed review dispatch omits localReview block for fully-rebutted findings receipts
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-09
---
# Routed review dispatch omits localReview block for fully-rebutted findings receipts

## Goal

When the review coordinator routes a remote request for a PR whose local
stage ended `findings` with every finding rebutted (outstanding == 0),
the routed request should carry a `localReview` summary with
`dispositionCounts` (`unresolved: 0`, `rebutted: N`) instead of omitting
the block entirely.

## Context

`_router_local_summary` (`templates/scripts/sd-ai-command-pack-review.py`,
~line 860) returns `None` for any receipt whose outcome is not in
`{clean, unavailable, failed, cancelled, skipped}`. Before the rebuttal
gate fix (PR #402, `_local_outstanding`), a `findings` receipt never
reached routing, so the gap was unreachable. Now a fully-rebutted
`findings` receipt routes like a clean one but the remote router gets no
local-review evidence. The `localReview` field is a documented remote
router protocol contract, so mapping a rebutted `findings` receipt to a
router outcome is a protocol decision, not just a coordinator change.

## Requirements

- Gate the new mapping on the same `_local_outstanding` helper
  (fail-closed on malformed disposition state, non-empty findings list
  required).
- Receipt bytes stay immutable; only the routed request payload changes.
- Router protocol docs updated for the new outcome/dispositionCounts
  shape; consumers of the descriptor validated against it.

## Acceptance Criteria

- [ ] Routed dispatch for a fully-rebutted receipt includes
      `localReview` with `dispositionCounts {unresolved: 0, rebutted: N}`.
- [ ] Outstanding > 0 still never dispatches.
- [ ] Malformed disposition state omits the block (or blocks dispatch)
      fail-closed, with a test per shape.
