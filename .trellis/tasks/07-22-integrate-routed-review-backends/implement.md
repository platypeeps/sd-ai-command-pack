# Implementation plan: clean check and unified review surface

## 1. Freeze Product And Protocol Contracts

- Record all approved product decisions: command names, fix-policy defaults,
  provider-failure handling, and mutation/publishing boundaries.
- Specify the unified invocation and fix-policy grammar, review configuration
  schema, local provider-adapter envelope, local receipt v1, report shape, and
  retired-target inventory.
- Specify the remote-integration stanza, side-effect-free capability descriptor,
  `ready|absent|invalid|unavailable` preflight taxonomy, optional local-only
  completion result, and post-dispatch failure/ambiguity boundary.
- Pin the reviewed v1 router request/receipt fixtures from
  `platypeeps/sd-github-review` task
  `07-22-publish-routed-review-receipt-contract`, including bounded
  local-summary fixtures and a compatible release/commit.
- Stop if the router contract remains provisional; there is no legacy remote
  path to hide an incomplete dependency.
- Pin the shared PR-eligibility JSON schema, structured-question capability
  contract, and live/retired command registry from their owning sibling tasks.

## 2. Build Deterministic `sd-check`

- Extract deterministic verification/readiness behavior from the current
  full-check and review-full-check paths into one source-template coordinator.
- Add strict `.sd-ai-command-pack/check.json` parsing for repository-specific
  prerequisite and check argv arrays.
- Remove every Prism, Gito, custom-review, and remote-review branch from the
  deterministic implementation.
- Remove implicit KB/map/generated-state refresh. Add before/after state tests
  proving that stale state is reported without repository mutation.
- Add one skill and one adapter family for every supported platform, with
  focused tests proving no AI/GitHub review side effect.
- Remove the `package.json` `check:full` selector, review-full-check helper,
  package-runner environment controls, and associated recursion guards rather
  than forwarding them to the new command.

## 3. Build Unified `sd-review`

- Add one source-template review coordinator with typed scope/local/remote
  controls and deterministic auto-scope resolution.
- Add the versioned pack-owned review configuration and strict parser.
  Provider command configuration uses validated argv arrays/adapters, never
  shell strings.
- Resolve router capability before provider calls or GitHub mutation in PR scope
  unless `remote=none`. Treat a missing stanza as optional absence, but fail on
  declared-invalid or unreadable integration state.
- Extract current Prism and Gito exclusions, batching, writable-cache setup,
  timeout, and bounded retry behavior into provider adapters; add the custom
  adapter contract.
- Compute exact-scope manifests/content digests, normalize provider outcomes,
  write local receipts atomically, and reuse only exact identity matches.
- Preserve worktree, branch, codebase, and PR outcomes through this single
  coordinator.
- Persist coordinator state and make transport, polling, retry accounting,
  head reconciliation, and observation executable/tested rather than encoded
  only in the skill body.

## 4. Integrate Routed Remote Review

- Add strict request/receipt validation using the pinned router fixtures.
- Persist and reuse the router logical dispatch identity plus normalized
  request fingerprint across retries and restarts; reject conflicting retry
  content and treat correlation IDs as tracing only. Add the explicit
  policy/capability-gated same-head rerequest operation.
- Implement the approved absence matrix: optional `remote=auto` completes
  locally without prompting; required or explicitly requested remote review
  stops with setup guidance; `remote=none` runs locally without claiming an
  unmet required remote gate.
- Stop optional-absence runs when the selected local provider fails or is
  unavailable, unless `local=none` was explicitly selected; do not claim a
  successful local-only review when no reviewer ran.
- In PR scope, run deterministic check, local review/disposition, bounded
  exact-head routing, receipt-declared observation, remote remediation, and
  exact-head thread/CI gates.
- Make `sd-github-review` the only remote request owner. Do not port the old
  direct reviewer request, fixed author matcher, command hook, or fallback.
- Cover malformed/unsupported data, identity mismatch, stale local evidence,
  forbidden local fields, contradictory dispatch, `none`, and new-head
  invalidation.
