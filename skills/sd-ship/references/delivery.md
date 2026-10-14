# Delivery and cancellation

Read this before claiming whole-item delivery, recording completion, or cancelling work.

## Delivery declaration

Slices are the default.
Every associated merge carries `Item: <item>`, which closes nothing.
Whole-item delivery also carries `Delivers: <item>`.
Changes without an item omit both trailers and create no placeholder row.
One PR claims one item.
Each later `--item` on `sd-ship lane enqueue` names another item it delivers: `--item A --item B --item C` claims A and closes B and C (operator ruling 2026-10-13, sd:3704).
The first `--item` is the claim and the lane's key: `lane list`, `retry`, `cancel`, `move` and `watch` name that item.
A body `Closes:` line is refused at enqueue and prepare: the `--item` list replaced it (sd:1481).
The lane passes the list to `prepare` the same way; prepare stores the closing set with the head and prints "this merge closes sd:A, sd:B, sd:C".
The merge adds `Delivers:` for each item in the set and closes it; only a `--deliver` claim closes them.
A merge whose stored set was read at another head, or a receipt prepared before sd:3704, refuses `closing_set_stale`; prepare again.
The title and commit `Delivers:` lines close nothing; builders write none, and prepare warns once about a title's ids.
An `--associate-only` claim closes nothing: a second `--item` on one stops the enqueue and the prepare (sd:3365).
Prepare and enqueue refuse an `--item` id that is no item or belongs to another repository.
An item the merge could not close returns `delivery_pending: true` with `closes_failed`; `reconcile` retries it.
A body line `Refs: sd:A, sd:B` names related or partial items; the merge adds no trailer for them and leaves them open.

The first prepare of an item names its claim, or it refuses.
Give `--deliver` to the item's last PR and `--associate-only` to each earlier PR.
A forgotten `--deliver` leaves the row open with its code on the default branch.
A branch of design records (`docs/work/`) and instruction files alone cannot `--deliver`; it associates (sd:3519).
A task or followup takes `--deliver` without an acceptance file.
Its verified merge moves it to done with the sentence `sd task status ID done --delivered-by SHA` records.
For a work item, use `prepare --deliver --acceptance-file FILE` only when every item acceptance criterion has evidence.
The JSON requires `item`, `complete: true`, and a nonempty `criteria` array.
Each criterion contains `criterion`, `passed: true`, and concrete `evidence`.
A criterion the owner waived takes `passed: false`, its `evidence`, and `waived: {"reason": TEXT, "decision": NOTE_ID}` (sd:3704); a passed row carries no `waived`.
The operator or the lead writes that note first: `sd task note N $'<ruling>\nWaive: <criterion>' --kind decision`, one `Waive:` line per criterion.
Prepare refuses a note on another item or of another kind (`waiver_refused`), a failed read (`waiver_unread`), and a note with no `Waive:` line equal to the criterion after whitespace is collapsed (`waiver_not_exact`).
The claim keeps the note's id, body and session; the delivery's completion record lists the waived criteria, and its `status_change` reason ends `; waived: N criteria (decision #ID)`.
The claim binds the item's current title, body, and artifact path.
Changed scope invalidates it.
Structural validation does not prove the completeness or meaning of human acceptance evidence.

Keep trailers contiguous in the merge message's final paragraph.
Put attribution and session links above them.
An explicit squash body preserves that ordering.
A missing delivery trailer leaves delivery unverified; do not invent completion.

## Umbrella items

An umbrella closes on a merge that names it, never on another item's merge alone (sd:3704):

- Slices carried `Item: sd:N`: run `sd work deliver N <last slice SHA> --associated --reason TEXT`.
- Another item's pull request meets its close condition: its enqueue names it with `--item N`.
- Noticed after that merge: the next `--deliver` enqueue in the repository names it with `--item N`.
- Delivered in a repository the workflow database does not register: `sd work cancel N --reason TEXT`, naming where it landed.

## Verified row completion

Record the row after the remote has confirmed the merge, not before.
Run `sd work deliver <row-id> <full-merge-commit-sha>`.
Its `sd_db.progress.deliver_work` operation checks the trailer and current remote default-branch ancestry before recording completion and `shipped_at`.
Unavailable or changing remote evidence leaves the row open.
Retry the same operation when evidence becomes available.
Do not set completion status or `shipped_at` separately.

The shared transition writes a single `status_change` note and its completion receipt in the same transaction.
On a second delivery to `done`, leave `shipped_at` where it was and add no further note.
`shipped_at` records initial delivery, not the moment of a later merge.
A slice merge writes no status; its item stays open and records the squash commit once.
With no database, the row operation is a no-op; the manual workflow refuses no merge for a missing row.

A database failure or active assignment can return `delivery_pending: true` with confirmed merge evidence.
For runner delivery, the library prepares an ancestry proof in the mutable owned clone.
The proof binds item revision, acceptance, commit, and run.
After retention, release clears its assignment and applies that proof without network access.
Changed scope, another assignment, or conflicting merge evidence rolls release back without losing the confirmed merge.
The immutable witness has no arbitrary expiry.

## Cancellation

Use `sd work cancel <row-id> --reason TEXT`.
For a task or followup, use `sd task cancel <row-id> --reason TEXT`.
The cancel writes `done` with a `cancelled` receipt and touches no file.
A cancel opens no pull request and does not wait for another merge.
A later merge associated with the cancelled item can carry `Closes: <item>` but no `Delivers:`.
`Delivers:` claims delivery; `Closes:` claims closure, so a cancel never receives the delivery trailer.
