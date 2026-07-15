# Evaluate pack workaround cleanup after upstream Trellis issues close

## Goal

Capture the conditional task for doing a broader cleanup pass after the filed
upstream Trellis issues close. The pack should periodically check whether local
workarounds are still necessary once upstream has accepted, rejected, or shipped
the requested capabilities.

## Trigger

Waiting for external trigger: one or more of these upstream issues closes:

- [mindfold-ai/Trellis#394](https://github.com/mindfold-ai/Trellis/issues/394)
- [mindfold-ai/Trellis#395](https://github.com/mindfold-ai/Trellis/issues/395)
- [mindfold-ai/Trellis#396](https://github.com/mindfold-ai/Trellis/issues/396)
- [mindfold-ai/Trellis#397](https://github.com/mindfold-ai/Trellis/issues/397)

Source:
`.trellis/tasks/archive/2026-07/07-07-file-upstream-trellis-issues/implement.md`.

## Requirements

- Check each closed upstream issue's final resolution and released Trellis
  availability.
- Decide whether the pack should remove, shrink, or keep each related
  workaround.
- Create narrower implementation tasks if cleanup spans unrelated pack areas.
- Keep the no-upstream-PR-without-consent rule intact; this task only evaluates
  pack-side cleanup.

## Acceptance Criteria

- [ ] Closed upstream issue resolutions are linked and summarized.
- [ ] Each related pack workaround has an explicit keep/shrink/remove decision.
- [ ] Follow-up implementation tasks are created for cleanup that is too large
  for one change.
- [ ] If no cleanup is warranted, the PRD records why.

## Notes

- Do not start this task until at least one listed issue closes.
- This is a parked task, not currently actionable backlog.
- Live check on 2026-07-14: issues #394, #395, and #396 remain open. Issue
  #397 closed as completed on 2026-07-09. Trellis 0.6.7 now provides
  `task.py create --no-start`, and this checkout's generated `task.py` is
  byte-identical to that canonical source. The pack has no #397-specific
  workaround to shrink or remove, so no local cleanup is warranted.
