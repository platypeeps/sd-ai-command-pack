---
title: sd worktree prune removes registrations with no directory
created: 2026-09-28
---
# PRD — sd worktree prune

## Problem

Today's Health strip showed "16 abandoned worktrees: registered, no directory
left" at 2026-09-27T14:30Z, and the Management page showed 23 in its sample
data. Both pages offer Prune, off with the reason "no CLI verb: sd worktree has
restore and resume only" (ui-design, verb check of 2026-09-28). The mockups write
`sd sessions prune --abandoned`; there is no `sessions` group, and `sd worktree`
is the group that owns registrations (`restore`, `resume`, checked with
`--help` on 2026-09-28).

A registration whose directory is gone can only be removed by hand in the
database. The count grows with every worktree deleted from the shell, and the
row stays amber for a fact nobody can act on.

## Requirements

1. `sd worktree prune --abandoned [--dry-run] [--json]` removes every
   registration whose directory no longer exists and prints each one it
   removed. `--dry-run` prints the same list and changes nothing.
2. A registration whose directory exists is never touched by `--abandoned`,
   whatever its branch state.
3. The verb refuses to run without a selector flag, so a bare `sd worktree
   prune` removes nothing.
4. The Today row for abandoned worktrees reads zero after a prune, with no
   other change.
5. The mockups update from `sd sessions prune` to the verb as built, and
   `designs/tools/collect-counts.mjs` regenerates `data/commands.js` (ui-design,
   `today.html` and `management.html`).

Out of scope: worktrees whose branch merged and whose directory still holds
build output. That is a second selector, `--merged`, for its own item; the
temp-data rule in the operator's instructions names the disk it protects.

## Acceptance criteria

- [ ] `sd worktree prune --help` lists `--abandoned` and `--dry-run`.
- [ ] With one registration pointing at a deleted directory, `--dry-run` names
      it and the row survives; without `--dry-run` the row is gone.
- [ ] A registration with a live directory survives `--abandoned`.
- [ ] `sd worktree prune` with no selector exits non-zero.
- [ ] `designs/v2/commands.html` shows no prune declaration with an off reason.

## References

- ui-design `products/system/designs/v2/today.html` (`sessions.prune`) and
  `management.html` (`wt.prune`).
- `bin/sd_restore.py`, the existing reader of worktree registrations.

## Log

- 2026-09-28 created
