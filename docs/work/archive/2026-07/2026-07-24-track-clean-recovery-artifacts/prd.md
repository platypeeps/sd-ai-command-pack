---
title: Track and clean recovery artifacts
status: done
created: 2026-07-24
branch: codex/stabilize-self-hosted-delivery-lifecycle
---
# Track and clean recovery artifacts

## Goal

Make temporary recovery stashes and worktrees observable, owned, and safely
retired so successful workflows do not leave separate cleanup tasks behind.

## Confirmed Evidence

- Session 202 existed solely to prove a PR #232 recovery stash contained no
  unique work before dropping it. The audit compared 23 paths; 19 matched and
  four had been superseded.
- Session 203 separately verified and removed a clean detached legacy archive
  worktree after proving its commit remained reachable.
- Current status and housekeeping can list Git artifacts, but no durable
  pack-owned record explains who created a recovery artifact, why it exists,
  or which evidence makes cleanup safe.

## Dependencies And Boundaries

- Parent: `07-22-streamline-sd-skill-workflows`.
- Reuse the work-loop's user-local, versioned, atomic, private-state patterns;
  do not place recovery receipts in tracked repository paths.
- `sd-status` remains read-only. Housekeeping is the only general cleanup owner,
  while the creating workflow owns immediate success-path cleanup.
- Never run broad `git clean`, destructive reset, or unverified stash/worktree
  deletion.

## Requirements

- R1: Define a versioned user-local recovery-artifact receipt keyed by stable
  repository identity and a unique artifact ID. Record type, creating workflow
  and run, purpose, creation time, original full head, artifact identity,
  intended cleanup condition, and bounded recovery guidance.
- R2: Support only explicitly registered pack-created stash and linked-worktree
  artifacts. Validate receipt schema, containment, permissions, symlink state,
  Git identity, and artifact existence before trusting it.
- R3: Register the receipt atomically immediately after artifact creation. If
  registration fails, either remove the just-created artifact through the same
  verified owner or stop before continuing with a visible recovery diagnostic.
- R4: The creating workflow removes its artifact and receipt in a `finally`
  path after successful recovery. Interruption preserves both for a later
  evidence-based decision.
- R5: `sd-status` reports each receipt as active, safely cleanable, needs
  review, missing-artifact, or unowned-artifact with one bounded reference. It
  never creates, repairs, or deletes receipts or Git artifacts.
- R6: Housekeeping may automatically remove only a pack-owned artifact whose
  receipt matches exactly, owner is no longer live, cleanup predicate is
  proven, and content/commit reachability checks establish that no unique work
  will be lost. Ambiguous or unique stash content requires a structured user
  decision and defaults to preserve.
- R7: Worktree cleanup requires the exact registered path, a clean worktree,
  matching Git common directory, no live lock/owner, and a reachable or
  otherwise explicitly retained commit. Stash cleanup requires exact stash
  object identity and proof that its index, worktree, and untracked components
  are redundant or superseded.
- R8: Reconcile missing receipts and foreign artifacts conservatively: report
  them, provide inspection commands, and never claim ownership or delete them.
- R9: Keep receipt paths and diagnostics bounded and private; durable JSON must
  not expose secrets, remote URLs, or uncontrolled raw filesystem errors.

## Acceptance Criteria

- [x] Successful recovery creates, uses, and removes a receipt/artifact pair
  without leaving a stash, linked worktree, or stale registry entry.
- [x] Interrupted fixtures survive restart and produce the same deterministic
  status classification and recovery guidance.
- [x] Clean reachable worktrees and demonstrably redundant stashes can be
  retired; dirty, unique, foreign, mismatched, symlinked, or live-owned
  artifacts are preserved.
- [x] Missing artifact, missing receipt, corrupt receipt, replaced path, stale
  owner, and concurrent cleanup cases fail safely without broad Git mutation.
- [x] Status is byte-for-byte read-only and housekeeping touches only the exact
  validated artifact and receipt.
- [x] Focused lifecycle, restart, concurrency, permission, symlink, and
  destructive-action tests plus `make check` pass.

## Out Of Scope

- Taking ownership of user-created stashes or worktrees.
- Automatically deleting content whose redundancy cannot be proven.
- Replacing Git's stash or worktree implementation.
