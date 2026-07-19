# Build Resumable Autonomous Work Loops

## Goal

Make `sd-work-backlog` and `sd-work-designs` autonomous, sequential work loops
that can take selected Trellis tasks from planning through a merged pull
request, continue across multiple tasks, and recover safely from context
compaction or session interruption.

## Background

Both skills currently describe bounded loops, but their continuation is
instruction-only. `sd-work-backlog` delegates to commands whose completion
reports can look terminal, especially housekeeping, so an agent may finish the
session instead of re-inventorying the backlog. `sd-work-designs` has a simpler
repeat contract, but stops after planning artifacts and does not carry the
selected task through implementation and merge.

Long-running sessions add another failure mode: conversational context can be
compacted, truncated, or degraded. The workflow must therefore treat Git,
Trellis, GitHub, and a minimal durable loop ledger as authoritative instead of
depending on retained conversation history.

## Requirements

### Shared Lifecycle

- `sd-work-backlog` must be the canonical loop controller and source of truth
  for autonomous iteration behavior.
- `sd-work-designs` must reuse that controller with a selector that considers
  only tasks that need `design.md` or `implement.md` when first selected.
- Both public skills must carry each selected task through planning when
  needed, implementation, validation, `sd-ship` review and merge, follow-up
  processing, clean-state verification, and backlog re-inventory.
- Preserve an explicit planning-only stop point, such as `until=design`, for
  users who want the current design-artifact-only workflow.
- Work on exactly one task, branch, and pull request at a time. A later
  iteration may not start until the prior iteration is merged and clean,
  safely parked before mutation, or stopped with a repository-wide blocker.
- Use existing skills as lifecycle authorities: `trellis-before-dev` for
  implementation context and `sd-ship until=merge` for publish, review, watch,
  finish-work, merge, and housekeeping. Do not duplicate their detailed gates.

### Optional Task Focus

- Accept an optional ordered task focus, including natural-language categories
  such as `focus="CI pipeline"` and structured selectors such as priority,
  package, task slug, status, or scope when the repository exposes those
  fields.
- Expose focus directly on the public command invocation. `focus="<value>"`
  and `focus-only="<value>"` are repeatable; repeated values retain their
  command-line order. The two modes are mutually exclusive in one invocation.
- Treat bare invocation text as one implicit preferred-focus expression. For
  example, `sd-work-backlog CI pipeline` is equivalent to
  `sd-work-backlog focus="CI pipeline"`. With no bare text or focus argument,
  retain normal backlog ranking.
- Reserve explicit `focus=` for multiple ordered focus expressions and
  `focus-only=` for strict filtering. Reject invocations that mix bare focus
  text with explicit focus arguments so no words are silently reinterpreted.
- Require every thin platform adapter to forward the user's focus arguments
  verbatim to the resolved skill. Reject malformed, mixed-mode, or unknown
  arguments before acquiring a loop lock or mutating repository state.
- Preserve current deterministic backlog ranking when no focus is supplied.
- Default `focus` behavior is a ranking preference: work matching actionable
  tasks first, then continue through the normally ranked backlog after the
  focused set is exhausted.
- Support an explicit `focus-only` behavior that considers only matching tasks
  and stops cleanly when no matching actionable task remains.
- Allow multiple focus values in operator-supplied order. Earlier values outrank
  later values; normal priority/age ranking breaks ties within each focus band.
- Determine natural-language matches conservatively from task title,
  description, PRD, package, scope, related files, and explicit metadata. Do
  not invent a match from unrelated source-code content.
- Explain why each selected task matched the focus and list ambiguous or
  non-matching candidates in the iteration inventory. Fall back to normal
  ranking for `focus`, but never silently broaden `focus-only`.
- Persist the original focus expression, normalized selectors, matching mode,
  and any operator updates in the loop ledger so resume preserves selection
  behavior.
