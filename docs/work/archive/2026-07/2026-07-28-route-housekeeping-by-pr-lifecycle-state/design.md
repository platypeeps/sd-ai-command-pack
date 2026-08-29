# Housekeeping PR-lifecycle routing design

## Boundary

Add one dispatcher inside the canonical housekeeping implementation. It owns
the transition from branch identity to exactly one lifecycle path; it does not
create a new public command or a second merge authority.

## State flow

1. Resolve the starting feature branch and bounded GitHub PR identity.
2. Classify the PR state as `OPEN`, `MERGED`, `CLOSED`, or indeterminate.
3. Route once:
   - `OPEN`: evaluate exact-head eligibility; if eligible, merge; reread PR
     identity; then attempt exact-head cleanup.
   - `MERGED`: bypass eligibility and attempt exact-head cleanup using the
     already-resolved identity.
   - `CLOSED`: stop with `pull_request_not_merged`.
   - indeterminate: stop with one identity/state anomaly.
4. Compose the result from the applicable evidence only.
5. Run delegated final status and report clean only if all required actions and
   the final status are clean.

## Evidence contract

The resolved PR identity must provide the PR number, URL, head branch, exact
head OID, base branch, lifecycle state, and merged evidence when applicable.
Do not select a PR solely by branch name after cleanup has begun. After this
invocation merges an open PR, reread provider state before any deletion so the
cleanup proof is bound to the merge that actually occurred.

For cleanup-only runs, `eligibility` is JSON `null`, not an empty or fabricated
eligibility receipt. Existing open-PR eligibility output remains unchanged.
Any schema-version decision must be reconciled with
`07-28-decide-housekeeping-result-schema-compatibility`.

## Failure behavior

- Provider errors, malformed JSON, multiple plausible PRs, head mismatch, or
  missing merge evidence stop before deletion.
- `CLOSED` never falls through to `OPEN` or `MERGED` behavior.
- A failure in the open-PR eligibility path preserves its existing reason
  codes and cannot be overwritten by cleanup output.
- An inapplicable eligibility gate cannot create a cleanup-only anomaly.

## Compatibility and rollout

Templates are authoritative. Keep the root script and result composer mirrors
byte-identical, update public schema documentation, and add fixtures before a
normal pack release and fleet refresh. The change is rollback-safe because the
existing exact-head merge and cleanup gates remain intact.
