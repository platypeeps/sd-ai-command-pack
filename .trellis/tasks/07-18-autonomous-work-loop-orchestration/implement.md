# Resumable Autonomous Work Loops Implementation Plan

## Execution Order

1. Complete and merge `07-18-positional-primary-command-inputs` first so this
   task consumes its positional-primary-subject and adapter guidance instead of
   creating a competing convention. Then review and approve this PRD/design,
   start this Trellis task, and confirm the current pack version and
   generated/template ownership before editing.
2. Define the work-loop JSON schema, state-root resolution, repository identity,
   lock/heartbeat behavior, atomic write rules, legal transitions, and
   reconciliation result types in focused tests. Include original/normalized
   focus expressions and focus mode in the schema.
3. Add the standard-library state helper in `templates/scripts/`, synchronize
   the root script mirror, and register the shipped payload in `manifest.json`.
   Implement read-only status before mutating transition commands.
4. Add unit tests for state-root precedence, Windows/POSIX paths, schema
   validation, permissions where supported, atomic recovery, stale locks,
   bounded history, invalid transitions, resume, and secret-free serialization.
5. Refactor the template `sd-work-backlog` skill into the canonical controller.
   Add its shared autonomous-loop/planning reference and synchronize the
   installed skill mirror.
6. Refactor `sd-work-designs` into the `needs-design` selector entry point.
   Make full lifecycle the default and add the explicit `until=design` stop
   point. Keep adapter prompts thin and skill-resolving.
7. Add deterministic focus parsing, grounded match evidence, ordered preference
   bands, structured selectors, focus-only exhaustion, persisted focus updates,
   selector composition tests, bare-text preferred-focus fallback, repeatable
   public argument handling, and pre-mutation rejection of mixed or malformed
   modes.
8. Extend `sd-ship` with the trusted nested return contract. Preserve its
   existing stage ownership, review-learning count, finish-work routing, and
   housekeeping merge authority.
9. Add the pre/post iteration reports, soft eight-to-twelve checkpoint,
   operator controls, blocker taxonomy, task-size guard, follow-up ledger,
   context-health states, proactive rehydration, and final-response guard.
10. Extend the status script/skill to report loop state and add focused status
   fixtures for active, paused, stopped, completed, stale, and contradictory
   ledgers, including preferred and focus-only selection state.
11. Update shared command-contract tests, generated parity expectations,
   installer coverage, manifest entries, and every platform adapter produced
   from the canonical templates. Do not manually diverge platform copies.
12. Update adapter guidance, README/help examples, the distributed pack guide,
   environment/state-path documentation, and release notes. Bump the pack
   version according to the release contract because consumer behavior and
   shipped payload change.
13. Run the focused suites, `git diff --check`, template/root drift checks,
   installer audit/tests, documentation checks, and the canonical full check.
    Exercise a disposable end-to-end fixture that performs at least two
    iterations and resumes from one interrupted lifecycle phase.

## Validation Plan

- State helper tests prove legal transitions, idempotent reconciliation, atomic
  recovery, lock safety, path portability, bounded serialization, and all
  context-health classifications.
- Skill tests prove `backlog` and `needs-design` selection, missing-design
  planning, full-cycle defaults, `until=design`, natural-language and structured
  focus, bare-text fallback, ordered focus bands, focus-only exhaustion,
  option-typo rejection, nested `sd-ship` return, iteration boundary output,
  soft checkpoint behavior, and final-stop guards.
- Recovery fixtures interrupt after selection, planning, branch creation,
  validation, PR creation, review request, external merge, finish-work, and
  housekeeping; each resume reaches the correct next phase without repetition.
- Failure fixtures distinguish transient, task-local, user-input, and
  repository-wide blockers, including the unsafe case where partial work cannot
  be parked while preserving a clean sequential loop.
- Status tests verify loop reporting does not mutate the ledger or require an
  active GitHub connection for local-only fields.
- Installer and generated-parity tests verify every supported platform receives
  synchronized skills, helper, references, and docs.
- Canonical release and full-check commands pass with Prism and Gito behavior
  unchanged from their explicit invocation policy.

## Documentation And Spec Updates

- Document that both commands are autonomous full-cycle loops with different
  selectors, and that `until=design` is the planning-only form.
- Document `focus`, `focus-only`, multiple ordered focus values, structured
  selectors, conservative natural-language matching, runtime focus controls,
  and examples such as `sd-work-backlog CI pipeline` and
  `sd-work-backlog focus="CI pipeline"`.
- Document run-level authority, explicit exclusions, operator controls, state
  location/override, resume behavior, soft checkpoints, and context-health
  limitations.
- Update `sd-help` examples and command comparison guidance.
- Update the frontend adapter specification so future commands preserve one
  canonical controller, thin adapters, structured nested returns, and
  repository-backed context reconciliation.
- Record the additive behavior and state-helper payload in the changelog and
  release metadata.

## Review Notes

- Review lifecycle ownership carefully. The outer loop must not duplicate any
  `sd-ship` stage, reviewer request, review-learning pass, finish-work action,
  or housekeeping merge.
- Verify that invocation authority is documented clearly without granting
  upstream Trellis PR or destructive-operation authority.
- Treat every final-looking nested report as data returned to the controller;
  only a verified terminal state may end the overall loop.
- Confirm the helper never persists secrets or repository command output.
- Prefer state reconciliation and idempotency over retrying a side effect after
  ambiguous failure.

## Rollback Points

- The state helper can land behind unused skill instructions first; no consumer
  behavior changes until the controller invokes it.
- Keep selector refactoring and `sd-ship` nested return changes in separable
  commits so either contract can be reverted without deleting user state.
- Schema migrations must read the immediately prior schema or fail with a clear
  recovery instruction; never silently discard an active ledger.
- If the full-cycle `sd-work-designs` default proves too surprising before
  release, retain the shared controller but hold the default switch until docs
  and adapters are aligned.

## Follow-Ups

- Consider platform-native fresh-context continuation adapters only after the
  portable ledger/resume contract is proven. They are not required for this
  task.
- Consider fleet-wide loop visibility later; this task limits `sd-status` to
  the current repository's active loop.
