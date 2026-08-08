# Preflight skips the planning branch-null rule it reports checking

## Goal

Make the default `node scripts/sd-ai-command-pack-review-preflight.mjs`
invocation enforce the planning-lifecycle rule it already contains, so a
`status: planning` task carrying a non-null `branch` fails locally instead of
reaching a human reviewer.

## Problem

The rule exists. `scripts/sd-ai-command-pack-review-preflight.mjs:2265-2267`:

```js
if (current.status !== 'planning' || current.completedAt !== null || current.branch !== null) {
  add('planning_lifecycle_mutation', `${taskDir}/task.json`, 'planning task must keep status planning, completedAt null, and branch null');
}
```

It is unreachable from the invocation developers actually run.
`validatePlanningBundle` has exactly one non-recovery call site, `:1157`, inside
the bookkeeping/finalization path:

```js
if (options.mode === 'completion') {
  validateCompletionBundle(entries, evidence, baseOid, add, { addAdvisory, deltaPaths });
} else {
  const taskEntries = bookkeepingTaskEntries(entries);
  if (taskEntries.length > 0) {
    validatePlanningBundle(entries, evidence, baseOid, add, { addAdvisory, deltaPaths });
```

The no-argument run performs the working-tree checks — diff size, authored
source lines, task-directory count, surface copies — and never enters that
branch.

### What makes this worse than an ordinary gap

The default run does not stay silent about the field. It prints:

```
PASS checked 1 changed Trellis task metadata record(s) for identity, lifecycle, branch, and link integrity.
```

So the operator is told `branch` and `lifecycle` were checked, by the same run
that did not check them. A gap that reports itself as covered is not a missing
check; it is a false one, and it removes the incentive to look.

### Reproduction

Verified against `4378d37b` on a real planning task
(`08-07-default-local-review-lanes`, `status: planning`):

```bash
python3 -c "import json;p='task.json';d=json.load(open(p));d['branch']='task/08-07-default-local-review-lanes';json.dump(d,open(p,'w'),indent=2)"
node scripts/sd-ai-command-pack-review-preflight.mjs
```

Observed:

```
exit=0
Review preflight: 0 failure(s), 0 warning(s).
PASS checked 1 changed Trellis task metadata record(s) for identity, lifecycle, branch, and link integrity.
```

Expected: a failure naming `planning_lifecycle_mutation`.

### Observed cost

On PR #364 this exact defect shipped to remote review. Preflight reported
`0 failure(s), 0 warning(s)` with `branch` set; the GitHub Copilot reviewer
caught it instead:

> PR description says `task.py start` has not been run and the task is
> planning-only, but `task.json` already records a concrete `branch`. Other
> planning tasks keep `branch: null` until the task is started.

A remote reviewer spending a round on something a local rule already encodes is
the failure mode preflight exists to prevent.

### The convention is universal, so the fix lands clean

Enumerated from the filesystem at `origin/main` (`4378d37b`), not sampled:

| Repository | Planning | Violations | Completed |
| --- | --- | --- | --- |
| `sd-ai-command-pack` | 52 | **0** | 286 |
| `sd-github-review` | 37 | **0** | 64 |

Zero pre-existing violations in either repository. The rule can be enforced
immediately without a migration or a grandfather list — the only task that ever
tripped it is the one that motivated this filing, and it was corrected by hand.

The 286 and 64 completed records matter for AC4: they are the population a
status-blind rule would start failing.

`base_branch` is conventionally set (`main`) and must stay set — only `branch`
is the planning-phase invariant. Any fix that clears both is wrong.

## Where the fix belongs

Not by calling `validatePlanningBundle` from the default path. That function is
bundle-scoped: its condition is `current.status !== 'planning' || ... ||
current.branch !== null`, which treats *any* non-planning status as a violation.
Correct inside a planning bundle, wrong as a general rule — it would fail every
legitimately `in_progress` task.

The default path already has the right seam. `:3029` calls

```js
validateTrellisBookkeepingMetadata(record, artifact.taskDir, artifact.archived)
```

per changed `task.json`, and that function (`:3342`) is what emits the
`field description must be a non-empty string` class of failure. It already
branches on the record's own status — `record.status === 'completed'` gates the
`completedAt` rules — but carries **no `branch` rule of any kind**.

Adding the planning invariant there conditions on the record's own status rather
than on bundle context, which is what makes AC4 hold without a special case:

```js
if (record.status === 'planning' && record.branch !== null) {
  issues.push('branch must be null while status is planning');
}
```

This is a proposed location, not a mandate — but a fix placed elsewhere has to
explain how it avoids failing `in_progress` tasks.

## Scope

In scope:

- Enforcing the planning `branch` invariant from the default working-tree
  invocation, for changed task records.
- Keeping the reported PASS line honest: it must name only the checks that
  actually ran on that invocation.

Out of scope:

- Changing the rule's content. `status`, `completedAt` and `branch` invariants
  are correct as written.
- The bookkeeping/finalization path, which already enforces this.
- `base_branch`, which is a separate field with the opposite convention.
- The documentation path-reference gap, filed separately as
  `08-07-ci-preflight-full-mode-gap`. Same script, unrelated defect.

## Acceptance criteria

- **AC1** — The reproduction above fails. Setting `branch` on a
  `status: planning` task and running the no-argument preflight exits non-zero
  and names the offending file and field.
- **AC2** — Reverting `branch` to `null` returns the run to
  `0 failure(s), 0 warning(s)`. Proves the new failure is attributable to the
  field and not to incidental strictness.
- **AC3** — A task correctly in `status: in_progress` with a non-null `branch`
  passes. This is the regression the naive fix causes, so it must be tested
  positively rather than assumed from the shape of the condition.
- **AC4** — An archived/completed task with a non-null `branch` passes.
  `validateTrellisBookkeepingMetadata` receives an `archived` flag and runs over
  archived layouts too; a rule that ignores status would fail history.
- **AC5** — Every existing task in the repository still passes, planning and
  archived alike. The survey above predicts zero new failures; AC5 is what
  confirms the prediction against the implementation rather than against the
  spec. Enumerate from `.trellis/tasks/**/task.json`, not from the changed set.
- **AC6** — The PASS line is verified against what ran. If the fix routes the
  check through a different function, the message must still be accurate for
  invocations where that function is skipped.

## Verification notes

AC1 is the load-bearing one and must be demonstrated failing *before* the fix,
not only passing after. A check newly wired in is exactly the kind that can be
reported as working while asserting nothing — which is the defect being fixed
here, and it would be ironic to reintroduce it in the repair.

AC5 cannot be satisfied by inspection. Enumerate from the filesystem
(`.trellis/tasks/*/task.json`), because a survey built from the tasks already in
mind cannot find the one nobody remembered.

## Not approved for implementation

`task.py start` has not been run; this task is `status: planning`.
