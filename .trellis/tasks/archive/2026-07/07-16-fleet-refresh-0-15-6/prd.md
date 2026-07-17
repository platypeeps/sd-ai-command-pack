# Roll out sd-ai-command-pack 0.15.6 to the fleet

## Goal

Refresh every known consumer from sd-ai-command-pack 0.15.5 to the tagged
0.15.6 release through reviewable, sequential pull requests. Finish with each
available consumer clean on its default branch, provenance and audit confirming
0.15.6, and no unresolved rollout PRs.

## Confirmed Facts

- Release `v0.15.6` points to merged pack commit `20a459d`.
- The committed release candidate ledger is valid and all six disposable
  consumer checks passed before release.
- Preflight reports all six consumers at 0.15.5 and `refresh-needed`.
- The authoritative order is rwbp-coordinator, loadsmith, hoa-manager,
  rwbp-website, mezmo_benchmark, then anomaly-metric-creator.
- Each consumer has a local checkout at the path declared by the fleet
  manifest and selects Claude, Gemini, GitHub, and OpenCode payloads.

## Requirements

- R1: Process consumers strictly one at a time in manifest priority order.
- R2: Before mutation, require a clean consumer worktree on its current default
  branch. Never stash, reset, clean, or install into a dirty checkout.
- R3: Create a dedicated PR branch from the current remote default branch.
- R4: Run the exact preflight install command from the 0.15.6 pack checkout,
  followed by the exact audit command with all four expected platforms.
- R5: Run the consumer's documented full-check or repository-equivalent gate.
  Do not open a PR when install, audit, or validation fails.
- R6: Commit only installer-managed payload, receipt, provenance, and
  intentionally updated managed blocks. Do not change consumer product code.
- R7: Push and open one consumer refresh PR, wait for checks and review to
  settle, and merge only through that consumer's green, comment-clean
  housekeeping gate.
- R8: After merge, confirm the consumer is clean on its default branch, its
  installed provenance reports 0.15.6, and the expected-platform audit passes.
- R9: Stop the fleet for a released-pack correctness, security, install/audit,
  or compatibility defect. Record low-risk or unrelated consumer findings as
  follow-up work without forcing a patch release.
- R10: Report every consumer's before version and final outcome, including an
  explicit reason for any skip.

## Acceptance Criteria

- [x] rwbp-coordinator is at 0.15.6 or has an explicit skip reason.
- [x] loadsmith is at 0.15.6 or has an explicit skip reason.
- [x] hoa-manager is at 0.15.6 or has an explicit skip reason.
- [x] rwbp-website is at 0.15.6 or has an explicit skip reason.
- [x] mezmo_benchmark is at 0.15.6 or has an explicit skip reason.
- [x] anomaly-metric-creator is at 0.15.6 or has an explicit skip reason.
- [x] Every refreshed consumer passed install audit and its repository-owned
  validation before PR creation.
- [x] Every merged consumer passed post-merge provenance and audit checks and
  ended clean on its default branch.
- [x] No rollout PR remains open unless the final report explicitly records it.
- [x] The final fleet table and target-version summary are complete.

## Rollout Results

| Consumer | Before | Result | Evidence | Final |
| --- | --- | --- | --- | --- |
| `platypeeps/rwbp-coordinator` | `0.15.5` | `refreshed+merged` | [PR #112](https://github.com/platypeeps/rwbp-coordinator/pull/112), merged 2026-07-17T04:39:12Z | `0.15.6` |
| `platypeeps/loadsmith` | `0.15.5` | `refreshed+merged` | [PR #75](https://github.com/platypeeps/loadsmith/pull/75), merged 2026-07-17T04:49:11Z | `0.15.6` |
| `platypeeps/hoa-manager` | `0.15.5` | `refreshed+merged` | [PR #108](https://github.com/platypeeps/hoa-manager/pull/108), merged 2026-07-17T05:02:37Z | `0.15.6` |
| `platypeeps/rwbp-website` | `0.15.5` | `refreshed+merged` | [PR #124](https://github.com/platypeeps/rwbp-website/pull/124), merged 2026-07-17T05:14:18Z | `0.15.6` |
| `answerbook/mezmo_benchmark` | `0.15.5` | `refreshed+merged` | [PR #346](https://github.com/answerbook/mezmo_benchmark/pull/346), merged 2026-07-17T05:33:39Z | `0.15.6` |
| `platypeeps/anomaly-metric-creator` | `0.15.5` | `refreshed+merged` | [PR #245](https://github.com/platypeeps/anomaly-metric-creator/pull/245), merged 2026-07-17T06:04:05Z | `0.15.6` |

## Validation Evidence

- Every consumer passed the 134-target expected-platform audit before its PR
  and after merge; final fleet preflight reports all six consumers at target.
- Coordinator passed 52 script tests, 324 application unit tests, its build,
  and 50 Playwright tests.
- Loadsmith passed the installed full check, 456 Swift tests, and the app,
  package, signing, and notarization dry-run gates.
- HOA Manager passed 27 script tests, 665 application unit tests, 78
  integration tests, its build, and 9 Playwright tests.
- rwbp-website passed 365 unit tests, its production build, and 56 Playwright
  tests against a freshly seeded local database.
- mezmo_benchmark passed 4,222 tests with 8 documented skips and 86.79 percent
  branch coverage; its full remote Python 3.12 lane also passed.
- anomaly-metric-creator passed 1,603 tests with 2 opt-in smoke skips locally
  on Homebrew Python 3.14.6, and its remote Python 3.14 lane passed in 19m09s.

## Follow-Up

- AMC's repo-local `trellis-placeholders` pre-commit hook performs a cross-file
  workspace consistency check but does not set `require_serial: true`.
  `pre-commit --all-files` can therefore split `index.md` and its journal into
  separate batches and report a false missing-journal failure. Explicit-file,
  staged-commit, full-check, and CI paths pass, so this is a low-risk AMC-local
  hardening item rather than a 0.15.6 rollout blocker.
- HOA Manager, mezmo_benchmark, and anomaly-metric-creator briefly retained a
  stale remote-tracking rollout ref after their successful housekeeping merge;
  `git fetch --prune origin` removed each ref and all three ended clean.
- Mezmo Copilot raised one pack-source release-ledger concern that does not run
  in consumers because the gate returns unless the source-only installer,
  manifest, and templates tree all exist. The finding was rebutted with that
  execution-path evidence and its thread was resolved without a code change.

## Out Of Scope

- Consumer product changes, dependency upgrades, and unrelated maintenance.
- Cloning missing consumer repositories or modifying dirty worktrees.
- Retagging 0.15.6 or changing pack-owned implementation during a healthy
  rollout.
- Opening a pull request in the upstream Trellis repository.
