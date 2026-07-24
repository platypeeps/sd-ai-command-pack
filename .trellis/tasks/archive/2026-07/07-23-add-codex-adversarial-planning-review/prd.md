# Add Codex adversarial planning review

## Goal

Add a cost-conscious adversarial planning review that asks native Codex to
challenge newly created or materially updated Trellis `prd.md`, `design.md`,
and `implement.md` artifacts alongside the host workflow's own review, then
ensures supported concerns are resolved before implementation begins.

## Background

- The current pack has no planning-artifact adversarial-review contract. Its
  existing adversarial verification belongs to `sd-audit-repo` and reviews
  repository-audit findings, not Trellis plans.
- The OpenAI Codex Claude plugin exposes `/codex:adversarial-review`, but this
  pack's recently established direction is to keep that plugin optional and
  call the supported native Codex CLI directly.
- Native `codex review` targets Git changes but cannot take the focused planning
  prompt needed here. `codex exec` supports a custom prompt, repository root,
  read-only sandbox, ephemeral sessions, and structured output.
- This pack owns `sd-*` workflows such as `sd-work-backlog` and `sd-continue`.
  Direct `trellis-brainstorm` and Trellis phase-gate behavior are upstream
  Trellis-owned. Claude Code nevertheless supports additive project rules
  under `.claude/rules/`, which gives this pack a supported integration point
  without modifying or shadowing an upstream Trellis skill.

## Requirements

- Trigger one adversarial planning pass after a batch creates or materially
  updates any active task's `prd.md`, `design.md`, or `implement.md`, before the
  plan is presented for implementation approval or an autonomous workflow
  starts implementation.
- On Claude Code, run a native Codex peer review in parallel with the host
  adversarial review. Use `codex exec` directly; do not require, inspect,
  invoke, patch, or install the OpenAI Codex Claude plugin.
- Constrain Codex to read-only review of the named planning artifacts and the
  minimum repository evidence needed to verify them. Do not grant write access
  or let the reviewer implement fixes.
- Ask Codex to challenge requirements, assumptions, scope, architecture,
  sequencing, failure handling, validation, compatibility, rollout, and
  rollback. Exclude style-only feedback and unsupported speculation.
- Aggregate and deduplicate host and Codex concerns. Verify every material
  concern against repository evidence before changing an artifact.
- Resolve each supported concern by updating the owning planning artifact;
  rebut unsupported concerns with evidence; and explicitly park genuinely
  external or product-blocked concerns. Do not enter implementation while an
  unresolved blocking concern remains.
- After artifact changes made in response to review, rerun the relevant
  adversarial review once against the converged artifact set. Stop on repeated
  concerns instead of silently looping or spending without bound.
- Treat a missing executable, incompatible CLI, authentication failure, or
  Codex runtime failure as a visible degraded optional lane. Preserve the host
  review and planning workflow; never misreport Codex as having approved.
- Avoid review calls for empty, formatting-only, generated-only, or unchanged
  planning-artifact batches.
- Preserve platform isolation: non-Claude behavior must not gain an implicit
  Codex dependency.
- Ship a concise Claude project rule that loads the canonical pack-owned review
  contract whenever Claude creates or materially updates Trellis planning
  artifacts. Do not replace or patch `trellis-brainstorm`.
- Document the trigger, review lifecycle, concern dispositions, bounded rerun,
  fallback behavior, and plugin independence in shipped guidance and specs.

## Acceptance Criteria

- [ ] A created or materially updated `prd.md`, `design.md`, or `implement.md`
      receives an adversarial review before implementation approval/start in
      every in-scope planning workflow.
- [ ] Claude Code launches a read-only native `codex exec` planning review as
      a peer lane without using plugin-managed files or commands.
- [ ] Missing or failed Codex is reported as skipped/failed while the host
      adversarial review continues and its result remains usable.
- [ ] Review output distinguishes addressed, rebutted, parked, and unresolved
      concerns with evidence; unresolved blockers prevent task start.
- [ ] A material artifact fix gets one bounded regression review, and repeated
      concerns stop for user judgment rather than looping indefinitely.
- [ ] Formatting-only or unchanged planning artifacts do not trigger paid
      Codex work.
- [ ] Non-Claude adapters and unrelated review workflows remain unchanged.
- [ ] Focused tests cover trigger detection, native CLI isolation, read-only
      invocation, result disposition, rerun bounds, failure fallback, and
      generated/template parity.
- [ ] Shipped docs/specs, generated mirrors, release metadata, fleet candidate
      evidence, and the repository-wide check are current and green.

## Out Of Scope

- Modifying or patching the OpenAI Codex Claude plugin.
- Letting the adversarial reviewer edit planning artifacts directly.
- Automatically resolving product decisions or external blockers.
- Opening an upstream Trellis pull request without separate explicit approval.

## Notes

- The review should run at the planning convergence boundary after a coherent
  artifact-edit batch, not once per file write.
- The Claude project rule covers both direct `trellis-brainstorm` and
  pack-owned SD planning flows because it is additive repository guidance, not
  a change to either workflow implementation.
