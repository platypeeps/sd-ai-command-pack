# Verify the ported integration-only review path against a live consumer PR head

> **This task exists because a merge was deliberately made on incomplete
> evidence.** PR #535 (`08-21-port-integration-only-profile`) shipped with its
> first acceptance criterion unticked, on an explicit operator decision
> recorded 2026-08-22. This task carries that criterion until it is genuinely
> met. Do not tick it in the parent task from inspection, from a dry run, or
> from this PRD.

## Problem

`08-21-port-integration-only-profile` moved the fleet integration-only review
profile from `sd-review-pr` onto `sd-review`, and repointed
`sd-fleet-refresh`'s `review` action to match. Everything about it is verified
by test **except** that it actually works end to end against a real PR.

Its criterion 1 reads:

> `sd-fleet-refresh` completes an integration-only review through `sd-review`
> against a real PR head, with the classifier consulted and the
> `review-result` return honored.

At merge time no fleet consumer had an open PR — all nine were checked. There
was no live head to review against, and manufacturing one means an
outward-facing push to another repository purely to satisfy a test. The
verification was deferred to the next fleet refresh, where consumer PRs are
created as ordinary output.

## Requirements

R1. On the next `sd-fleet-refresh` campaign, let the `review` action run its
    integration-only path through `sd-review` against a real consumer PR head.
    Do not force `remote-review` to avoid the new path.

R2. Record, in `.trellis/tasks/08-21-port-integration-only-profile/`:
    the `fleet-review-classify.py` JSON output, the `review-result` `sd-review`
    returned, the consumer name, and the full classified/local/PR head SHAs.

R3. Confirm the observable behaviors the port claims:
    - the classifier was consulted and reported `eligible: true`;
    - `classified-head`, the live local head, and the PR head were identical;
    - `0` remote rounds were recorded and no new review request was sent;
    - existing review events, comments, and threads were still inspected;
    - finish-work was deferred, not run by `sd-review`.

R4. Confirm the option-B deferral disposition specifically. If the PR was
    already merged when review ran, `sd-review` must have returned
    `deferral: cancelled` / `deferral-reason: pr-already-merged` and left the
    finish-work call to `sd-fleet-refresh` — not run it itself.

R5. If any of R3 or R4 does not hold, do **not** patch this task's evidence to
    match. Record what actually happened and fall back to design option A
    (narrow `sd-review/SKILL.md`'s no-housekeeping line), which
    `08-21-port-integration-only-profile/design.md` names as the recorded
    fallback.

R6. Only after R2-R4 hold, tick criterion 1 in
    `08-21-port-integration-only-profile/prd.md` and archive that task.

## Rollback

If the path is broken in a way that stalls a refresh, revert
`sd-fleet-refresh`'s `review` action to invoke `sd-review-pr`. That is a
one-line change, and `sd-review-pr` still runs its own integration-only path —
PR #535 deleted nothing. Children
`08-21-delete-review-pr-surface` and `08-21-retire-full-check-family` must not
land until this task is green, because they remove that fallback.

## Acceptance Criteria

- [ ] A real `sd-fleet-refresh` integration-only review ran through `sd-review`
      against a live consumer PR head.
- [ ] The classifier output and returned `review-result` are recorded in
      `08-21-port-integration-only-profile/`, with full SHAs.
- [ ] Every behavior in R3 is confirmed from that recorded evidence, not from
      skill text.
- [ ] The deferral disposition in R4 is confirmed, or option A is adopted with
      the reason recorded.
- [ ] Criterion 1 of `08-21-port-integration-only-profile` is ticked and that
      task is archived.

## Out Of Scope

- Creating a consumer PR solely to run this check. Use a refresh that was
  going to happen anyway.
- Deleting any `sd-review-pr` surface. That is children 2 and 3.
