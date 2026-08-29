# Fleet candidate validation and priority implementation plan

## Execution Order

1. Add the shared fleet schema/digest/ledger module and migrate preflight to
   schema version 2 with explicit priority ordering.
2. Update the fleet manifest with measured fast-first priorities and
   conservative repo-owned compatibility commands.
3. Add the disposable candidate validator and source-only audit declarations.
4. Add candidate-ledger enforcement to the release drift gate and exact-commit
   tag planner.
5. Update rollout, release, and consumer-review documentation plus the
   source-only fleet skill/template twin.
6. Add focused unit/integration tests for schema, ordering, candidate flow,
   ledger validation, tag enforcement, and source-only boundaries.
7. Bump the pack patch version and changelog. The release behavior is
   source-only and does not add or change a consumer-installed command.
8. Run the real full-fleet candidate sweep for that version and commit its
   generated all-pass ledger.
9. Refresh the spec KB and run focused tests, `make check`, and the canonical
   full check with optional Prism/Gito lanes disabled.

## Validation Commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_fleet_preflight tests.test_fleet_candidate \
  tests.test_release_ledger tests.test_install_audit

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py --check-ledger

python3 scripts/sd-ai-command-pack-update-spec-kb.py
make check
SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
  bash scripts/sd-ai-command-pack-full-check.sh
```

## Review Gates

- No manifest command may be a shell string; all are argv arrays.
- No candidate run may write to an active consumer checkout.
- Partial/failing runs must not replace the canonical ledger.
- Release tag validation must read committed head content, not trust a dirty
  working tree.
- New source-only helpers must be rejected if copied into consumer receipts.
- Template/root twins must remain byte-identical.

## Rollback Points

- Schema migration and preflight sorting can be reverted independently before
  the candidate gate is wired into release validation.
- The release gate should be wired only after candidate ledger generation and
  focused tests work, avoiding an unresolvable intermediate main state.

## Follow-Ups

Measure future rollout durations and adjust explicit priorities only when
repeated evidence changes the ordering. New compatibility checks belong in the
consumer entry, not in tool-specific pack logic.
