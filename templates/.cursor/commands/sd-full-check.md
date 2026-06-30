---
description: Run the SD full-check gate.
---

# Full Check

Run the SD full-check gate for the current repository.

1. Read `.agents/skills/sd-full-check/SKILL.md`.
2. Follow that skill exactly: run `bash scripts/sd-ai-command-pack-full-check.sh`, report
   deterministic check results, local Prism review status, optional Gito status,
   and any skipped checks.
3. Do not edit, stage, commit, or push files unless the user separately asks for
   fixes.
