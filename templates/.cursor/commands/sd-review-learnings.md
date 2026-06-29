---
description: Detect and update repo review learnings.
---

# Review Learnings

Detect and update repo-specific review learnings from local diff patterns and
recent PR review feedback.

1. Read `.agents/skills/sd-review-learnings/SKILL.md`.
2. Follow that skill exactly.
3. Prefer `python3 scripts/sd-ai-command-pack-review-learnings.py --base origin/main --include-working-tree` for the local scan.
4. Use `--update` only when the user asks to record or refresh the repo learning file.
