---
title: Cut the pack lane wait by letting the lane claim under load
created: 2026-11-03
item: sd:7412
branch: feat/sd-7412-lane-waits
---

# Design — parallel-lanes

Ruling: note #42396 (plan parallel lanes; this design first, reviewed before any build).

## Problem

The pack lane's median wait, enqueue to claim, was 60 min over 7 days (178 entries, 116 items).
The question (note #42310) asks whether to run more than one entry at a time.
The numbers say the lane is not short of runners: it sits idle while work waits.

Measured 2026-11-03 from the hub's lane history rows (`entry_times`), gate receipts and
the `lane-run` job log:

- Wait: median 60 min, p75 137, p90 178.
- Mean wait per entry: 52 min behind a running entry, 23 min with the lane idle and a
  runnable entry pending. Wall clock: the lane ran 65.5 h; it was idle with work pending 25.6 h.
- The idle has one main cause. In the job log (1516 runs, about 5.3 days) the pack lane
  stopped on `load_stop` 219 times (load5 at or above 24), ran 176 times, found its runner
  busy 30 times and spent its budget once.
- Service, claim to end: median 22 min. Prepare after a speculative gate that passed:
  2.4 min (41 merged entries). Prepare with no speculation: 26.5 min (50). Speculation
  skipped or failed: 38 to 45 min (19).
- Pack gate (`make check` in receipts): median 27 min, p90 43 (142 passes). Slot wait: mean 3 min.
- Failures: 63 of 178 entries (35%): gate 27, merge conflict 14, review blocking 13,
  other 9. They held the lane 17.8 of its 65.5 h; 1.53 entries per item.
- Review: not timed on its own. A prepare that reuses its gate takes 2.4 min, so review is
  seldom the long step.

A replay of the week's arrivals and service times through the queue gives these waits
(median / mean / p90, min). Each is a bound, not a forecast; see Risks.

- One lane, no idle: 9 / 27 / 75.
- Two lanes, no idle: 0 / 2 / 2.
- One lane, no idle, a 30% faster gate: 0 / 10 / 30.
- One lane, no idle, no failed entries: 0 / 12 / 43.

## Why the lane idles

`next_claim` calls `load_stop` (sd:3479) before each claim. It reads load5 and claims
nothing at or above `sd.gate_load_max` (24 here); the next cron slot, 5 min later, tries again.
The gate queue already applies the same limit, on load1, at admission (`sd_gate_slots`,
sd:2262), and admits in ticket order (sd:5409). Builders' `sd gate run` calls hold tickets
through a load spell; the lane holds none. When load falls, the builders start first,
load rises again, and the lane's next read finds it high. The lane loses its place every spell.

## Options, smallest first

A. Delete the claim-time load stop (recommended). The lane claims when free, runs the
review, and its gate takes a ticket in the one FIFO queue like any other gate. The gate
queue stays the one load bound. Replaces: the `load_stop` call in `next_claim`. `lane_room`
keeps its own load read for starting a second repository's lane. Adds one bound: the lane's
slot wait ends at the run's budget and puts the entry back (failure table, row 2).
Expected: most of the 23 min idle mean, plus the queue behind it; at best the 9 min replay median.

B. Speculation depth 2. Gate entry N+2 on the predicted landing of N and N+1, beside
today's depth 1 (sd:2586). Replaces nothing. Costs one more 27 min pack gate in flight,
wasted when either entry ahead fails: today's speculation hit rate is 53 of 101 (52%),
so depth 2 hits about 27%.

C. Two concurrent prepares, serial merge, recheck after the first lands. The second's
catch-up changes its tree, so it gates again unless it gated on the predicted landing, which
is B. It also breaks the one-runner-per-repository lock the lane relies on. Rejected.

D. Batching: gate two entries' merged tree once; bisect on a failure. Gate failures are 15%
of entries, so a pair fails about 28% of the time and then costs three gates. It needs a
new batch state. Rejected for now.

E. Faster gate: reuse passed shards by tree. The replay gives a mean of 10 min at 30% faster.
It changes what the one full gate proves (sd:5800) and is far larger than A. A later item if A falls short.

Recommendation: build A in one PR, then read `lane_times` for 7 days. Open B only if
the median wait stays above 30 min. Do not run parallel prepares.

## Approach (option A)

- `next_claim` no longer calls `load_stop`; the freeze window and run budget checks stay.
- The runner passes prepare a slot wait bound: the run's remaining budget less
  `ENTRY_SECONDS`, never above `GATE_SLOT_SECONDS`. `sd-check` takes it as its slot timeout.
- A slot wait that hits that bound is a retryable refusal that spent no gate. The runner
  puts the entry back as pending, without spending a reclaim. It counts `slot_waits` on the
  entry for the Queue page. The kept review pass (sd:3478) serves the next prepare.
- The speculative gate's wait ends at the run's deadline: the runner waits for it only until
  then, and cancels it through the existing `CANCEL_SECONDS` path.
- The module docstring loses the `load_stop` clause in `run`; sd:3479's reason moves to
  the gate queue's admission, which now covers it alone.

## Non-goals

- No second runner, no second lane per repository, no merge train.
- No change to slot count, `sd.gate_load_max`, or builder admission order.
- No change to other repositories' lanes beyond the same claim rule; they share the code.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| 1 Claim under load | entry `running`, step `prepare` | runner dies before review | existing reclaim puts it back pending (`RECLAIMS`) | existing reclaim test, run with load above the limit |
| 2 Gate waits for a slot | ticket in the gate queue; review pass kept | run budget ends first; cron TERM would count a reclaim | bounded wait ends; entry pending, `slot_waits` + 1, reclaims unchanged | fake slot that never frees: entry pending, review kept |
| 3 Gate admitted, load rises | gate running | gate times out (sd:3479 class) | `gate_failed`, not put back, as today; `flake_items` files a same-head pass | existing gate-timeout test |
| 4 Speculative gate queued | scratch worktree, ticket | still waiting at the run's deadline | cancel through `CANCEL_SECONDS`; next prepare gates itself | stop the run while the speculative ticket waits |
| 5 Older state | pending rows; older runner build | older runner meets `slot_waits`, or rollback | older code ignores the field; rollback only restores claim refusals | older-shape row with `slot_waits` claims and merges |

Evidence binding is unchanged: a gate receipt still names the head and tree it gated.

## Slices

Slice 1: option A with the table's tests, and the 30 min weekly check. It leaves every
machine's lanes claiming under load and waiting in the gate queue in order.

Slice 2: option B, speculation depth 2, in its own PR (ruling 1).

## Acceptance criteria

- [ ] `test_sd_lane` has a test that fails on `origin/main`: a claim at load5 above the limit runs the entry.
- [ ] Rows 2, 4 and 5 each have a test that stops the run there and passes.
- [ ] Seven days after the merge, `lane_times` for the pack shows a median wait under 30 min.
- [ ] The same week's lane history shows under 5 h idle with a runnable entry pending (25.6 h now).

## Risks

- The replay holds service times fixed. Load spells now wait in the gate queue, not before
  the claim, so part of the 23 min moves into service time. The real gain lies between
  today's 60 min median and the 9 min bound.
- The idle cause rests on the job log's counts, which carry no timestamps. Some idle may
  be the runner waiting for a speculative gate after a merge; that remains.
- A builder's gate may now wait behind a lane gate it would have beaten. FIFO order is the
  standing rule (sd:5409); we accept it.
- Failures (35%) are the second lever. This design does not cut them; review-blocking and
  conflict entries fail fast, gate failures cost a full gate each.

## Open questions

Answered by the operator on 2026-11-03 (notes #42427 to #42429):

1. Build A alone, then measure a week before B? Ruling: build A and B together.
   B is about 400 lines with its tests, so it lands as the second slice of this item;
   the first slice is A and the weekly check.
2. Lane gates in plain FIFO with builders? Ruling: FIFO, no priority (sd:5078 starved builders).
3. Target median wait? Ruling: 30 min, measured weekly; a miss files an item.
   `wait_question` already reads the week after each hosted run; its threshold drops to 30 min,
   and a done `lane-wait:` item a week past its close reopens with the question.
