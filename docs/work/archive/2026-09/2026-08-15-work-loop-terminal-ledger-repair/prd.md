---
title: Repair work-loop ledger evidence on a terminal run
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-15
---
# Repair work-loop ledger evidence on a terminal run

## Goal

Give a stopped work-loop run one sanctioned way to correct the `current` block's
`branch`, `head`, and `lastShippedSha`, and stop `reconcile` from damaging a
terminal run's checkpoint when an operator reaches for it as the nearest thing
available.

Today a run that stops after a merge keeps whatever `current` evidence it held
at its last mutating command. Every recovery command either refuses to run,
declines to touch those fields, or makes the ledger worse, so the only remaining
remedy is a hand-edit of the user-local `state.json` — outside the CLI, outside
its validation, and outside any audit trail.

## Observed Occurrence

Consumer repo `rwbp/rwbp-website`, pack v0.71.6, run
`d83bb64904154b00ba58e169e9301cde`. The run shipped PR #240, merged it through
housekeeping, processed follow-ups, and stopped with `operator_stop` at the
user's `stop after current` instruction. Afterwards the ledger's `current` block
still named the deleted feature branch and its pre-merge head, while
`git rev-parse origin/main` reported the merge commit. The repository was clean
and synchronized; only the ledger disagreed.

Recovering it took a hand-edit of `state.json` plus a manual restoration of
`checkpoint` and `contextHealth` from values read out of the helper's own source.

## Relationship To Existing Work

`08-09-work-loop-pr-supersession` owns the `#404` defect family: one-shot
merge-boundary evidence after branch deletion, and the missing sanctioned skip
from `selected`. Both of those live *before* the run stops, while a lock is still
held and phases can still advance.

This task owns the terminal dimension only: what a run can do about its own
`current` evidence once `phase` is `stopped`. Same ledger and probably the same
test harness, so the two are worth sequencing together, but the failing code
paths do not overlap — nothing in `#404` would have repaired the run above.

## Verified Findings

Line references are `scripts/sd-ai-command-pack-work-loop.py` at the commit this
task branches from.

1. **`stop` never records the post-merge boundary.** The handler sets
   `item["phase"] = "stopped"` (`:3159`) and writes a `checkpoint`; it does not
   read Git and does not touch `current.branch`, `current.head`, or
   `current.lastShippedSha`. A run whose last `evidence` call predates the merge
   therefore stops holding stale values by construction, not by operator error.

2. **`evidence` is unreachable after `stop`.** `stop` releases the run lock
   (`LOCK_RELEASING_STATUSES`, `:62`), and only two call sites opt into
   `released_lock_statuses` — `checkpoint` (`:2990`) and `stop` itself (`:3174`).
   `evidence` does not, so it fails with `work-loop state does not exist:
   …/lock.json` rather than with a statement about terminal runs. The mechanism
   for tolerating a deliberately-released lock already exists; `evidence` simply
   does not use it.

3. **`reconcile-terminal` cannot repair these fields even when it is allowed to
   run.** Its write path (`:1652-1668`) sets `terminalReconciliation`,
   `contextHealth`, and `checkpoint`, and nothing else — `current` is untouched.
   So the `--archived-task` gate (`:2784`, required) is not the only obstacle:
   the command is not a repair path for `current` evidence at all.

4. **The `--archived-task` gate additionally excludes legitimate multi-slice
   work.** `validated_archived_task` (`:1348-1400`) requires a normalized path
   below `.trellis/tasks/archive/` holding a `task.json` with
   `status == "completed"`. A task that deliberately stays `in_progress` across
   several slices — the observed case, six slices with one shipped — can never
   satisfy it, because the run being reconciled shipped real work for a task that
   is correctly still open.

5. **`reconcile` on a terminal run is actively destructive.** It is read-only for
   `current` but not for the rest of the state: it overwrote a clean
   operator-stop checkpoint with `state: "blocked"`, repeated invocations
   accumulated stale reasons, and `contextHealth` reached `red` at epoch 2 with
   `phase stopped cannot own a recovery checkpoint; checkpoint recovery requires
   every recorded current-state field`. The operator is left worse off than
   before, having run the command the status output pointed them at.

