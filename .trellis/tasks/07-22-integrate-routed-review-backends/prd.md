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

The unified review workflow resolves a cost- and risk-aware local provider plan,
records exact-scope evidence, and asks `sd-github-review` whether an independent
remote review is still required. Its default first substantive PR head runs
Prism and Gito concurrently before remote dispatch, while low-risk successors
may select one eligible provider and verified bookkeeping successors may skip.
One invocation owns findings disposition, fixes, exact-head reruns, thread
resolution, CI, and the final report.

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

## Dependencies

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

## Implementation Child Map

- `07-24-implement-read-only-sd-check` owns the deterministic successor and
  finding `1.4.6.1`; it must land before review integration and retirement.
- `07-24-implement-unified-routed-sd-review` owns the unified local/remote state
  machine and finding `1.1.2`; it depends on `sd-check` and router v1.
- `07-25-add-routed-review-operator-ux` owns nested configuration and budget
  operations over published router contracts; it depends on the unified
  `sd-review` surface and stable configuration/status/recovery interfaces.
- `07-25-publish-local-review-attestations` owns bounded publication of the
  unified coordinator's exact-head local receipt when the router explicitly
  selects local-attested execution.
- `07-24-simplify-review-shipping-composition` owns publish/review/ship
  boundaries and finding `1.5.2.1`; it depends on both successor commands.
- `07-24-remove-retired-review-surfaces` owns exhaustive deletion and installed
  target retirement; it runs after all callers use the new contracts.
- This task is the review-cutover coordination parent. It does not complete
  merely because the successor commands exist; every child and the clean-cutover
  evidence must be terminal.

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
- R6: In local `auto`, resolve a deterministic provider set from scope,
  data-handling, capability, minimum-quality, risk, finding-family, and cost
  policy. Run Prism and Gito concurrently for the first substantive PR head,
  cross-cutting or high-risk successor heads, and repeated finding families.
  Low-risk successors may select one lowest-cost eligible provider; verified
  documentation, metadata, or bookkeeping-only cases may use a stable recorded
  skip when policy permits. `all` still explicitly requests every eligible
  provider, and failure never silently substitutes an unselected or more
  expensive provider.
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
- R30: When compatible router discovery selects an explicit v2 local-attested
  route, publish the canonical exact-head local receipt through the trusted
  repository workflow instead of dispatching a GitHub-side reviewer. Preserve
  the same attempt/fingerprint across retries, expose
  `repository_attested` rather than independent trust, and fail closed without
  remote fallback on wrong-head, rejected, or ambiguous publication.
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
- R33: Execute the child order explicitly: read-only check, unified review,
  routed-review operator UX, shipping composition, then retirement. Do not
  expose a mixed old/new public surface as a completed release between those
  steps.
- R34: The final public experience has one vocabulary and authority model:
  `sd-check` checks, `sd-review` reviews, `sd-create-pr` publishes, `sd-ship`
  composes delivery, and `sd-housekeeping` merges/cleans. No other public or
  hidden route performs those same responsibilities.
- R35: Remove obsolete implementation code as well as names. Unreachable
  branches, parsers, environment readers, provider dispatchers, polling loops,
  generated templates, tests, and documentation are deleted rather than
  disabled, deprecated, or retained for speculative rollback.

Added 2026-07-28 — audit findings this task owned but did not cover. (Note: the
numbering above contains two `R30` entries and an out-of-order `R29`; new
requirements continue from R35 and do not renumber existing references.)

- R36 (A-056): Any `.sd-ai-command-pack/` configuration file that a shipped
  script reads must be install-audit-clean before its stanza ships — present in
  `LOCAL_ALLOWED_PACK_FILES` (`scripts/sd-ai-command-pack-install-audit.py:78`)
  or covered by a managed gitignore pattern (`installer/registry.py:1759`) — with
  a test asserting that every `.sd-ai-command-pack/` path constant read by a
  shipped script has a declared tracked/ignored disposition. The constant is not
  always named `CONFIG_PATH`: `scripts/sd-ai-command-pack-pr-body-scope.py:69`
  uses `DEFAULT_CONFIG_PATH` and `:70` `INSTALLED_TARGETS_FILE`, so a
  `CONFIG_PATH`-only assertion re-opens the same hole. Drive it from one registry
  of shipped pack-configuration paths rather than a name convention. R5 and R23 mandate `review.json` today while the allowlist holds
  only check.json, pr-body-scope.json, and review-preflight.json; because
  collection walks the filesystem (`install-audit.py:558`), an untracked
  `review.json` is still collected, fails at `:668`, and exits 1 at `:1021`. That
  breaks three gates at once, since `templates/scripts/sd-ai-command-pack-check.py:917`
  registers `pack.install-audit` as an `sd-check` gate. The immediate `review.json`
  fix is owned by `07-28-allowlist-review-json-install-audit`, which now carries
  only that instance. **This requirement owns the invariant** (decided
  2026-07-28): the registry of shipped pack-configuration paths and the test that
  enforces a declared disposition for each are built once, here.
- R37 (A-068): R5's "validated argument arrays, not shell strings" is not
  satisfied by a name-based guard. `review-local.py:400` checks executable names
  and `-c`, so `["/usr/bin/env","sh","-c",…]` and `["python3","-m",…]` pass;
  `:473` reads provider argv from the repo's own `review.json` and `:1666`
  executes it via `shutil.which` plus `Popen(cwd=repo)` with no confirmation gate
  and no provider allowlist at `:2131`. Because this tool reviews untrusted
  checkouts, checkout-plus-review runs attacker-chosen commands. Resolve it one
  of two ways and state which: pin argv[0] to a resolved allowlist, or document
  the adapter as full local code execution behind an explicit operator opt-in.
  Either way the acknowledgement must bind to the thing that can change under the
  operator — repository identity, the resolved configuration digest, the provider
  id, and the exact argv — and must be invalidated the moment any of those
  differ. A blanket "operator enabled local execution" flag is not sufficient:
  the attacker input is the checkout's own `review.json`, so an acknowledgement
  that survives a config change grants execution to content the operator never
  saw. A partial guard that makes the surface look bounded is not an acceptable
  third option.
