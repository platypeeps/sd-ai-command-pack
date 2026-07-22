# Add sd-github-review to fleet

## Goal

Add `platypeeps/sd-github-review` as a first-class `sd-ai-command-pack`
fleet consumer so release candidates are validated against it and operators can
include it in normal status, rollout, review, and timing workflows.

## Background

- The fleet source of truth is `docs/fleet/consumers.json`, currently schema
  version 4 with seven consumers in explicit cohort and priority order.
- `platypeeps/sd-github-review` is a public repository on `main`; its local
  checkout is at `~/repos/platypeeps/sd-github-review`.
- The repository already contains an installed pack receipt and uses the same
  `claude`, `gemini`, `github`, and `opencode` platform surfaces as the existing
  fleet.
- Its CI contract runs `npm ci`, `npm test`, `npm run check`, and
  `npm run validate:metadata` on Node 24. The tests and metadata validator need
  the declared `yaml` development dependency, so disposable candidate clones
  need an explicit dependency-install preparation step.
- The repository has no consumer-local `update_repomix` generator or tracked repomix
  map, so it must not inherit the map preparation used by six existing
  consumers.

## Requirements

- Add one canonical consumer entry for `sd-github-review` with GitHub slug
  `platypeeps/sd-github-review`, path hint
  `~/repos/platypeeps/sd-github-review`, the four supported platform names, a
  bounded timeout, and a unique rollout priority.
- Put the consumer in exactly one rollout cohort and keep cohort order identical
  to rollout-priority order, as required by the schema-v4 fleet contract.
  `sd-github-review` belongs at priority 70 as the last member of the
  bounded-parallel `post-canary` cohort, after `se-ai-command-pack`; AMC remains
  the only member of the sequential `final` cohort at priority 90.
- In disposable candidate clones, prepare with `npm ci`, then run the
  repository-owned read-only gates: `npm test`, `npm run check`, and
  `npm run validate:metadata`.
- Update checked-in inventory/order assertions and operator documentation so
  the manifest, tests, README, and fleet runbook describe the same eight-member
  fleet and preparation model.
- Regenerate the full candidate-validation ledger only after all eight
  disposable consumer clones pass. A partial diagnostic must not replace the
  canonical ledger.
- Preserve existing consumer identities, relative order, commands, and cohort
  behavior except for the insertion required by this task.

## Acceptance Criteria

- [ ] Fleet loading returns `platypeeps/sd-github-review` exactly once with the
  expected path, platforms, 180-second timeout, `npm ci` preparation, npm
  checks, priority 70, and post-canary cohort membership.
- [ ] The ordered fleet and rollout-policy tests include all eight consumers and
  retain AMC as a sequential final cohort.
- [ ] Documentation names the updated rollout order and accurately distinguishes
  repomix preparation, npm dependency preparation, and no-preparation consumers.
- [ ] A focused candidate run for `sd-github-review` passes in a disposable
  origin clone without mutating the active local checkout.
- [ ] The complete eight-consumer candidate run passes and writes a ledger whose
  fleet digest, consumer rows, base commits, preparation arrays, and check arrays
  match the updated manifest.
- [ ] Relevant fleet unit tests and the repository full check pass.

## Out of Scope

- Changing `sd-github-review` product code, CI, or pack installation.
- Refreshing or opening a PR in any consumer repository.
- Reordering or redesigning existing canary consumers.

## Notes

- Evidence anchors: `docs/fleet/consumers.json`,
  `tests/test_fleet_preflight.py:119`, `docs/FLEET_ROLLOUT.md:3`, and the target
  repository's package and CI workflow definitions.
- Baseline evidence: the target checkout's 30 tests, syntax checks, and action
  metadata validation all passed before planning.
