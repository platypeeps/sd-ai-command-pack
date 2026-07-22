# Design: Obsidian KB directory and symlink lifecycle

## Scope

Make the existing KB helper classify the repository-root `.obsidian-kb` path
explicitly, use an ignore pattern that covers both directories and symlinks,
and make housekeeping perform an unconditional post-finish refresh. Preserve
the public `--if-present` mode for other intentional opt-in callers.

This is one cohesive delivery rather than a parent/child split: helper
behavior, housekeeping invocation, mirrors, documentation, and tests must land
together to avoid distributing contradictory lifecycle contracts.

## Current Behavior

1. `create_copies()` calls `Path.mkdir(..., exist_ok=True)`. A root symlink to
   an existing directory happens to work because `Path.is_dir()` follows it,
   but no explicit validation or diagnostic owns that contract.
2. The managed ignore entry is `.obsidian-kb/`, which ignores a directory and
   its descendants but does not ignore a root symlink node.
3. Housekeeping pre-checks for the path and invokes the helper with
   `--if-present`, so an absent KB is skipped.
4. Source scripts and skills are byte-mirrored from `templates/**`; changing
   only a root installed copy would fail pack drift checks.

## Proposed Design

### Root-path classification

Add one small helper-owned classifier/validator used before refresh traversal:

| Root state | Refresh | Dry-run/check | Preservation rule |
| --- | --- | --- | --- |
| Absent | Allowed; create a real directory when writes begin | Inspect only; do not create | N/A |
| Real directory | Use in place | Inspect in place | Never replace |
| Symlink to existing directory | Traverse target | Inspect target | Preserve symlink bytes and target |
| Broken symlink | Exit `2` with explicit error | Exit nonzero with explicit error | Do not create target or unlink link |
| Symlink to non-directory | Exit `2` with explicit error | Exit nonzero with explicit error | Do not replace |
| Other occupied path | Exit `2` with explicit error | Exit nonzero with explicit error | Do not replace |

Perform invalid-root validation before updating ignore state or copying files,
so an invalid occupied path does not leave partial lifecycle writes. Creation
of an absent directory remains refresh-only; `--dry-run` and `--check` stay
read-only.

### Ignore contract

Change the generated rule to a repository-root, non-directory-only pattern:

```gitignore
/.obsidian-kb
```

This matches the symlink node and also ignores a real directory plus its
contents. Existing normalization already recognizes leading/trailing slashes,
so managed blocks and unmanaged legacy `.obsidian-kb/` entries can be upgraded
without a separate migration mechanism.

Tests that invoke Git must neutralize user/global excludes so success proves
the pack-managed rule, not machine configuration.

### Housekeeping ownership

Rename the internal shell helper if needed so its name reflects unconditional
refresh, remove the path-existence short circuit and `--if-present` argument,
and retain the existing ordering:

```text
finish-work -> normal KB refresh -> fetch/merge -> status
```

Dry-run still adds `--dry-run`, and any helper failure remains a pre-merge
anomaly with the normal-refresh recovery command.

The backlog post-follow-up call may retain `--if-present`; after the default
ship path, housekeeping has already created the KB, and this task does not
remove the public guarded mode.

## Files and Sync Boundaries

- `templates/scripts/sd-ai-command-pack-update-spec-kb.py` first, then the
  root `scripts/` mirror.
- `templates/scripts/sd-ai-command-pack-housekeeping.sh` first, then the root
  mirror.
- `templates/.agents/skills/sd-housekeeping/SKILL.md` first, then the root
  `.agents/` mirror.
- `templates/docs/SD_AI_COMMAND_PACK.md` first, then the root docs mirror.
- `README.md`, `.trellis/spec/backend/manifest-and-filesystem.md`, and
  `.trellis/spec/frontend/adapter-guidelines.md` for the source contract.
- `tests/test_update_spec_kb.py` and `tests/test_housekeeping.py` for behavior.
- The repo-root managed `.gitignore` entry may update when the helper refreshes
  this checkout and must remain intentional in the final diff.

## Compatibility and Migration

- No CLI option or exit code is removed.
- Existing `.obsidian-kb/` ignore rules are replaced by the managed root rule
  on the next normal refresh.
- Existing real KB directories and valid root symlinks are preserved in place.
- Broken or mistyped symlinks that previously failed indirectly now receive a
  stable, explicit diagnostic.
- Consumer rollout uses the normal pack installer/fleet flow; no consumer-only
  patches are part of this task.

## Risks and Mitigations

- **Writing through an unintended symlink:** require the target to exist and be
  a directory; never create a target or replace the link.
- **Tests pass due to a global ignore:** isolate `git check-ignore` from global
  excludes.
- **Partial writes on invalid roots:** validate before ignore or copy writes.
- **Template drift:** edit template sources first and run mirror/full checks.
- **Over-broad ignore matching:** anchor the pattern to repository root.

## Rollback

The change is reversible by restoring the prior managed ignore rule and
housekeeping guard. Generated KB files remain ignored local output; valid
directories and symlinks are never replaced, so rollback requires no data
migration.
