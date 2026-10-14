---
title: Experiments projection - sd writes the rows it owns into a team experiments database, keyed to a row id on the item
created: 2026-10-14
item: sd:3982
---

# Design: experiments projection (sd:3982)

Write this page only when the shape needs agreement before the code.
The item's row holds status, progress and decisions; this page holds the shape.

## Status

Design only. Nothing is built, and nothing writes to the team databases, until the operator approves Q1 below
(operator rulings, sd:3982, 2026-10-14 14:05 and 14:30 MDT). The schemas below were read once, read-only, through the
work satellite's Notion connection on 2026-10-14.

Adversarial review: one read-only round on 2026-10-14 found eight blocking findings. Dispositions:

- F1 the wanted value claimed a colleague's field: fixed; only `written` and `writing` make a field sd's.
- F2 an edit between fetch and write is overwritten: no conditional write exists in Notion; the drain fetches again
  before writing, and Q4 asks the operator to accept the window or make `Status` a seed.
- F3 two drains at once: rebutted by the threat model (two concurrent runs of one manual command are out of scope);
  `delivered` still checks the designation, and a second create surfaces as two pointer rows.
- F4 the fingerprint missed a pin change and a re-designation: fixed; `row` and `since` join it, and `delivered`
  checks the designation in its transaction.
- F5 title search lost a renamed row, and `off` lost an adopted row: fixed; recovery searches the pointer text, a
  plan records `creating` so sd never creates twice on its own, and `off` keeps `row`.
- F6 step 4 could graft a row id onto a newer request: fixed; rows skip steps 4 and 5, and the row id goes only on
  the item, through `delivered`.
- F7 step 2 compared `notion-row` with channel names: fixed; a `notion-row` request reads the channel `notion`.
- F8 `sd-status` cannot match a `~/` repo key: fixed; the request carries the key through `paths.expand`.

## Terms

- **Experiments database**: the team database in the work Notion space that holds one row per experiment.
- **Tasks database**: the team database beside it; each row links to one experiment.
- **Projection**: sd writes a row from an item and keeps the fields it owns current. It reads nothing back.
- **Designation**: the item's opt-in, `fields.experiments` on the item row, the item analogue of a document's
  `notion=`.
- **Row id**: the Notion page id of the row, recorded in the designation the way `page=` pins a mirror page.
- **sd-owned field**: a property sd writes on every update, under the guard below. **Seed field**: a property sd
  writes once, at create, and never again. **Person-owned field**: a property sd never writes.

## Problem

The team tracks experiments in two shared Notion databases that colleagues edit by hand. The operator's work on those
experiments lives in sd items, so the databases fall behind unless someone copies status across by hand.

The channels ruling makes this dashboard a projection sd fills (sd:3471, 2026-10-12), through the same queue and drain
as the research mirrors. That drain cannot do it today. It creates or updates one Markdown page under a container
(`skills/_shared/references/publication-contract.md`, steps 1 to 6); it writes no database row and no typed property,
and nothing in it protects a field a colleague edited.

## Schemas read

