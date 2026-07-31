# Recover bookkeeping-repair sessions through journal-only recovery

## Problem

Sessions whose work commits repair bookkeeping itself — journal-history fixes
under `.trellis/workspace/**` and task-lifecycle repairs whose *parent* state
was already dirty — cannot be journaled through the `journal-only-recovery`
subtype. This is root cause 3 of
`.trellis/tasks/archive/2026-07/07-29-scope-final-bundle-validator-to-delta/prd.md`, descoped
from that task by its 2026-07-30 adversarial-review scope decision after two
review rounds found the proposed no-re-audit widening unsound.

## Evidence

- Session 251 (2026-07-29) could not be recorded in its own push: its work
  included two journal-repair commits (`acc836dc`, `d21afe83`, both touching
  `.trellis/workspace/`) and one commit clearing a stale `branch` field
  (`f92221e5`), which per-commit lifecycle validation rejects with
  `planning_lifecycle_mutation` / `planning_baseline_invalid` against the
  task as it stood at that commit's parent.
- `validateJournalOnlyPlanningRecovery`
  (`scripts/sd-ai-command-pack-review-preflight.mjs:1787`) rejects any cited
  commit touching `.trellis/workspace/**`
  (`planning_recovery_commit_scope_invalid`), and its per-commit lifecycle
  validation loads the baseline from the cited commit's parent, so
  dirty-parent repairs fail even though the commit *fixes* the dirt.

## Constraints discovered in review (must shape the design)

- **No unaudited workspace admission.** An initial pull-request push is
  classified full CI, not `bookkeeping`
  (`.github/scripts/bookkeeping_ci_scope.py`, reason
  `pull_request_action_not_synchronize`), and the `Validate bookkeeping head`
  step in `.github/workflows/tests.yml` is gated on `mode == 'bookkeeping'` —
  so cited workspace mutations in a branch pushed whole receive **no**
  per-increment bookkeeping validation anywhere. Any widening must therefore
  audit cited workspace commits' content itself (e.g., run the
  journal-history-mutation rules per cited commit, parent..commit), not
  delegate to CI.
- **Direction-of-repair rule for lifecycle repairs.** A cited commit whose
  parent lifecycle state is dirty but whose own resulting state is clean
  planning (the `f92221e5` shape) should be admissible; a commit that leaves
  the task dirty should not. Blocking on `planning_baseline_invalid` at the
  parent rejects exactly the repairs this route exists to record.
- Everything the 07-29 task's design keeps load-bearing stays: the
  finalization bundle remains journal-plus-index only; archive and malformed
  `.trellis/tasks/**` paths stay rejected; cited commits stay published,
  linear, bounded ancestors of the receipt base.

## Acceptance criteria (sketch — refine at planning)

- [ ] A session citing a workspace journal-repair commit validates, and the
      cited commit's workspace changes pass a per-commit content audit
      (history-mutation, session-shape, whitespace rules).
- [ ] A session citing a dirty-parent lifecycle repair (`f92221e5` shape)
      validates; a commit leaving the task dirty still fails.
- [ ] The session-251 citation set validates end to end.
- [ ] All negative shapes pinned by `tests/test_bookkeeping_validator.py` for
      the 07-29 partition still block, **except** the 07-29 design's Test 6
      (any workspace-citing commit → invalid), which this task explicitly
      supersedes: replace it with content-aware workspace cases — a positive
      (audited journal-repair commit validates) and a negative (a cited
      workspace commit that mutates journal history invalidly still blocks).

## Notes

- Blocked on nothing, but should land after
  `07-29-scope-final-bundle-validator-to-delta` — it extends that task's
  partition table.
- Complex: needs `design.md` + `implement.md` before `task.py start`; the
  workspace content-audit mechanism is the core design problem.
