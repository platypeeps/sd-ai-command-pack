---
title: Channels, outbound first - one channel contract per repo, and the published URL reaches the item
created: 2026-10-13
item: sd:3471
---

# Design: channels, outbound first (sd:3471)

Write this page only when the shape needs agreement before the code.
The item's row holds status, progress and decisions; this page holds the shape.

## Terms

- **Channel**: a place a repo's work goes to (outbound) or comes from (inbound): Obsidian, Notion, Drive; later Jira,
  GitHub issues, feeds, Reddit, email, Slack.
- **Channel contract**: the `channels` block in a repo's `sd-plugin.json`. It says which channels the repo uses, and
  the folder each one writes to.
- **Brief** names three things today. A research-kit brief is a document published to `Briefs/<repo>/`.
  A routine brief is a vault note the scheduled routines write in their vault briefs folder; the dashboard's
  Briefs page reads these. A brief digest is the mail `obsidian-review` sends with the `Brief:` subject prefix.
  This page means the first unless it says otherwise.

## Rulings this design follows

All are operator rulings on the items named; they bind this design.

- Obsidian is a publication target and knowledge base only; tracking lives in sd (sd:3462, 2026-10-12).
- Channels are choosable per repo: Notion, email, Obsidian, Drive, GitHub issues, Jira, Slack; social later (same note).
- Outbound first: one channel contract per repo in `sd-plugin.json`; Notion, Obsidian and Drive publish with a
  folder each and a receipt URL. Inbound and briefs follow (sd:3471, 2026-10-13).
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
built: no file in the pack or in a research repo defines it. This design replaces that proposal.

## Approach

### The channel contract

One optional block in the repo's `sd-plugin.json`. The outbound half is `publish`; the inbound half, `watch`, comes
with the inbound slice and is refused by name before then.

```json
{
  "channels": {
    "publish": {
      "obsidian": {"folder": "Briefs/example-research"},
      "notion": {"folder": "Example"},
      "drive": {"folder": "Research/Example"}
    }
  }
}
```

- **Closed vocabulary**, refused by name at read time, like every manifest block: `publish` holds `obsidian`,
  `notion`, `drive`; each holds `folder` only, and `{}` means the channel's default folder; an empty `publish` refuses.
- **`folder` holds names, never an id.** No leading `/`, no `..` segment, no control character, no URL. Obsidian and
  Drive take a relative path; Notion takes one page name with no `/`, since a request carries one `subfolder`.
  Ids stay per machine (the two Notion variables) or per document (`space=`, `page=`, `file=`).
- **What `folder` means per channel.** Obsidian: the folder under `$OBSIDIAN_VAULT`. Notion: the page under the scope
  folder `SD_NOTION_PRIVATE_FOLDER` or `SD_NOTION_TEAM_FOLDER` names; it replaces today's `<repo>` subfolder.
  Drive: the path under My Drive; it replaces `Briefs/<repo>`.
- **A listed channel is a channel the repo uses.** With a `publish` block present, a document designated for a channel
  the block omits is refused for that channel, by name, and the other channels still publish. Omitting `obsidian`
  stops the vault copy, and the render reports it. The dashboard copy in `docs/dashboard/` is not a channel and always
  publishes.
- **The document still opts in.** An outward mirror stays opt-in per document (`notion=`, `drive=`), as the
  publication contract rules; the block says where, not whether. The Notion scope stays per document too: only
  `notion=dict(team=True)` reaches the team space, so the block has no scope key. Open question Q1 asks the operator
  whether a repo-wide opt-in is wanted.
- **Precedence.** A document's own `space=` or `folder=` wins over the block; the block wins over the default.
  A pinned `page=` or `file=` (drain step 5 writes one after the first drain) wins over both: that page is updated
  where it is, and a block folder change moves only documents with no pin. Where the block names a folder for a
  channel, the render names each pinned document of that channel, with the fix: delete the pin to create the page
  under the block's folder.
- **Stale requests are refused, not deleted.** A pending request for a channel the block now omits stays in the queue.
  The render names it on every run with its path, and drain step 2 refuses it: the drain reads the `repo` the request
  names, and a block there that omits the request's destination leaves the request unwritten. The operator deletes it
  by hand, with no drain session running. Nothing deletes a request automatically: a deletion racing a drain that
  passed step 2 before the block changed leaves a page written and a receipt that says otherwise. Re-enabling that
  channel later takes one render with `SD_MIRROR_REQUEUE=1`, which queues past the old receipt.
