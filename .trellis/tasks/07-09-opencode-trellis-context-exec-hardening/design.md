# Harden Vendored Trellis-Context JS Shell Invocation Design

## Overview

The OpenCode `trellis-context.js` adapter builds a shell command with a repo
derived script path. Switch it to argument-vector execution in the pack
template, sync the dogfood copy, and record an upstream Trellis handoff.

## Proposal

Replace the ``execSync(`${PYTHON_CMD} "${scriptPath}"`)`` pattern with
`execFileSync(PYTHON_CMD, [scriptPath], options)` or the closest existing
`session-utils.js` helper style. Preserve timeout, encoding, and error handling
semantics so context injection still fails soft, but remove shell parsing from
the path boundary.

Make the edit in `templates/.opencode/lib/trellis-context.js` if that is the
tracked source, then update the root `.opencode/lib/trellis-context.js` via the
installer or byte-identical copy. Add a syntax check and, if practical, a
minimal test or manual fixture using a path with quotes or `$`.

Because the file is Trellis-vendored, include a paste-ready upstream handoff in
the task or linked note. Do not open an upstream Trellis PR without explicit
user consent.

## Boundaries And Non-Goals

Do not rewrite the OpenCode plugin runtime. Do not remove the vendored copy.

## Affected Files

- `templates/.opencode/lib/trellis-context.js`
- `.opencode/lib/trellis-context.js`
- `tests/test_generated_parity.py` or OpenCode syntax lint tests
- This task artifact for the upstream handoff/link

## Risks And Edge Cases

`PYTHON_CMD` may itself be a command name rather than an absolute path. That is
safe with `execFileSync` as long as it is passed as the file argument and not
split by spaces.

## Validation

Run `node --check` on template and root copies, pack drift, and a path quoting
fixture if feasible.
