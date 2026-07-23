# Streamline backlog and design workflows

## Goal

Reduce the normal `sd-work-backlog` prompt by loading terminal reconciliation
and legacy recovery only when live state requires them. Retire the redundant
`sd-work-designs` public preset and expose its behavior through typed backlog
selectors, with no alias or redirect.

## Evidence

- `templates/.agents/skills/sd-work-backlog/SKILL.md:94-194` embeds terminal
  reconciliation, stopped/red recovery, and evidence mechanics before the core
  loop beginning near line 196.
- `templates/.agents/skills/sd-work-designs/SKILL.md:8-59` delegates to
  `sd-work-backlog` with a fixed selector and stop policy.
- The backlog state helper is already the authoritative loop ledger; prompt
  duplication adds context cost without adding state integrity.

## Dependencies

- Consume `07-22-add-portable-structured-questions` for unavoidable blocker or
  run-extension choices.
- Coordinate final command references with
  `07-22-integrate-routed-review-backends`, which rewires backlog review calls
  to `sd-review`.
- Coordinate retirement registration with
  `07-22-add-command-surface-drift-lint`.

## Requirements

- R1: Keep normal backlog invariants and the core loop in the canonical skill,
  but move rare terminal reconciliation, stopped/red recovery, and legacy
  ledger migration into conditionally loaded references or executable reports.
- R2: Load recovery material only when the authoritative helper reports the
  matching state or reason code. Do not rely on model inference from loose text.
- R3: Preserve run approval, iteration limits, no-touch ownership, task
  lifecycle, exact-head review/merge gates, stop-work-loop behavior, and
  resumability.
- R4: Add typed selector behavior equivalent to the current preset, including
  `selector=needs-design` and an explicit stop boundary such as
  `until=design|merge`.
- R5: Remove `sd-work-designs` from canonical skills, all generated adapters,
  manifest/help/catalog/docs, and live examples. Add no alias, forwarding skill,
  or compatibility parser.
- R6: Register all old pack-owned paths for provenance-safe retirement;
  preserve/report locally modified installed copies according to installer
  policy.
- R7: Use structured questions only for an unavoidable blocker, intentional
  parking choice, or explicit extension of a bounded long run. Do not ask at
  each iteration or before already-authorized lifecycle actions.
- R8: Keep recovery evidence in typed helper output and reports rather than
  reconstructing it from conversation history.

## Acceptance Criteria

- [ ] A normal healthy run does not load terminal recovery or legacy migration
  prose and preserves the existing selection/lifecycle behavior.
- [ ] Stopped, red, missing-ledger, stale-owner, and reconciliation fixtures
  load the correct bounded recovery reference and reject the wrong one.
- [ ] `sd-work-backlog selector=needs-design until=design` reproduces the
  intended design-first outcome without a separate public skill.
- [ ] No live `sd-work-designs` skill, adapter, manifest target, help entry,
  config key, alias, or redirect remains after clean install/refresh.
- [ ] Run approval and bounded iteration tests prove no new per-iteration
  prompting or authority expansion.
- [ ] Existing loop state, resume, stop, task lifecycle, and no-touch tests pass.
- [ ] `make sync`, focused generated parity, retirement tests, and `make check`
  pass.

## Out Of Scope

- Combining `sd-start`, `sd-continue`, or `sd-finish-work`.
- Changing backlog prioritization unrelated to design selection.
- Replacing the authoritative backlog state helper.
