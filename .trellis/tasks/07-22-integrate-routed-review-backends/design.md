# Design: Clean check and unified review surface

## Public Interface

The approved public surface has two orthogonal skills:

| Skill | Purpose | AI or GitHub side effects |
| --- | --- | --- |
| `sd-check` | Deterministic verification, readiness, scope, and preflight gates | None |
| `sd-review` | Worktree, branch, codebase, or PR review with local and optional routed-remote stages | Explicitly reported provider calls |

`sd-review` accepts one typed contract across all platform adapters:

- `scope=auto|changes|branch|codebase|pr`;
- `local=auto|<provider>|all|none`;
- `remote=auto|cheap|deep|copilot|none`;
- `fix=auto|ask|none`; and
- an explicit PR selector when branch discovery is insufficient.

Auto scope uses PR mode only for one unambiguous open PR bound to the branch or
an explicit selector. Otherwise it reviews dirty worktree content, or the
branch delta when clean. Codebase scope is never inferred.

The old `sd-full-check`, `sd-review-local`, and `sd-review-pr` names do not
remain as aliases or hidden compatibility modes.

## Components

- A deterministic check coordinator replaces the public full-check skill,
  script, review selector, and `package.json` `check:full` hook. It may reuse
  existing low-level check helpers but contains no local or remote AI lane.
- One review coordinator resolves scope, selects local provider adapters,
  records structured outcomes/receipts, drives remediation, calls the remote
  router in PR scope, and produces the final report.
- Local provider adapters encapsulate Prism, Gito, and configured custom tools.
  They classify native output into one normalized result contract and retain
  raw output only in ignored local artifacts.
- A remote protocol helper validates routed request/receipt JSON, exact-head
  identity, supported schema, and exactly-once dispatch evidence.
- Existing GitHub review, inline-comment, conversation-comment, check, thread,
  and CI readers remain the common remote findings plane behind the coordinator.
- `.sd-ai-command-pack/review.json` is the versioned pack-owned local provider
  profile/default configuration. Its remote-integration stanza declares only
  `optional|required` availability policy, workflow identity, and contract
  major. `.sd-ai-command-pack/check.json` defines repository-specific
  deterministic prerequisites and commands as validated argument arrays. Remote
  risk, backend selection, and dispatch policy remain router-owned.

The review coordinator, remote protocol helper, and shared PR eligibility gate
exchange versioned JSON. Skills may interpret their output and decide whether a
finding is valid, but provider transport, polling, head reconciliation, retry
accounting, and readiness are executable state transitions rather than prompt
memory.

## Deterministic Mutation Boundary

`sd-check` snapshots relevant repository state before running and has no
refresh path. Stale generated knowledge, maps, manifests, or receipts are
reported as deterministic findings with an owning remediation command. The
coordinator does not call `sd-update-spec`, knowledge refresh, Git mutation, or
GitHub mutation implicitly.

## Review State Machine

`resolve-scope -> router-capability-preflight-if-pr-and-not-none ->
deterministic-check-if-pr -> successor-local-policy-if-applicable ->
(local-skip | local-select -> local-review -> local-disposition) ->
remote-route-if-ready -> remote-receipt -> remote-materialize ->
remote-disposition -> exact-scope-or-head-clean`.

- `local=none` and `remote=none` are explicit recorded skips.
- Provider unavailability is not silently treated as clean and never triggers
  an unannounced more-expensive fallback.
- Outstanding local findings block remote routing. Fully dispositioned findings
  may proceed with their disposition counts and bounded confidence.
- Any local fix or checkout-content change returns to deterministic/local
  stages. Any new PR head invalidates local and remote receipts plus
  materialization evidence.
- Dirty worktree evidence is valid for local scope but cannot influence routing
  for a published PR head until committed and reviewed under that head.

## Local Provider Selection

Provider profiles declare:

- adapter ID and optional validated argument array;
- supported `changes`, `branch`, and `codebase` scopes;
- network/data-handling class;
- configured cost and quality tiers;
- timeout/retry policy; and
- adapter/provider version.

Custom providers use argv arrays or a bounded executable adapter. The clean
contract does not accept legacy shell-string environment commands.

In `local=auto`, choose one available provider with the lowest configured cost
tier that satisfies scope, data policy, required capability, and minimum
quality. Deterministic tie-breaking is configuration order. `all` deliberately
runs every eligible provider and reports each result.

Executable presence alone does not authorize a paid or network call. The
provider must be enabled by the versioned review configuration or explicit
invocation.

## Local Receipt Schema

Local receipt v1 contains:

- schema version, invocation/correlation ID, repository identity, and timestamp;
- scope kind, base OID, head OID, clean/dirty flag, reviewed path manifest, and
  canonical content digest covering applicable staged, unstaged, untracked,
  branch, or tracked-codebase bytes;
