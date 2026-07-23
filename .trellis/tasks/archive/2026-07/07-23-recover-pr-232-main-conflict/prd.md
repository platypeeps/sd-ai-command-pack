# Recover PR 232 after main conflict

## Goal

Restore PR #232 to a clean, exact-head-reviewed, mergeable state after PR #231
advanced `origin/main`, without losing either release's behavior or weakening
the command pack's review, lifecycle, or housekeeping gates.

## Background

- PR #232 is open from `codex/centralize-pr-eligibility-gates` at finish-work
  head `1c80d92a26609770379d4fe29091bd2713a2b0f0`.
- All checks on that head passed, but housekeeping refused to merge because
  GitHub first reported `UNKNOWN` and then `DIRTY` merge state.
- Current `origin/main` is `8293d0eaade12f1899ae07ff47da9dff655c573a`,
  which merged PR #231 and pack `0.32.2` after PR #232 branched from `0.32.1`.
- A read-only `git merge-tree` preview identifies overlapping release metadata,
  backend quality-spec additions, and two independently-created Session 199
  journal entries. The upstream malformed-context implementation and tests
  otherwise merge cleanly with PR #232's eligibility evaluator.

## Requirements

- R1: Integrate current `origin/main` with a normal merge commit. Do not rebase,
  force-push, squash away reviewed history, or bypass branch protection.
- R2: Preserve PR #231's fail-closed malformed task-context JSONL behavior,
  tests, task archive, specification additions, and release history.
- R3: Preserve PR #232's shared exact-head eligibility evaluator,
  housekeeping-only merge ownership, dependency-PR delegation, tests, task
  archive, and review fix.
- R4: Keep pack `0.33.0` as the combined candidate version while retaining the
  `0.32.2` changelog entry immediately below it. Regenerate command catalogs,
  installed manifests, provenance, and all other derived surfaces from their
  canonical sources.
- R5: Preserve journal history append-only. Keep upstream Session 199 unchanged,
  renumber PR #232's not-yet-merged centralization session to Session 200, and
  rebuild the journal index totals/order without overwriting either entry.
- R6: Regenerate the canonical all-consumer candidate ledger for the combined
  `0.33.0` payload; stale pre-merge payload digests are not acceptable.
- R7: Run focused conflict-sensitive tests, `make sync`, canonical fleet
  candidate validation, and `make check` before publication.
- R8: Push the merge resolution without force, request a fresh configured
  remote review for the new exact head, address all findings, and require green
  CI plus zero unresolved review threads.
- R9: Finish this recovery task through the standard lifecycle. Any additional
  archive/journal head must pass its own CI before one fresh housekeeping
  invocation decides merge eligibility.
- R10: Treat the recovery task and its parent-link metadata as required PR #232
  bookkeeping, and explicitly disposition the resulting multi-task-scope
  advisory during review.

## Acceptance Criteria

- [ ] PR #232 contains current `origin/main` as an ancestor and reports a clean
  merge state before housekeeping runs.
- [ ] Both malformed-context validation and PR eligibility behavior remain in
  canonical templates and installed mirrors with focused tests passing.
- [ ] `manifest.json` and installed metadata report `0.33.0`; the changelog
  retains both `0.33.0` and `0.32.2` in descending order.
- [ ] Journal/index history contains upstream Session 199 and centralization
  Session 200 exactly once each, with no historical session removed.
- [ ] The combined `0.33.0` fleet candidate ledger passes all configured
  consumers and matches the current payload digest.
- [ ] `make check`, PR CI, fresh-head remote review, and direct review-thread
  polling all pass.
- [ ] The recovery task is archived, its session is recorded, and housekeeping
  either merges PR #232 cleanly or stops with a new evidence-backed blocker.

## Out Of Scope

- New eligibility-evaluator features or router-receipt integration.
- Reworking PR #231's malformed-context implementation.
- Bypassing or weakening exact-head, CI, review-thread, finish-work, or
  housekeeping requirements to avoid the conflict-resolution cycle.
