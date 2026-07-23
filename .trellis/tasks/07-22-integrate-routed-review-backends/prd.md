# Consolidate review command surface and routed backends

## Goal

Replace the overlapping `sd-full-check`, `sd-review-local`, and
`sd-review-pr` public structures with the approved clean, orthogonal interface:

- `sd-check` for deterministic verification with no AI-review or GitHub-review
  side effects; and
- `sd-review` for worktree, branch, codebase, and PR review through one staged
  local-plus-remote lifecycle.

The cutover is intentionally not backward compatible. Remove the old skills,
platform adapters, scripts, environment-variable families, help entries, and
configuration readers rather than wrapping them. Preserve user outcomes and
installer safety, not legacy invocation shapes.

The unified review workflow selects the lowest-cost eligible local provider,
records exact-scope evidence, and asks `sd-github-review` whether an independent
remote review is still required. One invocation owns findings disposition,
fixes, exact-head reruns, thread resolution, CI, and the final report.

## Confirmed Evidence

- The current three commands occupy 79 live manifest targets: 26
  `review-pr`, 26 `review-local`, and 27 `full-check` targets across
  skills, commands, prompts, workflows, and scripts.
- `sd-full-check` and `sd-review-local` contain separate Prism/Gito
  invocation behavior, while `sd-review-pr` disables both and launches a
  remote-review loop. There is no reusable structured local result.
- `sd-create-pr`, `sd-ship`, `sd-work-backlog`, `sd-help`, README/docs,
  manifest parity tests, and installed adapters directly name the split
  surface.
- The installer already provides provenance-aware retired-target cleanup:
  unchanged vouched files can be removed during refresh, while locally modified
  copies are preserved and reported.

## Dependency And Ownership

- Depends on `platypeeps/sd-github-review` task
  `07-22-publish-routed-review-receipt-contract` publishing reviewed v1
  schemas, setup-descriptor and dispatch-phase fixtures, bounded local-summary
  fixtures, durable exact-head transport, and pilot evidence.
- `sd-ai-command-pack` owns the public command/skill surface, deterministic
  check implementation, local provider profiles/adapters, exact-scope local
  receipts, remediation loop, remote receipt consumption, and final report.
- `sd-github-review` is the only remote selection and dispatch owner. The
  command pack must not retain a direct Copilot or custom-remote dispatch path.
- `templates/**` remains authoritative for every shipped payload. Generated
  mirrors are synchronized through the normal pack workflow.
- Depends on `07-22-centralize-pr-eligibility-gates` publishing the shared
  read-only exact-head eligibility schema before the final merge-ready state is
  wired into the unified review lifecycle.
- Depends on `07-22-add-portable-structured-questions` publishing the canonical
  interaction policy and adapter capability mapping before review prompts are
  regenerated.
- Coordinates with `07-22-add-command-surface-drift-lint`: the lint
  infrastructure may land first, while this task owns registering and proving
  retirement of the old review/check identifiers.

## Requirements

- R1: Expose only `sd-check` and `sd-review` across every supported platform.
  `sd-check` is the deterministic primitive; `sd-review` owns every worktree,
  branch, codebase, and PR review mode.
- R2: Make the deterministic command run verification, readiness, scope, and
  preflight gates only. It must never invoke Prism, Gito, another AI reviewer,
  GitHub review dispatch, or findings remediation.
- R3: Give `sd-review` typed controls for
  `scope=auto|changes|branch|codebase|pr`,
  `local=auto|<provider>|all|none`, and
  `remote=auto|cheap|deep|copilot|none`, plus
  `fix=auto|ask|none`. Natural-language adapters map to the same contract
  instead of defining platform-specific modes.
- R4: Resolve `scope=auto` deterministically: use PR scope only when one open
  PR is unambiguously bound to the current branch or an explicit selector;
  otherwise review current worktree changes, or the branch delta when the
  worktree is clean. Whole-codebase review remains explicit.
- R5: Use one versioned pack-owned review configuration for local provider
  profiles and defaults. Profiles declare adapter ID, supported scopes,
  network/data-handling class, cost tier, quality tier, timeout, and version.
  Custom commands use validated argument arrays or adapters, not shell strings.
