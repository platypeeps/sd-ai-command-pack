# Structure skill runtime contracts

## Goal

Shorten `sd-housekeeping` and `sd-update-spec` without changing their authority
or outcomes. Move deterministic state/output contracts into versioned script
JSON and move rare repository-map, architecture, and knowledge extensions into
conditionally loaded references.

## Evidence

- `templates/.agents/skills/sd-housekeeping/SKILL.md:40-183` repeats substantial
  helper behavior and expected raw output in a 246-line skill.
- `sd-update-spec` is compact overall but concentrates optional repo-map,
  architecture, and KB extension behavior into one large section.
- Housekeeping's executable already owns strong exact-head, review-thread,
  check, branch, and cleanup guards; making its result typed can reduce prose
  duplication without weakening the gate.

## Dependencies

- Coordinate the housekeeping result schema with
  `07-22-centralize-pr-eligibility-gates`; do not create a second readiness
  schema.
- No dependency on routed-review consolidation for the initial output/refactor.

## Requirements

- R1: Add or extend versioned JSON output for housekeeping status, eligibility
  evidence, finish-work head, checks, threads, merge/cleanup actions, task
  lifecycle, branch state, and stable diagnostic reason codes.
- R2: Derive human output from the structured result where practical. The skill
  interprets the result rather than duplicating exact raw lines as its primary
  contract.
- R3: Preserve housekeeping as the only merge mutation owner and retain every
  current exact-head, unresolved-thread, check, branch, no-touch, and
  protected-main guard.
- R4: Keep high-consequence safety and mutation boundaries in the canonical
  skill even when deterministic mechanics move to the helper.
- R5: Keep the normal `sd-update-spec` flow in its canonical skill and move
  optional architecture, repo-map, and KB-specific procedures into direct,
  conditionally loaded references selected from repository evidence or explicit
  invocation.
- R6: Avoid deep reference chains. A normal run loads no optional reference;
  an applicable extension loads only its direct reference.
- R7: Preserve templates as source, generated parity, existing update-spec
  helper behavior, and upstream Trellis boundary rules.
- R8: Treat this as prompt-structure work, not authority expansion or a reason
  to merge distinct lifecycle skills.

## Acceptance Criteria

- [ ] Housekeeping structured output fully represents every decision needed by
  its skill and final report, including indeterminate/failure states.
- [ ] Existing exact-head, checks, threads, merge, task archive, branch cleanup,
  no-touch, and protected-main behavior remains covered and unchanged.
- [ ] The housekeeping skill no longer pins long raw output choreography where
  stable reason codes/fields are sufficient.
- [ ] A normal update-spec run loads no architecture/map/KB extension; matching
  fixtures load exactly one direct reference and preserve current behavior.
- [ ] Reference-selection failure is visible and does not silently skip a
  required extension.
- [ ] Focused output-schema, reference-routing, generated parity, `make sync`,
  and `make check` tests pass.

## Out Of Scope

- Changing merge authority or lifecycle semantics.
- Combining housekeeping with finish-work or update-spec.
- Replacing the shared PR eligibility task.
- Optimizing prompt length by deleting safety invariants.
