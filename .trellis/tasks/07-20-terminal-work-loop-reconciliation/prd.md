# Support terminal work-loop reconciliation

## Goal

Let operators safely reconcile a stopped or completed autonomous work-loop run
when verified task, Git, and GitHub state advanced after the loop released its
lock. The reconciliation must clear false red recovery guidance without
reviving the run, rewriting its historical lifecycle evidence, or weakening
the active-run state machine.

## Background

The existing helper supports same-phase evidence updates only while a run is in
an active evidence phase and owns its lock. `stop` releases that lock,
`mutate_state()` requires it for later mutations, and `validated_evidence()`
rejects the `stopped` phase. As a result, a run that stops red before an
operator completes its PR and Trellis bookkeeping can be audited but cannot be
marked reconciled through a supported command.

This is distinct from the completed
`07-19-work-loop-same-phase-evidence-updates` task. That task intentionally
preserved stopped, paused, and completed checkpoint intent while adding active
same-phase evidence updates.

The observed RWBP case is run `201a6f1c580a4e7c80305c3258066956`:

- delivery PR #147 merged head `a0858ac` as merge commit `f0ff6f6`;
- bookkeeping PR #148 archived the task and merged as `e312d9b`;
- the archived RWBP task `07-17-ci-gate-coverage` is completed;
- `main` is clean and synchronized; and
- the released-lock ledger remains stopped/red with the former active task
  path, merge-era HEAD, and obsolete reconciliation guidance.

## Requirements

### R1. Dedicated terminal operation

- Add a separate `reconcile-terminal` CLI path rather than allowing ordinary
  `evidence` or `reconcile` to mutate arbitrary terminal runs.
- Accept only ledgers whose status is `stopped` or `completed`.
- Never transition the run back to an active lifecycle phase or acquire the
  long-lived execution lock used by `start`.

### R2. Exclusive and fail-closed mutation

- Serialize the operation with a short-lived exclusive reconciliation lock and
  release it in `finally` handling.
- Reject a live run lock. Permit stale-lock recovery only through an explicit
  recovery flag after the existing process-liveness and repository-safety
  checks succeed.
- Keep state writes private, atomic, bounded, and byte-for-byte unchanged when
  any validation fails.

### R3. Verified terminal evidence

- Record terminal evidence separately from the original `current` lifecycle
  evidence so the historical stop remains auditable.
- At minimum record the archived task path and identity, delivery PR number and
  URL, shipped feature head, delivery merge commit, observed default branch and
  HEAD, optional bookkeeping PR and merge commit, timestamp, and reconciliation
  outcome.
- Verify locally that the archived task exists below `.trellis/tasks/archive/`,
  its `task.json` is completed, and its identity matches the recorded task.
- Verify that supplied commits exist locally, the shipped feature head matches
  or descends from the recorded shipped evidence, the merge commits contain the
  expected shipped/bookkeeping heads where the merge strategy permits that
  assertion, and the observed default branch and remote-tracking branch agree.
- Keep GitHub state collection in the orchestration skill: it must confirm the
  supplied PRs are merged and their heads/merge commits match before invoking
  the local helper. The helper must not infer network state.

### R4. Historical state preservation

- Preserve run ID, mode, selector, focus, iteration, counters, stop reason, and
  original `current` evidence.
- Do not increment `completed` or `mergedPrs`; work completed outside the loop
  must be represented by terminal reconciliation evidence, not rewritten as a
  loop-owned iteration.
- On success, set context health to green and mark the terminal checkpoint as
  reconciled/completed while keeping the lifecycle phase terminal.

### R5. Idempotency and contradictions

- Repeating the command with identical normalized evidence must succeed as a
  no-op.
- Different evidence for an already reconciled run must fail closed and leave
  the persisted state unchanged.
- Missing commits, mismatched task identity, an unarchived/incomplete task,
  dirty or divergent default-branch state, conflicting PR evidence, or an
  active owner must fail with actionable diagnostics.

### R6. Status and orchestration integration

- Update `sd-work-backlog` to collect exact Trellis, Git, and GitHub terminal
  evidence before invoking the helper.
- Update `sd-status` and housekeeping output to distinguish an unreconciled red
  terminal run from a reconciled historical run.
- A reconciled terminal run must not keep producing “Reconcile the red SD
  work-loop checkpoint” as the highest-priority next step.
- Keep template sources, installed mirrors, public docs, specs, manifest
  provenance, and command/help surfaces synchronized.

## Acceptance Criteria

- [ ] A stopped red run with no live owner can record verified post-stop task,
      delivery, bookkeeping, and default-branch evidence without being resumed.
- [ ] Successful reconciliation preserves the original lifecycle evidence and
      counters, writes a bounded terminal audit record, restores green context
      health, and marks the terminal checkpoint reconciled/completed.
- [ ] Identical repeated reconciliation is a no-op; conflicting repeated
      evidence fails without changing the ledger.
- [ ] Active/paused runs, live locks, unsafe stale locks, dirty trees,
      non-default branches, unsynchronized refs, missing or unrelated commits,
      incomplete/unarchived tasks, and mismatched PR evidence are rejected.
- [ ] Existing active-phase `transition`, `evidence`, `reconcile`, pause/resume,
      and stale-lock behavior remains unchanged.
- [ ] Status and housekeeping report reconciled runs as historical and stop
      recommending terminal reconciliation.
- [ ] Focused tests cover successful RWBP-shaped recovery, merge and squash
      ancestry variants, idempotency, every rejection boundary, atomic failure,
      old schema-version-1 ledgers, and generated template/root parity.
- [ ] Canonical repository checks and the full deterministic pack gate pass.

## Out Of Scope

- Resuming a stopped run or selecting its next task.
- Rewriting historical counters to pretend externally completed work ran inside
  the autonomous controller.
- Adding GitHub/network calls to the local ledger helper.
- Changing upstream Trellis runtime behavior.
- Automatically reconciling terminal runs without an explicit operator action.

## Open Questions

None currently block planning. Exact CLI flag names may be refined during
implementation while preserving the contracts above.
