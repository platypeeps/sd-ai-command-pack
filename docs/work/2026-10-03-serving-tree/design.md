# Design — serving tree

The requirements are in [prd.md](prd.md).

## Shape

A serving tree is a clean clone on a detached `HEAD`, for example
`~/.local/share/sd-ai-command-pack/serving`. It sits outside `~/repos`, so
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

## Verification

`verify_source` is unchanged. It compares `HEAD` with the receipt's commit
and reads `git status --porcelain`. A detached tree passes when it is clean
and at the rendered commit.

## Alternatives not taken

- A worktree of the working clone: it shares refs, and the lane's worktree
  cleanup and the fleet views would see it as work.
- A serving branch: activation would follow a moving name, not a commit.
