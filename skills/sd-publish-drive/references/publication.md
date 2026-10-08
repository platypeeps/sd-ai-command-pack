# Resumable Drive publication

`pack.py pieces preflight` renders final HTML with embedded images from the
current draft and attached approved tip. It does not read an old publication
artifact. `--out <scratch dir>/preview.html` produces a reviewable preview, including when
the editorial gates are not yet clear. `--claim` requires a ready, unparked,
database-owned piece with current passing gate records and the ready digest.
No command in this protocol makes a network call: the attended agent executes
only the concrete connector action dispatched once by the database.

## Prepare the destination and claim

Read these current machine configuration values through `sd config get`:
`sdw.google_account`, `sdw.drive_writing_folder`, and
`sdw.drive_publishing_folder`. Missing values block publication. Use the
available `google_drive_get_profile` and `google_drive_get_file_metadata`
connectors to read the account and each configured folder. They must return
the configured email and native folders named `Drafts` and `Published`.
Never guess IDs or substitute folders.

Save the unmodified connector results in a JSON context file:

```json
{
  "expected": {"account": "configured email", "drafts": "configured ID", "published": "configured ID"},
  "profile": {"email": "connector returned email"},
  "drafts": {"id": "connector returned ID", "title": "Drafts", "mime_type": "application/vnd.google-apps.folder"},
  "published": {"id": "connector returned ID", "title": "Published", "mime_type": "application/vnd.google-apps.folder"}
}
```

These are response shapes, not values to invent. Full `structuredContent`
wrappers are accepted too. Refresh the context from the actual connector
before every external operation; do not reuse old account or folder evidence.

The CLI trusts the attended executor to capture genuine connector responses.
It validates their fields and content, but cannot authenticate them to Google.
Recorded hashes detect changed evidence; they do not provide provider attestation.
Do not invent, selectively truncate, or rewrite context, receipts, or readbacks.

```text
pack.py pieces preflight --piece YEAR/SLUG --claim --context-file CONTEXT.json --json
pack.py pieces publication-status --piece YEAR/SLUG --claim CLAIM --out /new/claim.html --json
```

The immutable claim stores full SHA256 hashes for source files, assets, and
payload. Its large embedded HTML stays in a dedicated database table, outside
ordinary task reads. One active claim per piece is enforced by a unique
database constraint. Stage, review-record, tip and metadata changes refuse
while it is active. Source edits invalidate the next dispatch. This check does
not lock source files or bind a connector's future filesystem reads.

## Execute once, then read back

Confirm the concrete piece, word count, tip, final HTML, account and Published
folder with the user before the external push. Existing authorization for that
exact artifact and destination remains valid. The final move is the action
that hands the piece to the primary blog; staging alone is not publication.

```text
pack.py pieces publish --piece YEAR/SLUG --claim CLAIM --html /new/claim.html --context-file CONTEXT.json --confirmed --json
```

Execute the returned `action` only when `execute` is `true`, exactly once.
The first action is the available `google_drive_import_document` connector,
with `source_file` the returned claim upload and `upload_mode: native_google_docs`.
Before dispatch, the CLI compares `--html` with the immutable claim bytes.
It stages those claim bytes under
`~/.local/share/sd/publication-uploads/CLAIM/claim.html`, outside the strict journal.
The claim directory is private (`0700`); the HTML file is read-only (`0400`).
The CLI refuses changed or unsafe existing artifacts and never overwrites them.
Use the returned path verbatim. Editing the original export cannot change that copy.

This protects against accidental export edits, not a hostile process using the same OS account.
That account can change permissions or replace files after validation.
The path-only connector cannot bind its future read to a checked file descriptor or hash.
Initial Drive creation occurs before native readback; readback cannot undo that creation.
Complete content and visual checks still protect the later Published move.

The connector imports into My Drive with a unique claim title. Its actual
schema cannot set appProperties or choose an import parent, so this protocol
does not pretend it can create in Drafts or update a native Doc from HTML.
It never imports directly into Published.

Save the returned connector object and record it without editing its values:

```text
pack.py pieces publication-receipt --piece YEAR/SLUG --claim CLAIM --operation OPERATION --receipt-file RESPONSE.json --json
```

Then read both `google_drive_get_file_metadata(fileId=ID)` and
`google_drive_get_document(document_id=ID)` with the complete native document,
not text-only or field-truncated output. Save them as `metadata` and `document`
in one evidence JSON file and run:

```text
pack.py pieces reconcile --piece YEAR/SLUG --claim CLAIM --context-file CONTEXT.json --evidence-file EVIDENCE.json --json
```

The native readback must match the full normalized visible text, link set,
image count and image positions relative to prose. Every referenced inline
image must have a content URI and valid dimensions matching its aspect ratio.
Captions are part of the compared text. Google may transcode images, so these
checks do not assert byte identity: compare the rendered destination images
visually against the source before the final move. Missing or rearranged
figures, extra tabs, omitted body content and unresolved readbacks block it.

