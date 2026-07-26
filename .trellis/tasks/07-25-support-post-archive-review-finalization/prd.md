# Support post-archive review finalization

## Goal

Allow reviewed pull requests with post-archive remediation commits to produce truthful exact-head finish-work evidence and merge through housekeeping without duplicate journals, false task mutations, or caller attestations.

## Confirmed Evidence

- PR #253 completed normal task bookkeeping before remote review: work commit
  `dcddf77`, archive commit `409539e`, and journal commit `f35c66d` recorded
  session 230.
- Review then produced four code-bearing remediation commits through exact head
  `336f19ac873704394a7ec53e2880c6c033f93daf`; the task remained archived and
  no active task existed.
- `sd-review-pr` correctly reran exact-head checks and remote review, but its
  mandatory finish-work handoff had no active task to archive and could not
  produce a new valid completion or planning bundle without duplicating the
  completed session.
- Canonical housekeeping returned schema-version-1 `blocked` with
  `finish_work_missing`, refreshed the KB and refs, skipped merge, and left the
  branch untouched. CI, merge state, and review threads were otherwise clean.
- The journal-only planning recovery cannot safely cover this case: its
  referenced commits must be task-only planning changes, while post-archive
  review remediation legitimately changes code, tests, specs, and generated
  payload evidence.

## Boundaries

- Parent: `07-24-support-planning-only-pr-finalization`.
- Keep `sd-housekeeping` as the sole merge mutation owner and retain its
  exact-head, clean-tree, CI, merge-state, and unresolved-thread gates.
- Keep the public finalization modes `completion` and `planning`; do not add a
  user-selected review-remediation mode or another merge command.
- Do not weaken journal-only planning recovery to accept code-bearing commits.
- Do not mutate an archived task, rewrite a completed journal session, create a
  duplicate session solely to move the finish-work head, or accept a bare
  caller assertion.
- Implement entirely in `sd-ai-command-pack`; upstream Trellis changes or pull
  requests require separate explicit approval.
- Keep `templates/**` authoritative and synchronize installed mirrors.

## Requirements

- R1: Recognize a post-archive review successor only when a canonical prior
  completion bundle is an ancestor of the exact current PR head and can be
  independently revalidated from bounded Git and Trellis evidence.
- R2: Return normal `mode: completion` with a machine-readable internal subtype
  such as `completionSubtype: post-archive-review-successor`; callers and users
  never choose the subtype.
- R3: Bind the typed receipt to repository and branch identity, the original
  completion base and bookkeeping head, archived task directories, completed
  journal session, ordered successor commits, and the exact final head.
- R4: Require a linear, bounded successor range. Reject any successor change to
  `.trellis/tasks/**`, `.trellis/workspace/**`, finalization runtime evidence,
  or another bookkeeping surface. Code, tests, specs, and generated payload
  changes may remain in the successor range because final-head review and CI
  gates validate them separately.
- R5: Use one bounded historical recovery: identify the nearest adjacent
  canonical archive and journal completion tail, re-run the existing completion
  validator over its original range, and fail closed on missing, rewritten,
  nonlinear, or oversized history. Do not add durable repository receipt state.
- R6: `sd-finish-work` must emit or reuse the exact-head typed receipt without
  archiving, recording another journal session, staging, committing, pushing,
  or changing a task/session pointer. Repeated runs at the same head are
  idempotent.
- R7: `sd-review-pr` must treat the valid successor receipt as completed
  finish-work ownership. It must not relaunch journal recording after clean
  remote review merely because review remediation followed the original
  archive.
- R8: Eligibility and housekeeping must independently verify the receipt and
  current Git/GitHub head. Replace the bare `--finish-work-head` trust decision
  as the parent finalization contract migrates; do not introduce another
  head-only fallback.
- R9: A stale receipt, changed bookkeeping, missing objects, unrelated prior
  completion, invalid nearest candidate tail, head mismatch, merge commit,
  dirty tree, or absent proof must return stable blocked/indeterminate reason
  codes and must never reach merge mutation.
- R10: Avoid a bookkeeping-only successor commit after review convergence so
  this lifecycle does not trigger a redundant full CI and remote-review cycle.
- R11: Preserve normal completion, planning-only, and journal-only recovery
  behavior unchanged, including their existing failure boundaries.
- R12: Report the subtype and recovery source in typed finish-work,
  eligibility, housekeeping, and status evidence without exposing absolute
  paths or unbounded commit data.

## Acceptance Criteria

- [ ] A hermetic PR #253-shaped fixture (work, archive, journal, then multiple
  code/test/spec review fixes) produces a valid exact-head `completion`
  successor receipt with no filesystem or Git mutation.
- [ ] The original archive and journal range is revalidated with the canonical
  completion validator and the successor range is independently proven linear,
  bounded, and free of bookkeeping changes.
- [ ] Repeating finish-work at the same final head reuses the receipt and
  creates no task, journal, commit, push, CI run, or remote-review request.
- [ ] Housekeeping accepts the verified receipt only at the matching clean PR
  head and remains the sole operation capable of merging and deleting the
  proven source branch.
- [ ] Missing or invalid prior completion, altered task/workspace files, stale
  or forged receipts, rewritten ancestry, merges, and head mismatches all block
  with stable typed diagnostics.
- [ ] Existing completion, planning, journal-only recovery, eligibility,
  housekeeping, and status fixtures remain green without compatibility aliases
  or a third public finalization mode.
- [ ] Template/root mirrors are byte-identical; focused tests, `sd-check`,
  `make check`, and fleet candidate validation pass.
