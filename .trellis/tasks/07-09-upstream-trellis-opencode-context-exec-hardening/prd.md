# Harden vendored trellis-context.js shell invocation

## Goal

Stop the vendored OpenCode `trellis-context.js` from building a shell command
string around a filesystem path, which breaks (and could inject) on repo paths
containing shell metacharacters — on every OpenCode session start.

## Problem

Surfaced by the 2026-07-09 tooling review (INFO, CONFIRMED). At
`.opencode/lib/trellis-context.js:265` the code runs:

```js
execSync(`${PYTHON_CMD} "${scriptPath}"`)
```

`scriptPath` is derived from the repo location, so a repo path containing a
double quote, `$`, or backtick breaks the command or injects shell syntax. The
upstream OpenCode sibling helper named `session-utils.js` already does this
correctly with `execFileSync` and array args. The call is Trellis-vendored,
errors are swallowed, and it has a 10s timeout — but it executes on every
OpenCode session start, so a mis-quoted path silently disables Trellis context
injection (or worse) for that session.

This file is Trellis-owned generated runtime, not pack payload: it appears in
the platform registry only as an active marker/local-only exclude and has no
entry in `manifest.json`. A consumer-side or pack-repo edit would be overwritten
by `trellis update`. The durable fix therefore belongs upstream in Trellis.

## Requirements

- R1: Preserve a paste-ready Trellis handoff for replacing shell-string
  `execSync` with `execFileSync` (or equivalent array-argument execution).
- R2: Do not modify or review `.opencode/lib/trellis-context.js` in this pack.
- R3: Keep this task parked until the user explicitly approves upstream Trellis
  work or upstream ships the fix.

## Acceptance Criteria

- [x] Pack ownership verified: `trellis-context.js` is absent from
      `manifest.json` and pack templates.
- [x] No Trellis-owned runtime was modified or reviewed in this task.
- [x] Paste-ready upstream handoff recorded below.

## Paste-Ready Upstream Handoff (2026-07-14)

```markdown
Task: harden OpenCode trellis-context.js process invocation.

Repo: mindfold-ai/Trellis
Canonical file: packages/cli/src/templates/opencode/lib/trellis-context.js

The helper builds a shell command by interpolating `PYTHON_CMD` and
`scriptPath`, so repository paths containing quotes, dollar signs, backticks,
or other shell metacharacters can break or inject into every OpenCode
session-start invocation. Replace it with
`execFileSync(PYTHON_CMD, [scriptPath], options)` (matching the sibling
session-utils.js pattern), retain timeout/encoding behavior, and add a
regression test using metacharacters in the repo path. The generated consumer
copy is Trellis-owned; sd-ai-command-pack intentionally does not patch it. Do
not open an upstream PR without the user's explicit consent.
```

## Non-goals

- Rewriting the broader OpenCode plugin/session machinery — this is a scoped
  invocation-safety fix.
- Removing the vendored copy pending upstream (tracked by the upstream-cleanup
  roadmap task).
