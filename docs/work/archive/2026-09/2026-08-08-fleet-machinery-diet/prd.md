---
title: Fleet machinery diet
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-08
---
# Fleet machinery diet

## Problem

The 2026-08-08 KISS audit measured ~7,014 lines of fleet orchestration
machinery for an 8-repo fleet. The largest single piece, `fleet-timing.py`
(1,268 lines), estimates rollout schedules — cohorts, waves, timing windows —
for a fleet small enough to enumerate in one list. The machinery costs more
to maintain and review than the scheduling it automates.

## Requirements

1. Retire `fleet-timing.py`; replace cohort/wave planning with a sequential
   consumer list (registry order already exists in consumers.json).
2. Audit remaining fleet machinery for pieces whose complexity exceeds the
   8-repo reality; propose (not execute) further diets.
3. No behavior change to fleet refresh itself — this trims planning
   machinery, not the refresh mechanism.

## Acceptance criteria

- [ ] fleet-timing.py deleted; no references remain (repo-wide grep).
- [ ] Fleet refresh flow unchanged and green on a smoke run.
- [ ] Diet audit note recorded with line counts before/after.

## Evidence

KISS audit line counts, 2026-08-08.
