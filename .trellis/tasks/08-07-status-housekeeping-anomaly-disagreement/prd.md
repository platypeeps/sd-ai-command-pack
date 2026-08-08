# Leftover local branches block every housekeeping run as a strict anomaly

## Goal

Stop treating leftover local branches as a blocking anomaly on every successful
merge, and make the advisory/strict distinction legible, so a reader is not told
`Anomalies: none` by one surface and `blocked` by the other with no way to
reconcile them.

## Dependency

`08-07-status-worktree-invisibility` (merged) gives `sd-status` a worktree
inventory it does not have today. The worktree-held axis in the requirements
below needs that inventory to exist; this task classifies what that one makes
visible, and must not reimplement the discovery.

## Correction: this *is* a difference of mode

The original framing of this task claimed the two surfaces contradict each
other about one body of evidence, and that this "makes disagreeing about it a
defect rather than a difference of scope". **That premise is wrong**, and
adversarial review on 2026-08-08 caught it.

`sd-housekeeping` does invoke the installed collector rather than computing its
own inventory — but it invokes it with `--expect-clean`
(`scripts/sd-ai-command-pack-housekeeping.sh:1132`), and that flag changes
what the collector produces:

- `strict_anomalies(...)` is appended only under `expect_clean`
  (`scripts/sd-ai-command-pack-status.py:2066`), and "extra local branches
  remain" is one of its entries (`scripts/sd-ai-command-pack-status.py:1682`);
- the process exits nonzero only under that flag —
  `return 1 if args.expect_clean and local_report["anomalies"] else 0`
  (`scripts/sd-ai-command-pack-status.py:2701`);
- an ordinary status run passes `expect_clean=False`
  (`scripts/sd-ai-command-pack-status.py:2493`).

So a bare `sd-status` and housekeeping's embedded call are the same collector in
two deliberately different modes: advisory and strict. "Extra local branches" is
not something one surface sees and the other ignores — it is a condition only
strict mode is asked to report. The surfaces are not contradicting each other.

**What survives the correction.** The user-visible problem is unchanged and is
the actual subject of this task: a `blocked` verdict that fires on every
successful merge carries no information, and a reader who sees `Anomalies: none`
from the advisory surface has no way to reconcile that with `blocked` from the
strict one. The defect is that strict mode treats a normal steady state as a
blocking anomaly, and that the two modes are never explained to the reader —
not that they disagree about evidence.

This changes open question 1 below: it is no longer "which surface is wrong"
but "should strict mode treat leftover branches as blocking at all".

## Problem

For one unchanged repository state on 2026-08-07:

```text
sd-status:
  ==> Expected clean state
  - local branches (3): chore/task-upstream-add-session-numbering,
                        fix/work-loop-stop-after-pause, main
  ==> Anomalies
  none

sd-housekeeping:
  verdict: blocked | reasonCodes: ['status_anomalies']
  status anomalies: ['extra local branches remain: ...']
  eligibility: eligible []   anomalies: []
```

The advisory run files the branches under **Expected clean state** and reports
`Anomalies: none`. The strict run reports them as an anomaly and housekeeping
returns `blocked`. Per the correction above these are two modes, not two
readings of one result -- but nothing in either report tells the reader that.

Note also that housekeeping's own two evidence channels agree with the
collector, not with its verdict: eligibility is `eligible` with an empty reason
list, and its own anomaly list is empty. The `blocked` verdict rests entirely on
the `status_anomalies` reason code.

## Why it matters beyond tidiness

The disagreement is not cosmetic; it trained a reader to ignore the signal.
Across five consecutive status reports the branch `chore/task-upstream-add-session-numbering`
was reported as a cleanup item and dismissed as one, because `sd-status` said
`Anomalies: none` and housekeeping's `blocked` had been routine for several
merges running.

That branch was not clutter. It held a 222-line PRD, present nowhere else in the
repository, on a branch 18 commits behind `main` with no pull request. The
repository's own session pointer dangled at a directory that existed only there.
A verdict that is `blocked` on every clean merge carries no information, so the
one time it pointed at real stranded work it read the same as the other four.

## The exact line the verdict turns on

`scripts/sd-ai-command-pack-housekeeping-result.py:255-259`:

```text
elif eligibility_status == "blocked" or event_codes or status_anomalies:
    outcome = "blocked"
    reasons = eligibility_reasons + event_codes
    if status_anomalies and not event_codes:
        reasons.append("status_anomalies")
```

`status_anomalies` is read from the **embedded collector result**
(`status.get("anomalies", [])` at
`scripts/sd-ai-command-pack-housekeeping-result.py:237`), not from
housekeeping's own `anomalies` argument. The `and not event_codes` guard is
what produces the signature shape: housekeeping's own list is empty, so the
only reason code appended is `status_anomalies`, and a reader looking at
`anomalies: []` sees a `blocked` verdict with no visible cause.

That is worth stating precisely, because the natural description — "blocked with
an empty anomalies list" — is true of the top-level `anomalies` key and
misleading about the cause. The cause is present, one level down, in
`status.anomalies`.

## Reproduced seven more times on 2026-08-07/08

