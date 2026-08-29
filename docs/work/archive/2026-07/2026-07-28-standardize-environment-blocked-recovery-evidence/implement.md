# Environment-blocked recovery evidence implementation plan

## Contract first

1. Inventory the recorder, finish-work, housekeeping, work-loop, KB, and
   toolchain result schemas, error composers, exit codes, and platform skill
   consumers.
2. Reconcile ownership with the tasks listed in `prd.md`; do not duplicate
   their underlying fixes.
3. Select the shared schema location, versioning behavior, bounded enums,
   diagnostic limits, and legacy-consumer behavior.
4. Add reusable composers and validators in each implementation language that
   needs them. Do not add stderr heuristics or shell-string recovery actions.

## Incremental integration

5. Integrate one boundary at a time in this order: toolchain cache,
   user-local work-loop state, recorder/finish-work Git metadata, housekeeping
   Git and KB operations, then managed payload writes.
6. For each integration, capture the last verified checkpoint and mutation
   state directly from control flow and prove retry idempotency before marking
   it retryable.
7. Update canonical shared skills to present the fragment consistently and
   request only the narrow retry authority; keep platform adapters thin.
8. Update public docs, generated surfaces, manifests, and root mirrors through
   normal synchronization.
9. Add the cross-command retry cases to the workflow-program integration
   matrix and plan the normal release/fleet refresh.

## Validation

- Add focused cases to `tests/test_record_session.py`,
  `tests/test_housekeeping.py`, `tests/test_housekeeping_result.py`,
  `tests/test_work_loop.py`, `tests/test_update_spec_kb.py`, and
  `tests/test_toolchain_preflight.py` as applicable.
- Add shared schema tests for enums, version handling, size bounds, redaction,
  malformed input, unknown fields, and recovery-action argv safety.
- Prove retries do not duplicate a journal entry, commit, archive, merge,
  deletion, checkpoint, or cleanup action.
- Prove blocked paths cannot reach destructive or authority-expanding actions.
- Run focused suites after each integration, then `make sync`, install audit,
  generated parity, and `make check`.
- Validate the task artifacts before `task.py start` and do not start until the
  user reviews this plan.

## Risk and checkpoints

- Highest risk: a broad classifier could mislabel a repository defect as a
  permission issue. Only explicit owner-side construction is allowed.
- Schema risk: multiple result formats may not share one envelope. Resolve
  compatibility before integration rather than forcing uniform transport.
- Scope risk: this task touches several commands. Land integrations in bounded
  commits with focused tests so any one boundary can be reverted independently.
- Stop if an integration requires changing the underlying domain task; record
  the dependency and resume after that owner lands.
