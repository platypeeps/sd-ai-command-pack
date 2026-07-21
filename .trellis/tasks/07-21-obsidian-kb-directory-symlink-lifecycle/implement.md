# Implementation Plan: Obsidian KB directory and symlink lifecycle

## Ordered Checklist

1. Add focused helper tests for:
   - absent-path refresh creation;
   - existing real-directory refresh;
   - root symlink-to-directory preservation and target writes;
   - broken root symlink, symlink-to-file, and occupied-file failures;
   - managed-rule `git check-ignore` success for a directory and symlink with
     global excludes disabled;
   - read-only behavior for `--dry-run` and `--check` on missing/invalid roots.
2. Update the template KB helper with explicit root-path validation and the
   anchored `/.obsidian-kb` ignore rule. Validate invalid occupied roots before
   any refresh write and keep public `--if-present` behavior intact.
3. Synchronize the root helper mirror and run the focused KB test module.
4. Update the template housekeeping script to invoke normal refresh (plus
   `--dry-run` only when requested), remove absent-path skipping, and update
   diagnostics/actions. Synchronize the root mirror.
5. Update housekeeping contract tests so absent-path execution calls the
   helper and failures cite the normal-refresh recovery command.
6. Update the template/root housekeeping skill, template/root pack guide,
   README, and backend/frontend specs. Preserve the separate guarded
   post-follow-up contract where it remains intentional.
7. Refresh this repository's `.obsidian-kb` so the managed root ignore entry
   and generated task documentation are current; inspect any tracked
   `.gitignore` change.
8. Run focused validation, mirror/drift checks, then the full repository gate.

## Validation Commands

```bash
.venv/bin/python -m unittest tests.test_update_spec_kb tests.test_housekeeping
python3 scripts/sd-ai-command-pack-update-spec-kb.py --check
git diff --check
make check
```

Also verify source/template equality for each changed mirrored script, skill,
and guide through the repository's existing drift gate rather than maintaining
a separate manual sync check.

## Review Checkpoints

- Root symlink remains a symlink after refresh.
- Broken symlink target remains absent after every mode.
- Invalid-root failure occurs before ignore/copy writes.
- Git-ignore assertions are independent of the developer's global Git config.
- Housekeeping refresh runs before fetch/merge and no longer passes
  `--if-present`.
- `--if-present` still behaves as documented for callers that explicitly use
  it.
- Template/root mirrors and distributed docs express the same contract.

## Risky Files and Rollback Points

- `sd-ai-command-pack-update-spec-kb.py`: filesystem and symlink boundary;
  keep changes localized to root validation and ignore generation.
- `sd-ai-command-pack-housekeeping.sh`: merge-gate ordering; do not change any
  merge criteria while altering refresh arguments.
- Code specs and docs: update only the KB lifecycle sections so unrelated
  delivery contracts remain stable.
