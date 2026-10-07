# Design — implement progress in notes

The problem, the measurement and the requirements are in [prd.md](prd.md).
The steps are in [implement.md](implement.md).

## The shape

```text
implement.md (committed, reviewed)       note table (sd database)
  ## Steps                                 step 3: done · #1377 · 5dff9e55
  1. ...  2. ...  3. ...                   step 1: started
        |                                         |
        +---------- bin/sd_steps.py --------------+
                      plan_steps + step_status -> one status per step
                                  |
             sd task steps <item>   sd-status open-step   (dashboard: Q9)
```

One new module, `bin/sd_steps.py`, owns the plan parser, the note line format
and the join. `bin/sd_work.py` (`sd task note`, `sd task steps`),
`bin/sd-status` and `bin/sd-docs-lint` call it. The system repository and the
database schema do not change.

## Status

Proposed, 2026-10-07. The operator has not ruled Q1 to Q11. Each question
below carries a recommendation.

Planning review round 1 (codex) found that a renumbered plan moves a `done`
note onto other work. Round 2 found that a title match misses a scope change
under an unchanged title. Both are one class: a note survives a plan change
that should reopen its step. Points 1, 3, 4 and 7 now bind each note to a
digest of the whole step, and the table in point 3 covers every plan change
point 7 names. Round 2 also
found the template's "never tick" line wrong for `file` repositories; point
7 now limits it to `row` repositories.

## Decisions

### 0. The alternative first: a docs-only gate tier

The item asks to weigh this first: run docs lint and the citation checks on
a docs-only diff, not the full `make check`. And does Jev's skip tier already
cover docs-only diffs?

**The tier already exists, and neither repository declares it.** sd:2072
landed it in pack #1267 (`40e1d08b`). A repository declares
`.github/sd-check-scope.json` with `docs_paths` and `docs_command`. When every
changed path matches, `sd-check --base REF` runs only `docs_command`
(`decide` in `bin/sd_check_scope.py`). On 2026-10-07 one repository under
`~/repos` declares it: `mezmo-world-simulator`. The pack and system do not.

**Jev's skip tier does not cover the gate.** `skip` is a review tier, not a
gate tier. `route` in `bin/sd_route.py` plans `skip` when every path is in
`docs_skip`. `bin/sd_jev.py` may raise the tier and never lowers it
(sd:2132). No tier, Jev's or the policy's, changes what `sd-check` runs. The
review side is already free for docs in the pack: its `.github/sd-review.json`
routes `docs/**` and `*.md` to `skip`. System's `.github/sd-review.json` has
no `docs_skip`, so a docs-only system pull request still gets a standard
review. A planning-scope review keeps a floor of one reviewer at tier `skip`
(`review_depth` in `bin/sd-review`); that stays.

**What the tier would save.** Gate receipts since 2026-09-21 give a full,
passing `make check` a median of 552 s in the pack (364 receipts, p90 984 s)
and 436 s in system (374 receipts, p90 777 s). The docs-only squashes in
the window were 12 and 23 (prd.md). At one gate each, that is about 4.6 hours
of gate time in 16 days. Catch-up merges add more gates, so this is a floor.

**Why the tier does not answer this item.**

- It makes a progress commit cheaper. It does not make one happen. sd:2704's
  boxes stayed unticked, though its three pack code pull requests could
  tick them at no extra cost. Progress lands where the lane already writes it: notes.
- A progress-only commit is rare. Neither repository has an
  `implement.md`-only squash in the window (prd.md). Most `implement.md`
  edits ride with code, and the tier does nothing for those.
- Each repository needs a correct `docs_command`. In the pack, 27 test
  modules under `tests/` name `docs/work` on 2026-10-07, for example
  `tests/test_doc_citations.py` and `tests/governed.py`. In system,
  `tests/test_citations.py` and `tests/test_product_name.py` read every
  tracked `.md`. A hand-kept list of those tests drifts. `sd_check_scope`
  forces a full check only for files a command names in its argv, not for
  files a test reads.

**Recommendation: notes for progress, in this item. Declare the docs-only
tier in a separate item, system first.** The two are independent. The tier
cuts the cost of docs-only pull requests that remain, such as design
records. Notes remove the reason for progress commits and fix the stale
boxes.

**Q1.** Accept this split? Recommended: yes. File a separate item to
declare `.github/sd-check-scope.json` in system, with `docs_paths` limited to
`docs/**` and a `docs_command` that runs the `make check` preflight. Add
`docs_skip` to system's review policy in the same item. Do the pack after
system, once its doc-reading tests have a target of their own.

