---
title: Channels, outbound first - one channel setting per repo, and the published URL reaches the item
created: 2026-10-13
item: sd:3471
---

# Design: channels, outbound first (sd:3471)

Write this page only when the shape needs agreement before the code.
The item's row holds status, progress and decisions; this page holds the shape.

## Terms

- **Channel**: a place a repo's work goes to (outbound) or comes from (inbound): Obsidian, Notion, Drive; later Jira,
  GitHub issues, feeds, Reddit, email, Slack.
- **Channel setting**: the `channels` column on a repo's row in the workflow database. It says which publish channels
  the repo uses, and the folder each one writes to.
- **Brief** names three things today. A research-kit brief is a document published to `Briefs/<repo>/`.
  A routine brief is a vault note the scheduled routines write in their vault briefs folder; the dashboard's
  Briefs page reads these. A brief digest is the mail `obsidian-review` sends with the `Brief:` subject prefix.
  This page means the first unless it says otherwise.

## Rulings this design follows

All are operator rulings on the items named; they bind this design.

- Obsidian is a publication target and knowledge base only; tracking lives in sd (sd:3462, 2026-10-12).
- Channels are choosable per repo: Notion, email, Obsidian, Drive, GitHub issues, Jira, Slack; social later (same note).
- Outbound first: Notion, Obsidian and Drive publish with a folder each and a receipt URL. Inbound and briefs follow
  (sd:3471, 2026-10-13).
