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

## Verdict

**The caller is the defect. The recorder's completion gate is correct and was
refusing exactly what it should have refused.** Evidence, from the 25 run files
now on disk under `~/.local/state/sd-ai-command-pack/fleet-timing/`:

- 18 are `active`, 7 `completed`.
- Every one of the 18 has at least one consumer with `outcome: null`. Only 5
  have any open stage attempt. The dominant cause of stranding is therefore the
  missing `consumer-end`, not the missing `stage-end` the error text named.
- `consumer-end` appears nowhere in `.agents/skills/sd-fleet-refresh/SKILL.md`
  (zero matches). The skill's Timing evidence section told the operator to
  "bracket the corresponding delivery work" and named no command for closing
  either a stage or a lane.

So the primary fix is the skill: `stage-run` is now mandated as the bracket, and
`consumer-end` is mandated in the same step that records a terminal controller
result. Three recorder defects were found alongside it and fixed, none of them
the cause of the stranding:

1. The completion error named neither consumer, stage, nor attempt, and reported
   only the first of the two gates, so an operator who cleared the open attempts
   hit the missing-outcome gate as a fresh surprise. It now collects both and
   names each blocker with the exact remedial command.
2. `report` could not distinguish a measured run from an uninstrumented one. Six
   of the seven `completed` runs are hollow — outcomes recorded, no stages — and
   said nothing about it. `build_summary` now carries a derived `instrumentation`
   block naming every unmeasured lane.
3. An attempt that outlived its monotonic epoch could be neither ended nor
   reported: `build_summary` raised "monotonic clock moved backwards during
   active stage". This is not a clock fault — `time.monotonic_ns()` has no
   cross-process epoch, and every stage of a campaign is a separate process.
   `measure_elapsed` now falls back to the wall clock and records
   `elapsedSource: "wall"`, refusing only when both clocks moved backwards.
   Before: 20 of 25 files loaded and reported. After: 25 of 25.

**Never-instrumented lane, decided:** such a run may complete. Its consumer
outcomes are real evidence from the controller, and withholding completion would
strand the run permanently for a gap that has already happened. What it may not
do is read as measured data, so the report names every lane without stages and
`render_human` prints `instrumented: N/M consumers`.

**Disposition of the stranded historical runs:** left as they are. They are
private observability records, no timestamp is fabricated for them, and they now
all load and report — a reader can see both what was measured and what was not.

## Acceptance criteria

- [x] A written verdict, backed by executed evidence, on whether the recorder or
      the caller is the defect. Recorded either way.
- [x] A test drives a full simulated campaign and asserts the run reaches
      `completed` with every consumer carrying an `outcome`.
- [x] A test asserts that a run with an open attempt cannot be completed, and
      that the error names the consumer, stage, and attempt.
- [x] A test covers the never-instrumented lane and asserts the documented
      decision, whichever way it goes.
- [x] A test covers an early return in the caller between `stage-start` and
      `stage-end` and asserts the stage is not left open.
- [x] The 21 existing run files still load without error after the change.
- [x] `make check` passes.

## Out of scope

- Backfilling durations for the 15 stranded historical runs. Their disposition
  is a decision this task should state, but fabricating timestamps for them is
  never in scope.
