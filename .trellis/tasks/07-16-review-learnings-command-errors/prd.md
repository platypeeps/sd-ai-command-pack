# Handle review-learnings command errors

## Goal

Import and handle CommandError in the shipped review-learnings helper so git/gh availability and timeout failures emit structured diagnostics; add focused regression coverage and release 0.15.3.

## Requirements

- Treat shared-helper `CommandError` failures from local Git scans as expected
  CLI errors and report them with the existing
  `[sd-review-learnings:findings]` tag.
- Treat shared-helper `CommandError` failures from GitHub comment collection as
  expected CLI errors and report them with the existing
  `[sd-review-learnings:github]` tag.
- Preserve exit code `2` for both failure classes and never leak a traceback.
- Keep the shipped template and root mirror byte-identical.
- Release the consumer-visible correction as version 0.15.3.

## Acceptance Criteria

- [x] Missing-command and timeout-style `CommandError` failures are caught in
      both the findings and GitHub phases.
- [x] Focused tests assert the phase-specific diagnostic, exit code `2`, and
      absence of a traceback.
- [x] Template/mirror parity and the complete pack check pass.
- [x] `manifest.json` and `CHANGELOG.md` describe release 0.15.3.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