- R6: In local `auto`, run one lowest-cost configured provider that satisfies
  scope, data-handling, capability, and minimum-quality policy. `all` is an
  explicit high-assurance/comparison choice, not the default.
- R7: Record local receipt schema v1 with repository, scope kind, base/head,
  canonical content digest including applicable staged/unstaged/untracked
  bytes, provider/configuration identity, timing, normalized outcome, findings
  disposition, bounded confidence, and local artifact references.
- R8: Reuse local evidence only when repository, scope, content, base/head,
  provider/adapter versions, and configuration digest match exactly. Any change
  invalidates reuse and prevents duplicate provider billing for an unchanged
  exact scope.
- R9: Normalize local outcomes as `clean`, `findings`, `unavailable`,
  `failed`, `cancelled`, or `skipped`, with findings disposition represented
  separately. Do not conflate provider findings with authentication,
  configuration, timeout, or execution failure. `skipped` requires a stable
  reason such as explicit `local=none` or an exact-head bookkeeping-successor
  policy and supplies no new positive provider confidence.
- R10: In PR scope, run the deterministic contract, local review, findings
  disposition, bounded remote routing, remote observation/remediation, and
  exact-head gates as one state machine. Outstanding local findings block
  remote dispatch unless explicitly dispositioned.
- R11: Send only an allow-listed exact-head local summary to the router. Never
  send source, paths, prompts, raw findings, transcripts, credentials,
  configuration values, or local artifacts.
- R12: Enforce one remote request owner. Routed mode is the only PR remote path;
  no direct reviewer request, author-matcher configuration, or fallback
  dispatch remains in the pack.
- R13: Remove all live `sd-full-check`, `sd-review-local`, and
  `sd-review-pr` skills, commands, prompts, workflows, scripts, help/catalog
  entries, docs, manifest targets, and environment/configuration contracts. Add
  no aliases, redirectors, forwarding scripts, or legacy readers.
- R14: Add every old pack-owned target to provenance-aware retirement. Refresh
  deletes unchanged vouched files, preserves and reports drifted files, prunes
  empty directories, and never writes retired paths into the new installed
  receipt or provenance.
- R15: Update `sd-create-pr`, `sd-ship`, `sd-work-backlog`, help/catalog
  data, examples, docs, installer audit, tests, and fleet validation to call and
  describe only the new surface.
- R16: Produce one report shape across local and remote stages. Report provider,
  run-versus-reuse, scope, outcome/disposition, route reason, configured and
  observed cost tier, latency, workflow/artifact reference, channels, and
  material limitations without claiming equivalent provider output.
- R17: Keep raw local provider output in ignored local artifacts and remote
  findings on declared GitHub surfaces. Validate all config/receipt data before
  use and preserve bounded retries, timeouts, polling, round limits, and final
  thread/CI gates.
- R18: Ship the new surface only after router v1 and the coordinated fleet
  migration are ready. Rollback reinstalls the last pre-cut pack release; the
  new release contains no dormant legacy mode.
- R19: Support `fix=auto|ask|none`. Default to `auto` for `changes`, `branch`,
  and `pr`, and to `ask` for `codebase`. Auto mode fixes only clearly valid,
  in-scope findings; every mode asks before destructive, ambiguous,
  out-of-scope, architecture, dependency, product-behavior, or policy changes.
- R20: When the selected local provider is unavailable or fails, PR scope with a
  ready router continues to remote routing with the explicit local outcome and
  zero positive local-confidence credit unless repository policy requires local
  review. With optional router absence, the same provider failure stops because
  no review provider remains, unless the user explicitly selected `local=none`.
  Changes, branch, and codebase scopes also stop with the normalized provider
  diagnostic because no remote fallback exists. Never switch silently to a
  different or more expensive local provider.
- R21: Keep changes, branch, and codebase review worktree-only: they may edit
  and verify approved fixes but never stage, commit, or push. PR review stages
  only intended review-fix paths, creates one focused commit per verified round,
  and pushes automatically after `sd-check` passes so exact-head routing can
  continue. Neither mode stages unrelated or ambiguous paths.