- selected providers and attempted order, adapter/provider versions,
  configuration digest, and declared capability/data/cost/quality metadata;
- local-stage `clean|findings|unavailable|failed|cancelled|skipped` outcome and
  stable reason;
- per-attempt provider `clean|findings|unavailable|failed|cancelled` outcome,
  diagnostic category, bounded confidence, timing, and latency when attempted;
- optional prior local-receipt identity and exact successor-delta digest for a
  current-head `skipped:bookkeeping-successor` result;
- severity and disposition counts; and
- local-only raw artifact references.

Receipts are written atomically under one ignored pack-managed review artifact
directory. Reuse requires an exact match on repository, scope, content digest,
base/head, provider set/order, adapter/provider versions, and configuration
digest. Unknown schema majors, partial writes, or missing identity fail closed.

The command-line process status remains a small orchestration status, but
lifecycle decisions consume structured per-provider outcomes so findings are
never conflated with provider/configuration failure.

## Remote Routing Boundary

PR scope sends:

- owner/repository, PR number, and full head SHA;
- stable logical dispatch identity, normalized request fingerprint, attempt,
  and a tracing correlation ID;
- `auto|cheap|deep|copilot|none` remote intent;
- trusted deterministic evidence; and
- an allow-listed local summary from a clean or fully dispositioned exact-head
  receipt: receipt/schema identity, provider IDs/capability tiers, normalized
  outcome/disposition counts, bounded confidence, latency/cost tier, and scope
  digest.

The request never contains paths, source, prompts, raw findings, transcripts,
credentials, configuration values, or local artifacts. The router validates
identity and applies repository review floors before selecting a backend.

The returned receipt declares backend, route reason, cost/model tier, dispatch
state and timestamps, workflow URL, reviewer/check identities, finding
channels, idempotency/rerequest capability, and limitations. Unknown major
versions, stale heads, contradictory dispatch, and hostile values fail closed.
The command pack never executes commands supplied by a receipt.

The coordinator persists the logical dispatch identity and normalized request
fingerprint before dispatch and reuses them across retries, restarts, and
replacement tracing correlations. A conflicting retry fingerprint fails
closed. A same-head rerequest uses an explicit prior receipt and next attempt
and is sent only when the receipt declares support and repository policy
authorizes it.

## Router Capability And Fallback

PR scope performs a read-only capability preflight before any review-provider
call or GitHub mutation unless `remote=none`. It combines the versioned local
integration stanza with live GitHub workflow metadata and the router's canonical
setup descriptor:

- `ready`: the declared workflow is enabled and exposes a compatible contract;
- `absent`: no integration stanza or workflow declares router ownership and no
  dispatch was attempted;
- `invalid`: a declared workflow is missing, disabled, or incompatible; and
- `unavailable`: GitHub state cannot be read strongly enough to classify it.

No integration stanza defaults to optional `absent`. This default governs only
whether remote integration is required; it does not copy backend routing policy
into the command pack.

| Intent and policy | Capability | Behavior |
| --- | --- | --- |
| `remote=auto`, optional | `absent` | Run deterministic/local review and inspect existing GitHub feedback, threads, and CI without prompting. Report `remote=not-configured`, setup guidance, and zero remote confidence. |
| `remote=auto`, required | `absent` | Stop before provider calls or mutation with setup guidance. |
| `remote=cheap|deep|copilot` | `absent` | Stop early because the requested remote result cannot be supplied. |
| `remote=none` | any | Run the intentional local-only path without probing or dispatching. If remote integration is required, report that merge readiness remains unmet. |
| Routed intent | `invalid` or `unavailable` | Fail closed; do not reinterpret configuration drift or an unreadable state as absence. |
| Routed request started | failed, missing receipt, or ambiguous | Stop and reconcile the durable receipt/idempotency state. Never dispatch a direct or second reviewer request. |

The local-only fallback is a normal completion mode only for optional absence.
It does not invent remote policy, claim independent remote review, or repeatedly
ask for provider approval.

## Findings And Remediation

One coordinator normalizes local findings and GitHub-observable remote findings
into the existing evidence-led remediation workflow. Reports preserve the
provider-native detail and channel; normalized lifecycle state does not claim
identical reviewer prose or quality.

The approved default is `fix=auto` for changes, branch, and PR scope, and
`fix=ask` for codebase scope. Auto mode fixes clearly valid in-scope findings
under the same standing authority regardless of local or remote source, then
reruns from the appropriate deterministic/local stage. Ambiguous, destructive,
out-of-scope, architecture, dependency, product-behavior, or policy-changing
changes require user input in every mode. `fix=none` records findings without
editing.

## Provider Failure Policy

