# Make fleet timing runs reach completed instead of stranding active

Child of `08-21-fleet-ledger-integrity`. Independently verifiable; no ordering
dependency on the sibling task.

## Context

`fleet-timing report --run-id refresh-0-71-45-20260821T234057Z --complete`
answers:

```json
{"error": "cannot complete timing run with active stages",
 "operation": "report", "schemaVersion": 1, "status": "error"}
```

Read from the run's own state file, the campaign looks like this. `open` counts
attempts with `endedWallNs == null`:

| consumer | outcome | stages | open |
| --- | --- | --- | --- |
| rwbp-coordinator | `refreshed-merged` | 10 | — |
| loadsmith | `refreshed-merged` | 10 | — |
| hoa-manager | `null` | 10 | `local-gate#1` |
| rwbp-website | `null` | 4 | `local-gate#1` |
| mezmo_benchmark | `null` | 4 | `local-gate#1` |
| se-ai-command-pack | `null` | 0 | — |
| sd-github-review | `null` | 0 | — |
| people-profiles | `null` | 0 | — |
| anomaly-metric-creator | `null` | 0 | — |

Three separate failures, not one:

- **`stage-end` is skipped.** Three lanes hold an open `local-gate#1`. That
  alone is what the error names.
- **`consumer-end` is skipped.** Seven of nine lanes have `outcome: null`. Only
  the first two lanes of the campaign ever got one.
- **Instrumentation stops entirely.** The last four lanes recorded zero stages.

The ordering is the tell: the two fully-instrumented lanes are the first two
processed, the next three are partial, the last four are absent. Instrumentation
decays as a campaign proceeds, which points at the caller — the refresh skill —
not at the recorder.

This is systemic, not local to this campaign. Of 21 runs on disk under
`~/.local/state/sd-ai-command-pack/fleet-timing/`, **15 are `active`**, the
oldest (`refresh-v0-55-0-20260727T005724Z`) from 2026-07-27; only 6 reached
`completed`. Every rollout since late July has produced an unusable timing
record.

## Requirements

- Establish first, with evidence, whether the recorder or the caller is at
  fault. The decay pattern points at the caller; confirm or refute it before
  changing either. If the recorder is correct, this task closes by fixing the
  skill and saying so.
- A campaign must be able to reach `completed` by recording the evidence it
  actually produced. Completion must not become reachable by asserting an
  outcome that was never measured.
- The failure message must name what is missing and how to supply it — which
  consumer, which stage, which attempt — rather than the current bare "active
  stages", which does not say which stages or on which lanes.
- Decide explicitly what happens to a lane that was never instrumented. A run
  where four of nine lanes have no stages is not made trustworthy by being
  marked `completed`; if such a run can complete at all, the report must mark
  the gap so a reader cannot mistake it for measured data.
- Whatever the fix, `stage-end` and `consumer-end` must be driven by the same
  control flow that drives `stage-start`, so a future lane cannot be half
  instrumented by a caller that returns early.

## Acceptance criteria

- [ ] A written verdict, backed by executed evidence, on whether the recorder or
      the caller is the defect. Recorded either way.
- [ ] A test drives a full simulated campaign and asserts the run reaches
      `completed` with every consumer carrying an `outcome`.
- [ ] A test asserts that a run with an open attempt cannot be completed, and
      that the error names the consumer, stage, and attempt.
- [ ] A test covers the never-instrumented lane and asserts the documented
      decision, whichever way it goes.
- [ ] A test covers an early return in the caller between `stage-start` and
      `stage-end` and asserts the stage is not left open.
- [ ] The 21 existing run files still load without error after the change.
- [ ] `make check` passes.

## Out of scope

- Backfilling durations for the 15 stranded historical runs. Their disposition
  is a decision this task should state, but fabricating timestamps for them is
  never in scope.
