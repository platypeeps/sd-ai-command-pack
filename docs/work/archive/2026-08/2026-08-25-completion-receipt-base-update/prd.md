---
title: Let a completion receipt survive the base update the merge gate requires
status: done
created: 2026-08-25
branch: fix/completion-receipt-base-update
---
# Let a completion receipt survive the base update the merge gate requires

## Origin

Found on 2026-08-25 while shipping PR #551 at pack 0.71.52. The PR was green,
comment-clean and `CLEAN`-mergeable, and still could not be merged through
`sd-housekeeping`, because no valid finish-work receipt could be produced for
it by any documented route.

## The deadlock

Four rules that are individually reasonable close a loop:

1. This repository blocks a merge while the PR is `BEHIND` its base. The
   eligibility probe reports `merge_blocked_out_of_date` and the merge is
   skipped.
2. Clearing `BEHIND` means updating the branch onto the moved base. Without a
   force push, that is a merge commit.
3. `sd-finish-work` states the completion-successor rule fails closed on
   exactly that: *"A merge commit anywhere in the range ... still fails closed
   and is not a bug."*
4. `sd-housekeeping` requires the receipt from a feature branch; without one
   it reports `finish_work_missing` and skips the merge.

So: main moves after finish-work, the branch must be updated, the update makes
the receipt unobtainable, and the gate will not merge without it. Nothing in
the loop is reachable by a caller who may not force-push.

## Measured, both documented routes

`--base <head> --head <head>` (the moved-head route sd-ship prescribes):

```
status: invalid
reasonCodes: ['completion_successor_history_non_linear',
              'completion_successor_scope_invalid']
successor commit 3c663bff must have exactly one parent
successor commit 164dfde9 must have exactly one parent
```

It also reports `completion_successor_scope_invalid` for every task path the
merge brought in from the base — other people's archived tasks, which the
branch never touched.

`--base <captured-finalization-base> --head <head>`:

```
status: invalid
reasonCodes: ['bundle_scope_invalid', 'bundle_unsupported_file_mode',
              'completion_source_lifecycle_invalid']
CHANGELOG.md | finalization delta contains a non-bookkeeping path
```

This confirms sd-ship's own warning about the enlarged delta. Both routes are
exhausted.

## How #551 was actually landed

By explicit user approval to lift the no-force-push rule for that one branch:
rebase onto main, fold the archived-PRD evidence correction into the archive
commit, and regenerate the ledger. History became linear, and the same
`--base <head> --head <head>` call then returned
`status: valid, reasonCodes: ['completion_bundle_valid']` unchanged.

That is evidence the rule itself is right — linear history validates — and
that the gap is the absence of any non-force-push path to reach it.

One incidental trap found on the way: the receipt records the branch it was
generated on. Producing it from a temporary rebase branch yields
`finish_work_stale` with `matchesCurrentHead: true`, whose message
("does not match the current branch and exact head") does not say which half
mismatched.

## Goal

A PR whose base moves after finish-work must have at least one path to a valid
completion receipt that does not require rewriting published history.

## Directions worth weighing

- Let the successor walk first-parent through a merge whose second parent is
  an ancestor of the base branch. A base update is exactly that shape, and the
  paths it introduces are already on the base — they are not the branch's
  changes, which is what the scope rule is protecting.
- Or: exclude paths reachable from the base branch from the successor scope
  check, so a base update contributes nothing to the delta by construction.
- Or: accept the deadlock and document a sanctioned rebase step, in which case
  say so explicitly in `sd-ship` rather than leaving the caller to discover
  that no receipt exists.

## Direction, settled

Settled 2026-08-26. Directions 1 and 2 together; direction 3 rejected.

Direction 3 -- accept the deadlock and document a sanctioned rebase -- fails
on who is standing in it. The loop is only reachable by a caller who may not
force-push; for anyone who may, there was never a deadlock. Documenting a step
those callers cannot take is not a route, it is a nicer error message.

Directions 1 and 2 turn out to be one change, not two. The successor range is
already walked `--first-parent`, so the base's commits are excluded from the
commit list; what remains is that the merge commit itself is on that chain and
is rejected for having two parents, and that the scope check reads a
two-endpoint `git diff anchor head`, which reports everything the base brought
in. Fixing the parent test without fixing the diff leaves the receipt failing
on other people's task paths; fixing the diff without the parent test never
gets that far.

Measured in a scratch repository rather than argued. For a branch that touched
only `branchfile.txt` and then merged a moved base:

```
:100644 100644 587be6b b77b4eb M	branchfile.txt
:000000 100644 0000000 e45c9c2 A	trellis-tasks/someone-else.md
```

`git diff-tree --cc -r <merge>` is empty for that clean base update and
non-empty when both sides edited one file, so "this base update contributed
nothing" is something git will state rather than something the validator has
to assume. A conflicted base update is refused under its own reason code: a
conflict resolution is the branch's own content, and it is the one place this
relaxation could otherwise smuggle a task-path edit past the scope rule.

The classification is deliberately three-sided rather than the obvious
one-sided test. "Second parent is an ancestor of the base tip" is also
trivially true for a merge made while sitting on the base branch -- the shape
of the existing `test_completion_successor_rejects_merge_commit` -- so the
merge must additionally **not** be an ancestor of the base tip itself, and the
base tip must resolve at all. A merge is relaxed only when it is positively
proven to be a base update, never when the validator merely cannot prove
otherwise.

See `design.md` for the mechanism and `implement.md` for the order.

## Acceptance criteria

- [ ] A completion receipt validates for a branch that was updated onto a
      moved base after its archive commit, without any history rewrite.
- [ ] Paths a base update introduces are not reported as
      `completion_successor_scope_invalid`; the case is covered by a test
      built from a real merge, not a synthesized linear range.
- [ ] Whichever direction is chosen is written into `sd-ship`'s Stage 4
      moved-head rule, which today prescribes only a route that cannot
      succeed after a base update.
- [ ] `finish_work_stale` names which of branch or head mismatched.
- [ ] A regression test pins the deadlock itself: BEHIND base, update, receipt
      — the sequence must end in a valid receipt.
