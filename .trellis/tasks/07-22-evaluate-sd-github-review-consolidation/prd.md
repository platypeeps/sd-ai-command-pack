# Evaluate sd-github-review repository consolidation

## Goal

Decide whether `sd-ai-command-pack` and `sd-github-review` should become one
repository, remain independently versioned repositories, or adopt a narrower
shared-boundary arrangement. The decision should reduce duplicated maintenance
without blurring product ownership or making fleet delivery less reliable.

The intended product outcome is a smooth, cost-efficient review experience that
can select among local providers, Copilot, and other remote backends according
to cost and expected review quality. Backend choice should not require a
different workflow, while backend-specific limitations and evidence remain
observable rather than falsely homogenized.

Local code review must be equally easy to reach. The design must preserve review
of uncommitted or branch-local changes while allowing PR review to use the same
local stage as cost-efficient evidence for remote routing.

The public command and skill surface should be replaced, not wrapped. The new
surface must eliminate the overlapping `sd-full-check`, `sd-review-local`, and
`sd-review-pr` structures, remove their legacy configuration families and
platform adapters, and present orthogonal deterministic-check and staged-review
concepts under clean names.

## Confirmed Context

- `sd-ai-command-pack` currently treats `sd-github-review` as one configured
  fleet consumer and reports its installed pack version and repository state.
- This task is decision and planning work only. It does not authorize moving
  code, changing repository settings, rewriting history, or deprecating either
  repository.

## Evidence Findings

- `sd-ai-command-pack` is a Python-backed installer and release system for
  Trellis-oriented skills, scripts, documentation, and platform adapters. Its
  `manifest.json` and `templates/**` own the shipped payload; target
  repositories hold auditable installed copies.
- `sd-github-review` is a public, dependency-free Node 24 GitHub Action. Its
  product source is `src/**` plus `action.yml`; it selects `cheap`, `deep`,
  `copilot`, or `none` for GitHub pull-request events and exposes a stable
  workflow-output contract.
- There is no product-source import in either direction. The relationship is
  operational: `sd-github-review` consumes the command pack, while the pack's
  release candidate gate uses `sd-github-review` as an independent fleet
  compatibility target.
- The review surfaces overlap only at the Copilot request side effect.
  `sd-review-pr` is an interactive, local-check-first fix loop; the GitHub
  Action is an event-driven risk router that does not own the subsequent fix
  loop.
- Local review is currently split across three surfaces. `sd-review-local`
  owns a Prism/Gito/custom-provider fix loop, `sd-full-check` has separate
  Prism and Gito invocation paths, and `sd-review-pr` explicitly disables both
  providers before requesting remote review. This preserves a deterministic PR
  gate, but it also creates duplicated provider logic and no reusable proof that
  an exact local scope was already reviewed.
- The current local runner reports human-readable output and process status,
  not a structured exact-scope receipt. Provider findings, unavailability, and
  execution failures therefore cannot be safely reused or compared by the PR
  workflow without rerunning the provider.
- In this design, "local review" means review initiated against the local
  checkout, including staged, unstaged, untracked, branch, or whole-codebase
  scope. A local provider may still require network access, credentials, or
  paid model usage; the workflow must disclose those characteristics instead
  of treating `local` as synonymous with free or offline.
- Those three commands currently occupy 79 live manifest targets: 26
  `review-pr`, 26 `review-local`, and 27 `full-check` skills, commands, prompts,
  workflows, and scripts across supported platforms. `sd-create-pr`, `sd-ship`,
  `sd-work-backlog`, `sd-help`, docs, and parity tests also name the split
  surface directly.
- The installer already has provenance-aware retired-target cleanup. It can
  remove unchanged old command footprints during refresh and preserve/report
  locally modified copies, so a clean cut does not require forwarding aliases.
- The current `sd-github-review` receipt is
  `0.30.4+sd-github-review.1`, a consumer-local override of pack-managed files.
  The canonical pack has since reached v0.30.7. This is concrete ownership
  drift to remove, but it does not couple the Action's product source to the
  pack implementation.
- Live GitHub evidence shows no `sd-github-review` tags or releases yet. Code
  search finds references only in the Action repository, this pack, and the
  private pilot repository, so consolidation remains mechanically affordable
  if a stronger product reason emerges.

## Options Considered

1. **Keep separate with an explicit contract (selected).**
   Preserve independent Action and pack release/security boundaries, prohibit
   durable consumer-local pack overrides, and document which mechanism owns a
   Copilot request when both workflows are present.
2. **Full monorepo consolidation.** Move the Action under this repository and
   archive or redirect the standalone repository. This reduces repository
   count but couples Python pack releases, Node Action releases, CI, tag
   namespaces, and security review.
