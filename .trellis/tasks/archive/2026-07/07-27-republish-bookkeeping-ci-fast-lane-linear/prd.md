# Republish bookkeeping CI fast lane on linear history

## Goal

Publish the already validated bookkeeping-only CI fast lane from current
`main` on a linear replacement branch so the repository's canonical
finish-work receipt is valid. Preserve PR #270 until the replacement is
independently green and review-clean, then close the superseded PR without
force-pushing or rewriting its history.

## Background

- PR #270 is mergeable and all exact-head GitHub checks pass at
  `3d1a82779e8d4fefe4329e5f4d6b9327388b28b4`.
- Copilot reviewed that head with no new comments, and both earlier review
  threads are resolved.
- `sd-finish-work` rejects the exact-head completion receipt because merge
  commit `42d82cf86d648738a3212806f452b60ab495895b` is non-linear and brings
  upstream `.trellis/tasks/` and `.trellis/workspace/` changes into the
  post-archive successor range.
- Current `main` contains the original fast-lane task in `planning` state and
  Session 246 from the intervening Gemini settings work. The replacement must
  preserve both and add new completion bookkeeping without changing history.

## Requirements

- R1: Create a new branch from the current `origin/main`; do not force-push,
  rebase, reset, amend, or otherwise rewrite PR #270.
- R2: Replay the final functional, test, documentation, and specification
  content from PR #270 without replaying its merge commit, obsolete archive
  commits, or obsolete Session 246 journal entry.
- R3: Preserve all accepted review and CI fixes, including `checks: read`, the
  aggregate-job exact-head checkout, pinned actions, strict result-matrix
  handling, and their regression tests.
- R4: Keep both the original fast-lane task and this recovery task traceable.
  Activate both before the work commit, then archive both in the same
  completion bundle and record one new journal session.
- R5: Keep the replacement history first-parent linear from current `main`.
  After task archival and journal creation, allow only linear code/test/spec
  review-successor commits permitted by the canonical validator.
- R6: Validate content equivalence for the functional file set against PR
  #270's final reviewed head, while allowing only the deliberately regenerated
  Trellis task and workspace artifacts to differ.
- R7: Require focused tests, actionlint, `make check`, exact-head `sd-check`,
  remote review convergence, all required GitHub checks, zero unresolved
  GraphQL review threads, and a valid exact-head completion receipt.
- R8: Keep PR #270 open until the replacement PR satisfies R7. Then close
  PR #270 with a link to its replacement; do not merge either PR as part of
  this recovery task.

## Acceptance Criteria

- [ ] A new `codex/` branch is based directly on the current `origin/main` and
  contains no merge commit in its task-to-head first-parent history.
- [ ] The functional files match the reviewed PR #270 head, excluding only
  intentional Trellis lifecycle regeneration.
- [ ] The original fast-lane task and the recovery task are both archived with
  preserved task identity, and one non-conflicting journal session is added.
- [ ] Focused workflow tests, actionlint, and `make check` pass locally.
- [ ] `sd-check` passes on the exact pushed replacement head with an unchanged
  state guard.
- [ ] The replacement PR is mergeable, required CI is green, the configured
  remote review is clean, and GraphQL reports no unresolved review threads.
- [ ] `final-bundle --mode completion` returns schema version 1, `status:
  valid`, `completion_bundle_valid`, and the replacement's exact head OID.
- [ ] PR #270 remains unchanged until all preceding criteria pass, then is
  closed as superseded with the replacement PR linked.

## Out of Scope

- Changing the completion-successor validator's merge-commit policy.
- Force-updating, deleting, or otherwise rewriting PR #270 or its branch.
- Releasing or rolling out a new command-pack version.
- Merging the replacement PR.
