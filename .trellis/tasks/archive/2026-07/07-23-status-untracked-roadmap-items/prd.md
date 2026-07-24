# Route untracked roadmap items into sd-status follow-ups

## Goal

Stop `sd-status` from repeating Trellis tasks in both `Tasks` and `Roadmap`.
Remove the separate `Roadmap` section and report task-like items found in
roadmap files as `F-*` follow-ups only when no unarchived Trellis task already
represents them.

## Background

- `Tasks` already enumerates every valid unarchived Trellis task.
- `Roadmap` currently selects open top-level tasks from that same inventory, so
  every `R-*` row duplicates a `T-*` row.
- Prior program-design and implementation-plan backlogs were intentionally
  converted into Trellis tasks, and separate roadmap files were removed.
- The repository currently has no matching untracked roadmap item, but future
  roadmap/planning files in the repository are an additional follow-up source.

## Requirements

- R1: Remove the `Roadmap` section from human output and its separate roadmap
  inventory from JSON. Trellis tasks appear only under `Tasks`.
- R2: Add untracked roadmap-file items to the existing `Follow-ups` inventory
  with deterministic `F-*` selectors and a distinct roadmap kind/source.
- R3: Preserve complete `Tasks`, evidence-backed `Follow-ups`, report-local
  identifiers, read-only behavior, local/fleet modes, and all existing Git,
  GitHub, Trellis, and work-loop facts.
- R4: Update the source template first, synchronize dogfood mirrors, and keep
  skill text, installed guide, tests, release metadata, and candidate evidence
  aligned with the shipped behavior.
- R5: Discover roadmap candidates from repository files that contain task
  items, then exclude candidates already represented by an unarchived Trellis
  task before assigning `F-*` selectors with the other follow-ups.
- R6: Bound discovery to regular, non-symlinked Markdown/text files with
  roadmap-like names (`ROADMAP`, `BACKLOG`, `TODO`, `PROGRAM_DESIGN`, or
  `IMPLEMENTATION_PLAN`, with case/separator variants) or files below
  `roadmap/`, `proposals/`, or `rfcs/` directories. Do not scan arbitrary
  repository prose.
- R7: Recognize unchecked Markdown task boxes and unmarked Markdown list items
  as roadmap candidates. Unmarked list items count only at the top level;
  explicit unchecked task boxes count at any indentation. Ignore
  checked/completed task boxes and nested unmarked explanatory bullets.
- R8: Treat a candidate as already tracked when it references an unarchived
  Trellis task's durable ID/task path or its normalized item text exactly
  matches the normalized task title. Normalize case, whitespace, Markdown
  presentation, and the display-only `PARKED:` prefix, but do not use fuzzy or
  semantic matching.
- R9: Advance the status report schema version when removing the roadmap JSON
  field so machine consumers can reject the incompatible shape explicitly.

## Acceptance Criteria

- [x] A repository containing only Trellis tasks prints all tasks under
      `Tasks`, produces no task-backed roadmap follow-up, and has no `Roadmap`
      section.
- [x] No durable Trellis task is duplicated as an `F-*` follow-up.
- [x] Human and JSON output contain no separate roadmap inventory.
- [x] Repository-file roadmap candidates receive deterministic `F-*` IDs only
      when no unarchived Trellis task represents them.
- [x] Checked items, nested explanatory bullets, task-ID/path references, and
      exact normalized title matches are excluded; unmatched top-level bullets
      and unchecked boxes remain visible with source evidence.
- [x] Existing follow-up, task, next-step, fleet, and read-only behavior remains
      covered and green.
- [x] Template/root parity, release gates, candidate validation, and
      `make check` pass.

## Out of Scope

- Fuzzy or AI-based matching between roadmap prose and tasks.
- Scanning arbitrary repository prose, generated/ignored content, or remote
  planning systems.
- Creating Trellis tasks from status output or mutating roadmap source files.
