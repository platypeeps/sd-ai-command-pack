# Route sd-retro recorder through pack toolchain

## Goal

Ensure shared SD skills invoke pack-owned Python helpers through the pack
toolchain selector so consumers with an older system `python3` do not fail on
Python 3.10+ syntax.

## Requirements

- Route the `sd-retro` session-recorder invocation through
  `scripts/sd-ai-command-pack-toolchain.sh run-python`.
- Apply the same contract to every shared skill that directly invokes a
  pack-owned Python helper, preventing the same defect on sibling commands.
- Keep template skills and root dogfood mirrors byte-identical.
- Add regression coverage that rejects direct `python3` invocation of
  `scripts/sd-ai-command-pack-*` from shared skill templates.
- Release the consumer-visible correction as version 0.15.4.

## Acceptance Criteria

- [x] `sd-retro`, `sd-review-learnings`, `sd-update-spec`, and source-only
  `sd-fleet-refresh` route pack Python helpers through `run-python`.
- [x] Shared skill templates contain no direct
  `python3 scripts/sd-ai-command-pack-*` invocation.
- [x] Focused tests, generated parity, and the full pack gate pass.
- [x] `manifest.json` and `CHANGELOG.md` describe release 0.15.4.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
