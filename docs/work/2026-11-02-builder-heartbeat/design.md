---
title: Today lists in-session builders beside the headless build runs
created: 2026-11-02
item: sd:7221
branch: feat/sd-7221-builder-heartbeat
---

# Design — builder-heartbeat

The item's row holds status, progress and decisions; this page holds the shape.

## Problem

A lead's Claude Code teammates build in their own worktrees and write no
row. Today's Queue view (In motion, folded in by pack sd:7234) lists the
headless build runs of `sd_db.build`, so an in-session builder shows only
in the lead's `ListAgents`, and its budget's end lives only in a note.

## Approach

One verb, `sd assignments beat` (ruling note #41072), on the rows a build
claim already writes (note #40716): `assignment` and `runner_run`.

- `--start`: the lead registers a run for the items, the first its lead.
  One `assignment` per item (scope `teammate`, `budget_minutes`, members'
  `parent` the lead) and one `runner_run` on the lead with the worktree and
  branch. No lease and no process.
- `beat ITEM`: the builder refreshes `heartbeat_at` after each commit and
  before its report (`agents/sd-slice-builder.md`, step 4).
- `--end`: the lead ends the run on the builder's final report.
- `teammate.reap`, in the build-dispatch tick, ends a run whose items are
  all done, and one with no beat for its budget plus 30 minutes.
- `now_screen.builders` and `builds.panel` read the open runs; the Queue
  view draws each as a working row with its worktree, branch, due time and
  last beat.

The assignments hold status `in_session`, not `running`. A running
assignment means the runner owns the item: `workflow.change_status`
refuses every status write, and the cancel and work guards refuse too, so
the builder's own `sd task status` would fail. No new table or column.

Rejected: scope `build` on the same rows. `build.reap` would end a quiet
teammate after `STALE_SECONDS` (600 s), `_settle` would retry it as a
headless run, and `claim` and `room` would count it.

Two guards read every unreleased run whatever its scope, and both get the
build run's exemption:

- `ship.manual_merge_guard`: an open teammate run would refuse every lane
  merge in its repository. Test: `test_ship` `test_an_open_teammate_run_does_not_refuse_a_lane_merge`.
- `backup.JOURNALED_RUNS`: a teammate run has no runner journal, so every
  backup would fail. Test: `test_build` `Backup.test_a_teammate_run_needs_no_journal`.

## Non-goals

- Counting teammate runs in `build.room`'s machine and repository caps.
- A dashboard control to end a run: the lead ends it, and the reap backs it up.
- Cleaning a teammate's worktree: `build_run.sweep` reads scope `build` only.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| start | assignments and run, one transaction | stop or refusal | nothing written; the lead runs it again | `Start.test_a_start_refuses_and_writes_nothing` |
| start twice | none | a second start on a held item | refused, names the run | same test, case `held` |
| beat | `heartbeat_at` | no run registered | exit 1, nothing written; the builder goes on | `Beat.test_a_beat_with_no_open_run_refuses` |
| reap | outcome, release, assignments, notes, one transaction | a beat between the read and the end | compare-and-set on the beat read; the run stays | `Reap.test_a_beat_between_the_read_and_the_end_keeps_the_run` |
| reap | as above | a quiet builder inside its budget | the run lives past `STALE_SECONDS` | `Reap.test_a_quiet_run_inside_its_budget_lives_past_the_build_stale_limit` |
| reap | as above | the lead never ends it | ended past budget plus grace, or once every item is done | `Reap.test_a_run_silent_past_its_budget_and_grace_ends_interrupted`, `test_a_run_whose_items_all_landed_ends_done` |
| end | outcome, release, assignments, one transaction | the run already ended | refused, nothing written | `Beat.test_a_beat_with_no_open_run_refuses` |
| restore | none | a reimport is pending | start refused, reap skips | `Start.test_a_restore_reimport_holds_a_start_and_the_reap` |

## Acceptance criteria

- [x] `python3 -m unittest tests.sd_db.test_teammate` passes.
- [x] The two guard tests fail on origin/main and pass here.
- [x] The Queue view draws a teammate row with its worktree, branch, due time and beat.

## Risks

A rollback to the previous commit with teammate rows in the store reads
them through the old guards: an open run refuses lane merges in its
repository, and any teammate row fails the backup's journal check. Before
a rollback, end every open run with `sd assignments beat N --end`, then
delete the rows in one transaction:
`DELETE FROM runner_run WHERE assignment IN (SELECT id FROM assignment WHERE scope = 'teammate'); DELETE FROM assignment WHERE scope = 'teammate';`.

A builder that never beats is reaped only past its budget plus grace, so
a lost teammate shows for up to that long. Past its due time the row reads
`stalled`, so the operator sees it first.
