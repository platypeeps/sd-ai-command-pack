---
title: Retire item kind work and its delivery subsystem
created: 2026-11-01
item: sd:7064
branch: docs/sd-7064-design
---

# Design — retire-work-kind

The item's row holds status, progress and decisions; this page holds the shape.
The tables give a path and its line numbers at origin/main `5cf6b4990`. Pack sd:7004's branch
(`feat/sd-7004-kinds`, migration 046) moves some of them.

## Problem

`work` is the legacy `docs/work/<item>/prd.md` item. The operator ruled on
2026-10-31 that six kinds stay: `task`, `followup`, `idea`, `report`,
`work-idea` and `personal-idea`. Pack sd:7004 retires `personal` and
`skill-review` in migration 046; ruling #39210 moved `work` here.

The kind still drives a delivery subsystem: verified delivery and cancel
receipts, an owned-merge proof, a work-only status lock, dashboard controls
and two producers. No `work` row was filed after 2026-10-05 (id 5454), and
`sd-plan` writes `design.md` with an `item:` key now. The subsystem guards
rows that no longer arrive.

## Rows on the hub

Read-only on 2026-11-01, `file:~/.local/share/sd/sd.db?mode=ro`, schema 45.

| Measure | Rows |
| --- | --- |
| `kind='work'` | 106 |
| status `done` | 105 |
| status `planning` | 1 (hoa sd:1276, no branch, P3) |
| `source='docs/work'` | 102 |
| `source='register'` | 4 (world-simulator O27 to O30, all done) |
| `fields.completion` outcome `delivered` | 27 |
| `fields.completion` outcome `cancelled` | 69 |
| no receipt | 10 (9 done, 1 planning) |
| `shipped_at` set | 28 |
| `fields.artifact_link` set | 31 |
| `branch` set | 19 |
| notes on these rows | 760 |
| assignments on these rows | 0 |
| `ship:` receipts naming one | 46 (10 `deliver`; 9 not at `merged`) |
| `runner_run.delivery_proof` set | 0 of 216 runs |

Every `docs/work` and `register` row is `work`, and every `work` row has one
of the two sources. Each of the 27 delivered rows also carries a
`status_change` note that reads `delivered at <commit>`.

## Approach

Retire the kind in five slices: stop the producers, re-key the folder reader,
then delete the dashboard controls and the library subsystem, then migrate.

Migration 047 builds on 046 and copies its shape:

1. A guard refuses before `writable_schema` is on unless `item` holds 046's
   kind list or the list 047 leaves.
2. `UPDATE item SET kind = 'task' WHERE kind = 'work'`. Every other column
   stays: `source`, `external_id`, `path`, `branch`, `fields` (receipts and
   `artifact_link`), `shipped_at`, `source_commit`. No row is added, no note is
   written: a restore refuses a replay that changes a table's row count.
3. The CHECK text loses `'work', ` and keeps the six kinds.
4. A second guard accepts only the six-kind list, the status list and the gate
   CHECK, with no `'work'` word left and no `work` row. Then the cookie bump.

The reverse in the header widens the list and runs
`UPDATE item SET kind = 'work' WHERE source IN ('docs/work', 'register')`.
That restores every kind exactly, because only `work` rows ever carried
those sources and no producer writes them after slice 1.

The `docs/work` folder reader stays, keyed by source and not by kind. Note
#39209 says delete it; the code says it serves every legacy `prd.md` folder.
`sd-status` reads an archived `prd.md` folder through `Rows.item` and
`progress.item_for_artifact`; with a kind filter and no `work` row, each one
reads `unknown`. On disk now: 8 `prd.md` folders in hoa, 7 in system, 2 in the
pack, and the mezmo folders on the work satellite. Ruling #40102 keeps it.

