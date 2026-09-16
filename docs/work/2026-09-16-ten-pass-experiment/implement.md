# Implement — ten-pass-experiment

## Step checklist

- [ ] 1. This item's three pages land on main. (lane)
- [ ] 2. OWNER-ONLY: answer the open question, which vendor is "the other
      vendor" when Claude authors, as a note on sd:777.
- [ ] 3. OWNER-ONLY: passes 1 to 10. The other vendor reviews the next ten
      code pull requests; after each, one note on sd:777 in the template in
      `prd.md`, cost copied from the query there.
- [ ] 4. OWNER-ONLY: the report, one note on sd:777 with the accepted /
      rejected ratio over ten, the highest severity accepted, and the cost
      per pass.
- [ ] 5. OWNER-ONLY: the decision note, keep or remove the code review point.
- [ ] 6. The grep `grep -rn -E '[0-9]+ ?%|percent|threshold' bin/ skills/`
      names no line that disables a review point. At 2eafa78b it finds 33
      lines, the count sd:10 recorded, and none disables a point.

Steps 2 to 5 are the owner's. A lane may prepare step 1 and re-run step 6;
it runs no pass and writes no note.

## Verification

Step 1: `bin/sd-docs-lint` from the worktree ends `sd-docs-lint: clean`, and
`make check` runs green. Steps 2 to 5 cannot be verified by a lane; ten
notes of the template's shape on sd:777 are the evidence, read with
`bin/sd store item 777 --json`. Step 6 is the grep above, quoted.