### 1. Which note holds step status

**Decision: a `comment` note whose first line is `step <id>: <status>`.**

```text
step 3: done · #1377 · 5dff9e55
plan: 3f9a1c07d2e4 · Pack: the offload view.
Steps 3-5 merged in one squash; review codex, round 6 advisory.
```

- The status is one of `started`, `done` or `dropped`. A step with no note
  is `open`.
- The first line may end with ` · <evidence>`: free text such as
  `#1377 · 5dff9e55` or `system #172`. `dropped` should carry a reason on
  the next line.
- The second line is `plan: <digest> · <title>`. The digest is the first
  12 hex digits of the SHA-256 of the step's block when the note was
  written; the title is for a human reader. The writer computes both; point 3
  uses the digest.
- A step's block is its step line and every line after it, up to the next
  step line or the end of the section. Before hashing, the box mark is
  removed (`- [ ] ` and `- [x] ` read the same), runs of whitespace become
  one space, and blank lines are dropped. A tick or a re-wrap therefore keeps
  the digest; a changed word does not.
- Lines after the second are free text: the log, timings, a path under
  `/Volumes/local/repo-storage/<repo>/`.
- One note per step. The lane's "Steps 3-5 merged" becomes three notes.

Reasons:

- The lane writes progress as notes today: on 2026-10-07, sd:2704 holds 48
  notes that are not status changes. `sd task show` and the dashboard's
  Details pane list notes already. A step note appears in both with no
  renderer change.
- `kind` is a `CHECK` list in the `note` table. A new kind needs a
  `SCHEMA_VERSION` bump in system and a live migrate on the hub. sd:2704 note
  #10084 records what that costs: every `sd` write refused until the migrate
  ran.
- A `state` row, as sd:2783 uses, is structured but invisible in
  `sd task show` and Details. The step status would then live in one store
  and the log in another.

A hand-written comment that starts `step 3: done` but has no `plan:` line
is unbound. `sd task steps` lists it, marked `unbound`, and it sets no
status. Only a note bound to the step's current block closes a step.

**Q2.** Store step status as a `comment` note with a fixed first line? The
alternatives are a new note kind (schema bump) or a `state` row (invisible in
`sd task show`). Recommended: the `comment` note.

**Q3.** Use three statuses, `started`, `done` and `dropped`? Recommended:
yes. `blocked` is a `question` or `followup` note, which exist today.

### 2. What a step is: the plan parser

`plan_steps(text)` in `bin/sd_steps.py` returns `(id, title, ticked,
digest)` per step, the digest as point 1 defines it. A step id is a number with an optional lower-case letter: `1`, `2a`,
`12`.

It reads the first `## Steps`, `## Step checklist` or `## Order` section.
In it, a step is a line that starts at column 0 with `<id>. `,
`- [ ] <id>. ` or `- [x] <id>. `. Fenced code is skipped.

Measured on 2026-10-07, this reads 17 of 22 active plans in the pack and
system. One plan repeats ids, which design point 5 handles. Plans in other shapes, such as system sd:234's
"Slice 1, PR 1" headings, read as "no step list". Their notes still render,
each marked `not in plan`.

### 3. Writer and reader

**Writer:** `sd task note <item> --step <id>:<status> [--evidence TEXT]
[--body TEXT]`. It composes the first line and the `plan:` line from the
plan, appends `--body`, and writes a `comment` note through the existing
note path. With `--step`, `--kind` must be absent or `comment`.

It finds the plan through the item's work directory: the `prd.md` whose
frontmatter says `item: sd:<n>`, or the item's `path`, under the checkout
`item.repo` names. It reads that checkout's working tree. A plan that lists
no such id refuses, and names the ids it lists (R2). No plan found refuses
too, and names the path it read: without the plan, the writer has no block
to bind. A machine that lacks the checkout writes a plain comment instead.

**Reader:** `sd task steps <item> [--json]`. One row per plan step, then one
row per note id the plan lacks. The example is sd:2704 after the backfill;
its last row is invented, to show a note whose id the plan lacks:

```text
id  status   evidence          date        title
1   open                                   Measure, no code.
2   done     system #172       2026-10-05  System repository: the opt-in (Q1).
2a  done     #1374 · 458f7de0  2026-10-05  Pack: the offload view.
9   done     #1390             2026-10-06  (not in plan)
```

