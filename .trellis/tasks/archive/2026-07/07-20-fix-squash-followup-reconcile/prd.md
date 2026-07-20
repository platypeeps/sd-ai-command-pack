# Fix squash-merge follow-up reconciliation

## Goal

Allow a paused or blocked work-loop checkpoint to reconcile an unrelated
default-branch advance after the loop already recorded a verified squash merge,
without weakening shipped-commit or pull-request identity validation.

## Requirements

- Keep `templates/scripts/sd-ai-command-pack-work-loop.py` as the source of
  truth and synchronize its installed root mirror.
- Preserve the existing merge-boundary proof that a newly submitted
  `lastShippedSha` belongs to the feature branch that was actually shipped.
- When the ledger is already on its base branch, treat an unchanged recorded
  `lastShippedSha` as historical evidence during a later head-only advance;
  validate the new base-branch head as a descendant of the remembered head,
  but do not require a squash-disconnected feature SHA to be its ancestor.
- Add a regression covering a paused post-squash follow-up checkpoint with a
  later base-branch commit and complete recovery evidence.
- Ship the fix as a patch release with synchronized manifest, changelog,
  generated catalog, and fleet-candidate evidence.

## Acceptance Criteria

- [x] The exact AMC failure shape reconciles to the later `main` head and clears
      the recovery checkpoint.
- [x] A changed or self-anchored `lastShippedSha` still fails the existing
      ancestry/branch validation.
- [x] Template and installed work-loop scripts remain byte-identical.
- [x] Focused tests, lint/type checks, the full pack gate, and fleet candidate
      validation pass.

## Notes

- Triggered by AMC work-loop run
  `5B280C42-DC10-4D1C-8E36-85C5F691E313`: PR #267 was squash-merged and the
  recorded feature SHA is intentionally not an ancestor of later `main` head
  `fa6e63fa074c7877e7cd8d84d114e06d537e8f24`.
- User explicitly authorized this specific upstream PR on 2026-07-20.