- Cover runtime failure, missing receipt, and ambiguous dispatch as
  reconciliation-required failures with no direct or duplicate fallback.

## 5. Remove The Old Surface

- Delete source templates and generated copies for `sd-full-check`,
  `sd-review-local`, and `sd-review-pr` skills and every platform adapter.
- Delete obsolete full-check/review-local/review-full-check scripts and remove
  their manifest entries.
- Remove old environment-variable/configuration parsing and documentation,
  including direct remote-review controls and shell-string custom tools.
- Remove the live `check:full` package hook contract and migrate fleet-specific
  prerequisites to `.sd-ai-command-pack/check.json` argv arrays.
- Enumerate all old pack-owned installed paths in the retired-target registry.
  Extend refresh tests for unchanged deletion, drifted preservation/reporting,
  parent-directory pruning, and receipt/provenance removal.
- Add negative catalog/manifest/audit tests proving no alias, redirector,
  compatibility script, or legacy reader remains.

## 6. Rewire Owning Workflows And Documentation

- Update `sd-create-pr`, `sd-ship`, `sd-work-backlog`, help/catalog data,
  examples, review learnings where applicable, README, installed guide,
  configuration reference, changelog, and platform completion metadata.
- Reduce `sd-create-pr` to publish/reuse behavior, make `sd-ship` the explicit
  lifecycle composer, and retire `sd-watch-pr` plus its adapters and default
  housekeeping handoff.
- Generate host-specific structured-question guidance from the shared
  capability contract; do not introduce platform-specific tool names into the
  canonical skill.
- Document router setup detection, optional local-only completion, required and
  explicit-remote failures, stable non-prompting behavior, and setup guidance.
- Update every platform adapter from templates, then run `make sync`.
- Refresh manifest version/provenance expectations, installer audit, source
  map/KB, candidate ledger, and fleet rollout documentation.
- Permit old names only in explicit migration/changelog prose, retired-target
  constants, and retirement tests.

## 7. Validate And Pilot

- Run focused deterministic-check, local provider/receipt, router protocol,
  review lifecycle, retired-target, generated parity, manifest, installer,
  help/catalog, and downstream workflow tests.
- Run formatting/lint/type checks, `make sync`, `make check`, install
  `--check --json`, and full fleet candidate validation.
- Test clean install and upgrade from the last pre-cut release on disposable
  consumers for every supported platform footprint.
- Pilot changes, branch, codebase, and PR scopes; all local/remote overrides;
  eligible local-clean cost reduction; sensitive-change remote floors; no
  duplicate local call; no duplicate remote dispatch; new-head invalidation;
  delayed thread polling; and rollback by version pin.
- Test a router-free optional repository, a required router-free repository, a
  declared-but-disabled/incompatible workflow, unavailable GitHub metadata, and
  an ambiguous post-dispatch result.
- Record provider request count, latency, configured/observed cost tier,
  actionable findings, false positives, and operator pauses before tuning
  policy.
- Force finish-work to create a new head after a clean review and prove that
  the final gate reruns and, when routed integration applies, consumes a new
  router-issued exact-head receipt. Cover policy-allowed bookkeeping-only
  `none`, mixed changes, explicit remote intent, and required floors without a
  local exemption.
- Prove the bookkeeping-only path emits a distinct current-head local-stage
  `skipped` receipt and does not call the provider again, while mixed or
  required-local cases rerun/block and the router independently compares heads.
- Resume the coordinator from serialized states covering pending remote
  materialization, changed head, delayed review, round exhaustion, and an
  unavailable structured-question capability.

## Stop And Rollback Points

- Do not run `task.py start` until the user approves the final PRD/design and
  all product decisions are resolved.
- Do not publish the cutover until router v1, disposable upgrade tests, and the
  coordinated fleet migration are ready.
- Stop if deterministic/local scope identity cannot cover staged, unstaged,
  untracked, deleted, renamed, and disjoint-history cases reproducibly.
- Stop if any remote backend lacks a declared GitHub-observable findings
  channel or durable exact-head receipt.
- Roll back by reinstalling the last pre-cut pack version and compatible
  consumer configuration. Never recreate old aliases inside the new version.
