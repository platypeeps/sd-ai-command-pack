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
- At the planning convergence boundary, follow
  [docs/planning-adversarial-review-codex.md](docs/planning-adversarial-review-codex.md)
  in addition to the shipped planning contract. It adds a second, independent
  Codex review lane and amends sections 3 through 5 of that contract. It is
  deliberately unshipped — no `manifest.json` row, nothing under `templates/` —
  because a shipped file invoking the `codex` CLI registers as undeclared codex
  usage in every consumer. The lane applies to this repository only.
- Treat `templates/**` as the source of truth for shipped pack payloads.
  Root-level installed copies for platform directories present in this source
  checkout are byte-verified mirrors; when changing a shipped script, skill,
  prompt, command, or guide, update the template side first and keep the
  installed copy synchronized.

## Contributor Entry Points

- Read [CONTRIBUTING.md](CONTRIBUTING.md), then run `make check` before
  publishing a change.
- Read `.trellis/spec/frontend/adapter-guidelines.md` before changing commands,
  prompts, skills, or platform adapters.
- Read `.trellis/spec/backend/manifest-and-filesystem.md` before changing the
  installer, manifest, provenance, audit, or filesystem behavior.

<!-- SD-AI-COMMAND-PACK:ROUTING:START -->
## Canonical Entry Points

The SD AI Command Pack wraps several Trellis workflows. Where a wrapper
exists, it is the canonical entry point: it carries the pack's own gates,
review loop, and completion bookkeeping, and the underlying Trellis command
does not. Reaching past a wrapper to the command it wraps skips those.

Route by intent:

- **Publishing a branch, working its review, and merging it** — use the pack's
  ship workflow rather than invoking the create-PR, review, and merge steps
  separately. It sequences them and owns the stop-points between them.
- **Finishing a task** — use the pack's finish-work workflow. It produces the
  bookkeeping receipt the merge gate independently revalidates.
- **Merging** — go through the pack's housekeeping gate. It is the only merge
  authority; nothing else in the chain merges.
- **Reviewing changes locally before publishing** — use the pack's review
  workflow, which runs the deterministic checks the remote review assumes.
- **Anything with no pack wrapper** — use the Trellis command directly. The
  pack adds surfaces; it does not replace Trellis.

To see which wrappers this repository actually has, list the installed skills
rather than relying on a list written down somewhere: they are the pack's
`sd-*` skills, and the pack's own help surface enumerates them at runtime.

The pack verifies that this block matches the version it shipped — `install.py
<repo> --check` reports `refresh-required` if the text between the markers
drifts. It does **not** verify the routing against this repository's installed
skills, and deliberately names none: the block routes by intent so that there
is nothing in it that a later release or a thin conversion could make false.

Managed by the SD AI Command Pack. Edits outside this block are preserved;
edits inside it are replaced on the next install.
<!-- SD-AI-COMMAND-PACK:ROUTING:END -->
