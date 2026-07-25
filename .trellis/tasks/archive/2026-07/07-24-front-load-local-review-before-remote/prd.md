# Front-load local review before remote PR review

## Goal

Make Prism and Gito part of the normal PR lifecycle through a policy-routed, parallel local-review gate before the first remote review, with deduplicated remediation, exact-scope receipt reuse, selective reruns, and bookkeeping-only skips to reduce Copilot review churn.

## Confirmed Evidence

- The current `sd-create-pr` and `sd-review-pr` skills deliberately suppress
  Prism and Gito during the normal PR handoff. The command-owned helper forces
  `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0` and
  `SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0` before remote review
  (`templates/.agents/skills/sd-review-pr/SKILL.md:66` and
  `templates/scripts/sd-ai-command-pack-review-full-check.sh:64`).
- The separate local-review runner defaults to both Prism and Gito but invokes
  them sequentially (`scripts/sd-ai-command-pack-review-local.sh:704` and
  `scripts/sd-ai-command-pack-review-local.sh:753`). It has no reusable typed
  result for the PR lifecycle.
- The parent unified-review task already requires the ordered lifecycle
  `sd-check -> local review -> disposition -> remote routing`, exact-scope
  receipts, and bookkeeping-successor handling.
- Before this planning update, the parent routed-review requirement defined
  `local=auto` as one lowest-cost provider. This planning batch reconciles the
  parent PRD/design to the accepted provider-plan contract, including concurrent
  Prism and Gito coverage on the first substantive PR head.
- The review-convergence evidence records PR #237 requiring 22 remote-review
  rounds and 23 PR CI executions. The repeated findings were family-level
  boundary and state-machine concerns that should be searched for in one local
  batch before the first Copilot request.

## Dependencies And Boundaries

- Parent: `07-24-implement-unified-routed-sd-review`.
- Depends on `07-24-implement-read-only-sd-check` publishing the deterministic,
  read-only check contract.
- Depends on `07-24-feed-review-learnings-into-review-planning` publishing the
  bounded current finding-family evidence used to focus local review.
- Coordinates with `07-24-converge-review-finding-families`, which owns the
  repeated-family sibling-audit and redispatch stop after remote findings recur.
- Depends on the `sd-github-review` router capability and receipt contract
  required by the parent task. This task does not select or dispatch remote
  reviewers.
- This task owns local provider planning, concurrent execution, aggregation,
  exact-scope evidence, and the pre-remote gate inside `sd-review`.
- `07-24-simplify-review-shipping-composition` owns calling the reusable local
  stage before initial PR publication in `sd-ship`; this task publishes the
  contract and branch-to-PR reuse behavior that composition consumes.
- `07-24-remove-retired-review-surfaces` owns deletion of the legacy
  `sd-full-check`, `sd-review-local`, and `sd-review-pr` surfaces. This task adds
  no compatibility command or alias.

## Requirements

- R1: For PR-capable review, resolve the intended repository, base, head, and
  canonical diff, run the side-effect-free remote capability preflight when
  remote review is intended, and pass `sd-check` before invoking any local
  provider or requesting remote review.
- R2: Change `local=auto` from a single-provider choice to a deterministic,
  policy-selected provider set. The policy considers scope, change risk,
  data-handling constraints, capability, quality floor, configured cost, and
  prior finding families. Explicit `local=<provider>|all|none` remains
  authoritative.
- R3: The default first-head policy selects Prism and Gito for every substantive
  code PR and runs them concurrently. A versioned classifier may select one
  provider or a stable recorded skip for documentation-only, metadata-only,
  or verified bookkeeping-only changes. Repository policy may tighten this
  default but must not silently weaken a required local-review floor.
- R4: Treat source, tests, scripts, CI, security-sensitive configuration,
  contract/state-machine code, and source-owning generated templates as
  substantive. Classification must be deterministic, reported, and tested;
  an unknown or ambiguous classification uses the substantive policy.
- R5: Run selected providers in isolated processes with independent argv,
  timeout, cancellation, output, and artifact paths. Aggregate results only
  after all selected attempts reach a terminal state; one provider must not
  corrupt, mask, or overwrite another provider's evidence.
- R6: Normalize and deduplicate provider findings without erasing provider
  provenance. Verify candidates against code and specs, group related findings
  and known review families, and disposition them as one batch. Any outstanding
  actionable local finding blocks the first remote request.
