---
title: Queue shows an item waiting on its PR, and Metrics times the wait
created: 2026-11-06
item: sd:7859
---

# Design — pr-wait

The item's row holds status, progress and decisions; this page holds the shape.

## Problem

An item whose pull request waits on review reads as working in Today's Queue view.
Its worktree is still on disk, so `active_sessions` ties it to the item and Queue draws a working row.
Nothing says who the item waits on, and nothing records how long it waited.
The contribution lanes (`contributions.LANES`) already say who acts on a pull request,
but they live in observation checkpoints, and `sd-db prune` removes superseded checkpoints.
So the history of a lane is lost once the next observation lands.

## Approach

An item's linked pull request is its contribution `pull_url`, the one link `contributions.py` owns (ruling, note #45986).

1. **Record.** `contributions.record_lane(connection, item)` reads the item's lane the way the projection does,
   through one shared rule, `_lane`, and writes a `comment` note when the lane or the pull request's state changed:
   `PR lane: <lane> · <state> · <url>`, session `contribution-observer`.
   It compares with the item's newest such note for that url, so a rerun writes nothing.
   `observe_pull`, `observe_dependencies`, `acknowledge` and `configure` call it inside their own transaction,
   so the note and the checkpoint it describes land together or not at all.
2. **Backfill.** The first note for an item and url is preceded by what history still holds:
   the shadow row's `created_at` (opened, on reviewers), each `contribution-observer` followup note on the item
   (on you from its timestamp to its `resolved_at`), and the shadow's `merged_at` or `closed_at`.
   Backfilled notes carry their historical time and end in `(backfilled)`.
   `contribution_sync.refresh` calls `record_lanes` for every registered pull request once per run,
   so an item no longer observed (merged, done) is backfilled too.
3. **Durations.** `contributions.pr_waits(connection, now=)` reads the lane notes, oldest first.
   The time between a note and the next goes to its lane: `awaiting_you` and `newly_unblocked` are on you,
   `awaiting_them` is on reviewers; `merged` and `closed` end the wait. An open pull request counts to `now`.
   First PR to merge runs from the first note to the first `merged` one.
4. **Queue.** `/api/queue` gains `prs`: each item with an open pull request in a waiting lane,
   unless the item has a merging, next or blocked lane row, which keeps its lane state.
   Today's Queue view draws it as a `blocked` row, `blocked: PR · on you` or `on reviewers`, with how long it waited,
   and drops that item's live-session row and its suggested or open row. Build runs and runner assignments stay:
   they are a live process.
5. **Metrics.** `/api/metrics` gains `prs`: totals on you, on reviewers, waiting, and first PR to merge,
   and the five slowest items. The Metrics page draws it as one ledger table, as it draws the lanes.

`comment` is the note kind. `status_change` is `transition`'s alone and feeds status ages;
`followup` is open work that Needs you lists; `decision`, `question`, `proposal` and `exec` mean other things.
`configure` already records contribution changes as a `comment`.

Rejected: a lane-history table (the brief forbids a new store), and keeping history in checkpoints (prune removes them).
Rejected: deriving durations at read time from followups alone: the on-reviewers spans and the open time need the shadow,
and a read that joins three sources every page load is slower and drifts from what was recorded.

## Non-goals

- Pull requests the lane opens (`sd-ship prepare` receipts) are not contribution rows; linking them is a follow-up.
- No new command, flag, table or setting. No change to how lanes are computed.
- No GitHub read: the observer already reads GitHub.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| observe writes checkpoint, then lane note | checkpoint row and one note | process stops between the two | both are in one transaction: neither lands; the next observation writes both | `test_a_failed_lane_note_rolls_back_the_observation` |
| backfill notes, then the current lane note | several notes for one item | process stops mid-backfill | one transaction per item; nothing lands, the next refresh backfills again | `test_a_backfill_that_fails_writes_no_note` |
| rerun of observe or refresh | none | a second note for the same lane | `record_lane` compares with the newest note for the url and writes nothing | `test_an_observed_pull_writes_one_lane_note_and_a_rerun_writes_none` |
| acknowledge moves attention | checkpoint, then lane note | lane changes on you to on reviewers without a note | `acknowledge` calls `record_lane` in its transaction | `test_a_maintainer_comment_is_on_you_and_acknowledging_it_is_on_reviewers_again` |
| older state: item configured before this change | no lane notes | durations read nothing | refresh calls `record_lanes`, which backfills from shadow and followups | `test_backfill_reads_the_shadow_and_the_followups` |
| older state: rollback to the previous commit | lane notes stay | the old code ignores them | none needed: they are plain comments | not tested: no code reads them there |
| shadow row missing | no opened time | first note is the first observation | durations start there; Metrics counts no first-to-merge without a merge note | `test_without_a_shadow_row_the_wait_starts_at_the_first_note` |

## Acceptance criteria

- `make check CHANGED=lib/sd_db/contributions.py,dashboard/...` passes.
- A test that fails on `origin/main` covers each of: the note, its idempotence, the backfill, the durations,
  the Queue document, the Queue DOM row, and the Metrics part.

## Risks

- Backfill reads followups of any attention on the item, not only the pull request's: a dependency's followup counts as
  on you. Accepted: a registered item with a pull request rarely has dependencies.
- Followups resolved by `acknowledge` end the on-you span at the acknowledgement, not at the fix. Accepted: that is when
  the operator answered.
- What history cannot recover: spans before the shadow first saw the pull request, attention that was never a followup
  note (CI failures before sd:1776), and any pull request whose checkpoints were pruned and whose shadow row is gone.
