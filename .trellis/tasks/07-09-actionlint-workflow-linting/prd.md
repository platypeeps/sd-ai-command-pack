# Evaluate actionlint workflow linting when workflow syntax defects appear

## Goal

Capture the conditional task for adding `actionlint` coverage to the pack.
The current security and CI lanes already cover the known workflow risks, so
`actionlint` should not be added until a concrete GitHub Actions workflow syntax
defect proves the extra dependency and maintenance burden are worth it.

## Trigger

Waiting for external trigger: a real workflow syntax defect, review finding, or
CI failure that would have been caught by `actionlint` but is not caught by the
current `zizmor`, workflow-pip, lint, or full-check coverage.

Source: `.trellis/tasks/archive/2026-07/07-03-pack-shell-lint/prd.md` and
`.trellis/tasks/archive/2026-07/07-06-ci-skip-backstop-lint-lane/prd.md`.

## Requirements

- Confirm the motivating defect is workflow syntax or action-usage shape that
  `actionlint` catches better than existing gates.
- Choose a pinned, reproducible way to run `actionlint` locally and in CI.
- Keep the new lane low-noise on macOS and Ubuntu.
- Document the install/update implications if the tool adds new dependencies.

## Acceptance Criteria

- [ ] A concrete triggering defect is linked in this PRD.
- [ ] `actionlint` runs in CI and the local full-check or documented maintainer
  workflow, with version pinning.
- [ ] Existing workflow checks remain green and no duplicated gate creates
  noisy false positives.
- [ ] README or maintainer docs explain the new lint requirement if needed.

## Notes

- Do not start this task until the trigger exists.
- This is a parked task, not currently actionable backlog.
