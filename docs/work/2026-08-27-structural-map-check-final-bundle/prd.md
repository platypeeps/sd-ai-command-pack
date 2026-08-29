---
title: Run checkGeneratedStructuralMapPaths on the final-bundle path
status: planning
created: 2026-08-27
---
# Run checkGeneratedStructuralMapPaths on the final-bundle path

## Goal

`checkGeneratedStructuralMapPaths` is the correct check running at the wrong time. Run it
as part of the post-archive `final-bundle` path so generated-map drift is caught at the
moment it is created, rather than on a later PR.

## Background

`plugins/sd/bin/sd-ai-command-pack-review-preflight.mjs` dispatches at `:625-657`. The
`pre-archive`, `final-bundle`, and `seeded-task` subcommands take the
`runBookkeepingValidator` branch at `:632` and return before ever reaching
`runReviewPreflight()` at `:651`:

```js
if (['pre-archive', 'final-bundle', 'seeded-task'].includes(process.argv[2])) {
  ...
  process.exit(result.status === 'valid' ? 0 : 1);
} else if (process.argv.length > 2) {
  ...
} else {
  const result = runReviewPreflight();
```

So `checkGeneratedStructuralMapPaths` — which lives under `runReviewPreflight` — never
runs during finalization, which is precisely when an archive makes the consumer's
generated map stale. The drift is created in a commit the check cannot see, and surfaces
later as an unrelated-looking CI failure on the next PR.

## Evidence

Three observed instances in `answerbook/mezmo_benchmark`: PR #483, PR #511, PR #544. In
each, the stale map was created by a finalization commit and discovered afterwards.

## Requirements

- The generated-structural-map check runs on the `final-bundle` path, post-archive.
- It reports drift at the point of creation with a reason code distinct from
  `bundle_scope_invalid`, so the two failure modes are not conflated in the operator's output.
- Consumers with no generated structural map are unaffected: absent generator config is a
  skip, not a failure.
- Decide explicitly whether `pre-archive` and `seeded-task` should also run it, and record
  the reasoning either way. `pre-archive` runs before the file set moves, so it likely
  should not.

## Acceptance Criteria

- [ ] A finalization run that would leave the consumer's generated map stale fails at
      `final-bundle` with a dedicated reason code naming the map path.
- [ ] A finalization run in a consumer with no generated map reports no new finding.
- [ ] The check's inclusion or exclusion on `pre-archive` and `seeded-task` is documented
      with its rationale.

## Interaction with follow-up A

A (regenerate in `sd-finish-work`) and B (detect on `final-bundle`) are complementary, not
alternatives: A removes the drift, B catches it if A is unconfigured, fails, or the
consumer regenerates by hand. If A lands first, B becomes the backstop that proves A ran.

## Related

- Pack follow-up A: `.trellis/tasks/08-27-finish-work-regenerate-structural-map`
- Pack follow-up C: `.trellis/tasks/08-27-export-bookkeeping-prefixes`
- Consumer task, in the answerbook/mezmo_benchmark repository and not a path here: task 08-06-finalization-repomix-ordering
