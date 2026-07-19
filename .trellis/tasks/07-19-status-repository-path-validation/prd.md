# Fail closed for missing sd-status repository paths

## Goal

Prevent `sd-status` from reporting an adjacent or parent Git repository when a
user supplies a missing positional or `--repo` path, while retaining support
for existing file paths inside a repository.

## Background

The archived positional-input task
`.trellis/tasks/archive/2026-07/07-18-positional-primary-command-inputs`
introduced `sd-status /path/to/repo`. During the 0.21.x fleet rollout, Copilot
review of answerbook/mezmo_benchmark PR #357 found that `resolve_repo()` treats
every non-directory as a file and moves to its parent. A typo such as `repoo`
therefore reports the current repository when `repoo` does not exist.

The implementation is owned by sd-ai-command-pack and must ship through the
canonical template and installer flow rather than a consumer-local patch.

## Requirements

- Accept an existing repository directory.
- Accept an existing file path and perform Git discovery from its parent.
- Reject missing paths and non-file, non-directory filesystem entries before
  invoking Git discovery.
- Apply the same behavior to positional paths and `--repo`, which share the
  resolver.
- Keep the template and installed script twins synchronized.
- Release the shipped correction and resume the paused fleet rollout.

## Acceptance Criteria

- [x] A missing immediate child of a Git repository resolves to no repository.
- [x] `sd-status repoo --no-network` exits 1 without rendering the parent repo.
- [x] Existing directory and file paths continue to resolve correctly.
- [x] Focused status tests, template parity, all-fleet candidate validation,
  and canonical pack checks pass.
- [ ] The corrected release reaches the active consumer PR through install.py.
