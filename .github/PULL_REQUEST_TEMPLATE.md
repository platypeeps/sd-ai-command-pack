## Summary

<!-- 1-3 bullets: what changed and why. Name every behavior change in the diff. -->
<!-- If the diff touches copied pack/Trellis tooling, broad automation, or
CI/review files, add the matching explicit scope section on its own line —
"Tooling/generated scope:", "Automation scope:", or "CI/review scope:" — as
described in .github/copilot-instructions.md. A pack-version adoption PR, whose diff
is only files the pack itself installs, does not need one. -->

## Test plan

<!-- Focused checks first, then the local gate. -->

- [ ] Focused local checks:
- [ ] Local gate: `make check`

## Pre-PR checklist

<!-- Tick each item once confirmed, or replace the box with "N/A — reason". -->

- [ ] Docs, help text, and env-var references match the changed behavior
- [ ] Failure paths keep state consistent (no mutate-before-success)
- [ ] Helper errors are caught at entrypoints and reported, not raw tracebacks
- [ ] Portability checked (macOS/BSD vs GNU tools, CRLF, Windows paths)
- [ ] Copied pack/Trellis files changed only via the pack installer
- [ ] Trellis journals and task notes carry real content, no placeholders
- [ ] Review fixes are batched: address all comments, re-run the gate, push once

<!-- Closing block. Keep this order: attribution paragraph first, trailers
LAST, and nothing after them. A squash merge concatenates this body into the
commit message, and git reads trailers only out of the message's final
paragraph. GitHub appends its own `Co-authored-by:` line on squash: to an
existing trailer block it appends contiguously, which is fine because that is
a trailer too; after anything else it opens a new paragraph, which demotes
every trailer above it to prose no tool can read (sd:640, sd:5). Keep the
trailer lines contiguous, with no blank line among them. Omit `Item:` and
`Delivers:` when the change has no work item; `Delivers:` only on the one
merge that completes it. -->

🤖 Generated with [Claude Code](https://claude.com/claude-code)
https://claude.ai/code/session_<id>

Item: sd:<id>
Delivers: sd:<id>
Refs: sd:<other>