- **No block, no change.** A repo without `channels` publishes exactly as today, and its requests and fingerprints
  stay byte for byte the same. That keeps today's Notion mirrors working, the experiments dashboard's first target.
- **The block re-renders.** The re-render hook renders when a commit, pull or checkout changes a `.md` or `.py` file;
  C2 adds `sd-plugin.json`. A hook installed before C2 renders on the next `.md` or `.py` change instead;
  `sd-research-kit init-hook` replaces it, since it is a released body.

**Where it is read.** `lib/sd_db/channels.py` holds `read(checkout)` and `validate(block)`.
`bin/sd` adds `channels` to `MANIFEST_KEYS`, and `sd plugin list` shows it; the research publisher reads the
checkout's own `sd-plugin.json` through `read`; the dashboard reads it through the installed `sd_db`.
`prefix` stays required to register a plugin (`sd plugin add`), not to carry a `channels` block: the publisher reads
the checkout it renders, and research repos are not plugins. Decision recorded on sd:3471.

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
- **A `MIRRORS` dict in `research.conf.py`** (B2d F6). It fixes research repos only, and the ruling puts the contract
  in `sd-plugin.json`.
- **The contract in the `repo` table.** A database column edited from the dashboard needs no commit, but the ruling
  names `sd-plugin.json`, and the file is reviewed with the code that reads it.

## Non-goals

- Inbound channels, briefs and the five bases: later slices, below.
- Writing pieces' Drive publication: its claim already records the URL, and its folders are `sdw` settings.
  `SD_WRITING_DESTINATIONS` stays where it is.
- Email, Slack and social posting.
- Moving existing per-document `space=` and `page=` pins into the block: they keep working as overrides.
- Deleting or moving pages and vault copies left behind when a repo changes a folder: nothing deletes an outward copy.
- Drain step 5's write-back of page and file ids into `research.conf.py`. It is unchanged; research repos are
  private, and the block itself never holds an id.

## Failure table

