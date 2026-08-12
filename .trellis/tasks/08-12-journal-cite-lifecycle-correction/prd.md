# `journal-only-recovery` cannot cite a task lifecycle-correction commit

## Problem

A commit whose purpose is to correct a task's own lifecycle status can never
be cited by any journal session. The finalization that records the work is
structurally barred from naming the commit that did it.

`validateJournalOnlyPlanningRecovery`
(`scripts/sd-ai-command-pack-review-preflight.mjs:2709-2718`) validates each
cited commit by handing that commit's **parent** to `validatePlanningBundle`
as the baseline ref:

```js
for (const taskDir of validatePlanningBundle(
  taskRelatedEntries,
  commitEvidence,
  parentFields[1],          // the cited commit's parent
  add,
  { lifecycleOnly: true, currentRef: commit.oid },
))
```

That baseline is then required to be a valid planning task
(`scripts/sd-ai-command-pack-review-preflight.mjs:2322-2324`):

```js
const baseline = loadBookkeepingJsonAtRef(baseOid, `${taskDir}/task.json`, add, baselineOptions);
if (baseline && (baseline.status !== 'planning' || baseline.completedAt !== null || baseline.branch !== null)) {
  add('planning_baseline_invalid', `${taskDir}/task.json`, 'existing task was not a valid planning task at the bundle base');
}
```

The two conditions are jointly unsatisfiable for a correction commit. A commit
that moves a task from a non-planning status to `planning` has, by definition,
the non-planning status at its parent. `lifecycleOnly` mode reads the current
record at `commit.oid`, so the `planning_lifecycle_mutation` check passes; the
parent check is the only one that fires, and it fires necessarily.

Observed 2026-08-12 while shipping `08-12-thin-parent-status-blocks-finalization`
(PR #438). The correction commit `3e2991ea` returned
`08-09-deployment-thin-consumers` from `in_progress` to `planning`. Verified
against the shipped history:

| ref | `status` |
| --- | --- |
| `f0f12837` (parent) | `in_progress` |
| `3e2991ea` (the correction) | `planning` |

Citing it produced `planning_baseline_invalid`. The workaround was to cite only
the two commits either side of it — `f0f12837,b8653750` — and to state the
omission in the journal summary and the PR body, so the branch merged with its
central commit deliberately unrecorded.

A second, smaller defect sits on the same path. The recovery emits the generic
`planning_baseline_invalid` with the message "existing task was not a valid
planning task at **the bundle base**", but in `lifecycleOnly` mode the ref is
the cited commit's parent, not the bundle base. The message names neither the
offending commit nor the ref actually read, even though the sibling checks in
the same block already carry `planning_recovery_commit_parent_*` codes for
exactly this ref. The diagnostic sends a reader to inspect the wrong commit.

## Why it matters

Lifecycle corrections are not exotic. Any task started by mistake, any parent
started that should have stayed `planning`, and any status repaired after a
tooling defect produces this commit shape — and `task.py` writes no top-level
`status`, so the correction is always a hand edit that wants recording, not a
tool action that explains itself.

Today the choice is: omit the commit from the journal and lose the record of
the change most worth recording, or abandon `journal-only-recovery` for that
branch. Neither is a good default, and the omission is silent unless an author
notices and writes the gap down by hand, as `08-12`'s journal did.

## Goal

A branch that corrects a task's lifecycle status can record that commit in its
journal session, without weakening the check for the case it was written for:
a cited commit must not smuggle in an unrelated task-state change.

## Requirements

1. **Establish what the parent check is actually defending against**, from the
   validator's own rules rather than from inference, and state which of its
   guarantees a lifecycle-correction exemption would and would not preserve.
   The check has a real job: without it a cited commit could move a task out of
   `planning` and the recovery would ratify it.
2. **Decide the mechanism** and record the reasoning. Candidates, none of them
   pre-selected:
   - accept a parent whose record differs from the current one *only* in the
     direction of a correction — a non-planning status becoming `planning`,
     with `completedAt` and `branch` null on both sides;
   - keep the rule and give lifecycle corrections a distinct, explicitly
     narrower cited-commit class; or
   - keep the rule, and instead make the omission legible — a typed advisory
     naming the uncitable commit, so the gap is reported rather than
     depending on an author to notice it.
   A widening that also admits `planning` becoming `in_progress` is out: that
   is the direction the check exists to stop.
3. **Fix the misdiagnosis** regardless of which mechanism requirement 2 picks.
   In `lifecycleOnly` mode the failure must name the cited commit and say the
   ref is that commit's parent, consistent with the
   `planning_recovery_commit_parent_*` codes already used beside it.
4. **Cover the decision with tests** at the validator's existing test surface,
   including the direction that must keep failing.

## Acceptance criteria

- [ ] A fixture branch whose journal cites a commit moving a task from
      `in_progress` to `planning`, with `completedAt` and `branch` null
      throughout, produces a `status: valid` planning receipt — or, if
      requirement 2 selects the advisory route, produces a receipt whose
      typed advisory names that commit.
- [ ] A fixture branch whose journal cites a commit moving a task from
      `planning` to `in_progress` still fails. This is the direction the
      check defends and it must not be widened.
- [ ] The `lifecycleOnly` diagnostic names the cited commit and identifies
      the ref as that commit's parent, verified by asserting on the emitted
      message rather than by reading the code.
- [ ] `08-12-thin-parent-status-blocks-finalization`'s journal entry is
      reconciled or explicitly left as historical, with the reason recorded.
      Its session omits `3e2991ea` solely because of this defect.

      Established while filing this task: reconciling it in place is not
      available. A committed journal session is append-only —
      `validateTrellisJournalSessions`' history gate rejects a baseline
      session whose content changed — and CI reaches the same conclusion
      from the other side, because `bookkeeping_ci_scope.py:240-241`
      classifies any push delta touching `.trellis/workspace/` as a
      planning bundle and then requires a new completed session and its
      sibling index. Both the edit and its revert fail. So this criterion
      is satisfiable only by the "explicitly left as historical" branch,
      unless the fix chosen for requirement 2 also supplies a migration
      path — which is `.trellis/tasks/08-09-force-backup-journal` and
      issue #401's territory, not assumed here.

## Out of scope

- `validatePlanningClosureActiveTasks`. `08-12`'s D2 rejected widening it and
  that decision stands; this task is about citing a commit, not about which
  tasks may be left outside a closure.
- `completion_successor_history_non_linear`, owned by
  `08-09-update-branch-linearity-conflict`.
- The absence of a `task.py` command that writes top-level `status`. Related —
  it is why these corrections are hand edits — but a separate change.
