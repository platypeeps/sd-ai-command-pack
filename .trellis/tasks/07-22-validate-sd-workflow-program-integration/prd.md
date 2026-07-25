# Validate SD workflow program integration

## Goal

Prove that the completed F01-F17, G01-G07, and H01-H09 remediation children operate as one
coherent, cost-aware, fail-closed delivery workflow with no live legacy surface.
Run the coupled cross-child lifecycle matrix, map every finding to landed
implementation and validation evidence, and publish the closure evidence
consumed by the parent program task.

## Confirmed Evidence

- The parent `07-22-streamline-sd-skill-workflows` owns the F01-F17, G01-G07, and H01-H09 ledgers,
  task boundaries, completion contract, and program closure decision.
- Foundation and workflow changes are intentionally implemented in separate
  children so each remains independently reviewable and reversible.
- Cross-child failures can appear only after those contracts are combined:
  exact-head review evidence, eligibility, checkout trust, provider routing,
  structured interaction, orchestration, generated adapters, and drift lint
  all meet at the final delivery lifecycle.
- The user approved one integration task for the coupled scenarios rather
  than separate tasks that duplicate setup and prerequisites.

## Dependencies

This task must not start until these command-pack tasks are archived or have an
explicit parent-approved disposition:

- `07-22-evaluate-sd-github-review-consolidation`
- `07-22-integrate-routed-review-backends`
- `07-22-centralize-pr-eligibility-gates`
- `07-22-enforce-untrusted-checkout-preflight`
- `07-22-determinize-fleet-refresh-orchestration`
- `07-22-streamline-backlog-design-workflows`
- `07-22-harden-review-learnings-boundaries`
- `07-22-add-portable-structured-questions`
- `07-22-optimize-audit-charter-routing`
- `07-22-structure-skill-runtime-contracts`
- `07-22-add-command-surface-drift-lint`
- `07-24-correct-sd-skill-contract-drift`
- `07-24-harden-audit-read-only-methods`
- `07-24-align-status-selector-contract`
- `07-24-register-fleet-operator-policy-decision`
- `07-24-implement-read-only-sd-check`
- `07-24-implement-unified-routed-sd-review`
- `07-24-simplify-review-shipping-composition`
- `07-24-remove-retired-review-surfaces`
- `07-24-converge-review-finding-families`
- `07-24-validate-shipped-surface-closure`
- `07-24-validate-finish-work-bookkeeping-before-push`
- `07-24-add-bookkeeping-only-ci-fast-lane`
- `07-24-track-clean-recovery-artifacts`
- `07-24-standardize-sandbox-safe-tool-cache-routing`
- `07-24-feed-review-learnings-into-review-planning`
- `07-24-reread-pr-head-at-eligibility-completion`
- `07-24-support-planning-only-pr-finalization`

It also depends on `platypeeps/sd-github-review` task
`07-22-publish-routed-review-receipt-contract` publishing the reviewed v1
router contract and pilot evidence. Tree placement does not satisfy any of
these dependencies; the integration evidence must record their terminal state,
PR or commit identity, and accepted disposition.

## Shared Invariants

- I1: Evidence is bound to the current repository, declared scope, and full
  head identity.
- I2: Read-only commands do not refresh generated state or mutate Git, GitHub,
  tasks, providers, or external files.
- I3: Housekeeping remains the only merge mutation owner.
- I4: A skill may request bounded user judgment but cannot transfer an
  unbounded state machine to the user.
- I5: Host-specific tools are generated capability adaptations, not canonical
  runtime assumptions.
- I6: Failure, unavailable, stale, absent, and indeterminate outcomes remain
  distinct and fail closed wherever readiness cannot be proven.
- I7: Only the approved orthogonal command surface is live. Retired commands,
  aliases, wrappers, environment/configuration readers, hidden modes, duplicate
  provider dispatch, duplicate polling, and alternate merge paths are absent.

## Integration Scenarios

- S01: Finish-work creates a new head after review; the old evidence is not
  reused and the successor head re-enters the required review/eligibility path.
- S02: Remote routing is absent, invalid, unavailable, failed, or ambiguous;
  every state remains distinct and no unverified remote result is accepted.