- R22: Retire the repository-owned `package.json` `check:full` hook and its
  full-check environment-variable contract with the old command surface.
  Repository-specific deterministic prerequisites and commands move to a
  versioned check-configuration schema in pack metadata (the proposed
  `check.json` file under `.sd-ai-command-pack/`) using validated argument
  arrays. The new `sd-check` owns orchestration directly.
- R23: Add a side-effect-free router capability preflight for PR scope before
  any review-provider call or GitHub mutation unless `remote=none`. A versioned
  remote-integration stanza in the proposed `review.json` file under
  `.sd-ai-command-pack/` declares only `optional|required` integration policy,
  workflow identity, and contract major;
  backend selection policy remains router-owned. No stanza means optional and
  not configured. Classify the live integration as `ready`, `absent`, `invalid`,
  or `unavailable` without dispatching a review.
- R24: For `remote=auto`, an `absent` optional integration degrades without a
  prompt to deterministic and local review plus inspection of existing GitHub
  feedback, threads, and CI. Report `remote=not-configured`, setup guidance, and
  zero remote confidence. An absent required integration or any explicit
  `remote=cheap|deep|copilot` request stops early with setup guidance.
  `remote=none` always runs the intentional local-only path; when integration is
  required, its report must state that remote merge readiness remains unmet.
- R25: Treat a declared but invalid/disabled integration, an unavailable
  capability probe, router runtime failure, missing or malformed receipt, and
  ambiguous dispatch as failures rather than absence. Stop without direct
  Copilot/custom-provider fallback or a second dispatch, and provide receipt
  reconciliation or setup guidance appropriate to the state.
- R26: Make `sd-check` strictly read-only across the repository, Git, GitHub,
  generated knowledge, and caches tracked by the repository. It may report a
  stale `.obsidian-kb`, repo map, manifest, or generated artifact, but it must
  not refresh or rewrite one. Route refresh guidance to the owning command.
- R27: Bind the final clean decision to the full current PR head after every
  commit, including review-fix, spec, task-archive, journal, or finish-work
  commits. A new head re-enters the relevant deterministic, CI, thread, and
  review gates. When routed integration is ready or required, send a new
  exact-head routing request whose `supersedes` field carries the validated
  prior router receipt/correlation and full prior head identity;
  the router may return a new current-head `none` receipt for a verified
  bookkeeping-only successor when its policy permits. The command pack and
  shared eligibility gate must not mint a parallel local exemption or reuse an
  older-head receipt. To avoid duplicate local-provider spend, the pack may
  emit a new current-head local-stage `skipped:bookkeeping-successor` receipt
  from exact finish-work/delta evidence when local policy permits; it references
  but does not reuse the prior local receipt and grants no new confidence.
- R28: Implement provider dispatch, polling, receipt validation, head-change
  reconciliation, retry/round budgets, and GitHub observation as a tested
  executable state machine with versioned JSON state. The skill retains
  judgment and disposition policy but does not remain the authoritative
  transport program.
- R29: Make `sd-create-pr` publish or reuse a PR only. Make `sd-ship` explicitly
  compose create, review, finish-work/final-head re-entry, and housekeeping.
  Retire public `sd-watch-pr` and its default merge-capable handoff; internal
  waiting is a read-only coordinator primitive, not a discoverable command.
- R30: Consume the portable structured-question contract for genuinely
  ambiguous or higher-risk review choices. Do not prompt for normal in-scope
  fixes, bounded polling, thread resolution, optional-router absence, or other
  behavior already authorized by invocation and policy.
- R31: Add behavioral state-machine tests for head changes after review,
  finish-work commits, delayed feedback, multi-page threads, unavailable
  question tools, provider cost/data constraints, and missing/broken router
  states. Parity and prose assertions alone do not satisfy this requirement.
- R32: Persist one logical remote dispatch identity for each
  repository/PR/head/attempt plus a separate normalized request fingerprint.
  Reuse both across retries or changed tracing correlation IDs and fail closed
  if retry content conflicts. A same-head rerequest is a separate explicit next
  attempt that references the prior receipt and is allowed only when backend
  capability and repository policy permit it.

## Acceptance Criteria

- [ ] Clean installs expose exactly the approved new check/review skills and
  platform adapters; no old review/check command is discoverable.
