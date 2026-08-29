---
title: Retire the audit-path campaign branches left in five consumers
status: done
created: 2026-08-19
---
# Retire the audit-path campaign branches left in five consumers

## Status update — 2026-08-20 (already done; closing)

The work this task describes is complete, and was complete before the task was
picked up. Re-measured 2026-08-20 against live state rather than against the
snapshot below.

- **Local branches: gone.** `git branch --list chore/fix-install-audit-path-citation`
  returns empty in all five consumer checkouts.
- **Remote branches: gone.** `git ls-remote --heads origin <branch>` returns
  empty in all five. The snapshot further down, which reports live remotes in
  rwbp-coordinator, loadsmith, and rwbp-website, describes a condition that no
  longer exists.
- **No unlanded work.** All five PRs are MERGED (#247, #241, #274, #254, #515,
  merged 2026-08-19T22:03Z). Three heads compare as `diverged` against main --
  a squash-merge artifact, not divergent content. Every touched file was
  SHA-compared at head against main through the GitHub contents API and is
  identical: `.trellis/tasks/archive/2026-08/08-19-sd-ai-command-pack-0-71-33/prd.md`
  and `.trellis/workspace/sdelmas/journal-3.md`.
- **The stated blocker is stale.** This PRD claims each checkout is parked on an
  unrelated branch owned by another process. All five are on `main` and clean.

### What the acceptance criteria could not see

The criteria in this document **already pass** — and would have passed at
authoring time — because both commands they name are blind to the only residue
that actually remains: five stale remote-tracking refs
(`refs/remotes/origin/chore/fix-install-audit-path-citation`), left because no
checkout has fetched since the remotes were deleted. `git branch --list` and
`git ls-remote --heads origin` cannot observe a remote-tracking ref, so a
criteria set built from them reports success over a dirty cache.

Clearing them is `git fetch --prune` in each checkout — a local cache drop, not
a branch deletion, destroying nothing. Left undone deliberately: it is routine
housekeeping that the next fleet fetch performs as a side effect, and it is not
worth a campaign of its own.

Lesson for future cleanup tasks: an acceptance criterion that enumerates from
the same view the cleanup operates on cannot detect residue outside that view.
Prefer `git for-each-ref` over `git branch --list` when the question is "is
every trace of this branch gone."

Remaining: nothing actionable. Archived 2026-08-20.

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

Measured 2026-08-19 from the five checkouts, read-only:

| Consumer | Local branch | Remote branch |
| --- | --- | --- |
| rwbp-coordinator | present (`170d9ad`) | present |
| loadsmith | present (`88a8d41`) | present |
| hoa-manager | present (`a4ca49a`) | already deleted |
| rwbp-website | present (`d39d640`) | present |
| mezmo_benchmark | present (`9b36a53`) | already deleted |

So the remote half is already done in two of the five; the work is five local
deletions and three remote ones.

Several of these pull requests were squash-merged, so a branch tip is not
necessarily an ancestor of the default branch and `git branch -d` will refuse
it. Do not take containment from a local `origin/main`: no checkout was fetched
during this survey, so every local remote-tracking ref there is of unknown
freshness, and a local ancestry check on all five currently reports
`NOT-ancestor` for exactly that reason. Establish containment per repository
from GitHub at execution time. Content preservation was verified during the
campaign through the GitHub contents API on each default branch; that evidence
is what justifies deleting a branch whose commits do not appear in `main` as
commits.

## Requirements

- Delete the local `chore/fix-install-audit-path-citation` branch in each of the
  five consumers, and the remote one wherever it still exists, after proving per
  repository that its pull request is `MERGED` and that the branch's content
  reached the default branch. Re-measure presence rather than trusting the table
  above; a remote branch may be retired between filing and execution.
- Enumerate the consumers from `docs/fleet/consumers.json` rather than from the
  list above, which is a snapshot.
- Skip and report any checkout that is dirty, missing, or held by another
  worktree. Never stash, reset, clean, or force anything in a consumer.
- Squash-merged branches need the content proof before deletion, not an
  ancestry check, and the proof must be recorded per repository. A local
  ancestry check against an unfetched `origin/main` proves nothing either way.

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
