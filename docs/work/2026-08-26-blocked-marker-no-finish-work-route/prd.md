---
title: Blocked-marker bookkeeping has no route through the finish-work gate
status: planning
created: 2026-08-26
---
# Blocked-marker bookkeeping has no route through the finish-work gate

## Origin

Found on 2026-08-26 while landing PR #567, which recorded the `sd-review-pr`
retirement program's blocking relationships in `task.json`. Those relationships
lived only in PRD prose, so every ranking consumer treated gated tasks as
actionable — a mistake made twice in one session, once by the work loop and
once by hand.

Two of the four records could not be landed. Not by any mode, and not by
resplitting: three separate refusals, each measured rather than argued.

## Measured: three refusals, no route between them

| record | status | mode attempted | refusal |
| --- | --- | --- | --- |
| `08-21-port-integration-only-profile` | `in_progress` | `--mode planning` | `planning_lifecycle_mutation` |
| `08-21-port-integration-only-profile` | `in_progress` | `--mode completion`, active-task successor | `completion_successor_history_non_linear` ×16 plus `completion_successor_scope_invalid` ×98 |
| `08-09-retire-review-pr-surface` | `planning` | `--mode planning` | `planning_active_task_outside_closure` |

### Why planning mode refuses

`validateBookkeepingPlanningBundle`
(`templates/scripts/sd-ai-command-pack-review-preflight.mjs:2698-2713`) requires
every task directory the cited commits touch to be a planning task at both the
bundle base and its head:

```
planning task must keep status planning, completedAt null, and branch null
existing task was not a valid planning task at the bundle base
```

An `in_progress` task fails both, and nothing about a two-key addition changes
that — the failing property is the task's own status, not the edit.

### Why the closure rule refuses the parent

`validatePlanningClosureActiveTasks` (`:2723-2756`) walks each changed planning
task's `parent` and `children`, and refuses any neighbour that is `in_progress`
or `review` and outside the changed set:

```
linked task 08-21-port-integration-only-profile is in_progress; planning
finalization must not leave an active task outside the changed planning closure
```

`08-09-retire-review-pr-surface` is the parent of that task, so it cannot be in
a planning bundle. **Adding the child to satisfy the closure rule re-triggers
the lifecycle rule above.** The two rules are individually sound and jointly
unsatisfiable for this shape.

### Why the completion route refuses

The `active-task-review-successor` recovery covers exactly this case on paper —
one `in_progress` task, bookkeeping limited to its own directory. In practice
its range runs "from the oldest reachable prior touch to the current head", and
for a task whose work merged long ago that walks back into `main` behind merge
commits. Measured on a branch whose only content was the two-key addition:

```
completion_successor_history_non_linear | successor commit 399b4e3857c6 must have exactly one parent
completion_successor_scope_invalid      | 98 paths across ~30 unrelated task directories
```

That is documented fail-closed behaviour, not a bug in the branch: "Bookkeeping
history older than the bounded search window still fails closed and is not a
bug." It does mean the sanctioned route does not reach this case.

## Why this matters more than it looks

`in_progress` is the **first** ranking tie-breaker in
`work-loop.py` — ahead of priority. So an `in_progress` task that is really
blocked outranks every actionable `P0`. The marker that would fix it is exactly
the marker that cannot be landed, and the window where it is needed is exactly
the window where it is unlandable: once the blocking dependency clears, the task
archives and the marker is moot.

`08-21-port-integration-only-profile` is live proof. Its work merged as PR #535;
it is held open only because acceptance criterion 1 was deferred to
`08-22-verify-ported-integration-only-path`. Nothing in its `task.json` says so,
so the loop selects it as top actionable work.

## The two payloads, preserved

These are the exact records that could not land. They are kept here so nothing
depends on a branch surviving; the branches carrying them were deleted after
this task was filed, and PR #567 (closed) holds the same diff.

`.trellis/tasks/08-09-retire-review-pr-surface/task.json`:

```json
{
  "blocked": true,
  "blockedReason": "coordination parent; must not be implemented directly -- implement children 08-21-port-integration-only-profile, 08-21-delete-review-pr-surface, 08-21-retire-full-check-family"
}
```

