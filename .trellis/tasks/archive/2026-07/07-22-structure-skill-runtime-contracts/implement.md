# Implementation plan: structure skill runtime contracts

## 1. Inventory Decision Inputs And Outputs

- Map every housekeeping skill decision to helper evidence and current tests.
- Classify update-spec content as core or optional extension.

## 2. Add Typed Housekeeping Output

- Add a read-only stdlib result builder and ship it beside housekeeping.
- Add `--json` to housekeeping, keeping default human output unchanged and
  reserving JSON-mode stdout for one final document.
- Add stable action/anomaly codes at each Bash decision boundary.
- Extend the PR evaluator with a combined JSON-plus-shell adapter format so
  housekeeping embeds the shared eligibility result without rerunning remote
  evidence collection.
- Embed the delegated `sd-status --json` report rather than adding a parallel
  final-state collector.
- Derive `clean|blocked|indeterminate|failed` and result reason codes from the
  embedded status, eligibility, action, and anomaly evidence.

## 3. Reduce Housekeeping Prose

- Keep authority, safety, mutation boundary, recovery, and interpretation.
- Remove duplicated raw output/state choreography only after field-level tests
  prove equivalent observability.

## 4. Split Optional Update-Spec Guidance

- Create direct `architecture.md`, `repository-map.md`, and `obsidian-kb.md`
  references under the canonical skill.
- Register the references once so generation fans them out to every installed
  skill root and manifest target.
- Keep Trellis delegation, extension ordering, selection criteria, the normal
  KB helper invocation, safety boundaries, and final report shape in the core
  skill.
- Load zero optional references for a routine spec-only run; load each selected
  direct reference at most once, with no reference-to-reference chains.
- Make missing, unreadable, empty, unsafe, or contradictory selected references
  visible failures rather than silent skips.

## 5. Validate

- Add builder schema/classification/invalid-input tests, combined eligibility
  rendering tests, and end-to-end housekeeping human/JSON lifecycle tests.
- Add update-spec zero/one/multiple-extension routing assertions plus selected
  reference failure tests.
- Register any new shipped helper in manifest/provenance, per-file coverage,
  docs, version/changelog, and full-fleet candidate evidence.
- Run focused output-schema, housekeeping lifecycle, update-spec routing,
  generated parity, `make sync`, fleet candidate validation, and `make check`.

## Stop Points

- Stop if any safety decision still depends on an unstructured raw line; add a
  typed field before removing the prose contract.
- Stop if optional reference extraction creates a multi-hop loading chain.
