# Streamline and harden SD skill workflows

## Goal

Coordinate the complete remediation of the 2026-07-22 canonical skill review
and the accepted 2026-07-24 verification round.
Reduce overlapping commands, hidden mutations, prompt-owned state machines,
duplicated gates, unnecessary provider spend, stale documentation, unsafe
write or checkout-execution boundaries, and lifecycle states that cannot be
truthfully finalized without weakening the delivery lifecycle.

This parent owns the source finding ledgers, task boundaries, cross-child
completion contract, and final program-closure decision. It has no direct
implementation scope; each deliverable, including final integration execution
and evidence, is implemented and verified through its owning child.

## Confirmed Evidence

- The review covered all 22 canonical skills under
  `templates/.agents/skills`, critical helper scripts, the adapter generator,
  and relevant specifications. The inventory snapshot was
  `36230363acb367d8c70fe77e278da7b1ef3fd98d627d1372f7b604d78efdfe1c`.
- `templates/**` is authoritative for shipped payloads. Generated platform
  copies must remain synchronized through the normal pack workflow.
- The already-planned review cutover keeps `sd-ai-command-pack` and
  `sd-github-review` separate behind a versioned routed-review protocol and
  replaces the old review/check surface without compatibility aliases.
- Similarity signals among `sd-start`, `sd-continue`, `sd-finish-work`, and
  `sd-update-spec` reflect shared lifecycle vocabulary, not a justified merger.
  Those commands remain distinct.
- The 2026-07-24 review covered 21 current canonical skills at snapshot
  `8f5f11d25e3d193ac18576319c99d1552349f41888e26b7f7e239b0a2ea3126a`,
  confirmed all mapped copies matched canonical templates, and produced seven
  accepted findings. The user accepted every recommendation and required the
  resulting cutover to remove all obsolete code and features rather than retain
  compatibility structures.

## Finding Ledger And Ownership

| ID | Severity | Finding | Owning task |
| --- | --- | --- | --- |
| F01 | P1 | `sd-full-check` claims read-only behavior but can refresh `.obsidian-kb` by default. | `07-22-integrate-routed-review-backends` |
| F02 | P1 | Finish-work can create a new PR head after review, leaving review evidence head-ambiguous. | `07-22-integrate-routed-review-backends` plus `07-22-centralize-pr-eligibility-gates` |
| F03 | P1 | `sd-update-deps` re-describes merge eligibility even though housekeeping is the declared merge authority. | `07-22-centralize-pr-eligibility-gates` |
| F04 | P1 | The generated untrusted-PR warning covers only four commands although many adapters execute checkout-owned code. | `07-22-enforce-untrusted-checkout-preflight` |
| F05 | P1 | Split local/full/PR review paths can duplicate paid or network provider calls and cannot reuse exact-scope evidence. | `07-22-integrate-routed-review-backends` |
| F06 | P2 | `sd-review-pr` embeds transport, polling, GitHub API, remediation, commit, and push choreography in prompt prose. | `07-22-integrate-routed-review-backends` |
| F07 | P2 | `sd-fleet-refresh` leaves a high-consequence cross-repository state machine under prompt control. | `07-22-determinize-fleet-refresh-orchestration` |
| F08 | P2 | `sd-work-backlog` loads rare terminal-recovery mechanics on every normal run. | `07-22-streamline-backlog-design-workflows` |
| F09 | P2 | `sd-create-pr` performs review and exposes a private composition mode instead of publishing only. | `07-22-integrate-routed-review-backends` |
| F10 | P2 | `sd-watch-pr` overlaps review polling and can unexpectedly hand off to merge-capable housekeeping. | `07-22-integrate-routed-review-backends` |
| F11 | P2 | `sd-work-designs` is a redundant public preset for selectors already supported by `sd-work-backlog`. | `07-22-streamline-backlog-design-workflows` |
| F12 | P2 | `sd-review-learnings` can write outside the repository and lacks a complete mutation/safety/report contract. | `07-22-harden-review-learnings-boundaries` |
| F13 | P2 | Live specifications retain removed command identifiers such as `sd-review-local-all`. | `07-22-add-command-surface-drift-lint` |
| F14 | P2 | Canonical skills have no portable structured-question contract or generated `AskUserQuestion` guidance. | `07-22-add-portable-structured-questions` |
| F15 | P2 | Formal audits always load/run the broad charter set, even when some dimensions are inapplicable. | `07-22-optimize-audit-charter-routing` |
| F16 | P3 | Housekeeping and update-spec repeat deterministic output and rare extension mechanics in large prompts. | `07-22-structure-skill-runtime-contracts` |
| F17 | P1/P2 | Existing tests emphasize parity and pinned prose more than lifecycle scenarios and typed state transitions. | Every owning implementation child plus `07-22-validate-sd-workflow-program-integration`. |

