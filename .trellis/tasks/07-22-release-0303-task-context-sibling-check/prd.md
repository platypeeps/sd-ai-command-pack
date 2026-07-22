# Release 0.30.3 task-context sibling validation

## Goal

Make changed qualifying task.json files trigger sibling implement/check scaffold validation, add regression coverage, and publish the corrective release before resuming the fleet.

## Requirements

- Preserve the documented contract: a changed non-planning `task.json` must
  cause both sibling `implement.jsonl` and `check.jsonl` files to be inspected
  for generated `_example` scaffold rows, even when those siblings are absent
  from the diff.
- Keep metadata-only changes to planning tasks exempt unless a context file is
  itself changed; preserve existing archive-layout and symlink safety rules.
- Update the template source of truth and installed mirror together, add a
  regression that changes only `task.json`, and keep documentation accurate.
- Publish one corrective `0.30.3` release with synchronized version surfaces,
  provenance, and a canonical all-fleet candidate ledger before resuming
  consumer mutation.

## Acceptance Criteria

- [x] A changed qualifying `task.json` exposes seeded sibling context files
  even when the context files are unchanged.
- [x] A metadata-only planning-task change continues to ignore unchanged
  legacy planning scaffolds.
- [x] Focused review-preflight tests pass for template and installed behavior.
- [x] Full-fleet candidate validation and `make check` pass for `0.30.3`.
- [x] The source PR is reviewed, thread-clean, green, and ready for the
  housekeeping merge gate; the parent rollout verifies merge and tag before
  consumer mutation resumes.

## Notes

- Parent rollout: `07-22-enforce-housekeeping-task-archive`.
- Trigger: Copilot thread on `rwbp-coordinator` PR #170 at finish-work head
  `bcf849e`.
