# Phase-0 dead-surface cleanup

## Problem

The 2026-08-08 KISS audit found dead and contradictory surfaces that cost
review attention on every PR touching them:

- `review-full-check.sh` (+ its `templates/` twin) is unreachable: nothing in
  the registry invokes it; docs still reference it.
- A duplicate installed manifest receipt exists that nothing reads.
- Four documentation contradictions: sd-watch-pr described inconsistently at
  three sites; kcov count wrong; fleet-scripts template carve-out described
  contrary to actual install behavior.

## Requirements

1. Delete `review-full-check.sh` and template twin; remove registry/doc/test
   references (enumerate by repo-wide grep, not from this list).
2. Remove the duplicate installed manifest receipt IF a repo-wide grep proves
   nothing reads it; otherwise record the reader and keep.
3. Fix the four doc contradictions; each fix cites the authoritative behavior.

## Acceptance criteria

- [ ] Repo-wide grep for the deleted script name returns 0 hits outside
      CHANGELOG/history.
- [ ] Receipt decision recorded with the grep evidence either way.
- [ ] The four contradiction sites agree with observed behavior.
- [ ] Full check green; mirrors byte-identical.

## Evidence

2026-08-08 KISS audit (3.23 MB committed self-duplication across 231 groups;
173,615 bytes of drift-proof machinery; triple local-review implementation).
