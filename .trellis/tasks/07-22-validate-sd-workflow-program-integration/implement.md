# Implementation plan: validate SD workflow program integration

## 1. Verify Prerequisites

- Resolve every command-pack dependency task and the external router v1 task.
- Record terminal status, PR/commit/version identity, and any parent-approved
  disposition; stop on missing or ambiguous evidence.
- Select one exact integrated head and compatible router contract for the
  complete matrix.

## 2. Build The Evidence Matrix

- Create the task-local F01-F17 and S01-S11 evidence record under `research/`.
- Link each finding and scenario to its owning task, focused fixture, expected
  result, and final observation.
- Add only integration fixtures or evidence plumbing owned by this task; route
  production defects back to their implementation owner.

## 3. Execute Lifecycle Scenarios

- Run the exact-head, routing/provider, trust, structured-interaction, review
  pagination, dependency, fleet, audit, drift, and write-boundary scenarios.
- Exercise generated adapters and an installed payload where source-only tests
  cannot prove the contract.
- Preserve distinct unavailable/failure results and disclose paid or networked
  provider use.

## 4. Run Aggregate Validation

- Run focused integration tests and the affected child regression suites.
- Run `make sync`, `make check`, install `--check --json`, and applicable fleet
  candidate validation on the same recorded head.
- Scan live catalogs, specs, docs, manifests, adapters, and receipts for retired
  surfaces outside explicit history/migration fixtures.

## 5. Hand Off Program Closure

- Finalize the evidence record with pass, accepted disposition, or blocker for
  every prerequisite and matrix row.
- Add a concise closure summary to the parent task with exact evidence and
  final pack/router identities.
- Archive this task only after the parent can evaluate closure without any
  retired program-level plan file.

## Stop Points

- Stop when a prerequisite is incomplete, incompatible, or ambiguous.
- Stop and route a production defect to its owning child rather than expanding
  this task's implementation scope.
- Stop before any paid/networked provider call without the command's documented
  authorization and disclosure boundary.
- Stop before an upstream Trellis PR unless the user separately approves that
  specific PR.
