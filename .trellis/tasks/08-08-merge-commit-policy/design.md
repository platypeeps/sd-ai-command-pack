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
legitimately.

A merge **with** combined-diff paths is where an earlier draft of this
document was wrong, and the correction changes the mechanism rather than
softening a sentence. See "Premise correction" below.

### What `--cc` alone cannot tell you

`bookkeepingChangedEntries` parses `git diff --raw -z --find-renames` and
returns entries carrying a status (`D`/`R`/`C` detection for task artifacts)
and a destination mode — the latter is what lets the bundle validators reject
executable, symlink, and gitlink/submodule entries, which a name list cannot
distinguish. `git diff-tree --cc --name-only` returns bare paths and none of
that.

Under the refusal design this document originally carried, that gap was
harmless: nothing proceeded past a non-empty `--cc`, so there were no entries
to check. Under the revised mechanism the merge's paths *are* checked, so the
gap is live and is the open question recorded below. It is called out here
rather than left implicit because an adapter that quietly maps `--cc` names
into entry shapes is exactly where the mode rejection would go missing.

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

## Premise correction (2026-08-26)

`git diff-tree --cc` does not report conflicts. It reports paths whose merged
content differs from **every** parent, which is true of a conflict resolution
*and* of a file both sides merely touched that git auto-merged with no human
involvement. Measured, not argued, in
`08-26-completion-successor-cc-overrefusal` (PR #563): a clean auto-merge
exits 0 and still prints the path under `--cc`.

Two things follow, and both bear on this task.

**The earlier mechanism here was wrong.** Treating non-empty `--cc` as "the
merge resolved a conflict" would have shipped that false premise into a second
call site, under a reason code whose name asserts it. Naming a check after
something it does not measure is how the completion-successor rule's four
artifacts came to disagree with what it tests.

**The empty case is not the common case.** In this repository a version-bearing
PR must bump `manifest.json`, add the top `CHANGELOG.md` heading, and
regenerate the fleet ledgers, so any two such PRs write the same positions by
construction and the second one's base update always produces non-empty `--cc`.
A design whose only accepting branch is "`--cc` is empty" would therefore
refuse the merge-main-first-then-record procedure in exactly the cases the
procedure is used — leaving 08-08's deadlock in place while appearing to fix
it.

## Revised mechanism: check the merge's content, do not refuse it

The objection to a merge's own content is that nothing vouches for it. The
answer to unvouched content is to **check** it against the rules this loop
already applies, not to refuse the commit outright — the same reasoning as
Direction B of `08-26-completion-successor-cc-overrefusal`.

So the merge's `--cc` paths become *input to the existing per-path category
rules*, not a refusal trigger:

- empty `--cc` — the merge contributes nothing; nothing to check;
- non-empty `--cc` — those paths are the merge's own content, and they pass or
  fail on the same rules any cited commit's paths face: `.trellis/tasks/**`,
  `.trellis/workspace/**`, the task archive, and finalization evidence are
  refused; code, docs, specs, and generated payloads are ordinary work.

This keeps the property #558 set out to protect — a merge cannot smuggle a task
or workspace edit past the scope rule — while removing the refusal for the
version-stamped file set that provoked the task.

### Reason codes

No new reason code. The merge's out-of-scope paths fail under the existing
`planning_recovery_commit_scope_invalid`, which is already the accurate name
for what happened. Requirement 2 is met by naming the offending path, which
that code's message already does.

`planning_recovery_commit_non_linear` survives for a merge whose parents cannot
be read and for the >2-parent (octopus) case, which no prescribed procedure
produces. A `--cc` invocation that fails is `indeterminate`, never a pass.

### Settled by measurement (2026-08-26)

`--cc --name-only` yields bare paths, so it cannot drive the `D`/`R`/`C` checks
or the executable/symlink/gitlink rejections. `--cc --raw` can. Measured in a
scratch repository rather than assumed:

```
$ git diff-tree --cc -r --raw --no-commit-id HEAD
::100644 100644 100644 4040089d b9f14aa7 08c213db MM	f.txt
```

The combined raw record is `::<mode-p1> <mode-p2> <mode-result> <sha-p1>
<sha-p2> <sha-result> <status-per-parent>	path`. The destination mode is
present, so a gitlink (`160000`) or symlink (`120000`) introduced *by the
merge itself* is detectable.

The same probe confirmed the two things this design now rests on:

- the merge was a clean auto-merge — `git merge` exited 0, no conflict, no
  human involvement — and `--cc` still reported the path. That is #563's
  finding, reproduced independently here;
- a mode change and a symlink that arrived from the base side did **not**
  appear under `--cc`, because each matches one parent exactly. Content the
  base already carries is correctly invisible to this check, which is the
  premise the whole relaxation depends on.

**The trap this creates, which implement.md must carry.** The combined format
is not the two-endpoint format. `bookkeepingChangedEntries` parses

```
/^:(\d{6}) (\d{6}) [0-9a-f]+ [0-9a-f]+ ([A-Z]\d*)$/
```

— one leading colon, two modes, two blobs, one status. Combined records have
two colons, three modes, three blobs, and one status character per parent.
Feeding combined output to that regex produces `bundle_diff_malformed`, which
fails closed rather than silently passing, but it means the merge path needs
its own parser. That parser is the place a mode check could go missing, so it
is called out here as a named risk rather than left to be discovered.

## Dependency

This task should land after, or alongside,
`08-26-completion-successor-cc-overrefusal`. That task is correcting the same
premise in the completion-successor rule and owns the `merge-tree` accuracy
work; duplicating either here would re-create the divergence the PRD's Out of
Scope section warns about for the two `classifyFirstParentMerge` call sites.

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
regression belongs beside it, building a repo whose journal cites a merge that
carries version-stamped content — the shape that actually occurs — and a
counterpart whose merge content touches `.trellis/tasks/**`, which must still
fail under `planning_recovery_commit_scope_invalid`. A clean auto-merge that
`--cc` still reports belongs in the set too, since that is the case the old
premise got wrong. Exact cases and commands are `implement.md`'s to specify,
not this document's.
