# Implementation Plan

1. Add focused full-check tests with an isolated Git repository and a logging
   Prism stub.
   - Mixed committed, staged, and unstaged work must log only `review staged`
     and `review unstaged`.
   - A clean feature branch must log only the merge-base range review.
   - Local-only single-layer fixtures must select only that layer.
2. Update the authoritative full-check template so any local Prism work returns
   before merge-base/range selection.
3. Document full-check's local-first Prism scope in the distributed guide,
   README environment summary where useful, and the adapter guideline scenario.
4. Run `make sync` to update installed mirrors and generated metadata.
5. Bump the pack patch version and changelog, then run the normal fleet
   candidate validation for the changed payload.
6. Run focused tests, template parity/release gates, and `make check`.

## Validation Commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_full_check
make sync
make check
```

Run the repository's configured fleet candidate validation command after the
final payload digest is stable.

## Risk and Rollback Points

- Risk: returning too early could skip one non-empty local Git layer. Tests must
  cover both-layer and each single-layer state.
- Risk: tests can accidentally inherit the source checkout's base ref or Prism
  configuration. Fixtures must isolate Git state and use explicit environment
  variables.
- Rollback: restore the prior unconditional merge-base/range block and revert
  the documentation/version release changes as one payload unit.

## Pre-start Checks

- Confirm the user accepts local-first precedence over hunk-level caching.
- Read the task artifacts and frontend adapter spec through
  `trellis-before-dev` before editing.
- Start the Trellis task only after artifact approval.
