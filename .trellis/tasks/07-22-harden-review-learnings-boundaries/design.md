# Design: bounded review-learnings updates

## Modes

- `scan`: default, read-only analysis and proposed diff/report.
- `update`: repository-contained write after validation.
- `update-external`: exceptional path requiring explicit option and structured
  confirmation of the resolved absolute target.

The script remains noninteractive. The skill obtains any required confirmation
and passes a bounded authorization token/flag for the exact resolved target.

## Path Validation

Resolve repository root and target with symlink-aware canonicalization. A local
target is accepted only when the resolved path is contained by the resolved
repository root. Parent creation is permitted only after containment and target
type validation succeeds.

The authorization binds the resolved path, mode, and invocation; it cannot be
reused for a different target produced by a symlink race. Re-resolve immediately
before atomic replacement.

## Mutation

Produce the full candidate content in memory, preserve newline/encoding policy,
write a sibling temporary file, fsync where supported, and replace atomically.
On any validation or replacement error, report failure without staging or Git
mutation.

## Reporting

Structured output contains mode, containment, resolved target, before/after
digests, finding and change counts, write status, and diagnostic reason codes.
Human output derives from the structured result.

## Rollback

Repository-local updates remain ordinary reviewable working-tree changes.
External writes have no automatic rollback; this is why they require exact-path
confirmation and atomic replacement.
