# Design: unblock finalization for the thin-consumers tree

Fixes the state, not the gate. Evidence gathered 2026-08-12 against the
working tree at `93dbff9d`, not from memory.

## Evidence

**Every other active parent task is `planning`.** Enumerated by reading
each `task.json` under `.trellis/tasks/` and keeping those with a
non-empty `subtasks`/`children` array:

| Task | status | branch | children |
| --- | --- | --- | --- |
| `07-22-integrate-routed-review-backends` | `planning` | null | 5 |
| `07-22-streamline-sd-skill-workflows` | `planning` | null | 22 |
| `07-25-agent-artifacts` | `planning` | null | 4 |
| **`08-09-deployment-thin-consumers`** | **`in_progress`** | null | 8 |
| `08-09-thin-migration` | `planning` | null | 8 |

`08-09-thin-migration` is the decisive row: it is itself a parent of
eight children, four of them shipped, and it has stayed `planning`
throughout. The convention is already established and the thin-consumers
parent is the single outlier — one `task.py start` in `6e66f38a`.

**`in_progress` with `branch: null` is the signature of the defect.**
`task.py start` never writes `branch`; `sd-finish-work` documents this
and prepares the field itself at finalization. So a task that is
`in_progress` with `branch` still null was started and never implemented
against a branch — exactly this parent's history.

**The blocking rule is right; its premise does not hold here.**
`validatePlanningClosureActiveTasks`
(`scripts/sd-ai-command-pack-review-preflight.mjs:2335`) carries its own
rationale: a changed planning task linking to an `in_progress`/`review`
task outside the changed set means "the finalization would step over
in-flight implementation work". For a parent that is never an
implementation target there is no in-flight work to step over. The rule
is sound; the state it reads is wrong.

**No child blocks the flip.** All eight children resolved from the
filesystem: five `completed` in `archive/2026-08/`, three `planning`
and active (`08-09-thin-migration`, `08-09-plugin-closure-size`,
`08-09-machine-status-copy-unavailable`). None is `in_progress` or
`review`, so once the parent is `planning` the closure check has nothing
left to object to in either direction.

## D1 — Coordination parents stay `planning`

A parent that owns a requirement set, a child map, and cross-child
acceptance criteria, and that is not itself an implementation target,
stays `planning` for the length of the program. It is started only if it
acquires direct work of its own — at which point it has a branch, and
`in_progress` is then accurate.

Applied here: `08-09-deployment-thin-consumers` returns to `planning`.
No other active parent needs changing; the enumeration above is the
check, and it found exactly one outlier.

Consequence to state rather than discover later: when the program does
finish, the parent will need `task.py start` before it can be archived
`completed`, because completion runs from an active task. That is one
command at the end, against the current situation where its whole
subtree cannot be finalized at all. It is not this task's work.

## D2 — Rejected: widen the closure rule

The alternative was teaching `validatePlanningClosureActiveTasks` to
accept an `in_progress` neighbour whose `branch` is null. Rejected:

- it weakens a merge gate to accommodate one task's wrong state, and the
  same null-branch signature is produced by a task that genuinely was
  started and is mid-implementation before its first finalization;
- the rule's premise is correct for every case it was written for; and
- the state fix is a three-field data change with no behavior surface,
  while the rule change ships in the validator that every consumer's
  merge gate runs.

`08-09-update-branch-linearity-conflict` separately owns the other half
of the wall #434 hit — `completion_successor_history_non_linear` when a
ruleset `update-branch` merge commit lands in the successor range. That
is a real validator defect and stays that task's. Fresh evidence for it:
`gh pr update-branch` on #437 put merge commit `da96070a` on the branch
2026-08-12; it merged only because no finalization ran against it.

## D3 — The flip must land before the finalization base

`validatePlanningFinalization` checks the changed task record twice: the
current record must be `planning`/`completedAt: null`/`branch: null`
(`planning_lifecycle_mutation`, line 2312), **and** the record at the
bundle base must already have been a valid planning task
(`planning_baseline_invalid`, line 2324).

So the status flip cannot ride in the finalization range. It goes in a
work commit, and the finalization base is the last work commit after it.
Commit order on the branch:

1. work — flip `08-09-deployment-thin-consumers` to `planning`;
2. work — the parent's doc corrections;
3. **base = HEAD of (2)**;
4. bookkeeping — journal session citing (1) and (2).

At the base the parent is already `planning`, so both checks pass. The
receipt is `--mode planning`, subtype `journal-only-recovery`, whose
documented precondition is that the cited work commits are already
published — so (1) and (2) are pushed before the journal is recorded.

## D4 — The flip is a direct `task.json` edit

No CLI writes the top-level `status` field. `task.py` exposes
`start`, `finish`, and `set-meta`; `finish` only clears the active-task
pointer and leaves `status` untouched (`.trellis/scripts/task.py:146`),
and `set-meta` writes into the nested `meta` object — demonstrated
2026-08-12 when `set-meta description` produced `meta.description` and
left the top-level `description` empty, failing the preflight until the
field was edited directly.

So the flip edits `task.json` directly and runs `task.py validate` on
the result. `completedAt` and `branch` are already `null` and are
asserted unchanged rather than assumed.

## D5 — Recurrence

There is no repo-owned task-lifecycle spec surface to record D1 in:
Trellis owns `.trellis/workflow.md`, and grepping `.trellis/spec/` and
`CONTRIBUTING.md` for parent-task guidance returns only an unrelated
frontend adapter file. D1 is therefore recorded in the parent's own
`prd.md`, next to the sentence that already says it is not the
implementation target — the place a reader is standing when the question
arises.

## Rollback

One branch, three commits, no generated artifacts and no code. Reverting
the status flip restores the previous state exactly; the corrections are
prose. Nothing here touches the installer, the payload, or any consumer.
