# Fleet Refresh 0.19.11 Implementation Plan

## 1. Establish Release State

- [x] Confirm `main` is clean and synchronized with `origin/main`.
- [x] Confirm `manifest.json` reports `0.19.11` and tag `v0.19.11` resolves to
  the current release commit.
- [x] Run the source-owned fleet preflight and preserve its starting-version
  classifications and exact install/audit commands.

Rollback point: stop before consumer mutation if release identity, tag, ledger,
or preflight is invalid.

## 2. Refresh Consumers Sequentially

For each refresh-needed consumer in preflight order:

- [x] Verify the local checkout exists, is clean, and is on a synchronized
  default branch; otherwise record a skip without mutation.
- [x] Create a uniquely named `codex/` refresh branch from the default branch.
- [x] Run the preflight-provided install command from the pack source checkout.
- [x] Run the preflight-provided install audit with every expected platform.
- [x] Run the consumer's documented structural-map preparation when required,
  then its canonical full-check.
- [x] Inspect the diff and confirm it contains only installer-owned payload,
  receipts/provenance, and required deterministic generated artifacts.
- [x] Commit, push, and create a refresh PR with literal-file body handling.
- [x] Wait for CI and review to settle; address only consumer-owned integration
  findings and stop for any released-pack defect.
- [x] Merge through the consumer's housekeeping gate and complete branch/ref
  cleanup.
- [x] Confirm post-merge provenance is `0.19.11` and rerun install audit.

Rollback point: before PR creation, leave a failed local branch intact for
inspection. After PR creation, never force-push or bypass a blocked merge gate.

## 3. Close The Rollout

- [x] Rerun fleet preflight or fleet status to confirm final versions.
- [x] Record each consumer's before-version and final result.
- [x] Record skipped consumers, open PRs, anomalies, and released-pack defects
  as explicit follow-ups.
- [x] Update task acceptance criteria and run the relevant source-repo checks
  for task/spec-only bookkeeping.
- [x] Commit the rollout task record and finish the Trellis session.

## Final Rollout Record

| Consumer | Before | Result | Pull request |
| --- | --- | --- | --- |
| `platypeeps/rwbp-coordinator` | `0.19.7` | `refreshed+merged` | #120 |
| `platypeeps/loadsmith` | `0.19.3` | `refreshed+merged` | #90 |
| `platypeeps/hoa-manager` | `0.15.6` | `refreshed+merged` | #115 |
| `platypeeps/rwbp-website` | `0.15.6` | `refreshed+merged` | #133 |
| `answerbook/mezmo_benchmark` | `0.15.6` | `refreshed+merged` | #353 |
| `platypeeps/se-ai-command-pack` | `0.16.2` | `refreshed+merged` | #8 |
| `platypeeps/anomaly-metric-creator` | `0.15.6` | `refreshed+merged` | #251 |

Final fleet preflight reports all seven consumers at target `0.19.11`. There
are no stale consumers or open refresh PRs.

Follow-up records:

- `platypeeps/hoa-manager#114` tracks the repo-owned `npm run dev:db`
  documentation mismatch found during local validation.
- `platypeeps/sd-ai-command-pack#159` tracks low-risk hardening for the generic
  `.split(...)` boundary-risk classifier advisory.
- The rwbp-website local full-check required one retry after a sandbox approval
  timed out before execution; the retry passed without a product change.
- Mezmo's repo-owned housekeeping smoke test migrated three expected labels to
  the delegated `sd-status` output; the full suite then passed.
- Mezmo Copilot review produced one false-positive line-suffix-regex comment;
  direct source proof showed the literal colon is required, and the thread was
  resolved without a code change.

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
- [x] Stopped before tagging when source PR #154's squash merge exposed the
  two-parent-only main-push scope assumption.
- [x] Added GitHub-confirmed squash/rebase PR-merge detection while preserving
  fail-closed direct-push behavior, with focused tests for accepted and
  malformed evidence.
- [x] Hardened the workflow to avoid the GitHub PR API for traditional merge
  commits and made status repository discovery run from its normalized
  candidate directory.
- [x] Restored reserved `archive/` root rejection in the Trellis task artifact
  parser after final source review exposed the invalid-path regression.
- [x] Passed the full-fleet 0.19.8 candidate check for all seven consumers.
- [x] Refreshed the full-fleet candidate ledger after the archive-root fix.
- [x] Passed the canonical source gates for the final reviewed 0.19.8 payload.
- [x] Stopped the 0.19.8 rollout when coordinator PR #118 exposed first-page
  review-count truncation; no consumer refresh PR was merged.
- [x] Replace the REST page length with GraphQL `reviews.totalCount`, add
  regression coverage above the default page size, and document the contract.
- [x] Pass the full-fleet candidate check and canonical source gates for 0.19.9.
- [x] Merge source PR #156, pass the main release workflow, and tag the exact
  reviewed merge commit as `v0.19.9`.
- [x] Stop before updating the coordinator when its late review thread showed
  the boundary-risk sweep still read oversized untracked code in full.
- [x] Reuse a bounded file-descriptor read for untracked diff sizing and risk
  scanning, warn about skipped oversized code, and add focused coverage.
- [x] Pass the full-fleet candidate check and canonical source gates for 0.19.10.
- [x] Merge source PR #157, pass the main release workflow, and tag the exact
  reviewed merge commit as `v0.19.10`.
- [x] Complete coordinator PRs #118/#119 at 0.19.10 and verify post-merge audit.
- [x] Stop the Loadsmith rollout when PR #90 exposed raw-base comparison in
  the shared review-size and added-code risk probes.
- [x] Compare those probes from the branch merge base, document the contract,
  and add behind-base regression coverage.
- [x] Pass the full-fleet candidate check for all seven consumers on 0.19.11.
- [x] Pass the canonical source gates for 0.19.11.
