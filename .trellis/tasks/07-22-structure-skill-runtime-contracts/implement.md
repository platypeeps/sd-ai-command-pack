# Implementation plan: structure skill runtime contracts

## 1. Inventory Decision Inputs And Outputs

- Map every housekeeping skill decision to helper evidence and current tests.
- Classify update-spec content as core or optional extension.

## 2. Add Typed Housekeeping Output

- Reuse the shared PR eligibility schema.
- Add versioned action/lifecycle/cleanup results and stable reason codes.
- Derive human output from the structured result where possible.

## 3. Reduce Housekeeping Prose

- Keep authority, safety, mutation boundary, recovery, and interpretation.
- Remove duplicated raw output/state choreography only after field-level tests
  prove equivalent observability.

## 4. Split Optional Update-Spec Guidance

- Create direct references for architecture/map/KB extensions.
- Add deterministic selection and missing-reference failure behavior.
- Keep normal update-spec behavior unchanged.

## 5. Validate

- Run output schema/compatibility, housekeeping lifecycle, update-spec routing,
  generated parity, `make sync`, and `make check` tests.

## Stop Points

- Stop if any safety decision still depends on an unstructured raw line; add a
  typed field before removing the prose contract.
- Stop if optional reference extraction creates a multi-hop loading chain.
