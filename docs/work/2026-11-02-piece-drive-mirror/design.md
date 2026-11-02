---
title: Mirror each writing piece's files to Google Drive
created: 2026-11-02
item: sd:7243
branch: feat/sd-7243-piece-drive
---

# Design — piece-drive-mirror

The item's row holds status, progress and decisions; this page holds the shape.
Written against origin/main `72cba5043`.

## Problem

The operator asked on 2026-11-02 for two icons on each file of a writing
piece in the Writing page's Details gate rows: one opens the local file,
one opens its Google Drive copy. The files are `index.md` (the draft),
`research.md`, `fact-check.md` and `adversarial.md`. The Drive copy is a
mirror kept current.

Today no piece reaches Drive. The publication contract
(`skills/_shared/references/publication-contract.md`) has two producers:
`research.conf.py` entries, and routine briefs
(`source:bin/sd_research_publish.py::brief_docs`), designated on their item's
`fields.publish` and queued again on each brief render. A piece has no
`research.conf.py` entry and no render, so nothing queues it, and nothing
would queue it again after an edit (note #40798).

Pages open local files today only through `obsidian://open` links, for
vault copies (`published()` in `commands.js`, `markup._obsidian_reads`). The pack
sd:7242 bundle adds a view icon to each gate row: it reads the report
through `GET /api/writing/<item>/<gate>` and shows it read only in the
editor's evidence pane; Draft's opens the whole draft.

## Approach

Reuse the brief path end to end: the same designation key, queue,
request, fingerprint, receipt and drain. Add one producer beside
`brief_docs`, one trigger, one dashboard control and the icons.

1. **Designation.** A piece is designated on its item, as a brief is:
   `fields.publish.drive` (and `notion`, which the producer reads for free
   but the page does not offer). One designation covers all four files.
   Nothing is inferred: an undesignated piece queues nothing.
2. **Producer.** `piece_docs(connection, items)` beside `brief_docs`
   reads every `kind = 'idea'` row with a `piece` and a `fields.publish`,
   and gives one DOCS entry per file present:
   - `out`: `<year>-<slug>-<stem>`, with stem `draft`, `research`,
     `fact-check` or `adversarial`. The request is
     `<key>.<out>.drive.json`, as for any document.
   - `title`: `<piece title> · <stem>`.
   - `content`: the file's text, read from the registered checkout,
     never a linked worktree's. A file outside the repository is skipped
     and named, as `piece_files` does.
   - `source`: `sd:<item>/<file>`, such as `sd:7001/research.md`.
   - `item`: the piece's item, so drain step 6 records each URL there as
     `fields.published["<repo>::<out>"]`.

   An entry carrying `content` already takes the brief's route through
   `mirror_request` and `delivered_url`: no `rendered` path, the URL
   carried from the receipt in the same container, no step 5.
   `mirror_request` takes `source` from the entry when it names one, and
   writes no vault path for it. `enqueue_pieces(connection, items)` is
   `enqueue_briefs`' loop over `piece_docs`, sharing its read of each
   repo's channels setting. Through `enqueue`, it keeps every rule a
   render has: the main checkout on its default branch only, the
   `already_queued` digest check, the queue lock and `SD_MIRROR_DRY_RUN`.
3. **Re-queue trigger: the `sd writing` verbs.** After a write verb
   on a piece succeeds (`promote`, `register`, `stage`, `metadata`,
   `gate`, `park`, `adversarial`, `reconcile`), `bin/sd_writing.py`
   calls `enqueue_pieces(connection, {item})` and prints its lines on
   stderr. It never fails the verb, as `sd_controls._mirror_briefs`
   never fails a brief add. The digest check queues only the files whose
   text changed. An undesignated piece costs one row read.
4. **Dashboard control.** One Writing command, `piece.mirror`, "Mirror to
   Drive", posts `POST /api/writing/publish` `{item, channel}`. It runs
   `designate_brief`'s three steps for a piece: the channels setting
   must allow Drive, `fields.publish.drive` becomes `{}` in one
   transaction unless it is there, then `enqueue_pieces(connection,
   {item})`. It is idempotent, so on a designated piece it reads
   "Mirror again" and queues whatever changed since: the manual answer
   for a hand edit that no verb followed.
5. **Icons.** `writing_screen.document` gives each piece a `mirror`:
   the designation, and per file the copy entry
   `publishing.document_copies` already builds from the queue, the
   receipt and `fields.published`. Each gate row gets a Drive icon,
   drawn as the Documents and Briefs rows draw theirs (`published()` in
   `commands.js`): a link to the copy, `queued`, `missing` or `off`.
6. **Local open: the sd:7242 view icon, unchanged.** It opens the file
   read only through an existing route, works from any device, and sends
   no local path to the page. `writing_screen` holds that rule: "the
   repository goes out by its folder name only, so no local path
   leaves."
7. **Contract.** A section "A writing piece is designated on its item"
   beside the brief's. Step 5 changes from "a routine brief's request
   (`source` `sd:<item>`)" to "a request whose `source` is an item
   (`sd:<item>` or `sd:<item>/<file>`)". It also states that a piece
   never mirrors into `sdw.drive_publishing_folder`, the blog's gate.

Each new mechanism, and what it replaces:

- `piece_docs` and `enqueue_pieces`: no producer covers a row whose text
  lives in files. They reuse `enqueue`; nothing new is stored.
- The `sd:<item>/<file>` source form: a new value of an existing field.
  The drain needs it to skip step 5, since no `research.conf.py` exists.
- The verb trigger: no new command, five lines in an existing one.
- `POST /api/writing/publish`: the Writing page's write. It mirrors
  `/api/briefs/publish`, whose checks refuse a non-brief. Reusing that
  route would put a Writing control behind a Briefs refusal.
- `piece.mirror` and the `mirror` field: one command and one read field.

Rejected:

- **Re-queue in the drain's own digest check.** It is smaller (one call
  in the drain's first step, as `sd-research-kit project` runs there),
  but a drain runs only when the queue already holds a request
  (`mirror-sync-pending`, Publish now). With the queue empty, an edited
  piece would never trigger it, and the copy stays stale for good. The
  verbs follow every step of the writing skills.
- **Local open by `vscode://file/<path>`.** It opens the file editable,
  but only in a browser on the machine whose disk holds that path. It
  also sends the absolute path to the page against `writing_screen`'s
  rule. `file://` fails: Chrome refuses a `file://` link from an http
  page. `obsidian://open` opens only a file inside the vault, and
  content repos are not.
- **A Drive folder per piece.** The drain resolves only `Briefs/<repo>`
  or one named folder. The four docs land flat in `Briefs/<repo>`,
  grouped by their title prefix. A repo's channels setting can name
  another folder for the whole repo.

## Non-goals

- Untick. Dropping a piece's designation and trashing its four copies
  is a follow-up item. Until then no control drops it: `sd task edit`
  writes no `fields`.
- Publish now for a piece (`publish_drain`). Pieces drain with every
  other request, when a session sees `mirror-sync-pending`.
- A Notion choice on the page. The producer queues `notion` when the
  item names it.
- A re-queue on the dashboard's Stage and Park writes. Stage changes a
  file only in a `file`-owned repo; Park moves the folder, and `source`
  does not change with it. The next verb or "Mirror again" catches both.
- Trashing the copy of a deleted report. Its request and copy stay.
- Editing a piece from the page.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Mirror: designate | `fields.publish.drive` set in one transaction | the enqueue after it raises or the pack lacks `enqueue_pieces` | the designation stays; the answer says nothing was queued; the next verb or a second click queues | designation kept and `queued: false`, then a second call queues |
| Mirror: designate | none | channels setting unread, or Drive left out | refused before the write; nothing designated | refusal names the cause; `fields` unchanged |
| Enqueue: per file | one request and its receipt per file, under the queue lock | stop after two of four files | the next enqueue finds those two `already queued` and writes the other two | stop after file two; rerun writes two, skips two |
| Enqueue: read | none | a file unreadable, or a symlink out of the repo | that file is skipped and named; the others queue | unreadable `research.md`: three requests and one reason |
| Enqueue: refusal | none | linked worktree, or the main checkout off its default branch | nothing queued; the line says why; the next verb on the default branch queues | worktree verb queues nothing and prints the refusal |
| Enqueue: setting | none | that repo's channels setting unread | that repo's pieces held, named; others queue | unread setting holds the repo |
| Verb, then enqueue | the verb's write committed | enqueue raises, or the queue is unwritable | the verb's exit and JSON are unchanged; stderr names it; the next verb queues | enqueue raising leaves exit 0 and stdout unchanged |
| Drain step 3 to 6 | Drive doc, then receipt and item URL | contract's own table | as the contract's table; step 5 skipped for an `sd:` source | `delivered` on a piece request records the item URL |
| Next generation | request rewritten with the carried `file` id | receipt from another container or item | `delivered_url` carries nothing; the drain adopts by its pointer | changed draft carries `file=` from a receipt in the same container only |
| Rollback | piece requests left in the queue | an older drain reads the old step 5 and tries `research.conf.py` | step 5 fails, so the old contract says report and stop; the request stays with its id | not testable here; named in Risks |

## Acceptance criteria

- [ ] `piece_docs` gives four entries for a designated piece with four
  files, three without `adversarial.md`, and none undesignated.
- [ ] `enqueue_pieces` writes `<key>.<year>-<slug>-draft.drive.json`
  carrying the file's text, `source` `sd:<n>/index.md`, `item` `<n>`,
  and no `rendered` or vault path.
- [ ] A second `enqueue_pieces` with no edit queues nothing; one after a
  draft edit queues only the draft.
- [ ] `sd writing gate` on a designated piece queues its changed files;
  on an undesignated piece it writes nothing to the queue.
- [ ] `POST /api/writing/publish` designates and queues; a second post
  writes no second designation.
- [ ] `/api/writing` gives each piece's `mirror`; each Details gate row
  draws a Drive icon that links to the copy when one is delivered.
- [ ] `sd-docs-lint` passes on this page; the focused suites pass.

## Risks

- A hand edit with no verb after it leaves the Drive copy stale until
  the next verb or "Mirror again". The page shows the copy as current,
  since it reads the receipt, not the file. Accepted: a digest per poll
  of every piece is more than the page should do.
- After a rollback to a pack without this change, a drain session on the
  old contract may try step 5 on a piece request. Step 5's failure rule
  leaves the request with its id, so no copy is lost or doubled.
- A research document named `<year>-<slug>-<stem>` in a writing repo
  would share a request slot. `mirror_identity` compares the document
  name and repo, so the two would overwrite each other's request.
  Accepted: no writing repo has a `research.conf.py`.
- Evidence: a delivered URL is tied to its file by the receipt's request
  name, `item` and `delivered_to` container. A receipt for another item
  or container carries nothing.