- S03: Local providers are missing, paid or networked, or produce reusable
  exact-scope evidence; selection remains cost-aware and disclosed.
- S04: Checkout content originates from an untrusted fork; executable checkout
  paths fail closed before repository-provided instructions or code run.
- S05: Structured questions are available, unavailable, or noninteractive;
  behavior remains deterministic and preserves the same safety boundary.
- S06: Unresolved review threads span multiple GraphQL pages; pagination is
  complete and merge readiness remains blocked until every thread resolves.
- S07: Dependency PRs are safe, groupable, or unsafe; classification does not
  bypass exact-head eligibility or housekeeping ownership.
- S08: Fleet refresh stops, resumes, retries, and encounters no-touch
  ownership; receipts remain idempotent and resumable.
- S09: Audit fingerprints omit an optional charter in standard mode while
  exhaustive mode retains it and the mandatory core.
- S10: Retired identifiers appear in a live specification or adapter and are
  rejected by command-surface drift validation.
- S11: Review-learnings receives a relative, absolute, or symlink-escaping
  target; default behavior is read-only and out-of-repository writes require
  the explicit bounded contract.
- S12: A fresh install and an upgrade from the last pre-cut release expose only
  `sd-check`, `sd-review`, the publish-only `sd-create-pr`, explicit `sd-ship`,
  and housekeeping ownership. Old targets are removed provenance-safely, stale
  live references fail drift lint, and no runtime compatibility reader remains.
- S13: The same finding family appears on two remote-review rounds; automatic
  redispatch stops, a local sibling audit covers the complete invariant family,
  and related fixes publish as one verified batch.
- S14: A new source-only skill reference or platform adapter omits one required
  graph edge, or local and CI checker scopes drift; the shared closure validator
  fails locally with the exact missing relation.
- S15: A selected active task or final archive/journal bundle has invalid
  metadata, topology, placeholders, journal/index state, or whitespace; the
  canonical validator stops before archive or push at the owning boundary.
- S16: A verified bookkeeping-only successor receives a new exact-head
  aggregate CI result through the cheap lane, while mixed or ambiguous deltas
  retain the full matrix.
- S17: Recovery is interrupted after creating a stash or linked worktree; the
  receipt survives restart, status classifies it read-only, and cleanup removes
  only an exact no-loss artifact.
- S18: Home/user caches are unwritable; pack tools use the shared external
  cache environment while preserving GitHub/provider authentication and never
  writing into the repository.
- S19: Live review learning is current, stale, rate-limited, truncated, cached,
  or unavailable; planning consumes one bounded typed signal with limitations
  and never adds a tracked update or confidence from history alone.
- S20: The PR head advances while local branch evidence remains stable during
  eligibility evaluation; the final PR-head read returns retryable
  indeterminate and no stale eligible receipt reaches housekeeping.
- S21: A reviewed planning-only PR records one journal successor, produces
  independently verified typed planning-finalization evidence, merges through
  housekeeping, and preserves every planning task plus its active session
  pointer; mixed or ambiguous scope blocks without a false archive or bypass.

## Requirements

- R1: Produce an evidence map with one row for every F01-F17, G01-G07, and
  H01-H09 finding and one row for every S01-S21 scenario, linking each to its
  owning task, landed PR or commit, focused test, and observed result.
- R2: Exercise the matrix against the final generated command surface and
  installed payload, not isolated source-only helpers.
- R3: Verify the command pack and `sd-github-review` use the same successor-head,
  noninteractive-router, no-checkout, idempotency, and bookkeeping-only `none`
  semantics.
- R4: Run focused scenario tests, `make sync`, `make check`, install
  `--check --json`, and applicable fleet candidate validation on the final
  integrated head.
- R5: Verify live catalogs, specs, docs, manifests, generated adapters,
  installation receipts, parsers, configuration readers, scripts, tests, and
  help contain no retired surface. Only archived historical evidence and
  non-executable provenance retirement metadata may name old targets.
- R6: Route any discovered implementation defect back to its owning child or a
  separately approved follow-up. Do not absorb unrelated corrective work into
  this integration gate.
