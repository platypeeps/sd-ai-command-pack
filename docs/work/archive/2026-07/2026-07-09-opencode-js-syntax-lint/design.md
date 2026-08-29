# Add Node Check Syntax Lint For OpenCode JS Design

## Overview

The repo already syntax-checks the review preflight `.mjs`, but shipped
OpenCode JavaScript has no equivalent gate. Add a tracked-file `node --check`
lane for root and template `.opencode` JavaScript.

## Proposal

Add a lint helper in the workflow and Makefile that derives the file set from
`git ls-files`, filtering for `.opencode/**/*.js` and
`templates/.opencode/**/*.js`. For each file, run `node --check`. Keep the
behavior parallel to the existing review-preflight syntax check: CI requires
Node, local Makefile warns if Node is unavailable unless the project chooses a
stricter local requirement.

Update any tests that pin lint command text. This pairs with the
`trellis-context.js` hardening task, but can land independently.

## Boundaries And Non-Goals

Do not add ESLint or behavior tests for vendored OpenCode plugins. This is
syntax only.

## Affected Files

- `.github/workflows/tests.yml`
- `Makefile`
- `tests/test_generated_parity.py` if it asserts lint snippets
- Potentially `tests/test_pack_drift.py` if syntax-valid source checks expand

## Risks And Edge Cases

`git ls-files` can return no files in a minimal fixture. Treat that as a clear
skip or failure depending on whether the test fixture expects OpenCode payload.
Handle spaces in filenames with NUL-delimited lists.

## Validation

Temporarily introduce a syntax error in a fixture or controlled test and assert
the lint command fails, then revert it. Run current-tree lint green.