`step_status(steps, notes)` decides each row (R4):

1. A note counts for a step only when its id matches and the digest in its
   `plan:` line equals the digest of that id's block in the plan now.
2. The newest counted note wins, by timestamp, then note id.
3. With no counted note, a ticked `[x]` box reads `done`. This keeps
   existing plans correct with no backfill commit.
4. Otherwise the step is `open`.

A note whose id matches but whose digest does not is stale. The plan moved
under it. The row reads by rules 3 and 4, and is marked `changed` with the
note's title. Nothing is closed by a note written for other work or for a
smaller scope. To reconcile, the lane writes a new note for the id, which
binds the current block. Whether the old work still covers the new block is
the operator's or the lane's call, never the reader's.

The binding errs toward reopening. A change that does not alter the work,
such as a corrected size, reopens the step too, and costs one note. A
missed reopening would hide unfinished work, which is the fault this item
exists to remove.

The class: a plan edit changes what a step means while its `done` note
still matches. Review rounds 1 and 2 each found one instance. The table
enumerates every plan edit point 7 names, plus the two readers. Each cell
says whether a `done` note written before the edit still closes the step.
"Wrong" means it closes work that the edit added or moved.

| Plan edit after a `done` note on step 2 | Id only | Title | Block digest (chosen) | New id on scope change | Recovery | Test |
| --- | --- | --- | --- | --- | --- | --- |
| Reordered, block unchanged | `done`, right | `done`, right | `done`, right | `done`, right | none | criterion 10 |
| Box ticked, text re-wrapped | `done`, right | `done`, right | `done`, right | `done`, right | none | criterion 10 |
| Renumbered: id 2 now names other work | wrong | `changed` | `changed` | `changed` if the author obeys | new note on the moved step's new id | criterion 8 |
| Removed; id 2 retired | `not in plan` | `not in plan` | `not in plan` | `not in plan` | none | criterion 8 |
| Removed; id 2 reused for new work | wrong | `changed` | `changed` | wrong if the author reuses | new note when the new work lands | criterion 8 |
| Split into 2a and 2b; id 2 retired | `not in plan` | `not in plan` | `not in plan` | `not in plan` | notes on 2a, 2b | criterion 8 |
| Split; id 2 kept for the first half | wrong | wrong if the title stays | `changed` | `changed` if the author obeys | new note on 2 | criterion 9 |
| Merged with 3 into 2 | wrong | `changed` if retitled | `changed` | `changed` if the author obeys | new note on 2 | criterion 9 |
| Scope or check grown; title kept | wrong | wrong | `changed` | wrong if the author keeps the id | new note after the added work lands | criterion 9 |
| Size or PR split edited; title kept | `done` | `done` | `changed` | `done` | one new note | criterion 9 |
| Title reworded only | `done` | `changed` | `changed` | `done` | one new note | criterion 9 |
| Ruling written outside every step block | wrong | wrong | wrong | wrong | point 7: write it in the step's block | none; a rule |
| `file` repository reader | no join | no join | no join | no join | none; R7, ticks as today | criterion 6 |

Only the block digest covers every edit row without trusting the author.
"New id on scope change" covers the same rows only when the author obeys
it, and nothing checks that: the lint reads one version of the file and no
history. The digest errs toward reopening: a size or title edit reopens a
step that is still done, and costs one note. A missed reopening would hide
unfinished work, the fault this item exists to remove.

The ruling row is the limit of every binding. A plan-wide sentence above
the steps, such as "every step also updates the changelog", changes no
block. Point 7 therefore requires a change that alters a step to be written
in that step's block.

**Decision: the block digest, with point 7's stable ids kept as a rule.** It
is the one binding that covers every edit row. Block digest chosen by the
hub lead: forced new id cannot be checked by the lint. The operator may
overrule when ruling on Q1-Q11.

The digest binding is also the backstop for point 7's stable ids. A
renumbered plan breaks that rule, and the lint cannot see it: the lint
reads one version of the file and no history.

**Q4.** Should `sd-ship merge` write `step <id>: done` notes from a
`Steps:` line in the pull-request body? Recommended: not now. The lane
writes the notes with the verb, as it writes the "Landed" note today.
Revisit after the measurement in implement.md step 7.

### 4. How `sd-status` and the dashboard render progress