- [ ] Deterministic verification invokes no AI or GitHub review provider, while
  unified review covers changes, branch, codebase, and PR scopes.
- [ ] Scope auto-detection and every local/remote override have focused positive
  and negative tests, including ambiguous/no-PR behavior and `none`.
- [ ] Fix-policy tests prove the approved scope defaults, explicit overrides,
  and mandatory confirmation boundaries for higher-risk changes.
- [ ] Provider-failure tests prove ready-router PR continuation, required-local
  blocking, optional-absent stopping when local review fails, explicit
  `local=none`, zero confidence credit, non-PR stopping, and no silent provider
  substitution.
- [ ] Mutation tests prove non-PR scopes never stage/commit/push and PR scope
  publishes only intended verified fix paths in one focused commit per round.
- [ ] Prism, Gito, and custom adapters use one execution/result contract;
  matching receipts are reused and every identity/config/content change forces
  a rerun.
- [ ] One PR invocation spans deterministic checks, local review, routed remote
  review, findings remediation, exact-head invalidation, delayed thread reads,
  CI, and a stable final report.
- [ ] Local evidence can lower remote cost only within router policy and cannot
  bypass sensitive/large-change independent-review floors.
- [ ] Privacy tests prove routing requests and durable receipts contain none of
  the forbidden local material.
- [ ] Refresh from the prior pack version retires all unchanged old targets,
  preserves/reports modified targets, and leaves no old discoverable surface or
  stale receipt/provenance entry.
- [ ] `sd-create-pr`, `sd-ship`, `sd-work-backlog`, help, docs, adapters,
  manifest, audit, and tests contain only the new live names except explicit
  retirement/migration fixtures.
- [ ] `check:full`, its selector helper, and full-check environment keys are
  absent from live runtime/docs; repository prerequisites are validated through
  argument-array fixtures for the proposed check configuration.
- [ ] Router capability tests cover `ready`, truly `absent`, declared-invalid,
  disabled, incompatible, and probe-unavailable states without dispatch side
  effects. No integration stanza defaults to optional absence.
- [ ] `remote=auto` degrades silently to a clearly reported local-only result
  only for optional absence; explicit or required remote review stops early,
  and `remote=none` runs locally without claiming required remote readiness.
- [ ] Runtime/receipt/ambiguous-dispatch tests fail closed and prove that the
  command pack never issues a direct or duplicate fallback reviewer request.
- [ ] `sd-check` leaves tracked, untracked, ignored generated knowledge, Git,
  and GitHub state unchanged while reporting stale artifacts precisely.
- [ ] A finish-work or other post-review commit cannot inherit a clean verdict
  from an older head; tests cover full re-entry, a router-issued exact-head
  bookkeeping-only `none` receipt, mixed changes, explicit remote intent, and
  required remote floors without any command-pack-local exemption.
- [ ] A policy-allowed bookkeeping-only successor does not rerun a local
  provider: it receives a distinct current-head
  `skipped:bookkeeping-successor` local-stage receipt with zero new confidence.
  Mixed changes or required-local policy rerun/block normally.
- [ ] Review transport and polling resume from serialized coordinator state and
  reconcile a changed head without relying on prompt memory.
- [ ] Retrying with a new tracing correlation cannot cause a second backend
  dispatch for the same logical identity; conflicting retry fingerprints fail
  closed, and same-head rerequest fixtures require explicit prior receipt, next
  attempt, capability, and policy authorization.
- [ ] `sd-create-pr` has no review/spec-private return mode, `sd-ship` owns the
  composition, and no live `sd-watch-pr` target or merge-capable watch path
  remains.
- [ ] Generated adapters use the portable question contract only at documented
  decision boundaries and degrade safely when the host lacks the capability.
- [ ] Source templates, generated mirrors, manifest/provenance, candidate
  ledger, focused tests, `make check`, and fleet candidate validation pass.

## Out Of Scope

- Compatibility aliases, forwarding scripts, or legacy configuration readers.
- Embedding provider runtimes or remote provider credentials in the pack.
- Automatically learning routing policy from unbounded telemetry in v1.
- Merging or archiving either repository.
