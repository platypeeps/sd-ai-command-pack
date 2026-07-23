# Validate SD workflow program integration

## Goal

Prove that the completed F01-F17 remediation children operate as one coherent,
cost-aware, fail-closed delivery workflow. Run the coupled cross-child lifecycle
matrix, map every finding to landed implementation and validation evidence, and
publish the closure evidence consumed by the parent program task.

## Confirmed Evidence

- The parent `07-22-streamline-sd-skill-workflows` owns the F01-F17 ledger,
  task boundaries, completion contract, and program closure decision.
- Foundation and workflow changes are intentionally implemented in separate
  children so each remains independently reviewable and reversible.
- Cross-child failures can appear only after those contracts are combined:
  exact-head review evidence, eligibility, checkout trust, provider routing,
  structured interaction, orchestration, generated adapters, and drift lint
  all meet at the final delivery lifecycle.
- The user approved one integration task for the 11 coupled scenarios rather
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

## Requirements

- R1: Produce an evidence map from every F01-F17 finding and S01-S11 scenario
  to its owning task, landed PR or commit, focused test, and observed result.
- R2: Exercise the matrix against the final generated command surface and
  installed payload, not isolated source-only helpers.
- R3: Verify the command pack and `sd-github-review` use the same successor-head,
  noninteractive-router, no-checkout, idempotency, and bookkeeping-only `none`
  semantics.
- R4: Run focused scenario tests, `make sync`, `make check`, install
  `--check --json`, and applicable fleet candidate validation on the final
  integrated head.
- R5: Verify live catalogs, specs, docs, manifests, generated adapters, and
  installation receipts contain no retired surface outside explicit historical
  or migration fixtures.
- R6: Route any discovered implementation defect back to its owning child or a
  separately approved follow-up. Do not absorb unrelated corrective work into
  this integration gate.
- R7: Give the parent a concise closure record containing dependency states,
  evidence-map location, validation results, accepted follow-ups, and the pack
  version or commit that passed.

## Acceptance Criteria

- [ ] Every prerequisite has terminal evidence or an explicit parent-approved
  disposition; no tree-position inference is used.
- [ ] F01-F17 each map to an owner, landed identity, behavioral validation, and
  final result.
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
- [ ] I1-I6 hold across the combined lifecycle, including generated adapters
  and unavailable paths.
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
