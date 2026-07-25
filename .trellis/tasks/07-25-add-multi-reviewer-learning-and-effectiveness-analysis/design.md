# Multi-Reviewer Learning And Effectiveness Design

## Boundary

```text
normalized reviewer + trusted adjudication evidence
                    |
             shared safe parser
                    |
          +---------+----------+
          v                    v
sd-review-learnings     sd-review-effectiveness
recurrence/guidance     paired quality/value report
```

The shared parser owns provenance, bounds, trust coverage, exact-head pairing,
configuration segmentation, and finding relationship normalization.

`sd-review-learnings` groups validated underlying issues into recurring
families and proposes preventive repository guidance. Invalid findings are
excluded from promotion; duplicates count once; unresolved current findings may
remain actionable but cannot be promoted as trusted lessons without sufficient
evidence.

`sd-review-effectiveness` compares same-plan exact-head reviewers, separately
reporting correctness, unique value, redundancy, reliability/resilience,
latency, and cost. It never edits learning or reviewer configuration.

## Delivery Decomposition

| Child | Responsibility |
| --- | --- |
| `07-25-generalize-review-learnings-across-reviewers` | Reviewer-neutral recurrence collection and disposition-aware guidance |
| `07-25-add-review-effectiveness-command` | Paired correctness, marginal value, resilience, latency, and cost reporting |

## Failure Boundary

Unknown schema, mixed heads/configurations, stale/truncated evidence, missing
cost, insufficient pairing, or inadequate trusted adjudication lowers coverage
and prevents confident recommendations. Missing numbers remain unavailable,
not zero.
