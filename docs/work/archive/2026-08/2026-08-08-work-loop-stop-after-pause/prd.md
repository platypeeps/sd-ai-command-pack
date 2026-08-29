---
title: work-loop stop and reconcile fail on a run whose lock was already released
status: done
created: 2026-08-08
branch: fix/work-loop-stop-after-pause
---
# work-loop `stop` and `reconcile` fail on a run whose lock was already released

## Goal

Let the work-loop commands that act on an already-unlocked run actually act on
it. `pause` releases the ownership lock by design, and both `stop` and
`reconcile` then demanded one back, so a paused run could not be stopped and a
stopped run could not be reconciled.

## Problem

`stop` and `reconcile` reach `require_lock` through `mutate_state`, which took
the lock as unconditional. Against a paused run both failed with:

```text
work-loop state does not exist: .../lock.json
```

That message is the generic state-read error naming the lock file, so the
report does not say what is actually wrong.

The only way out was a `start --run-id` resume performed purely to re-take a
lock the very next command would drop again. That resume is not free: it flips
the run back to `active` and rewrites the checkpoint on the way through, so the
workaround corrupts the very state the operator was trying to retire.

Observed retiring run `d23a9c7f5f7447fd8ec5059776ed27f7` in a consumer
repository.

The `reconcile` half is the worse one. `references/run-recovery.md` routes a
stopped or red run *to* `reconcile`, so the documented recovery path could not
be walked at all: reconciling a real retired run failed with the same error.

## Requirements

### Functional

1. `mutate_state` accepts the set of persisted statuses whose lock the run is
   expected to have already handed back, and treats an absent lock as the
   documented outcome for exactly those statuses.
2. `stop` passes that allowance, so a paused run can be retired directly.
3. `reconcile` passes it too, so the documented recovery route is walkable.
4. The set names every status `stop` can persist. `stop` runs `release_lock`
   unconditionally after its mutation, so `paused`, `stopped`, and `completed`
   all end lockless — not just `paused`.
5. `active` is excluded. A live run still owns its lock, so an active run whose
   lock vanished still fails exactly as before.

### Non-functional

6. The narrowing is opt-in per call site. Omitting the parameter keeps the
   strict default for every other `mutate_state` caller, so this does not make
   the lock optional anywhere it was previously required.
7. Source and `templates/` twins change together.

## Acceptance Criteria

- [x] `stop` succeeds against a run persisted as `paused`, with no lock file
      present, and does not require a prior `start --run-id`
- [x] `reconcile` succeeds against a run persisted as `stopped` with no lock
      file present
- [x] A run persisted as `active` whose lock file is missing still fails, with
      the ownership error unchanged
- [x] A `mutate_state` caller that passes no allowance still requires the lock
- [x] `LOCK_RELEASING_STATUSES` contains exactly `paused`, `stopped`, and
      `completed`
- [x] `scripts/sd-ai-command-pack-work-loop.py` and its `templates/` twin are
      byte-identical after the change

## Notes

Filed retroactively on 2026-08-08. The fix was implemented and reviewed on
`fix/work-loop-stop-after-pause` (PR #349) before a Trellis task existed for
it; this PRD records the requirements the shipped change actually satisfies so
the work is archived rather than merged untracked. The gap itself — a code
branch reaching review with no backing task — is a process observation, not a
requirement of this task.
