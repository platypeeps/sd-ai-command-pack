---
title: Mirror each writing piece's files to Google Drive
created: 2026-11-02
item: sd:7243
branch: feat/sd-7243-piece-drive
---

# Design — piece-drive-mirror

The item's row holds status, progress and decisions; this page holds the shape.
Revised 2026-11-04 for the operator's scope change (note #40909), against
origin/main `0e5859c90`.

## Problem

The operator wants each writing piece's files in Google Drive, kept
current, with a link from the Writing page to each copy. The files are
`index.md` (the draft), `research.md`, `fact-check.md` and
`adversarial.md`.

The operator ruled on 2026-11-02 (note #40909):

1. The review stage creates or updates the Drive copy. No one designates.
2. Work pieces go to the work Drive. Pieces of every other realm go to the
   personal Drive. The account values stay in config.
3. Both Drives hold the same folders, Drafts and Published. A published
   piece moves to Published.
4. A dashboard link opens each Drive copy.
5. A copy updates when its source file changes, hand edits included.

The first build (three commits on this branch) mirrored a piece only
after a manual designation, `fields.publish.drive`, into `Briefs/<repo>`,
in one account. Rulings 1 to 3 replace that.

## Approach

Reuse the brief path end to end: the same queue, request, fingerprint,
receipt and drain. A piece is a producer beside `brief_docs`; its stage,
not a designation, says whether it mirrors.

1. **Stage decides (ruling 1).** `piece_docs` reads each piece that is
   not parked, at stage `review`, `ready` or `published`. Each gives one
   Drive entry per file present. Earlier stages, `declined` and parked
   pieces queue nothing, and a copy they already have stays.
2. **Folder by stage (ruling 3).** `review` and `ready` go to
   `Writing/Drafts`; `published` goes to `Writing/Published`. Both paths
   sit under My Drive in each account, and the drain creates a missing
   one, as it creates `Briefs/<repo>`.
3. **A move keeps the file (ruling 3).** A piece entry carries
   `moves: true`. `enqueue` then carries the file id across the two
   folders: `recorded` and `delivered_url` compare the identity without
   its `folder`. The request names the file and the new folder. The
   contract tells the drain to move a file that sits in another folder
   (`update_drive_file`, `add_parents` and `remove_parents`), then update
   it. Every other document keeps today's rule: a new folder drops the
   id. The account stays in the identity, so a piece that changes realm
   creates a new copy in the other Drive.
4. **Account by realm (ruling 2).** The realm is `places.realm_of` of
   the piece's repo, the rule the Writing page and Tasks already use.
   Realm `work` takes the `google.accounts.work.email` account; every
   other realm takes `google.accounts.personal.email`. Both are read by
   `realm_sweep.account`: the setting row, else the pack's machine
   config. The request carries the address as `account`; the drain
   passes it as `user_google_email`. An unread realm list or an unread
   account holds that piece, named, and queues nothing for it.
5. **Triggers.** The `sd writing` verbs that write a piece queue it
   after their write (first build), now with `publication-reconcile`,
   which moves a piece to `published`. The dashboard's Stage and Park
   writes queue it after theirs, best effort, as the verbs do.
6. **Hand edits (ruling 5).** The operator chose option A of note
   #43370. The dashboard service's tick (`service_actions`) starts
   `_piece_sweep` in a thread every 5 minutes. It runs `enqueue_pieces`
   over every piece, so only a changed file is queued. A sweep still
   running starts no second one and logs that once; the tick never
   waits on it.
7. **Dashboard link (ruling 4).** `writing_screen.document` gives each
   piece a `mirror`: its account realm, its folder, and per file the
   copy entries `publishing.document_copies` builds from the queue, the
   receipt and `fields.published`. Each gate row gets a Drive icon: a
   link to the copy, or off with the reason (queued, not mirrored at
   this stage, unknown).
8. **Contract.** The piece section says the above: stage, folders,
   account, move.

Deleted from the first build, since ruling 1 made it unneeded: the
designation on `fields.publish`, `designate_piece`, `piece_request`,
`POST /api/writing/publish`, the `_designate` split of
`designate_brief`, and the Notion copy of a piece.

Each new mechanism, and what it replaces:

- `piece_docs` and `enqueue_pieces`: no producer covers a row whose
  text lives in files. They reuse `enqueue`; nothing new is stored.
- `moves` on an entry: a new key on an existing request; it replaces
  "a new folder creates a second copy" for pieces only.
- `account` on a Drive target: a new request field. It replaces the
  drain's guess of which account to use.
- The `sd:<item>/<file>` source form: a new value of an existing field.
- `_piece_sweep` on the service tick: a new duty of an existing tick,
  ruled by the operator; it replaces nothing, as no trigger saw a hand
  edit before.

Rejected:

- **A designation per piece** (the first build): ruling 1 removed it.
- **Folders per repo, `Briefs/<repo>`**: ruling 3 names two folders,
  the same in both Drives.
- **An account per realm id** (`google.accounts.<realm>.email`): ruling 2
  sends every non-work realm to the personal Drive.
- **Local open by `vscode://` or `file://`**: as in the first design;
  the sd:7242 view icon stays the local open.

## Ruled question

How should a hand edit with no verb after it reach Drive? The operator
chose option A (note #43370): the existing service tick sweeps every 5
minutes. Rejected: option B, brief add and render, a lag of hours; and
option C, a hub cron job with a new verb, one more verb and job.

## Non-goals

- Trashing a copy: a declined, parked or deleted piece keeps its copy.
- A Notion copy of a piece.
- Publish now (`publish_drain`) for a piece: pieces drain with every
  other request, when a session sees `mirror-sync-pending`.
- A piece sent back from `review` to `drafting`: its copy stays.
- Editing a piece from the page.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Enqueue: read realm and account | none | realm list or account unread | that piece held and named; others queue; the next trigger queues it | unread realms hold the piece; unread account holds it |
| Enqueue: per file | one request and its receipt per file, under the queue lock | stop after two of four files | the next enqueue finds two `already queued` and writes two | stop after file two; rerun writes two, skips two |
| Enqueue: read file | none | a file unreadable or outside the repo | that file skipped and named; others queue | symlink out of the repo: three requests, one reason |
| Enqueue: refusal | none | linked worktree, or main off its branch | nothing queued; the line says why | files come from the registered checkout |
| Stage to published | request rewritten to `Writing/Published` with the carried file id | receipt from another account or item | no id carried; the drain adopts by its pointer, else creates | published piece carries `file`; another account carries none |
| Drain: move | Drive file's parent changed | stop after the move, before the update | the request still names the file; the next drain finds it in the folder, skips the move, updates | contract text; drain is a session |
| Drain: update, step 6 | Doc body, then receipt and item URL | contract's own table | as the contract's table; step 5 skipped for an `sd:` source | `delivered` on a piece request records the item URL |
| Verb or page write, then enqueue | the write committed | enqueue raises, or the queue is unwritable | the write's exit and answer unchanged; stderr or the answer names it | enqueue raising leaves exit 0 and stdout unchanged |
| Service tick: piece sweep | requests for changed files only | the database or a file read hangs or fails | the tick never waits; a hung sweep is logged once and blocks only later sweeps; a failed one is named and the next retries | tick test with a blocked sweep; sweep test with a failing connect |
| Account by realm: piece producer (`piece_accounts`; every verb, Stage, Park, reconcile and the sweep reach it) | none | realm list read in part: a skipped line may define `work`, and its repos would fall to personal | only a list read whole picks an account; partial, unset or unread holds every piece, named with the skipped line; the next trigger after the list is fixed queues it | a partial list holds work, other and unmatched repos and names line 1; unread and unset hold; `enqueue_pieces` with a partial list queues nothing, by item and for all |
| Account: the tick sweep (`_piece_sweep`) | none | as the piece producer: it calls `enqueue_pieces` over every piece | the same hold, named in the service log; the next sweep after the list is fixed queues it | `enqueue_pieces` with no items and a partial list queues nothing; the sweep logs every line but `unchanged` |
| Account: the verbs, Stage, Park and `publication-reconcile` | none | as the piece producer: each calls `enqueue_pieces` for its item | the same hold, named on stderr; the write stands | `enqueue_pieces` for the item with a partial list queues nothing |
| Account: briefs (`brief_docs`) | none | none of this class: a brief names no account | the drain's own account, as before | a brief request has no `account` with a realm list set |
| Account: publication claim (`sd_db.publication`) | none | none of this class: the account is the connector's profile readback, checked against the explicit configuration | another account is refused; nothing claimed | a profile with another address is refused |
| Account: realm sweep, research slides, mail draft, HOA attach | none | none of this class: each names its realm or reads its own account key, with no realm list | as each tool's own tests | `test_realm_sweep`, `test_research_slides` account tests |
| Rollback | piece requests left in the queue | an older drain ignores `account` and `moves` | it writes with its default account; a move becomes a new copy in Published | not testable here; named in Risks |

## Acceptance criteria

- [ ] `piece_docs` gives four Drive entries for a piece at `review`,
  none at `drafting`, none for a parked piece.
- [ ] A `review` piece's request names `Writing/Drafts`; a `published`
  one names `Writing/Published` and carries the file id delivered to
  Drafts.
- [ ] A work piece's request names the work account; any other
  realm's the personal account.
- [ ] A realm list not read whole (partial, unset, unread) or an unread
  account queues nothing for that piece and names why.
- [ ] `sd writing publication-reconcile` and the dashboard Stage write
  queue the piece.
- [ ] Each Details gate row draws a Drive link to a delivered copy.
- [ ] The service tick sweeps every piece each 5 minutes in a thread,
  and an unchanged file queues nothing.
- [ ] `sd-docs-lint` passes on this page; the focused suites pass.

## Risks

- A hand edit reaches the queue within 5 minutes of the sweep, then
  waits for the next drain.
- After a rollback, an older drain ignores `account` and `moves`. It
  writes with the session's default account and creates a second copy
  in Published. Accepted: the branch has not shipped, so no queue holds
  a piece request yet.
- A realm moved in Settings moves a piece to the other Drive at its next
  trigger; the old copy stays.
- Evidence: a delivered URL is tied to its file by the receipt's request
  name, `item` and `delivered_to` identity, which holds the account. A
  receipt for another item or account carries nothing.
