# Design: planning task topology semantics

## Boundary

Extend the task-oriented section of the existing review preflight rather than
adding another executable or changing Trellis lifecycle commands. The template
script remains the source of truth and the root script remains a synchronized
dogfood mirror.

The new check is semantic and diff-scoped. It complements, but does not absorb,
the existing task metadata integrity check:

1. structural validation continues to own record shape, lifecycle coherence,
   branch inequality, layouts, and reciprocal links;
2. the semantic check owns parent-relative bases for newly changed deferred
   planning children and PRD coverage for changed active parents; and
3. completed-root and task-context checks retain their current boundaries.

## Changed-task discovery

Build deterministic active-task directory sets from `currentChangedPaths()`:

- changed `task.json` paths drive planning-base validation;
- changed `task.json` and `prd.md` paths jointly drive parent PRD validation;
- deleted task records are ignored as old sides of moves;
- a deleted PRD remains represented by its path so a still-present parent with
  declared children fails the safe read; and
- archive paths and unsupported nesting are excluded from this semantic check
  and remain subject to existing layout checks where applicable.

This union is necessary to catch prose-only drift without scanning every task
on unrelated changes.

## Parent-relative planning bases

For a changed active task record, first rely on the structural validator. When
the record is a deferred planning child (`status` is `planning`, `branch` is
`null`, and `parent` is present), load the parent's safe parsed record through
the existing task lookup.

The allowed base set is:

```text
parent.base_branch
parent.branch, when non-empty
```

The first value keeps a newly planned child on the parent's durable integration
target. The second explicitly preserves a stack on work that the parent still
owns. Any other value is ungrounded in the recorded topology and fails.

If parent lookup or reciprocal metadata is already invalid, suppress a second
semantic error and let the existing structural check provide the authoritative
diagnostic. Standalone tasks and tasks with an assigned branch are not
classified because their stacking intent cannot be inferred deterministically
from the current schema.

## Parent PRD representation

For every in-scope active task directory, safely load its task record. If the
record has declared children, read `prd.md` with the same bounded,
no-symlink filesystem posture used by task metadata reads.

Match each declared identifier as an exact token, using task-identifier
characters as the boundary alphabet. For example,
`07-22-child-extension` must not satisfy `07-22-child`. The matcher does not
care whether the token is in backticks, a table, a list, a Markdown link, or a
dependency section.

Sort and deduplicate missing identifiers before emitting one bounded diagnostic
for the parent. Do not parse undeclared task IDs from the PRD: free-form prose
can legitimately mention dependencies, predecessors, archived work, and
examples that are not children.

## Failure posture

- Changed semantic inputs fail closed when their type or filesystem safety
  cannot be established.
- Diagnostics name the actionable `task.json` or `prd.md`, the observed
  relationship, and the accepted correction.
- Output order follows normalized task paths, then sorted child identifiers.
- Existing global result and diagnostic caps remain authoritative.

## Compatibility and release

The feature does not change command names or arguments, but it adds a new
consumer-visible rejection rule. Under `CONTRIBUTING.md`, that is changed
command semantics and therefore requires the next minor version (`0.31.0` from
`0.30.8`), a matching top changelog entry, synchronized generated payload, and
fresh full-fleet candidate evidence.

No Trellis-owned runtime is changed. If implementation exposes a desirable
`task.py create` improvement, record a separate handoff; do not open an
upstream Trellis PR from this task.

## Verification strategy

Use real Git fixture repositories for changed-path behavior and small exported
helper tests for exact-token and parent-relative decisions. Cover rejection,
intentional-stack acceptance, prose-only drift, unsafe PRDs, unchanged-history
grandfathering, deterministic diagnostics, and root/template byte identity.
