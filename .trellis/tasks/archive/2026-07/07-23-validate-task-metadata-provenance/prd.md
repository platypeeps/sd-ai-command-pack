# Validate task metadata provenance

## Goal

Require changed Trellis tasks to record machine-readable provenance when their
current backlog priority intentionally differs from a source priority, while
preserving archived task references as immutable historical evidence.

## Background

Review of `sd-github-review` PR #7 found two ambiguity classes that passed the
deterministic preflight:

- child tasks intentionally promoted P3 source issues to P2 and P1, but the
  task records did not carry the source priority or promotion rationale; and
- archived task metadata retained a reference to a roadmap deleted later,
  which was correct historical evidence but looked like a live broken link to
  a reviewer.

The preflight already excludes `.trellis/tasks/archive/**` from live
documentation path-existence checks. It also owns structural and topology
validation for changed Trellis task records. The missing contract is explicit,
bounded priority provenance plus executable coverage of the archive exemption.

## Requirements

### Optional priority provenance

- A task may declare `meta.priorityProvenance` with exactly the required
  semantic fields `sourcePriority` and `rationale`.
- When absent, ordinary task metadata retains its current behavior.
- When present, `meta.priorityProvenance` must be an object,
  `sourcePriority` and the task's current `priority` must each be one of
  `P0`, `P1`, `P2`, or `P3`, and the two priorities must differ.
- `rationale` must be a non-empty trimmed string no longer than 1,000
  characters. Diagnostics must not echo rationale content.
- Reject partial, malformed, same-priority, or oversized declarations with
  deterministic field-specific diagnostics.
- Ignore additional provenance keys so the metadata can grow compatibly
  without weakening the required fields.

### Historical path semantics

- Preserve the existing rule that archived Trellis task artifacts may mention
  repository paths deleted after the task completed.
- Add executable regression coverage that a later-deleted path referenced by
  an archived task remains accepted while the equivalent reference in an
  active task PRD is rejected.
- Do not rewrite archived tasks or weaken live PRD/spec path validation.

### Delivery

- Extend the existing task metadata integrity check in
  `templates/scripts/sd-ai-command-pack-review-preflight.mjs`; do not add a
  parallel executable.
- Synchronize the root dogfood mirror with `make sync`.
- Update the durable backend quality contract and focused preflight tests.
- Publish the new consumer-visible rejection semantics as version `0.32.0`,
  with matching changelog and exact-payload fleet candidate evidence.

## Acceptance Criteria

- [x] A valid P3-to-P2 or P3-to-P1 declaration passes and ordinary tasks
  without provenance remain unchanged.
- [x] Non-object, partial, invalid-priority, same-priority, empty-rationale,
  and oversized-rationale declarations fail with stable diagnostics.
- [x] Review-preflight executable coverage exercises both accepted and rejected
  changed task records.
- [x] An archived PRD may retain a path deleted later; an active PRD with the
  same missing path fails.
- [x] Template/root parity, focused tests, candidate validation, and
  `make check` pass for version `0.32.0`.

## Out of Scope

- Parsing free-form roadmap prose to infer a source priority.
- Requiring provenance on tasks whose source priority is unknown or unchanged.
- Changing Trellis task creation defaults or opening a Trellis upstream PR.
- Rewriting archived task or journal history.
