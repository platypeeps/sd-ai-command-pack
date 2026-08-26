# Design — a completion receipt that survives a base update

## The direction taken

PRD direction 1 and direction 2, together. Direction 3 (document the deadlock
and sanction a rebase) is rejected: the deadlock is only reachable by callers
who may not force-push, so "sanctioned rebase" is not a route for the people
who hit it.

Nothing here is speculative. Each claim below was measured against a scratch
repository containing a real base-update merge, not reasoned from the git
manual.

## What actually breaks

`evaluateCompletionSuccessorRange(anchorOid, headOid)`
(`templates/scripts/sd-ai-command-pack-review-preflight.mjs:2157`) already
walks `rev-list --first-parent --reverse anchor..head`, so the base's commits
are correctly excluded from the commit list. Two things then fail anyway.

**One.** The base-update merge is itself on the first-parent chain, and the
per-commit check rejects any commit without exactly one parent:

```js
if (fields.length !== 2 || fields[0] !== oid) {
  add('completion_successor_history_non_linear', ...)
```

Measured: a merge commit yields three fields where a linear commit yields two.

**Two.** The scope check reads a two-endpoint diff:

```js
const entries = bookkeepingChangedEntries(anchorOid, headOid, () => {});
```

`git diff --raw anchor head` reports everything the base brought in.
Measured, for a branch that touched only `branchfile.txt`:

```
:100644 100644 587be6b b77b4eb M	branchfile.txt
:000000 100644 0000000 e45c9c2 A	trellis-tasks/someone-else.md
```

The second path is someone else's, arriving from the base. Under the real
rule it is a `.trellis/tasks/` path and the receipt is refused. This is
exactly the PRD's observation that the failure names task paths the branch
never touched.

## The two predicates

**A base-update merge is identifiable, but not by the obvious test alone.**
`git merge-base --is-ancestor <P2> <base-tip>` is measured `YES` for the merge
above -- and it is also trivially true for a merge that has already landed on
the base branch, or for one made while sitting on the base branch. The existing
`test_completion_successor_rejects_merge_commit` (`tests/test_bookkeeping_validator.py:2005`)
is exactly that shape: it merges a side branch into `main` and expects
`completion_successor_history_non_linear`. A one-sided predicate would newly
accept it.

So the classification takes three conditions, and all three must hold:

1. the base tip resolves at all;
2. `--is-ancestor <P2> <base-tip>` -- the second parent is already on the base;
3. `--is-ancestor <merge-oid> <base-tip>` is **false** -- this branch's work is
   not itself on the base yet.

Condition 3 is what separates "I pulled the base into my branch" from "my
branch is the base". Fail any of the three and the commit is rejected as
`completion_successor_history_non_linear`, exactly as today. A merge is
relaxed only when it is positively proven to be a base update, never when the
validator merely cannot prove otherwise.

**A clean base update contributes nothing, and git will say so.**
`git diff-tree --cc -r <merge>` lists only paths modified relative to *all*
parents -- conflict resolutions. Measured empty for the clean base update, and
measured non-empty for a merge where the same file was edited on both sides:

```
diff --cc f.txt
index fe1d009,943f5f0..2ab19ae
```

So a conflicted base update is detectable and is refused under its own reason
code rather than being waved through. That matters: a conflict resolution
inside a base-update merge is the branch's own content, and it is the one
place this change could otherwise smuggle a task-path edit past the scope
rule.

## The changes

Both in `templates/scripts/sd-ai-command-pack-review-preflight.mjs` (source of
truth), plus one message in
`templates/scripts/sd-ai-command-pack-pr-eligibility.py`.

### 1. Accept a clean base-update merge on the first-parent chain

In the per-commit loop, a commit with three fields is no longer rejected
outright. It is accepted when both predicates hold, and refused otherwise:

- second parent is not an ancestor of the base tip -> keep
  `completion_successor_history_non_linear`, message unchanged.
- second parent is an ancestor but `diff-tree --cc` is non-empty -> a new
  reason code, `completion_successor_base_update_conflicted`, naming the
  conflicted paths. A distinct code, not a reuse: "you merged a feature
  branch" and "your base update had conflicts" call for different next steps
  from the caller.
- both hold -> accepted, and it contributes **no** paths.

The base tip needed by the first predicate is resolved inside the validator by
`trellisRootDefaultBranchName()` (`:5560`), which is already the file's answer
to "what is this repository's default branch" and is deliberately *not*
`defaultReviewBaseRef()` -- that one may return a stacked-PR feature base. Its
return is a bare name, so the tip is `origin/<name>` when that ref exists and
`<name>` otherwise.

