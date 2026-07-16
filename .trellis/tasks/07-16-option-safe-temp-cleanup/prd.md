# Make shell temp cleanup option-safe

## Goal

Replace unguarded rm -f calls for generated temp paths with rm -f -- across shipped shell scripts, add a regression guard, release the fix, and refresh the fleet without consumer-local patches.

## Requirements

- Treat the pack templates as the source of truth and keep root installed
  script mirrors byte-identical.
- Make every variable-path `rm -f` cleanup in the shipped full-check,
  review-local, and shell-library scripts option-safe with `--`.
- Add a regression guard that rejects a shipped shell template containing an
  unguarded `rm -f "$..."` form.
- Release the durable fix as `0.15.2`; do not patch consumer-owned copies by
  hand.
- Reinstall the release into the active AMC rollout PR and verify the four
  Copilot comments are obsolete or resolved before resuming the fleet.

## Acceptance Criteria

- [x] No shipped shell template contains `rm -f "$..."` without `--`.
- [x] Root script mirrors match their templates.
- [x] Focused tests and `make check` pass.
- [x] `manifest.json` and the changelog identify release `0.15.2`.
- [ ] AMC receives the fix through `install.py`, not a consumer-local patch.
- [ ] The pack PR is green, comment-clean, merged, and tagged before the fleet
  rollout resumes.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
