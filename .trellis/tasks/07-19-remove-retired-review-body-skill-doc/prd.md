# Remove retired review-body fallback from shipped skill documentation

## Goal

Remove the expired REVIEW_PREFLIGHT_PR_BODY fallback from current shipped guidance and extend regression coverage across shipped documentation surfaces.

## Confirmed Facts

- The fallback was removed in version 0.16.0 and is recorded as removed in the
  changelog.
- The current shipped `sd-full-check` skill still advertises the retired
  variable as a deprecated compatibility fallback.
- Existing retirement coverage checks selected installed guides but does not
  cover every shipped skill documentation surface.
- Historical changelog and archived task references are records and may retain
  the variable name.

## Requirements

- Remove the retired fallback from the canonical shipped `sd-full-check` skill
  and synchronize its installed mirror.
- Extend the retirement regression to inspect all current shipped
  documentation and skill surfaces where users could discover supported
  configuration.
- Distinguish current shipped guidance from historical records so the guard
  does not require rewriting changelog entries or archived Trellis evidence.
- Do not reintroduce runtime support or change current PR-body resolution
  behavior.

## Acceptance Criteria

- [ ] No current shipped command, skill, guide, or reference advertises
      `REVIEW_PREFLIGHT_PR_BODY` as supported configuration.
- [ ] Historical changelog and Trellis task/audit records remain intact.
- [ ] A focused regression fails when the retired variable is reintroduced in
      any current shipped documentation or skill surface.
- [ ] The canonical template and installed `sd-full-check` skill are
      byte-identical.
- [ ] Focused review-scope tests, source/template parity checks, and full-check
      pass.

## Out of Scope

- Changing PR-body scope semantics or adding a replacement environment
  variable.
- Rewriting historical release notes, archived tasks, or audit evidence.

## Notes

- Origin: audit finding A-036 in `.trellis/audit/report-2026-07-19.md`.
- This is a lightweight documentation and regression-coverage task and is
  ready to remain PRD-only.
