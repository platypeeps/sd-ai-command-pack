---
title: final-bundle blames every path when the base is wrong
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-07
---
# final-bundle blames every path when the base is wrong

## Goal

When `final-bundle` is invoked with a base that includes work commits, say so
once, instead of reporting every changed file as an individually invalid path
and leaving the caller to infer the argument was wrong.

## Problem

`scripts/sd-ai-command-pack-review-preflight.mjs:1131-1138`:

```js
const unsupported = paths.filter(
  (path) => !path.startsWith('.trellis/tasks/') && !path.startsWith('.trellis/workspace/'),
);
for (const path of unsupported) {
  add('bundle_scope_invalid', path, 'finalization delta contains a non-bookkeeping path');
}
```

The filter is correct: a finalization bundle *should* contain only bookkeeping
paths. What is wrong is the reporting. A base that is one work commit too old
puts every file that commit touched into the delta, and each one is reported
as though it were an independent defect in the bundle.

Observed while refreshing the pack in `loadsmith`. Invoking with
`--base origin/main` rather than the last work commit produced:

```
  34 planning_recovery_bundle_scope_invalid
  34 bundle_scope_invalid
   3 bundle_unsupported_file_mode
   1 planning_recovery_task_change_missing
   1 planning_recovery_commit_not_published
```

73 findings. Grepping all of them for `base`, `finalization base`, or
`last work commit` returns **0 matches**. Not one names the argument that was
actually wrong.

Re-running with `--base <last work commit>` returned
`valid (0 finding(s))`. Nothing about the bundle changed.

### Why the volume itself misleads

The count scales with the size of the work commit, so a larger and more
routine change produces a more alarming report. 73 findings reads as a
seriously malformed bundle. The correct reading was "the base is one commit
too old", which no single finding states.

It scales only within a window, bounded at both ends:

- Above `MAX_BOOKKEEPING_CHANGED_PATHS` (500, `:29`), the per-path loop never
  runs at all. `:1118-1121` adds a single `bundle_changed_paths_oversized`
  finding and **returns**, before reaching the `unsupported` filter and loop
  at `:1133-1138`.
  (`:1116` is unrelated — it truncates `evidence.changedPaths`, not the loop.)
- Below that, `MAX_BOOKKEEPING_FINDINGS` is 100 (`:27`) and `add` silently
  discards every finding past it (`:593`); validation itself continues.

So "one finding per unsupported path" holds only for deltas of at most 500
changed paths, and within those only up to the first 100 findings. A large
enough work commit produces a saturated 100-finding report that is no more
informative than the 73-finding one, still names no cause, and no longer even
lists every offending path — and a very large one collapses to a single
oversized finding that names no cause either.

The three `bundle_unsupported_file_mode` findings compound this. They named
`record-session.py`, `toolchain.sh`, and `work-loop.py` as introducing mode
`100755`. Those files were already `100755` before the change —
`git diff --summary origin/main HEAD` was empty. They appeared only because
the wrong base pulled them into a delta they did not belong to, so the report
invented a mode change that never happened.

### Why this is the same defect class the pack just fixed

Release 0.64.27 closed three helpers whose messages named something other than
the real cause — most directly `pr-eligibility`, which reported
`github_repository_unavailable` with `could not derive GitHub repo from origin`
when no derivation had been attempted (`CHANGELOG.md:20`). This is that pattern
once more: a truthful-looking message about the wrong subject.

## Requirements

- When a `final-bundle` run fails scope validation because the base includes
  work commits, the result names the base as the cause and the corrected base,
  having confirmed that same-mode validation at that base returns valid.
  Claiming a base is wrong without that confirmation is not acceptable — it
  reproduces the defect being fixed, one level up.
- The added diagnosis does not suppress or replace the existing per-path
  findings. Callers already parse `bundle_scope_invalid`, and a genuinely
  mis-scoped bundle at the correct base must keep reporting exactly what it
  reports today.
- The diagnosis is absent when the base is not implicated — in particular when
  the delta is a single commit, where no earlier base could be at fault.
- When the base is too old *and* the bundle is also genuinely mis-scoped, no
  candidate base validates, so no advisory is emitted and the caller sees
  today's output. That is the intended consequence of the confirmation rule
  above, not a gap: the alternative is naming a base that would not actually
  fix the run. An implementer must not "improve" on it by emitting an
  unconfirmed guess.

## Design notes

