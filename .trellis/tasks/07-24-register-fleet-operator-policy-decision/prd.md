# Register the fleet operator policy decision

## Goal

Resolve review finding `1.6.2.1` by registering a bounded fleet operator policy
decision with native structured-question adaptation, equivalent fallback, and
noninteractive parking.

## Confirmed Evidence

- `templates/.agents/skills/sd-fleet-refresh/SKILL.md:241-243` and
  `references/controller-recovery.md:99-105` require the portable question
  contract for a genuine operator policy choice.
- `installer/registry.py` assigns no `interaction_decisions` entry to
  `sd-fleet-refresh`, so generated adapters cannot expose host-native guidance.
- The deterministic controller already emits `operator-decision` and must remain
  the state-transition authority.

## Dependencies And Boundaries

- Parent: `07-24-correct-sd-skill-contract-drift`.
- Consume the completed portable structured-question infrastructure and the
  completed deterministic fleet controller; do not create a second interaction
  or state-machine implementation.
- The source-checkout-only installation policy remains unchanged.

## Requirements

- R1: Register `fleet-refresh.operator-policy` or an equivalently specific ID in
  the canonical interaction registry and bind it to `sd-fleet-refresh`.
- R2: Ask only after controller evidence leaves mutually exclusive policy
  choices. Routine retries, polling, receipts, optional absence, deterministic
  transitions, and actions already authorized by campaign policy never prompt.
- R3: Present at most three controller-validated choices. The lowest-risk park
  option is recommended; each option is bound to the exact campaign, consumer,
  release, head/PR, and proposed action.
- R4: Native structured-question hosts use their verified capability. Other
  interactive hosts receive one equivalent concise plain-text question. A
  noninteractive or unanswered decision records `operator-decision` and parks
  without advancing state.
- R5: A response may narrow authority or select an already validated action; it
  cannot broaden consumer scope, bypass no-touch/trust/exact-head/merge gates,
  authorize a destructive operation, or invent a transition.
- R6: Keep the neutral skill host-agnostic and generate host tool names only in
  tested platform adapters.

## Acceptance Criteria

- [ ] Registry validation recognizes exactly one fleet operator decision and the
  fleet command declares ownership of it.
- [ ] Claude-capable output names `AskUserQuestion`; Codex-capable output uses
  its verified native question capability; neutral and unsupported surfaces do
  not invent either tool name.
- [ ] Interactive fallback presents equivalent choices and consequences.
- [ ] Noninteractive, unanswered, stale-head, wrong-release, or mismatched-action
  fixtures park without a controller transition or repository mutation.
- [ ] Routine fleet transitions complete without approval fatigue.
- [ ] Generator parity, fleet controller tests, interaction-contract tests,
  `make sync`, and `make check` pass.

## Out Of Scope

- Making the controller interactive.
- Using questions to repair invalid state or override safety policy.
- Installing fleet refresh in consumer repositories.

## Notes

- No compatibility-only question ID or host-specific skill fork is permitted.
