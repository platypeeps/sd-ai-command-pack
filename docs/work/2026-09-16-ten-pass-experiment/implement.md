# Implement — ten-pass-experiment

## Step checklist

- [x] 1. This item's three pages land on main. (lane) Done 2026-09-17: #991
      merged as e2810a6f, and `prd.md`, `design.md` and `implement.md` are on
      main at ea32e76a.
- [ ] 2. OWNER-ONLY: answer the open question, which vendor is "the other
      vendor" when Claude authors, as a note on sd:777.
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
      #1011 removed. Net one. This box stays open: the grep is the item's
      done-when clause and is run again after the tenth pass.

Steps 2 to 5 are the owner's. A lane may prepare step 1 and re-run step 6;
it runs no pass and writes no note.

## Verification

Step 1: `bin/sd-docs-lint` from the worktree ends `sd-docs-lint: clean`, and
`make check` runs green. Steps 2 to 5 cannot be verified by a lane; ten
notes of the template's shape on sd:777 are the evidence, read with
`bin/sd store item 777 --json`. Step 6 is the grep above, quoted.
