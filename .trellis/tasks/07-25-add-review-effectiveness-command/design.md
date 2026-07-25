# Review Effectiveness Command Design

The command reads one bounded normalized evidence set and computes deterministic
grouped metrics. Direct quality comparisons require same-plan exact-head pairs.
Unpaired operational history is reported separately.

Every rate includes numerator/denominator and evidence strength. Advisory
dispositions include `insufficient-evidence`, `retain-for-unique-value`,
`retain-for-resilience`, `mostly-redundant`, `cost-ineffective`, and
`correctness-concern`, each with coverage, configuration/time range,
limitations, and revisit conditions.

Reports never mutate reviewer sets. Paste-ready configuration examples may be
offered only after evidence thresholds pass and remain human-applied.
