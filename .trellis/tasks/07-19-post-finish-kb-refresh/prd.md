# Refresh generated KB after post-review Trellis lifecycle mutations

## Goal

Keep repositories that already maintain `.obsidian-kb` fresh through the end of
the SD shipping and autonomous-backlog lifecycle. Task archival and newly
recorded follow-up tasks must not leave a clean checkout unable to pass the
pack's canonical full-check.

## Confirmed Facts

- `sd-update-spec` and `sd-ai-command-pack-update-spec-kb.py` own generated KB
  content.
- KB discovery includes Markdown from active and archived Trellis tasks.
- `sd-ship` refreshes specifications before review, then archives the Trellis
  task during its later housekeeping stage.
- `sd-work-backlog` can record follow-up tasks after the nested shipping flow.
- Full-check treats an existing stale `.obsidian-kb` as a failure, while its
  default mode does not require repositories without that directory to create
  one.
- Audit A-035 reproduced the issue on clean `main`: all earlier `make check`
  lanes passed before KB freshness failed.

## Requirements

- Give post-review Trellis lifecycle mutations one final, explicit KB refresh
  owner.
- Refresh after task archival and after any follow-up task creation that occurs
  before a workflow reports a clean completion boundary.
- Preserve the current opt-in-by-presence model: do not create `.obsidian-kb`
  in a repository where it is absent.
- Reuse the canonical KB helper instead of duplicating copy or dashboard logic
  in lifecycle skills.
- Surface refresh failures as actionable workflow failures; do not silently
  report a clean completion with stale generated knowledge.
- Keep template sources and root installed mirrors synchronized.
- Cover standalone shipping and autonomous-backlog lifecycle paths without
  introducing duplicate unconditional refreshes.

## Acceptance Criteria

- [ ] In a repository with an existing `.obsidian-kb`, `sd-ship until=merge`
      ends with `sd-ai-command-pack-update-spec-kb.py --check` passing after the
      Trellis task is archived.
- [ ] Follow-up Trellis tasks created by `sd-work-backlog` are reflected in the
      KB before that iteration reports a clean completion boundary.
- [ ] A repository without `.obsidian-kb` completes the same workflows without
      creating the directory.
- [ ] A KB refresh failure blocks or clearly marks the owning workflow as
      failed and names the recovery command.
- [ ] Focused lifecycle tests cover present-KB, absent-KB, archive, follow-up,
      and refresh-failure cases.
- [ ] Shipped template sources and installed mirrors remain byte-identical.
- [ ] The canonical repository checks pass with KB freshness enabled.

## Out of Scope

- Changing the files or categories included in the generated KB.
- Replacing the existing KB generator or full-check freshness contract.
- Modifying upstream Trellis task lifecycle behavior.

## Notes

- Origin: audit finding A-035 in `.trellis/audit/report-2026-07-19.md`.
- This is a lightweight, pack-owned lifecycle integration task and may remain
  PRD-only unless implementation research reveals a new cross-command contract.