Once verified, the next confirmed `pieces publish` dispatches only
`google_drive_update_file`: the exact claimed file ID, final title,
`addParents` the claimed Published ID, and `removeParents` the observed prior
parent IDs. This move does not require `--html` or read the staged import file.
Keep missing or changed import artifacts preserved; they do not block the move.
The database still verifies the claimed sources, content readback, account and destination.
It never writes native content again. Record that response, then
repeat the complete metadata/document readback and `pieces reconcile`.
Only this final proof atomically records `published_urls.gdrive`, the published
stage/date, and its database receipt. The sole observed parent must be the
configured Published folder. Neither an import success nor a move success is
accepted as proof of completion.

## Interrupted operations

A repeated dispatch returns `execute: false` and read-only recovery actions.
Never replay the earlier write merely because its caller lost the response.

- Lost claim ID: run `pieces get --piece YEAR/SLUG --json`. Read the active
  claim's `id` from `writing.publications`, then inspect that claim with
  `pieces publication-status --piece YEAR/SLUG --claim CLAIM --json`.
- Missing HTML export: run `pieces publication-status --piece YEAR/SLUG
  --claim CLAIM --out /new/claim.html`, then use that new `--html` path.
  This exports the same claim; it does not authorize another import.
  Import phases refuse changed staged uploads and preserve them for inspection.
  After verified native readback, the move needs neither import file.
- Lost import: run the exact claim-title search returned by the CLI and read
  every result page. Save the complete response pages as `search_pages` in
  the evidence JSON. One exact native candidate is adopted by ID. Zero or
  multiple candidates remain uncertain; an empty result never authorizes a
  second import, because Drive search visibility may lag a completed write.
- Lost move: read the exact document ID and reconcile actual parents/content.
  Never automatically move, rename, delete, or recreate based on a timeout.
- A never-dispatched claim can be released with `publication-abandon --reason
  TEXT`. After dispatch, `--leave` additionally acknowledges an external
  document may exist; it leaves that document untouched and blocks a fresh
  claim until the uncertainty is resolved.
- A partial staged upload remains preserved and refused. Inspect the claim
  with `pieces publication-status --piece YEAR/SLUG --claim CLAIM --json`.
  If its phase is `claimed` and `pending` is null, no dispatch was recorded.
  Release it with `pieces publication-abandon --piece YEAR/SLUG --claim CLAIM
  --reason "Interrupted staging; partial artifact preserved"`, then create a
  new claim through `pieces preflight --piece YEAR/SLUG --claim --context-file
  /current/context.json`. Export that new claim to a fresh path before dispatch.
  Keep the earlier stage for inspection. For any later phase or pending
  operation, use the existing reconciliation steps instead of a fresh import.
- An unresolved database restore holds publication. Do not infer that an old
  snapshot's missing URL proves nothing was published after the snapshot.

Derived transport copies under `~/.local/share/sd/publication-uploads/` remain
on disk by default, including completed and abandoned claims. No automatic
cleanup runs. The backed-up publication claim and journal retain the canonical
payload; transport copies do not replace that evidence.

The publisher also writes `<database-parent>/publications/`: immutable claim
payloads and append-only, hash-chained operation events, flushed to disk before
external dispatch and before recording a response in SQLite. Its catalog
detects missing claim directories; corrupt or missing evidence refuses the
next publication. Back up this directory with the database, but never roll it
back when restoring an older database snapshot. It records external effects,
not a second authority for ordinary workflow progress.

After the general restore is reconciled, `pieces publication-recover --piece
YEAR/SLUG --json` restores newer claim evidence from that journal. Follow its
exact-ID native readbacks to settle the destination. A move proved completed
after the source changed records the earlier version's real publication URL
and receipt, while leaving the current draft at review with no ready digest.
It never falsely marks that changed draft published. An explicitly abandoned
uncertain claim can be resumed by its `pieces reconcile` readbacks; no document
is deleted to resolve bookkeeping.

If a first journal initialization or a never-dispatched claim creation was
interrupted, `publication-recover --repair-incomplete` is the explicit repair.
It accepts only a creation prefix with no database claim, no registered
catalog entry, no later operation event and no restore history. It preserves
all partial bytes under `publication-recovery-evidence/` before rebuilding the
unused prefix. A possibly dispatched event remains held for actual destination
reconciliation; this repair never interprets a missing response as absence.
An incomplete backup merge leaves
`<database-parent>/publication-restore-intent.json`; its presence blocks both
publication and prefix repair. Resume that recorded restore to complete its
validated journal merge. Never remove the intent to bypass the hold.

The publisher never deletes or changes sharing. The later live primary-blog URL,
vault idea/tip updates and optional personal-blog adaptation keep their existing
separate workflow.

Google's documented upload conversion, native document structure and parent
move APIs underpin these connector capabilities:
[uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads),
[documents](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents),
[folders](https://developers.google.com/workspace/drive/api/guides/folder).