- R7: With `fix=auto`, apply only clearly valid in-scope fixes, run `sd-check`,
  and create at most one focused local-review fix commit before first remote
  dispatch. Higher-risk, ambiguous, out-of-scope, destructive, architecture,
  dependency, product, or policy changes use the parent structured-decision
  contract.
- R8: Bind each provider attempt and aggregate local receipt to the exact
  repository, canonical local-review scope, base/head, content digest,
  provider/adapter versions, configuration digest, policy decision, and
  finding dispositions. Never reuse stale evidence after any relevant byte,
  head, provider, or policy change.
- R9: Permit a pre-publication branch review to satisfy the PR local stage only
  when both invocations resolve to the same canonical branch-delta scope and
  every exact-match field is unchanged. PR creation, by itself, must not cause
  duplicate provider billing; a changed merge base, head, diff, or configuration
  invalidates reuse.
- R10: After a code-changing local or remote fix, re-enter `sd-check` and create
  a new current-scope local receipt. The policy may select one relevant provider
  for a low-risk successor, but it must select both for cross-cutting/high-risk
  changes or a repeated finding family. A prior receipt may inform routing but
  cannot supply current-head confidence.
- R11: Feed the bounded current review-learning and family checklist into each
  selected local provider without sending raw historical comments, credentials,
  unrelated source, or unbounded session history.
- R12: Preserve normalized `unavailable`, `failed`, `cancelled`, `findings`,
  `clean`, and `skipped` outcomes per provider. Never silently substitute an
  unselected or more expensive provider. PR flow may continue to the remote
  router with explicit partial/zero local confidence only when parent and repo
  policy allow it.
- R13: Emit `skipped:bookkeeping-successor` only from the parent's exact
  finish-work/delta evidence. Documentation or metadata classification alone is
  not sufficient to mint a bookkeeping skip.
- R14: Request remote review only after the aggregate current-scope local stage
  is terminal and every actionable finding is fixed or explicitly dispositioned.
  The router remains the sole remote selection and dispatch owner.
- R15: Report the provider plan and reason, concurrent versus reused attempts,
  configured/observed cost and latency, findings before remote review,
  deduplicated families, fix-batch size, remote rounds, exact head, and material
  limitations. Do not claim equivalent quality or count hypothetical rounds as
  rounds avoided.
- R16: Keep raw provider output in ignored local artifacts and expose one
  bounded normalized report to the review controller. Do not add provider calls
  to `sd-check` or retain the legacy full-check environment-variable contract.

## Acceptance Criteria

- [ ] A substantive first-head PR fixture selects Prism and Gito, proves both
  start before either completes, isolates their artifacts, and prevents remote
  dispatch until both attempts and finding dispositions are terminal.
- [ ] Documentation-only, metadata-only, ambiguous, and substantive fixtures
  produce deterministic provider plans; ambiguous input fails into the
  substantive Prism-plus-Gito policy.
- [ ] Findings from both providers are provenance-preserving, deduplicated,
  verified, and applied in at most one focused pre-remote fix commit before
  `sd-check` and local re-entry.
- [ ] A clean pre-publication receipt is reused after PR creation only for an
  identical canonical base/head/diff/provider/configuration/policy tuple; each
  mismatch fixture causes a fresh local stage.
- [ ] Low-risk, high-risk, repeated-family, remote-fix, and bookkeeping-successor
  fixtures exercise the selective-rerun and exact-head rules without stale
  confidence or duplicate billing.
- [ ] One missing, failed, rate-limited, timed-out, or cancelled provider remains
  distinct from clean and follows the parent policy without silent substitution
  or direct Copilot fallback.
- [ ] Remote routing receives only the bounded exact-head local summary and is
  called once after the local gate; no legacy helper or direct remote request
  path survives in this deliverable.
- [ ] Reports expose enough first-remote and subsequent-round telemetry to
  compare Copilot churn before and after rollout without estimating avoided
  rounds as fact.
- [ ] Focused provider-planning, concurrency, receipt, remediation, and review
  state-machine tests pass, followed by generated parity, install audit,
  `make sync`, and `make check`.

## Out Of Scope

- Re-enabling Prism or Gito inside `sd-check` or the legacy PR full-check helper.
- Running every local provider on every documentation, task, journal, or
  bookkeeping-only successor head.
- Selecting, dispatching, or implementing remote review backends in this repo.
- Claiming that Prism, Gito, and Copilot produce equivalent review quality.
- Preserving `sd-review-local`, `sd-review-pr`, or `sd-full-check` as public or
  hidden compatibility surfaces.