- Each repo's publish channels live in the workflow database, as a `channels` setting on the repo row, set by an
  `sd-db repo` verb and by the dashboard; not in `sd-plugin.json`. Dashboard edits write the row directly
  (sd:3471, 2026-10-13, superseding that day's earlier `sd-plugin.json` ruling).
- Each document still opts in to an outward mirror; the repo setting says where only (sd:3471 Q1, 2026-10-13).
- The dashboard edits a repo's publish channels from a repo-settings form (sd:3471 Q2, 2026-10-13).
- Notion is the work communication channel. The work space's experiments dashboard is a projection sd fills, and is
  the first outbound target to keep working (sd:3471, 2026-10-12).
- Inbound feeds: one general RSS/Atom subscription, no per-site code. Reddit is a channel both ways. X stays on a
  small posting quota. GitHub issues inbound means repos outside the managed list; managed repos still use no
  GitHub issues (sd:3471, 2026-10-12).
- Inbound Jira and GitHub issues show the ones assigned to or reported by the operator, not watched ones
  (sd:3461, 2026-10-13).

The first two rulings amend the publication contract (`skills/_shared/references/publication-contract.md`).
It says a document lives in Obsidian and is always written there. Under the rulings, the document is the Markdown in
its repo; Obsidian is one channel among the others, on by default, and a repo may turn it off. C2 edits the contract.

## Problem

Where a document is published is set per document and per machine, never per repo.
A research repo's `research.conf.py` designates each document with `notion=` or `drive=`, and three environment
variables (`OBSIDIAN_VAULT`, `SD_NOTION_PRIVATE_FOLDER`, `SD_NOTION_TEAM_FOLDER`) fix the containers.
The vault folder is always `Briefs/<repo>` and the Drive default always `Briefs/<repo>`.
A repo that wants its briefs elsewhere repeats `folder=` on every entry, and cannot move its vault copies at all.

The published URL never reaches the item. sd:3514 made `sd-research-kit delivered --url` put the URL and the
request's `item` on the receipt beside the queue, but nothing reads that receipt for an item, and no document names
an item yet (0 of 43 receipts carry a URL on 2026-10-13). The dashboard's item view cannot link a published brief
(sd:3465). Writing pieces are better off: `publication_claim.state` and `fields.writing.published_urls` hold their
URLs, but the dashboard shows only the claim id.

The 2026-10-12 review proposed a `MIRRORS` dict in `research.conf.py` for per-repo folders (B2d F6). It was never
built: no file in the pack or in a research repo defines it. This design drops that proposal; nothing is deleted
because nothing was written.

## Approach

### The channel setting

One nullable column on the `repo` row, beside `runner_merge`, `ci` and `lane_host`. It holds a JSON object:

```json
{"obsidian": {"folder": "Briefs/example-research"}, "notion": {"folder": "Example"}, "drive": {}}
```

- **Schema.** Migration `029_repo_channels.sql`:
  `ALTER TABLE repo ADD COLUMN channels TEXT CHECK (channels IS NULL OR json_valid(channels))`, and
  `SCHEMA_VERSION` becomes 29. `ADD COLUMN` for 016's and 024's reason: SQLite adds a nullable column in place, moves
  no row and touches no other table. Every row reads NULL, which means "no setting": today's behaviour. The file
  carries its reverse in a comment, as 024 does, run by hand with the dashboard, the runner and `sd-db serve`
  stopped: `BEGIN; ALTER TABLE repo DROP COLUMN channels; PRAGMA user_version = 28; COMMIT;`.
- **Backup.** `migrate` takes no backup itself; the operator runs it after one, with the dashboard, the runner and
  `sd-db serve` stopped (`lib/sd_db/migrate.py`). The C1 sitting is: `bin/sd-db backup` (it proves the copy), then
  `bin/sd-db migrate`, then restart the three. A pre-29 snapshot still restores: the restore path migrates it, and
  every `channels` reads NULL until set again (failure table, row "restore").
- **Closed vocabulary**, checked by one validator, `sd_db.channels.validate`, before any write: keys `obsidian`,
  `notion`, `drive`; each value an object holding `folder` or nothing; `{}` means the channel's default folder.
  An empty object refuses: clearing the setting is NULL.
- **`folder` holds names, never an id.** No leading `/`, no `..` segment, no control character, no URL. Obsidian and
  Drive take a relative path; Notion takes one page name with no `/`, since a request carries one `subfolder`.
  Ids stay per machine (the two Notion variables) or per document (`space=`, `page=`, `file=`).
- **What `folder` means per channel.** Obsidian: the folder under `$OBSIDIAN_VAULT`. Notion: the page under the scope
  folder `SD_NOTION_PRIVATE_FOLDER` or `SD_NOTION_TEAM_FOLDER` names; it replaces today's `<repo>` subfolder.
  Drive: the path under My Drive; it replaces `Briefs/<repo>`.
- **Setting it.** `bin/sd-db repo channels PATH` prints the value; `bin/sd-db repo channels PATH none` clears it;
  `bin/sd-db repo channels PATH obsidian=Briefs/x notion=Example drive=` sets it, `drive=` meaning the default folder
  and an unnamed channel meaning off. One setter, `repos.set_channels(connection, path, value, *, before=None)`,
  shaped like `set_runner_merge`: it refuses an unregistered path and a value the validator refuses, returns
  `(path, before)`. `before` is the value the caller read, as canonical JSON or `none`; given, it is compared inside
  the write transaction, so two forms both opened on a NULL row cannot both write. The verb passes no `before`, the
  dashboard always passes one. A failed read exits 1 with the cause; it never prints `none`.
  `repo list` keeps its fields and `runner_merge` stays last; the setting prints through the `channels` verb.
- **A listed channel is a channel the repo uses.** With a setting present, a document designated for a channel the
  setting omits is refused for that channel, by name, and the other channels still publish. Omitting `obsidian` stops
  the vault copy, and the render reports it. The dashboard copy in `docs/dashboard/` is not a channel and always
  publishes.
- **The document still opts in.** An outward mirror stays opt-in per document (`notion=`, `drive=`), as the
  publication contract rules and Q1 confirmed; the setting says where, not whether. The Notion scope stays per
  document too: only `notion=dict(team=True)` reaches the team space, so the setting has no scope key.
- **Precedence.** A document's own `space=` or `folder=` wins over the setting; the setting wins over the default.
  A pinned `page=` or `file=` (drain step 5 writes one after the first drain) wins over both: that page is updated
  where it is, and a folder change moves only documents with no pin. Where the setting names a folder for a channel,
  the render names each pinned document of that channel, with the fix: delete the pin to create the page under the
  setting's folder.
- **Stale requests are refused, not deleted.** A pending request for a channel the setting now omits stays in the
  queue. The render names it on every run with its path, and drain step 2 refuses it: the drain reads the row of the
  `repo` the request names (`bin/sd-db repo channels <repo>`), and a setting that omits the request's destination
  leaves the request unwritten. A read that fails (exit not 0) also leaves every request of that repo unwritten,
  with or without `item=`: unknown is not "no restriction". The operator deletes it by hand, with no drain session running. Nothing deletes a
  request automatically: a deletion racing a drain that passed step 2 before the setting changed leaves a page written
  and a receipt that says otherwise. Re-enabling that channel later takes one render with `SD_MIRROR_REQUEUE=1`, which
  queues past the old receipt.
- **No setting, no change.** A repo whose `channels` is NULL, or that has no row, publishes exactly as today, and its
  requests and fingerprints stay byte for byte the same. So does a machine with no workflow database at all (no
  database file and no `hub.json`): the pack's research kit still runs for an operator without `sd_db`. That keeps
  today's Notion mirrors working, the experiments dashboard's first target.
- **Unknown is not "no setting".** The render reads the row through `sd_db.connect` with a short bound. A database
  that exists but cannot be read (hub unreachable, a build mismatch, an unresolved restore) holds the vault copy and
  the queue for that render and says why; the dashboard copy is still written. Falling back to the defaults would
  publish into folders the operator moved away from.
- **A setting change re-renders on the next render.** The setting is not in the checkout, so no git hook sees it
  change. The dashboard form and the verb both print the remedy: run `sd-research-kit render` in the checkout, or wait
  for the next commit. Until then the vault copies and requests stay where the last render put them.

**Where it is read.** `sd_db.repos.repo_channels(connection, path)` returns the validated setting or `None`.
The research publisher calls it once per render; the dashboard reads the column with the rest of the row.
Nothing reads `sd-plugin.json` for channels, and `lib/sd_db/channels.py` holds no file reader: it holds `validate`
and `record_url`, below.

### The published URL reaches the item (sd:3465)

The item row holds the URL; the dashboard reads the row.

- **Store.** `fields.published` on the item, keyed by repository and document, since one item may own several
  documents: `{"<repo>::<document>": {"title": "<title>", "<channel>": "<url>"}}`. `<repo>` is the repository's
  home-relative key (`sd_db.paths.key`), as the `repo` table holds it, not the basename the queue file names use:
  two repositories with one basename get two keys. One `comment` note per change,
  `Published <channel> <document>: <url>`, gives history. No table, column or file is added. The receipt keeps its
  `url` for `sd-status`.
- **Writer.** `sd_db.channels.record_url(connection, item, repo, document, title, channel, url, who)`, one transaction:
  refuse while a `restore` state row is unresolved; refuse an unknown item; return `unchanged` when the field already
  holds the URL (no note); else set it and write the note. A satellite runs it over the existing remote connection.
- **Notion and Drive: bound to the drained generation.** `delivered <name> <fingerprint> --url <url>` records only
  when the pending request is still the generation the drain read (`fingerprint` equal). It then calls `record_url`
  with that request's `item`, `repo`, `document` and `title`, before it writes the receipt. A newer pending generation
  records nothing on the item and leaves the request: the next drain writes that generation and records with its
  `item`. Today `acknowledge_request` copies the pending request's `item` onto the receipt whatever its generation;
  C3 fixes that too.
- **`delivered` fails loudly.** A request that names `item` refuses without `--url`, before any write (exit 2).
  A refused or failed `record_url`, receipt write or removal leaves the request, prints the reason and exits 1.
  Today the receipt-write and removal failures print and exit 0.
- **Obsidian.** The vault copy is a local write at render, so the render records it:
  `obsidian://open?vault=<vault folder name>&file=<path without .md>`. `write_obsidian` returns which documents it
  wrote; only those that name `item=` are recorded, and only where the render would queue (main checkout, default
  branch, no `SD_SKIP_MIRROR`). A skipped copy (no vault, unreadable source, another checkout's copy, a failed write)
  records nothing. A failure prints `item: obsidian link for sd:<n> not recorded (<reason>)` and never fails the
  render or its git hook; the next render calls again, and an equal URL costs one read.
- **`item` joins the fingerprint when present,** as `source_url` did: changing `item=` re-queues that document once,
  and the drain's `delivered` records the URL on the new item. A request without `item` hashes as before. No document
  names `item=` today, so the upgrade re-queues nothing. C3 corrects the contract and the `designated_item` docstring,
  which say naming an item queues nothing.
- **Dashboard (system).** The item view gets a Published section: each document in `fields.published` with its
  channel links, then `fields.writing.published_urls`, then each publication claim's `url`.
  `writing.js` shows the claim's URL as a link where it shows the claim id now.

Rejected:

- **The dashboard reads the receipt directory.** Receipts are per machine, so a drain on the satellite leaves the hub's
  dashboard blind, and it puts a second store beside the database the ruling names as the tracking store.
- **A `MIRRORS` dict in `research.conf.py`** (B2d F6). It fixes research repos only, and the setting is per repo.
- **A `channels` block in `sd-plugin.json`.** The file is reviewed with the code, but a dashboard edit would leave an
  uncommitted change in a checkout, or need a branch and the lane for one folder name. The operator ruled for the
  repo row (sd:3471, 2026-10-13).
- **A table of its own, one row per repo and channel.** Three channels with one optional folder each fit one JSON
  column; `ci` and `lane_host` set the precedent of a repo setting as a column.

## Non-goals

- Inbound channels, briefs and the five bases: later slices, below.
- A history of setting changes: the verb and the dashboard print `before -> after`, as `runner-merge` does.
- Writing pieces' Drive publication: its claim already records the URL, and its folders are `sdw` settings.
  `SD_WRITING_DESTINATIONS` stays where it is.
- Email, Slack and social posting.
- Moving existing per-document `space=` and `page=` pins into the setting: they keep working as overrides.
- Deleting or moving pages and vault copies left behind when a repo changes a folder: nothing deletes an outward copy.
- Drain step 5's write-back of page and file ids into `research.conf.py`. It is unchanged; research repos are
  private, and the setting never holds an id.

## Failure table

Publishing moves state in steps: render, queue, drain, item record, receipt, removal. The drain's own rows
(steps 3 to 6 of the publication contract) stand; the rows below are the ones this design adds or changes.

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| migrate: add the column | `repo.channels` exists, `user_version` 29 | the script fails halfway, or a process still runs against 28 | `migrate` wraps the file and the version bump in one transaction, so a failure leaves 28; the sitting takes `sd-db backup` first and stops the dashboard, the runner and `sd-db serve`; the file's comment holds the reverse | `tests/sd_db/test_schema.py`: 029 on a version-28 fixture adds the column with every row NULL, a second run applies nothing, and the reverse returns to 28, fail-first |
| library at 29, database at 28 | nothing | C1 code reads a database not yet migrated | writes refuse with `SchemaTooOld`, as today; the render's read of the column fails and counts as unknown (row "render: read the setting"), never as "no setting" | `test_channels`: a version-28 fixture reads unknown, not `None`, fail-first |
| library at 28, database at 29 | nothing | a rollback of C1 after `migrate` | every caller of the older build refuses with `SchemaTooNew`, as for any migration; run the reverse in the file's comment, or restore the backup taken before `migrate` | none: the existing `SchemaTooNew` test covers it |
| set: verb or dashboard | `repo.channels` | a value the validator refuses; an unregistered path; a row that moved since the page read it | refused before any write, naming the key, the path or the current value; the row is unchanged | `tests/sd_db/test_repos.py`: each refusal leaves the row unchanged, fail-first; the dashboard test posts a stale `before` and reads `StaleSetting` |
| set: the change takes effect | nothing outside the row | the operator expects the vault copies and requests to move at once | the verb and the form print the remedy: run `sd-research-kit render` in the checkout, or wait for the next commit | `test_repos`: the verb's output names the render command |
| render: read the setting | nothing | hub unreachable, build mismatch, unresolved restore, or a stored value the validator refuses | the render writes the dashboard copy, names the cause, and writes no vault copy and queues nothing for that repo; requests queued earlier stay; the git hook exits 0, a hand-run render exits 1; the next render after a fix publishes | `test_sd_research_publish`: each cause holds the vault copy and leaves the queue as it was, fail-first |
| render: no database | nothing | the machine has no database file and no `hub.json` | today's behaviour, byte for byte | `test_sd_research_publish`: the no-database fixture equals the `origin/main` fixture |
| render: vault copy | the Markdown under the repo's folder | the setting moved the folder | the copy lands in the new folder; when the setting names a non-default folder, the render names any copy this checkout owns (by its frontmatter) left in `Briefs/<repo>`, and deletes nothing | `test_sd_research_publish`: a folder change reports the old copies |
| render: record Obsidian URL | `fields.published[...].obsidian`, one note | hub unreachable, restore open, or item unknown | the vault copy stands; the render prints the reason and exits 0; the next render records it | `test_channels_record`: a refused record leaves the render's exit 0 and records on the next render, fail-first |
| render: record Obsidian URL | nothing | the vault copy was skipped (no vault, another checkout's copy, write error) | nothing is recorded; the report names the skipped copy | `test_sd_research_publish`: each skip path records no URL, fail-first |
| render: stale request | nothing; the request stays | the setting dropped a channel that has a pending request | the render names the request and its path each run; drain step 2 reads the row and refuses it unwritten; the operator deletes it by hand with no drain session running; a drain that passed step 2 before the change may still write the page, so re-enabling the channel takes one render with `SD_MIRROR_REQUEUE=1` | `test_sd_research_publish`: a dropped channel's pending request is reported and left byte for byte, fail-first |
| render: enqueue | a request under the new container | the setting moved a Notion or Drive folder | an unpinned document's container differs, so a carried id is dropped and the drain creates the page in the new folder; the old page stays; a pinned document keeps its page and is reported | existing carried-id identity tests, plus one each for a folder change with and without a pin |
| drain: read the setting | nothing | `sd-db repo channels` fails: hub unreachable, build mismatch, a stored value the validator refuses | drain step 2 writes nothing outward for that repo; requests and receipts stay; the next drain after a fix proceeds | `test_repos`: the verb exits 1 and prints no `none` on a version-28 database and on a value the validator refuses, fail-first; the contract text names the refusal |
| drain: setting changed after render | a request for the old folder | the setting moved a folder after the render queued | the drain writes the queued generation where it names; the next render queues a new generation for the new folder, and the drain moves nothing of the old one | `test_sd_research_publish`: a render after a folder change queues the new container once |
| delivered: record URL | `fields.published[...].<channel>`, one note | hub unreachable, restore open, or item unknown | the request and receipt stay; exit 1; the next drain updates the page it names (its id is recorded) and runs `delivered` again | `test_delivered`: a refused record leaves request and receipt unchanged, fail-first |
| delivered: newer generation pending | receipt `delivered` for the drained fingerprint | a render queued generation B, with another item or container, while the drain wrote A | no item record; the receipt is written without B's item; B stays; the next drain writes B and records with B's item | `test_delivered`: B with a changed item records nothing on either item, fail-first |
| delivered: between record and receipt | URL on the item, receipt not written | process stopped, or the receipt write fails | the request stays; exit 1 on a write failure; the next drain updates the same page and `record_url` returns `unchanged` | `test_delivered`: stop after `record_url`, rerun completes with one note; a receipt write error exits 1, fail-first |
| delivered: removal | receipt written, request still present | the unlink fails | exit 1; the next render sees the receipt's fingerprint, the next drain re-acknowledges | `test_delivered`: an unlink error exits 1, fail-first |
| item changed | request carries the new `item` | `item=` edited after a delivered drain | the fingerprint changes, the next drain updates the page and records the URL on the new item; the old item keeps its URL | `test_sd_research_publish`: an `item=` change re-queues once; a request written before C3 with `item` re-queues once |
| restore | item and repo rows older than the receipts | a restore drops recorded URLs, and brings back an older `channels` value, or NULL from a pre-29 snapshot | renders hold and `record_url` refuses until the restore resolves; before resolving it, the operator compares `sd-db repo channels` for each repo that had a setting and sets it again with the verb (`set_channels` does not refuse during a restore); then `SD_MIRROR_REQUEUE=1` on a render re-queues, and each drain records again | `test_channels_record`: refusal while a restore is open; `test_sd_research_publish`: a render holds while a restore is open; `test_repos`: `set_channels` writes while a restore is open, fail-first |
| rollback of C2 or C3 | requests and vault copies from older code | a repo has a setting, which the old publisher ignores: it uses default folders and queues every designated channel, omitted ones included | do not drain a repo with a setting (`sd-status` lists requests by repo) until the roll-forward. A pinned document's page is unaffected. After the roll-forward, the first render rewrites each request of a moved folder under the same file name for the setting's container, and reports each request for an omitted channel as stale; the operator deletes those by hand, with no drain running. Delete the stray vault copies by hand | `test_sd_research_publish`: requests and vault copies written by the `origin/main` publisher, rendered again under a setting, are rewritten for a moved folder and reported for an omitted channel, fail-first |

## Slices

Four PRs. Each writes its tests first, and each behaviour test fails on `origin/main` before the fix. The
no-setting fixture tests pass on both by design: they guard today's behaviour.

1. **C1 repo row setting, verb and migration** (pack, sd:3462). `029_repo_channels.sql` and `SCHEMA_VERSION = 29`;
   `lib/sd_db/channels.py` `validate`; `repos.set_channels` and `repos.repo_channels`; `sd-db repo channels`
   (print, set, `none`) in the `runner-merge` shape; the verb in `docs/` beside `runner-merge`. Tests:
   `tests/sd_db/test_schema.py` (the migration row), `tests/sd_db/test_channels.py` (each refusal by key, a Notion
   folder with `/`, an empty object), `tests/sd_db/test_repos.py` (set, print, clear, unregistered path, stale
   `before`). The sitting after merge: `sd-db backup`, stop the dashboard, the runner and `sd-db serve`,
   `sd-db migrate`, start them. Leaves working: every row reads NULL, so nothing publishes differently. About 3 hours.
2. **C2 publisher reads the setting** (pack, sd:3462). The render reads `repos.repo_channels` once;
   `vault_folder`, `notion_target` and `mirror_targets` take its folder; an omitted channel refuses per destination;
   an omitted `obsidian` writes no vault copy; an unreadable setting holds the vault copy and the queue; the
   stale-request and pinned-document reports. `publication-contract.md` and the research conventions describe the
   setting, the amended Obsidian rule and drain step 2's row read and stale-request refusal. Tests: a repo with no
   setting, and a machine with no database, produce requests and fingerprints equal to the `origin/main` fixture;
   each channel's folder override; a document key wins over the setting; a pin wins over both; an omitted channel
   refuses, its pending request is reported and left, and the others still queue; each unknown cause holds.
   Leaves working: every research repo, none of which has a setting, publishes as before. About 4 hours.
3. **C3 the URL reaches the item** (pack, sd:3979). `channels.record_url`; `delivered` records for the drained
   generation only, requires `--url` for an item, and exits non-zero on every incomplete step; `write_obsidian`
   returns what it wrote and the render records those; `item` joins the fingerprint when present; the contract's
   step 6 and its `item=` paragraph say so. Tests: every failure-table row above marked `test_delivered`,
   `test_channels_record` or the Obsidian skip paths. Leaves working: a document without `item=` publishes and drains
   as before. About 4 hours.
4. **C4 dashboard** (system, sd:3465 and the system half of sd:3462). The pin bump; the item view's Published
   section; the writing claim URL as a link; a repo-settings form for each repo's channels: a checkbox and a folder
   field per channel, posted to `/api/repos/channels` with the value the page showed, written by
   `management_screen.set_repo` through `repos.set_channels` under the same `BEGIN IMMEDIATE` and hub-only refusal
   as `runner-merge`, and answered with the render remedy. Invoke `hallmark` first. Tests: `test_v2_tasks` and the
   writing screen test assert the links; the management test posts a value, a stale `before`, a refused folder and
   a satellite write, each fail-first. Leaves working: items with no URL show no section; a repo with no setting
   shows the defaults. About 4 hours.


### Later slices

**Inbound (sd:3461, then feeds and Reddit).** A repo's inbound sources join the same `channels` setting under
their own keys, set by the same verb and form.
Jira and GitHub issues come first: the shadow table already holds both (since sd:361); the slice adds per-repo
source settings and "mine" rows on Today and Tasks, filtered to issues assigned to or reported by the operator, not
watched ones. GitHub issues are read only for repos outside the managed list. Feeds follow: one
general RSS/Atom subscription read by `sd-watchlist` (sd:3980), the one feed reader, which retires the website's
ExternalChannels sync. Reddit joins both ways after that (sd:3981); X keeps its small posting quota.
`local-project-dashboard/.env`'s dead Jira keys go in the sd:3461 PR.

**Briefs (sd:3459).** The routines' write target moves from vault notes in their vault briefs folder to database
rows, and `briefs_screen.py` reads the rows. The vault then gets those briefs only as an Obsidian channel copy, under
the folder the system repo's `channels` setting names. The brief digest mail stays until sd:3459 and sd:3460 replace its buttons
(sd:3537 note 16666).

**The website (sd:3633, sd:3634).** The website becomes a publication channel whose publish receipt returns the
public URL, recorded through `record_url`. Social posts of website URLs stay on the website behind its approval gate.

**The Notion experiments dashboard (sd:3982).** A projection sd fills from item rows into the work Notion space,
through the same queue and drain as the research mirrors. Until it is built, C2's no-setting test is what keeps today's Notion
mirrors working.

**The five bases (sd:3558).** The 2026-10-10 five-bases design in the system repo, item sd:1145, stands; its seven
slices are filed as their own items: S1 sd:3972, S2 sd:3973, W1 sd:3974, P1 sd:3975, S3 sd:3976, S4 sd:3977, W2 sd:3978.
Since sd:3557 moved the database library into the pack, its importer, records module and mirror renderer are pack
slices. The Markdown mirror it renders is the writing plugin's Obsidian copy, at the
`store.bases` paths; it needs no `channels` setting.

## Open questions

None. The operator answered Q1 and Q2 on 2026-10-13 (Rulings above).

## Acceptance criteria

- [ ] `python3 -m unittest tests.sd_db.test_schema tests.sd_db.test_channels tests.sd_db.test_repos` passes with
      0 failures.
- [ ] After `sd-db migrate` on a version-28 copy, `sd-db status` reads 29 and `sd-db repo channels <path>` prints
      `none` for every row.
- [ ] `sd-db repo channels <path> notion=Example drive=Research/Example` prints `none -> ` and the new value;
      `notion=A/B` refuses naming `notion` and changes nothing.
- [ ] On a repo with no setting, every request `render` queues equals the `origin/main` fixture byte for byte.
- [ ] With `notion=Example`, a `notion=dict()` request carries `subfolder: "Example"`; with
      `drive=Research/Example`, a `drive=dict()` request carries `folder: "Research/Example"`.
- [ ] A `drive=` document in a repo whose setting omits `drive` reports `drive: not a channel of this repo`, names
      its pending Drive request and leaves that file unchanged, and queues its Notion request.
- [ ] With the hub unreachable, a render writes the dashboard copy, no vault copy and no request, and names the cause.
- [ ] With the hub unreachable, `sd-db repo channels <path>` exits 1 and prints no `none`.
- [ ] Two repositories with one basename record one item's URLs under two `fields.published` keys.
- [ ] After `delivered <name> <fp> --url https://example.test/p` on a request with `item: 7`, `sd task show 7` shows
      `Published notion <document>: https://example.test/p`, and a second `delivered` adds no note.
- [ ] With the hub unreachable, `delivered` exits 1 and the request file is unchanged.
- [ ] `delivered` on a request with `item` and no `--url` exits 2 and writes nothing.
- [ ] The dashboard item view for item 7 links `https://example.test/p` under the document's title.
- [ ] The dashboard's channels form changes a repo's row, and a second form posted with the old value is refused.


## Risks

- A rollback of C2 after a repo adopts a setting sends that repo's next drain to the default container and to
  channels the setting omits. Accepted, with the recovery in the failure table: hold that repo's drains.
- The setting lives in the hub's database, so a satellite's render needs the hub. With the hub down, a satellite
  writes only the dashboard copy until it returns. Accepted: falling back to defaults would publish to the wrong place.
- A restore to a snapshot from before a setting change brings back the old setting, and renders after the restore
  resolves publish under it. Accepted, with the recovery in the failure table's restore row.
- Changing a folder leaves the old pages and vault copies in place; they look current and are not. The render names
  vault copies left in the default folder only; copies in an earlier non-default folder and the outward pages need a
  hand check. Accepted: nothing here deletes an outward copy.
- A stale request is refused only by the drain's prose step 2; the pack ships no drain code. A drain that skips that
  step publishes to a channel the repo dropped. Accepted: the render names the request on every run until it is
  deleted, and `sd-status` lists it.
- A Notion `folder` is a page name under the scope folder, resolved by the drain. Two pages of that name under the
  scope folder are an ambiguity the drain reports and leaves queued, as the contract's look-before-create says.
- The Obsidian URL assumes the vault's name is its folder name, Obsidian's default. A renamed vault gets a link that
  opens nothing; the vault copy is still there.
- What ties a recorded URL to its item is the request generation: `delivered` records only when the fingerprint it
  was given is the pending request's, and that request was written by a render of the main checkout on its default
  branch. A hand-edited request can still point a URL at another item; the threat model accepts that.
- The receipt keeps `url` and `item` beside the row. Two places hold the URL; the row is the one any reader uses, and
  the receipt is the drain's record. Deleting the receipt's copy is left to the KISS audit.
