# Stabilization progress

This file is the durable cross-session checkpoint for the single-merge
stabilization campaign. Update it only after a focused package commit and its
local checks/review have completed.

## Campaign

- Branch: codex/stabilize-self-hosted-delivery-lifecycle (from clean main 0f3323b)
- Planning baseline: 6b8a8f8 (first bounded commit; planning + handoff surface)
- Lifecycle activation: d79ba90 — umbrella + all 11 work packages set to
  in_progress and assigned the shared branch; investigation and rollout tasks
  remain planning.
- Current package: 2 / 11 — 07-28-decide-housekeeping-result-schema-compatibility (not started)
- Last verified commit: 2616735
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
| 1 | `07-28-clarify-completion-housekeeping-obligations` | done | 2616735 | unittest (completion_lifecycle 9, sdlc_commands, help_command, surface_generation, generated_parity, pack_drift, install) + ruff + mypy green | self-review clean; candidate-ledger digest deferred to cumulative integration |
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

Package 1 (`07-28-clarify-completion-housekeeping-obligations`) complete at
commit `2616735`. Added the shared `sd-help/references/completion-lifecycle.md`
contract (registered in `SHARED_SKILL_REFERENCES`), a matching
`## Completion boundary` section in sd-finish-work, sd-housekeeping,
sd-review-pr, and sd-ship, an installed-guide pointer, and
`tests/test_completion_lifecycle.py` (9 tests). Regenerated command surfaces,
both manifests, and root mirrors via `make generate` + `make sync`.

Checks: `unittest` on completion_lifecycle (9) + sdlc_commands + help_command +
surface_generation + generated_parity + pack_drift + install all green; ruff
and mypy clean. Local review: self-review of the 16-file diff, scope matches the
intended set, no second merge authority introduced. Deferred, by design, to
cumulative integration: `candidate-validation.json` `payloadDigest` (refreshed
by release preparation), so `make generate` surface-check still reports the
candidate-ledger digest as stale until then.

Next: implement work package 2,
`07-28-decide-housekeeping-result-schema-compatibility`.