3. **Narrow integration without moving source.** Keep both repositories and
   add a documented adapter or policy contract only if real adoption shows the
   interactive and event-driven review paths need coordinated routing. There
   is currently no shared source code worth extracting into a third package.

## Current Interface Assessment

- The router is generic enough for **selection and in-workflow dispatch**. It
  emits a normalized route, reason, model, PR number, external-reviewer flag,
  and Copilot-request result; external provider credentials remain outside the
  router.
- It is not yet generic enough for a seamless **end-to-end `sd-review-pr`
  round**. Action step outputs are scoped to the GitHub workflow, while the
  local command-pack loop configures one request command and one author matcher
  before routing. The loop cannot currently discover the selected backend,
  observe a backend-neutral head-bound completion receipt, or know which
  review/comment/check channels carry that backend's findings.
- The command pack already normalizes much of the downstream lifecycle by
  reading GitHub reviews, inline comments, conversation comments, review
  threads, and CI. That is a useful common findings plane, but it assumes the
  selected backend materializes into one of those observable GitHub surfaces.
- A stable experience should mean one invocation, one fix loop, one exact-head
  clean gate, and one report shape. It should not pretend that raw reviewer
  prose, latency, cost, inline-thread support, or confidence are identical.
- The minimum separation-preserving bridge is a versioned per-round receipt
  containing the PR and head, route, backend, model or cost tier, reason,
  request status, trigger time, observable author/check identities, finding
  channels, retry capability, and workflow/run URL. Exactly one component must
  own the request side effect for a given head.
- Local review needs a separate, pack-owned receipt because it can cover dirty
  checkout state that does not exist on GitHub. That receipt must bind the
  repository, scope kind, base/head identities, worktree content digest,
  provider/configuration identity, outcome, disposition, and timing. Only a
  bounded exact-head summary may cross into the remote routing request.
- Cost efficiency and best-output claims require measured backend outcomes.
  The current router is deterministic risk policy based on path sensitivity,
  change size, and upstream confidence; it does not yet compare observed cost,
  latency, or finding quality.

## Decision

Keep the repositories separate and make the integration intentionally tight at
a small, versioned protocol boundary. `sd-github-review` should own routing and
backend dispatch; `sd-ai-command-pack` should own deterministic preflight, the
pack-local provider registry and receipt, the review/fix loop, exact-head
evidence, and user-facing lifecycle. Reconsider a monorepo only if the protocol
repeatedly requires shared mutable internals or atomic cross-repository releases
rather than stable versioned messages.

Use automatic per-PR cost/quality routing after deterministic checks, with an
explicit `auto`, `cheap`, `deep`, `copilot`, or `none` override. Within
`sd-ai-command-pack`, replace the current three-way public review/check surface.
The approved clean interface is `sd-check` for deterministic verification and
`sd-review` for local, codebase, and PR review. Do not ship aliases, redirecting
skills, compatibility scripts, or readers for retired configuration families.
Normal installer refresh retires old pack-owned targets safely.

## Cross-Repository Task Map

- This repository:
  `07-22-integrate-routed-review-backends` owns receipt consumption,
  the consolidated command/skill surface, a reusable exact-scope local-review
  engine and receipt, exact-head validation, backend-neutral observation, fix
  rounds, and the unified `sd-review` report.
- `platypeeps/sd-github-review`:
  `07-22-publish-routed-review-receipt-contract` owns the versioned routing
  setup descriptor, request/receipt schema, automatic and explicit selection,
  dispatch phase/idempotency, validation of bounded local-review summaries,
  backend observation metadata, and cost/quality evidence.
- The router contract task must publish and validate a stable v1 fixture before
  the command-pack child implements its consumer. This dependency is explicit;
  task-tree position does not imply it.

## Requirements

- R1: Compare each repository's purpose, maintainers, source-of-truth files,
  generated or installed artifacts, release cadence, tests, and downstream
  consumers using current repository evidence.
- R2: Identify concrete duplication, dependency direction, circular ownership,
  and operational friction between the repositories.
- R3: Evaluate at least three options: full consolidation into
  `sd-ai-command-pack`, continued separation with an explicit contract, and a
  narrower extraction or monorepo-style boundary.
- R4: Recommend one option and state which evidence would invalidate that
  recommendation.
- R5: Describe migration, compatibility, release, rollback, and repository
  archival consequences for the selected option and material alternatives.
- R6: Preserve the rule that shipped command-pack payloads are sourced from
  `templates/**`; do not create competing ownership for generated copies.
- R7: Determine whether the current router outputs and command-pack remote
  request hooks form a sufficient end-to-end abstraction across dispatch,
  completion detection, findings ingestion, fix rounds, and reporting.