When neither resolves, the merge is rejected as before. An earlier draft of
this design made that case `indeterminate`, on the reasoning that "I cannot
tell whether this was a base update" is a different statement from "this is a
feature merge". It is, but it is the wrong trade here: the validator's job is
to refuse a receipt it cannot vouch for, and an unresolvable base is a reason
to keep refusing, not a reason to soften the verdict. It also keeps every
existing test -- which runs in repositories with no `origin` and no
`SD_AI_COMMAND_PACK_DEFAULT_BRANCH` -- on exactly its current path.

### 2. Take the scope diff per commit, not endpoint to endpoint

Replace the single `bookkeepingChangedEntries(anchorOid, headOid, ...)` with a
union of `bookkeepingChangedEntries(parent, oid, ...)` across the first-parent
chain, skipping accepted base-update merges.

This is not a new idiom. `evaluateActiveTaskSuccessorRange` (`:1824`)
already walks exactly this way -- `bookkeepingChangedEntries(parent, oid, ...)`
threaded through a `parent` variable -- and the completion variant is the one
that diverged. The change brings the two into line rather than inventing a
third shape.

The union is slightly more conservative than the endpoint diff for a linear
range: a path added and then deleted appears in the union and not in the
endpoint diff. That direction is fail-closed, and it is the same conservatism
the active-task variant has always had.

`entries` in the return value is derived from the same union, so paths the
base contributed are not mode-validated either. Otherwise a base carrying an
executable file would fail the receipt under `bundle_unsupported_file_mode`
for a file the branch never touched -- which is the PRD's second measured
route failing for the same underlying reason as the first.

### 3. The same fix in the active-task variant

`evaluateActiveTaskSuccessorRange` rejects a merge with the identical
`fields.length !== 2` test (`:1856`; the completion variant's copy is `:2189`). A base update breaks it the same way.
The predicate is factored into one helper used by both; fixing one and leaving
the other is how the two variants diverged in the first place.

### 4. `finish_work_stale` says which half mismatched

`revalidate_finish_work_receipt`
(`templates/scripts/sd-ai-command-pack-pr-eligibility.py:356`) tests
`receipt_head != head or receipt_branch != branch` and reports one message for
both. The PRD hit exactly the confusing case: `matchesCurrentHead: true`
alongside "does not match the current branch and exact head". The message
becomes specific to whichever half actually differs, and names both values
when both do.

## Compatibility

- **Widened:** a branch updated onto a moved base can produce a valid
  completion receipt with no history rewrite. This is the deadlock.
- **Widened, incidentally:** a linear range is unaffected in the common case;
  the per-commit union only differs for add-then-delete, where it is stricter.
- **Narrowed:** nothing. A feature merge is still
  `completion_successor_history_non_linear`; a merge on the base branch itself
  still is, by condition 3; an unresolvable base tip still is; and a conflicted
  base update is refused under a new code rather than being newly permitted.
- Receipt schema, reason-code consumers, and every other validator are
  unchanged. `completion_successor_base_update_conflicted` is additive.

## Rollback

Revert the commit. No receipt field changes shape, so a receipt written under
either version validates under the other, except that a receipt produced for a
base-updated branch will stop validating -- which is the pre-change behaviour.

## Cross-task: this defect was already reported, twice

Found during implementation by grepping the reason code across the task tree,
not from the PRD.

**`08-09-update-branch-linearity-conflict`** (status `planning`) is the same
defect, observed on PR #400 on 2026-08-09 — sixteen days before PR #551
rediscovered it. It states the fix as option (a):

> successor validation learns a bounded, verifiable allowance for base-sync
> merge commits (second parent must be reachable from the default branch and
> the merge must introduce no delta versus its first parent beyond the base
> sync)

That is what shipped here, with one condition its wording does not carry: the
merge must also not already be on the default branch, or a merge made *while
sitting on* the base classifies as a base update. Its three acceptance
criteria are met by this task's tests and docs. It should be closed as
superseded rather than planned again — but that is the operator's call, not
this task's, so it is recorded here and raised rather than acted on.

**`08-08-merge-commit-policy`** (status `planning`) owns the standing
instruction not to decide this twice, and `08-09` defers to it explicitly.
Its requirement 1 asks whether merge commits are legitimate citable work
commits — "then fix the validator: distinguish what the merge contains, not
parent count" — or not. This change takes the first side, for one path, on
exactly that reasoning: it reads what the merge contains rather than counting
parents.

It does **not** decide `08-08`. That task's scope is the `journal-only-recovery`
subtype (`planning_recovery_commit_non_linear`) and `derive_work_commits` in
the session recorder, neither of which is touched here;
`test_journal_only_recovery_rejects_merge_commit` still passes unchanged. What
this change contributes to `08-08` is a precedent and a working predicate: if
that task decides the other way, this exception is the thing it has to
withdraw, and it is confined to `classifyFirstParentMerge`.
