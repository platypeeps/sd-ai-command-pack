# Implementation Plan: Reconcile main and recover PR 255

## 1. Establish and preserve identities

- [ ] Reread local/remote main, PR #255 head/base/state, and the old-base pivot.
- [ ] Verify the working tree is clean except for this task's planning files.
- [ ] Set this task's base branch to `main` and retain the expected remote-head
  lease `a35735be5f1887fc313646b49f1cadb97de97d6e`.
- [ ] Commit the approved recovery plan before rewriting history.

## 2. Reconcile local main

- [ ] Switch to `main` and rebase it onto `origin/main`.
- [ ] If the local journal commit conflicts or becomes empty, compare the full
  Session 230 content before omitting the redundant replay.
- [ ] Verify `main...origin/main` is `0 0`, the tree is clean, and Sessions
  229-231 remain present.

## 3. Rebase and reconcile PR #255

- [ ] Switch back to `codex/support-post-archive-review-finalization`.
- [ ] Rebase with `git rebase --onto origin/main 336f19a`.
- [ ] Resolve code, task, journal, version, and candidate-ledger conflicts under
  the design rules; run synchronization after template-side resolutions.
- [ ] Inspect the rewritten commit range and diff for duplicated old-base work.

## 4. Validate and publish

- [ ] Run focused bookkeeping, eligibility, housekeeping, and SDLC contract
  tests.
- [ ] Run template parity/synchronization checks, `make check`, and the full
  configured fleet candidate validation.
- [ ] Force-push only with the recorded exact lease.
- [ ] Retarget PR #255 to `main`, reopen it, and update stale PR metadata.

## 5. Review and finish

- [ ] Run `sd-review-pr` on the exact rewritten head, including the local gate
  and fresh remote review rounds required by policy.
- [ ] Address or rebut findings with evidence, reply to and resolve handled
  threads, and rerun exact-head validation after every push.
- [ ] Run review-learnings dry-run once for the converged review cycle.
- [ ] Produce and retain a valid exact-head finish-work receipt.
- [ ] Run guarded housekeeping, merge if eligible under the user's existing
  lifecycle authorization, archive this recovery task, and verify final clean
  local/remote state.

## Rollback Points

- Abort before publication if rebase conflicts cannot be resolved without
  expanding scope.
- Stop on a force-with-lease mismatch; never replace a newly advanced remote.
- Stop on invalid finish-work or eligibility evidence; retain the exact JSON
  finding instead of bypassing the gate.
