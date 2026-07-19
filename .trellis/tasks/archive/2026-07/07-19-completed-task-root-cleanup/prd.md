# Archive completed active-root tasks and detect recurrence

## Goal

Restore the Trellis task-directory invariant by archiving completed tasks that
remain in the active task root, and prevent the condition from becoming hidden
again.

## Confirmed Facts

- Four direct children of `.trellis/tasks/` have `task.json.status` set to
  `completed` but are not under `.trellis/tasks/archive/`.
- `sd-status` inventories direct task-root records but currently reports only
  `planning` and `in_progress` collections.
- The shared review preflight already validates other Trellis task-state
  invariants and is distributed from `templates/scripts/`.
- Trellis provides `task.py archive`, which preserves task metadata and moves a
  completed task into the year/month archive hierarchy.
- Audit finding A-037 records the affected directories and the missing
  visibility.

## Requirements

- Archive the four completed task directories identified by A-037 through the
  Trellis lifecycle command rather than moving files manually.
- Extend `sd-status` data and human-readable output with a bounded inventory of
  completed tasks found directly under `.trellis/tasks/`.
- Treat any such task as a status anomaly and provide the Trellis archive
  command as remediation.
- Add a shared preflight failure for completed direct task-root records so the
  invalid state is caught before publication.
- Ignore `.trellis/tasks/archive/`, non-directory entries, symlinks, and nested
  paths outside the direct active-task root.
- Handle unreadable or malformed task records consistently with each existing
  command's error behavior; this check must not execute task-configured code.
- Keep canonical templates and installed mirrors synchronized.

## Acceptance Criteria

- [x] The four A-037 task directories no longer exist in the active task root
      and appear in the normal Trellis archive hierarchy with completed
      metadata preserved.
- [x] `sd-status` reports zero completed tasks outside the archive after
      cleanup.
- [x] A status fixture containing a direct completed task reports its count,
      identity, anomaly, and archive remediation.
- [x] Review preflight fails when a direct task-root `task.json` has status
      `completed` and names the offending task and remediation command.
- [x] Review preflight passes for completed tasks under `archive/`, planning or
      in-progress direct tasks, symlinks, and repositories without Trellis
      tasks.
- [x] Status and preflight scans remain bounded to direct task-root entries.
- [x] Focused status and preflight tests pass, source/template parity passes,
      and canonical repository checks expose no new failure.

## Out of Scope

- Changing upstream Trellis archive semantics.
- Automatically moving tasks from read-only status or preflight commands.
- Repairing malformed task records or changing planning/in-progress task
  selection.

## Notes

- Origin: audit finding A-037 in `.trellis/audit/report-2026-07-19.md`.
- This is a lightweight invariant-enforcement task and may remain PRD-only.
