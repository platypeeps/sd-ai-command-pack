# Enforce pre-archive acceptance readiness

## Goal

Extend the command-pack bookkeeping validator so `pre-archive` fails before
Trellis mutation when a task still has incomplete required acceptance criteria
or represents post-archive obligations ambiguously.

The check must implement the lifecycle contract from
`07-28-clarify-completion-housekeeping-obligations` without treating every
unchecked Markdown checkbox anywhere in a PRD as a completion blocker.

## Confirmed Evidence

- `templates/scripts/sd-ai-command-pack-review-preflight.mjs` already provides
  the canonical read-only `pre-archive` validator and emits bounded typed
  findings with stable reason codes.
- The current validator checks task metadata, layout, lifecycle state,
  topology, context placeholders, size, regular-file status, and UTF-8, but it
  does not evaluate the PRD's acceptance readiness.
- In `platypeeps/rwbp-coordinator` PR #187, an archived task had unchecked
  merge/housekeeping criteria even though its implementation and exact-head
  review work were complete. Copilot discussion `discussion_r3661730449`
  exposed the resulting contradiction.
- Historical task `07-06-close-fleet-refresh-loop` reconciled several earlier
  archived tasks with unchecked post-merge criteria, demonstrating a recurring
  class of bookkeeping drift.

## Requirements

- R1: Extend the existing `pre-archive` path; do not add a second validator or
  divergent acceptance-criteria parser.
- R2: Parse only the bounded, regular, valid-UTF-8 task PRD already admitted by
  the bookkeeping validator. Evaluate the canonical acceptance section defined
  by `07-28-clarify-completion-housekeeping-obligations`.
- R3: Reject incomplete required pre-archive criteria with stable reason codes,
  source-relative path evidence, and concise human and schema-versioned JSON
  output before `task.py archive` runs.
- R4: Recognize the approved representation for post-archive housekeeping
  follow-through so valid downstream obligations do not produce false
  completion failures.
- R5: Fail closed on malformed or ambiguous acceptance structures, unsupported
  headings, invalid checkbox syntax in the completion section, duplicate
  lifecycle sections, or an inability to classify an unchecked obligation.
- R6: Remain read-only and deterministic. Do not rewrite PRDs, check boxes,
  task metadata, session pointers, branches, or journal records.
- R7: Preserve completion and planning finalization semantics, exact-head
  review/CI gates, and housekeeping merge authority. Acceptance readiness is
  bookkeeping evidence, not review or merge authorization.
- R8: Change the canonical template first and keep the root dogfood copy,
  documentation, provenance, and generated surfaces synchronized.

## Acceptance Criteria

- [x] A completion-ready task with every required acceptance criterion checked
  passes `pre-archive` with the existing valid receipt semantics.
- [x] An unchecked required pre-archive criterion fails with a stable typed
  reason before archive and leaves the task, journal, session pointer, and Git
  state unchanged.
- [x] A task using the approved post-archive handoff representation passes even
  when its downstream merge or cleanup work has not yet occurred.
- [x] Unchecked boxes outside the canonical completion section do not become
  accidental blockers unless the lifecycle contract explicitly classifies
  them as completion obligations.
- [x] Malformed, duplicated, ambiguous, oversized, symlinked, and invalid-UTF-8
  fixtures fail closed with bounded repository-relative diagnostics.
- [x] Focused tests cover valid completion, incomplete completion, valid
  post-archive handoff, planning finalization, and the PR #187 regression.
- [x] `sd-finish-work` still invokes `pre-archive` before `task.py archive`, and
  no failure path mutates or publishes task state.
- [x] Template/root parity, installer and generated-surface checks,
  `make sync`, and `make check` pass.

## Notes

- Depends on `07-28-clarify-completion-housekeeping-obligations` defining the
  accepted lifecycle representation and authoring examples.
- Primary implementation surfaces are the canonical review-preflight helper
  and `tests/test_bookkeeping_validator.py`; skill sequencing assertions remain
  in `tests/test_sdlc_commands.py`.
- Implement entirely in this command pack. Do not modify or publish upstream
  Trellis without separate explicit approval.
