# Design: shipped-surface closure validator

## Design Summary

Implement one read-only graph validator consumed by `sd-check`, local
pre-publication, and CI. Authoritative registry and manifest records become
nodes and declared relations; changed paths select the affected subgraph, and
the validator proves all required nodes and edges are present and consistent.

## Graph Model

Node kinds include:

- canonical template source and source-only reference;
- manifest install entry and generated target;
- platform adapter/root mirror;
- command/help/documentation identifier;
- local and CI check registration;
- provenance/retirement record;
- release metadata and candidate evidence.

Edges express `installs-as`, `generates`, `mirrors`, `documents`, `checks`,
`retires`, and `requires-release-evidence`. Node IDs are repository-relative
and validated from existing canonical data. The helper does not infer a new
install entry merely because a file is under `templates/`.

## Evaluation Flow

1. Load and validate registry, manifest, generator metadata, and checker scope.
2. Collect the committed plus intended working diff through bounded NUL-safe
   Git output, including non-ignored untracked paths.
3. Map changed paths/identifiers to nodes and compute transitive closure.
4. Validate existence, uniqueness, type, containment, required relations,
   release evidence, and local/CI scope equality.
5. Emit one versioned JSON report with stable findings and owner commands.

The same helper/configuration runs locally and in CI. Callers may select report
format, but not redefine node kinds, path globs, or required edges.

## Failure And Mutation Boundaries

Unknown schema, unsafe path, symlink, oversized input, invalid UTF-8,
unreadable authoritative data, or incomplete graph produces a controlled
failure. Stale but fixable generated state names its existing preparation
command. The validator never generates, synchronizes, refreshes, or stages.

## Compatibility And Rollback

The helper initially runs alongside existing focused parity tests, which remain
until the graph covers their behavioral contracts. Rollback removes the new
caller integration but keeps registry/manifest source data; it does not weaken
the existing release or parity gates.
