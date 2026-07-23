# Implementation plan: normalize program task topology

## 1. Materialize Integration Ownership

- Create `validate-sd-workflow-program-integration` as a P1 planning child of
  `07-22-streamline-sd-skill-workflows`.
- Populate its PRD with explicit prerequisite task IDs, the 11 integration
  scenarios, shared invariants, and testable closure evidence.
- Add task-local design and implementation plans for the integration gate;
  keep the task in `planning`.

## 2. Normalize Program And Child Ownership

- Update the parent PRD so final integration execution belongs to the new
  child while finding-ledger, coordination, and closure ownership remain on
  the parent.
- Add the integration child to the parent child map and completion criteria.
- Replace generic dependency-wave wording in active child artifacts with
  explicit task IDs or invariant language.

## 3. Retire Redundant Program Files

- Verify every architectural, sequencing, scenario, invariant, validation,
  rollback, and stop-point item has a durable task owner.
- Delete the parent's `design.md`, `implement.md`, empty `implement.jsonl`, and
  empty `check.jsonl`.
- Remove live references to deleted paths and to the parent directly executing
  integration work.

## 4. Validate

- Run `task.py list` and inspect both parent and child metadata.
- Search live files for deleted paths, generic wave labels, and stale
  integration ownership.
- Run the task-context/review preflight against the complete diff.
- Run `make check` and confirm task topology, documentation, generated KB, and
  repository gates remain green.

## Stop Points

- Stop if an item cannot be assigned losslessly to an existing child, the new
  integration child, or the parent closure contract.
- Stop rather than starting any remediation child; this task changes planning
  topology only.
- Stop if the migration would require rewriting historical records or opening
  an upstream Trellis pull request.