**`sd-status`:** `_step_rows` in `bin/sd-status` produces `open-step` rows.
Today it lists every `- [ ]` in every `.md` of an item that is not done. One
change, for `implement.md` in a `row` repository: a `- [ ] <id>.` box that
`step_status` reads `done` or `dropped` is not listed. A stale note counts
for nothing, so a box whose block changed is listed again. Every other box is
listed as today, with today's key.

So a step note only removes rows. A plan written as plain `<id>.` lines
produces no `open-step` rows, as today; `sd task steps` reads it. That is why
the template keeps the `- [ ]` box as the step marker (design point 7): the
box says "this is a step", and a note, never a tick, closes it.

The action text gains the second remedy: "do it, or record it with
`sd task note <n> --step <id>:done`". `prd.md` boxes and a `file` repository
keep today's reading (R5, R7). The section's `EXCLUDED` line about
checkboxes gains a clause naming the join.

`sd-status` reads the database already for item status. The join adds one
note query per active item with a plan.

**Dashboard:** no change in this item. Details lists every note, so a step
note shows there as written. A per-step table needs the plan text, which
lives in a checkout and not in the database. That table is a system change,
with a contract test against the pinned pack's `bin/sd_steps.py`.

**Q9.** Defer the dashboard step table to a system follow-up item?
Recommended: yes. File it when the operator wants a per-step view on the
dashboard.

### 5. How `sd-docs-lint` treats `implement.md`

`implement.md` stays an item document. Rules 1, 2, 6 and 7 apply as today.
The lint reads no database, so it never reads a step's status.

One addition, in rule 1: an `implement.md` whose step list repeats an id
fails, and names the id. A note keys on the id, so a repeated id makes a
note ambiguous.

On 2026-10-07 one plan outside an archive repeats ids: system's sd:2107
plan (`2026-09-29-jev-judgment-correctness`). Ids 1 and 2 appear twice under
`## Order`, in two lists. System runs the pack's lint at its `.sd-pack-rev`
pin, so the failure reaches system only when the pin moves. Step 4 of
implement.md fixes that plan before the pin moves.

**Q10.** Should the lint fail a diff that only ticks boxes in
`implement.md`? Recommended: no. The tick becomes harmless once `sd-status`
reads notes. Rule 8 shows what a diff-reading rule costs: it needs
`--changed` or a git fallback, which `make check` does not supply.

### 6. `.citations.tsv`: committed or generated on demand

**Decision: keep it committed. No pack change.**

Rule 6 compares each recorded snippet with the cited line now. The recorded
snippet is the baseline: what the author saw when the citation was written.
A file generated at check time records the present text, so every citation
matches and rule 6 checks nothing.

The cost is low. In the window, no pack squash and one system squash touched
a `.citations.tsv` (prd.md). A re-record follows a change to the cited text,
which is a plan change and is committed anyway. Progress out of
`implement.md` removes one cause of re-records: progress lines inserted above
a cited line moved it.

**Q6.** Keep `.citations.tsv` committed? Recommended: yes.

### 7. What counts as a plan change

`implement.md` changes in a commit when one of these changes:

- the steps: one added, removed, split, merged or reordered;
- a step's scope, size, check, or pull-request split;
- a ruling that changes any of the above.

A step id is an identity, not a position. Reordering keeps each step's
id. A new step takes an id the plan has never used, such as `2a` or the next
number. A removed, split or merged step's id is retired, not reused. A step
that is split keeps neither half on the old id. Point 3 catches a plan that
breaks this rule: the old note no longer matches the block, so it closes
nothing.

