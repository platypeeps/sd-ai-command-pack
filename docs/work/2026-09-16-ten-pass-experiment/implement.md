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
