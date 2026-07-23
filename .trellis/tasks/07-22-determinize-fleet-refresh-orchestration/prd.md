# Determinize fleet refresh orchestration

## Goal

Move authoritative cross-repository rollout state, wave scheduling, retries,
receipts, and next-action decisions out of the `sd-fleet-refresh` prompt and
into a deterministic, resumable controller. Keep the skill responsible for
operator-facing judgment and exception explanations.

## Evidence

- `templates/.agents/skills/sd-fleet-refresh/SKILL.md:73-110` defines timing
  state in prose.
- Lines 112-156 define wave planning and lines 197-297 define a ten-stage
  per-consumer lane plus merge control.
- Existing helpers already own parts of timing, wave planning, candidate
  validation, and finding classification, but the prompt remains the
  authoritative cross-repository coordinator.

## Dependencies

- No dependency on routed-review consolidation.
- May consume `07-22-add-portable-structured-questions` for exceptional
  operator choices. The controller itself must remain noninteractive and
  deterministic.
- Must preserve current fleet manifest, no-touch ownership, immutable release,
  and candidate-ledger contracts.

## Requirements

- R1: Add a versioned controller state/receipt schema covering campaign,
  immutable pack release, consumer identity, wave, lane stage, attempt,
  timestamps, head/PR identity, result, blocker, and next eligible action.
- R2: Provide deterministic `plan`, `next`, `record`, `status`, `resume`, and
  validation operations with JSON output. Replaying a recorded event must be
  idempotent.
- R3: Enforce concurrency, canary, wave, timeout, retry, and stop policies in
  executable code. Prompt text may explain decisions but cannot override an
  invalid transition.
- R4: Preserve no-touch and loop ownership. A consumer with live external
  ownership is skipped/parked with evidence and is never cleaned, committed,
  or reset by the campaign.
- R5: Bind every lane to the immutable release and resolved repository path.
  State from a different release, checkout identity, or campaign is rejected.
- R6: Preserve staged validation: preflight, install/update, focused candidate,
  local checks, PR publication/reuse, review, merge eligibility, merge, and
  post-merge verification. The controller names stages; owning skills still
  perform scoped actions.
- R7: Distinguish retryable infrastructure failure, product failure, review
  finding, ownership skip, permanent incompatibility, and operator decision.
- R8: Persist state atomically and support process interruption without
  duplicating install, PR, review request, or merge actions.
- R9: Keep commands bounded to configured consumers and explicit repository
  paths. No broad recursive cleanup or implicit discovery may expand scope.
- R10: Produce a concise campaign report from receipts rather than reconstructing
  status from conversation history.

## Acceptance Criteria

- [ ] Transition-table tests reject skipped stages, wrong-release receipts,
  duplicate side effects, stale PR heads, and invalid concurrent wave starts.
- [ ] An interrupted campaign resumes from persisted state without rerunning a
  completed side effect.
- [ ] Canary failure prevents later waves; successful bounded waves release the
  configured next consumers deterministically.
- [ ] No-touch/loop-owned consumer fixtures are parked without local mutation.
- [ ] Retryable and terminal failures produce different next actions and stable
  reason codes.
- [ ] The canonical skill no longer contains the authoritative ten-stage lane
  or timing state machine; it invokes and interprets the controller.
- [ ] Existing fleet candidate, manifest, immutable-release, and rollout tests
  remain green, and `make check` passes.

## Out Of Scope

- Changing the fleet membership or release cohort policy for unrelated reasons.
- Automatically overriding consumer-specific findings.
- Granting force-push, bypass, destructive cleanup, or upstream Trellis PR
  authority.
