# sd-ship: composite publish-to-merge orchestrator

## Problem
The publish→merge endgame spans four commands (create-pr, review-pr,
watch-pr, housekeeping) with no one-command happy path.

## Goal
sd-ship sequences the four stages with `until=pr|review|merge` stop-points,
adding no gate logic of its own.

## Requirements
Parent design § 3 is binding: stage chain with authoritative per-stage
gates, pass-through arguments, failed-stage stop with that stage's report,
mandatory stage-table final report, zero env vars. Ships via the Phase A
generator (skill + neutral + list entry only).

## Acceptance Criteria
- [ ] Format-drift pins: `until=pr|review|merge`, "adds no new gate logic",
      stage table items.
- [ ] Adapters + manifest entries appear via `make generate` with no hand
      edits.
- [ ] Guide/README document it; command lists updated.
