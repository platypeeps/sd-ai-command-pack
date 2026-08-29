# Add Node Check Syntax Lint For OpenCode JS Implementation Plan

## Execution Order

1. Add a NUL-safe shell snippet that enumerates tracked OpenCode `.js` files.
2. Wire it into `.github/workflows/tests.yml` lint lane.
3. Mirror it in `Makefile lint`, respecting existing local missing-tool style.
4. Update tests that pin lint command text.
5. Demonstrate a syntax-error failure in a test or manual verification note.

## Validation Plan

Run `make lint` with Node available, plus the workflow parity tests. Run
`node --check` manually over the enumerated files if debugging is needed.

## Documentation And Spec Updates

No guide update is required unless Makefile prerequisites change.

## Review Notes

Reviewers should check filename safety and that both root and template OpenCode
copies are covered.

## Follow-Ups

If behavior bugs appear in OpenCode JS later, create a separate behavioral test
task rather than expanding syntax linting.
