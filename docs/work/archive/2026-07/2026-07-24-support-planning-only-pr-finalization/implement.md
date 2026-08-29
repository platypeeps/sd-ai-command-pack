# Implementation plan: planning-only PR finalization

## 1. Reconcile dependencies and lock fixtures

- Land or explicitly reconcile
  `07-24-validate-finish-work-bookkeeping-before-push` and
  `07-24-reread-pr-head-at-eligibility-completion` before editing their shared
  validator/eligibility boundaries.
- Capture completion, planning-only, ambiguous, malformed, interrupted, stale,
  and already-merged fixtures. Include a bounded PR #244 fixture with multiple
  task additions/parent edits and a preserved current planning task.
- Lock the typed finalization schema and stable reason codes before wiring
  orchestration.

## 2. Implement deterministic finalization evaluation

- Add the canonical template helper and root mirror with strict JSON input and
  typed JSON/human output.
- Reuse the shared bookkeeping validator for task, topology, journal,
  placeholder, and whitespace rules.
- Add exact base/head ancestry, path, tree-mode, lifecycle-transition, active-
  task, repository, and PR identity proof.
- Default uncertainty to blocked or indeterminate; never infer planning mode
  from a path prefix or caller-supplied label alone.

## 3. Integrate SD finish-work

- Update template-first skill/runtime behavior to select completion or planning
  from the evaluator result.
- Keep existing pre-archive/archive behavior for completion.
- For planning, record one journal entry with the canonical recorder and
  preserve task metadata plus the active session pointer.
- Validate the full local bundle, emit the typed receipt, and permit at most one
  final successor push.

## 4. Integrate eligibility, housekeeping, and status

- Replace bare finish-work-head input with independently verified typed
  finalization evidence across eligibility and housekeeping.
- Preserve all current exact-head, check, review-thread, merge-state, and
  mutation-boundary rechecks.
- Report finalization mode and treat the preserved planning task as expected
  post-cleanup state.
- Remove every retired option, field, parser, environment reader, help string,
  fixture branch, and compatibility path after caller migration.

## 5. Validate the lifecycle

- Run focused finalization, recorder, eligibility, housekeeping, status,
  shipping, generated-parity, and command-surface tests.
- Prove retry behavior creates no duplicate journal, archive, receipt, push, or
  merge and that every invalid mode/identity case fails before mutation.
- Run `make sync`, `make check`, install `--check --json`, and the applicable
  fleet candidate validation.
- Release/install the implementation and dogfood PR #244 or a freshly based
  equivalent planning-only PR; record its exact receipt, CI/review identities,
  merge result, preserved task state, and final branch cleanup. Do not rewrite
  PR #244 history without separate user authorization.

## Stop And Rollback Points

- Stop before mutation when planning classification, task ownership, base/head
  identity, or dependency state is ambiguous.
- Stop before push when final-bundle validation or receipt generation fails;
  preserve local commits for bounded recovery.
- Stop before merge on any stale head, red/missing check, unresolved thread,
  non-clean merge state, or final-head mismatch.
- Revert/reinstall the release rather than restoring the retired attestation or
  bypassing housekeeping.
