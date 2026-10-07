# Implement — implement progress in notes

Pack pull requests A to C, and one small system pull request. The design is
in [design.md](design.md). The steps assume the recommended answers to Q1 to
Q11; a different ruling changes the step it names.

Progress on these steps goes to `sd task` notes on sd:2784, as the design
proposes. Nobody ticks a box below; this file changes only when the plan
changes.

Each step names its check and the result that means failure. Each check must
fail on `main` before the step's code lands.

## Step checklist

- [ ] 1. `bin/sd_steps.py`: plan parser, note line, join. Size S, 2 h. PR A.
      - `plan_steps(text)` returns `(id, title, ticked)` per step, from the
        first `## Steps`, `## Step checklist` or `## Order` section (design
        point 2). Fenced code is skipped.
      - `step_line(id, status, title, evidence=None)` writes the first line
        and the `title:` line; `read_step_line(body)` reads both, or returns
        None.
      - `step_status(steps, notes)` applies design point 3: a note counts
        only when id and title match; newest counted note, then `[x]`, then
        `open`. A note whose title differs marks the row `changed`. Notes
        for ids the plan lacks come back marked `not in plan`; a note with
        no `title:` line comes back `unbound`.
      - Check: `tests/test_sd_steps.py` covers each section heading, `2a`
        ids, a fenced example that is skipped, a `[x]` box with no note, a
        note that overrides `[x]`, two notes for one id, an unbound note, and a
        plan rewritten after a `done` note so id 2 names other work (PRD
        criterion 8). Swapping "newest" for "first" fails the two-note case.
        Dropping the title comparison fails criterion 8.
- [ ] 2. `sd task note --step` and `sd task steps`. Size M, 3 h. PR A.
      - In `bin/sd_work.py`, beside the existing `note` parser:
        `--step <id>:<status>` and `--evidence`; `--kind` absent or
        `comment`.
      - Find the plan through the item's work directory (design point 3).
        Refuse an id the plan lacks and list the plan's ids (R2). No plan:
        refuse and name the path read.
      - `sd task steps <item> [--json]` prints the rows of design point 3.
      - Check: PRD acceptance criteria 1, 2 and 3 pass against a fixture
        database and checkout. Criterion 2 also asserts that the note count
        is unchanged. Removing the id check fails criterion 2.
- [ ] 3. `sd-status` subtracts recorded steps. Size S, 2 h. PR B.
      - `_step_rows` in `bin/sd-status`: for `implement.md` in a `row`
        repository, skip a `- [ ] <id>.` box whose step reads `done` or
        `dropped`. Keys and every other box stay as today.
      - Add the second remedy to the action text. Update the `EXCLUDED`
        checkbox line, and the `open-step` row in
        `skills/sd-status/SKILL.md`, which mirrors the class table.
      - Check: PRD criteria 4, 6 and the `sd-status` half of 8 pass.
        Removing the join fails criterion 4.
- [ ] 4. `sd-docs-lint` rule 1 refuses a repeated step id. Size S, 1 h. PR B.
      - Reuse `plan_steps`. The failure names the item, the file and the id.
      - Check: PRD criterion 5 passes, and `make docs-lint` passes on this
        repository. Before the system pin moves past PR B, a system pull
        request renumbers the second list in sd:2107's plan. System's
        `sd-docs-lint` then passes with the new pack.
- [ ] 5. Template and documentation. Size S, 2 h. PR C.
      - `skills/sd-plan/templates/implement.md`: keep `- [ ] <id>.` steps;
        add one line: record progress with
        `sd task note <item> --step <id>:<status>`, never by a tick.
      - `skills/sd-plan/templates/prd.md`: the `## Log` section only where
        `.status-source` is not `row` (Q7), as its status instruction does.
      - `WORKFLOW.md`: the sd:1933 paragraph records an observed criterion
        as a note in a `row` repository (Q7). One paragraph says what a plan
        change is (design point 7).
      - `skills/sd-plan/SKILL.md` and `docs/work/README.md`: one line each.
      - Check: `make check` passes. `grep -n "## Log"
        skills/sd-plan/templates/prd.md` shows the section only inside the
        `file` branch of the template.
- [ ] 6. Backfill merged steps. Size S, 0.5 h. No pull request.
      - The lane writes eight `step <id>: done` notes on sd:2704 from the
        item's notes and merge shas (design point 8). It runs
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