Kept and still used by tasks: `cancel_work` with `task_guard` (renamed
`cancel_task`), `completion_record`, `waived_suffix`, `CANCELLABLE_TASK_KINDS`,
`item_for_artifact`, `ship.delivery_key`, `ship.note_merge`, `sd-ship
--deliver` for tasks and followups, `sd task status done --delivered-by`, and
`sd work deliver --associated` for a task or followup.
`completion_record` also accepts a `delivered` receipt on a `task` row. The 27
migrated delivered rows then keep reading as delivered, and `sd-status` raises
no new `unmarked` finding. `change_status` already drops the receipt when a
row reopens.

Rejected: move the rows first (047) and narrow the CHECK last (048). That
removes the window in which hoa sd:1276 takes no status move. It costs a
second migration and a second backup-helper reversal for one P3 planning row.

Rejected: one PR. The deletions and about 50 test files would hold the
producer stop behind the largest review.

### Producers

| Path | Lines | What | Becomes | Slice |
| --- | --- | --- | --- | --- |
| `lib/sd_db/workflow.py` | 453-531 | `register_work_item`, `create_item(kind="work")` at 527 | delete | 1 |
| `lib/sd_db/jobs/cli.py` | 76, 1047-1105, 1418 | `sd-db work register` | delete the verb | 1 |
| `bin/sd-db` | 27 | `work` in `CLI_VERBS` | delete | 1 |
| `bin/sd_work.py` | 339-381, 456-500, 1871-1876 | `sd work register`, `REGISTER_NEEDS`, `_register` | delete | 1 |
| `lib/sd_db/sources/register.py` | 273 | `sd-db import register` lands `kind="work"` | `task` | 1 |
| `skills/sd-plan/SKILL.md` | 54-62 | step 4 runs `sd work register` | delete the step | 1 |

`HAND_KINDS`, `sd task add --kind` and the dashboard Kind field never offer
`work`; a raw insert is the only other way, and 047's CHECK refuses it.

### Readers

| Path | Lines | What | Becomes | Slice |
| --- | --- | --- | --- | --- |
| `lib/sd_db/progress.py` | 101, 113 | `item_for_artifact` filters `kind = 'work'` | `source = 'docs/work'` | 2 |
| `bin/sd_lib.py` | 1639-1645, 1684-1694 | `Rows` reads folders through it | keep | 2 |
| `bin/sd_handoff_rows.py` | 118-132 | `item_for` (`sd-note`, `sd suggest`) | keep | 2 |
| `bin/sd_lib.py` | 2380-2382 | `named_row` refuses an `item:` key naming a `work` row | delete | 5 |
| `lib/sd_db/progress.py` | 148-180 | `completion_record` reads delivered receipts on `work` only | also on `task` | 4 |
| `lib/sd_db/progress.py` | 64-69 | `work_controls` | delete | 4 |
| `lib/sd_db/workflow.py` | 657-660 | `allowed_statuses` work branch | delete | 4 |
| `lib/sd_db/runner.py` | 54 | `RUNNABLE_KINDS` (read by `build.py` 142 and 318, `draft.py` 76) | drop `work` | 4 |
| `lib/sd_db/runner.py` | 613 | `delivery_candidates` SQL | drop `work` | 4 |
| `bin/sd-ship` | 2022-2037 | `delivered_at` work branch | delete | 4 |
| `dashboard/sd_dashboard/tasks_screen.py` | 368-371 | `work` key in item details | delete | 3 |
| `dashboard/sd_dashboard/screens.py` | 238, 263-275 | `completion_summary` panel | delete | 3 |
| `dashboard/sd_dashboard/v2/static/hoa.js` | 442 | `KINDS` filter | drop `work` | 3 |

Not this kind, left alone: the Today and `sd-status` section named `work`
(`reads.WORK_KIND` means "not an idea"), realm `work`, and
`repos.CLONE_PROFILES`.

### Writers and guards

