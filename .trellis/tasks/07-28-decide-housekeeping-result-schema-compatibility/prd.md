# Decide housekeeping result schema compatibility

## Goal

Resolve whether schema-version-1 housekeeping results must retain finishWorkHead as a deprecated alias or adopt an explicit schema migration.

## Background

- The receipt-based housekeeping result removed the previously emitted
  `invocation.finishWorkHead` field while retaining schema version 1.
- The parent task's R6 currently requires removing the retired attestation
  instead of maintaining dual compatibility.
- Copilot review on `platypeeps/people-profiles` PR #3 identified the conflict:
  removing a field under the same schema major can break existing consumers.
- `templates/scripts/sd-ai-command-pack-housekeeping-result.py` is the shipped
  source of truth; the root script is its byte-verified mirror.

## Requirements

- Inventory documented and tested consumers of schema-version-1 housekeeping
  results before choosing a compatibility policy.
- Record one explicit outcome before implementation:
  - retain `finishWorkHead` as a deprecated alias for a bounded migration
    window, derived only from verified `finishWork.headOid`; or
  - make the removal an explicit schema migration with deterministic rejection
    or adaptation of the prior schema.
- Do not silently remove the field while continuing to claim an unchanged
  schema contract.
- Preserve the receipt and independently verified `finishWork` object as the
  authoritative merge eligibility evidence; an alias must not restore the
  retired caller-trusted `--finish-work-head` path.
- Reconcile the selected policy with the parent task's R6, public docs, result
  composer, and focused compatibility tests.
- Update the template first and keep the root script byte-identical.

## Acceptance Criteria

- [ ] The task records an explicit compatibility decision, rationale, schema
  behavior, and any bounded deprecation window.
- [ ] Parent-task requirements and public result documentation contain no
  contradictory compatibility statements.
- [ ] Tests prove either the deprecated alias mapping and absence semantics or
  the versioned migration/rejection behavior for old consumers.
- [ ] Receipt-based exact-head eligibility remains authoritative and the
  retired `--finish-work-head` CLI is not restored.
- [ ] Template/root parity, focused result tests, and `make check` pass.

## Out of Scope

- Reintroducing caller-trusted finish-work head attestations.
- Changing unrelated housekeeping result fields or merge eligibility rules.
- Selecting a compatibility outcome without the consumer inventory required
  above.

## Notes

- Source finding: `platypeeps/people-profiles` PR #3 review thread on
  `sd-ai-command-pack-housekeeping-result.py`, observed 2026-07-27 UTC.
- Recommended default for evaluation: preserve the alias for one bounded
  compatibility window unless the inventory proves there are no consumers.
