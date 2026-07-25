# sd-review Finding Adjudication Operations Design

## Flow

```text
sd-review findings list/status -> read-only bounded router query
sd-review findings adjudicate
  -> read current finding + policy
  -> render proposed event and required trust
  -> obtain explicit operator decision
  -> invoke trusted no-checkout workflow
  -> validate event/receipt or report reconciliation
```

The pack presents contract fields and preserves structured decisions. It never
accepts a caller-supplied actor trust level or independently decides whether
the GitHub actor satisfies repository policy.

## Interaction

Adjudication groups duplicate proposals but keeps each finding identity
visible. Batch submission is bounded and all-or-nothing. High-risk findings
surface required CODEOWNER/second-maintainer policy before submission. If the
host lacks structured questions, interactive use asks one equivalent plain
question at a time; noninteractive ambiguous use stops.

List/status may display bounded summaries and GitHub references. Raw finding
bodies remain on their declared channels and private event details remain in
the authorized evidence store.