F02 deliberately has two owners with non-overlapping responsibilities:
`integrate-routed-review-backends` produces exact-head review evidence and
re-enters review after a material new head, while
`centralize-pr-eligibility-gates` consumes exact-head evidence and decides
merge eligibility without mutating the PR.

### 2026-07-24 Verification Ledger

| ID | Review ID | Severity | Finding | Owning task |
| --- | --- | --- | --- | --- |
| G01 | `1.1.1` | P2 | Status and housekeeping still claim the removed `R-*` selector/Roadmap contract. | `07-24-align-status-selector-contract` |
| G02 | `1.4.1.1` | P1 | The read-only audit tooling charter instructs checkout-code execution through `make -n` and `--help`. | `07-24-harden-audit-read-only-methods` |
| G03 | `1.4.1.2` | P2 | Audit architecture inventory is not safe for valid hostile filenames. | `07-24-harden-audit-read-only-methods` |
| G04 | `1.6.2.1` | P2 | Fleet operator policy choices are not registered for native/fallback structured interaction. | `07-24-register-fleet-operator-policy-decision` |
| G05 | `1.1.2` | P1 | Split review/check paths duplicate cost, evidence, transport, and prompt context. | `07-24-implement-unified-routed-sd-review` plus `07-24-remove-retired-review-surfaces` |
| G06 | `1.4.6.1` | P1 | Full-check mutates generated knowledge despite its no-edit safety contract. | `07-24-implement-read-only-sd-check` plus `07-24-remove-retired-review-surfaces` |
| G07 | `1.5.2.1` | P2 | Standalone watch defaults into a merge-capable housekeeping handoff. | `07-24-simplify-review-shipping-composition` plus `07-24-remove-retired-review-surfaces` |

### 2026-07-24 Recent-Run Follow-up Ledger

| ID | Original finding | Priority | Finding | Owning task |
| --- | --- | --- | --- | --- |
| H01 | F-1 | P1 | Same-family state and boundary defects are discovered one remote round at a time instead of triggering a root-cause and sibling audit. | `07-24-converge-review-finding-families` |
| H02 | F-2 | P1 | New shipped files and identifiers repeatedly omit a manifest, source-only, generated, platform, documentation, or local/CI check surface. | `07-24-validate-shipped-surface-closure` |
| H03 | F-3 | P1 | Task/archive/journal validation can occur only after finish-work bookkeeping has been committed or pushed. | `07-24-validate-finish-work-bookkeeping-before-push` |
| H04 | F-4 | P2 | Exact-head bookkeeping successors rerun the complete CI matrix even when a strict cheap lane can validate them safely. | `07-24-add-bookkeeping-only-ci-fast-lane` |
| H05 | F-5 | P2 | Recovery stashes and linked worktrees can outlive their workflow without durable ownership or a provable cleanup condition. | `07-24-track-clean-recovery-artifacts` |
| H06 | F-6 | P2 | Cache-writing tools rely on callers remembering sandbox-specific environment overrides and can fail before the requested operation begins. | `07-24-standardize-sandbox-safe-tool-cache-routing` |
| H07 | F-7 | P2 | Ordinary review consumes a stale checked-in learning snapshot instead of a bounded current read-only family summary. | `07-24-feed-review-learnings-into-review-planning` |
| H08 | F-8 | P1 | Local-branch eligibility does not re-read the PR head after collecting checks and thread evidence. | `07-24-reread-pr-head-at-eligibility-completion` |
| H09 | PR #244 housekeeping | P1 | A reviewed planning-only PR cannot merge through housekeeping without either withholding required finish-work evidence or incorrectly archiving an unfinished planning task. | `07-24-support-planning-only-pr-finalization` |

## Requirements

