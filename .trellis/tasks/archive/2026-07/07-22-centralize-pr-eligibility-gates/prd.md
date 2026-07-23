# Centralize PR eligibility and exact-head gates

## Goal

Replace duplicated prose-level PR readiness and merge criteria with one
read-only, deterministic, versioned gate. `sd-housekeeping` remains the only
component authorized to mutate GitHub merge state; other workflows may consume
the gate result but cannot reproduce or weaken it.

## Evidence

- `templates/.agents/skills/sd-update-deps/SKILL.md:14-17` declares
  housekeeping the merge authority, while lines 70-87 describe a separate
  agent-level merge gate.
- `templates/scripts/sd-ai-command-pack-housekeeping.sh:674-734` already
  implements exact-head check and paginated unresolved-thread handling.
- Review and ship can create finish-work bookkeeping commits after earlier
  review evidence, so final readiness needs an explicit current-head contract.

## Dependencies

- This task owns the shared read-only eligibility evaluator and its result
  schema.
- `07-22-integrate-routed-review-backends` owns production of unified
  exact-head review receipts. This task may land its generic evaluator first,
  but unified-receipt consumption cannot be completed until that schema is
  reviewed.
- `sd-housekeeping` owns the only merge mutation path. `sd-update-deps`,
  `sd-ship`, and future callers consume the evaluator or delegate to
  housekeeping.

## Requirements

- R1: Add one side-effect-free eligibility evaluator with versioned JSON input
  and output. It must not merge, approve, push, resolve threads, or change
  labels, branches, tasks, or repository files.
- R2: Bind every result to repository identity, PR number, base branch, and the
  full current head OID observed at both the beginning and end of evaluation.
- R3: Evaluate required checks against the same head, paginating review threads
  until exhaustion and distinguishing zero unresolved threads from unreadable
  or incomplete data.
- R4: Validate finish-work evidence for the exact current head. If a typed
  remote-review receipt is required, validate a router-issued receipt for that
  same current head, including a router-selected `none` result. Never mint or
  accept a command-pack-local bookkeeping exemption, infer one from prose or a
  commit message, or reuse an older-head router receipt.
- R5: Emit `eligible|blocked|indeterminate`, stable reason codes, observed
  evidence, timestamps, and schema/tool versions. Network/auth/rate-limit/API
  errors are `indeterminate`, not clean.
- R6: Re-read head identity immediately before returning. A changed head
  invalidates collected evidence and returns a retryable stale-head result.
- R7: Make housekeeping consume the evaluator and perform mutation only after
  an exact matching `eligible` result. It must retain its existing final
  mutation-boundary rechecks.
- R8: Make `sd-update-deps` classify dependency PRs and request the shared gate
  rather than restating merge criteria. Safe batching authority does not grant
  a second merge implementation.
- R9: Preserve delayed review-materialization polling and direct
  `reviewThreads` evidence. Green CI alone is never sufficient.
- R10: Preserve protected-main finish-work recovery and no-touch ownership.
  The evaluator reports state; it does not repair task lifecycle or branch
  state itself.

## Acceptance Criteria

- [ ] Unit fixtures cover eligible, blocked check, unresolved thread,
  multi-page threads, missing finish-work evidence, stale head, changed head,
  auth failure, rate limit, malformed receipt, and unknown schema major.
- [ ] Repeated evaluation produces equivalent JSON for equivalent external
  state and makes no local or GitHub mutation.
- [ ] Housekeeping is the only live code path containing merge mutation.
- [ ] `sd-update-deps` contains no independent prose or code implementation of
  thread/check/head eligibility and delegates successful PRs through the shared
  path.
- [ ] A new finish-work head cannot inherit an older review or check verdict.
- [ ] A policy-allowed bookkeeping-only successor is eligible only through a
  router-issued receipt for the exact new head when routed review is required;
  local-only policy remains explicit and does not fabricate remote evidence.
- [ ] Existing housekeeping exact-head, unresolved-thread, protected-main, and
  branch-cleanup tests remain green.
- [ ] Templates and generated copies are synchronized and `make check` passes.

## Out Of Scope

- Selecting or dispatching review providers.
- Automatically resolving review findings.
- Changing dependency safety classification.
- Granting new merge, approval, force-push, or branch-deletion authority.
