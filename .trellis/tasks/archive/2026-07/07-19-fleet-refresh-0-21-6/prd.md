# Roll out SD pack 0.23.11 to the consumer fleet

## Goal

Refresh all configured consumers from their current installed version to release
0.23.11 through the canonical fleet preflight, sequential PR, review, merge,
provenance, and audit process.

## Confirmed Facts

- Source release `v0.23.1` was created from merged PR #173 after the complete
  `main` workflow passed. Canary PR #126 then found two source-owned work-loop
  evidence defects, so the fleet target advanced to corrective release
  `v0.23.2`. The fresh canary review then found an unsanitized terminal status
  snapshot boundary, advancing the target to `v0.23.3`. After three consumers
  merged, rwbp-website PR #140 found unsanitized active snapshot fields, so the
  fleet target advanced to `v0.23.4`. SE PR #10 then found that a phase-only
  reconciliation could clear unresolved contradiction context, advancing the
  target to `v0.23.5`. Coordinator PR #128 then found that unrelated partial
  evidence could still clear the same checkpoint, advancing the fleet target
  to `v0.23.6`. Mezmo Benchmark PR #359 then surfaced three remaining
  source-owned contract defects in invalid status diagnostics, head-only
  evidence after local branch deletion, and transition CLI argument exposure,
  advancing the target to `v0.23.7`. Coordinator PR #129 then merged that
  pre-release payload before the source PR was merged or `v0.23.7` existed.
  Loadsmith PR #100 found that persisted-state validation still accepted a
  blank recorded branch, which a head-only evidence update could preserve.
  Because the `0.23.7` identity was already consumed, the source and fleet
  target advanced to `v0.23.8` rather than rewriting that version. During the
  corrective rollout, mezmo_benchmark PR #359 found that optional strings in
  the dynamically loaded run snapshot could sanitize to empty without
  invalidating the boundary, advancing the target again to `v0.23.9`. The
  refreshed Mezmo review then found that transition task and base-branch
  values could sanitize to blank before failing later with a generic malformed
  state error, advancing the target to `v0.23.10`. Anomaly Metric Creator PR
  #257 then found that the canonical work-loop status snapshot still omitted
  recorded base-branch and last-shipped-SHA evidence, advancing the final
  target to `v0.23.11`.
- Disposable candidate validation passed for all seven configured consumers
  for the corrective `0.23.11` payload, and the committed ledger matches the
  current payload and fleet manifest.
- `docs/FLEET_ROLLOUT.md` owns the rollout procedure and
  `docs/fleet/consumers.json` owns fleet membership, platform selection, and
  priority order.
- This is a cross-repository operation. Start it through the explicit
  `sd-fleet-refresh` workflow rather than as an implicit side effect of a
  repo-local backlog iteration.
- The 2026-07-19 `0.23.7` preflight found all seven consumers available.
  Coordinator reached the pre-release payload through PR #129; Loadsmith PR
  #100 was merged at `0.23.8`, and mezmo_benchmark PR #359 carried the
  corrective refresh through `0.23.10`. The final `0.23.11` pass completed all
  seven consumers through green, comment-clean rollout PRs and post-merge
  audits.

## Requirements

- Run the source fleet preflight before mutating a consumer and use the exact
  paths, commands, versions, and order it reports.
- Process consumers sequentially, starting with the fast canaries and keeping
  anomaly-metric-creator last.
- Require a clean consumer checkout before installation. Do not stash, reset,
  clean, clone, or overwrite unrelated work to force a refresh.
- Install release `0.23.11` with the consumer's configured platforms, then run
  install audit, provenance verification, and the repository-owned validation
  gate before opening a PR.
- Commit only installer-managed payload, receipts, provenance, and managed
  blocks. Keep consumer product changes out of rollout PRs.
- Merge only green, comment-clean rollout PRs through each repository's normal
  lifecycle owner, then verify the consumer is clean on its default branch.
- Stop the fleet for a released-pack correctness, security, install/audit, or
  compatibility defect; record unrelated findings as separate follow-ups.
- Report every consumer's before version and final outcome, including a clear
  reason for each skip or intentionally open PR.

## Acceptance Criteria

- [x] rwbp-coordinator is installed at `0.23.11` and passes post-merge audit.
- [x] loadsmith is installed at `0.23.11` and passes post-merge audit.
- [x] hoa-manager is installed at `0.23.11` and passes post-merge audit.
- [x] rwbp-website is installed at `0.23.11` and passes post-merge audit.
- [x] mezmo_benchmark is installed at `0.23.11` and passes post-merge audit.
- [x] se-ai-command-pack is installed at `0.23.11` and passes post-merge audit.
- [x] anomaly-metric-creator is installed at `0.23.11` and passes post-merge
      audit.
- [x] Every mutated consumer passed its repository-owned validation before PR
      creation and has no unresolved rollout review thread at merge.
- [x] No rollout PR remains open unless the final task results explicitly
      identify its repository, state, and blocker.
- [x] The final results include a seven-consumer before/after table and confirm
      the source fleet preflight reports every available consumer at target.

## Final Results

Release `v0.23.11` resolves to source commit
`b8e66b3c0ae437d5e2efb4fb55bb34fd388fef2d`. Source PR #182, the main CI
workflow, auto-tag workflow, and seven-consumer disposable candidate validation
all passed before the final fleet pass.

| Priority | Consumer | Before final pass | Rollout PR | Final audit |
| --- | --- | --- | --- | --- |
| P10 | `platypeeps/rwbp-coordinator` | `0.23.9` | #132 merged | `0.23.11`; preserved 1, unchanged 149 |
| P20 | `platypeeps/loadsmith` | `0.23.9` | #102 merged | `0.23.11`; preserved 1, unchanged 149 |
| P30 | `platypeeps/hoa-manager` | `0.23.9` | #127 merged | `0.23.11`; preserved 1, unchanged 149 |
| P40 | `platypeeps/rwbp-website` | `0.23.9` | #146 merged | `0.23.11`; preserved 1, unchanged 149 |
| P50 | `answerbook/mezmo_benchmark` | `0.23.10` | #360 merged | `0.23.11`; preserved 2, unchanged 148 |
| P60 | `platypeeps/se-ai-command-pack` | `0.23.10` | #11 merged | `0.23.11`; unchanged 150 |
| P90 | `platypeeps/anomaly-metric-creator` | `0.23.11` after canary PR #257 | #257 merged | `0.23.11`; preserved 2, unchanged 148 |

Each rollout PR passed its repository-owned validation and GitHub checks,
received a current-head Copilot review with zero comments, had no unresolved
review threads, and merged through the consumer housekeeping gate. The final
source fleet preflight reported all seven consumers `at-target`; no rollout PR
or rollout branch remains open.

## Out Of Scope

- Consumer product changes, dependency upgrades, and unrelated maintenance.
- Modifying a dirty or missing checkout to make it eligible for rollout.
- Retagging or rewriting releases `v0.23.1` through `v0.23.10`.
- Creating a pull request in the upstream Trellis repository.

## Notes

- Resume with `sd-fleet-refresh` after explicit operator selection of this
  cross-repository task.
- The directory slug retains `0-21-6` because this task was retargeted in place
  rather than duplicated; `task.json` and this PRD define the current target.
