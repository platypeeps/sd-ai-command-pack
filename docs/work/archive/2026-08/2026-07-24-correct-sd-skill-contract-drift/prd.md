---
title: Correct SD skill safety and interaction contract drift
status: done
created: 2026-07-24
---
# Correct SD skill safety and interaction contract drift

## Goal

Remediate the verified safety, status-schema, and structured-interaction defects from se-review-skills snapshot 8f5f11d25e3d193ac18576319c99d1552349f41888e26b7f7e239b0a2ea3126a without duplicating routed-review consolidation work.

## Confirmed Evidence

- Finding `1.4.1.1` (`sd-audit-repo`, P1):
  `templates/.agents/skills/sd-audit-repo/charters/tooling.md:48-63`
  promises read-only probes but directs a reviewer to execute repository targets
  and scripts through `make -n` and `--help`. Those invocations can evaluate or
  run checkout-owned code and therefore exceed the charter's stated authority.
- Finding `1.4.1.2` (`sd-audit-repo`, P2):
  `templates/.agents/skills/sd-audit-repo/charters/architecture.md:50-59`
  recommends a whitespace-delimited `git ls-files | xargs wc -l` pipeline. It
  misparses valid tracked filenames containing whitespace or newlines and does
  not terminate option parsing safely.
- Finding `1.1.1` (`sd-status` / `sd-housekeeping`, P2): the current status
  contract exposes only `F-*` and `T-*` selectors, but
  `templates/.agents/skills/sd-status/SKILL.md:134-138` and
  `templates/.agents/skills/sd-housekeeping/SKILL.md:75-77` still claim an
  `F/T/R` selector surface.
- Finding `1.6.2.1` (`sd-fleet-refresh`, P2):
  `templates/.agents/skills/sd-fleet-refresh/SKILL.md:241-243` and
  `references/controller-recovery.md:99-105` require the portable structured
  question contract for ambiguous operator policy choices, but fleet refresh
  owns no declared decision ID. Its generated adapters therefore cannot expose
  the existing host-capability guidance at that boundary.

The inventory was recomputed before task creation and retained snapshot ID
`8f5f11d25e3d193ac18576319c99d1552349f41888e26b7f7e239b0a2ea3126a`.
Installed copies matched their canonical templates. The generated untrusted-
checkout preflight already covers every execution-capable command, so this task
does not duplicate that completed foundation.

## Dependencies And Boundaries

- Keep `templates/**` authoritative and synchronize generated/dogfood mirrors
  through the normal pack workflow.
- Reuse the existing structured-question registry and generator for the fleet
  decision. Do not add host-specific tool names to the neutral skill body.
- `07-22-integrate-routed-review-backends` already owns review-command
  consolidation, shell-string retirement, and moving deterministic review
  transport out of prompt prose. This task must not absorb that work.
- Preserve formal-audit coverage, status inventory behavior, fleet controller
  authority, no-touch handling, and all existing trust and merge gates.
- No upstream Trellis change or pull request is required.

## Child Task Map

- `07-24-harden-audit-read-only-methods` owns findings `1.4.1.1` and
  `1.4.1.2`: non-executing audit methods and filename-safe inventory.
- `07-24-align-status-selector-contract` owns finding `1.1.1`: removal of the
  obsolete `R-*` selector and Roadmap-section contract from every live surface.
- `07-24-register-fleet-operator-policy-decision` owns finding `1.6.2.1`: the
  registered structured/fallback fleet decision and safe noninteractive park.
- This task coordinates those children and carries their snapshot evidence. It
  has no direct product-code implementation scope.

## Requirements

- R1: Make every `sd-audit-repo` charter method genuinely non-mutating by
  default. Static inspection may describe a repository command, but a read-only
  audit must not execute checkout-owned targets or scripts merely to verify that
  they resolve or display help.
- R2: Replace the architecture charter's filename pipeline with a portable,
  deterministic method that handles whitespace, newlines, option-like names,
  and an empty tracked-file set without interpreting paths as options.
- R3: Align every current `sd-status` and delegated `sd-housekeeping` selector
  description with the shipped `F-*` follow-up and `T-*` task sections. Do not
  restore a separate roadmap or `R-*` surface.
- R4: Declare one bounded fleet operator-policy decision in the canonical
  interaction registry and bind `sd-fleet-refresh` to it. Use native structured
  questions where supported, the equivalent concise plain-text fallback where
  unsupported, and `park` for noninteractive ambiguity.
- R5: The fleet question must be required only after deterministic evidence and
  controller state leave mutually exclusive operator choices. It must not ask
  for ordinary polling, retries, receipts, optional absence, or actions already
  authorized by the campaign.
- R6: Preserve the current capability ledger: no new mutation, merge, remote-
  dispatch, checkout-trust, or destructive-operation authority may be inferred
  from any question answer.

## Acceptance Criteria

- [ ] Audit charter contract tests reject instructions that execute repository
  targets/scripts under a read-only method, including `make -n` and arbitrary
  `--help` probes.
- [ ] Hostile tracked-filename fixtures prove the architecture inventory handles
  spaces, newlines, leading option characters, and an empty repository safely.
- [ ] Focused status/housekeeping tests fail on stale `R-*` or `F/T/R` claims and
  confirm the documented output contains only Follow-ups and Tasks.
- [ ] Fleet refresh owns a registered decision ID with 2-3 bounded choices, a
  recommended lowest-risk option, campaign-bound consequences, and
  noninteractive `park` behavior.
- [ ] Generated Claude-capable adapters expose the host-native structured
  question guidance for that fleet decision; neutral and unsupported adapters
  retain the portable fallback and do not invent tool names.
- [ ] Tests prove routine fleet transitions do not prompt and that an unanswered
  interactive decision cannot widen authority or advance the controller.
- [ ] Templates, generated adapters, root mirrors, manifest/provenance data, and
  focused tests remain synchronized; `make sync` and `make check` pass.
- [ ] No live review/check identifier or behavior owned by
  `07-22-integrate-routed-review-backends` is changed by this task.
- [ ] All three implementation children are archived with landed change and
  validation evidence before this task is completed.
- [ ] The final workflow-program integration task includes these four review
  findings in its evidence map and confirms that the obsolete `R-*` surface did
  not survive as an alias or compatibility reader.

## Notes

- This planning parent was created from `se-review-skills` snapshot
  `8f5f11d25e3d193ac18576319c99d1552349f41888e26b7f7e239b0a2ea3126a`.
- Planning classification, 2026-07-28: coordination parent — PRD-only, deliberately.
  No `design.md` or `implement.md`. G01-G04 are designed and executed in the three
  implementation children; this task owns only the finding-to-child map and the
  cross-child acceptance criteria above. `07-24-align-status-selector-contract` (G01)
  received its own `design.md` and `implement.md` on 2026-07-28.
