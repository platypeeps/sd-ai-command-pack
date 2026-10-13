---
title: The lane closes items on evidence tied to the reviewed head, records a waived criterion, and closes an umbrella on a trailer that names it
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

- Part 1: `Closes:` plus `Delivers:` trailers on the branch's own commits, stored at prepare with the head; the title
  closes nothing, and prepare warns per title id (sd:3704 note #17806).
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

### 1. The closing set comes from the claim, `Closes:` and branch-commit trailers; never the title

Evidence the lane trusts, and why:

- **The claim** (`--deliver`), as today.
- **`Closes:` lines in the prepared body**, as today (sd:1481). Merge reads the body stored at prepare, not the
  live one.
- **`Delivers: sd:N` trailers on the branch's own commits**, read at prepare from
  `git log --no-merges refs/remotes/origin/<base>..<head>` through `sd_ship_remote.git`, which raises on a failed
  call. A commit SHA cannot change, so this evidence is tied to the reviewed head. It is also where a builder writes
  "this commit delivers that item" (one commit per item). `sd_lib.commit_messages` is not used: it returns `[]`
  when git fails (`source:bin/sd_lib.py::commit_messages`), and a failed read is not an empty set.
- **Not the title.** A title is prose for a reader. It names context (#353), anyone can edit it on GitHub after
  review, and merge reads it live.

Shape:

- Prepare computes the closing set once: `Closes:` items, then branch-trailer items, minus the claimed item.
  Only `sd:<n>` trailer values count. It stores `closing = {"head": <head>, "items": [...]}` in the receipt.
  `sd_ship_body.items_closed` loses its title argument and takes the trailer list. It returns `()` without
  `deliver`, as today.
- An associate-only claim whose commits carry `Delivers:` for any item refuses with `closes_need_delivery`. A
  `Closes:` line gets the same refusal today (operator ruling 2026-10-11, sd:3365).
- `refuse_unclosable` checks the trailer items the same way it checks `Closes:` items: each must be an item in
  this repository.
- Each title `sd:N` outside the closing set gets a prepare warning: "the title names sd:N, which this merge
  leaves open; add `Closes: sd:N`, a `Delivers:` commit trailer, or `Refs:`". The squash subject still uses the live
  title (`squash_title`); only the closing role goes. Merge stops re-reading the title for closes
  (`source:bin/sd-ship::merge`).
- **Every reader takes the stored set**: `squash_body`, `hold_at_merge`, `deliver_closes`, `close_items` and
  `reconcile`, through `co_delivered` (`source:bin/sd-ship::co_delivered`). The set is fixed at prepare, so a web merge that drops
  a `Delivers:` line still reports that item in `closes_failed`, as today.
- **Before the merge is sent**, merge refuses `closing_set_stale` when `closing.head` is not the head being merged.
  The next action is "prepare again".
- **A receipt is read under the rule that wrote it.** A receipt with no `closing` field was prepared by older code.
  Before `merge_dispatch`, merge refuses it with `closing_set_stale`, and a new prepare stores the field. At
  `merge_dispatch` or later (prepare routes those to reconcile, `source:bin/sd-ship::prepare_head`), and for a web merge reconcile
  observes, `co_delivered` keeps today's reading of the stored body and title. That reading is the one the merge
  was prepared and sent under.
- `sd-ship lane enqueue` (`source:bin/sd_lane.py::check_item`) reads the same trailers from its worktree's branch.
  It refuses there instead of waiting minutes in the queue to refuse at prepare.

Rejected: `Closes:` only, with prepare refusing a commit trailer missing from `Closes:`. That has one source
fewer, but it makes the lead copy what the commits already say. Commit trailers are the stronger evidence of the
two, because a body is editable until prepare.

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
- **Another item's PR meets the close condition.** That PR names the umbrella in `Closes: sd:N`, or a branch commit
  carries `Delivers: sd:N` (part 1). The umbrella closes on that merge. sd:997's extra docs commit was needed only
  because nothing read the commit trailer, or because the condition was noticed after the merge.
- **Noticed after the merge.** The next `--deliver` PR in the repository names it in `Closes: sd:N`. It closes with
  that PR's commit: a body line, not a commit of its own.
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
| Prepare reads branch trailers | nothing yet | `git log` fails | Prepare refuses; nothing is stored, so no empty set either. A rerun reads again. | Point the range at a missing base ref so real git fails; prepare refuses and the receipt has no `closing`. |
| Prepare stores `closing` | receipt gains `{head, items}` | Process stops after the read, before the save | No field stored; the next prepare reads again. | Stop before `save`; the rerun stores the set once. |
| Branch moves after prepare | none | Merge would close the old head's set | Merge refuses `closing_set_stale`; prepare again. | Prepare at H1, add a commit carrying `Delivers:`, merge refuses. |
| Older unsent receipt reaches merge | none | No `closing` field; prepared under title closing | Merge refuses `closing_set_stale`; a new prepare stores the set and warns about title ids. | Receipt without the field in phase `ready_to_send`; merge refuses with that code. |
| Older receipt at `merge_dispatch` or merged | rows move to done | No `closing` field; prepare cannot help, it routes to reconcile | `co_delivered` keeps the old body-and-title reading for that receipt, the rule its message was sent under. | `merge_dispatch` receipt without the field whose message carries a title-derived `Delivers:`; reconcile closes it. |
| `merge_dispatch` saved, `PUT` lost | receipt holds `merge_message` | Stop between save and `PUT`, or response lost | `reconcile` reads the pull request; if merged, it closes the stored set. | Stop after the save; reconcile closes a trailer-only item. |
| Web merge or reconcile closes each item | rows move to done | One close fails (row done by hand, `Delivers:` dropped from the landed message) | `delivery_pending` with `closes_failed`, from the stored set; `reconcile` retries. | Extend `test_a_web_merge_without_the_closes_trailers_leaves_those_items_open` with a trailer-only item. |
| Rollback to the previous commit | receipt keeps `closing` | Old merge ignores it: trailer items stay open, title items close | Accepted. Name the open ones in the next `--deliver` PR's `Closes:`; reopen a wrongly closed one by hand. The new prepare already warned about each title id. | None: old code. |
| Prepare reads the decision note | nothing yet | Database read fails | Prepare refuses; no claim stored. | Closed connection; prepare refuses. |
| Prepare matches the `Waive:` line | nothing yet | The note mentions the criterion without waiving it, or waives a shorter or longer criterion | Prepare refuses `waiver_not_exact`; no claim stored. The operator or the lead writes a note with the exact line. | Three notes on the item: "Do not waive X", `Waive: X` for a row whose criterion is "X on Y", and `Waive:  X ` for row "X"; the first two refuse, the third passes. |
| Delivery writes `waived` | completion record and note | Transaction fails | Rolls back whole; `delivery_pending`, reconcile retries with the stored claim. | Fail inside the transaction; the row stays open with no note. |

## Slices

Two pull requests. Part 1 moves state in steps, so it gets its own PR. Part 3 is four lines in `delivery.md`,
which PR A edits anyway.

1. **PR A, closing set (parts 1 and 3).** `bin/sd_ship_body.py`, `bin/sd-ship`, `bin/sd_lane.py`, `WORKFLOW.md:278`,
   `skills/sd-ship/SKILL.md:113`, `skills/sd-ship/references/delivery.md:12`, tests in
   `tests/test_sd_ship.py` and `tests/test_sd_ship_lane.py`. It leaves every machine closing only on the claim,
   `Closes:` and commit trailers. Estimate: 4 hours of builder time, then one or two review rounds.
2. **PR B, waived row (part 2).** `bin/sd-ship` (`acceptance`, `record_delivery`, `close_task`),
   `lib/sd_db/progress.py` (`deliver_work`, `_complete_delivery`), `delivery.md`, tests. It shares `bin/sd-ship`
   with PR A, so it starts from PR A's merge. It leaves the waiver working on every machine. Estimate: 2 hours,
   then one review round.

## Acceptance criteria

- A `--deliver` PR whose title names sd:A, whose body has no `Closes:` and whose commits carry no `Delivers: sd:A`
  merges with no `Delivers: sd:A` and leaves sd:A open; prepare warned about it.
- A `--deliver` PR whose branch commit carries `Delivers: sd:B` closes sd:B on merge.
- An associate-only PR whose branch commit carries `Delivers: sd:B` refuses `closes_need_delivery`.
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
  open. The prepare warning names each one; the lead's bundle brief names `Closes:` or commit trailers. We accept
  one cycle of warnings.
- **A stray `Delivers:` on a branch commit closes an item.** That is the intent, but a copied commit message can
  carry one. The prepare result lists the closing set, and `refuse_unclosable` keeps it to this repository.
- **A waiver is only as good as the decision note.** Any session can write a `decision` note, so the check ties the
  waiver to a recorded ruling on the item with an exact `Waive:` line, not to the writer's identity; the claim
  keeps the note's `session` so a reader can see who wrote it. We accept that under the single-operator
  threat model.
- **Evidence ties.** The closing set is tied to the reviewed head (`closing.head`). The waiver is tied to the
  claimed item through `note.item` and to the row through an exact `Waive:` line. An umbrella close stays tied to the
  item through a trailer that names it.
