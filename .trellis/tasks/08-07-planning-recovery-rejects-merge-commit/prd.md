# Journal-only recovery rejects the correct merge-first finalization order

## Goal

Let a planning finalization succeed on a branch that merged `main` before
recording its journal session — the sequence the workflow already requires —
instead of failing it as non-linear history.

## Problem

The `journal-only-recovery` subtype of `final-bundle` validation requires every
cited work commit to be single-parent. Citing a merge commit fails with:

```text
planning_recovery_commit_non_linear
```

That rule collides with the procedure the rest of the workflow prescribes.
Recording a journal session *before* merging `main` is what causes
session-number collisions: `add_session.py` derives the next number from the
working tree alone, so a branch that records first and merges later claims a
number `main` has already taken. The fix for that — established after it
happened twice on 2026-08-06 — is to merge `main` first, then record.

Doing exactly that puts the merge commit into the branch's recent history, where
it lands in the default commit list the recorder cites. Validation then rejects
it.

Observed on 2026-08-07 shipping PR #350:

```text
merge main into branch      -> 3ee62194 (merge commit)
record session 315          -> cites 3ee62194
final-bundle validation     -> planning_recovery_commit_non_linear
```

The workaround was to drop the merge commit from the journal's commit table and
the sibling index row, then amend. It worked, but it is hand-editing generated
bookkeeping to satisfy a validator, and it is discoverable only by hitting the
failure.

### Why this is not a rare edge

Any branch that lives long enough to fall behind `main` must merge before
finalizing. The longer a branch waits, the more certain this is. The correct
procedure guarantees the failure; only branches that never fell behind avoid it.

## Requirements

### Functional

- A planning finalization whose cited commits include a merge commit created by
  merging the default branch into the feature branch must validate.
- The distinction to enforce is *what the merge contains*, not *how many parents
  it has*: a merge that brings in the default branch adds no work commits of the
  branch's own and should not make the bundle non-linear.
- If some merge shapes genuinely must be rejected, the diagnostic must say which
  and name the remedy, rather than reporting only the reason code.

### Non-functional

- No weakening of the scope rules that keep a journal-only bundle
  bookkeeping-only.
- No change to `completion` mode.

## Open questions

1. Is the single-parent rule guarding against a real failure, or was it a proxy
   for "the bundle should not contain work commits"? If the latter, the check
   should test content directly.
2. Should the recorder exclude default-branch merges from the commit table it
   generates, so the citation never contains one?

## Acceptance Criteria

- [ ] A branch that merges `main` and then records a planning session validates
- [ ] A test reproduces the PR #350 sequence end to end
- [ ] Any remaining rejected merge shape has a diagnostic naming the remedy
- [ ] Open question 1 is answered in `design.md` with evidence from the
      validator's history, not from reasoning about intent

## Notes

Filed 2026-08-07 from the PR #350 ship. Related: the session-numbering defects
in `08-06-upstream-add-session-numbering`, which are why merge-first is the
required order in the first place.
