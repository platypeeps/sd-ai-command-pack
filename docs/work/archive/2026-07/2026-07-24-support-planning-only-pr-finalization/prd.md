---
title: Support planning-only PR finalization
status: done
created: 2026-07-24
branch: codex/stabilize-self-hosted-delivery-lifecycle
---
# Support planning-only PR finalization

## Goal

Allow a reviewed Trellis planning-only pull request to complete session
bookkeeping and merge through the normal `sd-housekeeping` lifecycle without
archiving, completing, or deactivating implementation tasks that remain in
`planning`.

Keep one user-facing finish/housekeeping experience. The workflow must select a
`completion` or `planning` finalization internally from deterministic task,
diff, and Git identity evidence; a caller assertion or new public bypass flag
is not sufficient.

## Confirmed Evidence

- The installed Trellis finish-work contract always archives the current task
  when one exists (`.agents/skills/trellis-finish-work/SKILL.md:50-58`).
- Trellis distinguishes clearing a session pointer from completing a task:
  `task.py finish` preserves task status, while `task.py archive` writes
  `completed`, moves the task, and clears matching pointers
  (`.trellis/workflow.md:76`). The SD wrapper must not misuse either operation
  to manufacture merge evidence.
- The current housekeeping contract requires finish-work before every open
  feature-branch merge and accepts only a bare exact-head attestation
  (`templates/.agents/skills/sd-housekeeping/SKILL.md:24-33`).
- The eligibility evaluator checks that the supplied finish-work head equals
  the starting local head, but it does not distinguish completed-task
  finalization from planning-only session finalization
  (`templates/scripts/sd-ai-command-pack-pr-eligibility.py:845-859`).
- On 2026-07-24, reviewed PR #244 was clean and mergeable at
  `8dc8ca26b6c600d5bac4abe514a432d395c02184`, with all changed Trellis tasks
  still intentionally in `planning`. Canonical housekeeping returned typed
  `blocked` with `finish_work_missing` and left the branch untouched because
  truthful finish-work would have archived the current
  `add-bookkeeping-only-ci-fast-lane` task.
- Planning-only PR #225 is not a no-archive precedent: its final head also
  contained the archive of completed task
  `07-22-validate-task-context-before-pr` plus its journal record.
- The accepted command-surface direction is a clean orthogonal interface with
  no compatibility aliases or hidden duplicate modes. Planning finalization
  therefore belongs inside the existing finish-work/housekeeping composition,
  not in a second public command.

## Dependencies And Boundaries

- Parent: `07-22-streamline-sd-skill-workflows`; this task owns recent-run
  finding H09.
- Journal-only recovery child:
  `07-25-support-journal-only-finalization-recovery`.
- Post-archive review finalization child:
  `07-25-support-post-archive-review-finalization`; it owns exact-head
  completion-successor evidence when reviewed code fixes follow an already
  validated archive/journal tail, without widening planning mode or recording a
  duplicate session.
- Result-schema compatibility child:
  `07-28-decide-housekeeping-result-schema-compatibility`.
- Receipt-path validation child:
  `07-28-validate-finish-work-receipt-path`.
- Depends on `07-24-validate-finish-work-bookkeeping-before-push` publishing
  the canonical versioned task/journal validator. Extend that validator with a
  planning-finalization mode rather than creating a second metadata policy.
- Depends on `07-24-reread-pr-head-at-eligibility-completion` landing or being
  reconciled in the same implementation sequence because both tasks change
  the eligibility evaluator's final identity boundary.
- `07-24-add-bookkeeping-only-ci-fast-lane` consumes a valid planning
  finalization as another journal/task-only successor; it does not define the
  finalization state machine.
- `07-24-simplify-review-shipping-composition` and the routed-review tasks
  consume the resulting exact-head finalization evidence. They must not add a
  parallel planning exemption or merge path.
- Keep housekeeping as the sole merge mutation owner. Preserve clean-tree,
  local/remote/PR head equality, green required checks, clean merge state,
  complete unresolved-thread polling, and the mutation-boundary head recheck.
- Implement entirely in this command pack. Do not modify or publish upstream
  Trellis without separate explicit approval.
- Keep `templates/**` authoritative and synchronize every generated/dogfood
  mirror through the normal pack workflow.

## Requirements

- R1: Introduce one versioned finalization evaluator with two outcomes:
  `completion` and `planning`. It must also return bounded `blocked`,
  `indeterminate`, and `failed` results with stable reason codes. Mode selection
  is computed from repository evidence, never accepted from caller prose.
- R2: Select `planning` only when the full PR base-to-head range is linear and
  contains at least one Trellis planning artifact; every changed path is a
  bounded, regular, non-executable file below active `.trellis/tasks/**` or the
  final session record below `.trellis/workspace/**`; no archive path, task
  deletion, completed timestamp, lifecycle regression, symlink, submodule, or
  unsupported type transition is present.
- R3: Validate every added or modified task and its affected topology closure.
  New tasks must be `planning`; existing changed tasks must remain `planning`;
  directory identity, parent/child reciprocity, required metadata, PRD context,
  JSON/JSONL shape, placeholders, and whitespace must pass the canonical
  bookkeeping rules.