Publishing moves state in steps: render, queue, drain, item record, receipt, removal. The drain's own rows
(steps 3 to 6 of the publication contract) stand; the rows below are the ones this design adds or changes.

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| render: read the contract | nothing | `sd-plugin.json` unreadable or a bad `channels` block | the render writes the dashboard copy, names the file and the key, and writes no vault copy and queues nothing for that repo; requests queued under the last good block stay; the next render after a fix publishes | `test_sd_research_publish`: a bad block refuses by key and leaves the queue as it was, fail-first |
| render: vault copy | the Markdown under the repo's folder | the block moved the folder | the copy lands in the new folder; when the block names a non-default folder, the render names any copy this checkout owns (by its frontmatter) left in `Briefs/<repo>`, and deletes nothing | `test_sd_research_publish`: a folder change reports the old copies |
| render: record Obsidian URL | `fields.published[...].obsidian`, one note | hub unreachable, restore open, or item unknown | the vault copy stands; the render prints the reason and exits 0; the next render records it | `test_channels_record`: a refused record leaves the render's exit 0 and records on the next render, fail-first |
| render: record Obsidian URL | nothing | the vault copy was skipped (no vault, another checkout's copy, write error) | nothing is recorded; the report names the skipped copy | `test_sd_research_publish`: each skip path records no URL, fail-first |
| render: stale request | nothing; the request stays | the block dropped a channel that has a pending request | the render names the request and its path each run; drain step 2 refuses it unwritten; the operator deletes it by hand with no drain session running; a drain that passed step 2 before the block changed may still write the page, so re-enabling the channel takes one render with `SD_MIRROR_REQUEUE=1` | `test_sd_research_publish`: a dropped channel's pending request is reported and left byte for byte, fail-first |
| render: enqueue | a request under the new container | the block moved a Notion or Drive folder | an unpinned document's container differs, so a carried id is dropped and the drain creates the page in the new folder; the old page stays; a pinned document keeps its page and is reported | existing carried-id identity tests, plus one each for a block folder change with and without a pin |
| delivered: record URL | `fields.published[...].<channel>`, one note | hub unreachable, restore open, or item unknown | the request and receipt stay; exit 1; the next drain updates the page it names (its id is recorded) and runs `delivered` again | `test_delivered`: a refused record leaves request and receipt unchanged, fail-first |
| delivered: newer generation pending | receipt `delivered` for the drained fingerprint | a render queued generation B, with another item or container, while the drain wrote A | no item record; the receipt is written without B's item; B stays; the next drain writes B and records with B's item | `test_delivered`: B with a changed item records nothing on either item, fail-first |
| delivered: between record and receipt | URL on the item, receipt not written | process stopped, or the receipt write fails | the request stays; exit 1 on a write failure; the next drain updates the same page and `record_url` returns `unchanged` | `test_delivered`: stop after `record_url`, rerun completes with one note; a receipt write error exits 1, fail-first |
| delivered: removal | receipt written, request still present | the unlink fails | exit 1; the next render sees the receipt's fingerprint, the next drain re-acknowledges | `test_delivered`: an unlink error exits 1, fail-first |
| item changed | request carries the new `item` | `item=` edited after a delivered drain | the fingerprint changes, the next drain updates the page and records the URL on the new item; the old item keeps its URL | `test_sd_research_publish`: an `item=` change re-queues once; a request written before C3 with `item` re-queues once |
| restore | item rows older than the receipts | a database restore drops recorded URLs | `record_url` refuses until the restore resolves; then `SD_MIRROR_REQUEUE=1` on a render re-queues, and each drain records again; Obsidian records on the next render | `test_channels_record`: refusal while a restore is open |
| rollback of C2 or C3 | requests and vault copies from older code | a repo's block names a non-default folder, which the old publisher ignores | a pinned document is unaffected: old and new code both update the page its `page=` or `file=` names. An unpinned one: the old code writes its vault copy to `Briefs/<repo>` and queues it to the default container. Do not drain that repo's unpinned requests (`sd-status` lists them by repo) until the roll-forward: its first render rewrites each under the same file name for the block's container. Delete the stray vault copies by hand | none: a rollback runs old code; the risk is accepted below |

## Slices

Four PRs. Each writes its tests first, and each behaviour test fails on `origin/main` before the fix. The no-block
fixture tests pass on both by design: they guard today's behaviour.

1. **C1 contract block** (pack, sd:3462). `lib/sd_db/channels.py` `read` and `validate`; `channels` in `MANIFEST_KEYS`;
   `sd plugin list` shows the block; `docs/domain-packs.md` gains the block and the prefix rule.
   Tests: `tests/sd_db/test_channels.py` (each refusal by key, a Notion folder with `/`, a channels-only manifest
   reads with no `prefix`), `tests/test_sd_plugin.py` (`list --json` carries it; an unknown channel refuses at `add`).
   Leaves working: nothing reads the block for publishing yet; every manifest that registers today still registers.
   About 2 hours.
2. **C2 publisher reads the contract** (pack, sd:3462). `vault_folder`, `notion_target` and `mirror_targets` take the
   block's folder; an omitted channel refuses per destination; an omitted `obsidian` writes no vault copy; the
   stale-request and pinned-document reports; the hook triggers on `sd-plugin.json`. `publication-contract.md` and the
   research conventions describe the block, the amended Obsidian rule and drain step 2's stale-request refusal.
   Tests: a repo with no block produces requests and fingerprints equal to the `origin/main` fixture; each channel's
   folder override; a document key wins over the block; a pin wins over both; an omitted channel refuses, its pending
   request is reported and left, and the others still queue; a manifest-only commit renders. Leaves working: every research repo, none of which has
   a block, publishes as before. About 4 hours.
3. **C3 the URL reaches the item** (pack, sd:3979). `channels.record_url`; `delivered` records for the drained
   generation only, requires `--url` for an item, and exits non-zero on every incomplete step; `write_obsidian`
   returns what it wrote and the render records those; `item` joins the fingerprint when present; the contract's
   step 6 and its `item=` paragraph say so. Tests: every failure-table row above marked `test_delivered`,
   `test_channels_record` or the Obsidian skip paths. Leaves working: a document without `item=` publishes and drains
   as before. About 4 hours.
4. **C4 dashboard** (system, sd:3465 and the system half of sd:3462). The pin bump; the item view's Published section;
   the writing claim URL as a link; each repo's channels shown on the repo page with the file path, read-only until
   Q2 is answered. Invoke `hallmark` first. Tests: `test_v2_tasks` and the writing screen test assert the links,
   fail-first. Leaves working: items with no URL show no section. About 3 hours.

### Later slices

**Inbound (sd:3461, then feeds and Reddit).** The `watch` half of the same block names a repo's inbound sources.
Jira and GitHub issues come first: the shadow table already holds both (since sd:361); the slice adds per-repo
source settings and "mine" rows on Today and Tasks, filtered to issues assigned to or reported by the operator, not
watched ones. GitHub issues are read only for repos outside the managed list. Feeds follow: one
general RSS/Atom subscription read by `sd-watchlist` (sd:3980), the one feed reader, which retires the website's
ExternalChannels sync. Reddit joins both ways after that (sd:3981); X keeps its small posting quota.
`local-project-dashboard/.env`'s dead Jira keys go in the sd:3461 PR.

**Briefs (sd:3459).** The routines' write target moves from vault notes in their vault briefs folder to database
rows, and `briefs_screen.py` reads the rows. The vault then gets those briefs only as an Obsidian channel copy, under
the folder the system repo's block names. The brief digest mail stays until sd:3459 and sd:3460 replace its buttons
(sd:3537 note 16666).

**The website (sd:3633, sd:3634).** The website becomes a publication channel whose publish receipt returns the
public URL, recorded through `record_url`. Social posts of website URLs stay on the website behind its approval gate.

**The Notion experiments dashboard (sd:3982).** A projection sd fills from item rows into the work Notion space,
through the same queue and drain as the research mirrors. Until it is built, C2's no-block test is what keeps today's Notion
mirrors working.

**The five bases (sd:3558).** The 2026-10-10 five-bases design in the system repo, item sd:1145, stands; its seven
slices are filed as their own items: S1 sd:3972, S2 sd:3973, W1 sd:3974, P1 sd:3975, S3 sd:3976, S4 sd:3977, W2 sd:3978.
Since sd:3557 moved the database library into the pack, its importer, records module and mirror renderer are pack
slices. The Markdown mirror it renders is the writing plugin's Obsidian copy, at the
`store.bases` paths; it needs no `channels` block.

## Open questions

Filed on sd:3471 as questions; the slices above do not wait on them except where named.

- Q1: does a repo's `publish` block opt every finished document in, or does each document still opt in? The design
  keeps per-document opt-in, the standing publication rule.
- Q2: does the dashboard edit a repo's `channels` block, leaving an uncommitted change in the checkout, or show it
  read-only with the file path? C4 builds read-only.

## Acceptance criteria

- [ ] `python3 -m unittest tests.sd_db.test_channels tests.test_sd_plugin` passes with 0 failures.
- [ ] On a repo with no `channels` block, every request `render` queues equals the `origin/main` fixture byte for byte.
- [ ] With `"notion": {"folder": "Example"}`, a `notion=dict()` request carries `subfolder: "Example"`; with
      `"drive": {"folder": "Research/Example"}`, a `drive=dict()` request carries `folder: "Research/Example"`.
- [ ] A `drive=` document in a repo whose block omits `drive` reports `drive: not a channel of this repo`, names its
      pending Drive request and leaves that file unchanged, and queues its Notion request.
- [ ] Two repositories with one basename record one item's URLs under two `fields.published` keys.
- [ ] After `delivered <name> <fp> --url https://example.test/p` on a request with `item: 7`, `sd task show 7` shows
      `Published notion <document>: https://example.test/p`, and a second `delivered` adds no note.
- [ ] With the hub unreachable, `delivered` exits 1 and the request file is unchanged.
- [ ] `delivered` on a request with `item` and no `--url` exits 2 and writes nothing.
- [ ] The dashboard item view for item 7 links `https://example.test/p` under the document's title.

## Risks

- A rollback of C2 after a repo adopts a non-default folder sends that repo's next drain to the default container,
  which creates a page there. Accepted, with the recovery in the failure table.
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
