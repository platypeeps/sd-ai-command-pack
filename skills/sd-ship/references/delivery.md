# Delivery and cancellation

Read this before claiming whole-item delivery, recording completion, or cancelling work.

## Delivery declaration

Slices are the default.
Every associated merge carries `Item: <item>`, which closes nothing.
Whole-item delivery also carries `Delivers: <item>`.
Changes without an item omit both trailers and create no placeholder row.

Use `prepare --deliver --acceptance-file FILE` only when every item acceptance criterion has evidence.
The JSON requires `item`, `complete: true`, and a nonempty `criteria` array.
Each criterion contains `criterion`, `passed: true`, and concrete `evidence`.
The claim binds the item's current title, body, and artifact path.
Changed scope invalidates it.
Structural validation does not prove the completeness or meaning of human acceptance evidence.

Keep trailers contiguous in the merge message's final paragraph.
Put attribution and session links above them.
An explicit squash body preserves that ordering.
A missing delivery trailer leaves delivery unverified; do not invent completion.

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
The cancel writes `done` with a `cancelled` receipt and touches no file.
A cancel opens no pull request and does not wait for another merge.
A later merge associated with the cancelled item can carry `Closes: <item>` but no `Delivers:`.
`Delivers:` claims delivery; `Closes:` claims closure, so a cancel never receives the delivery trailer.
