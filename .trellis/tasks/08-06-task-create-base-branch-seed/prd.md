# task.py create records the current branch as the PR target

## Goal

Stop new root tasks from being created with a `base_branch` that names the
feature branch they happened to be authored on, and make a wrong value fail the
deterministic gate instead of reaching a paid review round.

## Problem

`.trellis/scripts/common/task_store.py:296`:

```python
# Record current branch as base_branch (PR target)
_, branch_out, _ = run_git(["branch", "--show-current"], cwd=repo_root)
current_branch = branch_out.strip() or "main"
```

and at `.trellis/scripts/common/task_store.py:325` that value is written
straight into the new record as `"base_branch": current_branch`.

The field means the branch a future pull request will target. The code records
the branch the author was standing on. Those coincide only when a task is
created from the default branch.

### Why that is the uncommon case here

The SD flow gives a task scaffold its own branch: a diff spanning more than one
Trellis task directory draws a review preflight *warning* — `warn(...)` at
`scripts/sd-ai-command-pack-review-preflight.mjs:4172-4176`, not a failure, so
more than one directory is permitted and merely discouraged — and the convention
that follows from it is to file each task on its own branch and open a pull
request. Every task created that way gets its own feature branch recorded as the
target it should be merged *into*.

The warning is a nudge, not a gate, so it is a convention rather than a forcing
function. That weakens the causal story slightly and is worth stating plainly:
the branch-per-task habit is why the defect fires so reliably, but nothing
mechanically compels it.

Both tasks filed on 2026-08-06 hit it:

- `08-06-local-provider-empty-scope` — corrected by hand before its PR opened.
- `08-06-preflight-bare-filename-references` — reached PR #342 with
  `base_branch: "chore/task-preflight-bare-filename-references"`, passed the
  deterministic gate with 0 failures and 0 warnings, and was caught by a paid
  Copilot round. Fixed in `5779c242`.

A third dated occurrence, 2026-08-07: `08-07-review-check-stale-cache` was
created from `task/08-07-review-check-stale-cache`, recorded that branch, and
reached PR #358 still holding it, where a paid Copilot round flagged it. Fixed in
`8a72d5fb`. That is the second time this defect has passed the deterministic gate
and then been caught by a paid review round — PR #342 was the first — which is
the exact cost R2 exists to remove.

It is not new, not confined to one week, and the stored population is growing. A
survey on 2026-08-06 gave 43 of 45 active records recording `main`, with two
exceptions: `07-30-upstream-task-start-branch-recording`, and this task's own
record, corrected by hand before its pull request opened.

Re-running that survey against `origin/main` on 2026-08-07 gives **45 of 51
recording `main`, with six exceptions**. All six are root tasks — confirmed by
reading `parent` on each record, every one `None` — so not one of them is the
legitimate stacked-child shape R3 protects:

| Task | Recorded `base_branch` | Refs matching that branch |
|---|---|---|
| `07-30-upstream-task-start-branch-recording` | `fix/silence-satisfied-scope-advisory` | 0 |
| `08-06-session-followups` | `fix/work-loop-stop-after-pause` | 2 |
| `08-07-local-finding-rebuttal-channel` | `chore/task-file-session-defects` | 0 |
| `08-07-planning-recovery-rejects-merge-commit` | `chore/task-file-session-defects` | 0 |
| `08-07-provenance-concurrent-session-collision` | `chore/task-file-session-defects` | 0 |
| `08-07-status-housekeeping-anomaly-disagreement` | `chore/task-file-session-defects` | 0 |

Five of the six name a branch with no matching ref locally or on the remote, so
they are dead references. Four of those five share one branch — the signature of
a single session filing four tasks from one feature branch with none of them
caught, which is the failure at scale rather than one slip.

So the value is wrong roughly whenever a task is filed through the normal SD
flow; the exception set tripled in a day; and at least one wrong record has been
merged and sat unnoticed for over a week.

### Why the deterministic gate did not catch it

`scripts/sd-ai-command-pack-review-preflight.mjs` does validate the field, but
only in shapes that miss this case:

- `scripts/sd-ai-command-pack-review-preflight.mjs:3302` — `base_branch` must be
  a non-empty string. A feature-branch name satisfies this.
- `scripts/sd-ai-command-pack-review-preflight.mjs:3309` — `branch` must differ
  from `base_branch`. On a freshly created task `branch` is null, so the
  comparison never fires.
- `scripts/sd-ai-command-pack-review-preflight.mjs:3241` — for a *child* task,
  `base_branch` must equal the parent's `base_branch` or the active branch. That
  rule deliberately permits the active branch, and it does not apply to root
  tasks at all.

