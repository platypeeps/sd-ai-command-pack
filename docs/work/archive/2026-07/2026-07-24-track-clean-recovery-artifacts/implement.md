# Implementation plan: recovery-artifact ownership and cleanup

## 1. Specify receipts and reconciliation fixtures

- Add schema fixtures for stash/worktree ownership, live/stale owner, missing
  receipt/artifact, foreign artifact, replaced identity, and corrupt state.
- Reproduce the redundant PR #232 stash and detached clean worktree as safe
  cleanup cases, plus unique/dirty variants that must be preserved.

## 2. Implement the private registry

- Reuse shared bounded readers, atomic writes, private directory handling, and
  owner/lock conventions.
- Add typed create/register/reconcile/cleanup operations with no shell-string
  execution and controlled diagnostics.
- Roll back a newly created artifact only through exact identity if receipt
  registration fails.

## 3. Integrate owners and observers

- Route pack-created recovery stash/worktree operations through the helper and
  add success-path `finally` cleanup.
- Add read-only status classifications and references.
- Add conservative housekeeping cleanup plus portable structured interaction
  for ambiguous content; default to preserve.

## 4. Validate destructive boundaries

- Test restart, concurrency, stale locks, symlinks, permissions, replaced
  paths, dirty worktrees, unique stash parents, and mutation-boundary rereads.
- Prove status performs no writes and housekeeping touches only exact validated
  artifacts.
- Run focused tests, generated parity, `make sync`, and `make check`.
