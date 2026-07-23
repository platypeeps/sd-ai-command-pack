# Remove detached legacy archive worktree

## Goal

Validate and safely remove the obsolete detached legacy archive worktree without losing unmerged or uncommitted work.

## Requirements

- Inspect `/private/tmp/sd-pack-legacy-archive.Up7NVE` before removal.
- Confirm the linked checkout has no uncommitted or untracked files.
- Confirm detached commit `9bdbaf783d979bd80a5955db4ab2aa4c8d8ae3cf` remains reachable from a retained ref, or preserve it before removal.
- Remove only the validated legacy worktree using Git worktree management.
- Verify the primary checkout remains clean and synchronized afterward.

## Acceptance Criteria

- [x] The legacy checkout is proven clean before removal.
- [x] Its detached commit is proven safely retained.
- [x] The exact legacy worktree no longer appears in `git worktree list`.
- [x] Repository status reports a clean synchronized `main` with no new anomalies.

## Notes

- This task changes no product code; it repairs local repository lifecycle state.
- Pre-removal evidence: the checkout was clean and unused; commit `9bdbaf783d979bd80a5955db4ab2aa4c8d8ae3cf` was an ancestor of `main` and was retained by `main`, `origin/main`, and `v0.30.7`.
- Post-removal evidence: the path is absent and `git worktree list --porcelain` reports only the primary checkout.
