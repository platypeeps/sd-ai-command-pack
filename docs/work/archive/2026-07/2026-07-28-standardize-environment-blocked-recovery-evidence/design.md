# Environment-blocked recovery evidence design

## Architecture

Define an additive schema fragment shared by command result composers. Each
mutation owner constructs the fragment at the point where it already knows the
operation, boundary, and mutation progress. Consumers render the evidence and
select a bounded retry; they do not infer intent from stderr.

## Contract

The fragment contains:

- `reasonCode`: fixed value `environment_blocked`.
- `boundary`: versioned bounded enum beginning with `git-metadata`,
  `user-state`, `tool-cache`, `kb-target`, and `managed-payload`.
- `operation`: command-owned bounded operation identifier.
- `retryable`: boolean derived by the owner, never by presentation code.
- `checkpoint`: the last lifecycle checkpoint the owner verified.
- `recoveryAction`: argv-shaped or skill-owned bounded instruction; never an
  interpolated shell string.
- `mutationState`: `none`, `partial-recoverable`, or `unknown`.
- `diagnostic`: size-bounded, secret-safe text with controlled path rendering.

Before implementation, inventory current result schemas and select one shared
schema location and versioning policy. Result payloads that cannot add the
fragment compatibly must version or adapt explicitly.

## Producer flow

1. The owning operation encounters a known environment or authority boundary.
2. It records the last verified checkpoint and mutation state from internal
   control flow, not textual error parsing.
3. It validates and emits the shared fragment inside the command's existing
   failure result.
4. The command preserves its existing nonzero or blocked status.
5. A skill presents the exact boundary and recovery checkpoint and, when
   retryable, requests only the narrow authority needed for that operation.
6. The retry revalidates identity, ownership, and checkpoint before mutation.

## Initial integrations

- Session recorder: staging or commit after a successful journal append.
- Finish-work: Git metadata and retained-receipt writes.
- Housekeeping: fetch/prune, linked-KB refresh, default-branch switch, and
  deletion-proof operations.
- Work loop: user-local lock, heartbeat, checkpoint, and reconciliation writes.
- Toolchain: cache creation, permissions, and ownership validation.

Each integration remains owned by its existing command. This task supplies the
common evidence language; it does not absorb the underlying domain logic.

## Safety and compatibility

- Unknown errors remain unknown; there is no fallback stderr classifier.
- Recovery actions are data, not executable authority.
- Diagnostics must not include tokens, remote URLs with credentials, arbitrary
  raw paths, or unbounded provider output.
- Unsupported versions fail closed or retain the legacy bounded result.
- A partial mutation requires command-specific reconciliation before retry.
- Rollout may be incremental, but a producer must not emit a fragment until
  its consumer and compatibility behavior are tested.

## Rollback

The contract is additive. An integration can revert to its prior bounded
failure result without changing completed lifecycle state. No migration writes
or automatic recovery actions are introduced.
