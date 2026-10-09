---
title: Serve the pack from a clean tree that moves by commit
created: 2026-10-03
branch: feat/serving-checkout-1118
item: sd:1118
---
# PRD — serving tree

## Problem

The machine runs the pack from the checkout people also work in,
`~/repos/platypeeps/sd-ai-command-pack`. Its readers are:

- the `~/bin/common/sd*` links;
- three Claude hooks;
- the install receipt;
- the `.venv` that the dashboard and runner services run.

The same checkout holds planning drafts and is the clone the worktrees hang
off. The merge lane fast-forwards it after each ship, with no re-render.
`--verify` is strict on purpose: untracked work fails `source_not_clean`, and
a moved `HEAD` fails `source_commit_changed`. So it cannot report green while
active work sits in the serving checkout.

The operator ruled on 2026-09-30: serve `~/bin/common` from a dedicated clean
checkout of `origin/main` that only setup updates, and that nobody works in.

## Requirements

1. The tree serves an exact merged commit: `git checkout --detach
   origin/main` in the tree, then `make setup`, which re-renders.
2. Strict verification stays sensitive to drift. `--verify` does not change.
3. Active planning work stays preserved. Nothing here touches the working
   checkout. Git refuses a checkout over conflicting changes in the tree.
4. Update and rollback are documented and tested. Rollback is `git checkout
   <commit>` and `make setup` in the tree (sd:3009).
5. Default paths do not change. A checkout on `main` keeps today's `--pull`.
6. `make setup` creates and refreshes the serving tree (`--serve`).

## Out of scope

- Running `make setup` on the operator's machine, and pointing
  `~/bin/common` at the serving tree: operator steps, listed in the pull
  request.
- The merge lane's fast-forward of the working checkout, and the system
  repository's `bin-links.sh` default (`SD_PACK_ROOT`).
