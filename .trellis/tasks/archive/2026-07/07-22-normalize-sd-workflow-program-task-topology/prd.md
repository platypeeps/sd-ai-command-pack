# Normalize SD workflow program task topology

## Goal

Replace the umbrella program's standalone design and implementation-plan files
with an explicit Trellis task topology. Preserve every independently verifiable
deliverable, dependency, invariant, integration scenario, stop point, and
closure condition while removing planning files and references that become
redundant once those responsibilities have task owners.

## Confirmed Facts

- `07-22-streamline-sd-skill-workflows` is the P1 parent for the F01-F17
  remediation program and intentionally has no direct implementation scope.
- Existing children already own every foundation and workflow-specific
  deliverable described by the program.
- The 11 cross-child integration scenarios currently exist only in the parent
  `design.md`; no child owns the final end-to-end validation gate.
- The user approved one integration child with the 11 scenarios as acceptance
  criteria rather than 11 separate lifecycle records.
- Program coordination and final closure remain responsibilities of the parent
  task. They do not need another self-referential closeout child.
- The parent `implement.jsonl` and `check.jsonl` are empty, and the parent must
  never be started for implementation work.

## Requirements

- R1: Create one P1 child task named
  `validate-sd-workflow-program-integration` under
  `07-22-streamline-sd-skill-workflows`.
- R2: Give the integration child explicit dependencies on every implementation
  child and on the external routed-review v1 contract. Parent/child placement
  must not be treated as dependency ordering.
- R3: Move all 11 integration-matrix scenarios, shared program invariants,
  final validation commands, version-based rollback, and applicable stop
  points into the integration child's planning artifacts without weakening or
  merging distinct outcomes.
- R4: Keep the parent PRD as the authoritative F01-F17 ledger, child map,
  cross-child acceptance contract, and closure owner. Transfer final
  integration execution and evidence ownership to the new child.
- R5: Preserve the existing foundation and workflow child tasks. Replace
  generic wave references with explicit task dependencies where needed; do not
  duplicate tasks that already own a deliverable.
- R6: Delete the parent `design.md`, `implement.md`, empty `implement.jsonl`,
  and empty `check.jsonl` after their content is represented by task metadata
  and planning artifacts.
- R7: Remove or rewrite every live reference that relies on the deleted files,
  generic dependency-wave names, or the parent executing the integration
  matrix directly. Historical journal/archive prose is not rewritten.
- R8: Keep all created tasks in `planning`; this migration must not start an
  implementation child or imply approval to implement the remediation program.

## Acceptance Criteria

- [x] `task.py list` shows the new integration task beneath the program parent
  and preserves every existing child relationship.
- [x] The integration task has testable acceptance criteria for all 11 former
  matrix scenarios and explicit dependencies for every prerequisite child.
- [x] The parent PRD maps F01-F17 and final integration ownership entirely to
  Trellis tasks, with coordination and closure retained by the parent.
- [x] No actionable foundation, workflow, integration, or closure deliverable
  remains only in the deleted program-level files.
- [x] The parent `design.md`, `implement.md`, `implement.jsonl`, and
  `check.jsonl` are absent.
- [x] Repository search finds no live reference to those deleted parent files,
  no generic numbered-wave dependency label, and no statement that the parent
  executes the integration matrix.
- [x] All affected task metadata and planning artifacts pass the repository's
  Trellis task-context validation.
- [x] `make check` passes with no generated or task-topology drift.

## Out Of Scope

- Implementing any F01-F17 remediation child.
- Starting the new integration child or the program parent.
- Changing the already-approved separate-repository boundary with
  `platypeeps/sd-github-review`.
- Rewriting historical journals, archived tasks, or merged PR records.
- Opening an upstream Trellis pull request.
