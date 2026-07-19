# Roll out SD pack 0.21.3 to the consumer fleet

## Goal

Refresh every stale consumer to the corrective sd-ai-command-pack 0.21.3 payload
through reviewable, sequential pull requests. Finish with each available
consumer clean on its default branch, provenance and audit confirming 0.21.3,
and no unresolved rollout PRs.

## Confirmed Facts

- Release 0.21.0 was merged and tagged after PR #162.
- Four consumers reached 0.21.0 before mezmo_benchmark's full pytest suite
  exposed a pack-owned candidate-file UTF-8 policy defect.
- The rollout stopped before publishing mezmo_benchmark, as required by R9;
  0.21.3 is the corrective fleet target.
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
  installed provenance reports 0.21.3, and expected-platform audit passes.
- R9: Stop the fleet for a released-pack correctness, security, install/audit,
  or compatibility defect. Record low-risk or unrelated findings as follow-up
  work instead of forcing a patch release.
- R10: Report every consumer's before version and final outcome with an
  explicit reason for every skip.

## Acceptance Criteria

- [ ] rwbp-coordinator is at 0.21.3 or has an explicit skip reason.
- [ ] loadsmith is at 0.21.3 or has an explicit skip reason.
- [ ] hoa-manager is at 0.21.3 or has an explicit skip reason.
- [ ] rwbp-website is at 0.21.3 or has an explicit skip reason.
- [ ] mezmo_benchmark is at 0.21.3 or has an explicit skip reason.
- [ ] se-ai-command-pack is at 0.21.3 or has an explicit skip reason.
- [ ] anomaly-metric-creator is at 0.21.3 or has an explicit skip reason.
- [ ] Every refreshed consumer passes install audit and its repository-owned
  validation before PR creation.
- [ ] Every merged consumer passes post-merge provenance and audit checks and
  ends clean on its default branch.
- [ ] No rollout PR remains open unless the final report explicitly records it.
- [ ] The final fleet table and target-version summary are complete.

## Out Of Scope

- Consumer product changes, dependency upgrades, and unrelated maintenance.
- Cloning missing consumer repositories or modifying dirty worktrees.
- Retagging earlier releases; the corrective payload ships as 0.21.3.
- Opening a pull request in the upstream Trellis repository.
