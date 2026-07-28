# Standardize environment-blocked recovery evidence

## Goal

Give every lifecycle mutation owner a bounded, typed way to distinguish an
environment or authority boundary from a repository defect and to identify the
smallest safe retry checkpoint without automatically escalating privileges or
restarting completed work.

## Background

- Recent Trellis-backed sessions repeatedly encountered filesystem or
  ownership failures at Git metadata, user-local loop state, tool caches,
  linked knowledge-base targets, and managed payloads.
- Most operations succeeded when rerun with the same scope and the required
  authority or an owned task-local cache, but generic diagnostics made the
  retry point unclear and encouraged full lifecycle reruns.
- Completed `07-24-standardize-sandbox-safe-tool-cache-routing` centralized
  cache routing but did not define a cross-command failure contract.
- Full evidence is recorded in
  `../07-28-analyze-recurring-trellis-workflow-instability/research/recent-trellis-workflow-instability.md`.

## Requirements

- R1: Define one reusable structured fragment with
  `reasonCode: environment_blocked`, a bounded `boundary` enum, bounded owning
  `operation`, `retryable`, last verified `checkpoint`, bounded
  `recoveryAction`, `mutationState`, and a secret-safe diagnostic.
- R2: Initially support the `git-metadata`, `user-state`, `tool-cache`,
  `kb-target`, and `managed-payload` boundaries. Unknown failures retain their
  existing command-owned failure result rather than being guessed into this
  contract.
- R3: Restrict `mutationState` to `none`, `partial-recoverable`, or `unknown`.
  A caller may advertise a retry only when the owning command can prove the
  checkpoint and idempotency conditions.
- R4: Integrate the fragment at known owning operations in session recording,
  finish-work, housekeeping, work-loop persistence, knowledge-base refresh,
  and toolchain cache setup while preserving each command's existing exit and
  fail-closed semantics.
- R5: Do not parse arbitrary stderr into authority decisions, expose secrets or
  uncontrolled paths, auto-escalate permissions, run a recovery action
  automatically, or restart the full lifecycle when a narrower retry exists.
- R6: Skills consuming the fragment must report the exact blocked boundary and
  checkpoint and may request only the narrow authority needed for the bounded
  retry. An environment block never authorizes merge, branch deletion,
  archive, force operations, or broad cleanup.
- R7: Define explicit schema-version and compatibility behavior before adding
  the fragment to an existing result object. Unsupported consumers retain
  their current bounded diagnostic instead of accepting partial evidence.
- R8: Change templates first, keep installed/root mirrors synchronized, and
  preserve atomic/private state, symlink, containment, ownership, and
  exact-path checks at every boundary.

## Dependencies and coordination

- Parent program: `07-22-streamline-sd-skill-workflows`.
- Build on completed `07-24-standardize-sandbox-safe-tool-cache-routing`;
  coordinate cache ownership with `07-25-user-scope-toolchain-caches` without
  duplicating routing.
- Keep recovery-artifact ownership in
  `07-24-track-clean-recovery-artifacts`, lock correctness in
  `07-25-fix-work-loop-lock-race`, and receipt input validation in
  `07-28-validate-finish-work-receipt-path`.
- Coordinate result-version choices with
  `07-28-decide-housekeeping-result-schema-compatibility`.
- Do not widen `07-25-harden-toolchain-failure-paths`; it owns GraphQL
  pagination and descriptor lifetime, not this cross-command contract.
- Feed environment-blocked and idempotent-retry scenarios into
  `07-22-validate-sd-workflow-program-integration`.

## Acceptance Criteria

- [x] The shared fragment has a documented schema, bounded enums, compatibility
      policy, size limits, and secret/path redaction rules.
- [x] Each initial owning operation emits a deterministic blocker only for a
      known boundary and retains its prior failure/exit behavior otherwise.
- [x] Fixtures distinguish no-mutation, partial-recoverable, and unknown states
      and prove the advertised retry resumes from the last verified checkpoint
      without duplicating journal, commit, archive, merge, or cleanup work.
- [x] Malformed diagnostics, unknown boundaries, foreign ownership, symlinks,
      replaced paths, missing authority, and concurrent retries fail safely.
- [x] No environment-blocked path reaches merge, branch deletion, archive,
      force operations, broad cleanup, or automatic privilege escalation.
- [x] Skills render a concise boundary, checkpoint, and bounded recovery action
      consistently across supported platforms.
- [x] Focused command and schema tests, template/root parity, install audit,
      `make sync`, and `make check` pass.

## Out of Scope

- A universal exception wrapper or arbitrary stderr classifier.
- Automatic permission escalation, permission broadening, or retry execution.
- Fixing the underlying work-loop race, cache ownership defect, recovery
  artifact lifecycle, or receipt validation inside this task.
- Changing upstream Trellis or creating an upstream pull request.
