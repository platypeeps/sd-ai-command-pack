---
title: Export the bookkeeping path prefixes as a consumable constant
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-27
---
# Export the bookkeeping path prefixes as a consumable constant

## Goal

Publish the bookkeeping path prefix pair — `.trellis/tasks/` and `.trellis/workspace/` —
as a named constant that both the pack's own validators and downstream consumers read,
instead of each site hardcoding the literals.

## Background

`validateBookkeepingFinalBundle` defines what a finalization delta may contain
(`plugins/sd/bin/sd-ai-command-pack-review-preflight.mjs:1453-1455`):

```js
(path) => !path.startsWith('.trellis/tasks/') && !path.startsWith('.trellis/workspace/')
```

That boundary is load-bearing for anyone integrating Trellis with a generated repository
map: a consumer must exclude exactly these two prefixes from its inventory, or a task
archive moves a path across the inventory boundary and no commit ordering satisfies both
the map's drift test and this validator.

There is no published constant to read, so consumers hand-copy the literals and then have
to hand-write a guard against drifting from them. In `answerbook/mezmo_benchmark` (PR #546)
that guard is `test_the_exclusion_matches_the_pack_bookkeeping_prefixes` — a test whose
entire reason for existing is that the pack does not export the pair. It asserts a
hardcoded tuple and cites the upstream line number in a docstring, which is the weakest
form of the check: a line-number citation goes stale silently.

The duplication is not only downstream. Inside the pack, `.trellis/tasks/` is compared with
`startsWith` at 13 sites and `.trellis/workspace/` at 5, so a future boundary change has to
be applied by hand at every one.

## Requirements

- A single exported constant (or accessor) holds the prefix pair, and every in-pack site
  that currently hardcodes a literal reads it instead.
- The constant is reachable by consumers without importing the validator's internals —
  decide the surface (a JSON manifest the pack already publishes, a documented export from
  a stable module, or a `--print-bookkeeping-prefixes` subcommand) and record the choice.
- The published surface is documented where an integrator would look: the finalization /
  bundle-scope documentation, not only inline in source.
- Behavior is unchanged. This is a de-duplication and publication task; widening or
  narrowing the boundary is explicitly out of scope and would be a separate task.

## Acceptance Criteria

- [ ] Zero remaining hardcoded `.trellis/tasks/` or `.trellis/workspace/` prefix literals
      in bundle-scope validation paths; a grep for the literals in those paths returns only
      the constant's own definition.
- [ ] A consumer can obtain the pair through the published surface without reading pack
      source, demonstrated by one worked example in the docs.
- [ ] The existing bookkeeping validator test suite passes unchanged, proving behavior did
      not move.

## Downstream effect

Once published, `answerbook/mezmo_benchmark` can rewrite its pin test to compare against the
real source rather than a hardcoded tuple plus a line-number citation. That is the intended
consumer-side outcome and is worth noting in the PR that lands this.

## Related

- Pack follow-up A: `.trellis/tasks/08-27-finish-work-regenerate-structural-map`
- Pack follow-up B: `.trellis/tasks/08-27-structural-map-check-final-bundle`
- Consumer PR: `answerbook/mezmo_benchmark` #546
