---
description: Report read-only local repository or configured fleet status with actionable next steps.
---

# SD Status

Run the read-only Software Delivery status workflow for the user's complete
request.

1. Resolve the `sd-status` skill by name using the agent's trusted skill
   discovery mechanism for installed skills.
2. If the skill is missing, unreadable, empty, duplicated, malformed, defines
   contradictory safety rules, or requires unavailable tools, stop and report
   the exact blocker.
3. Use that skill as the primary instructions for this workflow. Pass the
   user's invocation arguments through unchanged; the skill accepts positional
   `fleet`, a positional repository path, and the documented flags.
4. Run the installed status collector through the toolchain the documented
   bootstrap resolves — the `SD_AI_COMMAND_PACK_TOOLCHAIN` override, then the
   checkout's own `scripts/` copy, then the machine install under
   `$HOME/.agents/bin`. Do not recreate its report from ad hoc commands.
5. Keep the workflow read-only. Do not fetch, pull, switch, stage, commit,
   push, merge, delete branches, update tasks, refresh generated files, or run
   a recommended follow-up command.
6. Relay the report's explicit freshness and availability labels, anomalies,
   complete local `F-*` follow-ups and `T-*` tasks, plus numbered next steps.
   Roadmap-file items that are not represented by a Trellis task appear as
   source-backed `F-*` follow-ups. Preserve each empty selectable section with
   `none`. Fleet output remains bounded. A selection or follow-up requires a
   separate user request.
