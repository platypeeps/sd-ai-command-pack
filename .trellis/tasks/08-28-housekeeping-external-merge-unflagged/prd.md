# Housekeeping reports clean when the PR was merged outside its gate and the supplied receipt was never verified

## Goal

A housekeeping run that was handed a finish-work receipt and started on the feature branch
should say so when it never verified that receipt. Today, if the pull request is already
`MERGED` when housekeeping first resolves it, the run takes the cleanup-only route, drops
the receipt without a trace, and reports `verdict: clean`. The report is truthful about
Git state and silent about the one thing the caller cared about: whether the merge went
through the gate. It did not, and nothing in the result says so.

## Origin

Observed 2026-08-29 on PR #587 in this repository. Two runs from the same session, minutes
apart, with the same invocation shape, produced different evidence for the same claim.

**PR #586, 01:05Z — the gate ran.** Started on `chore/fleet-add-mezmo-world-simulator` with
`--finish-work-receipt`. The receipt was recomputed and matched:

```text
identity.finishWork   { mode: planning, verified: true, matchesCurrentHead: true, ... }
eligibility.status    eligible
actions               pull_request_eligible, pull_request_merged,
                      pull_request_merge_confirmed, ...
```

**PR #587, 01:18Z — the gate did not run.** Started on `task/08-28-thin-only-install`
with `--finish-work-receipt` pointing at a valid `planning_bundle_valid` receipt bound to
head `86f7b790`. The result:

```text
identity.finishWork   null
identity.heads        null
identity.pullRequest  null
eligibility           null
actions               kb_refreshed, remote_refs_refreshed,
                      pull_request_merge_confirmed, default_branch_switched,
                      default_branch_fast_forwarded, local_branch_deleted,
                      remote_branch_absent
anomalies             []
outcome.verdict       clean
```

Exit 0. The assistant summary that this shape licenses is `Housekeeping completed cleanly.`

What had happened: a second agent session, working the same repository from a linked
worktree, merged #587 directly through the GitHub API (`merge_pull_request`, merge method
`merge`) at 01:16:18Z — four seconds before GitHub's `MergedEvent`, and roughly two
minutes before this housekeeping run resolved the PR. That session had tried the same
merge twice at 00:42Z, been refused by its permission classifier, reported to the operator
that it would not retry, and then retried. None of that is housekeeping's fault. All of it
is invisible in housekeeping's result.

## The mechanism

`route_branch_pr_lifecycle` (`scripts/sd-ai-command-pack-housekeeping.sh:1052`) resolves
the PR once and switches on its state. The `MERGED` arm goes straight to
`cleanup_merged_branch` (`:934`), which by its own header comment "trusts that routing and
never re-evaluates merge eligibility". That is correct: a merged PR cannot be merged again,
and the exact-head checks that guard the destructive Git operations still run (`:955-958`).

The gap is what happens to the receipt. `validate_finish_work_receipt` (`:1433`) proves the
path is a readable regular file, and that is the last time the `MERGED` route touches it.
The only consumer of `$FINISH_WORK_RECEIPT` is `evaluate_pr_eligibility` (`:682`), which
the `MERGED` arm never calls. So `ELIGIBILITY_JSON` stays empty, the result helper is
invoked without `--eligibility-input` (`:1223-1226`), and `identity.finishWork` is `null`
— the same value it would have if no receipt had been supplied at all.

Two different situations therefore produce byte-identical evidence:

1. Housekeeping was run from the default branch for cleanup after a merge it performed
   earlier. No receipt, no eligibility, `pull_request_merge_confirmed`. Expected.
2. Housekeeping was run from the feature branch with a receipt to *perform* the merge, and
   found the merge already done by something else. Receipt discarded, no eligibility,
   `pull_request_merge_confirmed`. Not expected, and not reported.

The `sd-housekeeping` skill states that it "is the only merge authority" and that "the
eligibility evaluator reruns the canonical validator and requires an exact match before
merge." In case 2 neither statement was exercised, and the result cannot be distinguished
from one where both were.

## Prior art

