# Simplify completion successor anchor assignment

## Goal

Follow up on rwbp-coordinator PR #177 code-quality feedback by removing the redundant nearestAnchorFailure null guard from the v0.54.0 source template, preserving behavior and adding or confirming focused coverage before the next release.

## Requirements

- Remove the redundant `nearestAnchorFailure === null` guard in the completion-successor recovery loop while preserving the existing nearest-anchor behavior and diagnostics.
- Change the canonical template first and keep the root installed mirror byte-for-byte synchronized.
- Keep this cleanup out of the immutable v0.54.0 rollout; ship it through a later reviewed release.
- Retain or add focused regression coverage for valid and invalid adjacent archive/journal completion tails.

## Acceptance Criteria

- [x] The source template assigns the invalid anchor directly before leaving the loop, with no behavioral change.
- [x] The root installed mirror matches the template.
- [x] Focused completion-successor tests pass and demonstrate the same invalid-anchor diagnostic.
- [x] Pack validation and `make check` pass before publication.

## Completion note (2026-08-04)

- Guard removed in the canonical template `templates/scripts/sd-ai-command-pack-review-preflight.mjs`
  and mirrored byte-for-byte into `scripts/sd-ai-command-pack-review-preflight.mjs`
  (`if (nearestAnchorFailure === null) nearestAnchorFailure = anchor;` → `nearestAnchorFailure = anchor;`).
  The guard was provably always-true: `nearestAnchorFailure` is `null` on entry and every path
  reaching the assignment `break`s immediately, so the loop assigns it at most once.
- Regression coverage confirmed (no new tests needed): `test_completion_successor_rejects_invalid_nearest_anchor`
  (invalid tail → rc 1, `["completion_successor_anchor_invalid"]`) and
  `test_completion_successor_recovers_post_archive_review_fixes` (valid tail) both pass.
- Because the edit touches shipped payload, it ships as release **0.64.6**: `manifest.json`
  bumped 0.64.5→0.64.6, matching `CHANGELOG.md` heading added, command-catalog twins and the
  install manifest/provenance regenerated, and the fleet candidate ledger re-validated across all
  8 consumers (packVersion 0.64.6). `make check` green.

## Notes

- Origin: GitHub Code Quality finding on `platypeeps/rwbp-coordinator` PR #177, discussion `discussion_r3652753600`.
- Fleet severity disposition: `continue-with-follow-ups` under the `style` contract family; this is not a v0.54.0 blocker.
- Lightweight task; PRD-only is appropriate. Classified 2026-07-28: removing one redundant
  null guard in one template, syncing the mirror, and keeping an existing regression test
  green. Behavior-preserving by requirement, so there is no contract, migration, or
  rollback shape to design; the only sequencing constraint (ship after v0.54.0) is already
  a requirement above.
