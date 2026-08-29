# Design: Separate repositories with a staged review protocol

## Boundary

Repository boundaries follow product and release ownership, not the fact that
the products collaborate at runtime.

| Owner | Responsibility |
| --- | --- |
| `sd-ai-command-pack` | Deterministic gates, local-provider policy and execution, exact-scope local receipts, remediation, remote-receipt consumption, repeated exact-head rounds, and the user-facing lifecycle |
| `sd-github-review` | Remote risk/cost/quality policy, explicit remote overrides, backend selection, exactly-once dispatch, and a durable versioned remote receipt |
| Local provider adapter | Checkout-scope capability, provider invocation, normalized result classification, and local-only raw artifacts |
| Remote backend adapter | Provider credentials and invocation plus GitHub-observable findings through declared channels |

Moving both products into one Git repository would not remove the runtime
boundary: local review can operate on checkout state that GitHub cannot see,
while the router and remote providers run against a published PR head. The
integration point should therefore be a small bounded summary, not shared
provider internals.

## End-To-End Flow

1. `sd-review` resolves `scope=auto|changes|branch|codebase|pr`. Auto chooses PR
   scope when an open PR is unambiguously bound to the branch; otherwise it
   chooses local changes or the branch delta.
2. In PR scope, unless `remote=none`, `sd-review` performs a read-only router
   capability preflight before any provider call or GitHub mutation. It
   distinguishes ready, truly absent, declared-invalid, and unavailable setup.
3. In PR scope, `sd-review` invokes the deterministic `sd-check` contract with
   no AI-provider or GitHub-review side effect. `sd-check` is also independently
   available to users, CI, and other delivery skills.
4. The pack selects local mode `auto` or an explicit local override, invokes the
   shared local-review engine, and records an exact-scope local receipt. In
   `auto`, it runs the lowest-cost configured provider that satisfies the
   required scope, data-handling, and capability policy; `all` remains an
   explicit diagnostic choice.
5. Local findings are dispositioned through the command-pack remediation loop.
   Any content change invalidates the receipt and returns to the deterministic
   gate and local-review stage. Fixing defaults to automatic for changes,
   branch, and PR scopes and confirmation-first for codebase scope; destructive,
   ambiguous, out-of-scope, architecture, dependency, product-behavior, and
   policy changes always require confirmation.
6. Only when router capability is ready and the local stage is clean, has fully
   dispositioned findings, is unavailable under allowed policy, or is explicitly
   disabled does the pack send an exact-head remote routing request. It includes
   only a bounded local outcome summary, never raw source, prompts, findings, or
   transcripts.
7. `sd-github-review` validates the current PR head and local-summary identity,
   then selects `none`, `cheap`, `deep`, or `copilot` subject to the repository's
   configured minimum-review floor and any explicit remote override.
8. The router dispatches exactly once for that head and publishes a durable
   receipt containing selection, dispatch, and observation metadata without
   credentials or raw findings.
9. The command pack validates identity and schema, then watches the declared
   GitHub-visible review, comment, and check channels.
10. Unified `sd-review` logic classifies findings, replies to or resolves
   threads, fixes valid issues, and pushes one focused review-round commit.
11. A new head or checkout-content change invalidates all prior local and remote
    evidence. For a ready/required integration, the pack sends a new routing
    request that may reference the validated prior router receipt. The router
    may issue a new exact-head `none` receipt for a trusted bookkeeping-only
    successor when policy permits; the pack never reuses or locally exempts the
    prior receipt. Pack-owned local policy may emit a distinct current-head
    `skipped:bookkeeping-successor` local-stage receipt with zero new confidence
    instead of rebilling a provider; the router independently verifies the
    GitHub delta. Final thread and CI gates remain backend-independent.

## Local Review Contract

`sd-review` is the only public review entry point. Scope selects worktree,
branch, whole-codebase, or PR behavior; one engine invokes Prism, Gito, custom
providers, and routed remote review. `sd-check` is deterministic verification,
not an AI review lane. It shares low-level repository inspection helpers where
useful but never invokes a local or remote reviewer.

The local receipt records:

- schema and invocation identity;
- repository identity, scope kind, base and head OIDs, clean/dirty state, and a
  canonical digest covering the reviewed staged, unstaged, untracked, branch,
  or codebase content;
- selected providers, adapter/provider versions, configuration digest,
  declared capability and cost tier;
- outcome (`clean`, `findings`, `unavailable`, `failed`, or `cancelled`),
  disposition counts, bounded confidence, start/completion times, and latency;
- local-only artifact references for raw output.