- R8: If the current interface is insufficient, define the minimum versioned
  adapter contract needed to keep the repositories separate without exposing
  backend selection as a different user workflow.
- R9: Replace the current `sd-review-local`, `sd-full-check`, and `sd-review-pr`
  command/skill split with orthogonal deterministic-check and staged-review
  concepts while preserving worktree, branch, codebase, and PR outcomes.
- R10: Define one staged review lifecycle for deterministic checks, local AI
  review, and selectively escalated remote review, with one local execution
  contract and no duplicate provider invocation.
- R11: Remove retired skills, platform adapters, scripts, help/catalog entries,
  documentation, manifest targets, and old environment-variable/configuration
  contracts. Do not add aliases or compatibility readers.
- R12: Use provenance-aware installer retirement to delete unchanged old
  pack-owned targets on refresh while preserving and reporting locally modified
  files according to existing installer safety rules.
- R13: Update every owning workflow, including `sd-create-pr`, `sd-ship`,
  `sd-work-backlog`, help, docs, tests, and fleet validation, to call only the
  new surface.
- R14: Preserve graceful adoption when no router is configured: optional
  `remote=auto` performs a clearly reported local-only review without prompting,
  while explicit or required remote review stops early with setup guidance.
  `remote=none` remains an intentional local-only path and cannot claim that an
  unmet required remote gate was satisfied.
- R15: Distinguish true absence before dispatch from declared-invalid,
  unavailable, failed, or ambiguously dispatched router state. Fail closed for
  every non-absence state without restoring direct backend dispatch.
- R16: Treat every new PR head as a new remote-routing identity. A
  finish-work/bookkeeping-only successor may receive a new exact-head `none`
  receipt only from router `auto` policy after trusted prior/current comparison;
  the command pack cannot mint a local exemption or reuse the prior receipt.
- R17: Separate tracing correlation, logical dispatch identity, and normalized
  request fingerprint. Retries and restarts reuse one
  repository/PR/head/attempt identity and matching fingerprint; conflicting
  retry content fails closed. A same-head rerequest requires an explicit prior
  receipt, next attempt, backend capability, and policy authorization.

## Acceptance Criteria

- [x] The analysis contains an evidence-backed responsibility and dependency
  map for both repositories.
- [x] Material duplication and lifecycle friction are distinguished from
  intentional producer/consumer separation.
- [x] The alternatives are compared against maintainability, release coupling,
  test isolation, fleet rollout safety, and migration cost.
- [x] A clear recommendation, trade-offs, invalidation conditions, and next
  step are presented for user review.
- [x] The recommendation distinguishes a stable user experience from identical
  raw reviewer output and documents which backend differences must remain
  visible.
- [x] The design treats local review as a first-class, exact-scope stage and
  prevents duplicate local-provider runs across full-check and review flows.
- [ ] The final public surface contains no overlapping or forwarding legacy
  review/check skills, commands, scripts, configuration keys, or help entries.
- [ ] Refresh tests prove that old pack-owned targets are retired safely and
  cannot remain discoverable alongside the new surface.
- [x] The public names and granularity are fixed as `sd-check` for deterministic
  verification and `sd-review` for every review scope.
- [x] Remediation defaults are fixed as automatic for changes, branch, and PR
  scope and confirmation-first for codebase scope, with mandatory confirmation
  for higher-risk changes in every scope.
- [x] Optional local-provider failure in PR scope continues to a ready router
  with zero confidence credit; required-local policy, optional router absence,
  and every non-PR scope stop on local-provider failure unless `local=none` was
  explicitly selected.
- [x] Publishing boundaries are fixed: non-PR review is worktree-only, while PR
  review commits and pushes only intended fixes after deterministic validation.
- [x] Both repository-owned implementation tasks contain aligned requirements,
  an explicit dependency, and independently testable acceptance criteria.
- [x] Missing-router behavior distinguishes optional unconfigured repositories
  from required, broken, or ambiguously dispatched remote review without
  restoring direct backend dispatch to the command pack.
- [x] The cross-repository task artifacts agree that every successor head gets
  a distinct router decision/receipt, that router policy alone may classify a
  bookkeeping-only successor as `none`, and that the router remains
  noninteractive and never executes PR checkout code.
- [x] Both implementation tasks use the same logical-request-versus-correlation
  model and explicit same-head rerequest boundary, preventing a retry-generated
  correlation ID from causing duplicate provider spend.
- [x] No implementation begins without separate approval after planning.

## Out of Scope

- Performing the consolidation or opening migration pull requests.
- Changing the upstream Trellis repository.
- Folding unrelated fleet consumers into the same repository.
- Preserving aliases, compatibility scripts, or legacy configuration readers
  for `sd-full-check`, `sd-review-local`, or `sd-review-pr`.
