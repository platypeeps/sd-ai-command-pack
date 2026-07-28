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
- Current package: 5 / 11 — 07-28-route-housekeeping-by-pr-lifecycle-state (not started)
- Last verified commit: 6f873db
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
| 2 | `07-28-decide-housekeeping-result-schema-compatibility` | done | 78b7b05 | test_housekeeping_result (15, +3 migration) + generated_parity + pack_drift + ruff + mypy green | self-review clean; explicit no-alias migration, reconciled with parent R6 |
| 3 | `07-24-support-planning-only-pr-finalization` | done (validated) | 7bf587a | finalization lifecycle battery 212 tests green (bookkeeping_validator, review_preflight, pr_eligibility, housekeeping, housekeeping_result, review_stage) | integration proof; feature already in origin/main, not re-implemented |
| 4 | `07-28-validate-finish-work-receipt-path` | done | 6f873db | test_housekeeping (39, +8 receipt-path) + generated_parity + pack_drift (56) + ruff + shellcheck green | self-review clean; early fail-fast before side effects, downstream eligibility unchanged |
| 5 | `07-28-route-housekeeping-by-pr-lifecycle-state` | pending | — | — | — |
| 6 | `07-28-enforce-pre-archive-acceptance-readiness` | pending | — | — | — |
| 7 | `07-25-user-scope-toolchain-caches` | pending | — | — | — |
| 8 | `07-25-fix-work-loop-lock-race` | pending | — | — | — |
| 9 | `07-25-backlog-selector-blocked-markers` | pending | — | — | — |
| 10 | `07-24-track-clean-recovery-artifacts` | pending | — | — | — |
| 11 | `07-28-standardize-environment-blocked-recovery-evidence` | pending | — | — | — |

## Last checkpoint

Package 4 (`07-28-validate-finish-work-receipt-path`) complete at commit
`6f873db`. Added `validate_finish_work_receipt` to the housekeeping script and
call it in `main()` right after the repository root is resolved (so relative
receipt paths resolve identically to downstream eligibility) and before cache
prep, Obsidian KB refresh, network access, or Git mutation. It requires an
existing readable regular file and rejects symlinks (checked first), missing
paths, directories, and other non-regular files with stable exit-code-2
diagnostics that never echo the path. `--self-test` (exits earlier) and
dependency-PR mode (empty receipt) are unaffected; downstream exact-head
eligibility revalidation is unchanged. Template edited first, root mirror kept
byte-identical via `make sync`. Checks: `test_housekeeping` (39, +8 receipt-path
cases) + `test_generated_parity` + `test_pack_drift` (56) green; `ruff` and
`shellcheck -S warning` clean. (`make check` mypy scope excludes `tests/`; the
only non-test edit is the shell script, covered by shellcheck.)

Package 3 (`07-24-support-planning-only-pr-finalization`) validated at commit
`7bf587a`. Its deterministic completion/planning finalization machinery
(`final-bundle` evaluator, finish-work mode gate, typed eligibility evidence,
retired `finishWorkHead`) already shipped to `origin/main` in prior releases and
is not re-implemented; the campaign records integration validation on the branch
head. Focused finalization lifecycle battery (`bookkeeping_validator`,
`review_preflight`, `pr_eligibility`, `housekeeping`, `housekeeping_result`,
`review_stage`) = 212 tests green. Deliverable is `validation.md`; dogfood and
program integration (H09/07-22) are satisfied/deferred by the umbrella itself.

Package 2 (`07-28-decide-housekeeping-result-schema-compatibility`) complete at
commit `78b7b05`. Consumer inventory proved no shipped/documented/tested consumer
reads `invocation.finishWorkHead`; decided an explicit documented in-major
migration (schema stays 1, no alias, no deprecation window), consistent with
parent task 07-24 R6. Recorded the decision in the task `decision.md`, documented
the retirement + verified replacement in the result composer docstring
(template + byte-identical root), and pinned it with 3 new tests (absence with
and without a receipt, verified head relocated to `identity.finishWork.headOid`,
restored `--finish-work-head` rejected). Checks: `test_housekeeping_result` (15),
`test_generated_parity` + `test_pack_drift` (56), ruff, mypy all green.

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

Next: implement work package 5,
`07-28-route-housekeeping-by-pr-lifecycle-state`.