Experiments database, 17 properties. Title `Experiment`. Selects: `Stage` (Idea, Scoping, Running, Evaluating,
Decided), `Decision` (Productize, Iterate, Stop), `Status` (Todo, In Progress, Blocked, Done). People: `Lead`,
`Assignee`. Date: `Sprint`. Text: `Problem`, `Hypothesis`, `Success Measure`, `Outcome`, `Reference Docs`.
Relations: `Tasks` (two-way with the tasks database's `Experiment`), and the self-relations `Iteration Of` and
`Follow-ons`. Rollups over `Tasks`: `Task Progress` (percent of `Done` checked) and `Open Tasks` (count unchecked).

Tasks database, 9 properties. Title `Task`. Selects: `Status` (the same four), `Priority` (High, Medium, Low), `Type`
(Build, Benchmark, Research, Design, Docs, Demo). `Assignee` (person), `Due` (date), `Deliverable` (URL), `Experiment`
(relation to one experiment), `Done` (a formula the rollups read).

Neither database has a unique-id property or one set aside for a link back to sd; `Reference Docs` and
`Deliverable` hold the team's own links.

## Approach

### Which items project

Only an item the operator designates; nothing is inferred from a kind, a title or a repo, as the publication contract
rules for documents. A designation is one of two shapes in `fields.experiments`:

```json
{"as": "experiment", "since": "2026-10-14T20:30:00Z"}
{"as": "task", "of": 4021, "since": "2026-10-14T20:31:00Z"}
```

- **Experiment**: the item becomes one row in the experiments database.
- **Task**: the item becomes one row in the tasks database, linked to the row of item `of`. `of` must name an item
  designated `experiment`; a task of a task, a task of itself and an `of` naming no item refuse. One level only.
- **Adopting a row a colleague made**: a designation may carry `"row": "<page id>"` from the start. sd then updates
  that row and creates none; the guard below leaves every field a colleague already set.
- **Off**: `"as": "off"` stops the projection and keeps `row`, so designating the item again resumes on the same row
  instead of creating a second one. The row stays: nothing deletes an outward copy.
- **`since`** is the time of the last designation change. It joins the fingerprint, so a change of designation
  re-queues the item even where nothing else moved and the receipt says delivered.

The designation is written by one new flag on an existing verb (Q5):
`sd task edit N --experiment yes|of:M|row:ID|new|off`. `row:ID` pins an existing row; `new` drops the pinned row
so the next drain creates one; `off` stops. The queue is per machine and the item row is on the hub, so the flag
cannot see a pending request; `project` names one and `--plan` refuses it (failure table).

### Field mapping and ownership

sd writes only what it owns, plus a link back; every other property belongs to the people who edit the databases.

| Database | Property | Owner | Source in sd |
| --- | --- | --- | --- |
| Experiments | `Experiment` | seed | item title |
| Experiments | `Status` | sd | item status (map below) |
| Experiments | `Stage` | seed (Q3) | item status: `work-idea` kind Idea; planning, ready Scoping; in_progress, ready_to_send, blocked Running; done Evaluating |
| Experiments | `Decision`, `Lead`, `Assignee`, `Sprint`, the five text fields, `Iteration Of`, `Follow-ons` | person | none |
| Experiments | `Tasks`, `Task Progress`, `Open Tasks` | Notion | filled by each task's `Experiment` and the rollups |
| Tasks | `Task` | seed | item title |
| Tasks | `Status` | sd | item status (map below) |
| Tasks | `Experiment` | sd | the row id of item `of` |
| Tasks | `Due` | sd | item `due` |
| Tasks | `Priority` | seed | item priority: 1 High, 2 Medium, 3 and 4 Low, none empty |
| Tasks | `Type`, `Assignee`, `Deliverable` | person | none |
| Tasks | `Done` | Notion | the formula |

Status map, both databases: planning and ready Todo; in_progress and ready_to_send In Progress; blocked Blocked; done
Done, a cancelled item included.

**The link back** is the row's body: on create sd writes one line, `Projected from sd:<n>. sd keeps Status current;
edit anything else.` (Q2). sd writes the body only at create. The pointer is also what look-before-create matches on.
No item body, note or URL leaves sd: a row carries the title, status, due date and priority of a designated item, no
more.

**The guard.** An sd-owned field is written only while its live value is one sd itself put there. The designation
records two values per sd-owned field: `written`, the last value sd wrote and saw land, and `writing`, the value a
plan approved and the drain may have written. At each drain, for each sd-owned field:

- live value equals `written` or `writing`: the field is sd's. The live value becomes `written`, and the field is
  written when it differs from the wanted value.
- live value differs from both: a person changed it, even where it happens to equal what sd now wants. sd leaves it:
  the field is not written and is listed in `yielded`, which the plan reports and the item shows.
- an empty `written` and `writing` (a row being created, or an adopted row): an empty live value is sd's; any other
  value is the person's.

The wanted value alone never makes a field sd's: a colleague who set `Blocked` while sd also wants `Blocked` keeps
the field, and sd's later `Done` does not overwrite it. A yielded field becomes sd's again only when a person sets
it back to `written`, the value sd last wrote: that is the hand-back, and it needs no command.
Comparing against `writing` as well is what makes an interrupted write safe: a drain stopped after Notion took the
value but before sd recorded it sees its own value on the next run, not a colleague's.

Notion has no conditional write, so a colleague's edit that lands between the drain's fetch and its write is
overwritten. The drain fetches immediately before it writes, which keeps that window to seconds; Q4 asks the
operator to accept it or to make `Status` a seed.

### Row identity: create versus update

The row id is recorded in the designation, `fields.experiments.row`, the way drain step 5 writes `page=`.

- **Row id given**: the drain fetches that row and updates it. It never creates a second row for an item whose
  designation names one.
- **No row id, first time**: the plan records `creating`, the database id and the generation, on the item before it
  prints a create. The drain creates the row with the seed and sd-owned fields and the pointer, in one call, and
  `delivered` records the row id on the item (step 6, which takes the place of steps 4 and 5 for rows: the
  designation lives in the database, not in a file).
- **No row id, `creating` already set**: an earlier create may have landed with its id recorded nowhere. The drain
  searches the target database for the pointer text `sd:<n>`, whatever the row is titled now, and hands the plan
  every row whose body opens with that pointer. One row is adopted. None or two make the plan refuse, and the drain
  files one question on the item (Option: no row exists, create it, which is `--experiment new`; Option: this is the
  row, which is `--experiment row:ID`). sd never creates twice on its own, because search can lag a create.
- **No step 4.** The request file never holds a row id, so no `project` re-run can graft a row onto another
  generation, and `recorded()` is not used for rows. The request copies the designation's `row` for the report and the fingerprint.

### Reusing the queue, drain, `delivered` and `record_url`

No parallel path: one queue, one lock, one receipt directory, one `delivered`, one status report.

- **Enqueue**: `sd-research-kit project` reads every designated item from the workflow database and writes one
  request per item into `~/.claude/pending-mirror-syncs/`, named `sd-item-<n>.notion-row.json`, under
  `pending-mirror-syncs.lock`. A request carries `destination: "notion-row"`, `item`, `as`, `of`, `database` (the
  configured data source id), `repo` (the item's repo key passed through `paths.expand`, the disk path `sd-status`
  compares, as research requests carry), `target` (`experiments` or `tasks`), `row` and a `fingerprint`. The
  fingerprint covers the item, `as`, `of`, `since`, `row`, the database and the sd-owned values; a title change
  re-queues nothing, since the title is a seed. `already_queued` and the receipt keep an unchanged item from
  re-queueing, as for documents.
- **Who runs it**: the drain session, as its first step, on the machine that reaches the work Notion space. No hook,
  cron job or dashboard button runs it in this design.
- **Plan**: `sd-research-kit project --plan <request> --live <file>|--missing` is the guard, in code. It reads the
  item again, recomputes the request and refuses a request whose fingerprint is not that recompute (stale). It reads
  the item's repo channels setting and refuses where a setting omits `notion`. It checks the live row's parent
  database, the property types and the select options against the mapping. It then records `written`, `writing`,
  `yielded` and, for a create, `creating` on the item in one transaction, and prints the properties to write as
  JSON. A refusal exits non-zero and writes nothing.
- **Drain**: a new destination block in the contract's step 3, for `notion-row`: fetch the database schema and the
  row, run the plan, fetch the row again if the plan took more than a moment, write exactly what the plan printed in
  one Notion call, experiments before tasks. Step 2 changes in one place: a `notion-row` request reads the channel
  `notion`, since a destination name is not a channel name. Steps 4 and 5 do not apply to rows; steps 1 and 6 apply
  as written.
- **`delivered`**: unchanged in shape: `delivered <name> <fingerprint> --url <row url>`. For a `notion-row` request
  it calls `projection.record_row` where it calls `record_url` for a document, for the drained generation only. One
  transaction that checks the designation still has the request's `as`, `of`, `since` and database, and a `row` that
  is empty or equal to the URL's id; then writes `row` and `url`, moves `writing` to `written`, clears `creating`, and
  adds one comment note `Projected to <target>: <url>` when the row is new. The receipt and removal follow as today.
- **Status report**: `sd-status` reports any request as `mirror-sync-pending` from its `repo` and `target`, so a
  `notion-row` request shows on its repo's report with no change there.

`record_url` itself is not reused: its key is `<repo>::<document>` and its channel vocabulary is
`obsidian`, `notion`, `drive`, and a row is neither a document nor a channel folder. `record_row` shares its refusals
(restore open, unknown item, unreadable fields).

### Configuration

Two per-machine variables, set beside `$OBSIDIAN_VAULT` and the two Notion folder ids, never committed:

```sh
SD_NOTION_EXPERIMENTS=change-me          # data source id of the experiments database
SD_NOTION_EXPERIMENT_TASKS=change-me     # data source id of the tasks database
```

Unset, or holding a name instead of an id, `project` refuses and names the variable; nothing queues. A machine
without them never projects, which is how the build can land before anyone sets them.

### New mechanisms, and what each replaces

| Mechanism | Replaces | Smallest form |
| --- | --- | --- |
| `fields.experiments` on the item: `as`, `of`, `since`, `row`, `url`, `written`, `writing`, `yielded`, `creating` | nothing; the item analogue of `page=` | a JSON field, no migration |
| `sd task edit --experiment` | hand-editing the field | one flag on an existing verb |
| `sd-research-kit project` and its `--plan` form | copying status by hand | one verb on the command that owns the queue |
| destination `notion-row` and its contract block | nothing | one row in `DESTINATIONS`, one block in step 3 |
| `projection.record_row` | nothing; sibling of `record_url` | one library function |
| `SD_NOTION_EXPERIMENTS`, `SD_NOTION_EXPERIMENT_TASKS` | nothing | two variables beside the existing two |

Recommended: all six, and nothing else. No table, no column, no queue, no receipt kind and no new command.

Rejected:

- **A row queue or state store of its own.** It would duplicate the lock, the receipt, the generation rule and the
  status report this queue already has.
- **Writing Notion from code.** The pack holds no Notion credential, and its hooks cannot reach an MCP server.
- **Inferring experiments** from a kind or a title. The publication contract forbids inferring a target.
- **A read-only `sd projection` page beside the databases** (option 2 in note #19178): no new mechanism, but it is not
  the dashboard the team reads.
- **The guard as prose in the contract only.** It is the one property the operator asked for, so it is code with
  tests; the drain prose only calls it.
- **Last-writer-wins on sd-owned fields.** It overwrites a colleague's correction on the next drain.

## Non-goals

- Reading anything back into sd: `Stage`, `Decision`, `Outcome` and the people fields stay in Notion.
- Deleting or archiving a row, for an item un-designated, cancelled or deleted.
- People fields: sd holds no mapping from the operator to a Notion user.
- Item bodies, notes, published URLs or repo names in a row.
- Adding a property or a select option to either database; a schema change is the team's.
- Designating items in bulk, or a backfill.
- A dashboard control for the designation: a later system slice, after the operator approves writing.

## Failure table

Projection moves state in steps: project, plan, Notion write, item record, receipt, removal. The
contract's drain rows (its "What each failure leaves behind" table) stand; these rows are the ones this design adds.
The pack ships no drain code, so a row whose step is drain prose is tested on the code either side of it and on the
contract text.

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| project: read items | nothing | hub unreachable, build mismatch, restore open | no request is written; the cause is named; exit 1; requests queued earlier stay | `test_projection`: each cause leaves the queue byte for byte, fail-first |
| project: read config | nothing | a variable unset or holding a name | refuses, naming the variable; nothing queued | `test_projection`: unset and name-valued variables refuse, fail-first |
| project: write requests | one file per item | stopped between two files; a write fails or truncates a file | written one at a time under the lock; a truncated file fails `load_record`, so no drain reads it and the next `project` rewrites it | `test_projection`: a truncated request is rewritten on the next run |
| project: item un-designated or deleted | request stays | a request is pending for an item no longer designated | `project` names it with its path on every run; `--plan` refuses it as stale; the operator deletes it by hand with no drain running | `test_projection`: a dropped designation's request is reported and left byte for byte, fail-first |
| project: re-run during a drain | request rewritten | `project` runs between a plan and its `delivered` | the request holds no row id, so nothing is lost or grafted; `creating` and `writing` stay on the item; `delivered` for the old fingerprint records nothing, and the next drain adopts the row by its pointer | `test_projection`: a re-run after a plan leaves `creating` and `writing` on the item, fail-first |
| plan: stale request | nothing | the item's status, designation, `of` or the config changed after `project` | refuses `stale: run project`; the drain leaves the request; the next `project` rewrites it | `test_projection_plan`: each change refuses, fail-first |
| plan: hub or restore | nothing | hub unreachable, restore open | refuses; unknown is not a pass | `test_projection_plan`: both refuse, fail-first |
| plan: channels | nothing | the item's repo setting omits `notion`, or the setting cannot be read | refuses, naming the setting or the cause | `test_projection_plan`: both refuse, fail-first |
| plan: row deleted by hand | nothing | the pinned row is not found or is in the trash, which Notion also answers for lost access | the drain passes `--missing`; plan refuses and never prints a create; the drain files one question note on the item (Option: stop projecting it, `--experiment off`; Option: create a new row, `--experiment new`) unless one is open | `test_projection_plan`: `--missing` refuses with no create, fail-first; contract text names the note |
| plan: live read failed | nothing | the Notion fetch errors other than not found | the drain stops that request and does not call plan: a failed read is unknown, not missing | contract text test |
| plan: schema change | nothing | a mapped property renamed, removed or retyped; a select option removed; the row's parent is another database | refuses the whole request, naming the property; never edits the schema or adds an option; fix Notion or the mapping | `test_projection_plan`: each change refuses with the property's name, fail-first |
| plan: field edited by hand | `yielded` on the item | a live sd-owned value differs from `written` and `writing`, including one equal to the wanted value | the field is left out of the write and listed in `yielded`; the others are written; it is sd's again once a person sets it back to `written` | `test_projection_plan`: a hand-set `Status` is yielded, a hand-set value equal to the wanted one is not claimed and is not overwritten by a later wanted value, and setting it back to `written` hands it back, fail-first |
| plan: parent has no row | nothing | a task drained before its experiment's row exists | refuses `parent sd:<m> has no row yet`; the contract drains experiments first | `test_projection_plan`: refuses, fail-first |
| plan: record intent | `written`, `writing`, `yielded`, `creating` | the transaction fails | nothing is printed and nothing written; exit 1 | `test_projection_plan`: a refused write prints no plan |
| plan: designation changed after plan | nothing more | `sd task edit --experiment` runs while a drain is between plan and `delivered` | `delivered` checks `as`, `of`, `since`, database and `row` in its transaction and refuses a mismatch; the request stays and the next `project` rewrites it | `test_delivered`: each changed key refuses with request and receipt left, fail-first |
| Notion: fetch to write | a colleague's value overwritten | a person edits an sd-owned field in the seconds between the drain's fetch and its write | none: Notion has no conditional write; the drain fetches again just before writing; accepted under Q4 | none: no Notion code in the pack; the contract text names the second fetch |
| Notion: create | a row, `creating` on the item | stopped after create, before `delivered` | the next plan sees `creating`; the drain searches by the pointer text, not the title, and the plan adopts exactly one row; none or two refuse and file one question; sd never creates twice on its own | `test_projection_plan`: with `creating` set, no candidate and two candidates refuse with no create, one candidate is adopted with nothing yielded, fail-first |
| Notion: create, then the config moves | a row in the old database | the operator changes `SD_NOTION_EXPERIMENTS` while `creating` names the old database | the plan refuses, naming both databases; the operator answers with `--experiment new` or `row:ID` | `test_projection_plan`: `creating` for another database refuses, fail-first |
| Notion: update | the row's properties | stopped or failed after Notion took some values | the next plan sees `writing` on the row and counts it as sd's; nothing is yielded | `test_projection_plan`: a partly written row is completed with nothing yielded, fail-first |
| delivered: record row | `row`, `url`, `written` on the item, one note | hub down, restore open, item unknown, the item pins another row, the URL's id is not the request's row | request and receipt stay; exit 1; a re-run answers `unchanged` | `test_delivered`: each refusal leaves request and receipt, fail-first |
| delivered: between record and receipt | row on the item, no receipt | stopped, or the receipt write fails | existing row of the contract table: the request stays and the re-run records `unchanged` | `test_delivered`: stop after `record_row`, the re-run adds no note |
| delivered: newer generation pending | receipt for the drained fingerprint | `project` queued a newer generation during the drain | no row is recorded; `creating` and `writing` stay, so the next drain adopts the row by its pointer and counts its values as sd's | `test_delivered`: a newer generation records no row, and the next plan adopts and yields nothing, fail-first |
| two drains at once | two plans for one item | two sessions drain the same queue | out of the pack's threat model (two concurrent runs of one manual command); `delivered` still refuses a designation that moved, and a second create is found by the pointer search and reported as two rows | none |
| rollback of the build | `notion-row` requests in the queue | an older pack meets them | an older `delivered` calls `record_url`, which refuses the channel `notion-row` and exits 1; older drains do not know the destination and leave it; `sd-status` still lists it; delete them by hand with no drain running | `test_delivered`: the `origin/main` `record_url` refuses `notion-row` |

## Slices

Two pack PRs and one system PR, built only after the operator approves Q1. Each writes its tests first, and each
behaviour test fails on `origin/main` before the change.

1. **E1 designation** (pack). `lib/sd_db/projection.py`: the designation validator, the status, stage and priority
   maps, and `record_row`. `sd task edit --experiment`. Tests: `tests/sd_db/test_projection.py` (each designation
   shape, each refusal, `record_row` refusals and `unchanged`), the `sd task edit` test. Leaves working: an item can
   be designated; nothing reads the designation, so nothing leaves the machine. About 3 hours.
2. **E2 queue, plan, drain** (pack). `sd-research-kit project` and `--plan`; destination `notion-row`; `delivered`
   calls `record_row`; the contract's `notion-row` block, the drain order, and step 2's `notion-row` reads `notion`. Tests: every failure-table row marked
   `test_projection`, `test_projection_plan` or `test_delivered`, plus a no-designation run that leaves the queue
   byte for byte. Leaves working: with neither variable set, `project` refuses and every research mirror drains as
   before. About 5 hours.
3. **E3 dashboard** (system). The item view links `fields.experiments.url` in its Published section and shows a
   designation control that posts the same value as the flag. Invoke `hallmark` first. Leaves working: an item with
   no designation shows nothing new. About 3 hours.

After E2: the operator sets the two variables on the work satellite, designates one test experiment and one task,
and runs one drain there with the operator present. That is a sitting, not a slice.

## Open questions

Each goes to the operator as its own question on the dashboard.

1. **Q1 Approve writing into the team databases?** Option: approve sd-owned fields and seeds as mapped (Recommended).
   Option: use the read-only page beside the databases instead. Option: close the item.
2. **Q2 Link back.** Option: one pointer line in the row body at create; no schema change (Recommended). Option: add an
   `sd` text property to both databases; colleagues see a new column, and it is a team schema change.
3. **Q3 Stage.** Option: seed `Stage` at create from the status map, then leave it to people (Recommended). Option:
   leave `Stage` empty for people to set.
4. **Q4 Status ownership.** Option: sd owns `Status` under the guard, accepting that a colleague's edit landing in
   the seconds between the drain's fetch and write is overwritten (Recommended). Option: sd seeds `Status` once and
   owns nothing after create, which leaves the dashboard stale.
5. **Q5 Designation.** Option: `sd task edit --experiment`, then a dashboard control in E3 (Recommended). Option: the
   dashboard control only.

## Acceptance criteria

- [ ] `python3 -m unittest tests.sd_db.test_projection` passes with 0 failures.
- [ ] `sd task edit 7 --experiment of:7` refuses, naming a task of itself; `--experiment of:8` refuses while 8 is not
      designated `experiment`.
- [ ] With `SD_NOTION_EXPERIMENTS` unset, `sd-research-kit project` exits non-zero, names the variable and writes no
      file in the queue.
- [ ] With both variables set to synthetic ids and two designated items, `project` writes two `notion-row` requests;
      a second run writes none and reports both unchanged.
- [ ] `--plan` on a request whose item changed status since `project` exits non-zero with `stale`.
- [ ] `--plan` with a live row whose `Status` a person changed prints no `Status` and records it in `yielded`, also
      when the person's value equals the wanted one.
- [ ] `--plan` with `creating` set and no candidate row exits non-zero and prints no create.
- [ ] `--plan` with a live row lacking the `Status` property exits non-zero, naming `Status`.
- [ ] `--plan --missing` exits non-zero and prints no create.
- [ ] `delivered <name> <fp> --url https://example.test/<32 hex>` records the row id on the item; a second run adds no
      note.
- [ ] With no designation anywhere, every research request a render queues equals the `origin/main` fixture byte for
      byte.

## Risks

- The guard holds only if the drain calls `--plan` and writes what it prints; the pack ships no drain code. Accepted,
  as for drain step 2: the contract says so, and a plan is cheap to call.
- Notion answers "not found" for a deleted row and for lost access alike. Accepted: both refuse and ask the operator,
  and sd never recreates a row on its own.
- Property and option names live in the pack's mapping, not in config. A rename in Notion refuses every request until
  someone reconciles them. Accepted: a refusal is visible and loses nothing; a configurable mapping is a mechanism
  nobody has asked for.
- A designated item's title becomes readable to the team. Accepted: designation is per item and opt-in, and only the
  title, status, due date and priority go across.
- A person who sets a yielded field back to sd's last value hands it back, even by chance. Accepted: the value is the
  one sd wrote, so sd taking it again overwrites nothing the person chose differently.
- Notion has no conditional write: an edit landing between the drain's fetch and its write is lost (Q4).
- A request for an item with no repo appears in no repo's `sd-status`. `project` lists every pending `notion-row`
  request on each run, and it runs at the start of every drain.
- What ties each pass to its subject: `--plan` passes only for the request's item, its configured database, a live
  row whose parent is that database and whose id is the pinned one, and a fingerprint equal to a fresh recompute.
  `delivered` records only for the drained fingerprint, on the request's item, with a URL whose id is the request's
  row.
