# Fleet refresh 0.21.4 design

## Boundaries

The pack checkout is the orchestration source and remains on clean `main` at
released version 0.21.4. Each consumer is an independent mutation boundary.
The installer may change only managed payload, receipts, provenance, and
managed blocks; consumer product code is outside this task.

## Sequential State Machine

For each consumer in manifest priority order:

1. `eligible`: local clone exists and the worktree is clean.
2. `branched`: the default branch is current and a dedicated refresh branch is
   checked out.
3. `installed`: the preflight command installs 0.21.4 for every selected
   platform.
4. `validated`: expected-platform audit and consumer-owned full-check pass.
5. `published`: installer-owned changes are committed, pushed, and represented
   by exactly one open PR.
6. `settled`: required checks are green and review threads are resolved.
7. `merged`: the consumer housekeeping gate merges and cleans the branch.
8. `verified`: provenance reads 0.21.4, audit passes, and the default branch is
   clean and synchronized.

The next consumer starts only after the previous consumer reaches `verified`,
is intentionally `PR-open`, or is `skipped`.

## Failure Policy

- Dirty or missing checkout: skip without mutation and continue.
- Consumer-owned check failure: leave the local refresh branch for inspection,
  do not publish a PR, record the reason, and continue unless it exposes a pack
  compatibility defect.
- Pack correctness, security, install/audit, or compatibility defect: stop the
  fleet and report the need for a patch release.
- Low-risk style or unrelated consumer issue: record a follow-up and continue.
- Red CI, unresolved review, head drift, or non-clean merge state: do not merge;
  leave the PR open and report the blocker.

## Compatibility And Rollback

The installer writes consumer-local copies from the released source checkout.
A pre-PR failure remains on an unmerged local branch for inspection; no reset
or clean is permitted. A published failure remains an open PR until fixed or
closed deliberately. Consumers already merged are not rolled back because a
later consumer is skipped; only a confirmed released-pack defect justifies a
patch release and another fleet refresh.

## Reporting Contract

Track each consumer's preflight version, branch and PR identity, validation
result, merge result, and post-merge version. The final report uses only
`at-target`, `refreshed+merged`, `PR-open`, or `skipped+reason` outcomes.
