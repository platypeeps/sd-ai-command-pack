# Correct fleet merge finalization head epochs

## Goal

Allow a required consumer finish-work successor head to re-enter fleet PR
publication before the merge action is retried, without weakening exact-head
review, CI, or housekeeping evidence.

## Background

- Campaign `fleet-v0-55-2-20260727T135308Z` published and reviewed
  `rwbp-coordinator` PR #180 at
  `24da9cb62cbcf8cbc8003cce6a3659d3a6d5b63e`.
- The controller then issued merge action
  `311c775981ba8edc5d66c64afabab0a8b9b341a3f58dbe2d87cc3b12c33b948f`.
- The required `sd-finish-work` lifecycle archived the consumer task and
  recorded its journal, advancing the PR to
  `607c8ad62759764ccb55280347ab32c69ebe60b2` and producing a valid
  exact-head completion receipt.
- The released controller accepts bounded `pr-head-advanced` republication at
  review and merge eligibility, but not at merge. It therefore cannot record
  either the old issued action or the new merge head truthfully.
- The source finding classifier returned `pause-corrective-release`; the
  original campaign is blocked and PR #180 remains open and unmerged.

## Requirements

- Accept `pr-head-advanced` for an issued merge action when its receipt names
  the current published full head and existing PR number.
- Preserve the old publication epoch and merge-action receipt append-only,
  then return the lane to one new PR-publication attempt.
- Require the successor publication receipt before review, eligibility, and a
  new serialized merge attempt may proceed.
- Keep the existing two-attempt bound so a second merge-stage head advance
  parks as `retry-exhausted` rather than looping.
- Teach `sd-fleet-refresh` to compare the PR head after `sd-finish-work`, retain
  its valid receipt, and record the old-head merge action as
  `pr-head-advanced` before invoking housekeeping when the head changed.
- Keep terminal corrective-release recovery restricted to its existing
  missing-task-evidence case; do not use it for a normal finish-work successor.
- Update source contracts, operator documentation, generated/template mirrors,
  and release evidence for one corrective patch release.
- Preserve the blocked 0.55.2 campaign, consumer branch, PR #180, and valid
  finish-work receipt for controller recovery after the patch release.

## Acceptance Criteria

- [x] Controller unit tests prove first merge-stage head advance republishes,
      exact old/new head epochs remain valid, and the successor flow can merge.
- [x] Controller unit tests prove a second merge-stage head advance exhausts
      the bounded retry and invalid uses remain rejected without mutation.
- [x] Fleet skill and documentation direct the merge owner to stop before
      housekeeping, retain finish-work evidence, and use the controller-issued
      republication path whenever finish-work advances the PR head.
- [x] Existing terminal corrective recovery remains valid and regression
      tested.
- [x] Focused tests, generated parity, full source checks, and one canonical
      all-fleet candidate validation pass for the corrective release.
- [ ] The corrective release is merged and tagged before the original
      `fleet-v0-55-2-20260727T135308Z` campaign is recovered.

## Notes

- This task is a child of the original rollout task; it does not create a
  duplicate fleet campaign.
