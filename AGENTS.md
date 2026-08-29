# sd-ai-command-pack

Instructions for AI assistants working in this repository.

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
- `templates/**` holds the one copy of every shipped pack payload. The
  repository no longer installs itself, so there are no root-level rendered
  copies to keep synchronized: change the template and you have changed the
  only copy.

## Contributor Entry Points

- Read [CONTRIBUTING.md](CONTRIBUTING.md), then run `make check` before
  publishing a change.
- Read [docs/spec/frontend/adapter-guidelines.md](docs/spec/frontend/adapter-guidelines.md)
  before changing commands, prompts, skills, or platform adapters.
- Read [docs/spec/backend/manifest-and-filesystem.md](docs/spec/backend/manifest-and-filesystem.md)
  before changing the installer, manifest, provenance, audit, or filesystem
  behavior.
- Planning artifacts live in [docs/work](docs/work/README.md): one directory per
  item, `prd.md` plus `design.md`/`implement.md` when warranted. That directory
  is the whole tracked footprint of the workflow.

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
