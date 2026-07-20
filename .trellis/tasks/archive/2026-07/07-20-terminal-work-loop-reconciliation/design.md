# Terminal Work-Loop Reconciliation Design

## Overview

Add an explicit terminal-reconciliation boundary alongside the existing active
work-loop state machine. The command records verified facts that occurred after
the run stopped, but it does not reinterpret those facts as an active phase
advance.

The key separation is:

- `current`: immutable historical evidence captured by the active loop before
  it stopped; and
- `terminalReconciliation`: a bounded audit record proving how Trellis, Git,
  and merged PR state later converged.

This avoids making `stopped` an active evidence phase and avoids fabricating a
legal transition out of a terminal state.

## Command Boundary

Proposed signature:

```text
sd-ai-command-pack-work-loop.py reconcile-terminal --repo . --run-id <id> \
  --archived-task <path> \
  --delivery-pr-number <n> --delivery-pr-url <url> \
  --delivery-head <sha> --delivery-merge-commit <sha> \
  --branch <default> --head <sha> \
  [--bookkeeping-pr-number <n> --bookkeeping-pr-url <url> \
   --bookkeeping-head <sha> --bookkeeping-merge-commit <sha>] \
  [--recover-stale-lock] --json
```

All PR fields form validated groups: number, URL, head, and merge commit must be
provided together. Bookkeeping evidence is optional as a group.

The command is not an alias for `reconcile --verified-live-advance`. Ordinary
reconciliation continues to require the active run lock and active evidence
phases.

## State Contract

Add an optional top-level object so existing schema-version-1 ledgers remain
readable:

```json
{
  "terminalReconciliation": {
    "status": "verified",
    "reconciledAt": "2026-07-20T00:00:00Z",
    "archivedTask": ".trellis/tasks/archive/2026-07/07-17-ci-gate-coverage",
    "taskId": "ci-gate-coverage",
    "delivery": {
      "prNumber": 147,
      "prUrl": "https://github.com/example/repo/pull/147",
      "head": "<full sha>",
      "mergeCommit": "<full sha>"
    },
    "bookkeeping": {
      "prNumber": 148,
      "prUrl": "https://github.com/example/repo/pull/148",
      "head": "<full sha>",
      "mergeCommit": "<full sha>"
    },
    "observed": {
      "branch": "main",
      "head": "<full sha>"
    }
  }
}
```

Older readers must continue to ignore the additive field. New readers validate
its complete shape, normalized paths/URLs, bounded strings, and commit IDs.
Secret-like keys remain forbidden.

On success:

- `phase` remains `stopped`;
- `status` remains its original terminal value;
- `current`, counters, focus, iteration, history, and stop reason are unchanged;
- `contextHealth` becomes green with its epoch preserved; and
- `checkpoint` becomes a terminal completed/reconciled record rather than an
  active recovery target.

## Validation Flow

1. Resolve repository identity and state path without mutating either.
2. Validate the ledger and require terminal status/phase.
3. Inspect the existing lock:
   - live or ambiguous owner: reject;
   - stale owner: reject unless explicit stale recovery succeeds; and
   - absent owner: continue.
4. Acquire a short-lived lock through exclusive creation. Re-read the ledger
   after acquisition to prevent time-of-check/time-of-use drift.
5. Require a clean worktree on the detected default branch with local and
   remote-tracking tips equal to the submitted observed HEAD.
6. Resolve and normalize every submitted commit.
7. Validate the archived task path stays below the repository archive root,
   contains a regular `task.json`, is completed, and matches the original task
   identity even when the old ledger stored its former active path.
8. Validate PR number/URL pairs and local commit relationships. Merge commits
   may be merge, squash, or rebase results, so use strategy-aware containment:
   require exact submitted PR-head evidence from the orchestration layer and
   only enforce ancestry that Git can actually prove locally.
9. Compare the candidate terminal record with any existing record:
   identical means no-op; any difference means contradiction.
10. Atomically write the candidate state, then release the short-lived lock in
    `finally` handling.

## GitHub Trust Boundary

The helper remains local and deterministic. The `sd-work-backlog` skill must
use `gh pr view` or equivalent platform data to verify `MERGED`, head SHA, merge
commit, base branch, and URL before constructing the command. The helper
validates internal consistency and local Git availability but does not claim it
queried GitHub itself.

## Status Behavior

`sd-status` should render:

```text
Work loop: stopped; terminal reconciliation verified
External completion: delivery PR #147; bookkeeping PR #148
Context health: green; historical checkpoint reconciled
```

Historical counters remain visible and explicitly labeled as loop-owned. The
next-step generator suppresses terminal reconciliation only when the terminal
record is valid and verified; malformed or contradictory records remain an
anomaly.

## Compatibility And Rollout

- Keep schema version 1 if additive unknown top-level fields are already
  tolerated by older readers; otherwise introduce a compatible version bump
  with an explicit migration test.
- Update the canonical files under `templates/**` first and refresh root
  mirrors through the installer.
- Treat this as an additive minor pack release because it adds a public helper
  command and orchestration behavior.
- Rollback removes the new command and status interpretation but must not make a
  ledger containing the additive audit field unreadable.

## Risks

- A permissive terminal path could become a lock bypass. Restricting it to
  terminal ledgers and using a short-lived exclusive lock prevents that.
- Git ancestry alone cannot prove GitHub merge state. The orchestration/helper
  trust boundary must remain explicit in docs and tests.
- Rewriting counters would obscure who completed the work. Preserve them and
  report external completion separately.
- Old task paths differ after archive moves. Compare task identity and bounded
  archive location, not literal equality with the former active path.
