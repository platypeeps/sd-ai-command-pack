# Implement the unified routed sd-review command

## Goal

Implement `sd-review` as the one exact-scope, cost-aware review lifecycle for
worktree, branch, codebase, and PR scopes, replacing the overlapping local and
PR review workflows.

## Confirmed Evidence

- Review finding `1.1.2` confirms duplicated local/full/PR provider behavior,
  inconsistent scope evidence, direct remote dispatch, and 770 lines of
  transport/polling/remediation prose in `sd-review-pr`.
- Parent requirements R3-R12, R16-R21, R23-R25, R27-R28, and R30-R32 define the
  approved routed-review and exact-head contract.
- `sd-github-review` remains a separate framework and the sole remote backend
  selection/dispatch owner.

## Dependencies And Boundaries

- Parent: `07-22-integrate-routed-review-backends`.
- Depends on `07-24-implement-read-only-sd-check` publishing its typed check
  result and on `platypeeps/sd-github-review` task
  `07-22-publish-routed-review-receipt-contract` publishing reviewed v1 router
  schemas and pilot evidence.
- Contains `07-24-feed-review-learnings-into-review-planning`, which publishes
  bounded current family evidence;
  `07-24-converge-review-finding-families`, which adds the same-family
  sibling-audit and redispatch boundary; and
  `07-24-front-load-local-review-before-remote`, which owns risk/cost provider
  planning, concurrent first-head Prism/Gito execution, exact-scope aggregation,
  and branch-to-PR receipt reuse. All three children must complete before this
  task can claim review-loop convergence.
- This task builds the successor lifecycle. Removal of old public surfaces is
  owned by `07-24-remove-retired-review-surfaces`.

## Requirements

- R1: Expose one `sd-review` command with typed controls for
  `scope=auto|changes|branch|codebase|pr`,
  `local=auto|<provider>|all|none`,
  `remote=auto|cheap|deep|copilot|none`, and `fix=auto|ask|none`.
- R2: Resolve scope deterministically and bind every local/remote receipt to the
  repository, scope bytes/digest, base/head, provider/adapter versions, and
  configuration digest. Reuse only an exact match.
- R3: In local `auto`, resolve the child-owned deterministic provider set from
  scope, data-handling, capability, minimum-quality, risk, finding-family, and
  cost policy. The first substantive PR head, high-risk successors, and repeated
  families run Prism and Gito concurrently; bounded low-risk successors may run
  one lowest-cost eligible provider. Never silently switch to a different or
  more expensive provider after failure.
- R4: Keep provider definitions in one versioned pack-owned configuration with
  validated adapters/argument arrays, timeouts, cost/data classes, and normalized
  outcomes. No shell-string command configuration survives.
- R5: Use the `sd-github-review` capability/route/receipt contract for all remote
  decisions. The pack contains no direct Copilot request, reviewer-author
  matching, custom remote command, or fallback dispatch path.
- R6: Implement dispatch, polling, receipt validation, head-change
  reconciliation, retries, round budgets, and GitHub observation as a tested
  executable state machine. Integrate the child-owned provider plan, concurrent
  local attempts, exact-scope aggregation, family recurrence, sibling audit,
  and current-learning receipts rather than maintaining an independent prompt
  checklist. Skill prose retains judgment and user-facing disposition only.
- R7: Run `sd-check`, local review, finding disposition, remote routing,
  remediation, CI/thread observation, and exact-head re-entry in one ordered
  lifecycle. A new head invalidates prior readiness and receives its own receipt.
- R8: Keep non-PR scopes worktree-only. PR scope stages/pushes only approved
  review-fix paths after `sd-check`; unrelated paths remain untouched.
- R9: Use structured questions only for higher-risk fixes, true scope expansion,
  and explicit round extension. Ordinary in-scope fixes, bounded polling, thread
  resolution, and optional-router absence do not prompt.
- R10: Produce one report shape for local and remote stages, including provider,
  run/reuse, scope, outcome, route reason, cost class, latency, findings
  disposition, exact head, channels, and limitations.

## Acceptance Criteria

- [ ] Changes, branch, codebase, and PR fixtures all use the same public command
  and normalized result contract.
- [ ] Exact-scope fixtures prove unchanged work is not billed twice and any byte,
  head, provider, adapter, or configuration change invalidates reuse.
- [ ] A substantive first-head fixture runs Prism and Gito concurrently,
  deduplicates their current findings before remote routing, and exercises
  low-risk successor selection plus exact bookkeeping-successor skips.
- [ ] Missing, failed, rate-limited, cancelled, invalid, and unavailable local or
  remote providers remain distinct and never gain positive review confidence.
- [ ] Router-absent optional mode degrades exactly as specified; required,
  explicit, invalid, unavailable, failed, and ambiguous states fail closed with
  no direct fallback dispatch.
- [ ] Delayed feedback, multi-page threads, successor heads, retries with changed
  correlation, and bookkeeping-only successor receipts pass state-machine tests.
- [ ] Same-family repeated findings stop automatic redispatch, require the
  child-owned sibling audit and one batched fix, and require explicit extension
  if the family repeats after that audit.
- [ ] Current learning is collected at most once per review attempt, remains
  tracked-file read-only, and exposes stale/unavailable limitations without
  granting review confidence.
- [ ] No local or remote command is constructed through `bash -c`, `eval`, or an
  equivalent shell-string path.
- [ ] Focused review/state-machine tests, generated parity, install audit,
  `make sync`, and `make check` pass.

## Out Of Scope

- Merging the command-pack and `sd-github-review` repositories.
- Preserving `sd-review-local` or `sd-review-pr` as aliases, wrappers, modes, or
  hidden compatibility entry points.

## Notes

- Independent review backends may differ internally; the user-facing lifecycle,
  evidence, failure semantics, and cost disclosure must remain consistent.
