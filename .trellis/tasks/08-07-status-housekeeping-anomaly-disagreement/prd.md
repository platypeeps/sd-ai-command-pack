# sd-status and sd-housekeeping disagree about extra local branches

## Goal

Make one verdict about whether leftover local branches are an anomaly, so a
reader is not told "clean" and "blocked" about the same repository state.

## Housekeeping embeds the very collector it contradicts

`sd-housekeeping` does not compute its own inventory. Its task list has it
invoke the installed `sd-status --json` collector in strict mode and embed the
result unchanged, explicitly forbidding a parallel final-state collector. The
two verdicts are therefore produced from one body of evidence, which is what
makes disagreeing about it a defect rather than a difference of scope.

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

The status collector files the branches under **Expected clean state** and
reports `Anomalies: none`. Housekeeping reads the same evidence and returns
`blocked`.

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

## Requirements

### Functional

- One classification of leftover local branches, used by both surfaces.
- If a leftover branch is an anomaly, `sd-status` must report it under
  `Anomalies` rather than under `Expected clean state`.
- If it is not, `sd-housekeeping` must not return `blocked` for it.
- A branch that is *unmerged and has no pull request* must be distinguishable
  from one that is merged and simply not yet deleted. Those are different
  conditions and only one of them is cleanup.

### Non-functional

- No weakening of housekeeping's merge, deletion, or eligibility gates.
- `sd-status` remains read-only.

## Open questions

1. Which surface is wrong? Housekeeping's `blocked` is arguably right and the
   collector's `none` arguably wrong, but the reverse is defensible if leftover
   branches are normal in this workflow.
2. Should "unmerged branch with no PR" become its own reason code? It is the
   condition that actually mattered here, and neither surface names it today.

## Acceptance Criteria

- [ ] One shared classification; no state yields `Anomalies: none` alongside
      `reasonCodes: ['status_anomalies']`
- [ ] An unmerged, PR-less local branch is reported distinctly from a merged
      undeleted one
- [ ] A test asserts the two surfaces agree on a fixture with leftover branches
- [ ] Open question 1 is answered in `design.md` with a decision and rationale

## Notes

Filed 2026-08-07. The concrete cost is recorded above: five reports, one
stranded 222-line PRD, recovered as PR #353.
