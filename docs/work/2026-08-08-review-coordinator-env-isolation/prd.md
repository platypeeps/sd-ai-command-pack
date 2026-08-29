---
title: Fix review coordinator env isolation
status: planning
created: 2026-08-08
---
# Fix review coordinator env isolation

## Problem

Relocated from sd-github-review's backlog
(08-05-fix-review-coordinator-env-isolation there) — the defect is in THIS
repo's review coordinator, filed in the wrong repo. The coordinator's
subprocess environment leaks/withholds state such that `knowledge.obsidian-kb`
and `pack.review-scope` false-positive under the coordinator while the same
checks pass when run by hand. Operators have hand-waived the resulting red
gate twice — a gate that trains operators to override it is worse than no
gate.

## Requirements

1. Reproduce both false positives under the coordinator with a minimal env
   diff against the by-hand invocation.
2. Fix the coordinator's subprocess environment construction so check results
   match by-hand runs.
3. Regression test pinning the env contract for spawned checks.

## Acceptance criteria

- [ ] Both named checks agree (coordinator vs by-hand) on the same worktree
      state.
- [ ] Env contract test in place; full check green.
- [ ] sd-github-review's copy of the task is dropped in its own consolidation
      (cross-reference recorded there).

## Evidence

2026-08-08 cross-repo review: coordinator subprocess false-positives observed
on obsidian-kb and review-scope; two hand-waived red gates.
