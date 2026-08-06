# sd-review reports an all-excluded local diff as a provider failure

## Goal

Let `sd-review` distinguish "the local provider had nothing in scope" from "the
local provider failed", so a diff whose every path is excluded by provider
configuration does not fail the review stage closed.

## Problem

A local provider that is handed a diff with no reviewable files exits 0 and
produces no structured report. The coordinator classifies that as
`status: failed` for the provider, and the failure propagates:

```text
local provider failure blocks remote routing
```

Because an `absent` optional router may complete only on a *clean* local
receipt, there is then no way through with the skill's public controls. Observed
on PR #339, whose four changed paths were all under `.trellis/tasks/` while
`.gito/config.toml` excluded `.trellis/**`:

| controls | status | diagnostic |
|---|---|---|
| `local=auto remote=auto` | `failed` | local provider failure blocks remote routing |
| `local=none remote=auto` | `indeterminate` | optional router absence requires a clean local review |
| `local=none remote=copilot` | `blocked` | routed review is required or explicit but is not configured |

The deterministic `sd-check` gate passed in all three. Only the local lane was
stuck, and only because it had nothing to look at.

Evidence that the diff was empty rather than the provider broken: gito exited 0
in 1308 ms having logged only its bootstrap and merge-base diff. A real review
call on the same repository takes 6–15 s. After the exclusion was narrowed in
0.64.21, the identical invocation returned `clean` in 15384 ms with 0 findings.

### Why this is not merely a configuration mistake

0.64.21 narrowed `.gito/config.toml` so this specific collision stops happening,
but the failure mode is a property of the coordinator, not of one exclusion
list. Any repository whose provider configuration excludes a coherent area of
the tree — vendored code, generated assets, documentation — can produce a PR
confined to that area, and it will fail the review stage closed for a reason the
diagnostic does not name. The operator sees "provider failure" and has no signal
that the real cause is an empty scope.

## Requirements

### Functional

- R1: an all-excluded local diff must be a distinct, typed outcome — not
  `failed`. The receipt must say the provider had nothing in scope.
- R2: that outcome must not fail the review stage closed on its own. With an
  `absent` optional router, a not-applicable local lane should be able to
  complete, carrying an explicit limitation rather than a failure.
- R3: R2 must not become a way to skip review. A provider that genuinely fails,
  times out, crashes, or returns malformed output keeps failing closed exactly
  as today. The distinction must rest on evidence that the scope was empty, not
  on the absence of findings.
- R4: the diagnostic must name the cause and the remediation — which
  configuration excluded every path — so the operator is not left inferring it
  from a duration.

## Constraints

- Do not weaken the deterministic `sd-check` gate, which is unrelated and
  already passes in this scenario.
- Do not make `local=none` the sanctioned escape. It is a documented control,
  but it produces `local-skipped`, which is deliberately not clean; blurring
  that would let a real review be skipped by argument.
- The determination must be made from the provider's own inputs, not from
  parsing provider log text. Duration was decisive evidence for a human here,
  but it is not a contract.

## Open questions (resolve in design)

- Where does the empty-scope determination belong: the coordinator computing the
  post-exclusion file set before dispatch, or each provider adapter reporting a
  typed "no files in scope" result? The former needs the coordinator to
  understand every provider's exclusion syntax; the latter needs every adapter
  to distinguish it, and gito currently does not.
- Does the same hole exist for the other provider (`prism`), and for the
  `worktree` and `codebase` scopes as well as `branch_delta`?
- Should an all-excluded diff still be recorded in the durable receipt as an
  attempt, for cost accounting and for the review-round counters?
- Interaction with the family gate and `roundsAvoided`: does a not-applicable
  lane count as a round?

## Acceptance Criteria

- [ ] A PR whose every changed path is excluded by the configured local provider
      yields a typed not-applicable local outcome, not `failed`.
- [ ] With that outcome and an `absent` optional router, `sd-review scope=pr`
      completes with an explicit limitation naming the empty scope, and
      `exactHeadReady` is true.
- [ ] A provider that exits nonzero, times out, or returns malformed output
      still fails closed; a test asserts each of those separately from the
      empty-scope case.
- [ ] The reported diagnostic names the configuration that excluded every path.
- [ ] A regression test reproduces the PR #339 shape: a diff confined to a
      configured-excluded subtree, reviewed with `local=auto remote=auto`.

## Notes

- Source: shipping PR #339 on 2026-08-06. The workaround there was to narrow the
  exclusion (0.64.21), which fixed the instance and left the classification
  untouched.
- Sibling of `08-06-review-check-receipt-pinning`: both are `sd-review`
  coordinator classification defects where a non-actionable state is recorded as
  a failure and then blocks. They are separable — different phases, different
  state, no shared code path — and should stay separate tasks.
- Complex enough to need `design.md` and `implement.md` before `task.py start`:
  R3 puts a real correctness constraint against R2, and the open question about
  where the determination belongs is a genuine design choice.
