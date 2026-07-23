# Streamline and harden SD skill workflows

## Goal

Coordinate the complete remediation of the 2026-07-22 canonical skill review.
Reduce overlapping commands, hidden mutations, prompt-owned state machines,
duplicated gates, unnecessary provider spend, stale documentation, and unsafe
write or checkout-execution boundaries without weakening the delivery lifecycle.

This parent owns the source finding ledger, task boundaries, cross-child
dependencies, and final integration review. It has no direct implementation
scope; each deliverable is implemented and verified through its owning child.

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
| F17 | P1/P2 | Existing tests emphasize parity and pinned prose more than lifecycle scenarios and typed state transitions. | Every owning child; integration coverage is checked by this parent. |

F02 deliberately has two owners with non-overlapping responsibilities:
`integrate-routed-review-backends` produces exact-head review evidence and
re-enters review after a material new head, while
`centralize-pr-eligibility-gates` consumes exact-head evidence and decides
merge eligibility without mutating the PR.

## Requirements

- R1: Preserve the finding ledger as the authoritative, lossless source map.
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
- R5: Do not add legacy aliases or compatibility readers for surfaces selected
  for retirement. Provenance-aware refresh remains the removal mechanism.
- R6: Keep irreversible or higher-cost actions explicit. Do not introduce
  questions for actions already authorized by a command invocation and its
  documented safety boundary.
- R7: Every child adds behavioral tests for its risk boundary, not only
  generated parity or prose-string assertions.
- R8: No child may weaken exact-head validation, unresolved-thread polling,
  merge authority, no-touch ownership, checkout trust, or data/cost disclosure.
- R9: The parent closes only after all children are archived or have a recorded
  disposition accepted during final integration review.

## Child Task Map

- `07-22-evaluate-sd-github-review-consolidation`
  - owns the repository-boundary decision;
  - contains `07-22-integrate-routed-review-backends`, which owns F01, F02's
    review-production side, F05, F06, F09, and F10.
- `07-22-centralize-pr-eligibility-gates` owns F02's merge-consumption side and
  F03.
- `07-22-enforce-untrusted-checkout-preflight` owns F04.
- `07-22-determinize-fleet-refresh-orchestration` owns F07.
- `07-22-streamline-backlog-design-workflows` owns F08 and F11.
- `07-22-harden-review-learnings-boundaries` owns F12.
- `07-22-add-command-surface-drift-lint` owns F13.
- `07-22-add-portable-structured-questions` owns F14.
- `07-22-optimize-audit-charter-routing` owns F15.
- `07-22-structure-skill-runtime-contracts` owns F16.
- Every child owns its F17 scenario coverage; this parent owns the final
  cross-child lifecycle matrix.
- External dependency `platypeeps/sd-github-review` task
  `07-22-publish-routed-review-receipt-contract` owns noninteractive routing,
  trusted GitHub-only successor comparison, and a distinct durable receipt for
  every head. It may route a verified bookkeeping-only successor to `none`
  within policy; no command-pack child may create a competing exemption.

## Acceptance Criteria

- [ ] Every F01-F17 row has an active or archived task and a testable acceptance
  mapping; no finding is left only in review prose.
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
- [ ] Focused tests, `make sync`, `make check`, install audit, and applicable
  fleet validation pass after the final child lands.
- [ ] A final integration review proves that the streamlined workflow has one
  merge authority, one exact-head review lifecycle, no silent paid-provider
  escalation, and no hidden mutation in deterministic checks.

## Out Of Scope

- Implementing any child directly from this parent task.
- Merging the command pack and `sd-github-review` repositories.
- Combining distinct Trellis lifecycle commands solely because their prose is
  similar.
- Opening an upstream Trellis pull request without separate explicit approval.
