---
title: Implement progress lives in sd task notes; implement.md changes only when the plan changes
created: 2026-10-07
item: sd:2784
---
# PRD — implement progress in notes

## Status

Accepted. The design is in [design.md](design.md). Operator ruling
2026-10-07: accept all Q1-Q11.

## Problem

An `implement.md` file holds two kinds of text. The plan is the steps, their
sizes, their checks and the pull-request split. Progress is a ticked box, a
"what landed" paragraph, a timing, a log line. The plan needs review. Progress
does not, and nothing reviews it in practice.

Progress in a committed file costs a commit, and a commit in these
repositories costs a pull request, a gate and a merge slot. So progress is
either paid for or left out. Both happen.

The measurement covers 2026-09-21 00:00 MDT to 2026-10-07 on `origin/main`:
pack at `445c8fd9`, system at `8797a03`. It reads first-parent squash commits
with `git log --first-parent --name-only`.

| Measure | Pack | System |
| --- | --- | --- |
| Squash commits | 267 | 225 |
| Docs-only (every path `*.md`, under `docs/`, or `.citations.tsv`) | 12 | 23 |
| Of those, every path under `docs/work/` | 5 | 6 |
| Touch a `docs/work/**/implement.md` | 7 | 20 |
| Of those, with a code path as well | 5 | 15 |
| Change only `implement.md` (and `.citations.tsv`) | 0 | 0 |
| Touch a `.citations.tsv` | 0 | 1 |

Before 2026-09-21, 207 of 1,255 pack squashes touched an `implement.md`
(16%). Since then, 7 of 267 did (3%). In the pack, progress already moved to
notes by habit. The rule, a reader and a renderer did not follow.

The stated cost, a progress-only commit that pays a gate and a review, is
small. One system squash is that case: `72de9862`, sd:1335 step 10, which
records LAN timings. `9bdd1767` changes the plan (operator decisions), so it
is not progress. Most `implement.md` edits ride along with code.

The larger cost is staleness. sd:2704's
[implement.md](../archive/2026-10/2026-10-05-satellite-gate-offload/implement.md) has nine
steps and nine unticked boxes on 2026-10-07. Eight steps merged in five pull
requests: pack #1374, #1377 and #1380, system #172 and #177. Step 1 is a
measurement, recorded in note #9971. The item's notes hold that progress, in
free text. The boxes did not move, though the three pack pull requests
could tick them at no extra cost.

The stale boxes are noise in `sd-status`. Its `open-step` class reads every
`- [ ]` on an item that is not done. On 2026-10-07 the pack's
`sd-status --actions` lists 55 actionable rows. 43 are `open-step`; 15 of
those come from `implement.md` files, and 8 name sd:2704 steps that merged.

What the measurement cannot show:

- Whether a ride-along `implement.md` edit caused a catch-up conflict. The
  sd:2783 conflict count did not split the 29 conflicts without
  `CHANGELOG.md` by path.
- How much progress was never written down. A missing log line leaves no
  trace.

## Goal

Step status and progress logs are `sd task` notes. A reader renders each
step's status from the plan and the notes. A commit changes `implement.md`
only when the plan changes. `prd.md` and `design.md` stay committed, because
agreements need review.

## Requirements

R1. A note records one step's status in a fixed first line,
    `step <id>: <status>`, and a second line, `plan: <digest> · <title>`.
    The digest covers the step's whole block in the plan (design point 1). The status is `started`, `done` or `dropped`.
    `sd task note --step <id>:<status>` writes both lines.

R2. The writer refuses a step id that the item's plan does not list, and
    names the ids the plan lists. It refuses when it finds no plan.

R3. `sd task steps <item>` prints one row per plan step: id, status, the
    note's evidence, its date and the step's title. `--json` prints the same
    rows. A note whose id the plan lacks prints as a row marked
    `not in plan`.

R4. A note counts for a step only when its id and its block digest both
    match the plan now. The newest counted note decides the status. With no
    counted note, a ticked `[x]` box reads `done`. With neither, the step is
    `open`. A note whose digest no longer matches is shown as `changed` and
    closes nothing.

