# Implement the unified routed sd-review command Design

## Overview

Add one generated `sd-review` command backed by a shipped Python coordinator.
The coordinator composes the existing typed `sd-check` helper, the completed
exact-scope local-review stage, and the released `sd-github-review` v1 durable
workflow contract. It owns deterministic lifecycle transitions and bounded
receipts; the skill owns evidence-led finding disposition and the few decisions
that require user judgment.

This task introduces the successor surface without calling the legacy review
skills. The separate `remove-retired-review-surfaces` task owns deletion of
those old public surfaces after callers have migrated.

## Proposal

### Public command and executable boundary

Register `sd-review` once in `installer/registry.py`, author its neutral source
under `.github/command-sources/`, and generate every platform adapter. The
canonical skill accepts:

- `scope=auto|changes|branch|codebase|pr`;
- `local=auto|<provider>|all|none`;
- `remote=auto|cheap|deep|copilot|none`;
- `fix=auto|ask|none`; and
- an optional explicit PR number.

The skill invokes `scripts/sd-ai-command-pack-review.py` through the pack
toolchain wrapper. It does not reconstruct scope, provider, router, receipt, or
polling policy in prose.

### Coordinator state machine

The coordinator uses these persisted states:

`resolve -> capability -> check -> local -> local-disposition -> route ->
observe -> remote-disposition -> ready|blocked|failed`.

State is written atomically below the ignored pack review artifact root and is
bound to repository identity, normalized controls, canonical target, base/head,
scope digest, configuration digest, attempt, local receipt, router request
fingerprint, durable receipt, and bounded finding/CI/thread summaries. A resume
revalidates every non-null identity before advancing. A new worktree digest or
PR head invalidates readiness and starts a new attempt; an uncertain dispatch
enters `reconciliation-required` and never retries through a direct fallback.

### Scope and deterministic check

`auto` chooses one unambiguous current-branch PR, otherwise dirty worktree
changes, otherwise the current branch delta. It never infers `codebase`.
Changes, branch, and codebase remain worktree-only. PR scope requires a clean
worktree, exact local/remote head agreement, and the typed `sd-check` result
before any review dispatch.

The coordinator delegates exact scope hashing and local receipt reuse to
`sd-ai-command-pack-review-local.py`. It consumes that helper's typed status,
receipt, remote gate, and allow-listed remote summary. It never invokes local
provider commands itself and never accepts shell-string provider configuration.

### Router discovery and durable operation

For PR scope with `remote != none`, capability discovery combines:

1. the review configuration's `optional|required` integration policy;
2. a repository-owned `config/routed-review-setup-v1.json` declaration; and
3. read-only GitHub workflow metadata for the declared workflow path/name.

The setup descriptor must be regular UTF-8 JSON, schema/contract major 1,
noninteractive, checkout-free, support the requested intent and `route`, and
declare the durable `sd-github-review/receipt` check. The action reference and
workflow metadata must agree. Classification is `ready`, `absent`, `invalid`,
`incompatible`, or `unavailable`.

When ready, the coordinator builds only the canonical v1 `review-request`:
repository, PR, exact head, intent, attempt, correlation ID, policy identity,
and the allow-listed local summary. It invokes the declared GitHub
`workflow_dispatch` with `gh workflow run`, then observes the durable check
receipt and declared finding channels. It never requests Copilot directly,
matches a hard-coded reviewer as policy, or executes a backend command supplied
by a receipt.

The controller validates the returned receipt's schema, repository, PR, head,
attempt, route, dispatch identity/status, backend channels, and limitations.
Query/reconciliation reuses the same request fingerprint and attempt. A
same-head rerequest is possible only when the prior receipt and repository
policy explicitly permit it.

### Findings, CI, and threads

Local findings come from the local receipt. Remote findings come only from the
receipt-declared GitHub review, inline-thread, conversation-comment, or check
channels. The coordinator performs bounded paginated GraphQL/thread reads and
typed `gh pr checks` observation, records stable identities and family data,
and returns an action bundle to the skill.

The skill verifies findings against the checkout and applies `fix=auto` only to
ordinary in-scope low-risk fixes. Scope expansion, higher-risk changes, or an
extra round use the registered structured decisions. Addressed or rebutted
threads are replied to and resolved under standing authority. Any code change
must pass `sd-check`, become a focused PR-scope commit/push, and re-enter the
coordinator as a new exact head. Non-PR fixes are never staged or pushed.

### Configuration and reporting

