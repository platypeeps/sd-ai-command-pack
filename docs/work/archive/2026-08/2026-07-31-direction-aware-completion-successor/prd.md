---
title: Make completion-successor validation direction-aware
status: done
created: 2026-07-31
---
# Make completion-successor validation direction-aware

## Goal

Close the class of unresolvable merge blocks where a branch that legitimately
reverts a premature `task.py archive` can no longer satisfy any validation mode
in `scripts/sd-ai-command-pack-review-preflight.mjs`, and produces an opaque
`completion_successor_scope_invalid` with no documented recovery path.

The equivalent direction-blindness in the Python CI classifier was fixed in
`b3d0cb25` (`has_archive` now requires change type `A`/`M` under `archive/`).
The `.mjs` preflight carries a second, independent implementation of the same
classification concept and did not receive that fix.

## Background

PR #301 hit this. Its history legitimately contains `c59db841`
("Revert \"chore(task): archive 07-28-measure-unmeasured-runtime-surface\"",
reverting `c74a79eb`), which undoes a premature archive caused by the
now-fixed direction-blind CI classifier. `56946e32` is a *later* follow-up on
the same branch, not the revert itself.

`c59db841` necessarily restores paths under `.trellis/tasks/`. Verified shape:

```
R100  .trellis/tasks/archive/2026-07/07-28-…/prd.md   → .trellis/tasks/07-28-…/prd.md
R093  .trellis/tasks/archive/2026-07/07-28-…/task.json → .trellis/tasks/07-28-…/task.json
```

Every subsequent `final-bundle --mode completion` run returned
`completion_successor_scope_invalid` — reported as 12 occurrences by the run that
hit it; that count is a prior-session observation and is not reproducible now,
unlike the commit shape above, which is. No override, force, skip, or bypass flag
exists in either `scripts/sd-ai-command-pack-housekeeping.sh` or the preflight
validator, so the PR could only be merged by abandoning pack tooling entirely.

## Non-Goals

- **Do not weaken the successor scope guard.** Its purpose — no unattested
  bookkeeping mutation after the finalization a receipt attests to — is correct
  and stays. A branch whose finalization was undone must still fail.
- Do not add an override, force, or bypass flag to the validator or to
  housekeeping.
- Do not change the Python classifier; `b3d0cb25` already settled that lane.

The goal is that the failure becomes **diagnosable and recoverable**, not that
it becomes a pass.

## Requirements

- R1: `isAdjacentArchiveCommit` must be direction-aware. A commit that only
  removes paths from `.trellis/tasks/archive/` (a pure un-archive) must not
  qualify as a completion anchor's archive commit. This mirrors the `A`/`M`
  restriction that `b3d0cb25` applied to `has_archive`.
- R2: The anchor scan must stay fail-closed. A candidate whose successor range is
  `invalid` **or** `indeterminate` remains terminal — the scan must not continue
  past it in search of a passing anchor. An earlier draft of this requirement
  asked for the opposite; adversarial review showed that continuing would (a)
  convert git-inspection failures into passes and (b) let a bookkeeping mutation
  and its later reversal cancel inside a wider two-endpoint diff, defeating the
  guard. R1 already removes the case that motivated it. See `design.md` D2.
- R3: When the successor range un-archives the exact task the candidate anchor
  archived, that anchor is void. Report it under a distinct reason code, emitted
  alongside — not instead of — the scope findings for that range. "Un-archives"
  requires both halves for the same task: the archived `task.json` leaves and the
  active `task.json` arrives. A deletion without a restoration, or an added active
  copy while the archive remains, is a different event and keeps its own code.
- R4: The new reason code must state the recovery action — the finish-work
  receipt is stale and must be regenerated against the current head — so the
  operator is not left guessing.
- R5: Every behavior change is covered by a test built on the existing
  `make_post_archive_successor_repo` fixture in
  `tests/test_bookkeeping_validator.py`.
- R6: Existing successor tests keep passing unchanged. In particular, the
  guard-preserving cases at `tests/test_bookkeeping_validator.py:1136` and
  `:1162` must still yield `completion_successor_scope_invalid`.

## Acceptance Criteria

- [ ] A pure un-archive commit is not accepted as a completion *archive* anchor
      (new test, R1). On the post-#302 base it then falls through to the active-task
      recovery path and reports `completion_successor_active_task_anchor_missing`
      (an intended, better diagnosis than the pre-#302 `anchor_missing`); it must not
      report `completion_successor_anchor_reverted`.
- [ ] A candidate whose successor range is `indeterminate` still terminates the
      scan and reports `completion_successor_history_unavailable` — it does not
      fall through to a later anchor (new test, R2).
- [ ] An anchor whose task is un-archived later in the branch reports the new
      dedicated reason code **in addition to** its scope findings
      (new test, R3/R4).
- [ ] Half an un-archive is not diagnosed as one: an archived task deleted without
      restoration, and an active copy added while the archive remains, each report
      `completion_successor_scope_invalid` without
      `completion_successor_anchor_reverted` (new test, R3).
- [ ] Mixed failure keeps both diagnoses: a successor that un-archives the anchored
      task *and* writes `.trellis/.runtime/` reports
      `completion_successor_anchor_reverted` and `completion_successor_scope_invalid`
      together (new test, R3/R6).
- [ ] A fixture replaying the verified `c59db841` un-archive shape (archive→active
      renames of the whole task directory, `task.json` as a modified rename — `R093`
      observed because the revert restores the original active content; the exact
      similarity index is immaterial to the code path, which keys on `R…` status and
      paths, not the number) yields only `completion_successor_scope_invalid` before
      the change, and gains `completion_successor_anchor_reverted` after.
- [ ] Guard is intact: forbidden post-finalization bookkeeping mutation and
      `.trellis/.runtime/` writes still fail with
      `completion_successor_scope_invalid`.
- [ ] `make check` passes.

## Notes

- Source: direct fallout from PR #301, merged manually on 2026-08-01 by the user
  after the pack's own merge gate proved unable to pass it.
- Defects are in `scripts/sd-ai-command-pack-review-preflight.mjs` (post-#302
  anchors): `isAdjacentArchiveCommit` (:1769) and the diagnosis emitted by the scope
  loop in `evaluateCompletionSuccessorRange` (:1832). The successor-block `return`
  inside `attemptArchiveAnchorRecovery` (:1260) was initially listed as a third
  defect; it is not one — it is the fail-closed behavior this task preserves
  deliberately. (Pre-#302 these were :1279 / :1395 / :1209 inside the then-monolithic
  `validateCompletionSuccessorRecovery`.)
- Open question for `design.md`: whether the stale-receipt case is better
  detected here or at receipt generation in the finish-work lane. The validator
  fix is worth doing regardless, because the validator must fail *legibly* even
  when handed a stale receipt.
- Two independent implementations of one classification concept (Python CI
  scope + `.mjs` preflight) is itself the root risk — one got fixed, one did
  not. Worth a follow-up on whether they can share a contract; out of scope here.