An advisory channel already exists (`addAdvisory`, `:601-606`) and is the
natural carrier: additive, does not alter `status` or `reasonCodes`, and needs
no consumer change. It is returned as **top-level `advisories`**, alongside
`evidence` and `findings` (`:660-666`); human output reads `result.advisories`
(`:701`). Only `advisoriesDropped` lives under `evidence` (`:642-644`).

Two constraints make this less free than it looks.

**History inspection is mandatory, not an optimization.**
`bookkeepingChangedEntries` (`:1952`) runs `git diff --raw` between two OIDs
and returns paths, modes, and statuses only — no commit information at all. A
tempting cheaper fallback is to raise the advisory whenever unsupported paths
appear, without inspecting history. That is unsound: a valid bundle normally
spans more than one commit — the completion fixture in
`tests/test_bookkeeping_validator.py` commits `archive fixture` (`:684`) and
then `record fixture journal` (`:687`) after its base (`:672`) — so a
correct-base bundle whose archive commit contains a stray path is
indistinguishable from a too-old base on the aggregate diff alone. The cheap
form would fire on exactly the case the false-positive guard forbids.

So the advisory must walk `base..head`, identify a candidate base, and confirm
that same-mode validation at that candidate actually returns valid before
claiming the base is at fault. Pay that cost only on the failure path, never
on the success path.

**The walk needs a declared bound.** The pack already bounds an analogous
history operation at `MAX_BOOKKEEPING_RECOVERY_COMMITS` (100, `:30`); this
search should adopt an explicit bound of its own rather than walking unbounded,
and must behave predictably at it — diagnose within the bound, and stay silent
rather than guess beyond it. An implementation that hard-codes one or two
candidate commits is not a bounded search, it is a special case.

**Both modes need covering.** The shared per-path loop at `:1133-1138` runs
before the mode branch at `:1152`, so `bundle_scope_invalid` appears in both
planning and completion. But each mode then runs its own validator
(`validateCompletionBundle` / `validatePlanningBundle`, `:1153-1157`), and the
reproduction shows a mode-specific analogue alongside the shared one — 34
`bundle_scope_invalid` *and* 34 `planning_recovery_bundle_scope_invalid`. A
diagnosis wired into only one branch leaves the other reporting exactly the
defect this task exists to fix.

**The advisory can be silently dropped.** `addAdvisory` discards additions past
`MAX_BOOKKEEPING_ADVISORIES` (25, `:28`, enforced at `:602-605`), and
saturation is a real state the suite already asserts
(`tests/test_bookkeeping_validator.py:3638` expects exactly 25). A diagnosis
that explains the whole run must not be the one that falls off the end: emit
it before lower-priority advisories, or reserve capacity for it.

## Acceptance criteria

- [ ] A `final-bundle` run whose base is one work commit too old emits an
      advisory naming the base as the cause and giving the corrected base. The
      advisory text is quoted in the task record, and the base it names is
      shown to make the same-mode run return valid.
- [ ] The same holds for a base that is *several* work commits too old, not
      only one. The requirement covers any base that includes work commits, and
      multiple unrecorded work commits on `HEAD` is a supported derivation case
      (`CHANGELOG.md:10-14`), so a fixture with at least two work commits
      between base and the bookkeeping commits is tested and the advisory still
      names the correct base. A candidate search that stops at the first parent
      fails this.
- [ ] The search bound is declared as a named constant, and both of its edges
      are tested: a delta at the bound still diagnoses, and one past it emits no
      advisory rather than a wrong one. "At least two work commits" above is a
      floor, not the requirement — an implementation hard-coded to two
      candidates must fail this criterion.
- [ ] Both `--mode planning` and `--mode completion` are covered by the
      one-work-commit and multi-work-commit criteria above. The modes diverge at
      `:1152` into `validatePlanningBundle` and `validateCompletionBundle`, and
      the reproduction shows a mode-specific finding (34
      `planning_recovery_bundle_scope_invalid`) alongside the shared one, so a
      diagnosis wired into a single branch must not pass.
- [ ] A *valid* run does no history walk. Demonstrated by evidence that the
      candidate search did not execute on the success path — a counter, a
      trace, or an injected failure in the walk that a valid run does not
      trip. This is the success-path clause of the Design notes; without this
      criterion an implementation that walks history on every run passes
      everything else.
- [ ] The same run still emits its existing `bundle_scope_invalid` findings
      — one per unsupported path, for deltas of at most 500 changed paths and
      only up to the 100-finding cap — with unchanged codes and messages.
      Verified by comparing the finding list before and after the change on
      the same base/head pair. The advisory must not
      consume finding budget: a run already at the cap keeps exactly the
      findings it produced before.
