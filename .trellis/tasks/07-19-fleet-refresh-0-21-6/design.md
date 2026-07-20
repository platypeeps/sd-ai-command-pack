# Fleet Refresh 0.23.8 Design

## Ownership Boundary

The source checkout owns the release, fleet manifest, preflight, installer, and
this Trellis task. Each consumer owns its default branch, repository-specific
validation, pull request, and housekeeping gate. Rollout changes are limited to
installer-managed payload, receipts, provenance, and managed blocks; consumer
product code remains outside scope.

## Sequential State Machine

Process consumers in manifest priority order. For each consumer: verify a clean
default branch, create a dedicated refresh branch, install with the exact
preflight command, audit the selected platform set, run the repository-owned
gate, publish and settle the PR, merge through housekeeping, then verify the
target version and audit from the synchronized default branch. Advance only
after the consumer reaches `refreshed+merged`, `PR-open`, or an explicit skip.

The source task remains the cross-repository ledger. Consumer repositories do
not receive synthetic Trellis tasks solely for vendored refresh changes.

## Failure And Recovery

- Dirty or missing checkout: skip without mutation.
- Consumer-owned validation or unrelated finding: record the consumer and
  continue only when the released payload remains sound.
- Pack correctness, security, install/audit, or compatibility defect: stop the
  fleet and prepare a source patch release before resuming.
- Red, pending, unmergeable, or commented PR: leave it open and report it; do
  not force or bypass the consumer gate.
- An interrupted rerun begins with source preflight, which makes already
  refreshed consumers `at-target` and avoids duplicate PRs.

## Completion Evidence

The final source preflight must report all seven consumers at `0.23.8`. Each
mutated consumer must be clean on its default branch, synchronized with origin,
free of its rollout branch, and pass the post-merge install audit.
