# Design: resumable fleet refresh controller

## State Model

Campaign state is an append-only event stream or equivalently auditable atomic
state plus receipts. Each lane transitions through a fixed enum. Transitions
carry preconditions and an idempotency key derived from campaign, release,
consumer, stage, and attempt.

The controller never performs arbitrary shell actions from state. It returns a
bounded next action and expected evidence; the owning skill/script performs the
action and records a normalized result.

## Operations

- `plan`: validate manifest/release and produce waves.
- `next`: return currently eligible bounded actions.
- `record`: validate and atomically record one normalized result.
- `status`: report campaign and lane state without mutation.
- `resume`: reconcile persisted state with read-only repository/PR evidence.
- `validate`: reject schema, identity, transition, and receipt inconsistencies.

## Failure And Ownership

Ownership skips are terminal for the current campaign but resumable through a
new explicit attempt after ownership clears. Infrastructure failures follow a
bounded retry policy. Product/check/review failures park the lane for scoped
remediation. Ambiguous post-side-effect state enters reconciliation and never
repeats the side effect blindly.

## Skill Boundary

The skill:

- explains the campaign and material exceptions;
- requests operator judgment only for genuine policy/blocker choices;
- invokes owning lifecycle skills for scoped work; and
- reports controller receipts.

The controller owns order, concurrency, identity, retries, and completion.

## Rollback

The state schema is versioned and old campaign state is never silently
upgraded. Rollback to an earlier pack uses a new campaign or an explicit
compatible reader; it does not reinterpret newer state.