- R4: A planning finalization records the session through the canonical SD
  recorder but performs no `task.py archive`, no `task.py finish`, no status or
  completion-time mutation, and no active-session-pointer mutation. An active
  task may be absent; if present, it must be a planning task in the changed
  topology closure and must remain the current planning task after cleanup.
- R5: Emit a versioned typed finalization receipt bound to repository identity,
  PR/base identity, full base and final head OIDs, finalization mode, changed
  task IDs, preserved active-task identity, journal commit, validator result,
  and stable reason codes. Durable output must not expose absolute paths.
- R6: Replace the bare `finishWorkRequired`/`finishWorkHead` trust decision with
  the typed finalization evidence after all callers migrate. Eligibility must
  independently recompute or verify the receipt against Git and GitHub state;
  it must not trust a requested mode or head alone. Remove the retired
  attestation option and reader instead of maintaining dual compatibility.
- R7: Keep one public composition: `sd-finish-work` selects and records the
  finalization, then review/ship re-enters checks and review for the resulting
  exact head, and `sd-housekeeping` evaluates that head and remains the only
  merge/cleanup owner. Do not add a public `planning-finish` command or require
  the user to choose the internal mode.
- R8: Preserve completion semantics. A started task whose acceptance criteria
  are complete still validates before archive, archives through Trellis,
  records the journal, and produces `completion` evidence. Planning mode must
  never become a fallback for an incomplete, invalid, or ambiguous completion.
- R9: Keep finalization idempotent and recoverable. A retry after a journal
  commit or push must detect and reuse the exact valid state, never duplicate a
  journal entry, archive a planning task, rewrite history, or push more than one
  successor per finalization attempt.
- R10: Any code, workflow, configuration, specification, mixed, malformed,
  non-linear, stale, missing-object, or identity-ambiguous delta must reject
  planning mode. It may route to normal completion only when completion is
  independently valid; otherwise it blocks before merge.
- R11: Extend typed housekeeping/status reporting so operators can distinguish
  `completion`, `planning`, and missing/invalid finalization evidence without
  treating the presence of a still-planned active task as a cleanup anomaly.
- R12: Preserve unavailable/failure distinctions, checkout containment, output
  bounds, secret safety, and noninteractive behavior across the helper, skill,
  eligibility, and housekeeping surfaces.

## Acceptance Criteria

- [x] A fixture matching PR #244—multiple new and modified planning tasks, one
  preserved current planning task, a journal successor, and no product/runtime
  path—selects `planning`, records exactly one session, produces exact-head
  evidence, merges through housekeeping, and leaves every task and the active
  pointer in `planning` on synchronized `main`.
- [x] Planning finalization with no active task succeeds when all other scope
  and topology evidence is valid; an active task outside the changed planning
  closure blocks with a stable reason.
- [x] Source, workflow, config, spec, archive, completed/in-progress task,
  deletion, invalid topology/metadata, executable, symlink, submodule,
  non-linear history, stale head, or malformed receipt fixtures cannot select
  planning mode or reach the merge mutation boundary.
- [x] Existing completion fixtures still require pre-archive validation,
  archive the completed task, record the journal, and emit `completion`
  evidence; no completion case silently downgrades to planning.
- [x] Eligibility rejects missing, stale, wrong-repository, wrong-PR,
  wrong-base, wrong-mode, tampered, or caller-only evidence and re-reads the PR
  head before returning eligible.
- [x] Retry fixtures around journal creation, push, review/check settlement,
  and housekeeping produce no duplicate journal, false archive, second merge,
  or extra successor push.
- [x] The public catalog exposes no new finalization command or mode flag, and
  the retired bare finish-work-head attestation has no live option, parser,
  environment reader, help text, or compatibility branch after cutover.
- [x] Typed skill/runtime, eligibility, housekeeping, status, and install
  fixtures cover both modes and every fail-closed boundary; generated parity,
  command-surface drift checks, install audit, `make sync`, and `make check`
  pass.

## Post-Archive Handoff

- PR #244 (or a freshly based equivalent planning-only PR) is exercised as an
  end-to-end dogfood after the implementation lands; its final receipt,
  CI/review result, merge, task preservation, and cleanup identities are
  recorded in this task with no force-push or history rewrite unless the user
  separately authorizes that recovery. Deferred to the post-merge phase by
  explicit maintainer decision so the stabilization release is not delayed.
- Final program integration including H09 — proving planning-only finalization
  composes with the routed-review successor policy and bookkeeping-only CI lane
  without adding another merge authority — is completed in the broader program
  integration task after this PR merges, per the same maintainer decision.

## Out Of Scope

- Changing upstream Trellis archive, status, or session-pointer behavior.
- Treating a planning-only classification as review, CI, or merge authority by
  itself.
- Allowing arbitrary documentation-only PRs, code-bearing task PRs, archive
  moves, or user-declared path lists into planning mode.
- Preserving the bare finish-work-head attestation as an alias or fallback.
- Implementing the CI fast lane, routed-review provider policy, or final program
  integration inside this task.

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/archive/2026-07/07-24-support-planning-only-pr-finalization`:

- research/planning-only-housekeeping-gap.md
- validation.md
