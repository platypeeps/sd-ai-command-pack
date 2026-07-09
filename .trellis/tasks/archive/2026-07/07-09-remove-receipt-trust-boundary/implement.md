# Constrain Remove To Manifest-Recognized Targets Implementation Plan

## Execution Order

1. Add a helper that derives recognized removal targets from the loaded
   manifest files, selected platform set, generated state files, and managed
   block targets.
2. Filter receipt/provenance candidates through that helper before calling
   `remove_pack_file()`.
3. Add a hard `.git/` rejection path that is independent of force and hash
   matching.
4. Surface ignored candidates in normal and dry-run output.
5. Add regression tests for corrupted provenance/receipt entries and verify
   legitimate pack removal still works.

## Validation Plan

Run `python3 -m unittest tests.test_remove`, then the installer coverage gate.
Use at least one dry-run test to prove ignored entries are reported without
mutation.

## Documentation And Spec Updates

If output wording changes, update the installed guide's remove section and its
template twin. Security-facing notes can point to the invariant that receipts
select candidates but do not authorize arbitrary paths.

## Review Notes

The critical review question is whether every delete path passes through the
allowlist. Check generated state cleanup and managed blocks separately.

## Follow-Ups

If the allowlist helper also helps install-audit completeness checks, share it
in a later refactor rather than blocking this security fix.