Reuse is allowed only when repository, scope digest, base/head, provider,
adapter version, and configuration digest all match. Provider findings are not
the same as provider failure or missing configuration; the normalized outcome
must preserve that distinction.

## Cost And Privacy Policy

`local` describes execution context, not price or connectivity. Provider
profiles declare availability, supported scopes, data-handling class, cost
tier, quality tier, timeout, and adapter version. Presence of an executable
alone is not sufficient authorization for an undisclosed paid/network call.

A high-confidence, exact-head local-clean result may reduce the remote tier or
allow `none` only within repository policy. It cannot bypass the configured
minimum for sensitive paths, large changes, or required independent review.
Missing, failed, stale, or low-confidence local evidence never increases
confidence or triggers a silent expensive fallback.

The router is noninteractive and never checks out or executes PR-controlled
code. Structured user questions, when supported, occur in the command-pack UX
before request construction; ambiguous router configuration or state is a
typed failure rather than a prompt.

## Router Absence And Failure

An undeclared router is a supported optional-adoption state, not an error. With
`remote=auto`, the pack completes deterministic/local review, reads existing
GitHub feedback, threads, and CI, and reports `remote=not-configured` plus setup
guidance without prompting. Explicit remote intent or a repository-level
`required` integration stops before provider calls or mutation. `remote=none`
always runs the intentional local-only path, while reporting any unmet required
remote merge gate. If the selected local provider fails during optional absence,
the run stops rather than claiming that a local-only review completed; an
explicit `local=none` remains an intentional recorded skip.

Declared-invalid, disabled, incompatible, unreadable, failed, or ambiguously
dispatched router state is not absence. Those states fail closed and never
trigger direct Copilot/custom dispatch or a second router request.

## Clean-Cut Contract

- Start at local-receipt schema v1 and routed request/receipt schema v1; reject
  unknown major versions.
- Publish canonical remote fixtures in `sd-github-review` and matching consumer
  fixtures here. Keep the local receipt and provider-adapter contract pack-owned.
- Publish a canonical router setup descriptor and validate it through a
  side-effect-free capability preflight before remote-capable review begins.
- Bind remote evidence to owner, repository, PR number, and full head SHA. Bind
  local evidence to the stronger checkout-scope identity above.
- Keep one remote request owner: `sd-github-review`. The command pack has no
  direct Copilot/custom-reviewer dispatch path.
- Remove `sd-full-check`, `sd-review-local`, and `sd-review-pr` skills, platform
  adapters, helper scripts, manifest targets, help entries, documentation, and
  environment-variable/configuration contracts.
- Add no aliases, redirecting skills, forwarding scripts, or legacy config
  readers. Installer refresh treats the old pack-owned paths as retired:
  unchanged vouched files are deleted, locally modified files are preserved and
  reported, and old paths never appear in the new receipt or provenance.
- Update `sd-create-pr`, `sd-ship`, `sd-work-backlog`, help/catalog data, docs,
  tests, and fleet checks atomically with the new surface.

## User Experience

The approved public surface is:

- `sd-check`: deterministic verification only;
- `sd-review scope=auto|changes|branch|codebase|pr
  local=auto|<provider>|all|none remote=auto|cheap|deep|copilot|none
  fix=auto|ask|none`.

Natural-language invocations map to the same typed options. All platforms expose
one review skill/command rather than separate local and PR adapters.

Changes, branch, and codebase review may edit and verify approved fixes but
never stage, commit, or push. PR review stages only intended paths, creates one
focused commit per verified round after `sd-check`, and pushes automatically so
the exact-head lifecycle can continue.

The stable experience is one staged funnel, one remediation loop, one
exact-head clean decision, and one report shape. Reports name every provider,
show which stages ran or were reused, disclose cost tier and latency, and
surface missing capabilities. Backend opacity is not a goal.

## Invalidation Conditions

Reconsider a monorepo only if implementation demonstrates that stable receipts
cannot represent the required state, releases must be atomic across both
products, or shared mutable source becomes unavoidable. Ordinary schema
versioning, fixtures, and compatibility tests are not such evidence.

## Rollout And Rollback

Freeze the bounded local-summary field with the router contract, then land and
pilot router v1 before the command-pack cutover. The command-pack release adds
the new surface and retires the old one in a single version; fleet rollout
updates owning workflow references and router configuration together. There is
no in-version compatibility mode. Repositories without a router declaration use
the new optional local-only state, not old dispatch behavior. Rollback means
reinstalling the last pre-cut pack version and its matching consumer
configuration, not activating dormant legacy code in the new release.
