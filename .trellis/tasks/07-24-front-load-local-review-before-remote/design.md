# Design: Front-load local review before remote PR review

## Architecture And Ownership

The unified `sd-review` controller owns a local-review sub-state-machine between
deterministic readiness and remote routing. `sd-check` remains deterministic and
read-only. `sd-github-review` remains the sole remote routing and dispatch
owner.

This task adds no command surface. It supplies the provider-planning,
concurrency, aggregation, receipt, and reuse behavior consumed by
`sd-review`. The shipping-composition sibling invokes the same local stage
before PR creation when a branch is ready to publish.

## Ordered Lifecycle

For PR-intent work, the controller follows these states:

1. `resolve_target`: determine repository, canonical branch-delta scope, base,
   head, and content digest.
2. `preflight_remote`: when remote review is intended, classify router
   capability without dispatching or mutating GitHub.
3. `check`: run the typed `sd-check` contract.
4. `plan_local`: classify change risk and resolve the policy-selected provider
   set.
5. `run_local`: dispatch all selected providers concurrently into isolated
   attempt directories.
6. `aggregate_local`: validate terminal results, normalize and deduplicate
   findings, retain provenance, and write an aggregate receipt.
7. `remediate_local`: verify and batch approved fixes. Any code change returns
   to `check`; the new scope receives a fresh provider plan and receipt.
8. `publish_or_bind_pr`: the shipping coordinator may create the PR. If the
   canonical review target remains exact, the PR stage consumes the existing
   local receipt without another provider call.
9. `route_remote`: send only the allow-listed local summary and exact target to
   the remote router.
10. `observe_and_remediate`: process remote findings and CI. Code changes return
    to `check` and `plan_local` before another remote request.
11. `final_head`: re-enter exact-head gates for every successor commit. A
    proven bookkeeping-only successor may receive the existing stable skip
    outcome without provider execution.

The state machine persists a versioned transition record so a cancelled or
resumed invocation cannot accidentally duplicate provider or remote calls.

## Provider Plan

`local=auto` resolves to a plan rather than a single provider:

```json
{
  "schemaVersion": 1,
  "scope": "branch_delta",
  "riskClass": "substantive",
  "riskReasons": ["source", "state_contract"],
  "providers": ["prism", "gito"],
  "execution": "parallel",
  "policyId": "default-pr-first-head",
  "configurationDigest": "..."
}
```

The default policy is:

| Situation | Local plan |
| --- | --- |
| First substantive code head | Prism and Gito in parallel |
| Ambiguous classification | Prism and Gito in parallel |
| Documentation or metadata only | Cheapest eligible provider or policy skip |
| Low-risk successor code head | Relevant eligible provider selected by policy |
| Cross-cutting/high-risk successor | Prism and Gito in parallel |
| Repeated finding family | Prism and Gito with the family sibling checklist |
| Proven bookkeeping-only successor | Stable bookkeeping-successor skip |
| Explicit provider/all/none | Honor the explicit selection subject to policy |

Configuration can tighten the minimum set or data-handling policy. It cannot
silently downgrade a required set because a provider is unavailable. Provider
unavailability is an outcome handled after planning, not an invitation to
rewrite the plan.

## Concurrent Provider Execution

The controller creates one attempt record and artifact directory per provider,
then starts all planned adapters without waiting for earlier providers. Each
adapter receives a validated argv array, immutable target descriptor, bounded
review-learning summary, timeout, and its own stdout/stderr handles.

Aggregation waits for every attempt to become `clean`, `findings`,
`unavailable`, `failed`, or `cancelled`. Cancellation is propagated explicitly,
but partial output never becomes a clean result. A provider crash cannot delete
or overwrite a peer's artifact.

## Findings Aggregation And Remediation

Provider-native findings remain immutable source evidence. A normalized view
adds stable provider identity, path/line when present, severity, summary,
finding family, verification result, and disposition. Deduplication groups
overlapping candidates but retains every contributing provider.

The controller verifies candidates before editing and presents or auto-applies
one combined fix batch under the parent `fix` policy. Any remaining actionable
finding blocks remote dispatch. A code-changing fix invalidates the aggregate
receipt and starts a fresh exact-scope local stage after `sd-check`.

## Exact-Scope Receipt And PR Reuse

The local receipt records the invocation context separately from the canonical
review target. Both pre-publication branch review and the local part of PR
review use `branch_delta` as the canonical target, with exact repository, base
OID, head OID, path manifest, content digest, provider plan, adapter versions,
configuration digest, and policy digest.

Creating a PR changes invocation context but not necessarily the canonical
target. The PR stage reuses the receipt only when every target and provider-plan
field matches. A changed base branch, merge base, head, diff byte, adapter,
configuration, or policy creates a new receipt and provider run.

Code-changing successor heads never reuse prior positive confidence. They may
use prior finding families as routing input, but the selected providers review
the complete new canonical scope. Only the separately proven
`bookkeeping-successor` path may skip provider execution.

## Remote Boundary

The remote router receives an allow-listed summary: exact repository/base/head,
aggregate local outcome, provider identifiers and cost/quality classes,
finding/disposition counts, bounded confidence, receipt identity, and material
limitations. It receives no source, raw provider output, credentials, local
paths, prompts, or transcripts.

Remote routing cannot begin while the local state is non-terminal or has
outstanding actionable findings. Provider failure follows the parent policy:
the router may receive explicit partial or zero local confidence when local
review is optional, while a required local floor fails closed.

## Compatibility And Migration

The implementation lands only in the successor `sd-review` controller and its
versioned review configuration. The existing sequential local runner is
evidence and possible adapter code to extract, not a compatibility boundary.
Legacy commands, environment variables, and helpers are removed by the
retirement child after all callers use the new controller.

The parent PRD/design are reconciled in the same planning batch to define
`local=auto` as a provider plan rather than exactly one provider. Before this
task starts implementation, confirm that those parent requirements still match
this design instead of reopening the settled product decision.

## Operational And Rollback Considerations

- Concurrency is bounded by the selected plan; it never expands beyond the
  configured eligible providers.
- Durable attempt IDs and atomic receipts prevent duplicate billing after
  cancellation or resume.
- Per-provider latency and cost classes expose whether the first-head ensemble
  is worthwhile without inventing avoided-round counts.
- Rollback reinstalls the last pre-unified-review pack release. There is no
  runtime fallback to the legacy command surface.
