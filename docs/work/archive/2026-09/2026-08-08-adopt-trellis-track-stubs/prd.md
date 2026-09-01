---
title: Adopt the five track-* stubs relocated from the Trellis fork
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-08
---
# Adopt the five track-* stubs relocated from the Trellis fork

## Problem

The 2026-08-08 cross-repo backlog review removed five 07-27-track-* stub
tasks from the Trellis fork (~/repos/ai/Trellis, commit b9b73e27) because
each carried a Notes line reading "Likely owner: sd-ai-command-pack" — they
tracked pack surfaces (review-learnings diagnostics, completion receipts,
journal evidence, generated repo-map drift, gemini settings review scope)
while inflating the fork backlog by 20%. Their original PRDs are preserved
verbatim in this task's `research/` directory.

## Requirements

1. Triage each stub into exactly one of: an existing pack task (append an
   Absorbed/note section there), a new pack task, or a recorded won't-fix
   with rationale.
2. The relocation loses nothing: every stub's requirements are either
   represented in an active pack task or explicitly declined in this task's
   record.

## Register

- 07-27-track-gemini-settings-review-scope
- 07-27-track-journal-evidence-contradictions
- 07-27-track-no-active-task-completion-receipts
- 07-27-track-review-learnings-unsafe-path-diagnostic
- 07-27-track-archive-repo-map-drift

## Acceptance criteria

- [ ] Each of the five has a recorded disposition citing its research/ file.
- [ ] Any absorbed content lands as a section in the target task's prd.md.
- [ ] This task closes only when all five are dispositioned.

## Evidence

Trellis fork commit b9b73e27 (removal); sd-ai-command-pack
08-08-backlog-consolidation (PR #382) Notes section, sibling effort (b).

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/08-08-adopt-trellis-track-stubs`:

- research/07-27-track-archive-repo-map-drift.md
- research/07-27-track-gemini-settings-review-scope.md
- research/07-27-track-journal-evidence-contradictions.md
- research/07-27-track-no-active-task-completion-receipts.md
- research/07-27-track-review-learnings-unsafe-path-diagnostic.md
