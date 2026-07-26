# Support Journal-Only Finalization Recovery

## Goal

Allow `sd-finish-work` to recover safely when planning work was already
published before finish-work captured its finalization base, without fabricating
a task edit, widening the captured finalization range, or bypassing the
bookkeeping gate.

## Background

- Planning commits `d97244e` and `9c9b8c3` were already present on `main` and
  `origin/main` when finish-work began.
- Finish-work correctly captured `9c9b8c3` as its immutable base and created
  journal successor `686f484` without archiving a task.
- The exact `9c9b8c3..686f484` planning final-bundle failed with
  `planning_task_change_missing` because its delta contains only the new
  journal and index.
- The local journal commit must remain unchanged and unpushed until the same
  exact range validates.

## Requirements

- R1: Keep the public and internal CLI mode vocabulary at `completion` and
  `planning`. Journal-only recovery is an automatically detected planning
  subtype, not a user-selected third mode or a second finish command.
- R2: Preserve normal planning validation when the captured base-to-head range
  contains active planning task artifacts plus a completed journal session.
- R3: When that range contains no task artifacts, allow planning recovery only
  when it contains exactly one newly completed, index-matched journal session
  and no paths outside its journal/index pair.
- R4: Resolve every work commit referenced by the new session to one unique
  full commit ID. Each must be an ancestor of or equal to the captured base,
  must have exactly one parent, and must be bounded by the validator's existing
  finding/path limits.
- R5: Revalidate each referenced commit's parent-to-commit delta. Every changed
  path must be a regular active-task artifact under
  `.trellis/tasks/<MM-DD-name>`;
  archives, workspace files, code, specs, configuration, deletion, rename,
  copy, merge commits, or unsupported Git records fail closed.
- R6: Aggregate the referenced task directories into result evidence and apply
  the existing planning lifecycle and baseline-state rules. At least one
  qualifying task change must be proven. Recovery must not retroactively apply
  current publication-quality content checks to planning artifacts that were
  already published before the captured base; normal task-plus-journal bundles
  retain the full metadata, topology, context, PRD, and whitespace validation.
- R7: Emit stable, bounded diagnostics for unknown, non-ancestor, non-linear,
  duplicate, path-scope, lifecycle, and no-task recovery failures without
  printing absolute repository paths.
- R8: A valid recovery remains `mode: planning` and reports a machine-visible
  journal-only subtype while retaining the established schema version and
  `planning_bundle_valid` success code for downstream compatibility.
- R9: Update the canonical template first, synchronize the root mirror, update
  the `sd-finish-work` contract and code specs, and add focused positive and
  negative regression coverage. Do not modify upstream Trellis.
- R10: Do not amend, reset, replace, or push preserved journal commit `686f484`
  during implementation. Validate it through an isolated exact-head fixture or
  checkout using the corrected helper.

## Acceptance Criteria

- [ ] The preserved `9c9b8c3..686f484` range passes planning final-bundle with
      `planning_bundle_valid`, evidence identifying journal-only recovery, and
      the task directories recovered from `d97244e` and `9c9b8c3`.
- [ ] Existing task-plus-journal planning and archive-plus-journal completion
      fixtures remain unchanged and passing.
- [ ] Journal-only recovery rejects a referenced code/spec/config/workspace
      commit, merge commit, deletion or rename, unknown or non-ancestor commit,
      duplicate resolved commit, invalid planning lifecycle, multiple new
      sessions, and a session whose commits prove no task change.
- [ ] Already-published planning content debt does not block journal-only
      recovery, while the normal planning final-bundle continues to apply the
      complete task-artifact quality contract.
- [ ] Human and JSON diagnostics stay bounded and repository-relative, and the
      CLI exposes no new public mode.
- [ ] Template/root parity, focused bookkeeping and SD lifecycle tests, generic
      review preflight, and `make check` pass.

## Out of Scope

- Retrofitting arbitrary code-bearing or documentation-only history into
  planning finalization.
- Rewriting or force-pushing already-published history.
- Changing review, CI, merge, housekeeping, or upstream Trellis authority.
- Completing the broader planning-only PR finalization parent task.
