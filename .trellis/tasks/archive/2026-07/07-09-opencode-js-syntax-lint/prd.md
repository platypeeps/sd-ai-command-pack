# Add node --check syntax lint for .opencode JS

## Goal

Give the vendored OpenCode JavaScript a syntax gate in CI, matching the
existing `node --check` coverage for the `.mjs` preflight, so a syntax error in
those files is caught before it ships to consumers.

## Problem

Surfaced by the 2026-07-09 testing review. CI runs `node --check` on
`scripts/sd-ai-command-pack-review-preflight.mjs` (and its template twin) and
`node --check` is already available on the runners, but the OpenCode JS —
`.opencode/plugins/*.js` and `.opencode/lib/*.js` (session-start,
inject-workflow-state, inject-subagent-context, session-utils,
trellis-context) plus their `templates/` twins — has no syntax gate and no
behavioral test (they are Trellis-vendored). A syntax error there would ship to
consumers and only fail at OpenCode session start.

This pairs naturally with `07-09-upstream-trellis-opencode-context-exec-hardening`
(which changes one of these files) — the lint gate protects the change.

## Requirements

- R1: CI's lint lane runs `node --check` over every tracked `.opencode`
  JavaScript file (root copies and `templates/` twins), failing on a syntax
  error.
- R2: The check is enumerated from tracked files (e.g. `git ls-files`) so newly
  added `.opencode` JS is covered automatically, not a hardcoded list.
- R3: Mirror the check into the Makefile lint target (or document why CI-only),
  consistent with how the `.mjs` check is wired.

## Acceptance Criteria

- [x] Introducing a deliberate syntax error into an `.opencode` JS file fails
      the lint lane (demonstrated, then reverted).
- [x] The file set is derived from tracked files, not hardcoded.
- [x] Lint lane stays green on the current tree; the parity test that pins the
      CI workflow text (`tests/test_generated_parity.py`) is updated if it
      asserts the lint commands.

## Non-goals

- Full ESLint / behavioral testing of the vendored plugins — syntax-check only,
  matching the existing `.mjs` treatment.
- Linting non-`.opencode` vendored JS outside scope.
