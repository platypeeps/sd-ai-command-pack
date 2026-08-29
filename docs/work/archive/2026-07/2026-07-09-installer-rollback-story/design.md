# Document Installer Rollback And Evaluate Two-Phase Apply Design

## Overview

The installer has per-file atomic writes and conflict detection, but a default
run can still partially apply non-conflicting files before exiting on
conflicts. Users need a documented rollback path, and the pack should decide
whether to preflight conflicts before writing.

## Proposal

First document the supported recovery model: pack refreshes should be done in a
PR, so rollback is `git revert` or closing/resetting the refresh branch, with
install-audit used to diagnose drift afterward. Explain that `--backup` applies
only to force/remove paths and that default conflict exits may leave a mixed
branch before the PR is reverted.

Then evaluate two-phase apply in the installer. The design target is
plan-then-apply: build the list of selected file operations, detect conflicts,
and if any conflict would exit 2, print the full conflict list and perform no
writes. Keep dry-run and success-path output stable where practical.

## Boundaries And Non-Goals

Do not build a transactional journal or snapshot restore mechanism. PR revert
remains the rollback primitive.

## Affected Files

- `install.py`
- `installer/fileops.py`
- `tests/test_install_core.py`
- `docs/SD_AI_COMMAND_PACK.md` and `templates/docs/SD_AI_COMMAND_PACK.md`

## Risks And Edge Cases

Two-phase planning can accidentally duplicate install logic. Prefer reusing
existing conflict checks and returning planned results before mutation rather
than creating a separate parallel installer.

## Validation

Add a conflict fixture that proves zero files are written when any selected
target conflicts, if two-phase apply is adopted. Always validate guide twins
remain byte-identical.