6. **`stopped` is genuinely terminal.** `TRANSITIONS["stopped"]` is an empty
   frozenset (`:168`), so there is no phase move out of it and no existing
   same-phase command that may write `current`.

## Requirements

- A stopped run must have exactly one sanctioned, validated way to correct
  `current.branch`, `current.head`, and `current.lastShippedSha` against live Git,
  without hand-editing `state.json`.
- That path must verify the values it records against the repository rather than
  trusting the caller: the branch is the base branch, the head resolves and
  matches its remote-tracking branch, the shipped SHA is an ancestor reachable
  from that head.
- It must not require the run's Trellis task to be archived or completed. A
  multi-slice task that stays `in_progress` is a supported shape, not an
  anomaly.
- It must preserve the terminal record: the stop reason, the operator-stop
  checkpoint, and `contextHealth` survive a successful repair unchanged. Repair
  is not recovery and must not present itself as a resumable run.
- `reconcile` on a run whose `status` is `stopped` or `completed` must refuse
  with a typed diagnostic naming the repair command, and must leave `checkpoint`
  and `contextHealth` byte-identical. Refusing is the fix; a terminal run has
  nothing for it to reconcile.
- The typed status `recovery.reasonCode` must route an operator to the repair
  path for a stale-evidence terminal run, distinctly from `run_stopped`, which
  currently sends them to `references/run-recovery.md` and therefore to
  `reconcile`.
- Whether the repair is a new subcommand, a `--terminal`-style flag on
  `evidence`, or a widening of `reconcile-terminal` is a design decision, not a
  requirement. Widening `reconcile-terminal` means dropping `--archived-task`
  from required and teaching it to write `current`; both are behavior changes to
  a command that currently means something narrower.

Out of scope: the `#404` pre-stop merge-boundary gaps, which
`08-09-work-loop-pr-supersession` owns; any change to what `stop` itself records
at the moment it retires a run (worth considering there, since a `stop` that
captured the boundary would prevent most of this, but it is a separate behavior
change with its own compatibility surface).

## Acceptance Criteria

- [ ] A run stopped with `operator_stop` after a merge can correct all three
      `current` fields through a documented command, and the resulting values
      match `git rev-parse` for the base branch and the shipped SHA.
- [ ] That command succeeds while the run's Trellis task is still
      `in_progress`, with nothing under `.trellis/tasks/archive/` for it.
- [ ] After a successful repair, `checkpoint.state`, `checkpoint.reason`, and
      `contextHealth` are unchanged from their post-`stop` values, verified by
      comparing the state before and after.
- [ ] The command rejects a `head` that is not the base branch's verified head,
      a `lastShippedSha` unreachable from it, and a `branch` that is not the base
      branch — each with a distinct typed diagnostic, and each leaving the ledger
      unmodified.
- [ ] `reconcile` against a stopped run exits with a typed diagnostic naming the
      repair command, and a byte-comparison of `state.json` before and after
      shows no change. A regression test covers the specific damage observed:
      `checkpoint.state` must not become `blocked` and `contextHealth.level` must
      not become `red`.
- [ ] Running the repair twice with the same verified values is a no-op that
      succeeds, matching `reconcile-terminal`'s existing idempotency contract
      (`:1640-1650`). Note that `reconcile-terminal` *rewrites* `checkpoint` and
      `contextHealth` on success (`:1658-1667`), which is the opposite of the
      preservation required above — reconciling those two contracts is part of
      the design, not an oversight in either.
- [ ] Status output for a stopped run with stale `current` evidence reports a
      `recovery.reasonCode` that routes to the repair path, and the matching
      reference file exists and is listed in the skill's conditional-reference
      table.
- [ ] `references/terminal-reconciliation.md` states plainly that
      `reconcile-terminal` does not write `current`, so a future reader does not
      repeat the assumption that it is the repair path.

## Validation

- Unit tests over the helper's state machine for each acceptance criterion
  above, driving a synthetic ledger through `start` → shipped evidence → `stop`
  → repair, asserting on the persisted JSON rather than on command output.
- A refusal test per rejected input, each asserting both the exit status and
  that `state.json` is unchanged.
- Manual replay against the observed occurrence: reconstruct the
  `d83bb64904154b00ba58e169e9301cde` shape from the recorded values in this PRD
  and confirm the repair command reaches the same end state the hand-edit
  produced.
