# PARKED: Record the task branch in upstream task.py start

## Goal

Capture the conditional task for removing the pack-owned branch preparation in
`sd-finish-work` step 4 once upstream Trellis records a task's branch at
activation time. The pack currently owns that preparation only because
`task.py start` leaves `branch` null, so every task arrives at the completion
boundary unprepared and the wrapper has to repair it before the archive range
opens.

## Trigger

Waiting for an external trigger, either of:

- Upstream Trellis records the active branch in `task.py start`, at which point
  the pack's step 4 preparation becomes dead code for new tasks and should be
  narrowed to a compatibility path for records created by older versions.
- Upstream declines the change, at which point the preparation is permanent and
  its untested write path (see Requirements) needs a first-class test instead of
  a park.

This checkout runs Trellis 0.6.7 (`.trellis/.version`). No upstream issue has
been filed yet; filing one is the first action when this task unparks.

Source: `.trellis/tasks/archive/2026-07/07-30-resolve-branch-field-finalization-deadlock/design.md:177-184`,
which parked this explicitly as out of scope for the deadlock fix.

## Requirements

- Record the root cause. `cmd_start` in `.trellis/scripts/task.py:70-140` writes
  only `status`, in both the normal and the degraded no-session-identity path.
  No code path there writes `branch`. The only writer is `cmd_set_branch` in
  `.trellis/scripts/common/task_store.py:728-748`, invoked by hand. Both files
  are Trellis-vendored, so the fix is upstream, not pack-local.

- Record the second, independent reason this matters. The pack's own
  compensating write path has never run in a live finalization. The task that
  introduced it, `07-30-resolve-branch-field-finalization-deadlock`, had its
  branch recorded by hand before the deadlock was understood, so when that task
  finalized, step 4 took the no-op path — `branch` non-null and different from
  `base_branch`. The gate ordering was exercised for real; the
  `task.py set-branch` call and its scoped branch-metadata commit were not.
  `tests/test_finish_work_branch_preparation.py` pins the instruction ordering
  in the skill text, not the runtime behavior of the commands it names.

- Treat the next task that reaches finalization with a null `branch` as the
  rehearsal for that write path, and record what it did. Until then, no evidence
  exists that the preparation commit stays scoped to one `task.json`, that the
  detached-HEAD stop fires, or that the resulting commit lands outside the
  archive range as designed.

- Do not preemptively rewrite the pack's step 4 while parked. The deadlock fix
  shipped in 0.56.4 and is the current contract; changing it without an upstream
  trigger reopens the problem it closed.

## Acceptance Criteria

- [ ] An upstream issue exists describing the null `branch` at activation, with
      the two call sites above cited.
- [ ] The trigger is resolved one way or the other: upstream records the branch,
      or upstream declines.
- [ ] If upstream records it, `sd-finish-work` step 4 is narrowed to a
      compatibility path for pre-existing records, and the ordering test is
      updated to match.
- [ ] If upstream declines, the `set-branch` write path gains a runtime test
      rather than remaining pinned only as skill text.
- [ ] Either outcome records what the first live null-branch finalization
      actually did.

## Notes

- Do not start this task until one of the triggers above exists.
- This is a parked task, not currently actionable backlog.
- Related shipped work: pack 0.56.4, PR #280.
