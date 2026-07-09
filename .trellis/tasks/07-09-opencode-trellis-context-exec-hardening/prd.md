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

Because this file is a vendored adapter, the fix must ship through the pack's
`templates/` source of truth, not be hand-edited into the installed copy, and
should also be reported upstream.

## Requirements

- R1: Replace the shell-string `execSync` with `execFileSync` (or equivalent
  array-argument form) so `scriptPath` and `PYTHON_CMD` are passed as
  arguments, not interpolated into a shell command — matching
  `session-utils.js`.
- R2: The fix is made in the pack `templates/` source and propagated to the
  installed root copy via the installer, keeping the pack-drift/parity gates
  green (root copy byte-identical to template).
- R3: Report the same issue upstream to Trellis (this is vendored code); link
  the upstream reference from the task or the existing upstream-cleanup roadmap
  task.

## Acceptance Criteria

- [ ] `trellis-context.js` no longer constructs a shell string from a path;
      `node --check` passes and a repo path containing a quote/`$`/backtick no
      longer breaks context injection (manual or scripted verification note).
- [ ] `templates/` source and installed root copy are byte-identical
      (pack-drift gate green).
- [ ] Upstream report filed/linked.

## Non-goals

- Rewriting the broader OpenCode plugin/session machinery — this is a scoped
  invocation-safety fix.
- Removing the vendored copy pending upstream (tracked by the upstream-cleanup
  roadmap task).
