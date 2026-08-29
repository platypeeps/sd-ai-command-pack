---
title: Register the fleet operator policy decision
status: done
created: 2026-07-24
branch: feat/register-fleet-operator-policy
---
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

- [x] Registry validation recognizes exactly one fleet operator decision and the
  fleet command declares ownership of it.
  (Import validates 13→14 decisions; `grep -c fleet-refresh.operator-policy
  installer/registry.py` = 2 — one entry, one binding.)
- [x] Claude-capable output names `AskUserQuestion`; Codex-capable output uses
  its verified native question capability; neutral and unsupported surfaces do
  not invent either tool name.
  (`.claude/commands/sd/fleet-refresh.md` names `AskUserQuestion`; the Gemini
  toml carries its native question capability; `templates/.agents/skills/
  sd-fleet-refresh/` names no host tool.)
- [x] Interactive fallback presents equivalent choices and consequences.
  (Adapters render the three options and their consequence strings via the
  shared `structured-questions.md` reference entry.)
- [x] Noninteractive, unanswered, stale-head, wrong-release, or mismatched-action
  fixtures park without a controller transition or repository mutation.
  (Decision sets `noninteractive="park"`; the controller's existing park and
  reject paths are covered by `tests/test_fleet_controller.py`
  — `test_parked_canary_allows_wave_progression_only_with_opt_in`,
  `test_wrong_release_and_consumer_receipts_are_rejected`,
  `test_cli_operator_decision_requires_validated_provenance` — unchanged by
  this task and green under `make check`.)
- [x] Routine fleet transitions complete without approval fatigue.
  (The decision surfaces only on a genuine controller operator-decision; the
  unchanged do-not-ask prose keeps routine retries, polling, receipts, and
  optional absence non-prompting.)
- [x] Generator parity, fleet controller tests, interaction-contract tests,
  `make sync`, and `make check` pass.
  (`make generate` byte-stable, `make sync`, fleet candidate ledger
  re-validated, `make check` green.)

## Out Of Scope

- Making the controller interactive.
- Using questions to repair invalid state or override safety policy.
- Installing fleet refresh in consumer repositories.

## Notes

- No compatibility-only question ID or host-specific skill fork is permitted.
- Complex task. Planning complete 2026-07-28: `design.md` and `implement.md` added.
- **Both Confirmed Evidence citations are wrong.** Verified 2026-07-28:
  `SKILL.md:241-243` is the finding-severity gate's `fleet-finding-classify.py`
  invocation, and `controller-recovery.md:99-105` is the pack-blocker recovery
  transition. The real sites are `SKILL.md:110-112` (`operator-decision` in the receipt
  result vocabulary), `SKILL.md:282-288` (the ask / do-not-ask rule), and
  `controller-recovery.md:150-156` (the `## Operator Decisions` section). The third
  evidence bullet — no `interaction_decisions` entry on `sd-fleet-refresh` — is accurate
  and is the entire gap.
- **R2–R5 are already written; this is registry work only.** R2 at `SKILL.md:282-288`,
  R3 at `controller-recovery.md:152-155`, R4's park behavior at
  `controller-recovery.md:155-156`, R5 at `SKILL.md:280-281`. Rewriting them creates a
  second copy of a contract that already reads correctly.
- **The validator forces static options — `option_source` would be a safety regression.**
  `installer/registry.py:1136-1142` rejects dynamic options unless `multi_select=True` and
  the source string contains the literal substring `"independent"`. R2 specifies "mutually
  exclusive policy choices", which is single-select. R3's runtime binding to campaign /
  consumer / head / PR is prompt evidence (already required at
  `controller-recovery.md:154-155`), not option identity.
- **Other validator constraints that shape the entry** (`registry.py:1096-1135`, `:516-520`):
  2–3 options (matches R3's "at most three"); exactly one recommended option and it must be
  **first** (`if recommended != [0]`), so R3's "lowest-risk park option is recommended" also
  fixes its position; `noninteractive="park"` is a valid value matching R4 exactly, with
  `work-backlog.blocked-disposition` (`registry.py:579`) as the sibling that already pairs
  `park` with category `blocked-run-disposition`; and `INTERACTION_HEADER_MAX_LENGTH = 12`,
  so "Fleet policy" sits exactly at the limit.
- **Registration and binding cannot be split across commits.** `registry.py:1146` errors on
  an unknown decision id and `:1152` errors on an unreferenced one, both raising
  `RuntimeError("invalid interaction registry: …")` at import. There is no intermediate
  green state.
- **AC2 is blocked by an undeclared dependency on `07-28-regenerate-fleet-refresh-adapters`.**
  `sd-fleet-refresh` is the sole member of `SOURCE_ONLY_COMMAND_NAMES`
  (`registry.py:1176`) and its adapters are frozen. Measured: `.claude/commands/sd/audit-repo.md`
  contains `AskUserQuestion` once (its `audit.followups` decision regenerates), while
  `.claude/commands/sd/fleet-refresh.md` (mtime Jul 18) and
  `templates/.commands/sd-fleet-refresh.md` (mtime Jul 23) contain it zero times. Registering
  the decision will not reach the Claude surface AC2 names until the adapters unfreeze. Do
  not hand-edit the frozen adapter to make AC2 pass.
- `fleet-refresh.operator-policy` matches the established `<command-short>.<slug>` ID
  convention used by all seven existing decisions, so R1's preferred ID is the conventional
  one.