- R38 (A-051): Give the routed-receipt validation real coverage.
  `scripts/sd-ai-command-pack-review.py:1055` `_decode_receipt_check` has all
  eight `raise ReviewError` paths in the coverage missing list, and the
  validation body at `:1116` is reached by no test; review.py sits at the floor
  table's joint-lowest value (70, tied with check.py and review-local.py) at 73%
  actual (`.github/scripts/check-shipped-script-coverage.sh:51`). Add a table-driven
  malformed-receipt test through the decoder, and delete the branches unreachable
  from real payloads rather than testing them — untested defensive code and dead
  code are indistinguishable, which is the specific failure this task's receipt
  machinery cannot afford.
- R39 (A-082): Resolve the `routedReview` field this task is named as the owner
  of. `scripts/sd-ai-command-pack-pr-eligibility.py:750`, `:922`, and `:1241`
  emit an identical deferred literal naming this task, and no consumer exists
  anywhere. Either the routed lifecycle populates it as part of this work, or it
  is removed from the published eligibility schema and the deferral survives as a
  code comment. A field that can never take a second value is a comment, not a
  contract, and it goes stale the moment this task is renamed or archived.

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
- [ ] A substantive first-head fixture runs Prism and Gito concurrently,
  aggregates and deduplicates their findings before remote routing, and proves
  low-risk successor selection plus bookkeeping-only skips do not reuse stale
  confidence or create duplicate provider billing.
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
- [ ] Local-attested tests publish only bounded exact-head local receipt
      evidence, dispatch zero GitHub-side reviewers, preserve idempotency, and
      keep direct-handler, managed, `none`, absent, invalid, and incompatible
      setup behavior distinct.
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
- [ ] All five implementation children are archived with landed and validated
      evidence in dependency order.
- [ ] A repository-wide live-surface scan and upgrade-from-prior-release fixture
  prove that no old command, code path, shell-string/environment reader, alias,
  wrapper, fallback, hidden mode, or stale receipt remains executable.
- [ ] One end-to-end user journey proves the same scope, provider, finding,
  failure, head, and merge semantics across direct `sd-review`, `sd-ship`, and
  `sd-work-backlog` composition without duplicate provider or polling work.
- [ ] A consumer fixture containing every `.sd-ai-command-pack/` file this task
  introduces passes `install-audit` with exit 0, and a test fails if any
  `.sd-ai-command-pack/` path constant in any shipped script — whatever its
  identifier — lacks a declared tracked/ignored disposition.
- [ ] Adapter-argv fixtures prove the chosen R37 disposition: an allowlist build
  rejects `/usr/bin/env sh -c`, `python3 -m`, and any unresolved argv[0]; an
  opt-in build refuses to execute when the acknowledgement was recorded against a
  different repository, configuration digest, provider id, or argv, and refuses
  again after the fixture mutates `review.json` post-acknowledgement. Neither
  build relies on executable-name matching alone.
- [ ] The supported receipt schema and the production entrypoints that reach
  `_decode_receipt_check` are enumerated in `design.md`; malformed-receipt
  fixtures reach every `raise` path retained as reachable from those
  entrypoints; and every `raise` path not reachable from them is deleted rather
  than covered.
- [ ] `routedReview` is either populated by the routed lifecycle with at least
  two distinct observed values under test, or absent from the published schema
  and from all three producers.

## Out Of Scope

- Compatibility aliases, forwarding scripts, or legacy configuration readers.
- Embedding provider runtimes or remote provider credentials in the pack.
- Automatically learning routing policy from unbounded telemetry in v1.
- Merging or archiving either repository.

## Deferred features (2026-08-08 consolidation)

The 2026-08-08 backlog consolidation dropped the review-operator group —
blocked on sd-github-review v2 contracts that are parked/dropped in that
repo's own consolidation (9,390 of its 13,136 src LOC unreachable from the
Action entrypoint). Recorded here so the ideas are recoverable if the v2
governance direction is ever revived (content in git history under
`.trellis/tasks/<dir>/`):

- 07-25-add-routed-review-operator-ux — operator CLI umbrella (~19 planned
  subcommands), with children: 07-25-add-sd-review-budget-operations,
  07-25-add-sd-review-configuration-operations,
  07-25-add-sd-review-data-operations,
  07-25-add-sd-review-finding-adjudication-operations.
- 07-25-add-multi-reviewer-learning-and-effectiveness-analysis — with
  children 07-25-add-review-effectiveness-command and
  07-25-generalize-review-learnings-across-reviewers (the latter would have
  deleted batching that shipped in v0.64.11).
- 07-25-publish-local-review-attestations — attestation publication for local
  review runs.

## Rescope (2026-08-08)

Backlog-consolidation rescope: this program closes when
07-24-remove-retired-review-surfaces lands, PLUS the two pack-side contract
items from the 2026-08-08 collaboration review:

- Accept `supportedContractMajors` from the router's discovery descriptor,
  so the pack can negotiate contract versions instead of hard-pinning.
- Emit `riskClass` and changed-path count in the v1 route request, so the
  pack classifies and the router prices the review.

Priority moved P1 to P2. No other scope survives; the v2 governance surface
this program once targeted is parked/dropped in sd-github-review's own
consolidation.
