# Separate sd-create-pr publish and review stages for sd-ship

## Goal

Give sd-ship a supported Stage 1 publish-only delegation so sd-create-pr does not enter standalone review before Stage 2 can apply merge-through finish-work deferral.

## Requirements

- Add an internal composite-only delegation mode that lets `sd-ship` run the
  publish/reuse portion of `sd-create-pr` without entering its standalone
  `sd-review-pr` handoff.
- Keep standalone `sd-create-pr` behavior unchanged: after publishing, it must
  still enter the normal non-deferred review loop.
- Accept the internal mode only from the active `sd-ship` chain and reject it
  as a public user argument.
- Make Stage 1 and Stage 2 ownership explicit in both shared skills so
  `until=pr`, `until=review`, and `until=merge` each invoke review exactly when
  intended.
- Preserve every update-spec, staging, push, PR creation/reuse, review, CI, and
  finish-work gate.
- Update templates, installed mirrors, usage docs, adapter specs, focused
  lifecycle tests, release metadata, and fleet candidate validation.

## Acceptance Criteria

- [ ] `sd-ship until=pr` publishes or reuses the PR and stops without running
  review.
- [ ] `sd-ship until=review` publishes in Stage 1, then runs one non-deferred
  review loop in Stage 2.
- [ ] `sd-ship until=merge` publishes in Stage 1, then runs one deferred review
  loop in Stage 2 so Stage 4 remains the finish-work owner.
- [ ] Standalone `sd-create-pr` still publishes and enters standalone review.
- [ ] Focused lifecycle tests and canonical pack/fleet validation pass.

## Notes

- Discovered while resuming PR #145 through `sd-ship`: creating the operational
  shipping task made Stage 1 necessary, exposing the duplicate review handoff.
- The current PR #145 run should preserve `sd-ship`'s explicit stage boundary
  and leave this implementation for a dedicated follow-up stream.