- Support `focus <value>`, `focus-only <value>`, `add focus <value>`, and
  `clear focus` at iteration boundaries. Re-inventory immediately after a focus
  change.
- Combine focus with the public skill selector rather than replacing it. For
  example, `sd-work-designs focus="CI pipeline"` first considers CI-related
  tasks that need design artifacts.

### Autonomous Operation

- Invoking either full-cycle loop must establish a documented run-level
  authority for ordinary repo-local task planning, implementation, pull
  requests, review fixes, green merges, and clearly scoped follow-up task
  recording.
- Continue without per-iteration confirmation unless an unavoidable decision
  cannot be made safely from repository evidence and existing conventions.
- Upstream Trellis pull requests, destructive operations, credentials,
  security-sensitive choices, and irreducible product decisions remain outside
  the run-level authority.
- Classify blockers as transient, task-local, repository-wide, or requiring
  user input. Retry bounded transient failures, park task-local pre-mutation
  blockers, and stop only for repository-wide unsafe state or when every
  remaining candidate is blocked.
- When user input is unavoidable, ask one concise question with a recommended
  answer. Wait up to 15 minutes when the platform supports it; otherwise use
  the closest explicit wait. If unanswered, park the task and continue only
  when the repository can be returned to a clean, unambiguous state.
- Support operator instructions at iteration boundaries: stop now, stop after
  current, pause, skip current, reprioritize a task, update or clear focus, and
  report status.

### Iteration Reporting And Checkpoints

- Before each iteration, emit a brief plan naming the iteration, selected task,
  selection reason, lifecycle steps, and decisions or assumptions in effect.
- After each iteration, emit a brief result containing task outcome, PR and
  merge state, validation result, counters, decisions made, and follow-ups
  addressed, recorded, parked, or still requiring input.
- Re-inventory live state after every iteration. A delegated skill's final
  report must return to the loop controller and must not become the overall
  loop's final response.
- Offer a non-blocking stop opportunity near ten completed iterations. Choose a
  natural clean boundary in the approximate range of eight to twelve based on
  task size and current development flow. Continue unless the user asks to
  stop; do not interrupt an active task or require confirmation solely because
  the counter reached ten.
- The overall final report must include completed, parked, skipped, and blocked
  tasks; PR links; decisions; follow-ups; counters; final repository state;
  context-health events; and the concrete stop reason.

### Durable State And Context Health

- Add a standard-library helper that stores a versioned, minimal, user-local
  loop ledger outside the target repository working tree. Support an explicit
  state-directory override and platform-appropriate user-state fallbacks.
- Store only coordination metadata: repository identity, run ID, mode,
  selector, focus expressions/mode, iteration, current task and phase, branch,
  HEAD, PR, counters, compact decisions/follow-ups, checkpoint state,
  heartbeat, and stop reason.
  Do not store secrets, raw review payloads, or full command output.
- Write state atomically and use a recoverable run lock so concurrent loop
  sessions cannot mutate the same repository accidentally.
- At every phase and iteration boundary, reconcile the ledger with live Git,
  Trellis, and GitHub state. Existing branches, commits, PRs, reviewer requests,
  merges, finish-work actions, and housekeeping effects must be recognized
  idempotently rather than repeated.
- Detect harmful context degradation through evidence rather than model
  self-assessment. Treat runtime compaction notices, truncated output,
  continuation from summary, state contradictions, unverifiable remembered
  decisions, and duplicate-side-effect attempts as context-health signals.
- Use green, amber, and red context-health states. Green continues; amber
  reloads the selected task, applicable specs, Git, and PR state; red stops or
  safely parks after persisting a resumable checkpoint.
- Proactively rehydrate at every iteration and after several complex phases.
  The loop must remain resumable even when no platform exposes context-window
  usage or can automatically open a fresh agent session.
- Add loop information to `sd-status`, including run ID, mode, iteration,
  phase, task, PR, counters, heartbeat, context health, and checkpoint state.

