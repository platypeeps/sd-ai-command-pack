# Design — <slug>

Written only when requested. Explain the choices the PRD leaves open.

## Approach

<The shape of the solution, and the alternative you rejected with the reason.
A design with no rejected alternative usually means the choice was not examined.>

## Decisions

<Each one: what was decided, by whom, on what date, and what would reverse it.
A decision that outlives this item belongs in a decision record instead, which
`sd-plan --decision` writes under `docs/decisions/`. Most repositories have no
such directory and are not expected to grow one — `sd-docs-lint` rule 3 skips
it when it is absent. Without that directory, the decision stays here rather
than being filed into a path nothing in the repository reads.>

## Risks

<What could make this wrong. Name the ones you are accepting, not only the ones
you are mitigating.>
