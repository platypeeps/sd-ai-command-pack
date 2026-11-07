---
title: Build dispatch per lane host
created: 2026-11-06
item: sd:7933
branch: feat/sd-7933-build-per-host
---

# Design — build-per-host

The item's row holds status, progress and decisions; this page holds the shape.
The rulings are note #46608 on system sd:7932.

## Problem

The dashboard's Build refuses an item whose lane runs on a satellite:
"item N's lane runs on <host>; builds run on the hub only" (`build._repo_refusal`).
The operator wants to start those builds from the hub dashboard.
The satellite must build them itself, as only it runs that lane.
The database is the one channel: no SSH and no remote session.

Today one dispatcher, the hub's `build-dispatch` job, acts on every build run.
A second dispatcher on a satellite would reap, kill, watch and sweep the hub's runs,
and the hub's would probe a satellite pid on the hub and `kill_group` a hub pgid.

## Approach

A build run belongs to one host, read from `runner_run.owner` (ruling Q1).
A hub-lane run keeps `owner = "build-dispatch"`, the role, so a failover keeps it.
A satellite-lane run gets `owner = "build-dispatch@<lane_host>"`.
`build.run_host(owner)` is the part after `@`, or None for the hub.

`build.lane_hosts(connection)` is the set of lane hosts this machine builds for:
`{this_host()}` on a satellite (`served_by(connection)` names a hub),
and `{None, this_host()}` on the hub. A run is mine when its host is in that set.
That mirrors `ship._lane`: NULL is the hub's lane, a name is that machine's.

1. Press: `_repo_refusal` no longer refuses a lane host. A press queues for any lane.
2. Claim: takes only queued rows whose repository's `lane_host` is in `lane_hosts`.
   It skips the others and blocks none; the claim writes the owner from the lane host.
3. Room: counts only this host's build and draft runs against `MACHINE_CAP`
   and `REPO_CAP` (ruling Q3). The interactive builders are this machine's already.
4. Dispatch, reap, held release, watch, sweep and the spawn loop act only on mine.
5. Drafts and auto-pickup stay on the hub (ruling Q2): `eligible` and `draft`
   refuse a satellite lane; a satellite tick runs no pickup, no draft claim or reap,
   and no stop-on-blocks.
6. The failure push runs on the hub only, over every host's runs:
   one pusher sends each failure once, and the hub holds the notifier.
7. The tick's heartbeat key is `build-dispatch` on the hub and
   `build-dispatch@<host>` on a satellite, so one does not hide the other.
8. The Build dialog names "runs on <host>" for a satellite bundle, not the hub's room.
   The Builds panel row names the host and the log path, and reads no log
   on the hub's disk for it (ruling Q5).

Rejected: a `runner_run.host` column. It needs a migration, and the owner already
travels with every retry (`_settle`, `_health_unknown` copy it).

## Non-goals

- Auto-pickup and drafts for satellite lanes (ruling Q2).
- The system half: the job on the work satellite, its `SD_HUB_ONLY_AGENTS` entry,
  its log root (ruling Q4). That lands in the system repository after this.
- Live log reads of a satellite run from the hub.

## Failure table