- [ ] A genuinely mis-scoped bundle at the *correct* base — one that really
      does contain a stray non-bookkeeping path — produces no base advisory.
      This is the false-positive guard and must be tested explicitly, and the
      test must use a **multi-commit** bundle (stray path in the archive
      commit, journal commit after it). A single-commit fixture cannot
      distinguish a sound implementation from the unsound cheap one.
- [ ] A single-commit delta that fails scope validation produces no base
      advisory, satisfying the Requirements clause that the diagnosis is absent
      when no earlier base could be at fault. This is a separate fixture from
      the criterion above — that one is deliberately multi-commit, so it
      cannot also cover the single-commit case.

- [ ] The advisory survives a saturated run: a case that would otherwise emit
      `MAX_BOOKKEEPING_ADVISORIES` advisories still reports the base
      diagnosis.
- [ ] A reproduction is recorded with the real base/head pair, the finding
      count before, and the finding count plus advisory after.

## Notes

Reported from `loadsmith` at pack 0.64.27. The reproduction above is from the
`0.64.3 -> 0.64.27` refresh; base `origin/main`, head the journal commit, with
the correct base being the pack-refresh work commit.

This is a diagnosis defect only. No bundle was accepted that should have been
rejected, and none was rejected that should have been accepted. The cost is
operator time and the risk of "fixing" a bundle that was never broken.

## Second instance: a correct base, and the actionable diagnosis is discarded (2026-08-09)

Reported from `platypeeps/sd-github-review` PR #72 at pack 0.64.3. Same operator
cost as the `loadsmith` case, but a different mechanism, and this one is not
caused by a wrong `--base`. It is worth folding in here because the remedy is
the same shape: name the cause once instead of emitting findings about
something else.

`validateCompletionSuccessorRecovery`
(`scripts/sd-ai-command-pack-review-preflight.mjs:1727`) tries the archive
anchor, then the active-task anchor, then chooses **which** failure to report:

```js
const findingsToCommit = (archiveResult.shapedTailCount > 0 || archiveResult.status === 'indeterminate')
  ? archiveResult.findings
  : activeTaskResult.findings;
```

On a `--base == --head` call for a branch with exactly one `in_progress` task,
the archive search walked back into the default branch's history, found one
shaped archive/journal tail there (`shapedTailCount = 1`), and failed against
it. That count alone routed the report to the archive diagnosis. The operator
received:

```
completion_successor_history_non_linear
completion_successor_history_oversized
  completion successor contains more than 50 commits
  successor commit 19c9ee6d6f45 must have exactly one parent
  ... 9 more merge commits, all on the default branch
```

Every one of those findings is about commits the operator did not write, on a
branch they were not finalizing, and none is actionable.

The suppressed `activeTaskResult.findings` — recovered by running a patched
copy of the validator that commits the active-task findings unconditionally —
named the real problem on the first line, with exact repo-relative paths:

```
completion_successor_scope_invalid | .trellis/tasks/<other-task>/prd.md
completion_successor_scope_invalid | .trellis/tasks/<other-task>/task.json
completion_successor_scope_invalid | .trellis/spec/backend/directory-structure.md
completion_successor_scope_invalid | .trellis/spec/guides/cross-layer-thinking-guide.md
```

Four paths on the operator's own branch, two of which are a genuine design
question in their own right (see the sibling report on `.trellis/spec/**` and
`active-task-review-successor`).

### Why the heuristic misfires

The comment above it reasons that a shaped tail means "a specific, actionable
reason already exists there." That holds when the shaped tail is on the branch
being finalized. It does not hold when the search escapes into the default
branch, where *any* long-lived repository has a shaped tail and
`shapedTailCount > 0` is therefore near-certain rather than informative. The
condition selects the archive diagnosis in exactly the case where it is least
relevant.

A minimal correction consistent with this PRD's existing goal: when the archive
search's shaped tail lies outside the range under finalization, prefer the
active-task diagnosis, or emit both with the active-task findings first. The
present behavior discards the only findings the operator can act on.

### Acceptance criteria (additive)

- [ ] When both successor recoveries fail and the archive search's shaped tail
      is not reachable within the branch being finalized, the reported findings
      include the active-task diagnosis.
- [ ] A reproduction is recorded showing both finding sets for one invocation,
      as above.
