---
title: The lane closes the items the enqueue names on the final head, records a waived criterion, and closes an umbrella on a trailer that names it
created: 2026-10-13
item: sd:3704
---

# Design: lane evidence (sd:3704)

Write this page only when the shape needs agreement before the code.
The item's row holds status, progress and decisions; this page holds the shape.
Citations are on `origin/main` at 403abbf17.
The sd:3519 branch (`ship-fixes-3519`) adds `refuse_design_delivery` to prepare; nothing here conflicts with it.

## Status

Agreed 2026-10-13. The operator took the recommended option on each question:

- Part 1: a `--deliver` merge closes exactly the items named with `--item` on the enqueue; prepare prints that list
  and stores it with the head; titles and commit `Delivers:` lines close nothing (note #18007, which replaced the
  commit-trailer ruling #17806 after two review rounds found undone history still closing items).
- Part 2: `passed: false` plus `waived {reason, decision}`, the note on this item, listed in the delivery note
  (note #17816). Lane review then made the link exact: the note holds a `Waive:` line equal to the criterion.
- Part 3: no new close path; `delivery.md` documents the trailer paths (note #17816).
- Build order: PR A, then PR B.

## Problem

The lane closes or refuses items on the wrong evidence, in three ways.

1. **The title closes items.** With `--deliver`, every `sd:N` in the pull request title gets a `Delivers:` trailer
   and closes on merge (`source:bin/sd_ship_body.py::items_closed`, sd:3014). Merge reads the live GitHub title
   (`source:bin/sd-ship::merge`), so a title edited after review changes what closes. A branch commit's own
   `Delivers: sd:N` closes nothing: only the no-item path even reads it, as an advisory (`source:bin/sd-ship::dropped_delivery_notes`).
   In PR #366 of a consumer repo, the commits carried `Delivers: sd:3674` and `Delivers: sd:3690`, the title named
   only sd:3655, and the two stayed open until closed by hand. PR #353 is the other direction: an associate-only
   title closed sd:3331. sd:3365 fixed that case on 2026-10-11 (`test_an_associate_only_merge_closes_no_item_its_title_names`),
   so this design only keeps it fixed.
2. **A waived criterion cannot be stated.** `acceptance()` refuses any row without `passed: true`
   (`source:bin/sd-ship::acceptance`). In PR #365 of the same repo, the owner waived one criterion. The file had to say
   `passed: true` with evidence that opens "Waived, not met", so the record says a criterion passed that did not.
3. **An umbrella cannot close without a commit of its own.** `sd work deliver` needs `Delivers:` or, with
   `--associated`, `Item:` for that item on one merge (`source:lib/sd_db/progress.py::deliver_work`, `source:lib/sd_db/progress.py::deliver_associated_work`). sd:997's close
   condition was met by sd:2733's merge (#349). It still needed an extra docs commit carrying `Delivers: sd:997`.
   sd:179 and sd:364 were recorded as `cancelled` although their work had landed.

## Approach

### 1. The closing set is the enqueue's `--item` list on the final head; never the title or commit lines

Evidence the lane trusts, and why:

- **The `--item` list on the enqueue**, claimed item first. Each later `--item` names one more item the merge
  closes. The lead names it against the final head, so no history is trusted: a commit line can be undone by a
  later commit, with or without git's revert line, and two review rounds found both (note #18007).
- **`Closes:` lines in the prepared body**, as today (sd:1481). Merge reads the body stored at prepare.
- **Not the title**, which is prose a reader sees (#353), editable on GitHub after review, and read live at merge.
- **Not commit `Delivers:` lines.** Builders write none; sd-ship writes one per closed item into the squash, so
  `sd task status --delivered-by` keeps reading the landed commit.

Shape:

- `sd-ship lane enqueue --item A --item B --item C` stores `closes: [B, C]` on the entry; the runner calls
  `sd-ship prepare --item A --item B --item C`. Prepare's first `--item` is the claim; the rest are its closing set.
- Prepare checks each item as it checks a `Closes:` item (`source:bin/sd_ship_body.py::refuse_unclosable`): an item
  of this repository, and only with `--deliver`. Enqueue makes the same check (`source:bin/sd_lane.py::check_item`).
- Prepare stores `closing = {"head": <head>, "items": [...]}`, prints "this merge closes sd:A, sd:B, sd:C" and
  returns the list as `closes`. A delivering title that names other ids gets one warning line.
- **Every reader takes the stored set**: `squash_body`, `hold_at_merge`, `deliver_closes`, `close_items` and
  `reconcile`, through `co_delivered` (`source:bin/sd-ship::co_delivered`). A web merge that drops a `Delivers:`
  line still reports that item in `closes_failed`.
- **Before the merge is sent**, merge refuses `closing_set_stale` when `closing.head` is not the head being merged.
- **A receipt is read under the rule that wrote it.** One with no `closing` field refuses `closing_set_stale` before
  `merge_dispatch`; at `merge_dispatch` or later it keeps the old body-and-title reading it was sent under, and an
  associate-only one closes nothing (sd:3365).

Rejected: commit trailers (the first ruling, #17806). A trailer is history, and the final head can undo it; the
revert-line check closed only the case git writes. Rejected: title ids (sd:3014), for the reasons above.

### 2. A waived row names its reason and the decision note that waived it

Evidence the lane trusts: a `decision` note on this item that states the waiver in a `Waive:` line equal to the
row's criterion. The waiver is the owner's ruling, recorded in the workflow database where `sd task show` and the dashboard show it. Free text in the
acceptance file is written by whoever prepares, so on its own it proves nothing.

- A row is accepted when `passed` is `true`, or when `passed` is `false` and
  `waived = {"reason": "<text>", "decision": <note id>}`. `criterion` and `evidence` stay required. `evidence`
  says what was measured.
- The operator or the lead writes the note: `sd task note N $'<ruling>\nWaive: <criterion text>' --kind decision`.
  One `Waive:` line per waived criterion; a line starts with `Waive:` at column zero.
- Prepare reads the note: it must exist, have `item` equal to the claimed item and `kind = 'decision'`, and hold a
  `Waive:` line whose value equals the row's `criterion`. Both sides are compared after whitespace normalisation
  (strip, runs of whitespace to one space), exact and case-sensitive, never as a substring. The stored claim keeps
  the note's id, body and `session` with the row. A failed read refuses (unknown, not a pass).
- Refusals, each by name: a note on another item; a note of another kind; a note with no `Waive:` line equal to the
  criterion. So "Do not waive X" waives nothing (no `Waive:` line), and `Waive: p95 under 2 s` does not waive
  "p95 under 2 s on memory4k" (not equal).
- `complete: true` still means "every criterion has a row". Waived rows count as rows.
- The delivery record names the waiver in one transaction. `deliver_work(..., waived=[{criterion, decision}])` adds
  `waived` to the completion record and appends "; waived: <n> criteria (decision #<id>, ...)" to its
  `status_change` reason (`source:lib/sd_db/progress.py::_complete_delivery`). `close_task` adds the same suffix for a task.
  Merge and reconcile take the list from the stored claim.

Rejected: a reason with no decision note. That records "waived" without anything tying it to the owner.

### 3. An umbrella closes on a trailer that names it; no new close path

Evidence the lane trusts: a merged commit on the item's default branch whose trailer block names this item.
Nothing weaker. A merge that names other items does not show that it finished this one, and a reason in free text
cannot tie it. The existing paths already cover each case once part 1 lands:

- **Slices carried `Item: sd:N`.** `sd work deliver N <last slice> --associated --reason TEXT`
  (`source:lib/sd_db/progress.py::deliver_associated_work`), unchanged.
- **Another item's PR meets the close condition.** Its enqueue names the umbrella with `--item N`, or its body
  with `Closes: sd:N` (part 1). The umbrella closes on that merge.
- **Noticed after the merge.** The next `--deliver` PR in the repository names it with `--item N`. It closes with
  that PR's commit, not a commit of its own.
- **Delivered in an unregistered repository** (sd:179, sd:364): ancestry cannot be verified there, so those keep
  `sd work cancel` with a reason (non-goal).

`delivery.md` gets these four lines.
Rejected: `sd work deliver --associated` citing other items' merges (this page's first draft). It lets any
default-branch commit that names some item close any other item, and `sd-status` would still call the row
unmarked: `_receipt_gap` wants the commit to name the item (read by `source:bin/sd_lib.py::_unmarked`).
Also rejected: a new verb (`sd work resolve`), for the same reasons and one more command.

## Non-goals

- A delivery in a repository the workflow database does not register (sd:364's ai-experiments PR): ancestry
  cannot be verified there. Those keep `sd work cancel` with a reason.
- A new close path for umbrellas (part 3).
- The runner delivery proof (`source:lib/sd_db/ship.py::prepare_delivery`): the runner lease is gone (sd:3050), and nothing here
  changes that path.
- Re-checking a waiver's decision note at merge: the claim binds at prepare, as the item scope does.

## Failure table

Part 1 moves state in steps: prepare stores the set, merge sends the message, reconcile closes the items.
Part 2 writes once, in the delivery's one transaction. Part 3 changes only `delivery.md`.

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Enqueue stores `closes` | queue entry gains the list | An item is foreign, unknown, or named on an associate-only claim | Enqueue refuses; nothing is queued. | `test_a_second_item_of_another_repository_is_refused` |
| Runner calls prepare | none | An entry queued before this change has no `closes` | It prepares with the claimed item alone and prints that set; cancel it and enqueue again with every `--item`. | `test_each_item_the_enqueue_names_reaches_prepare` |
| Prepare stores `closing` | receipt gains `{head, items}` with title and body, in one save | Process stops before the save | No field stored; merge refuses `closing_set_stale` and the next prepare stores it. | `test_an_older_unsent_receipt_without_a_closing_set_refuses_the_merge` |
| Branch moves after prepare | none | Merge would close the old head's set | Merge refuses `closing_set_stale`; prepare again. | `test_a_closing_set_read_at_another_head_refuses_the_merge` |
| Older receipt at `merge_dispatch` or merged | rows move to done | No `closing`; prepare routes the phase to reconcile | The old body-and-title reading it was sent under; associate-only closes nothing. | `test_an_older_receipt_at_merge_dispatch_closes_what_its_title_named`, `test_an_older_associate_only_receipt_at_merge_dispatch_still_closes_nothing` |
| `merge_dispatch` saved, `PUT` answer lost | receipt holds `merge_message` | Response lost after GitHub merged | `reconcile` closes the stored set. | `test_a_lost_merge_response_still_closes_the_named_items` |
| Web merge or reconcile closes each item | rows move to done | The landed message dropped an item's `Delivers:`, or the row was done by hand | `delivery_pending` with `closes_failed`, from the stored set; `reconcile` retries. | `test_a_web_merge_without_the_closes_trailers_leaves_those_items_open` |
| Rollback to the previous commit | receipt keeps `closing` | Old merge ignores it and closes the title's ids; the later `--item` items stay open | Accepted: name them in the next `--deliver` PR; reopen a wrongly closed one with `sd task`. | None: old code. |
| Prepare reads the decision note | nothing yet | Database read fails | Prepare refuses; no claim stored. | Closed connection; prepare refuses. |
| Prepare matches the `Waive:` line | nothing yet | The note mentions the criterion without waiving it, or waives a shorter or longer criterion | Prepare refuses `waiver_not_exact`; no claim stored. The operator or the lead writes a note with the exact line. | Three notes on the item: "Do not waive X", `Waive: X` for a row whose criterion is "X on Y", and `Waive:  X ` for row "X"; the first two refuse, the third passes. |
| Delivery writes `waived` | completion record and note | Transaction fails | Rolls back whole; `delivery_pending`, reconcile retries with the stored claim. | Fail inside the transaction; the row stays open with no note. |

## Slices

Two pull requests. Part 1 moves state in steps, so it gets its own PR. Part 3 is four lines in `delivery.md`,
which PR A edits anyway.

1. **PR A, closing set (parts 1 and 3).** `bin/sd_ship_body.py`, `bin/sd-ship`, `bin/sd_lane.py`, `WORKFLOW.md:278`,
   `skills/sd-ship/SKILL.md:113`, `skills/sd-ship/references/delivery.md:12`, tests in
   `tests/test_sd_ship.py` and `tests/test_sd_ship_lane.py`. It leaves every machine closing only on the claim,
   `Closes:` and the enqueue's `--item` list. Estimate: 4 hours of builder time, then one or two review rounds.
2. **PR B, waived row (part 2).** `bin/sd-ship` (`acceptance`, `record_delivery`, `close_task`),
   `lib/sd_db/progress.py` (`deliver_work`, `_complete_delivery`), `delivery.md`, tests. It shares `bin/sd-ship`
   with PR A, so it starts from PR A's merge. It leaves the waiver working on every machine. Estimate: 2 hours,
   then one review round.

## Acceptance criteria

- A `--deliver` enqueue naming three items with `--item` closes all three on merge, each with a generated
  `Delivers:` line in the squash.
- An item named only in the title or a commit `Delivers:` line stays open; prepare warned about the title's ids.
- An associate-only enqueue or prepare with a second `--item` refuses `closes_need_delivery`.
- A receipt whose `closing.head` differs from the merged head, or an unsent one that lacks the field, refuses
  `closing_set_stale`.
- An acceptance file with one row `passed: false`, a reason and a decision note on the item holding
  `Waive: <criterion>` passes prepare. The delivery `status_change` note names it as waived. The same row citing
  another item's note, a note with no `Waive:` line, or a `Waive:` line that only contains or is contained in the
  criterion, refuses.
- `python3 -m unittest tests.test_sd_ship tests.test_sd_ship_lane` passes with 0 failures on each PR, and
  `make check` passes in the lane.

## Risks

- **Builders and the lead must change habits.** A batched PR that relied on title ids now leaves those items
  open, and so does one a builder named in a commit line. The prepare warning names the title's ids, and the
  printed closing set shows what closes; the lead's enqueue names every item with `--item`.
- **A waiver is only as good as the decision note.** Any session can write a `decision` note, so the check ties the
  waiver to a recorded ruling on the item with an exact `Waive:` line, not to the writer's identity; the claim
  keeps the note's `session` so a reader can see who wrote it. We accept that under the single-operator
  threat model.
- **Evidence ties.** The closing set is tied to the reviewed head (`closing.head`). The waiver is tied to the
  claimed item through `note.item` and to the row through an exact `Waive:` line. An umbrella close stays tied to the
  item through a trailer that names it.