### Follow-Ups, Cost, And Scope Control

- Process follow-ups before selecting the next task. Address small in-scope
  items immediately, record separable work as Trellis tasks, and capture
  durable conventions through the existing review-learning/spec workflows.
- Run the PR-scoped review-learning pass exactly once through its existing
  lifecycle owner; do not repeat it at the outer loop level.
- Detect tasks that are too large for one coherent PR during planning and split
  them into ordered Trellis tasks before implementation when run-level task
  creation is authorized.
- Track elapsed time, merged PRs, remote-review rounds, CI retries, completed
  tasks, parked tasks, and failures. Report soft cost/time warnings without
  weakening deterministic checks or merge criteria.
- Use bounded polling and report state deltas during CI and reviewer waits to
  avoid unnecessary context growth and service requests.

## Constraints

- `templates/**` remains the source of truth for shipped pack files; installed
  mirrors and all platform adapters must remain synchronized.
- The redesign must not bypass branch protection, `sd-review-pr` convergence,
  `sd-ship` lifecycle ownership, or `sd-housekeeping` merge safety.
- Do not create an upstream Trellis pull request without explicit consent for
  that specific PR.
- The helper must use the Python standard library and support macOS, Linux, and
  Windows path conventions without adding a runtime dependency.
- Skill behavior must remain useful on platforms that cannot wait, expose
  context usage, or automatically continue in a fresh session.

## Acceptance Criteria

- [ ] `sd-work-backlog` repeatedly selects and completes actionable tasks
      through clean merges until a documented stop condition is reached.
- [ ] `sd-work-designs` selects tasks missing planning artifacts and then uses
      the same complete plan-to-merge lifecycle by default.
- [ ] `focus="CI pipeline"` prioritizes matching actionable tasks, explains the
      match, and continues with the normal backlog after focused tasks finish.
- [ ] `focus-only="CI pipeline"` never selects a non-matching task and stops
      with a focused-backlog-exhausted reason when no match remains.
- [ ] Ordered and structured focus selectors compose with both public skill
      selectors, persist across resume, and can be changed between iterations.
- [ ] Public adapters accept repeatable `focus=` or `focus-only=` arguments,
      preserve their order, reject mixed modes before mutation, and behave as
      today when no focus is supplied.
- [ ] Bare text such as `sd-work-backlog CI pipeline` is treated as one
      preferred-focus expression, while bare/explicit mixtures fail clearly
      before mutation.
- [ ] An explicit planning-only stop point remains available.
- [ ] Both skills provide the required pre-iteration plan and post-iteration
      result/counter/decision summaries.
- [ ] A clean delegated `sd-ship`/housekeeping result returns control to backlog
      re-inventory instead of terminating the parent loop.
- [ ] A natural checkpoint near ten completed iterations offers a stop without
      blocking continued autonomous work.
- [ ] Task-local pre-mutation blockers can be parked while later actionable
      tasks continue; repository-wide blockers stop safely.
- [ ] The loop ledger and lock are user-local, atomic, versioned, secret-free,
      and recoverable after interruption or stale-state detection.
- [ ] Resume logic recognizes every completed lifecycle phase and does not
      duplicate branches, PRs, reviewer requests, merges, finish-work, or
      housekeeping effects.
- [ ] Context-health reconciliation detects injected ledger/live-state
      contradictions and chooses the documented green, amber, or red action.
- [ ] `sd-status` reports active, paused, stopped, and completed loop state.
- [ ] Tests cover selection modes, missing-design planning, repeated
      iterations, natural-language and structured focus, focus-only exhaustion,
      the near-ten checkpoint, operator controls, blocker classes, stale locks,
      atomic recovery, context rehydration, and crash/resume at each lifecycle
      transition.
- [ ] Generated/template parity, installer coverage, documentation checks, and
      the repository's canonical full check pass.
- [ ] Shipped payload changes include the required version and changelog update.
