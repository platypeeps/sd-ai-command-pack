# Design: Reconcile main and recover PR 255

## Boundaries

Treat local-default-branch normalization and PR-branch recovery as two ordered
history operations. The former removes a redundant local journal replay; the
latter rebases only the six PR #255-owned commits plus this recovery task onto
the authoritative default branch.

No production behavior is redesigned. Conflict resolution may synchronize
the existing 0.54.0 payload with current-main metadata, but must not expand the
feature scope.

## History Contract

1. Record the authoritative OIDs: local main `686f484`, current main
   `cce9cbb`, old PR head `a35735b`, and old-base pivot `336f19a`.
2. Rebase local `main` onto `origin/main`. If replay of `686f484` conflicts or
   becomes empty, verify its substantive Session 230 content is already in the
   target before omitting the redundant replay.
3. Rebase `codex/support-post-archive-review-finalization` with
   `--onto origin/main 336f19a`, so the old recovery series is not replayed.
4. Publish with an exact old-head lease. A lease mismatch is a hard stop and
   requires rereading remote state.

The old remote OID remains recoverable through Git object identity until the
recovery is verified; no broad reset or unguarded force push is used.

## Conflict Resolution

- Journal and workspace index: retain current-main Sessions 229-231 and assign
  the PR #255/recovery lifecycle the next truthful session number when it is
  finalized.
- Tasks: retain merged archive records, keep the active recovery task, and
  preserve parent/child references without duplicates.
- Release surfaces: keep 0.54.0 above the merged 0.53.0 and 0.52.1 history.
- Shipped payloads: edit canonical `templates/**` first and keep root mirrors
  byte-synchronized.
- Code conflicts: preserve both current-main recovery hardening and PR #255's
  successor-receipt behavior unless tests prove one supersedes the other.

## GitHub Lifecycle

After the rewritten branch is published, change PR #255's base to `main` and
reopen it. Reread the head OID, merge state, checks, reviews, and GraphQL review
threads after every remediation push. Prior review results are historical
evidence only; the rewritten exact head receives a fresh review cycle.

## Validation and Rollback

Run focused successor-receipt and housekeeping tests before the full suite,
then template synchronization checks, `make check`, and fleet candidate
validation. Keep finish-work receipts outside the repository.

Before publication, aborting a rebase restores the prior branch. After the
guarded force push, the recorded old OID can seed a recovery branch if needed.
Do not delete that recovery identity until PR and housekeeping verification
are complete.
