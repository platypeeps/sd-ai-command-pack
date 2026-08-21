# PARKED: Upstream Claude statusline UTF-8 stdin fix

## Goal

Preserve the verified Windows UTF-8 stdin correction for the Trellis-managed
Claude status-line hook so a future Trellis update does not overwrite the
consumer remediation.

## Requirements

- Treat `.claude/hooks/statusline.py` [absent: upstream Claude Code path, not a file in this repository] as
  Trellis-owned, not a shipped
  `sd-ai-command-pack` template; do not add an independent pack copy.
- Prepare a paste-ready Trellis handoff that changes the Windows stream loop
  from stdout/stderr to stdin/stdout/stderr and updates the comment to cover
  session input as well as output.
- Include the original review evidence from
  `platypeeps/sd-github-review#28` discussion `3659455212` and fixed consumer
  commit `92f855080e5ccb668f2d93a4567e0800c80b8291`.
- Include a regression test or deterministic simulation proving a legacy
  Windows input codepage is reconfigured to UTF-8 before `sys.stdin.read()`.
- Do not open an upstream Trellis pull request without the user's explicit
  approval for that specific PR.
- After an approved upstream fix is released, refresh the affected consumer
  runtime and verify the consumer-local patch is no longer divergent.

## Acceptance Criteria

- [ ] The Trellis source-of-truth hook configures stdin, stdout, and stderr as
      UTF-8 on Windows before reading session JSON.
- [ ] Automated evidence covers non-ASCII stdin under a simulated Windows
      legacy codepage.
- [ ] Any upstream PR was opened only after explicit user approval and includes
      the consumer review evidence.
- [ ] A subsequent Trellis refresh preserves the behavior without a
      consumer-only patch.

## Notes

- Trigger: an explicit request to prepare or submit the Trellis-owned fix, or
  a Trellis refresh that would overwrite the consumer correction.
- The fleet finding classifier recorded this as non-blocking hardening because
  the affected consumer was fixed and verified in-place.
