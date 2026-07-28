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
- Current package: 7 / 11 — 07-25-user-scope-toolchain-caches (not started)
- Last verified commit: 9eaf2ee2
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
| 5 | `07-28-route-housekeeping-by-pr-lifecycle-state` | done | 865d169 | test_housekeeping (42, +3 lifecycle routes) + test_housekeeping_result (15) + pr_eligibility + generated_parity + pack_drift + ruff + mypy + shellcheck green | self-review clean; single resolved identity, sole merge owner preserved, eligibility null on merged route |
| 6 | `07-28-enforce-pre-archive-acceptance-readiness` | done | 9eaf2ee2 | test_bookkeeping_validator (44, +8) + test_review_preflight + test_sdlc_commands + test_completion_lifecycle + test_generated_parity + test_pack_drift green; ruff clean | self-review clean; completion-ready-gated, read-only, no false positives (handoff prose / non-canonical / fenced boxes) |
| 7 | `07-25-user-scope-toolchain-caches` | pending | — | — | — |
| 8 | `07-25-fix-work-loop-lock-race` | pending | — | — | — |
| 9 | `07-25-backlog-selector-blocked-markers` | pending | — | — | — |
| 10 | `07-24-track-clean-recovery-artifacts` | pending | — | — | — |
| 11 | `07-28-standardize-environment-blocked-recovery-evidence` | pending | — | — | — |

## Last checkpoint

Package 6 (`07-28-enforce-pre-archive-acceptance-readiness`) complete at commit
`9eaf2ee2`. Extended the existing read-only `pre-archive` bookkeeping validator
in `sd-ai-command-pack-review-preflight.mjs` (no second validator) to evaluate
the canonical acceptance section from the Package 1 lifecycle contract. An
unchecked required item in the single `## Acceptance Criteria` section fails
closed with `pre_archive_acceptance_incomplete` before any Trellis mutation;
malformed/duplicate sections and checkbox-shaped `## Post-archive handoff`
bullets fail with `pre_archive_acceptance_malformed`. Prose handoff bullets,
unchecked boxes outside the canonical section, and fenced-code checkbox examples
never produce false failures (fence mask + canonical-section scoping). The
evaluation is gated on the completion-ready pre-archive path only, so planning
finalization and post-archive completion-successor validation keep their
semantics; it never rewrites a PRD, checks a box, or mutates metadata/pointers/
branches/journals, and acceptance readiness stays bookkeeping evidence, not
merge authorization. Package 6's own `design.md`/`implement.md` are intentionally
empty: the umbrella's design of record plus the complete child `prd.md` drive
the work, so no active-task planning artifact was created or materially updated
(the planning adversarial-review rule does not fire for these script/doc/test
edits). Template edited first; root mirror and `SD_AI_COMMAND_PACK.md` kept
byte-identical via `make sync`; generated surfaces unchanged (94). Checks:
`test_bookkeeping_validator` (44, +8 acceptance-readiness cases) +
`test_review_preflight` + `test_sdlc_commands` + `test_completion_lifecycle` +
`test_generated_parity` + `test_pack_drift` green; `ruff` clean. (`make check`
mypy/shellcheck scopes exclude the edited `.mjs`; the candidate-ledger
`payloadDigest` stays stale until release preparation, by design.)

Package 5 (`07-28-route-housekeeping-by-pr-lifecycle-state`) complete at commit
`865d169`. Replaced the unconditional merge-then-cleanup pair in the housekeeping
script with `route_branch_pr_lifecycle`, which resolves one bounded PR identity
and lifecycle state before choosing work. OPEN keeps the exact-head eligibility
gate, re-resolves after the merge attempt, and cleans up only if the merge
landed (else one `pull_request_open` anomaly, branch untouched); MERGED skips
eligibility and cleans up from the resolved identity (no finish-work receipt
required, `eligibility` stays null); CLOSED stops with `pull_request_not_merged`;
an unresolvable identity or unexpected state fails closed with a bounded anomaly,
and the new `pull_request_state_indeterminate` code was added to the result
composer's indeterminate set so the composed outcome is `indeterminate`, not
`blocked`. The exact-head cleanup body was extracted into `cleanup_merged_branch`
(the working-tree gate now lives there, inspected once per run). Housekeeping
remains the sole merge/cleanup owner. Template edited first; root mirror, doc
(`SD_AI_COMMAND_PACK.md`), and composer kept byte-identical via `make sync`.
Checks: `test_housekeeping` (42, +3 lifecycle-route tests, 2 message updates, 1
source-order update) + `test_housekeeping_result` (15) + `test_pr_eligibility`
+ `test_generated_parity` + `test_pack_drift` green; `ruff`, `mypy` (result
composer), and `shellcheck -S warning` clean.

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

Next: implement work package 7,
`07-25-user-scope-toolchain-caches`.
