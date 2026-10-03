---
title: Serve the pack from a clean tree that moves by commit
created: 2026-10-03
branch: installer-serving-tree
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

1. Activation reads an exact merged commit. `--pull` in a clean, detached
   serving tree fetches `origin` and detaches at the commit `origin/main`
   names, then re-renders.
2. Strict verification stays sensitive to drift. `--verify` does not change.
3. Active planning work stays preserved. Nothing here touches the working
   checkout. `--pull` and `--rollback` refuse a dirty serving tree.
4. Refresh and rollback are documented and tested. The receipt records
   `previousCommit`, and `--rollback` returns to it.
5. Default paths do not change. A checkout on `main` keeps today's `--pull`.

## Out of scope

- Creating the serving clone, running an install and changing launchd: these
  are operator steps, listed in the pull request.
- The merge lane's fast-forward of the working checkout, and the system
  repository's `bin-links.sh` default (`SD_PACK_ROOT`).
