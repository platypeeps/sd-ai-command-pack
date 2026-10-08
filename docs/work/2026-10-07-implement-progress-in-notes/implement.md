# Implement — implement progress in notes

Pack pull requests A to C, and one small system pull request. The design is
in [design.md](design.md). The steps follow the operator ruling of 2026-10-07,
which accepted the recommended answers to Q1 to Q11.

Progress on these steps goes to `sd task` notes on sd:2784, as the design
proposes. Nobody ticks a box below; this file changes only when the plan
changes.

Each step names its check and the result that means failure. Each check must
fail on `main` before the step's code lands.

## Step checklist

- [ ] 1. `bin/sd_steps.py`: plan parser, note line, join. Size S, 2 h. PR A.
      - `plan_steps(text)` returns `(id, title, ticked, digest)` per step, from the
        first `## Steps`, `## Step checklist` or `## Order` section (design
        point 2). Fenced code is skipped. The digest hashes the step's block
        as design point 1 defines it.
      - `step_line(id, status, step, evidence=None)` writes the first line
        and the `plan:` line; `read_step_line(body)` reads both, or returns
        None.
      - `step_status(steps, notes)` applies design point 3: a note counts
        only when id and digest match; newest counted note, then `[x]`, then
        `open`. A note whose digest differs marks the row `changed`. Notes
        for ids the plan lacks come back marked `not in plan`; a note with
        no `plan:` line comes back `unbound`.
      - `plan_checkout(item, given=None)` returns the checkout design
        point 3 orders: `given`, else the current checkout of the item's
        repository, else `item.repo`. A `given` checkout of another
        repository raises, naming both. Every caller in steps 2 and 3 uses
        it; none resolves a checkout on its own.
      - Check: `tests/test_sd_steps.py` covers each section heading, `2a`
        ids, a fenced example that is skipped, a `[x]` box with no note, a
        note that overrides `[x]`, two notes for one id, an unbound note, and a
        plan changed after a `done` note: each row of design point 3's table
        (PRD criteria 8, 9 and 10). Swapping "newest" for "first" fails the
        two-note case. Dropping the digest comparison fails criterion 8;
        hashing only the step line, or collapsing whitespace inside a
        fence, fails criterion 9; hashing the box mark fails criterion 10.
- [ ] 2. `sd task note --step` and `sd task steps`. Size M, 3 h. PR A.
      - In `bin/sd_work.py`, beside the existing `note` parser:
        `--step <id>:<status>` and `--evidence`; `--kind` absent or
        `comment`.
      - Find the plan through the item's work directory, in the checkout
        `plan_checkout` picks (design point 3): `--checkout`, else the
        current checkout of the item's repository, else `item.repo`.
        `plan_checkout` lives in `bin/sd_steps.py`, step 1. Refuse an id
        the plan lacks and list the plan's ids (R2). No plan: refuse and
        name the path read.
      - `sd task steps <item> [--json]` prints the rows of design point 3.
      - Check: PRD acceptance criteria 1, 2, 3 and 11 pass against a
        fixture database and checkout, criterion 11 with a fixture
        worktree. Criterion 2 also asserts that the note count
        is unchanged. Removing the id check fails criterion 2.
- [ ] 3. `sd-status` subtracts recorded steps. Size S, 2 h. PR B.
      - `_step_rows` in `bin/sd-status`: for `implement.md` in a `row`
        repository, skip a `- [ ] <id>.` box whose step reads `done` or
        `dropped`, with the plan from `plan_checkout(item, <its checkout>)`.
        The second remedy in the action text is `row` only too. Keys and every other box stay as today.
      - Add the second remedy to the action text. Update the `EXCLUDED`
        checkbox line, and the `open-step` row in
        `skills/sd-status/SKILL.md`, which mirrors the class table.
      - Check: PRD criteria 4, 6 and the `sd-status` half of 8 pass.
        Removing the join fails criterion 4.
- [ ] 4. `sd-docs-lint` rule 1 refuses a repeated step id. Size S, 1 h. PR B.
      - Reuse `plan_steps`. The failure names the item, the file and the id.
        The rule runs only where `.status-source` is `row`.
      - Check: PRD criterion 5 passes, both halves. Running the rule in a
        `file` repository fails its second half. `make docs-lint` passes on
        this repository. Before the system pin moves past PR B, a system pull
        request renumbers the second list in sd:2107's plan. System's
        `sd-docs-lint` then passes with the new pack.
- [ ] 5. Template and documentation. Size S, 2 h. PR C.
      - `skills/sd-plan/templates/implement.md`: keep `- [ ] <id>.` steps.
        Add a template-instruction comment that reads `.status-source`, as
        the `prd.md` template's status comment does. With `row`: record
        progress with `sd task note <item> --step <id>:<status>`, never by a
        tick, and write a change to a step inside its block. With `file`:
        tick the box (R7, R9).
      - `skills/sd-plan/templates/prd.md`: the `## Log` section only where
        `.status-source` is not `row` (Q7), as its status instruction does.
      - `WORKFLOW.md`: the sd:1933 paragraph records an observed criterion
        as a note in a `row` repository (Q7). One paragraph says what a plan
        change is (design point 7), for `row` repositories only.
      - `skills/sd-plan/SKILL.md` and `docs/work/README.md`: one line each.
      - Check: `make check` passes. `grep -n "## Log"
        skills/sd-plan/templates/prd.md` shows the section only inside the
        `file` branch of the template. `grep -n "never by a tick"` shows the
        text only inside the `row` clause of the implement template's
        comment.
- [ ] 6. Backfill merged steps. Size S, 0.5 h. No pull request.
      - The lane writes eight `step <id>: done` notes on sd:2704 from the
        item's notes and merge shas (design point 9). It runs
        `sd-status --actions` in system and backfills any merged step listed.
      - Check: PRD criterion 7. `sd task steps 2704` reports eight `done`,
        and the pack's `sd-status --actions` lists at most one `open-step`
        row for sd:2704. Nine rows means the join is not reached.
- [ ] 7. Measure, two weeks after PR C. Size S, 0.5 h.
      - Re-run the prd.md measurement over those two weeks.
      - Expect no squash whose only reason is progress. Count the
        `open-step` rows that name a merged step.
      - Answer Q4 from the result: if the lane missed step notes, add the
        `sd-ship merge` writer then.

## Estimate

| Step | Hours | Pull request |
| --- | --- | --- |
| 1 | 2 | A |
| 2 | 3 | A |
| 3 | 2 | B |
| 4 | 1 | B, plus one small system pull request |
| 5 | 2 | C |
| 6 | 0.5 | none |
| 7 | 0.5 | none |
| Total | 11 | |

Review rounds are not included. At an assumed 1 h per pull request, the
total is about 15 h.

The docs-only gate tier (Q1) is a separate item and is not estimated here.
