## Summary

<!-- 1-3 bullets: what changed and why. Name every behavior change in the diff. -->
<!-- If the diff touches copied pack/Trellis tooling, broad automation, or
CI/review files, add the matching explicit scope section on its own line —
"Tooling/generated scope:", "Automation scope:", or "CI/review scope:" — as
described in docs/SD_AI_COMMAND_PACK.md. -->

## Test plan

<!-- Focused checks first, then the local gate. -->

- [ ] Focused local checks:
- [ ] Local gate: `bash scripts/sd-ai-command-pack-full-check.sh`

## Pre-PR checklist

<!-- Tick each item once confirmed, or replace the box with "N/A — reason". -->

- [ ] Docs, help text, and env-var references match the changed behavior
- [ ] Failure paths keep state consistent (no mutate-before-success)
- [ ] Helper errors are caught at entrypoints and reported, not raw tracebacks
- [ ] Portability checked (macOS/BSD vs GNU tools, CRLF, Windows paths)
- [ ] Copied pack/Trellis files changed only via the pack installer
- [ ] Trellis journals and task notes carry real content, no placeholders
- [ ] Review fixes are batched: address all comments, re-run the gate, push once