A change that alters a step goes into that step's block: its scope, its
check, its size or its pull request. A sentence elsewhere in the file
changes no digest, so it reopens nothing (point 3, the table's last row).

These go to notes and are never a reason for a commit: a step's status,
"what landed", merge shas, timings, measurements, review rounds and their
dispositions, hand-offs. A measurement that a later decision rests on is
quoted into `design.md` with that decision, which is then a plan change.

The plan template keeps `- [ ] <id>.` as the step marker. It has no
`.status-source` branch today. It gains a template-instruction comment that
reads `.status-source`, as the `prd.md` template's status comment does.
With `row`: record progress with `sd task note <item> --step <id>:<status>`,
never by a tick. With `file`: tick the box, as today: a `file` repository has
no note join, so an unticked box there stays an `open-step` row (R7). A plan
that ticks a box in a `row` repository still reads correctly (point 3).

The same split applies to the `## Status` section of `prd.md` and
`design.md`. A ruling stays in it. "Implementation has not started" and
"steps 3-5 merged" do not; `sd task steps` answers that.

The `prd.md` template carries a `## Log` section, and `WORKFLOW.md` records
operator-observed criteria there (sd:1933, 2026-09-30). In a `row`
repository, both become notes.

**Q7.** Move `## Log` entries to notes in `row` repositories, and amend the
sd:1933 paragraph in `WORKFLOW.md` to say so? Recommended: yes. The ruling's
substance holds: no pull request ticks an operator-observed criterion in
advance. Only the place the observation is recorded changes.

**Q8.** Drop progress lines from `## Status` sections, keeping rulings?
Recommended: yes.

### 8. Existing plans and the backfill

No existing `implement.md` changes. A ticked box reads `done` until a note
says otherwise (point 3). In the pack on 2026-10-07, one active plan has
merged steps behind unticked boxes: sd:2704, eight steps. sd:2783's one
merged step is ticked. System's `open-step` rows were not measured here.

After the writer lands, the lane writes eight `step <id>: done` notes on
sd:2704 from its existing notes. It does the same for any merged step that
`sd-status --actions` lists in system. These are database writes, not
commits.

**Q5.** Read a ticked box as `done` when no note exists, and backfill
merged steps by notes only? Recommended: yes. No plan file is rewritten.

**Q11.** Include `prd.md` acceptance-criteria boxes? Recommended: no, not
in this item. 28 of the pack's 43 `open-step` rows on 2026-10-07 come from
`prd.md` boxes on planning items whose work has not started. Those rows are
correct. Revisit if a criterion with a merged check stays listed.

## Failure modes

| Fault | Effect | Who sees it |
| --- | --- | --- |
| Step id not in the plan | the writer refuses and lists the plan's ids | the writer |
| No plan found for the item | the writer refuses and names the path it read | the writer |
| Plan changed in a step's block after a note | the note is stale; the step reads by its box and is marked `changed` | the reader, in `sd task steps` and `sd-status` |
| A hand-written `step <id>:` comment with no `plan:` line | listed as `unbound`; it sets no status | the reader |
| Plan in an unparsed shape | `sd task steps` says "no step list"; notes render as `not in plan` | the reader |
| Plan repeats a step id | `sd-docs-lint` rule 1 fails, names the id | the author, at the gate |
| A wrong `done` note | the step reads `done`; a newer note corrects it | whoever reads the note |
| Database unreachable | `sd task steps` fails as every `sd` read does; `sd-status` reports the work section unreadable | the reader |

## Rollout and rollback

Steps 1 to 4 add readers and a writer; no output changes until a step note
exists, except the lint check of point 5. Step 5 changes the template and
the docs. Rollback reverts the pull requests. Step notes stay in the
database as ordinary comments and harm nothing.

## Alternatives rejected

- **A docs-only gate tier instead of notes:** point 0.
- **A new `step` note kind:** a schema bump for a value a fixed first line
  carries (Q2).
- **A `state` row per step:** invisible in `sd task show` and Details; the
  log would then sit in a second store (Q2).
- **Parse the lane's free-text notes, such as "Steps 3-5 merged":** the
  phrasing varies. A fixed line from one verb is cheaper to read.
- **Generate `.citations.tsv` on demand:** empties rule 6 (point 6).
- **Keep ticking boxes and fix `sd-status` only:** the box still needs a
  commit, and sd:2704 shows nobody pays for it.

## Open questions

The questions above, in one list. Each carries its recommendation.

| Q | Question | Recommended |
| --- | --- | --- |
| Q1 | Notes now; a docs-only gate tier as a separate item? | Yes; system first, then the pack. |
| Q2 | Store: `comment` note, new note kind, or `state` row? | `comment` note with a fixed first line. |
| Q3 | Statuses `started`, `done`, `dropped`? | Yes. |
| Q4 | `sd-ship merge` writes step notes from a `Steps:` line? | Not now; revisit after step 7. |
| Q5 | Ticked box reads `done` with no note; backfill merged steps by notes only? | Yes. |
| Q6 | Keep `.citations.tsv` committed? | Yes. |
| Q7 | `## Log` and the sd:1933 record move to notes in `row` repositories? | Yes. |
| Q8 | Progress lines leave `## Status`; rulings stay? | Yes. |
| Q9 | Dashboard step table deferred to a system item? | Yes. |
| Q10 | Lint fails a tick-only diff? | No. |
| Q11 | `prd.md` acceptance-criteria boxes in scope? | No. |