So a root task with `branch: null` has no rule constraining `base_branch` to the
default branch, which is exactly the record `task.py create` produces.

## Requirements

### Functional

- R1: a task created while on a feature branch must not silently record that
  branch as `base_branch`.
- R2: a root task whose `base_branch` is neither the repository's default branch
  nor a deliberate, recorded exception must fail the deterministic gate, naming
  the task path and the offending value.
- R3: R2 must not break the child-task rule at
  `scripts/sd-ai-command-pack-review-preflight.mjs:3241`, which permits a child
  to target the active branch. Stacked child work is a supported shape.
- R4: existing task records must not be invalidated wholesale. Any record the
  new rule would reject needs either a correction or a stated exemption before
  the rule can block.

## Constraints

- `.trellis/scripts/**` is vendored Trellis, and the review preflight's
  `isTrellisCopiedPath` treats it as a copied surface. A change there is an
  upstream change, not a pack-local one — see the open questions.
- The `scripts/` and `templates/scripts/` copies of the preflight must stay
  byte-identical; both change together.
- Do not make the gate infer intent from the branch name. A repository may
  legitimately target a long-lived integration branch.

## Open questions (resolve in design)

- Split or single? The seeding defect is upstream (`task_store.py`), the
  detection is pack-local (`review-preflight.mjs`). The pack-local half can land
  immediately and catches every future occurrence, including ones created by an
  unpatched upstream. Whether the upstream half is filed here, filed as a
  separate parked task in the style of
  `.trellis/tasks/07-30-upstream-task-start-branch-recording`, or reported
  upstream first is the first decision.
- What should `task.py create` record instead — the repository default branch
  resolved from the remote HEAD, the merge-base branch, or nothing at all,
  leaving `base_branch` null until `set-base-branch` runs? A null would trip the
  existing non-empty rule at
  `scripts/sd-ai-command-pack-review-preflight.mjs:3302`.
- How is "the default branch" resolved inside the check, and what happens in a
  checkout with no remote? The preflight already resolves a default branch
  elsewhere; reusing that surface is preferable to adding a second one.
- The R4 survey has been run twice and moved: two exceptions on 2026-08-06, six
  on 2026-08-07, five of them dead references, four of those sharing one branch.
  The open question is no longer "what to do with that one record" but what the
  disposition rule is for a set that grows every session: correct each to `main`,
  or build the exemption mechanism first and enrol them. Correcting a record is
  only safe if nothing reads the field for that record's history, and that has
  been checked for none of the five new ones. Whichever route is chosen, the
  survey must be re-run at implementation time — a table this task carries will
  be stale again by then.

## Acceptance Criteria

- [ ] A root task record whose `base_branch` names a branch other than the
      repository default fails the preflight, with the task path and the
      offending value in the diagnostic.
- [ ] A root task record whose `base_branch` is the default branch passes.
- [ ] A child task record targeting the active branch still passes, proving the
      rule at `scripts/sd-ai-command-pack-review-preflight.mjs:3241` is intact.
- [ ] **Before remediation:** running the new rule over the active task records
      reports exactly the set a freshly re-run survey identifies, and no others.
      Re-run the survey at implementation time rather than trusting the table
      above — the set went from two records to six in one day, so a stale copy of
      it will make this criterion pass while records still fail.
- [ ] **After remediation:** every record in that set has been corrected or
      granted a recorded exemption, and the rule then reports nothing. These are
      two separate criteria on purpose: a population that still produces the
      survey's failure set has not been remediated, and a remediated population
      cannot still produce it, so one criterion asserting both at once is not
      satisfiable at any single moment.
- [ ] Replaying PR #342's original record — `base_branch` set to
      `chore/task-preflight-bare-filename-references` — fails the gate, as a
      regression test against the observed occurrence.
- [ ] The `scripts/` and `templates/scripts/` preflight copies are identical,
      proven by `diff`.

## Notes

- Source: audit on 2026-08-06. The Copilot comment on PR #342 is the primary
  evidence; the seeding line was then read directly and confirmed to be
  unconditional.
- `.trellis/tasks/07-30-upstream-task-start-branch-recording` is adjacent but
  distinct: it covers `task.py start` never writing `branch`. This task covers
  `task.py create` writing the wrong `base_branch`. Neither subsumes the other.
- Complex enough to need `design.md` and `implement.md` before `task.py start`:
  the upstream-versus-pack split is a real decision, and R2 and R3 constrain each
  other.