| Path | Lines | What | Becomes | Slice |
| --- | --- | --- | --- | --- |
| `lib/sd_db/progress.py` | 27-36, 72-77 | `_work_guard`, `_work` | delete; `_work` takes `task_guard` | 4 |
| `lib/sd_db/progress.py` | 183-212 | `relink_artifact` | delete | 4 |
| `lib/sd_db/progress.py` | 215-242 | `cancel_work`, default work guard | `cancel_task`, `task_guard` default | 4 |
| `lib/sd_db/progress.py` | 245-346, 369-422 | `deliver_work`, `deliver_associated_work`, `_delivery_evidence`, `_verified`, `_complete_delivery`, `_waived` | delete | 4 |
| `lib/sd_db/ship.py` | 171-210, 221-254 | `prepare_delivery`, `finalize_delivery` (no production caller) | delete | 4 |
| `lib/sd_db/runner.py` | 299, 323, 365-367 | `delivery_proof` reset, update and finalize | delete; column stays | 4 |
| `lib/sd_db/writes.py` | 286-289 | `transition` refuses work `done` | delete | 4 |
| `lib/sd_db/workflow.py` | 89, 571-572, 757-761 | `DETAIL_KINDS`, repo lock, terminal and `done` refusals | drop `work`, delete | 4 |
| `bin/sd_work.py` | 860-863, 905, 996-1043, 1059-1080, 1415-1427, 1861-1870, 1878-1886 | `sd work relink`, `sd work cancel`, plain `sd work deliver`, work refusals | delete; `deliver --associated` stays for tasks | 4 |
| `bin/sd-ship` | 105-109, 611-623, 1988-2016, 2038-2045 | `DELIVERING_KINDS`, required acceptance file, `close_items` and `record_delivery` work branches | drop `work`, delete | 4 |
| `bin/sd_ship_body.py` | 226 | `_CLOSABLE_KINDS` | drop `work` | 4 |
| `dashboard/sd_dashboard/controls.py` | 101-127, 213-235 | work status panel, Relink and Cancel forms | delete | 3 |
| `dashboard/sd_dashboard/server.py` | 649-656 | `/api/items/N/relink`, `/api/items/N/cancel` | delete; `/cancel-task` stays | 3 |
| `dashboard/sd_dashboard/v2/static/task-details.js` | 96, 476-498, 546 | work `done` refusal, `work.relink`, `work.cancel`, repo lock | delete | 3 |

Documents go with the slice that removes the verb: `README.md` lines
262-330, `WORKFLOW.md` lines 15-20 and 296-338, `skills/sd-ship/SKILL.md`
line 54, `skills/sd-ship/references/delivery.md` lines 31-80,
`skills/sd-ship/references/recovery.md` lines 15-35 and
`dashboard/docs/pages/tasks.md` lines 18-20.

### Tests

49 test files and 3 skill documents name the kind or the subsystem.
The large ones are `tests/sd_db/test_progress.py` (58 hits),
`tests/test_sd_work.py` (35), `tests/sd_db/test_write_fence.py` (25),
`tests/test_delivery_evidence.py` (23), `tests/sd_db/test_work_register.py`
(21), `tests/test_sd_ship.py` (15) and `dashboard/tests/test_v2_tasks.py`
(15). `source:dashboard/tests/support.py::item` (line 93) defaults to `work`:
124 calls in 47 files pass no kind. `source:tests/row_seed.py::seed_row`
(line 33) seeds `work` for 9 files. Subsystem tests go with
their code; incidental seeds move to `task` in slice 2.

## What the operator loses

- A whole-item `sd-ship --deliver` no longer requires an acceptance file. A
  task may still give one, with waivers (sd:3704). Ruling #40103.
- No new delivery writes `shipped_at`, so `reads` "Shipped" and the report's
  delivered count stop growing from deliveries. None was written after
  2026-10-05.
- A done former-work row can reopen, like any task, and the reopen drops its
  receipt. Its `status_change` notes keep the delivery or cancel history.
- A former-work row's repository becomes editable. An edit unhooks its
  `prd.md` folder from `sd-status`, because the reader keys on repository.