The approved PR behavior is to record a configured provider's `unavailable` or
`failed` result and, when router capability is ready, continue to remote routing
without positive local confidence unless repository policy declares local review
required. The router then applies its normal independent-review floor; the
command pack does not silently select a different, more expensive local
provider.

When router capability is optional `absent`, a selected local provider's
unavailable/failed result stops because no review provider remains. An explicit
`local=none` is still honored and reported as an intentional skip.

In changes, branch, or codebase scope there is no remote review stage, so a
requested provider's unavailable/failed result stops the command with its
normalized diagnostic.

## Mutation And Publishing Boundary

The approved boundary keeps non-PR review worktree-local: changes, branch, and
codebase scopes may apply and verify approved fixes but never stage, commit, or
push. PR scope stages only intended review-fix paths, creates one focused commit
per verified round, and pushes so the exact-head local and remote cycle can
continue. Unrelated or ambiguous paths are never staged.

## Final-Head Completion

Every commit invalidates the previous completion verdict. After review fixes or
finish-work bookkeeping, `sd-ship` re-enters the shared exact-head eligibility
flow. The normal path reruns relevant deterministic/CI/thread evidence and, for
a ready or required routed integration, requests a new router decision for the
new head. The request may carry the validated prior router receipt through the
versioned `supersedes` field; the router independently compares the heads and
may issue a new current-head `none` receipt for a policy-allowed
bookkeeping-only delta. Unknown, mixed,
explicit-remote, required-floor, or non-comparable changes take the normal
review route. The command pack never creates a local exemption or treats the
prior receipt as current-head evidence.

Separately, pack-owned local policy may avoid rerunning a local provider for an
exact finish-work-only successor. It emits a distinct receipt bound to the new
head with outcome `skipped`, reason `bookkeeping-successor`, prior local receipt
identity, exact delta digest, and zero new confidence. Mixed changes,
unverifiable finish-work evidence, or required-local policy cannot use this
path. The router does not trust this local classification; it performs its own
GitHub comparison for the remote decision.

## Command Composition

- `sd-create-pr`: publish or reuse one PR and return its identity.
- `sd-review`: own review state, remediation, and exact-head review evidence.
- `sd-ship`: compose PR creation, review, finish-work, final-head re-entry, and
  housekeeping.
- `sd-housekeeping`: consume eligibility and remain the only merge mutation
  owner.

`sd-watch-pr` is removed. The coordinator may expose an internal read-only wait
operation, but it cannot merge or hand off to housekeeping implicitly.

## Interaction Contract

The canonical skill names decision categories, recommendations, and safe
fallback behavior. Generated adapters select the host-native structured tool
when available. Review uses questions for scope expansion, higher-risk fixes,
finding batch selection, or an explicit round-budget extension. It does not ask
for optional-router absence, normal low-risk fixes, bounded waits, or actions
already covered by the command's authority.

## Removal And Installer Retirement

The cutover removes every live old surface:

- source templates and generated copies for the three old skills and all
  platform adapters;
- old review/full-check orchestration scripts and manifest targets;
- old environment-variable/configuration documentation and parsers;
- the `package.json` `check:full` selector convention, review-full-check helper,
  and full-check package-runner controls;
- help catalog/examples and README/guide sections; and
- direct references in `sd-create-pr`, `sd-ship`, `sd-work-backlog`, audit,
  tests, and fleet tooling.

All old pack-owned target paths enter the existing retired-target registry.
Normal refresh deletes only vouched unchanged copies and prunes empty
directories. Drifted or unverifiable copies are preserved and reported, but
they are not treated as installed/discoverable new-pack commands. No redirecting
skill, compatibility script, alias, or legacy configuration reader is added.

Historical changelog, migration notes, and retirement tests may name the old
commands; live help, docs, manifest entries, and runtime code may not.

## Reporting

One review report lists:

- resolved scope and exact identity;
- deterministic check result when applicable;
- local provider selection, run versus receipt reuse, outcome/disposition,
  configured cost tier, latency, and artifact reference;
- remote route/backend, reason, configured/observed cost tier, latency,
  workflow URL, finding channels, and limitations;
- router capability state, integration requirement, local-only fallback reason,
  setup guidance when absent, and whether remote merge readiness was satisfied;
  and
- exact-scope/head completion, CI, and unresolved-thread state.

## Release And Rollback

Router v1 lands and pilots first. The command-pack cutover then ships the new
surface, dependent skill updates, retired-target registry, and fleet migration
as one release. Consumers without a router declaration enter the documented
optional local-only state rather than a legacy dispatch path. There is no
dual-surface transition release.

Consumers refresh the pack and router configuration together. Rollback pins and
reinstalls the last pre-cut command-pack version and matching consumer
configuration; the new release contains no dormant legacy path to reactivate.
