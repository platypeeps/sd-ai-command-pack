# Parent task `in_progress` blocks bookkeeping finalization for its whole child tree

## Problem

`08-09-deployment-thin-consumers` is a coordination parent. Its own PRD
says so in the first paragraph: "Children carry the independently
verifiable deliverables; this task is not the implementation target."
It was nevertheless started — `6e66f38a`, `chore(task): start
deployment-thin-consumers parent (planning -> in_progress)` — and it has
stayed `in_progress` ever since, with `branch: null`, because no branch
ever implements it directly.

That state makes its entire subtree unshippable through ordinary
bookkeeping finalization. Demonstrated 2026-08-12 across three pull
requests, each failing a different way:

1. **#434** edited the parent's own directory.
   - `final-bundle --mode planning` → `planning_baseline_invalid` +
     `planning_lifecycle_mutation` on
     `.trellis/tasks/08-09-deployment-thin-consumers/task.json`
     ("existing task was not a valid planning task at the bundle base").
   - `final-bundle --mode completion` with base equal to head, the
     `active-task-review-successor` recovery →
     `completion_successor_history_non_linear`: the bounded search over
     that task's own bookkeeping history reaches merge commits
     (`72791065`, `d7913054`, …), which is a documented fail-closed path.
2. **#435** dropped the parent's files and changed only two of its
   children (`08-09-thin-migration`, `08-10-thin-canary-conversion`).
   Not sufficient — `planning_active_task_outside_closure`: "linked task
   08-09-deployment-thin-consumers is in_progress; planning finalization
   must not leave an active task outside the changed planning closure."
   The constraint is the parent-child linkage, not the file set.
   `.github/workflows` runs the same validator, so the journal commit
   turned the PR red and `BLOCKED` on branch protection.
3. **#436** shipped only by omitting finalization entirely: the branch
   was rebuilt at its last commit before the journal, and merged with no
   journal session recorded for that work.

`task.py finish` does not help — it clears the active-task pointer and
leaves `status` untouched (`.trellis/scripts/task.py:146`).

So today the tree has three states and no good one: edit the parent
(mode 1, blocked), edit any child (mode 2, blocked), or ship without a
journal (mode 3, what #436 did — bookkeeping silently skipped).

## Goal

A coordination parent that is legitimately open for the length of a
program must not make its own artifacts and its children's artifacts
unshippable. Fix the state, the mechanism, or both, and decide which.

## Requirements

1. **Decide the correct lifecycle state for a coordination parent** that
   owns requirements and a child map but is never an implementation
   target. Candidates: it stays `planning` for the program's duration
   and is started only if it acquires direct work; or `in_progress`
   stays correct and the finalization closure rule learns to accept a
   parent with no direct changes. Evidence for the decision comes from
   the validator's own rules and from how the other parent tasks in
   `.trellis/tasks/` are actually being used — enumerate them, do not
   assume this parent is unique.
2. **Apply the decision to `08-09-deployment-thin-consumers`**, and to
   any other active parent the enumeration in requirement 1 shows is in
   the same state.
3. **Land the parent's outstanding doc corrections**, which are blocked
   behind this and are the reason it surfaced. Both files still assert
   the pre-0.71.2 `codex` vendored-retention carve-out that PR #433
   retired:
   - `prd.md` — the retention acceptance criterion is titled "Codex/pi
     retention holds", states `shared` carries `["codex", "pi"]`, and
     repeats the probe-falsified justification that Codex "never reads
     `~/.agents/skills`" verbatim. Retitle to pi, `["pi"]`, and cite
     `.trellis/tasks/archive/2026-08/08-09-codex-home-skills-family/research/codex-skills-resolution-probe.md`.
   - `prd.md` — the child task map omits three declared children
     (`08-09-plugin-closure-size`,
     `08-09-machine-status-copy-unavailable`,
     `08-09-codex-home-skills-family`), which the review preflight's
     declared-children rule fails on as soon as the file is touched.
   - `design.md:~190` — states `shared` carries `["codex", "pi"]` as a
     live design claim, and describes the undeclared-marker rule as an
     unconditional blocker. Since 0.71.2 the blocking set is derived
     from `retainVendoredFor`, making pi blocking and codex advisory.
   - `design.md:~195` and `prd.md:~127` — both cite
     `08-09-thin-machine-installer/research/platform-verification.md`.
     That task is archived; the file exists only under
     `.trellis/tasks/archive/2026-08/`. Found by Copilot on #434.

   The corrected text for all four sites was written and verified
   (`make full-check`: 0 failures) on the abandoned branch whose commits
   are `d386f250` and `d3b34c8b` — reachable from PR #434, which is
   closed rather than deleted. Recover it from there rather than
   re-deriving it.
4. **Record the missing journal session for #436's work**, or state
   explicitly why it is not owed. That work merged without one because
   finalization could not run.

## Acceptance criteria

- [ ] The lifecycle decision is recorded with its reasoning, and the
      enumeration backing it lists every active parent task and its
      status — produced by reading `task.json` files, not from memory.
- [ ] A branch that changes only `08-09-deployment-thin-consumers` and a
      branch that changes only one of its children each produce a
      `status: valid` `final-bundle` receipt. Both cases are checked:
      #435 proved that fixing the parent case alone does not fix the
      child case.
- [ ] The four correction sites in requirement 3 are landed, and a
      repo-wide grep for `"codex", "pi"` and for `codex` beside
      `retainVendoredFor` returns hits only in these classes: the
      archive, the CHANGELOG's historical entries, journal history,
      **the annotated dated snapshot at
      `08-09-thin-migration/design.md:26`**, which deliberately keeps
      the superseded literal because that section is a measurement at
      `d7913054`, and **this task's own artifacts**, which quote the
      wrong text in order to name it. A criterion demanding zero live
      hits would be unsatisfiable, and #436 already merged the
      annotation that makes the snapshot correct.
- [ ] `.trellis/tasks/08-09-thin-machine-installer/` is confirmed
      absent and every surviving citation of it resolves under
      `.trellis/tasks/archive/2026-08/`, checked by resolving each path
      from the filesystem rather than by reading the prose.

## Out of scope

- The canary conversion itself, which needs its own per-cohort user
  authorization.
- Changing the validator's merge-commit handling in the
  `active-task-review-successor` recovery. That fail-closed behavior is
  documented and was not wrong here; the parent's status is the defect.