- `sd work relink` goes. A task folder names its row with `item: sd:<id>`;
  an archive move of a `prd.md` folder still resolves by its original slug.
- `sd work cancel` and plain `sd work deliver` go. `sd task cancel` and
  `sd task status done --delivered-by` cover a task.
- The owned-merge delivery proof goes. No run ever wrote one.
- The v1 item page's Delivered or Cancelled panel goes. History shows it.

## Non-goals

- No change to `idea`, `report`, `followup` or the two idea kinds.
- No `item:` key edits in other repositories' `prd.md` folders.
- `runner_run.delivery_proof` and `item.shipped_at` stay as columns.
- No new command, flag, field or state store.
- System's `docs/design/coding-workflow.md` names `sd work`; a system item
  covers it.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| 047 on a store holding every work shape | `work` rows become `task`; CHECK narrows to six | none expected | one transaction | `test_work_rows_become_tasks_and_every_other_column_stays` |
| Re-run on the new shape (`migrate`, restore replay) | nothing | a refused or changing replay blocks a restore | guard A accepts the six-kind list; `UPDATE` and `replace` match nothing | `test_a_replay_on_the_new_shape_changes_nothing` |
| Crash after the `UPDATE`, before the CHECK edit | rows half moved in the transaction | process dies or a statement aborts | `migrate` wraps file and version bump in one transaction; the store stays at 46; the next run finishes | `test_a_failure_after_the_update_leaves_forty_six_and_a_rerun_finishes` |
| Guard A meets an unknown `item` shape | nothing | hand edit, or a store that skipped 046 | abort before `writable_schema`; stays at 46 | `test_an_unknown_item_shape_is_refused_and_left_at_forty_six` |
| Restore a snapshot at 45 holding `personal` and `work` rows | replay runs 046 then 047 | a changed row count refuses the restore | both move kinds only and add no row | `test_a_restore_of_a_forty_five_snapshot_keeps_every_count` |
| Older client opens the store | nothing | a build at 46 | `SchemaTooNew`; a satellite gets `remote.BuildMismatch` until `repo-sync.sh follow` | `TheVersionRefusals.test_a_newer_database_is_refused_on_open_naming_both` |
| Something writes `work` after 047 | nothing | a raw insert, an old script | the CHECK refuses it; slice 1 removed every producer | `test_work_is_refused_after_the_migration`, `test_no_producer_names_kind_work` |
| Roll the hub back past 047 | nothing | the old build meets 47 | the header reverse widens the list and restores `work` by source | `test_the_reverse_restores_every_work_row` |
| `sd-status` reads an archived `prd.md` folder after 047 | nothing | no row found reads `unknown`; no receipt reads `unmarked` | slice 2 keys the reader on source; `completion_record` reads delivered task receipts | `test_a_migrated_delivered_row_reads_done_with_no_finding` |
| A stale `ship:` receipt names a migrated row | nothing | reconcile closes a done row twice or refuses it | `delivered_at` finds the `delivered at` note; a done task stays done | `test_reconcile_of_a_merged_deliver_receipt_on_a_migrated_row_is_a_no_op` |
| Window between slice 4 and slice 5 | none | hoa sd:1276 takes no status move; `sd task cancel` refuses `work` | slice 5 moves it to `task`; nothing is lost | `test_a_work_row_takes_no_status_until_migrated` (slice 4, deleted in 5) |
| Window between slice 3 and slice 4 | none | the CLI still delivers or cancels work; the dashboard does not | no open row needs it; the CLI stays the way out | none: no state moves |

## Slices

Each slice is one PR. Slice 5 needs pack sd:7004 (046) on main; slices 1 to 4
do not, but land after it to avoid conflicts in `RUNNABLE_KINDS` and
`_CLOSABLE_KINDS`.

