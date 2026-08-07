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

The SD flow gives a task scaffold its own branch: the review preflight permits
at most one Trellis task directory per diff, so filing a task means creating a
branch, creating the task on it, and opening a pull request. Every task created
that way gets its own feature branch recorded as the target it should be merged
*into*.

Both tasks filed on 2026-08-06 hit it:

- `08-06-local-provider-empty-scope` — corrected by hand before its PR opened.
- `08-06-preflight-bare-filename-references` — reached PR #342 with
  `base_branch: "chore/task-preflight-bare-filename-references"`, passed the
  deterministic gate with 0 failures and 0 warnings, and was caught by a paid
  Copilot round. Fixed in `5779c242`.

It is not new, and not confined to this week. Surveying every active task record
gives 43 of 45 recording `main`, with two exceptions:

- `07-30-upstream-task-start-branch-recording` records
  `fix/silence-satisfied-scope-advisory` — a root task, authored 2026-07-30,
  already merged to `main` carrying a feature branch as its stated PR target.
- this task's own record, created the same way and corrected by hand before
  its pull request opened.

So the value is wrong roughly whenever a task is filed through the normal SD
flow, and at least one wrong record has already been merged and sat unnoticed
for a week.

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
- The R4 survey is already done: 43 of 45 active records name `main`, and
  `07-30-upstream-task-start-branch-recording` names
  `fix/silence-satisfied-scope-advisory`. Open question is what to do with that
  one — correct it to `main`, or treat it as the exception mechanism's first
  case. Correcting it is only safe if nothing reads the field for that record's
  history.

## Acceptance Criteria

- [ ] A root task record whose `base_branch` names a branch other than the
      repository default fails the preflight, with the task path and the
      offending value in the diagnostic.
- [ ] A root task record whose `base_branch` is the default branch passes.
- [ ] A child task record targeting the active branch still passes, proving the
      rule at `scripts/sd-ai-command-pack-review-preflight.mjs:3241` is intact.
- [ ] Running the new rule over all current active task records reports exactly
      the known non-default record,
      `07-30-upstream-task-start-branch-recording`, and that record has been
      corrected or exempted before the rule is allowed to block.
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
