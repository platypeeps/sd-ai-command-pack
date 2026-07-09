# Add Server-Side Backstop For Direct Main Pushes Implementation Plan

## Execution Order

1. Decide whether the check lives as an inline workflow step or a reusable
   script under `scripts/`.
2. Implement changed-path collection using the push before/after SHAs and
   rename-safe diff options.
3. Add tests that exercise the path classifier outside GitHub Actions.
4. Wire the step into `push` to `main` without affecting pull-request lanes.
5. Document the local hook plus CI backstop relationship.

## Validation Plan

Run the focused classifier tests, workflow parity tests if present, and
`zizmor --offline .github/workflows/`. Manually dry-run the script in a temp
repo with a rename-into-chore case.

## Documentation And Spec Updates

Update README/CONTRIBUTING direct-main guidance to say local hook is the
preventive control and CI is the server-side backstop.

## Review Notes

Reviewers should check branch-creation and forced-update behavior. Ambiguous
diffs should fail closed.

## Follow-Ups

If this duplicates a lot of pre-push logic, consider a later shared helper, but
do not block the backstop on refactoring.
