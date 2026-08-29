---
title: Machine-visible blocked markers and backlog ordering
status: done
created: 2026-07-25
branch: codex/stabilize-self-hosted-delivery-lifecycle
---
# Machine-visible blocked markers and backlog ordering

## Goal

The sd-work-backlog selector (and any session reading the board) can distinguish
externally-blocked tasks from ready ones, and cross-program ordering is visible on the
board instead of living only in PRD prose.

## Origin

Opportunity from the 2026-07-25 cross-plan review: the 7 routed-review/learnings tasks are
planning-complete but hard-blocked on sd-github-review contract stability, yet they look
identical to ready tasks in `task.py list`; the audit backlog and agent-artifacts program
likewise carry ordering constraints only as PRD text.

## Requirements

- R1: Define a machine-visible convention for "blocked on external dependency" — e.g. a
  `task.json` field (blockedOn: <repo>/<task or contract>), a status value, or a
  documented title/priority convention. Prefer extending task.json via the Trellis
  scripts' existing schema handling.
- R2: `task.py list` renders the marker; the sd-work-backlog selector skips blocked tasks
  and says why.
- R3: A lightweight ordering signal (e.g. `after: <task>` or a numeric order field) that
  the selector respects within a priority band; PRD prose remains the source of nuance.
- R4: Apply the convention to the currently-blocked routed-review/learnings tasks (7) and
  the agent-artifacts children with hard dependencies, as the first consumers.
- R5: Trellis is vendored: implement in whatever layer this repo owns (pack skills/scripts
  or documented convention) without forking Trellis internals it does not own; if a
  Trellis-core change is needed, record that as an upstream ask instead.

## Acceptance Criteria

- [x] Blocked tasks are visibly distinct in `task.py list` output (or the selector's view).
- [x] sd-work-backlog demonstrably skips a blocked task and reports the reason.
- [x] The 7 review-ops tasks and dependent agent-artifacts children carry the markers.

## Reconciliation with the existing PARKED convention (2026-07-25)

- This repo ALREADY has a parking convention: `# PARKED:` title prefixes with explicit
  triggers (exemplars: the seven 07-09/07-16 tasks), and sd-work-backlog SKILL prose that
  summarizes "parked, skipped, failed, and blocked" selections. R1-R3 must FORMALIZE and
  machine-encode that convention (title-prefix detection and/or task.json field), not
  invent a parallel one. The seven routed-review/learnings tasks now carry the PARKED
  prefix + a blocked note as the first consumers; migrate them to the final encoding.