Extend the versioned `.sd-ai-command-pack/review.json` contract with an
optional `remoteIntegration` object while keeping the existing provider and
policy fields canonical. Supported fields are bounded integration requirement,
descriptor path, and observation/round limits. Unknown fields or unsafe paths
fail closed.

One schema-version-1 report includes controls, canonical target, attempt/state,
typed check result, local provider plan and run/reuse receipt, router capability,
remote route/receipt, cost and latency, finding dispositions, CI/thread state,
exact-head readiness, limitations, and a stable exit status.

## Boundaries And Non-Goals

- Do not merge the command-pack and router repositories.
- Do not copy router backend policy or provider secrets into this repository.
- Do not remove legacy public surfaces in this task or use them as fallbacks.
- Do not make `sd-check` invoke a model, GitHub mutation, or generated refresh.
- Do not merge, archive Trellis work, or make housekeeping decisions from the
  review coordinator.
- Do not claim clean review from unavailable, failed, cancelled, malformed, or
  reconciliation-required provider state.

## Affected Files

- `templates/scripts/sd-ai-command-pack-review.py` and root mirror;
- `templates/scripts/sd-ai-command-pack-review-local.py` and root mirror for the
  shared review-configuration extension;
- `templates/.agents/skills/sd-review/SKILL.md` and generated platform adapters;
- `.github/command-sources/sd-review.md`;
- `installer/registry.py`, manifest/provenance, help catalog, README, installed
  guide, changelog, and release candidate ledger;
- focused controller, protocol, configuration, generation, installation, and
  surface-closure tests.

## Data And Command Contracts

- All Git/GitHub/provider commands are argv arrays executed through the shared
  toolchain/cache boundary.
- Router request and receipt schema major is 1. Unknown major versions fail.
- Descriptors, state, reports, and receipts are bounded strict UTF-8 JSON.
- State writes use private ignored directories, sibling temporary files, flush,
  fsync, and atomic replacement.
- Repository paths must be contained regular files without symlink traversal.
- Correlation IDs trace attempts; normalized request fingerprints and logical
  dispatch IDs provide idempotency.
- Raw source, prompts, provider transcripts, credentials, local paths, and raw
  findings never enter the remote request.

## Risks And Edge Cases

- GitHub workflow dispatch has no synchronous receipt response, so observation
  must tolerate delayed Check Run materialization and page through declared
  channels without duplicating dispatch.
- A provider or GitHub command may fail after a side effect. Persist intent
  before dispatch and require durable receipt reconciliation afterward.
- PR creation may preserve an exact branch target; receipt reuse is allowed only
  when every target and provider-plan field remains equal.
- Bookkeeping-only successor classification is local evidence only. The router
  independently decides whether a new exact-head remote receipt may route to
  `none`.
- Optional absent routing is a visible local-only completion; invalid,
  incompatible, unavailable, explicit, or required states fail closed according
  to the approved matrix.
- Bounded observation expiry returns a resumable pending result rather than a
  false clean verdict.

## Validation

- Unit and subprocess fixtures for every scope/control combination, exact reuse
  and invalidation field, configuration error, provider outcome, router
  capability state, request/receipt fixture, dispatch ambiguity, delayed and
  paginated observation, CI/thread state, successor head, family gate, and
  round extension.
- Root/template parity, generated adapters, registry/help catalog, manifest,
  install/update/audit, surface closure, and shipped-script coverage.
- `make sync`, typed `sd-check`, full fleet candidate validation, and
  `make check` on the final feature head.

## Focused First-Review Risk Evidence

This task intentionally delivers one state-machine controller and its public
surface as an atomic outcome. Splitting the controller, configuration parser,
generated adapters, and protocol fixtures across PRs would leave an exposed
partial lifecycle; legacy-surface removal and caller migration remain separate
follow-up tasks.

The first-review boundary matrix is covered as follows:

- Structured inputs and strict types: valid/default configuration fixtures plus
  malformed containers, unknown keys, unsafe booleans-as-integers, and bounded
  scalar failures.
- Paths and filesystem boundaries: regular contained descriptors and private
  atomic state plus missing, traversal, symlink, oversize, and changed-byte
  invalidation fixtures.
- Normalization and canonical evidence: stable configuration digests, scope
  bytes, request fingerprints, receipt identity, and exact-head comparisons,
  with malformed or noncanonical evidence failing closed.
- Diagnostic fidelity and redaction: bounded stable failure/limitation fields
  are asserted without raw prompts, provider transcripts, credentials, or host
  paths entering router requests or durable state.

Focused controller, local-stage, install, generated-surface, shipped-coverage,
and full-fleet candidate checks must pass before the first remote review.
