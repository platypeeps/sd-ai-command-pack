# Fleet Refresh 0.19.4 Implementation Plan

## 1. Establish Release State

- [ ] Confirm `main` is clean and synchronized with `origin/main`.
- [ ] Confirm `manifest.json` reports `0.19.4` and tag `v0.19.4` resolves to
  the current release commit.
- [ ] Run the source-owned fleet preflight and preserve its starting-version
  classifications and exact install/audit commands.

Rollback point: stop before consumer mutation if release identity, tag, ledger,
or preflight is invalid.

## 2. Refresh Consumers Sequentially

For each refresh-needed consumer in preflight order:

- [ ] Verify the local checkout exists, is clean, and is on a synchronized
  default branch; otherwise record a skip without mutation.
- [ ] Create a uniquely named `codex/` refresh branch from the default branch.
- [ ] Run the preflight-provided install command from the pack source checkout.
- [ ] Run the preflight-provided install audit with every expected platform.
- [ ] Run the consumer's documented structural-map preparation when required,
  then its canonical full-check.
- [ ] Inspect the diff and confirm it contains only installer-owned payload,
  receipts/provenance, and required deterministic generated artifacts.
- [ ] Commit, push, and create a refresh PR with literal-file body handling.
- [ ] Wait for CI and review to settle; address only consumer-owned integration
  findings and stop for any released-pack defect.
- [ ] Merge through the consumer's housekeeping gate and complete branch/ref
  cleanup.
- [ ] Confirm post-merge provenance is `0.19.4` and rerun install audit.

Rollback point: before PR creation, leave a failed local branch intact for
inspection. After PR creation, never force-push or bypass a blocked merge gate.

## 3. Close The Rollout

- [ ] Rerun fleet preflight or fleet status to confirm final versions.
- [ ] Record each consumer's before-version and final result.
- [ ] Record skipped consumers, open PRs, anomalies, and released-pack defects
  as explicit follow-ups.
- [ ] Update task acceptance criteria and run the relevant source-repo checks
  for task/spec-only bookkeeping.
- [ ] Commit the rollout task record and finish the Trellis session.

## Release Correction Evidence

- [x] Stopped the 0.19.3 rollout when Loadsmith PR #90 identified a pack-owned
  file-path resolution defect; no 0.19.3 consumer PR was merged.
- [x] Fixed `resolve_repo()` in the canonical status template and root mirror,
  with coverage for a file inside a repository and a missing path.
- [x] Bumped the shipped payload and release documentation to 0.19.4.
- [x] Regenerated command surfaces and dogfood provenance.
- [x] Passed the full-fleet 0.19.4 candidate check for all seven consumers.
- [x] Passed the canonical source tests, coverage, lint, type, security, audit,
  KB freshness, template parity, release-ledger, and full-check lanes.
