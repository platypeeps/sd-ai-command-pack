# Post-Finish KB Refresh Implementation Plan

## Execution Order

1. Add focused failing tests for `--if-present`: absent KB no-op, present KB
   refresh, occupied-path failure, and compatibility with dry-run/check.
2. Implement `--if-present` in the template KB helper and synchronize the root
   mirror.
3. Add a Bash 3.2-compatible housekeeping function that invokes the toolchain
   and helper after finish-work ownership and before merge. Preserve dry-run,
   add an actionable anomaly on failure, and stop before merge.
4. Update the template `sd-housekeeping` and `sd-ship` skills to name the one
   post-archive owner. Keep `sd-ship` free of a duplicate helper invocation.
5. Update the template `sd-work-backlog` skill to refresh once after follow-up
   processing and before recording a completed iteration.
6. Synchronize root skill/script mirrors and add lifecycle contract tests for
   present, absent, archive, follow-up, failure, and no-duplicate ownership.
7. Document the cross-command contract in the adapter spec and distributed
   guide, then update release metadata for the shipped behavior change.
8. Self-install to refresh provenance and receipts, refresh the repository KB,
   and run the focused and canonical validation gates.

## Validation Commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_update_spec_kb tests.test_housekeeping \
  tests.test_sdlc_commands
bash scripts/sd-ai-command-pack-housekeeping.sh --self-test
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-update-spec-kb.py
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-update-spec-kb.py --check
make check
SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
bash scripts/sd-ai-command-pack-full-check.sh
```

## Review Focus

- Repositories without `.obsidian-kb` never get one from housekeeping or the
  autonomous backlog loop.
- Broken links and occupied KB paths fail instead of being mistaken for
  absence.
- Housekeeping blocks before merge when its post-finish refresh fails.
- Follow-up task creation cannot precede a clean iteration boundary without a
  final refresh attempt.
- No lifecycle invokes the post-archive refresh twice.
- Template/root parity and Bash 3.2 compatibility remain intact.

## Completion Checklist

- [x] Helper contract and focused tests pass.
- [x] Housekeeping archive boundary is covered and failure-safe.
- [x] Backlog follow-up boundary is covered and failure-safe.
- [x] Ship delegates refresh ownership without duplication.
- [x] Docs, spec, version, changelog, provenance, and receipts are current.
- [x] Canonical checks pass with KB freshness enabled.
