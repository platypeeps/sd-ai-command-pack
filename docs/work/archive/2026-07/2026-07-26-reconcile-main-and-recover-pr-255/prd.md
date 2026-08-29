---
title: Reconcile main and recover PR 255
status: done
created: 2026-07-26
---
# Reconcile main and recover PR 255

## Goal

Restore a clean local default branch and make PR #255 reviewable against
`main` without losing either the already-merged journal history or the PR's
post-archive finalization work.

## Background

- Local `main` is clean at `686f484`, one commit ahead of and 17 commits
  behind `origin/main` at `cce9cbb`.
- The local-only commit records the planning session that current
  `origin/main` already preserves as Session 230, alongside Sessions 229 and
  231.
- PR #255 is closed with deleted base branch
  `codex/support-journal-only-finalization-recovery`, while its head branch
  `codex/support-post-archive-review-finalization` remains available at
  `a35735b`.
- Commit `336f19a` is the last old-base commit before PR #255's own planning,
  implementation, archive, journal, and review-remediation commits.

## Requirements

- R1: Reconcile local `main` to current `origin/main` while preserving all
  substantive Session 230 journal content and the later merged sessions.
- R2: Rebase only PR #255-owned commits after `336f19a` onto current
  `origin/main`; do not replay the superseded recovery implementation.
- R3: Preserve the pre-rewrite remote head through an exact
  `--force-with-lease` guard, then retarget PR #255 to `main` and reopen it.
- R4: Resolve journal numbering, release metadata, task-tree, and
  template/mirror conflicts in favor of one coherent 0.54.0 candidate without
  dropping current-main content.
- R5: Keep this recovery task and its lifecycle evidence on PR #255's branch.
- R6: Validate the exact rewritten head with focused tests, template parity,
  `make check`, and all configured fleet candidates.
- R7: Run a fresh PR review cycle for the rewritten head, address and resolve
  actionable findings, produce valid finish-work evidence, and run guarded
  housekeeping.
- R8: Fail closed on unexpected history, lease, validation, review, or GitHub
  state instead of overwriting a newer remote branch or bypassing a gate.

## Acceptance Criteria

- [ ] Local `main` is clean and has zero commits ahead of or behind
  `origin/main`.
- [ ] Session 230 and all later merged journal entries remain present after
  local-main reconciliation.
- [ ] PR #255 targets `main`, is open, and its rewritten head contains only
  current-main history plus the intended PR #255 and recovery-task changes.
- [ ] The force push succeeds only against expected old head
  `a35735be5f1887fc313646b49f1cadb97de97d6e`.
- [ ] Canonical templates and installed mirrors are synchronized, release
  metadata consistently names 0.54.0, and journal/task references are valid.
- [ ] Focused tests, `make check`, and fleet candidate validation pass on the
  exact PR head.
- [ ] Fresh review rounds converge with no unresolved actionable threads and
  required GitHub checks pass on the exact head.
- [ ] Finish-work returns valid exact-head evidence and housekeeping reaches a
  clean terminal state, or reports one precise typed external blocker.

## Out of Scope

- New post-archive finalization features beyond the existing PR #255 scope.
- Work on unrelated backlog tasks or consumer repositories.
- Any pull request or source change in upstream Trellis.
