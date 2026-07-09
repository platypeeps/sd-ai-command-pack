# Document installer rollback and evaluate two-phase apply

## Goal

Give consumers an explicit rollback story for a failed or partial pack
refresh, and evaluate whether the installer should apply all-or-nothing
instead of writing non-conflicting files before bailing on a conflict.

## Problem

The 2026-07-09 architecture review found the rollback mitigation is real but
undocumented and the apply is not transactional:

- Per-file writes are atomic and conflicts preserve existing files (the run
  exits 2 after listing conflicts, `install.py:303-320`), but a conflicted run
  still writes the *non-conflicting* files first — leaving a partial,
  mixed-version tree with no rollback command.
- `--backup` `.bak` copies are produced only with `--force`/`--remove`, so a
  default refresh that partially applies has no per-file undo.
- The actual rollback path is "revert the refresh PR" (refreshes go through
  PRs per README:441-443) plus install-audit catching hash mismatches after
  the fact — but this is nowhere stated as the procedure.

Neither is a correctness bug; the gap is an undocumented recovery procedure
plus an optional robustness improvement.

## Requirements

- R1: Document the rollback procedure in the installed guide
  (`docs/SD_AI_COMMAND_PACK.md` + twin): what a partial apply looks like, that
  refreshes go through PRs so `git revert`/PR-revert is the supported rollback,
  and how install-audit surfaces post-hoc drift.
- R2: Evaluate a two-phase apply — compute the full write plan and detect all
  conflicts *before* writing any file, so a conflicted run leaves the tree
  untouched (exit 2 with the conflict list, zero partial writes). Record the
  decision (adopt / defer with rationale) in the task; if adopted, implement
  behind the existing conflict-exit contract without changing success-path
  behavior.

## Acceptance Criteria

- [ ] Installed guide documents the rollback procedure; docs twins
      byte-identical; review-preflight doc-path checker passes.
- [ ] Two-phase-apply decision recorded. If adopted: a test asserts a run with
      any conflict writes zero files (plan-then-apply), and the existing
      success/idempotent/dry-run tests still pass with 100% installer coverage.

## Non-goals

- A full transactional journal / snapshot-and-restore installer — PR-revert
  remains the primary rollback; R2 is bounded to pre-flighting conflicts.
