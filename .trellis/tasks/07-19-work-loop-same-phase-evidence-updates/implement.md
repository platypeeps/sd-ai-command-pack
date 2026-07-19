# Support Same-Phase Work-Loop Evidence Updates Implementation Plan

## Execution Order

1. Add field groups, reusable update validation, Git commit/ancestry helpers,
   and checkpoint clearing to the canonical template work-loop helper.
2. Add the `evidence` CLI and route verified reconciliation through the shared
   validation path without permitting same-phase lifecycle transitions.
3. Extend focused work-loop tests across normal shipping advances, merge
   evidence, invalid updates, atomic failure, old ledgers, and reconciliation.
4. Update the canonical backlog skill to record evidence after commits, PR
   publication, review fixes, finish-work, and merge; synchronize its mirror.
5. Update public docs and the frontend adapter spec, then bump release metadata
   and refresh installed mirrors/provenance through the canonical installer.
6. Run focused tests, generated parity, full repository checks, KB refresh, and
   the release/fleet candidate gate required for shipped payload changes.

## Validation Plan

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest \
  tests.test_work_loop
make check
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-update-spec-kb.py
SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
bash scripts/sd-ai-command-pack-full-check.sh
```

Use the repository release/candidate-validation command surfaced by `make
check` if the manifest gate requires refreshed evidence.

## Documentation And Spec Updates

- Document `evidence` as the only supported same-phase mutable-evidence path.
- State that `transition` remains phase-only and cannot be used as an update.
- Explain verified reconcile behavior and when successful recovery clears an
  obsolete checkpoint.
- Record the shipped behavior in `CHANGELOG.md` and bump the minor version for
  the additive shipped helper CLI.

## Review Notes

- Check every field independently for initialization, no-op, legal advance, and
  contradiction behavior.
- Verify merge handling works for squash and merge commits without allowing an
  arbitrary branch switch.
- Ensure failed updates leave the on-disk ledger byte-for-byte unchanged.
- Keep template/root copies synchronized through the installer, not ad hoc
  divergence.

## Rollback Points

- Before the CLI is documented, the helper changes can be reverted as one
  source-and-test unit.
- After release metadata changes, revert the whole shipped payload commit; do
  not leave a version bump without its helper behavior.

## Follow-Ups

- No upstream Trellis change is required.
- If later providers need cryptographic PR-to-commit verification, track that
  separately rather than adding network behavior to this local state helper.
