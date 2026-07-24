# Mark future-triggered tasks as PARKED

## Goal

Make current Trellis work that cannot advance until a named future event
immediately recognizable in status and backlog output.

The repository currently has seven such tasks. Their titles should begin with
the exact `PARKED: ` prefix, while ordinarily sequenced parent/child work
remains unprefixed.

## Requirements

- R1: Prefix the `task.json` title and matching `prd.md` H1 for these current
  externally trigger-gated tasks:
  - `actionlint-workflow-linting`;
  - `trellis-version-compatibility`;
  - `upstream-issue-closure-cleanup`;
  - `upstream-platform-state`;
  - `upstream-trellis-api-cleanup`;
  - `upstream-trellis-opencode-context-exec-hardening`; and
  - `upstream-trellis-hook-shell-semantics`.
- R2: Limit changes to each task's `task.json` title and matching `prd.md` H1.
  Preserve task IDs, directory names, descriptions, status, priority, and
  task-tree topology.
- R3: Do not change command-pack templates, installed mirrors, status or
  backlog behavior, tests, documentation, release metadata, or upstream
  Trellis.

## Acceptance Criteria

- [x] All seven current task records and PRD headings use the exact `PARKED: `
      prefix; no internally sequenced program parent or validation task is
      mislabeled.
- [x] No file outside the seven current task directories and this task's
      lifecycle bookkeeping is changed.

## Out of Scope

- Establishing or documenting a command-pack naming convention.
- Changing status or backlog selection behavior.
- Adding a `parked` value to Trellis task status or extending `task.json`.
- Renaming task directories, durable task IDs, or parent/child links.
