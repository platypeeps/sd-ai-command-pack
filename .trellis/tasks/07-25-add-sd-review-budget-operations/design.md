# sd-review Budget Operations Design

## Boundary

The command pack discovers and invokes bounded router operations. The private
control plane computes balances, reservations, exhaustion, forecasts, and
recovery eligibility. The pack validates and presents the response without
recomputing those decisions.

## Read Model

Every report carries contract identity, compiled configuration/catalog digest,
observation time, freshness classification, and known/unknown coverage. Shared
pools are identified explicitly so aggregation does not count one balance as
independent capacity for multiple lanes or candidates.

Reports preserve `reviewOutcome`, `assuranceOutcome`, and `gateOutcome` plus
the gate reason and explicit lane merge policy. A passing gate is never used as
evidence that deferred assurance completed.

| Operation | Primary question | Mutation |
| --- | --- | --- |
| `status` | Where does budget stand by overall/repo/lane/chain/candidate/provider/model/pool? | None |
| `pending` | Which deferred exact heads still need review and when can they recover? | None |
| `explain` | Why would each slot select, skip, fail, or defer now? | None |
| `retry` | Can the trusted workflow create the next bounded attempt for this exact head? | Explicit workflow dispatch |

## Recovery Flow

`retry` first reads current pending state, validates repository/PR/head and
compiled digest, displays the declared action, and obtains explicit operator
authorization. It invokes only the setup descriptor's trusted workflow with a
stable logical attempt identity and normalized fingerprint. The response must
link the prior deferred record, new attempt, workflow run, and eventual
receipt. Changed heads, conflicting fingerprints, ambiguous dispatch, or
missing receipt identity stop for reconciliation.

The retry is a distinct linked attempt. The router, not the pack, owns
immutable receipts and revisioned exact-head assurance/gate projections; the
pack displays the prior/new attempt link and resulting projection identity.

## Output Safety

Output contains safe aliases and aggregate state only. It never includes
credentials, secret values, prompts, source, raw findings, private ledger rows,
or commands supplied by an untrusted response.
