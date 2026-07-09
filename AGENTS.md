<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## Maintainer Rules

- Do not create pull requests in the upstream `Trellis` repository without
  explicit approval from the user for that specific upstream PR. If
  `sd-ai-command-pack` work uncovers a `Trellis`-owned change, document the
  finding and provide a paste-ready handoff instead of opening a `Trellis` PR.
- Treat `templates/**` as the source of truth for shipped pack payloads.
  Root-level installed copies for platform directories present in this source
  checkout are byte-verified mirrors; when changing a shipped script, skill,
  prompt, command, or guide, update the template side first and keep the
  installed copy synchronized.
