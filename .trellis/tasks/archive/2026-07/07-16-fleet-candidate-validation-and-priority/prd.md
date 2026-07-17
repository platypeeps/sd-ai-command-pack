# Harden pre-release fleet compatibility and canary rollout

## Goal

Catch pack-to-consumer incompatibilities before a version is tagged, then roll
validated releases through fast canaries before the slower fleet members. This
reduces avoidable patch-release chains without weakening consumer validation.

## Problem

The 0.15.x rollout exposed several defects one consumer at a time. Focused
regression tests now cover those exact defects, but the release process still
has no compatibility proof against the real fleet before tagging. Fleet order
also follows JSON array order, which currently starts with the slowest repo,
anomaly-metric-creator, instead of using quick consumers as canaries.

Consumer refresh PRs can also generate low-value review churn when reviewers
re-review vendored pack implementation instead of the consumer-owned install,
provenance, integration, and migration surfaces.

## Requirements

- R1: Give every fleet consumer an explicit, unique rollout priority and sort
  preflight/rollout results by that value rather than manifest array order.
- R2: Put the historically faster consumers first: rwbp-coordinator,
  loadsmith, and hoa-manager form the initial canary group;
  anomaly-metric-creator runs last.
- R3: Let every consumer declare one or more lightweight compatibility checks
  as argument arrays. Execute them directly without shell interpolation.
- R4: Add a source-only candidate validator that clones each consumer's origin
  into disposable storage, installs the current pack candidate, runs the
  install audit with the expected platforms, and runs the declared checks.
- R5: Never mutate, stash, reset, clean, or depend on the branch state of an
  active consumer worktree during candidate validation.
- R6: Continue after an individual candidate failure so one run reports the
  complete fleet result. Write the canonical validation ledger only after a
  full-fleet all-pass run.
- R7: Bind the ledger to the pack version, installable payload digest, fleet
  manifest digest, consumer set, and checked consumer base commits.
- R8: Reject a release version bump in local/CI release gates and automatic
  tagging when its committed candidate-validation ledger is absent, stale,
  partial, or contains failures.
- R9: Document the pre-release candidate sweep, fast-first rollout order,
  interruption threshold, and consumer review ownership.
- R10: Mid-rollout patch releases are reserved for correctness, security,
  install/audit, or compatibility blockers. Low-risk hardening, style, and
  unrelated consumer findings become follow-up work for a later release.
- R11: Consumer refresh review focuses on install/provenance integrity,
  platform wiring, secrets, documentation accuracy, and repo-owned migration
  changes. Pack-owned implementation is reviewed in this source repository.
- R12: Keep the candidate tooling and fleet command source-only; do not ship
  them into consumers.

## Acceptance Criteria

- [x] The fleet manifest uses a validated schema with explicit unique
      priorities, argv-based candidate checks, and bounded check timeouts.
- [x] Fleet preflight output is ordered coordinator, loadsmith, HOA, website,
      Mezmo, then AMC and exposes priority in text and JSON output.
- [x] Candidate validation uses temporary clones sourced from each local
      checkout's `origin`, installs/audits the current working candidate, runs
      all declared checks, and cleans temporary worktrees.
- [x] A selected-consumer diagnostic run cannot overwrite the canonical
      full-fleet ledger.
- [x] Ledger verification detects version, payload, fleet-manifest, consumer,
      and pass-status drift.
- [x] Release PR/full-check validation and the tag creator reject version
      changes without a valid ledger.
- [x] Source-only install audit coverage recognizes the new fleet helpers
      without allowing them in consumers.
- [x] Release and rollout docs describe candidate validation, the canary order,
      interruption policy, and review ownership.
- [x] Focused tests cover schema validation, priority ordering, command safety,
      temporary-clone behavior, ledger writes/checks, release-gate rejection,
      and source-only classification.
- [x] The checked-in candidate ledger validates the release payload produced by
      this change, and the repository's full check passes.

## Non-Goals

- Running full consumer CI suites before release; the candidate checks are
  intentionally lightweight compatibility probes.
- Automatically changing consumer product code from the pack checkout.
- Parallel consumer rollouts or bypassing consumer PR/housekeeping gates.
- Creating PRs in upstream Trellis.

## Evidence

- The previous rollout's observed green-check windows were approximately 1m27
  for coordinator, 2m50 for loadsmith, 4m59 for HOA, 6m37 for website, 6m53
  for Mezmo, and 18m47 for AMC.
- `load_fleet_consumers()` previously preserved incidental JSON order, while
  the manifest listed AMC first.
- The standard PR-body scope guidance already tells reviewers to focus copied
  tooling review on integration wiring, provenance, secrets, and docs. This
  task extends that ownership rule into the fleet release procedure rather
  than creating a competing review convention.
- A real disposable-clone sweep passed all six consumers for pack 0.15.6. The
  candidate checks completed in 5.2s (coordinator), 9.9s (loadsmith), 3.3s
  (HOA), 5.4s (website), 9.6s (Mezmo), and 3.1s (AMC).
- `make check` passed with 100% installer coverage, 94% candidate-validator
  coverage, 95% shared fleet-library coverage, lint, mypy, security audits,
  KB freshness, release drift checks, and full-check validation.
