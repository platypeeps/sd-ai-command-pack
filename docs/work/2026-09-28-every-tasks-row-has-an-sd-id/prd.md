---
title: Every row on the Tasks page has an sd id
created: 2026-09-28
---
# PRD — every Tasks row has an sd id

## Problem

The v2 Tasks mockup carries two real rows observed 2026-09-27 that have no sd
id: "repo-sync failed: home-assistant/core" (kind `ops`, from a job failure)
and "A2 VSD alarm follow-up" (kind `followup`, HOA, reference `a2-vsd`). On
those rows Status → Ready, Edit, Note and Run are off with the reason "no CLI:
this row has no sd id" (ui-design, verb check of 2026-09-28).

The page is a view of the task table, and a row the table does not hold cannot
be moved, edited or run. Each such row is a fact another source knows (a job
log, an HOA runbook) that the dashboard pastes in as if it were a task.

## Requirements

1. The Tasks page lists rows from the task table only. No page-side row is
   synthesized from a job log or a document.
2. A source that wants a task creates one: a failed job creates an `ops`
   followup through `sd task add --kind followup --ref <source>:<id>`, and an
   HOA followup does the same from its runbook step.
3. `--ref` is new on `sd task add`: it records the source id on the task, and a
   second add with the same reference updates the existing task whatever its
   status, so a retried delivery of the same occurrence never reopens work
   the operator resolved or cancelled. A reference names one occurrence, a
   job by its run (`job:<name>:<run>`), not its lifetime: the next failing
   run carries a new reference and raises a new task.
4. `sd today --json` and `sd task show` print the reference, so the row can be
   traced back to the log or document that raised it.
5. The mockup's two id-less rows become rows with ids, the "no sd id" reasons
   go, and `designs/tools/collect-counts.mjs` regenerates `data/commands.js`
   (ui-design, `tasks.html`).

## Acceptance criteria

- [x] `sd task add --help` lists `--ref`.
- [x] `sd task add "x" --kind followup --ref job:repo-sync:42` twice leaves
      one task, and `sd task show` on it prints the reference.
- [x] After that task is done, the same add leaves it done and creates
      nothing; `--ref job:repo-sync:43` creates a second task.
- [x] Every row in `sd today --json`'s task list carries an `id`.
- [ ] `designs/v2/commands.html` shows no declaration with the reason "this row
      has no sd id".

## References

- ui-design `products/system/designs/v2/tasks.html`, the `noId` reason and the
  two `real: true` rows with `id: null`.
- `bin/sd_work.py`, `sd task add`.
- system `local-sd-db/sd_db/workflow.py`, `TASK_STATUSES`.

## Log

- 2026-09-28 created
- 2026-09-28 review pass 1 (codex, advisory, addressed): a reference that
  deduplicates for a job's lifetime would send a later failure to a done row.
  Requirement 3 now keys a job by its run; a criterion covers the second failure.
- 2026-09-28 review pass 2 (codex, advisory, addressed): with run-scoped
  references, deduplicating only among open tasks let a retried delivery of a
  resolved run raise new work. Requirement 3 now deduplicates across every
  status; the criterion shows run 43 as the new task.
- 2026-10-07 requirements 3 and 4 built in the pack (`--ref`, `ref:` and `ref`);
  requirements 1, 2 and 5 are ui-design and job-side work and stay open.