- R1: Preserve the F01-F17, G01-G07, and H01-H09 finding ledgers as the authoritative,
  lossless source map.
  A finding may be split only when each task states its non-overlapping piece.
- R2: Keep all children independently startable, testable, reviewable, and
  archivable. Parent/child placement does not substitute for written
  dependencies in each child artifact.
- R3: Keep templates authoritative, regenerate all installed platform mirrors,
  refresh manifest/provenance/candidate data when applicable, and prohibit
  source-only edits to shipped payloads.
- R4: Prefer deterministic executables with versioned JSON input/output for
  state, identity, eligibility, and orchestration. Skills retain product
  judgment, safety policy, and interpretation.
- R5: Do not add or retain legacy aliases, wrappers, fallbacks, hidden modes,
  dead implementation branches, or compatibility readers for surfaces selected
  for retirement. Provenance-aware refresh remains the installed-copy removal
  mechanism; rollback is release-level reinstall.
- R6: Keep irreversible or higher-cost actions explicit. Do not introduce
  questions for actions already authorized by a command invocation and its
  documented safety boundary.
- R7: Every child adds behavioral tests for its risk boundary, not only
  generated parity or prose-string assertions.
- R8: No child may weaken exact-head validation, unresolved-thread polling,
  merge authority, no-touch ownership, checkout trust, or data/cost disclosure.
- R9: The parent closes only after all durable children, including
  `07-22-validate-sd-workflow-program-integration`, are archived or have a
  recorded disposition and the integration closure record is accepted.

## Child Task Map

- `07-22-evaluate-sd-github-review-consolidation`
  - owns the repository-boundary decision;
    - contains `07-22-integrate-routed-review-backends`, which owns F01, F02's
      review-production side, F05, F06, F09, F10, and G05-G07 through four
      implementation children.
- `07-22-centralize-pr-eligibility-gates` owns F02's merge-consumption side and
  F03.
- `07-23-recover-pr-232-main-conflict` owns the bounded integration and
  revalidation work required after the completed centralization child conflicted
  with concurrently merged pack release `0.32.2`; it adds no new F01-F17 scope.
- `07-22-enforce-untrusted-checkout-preflight` owns F04.
- `07-22-determinize-fleet-refresh-orchestration` owns F07.
- `07-22-streamline-backlog-design-workflows` owns F08 and F11.
- `07-22-harden-review-learnings-boundaries` owns F12.
- `07-25-add-multi-reviewer-learning-and-effectiveness-analysis` extends the
  now-bounded learning surface to all configured reviewers and adds separate
  read-only effectiveness analysis after trusted adjudication contracts land.
- `07-22-add-command-surface-drift-lint` owns F13.
- `07-22-add-portable-structured-questions` owns F14.
- `07-22-optimize-audit-charter-routing` owns F15.
- `07-22-structure-skill-runtime-contracts` owns F16.
- `07-23-expand-sd-status-selectable-inventory` introduced the selectable status
  inventory; `07-23-status-untracked-roadmap-items` subsequently removed the
  duplicate Roadmap/R surface. `07-24-align-status-selector-contract` owns the
  remaining live F/T contract drift as G01.
- `07-24-correct-sd-skill-contract-drift` coordinates G01-G04 through three
  independently implementable children.
- `07-24-add-bookkeeping-only-ci-fast-lane` owns the post-finish-work CI
  efficiency improvement: it preserves exact-head `CI Result` while replacing
  redundant full-suite execution for strictly validated Trellis-only successor
  heads with a fail-closed metadata lane. It does not own routed-review
  receipts or change any F01-F17/G01-G07 disposition.
- `07-24-converge-review-finding-families` owns H01 under the unified review
  controller; `07-24-feed-review-learnings-into-review-planning` owns H07 and
  supplies its family vocabulary/evidence.
- `07-24-validate-shipped-surface-closure` owns H02 under the read-only
  `sd-check` implementation and shares one graph with local and CI callers.
- `07-24-validate-finish-work-bookkeeping-before-push` owns H03 and publishes
  the canonical bookkeeping validator consumed by H04's CI lane.
- `07-24-track-clean-recovery-artifacts` owns H05 without adopting or deleting
  ambiguous user-created Git state.
- `07-24-standardize-sandbox-safe-tool-cache-routing` owns H06 across every
  pack subprocess path while preserving authentication/configuration state.
