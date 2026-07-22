# Release 0.30.4 KB ignore deduplication

## Goal

Remove equivalent unmanaged Obsidian KB ignore rules when refreshing an existing managed block, add regression coverage, and publish the corrective release before resuming the fleet.

## Requirements

- When an existing managed Obsidian KB ignore block is refreshed, remove any
  equivalent unmanaged `.obsidian-kb` ignore entries outside that block.
- Preserve unrelated ignore rules, comments, invalid UTF-8 bytes, marker
  validation, symlink safety, and local-exclude behavior.
- Make live fleet refreshes run each consumer's declared `candidatePrepare`
  commands after installation and audit, before the consumer full-check.
- Print the repo-scoped preparation commands in human-readable fleet preflight
  output so operators do not need to reconstruct them from JSON.
- Update the template source of truth, installed mirror, rollout documentation,
  release surfaces, regression coverage, and canonical full-fleet candidate
  ledger together.

## Acceptance Criteria

- [x] Refreshing a managed ignore block with equivalent entries before or after
  it leaves exactly one canonical `/.obsidian-kb` rule.
- [x] Focused KB-helper and fleet-preflight tests cover the reproduced Mezmo
  failure mode and the printed preparation command.
- [x] `make sync`, the full-fleet candidate validator, and `make check` pass for
  release `0.30.4`.
- [x] The source PR is reviewed, green, thread-clean, and ready for the
  exact-head housekeeping merge gate; the parent rollout verifies merge and
  tag identity before resuming from a fresh `0.30.4` preflight.

## Notes

- Parent rollout: `07-22-enforce-housekeeping-task-archive`.
- Trigger: deterministic Python 3.11 and 3.12 failures on
  `answerbook/mezmo_benchmark` PR #411 at head
  `df38ca76162e7cecb5fe9815f3d4cd4807fee2bb`.
