# Recover PR 232 After Main Conflict Implementation Plan

## Execution Order

1. Activate this task, bind it to
   `codex/centralize-pr-eligibility-gates`, validate task topology, and commit
   the recovery planning metadata so the working tree is clean before merge.
2. Fetch `origin/main`, verify its current OID and PR #232's exact remote head,
   and confirm the local branch is synchronized with the PR.
3. Merge current `origin/main` with a normal merge commit. Do not rebase or
   force-push.
4. Resolve source-owned conflicts:
   - combine both backend quality-spec additions;
   - retain upstream malformed-context code/tests;
   - keep the combined pack version at `0.33.0` and both changelog entries;
   - keep upstream Session 199 and append the centralization session as 200.
5. Run `make generate` and `make sync` so installed mirrors, catalogs,
   provenance, and KB state follow canonical sources.
6. Run focused conflict-sensitive tests and inspect journal/index uniqueness,
   manifest version consistency, template parity, and the sole live merge call.
7. Run the canonical no-filter fleet candidate validator to replace stale
   payload evidence, then run `make check`.
8. Commit the merge resolution, push without force, and confirm PR #232
   targets `main`, contains current `origin/main`, and reports the pushed head.
9. Run the deterministic PR gate, disposition boundary/size/multi-task
   advisories, request the configured remote reviewer for the exact head, fix
   and reply to findings, and require green CI plus zero unresolved threads.
10. Run finish-work for this recovery task, push its archive/journal commits,
    wait for exact-head CI, then invoke housekeeping once with that full OID.

## Validation Plan

- Focused tests:
  - `tests/test_review_preflight.py`
  - `tests/test_pr_eligibility.py`
  - `tests/test_housekeeping.py`
  - `tests/test_sdlc_commands.py`
  - generated parity and release-gate tests
- Structural checks:
  - `git merge-base --is-ancestor origin/main HEAD`
  - journal Session 199/200 uniqueness and index total/order
  - `git diff --check`
  - template/root byte parity and one live `gh pr merge` owner
- Broad gates:
  - `make generate`
  - `make sync`
  - canonical all-consumer candidate validation
  - `make check`
  - PR CI, configured remote review, delayed GraphQL thread poll

## Documentation And Spec Updates

Preserve and combine the two existing backend quality contracts. No new product
documentation is required beyond accurate release history and this recovery
task's lifecycle evidence.

## Review Notes

- The release-number conflict is resolved semantically, not by choosing one
  side wholesale: `0.33.0` includes the already-merged `0.32.2` fix.
- The journal conflict is append-only history, not ordinary text: upstream 199
  stays and the unmerged branch entry becomes 200.
- Multiple Trellis task directories in the PR are directly caused by recovery
  and must be explicitly dispositioned before remote review.

## Rollback Points

- Before the merge commit is published: abort and restore the clean pre-merge
  feature head if any resolution is uncertain.
- After publication: correct forward with normal commits and re-enter review;
  never force-push the shared PR branch.

## Follow-Ups

Unified router-issued exact-head review-receipt consumption remains owned by
`07-22-integrate-routed-review-backends` and is not expanded here.
