---
description: Run the Trellis start workflow.
---

# Start

Run the Trellis start workflow for the current repository.

1. Read `.agents/skills/trellis-start/SKILL.md`.
2. If that skill file is missing or unreadable, stop and report that the
   Trellis start skill is unavailable.
3. Follow that skill exactly to load compact Trellis session context, inspect
   the current task/workflow state, and classify the next action.
4. Report the selected next action, whether a Trellis task is active or should
   be considered, plus any missing context or blockers the skill identifies.
