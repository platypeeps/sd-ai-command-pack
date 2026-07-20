# Require released target identity before fleet mutation

## Goal

Prevent unreleased or mismatched pack identities from being installed or merged
into consumers during fleet refresh.

## Background

- Coordinator PR #129 consumed the 0.23.7 identity before the source PR merged
  or a matching release tag existed, forcing the source target to advance to
  0.23.8 instead of reusing that version.
- The fleet skill says rollout starts after the source release exists, but the
  preflight does not currently make that lifecycle boundary impossible to
  bypass.

## Requirements

- Before reporting any consumer as mutable, resolve the target version from the
  manifest and require the corresponding immutable release tag to exist.
- Verify that the tagged release carries the same pack version and installable
  payload digest as the target being rolled out.
- Verify the candidate ledger is valid for that released payload and the
  current fleet manifest.
- Permit source `main` to contain later bookkeeping commits when the shipped
  payload remains byte-identical to the tag; do not require `HEAD` itself to be
  the tagged commit.
- Fail before branch creation or installation with actionable diagnostics for
  a missing tag, version mismatch, payload mismatch, stale ledger, or rewritten
  tag.
- Expose the guard result in human and JSON preflight output, including
  `dry-run` operation.
- Add regression coverage and synchronize documentation and shipped skill
  surfaces.

## Acceptance Criteria

- [ ] A missing target tag stops preflight before any consumer mutation.
- [ ] A tag whose version or payload does not match the manifest target is
      rejected.
- [ ] A stale or mismatched candidate ledger is rejected.
- [ ] Post-release bookkeeping commits do not cause a false failure when the
      installable payload still matches the tag.
- [ ] Tests reproduce the pre-release 0.23.7 consumption scenario and prove it
      cannot proceed.
- [ ] Human and JSON reports identify the exact failed identity check.

## Out of Scope

- Creating, moving, deleting, or rewriting release tags.
- Automatically publishing a source release from the fleet command.

## Notes

- Add `design.md` and `implement.md` before starting implementation.
