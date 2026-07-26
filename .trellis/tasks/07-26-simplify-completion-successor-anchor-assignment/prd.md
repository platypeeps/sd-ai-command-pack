# Simplify completion successor anchor assignment

## Goal

Follow up on rwbp-coordinator PR #177 code-quality feedback by removing the redundant nearestAnchorFailure null guard from the v0.54.0 source template, preserving behavior and adding or confirming focused coverage before the next release.

## Requirements

- Remove the redundant `nearestAnchorFailure === null` guard in the completion-successor recovery loop while preserving the existing nearest-anchor behavior and diagnostics.
- Change the canonical template first and keep the root installed mirror byte-for-byte synchronized.
- Keep this cleanup out of the immutable v0.54.0 rollout; ship it through a later reviewed release.
- Retain or add focused regression coverage for valid and invalid adjacent archive/journal completion tails.

## Acceptance Criteria

- [ ] The source template assigns the invalid anchor directly before leaving the loop, with no behavioral change.
- [ ] The root installed mirror matches the template.
- [ ] Focused completion-successor tests pass and demonstrate the same invalid-anchor diagnostic.
- [ ] Pack validation and `make check` pass before publication.

## Notes

- Origin: GitHub Code Quality finding on `platypeeps/rwbp-coordinator` PR #177, discussion `discussion_r3652753600`.
- Fleet severity disposition: `continue-with-follow-ups` under the `style` contract family; this is not a v0.54.0 blocker.
