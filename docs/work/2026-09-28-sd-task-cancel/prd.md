---
title: sd task cancel records a dropped task instead of deleting it
created: 2026-09-28
---
# PRD — sd task cancel

## Problem

The v2 Tasks mockup offers Delete on a task, written as `sd task delete 1038`
and off with the reason "no CLI verb: sd task has no delete; move it to Done to
keep a record" (ui-design, verb check of 2026-09-28).

Done is the wrong record for a task nobody did. The task statuses are
`planning`, `ready`, `in_progress`, `blocked` and `done` (`TASK_STATUSES` in
`local-sd-db/sd_db/workflow.py`, system repository), so a dropped task either
stays open forever or lies about having been finished. Work items already have the honest verb: `sd work cancel
<item> --reason` records a deliberate cancellation and keeps the row.

## Requirements

1. `sd task cancel <id> --reason "<why>" [--if-revision R] [--json]` moves the
   task to a terminal `cancelled` status, keeps the row and prints it. The
   reason is required and lands as a note on the task.
2. `cancelled` joins the task statuses as terminal: allowed from every status
   except `done`, and no move leaves it.
3. `sd today`, the Tasks page and the dashboards leave cancelled tasks out of
   every open count, and `sd task show` still prints one.
4. There is no hard delete verb. A row that must go for a legal reason is a
   database operation, not a command.
5. The mockup's Delete becomes Cancel with `sd task cancel <id> --reason`, and
   `designs/tools/collect-counts.mjs` regenerates `data/commands.js` (ui-design,
   `tasks.html`).

## Acceptance criteria

- [ ] `sd task cancel --help` requires `--reason`.
- [ ] After `sd task cancel <id> --reason x`, `sd task show <id>` prints status
      `cancelled` and the reason; `sd today --json` does not list the task.
- [ ] `sd task status <id> ready` on a cancelled task exits non-zero.
- [ ] `sd task cancel` on a done task exits non-zero.
- [ ] `designs/v2/commands.html` shows no delete declaration.

## References

- ui-design `products/system/designs/v2/tasks.html` (`item.delete`).
- system `local-sd-db/sd_db/workflow.py`, `TASK_STATUSES` and
  `allowed_statuses`.
- `bin/sd_work.py`, `sd work cancel`, the verb this one mirrors.

## Log

- 2026-09-28 created
