# Backfill archived task metadata descriptions

## Goal

Backfill blank archived Trellis task metadata descriptions and add a lightweight guard against future blank completed-task descriptions.

## Problem

The architectural review found three archived tasks whose PRDs are substantive but whose `task.json` descriptions are blank:

- `.trellis/tasks/archive/2026-07/07-04-recorder-add-output/task.json`
- `.trellis/tasks/archive/2026-07/07-04-recorder-empty-subject/task.json`
- `.trellis/tasks/archive/2026-07/07-04-recorder-hardening/task.json`

The tasks themselves are accurate, but blank descriptions reduce searchability and make later task audits less useful.

## Requirements

- Backfill concise descriptions for archived task metadata where the PRD already contains enough context.
- Preserve existing task status, archive location, timestamps, assignee, priority, and PRD content unless a clear metadata error is found.
- Add a lightweight guard so future completed or archived tasks with blank descriptions are easy to spot.
- Keep the guard low-noise. It can live in a local review/preflight check, a Trellis task hygiene helper, or documentation if automation is not worth the complexity.
- Do not reopen or alter the completed task outcomes.

## Acceptance Criteria

- [x] The three known archived tasks have non-empty descriptions that match their PRDs.
- [x] No archived task status or completion data is accidentally changed.
- [x] A future blank description is detected by the selected guard or documented in a checklist used by repo maintainers.
- [x] Task listing and archive listing still work.
- [x] `python3 ./.trellis/scripts/task.py list-archive` succeeds.
- [x] `python3 -m unittest discover -s tests` passes if code or tests are changed.
- [x] `git diff --check` passes.

## Implementation Notes

- Use each PRD's goal and implementation summary to write one-sentence descriptions.
- If the guard is automated, keep it scoped to repo-owned Trellis tasks and avoid failing on unrelated Trellis runtime artifacts.

## Notes

- This is a hygiene task. It is intentionally small and can be handled independently of the larger architecture work.
- Upstream: a drafted Trellis issue in `07-07-file-upstream-trellis-issues`
  (issue 4) asks `task.py` itself to warn on blank descriptions at
  create/archive time. If Trellis adopts it, the "lightweight guard"
  requirement here can be satisfied by the upstream warning; the
  backfill of the three known blank descriptions is needed either way.