R5. `sd-status` does not list an `implement.md` `- [ ] <id>.` box as
    `open-step` when R4 reads the step `done` or `dropped`. Every other box
    keeps today's reading, including every box in `prd.md`.

R6. In a `row` repository, `sd-docs-lint` fails an `implement.md` whose
    step list repeats a step id. It reads no database. A `file` repository
    keeps today's lint result.

R7. A repository whose `docs/work/.status-source` is not `row` behaves
    exactly as today.

R8. `.citations.tsv` stays committed, and rule 6 reads it as today.

R9. The plan template keeps `- [ ] <id>.` as the step marker. In a `row`
    repository, it and `WORKFLOW.md` say that progress goes to notes, never
    to a tick, and that `implement.md` changes only when the plan changes.
    In a `file` repository, both keep today's instruction to tick the box.

## Acceptance criteria

1. A test writes `step 2: done` for a fixture item whose plan lists steps
   1, 2 and 3 as `- [ ]` boxes. `sd task steps` reports 1 `open`, 2 `done` and 3 `open`.
2. A test writes `step 9: done` for the same item. The writer refuses and
   names 1, 2 and 3. No note is written. With the plan moved away, the
   writer refuses and names the path it read; no note is written.
3. A test writes `step 2: done`, then `step 2: dropped`. The step reads
   `dropped`. A ticked `[x]` box with no note reads `done`.
4. An `sd-status` fixture with the same item lists `open-step` rows for
   steps 1 and 3 only. Removing the note join lists all three.
5. `sd-docs-lint` fails a fixture `implement.md` that lists step 2 twice,
   and names the id, in a `row` repository. The same fixture in a `file`
   repository keeps the result it has on `main`. The lint passes every
   active item in this repository.
6. A fixture repository with `.status-source` set to `file`, and a `done`
   note for step 2, lists the same `open-step` rows and the same action
   text as on `main`. Applying the join or the new action text there fails
   the test.
7. After the backfill (implement.md, step 6), `sd task steps 2704` reports
   eight `done` steps, and the pack's `sd-status` lists at most one
   `open-step` row for sd:2704.
8. A test records `step 2: done`, then rewrites the plan so that id 2
   names a different, unticked step. `sd task steps` reports step 2 `open`
   and marked `changed`. `sd-status` lists its `open-step` row again.
   Dropping the digest comparison reads step 2 `done` and fails the test.
   Removing step 2, or splitting it into 2a and 2b, instead prints the
   note as a `not in plan` row, and 2a and 2b read `open`.
9. A test records `step 2: done`, then adds a nested requirement under step
   2 and keeps its step line unchanged. Step 2 reads `open`, marked
   `changed`. Hashing only the step line reads it `done` and fails the
   test. Each of these also reads `changed`: rewording only the title,
   merging step 3's block into step 2, cutting step 2's block to its
   first half, changing its size, and re-indenting one line inside a
   fenced code block in step 2 with every prose line unchanged. Collapsing
   whitespace inside the fence reads that last case `done` and fails the
   test.
10. A test records `step 2: done`, then moves step 2 above step 1, ticks its
   box and re-wraps its prose. Step 2 still reads `done`. Hashing the box
   mark or the raw prose whitespace fails the test.
11. A fixture main checkout lists steps 1 to 3, and a worktree of it adds
   step 4. Run from the worktree, `step 4: done` is written with the
   worktree's block digest. Run from the main checkout, it refuses and names
   1, 2 and 3. With `--checkout <worktree>` from elsewhere, it is written.
   After the worktree's plan is copied to main, step 4 reads `done` there.
   A `--checkout` of another repository refuses. Before the copy,
   `sd task steps` on the main checkout lists the note as `not in plan`. Reading only
   `item.repo` fails the first case.

## Out of scope

- A docs-only gate tier for the pack or system. The tier exists (sd:2072);
  declaring it is its own item (design point 0, Q1).
- A step table on the dashboard. The Details pane already lists the notes
  (Q9).
- Acceptance-criteria boxes in `prd.md` (Q11).
- A new note kind or a schema change (Q2).
