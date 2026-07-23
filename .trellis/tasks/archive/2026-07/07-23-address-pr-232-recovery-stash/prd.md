# Address stale PR 232 recovery stash

## Goal

Inspect the sole repository stash left by PR #232 conflict recovery, prove whether its changes are already merged or still unique, and remove it only when no work would be lost.

## Requirements

- Inspect the exact stash metadata, parents, changed paths, and patch without
  applying it to `main`.
- Compare every stashed change with merged `main` and the PR #232 history to
  determine whether the stash contains any unique work.
- Drop only the verified redundant stash. If any unique change remains,
  preserve the stash and report the evidence instead of guessing.
- Keep the working tree clean and limit all actions to this repository.

## Acceptance Criteria

- [x] The stash disposition is supported by path- and patch-level evidence.
- [x] A fully redundant stash is removed, or a non-redundant stash is retained
      with its unique contents identified.
- [x] `main` remains clean and synchronized with `origin/main`.
- [x] Final repository status reports the expected stash count with no new
      anomaly.

## Notes

This is a lightweight repository-cleanup task. It does not restore or apply
stash contents unless separate evidence shows the merged branch is missing
unique work.

## Disposition Evidence

- Dropped `stash@{0}` at object
  `bf8529654a3f5d25551f7e3038cc7ececeeb95ac`, created during the temporary
  PR #232 rebase attempt.
- Nineteen of twenty-three working-tree paths matched merged `main` exactly.
- The remaining spec, changelog, fleet ledger, and task metadata were older
  than merged corrections, release history, regenerated evidence, and archive
  state.
- The three staged blobs were earlier versions of the final working snapshot,
  and the stash's untracked parent referenced Git's empty tree.
