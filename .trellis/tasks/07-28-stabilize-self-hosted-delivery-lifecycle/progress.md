# Stabilization progress

This file is the durable cross-session checkpoint for the single-merge
stabilization campaign. Update it only after a focused package commit and its
local checks/review have completed.

## Campaign

- Branch: codex/stabilize-self-hosted-delivery-lifecycle (from clean main 0f3323b)
- Planning baseline: 6b8a8f8 (first bounded commit; planning + handoff surface)
- Lifecycle activation: umbrella + all 11 work packages set to in_progress and
  assigned the shared branch; investigation and rollout tasks remain planning.
- Current package: 1 / 11 — 07-28-clarify-completion-housekeeping-obligations (not started)
- Last verified commit: 6b8a8f8
- Cumulative matrix: not run
- Pull request: none
- Finalization receipt: none
- Pre-start separation: resolved. Unrelated task
  `07-28-bound-review-learnings-unsafe-path-diagnostics` is preserved at commit
  `22aa265` on local branch
  `codex/plan-bound-review-learnings-unsafe-path-diagnostics` and is absent
  from the umbrella working tree.

## Work packages

| Order | Task | State | Commit | Focused checks | Local review |
| ---: | --- | --- | --- | --- | --- |
| 1 | `07-28-clarify-completion-housekeeping-obligations` | pending | — | — | — |
| 2 | `07-28-decide-housekeeping-result-schema-compatibility` | pending | — | — | — |
| 3 | `07-24-support-planning-only-pr-finalization` | pending | — | — | — |
| 4 | `07-28-validate-finish-work-receipt-path` | pending | — | — | — |
| 5 | `07-28-route-housekeeping-by-pr-lifecycle-state` | pending | — | — | — |
| 6 | `07-28-enforce-pre-archive-acceptance-readiness` | pending | — | — | — |
| 7 | `07-25-user-scope-toolchain-caches` | pending | — | — | — |
| 8 | `07-25-fix-work-loop-lock-race` | pending | — | — | — |
| 9 | `07-25-backlog-selector-blocked-markers` | pending | — | — | — |
| 10 | `07-24-track-clean-recovery-artifacts` | pending | — | — | — |
| 11 | `07-28-standardize-environment-blocked-recovery-evidence` | pending | — | — | — |

## Last checkpoint

Lifecycle activated. Branch `codex/stabilize-self-hosted-delivery-lifecycle`
created from clean `main` (`0f3323b`); planning baseline committed at `6b8a8f8`.
Umbrella is the active session task; all eleven work packages are `in_progress`
on the shared branch. Investigation and rollout tasks remain `planning`.

Next: implement work package 1,
`07-28-clarify-completion-housekeeping-obligations`.
