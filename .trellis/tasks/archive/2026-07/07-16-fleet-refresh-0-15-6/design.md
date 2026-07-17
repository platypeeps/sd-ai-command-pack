# Fleet refresh 0.15.6 design

## Boundaries

The pack checkout is the orchestration source and remains on clean `main` at
tagged version 0.15.6. Each consumer is an independent mutation boundary. The
installer may change only its managed payload, receipt, provenance, and managed
blocks; consumer product code is outside this task.

## Sequential State Machine

For each consumer in manifest priority order:

1. `eligible`: local clone exists, worktree is clean, default branch is known.
2. `branched`: default branch is fast-forwarded and a dedicated refresh branch
   is checked out.
3. `installed`: the preflight command installs 0.15.6 for all selected
   platforms.
4. `validated`: expected-platform audit and consumer-owned full-check pass.
5. `published`: installer-owned changes are committed, pushed, and represented
   by exactly one open PR.
6. `settled`: required checks are green and review threads are resolved.
7. `merged`: the consumer housekeeping gate merges and cleans the branch.
8. `verified`: provenance reads 0.15.6, audit passes, and the default branch is
   clean and synchronized.

The next consumer starts only after the previous consumer reaches `verified`,
`PR-open` under an explicit no-merge run, or `skipped`.

## Failure Policy

- Dirty or missing checkout: skip without mutation and continue.
- Consumer-owned check failure: leave the local refresh branch for inspection,
  do not publish a PR, record the reason, and continue unless it exposes a pack
  compatibility defect.
- Pack correctness, security, install/audit, or compatibility defect: stop the
  fleet and report a patch-release requirement.
- Low-risk style or unrelated consumer issue: record a follow-up and continue.
- Red CI, unresolved review, head drift, or non-clean merge state: do not merge;
  leave the PR open and report the blocker.

## Compatibility And Rollback

The installer is run from the tagged source checkout but writes consumer-local
copies. A pre-PR failure is rolled back by leaving the branch unmerged for
inspection; no reset or clean is permitted. A published failure remains an
open PR until fixed or closed deliberately. Merged consumers are not rolled
back merely because a later consumer is skipped; only a confirmed released-pack
defect justifies a patch release and subsequent fleet refresh.

## Reporting Contract

Track each consumer's preflight version, branch/PR identity, validation result,
merge result, and post-merge version. The final report uses only `at-target`,
`refreshed+merged`, `PR-open`, or `skipped+reason` outcomes.