Seven consecutive merges across two sessions produced this verdict, every one
of them **after** the merge had fully succeeded. A representative result:

```text
verdict: blocked | reasonCodes: ['status_anomalies']
anomalies: []
eligibility: eligible []
actions: [kb_refreshed, remote_refs_refreshed, pull_request_eligible,
          pull_request_merged, pull_request_merge_confirmed,
          default_branch_switched, default_branch_fast_forwarded,
          local_branch_deleted, remote_branch_deleted, remote_refs_pruned]
status.anomalies: ["extra local branches remain: chore/file-claude-skill-surface-gap,
  chore/file-plan-only-payload-shape, chore/file-plugin-review-lanes,
  chore/file-preflight-base-diagnosis, chore/file-preflight-planning-branch-gap,
  chore/file-record-session-merge-commit, chore/file-sd-submit-pack-task,
  chore/pack-gitignore-pycache-task, fix/work-loop-stop-after-pause,
  task/08-07-ci-preflight-mode-gap, task/08-07-default-local-review-lanes,
  task/08-07-eligibility-superseded-runs, task/08-07-review-check-stale-cache,
  task/08-07-ship-resume-kb-gap"]
```

Every merge action completed through `remote_refs_pruned`, and the executable
still exited nonzero. Two things this adds to the original report:

- **The branch count grew from 3 to 14** across these sessions without changing
  the verdict's shape. The signal does not scale with severity, so it cannot be
  used to notice that the leftover-branch situation is getting worse — which,
  over this session, it was.
- **Concurrent worktrees make the condition semi-permanent.** Several of those
  branches are checked out in other sessions' live worktrees and therefore
  cannot be deleted by any correct cleanup. A verdict that is `blocked` on a
  condition the operator is not free to resolve is guaranteed to stay `blocked`,
  which is how the original report's "trained a reader to ignore the signal"
  outcome reproduces rather than being a one-off.

This is the evidence behind the reframed open question 1: for branches held by
live worktrees, "leftover" is a normal steady state rather than a cleanup item,
which is an argument for removing the entry from `strict_anomalies` rather than
for surfacing it more loudly.

## Requirements

### Functional

- One classification of leftover local branches, used by both surfaces.
- If a leftover branch is an anomaly, `sd-status` must report it under
  `Anomalies` rather than under `Expected clean state`.
- If it is not, `sd-housekeeping` must not return `blocked` for it.
- A branch that is *unmerged and has no pull request* must be distinguishable
  from one that is merged and simply not yet deleted. Those are different
  conditions and only one of them is cleanup.
- Worktree-held is an orthogonal axis, not a third label. A branch may be
  merged and held, or unmerged and PR-less and held, so the classification is a
  matrix over (merge/PR state) x (worktree-held) rather than three exclusive
  categories. A held branch cannot be deleted while held, so treating it as a
  cleanup item makes the verdict permanently unresolvable for anyone running
  concurrent sessions.
- Unknown PR evidence is its own state. The collector can report GitHub
  unavailable and bounds its open-PR enumeration, so "unmerged and PR-less"
  must never be asserted from absent, truncated, stale, or failed PR evidence --
  that combination reports as unknown, not as the condition that matters.
- Whatever reason code survives must name its cause where a reader will see it.
  Today the top-level `anomalies` list is empty while the cause sits in
  `status.anomalies`, so the verdict reads as unexplained.

### Non-functional

- No weakening of housekeeping's merge, deletion, or eligibility gates.
- `sd-status` remains read-only.

## Open questions

1. Should strict mode treat leftover local branches as blocking at all? Given
   the correction above, the question is not which surface is wrong but whether
   `strict_anomalies` should include a condition that is a normal steady state
   for anyone running concurrent worktrees. If it should, the reader needs the
   advisory/strict distinction surfaced; if not, the entry leaves
   `strict_anomalies`.
2. Should "unmerged branch with no PR" become its own reason code? It is the
   condition that actually mattered here, and neither surface names it today.

## Acceptance Criteria

- [ ] One shared classification; no state yields `Anomalies: none` alongside
      `reasonCodes: ['status_anomalies']`
- [ ] An unmerged, PR-less local branch is reported distinctly from a merged
      undeleted one, and from either of those while held by a live worktree
- [ ] Unavailable, truncated, or stale PR evidence yields an explicit unknown
      rather than a false "no pull request" claim
- [ ] A branch held by a live worktree is reported distinctly from both, and
      does not by itself produce a `blocked` verdict
- [ ] A successful merge whose **only** embedded strict anomaly is the
      leftover-branch entry does not exit nonzero. Every other strict anomaly --
      dirty tree, divergent default branch, retained remote source branch --
      still blocks exactly as it does today; this criterion reclassifies one
      condition and must not become a general exit-zero rule
- [ ] Any surviving `blocked` verdict names its cause in the same structure a
      reader inspects, not only in the embedded `status.anomalies`
- [ ] A test asserts the two surfaces agree on a fixture with leftover branches
- [ ] Open question 1 is answered in `design.md` with a decision and rationale

## Notes

Filed 2026-08-07. The concrete cost is recorded above: five reports, one
stranded 222-line PRD, recovered as PR #353.
