# Revisit recorder and housekeeping wrappers after upstream Trellis APIs land

## Goal

Capture the conditional task for shrinking pack-owned recorder and housekeeping
workarounds when upstream Trellis provides structured session content and
machine-readable command output. The pack currently owns wrapper behavior
because the upstream interfaces are text-oriented or placeholder-seeded.

## Trigger

Waiting for external trigger: upstream
[mindfold-ai/Trellis#394](https://github.com/mindfold-ai/Trellis/issues/394)
or [mindfold-ai/Trellis#395](https://github.com/mindfold-ai/Trellis/issues/395)
lands with a usable released Trellis version.

Source:
`.trellis/tasks/archive/2026-07/07-06-housekeeping-recorder-robustness/prd.md`.

## Requirements

- Verify the upstream behavior in a real or fixture Trellis install before
  removing any pack workaround.
- Identify which pack wrapper paths can shrink safely:
  `sd-ai-command-pack-record-session.py`, housekeeping task/context parsing, or
  related review-preflight checks.
- Preserve placeholder-free journals, retry safety, clear errors, and
  Bash/Python compatibility.
- Keep consumer repos working across the supported Trellis version range.

## Acceptance Criteria

- [ ] The upstream Trellis release or issue resolution is linked.
- [ ] Pack wrappers are simplified only where upstream behavior covers the same
  contract.
- [ ] Recorder and housekeeping regression tests still cover the retained pack
  behavior.
- [ ] Docs/specs are updated to describe the reduced workaround surface.

## Notes

- Do not start this task until one of the upstream triggers exists.
- This is a parked task, not currently actionable backlog.
- Live check on 2026-07-20: [mindfold-ai/Trellis#395](https://github.com/mindfold-ai/Trellis/issues/395)
  closed as completed through [PR #448](https://github.com/mindfold-ai/Trellis/pull/448),
  whose migration manifest targets Trellis 0.6.8. This checkout still uses
  Trellis 0.6.7, and [#394](https://github.com/mindfold-ai/Trellis/issues/394)
  remains open for structured session content. Keep the wrappers unchanged
  until 0.6.8 is available, then scope the JSON-output cleanup independently
  while leaving structured-content cleanup parked on #394.
