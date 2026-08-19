# Retire the audit-path campaign branches left in five consumers

## Goal

Delete the merged `chore/fix-install-audit-path-citation` branch, local and
remote, in each of the five consumer repositories the 2026-08-19 fleet audit
path campaign touched.

## Background

That campaign corrected the install-audit path recorded in consumer task and
journal records. Six pull requests landed on 2026-08-19 -- one in this pack and
one in each of loadsmith, hoa-manager, rwbp-coordinator, rwbp-website, and
mezmo_benchmark. The pack's own branch was retired by its housekeeping run. The
five consumer branches were not, because each of those checkouts is parked on
an unrelated branch owned by another process, and the campaign's own safety
rule forbids touching a checkout in that state.

Three of the five merged as squashes, so the branch tip is not an ancestor of
the default branch and `git branch -d` will refuse it. Content preservation was
verified at the time through the GitHub contents API on each default branch;
that evidence is what justifies deleting a branch whose commits do not appear
in `main`.

## Requirements

- Delete the local and remote `chore/fix-install-audit-path-citation` branch in
  each of the five consumers, after proving per repository that its pull
  request is `MERGED` and that the branch's content reached the default branch.
- Enumerate the consumers from `docs/fleet/consumers.json` rather than from the
  list above, which is a snapshot.
- Skip and report any checkout that is dirty, missing, or held by another
  worktree. Never stash, reset, clean, or force anything in a consumer.
- Squash-merged branches need the content proof before deletion, not an
  ancestry check, and the proof must be recorded per repository.

## Acceptance criteria

- [ ] `git branch --list chore/fix-install-audit-path-citation` and
      `git ls-remote --heads origin chore/fix-install-audit-path-citation`
      return nothing in every enumerated consumer, or the checkout is reported
      as skipped with its exact reason.
- [ ] Every deletion cites its pull request number, merged state, and the
      content evidence that justified it.
- [ ] No consumer checkout changed branch, gained a stash, or lost uncommitted
      work.

## Out of scope

- Any other stale branch in those repositories. This task retires one named
  branch from one campaign.
- Re-verifying the audit-path corrections themselves; that was done and
  archived under `08-19-fleet-audit-path-in-consumer-records`.