- `07-24-reread-pr-head-at-eligibility-completion` owns H08 as a focused fix to
  the shared eligibility evaluator before final integration.
- `07-24-support-planning-only-pr-finalization` owns H09. It adds a
  deterministically proven planning finalization that records the session and
  preserves planned task state, replaces the bare finish-work-head attestation
  with typed evidence, and leaves housekeeping as the sole merge owner.
- `07-28-route-housekeeping-by-pr-lifecycle-state` owns the cleanup-only
  lifecycle-ordering gap found by the recurring-instability investigation.
- `07-28-standardize-environment-blocked-recovery-evidence` owns the shared
  typed boundary/checkpoint contract for environmental recovery failures.
- Every implementation child owns its task-local F17 scenario coverage.
- `07-22-normalize-sd-workflow-program-task-topology` is the completed
  bookkeeping child that converted the program design and implementation plan
  into this task-native topology. It owns no ongoing remediation or integration
  work.
- `07-22-validate-sd-workflow-program-integration` owns shared invariants,
  S01-S21, the final cross-child lifecycle matrix, the
  F01-F17/G01-G07/H01-H09 evidence map, and the closure record consumed by this
  parent.
- External dependency `platypeeps/sd-github-review` task
  `07-22-publish-routed-review-receipt-contract` owns noninteractive routing,
  trusted GitHub-only successor comparison, and a distinct durable receipt for
  every head. It may route a verified bookkeeping-only successor to `none`
  within policy; no command-pack child may create a competing exemption.

## Coordination And Closure

- Start only the child that owns the next independently verifiable deliverable;
  never start this parent unless it gains separately approved direct scope.
- Treat written child dependencies as the execution order. Parent/child tree
  position alone never satisfies a prerequisite.
- Preserve template authority and generated parity in every implementation
  child instead of deferring regeneration to final integration.
- After the integration child publishes its closure record, record each child
  PR or commit and any accepted follow-up, archive completed children, and
  close this parent only when R9 and all acceptance criteria hold.
- Planning classification, 2026-07-28: coordination parent — PRD-only, deliberately.
  No `design.md` or `implement.md`. This task has no direct implementation scope (see
  the Goal and Out Of Scope), so a design doc would have to invent boundaries and
  contracts it does not own, and an implementation checklist would contradict "never
  start this parent". Technical design and execution order live in each owning child.
  If this parent is ever granted separately approved direct scope, reclassify then.

## Acceptance Criteria

- [ ] Every F01-F17, G01-G07, and H01-H09 row has an active or archived task and a testable
  acceptance mapping; no finding is left only in review prose.
- [ ] Each child contains explicit dependencies, out-of-scope boundaries,
  rollback/stop points where material, and behavioral validation commands.
- [ ] Review/check consolidation, exact-head merge gating, and structured
  interaction share compatible contracts rather than three parallel policies.
- [ ] The command-pack and `sd-github-review` task artifacts use the same
  successor-head, noninteractive-router, no-checkout, idempotency, and
  bookkeeping-only `none` semantics.
- [ ] Generated adapters fail closed for untrusted checkout execution and
  remain portable across hosts with and without structured-question tools.
- [ ] Prompt-owned state machines are replaced or reduced without losing
  recoverability, receipts, observability, or operator control.
- [ ] Retired commands and stale identifiers are absent from live surfaces and
  caught by automated drift validation.
- [ ] Obsolete code, environment/configuration readers, aliases, wrappers,
  fallbacks, hidden modes, provider dispatch, polling, and alternate merge paths
  are deleted; historical archives and non-executable retirement metadata are
  the only allowed references.
- [ ] Focused tests, `make sync`, `make check`, install audit, and applicable
  fleet validation pass after the final child lands.
- [ ] `07-22-validate-sd-workflow-program-integration` proves that the
  streamlined workflow has one merge authority, one exact-head review
  lifecycle, no silent paid-provider escalation, and no hidden mutation in
  deterministic checks, plus one orthogonal public command vocabulary with no
  legacy runtime, then publishes the evidence required for closure.

## Out Of Scope

- Implementing any child directly from this parent task.
- Merging the command pack and `sd-github-review` repositories.
- Combining distinct Trellis lifecycle commands solely because their prose is
  similar.
- Opening an upstream Trellis pull request without separate explicit approval.
