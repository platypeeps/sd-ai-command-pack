## Summary

<!-- 1-3 bullets: what changed and why. Name every behavior change in the diff. -->

## Test plan

<!-- Focused checks first, then the local gate. -->

- [ ] Focused local checks:
- [ ] Local gate: `sd gate check --base main`

## Pre-PR checklist

<!-- Tick each item once confirmed, or replace the box with "N/A — reason". -->

- [ ] Docs, help text, and env-var references match the changed behavior
- [ ] Failure paths keep state consistent (no mutate-before-success)
- [ ] Helper errors are caught at entrypoints and reported, not raw tracebacks
- [ ] Portability checked (macOS/BSD vs GNU tools, CRLF, Windows paths)
- [ ] Work item pages under `docs/work/` carry real content, no placeholders
- [ ] Review fixes are batched: address all comments, re-run the gate, push once

<!-- Closing block. Keep this order: attribution paragraph first, trailers
LAST, and nothing after them. A squash merge concatenates this body into the
commit message, and git reads trailers only out of the message's final
paragraph. GitHub appends its own `Co-authored-by:` line on squash: to an
existing trailer block it appends contiguously, which is fine because that is
a trailer too; after anything else it opens a new paragraph, which demotes
every trailer above it to prose no tool can read (sd:640, sd:5). Keep the
trailer lines contiguous, with no blank line among them.
Write no association, delivery or authorship line here. sd-ship appends the
`Work` line to the body it publishes, and the `Item`, `Delivers` and
authorship lines to the squash message; `sd-ship body` shows the result
(sd:1870). A merge made without sd-ship writes them by hand, as WORKFLOW.md
says. -->

🤖 Generated with [Claude Code](https://claude.com/claude-code)
https://claude.ai/code/session_<id>

Refs: sd:<other>
