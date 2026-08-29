# Close Drift-Gate Absence Blindness And Refresh Dogfood Copies Implementation Plan

## Execution Order

1. Add a failing test fixture or direct assertion for missing dogfood twins.
2. Add template-source completeness and target casefold uniqueness assertions.
3. Run `python3 install.py . --force` to restore root dogfood copies.
4. Update maintainer docs to either preserve or narrow the byte-mirror claim.
5. Run `python3 install.py . --dry-run` and confirm it reports no changes.

## Validation Plan

Run `python3 -m unittest tests.test_pack_drift tests.test_generated_parity`.
Then run the local full-check with Prism/Gito disabled.

## Documentation And Spec Updates

Update `AGENTS.md` outside the Trellis block and `.github/copilot-instructions.md`
only where their mirror wording is inaccurate. Do not edit Trellis-managed
blocks manually.

## Review Notes

Reviewers should verify that generated or cache files under `templates/` are
not accidentally treated as payload. If any tracked `__pycache__` file is
present, decide whether to remove it or explicitly exclude it as part of the
template completeness assertion.

## Follow-Ups

If the restored dogfood copies reveal adapter content drift, let
`07-09-adapter-parity-generation` own the architectural cleanup.
