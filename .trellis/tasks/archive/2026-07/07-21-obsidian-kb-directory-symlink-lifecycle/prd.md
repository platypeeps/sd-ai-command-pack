# Honor Obsidian KB directory and symlink lifecycle

## Goal

Make the pack-managed `.obsidian-kb` lifecycle predictable across consumer
repositories: create the knowledge-base directory when it is absent, and
preserve and use an existing repository-root symlink instead of replacing it
or leaving it visible as untracked Git state.

## Background

- The normal KB refresh already creates `.obsidian-kb` when it is absent.
- Pack housekeeping currently invokes the helper with `--if-present`, so it
  skips repositories where `.obsidian-kb` has not been created yet.
- The generated ignore entry is `.obsidian-kb/`. That ignores a real directory
  but not a repository-root symlink, causing a valid KB symlink to appear as an
  untracked path and block clean-worktree gates.
- The refresh implementation currently follows an existing symlink whose
  target is a directory, but that root-symlink contract is not explicit in the
  documentation or regression tests.

## Requirements

- R1: A normal KB refresh and the housekeeping-owned post-finish refresh must
  create `.obsidian-kb` when no path exists.
- R2: When `.obsidian-kb` is an existing symlink to a directory, the pack must
  preserve the symlink and refresh content through it into the target.
- R3: The managed Git ignore entry must be rooted at the repository and ignore
  `.obsidian-kb` whether it is a real directory or a symlink, while continuing
  to ignore a directory's descendants.
- R4: A broken root symlink, a root symlink to a non-directory, or another
  occupied non-directory path must fail clearly and nonzero before generated
  content is written. The helper must not replace the path or create a broken
  symlink's target.
- R5: `--dry-run` and `--check` must remain read-only and apply the same root
  path classification without creating a missing directory or following an
  unusable symlink.
- R6: `--if-present` remains a supported opt-in guard for callers that
  intentionally do not create a KB, but housekeeping must use the normal
  refresh mode rather than that guard.
- R7: Canonical scripts, installed mirrors, documentation, code specs, and
  tests must remain synchronized. Consumer repositories receive the behavior
  through the normal pack rollout rather than repo-specific patches.

## Technical Notes

- The current copy writer already traverses a valid `.obsidian-kb` symlink to
  an existing directory without replacing the link. The implementation should
  make that root-path classification explicit before any refresh writes.
- The current managed ignore entry `.obsidian-kb/` is directory-only. A
  repository-root pattern without a trailing slash is required so Git also
  ignores the symlink node.
- Existing managed or unmanaged `.obsidian-kb/` ignore entries should migrate
  through the helper's current managed-block replacement logic.
- A broken symlink is an occupied user-owned path, not permission to choose or
  create its destination.

## Acceptance Criteria

- [x] AC1 (R1): A normal refresh and a housekeeping refresh create
      `.obsidian-kb` plus generated knowledge files when the path is absent.
- [x] AC2 (R3): The managed ignore rule causes an isolated
      `git check-ignore -- .obsidian-kb` assertion to succeed for both a real
      directory and a repository-root symlink.
- [x] AC3 (R2): An existing root symlink to a directory remains a symlink,
      and its target receives the refreshed generated files.
- [x] AC4 (R4): A non-directory occupied path, broken symlink, and symlink to a
      non-directory each produce a clear nonzero failure without replacing the
      path, creating the broken target, or writing generated content.
- [x] AC5 (R5, R6): `--dry-run`, `--check`, and `--if-present` retain their
      documented mode semantics; housekeeping alone switches from guarded to
      normal refresh.
- [x] AC6 (R7): Automated tests cover all lifecycle cases, source/template
      mirrors match, and the relevant pack validation passes.

## Out of Scope

- Choosing or creating a user-specific Obsidian vault path when no symlink is
  present.
- Creating the target of a broken `.obsidian-kb` symlink.
- Changing the full-check KB auto-repair opt-in rules or removing the public
  `--if-present` option.
- Committing generated KB content or the `.obsidian-kb` path to consumer
  repositories.
