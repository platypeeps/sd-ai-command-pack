---
title: Typed refinalization exit for the sd-ship planning chain
status: planning
created: 2026-08-14
---
# Typed refinalization exit for the sd-ship planning chain

Upstream record: issue #408. Observed end-to-end on
`platypeeps/se-ai-command-pack` PR #157.

## Goal

Give an `sd-ship until=merge` chain in planning-mode finalization a sanctioned
in-band exit when a remote review fix lands after Stage 2b's journal commit
and touches an authored path. Today Stage 4's moved-head recomputation must
reuse the captured base, the authored fix path makes every permitted receipt
fail `bundle_scope_invalid`, Stage 4 is forbidden from invoking finish-work,
and the chain stops with a validator failure and no named route out. The
working recovery — a fresh out-of-chain `sd-finish-work`, then
`sd-housekeeping --finish-work-receipt` — exists but is written down nowhere
the stopped chain points.

This is systematic, not incidental: any consumer with a platform
auto-reviewer (Copilot) and no configured review router hits it whenever
review timing straddles finalization.

## Requirements

Either shape from the issue is acceptable:

1. **Typed outcome** — Stage 4 recognizes the exact shape (planning-mode
   recomputation, `bundle_scope_invalid`, non-bookkeeping path introduced
   after the finalization commit) and stops with a typed
   `needs-refinalization` outcome naming the recovery sequence.
2. **Base re-derivation** — Stage 4 re-derives the planning base at the last
   non-bookkeeping commit before recomputation.

Invariants that must survive: finish-work runs at most once per chain,
Stage 4 produces zero bookkeeping, the merge gate still requires an
exact-head receipt, the bookkeeping-only fix case keeps its current
single-pass behaviour, and no history rewriting.

## Acceptance Criteria

- [ ] The issue #408 reproduction shape no longer ends in an unnamed
      validator stop: the chain emits the typed outcome (or revalidates via
      the re-derived base) with the recovery route in the report.
- [ ] Completion-mode behaviour is unchanged.
- [ ] The invariants listed above each have a test or an explicit recorded
      rationale for why a test cannot hold them.
### On issue closure

Issue closure is deliberately not an acceptance criterion. #408 was closed as
`not planned` on 2026-08-14, when tracking for this work moved to the Trellis
task tree; the defect is unchanged and this task still owns it. A criterion
promising to close it would already be satisfied and would prove nothing.

The shipping PR should reference it for provenance as a bare `#408`, never
with a closing keyword — see `08-14-pack-paper-cuts` item 4 for why a PR
body's closing keyword reaches the merge commit message.
