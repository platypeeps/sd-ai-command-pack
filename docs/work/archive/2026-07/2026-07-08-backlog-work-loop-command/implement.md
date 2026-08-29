# Implementation Plan: Backlog Work Loop Command

## Steps

1. Add the shared skill:
   - create `templates/.agents/skills/sd-work-backlog/SKILL.md`
   - include safety rules, selection/ranking, loop steps, parking, and final
     report expectations
   - make sequential execution explicit: exactly one task per iteration, no
     next task until the current task is completed, parked, or stopped
   - include a follow-up/learning ledger step before the loop advances
   - copy it to `.agents/skills/sd-work-backlog/SKILL.md` for this repo's
     dogfooded command surface
2. Add thin platform adapters:
   - Claude, Cursor, Gemini, GitHub Copilot, and OpenCode templates
   - dogfood adapters for installed platforms present in this repo when
     applicable
3. Update `manifest.json`:
   - shared skill installed always
   - platform adapter entries parallel to existing `sd-create-pr` and
     `sd-housekeeping`
   - native skill/workflow mappings for platforms that reuse shared skills or
     Cursor-style adapters
4. Update documentation:
   - README command list and workflow section
   - `docs/SD_AI_COMMAND_PACK.md`
   - `templates/docs/SD_AI_COMMAND_PACK.md`
5. Update tests:
   - installer expected-file assertions
   - adapter-reference assertions
   - shared-skill content assertions
   - assertions that the shared skill mentions sequential one-task iteration
     and follow-ups/learnings being addressed or recorded as tasks
6. Refresh generated KB through `sd-update-spec` helper if docs/specs changed.
7. Validate:
   - focused installer tests around command/adapters
   - `python3 -m unittest discover -s tests`
   - `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh`

## Risk Points

- `manifest.json` contains many platform-specific mappings; use existing
  command entries as the pattern and verify through tests.
- The command is intentionally powerful. Keep all merge/publish details
  delegated to existing commands and document stop conditions clearly.
- Generated `.obsidian-kb/` must be refreshed after docs/skill changes or the
  full-check KB lane will fail.

## Rollback

If implementation proves too broad, keep only the shared skill and core five
adapters in the first PR, then file a follow-up for extended platform mappings.
