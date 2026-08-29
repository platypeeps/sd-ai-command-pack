# Post-Finish KB Refresh Design

## Overview

Extend the canonical Obsidian KB helper with an opt-in-by-presence mode, then
invoke that mode at the two lifecycle boundaries that can mutate Trellis task
documentation after the normal specification refresh:

1. `sd-housekeeping` refreshes an existing KB after `sd-finish-work` has
   archived the current task and before it merges the branch.
2. `sd-work-backlog` refreshes an existing KB after it records any follow-up
   tasks and before it records a clean iteration result.

The KB helper remains the only owner of copy, dashboard, overview, conflict,
and ignore-file behavior. Lifecycle skills only decide when a refresh is
required.

## Helper Contract

Add `--if-present` to `sd-ai-command-pack-update-spec-kb.py` as an independent
flag that can be combined with normal refresh, `--dry-run`, or `--check`.

- If `.obsidian-kb` is absent, print a one-line skip reason and return success
  without creating the directory or changing `.gitignore`.
- If `.obsidian-kb` exists, preserve the selected mode's current behavior and
  exit codes.
- Treat an occupied path or symbolic link as present. Existing validation must
  report conflicts instead of silently skipping an invalid KB path.

This mode is intentionally additive. An unqualified helper invocation still
creates or refreshes the KB as `sd-update-spec` expects.

## Lifecycle Ownership

`sd-housekeeping` invokes the shipped toolchain and KB helper once before any
merge or cleanup side effect. A failed refresh adds an actionable anomaly,
prints the normal status report, and stops the workflow before merge. Dry-run
uses the helper's dry-run mode. A missing KB is a visible no-op.

`sd-ship` does not invoke the helper directly. Its Stage 4 contract states that
the single delegated housekeeping run owns the post-finish refresh.

After nested shipping returns, `sd-work-backlog` processes follow-ups and then
invokes the helper once before recording the iteration result. Failure blocks
the iteration with the exact recovery command. This second owner exists only
because follow-up tasks can be created after housekeeping has completed.

## Distribution

Update template sources first and synchronize their root dogfood mirrors:

- `templates/scripts/sd-ai-command-pack-update-spec-kb.py`
- `templates/scripts/sd-ai-command-pack-housekeeping.sh`
- `templates/.agents/skills/{sd-housekeeping,sd-ship,sd-work-backlog}/SKILL.md`

The existing manifest targets already distribute these files, so no new
target is needed. Refresh installed provenance after synchronization.

## Failure And Recovery

- Absent KB: success with a skip reason; no filesystem mutation.
- Existing fresh or refreshable KB: success after refresh or dry-run preview.
- Existing conflicting or unreadable KB: preserve helper diagnostics and stop
  the owning lifecycle before it reports a clean boundary.
- Missing helper/toolchain while a KB exists: stop with the exact supported
  command needed to retry after restoring the pack install.

The recovery command is:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-update-spec-kb.py --if-present
```

## Testing Strategy

- Exercise helper present, absent, occupied-path, refresh, dry-run, and check
  combinations in filesystem fixtures.
- Pin housekeeping ordering: guarded refresh after finish-work ownership and
  before merge, with failure blocking and an actionable recovery command.
- Pin ship/backlog ownership so the archive refresh is delegated exactly once
  and the post-follow-up refresh happens before iteration completion.
- Run generated parity, manifest/provenance checks, focused suites, and the
  canonical full-check with KB freshness enabled.

## Rollback

The helper flag is additive. If lifecycle integration causes regressions,
remove the two invocations and their skill contracts while retaining the flag;
do not duplicate KB generation logic as a fallback.
