# Decision: housekeeping result schema compatibility

Status: decided (2026-07-28). Owner task:
`07-28-decide-housekeeping-result-schema-compatibility`.

## Decision

Treat the removal of `invocation.finishWorkHead` from the schema-version-1
housekeeping result as an **explicit, documented in-major migration** — not a
deprecated alias and not a silent removal. Schema major stays `1`; there is
**no deprecation window** and no compatibility alias.

The rejected alternative — retaining `finishWorkHead` as a deprecated alias
derived from `finishWork.headOid` — is declined because it directly
contradicts the parent task and the shipped contract (see Reconciliation).

## Consumer inventory (schema-version-1 housekeeping results)

Performed before choosing a policy, per the PRD.

- **Shipped pack code**: `invocation.finishWorkHead` appears in **no** file
  under `templates/`, `scripts/`, `installer/`, `docs/`, or `.trellis/spec/`.
  The composer emits, and downstream code reads, only the current fields.
- **Result consumers**: `sd-ai-command-pack-housekeeping.sh` composes the
  result and the `sd-housekeeping` skill interprets the typed `identity`,
  `eligibility`, `actions`, `anomalies`, `outcome`, and `status` fields. None
  reads `invocation.finishWorkHead`.
- **Documented contract**: `adapter-guidelines.md` never named
  `invocation.finishWorkHead` as a public field and explicitly forbids a
  "compatibility head-attestation option". Public `docs/` do not describe the
  field either. No document claims an unchanged schema that included it.
- **Tests**: `tests/test_housekeeping_result.py` pins `schemaVersion == 1`,
  the verified `identity.finishWork` object (with `headOid`), and
  `invocation.finishWorkReceiptProvided`. No test references `finishWorkHead`.
- **Fleet/external installs**: consumer repositories re-consume through their
  own installed skill and scripts, refreshed by the (separately gated) fleet
  rollout. The verified head remains available at
  `identity.finishWork.headOid`, strictly more authoritative than the retired
  invocation echo.

Conclusion: the inventory proves there is **no consumer** — shipped,
documented, or tested — of `invocation.finishWorkHead`. The PRD's default
("preserve the alias unless the inventory proves there are no consumers")
therefore resolves against the alias.

## Schema behavior

- `schemaVersion` remains `1`.
- Authoritative finish-work head: `identity.finishWork.headOid`, gated by
  `identity.finishWork.verified` (independently recomputed exact-head proof).
- `invocation.finishWorkReceiptProvided` is a boolean provenance flag only.
- `invocation.finishWorkHead` is absent by contract; its former value is
  adapted into the verified `identity.finishWork` object.
- The retired caller-trusted `--finish-work-head` CLI input is not restored.

The migration is made non-silent by: a migration record in the composer module
docstring (the shipped source of truth), this decision record, and focused
tests that pin the absence and the relocated verified head.

## Reconciliation

- **Parent R6** (`07-24-support-planning-only-pr-finalization`): "Replace the
  bare `finishWorkRequired`/`finishWorkHead` trust decision with independently
  verified typed evidence." Its PRD forbids "compatibility aliases or hidden
  duplicate modes" and lists "Preserving the bare finish-work-head attestation
  as an alias or fallback" as out of scope; its design says "Remove
  `--finish-work-head`, `finishWorkRequired`, `finishWorkHead`". This decision
  is consistent: removal is real and now explicitly documented, with no alias.
- **Public docs / spec**: contain no contradictory compatibility statement;
  `adapter-guidelines.md` already forbids the head-attestation option. No doc
  edit is required to remove a contradiction; the migration is documented at
  the composer source of truth.
- **Result composer**: documents the retirement and the verified replacement.
- **Tests**: prove the absence semantics and the relocated verified head.

## Acceptance criteria mapping

- Explicit decision + rationale + schema behavior + (no) deprecation window —
  this record.
- No contradictory compatibility statements in parent/docs — verified above.
- Tests prove versioned migration/absence semantics for old consumers —
  `tests/test_housekeeping_result.py` migration cases.
- Receipt-based exact-head eligibility stays authoritative; `--finish-work-head`
  not restored — parser rejection test + verified evidence path.
- Template/root parity, focused result tests, `make check` pass — run in this
  package's checks.

## Source finding

`platypeeps/people-profiles` PR #3 review thread on
`sd-ai-command-pack-housekeeping-result.py`, observed 2026-07-27 UTC.
