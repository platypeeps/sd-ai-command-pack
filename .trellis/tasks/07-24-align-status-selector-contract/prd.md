# Align status and housekeeping selector contracts

## Goal

Resolve review finding `1.1.1` by removing the obsolete `R-*` selector and
Roadmap-section contract from every live status and housekeeping surface while
preserving untracked roadmap-file items as `F-*` follow-ups.

## Confirmed Evidence

- `templates/.agents/skills/sd-status/SKILL.md:68-81` defines only `F-*` and
  `T-*`, but lines 134-138 still accept an `F/T/R` identifier.
- `templates/.agents/skills/sd-housekeeping/SKILL.md:75-77` still describes the
  delegated result as containing `F/T/R` selectors.
- `07-23-status-untracked-roadmap-items` intentionally removed the separate
  Roadmap section and routed unmatched roadmap-file tasks into Follow-ups.

## Dependencies And Boundaries

- Parent: `07-24-correct-sd-skill-contract-drift`.
- Preserve the current status JSON schema, complete Trellis task inventory,
  read-only behavior, roadmap-source discovery, and deterministic `F-*`/`T-*`
  ordering.
- Do not reintroduce a third category for compatibility.

## Requirements

- R1: Remove `F/T/R`, `R-*`, and separate Roadmap-section claims from every live
  skill, command, prompt, guide, generated adapter, test expectation, and active
  program task that describes current behavior.
- R2: Keep `F-*` for evidence-backed follow-ups, including unmatched task-like
  roadmap-file items, and `T-*` for every valid unarchived Trellis task.
- R3: Treat an incoming `R-*` selection as unsupported current input rather than
  silently translating it, restoring a hidden alias, or guessing a task.
- R4: Update status-to-housekeeping typed handoff documentation so both commands
  describe the same selector and empty-section behavior.
- R5: Add a source-drift test that fails when current surfaces mention the
  retired selector contract outside explicitly archived historical records.
- R6: Synchronize templates, root mirrors, generated adapters, docs, release
  metadata, and candidate evidence through the normal pack workflow.

## Acceptance Criteria

- [ ] Local status human and JSON output expose only Follow-ups (`F-*`) and Tasks
  (`T-*`); no Roadmap collection or `R-*` selector exists.
- [ ] Housekeeping relays the same F/T inventory without describing or accepting
  a removed category.
- [ ] Untracked roadmap-file tasks still appear as deduplicated `F-*` follow-ups
  with path/line evidence.
- [ ] A later `R-1` request returns a precise unsupported/stale-snapshot result
  and performs no mutation.
- [ ] Live-surface drift validation finds no obsolete F/T/R wording; archived
  task history may retain historical evidence.
- [ ] Focused status/housekeeping tests, template/root parity, `make sync`, and
  `make check` pass.

## Out Of Scope

- Adding fuzzy roadmap-to-task matching.
- Creating tasks during status.
- Preserving `R-*` through an alias, redirect, compatibility reader, or hidden
  machine-only field.

## Notes

- Historical archived Trellis artifacts are evidence, not live command surface.
