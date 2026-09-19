# Implement — ten-pass-experiment

## Current status — 2026-09-18

Blocked. The user cancelled external provider reviews. No qualifying Codex pass exists on sd:777.
Resume only after explicit authorization to run these reviews. Steps 3 through 6 remain open.

## Step checklist

- [x] 1. This item's three pages land on main. (lane) Done 2026-09-17: #991
      merged as e2810a6f, and `prd.md`, `design.md` and `implement.md` are on
      main at ea32e76a.
- [x] 2. OWNER-ONLY: answer the open question, which vendor is "the other
      vendor" when Claude authors, as a note on sd:777. Done 2026-09-17: the
      owner's decision note on sd:777 names Codex; `design.md` records it
      (#1030, 7f4e0c3d).
- [ ] 3. OWNER-ONLY: passes 1 to 10. The other vendor reviews the next ten
      code pull requests; after each, one note on sd:777 in the template in
      `prd.md`, cost copied from the query there, or in the `estimate` form
      when the query has no row for the pass. A reversal of the shape
      follows the re-record rule in `design.md`.
- [ ] 4. OWNER-ONLY: the report, one note on sd:777 with the accepted /
      rejected ratio over ten, the highest severity accepted, and the cost
      per pass. Each reported cost keeps its marker from the note, copied or
      `estimate`; the report carries no combined total over the ten and no
      sum that mixes a copied cost with an estimate.
- [ ] 5. OWNER-ONLY: the decision note, keep or remove the code review point.
- [ ] 6. The grep `grep -rn -E '[0-9]+ ?%|percent|threshold' bin/ skills/`
      names no line that disables a review point. At 2eafa78b it finds 33
      lines, the count sd:10 recorded, and none disables a point. Re-run
      2026-09-17 at ea32e76a: 34 lines, none disables a point. The drift,
      counting a line reworded in place as staying: R10-D1's idle-planning
      threshold moved, six lines leaving `bin/sd_sweep.py`, `bin/sd` and
      `bin/sd-status` and eight arriving in `bin/sd_lib.py`, `bin/sd_rules.py`
      and `bin/sd-status`, plus three reworded in place; and one unrelated
      `for-each-ref --format` line left `bin/sd-status` with the function
      #1011 removed. Net one. Re-run 2026-09-18 at cf420fca: 48 lines,
      none disables a point. The drift is 14 arrivals and no departure.
      Every arrival is incidental to this item. Nine in `bin/sd-review`
      and seven in `bin/sd_registry.py` are sd:788's meter, where
      `percent` names a remaining quota and not a review. Four in
      `bin/sd_lib.py` and three in `bin/sd_rules.py` are R10-D1's
      45-day idle-planning threshold, already recorded as moved. One is
      the same unrelated `for-each-ref --format` line, in
      `bin/sd-status`. One arrival reads like a review control and is
      not one: `source:bin/sd-review::dispose`, where
      `threshold = BLOCKING_ORDER[floor]` labels a finding `blocking`
      or `advisory`. The pass still runs. Every finding is still
      collected and still reported. Only the label moves, and the
      function's own docstring records that nothing is written to a
      pull request, a label, a check run or any file. This box stays
      open: the grep is the item's done-when clause and is run again
      after the tenth pass.

Steps 2 to 5 are the owner's. A lane may prepare step 1 and re-run step 6;
it runs no pass and writes no note.

## Verification

Step 1: `bin/sd-docs-lint` from the worktree ends `sd-docs-lint: clean`, and
`make check` runs green. Steps 2 to 5 cannot be verified by a lane; ten
notes of the template's shape on sd:777 are the evidence, read with
`bin/sd store item 777 --json`. Step 6 is the grep above, quoted.

## Amendment — the post-merge position (2026-09-18)

The owner ruled on 2026-09-18 that a pass runs after its pull request merges.
`prd.md`'s amendment section holds the settled definitions and `design.md` the
decisions. Steps 3, 4 and 5 stay OWNER-ONLY and stay open; their wording is
amended by that section rather than rewritten here, and no box below is ticked
by this change. The status above still stands: external provider reviews are
cancelled, so no pass runs and no dispatch is built until the owner reverses
that in writing.

Two additions to the checklist, both open, both waiting on that reversal:

- [ ] 7. The trigger. New work, not configuration: nothing fires on
      `pull_request: closed`. The two shapes are in `prd.md`; the recommended
      one is a step in the merge lane's own checkout, after the prescribed
      `gh pr merge --squash --match-head-commit`, running
      `sd-review --provider codex --scope branch --base <parent sha>` with the
      owner's own key and writing nothing to GitHub. The other shape, a workflow
      on `pull_request: closed` gated on a merged check, needs `OPENAI_API_KEY`
      in CI and expands a lane that today holds `contents: read` and asks for
      nothing. Neither is built by this item. Verifiable by a lane once built:
      the dispatch resolves `<parent>..<squash>` as its subject, and the run
      writes an `assignment` row with `role = 'reviewer'` and a `cost` row with
      `source = 'run'` that the query in `prd.md` then selects.
- [ ] 8. OWNER-ONLY: the report states the two costs the post-merge position
      carries, that the "would this have blocked the merge" signal is gone and
      that the second vendor saw code Copilot had already reviewed and the owner
      had already fixed. A report that gives the ratio without both is not the
      report this item asks for.

## Verification (continued)

This amendment's own checks, run on the branch that lands it:

- The review table's code row is byte-identical in `WORKFLOW.md` and
  `.claude/rules/sd-planning-adversarial-review.md` and still contains
  `Code, before merge`, so `source:tests/test_sd_ship_skill.py::code_row_cap`
  still finds it. `tests.test_sd_ship_skill` and `tests.test_workflow_policy`
  are the check.
- `tests.test_doc_citations` holds `SYMBOL_ANCHORED_CITATIONS` at its baseline:
  every citation this amendment adds into a function names
  `source:<path>::<symbol>`, so no count rises.
- `bin/sd-docs-lint` ends `sd-docs-lint: clean`.
