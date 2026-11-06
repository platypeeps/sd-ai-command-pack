---
title: Queue shows an item waiting on its PR, and Metrics times the wait
created: 2026-11-06
item: sd:7859
branch: feat/sd-7859-pr-wait
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
A pull request `sd-ship prepare` opened is linked the same way from its ship receipt (ruling, note #46009).

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
   `contribution_sync.note_lanes`, which each shadow sync runs, calls `record_lanes` for every registered pull request,
   so an item no longer observed (merged, done) is backfilled too.
3. **Durations.** `contributions.pr_waits(connection, now=)` reads the lane notes, oldest first.
   The time between a note and the next goes to its lane: `awaiting_you` and `newly_unblocked` are on you,
   `awaiting_them` is on reviewers; `merged` and `closed` end the wait. An open pull request counts to `now`.
   Only a note whose state is `open` counts: attention on a closed or merged pull request waits on no one.
   First PR to merge runs from the first note to the first `merged` one.
4. **Queue.** `/api/queue` gains `prs`: each item with an open pull request in a waiting lane,
   unless the item has a merging, next or blocked lane row, which keeps its lane state.
   Today's Queue view draws it as a `blocked` row, `blocked: PR · on you` or `on reviewers`, with how long it waited,
   and drops that item's live-session row and its suggested or open row. Build runs and runner assignments stay:
   they are a live process.
5. **Link.** `contributions.link_shipped` reads each `ship:` receipt's item and `pull_request.url` and sets that url as
   the item's `pull_url` through `configure`, in its one transaction, which notes the lane too.
   `note_lanes` calls it before `record_lanes`, so new pull requests and the open receipts from before
   this change are linked by the same pass. The operator's pull request is already observed as authored.
   It links every kind `sd-ship --deliver` closes, work, task and followup (`contributions.KINDS`, which a test ties
   to sd-ship's `DELIVERING_KINDS`), so `configure`, `_registered` and the projection take those kinds too: one list,
   not a second item-to-PR link read from receipts beside the contribution one.
   Left alone: a merged receipt, a done item, an item of another kind (an idea rides a pull request only as an
   associated slice), an item that names a pull request or issue, and a url another item holds
   (a bundle's second item). A `prepared` lane entry, where a manual-merge lane stops for a person's review, no longer
   hides the wait: Queue draws one row that leads with `blocked: PR` and keeps Retry and Approve.
   A merging or next entry, as an auto-merge lane's is, keeps its lane row.
6. **Metrics.** `/api/metrics` gains `prs`: totals on you, on reviewers, waiting, and first PR to merge,
   and the five slowest items. The Metrics page draws it as one ledger table, as it draws the lanes.

`comment` is the note kind. `status_change` is `transition`'s alone and feeds status ages;
`followup` is open work that Needs you lists; `decision`, `question`, `proposal` and `exec` mean other things.
`configure` already records contribution changes as a `comment`.

Rejected: a lane-history table (the brief forbids a new store), and keeping history in checkpoints (prune removes them).
Rejected: deriving durations at read time from followups alone: the on-reviewers spans and the open time need the shadow,
and a read that joins three sources every page load is slower and drifts from what was recorded.

## Non-goals

- No new command, flag, table or setting. No change to how lanes are computed.
- No GitHub read: the observer already reads GitHub.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| observe writes checkpoint, then lane note | checkpoint row and one note | process stops between the two | both are in one transaction: neither lands; the next observation writes both | `test_a_failed_lane_note_rolls_back_the_observation` |
| note a lane beside observe, configure or acknowledge | the write and one note | the note fails on its row's data (`ROW_ERRORS`) | the note alone rolls back; the write stands; the sync's lane pass retries and says it | `test_a_lane_note_that_fails_on_its_data_does_not_roll_back_the_observation` |
| backfill notes, then the current lane note | several notes for one item | process stops mid-backfill | one transaction per item; nothing lands, the next refresh backfills again | `test_a_backfill_that_fails_writes_no_note` |
| rerun of observe or refresh | none | a second note for the same lane | `record_lane` compares with the newest note for the url and writes nothing | `test_an_observed_pull_writes_one_lane_note_and_a_rerun_writes_none` |
| acknowledge moves attention | checkpoint, then lane note | lane changes on you to on reviewers without a note | `acknowledge` notes the lane in its transaction | `test_a_maintainer_comment_is_on_you_and_acknowledging_it_is_on_reviewers_again` |
| older state: item configured before this change | no lane notes | durations read nothing | the sync's `note_lanes` calls `record_lanes`, which backfills from shadow and followups | `test_backfill_reads_the_shadow_and_the_followups` |
| link a receipt's pull request | item metadata, a comment, a lane note | process stops mid-pass | one transaction per item; a rerun skips linked items and links the rest | `test_a_pull_request_prepare_opened_is_linked_to_its_item_and_noted_on_reviewers` |
| link a receipt whose item is work or a followup | item metadata, a comment, a lane note | the item never waits on its pull request | `KINDS` holds every delivering kind; a test fails when it and sd-ship's `DELIVERING_KINDS` differ | `test_every_kind_the_lane_delivers_is_linked_and_waits_on_its_pull_request` |
| per-row loop: receipts in `link_shipped` | none for a bad receipt | `ship.read` or `_url` rejects it, its `pull_request` is no object, or `configure` refuses | said as `ship receipt <key>: <error>` and skipped; the rest are linked | `test_a_corrupt_receipt_is_reported_and_the_good_one_is_still_linked`, `test_bad_receipts_are_said_and_the_good_one_is_linked_and_noted` |
| per-row loop: items in `record_lanes` | none for a bad item | `record_lane` raises for one item | said as `item <n>: <error>` and skipped; the rest are noted | `test_one_item_that_fails_its_lane_note_is_reported_and_the_rest_are_noted` |
| per-row loop: registered items in both passes and in `acknowledge` | none | one item's contribution metadata is malformed | said and skipped by both passes (`_registered(errors=)`); `acknowledge` skips it and keeps the operator's acknowledgement | `test_an_item_with_malformed_metadata_is_reported_and_stops_neither_pass`, `test_an_unrelated_malformed_item_does_not_roll_back_an_acknowledgement` |
| per-row loop: backfill events in `_history` | backfilled notes | a shadow or followup time names no zone | that event is skipped; a comment on the item names each skipped time | `test_a_backfill_event_with_no_zone_is_skipped_and_said_on_the_item` |
| the sync runs `note_lanes` | as above | a pass raises anything | said in the sync's `lanes`; the other pass still runs | `test_a_pass_that_raises_anything_is_said_and_the_other_pass_still_runs` |
| read loop: `pr_waits` | none | a malformed item or note | the read fails as a whole; Queue and Metrics say it was not read | `test_a_pr_wait_read_that_failed_says_so_and_shows_no_rows` |
| a lane problem in a sync | none | a bad receipt every run | said in `lanes` and the report; the sync stays ok, the watermark moves, the heartbeat is ok | `test_a_bad_receipt_fails_no_sync_and_holds_no_watermark` |
| older state: open receipts from before this change | no item link | their waits never show | the first sync links them | `test_bad_receipts_are_said_and_the_good_one_is_linked_and_noted` |
| older state: rollback to the previous commit | lane notes and links stay | the old code ignores the notes | none needed: notes are plain comments; a linked item is an ordinary contribution there | not tested: no code reads the notes there |
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
