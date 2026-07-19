# Roll out SD pack 0.21.4 to the consumer fleet

## Goal

Refresh every stale consumer to the corrective sd-ai-command-pack 0.21.4 payload
through reviewable, sequential pull requests. Finish with each available
consumer clean on its default branch, provenance and audit confirming 0.21.4,
and no unresolved rollout PRs.

## Confirmed Facts

- Release 0.21.0 was merged and tagged after PR #162.
- Four consumers reached 0.21.0 before mezmo_benchmark's full pytest suite
  exposed a pack-owned candidate-file UTF-8 policy defect. Subsequent canary
  review found chmod portability, status path validation, and read-only status
  import defects; each stopped the rollout and shipped through 0.21.1-0.21.4.
- Release 0.21.4 is the final corrective fleet target.
- `docs/FLEET_ROLLOUT.md` is the rollout procedure authority.
- `docs/fleet/consumers.json` defines seven consumers and their selected
  Claude, Gemini, GitHub, and OpenCode platforms.
- The authoritative order is rwbp-coordinator, loadsmith, hoa-manager,
  rwbp-website, mezmo_benchmark, se-ai-command-pack, then
  anomaly-metric-creator.
- The first three consumers are fast canaries; anomaly-metric-creator remains
  last because its validation cycle is materially slower.

## Requirements

- R1: Run source preflight before mutating any consumer and use its reported
  versions, paths, install commands, audit commands, and priority order.
- R2: Process consumers strictly one at a time. Start the next consumer only
  after the previous one is verified, intentionally left PR-open, or skipped.
- R3: Before mutation, require a clean consumer worktree. Never stash, reset,
  clean, clone, or install into a dirty or missing checkout.
- R4: Create a dedicated refresh branch from the consumer's current default
  branch, then run the exact preflight installer and expected-platform audit.
- R5: Run the consumer's documented full-check or repository-equivalent gate.
  Do not open a PR when installation, audit, or validation fails.
- R6: Commit only installer-managed payload, receipt, provenance, and managed
  blocks. Do not change consumer product code.
- R7: Push and open one refresh PR per stale consumer, wait for checks and
  reviews to settle, and merge only through the consumer's green,
  comment-clean housekeeping gate.
- R8: After merge, confirm the consumer is clean on its default branch, its
  installed provenance reports 0.21.4, and expected-platform audit passes.
- R9: Stop the fleet for a released-pack correctness, security, install/audit,
  or compatibility defect. Record low-risk or unrelated findings as follow-up
  work instead of forcing a patch release.
- R10: Report every consumer's before version and final outcome with an
  explicit reason for every skip.

## Acceptance Criteria

- [x] rwbp-coordinator is at 0.21.4.
- [x] loadsmith is at 0.21.4.
- [x] hoa-manager is at 0.21.4.
- [x] rwbp-website is at 0.21.4.
- [x] mezmo_benchmark is at 0.21.4.
- [x] se-ai-command-pack is at 0.21.4.
- [x] anomaly-metric-creator is at 0.21.4.
- [x] Every refreshed consumer passes install audit and its repository-owned
  validation before PR creation.
- [x] Every merged consumer passes post-merge provenance and audit checks and
  ends clean on its default branch.
- [x] No rollout PR remains open unless the final report explicitly records it.
- [x] The final fleet table and target-version summary are complete.

## Results

| Consumer | Before | Outcome |
| --- | --- | --- |
| rwbp-coordinator | 0.21.3 | 0.21.4, [PR #125](https://github.com/platypeeps/rwbp-coordinator/pull/125) merged |
| loadsmith | 0.21.3 | 0.21.4, [PR #96](https://github.com/platypeeps/loadsmith/pull/96) merged |
| hoa-manager | 0.21.3 | 0.21.4, [PR #121](https://github.com/platypeeps/hoa-manager/pull/121) merged |
| rwbp-website | 0.21.3 | 0.21.4, [PR #139](https://github.com/platypeeps/rwbp/pull/139) merged |
| mezmo_benchmark | 0.21.3 | 0.21.4, [PR #358](https://github.com/answerbook/mezmo_benchmark/pull/358) merged |
| se-ai-command-pack | 0.19.11 | 0.21.4, [PR #9](https://github.com/platypeeps/se-ai-command-pack/pull/9) merged |
| anomaly-metric-creator | 0.19.11 | 0.21.4, [PR #256](https://github.com/platypeeps/anomaly-metric-creator/pull/256) merged |

Final source preflight reported seven `at-target` consumers. The only new
follow-up is the planned P3 `status-snapshot-contract-validation` hardening
task recorded from AMC's non-blocking Copilot review.

## Out Of Scope

- Consumer product changes, dependency upgrades, and unrelated maintenance.
- Cloning missing consumer repositories or modifying dirty worktrees.
- Retagging earlier releases; the final corrective payload ships as 0.21.4.
- Opening a pull request in the upstream Trellis repository.