1. Stop producers. Delete `register_work_item`, `sd work register`,
   `sd-db work register` and the `sd-plan` step; `register` lands `task`.
   Delete `tests/sd_db/test_work_register.py`. Fail-first: a source scan
   finds no `kind="work"` writer under `bin/` and `lib/`. Leaves: no new
   `work` row; every reader unchanged.
2. Re-key the reader and the seeds. `item_for_artifact` filters on
   `source = 'docs/work'`; `support.item()` and `row_seed` default to `task`;
   incidental seeds move to `task`. Fail-first: a `task` row with
   `source='docs/work'` resolves its folder in `sd-status`. Leaves: the same
   102 rows resolve; tests no longer depend on `work` by default.
3. Dashboard. Delete the work panel, the Relink and Cancel forms and actions,
   both routes, `completion_summary`, and `work` in the hoa filter. Fail-first:
   `POST /api/items/N/relink` answers 404, and a work row's details carry no
   `work.*` action. Leaves: the CLI still serves work rows.
4. Library and CLI. Delete the writers above, the owned-merge proof and the
   work branches in `sd-ship`; rename `cancel_work` to `cancel_task`;
   `completion_record` accepts a delivered task receipt; docs follow. Delete
   the subsystem tests. Fail-first: `completion_record` on a `task` row with a
   delivered receipt returns it. Leaves: `work` rows read but take no status.
5. Migration 047. Rows to `task`, CHECK to six, the `named_row` refusal and
   the last `work` seeds go; backup and judgment helpers reverse 047, as for
   046. Carries `Closes: sd:7004` and `Closes: sd:7064`. Fail-first: the
   failure table's 047 rows.

Slices 1, 3 and 4 are mostly deletions and can run on Sonnet. Slices 2 and 5
stay on Opus.

## Acceptance criteria

- On a copy of the hub store, `SELECT kind, count(*) FROM item GROUP BY kind`
  after `migrate` lists six kinds at most and no `work`; `task` grows by 106.
- On the same copy, a column dump of the 106 rows matches the dump from before,
  except `kind`.
- `sd-status` in hoa and system names the same findings before and after 047.
- `grep -rnE "kind *(=|==|!=) *['\"]work['\"]|deliver_work|relink_artifact|work_controls"
  bin lib dashboard --include='*.py' --include='*.js'` prints nothing but
  schema history.
- `make test SUITE=sd_db` and the dashboard suites that name a kind pass.

## Open questions

Both are answered (operator rulings, 2026-11-01).

1. The `docs/work` reader. Note #39209 listed it for deletion.
   Ruling #40102: keep it, keyed on `source = 'docs/work'`. Every `prd.md`
   folder keeps its row; slice 2 makes the two-line change.
2. Whole-item delivery evidence. `work` required an acceptance file with a
   result per criterion; a task makes it optional.
   Ruling #40103: accept the loss. `--deliver` no longer requires an
   acceptance file; a task may still give one, with waivers.

Decided here, each a routine call (recorded on the item):

- One migration, not two: the frozen window holds one P3 planning row.
- `cancel_work` becomes `cancel_task`: all three callers change in slice 4.
- `register` lands `task`; its importer stays.
- `completion_record` reads delivered receipts on `task` rows.
- `sd work deliver --associated` stays for a task or followup: `sd-ship`
  names it as the repair for an associate-only merge.

## Risks

- Slice 2's default flip may break dashboard tests that assert work
  behaviour. Not measured: every gate slot was held. Its builder runs the
  dashboard suites first and sizes the slice from the failures.
- The reverse restores `work` by source. A `task` row given
  `source='docs/work'` after 047 would turn into `work`. No producer writes
  that source after slice 1. Accepted.
- Guard A ties its pass to the exact CHECK text that 046 leaves. A store with
  any other `item` shape fails and names it. Accepted: the operator fixes the
  shape and reruns.
- The 9 `ship:` receipts not at `merged` that name a work row stay stale.
  Their items are done; a later `prepare` on one meets a done task.
