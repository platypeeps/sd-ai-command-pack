---
description: Run the SD local review loop.
mode: agent
---

# Local Review

Run the SD local review loop for the current repository.

1. Read `.agents/skills/sd-review-local/SKILL.md`.
2. Follow that skill exactly: run the requested local review tools through
   `scripts/sd-ai-command-pack-review-local.sh`, defaulting to Prism plus Gito,
   and support a specific configured review tool when the user names one.
3. Present grouped findings and ask which items to fix before editing.
4. Fix only selected findings, run the relevant checks, then repeat the same
   local review tool stack.
5. Stop when no findings remain or the user selects no more items to fix, and
   report tools run, fixes made, skipped findings, checks, and final tree state.
