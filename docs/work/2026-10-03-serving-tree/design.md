# Design — serving tree

The requirements are in [prd.md](prd.md).
sd:3009 replaced the sd:1118 environment slots with a plain clone (operator ruling, 2026-10-08).

## Shape

A serving tree is a plain clone on a detached `HEAD`, at
`${XDG_DATA_HOME:-~/.local/share}/sd-ai-command-pack/serving`. It sits outside `~/repos`, so
repo-sync never reads it as a checkout. It is a separate clone, not a
worktree: nothing lists it as active work, and worktree cleanup cannot reach
it. It is detached because it serves a commit, not a branch.

Git and `make setup` move it; the installer keeps no state of its own for it:

| Action | In the tree |
| --- | --- |
| Update | `git fetch && git checkout --detach origin/main && make setup` |
| Roll back | `git checkout --detach <commit> && make setup SERVE=no && .venv/bin/python bin/sd_install.py --user`; `git reflog` lists the commits it served |

`make setup` builds the tree's own `.venv` and ends with `bin/sd_install.py --serve`.
A rollback skips that step with `SERVE=no` and renders with `--user`: a commit from before sd:3009 refuses `--serve`
in the tree, and one from before sd:1118 has no such step.
In the tree, `--serve` renders it with `--user`.
In any other checkout, `--serve` clones `origin` into the tree the first time, then runs the update.
It splits `make setup` into `make setup SERVE=no` and the tree's own `--serve` under the tree's `.venv` python,
so `--home` and `--bin-dir` reach the tree's installer and the render reads the `sd_db` just built.

## What it gives up

While `make setup` rebuilds `.venv`, served commands find it marked mid-provision and load no `sd_db`.
Between the checkout and the render, the tree's new code runs with the last render's links and hooks.
sd:1118 built beside the tree to close both windows, at 688 installer lines and 19 review rounds.
Before sd:1118 the working checkout had the same windows.

## Moving over from the A/B slots

`make setup` detaches a `.venv` link and builds a directory in its place, so a tree with `.venv -> .venv-b`
gets its own `.venv` on its first run. The tree's `--serve` then removes `.venv-a`, `.venv-b` and the
`serving.lock` beside the tree. It removes nothing while `.venv` is still a link.

## Verification

`verify_source` is unchanged. It compares `HEAD` with the receipt's commit
and reads `git status --porcelain`. A detached tree passes when it is clean
and at the rendered commit.

## Alternatives not taken

- A worktree of the working clone: it shares refs, and the lane's worktree
  cleanup and the fleet views would see it as work.
- A serving branch: the tree would follow a moving name, not a commit.
- The sd:1118 slots, lock and receipt-driven link moves: sd:3009 deleted them.
