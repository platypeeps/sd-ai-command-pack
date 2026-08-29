# Validate sd-status work-loop snapshot contracts Implementation Plan

## Execution Order

1. Add a small pure snapshot-validation helper to the canonical status script.
2. Call it from `collect_work_loop()` after the existing dictionary check.
3. Add focused unit coverage for accepted and malformed helper snapshots.
4. Synchronize the root script mirror from the canonical template.
5. Update the task results, status contract documentation/spec, changelog, and
   patch release metadata.
6. Regenerate pack-owned catalogs/provenance and the Obsidian KB.

## Validation Plan

1. Run `tests.test_status` through the repo toolchain.
2. Run template parity and the deterministic full-check with Prism/Gito off.
3. Run the exact-payload fleet candidate check for every configured consumer.
4. Run `make check` and `git diff --check` before publishing.

## Documentation And Spec Updates

- Document the accepted work-loop snapshot states and fail-closed adapter
  behavior in `docs/SD_AI_COMMAND_PACK.md` and its canonical template.
- Capture the structural validation convention in the backend quality spec.
- Add the release entry and bump the manifest patch version.

## Review Notes

- Confirm valid stopped/completed snapshots are not accidentally rejected.
- Confirm unsupported values and malformed focus/nested structures are not
  included in diagnostics.
- Confirm `bool` does not satisfy the integer iteration contract.

## Rollback Points

- Revert the validator call and helper together; the existing dynamic-load
  exception handling remains independent.
- Do not alter the work-loop helper or ledger format as part of rollback.

## Follow-Ups

- None. Any future schema evolution must update the helper and adapter contract
  in the same pack release.
