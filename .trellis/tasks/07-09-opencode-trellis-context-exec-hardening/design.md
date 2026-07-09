# Harden Vendored Trellis-Context JS Shell Invocation Design

## Overview

The OpenCode `trellis-context.js` adapter builds a shell command with a repo
derived script path. Switch the current vendored copy to argument-vector
execution and record an upstream Trellis handoff.

## Proposal

Replace the ``execSync(`${PYTHON_CMD} "${scriptPath}"`)`` pattern with
`execFileSync(PYTHON_CMD, [scriptPath], options)` or the closest existing
`session-utils.js` helper style. Preserve timeout, encoding, and error handling
semantics so context injection still fails soft, but remove shell parsing from
the path boundary.

Make the edit in the current source-of-truth file,
`.opencode/lib/trellis-context.js`. If the implementation introduces a shipped
template twin later, keep that twin synchronized through the normal pack
payload flow. Add a syntax check and, if practical, a minimal test or manual
fixture using a path with quotes or `$`.

Because the file is Trellis-vendored, include a paste-ready upstream handoff in
the task or linked note. Do not open an upstream Trellis PR without explicit
user consent.

## Boundaries And Non-Goals

Do not rewrite the OpenCode plugin runtime. Do not remove the vendored copy.

## Affected Files

- `.opencode/lib/trellis-context.js`
- `tests/test_generated_parity.py` or OpenCode syntax lint tests
- This task artifact for the upstream handoff/link

## Risks And Edge Cases

`PYTHON_CMD` may itself be a command name rather than an absolute path. That is
safe with `execFileSync` as long as it is passed as the file argument and not
split by spaces.

## Validation

Run `node --check .opencode/lib/trellis-context.js`, pack drift checks, and a
path quoting fixture if feasible. Add any future template twin to the same
validation once it exists.