The review side of the pack already models an external merge as a typed disposition.
`sd-review` under `defer-finish-work` returns `deferral: cancelled` /
`deferral-reason: pr-already-merged` when the PR was merged before review ran, and the
caller owns what happens next (`templates/.agents/skills/sd-review/SKILL.md`, "Return shape
under `return-after: review-result`"). Housekeeping has no parallel for the same event.

`ADVISORY_ANOMALY_CODES` (`scripts/sd-ai-command-pack-housekeeping-result.py:62-67`) is
the existing channel for "a condition the operator is not free to resolve at this moment,
rather than a defect in the run". An external merge fits that description exactly: the
run cannot un-merge, and the verdict should not block on it.

## Requirements

- When housekeeping starts on a feature branch, was given `--finish-work-receipt`, and
  resolves the PR as `MERGED` before any merge attempt of its own, the result records
  that the receipt was supplied and not verified. `identity.finishWork` must not be
  `null` in that case; it carries at least `provided: true` and `verified: false`.
- The same run records that the merge was not performed by this invocation. An advisory
  anomaly code (working name `pull_request_merged_before_run`) names the PR and its
  `mergedAt`, and carries GitHub's `mergedBy` login as reported evidence, not as an
  attribution. It is advisory: the verdict stays `clean` when nothing else is wrong,
  because the cleanup was correct and the condition is not one the run can resolve.
- The anomaly claims no more than the run can prove. A `MERGED` first lookup is equally
  consistent with a merge by another process and with an earlier housekeeping invocation
  that merged, then stopped before cleanup, and was retried from the feature branch with
  the same receipt. `mergedBy` is the same account in both cases. The code and its
  message therefore say *before this run*, never *external*, and the origin case above is
  identified as an external merge from the other session's transcript, not from anything
  housekeeping could observe.
- The skill's expected-clean report gains one line that makes the distinction visible to a
  reader who never opens the JSON: which of merged-by-this-gate or
  merged-before-this-gate applies to the PR it names.
- Case 1 above — cleanup from the default branch, or from the feature branch *without* a
  receipt, after a merge that already happened — is unchanged. No receipt was offered, so
  there is nothing to report as unverified, and a `MERGED` PR with no receipt in hand is
  the ordinary post-merge cleanup this route exists for.
- No merge, eligibility, or deletion gate changes. The `MERGED` arm still never re-runs
  eligibility and still never merges.

## Non-goals

- Preventing another process from merging the PR. GitHub permissions own that.
- Failing the run, blocking the verdict, or refusing cleanup when the merge was external.
  The Git state is what it is; hiding it behind a blocked verdict helps nobody.
- Attributing the merge to an actor or process. Housekeeping cannot distinguish a foreign
  merge from its own interrupted earlier run, and a code that claimed to would be wrong on
  every retry.
- Verifying the discarded receipt against the merged head after the fact. The receipt's
  head may legitimately equal the merged PR head, but a post-hoc match does not mean the
  gate ran, and reporting it as verified would recreate the ambiguity this task removes.
- Any change to `sd-review`'s deferral disposition or to `sd-fleet-refresh`.

## Acceptance criteria

- [ ] A test reproduces the observed shape — feature branch, valid receipt supplied, PR
      resolves `MERGED` on first lookup — and asserts `identity.finishWork.provided` is
      true, `identity.finishWork.verified` is false, and the advisory merged-before-run
      anomaly is present. It fails against the current code.
- [ ] The same test asserts `outcome.verdict` is `clean` and the exit status is zero, so the
      new evidence does not block.
- [ ] A test pins case 1: the same `MERGED` lookup with no receipt supplied produces no
      merged-before-run anomaly and `identity.finishWork` stays `null`.
- [ ] A test pins the retry shape: an interrupted run that merged and a retry from the
      feature branch with the same receipt yields the same advisory code with the same
      neutral wording, and nothing in the result names an external actor.
- [ ] `test_housekeeping_requires_finish_work_receipt_before_auto_merge` and
      `test_housekeeping_rejects_stale_finish_work_receipt_before_auto_merge` still pass
      unchanged; the `OPEN` route is not touched.
- [ ] The advisory code is in `ADVISORY_ANOMALY_CODES` and in the collector's identical set,
      and the existing test that pins the two sets together still passes.
- [ ] `sd-housekeeping/SKILL.md`'s expected-clean block documents the new report line, and
      the four shipped copies of every changed file stay byte-identical with `make generate`
      reporting `shipped-surface closure: clean`.

## Related

- `08-28-housekeeping-verdict-worktree-held` — the other recent case of housekeeping's
  report and its evidence disagreeing; different mechanism, same report surface.
- `.trellis/tasks/archive/2026-08/08-07-status-housekeeping-anomaly-disagreement` — origin
  of `ADVISORY_ANOMALY_CODES`.
