# Design: progressive backlog recovery and typed design selection

## Core And Conditional Content

The canonical skill retains:

- invocation and run authority;
- normal selection and lifecycle invariants;
- helper invocation and typed outcome handling;
- bounded iteration/stop behavior; and
- final reporting.

Conditional references own:

- terminal/merged reconciliation;
- stopped/red run recovery;
- missing or legacy ledger migration; and
- exceptional ownership recovery.

The helper emits a stable reason code that selects at most the needed reference.

## Public Interface

`sd-work-backlog` owns typed selectors and stop boundaries. The design-oriented
preset becomes a normal invocation, for example:

`sd-work-backlog selector=needs-design until=design`

Natural-language adapters map to the same contract. No `sd-work-designs`
adapter remains.

## Interaction

Normal operation is non-prompting once the run is approved. Structured
questions are reserved for mutually exclusive blocker dispositions or a
bounded run extension. Noninteractive execution parks safely at those points.

## Retirement

The live registry removes the old command. The installer retirement registry
owns deletion of unchanged installed targets and reporting of drifted copies.
Historical changelog/migration fixtures may retain the identifier through an
explicit lint allowlist.

## Rollback

Rollback reinstalls the prior pack version. The new version does not keep a
hidden alias.