```text
Step | State moved | Failure | Recovery | Test
Press | build assignment queued for a satellite-lane item | the old refusal | none needed: the press queues for any lane; other refusals still refuse the whole selection | test_build.Queue.test_press_queues_a_satellite_lane_item
Claim on the hub | hub-lane rows claimed, owner build-dispatch | the hub claims or blocks a satellite row | the claim skips a row whose lane host is not its own; the row stays queued | test_build.Hosts.test_the_hub_claim_skips_a_satellite_row
Claim on a satellite | its rows claimed, owner build-dispatch@<host> | it claims a hub row or another satellite's | the same filter; the hub's rows stay queued | test_build.Hosts.test_a_satellite_claims_only_its_lane
Claim, lane moved before it | the row goes to the host that holds the lane at claim time | a stale host from the press | the claim reads lane_host in its own transaction | test_build.Hosts.test_a_lane_move_before_the_claim_moves_the_claim
Claim, load unread | nothing | gate_load() is None on a host | no claim; the tick's why names the unread load; the next tick reads again | test_build_run.Tick.test_an_unread_load_says_why
Room | builders counted per host | the hub's runs fill the satellite's cap, or the reverse | room counts only runs whose host is in lane_hosts | test_build.Hosts.test_room_counts_only_this_hosts_runs
Spawn | a supervisor started for an open run with none | the hub spawns a satellite run's supervisor on the hub | the spawn loop takes mine only | test_build_run.Hosts.test_each_tick_spawns_only_its_own_runs
Worktree, build, review, fix | the satellite's supervisor walks its steps on its disk | supervisor lost | the satellite's reap retries once; the retry keeps the owner | test_build.Hosts.test_a_retry_keeps_the_satellite_owner
Reap and kill | outcome, kill, settle | the hub probes a satellite pid or kills a hub pgid by its number | reap and held release take mine only; the satellite reaps its own | test_build.Hosts.test_the_hub_never_signals_or_reaps_a_satellite_run
Cancel from the hub | cancel_requested on the run | no satellite tick runs | the run stays open with the request; the satellite supervisor's beat or its reap ends it cancelled | test_build.Hosts.test_a_hub_cancel_lands_on_the_satellite_reap
Enqueue | lane entry on the satellite | the lane moved after the claim: sd-ship refuses (LaneElsewhere) | the run ends blocked with the refusal; Retry queues it, and the next claim goes to the new lane host | test_build_run.Supervise.test_a_body_the_lane_refuses_blocks_with_its_reason (the same refusal path)
Lane watch | enqueued to cleaning or lane_failed | the hub runs lane list for a satellite repo and probes its pids | watch takes mine only | test_build_run.Hosts.test_each_tick_watches_only_its_own_runs
Sweep | a done bundle's worktree removed | the hub removes a path that names a satellite worktree | sweep takes mine only | test_build_run.Hosts.test_sweep_leaves_another_hosts_worktree
Report back | notes, run row, cost rows in the one database | the hub stats a satellite log path | the panel row names host and log path and reads no log for it | test_build_panel.Panel.test_a_satellite_run_names_its_host
Push failure | one ntfy push per failed run or entry | hub and satellite both push one failure | push_failures returns nothing on a satellite; the hub pushes every host's | test_build_run.Hosts.test_a_satellite_pushes_nothing
Drafts and pickup | draft runs, auto-pickup queue | a satellite tick claims a draft or picks hub items | the satellite tick skips pickup, stop-on-blocks, draft claim and draft reap; eligible skips a satellite lane | test_build.Hosts.test_auto_pickup_skips_a_satellite_lane, test_build_run.Hosts.test_a_satellite_tick_runs_no_draft_or_pickup
Heartbeat | state heartbeat row | the satellite's beat hides a dead hub job | the satellite beats build-dispatch@<host> | test_build_run.Hosts.test_a_satellite_tick_beats_its_own_key
Older state | runs from before this change | an owner with no @ | reads as the hub's, as before | the existing test_build and test_build_run suites
Rollback | the previous pack on the hub | its reap acts on every run and reads a live satellite pid as gone | before a rollback, cancel each open satellite run on the Builds panel and let the satellite end it | none: a procedure
```

## Acceptance criteria

- `python3 -m unittest tests.sd_db.test_build tests.sd_db.test_build_run tests.sd_db.test_draft` passes with 0 failures.
- `python3 -m unittest dashboard.tests.test_build_panel` passes with 0 failures.
- On `origin/main`, each new test above fails.

## Risks

- A satellite with no `build-dispatch` job leaves its rows queued for ever.
  The Build dialog names the host, and the system half installs the job.
- Two machines whose `hostname -s` agree would both claim one lane.
  `ship._lane` has the same rule; the lane host names are unique in the fleet.
- A rollback of the hub's pack while a satellite run is open is unsafe (last table row).
