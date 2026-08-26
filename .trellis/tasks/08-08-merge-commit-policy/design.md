# Design — one merge-commit policy

## Decision

**Merge commits are legitimate citable work commits. The validator changes;
the recorder does not.**

Recorded 2026-08-26. Requirement 1 of the PRD asks for one side to move, not
both. The validator moves because the pack has already decided this question
once, in the other bookkeeping rule, and decided it this way.

## The contradiction, and what each artifact says now

| Voice | Location | Position on a cited merge commit |
| --- | --- | --- |
| planning-recovery validator | `templates/scripts/sd-ai-command-pack-review-preflight.mjs:3007` | Refuses. `parentFields.length !== 2` → `planning_recovery_commit_non_linear`, no inspection of content. |
| completion-successor validator | same file, `classifyFirstParentMerge` (~:1851) | Accepts a *proven* base sync. Judges what the merge contains, not how many parents it has. |
| recorder | `templates/scripts/sd-ai-command-pack-record-session.py:119` `derive_work_commits` (the PRD cites `scripts/...:113-140`, the generated mirror; `templates/scripts/` is the source of truth and is where any edit goes) | Cites merges. `git log` with no `--no-merges`; the workspace-only filter passes merges on both shapes (clean merge short-circuits on an empty path list; combined-diff merge is almost never workspace-only). |
| session numbering D3 | `.trellis/tasks/08-06-upstream-add-session-numbering` | Builds the commit table by splitting on commas with no inspection. Resolution delegated here. |
| prescribed procedure | merge-main-first-then-record, established after two session-number collisions on 2026-08-06 | Guarantees a merge commit is cited. |

The prescribed procedure and the planning-recovery validator cannot both be
right. Observed on PR #350: merge `3ee62194`, session 315 cites it, validation
refuses, and the workaround was hand-editing generated bookkeeping — which is
the failure mode the bundle validator exists to prevent.

## Why the validator is the side that moves

Excluding merges from the recorder would make the two validators disagree
about what a merge *is*. After #558, the completion-successor rule accepts a
merge that is provably a base sync, on the reasoning that "everything a clean
base update carries is already on the base, so it contributes nothing the
branch is answerable for". A recorder patched with `--no-merges` would leave
planning-recovery refusing every merge on parent count while the successor
rule reasons about content two thousand lines away in the same file. That is
the three-way contradiction reproduced as a two-way one.

It also does not fix the recorder's *other* defect, which the PRD names: the
workspace-only filter mis-attributes work on non-merge shapes too. That is a
separate bug and should not be smuggled in under a policy decision.

## Mechanism

Not a copy of `classifyFirstParentMerge`. One of its three conditions inverts
here, and getting that wrong would open the gate rather than move it.

In the successor range, a merge that is *already on the base* is
disqualifying — it is a merge made while sitting on the base, not a branch
update. In planning recovery, every cited commit is *required* to be on the
base: the loop refuses anything else as
`planning_recovery_commit_not_published` before parents are ever inspected.
So "is it on the base" cannot separate the good case from the bad one here,
and the condition must be dropped rather than transplanted.

What remains is the condition that actually carries the weight:

1. The commit is already published (existing check, unchanged).
2. `git diff-tree --cc -r --name-only --no-commit-id <oid>` reports the paths
   the merge differs from *every* parent. That is the merge's own content.

A merge with no combined-diff paths contributed nothing and is cited
legitimately. A merge with combined-diff paths resolved a conflict, and the
resolution is content that was never reviewed as part of any branch — it stays
refused, under its own reason code rather than the generic one.

### Ordering, which carries a check that is easy to lose

The `--cc` test must run **before** `bookkeepingChangedEntries`, and must
refuse rather than fall through. This is not a stylistic preference.

`bookkeepingChangedEntries` parses `git diff --raw -z --find-renames` and
returns entries carrying a status (`D`/`R`/`C` detection for task artifacts)
and a destination mode — the latter is what lets the bundle validators reject
executable, symlink, and gitlink/submodule entries, which a name list cannot
distinguish. `git diff-tree --cc --name-only` returns bare paths and none of
that.

So a design that *sourced the merge's entries from* `--cc` would silently drop
delete/rename/copy detection and every mode-based rejection — a merge could
carry in a symlink or a submodule pointer and no check downstream would see the
mode to refuse it.

The ordering removes the problem instead of shimming around it:

- non-empty `--cc` → refuse as `planning_recovery_commit_merge_conflicted`, and
  never reach the entries code;
- empty `--cc` → the merge contributes nothing, so `commitEntries` and
  `commitPaths` are both empty, and every downstream per-entry and per-path
  loop is a no-op over an empty list.

Nothing is skipped, because in the only case that proceeds there is nothing to
check. No `--cc`-to-entry adapter is written, and none should be: an adapter
would be the place the mode check goes missing.

### The second change, which is not optional

`commitPaths` is currently derived from `bookkeepingChangedEntries(parentFields[1], commit.oid)`
— a diff against the first parent. For a merge that brought main in, that diff
is *all of main's changes since the branch point*, which will exceed
`MAX_BOOKKEEPING_CHANGED_PATHS` or fail the workspace-only scope rule, or both.
Relaxing the parent-count check alone therefore converts
`planning_recovery_commit_non_linear` into
`planning_recovery_commit_scope_invalid` and fixes nothing.

For a merge, the paths the commit is answerable for are the combined-diff
paths — the same set condition 2 computes. So the two changes are one change:
compute the merge's paths with `--cc`, and the empty case falls out as
"contributes nothing" without a special branch.

## Reason codes

- Keep `planning_recovery_commit_non_linear` for a merge whose parents cannot
  be read, and for the >2-parent (octopus) case, which no prescribed procedure
  produces.
- Add `planning_recovery_commit_merge_conflicted` for a two-parent merge with
  non-empty combined diff. Requirement 2 — "the losing side's diagnostic must
  name the remedy" — is met here: the message names the conflicted paths and
  says the resolution must be carried by a reviewed commit.
- A `--cc` invocation that fails is `indeterminate`, never a pass. #558's
  comment is the precedent: a merge is relaxed only when positively proven
  clean, never when the check merely cannot prove otherwise.

## D3

Resolved consistently by needing no change. `add_session.py` builds the commit
table without inspecting hashes; under this decision a merge in that table is
legal, so the upstream behaviour is correct as it stands. The note in
`08-06-upstream-add-session-numbering` delegating D3 here can be closed
against this document.

## What this does not change

`derive_work_commits` keeps citing merges, deliberately. Its workspace-only
filter defect on non-merge shapes is untouched and stays open as its own
concern — this task owns the policy, not that bug.

## Rollback

The change is additive within one loop body: a `--cc` call and a new reason
code. Reverting the diff restores parent-count refusal exactly.

The narrower claim, which is the one that was checked: no digest or schema
version keys on the planning-recovery verdict. The only hashes in this file
are `lineageDigest` and `subjectDigest`, neither of which covers it. A
finish-work receipt is retained within a run and recomputed against the
current head when the head moved, and eligibility recomputes and compares the
proof before merge — so a rule change cannot leave a stored receipt that is
accepted under the old policy. It is not claimed that no receipt exists;
it is claimed that none outlives the run that produced it.

## Where validation lands

`tests/test_bookkeeping_validator.py` already holds the sibling coverage from
#558 (`make_base_update_repo` and the `base_update` cases). The PR #350
regression belongs beside it, building a repo whose journal cites a clean
merge, plus a conflicted-merge counterpart that must still refuse. Exact
cases and commands are `implement.md`'s to specify, not this document's.