- R7: Give the parent a concise closure record containing dependency states,
  evidence-map location, validation results, accepted follow-ups, and the pack
  version or commit that passed.

## Acceptance Criteria

- [ ] Every prerequisite has terminal evidence or an explicit parent-approved
  disposition; no tree-position inference is used.
- [ ] F01-F17, G01-G07, and H01-H09 each map to an owner, landed identity, behavioral
  validation, and final result.
- [ ] S01 proves successor-head review evidence cannot be reused ambiguously.
- [ ] S02 proves all remote-router unavailable/failure states remain distinct
  and fail closed.
- [ ] S03 proves local provider selection is cost-aware, disclosed, and reuses
  only exact-scope evidence.
- [ ] S04 proves untrusted checkout execution is blocked before repository code
  or instructions run.
- [ ] S05 proves structured, fallback, and noninteractive interaction paths
  preserve one decision and safety contract.
- [ ] S06 proves all review-thread pages participate in merge readiness.
- [ ] S07 proves dependency grouping never bypasses eligibility or merge
  authority.
- [ ] S08 proves fleet stop/resume/retry/no-touch behavior is deterministic and
  idempotent.
- [ ] S09 proves standard audit routing may omit an optional charter while
  exhaustive mode and the mandatory core remain intact.
- [ ] S10 proves retired live identifiers fail deterministic drift validation.
- [ ] S11 proves review-learnings path containment and explicit external-write
  consent across relative, absolute, and symlink-escape cases.
- [ ] S12 proves fresh-install and upgrade behavior, exhaustive live-surface
  removal, no dormant readers, and one consistent command/authority vocabulary.
- [ ] S13 proves same-family review recurrence triggers a sibling audit,
  batched remediation, and bounded redispatch rather than an unbounded loop.
- [ ] S14 proves one shared graph catches incomplete shipped surfaces and
  local/CI scope drift before publication.
- [ ] S15 proves invalid finish-work bookkeeping is blocked before archive or
  push by the same rules later used in CI.
- [ ] S16 proves bookkeeping-only exact heads retain a required validated CI
  result without executing the expensive full matrix.
- [ ] S17 proves recovery artifacts have durable ownership, restart-safe status,
  and conservative no-loss cleanup.
- [ ] S18 proves sandbox-safe cache routing preserves authentication and keeps
  tool state outside the repository.
- [ ] S19 proves current review-learning consumption is bounded, read-only,
  limitation-aware, and does not create a per-PR documentation commit.
- [ ] S20 proves both local and PR final-head changes invalidate eligibility
  before housekeeping's mutation boundary.
- [ ] S21 proves planning-only finalization preserves planned task/session
  state, emits independently verified exact-head evidence, and composes with
  review, CI, eligibility, merge, and cleanup without a second authority.
- [ ] I1-I7 hold across the combined lifecycle, including generated adapters
  and unavailable paths.
- [ ] A repository-wide dead-code and identifier scan finds no callable retired
  skill, adapter, script, environment family, package hook, direct remote
  dispatcher, watch-to-merge path, alias, wrapper, fallback, or hidden mode.
- [ ] Focused tests, `make sync`, `make check`, install `--check --json`, and
  applicable fleet validation pass on the recorded final head.
- [ ] The parent receives a complete closure record and can decide whether to
  archive the program without consulting retired program-plan files.

## Out Of Scope

- Implementing or repairing the remediation children within this task.
- Weakening a failed scenario so the matrix can pass.
- Adding compatibility aliases for retired command surfaces.
- Merging the command-pack and `sd-github-review` repositories.
- Opening an upstream Trellis pull request without separate explicit approval.

## Reconciliation note (2026-07-25)

- The program gained children after this task's scope list was written: the
  `07-25-add-routed-review-operator-ux` subtree (3 children) and the
  `07-25-add-multi-reviewer-learning-and-effectiveness-analysis` subtree (2 children),
  both currently PARKED on external sd-github-review contracts. Before closure, either
  extend the evidence map and lifecycle matrix to include them, or record explicitly that
  program closure covers the pre-07-25 finding set (F01-F17/G01-G07/H01-H09) and the
  parked subtrees close separately. The owning parent's child map already lists them.
