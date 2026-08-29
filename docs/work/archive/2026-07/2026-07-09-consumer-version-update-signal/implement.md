# Give Consumers A Pack-Version Update Signal Implementation Plan

## Execution Order

1. Choose the delivery surface, preferably an optional install-audit flag to
   avoid another shipped command.
2. Add reference manifest loading with clear warnings and no hard failure.
3. Add version comparison output while preserving existing exit codes.
4. Document one command a consumer can run against a local pack checkout.
5. Add focused install-audit tests for each compare state.

## Validation Plan

Run `python3 -m unittest tests.test_install_audit` and the shipped-scripts
coverage gate. Run the command manually against this checkout as the upstream
reference.

## Documentation And Spec Updates

Update the installed guide twins near refresh mechanics. Mention that the check
is advisory and that refreshes should still be committed through PRs.

## Review Notes

Reviewers should check that unavailable upstream references do not break
existing audit automation.

## Follow-Ups

After tags are contiguous, consider an optional tag-based comparison mode if
local checkout comparison is not enough.