`.trellis/tasks/08-21-port-integration-only-profile/task.json`:

```json
{
  "blockedOn": "08-22-verify-ported-integration-only-path",
  "blockedReason": "criterion 1 is deferred to 08-22-verify-ported-integration-only-path; this task stays in_progress and must not be archived until that task ticks it"
}
```

Both are pure key additions: `status`, `completedAt`, and `branch` are
untouched. Marker placement follows the `07-25-dispatch-rollout` precedent
(immediately after `title`). `blockedReason` names concrete task IDs rather
than ordinals because `work-loop.py:868` reads

```python
reason = candidate.get("blockedReason") or candidate.get("blockedOn")
```

so `blockedReason` wins and is the only string a ranked report renders.

`08-21-retire-full-check-family` is deliberately **not** marked: its
independence was verified against `sd-review-pr`'s SKILL.md, which explicitly
forbids a full-check fallback, so it is genuinely actionable.

## Goal

A bookkeeping-only edit to an active task's `task.json` — one that changes no
lifecycle field — must have at least one route to a valid finish-work receipt,
whether the task is `planning` or `in_progress`, and whether or not it links to
an active task outside the changed set. Without weakening the property each
refusing rule protects.

## Directions worth weighing

- **A. A lifecycle-neutral bookkeeping delta.** The refusals all key on the
  task's *status* rather than on what the commit changed. A delta that provably
  touches no lifecycle field (`status`, `completedAt`, `branch`, `parent`,
  `children`) and no artifact body is a different kind of change from the ones
  these rules were written to police. Recognising it explicitly would clear all
  three refusals at once without relaxing any of them for ordinary edits.
- **B. Narrow the closure rule to what it protects.** It exists so a planning
  finalization does not archive a set while leaving a linked active task
  stranded. A change that alters no lifecycle field strands nothing. Narrowing
  the trigger from "any changed planning task" to "any changed planning task
  whose lifecycle fields moved" would fix the parent case alone — smaller than
  A, and insufficient on its own, since the `in_progress` child still fails.
- **C. Bound the active-task successor search by the task's own history.** The
  range currently starts at the oldest reachable prior touch. Starting it at the
  merge-base with the default branch would keep it on the branch's own commits.
  This is adjacent to `08-26-completion-successor-cc-overrefusal` and should not
  be designed independently of it.
- **D. Do nothing and document the gap.** Rejected: the workaround is a human
  waiving the merge gate, which is what PR #560 already had to do and what two
  tasks are now open to prevent.

A and C are complementary. B is subsumed by A.

## Out of scope

- The ranking policy that puts `in_progress` ahead of priority. That ordering is
  defensible; this task is about the marker being recordable, not about how a
  recorded marker is ranked.
- `08-26-completion-successor-cc-overrefusal`'s classifier change. It shares the
  `--cc`/merge-commit machinery and Direction C touches adjacent code, but its
  premise is base updates, not bookkeeping scope.

## Acceptance criteria

- [ ] A commit adding only `blockedOn`/`blockedReason`/`blocked` to an
      `in_progress` task's `task.json` reaches a valid finish-work receipt, with
      no history rewrite and no lifecycle field changed. The test is built from
      a real branch, not a synthesized range.
- [ ] A commit adding the same keys to a `planning` task that parents an
      `in_progress` task reaches a valid receipt, and the closure rule still
      refuses a bundle that actually moves a lifecycle field while leaving a
      linked active task outside the changed set.
- [ ] Both payloads recorded above are landed on their real task records, and
      `work-loop.py rank` reports both as blocked with the reason naming the
      concrete dependency task ID.
- [ ] A bundle that changes a lifecycle field on an `in_progress` task is still
      refused, and the test asserts the reason code rather than only the invalid
      status.
- [ ] All four copies of `sd-ai-command-pack-review-preflight.mjs` are
      byte-identical and `make generate` reports `shipped-surface closure:
      clean`:

      ```bash
      find . -name sd-ai-command-pack-review-preflight.mjs -not -path './.git/*' \
        -print0 | xargs -0 shasum -a 256 | awk '{print $1}' | sort -u | wc -l
      # expect exactly 1
      ```
