# Design: recovery-artifact ownership and cleanup

## Design Summary

Introduce a private user-local registry for recovery artifacts created by
pack-owned workflows. Each stash or linked worktree receives a versioned
receipt immediately after creation. The creating workflow owns normal cleanup;
status classifies leftovers read-only, and housekeeping may retire only
artifacts whose exact identity and no-loss predicate are proven.

## Receipt Model

A receipt contains:

- schema version and unique safe artifact ID;
- stable repository identity without embedding an uncontrolled raw path;
- artifact type and exact Git identity (stash object or worktree/gitdir pair);
- creating command, run/owner identity, purpose, and timestamp;
- original full head and bounded expected destination/outcome;
- type-specific cleanup predicate and last reconciliation result.

Store receipts below the existing user-local SD state root using atomic
replacement and private permissions. Receipt files are never tracked and must
not share ownership with Git's own metadata.

## Lifecycle

1. A workflow creates an artifact through a typed helper.
2. The helper validates the created identity and atomically records its
   receipt. Registration failure triggers immediate verified rollback or a
   visible stop.
3. Normal success executes owner cleanup in `finally` and removes the receipt
   only after the artifact is gone.
4. On restart, status reconciles receipts against Git and the owner ledger.
5. Housekeeping applies type-specific proof and cleans only `safe-cleanable`
   artifacts. Ambiguous cases remain preserved and selectable for review.

## Cleanup Proof

Worktrees require an exact registered contained path, matching Git common
directory, clean status, no active owner/lock, and a retained/reachable commit.
Stashes require exact object identity and comparison of index, working-tree,
and untracked parents against recorded successful state. Any unique or
unverifiable content is preserve-only.

Foreign artifacts without receipts are reported as unowned. Missing artifacts
with receipts produce a stale-receipt finding; neither case is adopted or
deleted automatically.

## Concurrency And Rollback

Use a short-lived exclusive registry/artifact lock with bounded stale-owner
recovery. Re-read receipt and Git identity at the deletion boundary. Rollback
stops creating new receipts but leaves existing receipts readable for manual
inspection; it never bulk-deletes registry or Git state.
