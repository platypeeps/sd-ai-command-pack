# Design — serving tree

The requirements are in [prd.md](prd.md).

## Shape

A serving tree is a clean clone on a detached `HEAD`, at
`${XDG_DATA_HOME:-~/.local/share}/sd-ai-command-pack/serving`. It sits outside `~/repos`, so
repo-sync never reads it as a checkout. It is a separate clone, not a
worktree: nothing lists it as active work, and worktree cleanup cannot reach
it. It is detached because activation names a commit, not a branch.

`bin/sd_install.py` tells the modes apart by `git rev-parse --abbrev-ref HEAD`:

| HEAD | `--pull` | `--rollback` |
| --- | --- | --- |
| `main` | fast-forward and render, as before | refused |
| detached (`HEAD`) | fetch, detach at `origin/main`, render | detach at `previousCommit`, render |
| any other branch | refused | refused |

Both refuse tracked and untracked changes before they run git.

## The way back

`cmd_user` writes the receipt. It now records `previousCommit` through
`previous_commit(recorded, commit)`:

- a render at a new commit records the commit the receipt held;
- a render at the same commit keeps the recorded `previousCommit`, so a
  re-render does not forget the way back.

`--rollback` is an ordinary activation. The commit it leaves becomes the new
`previousCommit`, so a second `--rollback` undoes the first. It refuses a
receipt with no `previousCommit` and a commit the tree does not have.

## Activation (review round 1)

`_activate` ran the whole activation in the installer already loaded.
Review round 2 replaced that: see the next section.

- **Contract.** The next activation runs the target commit's installer. So
  `--pull` and `--rollback` refuse a target whose `bin/sd_install.py`
  declares no `ACTIVATION_CONTRACT`. An installer from before the serving tree
  rejects `--rollback`, and no second rollback could come back from it.
- **Put back.** A render that refuses or raises returns the tree to the
  commit it started from, and the receipt to its bytes before the run. The
  commands served and the receipt never disagree, so `--rollback` after a
  failed update still starts from the commit the receipt names.

## Activation (sd:1118 review round 2)

- **The target renders itself.** After the checkout, `_activate` runs the
  target commit's installer as `--user`, so a change to rendering applies in
  the update that brings it. The loaded installer only supervises.
- **Put back.** A target render that fails returns the tree to the original
  commit and the receipt to its bytes, then renders the original commit
  again with the loaded installer, which is that commit's. It renders only
  when the restored receipt names the tree: on a failed first `--serve` the
  receipt names the working checkout, which stays installed (review round 10).
- **Prune last.** Renders and links the new checkout drops are pruned only
  after its receipt is written, so a failed install deletes nothing of the
  last one (review round 11).
- **Renders recover.** A failed `cmd_user` restores every render it wrote,
  not only the Codex policies, so a failed target leaves none of its files.

## `make setup` serves (sd:1118, second pass)

The ruling makes `make setup` the only step that moves the serving tree.
Its last line runs `bin/sd_install.py --serve` from the working checkout:

- **Clone.** A missing tree is cloned from the working checkout's `origin`
  into a spare directory beside it, detached at `origin/main`, then renamed
  into place. A clone cut short leaves no half-made tree.
- **Library.** The tree's `.venv` is a link to the environment `make setup`
  just provisioned with `sd_db`: the one running `--serve`, else the main
  checkout's `.venv` (review round 3). The clone's `info/exclude` names it,
  so `--verify` stays clean. A real `.venv` directory there is left alone.
  A `--pull` that refuses or fails puts the old link back (review round 4).
- **Hand-over.** `--serve` runs the tree's own installer as `--pull`, so the
  activation is the tree's code, as in the first pass.
- **Links.** `link_plan` gains a fourth state, `recorded`: a link the
  receipt names, still at its recorded target. The install moves it to the
  new checkout with one rename, and puts it back on a failure. Any other
  link stays foreign and refuses the run.
- **Hooks.** The install adds the new checkout's hook commands, then drops
  the ones the receipt recorded for the last checkout, so each hook runs
  once. A hook the receipt does not name stays. A later failure puts the
  settings bytes back, unless another writer changed them (review round 6).
- **Opt-out.** `make setup SERVE=no` provisions without moving the tree,
  for a rollback that should stay put.

## Verification

`verify_source` is unchanged. It compares `HEAD` with the receipt's commit
and reads `git status --porcelain`. A detached tree passes when it is clean
and at the rendered commit.

## Alternatives not taken

- A worktree of the working clone: it shares refs, and the lane's worktree
  cleanup and the fleet views would see it as work.
- A serving branch: activation would follow a moving name, not a commit.
