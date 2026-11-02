---
title: Retire the item kinds personal, work and skill-review
created: 2026-11-01
item: sd:7004
branch: feat/sd-7004-kinds
---

# Design — retire-item-kinds

The item's row holds status, progress and decisions; this page holds the shape.

## Problem

`item.kind` allows nine values; the operator ruled on 2026-10-31 that six stay:
`task`, `followup`, `idea`, `report`, `work-idea` and `personal-idea`.

- `personal` adds nothing over a task: house chores live in a repository now.
  It also blocks title, due and body edits, since `DETAIL_KINDS` leaves it out.
  The hub holds 5 rows, all done.
- `skill-review` has 0 rows. The catalogue files a review as its own kind,
  while promote, demote and apply already file `task` rows marked by
  `fields.skill_review` (`workflow.PRODUCED_FIELDS`).
- `work` is the legacy `prd.md` item. The hub holds 105 done rows and 1 open.
  The kind drives a delivery subsystem: `deliver_work`, `cancel_work`, the
  owned-merge delivery proof, the `docs/work` row reader behind `sd-status`
  and `sd-ship`, and two producers.

## Approach

Two slices, each one migration that edits the CHECK in place, as 009 and 032 did.
A rebuild is ruled out: four foreign keys point at `item(id)` (009 says why).

Slice 1, this PR, migration 046:

1. A guard refuses before `writable_schema` is on unless `item` holds 032's
   kind list or the list 046 leaves (a restore replays onto either).
2. `UPDATE item SET kind = 'task' WHERE kind IN ('personal', 'skill-review')`.
   `repo`, `status`, notes and every other column stay as they are.
3. The CHECK text loses `'skill-review'` and `'personal'`.
4. A second guard accepts only the new list, the status list and the gate
   CHECK, with neither word left; then the schema cookie is bumped.

The library follows: `HAND_KINDS`, `REPO_LESS_KINDS`, `TASK_STATUS_KINDS`,
`priority_sweep.KINDS`, `sd_ship_body._CLOSABLE_KINDS`, `runner.RUNNABLE_KINDS`
and the dashboard's kind lists drop both. `sd task add --kind` reads
`HAND_KINDS`, so its choices follow. The catalogue files a review as a `task`
row whose `fields.skill_review.action` is `review`; `skills_catalog.is_review`
is the one test for it, and delivery leaves such a row out, as it left the
kind out before.

The migration writes no note. A restore replays migrations onto an older
snapshot and refuses any change in a table's row count (`backup.py`,
`_upgrade_restore_candidate`), so a note per moved row would refuse every
restore of a snapshot that holds one.

Slice 2, pack sd:7064: retire `work`. Stop both producers
(`workflow.register_work_item` and `sources/register.py`), delete the
delivery subsystem and its tests, convert the open hoa sd:1276 to a task that
its folder names with `item: sd:1276`, migrate the 105 done rows to `task`,
and narrow the CHECK to six. Every test that seeds `kind="work"` changes with
it: about 40 files, and `dashboard/tests/support.py` defaults to it.

Rejected: retiring all three in one PR. The `work` half deletes a subsystem
and rewrites 40 test files; bundled, it would hold the two small kinds behind
the largest review.

## Non-goals

- No change to `work` rows or code in slice 1.
- No new command, flag, field or state store.
- The reverse does not put `personal` or `skill-review` back on a moved row:
  the migration records no original kind, and an older build reads a task.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Migrate a store holding rows of every kind | `personal` and `skill-review` rows become `task`; the CHECK narrows | none expected | not needed: one transaction | `TheRetiredItemKinds.test_rows_of_the_retired_kinds_become_tasks_and_the_check_narrows` |
| Re-run on the new shape (`migrate` again, or a restore replay) | nothing | a replay that refused or changed rows would block a restore | the guard accepts the new list; the `UPDATE` and `replace` match nothing | `test_a_replay_on_the_new_shape_changes_nothing`, `test_a_second_migrate_applies_nothing` |
| Crash after the `UPDATE`, before the CHECK edit | rows half moved inside the transaction | the process dies or a statement aborts | `migrate` wraps the file and its version bump in one transaction: the store stays at 45 with every row's kind; the next run finishes | `test_a_failure_after_the_update_leaves_forty_five_and_a_rerun_finishes` |
| Guard meets a shape it does not know | nothing | a hand edit or another branch's CHECK | the guard aborts before `writable_schema`; the store stays at 45 | `test_an_unknown_item_shape_is_refused_and_left_at_forty_five` |
| Restore an older snapshot that holds `personal` rows | the replay moves them to `task` | a changed row count refuses the restore | the migration moves kinds only and adds no row | `test_a_restore_of_an_older_snapshot_keeps_every_count` |
| An older client writes a retired kind after the migration | nothing | a local build at 45 opens the store | `connect` refuses a store newer than its build (`SchemaTooNew`); a raw insert fails the CHECK | `test_a_retired_kind_is_refused_after_the_migration`, `TheVersionRefusals.test_a_newer_database_is_refused_on_open_naming_both` |
| A satellite on the older build writes over the tailnet | nothing | its `sd task add --kind personal` reaches the hub | the hub refuses a build that differs before it opens the file (`remote.BuildMismatch`); `repo-sync.sh follow` moves the satellite | `test_wire.test_a_newer_hub_refuses_this_satellite_and_names_it_to_upgrade` |
| The current build files a retired kind | nothing | `sd task add --kind personal`, an edit to `personal`, a catalogue review | `HAND_KINDS` refuses both kinds; the catalogue files a `task` | `KindEditing.test_every_kind_list_names_only_kinds_the_schema_allows`, `test_review_files_one_item_and_the_dashboard_writes_the_same_row` |
| Roll the hub back to the previous commit | nothing | the older build meets a store at 46 | it refuses (`SchemaTooNew`); the reverse in 046's header widens the CHECK and sets 45; moved rows stay `task` | `test_the_reverse_widens_the_list_back` |

The `work` rows belong to pack sd:7064 and stay out of this table and
this PR's tests: the migration of its done rows, the conversion of hoa
sd:1276, a producer that writes `work` after the narrow, and the
delivery subsystem's removal. sd:7064's own design adds them.

## Slices

1. Migration 046 and the library for `personal` and `skill-review` (this PR).
   Every machine keeps working: the hub migrates; a satellite refuses until
   `repo-sync.sh follow` moves it, as for every migration.
2. Retire `work` (pack sd:7064): stop the producers, delete the delivery
   subsystem, convert hoa sd:1276, migrate the done rows, narrow to six kinds.

## Acceptance criteria

- `make test SUITE=sd_db` passes, and the dashboard suites that name a kind pass.
- On a copy of a store at 45, `SELECT kind, count(*) FROM item GROUP BY kind`
  after `migrate` lists no `personal` and no `skill-review` row.
- After slice 2, the same query lists only the six kinds.

## Risks

- A hand-edited CHECK on some machine refuses the migration; the guard names it.
  Accepted: the operator fixes the shape and reruns.
- A `skill-review` row on a satellite's local store would move to a task that
  `is_review` reads as a review only if its fields say `review`. The catalogue
  always wrote that action, so the row stays a review.
- The two CHECK guards tie their pass to the exact text: the kind list, the
  status list and the gate CHECK. A store with any other `item` shape fails.
